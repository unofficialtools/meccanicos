#!/usr/bin/env python3
"""mos-backup-restore - get files back from a backup, full screen: pick a
backup (newest first), browse its folders, mark files and folders, restore
them into ~/Restored-<date>. Your home folder itself is never changed.

  mos-backup browse            this view (also: mos-backup restore, in a terminal)
  mos-backup versions FILE [--restore ID | --menu]
                               the backed-up versions of one file; --restore puts
                               one next to it, --menu picks one full screen

Started by mos-backup, which has already found the backup (RESTIC_REPOSITORY,
RESTIC_PASSWORD_FILE). Everything goes through restic: snapshots, ls, restore.
"""

import curses
import datetime
import json
import locale
import os
import re
import shutil
import subprocess
import tempfile
import sys

# The look shared by MeccanicOS TUIs: MECCANICOS_PYLIB from the Nix wrapper, else next to this file.
sys.path.insert(0, os.environ.get("MECCANICOS_PYLIB") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import mos_tui as ui  # noqa: E402

HOME = os.path.expanduser("~")
TAG = "meccanicos"


class Failed(Exception):
    pass


def restic(*args, lock=False):
    """Run restic; its output. Never shows the password (restic reads it from
    its file). lock: for restore, which locks like backup does."""
    try:
        p = subprocess.run(["restic", *([] if lock else ["--no-lock"]), *args], capture_output=True, text=True,
                           env=dict(os.environ, LC_ALL="C"))
    except OSError as e:
        raise Failed(f"restic: {e}")
    if p.returncode != 0:
        lines = [l for l in p.stderr.splitlines() if l.strip()]
        if not lines:
            raise Failed("restic failed (is the backup disk plugged in?)")
        try:  # with --json, errors are JSON too
            raise Failed(json.loads(lines[-1])["message"])
        except (ValueError, KeyError, TypeError):
            raise Failed(lines[-1])
    return p.stdout


def when(stamp):
    """restic's time (nanoseconds, offset) as a local datetime."""
    stamp = re.sub(r"(\.\d{6})\d+", r"\1", stamp).replace("Z", "+00:00")
    try:
        return datetime.datetime.fromisoformat(stamp).astimezone()
    except ValueError:
        return None


def snapshots():
    """[{id, short, time, host, paths, files, size}], newest first."""
    found = []
    for s in json.loads(restic("snapshots", "--json", "--tag", TAG) or "[]"):
        summary = s.get("summary") or {}
        found.append({"id": s["id"], "short": s.get("short_id", s["id"][:8]), "time": when(s.get("time", "")),
                      "host": s.get("hostname", ""), "paths": s.get("paths", []),
                      "files": summary.get("total_files_processed"), "size": summary.get("total_bytes_processed")})
    found.sort(key=lambda s: s["time"].timestamp() if s["time"] else 0, reverse=True)
    return found


def ls(sid, path):
    """What is in folder path of snapshot sid: [{name, path, dir, size, mtime}], folders first."""
    found = []
    for line in restic("ls", "--json", sid, path).splitlines():
        try:
            n = json.loads(line)
        except ValueError:
            continue
        if n.get("struct_type") != "node" or n.get("path") == path:
            continue  # the snapshot itself, and the folder asked for
        found.append({"name": n["name"], "path": n["path"], "dir": n.get("type") == "dir",
                      "size": n.get("size"), "mtime": when(n.get("mtime", ""))})
    found.sort(key=lambda e: (not e["dir"], e["name"].casefold()))
    return found


def literal(path):
    """restic --include takes patterns: this one matches path and nothing else."""
    return re.sub(r"([][\\*?])", r"\\\1", path)


def target():
    return os.path.join(HOME, "Restored-" + datetime.datetime.now().strftime("%Y%m%d-%H%M"))


def restore(sid, paths, to):
    """Restore paths (everything if none) of snapshot sid under folder to."""
    if os.path.realpath(to) == "/":
        raise Failed("restoring into / would overwrite your files; pick another folder")
    os.makedirs(to, exist_ok=True)
    restic("restore", sid, "--target", to, *[a for p in paths for a in ("--include", literal(p))], lock=True)
    return to


def versions(path):
    """The backups that have path, newest first: [{snap, size, mtime, changed, now}].
    changed: differs (size or time) from the version before it; now: same as the file today."""
    snaps = {s["id"]: s for s in snapshots()}
    found = []
    for hit in json.loads(restic("find", "--json", "--tag", TAG, literal(path)) or "[]"):
        snap = snaps.get(hit.get("snapshot"))
        m = next((m for m in hit.get("matches") or [] if m.get("path") == path), None)
        if snap and m:
            found.append({"snap": snap, "size": m.get("size"), "mtime": when(m.get("mtime", "")),
                          "dir": m.get("type") == "dir", "stamp": m.get("mtime", "")})
    found.sort(key=lambda v: v["snap"]["time"].timestamp() if v["snap"]["time"] else 0, reverse=True)
    try:
        st = os.stat(path)
    except OSError:
        st = None
    for i, v in enumerate(found):
        older = found[i + 1] if i + 1 < len(found) else None
        v["changed"] = older is None or (v["size"], v["stamp"]) != (older["size"], older["stamp"])
        v["now"] = bool(st and v["mtime"] and (v["dir"] or v["size"] == st.st_size)
                        and abs(v["mtime"].timestamp() - st.st_mtime) < 0.001)
    return found


def note(v):
    return ("changed" if v["changed"] else "unchanged") + (", same as now" if v["now"] else "")


def snapshot(sid):
    """The snapshot with this ID (or prefix, or latest)."""
    snaps = snapshots()
    found = snaps[:1] if sid == "latest" else [s for s in snaps if s["id"].startswith(sid)]
    if len(found) != 1:
        raise Failed(f"no backup {sid}" if not found else f"{sid} matches several backups")
    return found[0]


def next_to(path, snap):
    """Restore path as it was in snap next to it, as "name (YYYY-MM-DD HHMM).ext";
    never overwrites anything. Returns where it went."""
    folder, name = os.path.split(path)
    stem, ext = (name, "") if os.path.isdir(path) else os.path.splitext(name)
    label = snap["time"].strftime("%Y-%m-%d %H%M") if snap["time"] else snap["short"]
    os.makedirs(folder, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=".mos-restore-", dir=folder)
    try:
        restic("restore", snap["id"], "--target", tmp, "--include", literal(path), lock=True)
        got = tmp + path
        if not os.path.lexists(got):
            raise Failed(f"{tilde(path)} is not in the backup of {date(snap['time'])}")
        for n in range(1, 100):
            new = os.path.join(folder, f"{stem} ({label}){'' if n == 1 else f' {n}'}{ext}")
            try:
                if os.path.isdir(got) and not os.path.islink(got):
                    if os.path.lexists(new):
                        continue
                    os.rename(got, new)
                else:
                    os.link(got, new, follow_symlinks=False)  # fails if new exists: never overwrites
                return new
            except FileExistsError:
                continue
        raise Failed("too many restored copies already")
    except OSError as e:
        raise Failed(str(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def human(n):
    if n is None:
        return ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def date(t, full=True):
    if not t:
        return "?"
    return t.strftime("%a %d %b %Y %H:%M" if full else "%d %b %Y %H:%M")


def tilde(path):
    return "~" + path[len(HOME):] if path == HOME or path.startswith(HOME + "/") else path


# ---- full screen ---------------------------------------------------------------------
class App:
    def __init__(self, scr):
        self.scr = scr
        self.view = "snapshots"  # or "browse"
        self.sel = {"snapshots": 0, "browse": 0}
        self.focus = 0
        self.msg, self.err = "", False
        self.snaps, self.snap, self.cwd, self.entries = [], None, "/", []
        self.marked = set()
        self.cache = {}
        self.busy("Reading the list of backups…")
        try:
            self.snaps = snapshots()
            self.say("" if self.snaps else "No backups yet: run mos-backup now.")
        except Failed as e:
            self.say(f"✗ {e}", True)

    def rows(self):
        if self.view == "snapshots":
            return self.snaps
        return ([{"name": "..", "path": os.path.dirname(self.cwd), "dir": True, "up": True}] if self.cwd != "/" else []) + self.entries

    def current(self):
        rows = self.rows()
        if not rows:
            return None
        self.sel[self.view] = min(self.sel[self.view], len(rows) - 1)
        return rows[self.sel[self.view]]

    def buttons(self):
        if self.view == "snapshots":
            return [("Browse", "b", self.browse), ("Restore everything", "e", self.restore_all), ("Quit", "q", None)]
        n = len(self.marked)
        return [("Open", "o", self.open), ("Mark", "m", self.mark),
                (f"Restore {n} marked" if n else "Restore", "r", self.restore_marked),
                ("Back", "b", self.back), ("Quit", "q", None)]

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
        if self.view == "snapshots":
            ui.bar(s, 0, "Restore from a backup › pick a backup")
            head = f"  {'When':<22}{'Computer':<16}{'Files':>9}{'Size':>11}   Backup"
            empty = "No backups to show."
        else:
            ui.bar(s, 0, f"Restore › {date(self.snap['time'], False)} › {tilde(self.cwd)}")
            head = f"  {'':2}{'Name':<44}{'Size':>10}   Changed"
            empty = "This folder is empty in the backup."
        y = 2
        ui.put(s, y, 0, head, ui.attr(ui.HEADING))
        ui.put(s, y + 1, 0, "─" * w, ui.attr(ui.BORDER))
        y += 2
        rows = self.rows()
        list_h = h - y - 6
        cur = self.sel[self.view] = min(self.sel[self.view], max(0, len(rows) - 1))
        top = max(0, cur - list_h + 1)
        if not rows:
            ui.put(s, y, 2, empty, ui.attr(ui.DIM))
        for i, r in enumerate(rows[top: top + list_h]):
            a = ui.attr(ui.NORMAL)
            if self.view == "snapshots":
                files = "" if r["files"] is None else str(r["files"])
                line = f"  {date(r['time']):<22}{r['host'][:15]:<16}{files:>9}{human(r['size']):>11}   {r['short']}"
            elif r.get("up"):
                line = "     .. (the folder above)"
                a = ui.attr(ui.DIM)
            else:
                mark = "✓" if r["path"] in self.marked else " "
                name = r["name"] + ("/" if r["dir"] else "")
                line = f"  {mark} {name[:43]:<44}{'' if r['dir'] else human(r['size']):>10}   {date(r['mtime'], False)}"
                if r["path"] in self.marked:
                    a = ui.attr(ui.OK)
            ui.row(s, y + i, 0, w, line, top + i == cur, a)
        # About the chosen backup / what is marked
        info = ""
        if self.view == "snapshots" and self.snaps:
            snap = self.current()
            info = f"Backed up: {', '.join(tilde(p) for p in snap['paths'])}   Restores go to ~/Restored-<date>; your files are not touched."
        elif self.view == "browse":
            if self.marked:
                names = ", ".join(tilde(p) for p in sorted(self.marked))
                info = f"{len(self.marked)} marked: {names}"
            else:
                info = "Space marks files and folders; r restores them into ~/Restored-<date>."
        ui.put(s, h - 5, 0, "─" * w, ui.attr(ui.BORDER))
        ui.put(s, h - 4, 2, info[: w - 3], ui.attr(ui.DIM))
        ui.buttons(s, h - 3, 1, [(l, k) for l, k, _ in self.buttons()], self.focus)
        ui.message(s, h - 2, 1, ("✗ " if self.err and not self.msg.startswith("✗") else "") + self.msg)
        if self.view == "snapshots":
            keys = [("↑↓", "move"), ("←→", "button"), ("Enter", "press"), ("q", "quit")]
        else:
            keys = [("↑↓", "move"), ("←→", "button"), ("Enter", "press"), ("Space", "mark"),
                    ("Backspace", "folder above"), ("Esc", "backups")]
        ui.keybar(s, h - 1, keys)
        s.refresh()

    def busy(self, msg):
        self.say(msg)
        self.draw()

    # -- actions -------------------------------------------------------------------------
    def browse(self):
        snap = self.current()
        if not snap:
            return self.say("No backup to browse.")
        if snap is not self.snap:
            self.marked, self.cache = set(), {}
        self.snap = snap
        # Start in the home folder that was backed up.
        start = snap["paths"][0] if snap["paths"] else "/"
        self.view, self.focus = "browse", 0
        self.go(start)

    def go(self, path):
        key = path
        if key not in self.cache:
            self.busy(f"Reading {tilde(path)}…")
            try:
                self.cache[key] = ls(self.snap["id"], path)
            except Failed as e:
                return self.say(f"✗ {e}", True)
        came_from = self.cwd
        self.cwd, self.entries = path, self.cache[key]
        self.sel["browse"] = 0
        # Going up: land on the folder we were in.
        for i, r in enumerate(self.rows()):
            if r["path"] == came_from and not r.get("up"):
                self.sel["browse"] = i
        self.say("")

    def up(self):
        if self.cwd != "/":
            self.go(os.path.dirname(self.cwd))

    def open(self):
        r = self.current()
        if not r:
            return
        if r["dir"]:
            self.go(r["path"])
        else:
            self.mark()

    def mark(self):
        r = self.current()
        if not r or r.get("up"):
            return
        self.marked.symmetric_difference_update({r["path"]})
        self.sel["browse"] = min(self.sel["browse"] + 1, len(self.rows()) - 1)

    def back(self):
        self.view, self.focus = "snapshots", 0
        self.say("")

    def do_restore(self, paths):
        snap, to = self.snap, target()
        what = (f"{len(paths)} marked item(s)" if len(paths) > 1 else tilde(paths[0])) if paths else "everything"
        question = (f"Restore {what}\nfrom the backup of {date(snap['time'])}\ninto {tilde(to)}?\n\n"
                    "Your home folder is not changed: copy back what you need.")
        if not ui.confirm(self.scr, question, yes="Restore", title="Restore from backup"):
            return
        self.busy(f"Restoring into {tilde(to)}…")
        try:
            restore(snap["id"], paths, to)
        except Failed as e:
            return self.say(f"✗ {e}", True)
        where = to + (paths[0] if len(paths) == 1 else os.path.commonpath(paths) if paths else (snap["paths"] or [""])[0])
        self.marked = set()
        self.say(f"✓ Restored. Your files are in {tilde(where)}")

    def restore_marked(self):
        paths = sorted(self.marked)
        if not paths:
            r = self.current()
            if not r or r.get("up"):
                return self.say("Mark files or folders first (Space).")
            paths = [r["path"]]
        self.do_restore(paths)

    def restore_all(self):
        self.snap = self.current()
        if not self.snap:
            return self.say("No backup to restore.")
        self.marked, self.cache = set(), {}
        self.do_restore([])

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
            elif k == curses.KEY_PPAGE:
                self.sel[self.view] = max(0, self.sel[self.view] - 10)
            elif k == curses.KEY_NPAGE:
                self.sel[self.view] = min(max(0, n - 1), self.sel[self.view] + 10)
            elif k == curses.KEY_LEFT:
                self.focus = (self.focus - 1) % len(self.buttons())
            elif k in (curses.KEY_RIGHT, "\t"):
                self.focus = (self.focus + 1) % len(self.buttons())
            elif k in ui.ENTER:
                if not self.press(self.focus):
                    return
            elif k == ui.ESC:
                if self.view == "snapshots":
                    return
                self.back()
            elif self.view == "browse" and k == " ":
                self.mark()
            elif self.view == "browse" and k in ui.BACKSPACE:
                self.up()
            elif isinstance(k, str):
                for i, (_, key, _) in enumerate(self.buttons()):
                    if k.lower() == key:
                        self.focus = i
                        if not self.press(i):
                            return
                        break


class Versions:
    """mos-backup versions FILE --menu: the versions of one file, restore one next to it."""

    def __init__(self, scr, path):
        self.scr, self.path = scr, path
        self.sel, self.focus = 0, 0
        self.msg, self.err = "", False
        self.rows = []
        self.busy("Looking through the backups…")
        try:
            self.rows = versions(path)
            self.say("" if self.rows else "No backup has this file yet.")
        except Failed as e:
            self.say(f"✗ {e}", True)

    def say(self, msg, err=False):
        self.msg, self.err = msg, err

    def busy(self, msg):
        self.say(msg)
        self.draw()

    def draw(self):
        s = self.scr
        s.erase()
        h, w = s.getmaxyx()
        if h < 10 or w < 50:
            ui.put(s, 0, 0, "Make the window larger.")
            s.refresh()
            return
        ui.bar(s, 0, f"Versions › {tilde(self.path)}")
        ui.put(s, 2, 0, f"  {'Backup of':<24}{'Size':>10}   {'Last edited':<20}", ui.attr(ui.HEADING))
        ui.put(s, 3, 0, "─" * w, ui.attr(ui.BORDER))
        list_h = h - 10
        self.sel = min(self.sel, max(0, len(self.rows) - 1))
        top = max(0, self.sel - list_h + 1)
        for i, v in enumerate(self.rows[top: top + list_h]):
            line = f"  {date(v['snap']['time']):<24}{'' if v['dir'] else human(v['size']):>10}   {date(v['mtime'], False):<20}{note(v)}"
            ui.row(s, 4 + i, 0, w, line, top + i == self.sel, ui.attr(ui.DIM if not v["changed"] else ui.NORMAL))
        ui.put(s, h - 5, 0, "─" * w, ui.attr(ui.BORDER))
        ui.put(s, h - 4, 2, "Restore puts the chosen version next to the file, with its date in the name.", ui.attr(ui.DIM))
        ui.buttons(s, h - 3, 1, [("Restore next to it", "r"), ("Quit", "q")], self.focus)
        ui.message(s, h - 2, 1, ("✗ " if self.err and not self.msg.startswith("✗") else "") + self.msg)
        ui.keybar(s, h - 1, [("↑↓", "move"), ("←→", "button"), ("Enter", "press"), ("q", "quit")])
        s.refresh()

    def restore(self):
        if not self.rows:
            return self.say("Nothing to restore.")
        v = self.rows[self.sel]
        self.busy(f"Restoring the version of {date(v['snap']['time'])}…")
        try:
            new = next_to(self.path, v["snap"])
        except Failed as e:
            return self.say(f"✗ {e}", True)
        self.say(f"✓ Saved as {os.path.basename(new)}")

    def run(self):
        while True:
            self.draw()
            k = self.scr.get_wch()
            if k == curses.KEY_UP:
                self.sel = max(0, self.sel - 1)
            elif k == curses.KEY_DOWN:
                self.sel = min(max(0, len(self.rows) - 1), self.sel + 1)
            elif k in (curses.KEY_LEFT, curses.KEY_RIGHT, "\t"):
                self.focus = 1 - self.focus
            elif k in ui.ENTER:
                if self.focus == 1:
                    return
                self.restore()
            elif k in (ui.ESC, "q"):
                return
            elif k == "r":
                self.focus = 0
                self.restore()


def cli_versions(args):
    """mos-backup versions FILE [--restore ID | --menu]"""
    if not args or args[0].startswith("--") or len(args) not in (1, 2, 3) or \
            (len(args) == 2 and args[1] != "--menu") or (len(args) == 3 and args[1] != "--restore"):
        print("usage: mos-backup versions FILE [--restore ID | --menu]", file=sys.stderr)
        return 2
    path = os.path.abspath(os.path.expanduser(args[0]))
    try:
        if args[1:2] == ["--menu"]:
            if not sys.stdout.isatty():
                print("mos-backup: --menu needs a terminal", file=sys.stderr)
                return 2
            locale.setlocale(locale.LC_ALL, "")
            os.environ.setdefault("ESCDELAY", "25")
            curses.wrapper(lambda scr: (ui.init(), Versions(scr, path).run()))
        elif args[1:2] == ["--restore"]:
            new = next_to(path, snapshot(args[2]))
            print(f"Restored next to it: {new}")
        else:
            vs = versions(path)
            if not vs:
                print(f"No backup has {path}.", file=sys.stderr)
                return 1
            print(f"Versions of {path}, newest first:")
            for v in vs:
                print(f"  {v['snap']['short']}  {date(v['snap']['time']):<22}{'' if v['dir'] else human(v['size']):>10}  {note(v)}")
    except Failed as e:
        print(f"mos-backup: {e}", file=sys.stderr)
        return 1
    return 0


def main(argv):
    if argv and argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    if not os.environ.get("RESTIC_REPOSITORY"):
        print("mos-backup-restore: start it with mos-backup browse", file=sys.stderr)
        return 2
    if argv[:1] == ["versions"]:
        return cli_versions(argv[1:])
    if not sys.stdout.isatty():
        print("mos-backup-restore: the full-screen view needs a terminal", file=sys.stderr)
        return 2
    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")
    curses.wrapper(lambda scr: (ui.init(), App(scr).run()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
