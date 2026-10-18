"""The fleet server: one SSH account, `fleet`, and two SQLite databases.

Everything reaches it over SSH. sshd asks keys.py who a key belongs to, and
runs `mos-fleet-serve ROLE NAME` for it (a forced command):

    host NAME       a computer of the fleet (its SSH host key, in hosts/NAME/host.toml)
                      session    the agent's connection: facts, logs, jobs, results;
                                 the system it should run, its people's password hashes
                      fetch      the store paths of that system (and only those)
                      relay ID   the computer's end of an admin's `mos-fleet shell`
    enroll NAME     a computer being installed, once (its key came on the stick)
    admin NAME      a person in fleet-admins: git push/pull of the repository,
                    and the commands in ADMIN below
    bootstrap ...   an admin key added at the console (a day): info and git only

The server never writes to the repository. What computers report, and what
admins do, goes to state.db; password hashes and recovery keys to secrets.db.
"""

import argparse
import ctypes
import datetime
import fcntl
import hmac
import io
import json
import os
import secrets
import select
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import time

from .common import (HASH_RE, MAX_LINE, REV_RE, SYSTEM_RE, TOKEN_RE, VERSION, Fail, Lines, clip, dumps, now,
                     parse, run, say, warn, write_atomic)
from . import settings
from .repo import BRANCH_RE, HOST_FILES, HOST_RE, PERSON_RE, PROFILE_RE, UNLOCK, Invalid, Repo, fingerprint, ssh_key

CFG = settings.get("server")
STATE = os.environ.get("MOS_FLEET_STATE") or CFG["state"]
GIT = os.path.join(STATE, "fleet.git")
MAIN = os.path.join(STATE, "main")  # the newest valid main branch, as files
RELAY = os.path.join(STATE, "relay")
ROOTS = os.path.join(STATE, "roots")
TRIGGER = os.path.join(STATE, "build.trigger")
ZERO = "0" * 40
TANG_PORT = str(CFG["tang_port"])


# ------------------------------------------------------------- databases --
def _dal(name, migrate):
    from pydal import DAL

    db = DAL(f"sqlite://{name}", folder=STATE, migrate=migrate, fake_migrate=False, pool_size=0,
             check_reserved=None, entity_quoting=True)
    db.executesql("PRAGMA busy_timeout=15000")
    return db


# How SQLite stores what isn't text, for a column added to an adopted table.
SQL_TYPES = {"boolean": "CHAR(1)", "integer": "INTEGER", "datetime": "TIMESTAMP"}


def define(db, migrate, name, *fields):
    """db.define_table. A table that is in the file but has no pydal record next
    to it (a database put back by `mos-fleet server restore`) is adopted, not
    created again: its record is written, and the columns it lacks (added since
    that backup) are added."""
    have = {r[1] for r in db.executesql(f'PRAGMA table_info("{name}")')}
    adopt = migrate and have and not os.path.exists(os.path.join(STATE, f"{db._uri_hash}_{name}.table"))
    t = db.define_table(name, *fields, **({"fake_migrate": True} if adopt else {}))
    if adopt:
        for f in t:
            if f.name not in have:
                db.executesql(f'ALTER TABLE "{name}" ADD COLUMN "{f.name}" {SQL_TYPES.get(f.type, "TEXT")}')
    return t


def open_state(migrate=False):
    from pydal import Field

    db = _dal("state.db", migrate)
    # Jobs delivered before agents acknowledged them (received_on) count as received:
    # sent again, an old job could run twice.
    old_jobs = migrate and "received_on" not in [r[1] for r in db.executesql('PRAGMA table_info("job")')] \
        and bool(db.executesql('PRAGMA table_info("job")'))
    define(db, migrate, "host", Field("name", unique=True), Field("profile"), Field("branch"),
           Field("host_key_fp"), Field("in_repo", "boolean", default=True),
           Field("first_seen", "datetime"), Field("last_seen", "datetime"), Field("address"),
           Field("agent_version"), Field("nixos_version"), Field("kernel"),
           Field("current_system", length=300), Field("current_rev"),
           Field("desired_system", length=300), Field("desired_rev"), Field("log_cursor", "text"))
    define(db, migrate, "revision", Field("rev"), Field("branch"), Field("pushed_by"), Field("pushed_on", "datetime"),
           Field("valid", "boolean"), Field("errors", "text"))
    define(db, migrate, "build", Field("host"), Field("rev"), Field("branch"), Field("system_path", length=300),
           Field("started", "datetime"), Field("finished", "datetime"), Field("ok", "boolean"),
           Field("log", "text"))
    define(db, migrate, "deployment", Field("host"), Field("rev"), Field("from_system", length=300),
           Field("to_system", length=300), Field("started", "datetime"), Field("finished", "datetime"),
           Field("result"), Field("output", "text"))
    define(db, migrate, "report", Field("host"), Field("time", "datetime"), Field("facts", "text"))
    define(db, migrate, "log", Field("host"), Field("time", "datetime"), Field("boot_id"), Field("unit"),
           Field("priority", "integer"), Field("message", "text"))
    define(db, migrate, "job", Field("host"), Field("kind"), Field("args", "text"), Field("token"),
           Field("created_by"), Field("created_on", "datetime"), Field("delivered_on", "datetime"),
           Field("received_on", "datetime"), Field("finished_on", "datetime"),
           Field("canceled", "boolean", default=False), Field("exit_code", "integer"), Field("output", "text"))
    define(db, migrate, "session", Field("host"), Field("connected_on", "datetime"),
           Field("disconnected_on", "datetime"), Field("address"), Field("pid", "integer"))
    define(db, migrate, "audit", Field("time", "datetime"), Field("actor"), Field("action"), Field("target"),
           Field("details", "text"))
    define(db, migrate, "enrollment", Field("host"), Field("profile"), Field("unlock"), Field("branch"),
           Field("disk_serial"), Field("enroll_key", length=1024), Field("created_by"),
           Field("created_on", "datetime"), Field("expires", "datetime"), Field("used_on", "datetime"),
           Field("host_key", length=1024), Field("files", "text"), Field("facts", "text"),
           Field("address"), Field("added_on", "datetime"))
    if migrate:
        if old_jobs:
            db.executesql('UPDATE "job" SET "received_on" = "delivered_on" WHERE "delivered_on" IS NOT NULL')
        db.executesql("PRAGMA journal_mode=WAL")
        for t, cols in (("log", "host, time"), ("report", "host, time"), ("job", "host, delivered_on"),
                        ("build", "host, rev"), ("deployment", "host, started"), ("session", "host"),
                        ("audit", "time"), ("enrollment", "host")):
            db.executesql(f'CREATE INDEX IF NOT EXISTS "{t}_idx" ON "{t}" ({cols})')
        db.commit()
    return db


def open_secrets(migrate=False):
    from pydal import Field

    db = _dal("secrets.db", migrate)
    define(db, migrate, "password", Field("person", unique=True), Field("hash"), Field("set_on", "datetime"),
           Field("set_by"), Field("from_host"))
    define(db, migrate, "recovery_key", Field("host"), Field("host_key", length=1024), Field("ciphertext", "text"),
           Field("created_on", "datetime"), Field("confirmed", "boolean", default=False))
    define(db, migrate, "passwd_attempt", Field("person"), Field("host"), Field("time", "datetime"),
           Field("ok", "boolean"))
    if migrate:
        db.executesql("PRAGMA journal_mode=WAL")
        db.commit()
    return db


def audit(db, actor, action, target="", details=""):
    db.audit.insert(time=now(), actor=actor, action=action, target=target, details=clip(details, 4000))
    db.commit()


# ------------------------------------------------------------ repository --
def git(*args, check=True, input=None):
    return run(["git", "--git-dir", GIT, *args], check=check, input=input)


def heads():
    out = git("for-each-ref", "--format=%(refname:strip=2) %(objectname)", "refs/heads", check=False)
    return dict(line.split() for line in out.splitlines() if len(line.split()) == 2)


def archive(rev, dest):
    """One commit's files into dest. Links that leave dest are refused."""
    data = subprocess.run(["git", "--git-dir", GIT, "archive", "--format=tar", rev], capture_output=True)
    if data.returncode != 0:
        raise Fail(f"git archive {rev[:12]}: {data.stderr.decode(errors='replace').strip()}")
    os.makedirs(dest, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data.stdout)) as tar:
        tar.extractall(dest, filter="data")


def check_rev(rev, where):
    """A commit's files, checked: the Repo (errors empty when valid)."""
    shutil.rmtree(where, ignore_errors=True)
    try:
        archive(rev, where)
    except (Fail, tarfile.TarError, OSError) as e:
        r = Repo.__new__(Repo)
        r.errors = [f"{e}"]
        return r
    return Repo(where)


def main_repo():
    if os.path.isfile(os.path.join(MAIN, "fleet.toml")):
        r = Repo(MAIN)
        if not r.errors:
            return r
    return None


def main_rev():
    try:
        return open(os.path.join(MAIN, ".rev")).read().strip()
    except OSError:
        return None


class Lock:
    def __init__(self, name):
        self.fh = open(os.path.join(STATE, name), "a")

    def __enter__(self):
        fcntl.flock(self.fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, *a):
        fcntl.flock(self.fh, fcntl.LOCK_UN)
        self.fh.close()


def refresh(db=None, sdb=None):
    """Bring MAIN, the host table, recovery keys and keys.json up to the
    newest main branch. Only a valid main counts (the hook rejects invalid
    pushes; this checks again)."""
    db = db or open_state()
    sdb = sdb or open_secrets()
    with Lock("refresh.lock"):
        rev = heads().get("main")
        if rev and rev != main_rev():
            tmp = f"{MAIN}.new"
            r = check_rev(rev, tmp)
            if r.errors:
                warn(f"main {rev[:12]} is not valid; keeping the previous one:\n  " + "\n  ".join(r.errors[:20]))
            else:
                with open(os.path.join(tmp, ".rev"), "w") as fh:
                    fh.write(rev + "\n")
                shutil.rmtree(f"{MAIN}.old", ignore_errors=True)
                if os.path.exists(MAIN):
                    os.rename(MAIN, f"{MAIN}.old")
                os.rename(tmp, MAIN)
                shutil.rmtree(f"{MAIN}.old", ignore_errors=True)
        repo = main_repo()
        names = set(repo.hosts) if repo else set()
        for h in names:
            t = repo.hosts[h]
            fields = dict(profile=t["profile"], branch=t.get("branch", "main"), in_repo=True,
                          host_key_fp=fingerprint(t["_key"]))
            row = db.host(name=h)
            if row:
                if row.host_key_fp and row.host_key_fp != fields["host_key_fp"]:
                    fields.update(current_system=None, current_rev=None, log_cursor=None)  # reinstalled
                row.update_record(**fields)
            else:
                db.host.insert(name=h, **fields)
            for rk in sdb((sdb.recovery_key.host == h) & (sdb.recovery_key.host_key == t["_key"])
                          & (sdb.recovery_key.confirmed == False)).select():  # noqa: E712
                rk.update_record(confirmed=True)
            db((db.enrollment.host == h) & (db.enrollment.host_key == t["_key"])
               & (db.enrollment.added_on == None)).update(added_on=now())  # noqa: E711
        db((db.host.in_repo == True) & ~db.host.name.belongs(sorted(names) or [""])).update(  # noqa: E712
            in_repo=False, desired_system=None, desired_rev=None)
        db.commit()
        sdb.commit()
        write_keys(db, repo)
    return repo


def write_keys(db, repo):
    t = now()
    data = {"admins": {}, "hosts": {}, "enroll": {}}
    if repo:
        data["admins"] = {n: p["_keys"] for n, p in repo.admins().items() if p.get("_keys")}
        data["hosts"] = {h: v["_key"] for h, v in repo.hosts.items()}
    for e in db((db.enrollment.used_on == None) & (db.enrollment.expires > t)).select():  # noqa: E711
        data["enroll"][e.host] = {"key": e.enroll_key, "expires": time.time() + (e.expires - t).total_seconds()}
    write_atomic(os.path.join(STATE, "keys.json"), json.dumps(data, indent=1) + "\n")


# -------------------------------------------------------------- the hosts --
def crypt_ok(password, hashed):
    lib = ctypes.CDLL(os.environ.get("MOS_FLEET_LIBCRYPT", "libcrypt.so.2"))
    lib.crypt.restype = ctypes.c_char_p
    lib.crypt.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    out = lib.crypt(password.encode(), hashed.encode())
    return bool(out) and hmac.compare_digest(out, hashed.encode())


def online_hosts(db):
    out = set()
    for s in db(db.session.disconnected_on == None).select():  # noqa: E711
        try:
            os.kill(s.pid, 0)
            out.add(s.host)
        except (OSError, TypeError):
            s.update_record(disconnected_on=now())
    db.commit()
    return out


class HostSession:
    """The agent's connection: one JSON message per line, both ways."""

    def __init__(self, name):
        self.name = name
        self.db, self.sdb = open_state(), open_secrets()
        self.io = Lines(0, 1)
        self.sent_desired = self.sent_pw = self.repo_rev = self.repo = None
        self.next_pw = self.seen = 0
        self.started = now()
        self.hello = self.acks = False  # the agent said hello; it acknowledges jobs (agent 3)
        self.sent_jobs = set()

    def run(self):
        db = self.db
        addr = (os.environ.get("SSH_CONNECTION") or "?").split(" ")[0]
        sid = db.session.insert(host=self.name, connected_on=now(), address=addr, pid=os.getpid())
        row = db.host(name=self.name) or db.host(db.host.insert(name=self.name))
        row.update_record(last_seen=now(), address=addr, first_seen=row.first_seen or now())
        db.commit()
        try:
            while True:
                r, _, _ = select.select([0], [], [], 1.0)
                if r:
                    chunk = os.read(0, 1 << 16)
                    if not chunk:
                        break
                    for msg in self.io.feed(chunk):
                        self.handle(msg)
                if not self.tick():
                    break
                db.commit()
        except (Fail, OSError) as e:
            warn(f"mos-fleet: {e}")
        finally:
            db.rollback()
            db(db.session.id == sid).update(disconnected_on=now())
            db.commit()

    # ---- server -> agent
    def tick(self):
        db = self.db
        rev = main_rev()
        if rev != self.repo_rev:
            self.repo_rev, self.repo = rev, main_repo()
            self.sent_pw, self.next_pw = None, 0
        if not self.repo or self.name not in self.repo.hosts:
            self.io.send({"t": "bye", "reason": "this computer is no longer in the fleet repository"})
            return False
        row = db.host(name=self.name)
        if row and row.desired_system and row.desired_system != self.sent_desired:
            self.io.send({"t": "desired", "system": row.desired_system, "rev": row.desired_rev, "branch": row.branch})
            self.sent_desired = row.desired_system
        if not self.hello:
            return True
        # Jobs not delivered yet, and (to agents that acknowledge them) those delivered in an
        # earlier session that never said they arrived: the connection may have dropped
        # first. The agent keeps the ids it has seen, so a job sent again doesn't run again.
        j = db.job
        again = (j.delivered_on <= self.started) if self.acks else (j.id < 0)
        claim = (j.received_on == None) & ((j.delivered_on == None) | again)  # noqa: E711
        for r in db((j.host == self.name) & (j.canceled == False) & (j.finished_on == None)  # noqa: E711,E712
                    & claim).select(orderby=j.id):
            if r.id in self.sent_jobs:
                continue
            t = now()
            if db((j.id == r.id) & claim).update(delivered_on=t, **({} if self.acks else {"received_on": t})):
                db.commit()
                self.sent_jobs.add(r.id)
                self.io.send({"t": "job", "id": r.id, "kind": r.kind, "args": json.loads(r.args or "{}"),
                              "token": r.token})
        if time.time() >= self.next_pw:
            self.next_pw = time.time() + 5
            allowed = self.repo.allowed(self.name)
            rows = self.sdb(self.sdb.password.person.belongs(list(allowed) or [""])).select()
            hashes = {r.person: r.hash for r in rows}
            digest = dumps(sorted(hashes.items()))
            if digest != self.sent_pw:
                self.io.send({"t": "passwords", "hashes": hashes})
                self.sent_pw = digest
            self.sdb.commit()
        return True

    # ---- agent -> server
    def handle(self, m):
        db, t = self.db, m.get("t")
        if time.time() - self.seen > 5:
            self.seen = time.time()
            db(db.host.name == self.name).update(last_seen=now())
        if t in ("hello", "facts"):
            facts = m.get("facts") if isinstance(m.get("facts"), dict) else {}
            text = dumps(facts)
            if len(text) > 256 << 10:
                return
            db.report.insert(host=self.name, time=now(), facts=text)
            cur = m.get("system")
            db(db.host.name == self.name).update(
                agent_version=clip(m.get("agent"), 40), nixos_version=clip(facts.get("os"), 120),
                kernel=clip(facts.get("kernel"), 120),
                **({"current_system": cur} if isinstance(cur, str) and SYSTEM_RE.fullmatch(cur) else {}))
            if t == "hello":
                self.sent_desired = None  # say it again: the agent just started
                self.hello = True
                try:
                    self.acks = int(m.get("agent")) >= 3
                except (TypeError, ValueError):
                    self.acks = False
                row = db.host(name=self.name)
                if row and row.log_cursor:  # where its logs here end: the agent goes on from there
                    self.io.send({"t": "logs-ok", "cursor": row.log_cursor})
        elif t == "logs":
            entries = m.get("entries")
            if not isinstance(entries, list) or len(entries) > 5000:
                return
            rows = []
            for e in entries:
                if not isinstance(e, dict):
                    continue
                try:
                    when = time.gmtime(float(e.get("time", 0)))
                    prio = int(e.get("prio", 6))
                except (TypeError, ValueError, OverflowError):
                    continue
                rows.append(dict(host=self.name, time=time.strftime("%Y-%m-%d %H:%M:%S", when),
                                 boot_id=clip(e.get("boot"), 64), unit=clip(e.get("unit"), 128),
                                 priority=max(0, min(7, prio)), message=clip(e.get("msg"), 4096)))
            if rows:
                db.log.bulk_insert(rows)
            cursor = clip(m.get("cursor"), 1024)
            db(db.host.name == self.name).update(log_cursor=cursor)
            db.commit()
            self.io.send({"t": "logs-ok", "cursor": cursor})
        elif t == "deploy":
            system, state = m.get("system"), m.get("state")
            if not (isinstance(system, str) and SYSTEM_RE.fullmatch(system)) or state not in ("started", "ok", "failed"):
                return
            rev = m.get("rev") if isinstance(m.get("rev"), str) and REV_RE.fullmatch(m.get("rev")) else None
            row = db.host(name=self.name)
            if state == "started":
                db.deployment.insert(host=self.name, rev=rev, from_system=row.current_system, to_system=system,
                                     started=now(), result="started")
            else:
                d = db((db.deployment.host == self.name) & (db.deployment.to_system == system)).select(
                    orderby=~db.deployment.id, limitby=(0, 1)).first()
                if not d:
                    d = db.deployment(db.deployment.insert(host=self.name, rev=rev, to_system=system, started=now()))
                d.update_record(result=state, finished=now(), output=clip(m.get("output"), 64 << 10))
                if state == "ok":
                    row.update_record(current_system=system, current_rev=rev or d.rev)
        elif t == "job-got":
            if isinstance(m.get("id"), int):
                db((db.job.id == m["id"]) & (db.job.host == self.name) & (db.job.received_on == None)).update(  # noqa: E711
                    received_on=now())
        elif t == "job-done":
            j = db.job(m.get("id")) if isinstance(m.get("id"), int) else None
            if j and j.host == self.name and not j.finished_on:
                code = m.get("code")
                j.update_record(finished_on=now(), received_on=j.received_on or now(),
                                exit_code=code if isinstance(code, int) else None,
                                output=clip(m.get("output"), 256 << 10))
        elif t == "passwd":
            ok, err = self.passwd(m)
            self.io.send({"t": "passwd-result", "req": m.get("req"), "ok": ok, "error": err})
        elif t == "ping":
            self.io.send({"t": "pong"})
        db.commit()

    def passwd(self, m):
        """A person changes their own password on this computer: they must
        know the current one (so a computer can't change anyone's at will)."""
        sdb, person = self.sdb, m.get("person")
        old, new = m.get("old"), m.get("new_hash")
        if not (isinstance(person, str) and PERSON_RE.fullmatch(person)) or not isinstance(old, str) \
                or not (isinstance(new, str) and HASH_RE.fullmatch(new)) or len(old) > 1024:
            return False, "bad request"
        if person not in self.repo.allowed(self.name):
            return False, "you can't log in on this computer"
        recent = sdb((sdb.passwd_attempt.person == person) & (sdb.passwd_attempt.ok == False)  # noqa: E712
                     & (sdb.passwd_attempt.time > now() - datetime.timedelta(hours=1))).count()
        if recent >= CFG["password_attempts_per_hour"]:
            audit(self.db, f"host:{self.name}", "password-locked", person, f"{recent} wrong passwords in an hour")
            return False, "too many wrong passwords: try again in an hour, or ask an admin"
        row = sdb.password(person=person)
        if not row:
            return False, "no password set yet: ask an admin (mos-fleet password set)"
        good = crypt_ok(old, row.hash)
        sdb.passwd_attempt.insert(person=person, host=self.name, time=now(), ok=good)
        if not good:
            sdb.commit()
            audit(self.db, f"host:{self.name}", "password-wrong", person)
            return False, "the current password is wrong"
        row.update_record(hash=new, set_on=now(), set_by=person, from_host=self.name)
        sdb.commit()
        audit(self.db, person, "password-changed", person, f"on {self.name}")
        self.next_pw = 0
        return True, None


def host_fetch(name):
    """The paths of this computer's system it lacks, as `nix-store --export`."""
    db = open_state()
    rd = sys.stdin.buffer
    req = parse(rd.readline(MAX_LINE + 1))
    system = req.get("system")
    row = db.host(name=name)
    out = Lines(0, 1)
    if not isinstance(system, str) or not SYSTEM_RE.fullmatch(system) or system != row.desired_system:
        out.send({"ok": False, "error": "not the system this computer should run"})
        return 1
    closure = run(["nix-store", "--query", "--requisites", system]).split()
    out.send({"ok": True, "paths": closure})
    want = parse(rd.readline(MAX_LINE + 1)).get("want")
    allowed = set(closure)
    if not isinstance(want, list) or not all(isinstance(p, str) and p in allowed for p in want):
        out.send({"ok": False, "error": "asked for paths outside the system"})
        return 1
    want = set(want)
    order = [p for p in closure if p in want]
    out.send({"ok": True, "count": len(order)})
    if order:
        r = subprocess.run(["nix-store", "--export", *order], stdout=1)
        return r.returncode
    return 0


def pump(rfd, wfd, sock):
    """Bytes both ways between (rfd, wfd) and a socket, until both sides end."""
    sock.setblocking(False)
    ins, done_in = [rfd, sock], False
    while ins:
        r, _, _ = select.select(ins, [], [])
        if rfd in r:
            data = os.read(rfd, 1 << 16)
            if not data:
                ins.remove(rfd)
                done_in = True
                try:
                    sock.shutdown(socket.SHUT_WR)
                except OSError:
                    pass
            else:
                sock.setblocking(True)
                sock.sendall(data)
                sock.setblocking(False)
        if sock in r:
            try:
                data = sock.recv(1 << 16)
            except BlockingIOError:
                continue
            if not data:
                break
            while data:
                n = os.write(wfd, data)
                data = data[n:]
    del done_in
    sock.close()


def host_relay(name, token):
    if not TOKEN_RE.fullmatch(token or ""):
        raise Fail("bad relay")
    db = open_state()
    j = db((db.job.token == token) & (db.job.host == name) & (db.job.kind == "relay")).select().first()
    if not j or j.canceled or (now() - j.created_on).total_seconds() > 120:
        raise Fail("no such relay")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(os.path.join(RELAY, f"{token}.sock"))
    pump(0, 1, s)
    return 0


def enroll(name):
    """A new computer introduces itself, once, with the key from the stick:
    its SSH host key, its /etc/nixos files, the recovery key (encrypted for
    the admins). An admin then adds it to the repository (mos-fleet host add)."""
    db, sdb = open_state(), open_secrets()
    out = Lines(0, 1)
    e = db((db.enrollment.host == name) & (db.enrollment.used_on == None)).select(  # noqa: E711
        orderby=~db.enrollment.id).first()
    if not e or e.expires < now():
        out.send({"ok": False, "error": "no enrollment for this computer (mos-fleet host prepare)"})
        return 1
    data = sys.stdin.buffer.read(4 << 20)
    try:
        m = parse(data)
        host_key = ssh_key(m.get("host_key", ""))
        files = m.get("files") or {}
        rec = m.get("recovery") or ""
        facts = m.get("facts") or {}
        if not isinstance(files, dict) or not set(files) <= set(HOST_FILES) \
                or not all(isinstance(v, str) and len(v) < 256 << 10 for v in files.values()):
            raise Fail("files: only " + ", ".join(HOST_FILES))
        if not isinstance(rec, str) or len(rec) > 16 << 10 or (rec and not rec.startswith("-----BEGIN AGE ENCRYPTED FILE-----")):
            raise Fail("recovery: an armored age file")
        if not isinstance(facts, dict) or len(dumps(facts)) > 256 << 10:
            raise Fail("facts: too big")
    except (Fail, Invalid) as err:
        out.send({"ok": False, "error": str(err)})
        return 1
    repo = main_repo()
    if repo:
        taken = {v["_key"] for v in repo.hosts.values()} | {k for p in repo.people.values() for k in p.get("_keys", [])}
        if host_key in taken:
            out.send({"ok": False, "error": "this host key is already in use"})
            return 1
    addr = (os.environ.get("SSH_CONNECTION") or "?").split(" ")[0]
    n = db((db.enrollment.id == e.id) & (db.enrollment.used_on == None)).update(  # noqa: E711
        used_on=now(), host_key=host_key, files=dumps(files), facts=dumps(facts), address=addr)
    db.commit()
    if n != 1:
        out.send({"ok": False, "error": "already used"})
        return 1
    if rec:
        sdb.recovery_key.insert(host=name, host_key=host_key, ciphertext=rec, created_on=now(), confirmed=False)
        sdb.commit()
    audit(db, f"enroll:{name}", "enrolled", name, f"from {addr}, host key {fingerprint(host_key)}")
    write_keys(db, main_repo())
    out.send({"ok": True, "fingerprint": fingerprint(host_key)})
    return 0


# ----------------------------------------------------------------- admins --
def since(text):
    """'30m', '2h', '7d' -> a datetime."""
    unit = {"s": 1, "m": 60, "h": 3600, "d": 86400}.get(text[-1:])
    if not unit or not text[:-1].isdigit():
        raise Fail("--since: like 30m, 2h, 7d")
    return now() - datetime.timedelta(seconds=int(text[:-1]) * unit)


def fmt(t):
    return t.strftime("%Y-%m-%d %H:%M:%S") if t else "-"


def host_state(row, last_build, online, last_deploy=None):
    if not row.in_repo:
        return "retired"
    if not row.desired_system:
        if last_build and last_build.ok is False:
            return "build failed"
        if last_build and not last_build.finished:
            return "building"
        return "not built yet" if row.branch in heads() else f"waiting for branch {row.branch}"
    if last_build and last_build.ok is False and last_build.rev != row.desired_rev:
        return "build failed (runs the previous one)"
    if last_deploy and last_deploy.to_system == row.desired_system and last_deploy.result == "failed":
        return f"switch failed (mos-fleet deployments {row.name})"
    if row.current_system == row.desired_system:
        return "up to date"
    return "updating" if online else "update pending (offline)"


class Admin:
    def __init__(self, role, name):
        self.role, self.name = role, name
        self.actor = name if role == "admin" else "console-key"
        self.db = open_state()

    def need_host(self, h, in_repo=True):
        if not HOST_RE.fullmatch(h):
            raise Fail(f"{h!r}: not a computer name")
        row = self.db.host(name=h)
        if not row or (in_repo and not row.in_repo):
            raise Fail(f"{h}: not in the fleet repository")
        return row

    def main(self, line):
        argv = shlex.split(line)
        if not argv:
            raise Fail("Use mos-fleet on your computer (this account runs no shell).")
        if argv[0] in ("git-upload-pack", "git-receive-pack"):
            return self.git(argv)
        if self.role == "bootstrap" and argv[0] != "info":
            raise Fail("A console key may only push the repository and read info.")
        p = argparse.ArgumentParser(prog="mos-fleet (server)", add_help=False, exit_on_error=False)
        sub = p.add_subparsers(dest="cmd", required=True)
        sub.add_parser("info")
        x = sub.add_parser("status")
        x.add_argument("host", nargs="?")
        x.add_argument("--all", action="store_true")
        x.add_argument("--json", action="store_true")
        x = sub.add_parser("logs")
        x.add_argument("host")
        x.add_argument("--unit")
        x.add_argument("--since")
        x.add_argument("--priority", type=int)
        x.add_argument("--limit", type=int, default=200)
        x.add_argument("--follow", action="store_true")
        x.add_argument("--after", type=int, default=0, help="only entries after this id")
        x.add_argument("--json", action="store_true")
        x = sub.add_parser("builds")
        x.add_argument("host", nargs="?")
        x.add_argument("--limit", type=int, default=20)
        x.add_argument("--log", action="store_true")
        x.add_argument("--json", action="store_true")
        sub.add_parser("build-retry").add_argument("hosts", nargs="+")
        x = sub.add_parser("deployments")
        x.add_argument("host")
        x.add_argument("--limit", type=int, default=20)
        x.add_argument("--json", action="store_true")
        x = sub.add_parser("run")
        x.add_argument("--host", action="append", default=[])
        x.add_argument("--profile")
        x.add_argument("--timeout", type=int, default=600)
        x.add_argument("--wait", type=int, default=0)
        x.add_argument("argv", nargs="+")
        for k in ("reboot", "switch", "facts"):
            sub.add_parser(k).add_argument("hosts", nargs="+")
        x = sub.add_parser("jobs")
        x.add_argument("host", nargs="?")
        x.add_argument("--limit", type=int, default=30)
        x.add_argument("--json", action="store_true")
        x = sub.add_parser("job")
        x.add_argument("id", type=int)
        x.add_argument("--json", action="store_true")
        sub.add_parser("cancel").add_argument("id", type=int)
        sub.add_parser("relay").add_argument("host")
        sub.add_parser("password-set").add_argument("person")
        x = sub.add_parser("recover")
        x.add_argument("host")
        x = sub.add_parser("enroll-create")
        x.add_argument("host")
        x.add_argument("--profile", required=True)
        x.add_argument("--unlock", required=True)
        x.add_argument("--branch", default="main")
        x.add_argument("--disk-serial")
        x.add_argument("--key", required=True)
        x.add_argument("--days", type=int, default=7)
        x = sub.add_parser("enroll-show")
        x.add_argument("host")
        sub.add_parser("enroll-list").add_argument("--json", action="store_true")
        sub.add_parser("enroll-delete").add_argument("host")
        x = sub.add_parser("audit")
        x.add_argument("--limit", type=int, default=50)
        x.add_argument("--json", action="store_true")
        try:
            a = p.parse_args(argv)
        except (argparse.ArgumentError, SystemExit) as e:
            raise Fail(f"{e}") from None
        return getattr(self, "cmd_" + a.cmd.replace("-", "_"))(a)

    # ---- git
    def git(self, argv):
        if len(argv) != 2 or argv[1].strip("/'~") != "fleet.git":
            raise Fail("The repository is fleet.git.")
        audit(self.db, self.actor, argv[0], "fleet.git")
        env = {**os.environ, "MOS_FLEET_ADMIN": self.actor}
        os.execvpe(argv[0], [argv[0], GIT], env)

    # ---- reading
    def cmd_info(self, a):
        repo = main_repo()
        thp = subprocess.run(["tang-show-keys", TANG_PORT], capture_output=True, text=True)
        key = ssh_key(open("/etc/ssh/ssh_host_ed25519_key.pub").read())
        say(json.dumps({"version": VERSION, "server_host_key": key, "fingerprint": fingerprint(key),
                        "tang_port": int(TANG_PORT), "tang_thumbprint": (thp.stdout.split() or [None])[0] if thp.returncode == 0 else None,
                        "main": main_rev(), "organization": repo.fleet["organization"] if repo else None}))

    def builds_of(self, h):
        b = self.db.build
        return self.db(b.host == h).select(orderby=~b.id, limitby=(0, 1)).first()

    def deployment_of(self, h):
        d = self.db.deployment
        return self.db(d.host == h).select(orderby=~d.id, limitby=(0, 1)).first()

    def cmd_status(self, a):
        db = self.db
        q = (db.host.id > 0) if a.all else (db.host.in_repo == True)  # noqa: E712
        if a.host:
            self.need_host(a.host, in_repo=False)
            q = db.host.name == a.host
        on = online_hosts(db)
        rows = []
        for r in db(q).select(orderby=db.host.name):
            st = host_state(r, self.builds_of(r.name), r.name in on, self.deployment_of(r.name))
            rows.append(dict(name=r.name, online=r.name in on, last_seen=fmt(r.last_seen), profile=r.profile,
                             branch=r.branch, state=st, current_rev=(r.current_rev or "")[:10],
                             desired_rev=(r.desired_rev or "")[:10], address=r.address, agent=r.agent_version,
                             os=r.nixos_version, kernel=r.kernel))
        if a.json:
            say(json.dumps(rows))
            return
        if not rows:
            say("No computers yet: mos-fleet host prepare NAME --profile P --unlock U")
            return
        say(f"{'COMPUTER':16} {'':7} {'LAST SEEN (UTC)':19}  {'PROFILE/BRANCH':18} {'RUNS':10} STATE")
        for r in rows:
            say(f"{r['name']:16} {'online' if r['online'] else 'offline':7} {r['last_seen']:19}  "
                f"{(r['profile'] or '') + '/' + (r['branch'] or ''):18} {r['current_rev'] or '-':10} {r['state']}")
        if a.host and rows:
            r = rows[0]
            say(f"\n  address {r['address'] or '-'}   agent {r['agent'] or '-'}   {r['os'] or ''}   kernel {r['kernel'] or '-'}")
            b = self.builds_of(a.host)
            if b and b.ok is False:
                say(f"\n  The last build ({(b.rev or '')[:10]}) failed:\n" + "\n".join("    " + x for x in (b.log or "").splitlines()[-25:]))

    def cmd_logs(self, a):
        db = self.db
        self.need_host(a.host, in_repo=False)
        q = db.log.host == a.host
        if a.unit:
            q &= db.log.unit == a.unit
        if a.priority is not None:
            q &= db.log.priority <= a.priority
        if a.since:
            q &= db.log.time >= since(a.since)
        if a.after:
            q &= db.log.id > a.after
        rows = db(q).select(orderby=~db.log.id, limitby=(0, max(1, min(a.limit, 100000))))
        if a.json:
            say(json.dumps([dict(id=r.id, time=fmt(r.time), unit=r.unit, priority=r.priority, message=r.message)
                            for r in reversed(rows)]))
            return
        last = 0
        for r in reversed(rows):
            say(f"{fmt(r.time)} {r.unit or '?'}[{r.priority}]: {r.message}")
            last = max(last, r.id)
        while a.follow:
            time.sleep(1)
            db.commit()
            for r in db(q & (db.log.id > last)).select(orderby=db.log.id):
                say(f"{fmt(r.time)} {r.unit or '?'}[{r.priority}]: {r.message}")
                last = r.id

    def cmd_builds(self, a):
        db, b = self.db, self.db.build
        q = b.host == a.host if a.host else b.id > 0
        rows = db(q).select(orderby=~b.id, limitby=(0, a.limit))
        if a.json:
            say(json.dumps([dict(id=r.id, host=r.host, branch=r.branch, rev=r.rev, started=fmt(r.started),
                                 finished=fmt(r.finished), ok=r.ok, log=(r.log or "")[-20000:] if a.log else None)
                            for r in rows]))
            return
        for r in rows:
            st = "ok" if r.ok else "FAILED" if r.ok is False else "building" if r.started else "retry asked"
            say(f"{fmt(r.started)}  {r.host:16} {r.branch or '':10} {(r.rev or '')[:10]}  {st}")
            if a.log and r.log:
                say("\n".join("    " + x for x in r.log.splitlines()[-40:]))

    def cmd_build_retry(self, a):
        """Build again a computer's failed build of the same commit (a network
        problem, a full disk): once per request, and recorded."""
        db, b, hs = self.db, self.db.build, heads()
        asked = []
        for h in a.hosts:
            row = self.need_host(h)
            rev = hs.get(row.branch or "main")
            last = db((b.host == h) & (b.rev == rev)).select(orderby=~b.id).first() if rev else None
            if not last or last.ok is not False:
                raise Fail(f"{h}: its last build of {(rev or '?')[:10]} didn't fail; nothing to retry.")
            b.insert(host=h, rev=rev, branch=row.branch or "main", log=f"retry asked by {self.actor}")
            audit(db, self.actor, "build-retry", h, rev[:10])
            asked.append(h)
        db.commit()
        with open(TRIGGER, "w") as fh:
            fh.write(f"{time.time()}\n")
        say(f"Building again: {', '.join(asked)} (mos-fleet builds).")

    def cmd_deployments(self, a):
        db, d = self.db, self.db.deployment
        self.need_host(a.host, in_repo=False)
        rows = db(d.host == a.host).select(orderby=~d.id, limitby=(0, a.limit))
        if a.json:
            say(json.dumps([dict(id=r.id, rev=r.rev, started=fmt(r.started), finished=fmt(r.finished),
                                 result=r.result, to_system=r.to_system, output=(r.output or "")[-20000:])
                            for r in rows]))
            return
        for r in rows:
            say(f"{fmt(r.started)}  {(r.rev or '')[:10]}  {r.result or '?':8} {os.path.basename(r.to_system or '')[33:]}")
            if r.result == "failed" and r.output:
                say("\n".join("    " + x for x in r.output.splitlines()[-15:]))

    def cmd_jobs(self, a):
        db, j = self.db, self.db.job
        q = (j.host == a.host) if a.host else (j.id > 0)
        rows = db(q & (j.kind != "relay")).select(orderby=~j.id, limitby=(0, a.limit))
        if a.json:
            say(json.dumps([dict(id=r.id, host=r.host, kind=r.kind, created_by=r.created_by, created_on=fmt(r.created_on),
                                 state=job_state(r), command=job_args(r)) for r in rows]))
            return
        for r in rows:
            st = job_state(r)
            say(f"{r.id:6}  {fmt(r.created_on)}  {r.host:16} {r.kind:7} {st:10} by {r.created_by}  {job_args(r)}")

    def cmd_job(self, a):
        r = self.db.job(a.id)
        if not r:
            raise Fail(f"No job {a.id}.")
        d = dict(id=r.id, host=r.host, kind=r.kind, args=json.loads(r.args or "{}"), created_by=r.created_by,
                 created_on=fmt(r.created_on), delivered_on=fmt(r.delivered_on), received_on=fmt(r.received_on),
                 finished_on=fmt(r.finished_on), canceled=r.canceled, exit_code=r.exit_code, output=r.output,
                 state=job_state(r))
        if a.json:
            say(json.dumps(d))
        else:
            say(f"job {r.id} on {r.host}: {r.kind} {job_args(r)}\n  by {r.created_by} at {d['created_on']}; "
                f"sent {d['delivered_on']}; received {d['received_on']}; finished {d['finished_on']}; {job_state(r)}")
            if r.output:
                say(r.output.rstrip("\n"))

    def cmd_audit(self, a):
        db = self.db
        rows = db(db.audit.id > 0).select(orderby=~db.audit.id, limitby=(0, a.limit))
        if a.json:
            say(json.dumps([dict(time=fmt(r.time), actor=r.actor, action=r.action, target=r.target, details=r.details)
                            for r in rows]))
            return
        for r in rows:
            say(f"{fmt(r.time)}  {r.actor:16} {r.action:18} {r.target or ''}  {r.details or ''}")

    # ---- acting
    def jobs_for(self, hosts, kind, args, token=None):
        ids = []
        for h in hosts:
            self.need_host(h)
            ids.append(self.db.job.insert(host=h, kind=kind, args=json.dumps(args), token=token,
                                          created_by=self.actor, created_on=now()))
            audit(self.db, self.actor, f"job-{kind}", h, json.dumps(args))
        self.db.commit()
        return ids

    def cmd_run(self, a):
        hosts = list(a.host)
        if a.profile:
            repo = main_repo()
            if not PROFILE_RE.fullmatch(a.profile) or not repo or a.profile not in repo.profiles:
                raise Fail(f"No profile {a.profile}.")
            hosts += repo.hosts_of(a.profile)
        if not hosts:
            raise Fail("Which computers? --host NAME (again for more) or --profile P")
        ids = self.jobs_for(sorted(set(hosts)), "run", {"argv": a.argv, "timeout": max(1, min(a.timeout, CFG["max_job_seconds"]))})
        self.wait(ids, a.wait)

    def wait(self, ids, seconds):
        db = self.db
        end = time.time() + max(0, min(seconds, 3600))
        while time.time() < end:
            db.commit()
            if all(db.job(i).finished_on for i in ids):
                break
            time.sleep(1)
        db.commit()
        bad = 0
        for i in ids:
            r = db.job(i)
            if r.finished_on:
                say(f"== {r.host}: exit {r.exit_code}  (job {i})")
                if r.output:
                    say(r.output.rstrip("\n"))
                bad += r.exit_code != 0
            else:
                st = job_state(r)
                say(f"== {r.host}: {st + ' (offline?)' if st == 'queued' else st}  (job {i}; mos-fleet job {i})")
        if bad:
            sys.exit(1)

    def cmd_reboot(self, a):
        self.wait(self.jobs_for(a.hosts, "reboot", {}), 0)

    def cmd_switch(self, a):
        self.wait(self.jobs_for(a.hosts, "switch", {}), 0)

    def cmd_facts(self, a):
        self.wait(self.jobs_for(a.hosts, "facts", {}), 0)

    def cmd_cancel(self, a):
        db = self.db
        if not db((db.job.id == a.id) & (db.job.delivered_on == None)).update(canceled=True):  # noqa: E711
            raise Fail(f"Job {a.id}: already sent to the computer (or no such job).")
        audit(db, self.actor, "job-cancel", str(a.id))

    def cmd_relay(self, a):
        """The admin's end of `mos-fleet shell`: the computer connects back to
        this socket, and SSH runs end-to-end through it to its own sshd."""
        self.need_host(a.host)
        token = secrets.token_hex(16)
        path = os.path.join(RELAY, f"{token}.sock")
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        old = os.umask(0o077)
        try:
            srv.bind(path)
        finally:
            os.umask(old)
        srv.listen(1)
        srv.settimeout(CFG["relay_wait_seconds"])
        (jid,) = self.jobs_for([a.host], "relay", {}, token=token)
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            self.db(self.db.job.id == jid).update(canceled=True, finished_on=now(), exit_code=1)
            self.db.commit()
            raise Fail(f"{a.host} didn't answer: is it online? (mos-fleet status {a.host})") from None
        finally:
            srv.close()
            os.unlink(path)
        self.db(self.db.job.id == jid).update(finished_on=now(), exit_code=0)
        self.db.commit()
        pump(0, 1, conn)

    def cmd_password_set(self, a):
        repo = main_repo()
        if not PERSON_RE.fullmatch(a.person) or not repo or a.person not in repo.people:
            raise Fail(f"No person {a.person} in the repository.")
        h = sys.stdin.readline().strip()
        if not HASH_RE.fullmatch(h):
            raise Fail("Expected a yescrypt ($y$) or SHA-512 ($6$) hash on standard input.")
        sdb = open_secrets()
        row = sdb.password(person=a.person)
        if row:
            row.update_record(hash=h, set_on=now(), set_by=self.actor, from_host=None)
        else:
            sdb.password.insert(person=a.person, hash=h, set_on=now(), set_by=self.actor)
        sdb(sdb.passwd_attempt.person == a.person).delete()
        sdb.commit()
        audit(self.db, self.actor, "password-set", a.person)
        say(f"{a.person}'s password is set on the server: computers online get it within seconds, the others "
            f"when they connect (a computer that can't apply it says so in its logs).")

    def cmd_recover(self, a):
        if not HOST_RE.fullmatch(a.host):
            raise Fail("Not a computer name.")
        sdb = open_secrets()
        rows = sdb(sdb.recovery_key.host == a.host).select(orderby=~sdb.recovery_key.id)
        if not rows:
            raise Fail(f"No recovery key for {a.host}.")
        r = next((x for x in rows if x.confirmed), rows.first())
        audit(self.db, self.actor, "recover", a.host)
        say(json.dumps({"host": a.host, "confirmed": bool(r.confirmed), "created_on": fmt(r.created_on),
                        "host_key_fp": fingerprint(r.host_key), "ciphertext": r.ciphertext}))

    def cmd_enroll_create(self, a):
        db = self.db
        repo = main_repo()
        if not HOST_RE.fullmatch(a.host):
            raise Fail("Not a computer name.")
        if not repo or a.profile not in repo.profiles:
            raise Fail(f"No profile {a.profile} on the server's main branch: push it first.")
        if a.unlock not in UNLOCK or not BRANCH_RE.fullmatch(a.branch):
            raise Fail("Bad --unlock or --branch.")
        if a.disk_serial and (len(a.disk_serial) > 100 or not a.disk_serial.isprintable()):
            raise Fail("Bad --disk-serial.")
        key = ssh_key(a.key)
        db(db.enrollment.host == a.host).update(expires=now())  # earlier ones: expired
        t = now()
        db.enrollment.insert(host=a.host, profile=a.profile, unlock=a.unlock, branch=a.branch,
                             disk_serial=a.disk_serial, enroll_key=key, created_by=self.actor, created_on=t,
                             expires=t + datetime.timedelta(days=max(1, min(a.days, CFG["max_enroll_days"]))))
        db.commit()
        audit(db, self.actor, "enroll-create", a.host, f"profile {a.profile}, unlock {a.unlock}")
        write_keys(db, repo)
        self.cmd_info(a)

    def cmd_enroll_show(self, a):
        db = self.db
        e = db(db.enrollment.host == a.host).select(orderby=~db.enrollment.id).first()
        if not e:
            raise Fail(f"No enrollment for {a.host} (mos-fleet host prepare {a.host} …).")
        say(json.dumps(dict(host=e.host, profile=e.profile, unlock=e.unlock, branch=e.branch, disk_serial=e.disk_serial,
                            created_by=e.created_by, created_on=fmt(e.created_on), expires=fmt(e.expires),
                            used_on=fmt(e.used_on) if e.used_on else None, host_key=e.host_key,
                            fingerprint=fingerprint(e.host_key) if e.host_key else None,
                            files=json.loads(e.files or "{}"), facts=json.loads(e.facts or "{}"),
                            address=e.address, added_on=fmt(e.added_on) if e.added_on else None)))

    def cmd_enroll_list(self, a):
        db = self.db
        rows = db(db.enrollment.added_on == None).select(orderby=~db.enrollment.id)  # noqa: E711
        if a.json:
            say(json.dumps([dict(host=e.host, profile=e.profile, created_on=fmt(e.created_on), created_by=e.created_by,
                                 state="introduced" if e.used_on else "expired" if e.expires < now() else "waiting",
                                 fingerprint=fingerprint(e.host_key) if e.host_key else None) for e in rows]))
            return
        for e in rows:
            st = "waiting for: mos-fleet host add" if e.used_on else "expired" if e.expires < now() else "waiting for the computer"
            say(f"{e.host:16} {e.profile:12} {fmt(e.created_on)}  by {e.created_by:12} {st}")

    def cmd_enroll_delete(self, a):
        db = self.db
        n = db(db.enrollment.host == a.host).update(expires=now())
        audit(db, self.actor, "enroll-delete", a.host)
        write_keys(db, main_repo())
        say(f"{n} enrollment(s) for {a.host} cancelled.")


def job_state(r):
    """queued; sent (not yet confirmed: sent again at the next connection); running
    (the computer has it; no result yet, maybe never: e.g. it was turned off); exit N."""
    return ("canceled" if r.canceled else f"exit {r.exit_code}" if r.finished_on
            else "running" if r.received_on else "sent" if r.delivered_on else "queued")


def job_args(r):
    a = json.loads(r.args or "{}")
    return shlex.join(a["argv"]) if "argv" in a else ""


# ------------------------------------------------------------------ hooks --
def pre_receive():
    """Nothing invalid gets into the repository; main is never rewritten."""
    bad = []
    for line in sys.stdin:
        try:
            old, new, ref = line.split()
        except ValueError:
            continue
        branch = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else None
        if not branch or not BRANCH_RE.fullmatch(branch):
            bad.append(f"{ref}: only branches named like main or testing")
            continue
        if new == ZERO:
            if branch == "main":
                bad.append("main can't be deleted")
            continue
        if branch == "main" and old != ZERO and \
                subprocess.run(["git", "--git-dir", GIT, "merge-base", "--is-ancestor", old, new]).returncode != 0:
            bad.append("main can't be rewritten (no force push): add a commit instead (git revert)")
            continue
        r = check_rev(new, os.path.join(STATE, f"check.{os.getpid()}"))
        shutil.rmtree(os.path.join(STATE, f"check.{os.getpid()}"), ignore_errors=True)
        bad += [f"{branch}: {e}" for e in r.errors]
    if bad:
        warn("mos-fleet: push refused:\n  " + "\n  ".join(bad))
        return 1
    return 0


def post_receive():
    db = open_state()
    actor = os.environ.get("MOS_FLEET_ADMIN", "?")
    for line in sys.stdin:
        try:
            old, new, ref = line.split()
        except ValueError:
            continue
        branch = ref.rsplit("/", 1)[-1]
        db.revision.insert(rev=new, branch=branch, pushed_by=actor, pushed_on=now(), valid=True)
        audit(db, actor, "push", branch, f"{old[:10]}..{new[:10]}")
    db.commit()
    refresh(db)
    with open(TRIGGER, "w") as fh:
        fh.write(f"{time.time()}\n")
    say("mos-fleet: accepted; the server builds the computers now (mos-fleet status).")
    return 0


# ------------------------------------------------------------- the builds --
def build():
    """Build each computer's system from the branch it follows; the newest
    good build is what it should run. A failed build leaves it on the
    previous one (and is recorded: not an error of this service). Pushes
    that arrive meanwhile are built before it ends."""
    while True:
        before = heads()
        build_once()
        if heads() == before:
            return 0


def build_once():
    db = open_state()
    with Lock("build.lock"):
        repo = refresh(db)
        if not repo:
            say("No valid main branch yet.")
            return 0
        hs = heads()
        checked = {}
        failed = 0
        os.makedirs(ROOTS, exist_ok=True)
        for h in sorted(repo.hosts):
            branch = repo.hosts[h].get("branch", "main")
            rev = hs.get(branch)
            if not rev:
                continue
            b = db.build
            last = db((b.host == h) & (b.rev == rev)).select(orderby=~b.id).first()
            # A failed build stays failed until a new commit, or `mos-fleet build retry`
            # (a row not started yet); a good one is built again if its system is gone
            # (a server restored from a backup).
            asked = last if last and not last.finished and not last.started else None
            if last and last.finished and (not last.ok or os.path.exists(last.system_path or "")):
                if last.ok:
                    db(db.host.name == h).update(desired_system=last.system_path, desired_rev=rev)
                    db.commit()
                continue
            if branch != "main":
                if rev not in checked:
                    where = os.path.join(STATE, f"check.{os.getpid()}")
                    checked[rev] = check_rev(rev, where).errors
                    shutil.rmtree(where, ignore_errors=True)
                if checked[rev]:
                    fields = dict(host=h, rev=rev, branch=branch, started=now(), finished=now(), ok=False,
                                  log="\n".join(checked[rev]))
                    asked.update_record(**fields) if asked else db.build.insert(**fields)
                    db.commit()
                    continue
            if asked:
                bid = asked.id
                asked.update_record(started=now())
            else:
                bid = db.build.insert(host=h, rev=rev, branch=branch, started=now())
            db.commit()
            say(f"building {h} ({branch} {rev[:10]})")
            ref = f"git+file://{GIT}?ref=refs/heads/{branch}&rev={rev}"
            r = subprocess.run(["nix", "build", "--no-write-lock-file", "--print-out-paths",
                                "--out-link", os.path.join(ROOTS, h),
                                f"{ref}#nixosConfigurations.{h}.config.system.build.toplevel"],
                               capture_output=True, text=True)
            path = r.stdout.strip().splitlines()[-1] if r.returncode == 0 and r.stdout.strip() else ""
            ok = bool(SYSTEM_RE.fullmatch(path))
            db(db.build.id == bid).update(finished=now(), ok=ok, system_path=path if ok else None,
                                          log=clip(r.stderr[-20000:], 20000))
            if ok:
                db(db.host.name == h).update(desired_system=path, desired_rev=rev)
            else:
                failed += 1
                warn(f"FAILED: {h}\n{r.stderr[-3000:]}")
            db.commit()
        return failed


def prune():
    db = open_state()
    repo = main_repo()
    keep = repo.setting("logs", "keep_days", 30) if repo else 30
    t = now()
    db(db.log.time < t - datetime.timedelta(days=keep)).delete()
    db(db.report.time < t - datetime.timedelta(days=CFG["keep_reports_days"])).delete()
    db(db.job.created_on < t - datetime.timedelta(days=CFG["keep_jobs_days"])).delete()
    db(db.deployment.started < t - datetime.timedelta(days=CFG["keep_deployments_days"])).delete()
    db(db.session.disconnected_on < t - datetime.timedelta(days=CFG["keep_sessions_days"])).delete()
    db.commit()
    sdb = open_secrets()
    sdb(sdb.passwd_attempt.time < t - datetime.timedelta(days=30)).delete()
    sdb.commit()
    db.executesql("PRAGMA wal_checkpoint(TRUNCATE)")
    return 0


def setup():
    """At boot (as fleet): folders, the bare repository and its hooks, the
    databases, keys.json."""
    os.umask(0o077)
    for d in (RELAY, ROOTS):
        os.makedirs(d, exist_ok=True)
    if not os.path.isdir(GIT):
        run(["git", "init", "-q", "--bare", "-b", "main", GIT])
    git("config", "receive.fsckObjects", "true")
    git("config", "receive.denyNonFastForwards", "false")  # the hook decides: main never, testing may
    hook = os.environ.get("MOS_FLEET_HOOK", "")
    if not hook.startswith("/nix/store/"):
        raise Fail("MOS_FLEET_HOOK is not set")
    for name in ("pre-receive", "post-receive"):
        p = os.path.join(GIT, "hooks", name)
        write_atomic(p, f"#!/bin/sh\nexec {hook} {name}\n", mode=0o700)
    for f in os.listdir(RELAY):
        os.unlink(os.path.join(RELAY, f))
    db = open_state(migrate=True)
    open_secrets(migrate=True)
    db(db.session.disconnected_on == None).update(disconnected_on=now())  # noqa: E711
    db.commit()
    refresh(db)
    return 0


# ------------------------------------------------------------ entry points --
def serve_main(argv=None):
    """mos-fleet-serve ROLE NAME (sshd's forced command)."""
    argv = sys.argv[1:] if argv is None else argv
    line = os.environ.get("SSH_ORIGINAL_COMMAND", "")
    try:
        if len(argv) != 2:
            raise Fail("usage: mos-fleet-serve ROLE NAME")
        role, name = argv
        if role == "host":
            if not HOST_RE.fullmatch(name):
                raise Fail("bad name")
            words = line.split()
            if not words or words == ["session"]:
                HostSession(name).run()
                return 0
            if words == ["fetch"]:
                return host_fetch(name)
            if len(words) == 2 and words[0] == "relay":
                return host_relay(name, words[1])
            raise Fail("unknown request")
        if role == "enroll":
            if not HOST_RE.fullmatch(name) or line.split() not in ([], ["enroll"]):
                raise Fail("bad enrollment")
            return enroll(name)
        if role in ("admin", "bootstrap"):
            if role == "admin" and not PERSON_RE.fullmatch(name):
                raise Fail("bad name")
            return Admin(role, name).main(line) or 0
        raise Fail("unknown role")
    except Fail as e:
        warn(f"mos-fleet: {e}")
        return 1
    except Invalid as e:
        warn(f"mos-fleet: {e}")
        return 1


def hook_main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        return {"pre-receive": pre_receive, "post-receive": post_receive}[argv[0]]()
    except Fail as e:
        warn(f"mos-fleet: {e}")
        return 1


def status():
    db = open_state()
    on = online_hosts(db)
    say(f"\n== Repository\n   main {main_rev() or '(none yet: mos-fleet init, on an admin computer)'}")
    hosts = db(db.host.in_repo == True).select()  # noqa: E712
    t = now() - datetime.timedelta(days=1)
    bad = db((db.build.ok == False) & (db.build.started > t)).count()  # noqa: E712
    pending = db((db.enrollment.used_on != None) & (db.enrollment.added_on == None)).count()  # noqa: E711
    say(f"\n== Computers\n   {len(hosts)} in the repository, {len(on)} online; {bad} failed build(s) today;"
        f" {pending} waiting for mos-fleet host add")
    for r in hosts:
        say(f"   {r.name:16} {'online ' if r.name in on else 'offline'}  last seen {fmt(r.last_seen)}  "
            f"{host_state(r, db(db.build.host == r.name).select(orderby=~db.build.id).first(), r.name in on, db(db.deployment.host == r.name).select(orderby=~db.deployment.id).first())}")
    return 0


def backup(dest):
    """Consistent copies (SQLite's online backup) and a bundle of the repository."""
    import sqlite3

    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, mode=0o700)
    for name in ("state.db", "secrets.db"):
        src = sqlite3.connect(os.path.join(STATE, name))
        dst = sqlite3.connect(os.path.join(dest, name))
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
    if heads():
        git("bundle", "create", os.path.join(dest, "fleet.bundle"), "--all")
    return 0


def service_main(argv=None):
    """mos-fleet-server setup|build|prune|refresh|status|backup DIR (as fleet)."""
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv[:1] == ["backup"] and len(argv) == 2:
            return backup(argv[1])
        return {"setup": setup, "build": build, "prune": prune, "status": status,
                "refresh": lambda: refresh() and 0}[argv[0]]()
    except Fail as e:
        warn(f"mos-fleet: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(serve_main())
