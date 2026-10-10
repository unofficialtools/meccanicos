"""mos, mos-config and mos-doctor (modules/mos-cli.nix sets MECCANICOS_PROG).

`mos` lists every mos-* command; type mos- and press Tab to see them
too. Each one answers -h / --help. `mos help [TOPIC]` opens the offline Help
(modules/help.nix): the overview, or the manual at TOPIC; over SSH, the manual
in the terminal.
"""

import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as c  # noqa: E402

# Every MeccanicOS command, what it is for (shown by `mos` when it is installed).
COMMANDS = [
    ("Fix and set up", [
        ("mos-doctor", "find and fix problems: Wi-Fi, Bluetooth, sound, display, disk"),
        ("mos-config", "common settings in one place; export them to another computer"),
        ("mos-ai-setup", "set up the AI (a local model, or Claude, ChatGPT, Grok)"),
        ("mos-unlock", "ways to unlock the encrypted disk (TPM, key, remote)"),
    ]),
    ("Apps and files", [
        ("mos-apps", "find, try, install and remove apps"),
        ("mos-open", "open any file with the right app (also: open)"),
        ("mos-print", "print a file, or save it as PDF (also: print)"),
        ("mos-printers", "printers: add them, pick the default, see and cancel the queue"),
        ("mos-logins", "who logged in or tried; block, stop SSH, disconnect / reconnect"),
        ("mos-vault", "encrypted vaults and a persistent home on the USB stick"),
        ("mos-backup", "back up your home, encrypted"),
        ("mos-dropbox", "Dropbox in a folder"),
        ("mos-passwords", "your passwords (gopass)"),
    ]),
    ("Desktop", [
        ("mos-ask", "the command bar (Super+Space)"),
        ("mos-keys", "every keyboard shortcut (shortcuts in the command bar)"),
        ("mos-screenshot", "take a screenshot"),
        ("mos-read", "read the copied text aloud"),
        ("mos-say", "say something aloud (also: say)"),
        ("mos-ai", "ask the AI from the terminal"),
        ("mos-about", "this computer and MeccanicOS"),
    ]),
    ("System", [
        ("mos-updates", "updates in one place: system and apps, and how to go back"),
        ("mos-upgrade", "update to the newest MeccanicOS and NixOS packages (also mos-update)"),
        ("mos-rebuild", "apply changes made in /etc/nixos"),
        ("mos-install", "install MeccanicOS on this computer (live USB)"),
        ("mos-gpu-driver", "which graphics driver this computer uses"),
    ]),
]


def index():
    version = open("/etc/meccanicos/version").read().split()[0] if os.path.exists("/etc/meccanicos/version") else ""
    print(f"{c.NAME} {version}".strip() + " commands (each one: --help)\n")
    width = max(len(n) for _, cmds in COMMANDS for n, _ in cmds)
    for group, cmds in COMMANDS:
        here = [(n, d) for n, d in cmds if shutil.which(n)]
        if here:
            print(group)
            for n, d in here:
                print(f"  {n:<{width}}  {d}")
            print()
    print("Start with: mos-doctor (something isn't working) or mos-config (change a setting).")
    print("The manual: mos help [TOPIC], e.g. mos help backups.")
    return 0


HELP = f"/run/current-system/sw/share/{os.environ.get('MECCANICOS_ID', 'meccanicos')}/help"


def slug(heading):
    """The anchor pandoc (and GitHub) give a heading: "Updates — `mos-updates`" -> "updates--mos-updates"."""
    s = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return s.replace(" ", "-")


def find_heading(topic):
    """The README heading for TOPIC (any case): the first heading with words
    starting like TOPIC's, else the section whose text mentions it most."""
    words = topic.lower().replace("-", "").split()  # wifi finds Wi-Fi
    sections, fenced = [], False  # [heading, text], outside ``` code blocks
    for line in open(f"{HELP}/README.md", encoding="utf-8"):
        if line.startswith("```"):
            fenced = not fenced
        m = None if fenced else re.match(r"#{1,4} (.+)", line)
        if m:
            sections.append([m.group(1).strip(), ""])
        elif sections:
            sections[-1][1] += line.lower().replace("-", "")
    has = lambda text: all(re.search(r"\b" + re.escape(w), text) for w in words)  # noqa: E731
    for heading, _ in sections:
        if has(heading.lower().replace("-", "")):
            return heading
    counts = [(sum(len(re.findall(r"\b" + re.escape(w), text)) for w in words), heading)
              for heading, text in sections if has(text)]
    return max(counts)[1] if counts else None


def show_help(topic):
    if not os.path.isdir(HELP):
        print(f"mos help: the Help is not on this system ({HELP})", file=sys.stderr)
        return 1
    heading = find_heading(" ".join(topic)) if topic else None
    if topic and not heading:
        print(f"mos help: nothing about '{' '.join(topic)}' in the manual; the topics are its headings.",
              file=sys.stderr)
    graphical = os.environ.get("DISPLAY") and not os.environ.get("SSH_CONNECTION")
    if graphical:
        # The browser, not xdg-open: a file:// address with ?version and #topic.
        url = f"file://{HELP}/manual.html"
        if os.path.exists("/etc/meccanicos/version"):
            url += "?v=" + open("/etc/meccanicos/version").read().split()[0]
        if heading:
            url += "#" + slug(heading)
        browser = shutil.which("brave") or shutil.which("xdg-open")
        subprocess.Popen([browser, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return 0
    if not sys.stdout.isatty():
        # Into a pipe or a file: plain text, from the topic on.
        lines = open(f"{HELP}/README.md", encoding="utf-8").readlines()
        start = next((i for i, line in enumerate(lines)
                      if heading and line.startswith("#") and line.strip("# \n") == heading), 0)
        try:
            sys.stdout.writelines(lines[start:])
            sys.stdout.flush()
        except BrokenPipeError:  # e.g. | head: the reader has had enough
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    # A terminal: the README, coloured when bat is there, at the topic.
    # (bat colours the line, so less looks for the heading's words, not its "#".)
    pager = ["less", "-R"] + ([f"+/{re.escape(heading.split('`')[0].strip())}"] if heading else [])
    if shutil.which("bat"):
        show = subprocess.Popen(["bat", "--style=plain", "--color=always", "--language=markdown",
                                 f"{HELP}/README.md"], stdout=subprocess.PIPE)
        subprocess.run(pager, stdin=show.stdout)
        show.wait()
    else:
        subprocess.run(pager + [f"{HELP}/README.md"])
    return 0


def main():
    prog = os.environ.get("MECCANICOS_PROG", "mos")
    argv = sys.argv[1:]
    try:
        if prog == "config":
            import config
            return config.main(argv)
        if prog == "doctor":
            import doctor
            return doctor.main(argv)
        if argv and argv[0] == "help":
            return show_help(argv[1:])
        if argv and argv[0] not in ("-h", "--help"):
            print(f"mos: unknown command {argv[0]} (the commands are mos-*; run mos to list them)",
                  file=sys.stderr)
            return 2
        return index()
    except c.UsageError as e:
        print(f"mos-{prog}: {e}", file=sys.stderr)
        return 2
    except c.Failed as e:
        print(f"mos-{prog}: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
