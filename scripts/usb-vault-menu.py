#!/usr/bin/env python3
"""usb-vault menu - encrypted storage on the boot USB stick, full screen.

What survives a restart and the space left at the top (usb-vault summary),
then the stick's state (usb-vault status), what you can do below.
Creating something is one form (size, kind, the password twice), then a
confirmation; the work itself runs on the plain terminal, so its progress
shows, then the menu comes back. Every step is a `usb-vault` command
(scripts/usb-vault.sh): passwords go to it on stdin, never on a command line.

Keys: ↑↓ move · Enter choose · Esc back · q quit. Colours and keys as in
every MeccanicOS full-screen tool (scripts/lib/mos_tui.py).
"""

import curses
import glob
import locale
import os
import re
import subprocess
import sys

# The look shared by MeccanicOS TUIs: MECCANICOS_PYLIB from the Nix wrapper, else next to this file.
sys.path.insert(0, os.environ.get("MECCANICOS_PYLIB") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import mos_tui as ui  # noqa: E402

VAULT = os.environ.get("USB_VAULT_CMD", "usb-vault")
ENTER, ESC = ui.ENTER, ui.ESC
MIN_PASS = 16  # usb-vault.sh new_passphrase
SIZE_RE = re.compile(r"\d+(\.\d+)?[KMGT]?", re.I)
SUMMARY = "What survives a restart"  # its first line (usb-vault.sh cmd_summary)
OK_RE, LOST_RE = re.compile(r"kept"), re.compile(r"lost at shutdown")


def vault(*args, input=None, yes=False):
    """Run usb-vault (it gets root through sudo); (exit code, output)."""
    env = dict(os.environ, USB_VAULT_GUI="0", **({"USB_VAULT_YES": "1"} if yes else {}))
    try:
        # No terminal for it: sudo must not ask inside the menu (main() asked already).
        p = subprocess.run([VAULT, *args], input=input, capture_output=True, text=True, env=env, timeout=120,
                           **({} if input is not None else {"stdin": subprocess.DEVNULL}))
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)
    return p.returncode, (p.stdout + p.stderr).strip()


def to_bytes(size):
    """16G -> bytes (as usb-vault reads sizes: K, M, G, T are powers of 1024)."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([KMGT]?)", size.strip(), re.I)
    return int(float(m.group(1)) * 1024 ** "_KMGT".index((m.group(2) or "_").upper()))


def last_line(text):
    lines = [l for l in text.splitlines() if l.strip()]
    return re.sub(r"^usb-vault: ", "", lines[-1]) if lines else ""


class Menu:
    def __init__(self, scr):
        self.scr = scr
        self.sel = 0
        self.msg = ""
        self.load()

    # ---- the stick ---------------------------------------------------------------
    def load(self):
        code, out = vault("status")
        self.status = out.splitlines() if code == 0 else ["No MeccanicOS USB stick found:", last_line(out),
                                                          "(Vaults live on the stick MeccanicOS started from.)"]
        self.found = code == 0
        # status ends with the summary (what survives a restart); without a
        # stick (an installed system) ask for the summary alone.
        cut = next((i for i, l in enumerate(self.status) if l.startswith(SUMMARY)), None)
        if cut is not None:
            self.summary = self.status[cut:]
            self.status = self.status[:cut]
            while self.status and not self.status[-1].strip():
                self.status.pop()
        else:
            code, out = vault("summary")
            self.summary = out.splitlines() if code == 0 else []
        code, out = vault("list")
        lines = out.splitlines() if code == 0 else []
        self.ventoy = bool(lines) and lines[0] == "ventoy"
        # open|locked, path, mount (empty when locked, so the last tab may be trimmed)
        self.vaults = [(l.split("\t") + ["", ""])[:3] for l in lines[1:] if "\t" in l]
        self.recover = any(l.startswith("Recover") for l in self.status)
        has_home = any(l.startswith("Home") and "none" not in l for l in self.status)
        items = []
        if self.found:
            locked = [v for v in self.vaults if v[0] == "locked"]
            opened = [v for v in self.vaults if v[0] == "open"]
            if locked:
                items.append(("Unlock a vault", "Open a locked folder (asks for its password)", self.unlock))
            if opened:
                items.append(("Lock vaults", "Lock every open vault again", self.lock))
            # Two ways to keep things, in plain words; the CLI has the rest
            # (create-partition, create-home --file, sizes of the files area).
            if not has_home:
                items.append(("Keep my files and settings on this stick", "Recommended: everything you do is kept, "
                              "encrypted; asks for its password at start-up", self.create_home))
            items.append(("Create a vault (a locked folder)", "A folder for a few private files, "
                          "locked until you unlock it with its password", self.create_file))
            items.append(("Open the USB stick's files", "The stick's own files area, in the file manager", self.stick))
            if self.vaults or has_home:
                items.append(("Back up vaults to another disk", "Copy them (still encrypted) to a folder on another disk", self.backup))
            if self.recover:
                items.append(("Recover vaults after re-flashing", "Put the vault partitions back in the table: nothing is erased", self.do_recover))
        items.append(("Quit", "", None))
        self.items = items
        self.sel = min(self.sel, len(items) - 1)

    # ---- drawing -------------------------------------------------------------------
    def put(self, y, x, text, attr=0, win=None):
        ui.put(win or self.scr, y, x, text, attr)

    def draw(self):
        scr = self.scr
        scr.erase()
        h, w = scr.getmaxyx()
        if h < 16 or w < 60:
            self.put(0, 0, "Make the window larger.")
            scr.refresh()
            return
        ui.bar(scr, 0, "USB Vault — encrypted storage on your boot USB stick")
        y = 2
        room = h - 7 - len(self.items)
        # The summary first (its "kept"/"lost" in green/red), then the stick.
        lines = self.summary + ([""] if self.summary else []) + self.status
        for i, line in enumerate(lines[: max(1, room)]):
            if i < len(self.summary):
                self.summary_line(y, line)
            else:
                self.put(y, 2, line, ui.attr(ui.DIM if not line.startswith(" ") else ui.NORMAL))
            y += 1
        y += 1
        self.put(y, 1, "─" * (w - 3), ui.attr(ui.BORDER))
        y += 1
        for i, (label, _, _) in enumerate(self.items):
            ui.row(scr, y + i, 2, min(w - 4, 50), f"  {label}", i == self.sel)
        self.put(h - 3, 2, self.items[self.sel][1], ui.attr(ui.DIM))
        ui.message(scr, h - 2, 2, self.msg)
        ui.keybar(scr, h - 1, [("↑↓", "move"), ("Enter", "choose"), ("r", "reload"), ("q", "quit")])
        scr.refresh()

    def summary_line(self, y, line):
        """  Label : kept|lost ...  with the verdict coloured; headings in sand."""
        scr = self.scr
        if not line.startswith(" "):
            ui.put(scr, y, 2, line, ui.attr(ui.HEADING))
            return
        label, sep, value = line.partition(": ")
        x = ui.put(scr, y, 2, label + sep, ui.attr(ui.NORMAL))
        verdict = OK_RE.match(value) or LOST_RE.match(value)
        if verdict:
            x = ui.put(scr, y, x, verdict.group(0), ui.attr(ui.OK if verdict.re is OK_RE else ui.ERR))
            value = value[verdict.end():]
        ui.put(scr, y, x, value, ui.attr(ui.DIM if verdict else ui.NORMAL))

    # ---- asking --------------------------------------------------------------------
    def box(self, title, lines, height=None, width=0):
        self.draw()  # the menu behind, without what an earlier box left
        h, w = self.scr.getmaxyx()
        bw = min(max([len(l) for l in lines] + [len(title) + 6, 52, width]) + 6, w - 2)
        bh = min(height or len(lines) + 2, h - 2)
        win = curses.newwin(bh, bw, (h - bh) // 2, (w - bw) // 2)
        win.keypad(True)
        ui.frame(win, title)
        for i, l in enumerate(lines[: bh - 2]):
            self.put(1 + i, 2, l, ui.attr(ui.NORMAL), win)
        return win

    def pick(self, title, options):
        """One of options (labels); its index or None."""
        i = 0
        while True:
            win = self.box(title, [""] * len(options))
            for j, o in enumerate(options):
                ui.row(win, 1 + j, 2, win.getmaxyx()[1] - 4, f" {o} ", j == i)
            win.refresh()
            k = win.get_wch()
            if k == curses.KEY_UP:
                i = (i - 1) % len(options)
            elif k in (curses.KEY_DOWN, "\t"):
                i = (i + 1) % len(options)
            elif k in ENTER:
                return i
            elif k in (ESC, "q"):
                return None

    def confirm(self, title, text, yes="Go ahead"):
        self.draw()
        return ui.confirm(self.scr, text, yes=yes, title=title, default_yes=True)

    def form(self, title, fields, note="", ok="OK"):
        """fields: [(label, default, kind)], kind "text", "secret" or a list of
        choices (←→ changes), then the buttons ok and Cancel. ↑↓/Tab move,
        Enter goes to the next field or presses the button. Returns
        {label: value} or None (Cancel, Esc)."""
        values = {l: d for l, d, _ in fields}
        labels = [(ok, ""), ("Cancel", "")]  # letters type into the fields
        n = len(fields)
        i = 0  # n: the ok button, n + 1: Cancel
        lw = max(len(l) for l, _, _ in fields) + 2
        notes = note.splitlines() if note else []
        try:
            while True:
                lines = [""] * n + [""] + notes + ["", ""]
                win = self.box(title, lines, width=lw + 30)
                bw = win.getmaxyx()[1]
                at = None
                for j, (label, _, kind) in enumerate(fields):
                    v = values[label]
                    self.put(1 + j, 2, f"{label}:", ui.attr(ui.KEY if j == i else ui.NORMAL), win)
                    shown = f"‹ {v} ›" if isinstance(kind, list) else v
                    x = ui.field(win, 1 + j, 2 + lw, bw - lw - 5, shown, j == i, kind == "secret")
                    if j == i and not isinstance(kind, list):
                        at = (1 + j, x)
                for j, l in enumerate(notes):
                    self.put(2 + n + j, 2, l, ui.attr(ui.DIM), win)
                ui.buttons(win, len(lines), bw - ui.width_of(labels) - 3, labels, i - n)
                ui.cursor(at is not None)
                if at:
                    win.move(*at)
                win.refresh()
                k = win.get_wch()
                if k == ESC:
                    return None
                if k in (curses.KEY_UP, curses.KEY_BTAB):
                    i = (i - 1) % (n + 2)
                elif k in (curses.KEY_DOWN, "\t"):
                    i = (i + 1) % (n + 2)
                elif k in ENTER:
                    if i == n:
                        return values
                    if i == n + 1:
                        return None
                    i += 1
                elif i >= n:
                    if k in (curses.KEY_LEFT, curses.KEY_RIGHT):
                        i = n + (1 - (i - n))
                    continue
                else:
                    label, _, kind = fields[i]
                    if isinstance(kind, list):
                        if k in (curses.KEY_LEFT, curses.KEY_RIGHT, " "):
                            step = -1 if k == curses.KEY_LEFT else 1
                            values[label] = kind[(kind.index(values[label]) + step) % len(kind)]
                    elif (t := ui.typed(values[label], k)) is not None:
                        values[label] = t
        finally:
            ui.cursor(False)

    def check_password(self, v, a, b):
        if v[a] != v[b]:
            self.msg = "✗ The two passwords are different."
        elif len(v[a]) < MIN_PASS:
            self.msg = f"✗ Use a password of at least {MIN_PASS} characters (a few words work well)."
        else:
            return True
        return False

    def check_size(self, size, empty_ok):
        if (empty_ok and not size) or SIZE_RE.fullmatch(size):
            return True
        self.msg = "✗ How much room: like 16G (gigabytes) or 500M" + (", or empty for all the free space." if empty_ok else ".")
        return False

    # ---- doing ---------------------------------------------------------------------
    def outside(self, title, args, password=None):
        """Run usb-vault on the plain terminal (its progress shows), then back."""
        curses.endwin()
        print(f"\n== {title} ==\n", flush=True)
        stdin = f"{password}\n{password}\n" if password is not None else None
        env = dict(os.environ, USB_VAULT_GUI="0", USB_VAULT_YES="1")
        try:
            code = subprocess.run([VAULT, *args], input=stdin, text=True, env=env).returncode
        except (OSError, KeyboardInterrupt):
            code = 1
        print("\n" + ("Done." if code == 0 else "That did not work (see above)."))
        try:
            input("Press Enter to go back to the menu.")
        except (EOFError, KeyboardInterrupt):
            pass
        self.scr.refresh()
        self.load()
        self.msg = f"✓ {title}: done" if code == 0 else f"✗ {title}: did not work"

    def unlock(self):
        locked = [v for v in self.vaults if v[0] == "locked"]
        i = 0 if len(locked) == 1 else self.pick("Unlock which vault?", [os.path.basename(v[1]) for v in locked])
        if i is None:
            return
        path = locked[i][1]
        v = self.form(f"Unlock {os.path.basename(path)}", [("Password", "", "secret")], ok="Unlock")
        if not v:
            return
        self.msg = "Unlocking…"
        self.draw()
        code, out = vault("open", path, input=v["Password"] + "\n")
        self.load()
        self.msg = ("✓ " if code == 0 else "✗ ") + last_line(out)

    def lock(self):
        code, out = vault("close")
        self.load()
        self.msg = ("✓ Vaults locked." if code == 0 else "✗ " + last_line(out))

    def stick(self):
        code, out = vault("stick")
        m = re.search(r"are at (\S+)", out)
        if code == 0 and m:
            subprocess.Popen(["xdg-open", m.group(1)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            self.msg = f"✓ The stick's files: {m.group(1)}"
        else:
            self.msg = "✗ " + last_line(out)

    def create_home(self):
        v = self.form("Keep my files and settings", [("Room for", "16G", "text"), ("Password", "", "secret"),
                                                     ("Password again", "", "secret")],
                      ok="Next", note="Everything you do from now on is kept on this stick, encrypted.\n"
                      "At every start you'll be asked for this password (Enter skips:\n"
                      "a fresh session). Forget it and the files can't be opened.")
        if not v or not self.check_size(v["Room for"], False) or not self.check_password(v, "Password", "Password again"):
            return
        if not self.confirm("Keep my files and settings",
                            f"{v['Room for']} on this stick for your files and settings, encrypted.\n"
                            "What you have now is copied in. Nothing on the stick is erased.\n"
                            "Restart the computer afterwards to start using it.", yes="Create"):
            return
        # usb-vault picks partition or file (Ventoy, or no partition slot left: file).
        self.outside("Keep my files and settings", ["create-home", "--size", v["Room for"]], v["Password"])

    def create_file(self):
        taken = {os.path.basename(v[1]).removesuffix(".luks") for v in self.vaults}
        default = next(n for n in ["private"] + [f"private-{i}" for i in range(2, 100)] if n not in taken)
        v = self.form("Create a vault", [("Name", default, "text"), ("Room for", "4G", "text"),
                                         ("Password", "", "secret"), ("Password again", "", "secret")],
                      ok="Next", note="A locked folder for a few private files. Unlock it here when you\n"
                      "need it: it opens as ~/Vault-NAME. Forget the password and the\n"
                      "files can't be opened.")
        if not v or not self.check_size(v["Room for"], False) or not self.check_password(v, "Password", "Password again"):
            return
        name = re.sub(r"[^\w-]", "_", v["Name"].strip().removesuffix(".luks") or default)
        if name in taken:
            self.msg = f"✗ There is already a vault called {name}."
            return
        if not self.confirm("Create a vault", f"A locked folder called {name}, with room for {v['Room for']}.\n"
                                              f"Unlocked, it opens as ~/Vault-{name}. Nothing on the stick is erased.", yes="Create"):
            return
        args = ["create-file", "--size", v["Room for"], "--name", name]
        if not self.ventoy:
            # A plain stick without a files area gets one just big enough (2 GiB to spare),
            # so its free space is still there for "Keep my files and settings".
            args += ["--data-size", str(to_bytes(v["Room for"]) + 2 * 2**30)]
        self.outside("Create a vault", args, v["Password"])

    def backup(self):
        user = os.environ.get("USER", "")
        disks = sorted(glob.glob(f"/run/media/{user}/*"))
        v = self.form("Back up vaults", [("To folder", disks[0] if disks else "", "text")],
                      ok="Back up", note="A folder on another disk (plugged-in disks are in /run/media).\n"
                      "Vaults are locked first, and copied still encrypted.")
        if not v:
            return
        folder = os.path.expanduser(v["To folder"].strip())
        if not os.path.isdir(folder):
            self.msg = f"✗ No such folder: {folder or '(empty)'}"
            return
        self.outside("Back up vaults", ["backup", folder])

    def do_recover(self):
        if self.confirm("Recover vaults", "Put the vault partitions saved on the stick back in its\n"
                                          "partition table. Nothing is erased.", yes="Recover"):
            self.outside("Recover vaults", ["recover"])

    def run(self):
        while True:
            self.draw()
            k = self.scr.get_wch()
            if k == curses.KEY_UP:
                self.sel = (self.sel - 1) % len(self.items)
            elif k == curses.KEY_DOWN:
                self.sel = (self.sel + 1) % len(self.items)
            elif k in ENTER:
                act = self.items[self.sel][2]
                if act is None:
                    return
                self.msg = ""
                act()
            elif k in ("q", ESC):
                return
            elif k == "r":
                self.load()
                self.msg = "reloaded"


def main(argv):
    if argv and argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("usb-vault menu needs a terminal (usb-vault --help for the commands)", file=sys.stderr)
        return 2
    # Root comes from sudo: ask for its password now, on the plain terminal, if it wants one.
    if subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode != 0:
        if subprocess.run(["sudo", "-v"]).returncode != 0:
            return 1
    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")

    def start(scr):
        ui.init()
        Menu(scr).run()

    curses.wrapper(start)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:  # Ctrl+C: curses.wrapper has restored the terminal
        sys.exit(130)
