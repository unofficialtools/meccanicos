"""mos-config's full-screen view: move to a setting, Enter to change it.

Choices are picked from a list, on/off settings flip, the rest are typed
(checked as with `mos-config set`). Settings that need a rebuild are
collected and applied together on the way out. Anything that may ask a
question (a sudo password, export/import, the doctor, the rebuild) runs on
the plain terminal, then the view comes back.

Network comes first: not settings but what `mos-config network` does (join
a Wi-Fi network, sign in to a hotel/café network, VPNs on and off).
"""

import contextlib
import curses
import io
import locale
import os
import re
import sys

import common as c
import config as cfg

# The look shared by MeccanicOS TUIs: MECCANICOS_PYLIB from the Nix wrapper, else scripts/lib.
sys.path.insert(0, os.environ.get("MECCANICOS_PYLIB") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import mos_tui as ui  # noqa: E402

MINUTES = ["never", "5", "10", "15", "20", "30", "45", "60", "90", "120"]
PERCENT = ["off", "60", "70", "75", "80", "85", "90", "95"]
OTHER = "other…"
ENTER, ESC = ui.ENTER, ui.ESC
KEYS = [("↑↓", "move"), ("Enter", "change"), ("e", "export"), ("i", "import"), ("d", "doctor"), ("r", "refresh"),
        ("q", "quit")]
NMTUI = "Other network (hidden, more options)…"


class NetRow:
    """A Network line: shown like a setting, but Enter runs act (nothing is saved)."""
    system = rebuild = False
    choices = example = None

    def __init__(self, key, help, get, act):
        self.key, self._help, self._get, self.act = key, help, get, act

    @property
    def help(self):  # may say what the value is, in full
        return self._help() if callable(self._help) else self._help

    def get(self):
        try:
            return self._get()
        except Exception:  # NetworkManager not answering: no value
            return None


def options(s):
    """What Enter offers: values to pick from, or None to type one."""
    ch = s.choices
    if isinstance(ch, list):
        return ch
    if ch is cfg.minutes:
        least = 15 if s.key == "power.suspend" else 0  # the power manager's minimum
        return [m for m in MINUTES if m == "never" or int(m) >= least] + [OTHER]
    if ch is cfg.percent_or_off:
        return PERCENT + [OTHER]
    if s.key in ("sound.output", "sound.input"):
        names = cfg.nodes("Sinks" if s.key == "sound.output" else "Sources").values()
        return list(dict.fromkeys(names)) or None
    return None


def plain(text):
    """Captured messages without colours and marks, on one line."""
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    return " ".join(line.strip(" ✓!✗") for line in text.splitlines() if line.strip())


class App:
    def __init__(self, scr):
        self.scr = scr
        self.net = None
        self.rows = (self.net_rows() if c.have("nmcli") else []) + cfg.visible()
        self.sel = 0
        self.top = 0
        self.msg = ""
        self.pending = []  # keys saved in /etc/nixos/meccanicos.toml, waiting for a rebuild
        # The screen: group headings and settings, in order.
        self.lines, group = [], None
        for i, s in enumerate(self.rows):
            g = s.key.split(".")[0]
            if g != group:
                if group:
                    self.lines.append(("gap", None))
                self.lines.append(("group", g))
                group = g
            self.lines.append(("row", i))
        self.load()

    def load(self):
        self.net = cfg.net_status() if c.have("nmcli") else None
        self.values = {s.key: cfg.show(s.get(), s) for s in self.rows}

    def net_rows(self):
        return [
            NetRow("network.connection", lambda: f"now: {cfg.net_summary(self.net)}; Enter: join a Wi-Fi network",
                   lambda: cfg.net_summary(self.net), self.wifi),
            NetRow("network.internet", "Enter: open the sign-in page of a hotel, café or airport network",
                   lambda: cfg.INTERNET.get(self.net["internet"], self.net["internet"]).split(" (")[0], self.signin),
            NetRow("network.vpn", "Enter: turn a VPN on or off, add or import one",
                   lambda: cfg.vpn_summary(self.net), self.vpn),
        ]

    # ---- drawing -------------------------------------------------------------------
    def put(self, y, x, text, attr=0):
        ui.put(self.scr, y, x, text, attr)

    def draw(self):
        scr = self.scr
        scr.erase()
        h, w = scr.getmaxyx()
        if h < 12 or w < 50:
            self.put(0, 0, "Make the window larger.")
            scr.refresh()
            return
        where = "live USB" if not c.installed() else ""
        ui.bar(scr, 0, f"{c.NAME} settings", where)
        body = h - 6  # lines 2 .. h-5
        at = self.lines.index(("row", self.sel))
        if at < self.top:
            self.top = at - 1 if at and self.lines[at - 1][0] == "group" else at
        if at >= self.top + body:
            self.top = at - body + 1
        kw = max(len(s.key) for s in self.rows)
        vw = min(26, max(len(v) for v in self.values.values()))
        for y, (kind, item) in enumerate(self.lines[self.top: self.top + body], start=2):
            if kind == "group":
                self.put(y, 1, item.capitalize(), ui.attr(ui.HEADING))
            elif kind == "row":
                s = self.rows[item]
                v = self.values[s.key]
                v = v if len(v) <= vw else v[: vw - 1] + "…"
                mark = "*" if s.key in self.pending else " "
                line = f"  {s.key:<{kw}}  {v:<{vw}}{mark}"
                ui.row(scr, y, 1, w - 3, line, item == self.sel)
                if mark != " " and item != self.sel:
                    self.put(y, 1 + len(line) - 1, mark, ui.attr(ui.KEY))
        if self.top + body < len(self.lines):
            self.put(h - 5, w - 4, "↓", ui.attr(ui.DIM))
        s = self.rows[self.sel]
        tags = []
        if s.system:
            tags.append("whole computer")
        if s.rebuild and c.installed():
            tags.append("applied by a rebuild, when you leave")
        self.put(h - 4, 1, "─" * (w - 3), ui.attr(ui.BORDER))
        self.put(h - 3, 2, s.help[0].upper() + s.help[1:] + (f"  ({'; '.join(tags)})" if tags else ""), ui.attr(ui.DIM))
        msg = self.msg
        if not msg and not c.installed():
            msg = f"Settings for the installed system (SSH, updates, ...) appear once {c.NAME} is installed."
        if self.msg:
            ui.message(scr, h - 2, 2, msg)
        else:
            self.put(h - 2, 2, msg, ui.attr(ui.DIM))
        ui.keybar(scr, h - 1, KEYS)
        scr.refresh()

    # ---- asking --------------------------------------------------------------------
    def pick(self, label, opts, current=None):
        """A list in a box; returns the chosen option or None (Esc)."""
        h, w = self.scr.getmaxyx()
        ph = min(len(opts) + 2, h - 2)
        pw = min(max(len(o) for o in opts + [label]) + 8, w - 2)
        win = curses.newwin(ph, pw, (h - ph) // 2, (w - pw) // 2)
        win.keypad(True)
        i = opts.index(current) if current in opts else 0
        top, n = 0, ph - 2
        while True:
            top = min(max(top, i - n + 1), i)
            ui.frame(win, label)
            for r, o in enumerate(opts[top: top + n]):
                dot = "•" if o == current else " "
                ui.row(win, 1 + r, 1, pw - 2, f" {dot} {o}", top + r == i)
            win.refresh()
            k = win.get_wch()
            if k in (curses.KEY_UP, "k"):
                i = (i - 1) % len(opts)
            elif k in (curses.KEY_DOWN, "j", "\t"):
                i = (i + 1) % len(opts)
            elif k in (curses.KEY_HOME, "g"):
                i = 0
            elif k in (curses.KEY_END, "G"):
                i = len(opts) - 1
            elif k in ENTER or k == " ":
                return opts[i]
            elif k in (ESC, "q", curses.KEY_LEFT):
                return None

    def prompt(self, label, text="", secret=False):
        """A field to type in, on the message line; returns the text or None (Esc)."""
        ui.cursor(True)
        try:
            while True:
                self.draw()
                h, w = self.scr.getmaxyx()
                self.scr.move(h - 2, 0)
                self.scr.clrtoeol()
                x = ui.put(self.scr, h - 2, 2, f"{label}: ", ui.attr(ui.KEY))
                at = ui.field(self.scr, h - 2, x, max(10, w - x - 3), text, True, secret)
                self.scr.move(h - 2, min(at, w - 2))
                self.scr.refresh()
                k = self.scr.get_wch()
                if k in ENTER:
                    return text.strip()
                if k == ESC:
                    return None
                if (t := ui.typed(text, k)) is not None:
                    text = t
        finally:
            ui.cursor(False)

    # ---- doing ---------------------------------------------------------------------
    def outside(self, title, fn, pause=True):
        """Run fn on the plain terminal (it may ask questions), then come back."""
        curses.endwin()
        c.NO_PROMPT = False
        print(f"\n== {title} ==\n", flush=True)
        try:
            result = fn()
        except (c.Failed, c.UsageError) as e:
            c.bad(str(e))
            result = None
        except KeyboardInterrupt:
            result = None
        if pause is True or (pause == "failed" and result is None):
            try:
                input("\nPress Enter to go back to the settings.")
            except (EOFError, KeyboardInterrupt):
                pass
        c.NO_PROMPT = True
        self.scr.refresh()
        return result

    def apply(self, s, value):
        buf = io.StringIO()
        try:
            with contextlib.redirect_stderr(buf):
                pending = cfg.change(s, value)
        except c.Failed as e:
            if "password" not in str(e) and "terminal is required" not in str(e):
                self.msg = f"✗ {s.key}: {e}"
                return
            # sudo wants a password: ask for it on the terminal.
            pending = self.outside(f"{s.key} = {cfg.show(value, s)}", lambda: cfg.change(s, value), pause=False)
            if pending is None:
                self.msg = f"✗ {s.key}: not changed"
                return
        except (c.UsageError, OSError, ValueError, KeyError) as e:
            self.msg = f"✗ {s.key}: {e}"
            return
        if pending and s.key not in self.pending:
            self.pending.append(s.key)
        self.load()
        extra = plain(buf.getvalue())
        self.msg = f"✓ {s.key} = {self.values[s.key]}" + (f"  ({extra})" if extra else "") + \
                   ("  — applied when you leave" if pending else "")

    def edit(self):
        s = self.rows[self.sel]
        cur = self.values[s.key]
        self.msg = ""
        if isinstance(s, NetRow):
            try:
                s.act()
            except (c.Failed, c.UsageError, OSError) as e:
                self.msg = f"✗ {e}"
            self.load()
            return
        if s.choices is cfg.onoff:
            text = "off" if cur == "on" else "on"
        else:
            opts = options(s)
            text = self.pick(s.key, opts, cur.removesuffix(" min")) if opts else None
            if opts and text is None:
                return
            if text is None or text == OTHER:
                hint = f" (e.g. {s.example})" if s.example else ""
                text = self.prompt(f"{s.key}{hint}", "" if cur == "-" or text == OTHER else cur)
                if text is None:
                    return
            if text.endswith(" min"):
                text = text[:-4]
        try:
            value = s.parse(text)
        except c.UsageError as e:
            self.msg = f"✗ {s.key}: {e}"
            return
        self.apply(s, value)

    # ---- network (changed only here, when asked) ---------------------------------------
    def flash(self, text):
        """A note while something takes a few seconds."""
        self.msg = text
        self.draw()

    def wifi(self):
        if not any(r[1] == "wifi" for r in cfg.nm_rows("DEVICE,TYPE", "device")):
            self.msg = "✗ no Wi-Fi here (a cable works; mos-doctor network checks why)"
            return
        self.flash("Looking for Wi-Fi networks…")
        nets = cfg.wifi_networks()
        width = max([len(n[0]) for n in nets] + [10])
        label = {f"{ssid:<{width}}  {sig:>3}%{'' if secured else '  open'}": (ssid, secured, on)
                 for ssid, sig, secured, on in nets}
        current = next((k for k, v in label.items() if v[2]), None)
        opts = list(label) + [NMTUI]
        if self.net and self.net["type"] == "wifi":
            opts.append(f"Disconnect from {self.net['connection']}")
        self.flash("")
        pick = self.pick("Wi-Fi networks", opts, current)
        if pick is None:
            return
        if pick == NMTUI:
            self.outside("Network (nmtui)", lambda: os.system("nmtui connect"), pause=False)
            return
        if pick.startswith("Disconnect from "):
            c.run("nmcli", "device", "disconnect", self.net["device"], check=True)
            self.msg = f"✓ disconnected from {self.net['connection']}"
            return
        ssid, secured, on = label[pick]
        if on:
            self.msg = f"✓ already connected to {ssid}"
            return
        password = None
        if secured and not cfg.wifi_profile(ssid):
            password = self.prompt(f"Password for {ssid}", secret=True)
            if not password:
                return
        self.flash(f"Connecting to {ssid}…")
        try:
            cfg.wifi_connect(ssid, password)
        except c.Failed:
            if password or not secured:
                raise
            # Remembered, but its password changed: ask for the new one.
            password = self.prompt(f"Password for {ssid}", secret=True)
            if not password:
                return
            self.flash(f"Connecting to {ssid}…")
            cfg.wifi_connect(ssid, password)
        self.msg = f"✓ connected to {ssid}"

    def signin(self):
        self.flash("Looking for the sign-in page…")
        url = cfg.portal_url()
        cfg.open_url(url)
        self.msg = f"✓ opened {url} in the browser: sign in there, then r to refresh"

    def vpn(self):
        have = cfg.vpns()
        label = {f"{name}  ({'on' if on else 'off'})": (name, on) for name, on in have}
        add = "Add a VPN (Network Connections)…"
        imports = {f"Import {cfg.IMPORTS[k]}…": k for k in cfg.vpn_kinds()}
        pick = self.pick("VPN", list(label) + [add] + list(imports))
        if pick is None:
            return
        if pick in label:
            name, on = label[pick]
            if on:
                self.flash(f"Disconnecting {name}…")
                cfg.vpn_down(name)
                self.msg = f"✓ VPN {name} off"
            elif self.outside(f"VPN {name}", lambda: cfg.vpn_up(name) or True, pause="failed"):
                self.msg = f"✓ VPN {name} on"
            else:
                self.msg = f"✗ VPN {name} did not connect"
        elif pick == add:
            if os.environ.get("DISPLAY") and c.have("nm-connection-editor"):
                cfg.vpn_add()
                self.msg = "✓ Network Connections opened: + adds one (then r to refresh)"
            else:
                self.outside("Add a VPN (nmtui)", cfg.vpn_add, pause=False)
        else:
            path = self.prompt("VPN file", "~/Downloads/")
            if not path:
                return
            self.msg = f"✓ VPN added: {cfg.vpn_import(path)} (Enter to turn it on)"

    def export(self):
        path = self.prompt("Export to", "~/mos-settings.toml")
        if not path:
            return
        what = self.pick("Export", ["settings", "settings and dotfiles",
                                    "settings, dotfiles and secrets (encrypted)"], "settings")
        if what is None:
            return
        args = [os.path.expanduser(path)] + (["--dotfiles"] if "dotfiles" in what else []) + \
               (["--with-secrets"] if "secrets" in what else [])
        self.outside("Export", lambda: cfg.cmd_export(args))

    def import_(self):
        path = self.prompt("Import from", "~/mos-settings.toml")
        if not path:
            return
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            self.msg = f"✗ no such file: {path}"
            return
        args = [path]
        folder = os.path.dirname(os.path.abspath(path))
        if any(os.path.exists(os.path.join(folder, f)) for f in ("dotfiles.tar.gz", "dotfiles.tar.gz.age")):
            if self.pick("Its dotfiles too?", ["yes", "no"], "no") == "yes":
                args.append("--dotfiles")
        self.outside("Import", lambda: cfg.cmd_import(args))
        self.load()

    def doctor(self):
        import doctor
        self.outside("Configuration Doctor", lambda: doctor.main([]))
        self.load()

    def leave(self):
        """True to quit: first apply what waits for a rebuild, if wanted."""
        if not self.pending:
            return True
        n = len(self.pending)
        ans = self.pick(f"{n} change{'s need' if n > 1 else ' needs'} a rebuild",
                        ["Rebuild now (a few minutes)", "Later (run mos-rebuild)", "Back to the settings"])
        if ans is None or ans.startswith("Back"):
            return False
        if ans.startswith("Rebuild"):
            def go():
                if os.system("mos-rebuild") != 0:
                    raise c.Failed("the rebuild failed; your previous system is still in the boot menu")
                c.ok("applied")
            self.outside("Rebuilding", go)
        return True

    def run(self):
        while True:
            self.draw()
            k = self.scr.get_wch()
            if k == curses.KEY_RESIZE:
                continue
            if k in (curses.KEY_UP, "k"):
                self.sel = max(0, self.sel - 1)
            elif k in (curses.KEY_DOWN, "j"):
                self.sel = min(len(self.rows) - 1, self.sel + 1)
            elif k in (curses.KEY_PPAGE,):
                self.sel = max(0, self.sel - 10)
            elif k in (curses.KEY_NPAGE,):
                self.sel = min(len(self.rows) - 1, self.sel + 10)
            elif k in (curses.KEY_HOME, "g"):
                self.sel = 0
            elif k in (curses.KEY_END, "G"):
                self.sel = len(self.rows) - 1
            elif k in ENTER or k in (" ", curses.KEY_RIGHT, "l"):
                self.edit()
            elif k == "e":
                self.export()
            elif k == "i":
                self.import_()
            elif k == "d":
                self.doctor()
            elif k == "r":
                self.load()
                self.msg = "refreshed"
            elif k in ("q", ESC):
                if self.leave():
                    return


def main():
    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")  # Esc right away, not after a second

    def start(scr):
        ui.init()
        App(scr).run()

    c.NO_PROMPT = True
    try:
        curses.wrapper(start)
    except curses.error:  # a terminal curses can't drive: the plain list
        cfg.cmd_list([])
    finally:
        c.NO_PROMPT = False
    return 0
