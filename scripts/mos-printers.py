#!/usr/bin/env python3
"""mos-printers - your printers, full screen: find and add printers, pick
the default one, see what is waiting to print and cancel it.

  mos-printers                 the full-screen view
  mos-printers list            printers (* the default) and their state
  mos-printers discover        printers on the network and on USB
  mos-printers add URI [NAME]  add a printer found by discover
  mos-printers remove NAME
  mos-printers default NAME    print on NAME unless told otherwise
  mos-printers queue [NAME]    what is waiting to print
  mos-printers cancel JOB...   cancel jobs (an id like Office-12), or
  mos-printers cancel --all [NAME]

Network printers (IPP Everywhere, AirPrint) work without drivers; USB
printers use the drivers MeccanicOS ships (Gutenprint, HP, Brother, Epson, ...).
Everything goes through CUPS (lpstat, lpadmin, lpinfo, cancel); changes that
need an administrator use sudo. To print a file: print FILE.
"""

import curses
import locale
import os
import re
import subprocess
import sys

# The look shared by MeccanicOS TUIs: MECCANICOS_PYLIB from the Nix wrapper, else next to this file.
sys.path.insert(0, os.environ.get("MECCANICOS_PYLIB") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import mos_tui as ui  # noqa: E402

ENV = dict(os.environ, LC_ALL="C")  # lpstat's words, to read them
TESTPAGE = os.environ.get("MECCANICOS_TESTPAGE", "/run/current-system/sw/share/cups/data/testprint")
DENIED = re.compile(r"forbidden|not authorized|unauthorized|permission|password", re.I)


class Failed(Exception):
    pass


def run(cmd, admin=False, timeout=30):
    """Run a CUPS command; its output. admin: retried with sudo when CUPS
    says no (the user's sudo needs no password in MeccanicOS)."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, env=ENV, timeout=timeout)
        if p.returncode != 0 and admin and DENIED.search(p.stderr + p.stdout):
            p = subprocess.run(["sudo", "-n", *cmd], capture_output=True, text=True, env=ENV, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Failed(f"{cmd[0]}: {e}")
    if p.returncode != 0:
        lines = [l for l in (p.stderr or p.stdout).splitlines() if l.strip()]
        raise Failed(re.sub(r"^\w+: ", "", lines[-1]) if lines else f"{cmd[0]} failed")
    return p.stdout


# ---- CUPS ------------------------------------------------------------------------
def printers():
    """[{name, state, default, uri, info, location, reason}]."""
    try:
        out = run(["lpstat", "-l", "-p"])
    except Failed:
        return []  # no printers (lpstat says so on stderr) or no CUPS
    found, cur = [], None
    for line in out.splitlines():
        m = re.match(r"printer (\S+) (?:is (\w+)|now printing (\S+?))\.?\s+(enabled|disabled)", line)
        m2 = re.match(r"printer (\S+) disabled", line)
        if m or m2:
            name = (m or m2).group(1)
            if m and m.group(4) == "enabled":
                state = "printing" if m.group(3) else (m.group(2) or "idle")
            else:
                state = "stopped"
            cur = {"name": name, "state": state, "default": False, "uri": "", "info": "", "location": "", "reason": ""}
            found.append(cur)
        elif cur and (m := re.match(r"\s+Description: (.*)", line)):
            cur["info"] = m.group(1).strip()
        elif cur and (m := re.match(r"\s+Location: (.*)", line)):
            cur["location"] = m.group(1).strip()
        elif cur and line.startswith("\t") and not cur["reason"] and ":" not in line:
            cur["reason"] = line.strip()  # why it stopped
    try:
        uris = dict(re.findall(r"device for (\S+): (\S+)", run(["lpstat", "-v"])))
    except Failed:
        uris = {}
    default = default_printer()
    for p in found:
        p["uri"] = uris.get(p["name"], "")
        p["default"] = p["name"] == default
    return found


def default_printer():
    try:
        m = re.search(r"destination: (\S+)", run(["lpstat", "-d"]))
    except Failed:
        return ""
    return m.group(1) if m else ""


def jobs(name=None):
    """[{id, user, size, when}] waiting or printing."""
    try:
        out = run(["lpstat", "-o", *([name] if name else [])])
    except Failed:
        return []
    found = []
    for line in out.splitlines():
        m = re.match(r"(\S+-\d+)\s+(\S+)\s+(\d+)\s+(.*)", line)
        if m:
            found.append({"id": m.group(1), "user": m.group(2), "size": int(m.group(3)), "when": m.group(4).strip()})
    return found


def discover():
    """[{uri, model, info, kind}]: printers CUPS can reach (about 10 s)."""
    out = run(["lpinfo", "--timeout", "8", "-l", "-v"], admin=True, timeout=40)
    found, cur = [], None
    for line in out.splitlines():
        if m := re.match(r"Device: uri = (\S+)", line):
            cur = {"uri": m.group(1), "model": "", "info": "", "class": "", "id": ""}
            found.append(cur)
        elif cur and (m := re.match(r"\s+(class|info|make-and-model|device-id) = (.*)", line)):
            value = m.group(2).strip()
            cur[{"make-and-model": "model", "device-id": "id"}.get(m.group(1), m.group(1))] = "" if value == "Unknown" else value
    # Only real devices (not "network socket" and other bare backends), one
    # entry per printer, preferring the driverless way to reach it.
    rank = {"ipps": 0, "ipp": 1, "dnssd": 2, "usb": 3}
    best = {}
    for d in found:
        scheme = d["uri"].split(":", 1)[0]
        if "://" not in d["uri"] or d["uri"].endswith("://") or scheme not in rank:
            continue
        d["kind"] = "USB" if scheme == "usb" else "network"
        key = (d["model"] or d["info"]).lower() or d["uri"]
        if key not in best or rank[scheme] < rank[best[key]["uri"].split(":", 1)[0]]:
            best[key] = d
    have = {p["uri"] for p in printers()}
    return [d for d in best.values() if d["uri"] not in have]


def queue_name(text):
    """A CUPS printer name: letters, digits, - and _ only."""
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")[:40]
    return name or "Printer"


def driver_for(dev):
    """The model to add dev with: driverless when it can, else a driver."""
    if not dev["uri"].startswith("usb:"):
        return "everywhere"
    if dev.get("id"):
        try:
            for line in run(["lpinfo", "--device-id", dev["id"], "-m"], admin=True, timeout=40).splitlines():
                if line.strip():
                    return line.split()[0]  # the best match comes first
        except Failed:
            pass
    return "everywhere"


def add(uri, name=None, dev=None):
    dev = dev or {"uri": uri}
    name = queue_name(name or dev.get("model") or dev.get("info") or uri.split("/")[-1])
    taken = {p["name"] for p in printers()}
    base, n = name, 2
    while name in taken:
        name, n = f"{base}_{n}", n + 1
    run(["lpadmin", "-p", name, "-E", "-v", uri, "-m", driver_for(dev),
         *(["-D", dev["model"]] if dev.get("model") else [])], admin=True, timeout=90)
    if not default_printer():
        set_default(name)
    return name


def remove(name):
    run(["lpadmin", "-x", name], admin=True)


def set_default(name):
    """For everyone (needs an administrator) and, in any case, for you."""
    try:
        run(["lpadmin", "-d", name], admin=True)
    except Failed:
        pass
    run(["lpoptions", "-d", name])


def resume(name):
    run(["cupsenable", name], admin=True)
    run(["cupsaccept", name], admin=True)


def cancel(ids):
    run(["cancel", *ids], admin=True)


def cancel_all(name=None):
    run(["cancel", "-a", *([name] if name else [])], admin=True)


def test_page(name):
    out = run(["lp", "-d", name, "-t", "Test page", TESTPAGE])
    m = re.search(r"request id is (\S+)", out)
    return m.group(1) if m else ""


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


# ---- full screen ---------------------------------------------------------------------
STATE = {"idle": "ready", "printing": "printing", "stopped": "stopped"}


class App:
    def __init__(self, scr):
        self.scr = scr
        self.view = "printers"  # or "queue", "found"
        self.sel = {"printers": 0, "queue": 0, "found": 0}
        self.focus = 0
        self.msg, self.err = "", False
        self.found = []
        self.load()

    def load(self):
        self.printers = printers()
        cur = self.printer()
        self.jobs = jobs(cur["name"]) if cur and self.view == "queue" else []
        self.counts = {}
        for j in jobs():
            q = j["id"].rsplit("-", 1)[0]
            self.counts[q] = self.counts.get(q, 0) + 1

    def printer(self):
        if not self.printers:
            return None
        self.sel["printers"] = min(self.sel["printers"], len(self.printers) - 1)
        return self.printers[self.sel["printers"]]

    def rows(self):
        return {"printers": self.printers, "queue": self.jobs, "found": self.found}[self.view]

    def buttons(self):
        p = self.printer()
        if self.view == "queue":
            return [("Cancel job", "c", self.cancel_one), ("Cancel all", "a", self.cancel_every),
                    ("Back", "b", self.back), ("Quit", "q", None)]
        if self.view == "found":
            return [("Add", "a", self.add_found), ("Search again", "s", self.find),
                    ("Back", "b", self.back), ("Quit", "q", None)]
        btns = [("Add printers", "a", self.find)]
        if p:
            btns += [("Make default", "d", self.make_default), ("Queue", "u", self.show_queue),
                     ("Test page", "t", self.test)]
            if p["state"] == "stopped":
                btns.append(("Resume", "e", self.resume))
            btns.append(("Remove", "x", self.remove))
        return btns + [("Quit", "q", None)]

    def say(self, msg, err=False):
        self.msg, self.err = msg, err

    # -- drawing ----------------------------------------------------------------------
    def draw(self):
        s = self.scr
        s.erase()
        h, w = s.getmaxyx()
        if h < 12 or w < 60:
            ui.put(s, 0, 0, "Make the window larger.")
            s.refresh()
            return
        p = self.printer()
        title = {"printers": "Printers", "queue": f"Printers › {p['name'] if p else ''} › waiting to print",
                 "found": "Printers › add a printer"}[self.view]
        ui.bar(s, 0, title)
        rows = self.rows()
        y = 2
        if self.view == "printers":
            head = f"  {'':2}{'Printer':<26}{'State':<11}{'Jobs':<6}Where"
            empty = "No printers yet. Press a to look for printers on the network and on USB."
        elif self.view == "queue":
            head = f"  {'Job':<22}{'From':<12}{'Size':<10}Sent"
            empty = "Nothing is waiting to print."
        else:
            head = f"  {'Printer':<40}{'How':<10}Address"
            empty = "No new printers found. Is it on, and on the same network (or plugged in)?"
        ui.put(s, y, 0, head, ui.attr(ui.HEADING))
        ui.put(s, y + 1, 0, "─" * w, ui.attr(ui.BORDER))
        y += 2
        list_h = h - y - 6
        cur = self.sel[self.view] = min(self.sel[self.view], max(0, len(rows) - 1))
        top = max(0, cur - list_h + 1)
        if not rows:
            ui.put(s, y, 2, empty, ui.attr(ui.DIM))
        for i, r in enumerate(rows[top: top + list_h]):
            n = top + i
            if self.view == "printers":
                state = STATE.get(r["state"], r["state"])
                where = r["location"] or r["info"] or r["uri"]
                line = f"  {'★' if r['default'] else ' '} {r['name'][:25]:<26}{state:<11}{self.counts.get(r['name'], 0):<6}{where}"
            elif self.view == "queue":
                line = f"  {r['id'][:21]:<22}{r['user'][:11]:<12}{human(r['size']):<10}{r['when']}"
            else:
                line = f"  {(r['model'] or r['info'])[:39]:<40}{r['kind']:<10}{r['uri']}"
            if n == cur:
                ui.row(s, y + i, 0, w, line, True)
            else:
                ui.put(s, y + i, 0, line, ui.attr(ui.ERR if self.view == "printers" and r["state"] == "stopped" else ui.NORMAL))
        # About the chosen printer
        info = ""
        if self.view == "printers" and p:
            info = p["info"] + (f" — stopped: {p['reason']}" if p["state"] == "stopped" and p["reason"] else "")
            info += "   ★ the default printer" if p["default"] else ""
        ui.put(s, h - 5, 0, "─" * w, ui.attr(ui.BORDER))
        ui.put(s, h - 4, 2, info, ui.attr(ui.DIM))
        ui.buttons(s, h - 3, 1, [(l, k) for l, k, _ in self.buttons()], self.focus)
        ui.message(s, h - 2, 1, ("✗ " if self.err and not self.msg.startswith("✗") else "") + self.msg)
        ui.keybar(s, h - 1, [("↑↓", "move"), ("←→", "button"), ("Enter", "press"), ("r", "reload"), ("q", "quit")])
        s.refresh()

    def busy(self, msg):
        self.say(msg)
        self.draw()

    def confirm(self, question, yes):
        return ui.confirm(self.scr, question, yes=yes)

    # -- actions -------------------------------------------------------------------------
    def act(self, fn, *args, ok=""):
        try:
            fn(*args)
        except Failed as e:
            self.say(f"✗ {e}", True)
            return False
        if ok:
            self.say(f"✓ {ok}")
        self.load()
        return True

    def make_default(self):
        p = self.printer()
        self.act(set_default, p["name"], ok=f"{p['name']} is the default printer.")

    def show_queue(self):
        self.view, self.focus = "queue", 0
        self.load()
        self.say("")

    def back(self):
        self.view, self.focus = "printers", 0
        self.load()

    def test(self):
        p = self.printer()
        self.act(test_page, p["name"], ok=f"Test page sent to {p['name']}.")

    def resume(self):
        p = self.printer()
        self.act(resume, p["name"], ok=f"{p['name']} prints again.")

    def remove(self):
        p = self.printer()
        if self.confirm(f"Remove the printer {p['name']}?", "Remove"):
            self.act(remove, p["name"], ok=f"{p['name']} removed.")

    def cancel_one(self):
        if not self.jobs:
            return self.say("Nothing to cancel.")
        j = self.jobs[self.sel["queue"]]
        self.act(cancel, [j["id"]], ok=f"{j['id']} cancelled.")

    def cancel_every(self):
        p = self.printer()
        if not self.jobs:
            return self.say("Nothing to cancel.")
        if self.confirm(f"Cancel everything waiting on {p['name']}?", "Cancel all"):
            self.act(cancel_all, p["name"], ok="All cancelled.")

    def find(self):
        self.view, self.focus = "found", 0
        self.busy("Looking for printers on the network and on USB (about 10 seconds)…")
        try:
            self.found = discover()
        except Failed as e:
            self.found = []
            return self.say(f"✗ {e}", True)
        self.sel["found"] = 0
        self.say(f"✓ {len(self.found)} new printer(s) found. a adds the chosen one." if self.found
                 else "No new printers found.")

    def add_found(self):
        if not self.found:
            return self.say("Nothing to add: s searches again.")
        d = self.found[self.sel["found"]]
        self.busy(f"Adding {d['model'] or d['uri']}…")
        try:
            name = add(d["uri"], dev=d)
        except Failed as e:
            return self.say(f"✗ {e}", True)
        self.view, self.focus = "printers", 0
        self.load()
        self.sel["printers"] = next((i for i, p in enumerate(self.printers) if p["name"] == name), 0)
        self.say(f"✓ {name} added. t prints a test page.")

    def press(self, i):
        btns = self.buttons()
        if 0 <= i < len(btns):
            fn = btns[i][2]
            if fn is None:
                return False
            fn()
        return True

    def run(self):
        while True:
            self.focus = min(self.focus, len(self.buttons()) - 1)
            self.draw()
            k = self.scr.get_wch()
            n = len(self.rows())
            if k == curses.KEY_UP:
                self.sel[self.view] = max(0, self.sel[self.view] - 1)
            elif k == curses.KEY_DOWN:
                self.sel[self.view] = min(max(0, n - 1), self.sel[self.view] + 1)
            elif k == curses.KEY_LEFT:
                self.focus = (self.focus - 1) % len(self.buttons())
            elif k in (curses.KEY_RIGHT, "\t"):
                self.focus = (self.focus + 1) % len(self.buttons())
            elif k in ui.ENTER:
                if not self.press(self.focus):
                    return
            elif k == ui.ESC:
                if self.view == "printers":
                    return
                self.back()
            elif k == "r":
                self.load()
                self.say("reloaded")
            elif isinstance(k, str):
                for i, (_, key, _) in enumerate(self.buttons()):
                    if k.lower() == key:
                        self.focus = i
                        if not self.press(i):
                            return
                        break


# ---- command line ------------------------------------------------------------------------
def usage_error(problem):
    print(f"mos-printers: {problem} (mos-printers --help)", file=sys.stderr)
    sys.exit(2)


def main(argv):
    if argv and argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    if not argv:
        if not sys.stdout.isatty():
            usage_error("the full-screen view needs a terminal")
        locale.setlocale(locale.LC_ALL, "")
        os.environ.setdefault("ESCDELAY", "25")
        curses.wrapper(lambda scr: (ui.init(), App(scr).run()))
        return 0
    cmd, args = argv[0], argv[1:]
    try:
        if cmd == "list":
            ps = printers()
            if not ps:
                print("No printers yet: mos-printers discover, then mos-printers add URI.")
            for p in ps:
                print(f"{'*' if p['default'] else ' '} {p['name']:<26} {STATE.get(p['state'], p['state']):<9} {p['uri']}")
        elif cmd == "discover":
            for d in discover():
                print(f"{d['uri']}\t{d['kind']}\t{d['model'] or d['info']}")
        elif cmd == "add":
            if not 1 <= len(args) <= 2:
                usage_error("add needs URI [NAME]")
            print(f"Added {add(args[0], args[1] if len(args) > 1 else None)}.")
        elif cmd == "remove":
            if len(args) != 1:
                usage_error("remove needs NAME")
            remove(args[0])
        elif cmd == "default":
            if len(args) != 1:
                usage_error("default needs NAME")
            set_default(args[0])
        elif cmd == "queue":
            js = jobs(args[0] if args else None)
            if not js:
                print("Nothing is waiting to print.")
            for j in js:
                print(f"{j['id']:<24} {j['user']:<12} {human(j['size']):<10} {j['when']}")
        elif cmd == "cancel":
            if args[:1] == ["--all"]:
                cancel_all(args[1] if len(args) > 1 else None)
            elif args:
                cancel(args)
            else:
                usage_error("cancel needs JOB... or --all")
        else:
            usage_error(f"unknown command '{cmd}'")
    except Failed as e:
        print(f"mos-printers: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:  # Ctrl+C: curses.wrapper has restored the terminal
        sys.exit(130)
