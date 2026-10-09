#!/usr/bin/env python3
"""mos-updates - what can be updated, and how to undo it, in one place.

  mos-updates           the full-screen view: check, update, go back
  mos-updates status    the same, as plain text

System (MeccanicOS + NixOS), installed: mos-update --check shows what would
change, mos-update updates (--boot: at the next restart), mos-upgrade
refreshes the NixOS packages. Every update keeps the system before it:
"Go back" runs sudo nixos-rebuild switch --rollback, and older systems are
in the boot menu. On the live USB the system is updated by writing a newer
ISO to the stick; the vaults on it are kept.

Your apps (apps, your own Nix profile): apps update, apps undo.
Nothing changes without asking first; changes run in the terminal so you
see what they do.
"""

import curses
import glob
import json
import locale
import os
import re
import shutil
import subprocess
import sys
import time

# The look shared by MeccanicOS TUIs: MECCANICOS_PYLIB from the Nix wrapper, else next to this file.
sys.path.insert(0, os.environ.get("MECCANICOS_PYLIB") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import mos_tui as ui  # noqa: E402

NAME = os.environ.get("MECCANICOS_NAME", "MeccanicOS")
ID = os.environ.get("MECCANICOS_ID", "meccanicos")
REPO = os.environ.get("MECCANICOS_REPO", "https://github.com/unofficialtools/meccanicos")
ROOT = os.environ.get("MECCANICOS_ROOT", "")  # testing: read /etc, /nix, /run under this folder
NIXOS_DIR = ROOT + os.environ.get("MECCANICOS_NIXOS_DIR", "/etc/nixos")
PROFILES = ROOT + "/nix/var/nix/profiles"
UNKNOWN = "unknown"


def installed():
    """An installed system (vs the live USB), as scripts/mos/common.py decides."""
    if "MECCANICOS_LIVE" in os.environ:
        return os.environ["MECCANICOS_LIVE"] != "1"
    return os.path.exists(os.path.join(NIXOS_DIR, "flake.nix"))


def read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def output(*cmd, timeout=5):
    """A program's output, or "" if it is missing or failed."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return p.stdout.strip() if p.returncode == 0 else ""


def when(t):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t)) if t else UNKNOWN


def os_release(root=""):
    data = {}
    for line in read(root + "/etc/os-release").splitlines():
        k, _, v = line.partition("=")
        data[k] = v.strip().strip('"')
    return data


# ---- the system --------------------------------------------------------------------
def build(root=ROOT):
    """When this MeccanicOS was built ("2026-10-06 17:23 UTC"), or unknown."""
    return read(f"{root}/etc/{ID}/version") or UNKNOWN


def nixos(root=ROOT):
    rel = os_release(root)
    return rel.get("BUILD_ID") or rel.get("VERSION") or rel.get("VERSION_ID") or UNKNOWN


def generations():
    """[{n, time, build, nixos, path}] of the system, oldest first (installed)."""
    gens = []
    for link in glob.glob(os.path.join(PROFILES, "system-*-link")):
        m = re.fullmatch(r"system-(\d+)-link", os.path.basename(link))
        if not m:
            continue
        try:
            t = os.lstat(link).st_mtime
            path = os.path.realpath(link)
        except OSError:
            continue
        gens.append({"n": int(m.group(1)), "time": t, "path": path,
                     "build": read(f"{link}/etc/{ID}/version") or UNKNOWN,
                     "nixos": read(f"{link}/nixos-version") or UNKNOWN})
    return sorted(gens, key=lambda g: g["n"])


def gen_number(name):
    """profile-42-link -> 42, or None."""
    m = re.search(r"-(\d+)-link$", name)
    return int(m.group(1)) if m else None


def profile_gen(link):
    """The generation a profile points at (system -> system-42-link), or None."""
    try:
        return gen_number(os.readlink(link))
    except OSError:
        return None


def auto_updates():
    """(on, last run): the weekly mos-auto-upgrade timer (modules/installed.nix)."""
    on = any(os.path.exists(ROOT + d + "/mos-auto-upgrade.timer")
             for d in ("/etc/systemd/system", "/run/current-system/etc/systemd/system"))
    if not on:
        return False, ""
    last = output("systemctl", "show", "mos-auto-upgrade.timer", "-p", "LastTriggerUSec", "--value")
    result = output("systemctl", "show", "mos-auto-upgrade.service", "-p", "Result", "--value")
    if not last or last == "n/a":
        return True, "not run yet" if last else UNKNOWN
    return True, last + ("" if result in ("", "success") else " (it failed: journalctl -u mos-auto-upgrade)")


def nixpkgs_date():
    """When the NixOS packages in /etc/nixos/flake.lock were published."""
    try:
        with open(os.path.join(NIXOS_DIR, "flake.lock")) as f:
            lock = json.load(f)
        nodes = lock["nodes"]
        name = nodes[lock.get("root", "root")]["inputs"]["nixpkgs"]
        return when(nodes[name if isinstance(name, str) else name[0]]["locked"]["lastModified"])
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return UNKNOWN


# ---- your apps ---------------------------------------------------------------------
def apps_profile():
    if os.environ.get("APPS_PROFILE"):
        return os.environ["APPS_PROFILE"]
    state = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    for p in (os.path.join(state, "nix/profiles/profile"), os.path.expanduser("~/.nix-profile")):
        if os.path.lexists(p):
            # ~/.nix-profile -> the profile itself (the one with profile-N-link next to it)
            target = os.readlink(p) if os.path.islink(p) else ""
            if target and not target.startswith("/nix/store/") and "-link" not in target:
                p = os.path.join(os.path.dirname(p), target)
            return p
    return ""


def apps():
    """(how many apps you installed or None, last change time, can undo)."""
    profile = apps_profile()
    if not profile:
        return 0, 0, False
    try:
        with open(os.path.join(profile, "manifest.json")) as f:
            count = len(json.load(f).get("elements", []))
    except FileNotFoundError:
        count = 0  # a profile from nix-env, or empty
    except (OSError, ValueError, AttributeError):
        count = None
    n = profile_gen(profile)
    links = glob.glob(os.path.join(os.path.dirname(profile), os.path.basename(profile) + "-*-link"))
    try:
        t = os.lstat(os.path.join(os.path.dirname(profile), os.readlink(profile))).st_mtime
    except OSError:
        t = 0
    return count, t, n is not None and any((gen_number(l) or n) < n for l in links)


# ---- everything, for both views ----------------------------------------------------------
class Action:
    def __init__(self, label, cmd, about, ask="", yes="Yes", sudo=False):
        self.label, self.cmd, self.about = label, cmd, about
        self.ask, self.yes = ask, yes  # the question asked first ("" = changes nothing), its yes button
        self.sudo = sudo  # run with sudo (mos-update, mos-upgrade and apps see to it themselves)


class Note(str):
    """A line shown dimmed: help rather than state."""


def report():
    """[(heading, [line or Action])]: what the views show."""
    sections = []
    live = not installed()
    if live:
        sections.append((f"System ({NAME} + NixOS) — live USB", [
            f"{NAME:<11} built {build()}",
            f"{'NixOS':<11} {nixos()}",
            "",
            "The live system is updated by writing a newer ISO to the stick:",
            f"  download it from {REPO}/releases/tag/latest",
            "  and write it as before (README: \"Updating the stick later\"; with Ventoy,",
            "  replace the .iso file). Vaults and the persistent home on the stick are kept;",
            "  if they don't show up, usb-vault recover. To be safe first: usb-vault backup DIR.",
        ]))
    else:
        gens = generations()
        current = os.path.realpath(ROOT + "/run/current-system")
        nxt = profile_gen(os.path.join(PROFILES, "system"))
        on, last = auto_updates()
        commit = read(os.path.join(NIXOS_DIR, ".mos-commit"))
        lines = [
            f"{NAME:<11} built {build()}" + (f", commit {commit}" if commit else ""),
            f"{'NixOS':<11} {nixos()}, packages from {nixpkgs_date()}",
            f"{'Automatic':<11} " + (f"on: weekly, applied at the next start; last run {last}" if on
                                     else "off (turn on: mos-config set updates.auto on)"),
            f"{'Changed':<11} last {when(max((g['time'] for g in gens), default=0))}",
        ]
        if gens and nxt is not None and os.path.realpath(os.path.join(PROFILES, "system")) != current:
            lines.append(f"{'Waiting':<11} a newer system is ready: restart to use it")
        lines.append("")
        lines += [
            Action("Check for updates", ["mos-update", "--check"], f"what the newest {NAME} would change (changes nothing)"),
            Action("Update now", ["mos-update"], f"download the newest {NAME} and switch to it",
                   ask=f"Update to the newest {NAME} now?\nIt downloads it, rebuilds the system and switches to it.\n"
                       "The system before stays in the boot menu.", yes="Update"),
            Action("Update at next restart", ["mos-update", "--boot"], "the same, used from the next start",
                   ask=f"Update to the newest {NAME} at the next restart?\nIt downloads and builds it now; "
                       "your running system does not change.", yes="Update"),
            Action("Refresh NixOS packages", ["mos-upgrade"], f"newer packages, same {NAME} (mos-upgrade)",
                   ask=f"Get the newest NixOS packages and switch to them?\nSame {NAME}; "
                       "the system before stays in the boot menu.", yes="Refresh"),
        ]
        sections.append((f"System ({NAME} + NixOS)", lines))

        undo = []
        if not gens:
            undo.append(f"Earlier systems: {UNKNOWN}")
        for g in gens[-6:]:
            mark = []
            if g["path"] == current:
                mark.append("running")
            if g["n"] == nxt:
                mark.append("next start")
            undo.append(f"{g['n']:>4}  {when(g['time'])}  {NAME} {g['build']:<22} NixOS {g['nixos']}"
                        + (f"  ← {', '.join(mark)}" if mark else ""))
        if len(gens) > 6:
            undo.append(f"      … {len(gens) - 6} older (all of them: nixos-rebuild list-generations)")
        prev = max((g["n"] for g in gens if nxt is not None and g["n"] < nxt), default=None)
        undo.append("")
        if prev is not None:
            undo.append(Action("Go back to the previous system", ["nixos-rebuild", "switch", "--rollback"],
                               f"switch to system {prev} (sudo nixos-rebuild switch --rollback)",
                               ask=f"Go back to system {prev} and switch to it now?\n"
                                   "Your files in /etc/nixos stay as they are: the next update or\n"
                                   "mos-rebuild builds them again (mos-update keeps the previous ones\n"
                                   "in /etc/nixos.previous).", yes="Go back", sudo=True))
        undo.append(Note("Older systems are also in the boot menu: pick one when the computer starts."))
        sections.append(("Undo — earlier systems", undo))

    count, t, can_undo = apps()
    lines = [f"{'Installed':<11} " + (UNKNOWN if count is None else f"{count} app{'s' if count != 1 else ''}")
             + (f", last change {when(t)}" if t else "") + " (apps list)"]
    if live:
        lines.append(f"{'':<11} on the live USB they last until shutdown, even with a persistent home")
    lines += [
        "",
        Action("Update all apps", ["apps", "update"], "the newest versions of the apps you installed",
               ask="Update all the apps you installed?\napps undo puts them back.", yes="Update"),
        Action("Undo the last change to your apps", ["apps", "undo"], "the last install, removal or update"
               + ("" if can_undo else " (nothing to undo yet)"),
               ask="Undo the last install, removal or update of your apps?", yes="Undo"),
        Action("Manage apps", ["apps", "manage"], "find, install and remove apps"),
        Note(f"{NAME}'s own apps are updated with the system."),
    ]
    sections.append(("Apps — yours", lines))
    return sections


def status():
    for heading, lines in report():
        print(heading)
        for line in lines:
            if isinstance(line, Action):
                cmd = ("sudo " if line.sudo else "") + " ".join(line.cmd)
                print(f"  {line.label + ':':<36} {cmd}")
            else:
                print(f"  {line}".rstrip())
        print()
    return 0


# ---- full screen -----------------------------------------------------------------------
class App:
    def __init__(self, scr):
        self.scr = scr
        self.sel = 0
        self.msg, self.err = "", False
        self.load()

    def load(self):
        self.lines = []  # (text, role, Action or None)
        for heading, lines in report():
            self.lines.append((heading, ui.HEADING, None))
            for line in lines:
                if isinstance(line, Action):
                    self.lines.append((line.label, ui.NORMAL, line))
                else:
                    self.lines.append((line, ui.DIM if isinstance(line, Note) else ui.NORMAL, None))
            self.lines.append(("", ui.NORMAL, None))
        self.actions = [i for i, (_, _, a) in enumerate(self.lines) if a]
        self.sel = min(self.sel, len(self.actions) - 1)

    def draw(self):
        s = self.scr
        s.erase()
        h, w = s.getmaxyx()
        if h < 12 or w < 60:
            ui.put(s, 0, 0, "Make the window larger.")
            s.refresh()
            return
        ui.bar(s, 0, f"Updates — {NAME}", "installed" if installed() else "live USB")
        body = h - 4
        cur = self.actions[self.sel] if self.actions else 0
        top = max(0, min(cur - body // 2, len(self.lines) - body))
        width = max(len(a.label) for a in (self.lines[i][2] for i in self.actions)) + 4 if self.actions else 0
        for y, (text, role, a) in enumerate(self.lines[top: top + body], start=1):
            if a:
                ui.row(s, y, 2, width, f" ▸ {a.label}", top + y - 1 == cur)
                ui.put(s, y, width + 4, a.about, ui.attr(ui.DIM))
            else:
                ui.put(s, y, 2 if role == ui.HEADING else 4, text, ui.attr(role))
        ui.message(s, h - 2, 1, ("✗ " if self.err and not self.msg.startswith("✗") else "") + self.msg)
        ui.keybar(s, h - 1, [("↑↓", "move"), ("Enter", "do it"), ("r", "reload"), ("q", "quit")])
        s.refresh()

    def outside(self, a):
        """Run an action on the plain terminal (its progress shows), then back."""
        cmd = (["sudo"] if a.sudo and os.geteuid() != 0 else []) + a.cmd
        curses.def_prog_mode()
        curses.endwin()
        print(f"\n== {a.label}: {' '.join(cmd)} ==\n", flush=True)
        try:
            code = subprocess.run(cmd).returncode
        except OSError as e:
            print(e)
            code = 127
        except KeyboardInterrupt:
            code = 130
        print("\n" + ("\033[38;5;114mDone.\033[0m" if code == 0 else f"\033[38;5;203mThat did not work (exit {code}, see above).\033[0m")
              + " Press Enter to go back.", end="", flush=True)
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
        curses.reset_prog_mode()
        self.scr.clear()
        self.load()
        self.msg, self.err = (f"✓ {a.label}: done", False) if code == 0 else (f"✗ {a.label}: did not work", True)

    def press(self):
        if not self.actions:
            return
        a = self.lines[self.actions[self.sel]][2]
        if not shutil.which(a.cmd[0]):
            self.msg, self.err = f"✗ {a.cmd[0]} is not on this system.", True
            return
        if a.ask and not ui.confirm(self.scr, a.ask, yes=a.yes, title=a.label):
            self.msg, self.err = "Nothing changed.", False
            return
        self.outside(a)

    def run(self):
        while True:
            self.draw()
            k = self.scr.get_wch()
            if k in (curses.KEY_UP, "k"):
                self.sel = max(0, self.sel - 1)
            elif k in (curses.KEY_DOWN, "j", "\t"):
                self.sel = min(len(self.actions) - 1, self.sel + 1)
            elif k in ui.ENTER:
                self.press()
            elif k in (ui.ESC, "q"):
                return
            elif k == "r":
                self.load()
                self.msg, self.err = "reloaded", False


def main(argv):
    if argv and argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    if argv and argv[0] == "status":
        return status()
    if argv:
        print(f"mos-updates: unknown command '{argv[0]}' (mos-updates --help)", file=sys.stderr)
        return 2
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return status()  # no terminal to draw on: the text
    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")
    try:
        curses.wrapper(lambda scr: (ui.init(), App(scr).run()))
    except curses.error:  # a terminal curses can't drive: the text
        return status()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:  # Ctrl+C: curses.wrapper has restored the terminal
        sys.exit(130)
