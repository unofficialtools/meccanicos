#!/usr/bin/env python3
"""mos-tour - a spoken tour of MeccanicOS that plays by itself: the ideas behind
it, then a demo it performs on the desktop (command bar, terminal, yazi,
pictures, opening and printing files, the trash, reading aloud,
nix-shell, apps for one folder, settings, the doctor), and previews of the persistent home, the installer and the Apps Manager. It is
filmed in a VM as the tutorial video (modules/tutorial-recorder.nix).

  mos-tour                    play the tour
  mos-tour N                  start at step N
  mos-tour --record CUES      for the video: no key hints; each spoken line
                                goes to CUES as "start<TAB>seconds<TAB>text",
                                waits to leave out as "cut<TAB>start<TAB>end"

Keys (in the tour's window): Space pause · ←/→ previous/next step ·
R replay the step · M voice on/off · Q quit

Only one tour runs at a time. Closing its window stops it, its voice and the
windows it opened. Every claim it makes about MeccanicOS is backed by the
configuration; the comment next to each one says where.
"""

import curses
import fcntl
import hashlib
import re
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

SAY = os.environ.get("MECCANICOS_TUTORIAL_SAY", "say")
SAMPLES = os.environ.get("MECCANICOS_TUTORIAL_SAMPLES", "")
NAME = os.environ.get("MECCANICOS_NAME", "MeccanicOS")
HOME = os.path.expanduser("~")
DIR = os.path.join(HOME, "Tutorial")
LOCK = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "mos-tutorial.lock")
TYPE_DELAY = 90  # ms between typed keys


# ---- the desktop ---------------------------------------------------------------
def xdo(*args, wait=True):
    try:
        if wait:
            return subprocess.run(["xdotool", *args], capture_output=True, text=True, timeout=10).stdout
        return subprocess.Popen(["xdotool", *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return "" if wait else None


def windows(cls):
    """Visible windows whose WM_CLASS matches cls (case-insensitive regex)."""
    return set(xdo("search", "--onlyvisible", "--class", cls).split())


def close_window(wid):
    try:
        subprocess.run(["wmctrl", "-i", "-c", hex(int(wid))], capture_output=True, timeout=3)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass


def center(wid):
    """Move a window to the middle of the screen (for the video: Xfce places
    new windows before they grow to the recorder's larger font, some half off-screen)."""
    time.sleep(0.5)  # let it reach its final size
    try:
        sw, sh = map(int, xdo("getdisplaygeometry").split())
        geo = dict(l.split("=", 1) for l in xdo("getwindowgeometry", "--shell", wid).split())
        w, h = int(geo["WIDTH"]), int(geo["HEIGHT"])
    except (ValueError, KeyError):
        return
    xdo("windowmove", wid, str(max(0, (sw - w) // 2)), str(max(40, (sh - h) // 2)))


def running(pattern):
    try:
        return subprocess.run(["pgrep", "-u", str(os.getuid()), "-f", pattern], capture_output=True, timeout=3).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0


def prepare_samples():
    """~/Tutorial as new: a picture, a short video and two text files."""
    os.makedirs(DIR, exist_ok=True)
    if SAMPLES and os.path.isdir(SAMPLES):
        for f in os.listdir(SAMPLES):
            dst = os.path.join(DIR, f)
            if os.path.exists(dst):
                os.remove(dst)
            shutil.copy(os.path.join(SAMPLES, f), dst)
            os.chmod(dst, 0o644)
    try:
        os.remove(os.path.join(DIR, "notes.pdf"))
    except OSError:
        pass


# ---- the steps -------------------------------------------------------------------
# A step is a title, its bullets and a play(t) generator: it yields "wait
# until" predicates made by the Tour (t.say, t.key, t.type, t.until, ...).
# A bullet is "text", or ("text shown", "text spoken").
def step(title, bullets, play=None, mock=None):
    return {"title": title, "bullets": bullets, "play": play or talk, "mock": mock}


def spoken(bullet):
    return bullet[1] if isinstance(bullet, tuple) else bullet


def talk(t):
    for i in range(len(t.step["bullets"])):
        yield t.point(i)


def shortcuts(t):
    yield t.point(0)
    if not (yield from t.command_bar("shortcuts")):
        return
    yield t.key("Return", "Enter")
    yield t.until(lambda: windows("rofi"), 5)
    yield t.sleep(1)
    yield t.point(1)
    yield t.sleep(2)
    yield t.key("Escape", "Esc")
    yield t.sleep(1)


def command_bar(t):
    yield t.point(0)
    if not (yield from t.command_bar("browser")):
        return
    yield t.point(1)
    t.expect("brave")
    yield t.key("Return", "Enter")
    # Brave takes a while to start and to close: the video skips those waits.
    start = time.time() + 0.5
    yield from t.new_window("brave", 120)
    t.cut(start, time.time() - 0.3)
    # The page stays up for 4 seconds in the video too.
    shown = time.time()
    yield t.sleep(4)
    t.hold(shown, time.time())
    if t.last:
        brave = t.last
        yield t.key("super+q", "Super + Q", brave)
        start = time.time() + 0.3
        yield t.until(lambda: brave not in windows("brave"), 20)
        t.cut(start, time.time() - 0.2)
        t.forget(brave)
    yield t.sleep(1)


def desktop_menu(t):
    yield t.point(0)
    yield t.click(960, 560, 3, "Right-click on the desktop")
    yield t.sleep(1.2)
    yield t.point(1)
    # Applications, the menu's last item (Up from the top wraps to it), opened.
    yield t.key("Up", "↑")
    yield t.sleep(0.6)
    yield t.key("Right", "→")
    yield t.sleep(4)
    yield t.key("Escape", "Esc")
    yield t.key("Escape", "Esc")
    t.park()
    yield t.sleep(1)


def terminal(t):
    yield t.point(0)
    yield from t.terminal()
    yield t.point(1)


def yazi(t):
    yield t.point(0)
    yield from t.yazi()
    for k in ("Down", "Down", "Down", "Up", "Up", "Up"):
        yield t.key(k, "↓" if k == "Down" else "↑", t.term)
        yield t.sleep(0.5)
    yield t.point(1)
    yield t.point(2)


def open_pdf(t):
    yield from t.shell()
    yield t.point(0)
    t.expect("evince")
    yield from t.command("open Tutorial/welcome.pdf")
    yield from t.new_window("evince")
    yield t.sleep(2.5)
    yield t.close(t.last)
    yield t.sleep(1)


def print_pdf(t):
    pdf = os.path.join(DIR, "notes.pdf")
    before = mtime(pdf)
    yield from t.shell()
    yield t.point(0)
    yield from t.command("print Tutorial/notes.txt")
    yield t.sleep(1.5)
    yield t.point(1)
    yield t.type("pdf", t.term)
    yield t.sleep(1)
    yield t.key("Return", "Enter", t.term)
    yield t.until(lambda: mtime(pdf) > before, 30)
    yield t.sleep(1)


def trash(t):
    yield from t.shell()
    yield t.point(0)
    yield from t.command("trash Tutorial/old-notes.txt")
    yield from t.command("ls Tutorial")
    yield t.sleep(1)
    yield t.point(1)
    yield from t.command("trash-restore Tutorial")
    yield t.sleep(1.5)
    yield t.type("0", t.term)
    yield t.key("Return", "Enter", t.term)
    yield t.sleep(1)
    yield from t.command("ls Tutorial")
    yield t.sleep(1.5)


def read_aloud(t):
    text = f"Hello! This is {NAME}, reading aloud the text you copied."
    yield t.point(0)
    t.copy(text)
    t.caption = f"Copied: “{text}”"
    yield t.sleep(2)
    yield t.point(1)
    if not (yield from t.command_bar("read clipboard")):
        return
    t.expect("mos-read")
    yield t.key("Return", "Enter")
    yield from t.new_window("mos-read", 20)
    # It closes its window when it has read everything.
    yield t.until(lambda: not windows("mos-read"), 60)


def nix_shell(t):
    # nix-shell runs bash with its own --rcfile once cowsay is there.
    ready = lambda: running("[-]-rcfile .*nix-shell")  # noqa: E731
    yield from t.shell()
    yield from t.command("clear")  # a clean terminal after the trash commands
    yield t.point(0)
    yield t.point(1)
    yield from t.command("nix-shell -p cowsay")
    t.caption = "Downloading cowsay…"
    yield t.until(lambda: ready() or not running("(^|/)nix-shell -p"), 300)
    if ready():
        yield t.point(2)
        yield from t.command(f"cowsay Hello from {NAME}!")
        yield t.sleep(2)
        yield t.point(3)
        yield from t.command("exit")
        yield t.point(4)
    else:
        t.caption = "No internet: cowsay can't be downloaded now."
        yield t.sleep(3)


def folder_apps(t):
    # mos-apps.py --here: .envrc `use nix -p`; shell.nix: direnv in every
    # shell; vscodium.nix: the direnv extension.
    yield from t.shell()
    yield t.point(0)
    yield from t.command("mkdir -p Tutorial/project && cd Tutorial/project")
    yield from t.command("apps install --here cowsay")
    t.caption = "Getting cowsay for this folder…"
    yield t.until(lambda: not running("mos-apps.py install"), 300)
    yield t.sleep(2)  # direnv loads it at the next prompt
    yield t.point(1)
    yield from t.command("cowsay This folder has its own apps")
    yield t.sleep(2)
    yield t.point(2)
    # Two commands: direnv unloads the folder's apps at the prompt in between.
    yield from t.command("cd ~")
    yield from t.command("cowsay Hello")
    yield t.sleep(2)
    yield t.point(3)
    # The last step in the terminal: close it.
    yield from t.command("exit")
    t.forget(t.term)
    t.term = None


def launcher(t, text):
    """Open a menu entry that runs in a terminal (mos-cli.nix) from the
    command bar; its window, or None."""
    if not (yield from t.command_bar(text)):
        return None
    t.expect("^xfce4-terminal$")
    yield t.key("Return", "Enter")
    yield from t.new_window("^xfce4-terminal$")
    return t.last


def settings(t):
    # mos-cli.nix: Configuration Management runs mos-config, full screen.
    yield t.point(0)
    win = yield from launcher(t, "configuration management")
    if not win:
        return
    yield t.sleep(2)
    yield t.point(1)
    yield t.point(2)
    # The clock: on the live USB the last setting but one (config.py SETTINGS).
    yield t.key("End", "End", win)
    yield t.key("Up", "↑", win)
    yield t.sleep(0.8)
    yield t.key("Return", "Enter", win)
    yield t.sleep(1)
    yield t.key("Down", "↓  12h", win)
    yield t.key("Return", "Enter", win)
    t.caption = "The clock in the top bar now shows 12-hour time."
    yield t.sleep(3)
    yield t.key("Return", "Enter", win)  # and back
    yield t.sleep(0.8)
    yield t.key("Up", "↑  24h", win)
    yield t.key("Return", "Enter", win)
    yield t.sleep(1)
    yield t.point(3)
    yield t.point(4)
    yield t.key("q", "q  (quit)", win)
    yield t.until(lambda: win not in windows("^xfce4-terminal$"), 5)
    yield t.close(win)


def doctor(t):
    # mos-cli.nix: Configuration Doctor runs mos-doctor, which checks every area.
    yield t.point(0)
    win = yield from launcher(t, "configuration doctor")
    if not win:
        return
    yield t.sleep(4)
    yield t.point(1)
    yield t.point(2)
    yield t.point(3)
    yield t.sleep(1)
    yield t.close(win)


def office(t):
    yield t.point(0)
    oo = None
    for n, text in ((1, "word processor"), (2, "spreadsheet"), (3, "presentations")):
        yield t.point(n)
        if not (yield from t.command_bar(text)):
            return
        start = time.time() + 0.5
        if oo is None:
            t.expect("ONLYOFFICE")
            yield t.key("Return", "Enter")
            yield from t.new_window("ONLYOFFICE", 120)
            oo = t.last
            if not oo:
                return
            yield t.sleep(6)  # the editor draws itself: left out of the video
        else:
            yield t.key("Return", "Enter")  # a new tab in the same window
            yield t.sleep(5)
        t.cut(start, time.time() - 2)
    yield t.point(4)
    if not (yield from t.command_bar("vscodium")):
        return
    start = time.time() + 0.5
    t.expect("vscodium")
    yield t.key("Return", "Enter")
    yield from t.new_window("vscodium", 120)
    code = t.last
    yield t.sleep(6)
    t.cut(start, time.time() - 2.5)
    yield t.point(5)
    for wid, cls in ((code, "vscodium"), (oo, "ONLYOFFICE")):
        if wid:
            yield t.close(wid)
            yield t.until(lambda: wid not in windows(cls), 8)
            yield t.sleep(0.5)
    # OnlyOffice may keep a window (another editor, or "save changes?"):
    # its documents are new and empty, so nothing is lost.
    for wid in windows("ONLYOFFICE"):
        close_window(wid)
    yield t.until(lambda: not windows("ONLYOFFICE"), 5)
    if windows("ONLYOFFICE"):
        subprocess.run(["pkill", "-f", "DesktopEditors|onlyoffice-desktopeditors"], capture_output=True)
        yield t.until(lambda: not windows("ONLYOFFICE"), 5)
    yield t.sleep(1)


def logins(t):
    # mos-logins demo: a sample alert, closed by itself (nothing is changed).
    yield t.point(0)
    env = dict(os.environ, MECCANICOS_LOGINS_DEMO_SECONDS="16")
    try:
        demo = subprocess.Popen(["mos-logins", "demo"], env=env, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        demo = None
    t.caption = "An example alert: nothing happened, and nothing is changed."
    yield t.sleep(2)
    yield t.point(1)
    yield t.point(2)
    yield t.point(3)
    if demo:
        yield t.until(lambda: demo.poll() is not None, 20)
    yield t.sleep(1)


def mock(t):
    """A preview: its screens, in a window of their own named after the app."""
    screens = t.step["mock"]
    yield from t.show_mock(screens)
    for i in range(len(t.step["bullets"])):
        if i in screens:
            t.mock = screens[i]
            t.write_mock()
        yield t.point(i)
    yield t.sleep(1.5)
    yield t.close(t.mock_win)


def steps():
    return [
        step(f"Welcome to {NAME}", [
            f"{NAME} is a Linux distribution.",
            "It is designed to be lightweight, fast, secure and coherent.",
            "It can run live from a USB drive, or it can be installed.",
            "Installing it does not require a network connection.",
        ]),
        # installed.nix LUKS2 root + hibernation swap; drivers.nix firewall + avahi;
        # installed.nix openssh (publickey only); mos-install.py: ssh-keygen -t ed25519.
        step(f"{NAME} is secure", [
            "The whole disk is encrypted with LUKS, including hibernation data.",
            "The firewall only allows printer discovery and SSH with keys.",
        ]),
        # nixpkgs (Repology: the largest repository); nixos-rebuild boot + rollback.
        step(f"{NAME} is built on NixOS", [
            f"{NAME} is based on a hardened NixOS.",
            "NixOS has the largest collection of Linux packages.",
            "NixOS guarantees a reproducible environment.",
            "NixOS provides atomic upgrades: a failed upgrade changes nothing, and you can roll back.",
        ]),
        step("The command bar", [
            ("Super + Space is the entry point to everything.", "Super plus Space is the entry point to everything."),
            "For example, type browser to start the Web Browser.",
        ], command_bar),
        step("A desktop menu", [
            f"{NAME} does not have a traditional start menu.",
            "Right-click the desktop for a menu of your apps.",
        ], desktop_menu),
        # packages.nix: OnlyOffice's entries (new document / spreadsheet /
        # presentation); vscodium.nix.
        step("Office and code", [
            "OnlyOffice writes documents, spreadsheets and presentations, in Microsoft Office's formats.",
            ("Super + Space, then Word Processor: a new document.",
             "Super plus Space, then type Word Processor, for a new document."),
            ("Spreadsheet: a new spreadsheet.", "Then Spreadsheet, for a new spreadsheet."),
            ("Presentations: a new presentation, in the same window.",
             "And Presentations, for a new presentation, in the same window."),
            ("VSCodium is the editor for code, with Nix, Git and web extensions ready.",
             "V S Codium is the editor for code, with Nix, Git and web extensions ready."),
            "Close them when you are done.",
        ], office),
        step("A terminal", [
            ("Super + Space, then terminal, opens a terminal.",
             "Super plus Space, then type terminal, opens a terminal."),
            "The next steps happen inside the terminal.",
        ], terminal),
        step("Files: yazi", [
            "yazi is a file manager for navigating your files.",
            "The right side previews the file.",
            "Select a file and press Enter to open it with the right app, the same as the open command.",
        ], yazi),
        step("Open anything", [
            "The open command opens any kind of file with the right app.",
        ], open_pdf),
        step("Print to PDF", [
            "The print command prints any file.",
            "It lets you choose a printer, or save as PDF, right there.",
        ], print_pdf),
        step("The trash", [
            "The trash command moves a file or folder to the trash, instead of deleting it.",
            "The trash-restore command brings it back.",
        ], trash),
        step("Reading aloud", [
            f"Copy any text, and {NAME} can read it aloud.",
            ("Press Super + Space and type Read Clipboard Aloud.", "Press Super plus Space and type Read Clipboard Aloud."),
        ], read_aloud),
        step("Any app, right now", [
            "The nix-shell command lets you use packages without installing them.",
            ("nix-shell -p cowsay creates a shell with the cowsay package in it.",
             "nix shell, dash p, cow say, creates a shell with the cow say package in it."),
            "Use it right away. Nothing outside the shell is affected.",
            "When you exit the shell, the package is gone.",
            "You can create nix shells for tools, compilers and libraries too.",
        ], nix_shell),
        step("Apps for one folder", [
            ("apps install --here gives one folder its own apps, such as a project's compilers and tools.",
             "apps install, dash dash here, gives one folder its own apps, such as a project's compilers and tools."),
            "In that folder, and the folders inside it, they are ready in every terminal, and in VSCodium.",
            "Leave the folder, and they are gone.",
            ("Commit the .envrc file, and everyone working on the project gets the same tools.",
             "Commit the dot env R C file, and everyone working on the project gets the same tools."),
        ], folder_apps),
        # config.py SETTINGS (live: no installed-only ones); export/import.
        step("Settings in one place", [
            ("Super + Space, then Configuration Management.",
             "Super plus Space, then type Configuration Management."),
            "It shows the common settings in one place: screen, keyboard, touchpad, power, sound, clock and time zone.",
            "Move to a setting and press Enter to change it.",
            "Once installed, it also manages SSH, the firewall, updates and the graphics driver.",
            "It can export your settings, and import them on another computer.",
        ], settings),
        # doctor.py: AREAS; fix() asks first; --report.
        step("When something doesn't work", [
            ("Super + Space, then Configuration Doctor.", "Super plus Space, then type Configuration Doctor."),
            "It checks Wi-Fi and the internet, Bluetooth, sound, the screen and disk space.",
            "It explains what is wrong and offers a fix, but it always asks first.",
            "It can also save a report, to ask for help.",
        ], doctor),
        # mos-printers.py: list, discover + add, default, test page, queue + cancel.
        step("Printers", [
            ("Super + Space, then Printers.", "Super plus Space, then type Printers."),
            "Add printers finds printers on the network and on USB, and adds the one you choose.",
            "Pick the default printer, print a test page, or remove a printer.",
            "Queue shows what is waiting to print, and cancels it.",
        ], mock, PRINTERS_MOCK),
        # mos-logins.py: the watcher's alerts (demo shows one), Disconnect.
        step("Login alerts", [
            f"{NAME} watches logins: an SSH login from somewhere new, or an attack, shows an alert like this one.",
            "Its buttons block the address, stop SSH, or disconnect the computer.",
            ("Super + Shift + Esc disconnects at once: remote sessions end and every network goes off.",
             "Super plus Shift plus Escape disconnects at once: remote sessions end and every network goes off."),
            "Logins, in the command bar, shows who is connected and who tried. Alerts never flood you.",
        ], logins),
        step("Managing apps", [
            ("Super + Space: Apps Manager.", "Super plus Space, then type Apps Manager."),
            "The Apps Manager lists your apps, uninstalls and upgrades them, and finds and installs new ones.",
            "It also lets you try a new app in a nix shell, without installing it.",
        ], mock, APPS_MOCK),
        step("A persistent home", [
            f"If you run {NAME} from a USB drive without installing it,",
            "you can keep your files and settings on the same drive, encrypted.",
            ("Super + Space: USB Vault, then Keep my files and settings on this stick.",
             "Super plus Space, then type USB Vault, and choose Keep my files and settings on this stick."),
            "The next time you boot, your files are there, and your computer was not touched.",
        ], mock, HOME_MOCK),
        step(f"Installing {NAME}", [
            f"If you choose to install {NAME} on your computer,",
            "click the Install icon: all the choices are on a single form.",
            f"It erases the disk and copies {NAME} to it, encrypted.",
        ], mock, INSTALL_MOCK),
        step("Keyboard shortcuts", [
            ("Super + Space, then shortcuts, lists every shortcut.",
             "Super plus Space, then type shortcuts, lists every shortcut."),
            ("Super + M moves a window and Super + R resizes it: then the arrow keys, and Enter.",
             "Super plus M moves a window, and Super plus R resizes it: then the arrow keys, and Enter."),
        ], shortcuts),
        step("That's it", [
            ("Super + Space starts everything.", "Super plus Space starts everything."),
            ("Type shortcuts there to see every shortcut.", "Type shortcuts there to see every shortcut."),
            "This video is on your desktop, to watch again.",
            f"Enjoy {NAME}!",
        ]),
    ]


# ---- previews (drawn here; nothing is changed) ------------------------------------
# {bullet index: screen shown from that bullet on}, drawn in the colours of
# the real tools (scripts/lib/mos_tui.py). A line starting with
#   =  is a title bar    >  the selected row    ~  the key bar    .  dim
#   ✓  a done message (green)
# and inside a line: [[Focused button]] [Button] <<shown tab>> {{field being
# typed in}} {field} #heading# «key».
# ANSI colours of the roles in mos_tui.py.
_STYLE = {
    "bar": "38;5;253;48;5;23;1", "sel": "38;5;235;48;5;214;1", "btn": "38;5;252;48;5;238",
    "field": "38;5;253;48;5;237", "key": "38;5;214;1", "head": "38;5;180;1", "dim": "38;5;245",
    "ok": "38;5;114", "border": "38;5;66", "text": "38;5;250",
}
_TOKEN = re.compile(r"\[\[(.+?)\]\]|\[(.+?)\]|<<(.+?)>>|\{\{(.+?)\}\}|\{(.+?)\}|#(.+?)#|«(.+?)»|\(\((.+?)\)\)|([┌┐└┘│─]+)")


def _strip(line):
    """The line without its kind mark: > and . leave their column blank."""
    mark = line[:1]
    if mark and mark in ">.":
        return " " + line[1:]
    return line[1:] if mark and mark in "=~" else line


def mock_plain(line):
    """A preview line as text, its markup gone (and its width)."""
    line = _strip(line)
    return _TOKEN.sub(lambda m: next(f" {g} " if i < 5 else g for i, g in enumerate(m.groups()) if g is not None), line)


def mock_ansi(line, width):
    """A preview line in the tools' colours, as escape codes."""
    kind = {"=": "bar", ">": "sel", "~": "bar", ".": "dim"}.get(line[:1], "ok" if line.startswith("✓") else "text")
    line = _strip(line)
    esc = lambda k: f"\033[0;{_STYLE[k]}m"  # noqa: E731
    base = esc(kind)
    on_bar = kind in ("bar", "sel")

    def token(m):
        g = m.groups()
        styled = [("sel", f" {g[0]} "), ("btn", f" {g[1]} "), ("bar", f" {g[2]} "), ("sel", f" {g[3]} "),
                  ("field", f" {g[4]} "), ("head", g[5]), ("key", g[6]), ("dim", g[7]), ("border", g[8])]
        k, text = next(x for x, y in zip(styled, g) if y is not None)
        if k == "key" and on_bar:
            return f"\033[0;38;5;214;48;5;23;1m{text}{base}"
        return f"{esc(k)}{text}{base}"

    out = base + _TOKEN.sub(token, line)
    pad = width - len(mock_plain(line))
    return out + (" " * pad if on_bar else "") + "\033[0m"


def _box(title, rows, inner=62):
    """A popup's frame around rows (with markup), as the tools draw them."""
    top = f"  ┌─ #{title}# " + "─" * (inner - len(title) - 3) + "┐"
    body = [f"  │ {r}" + " " * (inner - 1 - len(mock_plain(r))) + "│" for r in rows]
    return [top, *body, "  └" + "─" * inner + "┘"]


APPS_MOCK = {
    "title": "Apps Manager",
    0: ["= Apps Manager", "",
        " <<Installed (14)>> [Search]", "",
        "#  App            Version   Status#",
        "──────────────────────────────────────────────────────────────────────",
        ">  vlc            3.0.21    installed",
        "   brave          1.96.59   comes with MeccanicOS: Brave Web Browser",
        "   onlyoffice     9.1.0     comes with MeccanicOS: Office Documents (OnlyOffice)",
        "   celluloid      0.29      comes with MeccanicOS: Video Player (Celluloid)",
        "", "──────────────────────────────────────────────────────────────────────",
        " [[Uninstall]]  [Update]  [Update all]  [Undo]  [Search]  [Quit]",
        ". Live USB: apps you install last until you shut down.",
        "~ «↑↓» move   «←→» button   «Enter» press   «Tab» switch list   «q» quit"],
    2: ["= Apps Manager", "",
        " [Installed (14)] <<Search>>", "",
        " #Search:# {inkscape                                                  }", "",
        "#  App                 Version   What it is#",
        "──────────────────────────────────────────────────────────────────────",
        ">  inkscape            1.4.2     Vector graphics editor",
        "   inkscape-with-ext   1.4.2     Inkscape with its extensions",
        "", "──────────────────────────────────────────────────────────────────────",
        " [[Install]]  [Try it]  [New search]  [Back]  [Quit]",
        "✓ 9 apps found. i installs, t tries without installing.",
        "~ «↑↓» move   «←→» button   «Enter» press   «Tab» switch list   «q» quit"],
}

HOME_MOCK = {  # scripts/usb-vault-menu.py
    "title": "USB Vault",
    0: ["= USB Vault — encrypted storage on your boot USB stick", "",
        ". Stick: /dev/sdb (SanDisk Ultra, 64G, Ventoy)", ". Home: none", ". Vaults: none", "",
        "──────────────────────────────────────────────────────────────────────",
        ">   Keep my files and settings on this stick      ",
        "    Create a vault (a locked folder)",
        "    Open the USB stick's files",
        "    Quit", "", "",
        ". Recommended: everything you do is kept, encrypted; asks for its password at start-up",
        "~ «↑↓» move   «Enter» choose   «r» reload   «q» quit"],
    2: ["= USB Vault — encrypted storage on your boot USB stick", "",
        *_box("Keep my files and settings", [
            "«Room for:»        {{16G" + " " * 36 + "}}",
            "Password:        {" + "•" * 24 + " " * 15 + "}",
            "Password again:  {" + "•" * 24 + " " * 15 + "}",
            "",
            "((Everything you do from now on is kept on this stick.))",
            "((At every start you'll be asked for this password.))",
            "",
            " " * 38 + "[Next]  [Cancel]",
        ]),
        "", "", "~ «↑↓» move   «Enter» choose   «r» reload   «q» quit"],
    3: ["", f"  Password for your saved {NAME} home (Enter to skip): ****", "", "  ...", "",
        "✓ Welcome back: your files and settings are here."],
}

PRINTERS_MOCK = {  # scripts/mos-printers.py
    "title": "Printers",
    0: ["= Printers", "",
        "#    Printer                   State      Jobs  Where#",
        "──────────────────────────────────────────────────────────────────────",
        ">  ★ Office_Laser              ready      0     2nd floor",
        "     Kitchen_Inkjet            ready      0     HP ENVY 6000 series",
        "", "", "",
        "──────────────────────────────────────────────────────────────────────",
        ". Brother HL-L2350DW series   ★ the default printer",
        " [[Add printers]]  [Make default]  [Queue]  [Test page]  [Remove]  [Quit]", "",
        "~ «↑↓» move   «←→» button   «Enter» press   «r» reload   «q» quit"],
    1: ["= Printers › add a printer", "",
        "#  Printer                                 How       Address#",
        "──────────────────────────────────────────────────────────────────────",
        ">  Canon PIXMA G3270                       network   ipps://Canon-G3270.local:443/ipp/print",
        "   Epson ET-2850 Series                    USB       usb://EPSON/ET-2850%20Series",
        "", "", "",
        "──────────────────────────────────────────────────────────────────────", "",
        " [[Add]]  [Search again]  [Back]  [Quit]",
        "✓ 2 new printer(s) found. a adds the chosen one.",
        "~ «↑↓» move   «←→» button   «Enter» press   «r» reload   «q» quit"],
    2: ["= Printers", "",
        "#    Printer                   State      Jobs  Where#",
        "──────────────────────────────────────────────────────────────────────",
        "   ★ Office_Laser              ready      0     2nd floor",
        ">    Kitchen_Inkjet            printing   2     HP ENVY 6000 series",
        "     Canon_PIXMA_G3270         ready      0     Canon PIXMA G3270",
        "", "",
        "──────────────────────────────────────────────────────────────────────",
        ". HP ENVY 6000 series",
        " [Add printers]  [Make default]  [Queue]  [[Test page]]  [Remove]  [Quit]",
        "✓ Test page sent to Kitchen_Inkjet.",
        "~ «↑↓» move   «←→» button   «Enter» press   «r» reload   «q» quit"],
    3: ["= Printers › Kitchen_Inkjet › waiting to print", "",
        "#  Job                   From        Size      Sent#",
        "──────────────────────────────────────────────────────────────────────",
        ">  Kitchen_Inkjet-41     live        1.2 MB    Tue 06 Oct 2026 10:41:02",
        "   Kitchen_Inkjet-42     live        84.0 KB   Tue 06 Oct 2026 10:41:30",
        "", "", "",
        "──────────────────────────────────────────────────────────────────────", "",
        " [[Cancel job]]  [Cancel all]  [Back]  [Quit]", "",
        "~ «↑↓» move   «←→» button   «Enter» press   «r» reload   «q» quit"],
}

INSTALL_MOCK = {  # scripts/mos-install.py
    "title": f"Install {NAME}",
    0: [f"= {NAME} installer", "",
        "  Country          United States", "  Language         English (US)", "  Time zone        America/Chicago",
        "  Keyboard         English (US)", "  Wi-Fi network    (none — set up later)", "  Full name        Ada Lovelace",
        "  Username         ada", "  Password         ••••••••", "  Disk password    ••••••••••••••••",
        "> Target disk      Samsung SSD 970, 500 GB",
        ". Filesystem       ext4 on LUKS2 (encrypted), EFI boot", "",
        "                         [  Install now  ]", "", "",
        "~ «↑↓» move   «Enter» change   «Tab» next   «Ctrl-C» quit"],
    2: [f"= {NAME} installer", "",
        "✓ 1/8  Partitioning the disk", "✓ 2/8  Encrypting (LUKS2)", "✓ 3/8  Creating filesystems",
        f"✓ 4/8  Copying {NAME} to disk (no download needed)", "  5/8  Language, keyboard, time zone, screen",
        ".  6/8  Creating user ada", ".  7/8  Saving your configuration to /etc/nixos", ".  8/8  Finishing"],
}

# ---- voice -------------------------------------------------------------------------
class Voice:
    """`say`, with no pause between lines: Piper takes a second or two to
    start, so the next lines are made ahead (say --to FILE) while one is
    spoken (say --play FILE). Playing runs in its own process group, so
    stopping it stops the player too; `say` speaks one voice at a time."""

    def __init__(self):
        self.proc = None
        self.on = shutil.which(SAY) is not None or os.path.exists(SAY)
        self.dir = tempfile.mkdtemp(prefix="mos-tutorial-", dir=os.environ.get("XDG_RUNTIME_DIR"))
        self.queue = []  # lines to make, in order
        self.making = None
        self.cond = threading.Condition()
        threading.Thread(target=self.maker, daemon=True).start()

    def file(self, text):
        return os.path.join(self.dir, hashlib.sha1(text.encode()).hexdigest())

    def prepare(self, texts):
        """Make these lines next, in this order, instead of what was queued."""
        with self.cond:
            self.queue = [t for t in dict.fromkeys(texts) if t != self.making and not os.path.exists(self.file(t))]
            self.cond.notify()

    def maker(self):
        while True:
            with self.cond:
                while not self.queue:
                    self.cond.wait()
                self.making = text = self.queue.pop(0)
            try:
                # Lowest priority: Piper uses every core it can, and the desktop
                # must keep drawing (in the recording VM, software OpenGL: the
                # Video Player showed only black).
                subprocess.run([SAY, "--to", self.file(text), text], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=60, preexec_fn=lambda: os.nice(19))
            except (OSError, subprocess.SubprocessError):
                pass
            with self.cond:
                self.making = None

    def say(self, text):
        self.stop()
        if not self.on:
            return
        path = self.file(text)
        with self.cond:
            if not os.path.exists(path) and text != self.making:
                self.queue = [text] + [t for t in self.queue if t != text]
                self.cond.notify()
        try:
            self.proc = subprocess.Popen([SAY, "--play", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError:
            self.proc = None

    def busy(self):
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        if self.busy():
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except OSError:
                pass
        self.proc = None

    def clean(self):
        shutil.rmtree(self.dir, ignore_errors=True)


# ---- screen ----------------------------------------------------------------------
# The colours of every MeccanicOS full-screen tool (scripts/lib/mos_tui.py).
def init_colors():
    curses.start_color()
    curses.use_default_colors()
    rich = curses.COLORS >= 256
    p = lambda a, b: a if rich else b  # noqa: E731
    curses.init_pair(1, p(250, curses.COLOR_WHITE), -1)  # text
    curses.init_pair(2, p(253, curses.COLOR_WHITE), p(23, curses.COLOR_CYAN))  # bars
    curses.init_pair(3, p(180, curses.COLOR_YELLOW), -1)  # titles
    curses.init_pair(4, p(214, curses.COLOR_YELLOW), -1)  # keys, current bullet
    curses.init_pair(5, p(114, curses.COLOR_GREEN), -1)  # key being pressed
    curses.init_pair(6, p(242, curses.COLOR_WHITE), -1)  # dim
    curses.init_pair(7, p(187, curses.COLOR_WHITE), p(235, curses.COLOR_BLACK))  # mock screen
    curses.init_pair(8, p(253, curses.COLOR_WHITE), p(23, curses.COLOR_CYAN))  # mock cursor line


def wrap(text, width):
    lines, line = [], ""
    for word in text.split():
        if len(line) + len(word) + 1 > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    return lines


class Tour:
    def __init__(self, scr, start, cues=None):
        self.cues = cues  # --record: the subtitles' file
        if cues:
            self.park()
        self.scr = scr
        self.steps = steps()
        self.i = max(0, min(start, len(self.steps) - 1))
        self.voice = Voice()
        self.paused = False
        self.opened = set()  # windows the tour opened (closed when it ends)
        self.term = None  # the demo terminal
        self.last = None  # the window opened last
        self.before = {}  # window class: windows before the action that opens one
        self.typing = 0.0  # until when keys go out (stray ones here are ignored)
        self.enter()

    # -- steps --
    @property
    def step(self):
        return self.steps[self.i]

    def enter(self):
        self.play = self.step["play"](self)
        self.wait = None
        self.current = -1  # bullet being spoken
        self.caption = ""
        self.mock = None
        self.mock_win = None
        self.speech = None
        # This step's lines, then the next step's, made while they wait.
        if self.voice.on:
            nxt = self.steps[self.i + 1]["bullets"] if self.i + 1 < len(self.steps) else []
            self.voice.prepare([spoken(b) for b in self.step["bullets"] + nxt])

    def go(self, j):
        """Jump to step j: what the current step left open is closed first."""
        self.play.close()
        self.voice.stop()
        self.close_all()
        if 0 <= j < len(self.steps):
            self.i = j
            self.enter()
        else:
            raise SystemExit

    def advance(self):
        if self.paused:
            return
        if self.wait is not None and not self.wait():
            return
        try:
            self.wait = next(self.play)
        except StopIteration:
            if self.i + 1 >= len(self.steps):
                raise SystemExit
            self.i += 1
            self.enter()
            self.wait = self.sleep(0.5)

    # -- what play() yields: predicates "done yet?" --
    def sleep(self, seconds):
        end = time.monotonic() + seconds
        return lambda: time.monotonic() >= end

    def until(self, pred, timeout):
        end = time.monotonic() + timeout
        last = [0.0]

        def done():
            if time.monotonic() >= end:
                return True
            if time.monotonic() - last[0] < 0.4:
                return False
            last[0] = time.monotonic()
            return bool(pred())

        return done

    def point(self, n):
        """Highlight bullet n and speak it."""
        self.current = n
        self.caption = ""
        b = self.step["bullets"][n]
        wait = self.say(spoken(b))
        if self.cues:
            self.cue(b[0] if isinstance(b, tuple) else b, spoken(b))
        return wait

    def hold(self, start, end):
        """For the video: keep this stretch whole, though nothing moves in it
        (the encoder otherwise shortens still, silent moments)."""
        if self.cues and end > start:
            with open(self.cues, "a") as f:
                f.write(f"hold\t{start:.3f}\t{end:.3f}\n")

    def cut(self, start, end):
        """For the video: leave out this stretch of waiting (seconds since the epoch)."""
        if self.cues and end > start:
            with open(self.cues, "a") as f:
                f.write(f"cut\t{start:.3f}\t{end:.3f}\n")

    def cue(self, shown, text):
        """A subtitle: the line as shown, for as long as it is spoken."""
        # say --play waits for the audio (22050 Hz, 16-bit mono) if it isn't made yet.
        path = self.voice.file(text)
        for _ in range(100):
            if os.path.exists(path):
                break
            time.sleep(0.1)
        seconds = os.path.getsize(path) / 44100 if os.path.exists(path) else 1 + 0.35 * len(text.split())
        with open(self.cues, "a") as f:
            f.write(f"{time.time():.3f}\t{seconds:.2f}\t{shown}\n")

    def say(self, text):
        self.speech = text
        self.voice.say(text)
        if not self.voice.on:  # time to read it instead
            return self.sleep(1 + 0.35 * len(text.split()))
        end = time.monotonic() + 60
        return lambda: not self.voice.busy() or time.monotonic() >= end

    # wid: the window to type into ("" = whichever has the keyboard, e.g. the
    # command bar). None means that window didn't open: nothing is sent, so
    # keys never land in a window they weren't meant for.
    def key(self, keys, caption, wid=""):
        if wid is None:
            return self.sleep(0)
        self.caption = f"⌨  {caption}"
        self.typing = time.monotonic() + 1
        self.activate(wid)
        xdo("key", "--clearmodifiers", "--delay", "120", *keys.split())
        return self.sleep(0.5)

    def type(self, text, wid=""):
        if wid is None:
            return self.sleep(0)
        self.caption = f"⌨  {text}"
        self.typing = time.monotonic() + 1 + len(text) * TYPE_DELAY / 1000
        self.activate(wid)
        proc = xdo("type", "--delay", str(TYPE_DELAY), text, wait=False)
        return lambda: proc is None or proc.poll() is not None

    def click(self, x, y, button, caption):
        """Move the pointer there and click (button 3: right-click)."""
        self.caption = f"🖱  {caption}"
        xdo("mousemove", "--sync", str(x), str(y))
        time.sleep(0.4)
        xdo("click", str(button))
        return self.sleep(0.3)

    def park(self):
        """The pointer out of the way, in the bottom-right corner."""
        xdo("mousemove", "1910", "1070")

    def activate(self, wid):
        # Separate from key/type: chained after it, xdotool would send the
        # keys as synthetic events, which terminals ignore.
        if wid:
            xdo("windowactivate", "--sync", wid)

    def close(self, wid):
        if wid:
            close_window(wid)
            self.forget(wid)
        return self.sleep(0.3)

    def forget(self, wid):
        self.opened.discard(wid)

    def copy(self, text):
        try:
            p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            p.communicate(text.encode(), timeout=3)
        except (OSError, subprocess.SubprocessError):
            pass

    def close_all(self):
        for wid in list(self.opened):
            close_window(wid)
        self.opened.clear()
        self.term = self.last = None

    # -- demo building blocks (used with yield from) --
    def expect(self, cls):
        """Note the windows of cls before the action that opens a new one."""
        self.before[cls] = windows(cls)

    def new_window(self, cls, timeout=20):
        before = self.before.pop(cls, None)
        before = windows(cls) if before is None else before
        found = []
        self.last = None

        def appeared():
            new = windows(cls) - before
            if new:
                found.append(min(new, key=int))
            return new

        yield self.until(appeared, timeout)
        if found:
            self.last = found[0]
            self.opened.add(found[0])
            if self.cues:
                center(found[0])

    def command_bar(self, text):
        """Open the command bar and type text; False if it didn't open."""
        yield self.key("super+space", "Super + Space")
        yield self.until(lambda: windows("rofi"), 5)
        if not windows("rofi"):
            return False
        yield self.sleep(0.5)
        yield self.type(text)
        yield self.sleep(1)
        return True

    def terminal(self):
        """The demo terminal, opened from the command bar if it isn't open."""
        if self.term and self.term in windows("^xfce4-terminal$"):
            return
        self.term = None
        if not (yield from self.command_bar("terminal")):
            return
        self.expect("^xfce4-terminal$")
        yield self.key("Return", "Enter")
        yield from self.new_window("^xfce4-terminal$")
        self.term = self.last
        yield self.sleep(1)

    def command(self, line):
        yield self.type(line, self.term)
        yield self.key("Return", "Enter", self.term)
        yield self.sleep(1.5)

    def shell(self):
        """The demo terminal at a shell prompt."""
        if self.term and running("(^|/)yazi( |$)"):
            yield self.key("q", "q", self.term)
            yield self.until(lambda: not running("(^|/)yazi( |$)"), 5)
        yield from self.terminal()

    def yazi(self):
        """yazi in the Tutorial folder, in the demo terminal."""
        had = self.term is not None
        yield from self.terminal()
        if not (had and running("(^|/)yazi( |$)")):
            yield from self.command("yazi Tutorial")
            yield self.until(lambda: running("(^|/)yazi( |$)"), 5)
            yield self.sleep(1)

    # -- previews in their own window --
    def show_mock(self, screens):
        """Open the preview window: `watch` shows the file write_mock writes."""
        pages = [v for k, v in screens.items() if isinstance(k, int)]
        self.mock_w = max(len(mock_plain(l)) for p in pages for l in p) + 2
        rows = max(len(p) for p in pages) + 2
        self.mock_file = os.path.join(self.voice.dir, "preview.txt")
        self.mock = pages[0]
        self.write_mock()
        self.expect("mos-preview")
        try:
            subprocess.Popen(["xfce4-terminal", "--disable-server", "--class", "mos-preview",
                              "--title", screens["title"], "--hide-menubar", "--hide-scrollbar",
                              f"--geometry={self.mock_w}x{rows}",
                              # Redrawn when write_mock replaces the file (watch -c knows 8 colours only).
                              "-x", "bash", "-c", 'printf "\\033[?25l"; last=; while :; do '
                              'm=$(stat -c %y "$0" 2>/dev/null); [ "$m" != "$last" ] && { last=$m; '
                              'printf "\\033[H\\033[2J"; cat "$0"; }; sleep 0.2; done', self.mock_file],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError:
            pass
        yield from self.new_window("mos-preview", 15)
        self.mock_win = self.last

    def write_mock(self):
        # Written whole, so the window never shows half of it.
        tmp = self.mock_file + ".part"
        with open(tmp, "w") as f:
            f.write("\n".join(mock_ansi(l, self.mock_w) for l in self.mock))
        os.replace(tmp, self.mock_file)

    # -- drawing --
    def draw(self):
        s = self.scr
        s.erase()
        h, w = s.getmaxyx()
        cp = curses.color_pair

        def put(y, x, t, a=0):
            if 0 <= y < h and x < w:
                try:
                    s.addstr(y, x, t[: w - x - (1 if y == h - 1 else 0)], a)
                except curses.error:
                    pass

        bar = f" {NAME} tour   {self.i + 1}/{len(self.steps)}"
        state = "" if self.cues else "paused" if self.paused else ("voice on" if self.voice.on else "voice off")
        put(0, 0, bar.ljust(w), cp(2) | curses.A_BOLD)
        put(0, max(0, w - len(state) - 1), state, cp(2))
        put(2, 2, self.step["title"], cp(3) | curses.A_BOLD)
        y = 4
        for n, b in enumerate(self.step["bullets"]):
            text = b[0] if isinstance(b, tuple) else b
            attr = cp(4) | curses.A_BOLD if n == self.current else (cp(1) if n < self.current else cp(6))
            for k, line in enumerate(wrap(text, w - 6)):
                put(y, 2, ("• " if k == 0 else "  ") + line, attr)
                y += 1
        if self.mock:
            y += 1
            boxw = min(w - 4, max(len(mock_plain(l)) for l in self.mock) + 2)
            for line in self.mock:
                if y >= h - 3:
                    break
                attr = cp(8) | curses.A_BOLD if line.startswith(">") else cp(7)
                put(y, 2, (" " + mock_plain(line)).ljust(boxw), attr)
                y += 1
            put(min(y, h - 3), 2, " preview — nothing is changed ".rjust(boxw), cp(6))
        if self.caption:
            put(h - 3, 2, self.caption, cp(5) | curses.A_BOLD)
        keys = [] if self.cues else [("Space", "pause"), ("←/→", "step"), ("R", "replay"), ("M", "voice"), ("Q", "quit")]
        x = 1
        for k, label in keys:
            put(h - 1, x, k, cp(4) | curses.A_BOLD)
            put(h - 1, x + len(k) + 1, label, cp(6))
            x += len(k) + len(label) + 4
        s.refresh()

    def loop(self):
        curses.curs_set(0)
        self.scr.timeout(100)
        while True:
            self.advance()
            self.draw()
            k = self.scr.getch()
            if k == -1 or time.monotonic() < self.typing:
                continue
            c = chr(k).lower() if 0 <= k < 256 else ""
            if c == " ":
                self.paused = not self.paused
                if self.paused:
                    self.voice.stop()
                elif self.speech is not None and self.wait is not None and not self.wait():
                    self.wait = self.say(self.speech)  # say the interrupted bullet again
            elif k in (curses.KEY_RIGHT,) or c == "n":
                self.go(self.i + 1)
            elif k in (curses.KEY_LEFT,) or c == "b":
                self.go(max(0, self.i - 1))
            elif c == "r":
                self.go(self.i)
            elif c == "m":
                self.voice.on = not self.voice.on
                if not self.voice.on:
                    self.voice.stop()
            elif c == "q" or k == 27:
                return


def keep_on_top():
    # A small window in the top-right corner that stays above the others
    # (none when it plays hidden, in the recorder).
    wid = os.environ.get("WINDOWID")
    if not (wid and wid.isdigit()):
        return
    target = ["-i", "-r", hex(int(wid))]
    try:
        subprocess.run(["wmctrl"] + target + ["-b", "add,above"], capture_output=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        pass


def main(argv):
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    if not sys.stdout.isatty():
        sys.exit("mos-tour needs a terminal: mos-tour --window")
    cues = None
    if argv[:1] == ["--record"] and len(argv) > 1:
        cues, argv = argv[1], argv[2:]
    start = int(argv[0]) - 1 if argv and argv[0].isdigit() else 0
    # One tour at a time: two would talk over each other.
    lock = open(LOCK, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        try:
            subprocess.run(["wmctrl", "-x", "-a", "mos-tutorial"], capture_output=True, timeout=3)
        except (OSError, subprocess.SubprocessError):
            pass
        print("The tutorial is already running.")
        return 0
    prepare_samples()
    keep_on_top()
    os.environ.setdefault("ESCDELAY", "25")
    tour = None

    def finish():
        if tour:
            tour.voice.stop()
            tour.close_all()
            tour.voice.clean()

    # Closing the window (SIGHUP) or being stopped: silence, and close what
    # the tour opened.
    def stopped(signum, frame):
        finish()
        os._exit(0)

    for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stopped)

    def run(scr):
        nonlocal tour
        init_colors()
        tour = Tour(scr, start, cues)
        tour.loop()

    try:
        curses.wrapper(run)
    except SystemExit:
        pass
    finally:
        finish()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
