"""mos-fleet tui: the fleet, full screen, in the look of the other mos tools.

  mos-fleet                    (in a terminal, with no command) or
  mos-fleet tui [--repo DIR]   the fleet repository's computers, people,
                               groups, profiles, unpushed changes and audit
  mos-fleet tui --demo         made-up data: nothing is read or changed

A front end only: every change runs the same `mos-fleet` command you would
type (and so is checked, committed, and audited on the server the same way),
and nothing reaches the server until Push. It runs in your terminal, as you;
`Shell` leaves it for `mos-fleet shell` and comes back.
"""

import curses
import json
import os
import shlex
import shutil
import subprocess
import sys

from .common import Fail
from .repo import ADMINS, UNLOCK, Repo, fingerprint

try:  # the look shared by MeccanicOS TUIs: next to the package, or in scripts/lib
    import mos_tui as ui
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
    import mos_tui as ui

STATUS = {"M": "changed", "A": "new", "??": "new", "D": "removed", "R": "renamed"}
TABS = ["Computers", "People", "Groups", "Profiles", "Changes", "Audit"]
PANES = ["Logs", "Builds", "Deployments", "Jobs"]
PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ------------------------------------------------------------------ data --
class Live:
    """The admin's clone of the fleet repository, and the server over SSH."""

    demo = False

    def __init__(self, root):
        from . import admin
        self.admin, self.root = admin, root
        self.reload()

    def reload(self):
        self.r = Repo(self.root)

    def server(self, *args):
        return json.loads(self.admin.remote(self.r, *args) or "null")

    # ---- reading
    def title(self):
        d, n = len(self.dirty()), len(self.commits())
        return f"{self.r.fleet.get('organization', '?')} · {self.r.fleet.get('server', '?')}" + \
            (f" · {plural(d, 'file')} not committed" if d else "") + (f" · {n} not pushed" if n else "")

    def hosts(self):
        return self.server("status", "--all", "--json")

    def host(self, name):
        rows = self.server("status", name, "--json")
        return rows[0] if rows else None

    def pane(self, name, which):
        if which == "Logs":
            return self.server("logs", name, "--limit", "500", "--json")
        if which == "Builds":
            return self.server("builds", name, "--log", "--json")
        if which == "Deployments":
            return self.server("deployments", name, "--json")
        return self.server("jobs", name, "--json")

    def job(self, jid):
        return self.server("job", str(jid), "--json")

    def pending(self):
        return self.server("enroll-list", "--json")

    def audit(self):
        return self.server("audit", "--limit", "500", "--json")

    def commits(self):
        p = subprocess.run(["git", "-C", self.root, "log", "--format=%h\t%an\t%ad\t%s", "--date=format:%Y-%m-%d %H:%M",
                            "origin/main..HEAD"], capture_output=True, text=True)
        return [dict(zip(("hash", "author", "date", "subject"), x.split("\t", 3))) for x in p.stdout.splitlines()]

    def dirty(self):
        """The working tree's changes: [(status, path)], as git status says them."""
        p = subprocess.run(["git", "-C", self.root, "status", "--porcelain", "--untracked-files=all"],
                           capture_output=True, text=True)
        return [(x[:2].strip() or "?", x[3:]) for x in p.stdout.splitlines()]

    def diff(self):
        ok, out = self.cli("diff", "--worktree")
        return out

    def discard(self):
        """Back to the last commit: changed files restored, new ones removed."""
        new = [f for st, f in self.dirty() if st == "??"]
        subprocess.run(["git", "-C", self.root, "restore", "--staged", "--worktree", "--source=HEAD", "--", "."],
                       capture_output=True)
        for f in new:
            try:
                os.remove(os.path.join(self.root, f))
                os.removedirs(os.path.dirname(os.path.join(self.root, f)))
            except OSError:
                pass
        left = self.dirty()
        return (not left), ("Discarded: back to the last commit." if not left
                            else "✗ Still changed: " + ", ".join(f for _, f in left))

    # ---- doing: the command line, as typed
    def argv(self, *args):
        me = os.environ.get("MOS_FLEET_CLI")
        base = [me] if me else [sys.executable, "-c", f"import sys; sys.path.insert(0, {PKG!r}); "
                                "from mos_fleet.cli import main; sys.exit(main())"]
        return base + ["--repo", self.root, *args]

    def cli(self, *args, input=None):
        p = subprocess.run(self.argv(*args), input=input, capture_output=True, text=True,
                           stdin=None if input is not None else subprocess.DEVNULL)
        out = (p.stdout + p.stderr).replace("\033[1;31mmos-fleet:\033[0m ", "").strip()
        return p.returncode == 0, out

    def interactive(self, *args):
        return subprocess.call(self.argv(*args))

    def edit_profile(self, name):
        rel = f"profiles/{name}.nix"
        path = os.path.join(self.root, rel)
        before = open(path).read()
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or next(
            (e for e in ("jed", "nano", "vi") if shutil.which(e)), "vi")
        subprocess.call([*shlex.split(editor), path])
        if open(path).read() == before:
            return True, "Nothing changed."
        r = Repo(self.root)
        if r.errors:
            with open(path, "w") as fh:
                fh.write(before)
            return False, "Not changed, it wouldn't be valid: " + "; ".join(r.errors)
        return True, f"Changed, not committed: profile edit {name}"


class Demo(Live):
    """Made-up data, for a look (and the screenshots): nothing is read or changed."""

    demo = True

    def __init__(self, root=None):
        self.r = demo_repo()

    def reload(self):
        pass

    def title(self):
        return "Acme Robotics · fleet.acme.example · 3 files not committed · 1 not pushed"

    def dirty(self):
        return [("M", "groups.toml"), ("??", "people/gverdi.toml"), ("M", "people/tbruno.toml")]

    def discard(self):
        return True, "demo: back to the last commit (nothing was changed)"

    def hosts(self):
        return DEMO_HOSTS

    def host(self, name):
        return next((h for h in DEMO_HOSTS if h["name"] == name), None)

    def pane(self, name, which):
        return demo_pane(name, which)

    def job(self, jid):
        return {"output": "Filesystem      Size  Used Avail Use% Mounted on\n/dev/mapper/root  476G  121G  353G  26% /\n",
                "exit_code": 0}

    def pending(self):
        return [dict(host="lab-07", profile="lab", created_on="2026-10-12 16:02:11", created_by="arossi",
                     state="introduced", fingerprint="SHA256:7mKq0xY3dWbR2vNf8LhTzC1pEo5sJ9aUiG4kXwQe6Bc"),
                dict(host="front-desk", profile="office", created_on="2026-10-13 08:15:40", created_by="mbianchi",
                     state="waiting", fingerprint=None)]

    def audit(self):
        return DEMO_AUDIT

    def commits(self):
        return [dict(hash="8b07f3d", author="Anna Rossi", date="2026-10-13 09:50", subject="lab-gpu: on the testing branch")]

    def diff(self):
        return ("lab-01:\n   + gverdi may log in\n   - tbruno may no longer log in\n"
                "lab-02:\n   + gverdi may log in\n   - tbruno may no longer log in\n"
                "lab-gpu:\n   branch: main -> testing\n   + gverdi may log in\n   - tbruno may no longer log in")

    def cli(self, *args, input=None):
        return True, f"demo: mos-fleet {shlex.join(args)} (nothing was changed)"

    def interactive(self, *args):
        print(f"demo: mos-fleet {shlex.join(args)}\n(Enter to go back)")
        input()
        return 0

    def edit_profile(self, name):
        return True, f"demo: your editor on profiles/{name}.nix, then a commit"


# ------------------------------------------------------------------ the screen --
class App:
    def __init__(self, scr, data):
        self.scr, self.d = scr, data
        self.tab, self.pane_i = 0, 0
        self.host = None  # a computer's page, when open
        self.pending_view = False
        self.sel, self.top, self.focus = {}, {}, 0
        self.search = ""
        self.msg = ""
        self.cache = {}
        self.edits = []  # this session's edits not committed yet: the commit message's start
        self.load()

    # ---- data, with a spinner while the server answers
    def fetch(self, key, fn, *args):
        if key not in self.cache:
            try:
                self.cache[key] = ui.wait(self.scr, "Asking the server…", fn, *args) if self.scr else fn(*args)
            except (Fail, OSError, ValueError) as e:
                self.cache[key] = []
                self.say(f"✗ {e}")
        return self.cache[key]

    def load(self, keep=False):
        if not keep:
            self.cache = {}
        self.d.reload()
        if self.d.r.errors:
            self.say("✗ the repository has problems: " + "; ".join(self.d.r.errors)[:300])
        self.head = self.d.title()

    def view(self):
        if self.host:
            return f"host:{PANES[self.pane_i]}"
        if self.pending_view:
            return "pending"
        return TABS[self.tab]

    def rows(self):
        """(rows for the list, column heading, empty text, text rows?)"""
        v, r = self.view(), self.d.r
        if v == "Computers":
            hosts = self.fetch("hosts", self.d.hosts)
            self.fetch("pending", self.d.pending)  # for the Waiting button's count
            known = {h["name"] for h in hosts}
            hosts = hosts + [dict(name=n, online=False, last_seen="-", profile=t["profile"], branch=t.get("branch", "main"),
                                  state="not pushed yet", current_rev="") for n, t in r.hosts.items() if n not in known]
            rows = [(h, f"  {'●' if h['online'] else '○'} {h['name']:<15}{(h['profile'] or '') + '/' + (h['branch'] or ''):<17}"
                        f"{h['current_rev'] or '-':<12}{h['state'][:37]:<38}{h['last_seen']}") for h in hosts]
            head = f"    {'Computer':<15}{'Profile/branch':<17}{'Runs':<12}{'State':<38}Last seen (UTC)"
            return rows, head, "No computers yet: Add computer."
        if v == "pending":
            rows = [(e, f"  {e['host']:<15}{e['profile']:<12}{e['created_on']:<21}{e['created_by']:<12}"
                        + {"introduced": "installed: take it in (Add to fleet)", "expired": "expired",
                           "waiting": "waiting for its installation"}[e["state"]]) for e in self.fetch("pending", self.d.pending)]
            return rows, f"  {'Computer':<15}{'Profile':<12}{'Prepared (UTC)':<21}{'By':<12}State", "Nothing waiting."
        if v == "People":
            rows = []
            for n, p in sorted(r.people.items()):
                where = [h for h in sorted(r.hosts) if n in r.allowed(h)]
                notes = ", ".join(x for x, on in (("disabled", p.get("disabled")), ("admin key", p.get("age_recipient")),
                                                  (plural(len(p.get("ssh_keys", [])), "SSH key"), p.get("ssh_keys"))) if on)
                rows.append((dict(p, id=n), f"  {n:<12}{p['name'][:22]:<23}{', '.join(p.get('groups', []))[:24]:<25}"
                                            f"{plural(len(where), 'computer'):>13}     {notes}"))
            return rows, f"  {'Name':<12}{'Full name':<23}{'Groups':<25}{'Logs in on':<19}Notes", "Nobody yet: Add."
        if v == "Groups":
            rows = []
            for g, t in r.groups.items():
                members = sorted(n for n, p in r.people.items() if g in p.get("groups", []))
                rows.append((dict(t, id=g, members=members), f"  {g:<15}{t['gid']:<7}{'yes' if t.get('sudo') else '':<6}"
                                                                 f"{', '.join(t.get('profiles', []))[:19]:<20}{', '.join(members)}"))
            return rows, f"  {'Group':<15}{'GID':<7}{'Sudo':<6}{'Logs in on':<20}Members", "No groups."
        if v == "Profiles":
            rows = []
            for p in sorted(r.profiles):
                gs = [g for g in r.groups if r.allows(g, p) and g != ADMINS]
                hs = r.hosts_of(p)
                rows.append((dict(id=p), f"  {p:<14}{len(hs):>3}  {', '.join(hs)[:44]:<46}{', '.join(gs)}"))
            return rows, f"  {'Profile':<14}{'Computers':<51}Groups", "No profiles yet: Add."
        if v == "Changes":
            dirty, commits = self.fetch("dirty", self.d.dirty), self.fetch("commits", self.d.commits)
            rows = []
            if dirty:
                rows += [(None, "Not committed:")] + [(None, f"    {STATUS.get(st, st):<10}{f}") for st, f in dirty] + [(None, "")]
            if commits:
                rows += [(None, "Committed, not pushed:")] + [
                    (None, f"    {c['hash']}  {c['date']}  {c['author'][:16]:<17}{c['subject']}") for c in commits] + [(None, "")]
            if rows:
                rows += [(None, "What changes where, once pushed:")] + \
                        [(None, "    " + x) for x in self.fetch("diff", self.d.diff).splitlines()]
            return [(i, "  " + x) for i, x in rows], "  Not on the server yet", "Nothing changed: everything is committed and pushed."
        if v == "Audit":
            rows = [(e, f"  {e['time']:<21}{e['actor'][:13]:<14}{e['action'][:17]:<18}{(e['target'] or '')[:15]:<16}"
                        f"{e['details'] or ''}") for e in self.fetch("audit", self.d.audit)]
            return rows, f"  {'When (UTC)':<21}{'Who':<14}{'What':<18}{'On':<16}Details", "Nothing yet."
        # a computer's pane
        which = PANES[self.pane_i]
        items = self.fetch(f"{self.host}:{which}", self.d.pane, self.host, which)
        if which == "Logs":
            rows = [(e, f"  {e['time'][5:]:<16}{(e['unit'] or '?').removesuffix('.service')[:22]:<23}{e['message']}")
                    for e in reversed(items)]
            return rows, f"  {'When (UTC)':<16}{'Unit':<23}Message (newest first)", "No log lines."
        if which == "Builds":
            rows = [(b, f"  {b['started']:<21}{b['branch'] or '':<10}{(b['rev'] or '')[:10]:<12}"
                        f"{'ok' if b['ok'] else 'FAILED' if b['ok'] is False else 'building'}") for b in items]
            return rows, f"  {'Started (UTC)':<21}{'Branch':<10}{'Revision':<12}Result", "No builds."
        if which == "Deployments":
            rows = [(x, f"  {x['started']:<21}{(x['rev'] or '')[:10]:<12}{x['result'] or '?':<10}"
                        f"{os.path.basename(x['to_system'] or '')[33:]}") for x in items]
            return rows, f"  {'Started (UTC)':<21}{'Revision':<12}{'Result':<10}System", "No deployments."
        rows = [(j, f"  {j['id']:<7}{j['created_on']:<21}{j['kind']:<8}{j['state']:<10}{j['created_by'][:11]:<12}{j['command']}")
                for j in items]
        return rows, f"  {'Job':<7}{'Created (UTC)':<21}{'Kind':<8}{'State':<10}{'By':<12}Command", "No jobs."

    def shown(self):
        rows, head, empty = self.rows()
        if self.search:
            s = self.search.lower()
            rows = [x for x in rows if s in x[1].lower()]
        return rows, head, empty

    def chosen(self):
        rows = self.shown()[0]
        i = self.sel.get(self.view(), 0)
        return rows[i][0] if rows and i < len(rows) else None

    # ---- buttons: (label, key, action)
    def buttons(self):
        v, c = self.view(), self.chosen()
        quit_ = ("Quit", "q", None)
        if v.startswith("host:"):
            return [("View", "v", self.open_item), ("Run", "u", self.run_here), ("Shell", "s", self.shell), ("Switch", "w", lambda: self.job("switch")),
                    ("Reboot", "b", lambda: self.job("reboot")), ("Facts", "f", lambda: self.job("facts")),
                    ("Profile", "p", self.set_profile), ("Recovery key", "k", self.recover),
                    ("Retire", "t", self.retire), ("Back", "", self.back)]
        if v == "pending":
            return [("Add to fleet", "a", self.host_add), ("Back", "", self.back)]
        if v == "Computers":
            n = len([e for e in self.cache.get("pending", []) if e["state"] == "introduced"])
            return [("Open", "o", self.open_host), ("Add computer", "a", self.prepare),
                    (f"Waiting ({n})" if n else "Waiting", "w", self.show_pending), ("Run", "u", self.run_profile), quit_]
        if v == "People":
            off = c and c.get("disabled")
            return [("Edit", "e", self.person_edit), ("Add", "a", self.person_add), ("Password", "p", self.password),
                    ("Enable" if off else "Disable", "d", self.person_toggle), ("Remove", "m", self.person_remove), quit_]
        if v == "Groups":
            return [("Edit", "e", self.group_edit), ("Members", "m", self.members), ("Add", "a", self.group_add),
                    ("Remove", "v", self.group_remove), quit_]
        if v == "Profiles":
            return [("Edit", "e", self.profile_edit), ("Add", "a", self.profile_add),
                    ("Remove", "m", self.profile_remove), quit_]
        if v == "Changes":
            return [("Commit", "c", self.commit), ("Discard", "d", self.discard), ("Push", "p", self.push),
                    ("Validate", "v", self.validate), ("Upgrade", "u", self.upgrade), quit_]
        return [quit_]

    # ---- helpers for actions
    def say(self, msg):
        self.msg = msg

    def do(self, *args, input=None, note="Working…", show=False, reload=True):
        """Run a mos-fleet command; its last line on the message line (all of it: show).
        Edits of the repository only change the files (--no-commit): Commit, in
        Changes, commits them all at once."""
        edit = args[0] == "member" or (args[0] in ("person", "group", "profile", "host")
                                       and args[1] not in ("prepare", "list", "pending", "show"))
        if edit:
            args += ("--no-commit",)
        ok, out = ui.wait(self.scr, note, self.d.cli, *args, input=input)
        if ok and edit:
            self.edits.append(" ".join(x for x in args[:3] if not x.startswith("-")))
        if reload:
            self.load()
        if show and out:
            pager(self.scr, f"mos-fleet {args[0]}", out)
        lines = [x for x in out.splitlines() if x.strip() and not x.startswith("   (")]
        self.say(("✓ " if ok else "✗ ") + (lines[-1].strip() if lines else ("done" if ok else "failed")))
        return ok

    def need(self, what="a line"):
        c = self.chosen()
        if not c:
            self.say(f"Choose {what} first.")
        return c

    def outside(self, fn, *args):
        """Leave the full screen for a program that needs the terminal (ssh, an editor)."""
        curses.def_prog_mode()
        curses.endwin()
        try:
            return fn(*args)
        finally:
            curses.reset_prog_mode()
            self.scr.clear()

    def go(self, tab):
        self.tab, self.host, self.pending_view, self.focus, self.search = tab, None, False, 0, ""

    def back(self):
        self.host, self.pending_view, self.focus, self.search = None, False, 0, ""

    # ---- computers
    def open_host(self):
        c = self.need("a computer")
        if c:
            self.host, self.pane_i, self.focus, self.search = c["name"], 0, 0, ""
            self.cache.pop(f"host:{c['name']}", None)

    def show_pending(self):
        self.pending_view, self.focus = True, 0

    def prepare(self):
        r = self.d.r
        if not r.profiles:
            return self.say("No profiles yet: add one in Profiles first.")
        f = form(self.scr, "Add a computer", [
            ("Name", "name", "", "text"), ("Profile", "profile", sorted(r.profiles), "choice"),
            ("Disk unlock", "unlock", ["tang", "tpm-pin", "fido2"], "choice"), ("Branch", "branch", "main", "text"),
            ("Disk serial (optional)", "serial", "", "text"), ("Stick folder (empty: the stick)", "to", "", "text")],
            "Prepare", note="A one-time key and its settings go on the MeccanicOS stick;\n"
                            "install with it, then take the computer in (Waiting).")
        if f:
            args = ["host", "prepare", f["name"], "--profile", f["profile"], "--unlock", f["unlock"], "--branch", f["branch"]]
            args += (["--disk-serial", f["serial"]] if f["serial"] else []) + (["--to", f["to"]] if f["to"] else [])
            self.do(*args, note="Preparing (the server, the stick)…", show=True)

    def host_add(self):
        e = self.need("a computer")
        if not e:
            return
        if e["state"] != "introduced":
            return self.say(f"{e['host']} hasn't been installed yet (or its key expired).")
        if ui.confirm(self.scr, f"Take {e['host']} into the fleet?\n\nIts installer showed a fingerprint: is it\n\n"
                                f"    {e['fingerprint']}\n\nIf it differs, say no: it isn't your computer.",
                      yes="Same: add it", no="No", title="Compare the fingerprint"):
            self.do("host", "add", e["host"], "--yes")

    def run_profile(self):
        r = self.d.r
        f = form(self.scr, "Run a command", [("On the computers of", "profile", sorted(r.profiles) or ["-"], "choice"),
                                             ("Command", "cmd", "", "text")], "Run",
                 note="As root, at once on those online (later on the others);\nthe output comes back here.")
        if f and f["cmd"].strip():
            self.do("run", "--profile", f["profile"], "--", *shlex.split(f["cmd"]), note="Running…", show=True, reload=False)

    def run_here(self):
        f = form(self.scr, f"Run a command on {self.host}", [("Command", "cmd", "", "text")], "Run",
                 note="As root; the output comes back here.")
        if f and f["cmd"].strip():
            self.do("run", "--host", self.host, "--", *shlex.split(f["cmd"]), note="Running…", show=True, reload=False)
            self.cache.pop(f"{self.host}:Jobs", None)

    def job(self, kind):
        if kind != "reboot" or ui.confirm(self.scr, f"Restart {self.host} now? Whoever uses it loses unsaved work.",
                                          yes="Restart"):
            self.do(kind, self.host, reload=False)
            self.cache.pop(f"{self.host}:Jobs", None)

    def shell(self):
        self.outside(self.d.interactive, "shell", self.host)

    def set_profile(self):
        r = self.d.r
        t = r.hosts.get(self.host, {})
        f = form(self.scr, f"{self.host}", [
            ("Profile", "profile", sorted(r.profiles), "choice", t.get("profile")),
            ("Branch", "branch", t.get("branch", "main"), "text"),
            ("Disk unlock", "unlock", list(UNLOCK), "choice", t.get("unlock"))], "Save")
        if f:
            self.do("host", "set", self.host, "--profile", f["profile"], "--branch", f["branch"], "--unlock", f["unlock"])

    def recover(self):
        if ui.confirm(self.scr, f"Show {self.host}'s disk recovery key?\nThe server records who asked (audit).",
                      yes="Show it"):
            ok, out = ui.wait(self.scr, "Asking the server…", self.d.cli, "recover", self.host)
            if self.d.demo:
                out = (f"Recovery key for {self.host} (host key SHA256:Qm4Lr8sWd0aV2kXcF7nJ1tYhB9eZ3uPgO6iT5vRw2Xs):\n\n"
                       "    rkey-4F7Q-9XKD-2MWB-H8TC-6PZA-3LVN\n\n"
                       "Type it when the computer asks for the disk password at power-on.")
            pager(self.scr, "Recovery key", out)
            self.say("")

    def retire(self):
        if ui.confirm(self.scr, f"Retire {self.host}? It leaves the repository (a commit);\nafter Push, the server "
                                "refuses it. Its recovery key stays.", yes="Retire"):
            if self.do("host", "retire", self.host):
                self.back()

    # ---- people
    def person_add(self):
        r = self.d.r
        f = form(self.scr, "Add a person", [
            ("User name", "name", "", "text"), ("Full name", "full", "", "text"), ("Email", "email", "", "text"),
            ("Groups (comma)", "groups", "", "text"), ("SSH key (optional)", "key", "", "text")], "Add",
            note=f"Groups: {', '.join(r.groups)}")
        if f:
            args = ["person", "add", f["name"], f["full"]] + (["--email", f["email"]] if f["email"] else [])
            args += [x for g in split(f["groups"]) for x in ("--group", g)] + (["--ssh-key", f["key"]] if f["key"] else [])
            self.do(*args)

    def person_edit(self):
        p = self.need("a person")
        if not p:
            return
        f = form(self.scr, f"Edit {p['id']}", [
            ("Full name", "full", p["name"], "text"),
            ("Email", "email", p.get("email") or "", "text"),
            ("Groups (comma)", "groups", ", ".join(p.get("groups", [])), "text"),
            ("Add an SSH key", "key", "", "text"), ("Admin key (age1…)", "age", p.get("age_recipient") or "", "text")],
            "Save", note="SSH keys now: " + (", ".join(fingerprint_of(k) for k in p.get("ssh_keys", [])) or "none"))
        if not f:
            return
        old, new = set(p.get("groups", [])), set(split(f["groups"]))
        args = ["person", "edit", p["id"], "--full-name", f["full"], "--email", f["email"], "--age-recipient", f["age"]]
        args += [x for g in sorted(new - old) for x in ("--add-group", g)]
        args += [x for g in sorted(old - new) for x in ("--remove-group", g)]
        args += ["--add-ssh-key", f["key"]] if f["key"] else []
        self.do(*args)

    def password(self):
        p = self.need("a person")
        if not p:
            return
        f = form(self.scr, f"{p['id']}'s password", [("New password", "a", "", "secret"), ("Again", "b", "", "secret")],
                 "Set", note="Only its hash leaves this computer; every computer\nwhere they may log in gets it in seconds.")
        if not f:
            return
        if f["a"] != f["b"]:
            return self.say("✗ The two differ: nothing changed.")
        self.do("password", "set", p["id"], "--stdin", input=f["a"] + "\n", reload=False)

    def person_toggle(self):
        p = self.need("a person")
        if p:
            off = p.get("disabled")
            if off or ui.confirm(self.scr, f"Disable {p['id']}? After Push they can't log in anywhere.", yes="Disable"):
                self.do("person", "enable" if off else "disable", p["id"])

    def person_remove(self):
        p = self.need("a person")
        if p and ui.confirm(self.scr, f"Remove {p['id']} from the repository?\nTheir home folders stay on the computers.",
                            yes="Remove"):
            self.do("person", "remove", p["id"])

    # ---- groups
    def group_add(self):
        f = form(self.scr, "Add a group", [
            ("Name", "name", "", "text"), ("Logs in on (profiles, comma; * all)", "profiles", "", "text"),
            ("Sudo", "sudo", False, "check"), ("Description", "desc", "", "text")], "Add",
            note=f"Profiles: {', '.join(sorted(self.d.r.profiles)) or 'none yet'}")
        if f:
            args = ["group", "add", f["name"]] + [x for p in split(f["profiles"]) for x in ("--profile", p)]
            self.do(*args, *(["--sudo"] if f["sudo"] else []), *(["--description", f["desc"]] if f["desc"] else []))

    def group_edit(self):
        g = self.need("a group")
        if not g:
            return
        f = form(self.scr, f"Edit {g['id']}", [
            ("Logs in on (profiles, comma; * all)", "profiles", ", ".join(g.get("profiles", [])), "text"),
            ("Sudo", "sudo", bool(g.get("sudo")), "check"), ("Description", "desc", g.get("description") or "", "text")],
            "Save")
        if f:
            old, new = set(g.get("profiles", [])), set(split(f["profiles"]))
            args = ["group", "edit", g["id"], "--sudo" if f["sudo"] else "--no-sudo", "--description", f["desc"]]
            args += [x for p in sorted(new - old) for x in ("--add-profile", p)]
            args += [x for p in sorted(old - new) for x in ("--remove-profile", p)]
            self.do(*args)

    def members(self):
        g = self.need("a group")
        if not g:
            return
        f = form(self.scr, f"Members of {g['id']}", [("Members (comma)", "m", ", ".join(g["members"]), "text")], "Save",
                 note="People: " + ", ".join(sorted(self.d.r.people)))
        if f:
            old, new = set(g["members"]), set(split(f["m"]))
            for n in sorted(new - old):
                if not self.do("member", "add", g["id"], n):
                    return
            for n in sorted(old - new):
                if not self.do("member", "remove", g["id"], n):
                    return
            if old == new:
                self.say("Nothing changed.")

    def group_remove(self):
        g = self.need("a group")
        if g and ui.confirm(self.scr, f"Remove the group {g['id']}?", yes="Remove"):
            self.do("group", "remove", g["id"])

    # ---- profiles
    def profile_add(self):
        f = form(self.scr, "Add a profile", [("Name", "name", "", "text"), ("And a group of the same name", "group", True, "check")],
                 "Add", note="A kind of computer: profiles/NAME.nix says what it runs;\nits group, who may log in.")
        if f:
            self.do("profile", "add", f["name"], *([] if f["group"] else ["--no-group"]))

    def profile_edit(self):
        p = self.need("a profile")
        if p:
            ok, out = self.outside(self.d.edit_profile, p["id"])
            self.load()
            if ok and out.startswith("Changed"):
                self.edits.append(f"profile edit {p['id']}")
            self.say(("✓ " if ok else "✗ ") + out)

    def profile_remove(self):
        p = self.need("a profile")
        if p and ui.confirm(self.scr, f"Remove the profile {p['id']}?", yes="Remove"):
            self.do("profile", "remove", p["id"])

    # ---- changes
    def commit(self):
        dirty = self.d.dirty()
        if not dirty:
            return self.say("Nothing to commit.")
        f = form(self.scr, "Commit", [("Message", "m", "; ".join(self.edits), "text")], "Commit",
                 note="Every change below, as one commit:\n" + "\n".join(
                     f"  {STATUS.get(st, st):<10}{p}" for st, p in dirty[:8]) + ("\n  …" if len(dirty) > 8 else ""))
        if f is None:
            return
        if not f["m"].strip():
            return self.say("✗ A message, please: what changed, and why.")
        if self.do("commit", "-m", f["m"].strip()):
            self.edits = []

    def discard(self):
        dirty = self.d.dirty()
        if not dirty:
            return self.say("Nothing to discard.")
        if ui.confirm(self.scr, "Discard every change not committed?\n\n" + "\n".join(
                f"  {STATUS.get(st, st):<10}{p}" for st, p in dirty[:10]) + ("\n  …" if len(dirty) > 10 else ""),
                yes="Discard"):
            ok, out = self.d.discard()
            self.load()
            self.edits = []
            self.say(("✓ " if ok else "") + out)

    def push(self):
        if self.d.dirty():
            return self.say("✗ Changes not committed: Commit them (or Discard) first.")
        if not self.d.commits():
            return self.say("Everything is pushed.")
        if ui.confirm(self.scr, "Push? It is checked (and every computer evaluated) first;\nthen the server builds, "
                                "and each computer switches within minutes.", yes="Push"):
            self.do("push", note="Checking every computer (nix), then pushing…", show=True)

    def validate(self):
        self.do("validate", note="Checking the files, and evaluating every computer (nix)…", show=True, reload=False)

    def upgrade(self):
        f = form(self.scr, "Upgrade MeccanicOS", [("First the testing branch only", "testing", True, "check")], "Upgrade",
                 note="The newest MeccanicOS for the fleet (flake.lock): checked,\ncommitted and pushed.")
        if f:
            self.do("upgrade", *(["--testing"] if f["testing"] else []), note="Upgrading (nix flake update)…", show=True)

    def open_item(self):
        """Enter on a list line: what it is about."""
        v, c = self.view(), self.chosen()
        if not c:
            return
        if v == "Computers":
            return self.open_host()
        if v == "pending":
            return self.host_add()
        if v == "People":
            return self.person_edit()
        if v == "Groups":
            return self.group_edit()
        if v == "Profiles":
            return self.profile_edit()
        if v == "host:Builds":
            return pager(self.scr, f"Build of {(c['rev'] or '')[:10]} for {self.host}", c.get("log") or "(no log)")
        if v == "host:Deployments":
            return pager(self.scr, f"Deployment of {(c['rev'] or '')[:10]}", c.get("output") or "(no output)")
        if v == "host:Jobs":
            j = ui.wait(self.scr, "Asking the server…", self.d.job, c["id"])
            return pager(self.scr, f"Job {c['id']}: {c['kind']} {c['command']}",
                         (j.get("output") or "(no output)") + f"\n\nexit {j.get('exit_code')}")
        if v == "host:Logs":
            return pager(self.scr, f"{c['time']} {c['unit']}", c["message"])

    # ---- drawing
    def draw(self):
        s = self.scr
        s.erase()
        h, w = s.getmaxyx()
        if h < 16 or w < 80:
            ui.put(s, 0, 0, "Make the window larger (80x16 at least).")
            s.refresh()
            return
        v = self.view()
        if self.host:
            ui.bar(s, 0, f"Fleet › Computers › {self.host}", self.head)
            tabs(s, 1, PANES, self.pane_i)
            y = self.draw_host(3)
        else:
            ui.bar(s, 0, "Fleet › " + ("Computers › waiting" if v == "pending" else v), self.head)
            tabs(s, 1, TABS, self.tab)
            y = 3
        rows, head, empty = self.shown()
        ui.put(s, y, 0, head, ui.attr(ui.HEADING))
        ui.put(s, y + 1, 0, "─" * w, ui.attr(ui.BORDER))
        y += 2
        list_h = h - y - 4
        key = v
        cur = self.sel[key] = min(self.sel.get(key, 0), max(0, len(rows) - 1))
        top = self.top.get(key, 0)
        top = min(max(top, cur - list_h + 1), cur)
        self.top[key] = top
        if not rows:
            ui.put(s, y, 2, "Nothing matches “" + self.search + "”." if self.search else empty, ui.attr(ui.DIM))
        selectable = v != "Changes"
        for i, (item, line) in enumerate(rows[top: top + list_h]):
            if selectable and top + i == cur:
                ui.row(s, y + i, 0, w, line, True)
            else:
                ui.put(s, y + i, 0, line, self.colour(v, item, line))
                if v == "Computers" and item:
                    ui.put(s, y + i, 2, "●" if item["online"] else "○", ui.attr(ui.OK if item["online"] else ui.DIM))
        if top + list_h < len(rows):
            ui.put(s, h - 5, w - 3, "↓", ui.attr(ui.DIM))
        ui.put(s, h - 4, 0, "─" * w, ui.attr(ui.BORDER))
        ui.buttons(s, h - 3, 1, [(l, k) for l, k, _ in self.buttons()], self.focus)
        if self.search:
            ui.put(s, h - 2, 1, f"/{self.search}", ui.attr(ui.KEY))
        else:
            ui.message(s, h - 2, 1, self.msg[: w - 2])
        keys = [("↑↓", "move"), ("←→", "button"), ("Enter", "press")]
        keys += [("1-4", "pane")] if self.host else [("1-6", "tab")]
        keys += [("/", "search"), ("r", "reload"), ("Esc", "back" if self.host or self.pending_view else "quit")]
        ui.keybar(s, h - 1, keys)
        s.refresh()

    def draw_host(self, y):
        s, r = self.scr, self.d.r
        hs = self.fetch(f"host:{self.host}", self.d.host, self.host) or {}
        t = r.hosts.get(self.host, {})
        allowed = r.allowed(self.host) if self.host in r.hosts else {}
        on = hs.get("online")
        x = ui.put(s, y, 2, "● online" if on else "○ offline", ui.attr(ui.OK if on else ui.DIM))
        x = ui.put(s, y, x, f"   last seen {hs.get('last_seen', '-')}   address {hs.get('address') or '-'}", ui.attr(ui.NORMAL))
        state = hs.get("state", "-")
        bad = "fail" in state
        ui.put(s, y + 1, 2, f"{'Profile':<10}{t.get('profile', '-')} · branch {t.get('branch', 'main')} · "
                            f"disk unlock {t.get('unlock', '-')}", ui.attr(ui.NORMAL))
        x = ui.put(s, y + 2, 2, f"{'State':<10}", ui.attr(ui.NORMAL))
        x = ui.put(s, y + 2, x, state, ui.attr(ui.ERR if bad else ui.OK if state == "up to date" else ui.KEY))
        ui.put(s, y + 2, x, f"   runs {hs.get('current_rev') or '-'} · wanted {hs.get('desired_rev') or '-'}", ui.attr(ui.DIM))
        ui.put(s, y + 3, 2, f"{'System':<10}{hs.get('os') or '-'} · kernel {hs.get('kernel') or '-'} · agent "
                            f"{hs.get('agent') or '-'}", ui.attr(ui.NORMAL))
        who = ", ".join(n + (" (sudo)" if sudo else "") for n, sudo in sorted(allowed.items()))
        ui.put(s, y + 4, 2, f"{'Logins':<10}{who or 'nobody yet'}", ui.attr(ui.NORMAL))
        return y + 6

    def colour(self, v, item, line):
        if item is None:
            return ui.attr(ui.HEADING) if line.strip().endswith(":") and not line.startswith("    ") else ui.attr(ui.NORMAL)
        if v == "Computers":
            st = item["state"]
            return ui.attr(ui.ERR if "fail" in st else ui.DIM if st == "retired" else ui.NORMAL)
        if v == "host:Logs":
            return ui.attr(ui.ERR if (item.get("priority") or 6) <= 3 else ui.KEY if item.get("priority") == 4 else ui.NORMAL)
        if v == "host:Builds" and item.get("ok") is False or v == "host:Deployments" and item.get("result") == "failed":
            return ui.attr(ui.ERR)
        if v == "People" and item.get("disabled"):
            return ui.attr(ui.DIM)
        return ui.attr(ui.NORMAL)

    # ---- keys
    def run(self):
        while True:
            self.focus = min(self.focus, len(self.buttons()) - 1)
            self.draw()
            k = self.scr.get_wch()
            v = self.view()
            n = len(self.shown()[0])
            if self.search and k == ui.ESC:
                self.search = ""
                continue
            if k == curses.KEY_RESIZE:
                continue
            moves = {curses.KEY_UP: -1, curses.KEY_DOWN: 1, curses.KEY_PPAGE: -10, curses.KEY_NPAGE: 10}
            if k in moves:
                if v == "Changes":
                    self.top[v] = max(0, self.top.get(v, 0) + moves[k])
                else:
                    self.sel[v] = max(0, min(n - 1, self.sel.get(v, 0) + moves[k]))
            elif k == curses.KEY_HOME:
                self.sel[v] = 0
            elif k == curses.KEY_END:
                self.sel[v] = max(0, n - 1)
            elif k == curses.KEY_LEFT or k == curses.KEY_BTAB:
                self.focus = (self.focus - 1) % len(self.buttons())
            elif k in (curses.KEY_RIGHT, "\t"):
                self.focus = (self.focus + 1) % len(self.buttons())
            elif k in ui.ENTER:
                fn = self.buttons()[self.focus][2]  # the focused button; the first acts on the chosen line
                if fn is None:
                    return
                fn()
            elif k == ui.ESC or k == "q":
                if self.host or self.pending_view:
                    self.back()
                else:
                    return
            elif k == "/":
                self.search = ask_search(self.scr, self.search)
                self.sel[v] = 0
            elif k == "r":
                self.load()
                self.say("reloaded")
            elif isinstance(k, str) and len(k) == 1 and k in "123456":
                i = int(k) - 1
                if self.host and i < len(PANES):
                    self.pane_i, self.search = i, ""
                elif not self.host and i < len(TABS):
                    self.go(i)
            elif k == "\x0c":  # Ctrl+L
                self.scr.clear()
            elif isinstance(k, str):
                for i, (_, key, fn) in enumerate(self.buttons()):
                    if key and k.lower() == key:
                        self.focus = i
                        if fn is None:
                            return
                        fn()
                        break


# ------------------------------------------------------------------ pieces --
def tabs(win, y, names, cur):
    """The tab line under the title bar: the current one bold, the others dim."""
    x = 1
    for i, name in enumerate(names):
        x = ui.put(win, y, x, f" {i + 1} ", ui.attr(ui.KEY))
        x = ui.put(win, y, x, name, ui.attr(ui.HEADING) | (curses.A_UNDERLINE if i == cur else 0) if i == cur
                   else ui.attr(ui.DIM))
        x += 2


def plural(n, what):
    return f"{n} {what}" + ("" if n == 1 else "s")


def split(text):
    return [x.strip() for x in text.replace(" ", ",").split(",") if x.strip()]


def fingerprint_of(key):
    try:
        return fingerprint(key)[:19] + "…"
    except Exception:
        return "?"


def ask_search(scr, text):
    """/ in the list: a filter, typed on the message line; Enter keeps it, Esc clears it."""
    ui.cursor(True)
    try:
        while True:
            h, w = scr.getmaxyx()
            ui.put(scr, h - 2, 0, " " * (w - 1))
            ui.put(scr, h - 2, 1, "Search: ", ui.attr(ui.KEY))
            cx = ui.field(scr, h - 2, 9, min(40, w - 11), text, True)
            scr.move(h - 2, min(cx, w - 2))
            scr.refresh()
            k = scr.get_wch()
            if k in ui.ENTER:
                return text
            if k == ui.ESC:
                return ""
            t = ui.typed(text, k)
            if t is not None:
                text = t
    finally:
        ui.cursor(False)


def form(scr, title, fields, ok, note=""):
    """A box of fields: (label, key, value, kind[, initial choice]), kind text,
    secret, choice (value: the options; ←→ change it) or check (Space).
    Returns {key: value}, or None (Esc, Cancel)."""
    vals, opts = {}, {}
    for f in fields:
        label, key, value, kind = f[:4]
        if kind == "choice":
            opts[key] = list(value)
            vals[key] = f[4] if len(f) > 4 and f[4] in value else (value[0] if value else "")
        else:
            vals[key] = value
    notes = note.splitlines() if note else []
    labels = [(ok, ""), ("Cancel", "")]
    lw = max(len(f[0]) for f in fields) + 2
    h, w = scr.getmaxyx()
    bw = min(w - 2, max(lw + 46, max([len(x) for x in notes] + [0]) + 6))
    fw = bw - lw - 6
    bh = 2 * len(fields) + len(notes) + (1 if notes else 0) + 5
    win = curses.newwin(bh, bw, max(0, (h - bh) // 2), (w - bw) // 2)
    win.keypad(True)
    focus = 0  # fields, then the two buttons
    n = len(fields)
    while True:
        ui.frame(win, title)
        y = 2
        for i, n_ in enumerate(notes):
            ui.put(win, y + i, 3, n_, ui.attr(ui.DIM))
        y += len(notes) + (1 if notes else 0)
        cursor_at = None
        for i, f in enumerate(fields):
            label, key, _, kind = f[:4]
            fy = y + 2 * i
            ui.put(win, fy, 3, label, ui.attr(ui.HEADING if i == focus else ui.NORMAL))
            x = 3 + lw
            if kind == "choice":
                ui.field(win, fy, x, fw, f"‹ {vals[key]} ›", i == focus)
            elif kind == "check":
                ui.field(win, fy, x, 5, "[x]" if vals[key] else "[ ]", i == focus)
            else:
                cx = ui.field(win, fy, x, fw, vals[key], i == focus, secret=kind == "secret")
                if i == focus:
                    cursor_at = (fy, cx)
        ui.buttons(win, bh - 2, bw - ui.width_of(labels) - 3, labels, focus - n if focus >= n else -1)
        ui.cursor(cursor_at is not None)
        if cursor_at:
            win.move(*cursor_at)
        win.refresh()
        k = win.get_wch()
        kind = fields[focus][3] if focus < n else None
        key = fields[focus][1] if focus < n else None
        if k == ui.ESC:
            ui.cursor(False)
            return None
        if k in (curses.KEY_DOWN, "\t"):
            focus = (focus + 1) % (n + 2)
        elif k in (curses.KEY_UP, curses.KEY_BTAB):
            focus = (focus - 1) % (n + 2)
        elif k in ui.ENTER:
            if focus < n:
                focus += 1
            else:
                ui.cursor(False)
                return dict(vals) if focus == n else None
        elif focus >= n and k in (curses.KEY_LEFT, curses.KEY_RIGHT):
            focus = n + (1 - (focus - n))
        elif kind == "choice" and k in (curses.KEY_LEFT, curses.KEY_RIGHT, " "):
            o = opts[key]
            if o:
                vals[key] = o[(o.index(vals[key]) + (-1 if k == curses.KEY_LEFT else 1)) % len(o)]
        elif kind == "check" and k == " ":
            vals[key] = not vals[key]
        elif kind in ("text", "secret"):
            t = ui.typed(vals[key], k)
            if t is not None:
                vals[key] = t


def pager(scr, title, text):
    """Text to read, full screen: ↑↓ PgUp PgDn scroll, q or Esc goes back."""
    lines = [x.expandtabs() for x in (text or "").splitlines()] or [""]
    top = 0
    while True:
        h, w = scr.getmaxyx()
        scr.erase()
        ui.bar(scr, 0, f"Fleet › {title}")
        body = h - 3
        top = max(0, min(top, len(lines) - body))
        for i, line in enumerate(lines[top: top + body]):
            ui.put(scr, 2 + i, 2, line, ui.attr(ui.NORMAL))
        if top + body < len(lines):
            ui.put(scr, h - 2, w - 3, "↓", ui.attr(ui.DIM))
        ui.keybar(scr, h - 1, [("↑↓", "scroll"), ("PgUp PgDn", "page"), ("q", "back")])
        scr.refresh()
        k = scr.get_wch()
        if k in (ui.ESC, "q") or k in ui.ENTER:
            return
        top += {curses.KEY_UP: -1, curses.KEY_DOWN: 1, curses.KEY_PPAGE: -body, curses.KEY_NPAGE: body,
                curses.KEY_HOME: -len(lines), curses.KEY_END: len(lines)}.get(k, 0)


# ------------------------------------------------------------------ demo data --
def demo_repo():
    """A made-up fleet repository (in memory): Acme Robotics."""
    r = Repo.__new__(Repo)
    r.root, r.errors = "/nonexistent", []
    r.fleet = {"organization": "Acme Robotics", "server": "fleet.acme.example"}
    r.profiles = {"office", "lab", "kiosk", "server"}
    r.groups = {
        ADMINS: {"gid": 3000, "profiles": ["*"], "sudo": True, "description": "fleet admins"},
        "office": {"gid": 3001, "profiles": ["office"], "sudo": False},
        "lab": {"gid": 3002, "profiles": ["lab", "office"], "sudo": False},
        "lab-admins": {"gid": 3003, "profiles": ["lab"], "sudo": True},
        "kiosk": {"gid": 3004, "profiles": ["kiosk"], "sudo": False},
    }
    key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBaT8b1Vh5U0qP0Rb4Kc9M3bq1u2YyN0f3a6kM9a0b1c"
    people = [("arossi", "Anna Rossi", [ADMINS], True), ("mbianchi", "Marco Bianchi", [ADMINS, "office"], True),
              ("gverdi", "Giulia Verdi", ["lab"], False), ("lconti", "Luca Conti", ["lab", "lab-admins"], False),
              ("sricci", "Sara Ricci", ["office"], False), ("pgallo", "Paolo Gallo", ["office"], False),
              ("eferrari", "Elena Ferrari", ["office", "lab"], False), ("dmarino", "Davide Marino", ["kiosk"], False),
              ("fgreco", "Francesca Greco", ["office"], False), ("tbruno", "Tommaso Bruno", ["lab"], False)]
    r.people = {n: {"name": full, "uid": 2000 + i, "groups": gs, "ssh_keys": [key] if adm or i % 3 == 0 else [],
                    "age_recipient": "age1qyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqs3290gq" if adm else None,
                    "disabled": n == "tbruno"}
                for i, (n, full, gs, adm) in enumerate(people)}
    r.hosts = {h["name"]: {"profile": h["profile"], "branch": h["branch"], "unlock": "tang" if h["profile"] != "kiosk"
                           else "tpm-pin", "_key": key} for h in DEMO_HOSTS if h["state"] != "retired"}
    return r


def _host(name, profile, online, state, seen, rev="4f9a1c2e7b", branch="main", want="4f9a1c2e7b", addr=None):
    return dict(name=name, online=online, last_seen=seen, profile=profile, branch=branch, state=state, current_rev=rev,
                desired_rev=want, address=addr or f"10.20.0.{10 + len(name)}", agent="2.0", os="NixOS 26.05 (MeccanicOS 2026.10)",
                kernel="6.12.51")


DEMO_HOSTS = [
    _host("accounting-1", "office", True, "up to date", "2026-10-13 09:58:41", addr="10.20.1.21"),
    _host("accounting-2", "office", True, "up to date", "2026-10-13 09:58:37", addr="10.20.1.22"),
    _host("front-office", "office", False, "update pending (offline)", "2026-10-11 18:02:10", rev="1d3e5b77a0",
          addr="10.20.1.30"),
    _host("kiosk-lobby", "kiosk", True, "up to date", "2026-10-13 09:58:50", addr="10.20.3.5"),
    _host("lab-01", "lab", True, "up to date", "2026-10-13 09:58:44", addr="10.20.2.11"),
    _host("lab-02", "lab", True, "updating", "2026-10-13 09:58:39", rev="1d3e5b77a0", addr="10.20.2.12"),
    _host("lab-03", "lab", True, "up to date", "2026-10-13 09:58:46", addr="10.20.2.13"),
    _host("lab-04", "lab", False, "up to date", "2026-10-12 19:31:05", addr="10.20.2.14"),
    _host("lab-gpu", "lab", True, "build failed (runs the previous one)", "2026-10-13 09:58:31", rev="1d3e5b77a0",
          branch="testing", want="1d3e5b77a0", addr="10.20.2.40"),
    _host("render-1", "server", True, "up to date", "2026-10-13 09:58:48", addr="10.20.4.2"),
    _host("reception", "office", True, "up to date", "2026-10-13 09:58:35", addr="10.20.1.10"),
    _host("old-laptop", "office", False, "retired", "2026-09-30 12:00:00", rev="0b2c4d6e8f", addr="10.20.1.99"),
]

DEMO_AUDIT = [dict(time=t, actor=a, action=x, target=g, details=d) for t, a, x, g, d in [
    ("2026-10-13 09:41:12", "arossi", "push", "main", "4f9a1c2e7b"),
    ("2026-10-13 09:40:55", "arossi", "git-receive-pack", "fleet.git", ""),
    ("2026-10-13 09:22:03", "lab-02", "password-changed", "gverdi", "via mos-passwd"),
    ("2026-10-13 09:15:47", "mbianchi", "job-run", "lab-01", '{"argv": ["df", "-h", "/"]}'),
    ("2026-10-13 09:15:47", "mbianchi", "job-run", "lab-03", '{"argv": ["df", "-h", "/"]}'),
    ("2026-10-13 08:15:40", "mbianchi", "enroll-create", "front-desk", "profile office, unlock tang"),
    ("2026-10-12 17:05:30", "arossi", "recover", "lab-04", ""),
    ("2026-10-12 16:44:18", "lab-07", "enrolled", "lab-07", "SHA256:7mKq0xY3dWbR2vN…"),
    ("2026-10-12 16:02:11", "arossi", "enroll-create", "lab-07", "profile lab, unlock tang"),
    ("2026-10-12 11:30:02", "mbianchi", "password-set", "sricci", ""),
    ("2026-10-12 10:12:44", "arossi", "job-reboot", "kiosk-lobby", "{}"),
    ("2026-10-11 18:20:19", "arossi", "push", "testing", "1d3e5b77a0"),
]]


def demo_pane(name, which):
    if which == "Logs":
        lines = [
            ("09:58:41", "mos-fleet-agent.service", 6, "facts sent"),
            ("09:57:12", "sshd.service", 6, "Accepted publickey for gverdi from 10.20.2.40 port 51544 ssh2"),
            ("09:56:30", "NetworkManager.service", 6, "<info> device (wlp2s0): state change: activated"),
            ("09:52:03", "kernel", 4, "iwlwifi 0000:02:00.0: firmware: direct-loading firmware iwlwifi-ty-a0-gf-a0-89.ucode"),
            ("09:50:44", "mos-fleet-agent.service", 6, "switched to 4f9a1c2e7b (main)"),
            ("09:50:20", "mos-fleet-agent.service", 6, "fetching the new system: 214 paths, 312 MiB"),
            ("09:41:30", "cups.service", 6, "Printer Office_Laser added"),
            ("09:12:08", "systemd-logind.service", 6, "New session 4 of user gverdi."),
            ("08:59:59", "smartd.service", 3, "Device: /dev/nvme0, Critical Warning (0x04): Reliability"),
            ("08:31:17", "mos-fleet-agent.service", 6, "connected to the fleet server"),
            ("08:31:02", "systemd", 6, "Startup finished in 6.1s (firmware) + 2.4s (loader) + 3.8s (kernel) + 9.2s (userspace)"),
        ]
        return [dict(id=i, time=f"2026-10-13 {t}", unit=u, priority=p, message=m) for i, (t, u, p, m) in
                enumerate(reversed(lines))]
    if which == "Builds":
        failed = name == "lab-gpu"
        return [dict(rev="4f9a1c2e7b", branch="main" if not failed else "testing", started="2026-10-13 09:41:20",
                     ok=not failed, log="error: builder for '/nix/store/…-nvidia-x11-580.95.05-6.12.51.drv' failed with "
                                        "exit code 2\n  last 10 log lines:\n  > make: *** [Makefile:30: modules] Error 2"
                                        if failed else "built /nix/store/…-nixos-system-" + name),
                dict(rev="1d3e5b77a0", branch="main", started="2026-10-11 18:20:31", ok=True, log=""),
                dict(rev="9c8b7a6d5e", branch="main", started="2026-10-09 10:02:11", ok=True, log="")]
    if which == "Deployments":
        return [dict(rev="4f9a1c2e7b", started="2026-10-13 09:50:20", result="ok",
                     to_system="/nix/store/6zq4m1yg8l8b1d0x7w2s5c3v9r4p0k2j-nixos-system-" + name + "-26.05.20261002.774debe",
                     output=""),
                dict(rev="1d3e5b77a0", started="2026-10-11 18:31:02", result="ok",
                     to_system="/nix/store/2kq8n0vd3s9w1x7c5b4m6l2j8h0g4f6d-nixos-system-" + name + "-26.05.20260930.1a2b3c4",
                     output="")]
    return [dict(id=118, created_on="2026-10-13 09:15:47", kind="run", state="exit 0", created_by="mbianchi",
                 command="df -h /"),
            dict(id=97, created_on="2026-10-12 10:12:44", kind="facts", state="exit 0", created_by="arossi", command="")]


# ------------------------------------------------------------------ entry --
def check(data):
    """Every tab and pane's lines, printed instead of drawn (tests: mos-fleet tui --check)."""
    app = App(None, data)
    bad = []
    for i, tab in enumerate(TABS):
        app.go(i)
        views = [(tab, None)] + ([("pending", None)] if tab == "Computers" else [])
        if tab == "Computers":
            views += [(f"{h} › {p}", (h, j)) for h in sorted(data.r.hosts) for j, p in enumerate(PANES)]
        for name, host in views:
            app.back()
            app.pending_view = name == "pending"
            if host:
                app.host, app.pane_i = host
            app.msg = ""
            rows, head, empty = app.rows()
            print(f"== {name}\n{head}")
            for _, line in rows:
                print(line.rstrip())
            if app.msg.startswith("✗"):
                bad.append(f"{name}: {app.msg}")
    for b in bad:
        print(b, file=sys.stderr)
    return 1 if bad else 0


def main(repo_root, demo=False, check_only=False):
    if not demo and not os.path.isfile(os.path.join(repo_root, "fleet.toml")):
        raise Fail(f"No fleet repository in {repo_root} (mos-fleet clone SERVER, or --repo DIR).")
    data = Demo() if demo else Live(repo_root)
    if check_only:
        return check(data)
    os.environ.setdefault("ESCDELAY", "25")
    curses.wrapper(lambda scr: (ui.init(), scr.keypad(True), App(scr, data).run()))
    return 0

