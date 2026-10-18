"""The agent on a managed computer (root, systemd: mos-fleet-agent).

It keeps one SSH connection to the fleet server open, authenticated with
this computer's own SSH host key, the server's key pinned
(/etc/mos-fleet/known_hosts). Over it:

  - it sends facts, logs (journald, since the last acknowledged cursor) and
    the results of what it did;
  - it receives the system it should run (fetched with `fetch`, then
    switched to), its people's password hashes, and jobs (run a command,
    reboot, switch, report facts, relay an admin's SSH to the local sshd).

The server can't reach it: it always connects out, so laptops behind NAT
work. A new computer first introduces itself with the one-time key the
installer copied from the stick (enroll.key), then waits until an admin
adds it to the repository.

mos-passwd talks to it over /run/mos-fleet/agent.sock (it knows who is
asking from the socket's peer credentials).
"""

import getpass
import json
import os
import pwd
import queue
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time

from .common import (HASH_RE, MAX_LINE, STORE_PATH_RE, SYSTEM_RE, TOKEN_RE, VERSION, Fail, dumps, parse,
                     split_server, write_atomic, SERVER_ALIAS)
from . import settings
from .repo import PERSON_RE

CONF = "/etc/mos-fleet/client.json"
KNOWN = "/etc/mos-fleet/known_hosts"
CFG = settings.get("agent")
STATE = os.environ.get("MOS_FLEET_STATE") or CFG["state"]
RUN = "/run/mos-fleet"
SOCK = os.path.join(RUN, "agent.sock")
IDENTITY = "/etc/ssh/ssh_host_ed25519_key"
PASSWORDS = os.path.join(STATE, "passwords")
ENROLL_KEY = os.path.join(STATE, "enroll.key")
RECOVERY = os.path.join(STATE, "recovery.age")
ENROLLED = os.path.join(STATE, "enrolled")
ACCEPTED = os.path.join(STATE, "accepted")  # the server has let it in once: it is in the fleet
CURSOR = os.path.join(STATE, "log.cursor")
JOBS_SEEN = os.path.join(STATE, "jobs.seen")  # jobs received: one sent again isn't run again
SYSTEM_PROFILE = "/nix/var/nix/profiles/system"


def log(text):
    print(text, flush=True)


def log_error(text):
    print(f"<3>{text}", flush=True)  # journald: priority err (sent with the logs)


def ssh_cmd(cfg, *remote, identity=IDENTITY):
    host, port = split_server(cfg["server"])
    return ["ssh", "-F", "/dev/null", "-i", identity, "-o", "IdentitiesOnly=yes",
            "-o", f"UserKnownHostsFile={KNOWN}", "-o", "GlobalKnownHostsFile=/dev/null",
            "-o", "StrictHostKeyChecking=yes", "-o", f"HostKeyAlias={SERVER_ALIAS}", "-o", "BatchMode=yes",
            "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3", "-o", "ConnectTimeout=20",
            "-o", "LogLevel=ERROR", "-p", port, f"fleet@{host}", *remote]


def current_system():
    return os.path.realpath("/run/current-system")


def read(path, limit=1 << 20):
    try:
        with open(path) as fh:
            return fh.read(limit)
    except OSError:
        return None


def facts():
    f = {"hostname": socket.gethostname(), "kernel": os.uname().release, "agent": VERSION}
    osr = dict(line.split("=", 1) for line in (read("/etc/os-release") or "").splitlines() if "=" in line)
    f["os"] = osr.get("PRETTY_NAME", "").strip('"')
    try:
        f["uptime"] = int(float(read("/proc/uptime").split()[0]))
        f["load"] = read("/proc/loadavg").split()[:3]
        mem = dict(line.split(":", 1) for line in read("/proc/meminfo").splitlines() if ":" in line)
        f["memory_mb"] = int(mem["MemTotal"].split()[0]) // 1024
    except (AttributeError, KeyError, ValueError, IndexError):
        pass
    f["current_system"] = current_system()
    f["booted_system"] = os.path.realpath("/run/booted-system")
    for key, cmd in (("disks", ["lsblk", "-J", "-d", "-o", "NAME,SIZE,MODEL,SERIAL,TYPE"]),
                     ("addresses", ["ip", "-j", "-brief", "address"])):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                f[key] = json.loads(r.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    return f


class Agent:
    def __init__(self):
        with open(CONF) as fh:
            self.cfg = json.load(fh)
        self.proc = None
        self.wlock = threading.Lock()
        self.q = queue.Queue()
        self.want = None  # (system, rev) the server says
        self.deploying = threading.Lock()
        self.failed = set()  # systems that failed to switch: not retried by themselves
        self.pending = {}  # passwd requests: req -> [Event, result]
        self.req = 0
        self.cursor_sent = None
        self.restart = False
        self.was_refused = False
        self.pw_lock = threading.Lock()

    # ---- the connection
    def send(self, obj):
        with self.wlock:
            p = self.proc
            if not p or p.poll() is not None:
                raise Fail("not connected")
            p.stdin.write((dumps(obj) + "\n").encode())
            p.stdin.flush()

    def try_send(self, obj):
        try:
            self.send(obj)
            return True
        except (Fail, OSError):
            return False

    def run(self):
        os.makedirs(STATE, mode=0o700, exist_ok=True)
        threading.Thread(target=self.serve_socket, daemon=True).start()
        backoff = 10
        while True:
            if os.path.exists(ENROLL_KEY) and not os.path.exists(ENROLLED) and not self.enroll():
                # The server may have taken it and only its answer got lost (the key then
                # works no more): once an admin adds this computer, its session gets in.
                self.session()
                if self.restart:
                    return 0
                if not os.path.exists(ENROLLED):
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 2 * CFG["reconnect_max_seconds"])
                    continue
            started = time.time()
            why = self.session()
            if self.restart:
                log("restarting with the new system's agent")
                return 0
            backoff = 10 if time.time() - started > 120 else min(backoff * 2, CFG["reconnect_max_seconds"])
            if why in ("bye", "refused"):
                backoff = 2 * CFG["reconnect_max_seconds"]
            time.sleep(backoff)

    def enroll(self):
        """Once: introduce this computer with the stick's one-time key."""
        files = {}
        for f in ("hardware-configuration.nix", "local.nix", "meccanicos.toml"):
            t = read(f"/etc/nixos/{f}", 256 << 10)
            if t is not None:
                files[f] = t
        payload = {"host_key": read(IDENTITY + ".pub", 8192) or "", "files": files,
                   "recovery": read(RECOVERY, 16 << 10) or "", "facts": facts()}
        try:
            os.chmod(ENROLL_KEY, 0o600)
            r = subprocess.run(ssh_cmd(self.cfg, "enroll", identity=ENROLL_KEY), input=dumps(payload) + "\n",
                               capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as e:
            log(f"enrollment: {e}")
            return False
        try:
            res = parse(r.stdout.strip().splitlines()[-1].encode()) if r.stdout.strip() else {}
        except Fail:
            res = {}
        if not res.get("ok"):
            log(f"enrollment: {res.get('error') or r.stderr.strip()[-300:] or 'no answer'}")
            return False
        self.enrolled()
        log(f"enrolled ({res.get('fingerprint')}): an admin adds this computer with mos-fleet host add")
        return True

    def enrolled(self):
        write_atomic(ENROLLED, time.strftime("%Y-%m-%d %H:%M:%S\n"))
        for f in (ENROLL_KEY, RECOVERY):
            try:
                os.remove(f)
            except OSError:
                pass

    def session(self):
        try:
            self.proc = subprocess.Popen(ssh_cmd(self.cfg, "session"), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE)
        except OSError as e:
            log(f"ssh: {e}")
            return "error"
        q = self.q = queue.Queue()
        refused = threading.Event()

        def errors(err):
            # ssh's own messages, to the journal; a refused key is how a
            # computer learns it was retired while it wasn't connected.
            for line in err:
                text = line.decode(errors="replace").rstrip()
                if "Permission denied" in text:
                    refused.set()
                else:
                    log(f"ssh: {text}")

        threading.Thread(target=errors, args=(self.proc.stderr,), daemon=True).start()

        def reader(out):
            try:
                for line in out:
                    try:
                        q.put(parse(line))
                    except Fail:
                        pass
            finally:
                q.put(None)

        threading.Thread(target=reader, args=(self.proc.stdout,), daemon=True).start()
        why = "closed"
        try:
            self.send({"t": "hello", "agent": VERSION, "system": current_system(), "facts": facts()})
            interval = int(self.cfg.get("interval", 300))
            next_facts, next_logs = time.time() + interval, time.time() + 5
            while True:
                try:
                    msg = q.get(timeout=1)
                except queue.Empty:
                    msg = False
                if msg is None:
                    break
                if msg:
                    if not os.path.exists(ACCEPTED):
                        write_atomic(ACCEPTED, time.strftime("%Y-%m-%d %H:%M:%S\n"))
                    if os.path.exists(ENROLL_KEY) and not os.path.exists(ENROLLED):
                        log("enrolled (the server's answer to the enrollment was lost; it is in the fleet now)")
                        self.enrolled()
                    if msg.get("t") == "bye":
                        log(f"the server says: {msg.get('reason')}")
                        why = "bye"
                        break
                    self.handle(msg)
                if self.restart:
                    break
                t = time.time()
                if t >= next_facts:
                    next_facts = t + interval
                    self.send({"t": "facts", "agent": VERSION, "system": current_system(), "facts": facts()})
                    self.apply_passwords(self.current_hashes())  # again what failed before
                if t >= next_logs:
                    next_logs = t + CFG["logs_every_seconds"]
                    self.send_logs()
        except (Fail, OSError) as e:
            log(f"session: {e}")
        finally:
            with self.wlock:
                p, self.proc = self.proc, None
            try:
                p.stdin.close()
            except OSError:
                pass
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
            for ev in self.pending.values():
                ev[0].set()
        if why == "closed" and refused.wait(timeout=2):
            why = "refused"
            if not self.was_refused:
                log("the server refuses this computer's key: it is no longer in the fleet (or its key changed); "
                    "trying again now and then" if os.path.exists(ACCEPTED) else
                    "the server doesn't know this computer yet: an admin adds it (mos-fleet host add "
                    f"{socket.gethostname()}); trying again now and then")
        self.was_refused = why == "refused"
        return why

    def handle(self, m):
        t = m.get("t")
        if t == "desired":
            s, rev = m.get("system"), m.get("rev")
            if isinstance(s, str) and SYSTEM_RE.fullmatch(s):
                self.want = (s, rev if isinstance(rev, str) else None)
                if s != current_system() and s not in self.failed:
                    self.deploy()
        elif t == "passwords":
            h = m.get("hashes")
            if isinstance(h, dict):
                self.apply_passwords(h)
        elif t == "job":
            jid = m.get("id")
            if not isinstance(jid, int):
                return
            seen = self.jobs_seen()
            new = jid not in seen
            if new:  # written down before it runs: sent again (our answer lost), it isn't run twice
                write_atomic(JOBS_SEEN, dumps((seen + [jid])[-1000:]) + "\n")
            self.try_send({"t": "job-got", "id": jid})
            if new:
                threading.Thread(target=self.job, args=(m,), daemon=True).start()
        elif t == "logs-ok":
            # The answer to a batch, or (at the start) where the server's copy ends: what it
            # has stored is where the next batch starts, so nothing is sent twice.
            cur = m.get("cursor")
            if isinstance(cur, str) and cur and len(cur) < 4096 and cur != (read(CURSOR, 4096) or "").strip():
                write_atomic(CURSOR, cur)
        elif t == "passwd-result":
            ev = self.pending.get(m.get("req"))
            if ev:
                ev[1] = m
                ev[0].set()

    def jobs_seen(self):
        try:
            seen = json.loads(read(JOBS_SEEN, 1 << 20) or "[]")
            return [i for i in seen if isinstance(i, int)] if isinstance(seen, list) else []
        except ValueError:
            return []

    # ---- the system
    def deploy(self, force=False, done=None):
        if not self.want or not self.deploying.acquire(blocking=False):
            return False
        system, rev = self.want

        def work():
            ok = system == current_system()
            try:
                if ok and not force:
                    return
                self.try_send({"t": "deploy", "state": "started", "system": system, "rev": rev})
                log(f"switching to {system}")
                code = None
                try:
                    self.fetch(system)
                    code, out = self.switch(system)
                except (Fail, OSError, subprocess.SubprocessError) as e:
                    out = str(e)
                running = current_system() == system
                # Both: switch-to-configuration can fail after the new system became the current one.
                ok = code == 0 and running
                if not ok:
                    self.failed.add(system)
                    if running:
                        out = (f"the new system is running, but switching failed (exit {code}): some services "
                               "may not have started; mos-fleet switch tries again, the boot menu has the "
                               f"previous system\n{out}")
                log(f"switch {'done' if ok else 'FAILED'}: {out[-500:]}")
                self.try_send({"t": "deploy", "state": "ok" if ok else "failed", "system": system, "rev": rev,
                               "output": out[-60000:]})
                if running:
                    self.restart = True  # the new system may carry a new agent
            finally:
                self.deploying.release()
                if done:
                    done(ok)

        threading.Thread(target=work, daemon=True).start()
        return True

    def fetch(self, system):
        """The store paths this computer lacks, from the server, imported."""
        p = subprocess.Popen(ssh_cmd(self.cfg, "fetch"), stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        try:
            p.stdin.write((dumps({"system": system}) + "\n").encode())
            p.stdin.flush()
            r = parse(p.stdout.readline(64 << 20))
            if not r.get("ok"):
                raise Fail(f"fetch: {r.get('error')}")
            paths = r.get("paths")
            if not isinstance(paths, list) or system not in paths \
                    or not all(isinstance(x, str) and STORE_PATH_RE.fullmatch(x) for x in paths):
                raise Fail("fetch: a bad list of paths")
            missing = []
            for i in range(0, len(paths), 500):
                out = subprocess.run(["nix-store", "--check-validity", "--print-invalid", *paths[i:i + 500]],
                                     capture_output=True, text=True)
                missing += out.stdout.split()
            p.stdin.write((dumps({"want": missing}) + "\n").encode())
            p.stdin.flush()
            r = parse(p.stdout.readline(1 << 20))
            if not r.get("ok"):
                raise Fail(f"fetch: {r.get('error')}")
            log(f"fetching {len(missing)} of {len(paths)} store paths")
            if missing:
                imp = subprocess.Popen(["nix-store", "--import"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL)
                shutil.copyfileobj(p.stdout, imp.stdin, 1 << 20)
                imp.stdin.close()
                if imp.wait() != 0:
                    raise Fail("nix-store --import failed")
        finally:
            try:
                p.stdin.close()
            except OSError:
                pass
            p.wait(timeout=60)
        if subprocess.run(["nix-store", "--check-validity", system], capture_output=True).returncode != 0:
            raise Fail("the system isn't complete after fetching")

    def switch(self, system):
        subprocess.run(["nix-env", "-p", SYSTEM_PROFILE, "--set", system], check=True, capture_output=True)
        # Outside this service's cgroup: switching may restart services, and
        # must finish even if the agent itself goes away meanwhile.
        r = subprocess.run(["systemd-run", "--unit", f"mos-fleet-switch-{int(time.time())}", "--wait",
                            "--collect", "--pipe", "--quiet", "--service-type=exec",
                            f"{system}/bin/switch-to-configuration", "switch"],
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace")
        return r.returncode, f"exit {r.returncode}\n{r.stdout}{r.stderr}"

    # ---- people
    def apply_passwords(self, hashes):
        """Returns the people whose password could not be set here (tried again later)."""
        with self.pw_lock:  # the session and mos-passwd's socket both apply them
            return self._apply_passwords(hashes)

    def _apply_passwords(self, hashes):
        os.makedirs(PASSWORDS, mode=0o700, exist_ok=True)
        good = {n: h for n, h in hashes.items()
                if isinstance(n, str) and PERSON_RE.fullmatch(n) and isinstance(h, str) and HASH_RE.fullmatch(h)}
        for f in os.listdir(PASSWORDS):
            if f not in good:
                os.remove(os.path.join(PASSWORDS, f))
        failed, shadow = [], {}
        for line in (read("/etc/shadow", 16 << 20) or "").splitlines():
            parts = line.split(":")
            if len(parts) > 1:
                shadow[parts[0]] = parts[1]
        for n, h in good.items():
            path = os.path.join(PASSWORDS, n)
            if read(path) != h + "\n":
                write_atomic(path, h + "\n")  # hashedPasswordFile: read at activation
            try:
                if pwd.getpwnam(n).pw_uid >= 1000 and shadow.get(n) != h:
                    r = subprocess.run(["chpasswd", "-e"], input=f"{n}:{h}\n", text=True, capture_output=True)
                    if r.returncode != 0:
                        failed.append(n)
                        log_error(f"password of {n}: not set on this computer (chpasswd: "
                                  f"{(r.stderr or '').strip()[-200:] or r.returncode}); trying again later")
            except KeyError:
                pass  # not on this computer (yet): its system brings the account
        return failed

    # ---- jobs
    def job(self, m):
        jid, kind, args = m.get("id"), m.get("kind"), m.get("args") or {}

        def done(code, output=""):
            self.try_send({"t": "job-done", "id": jid, "code": code, "output": output[-250000:]})

        if kind == "run":
            argv = args.get("argv")
            if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
                return done(2, "bad command")
            try:
                r = subprocess.run(argv, capture_output=True, text=True, errors="replace",
                                   timeout=int(args.get("timeout", CFG["job_timeout_seconds"])), stdin=subprocess.DEVNULL)
                done(r.returncode, r.stdout + r.stderr)
            except FileNotFoundError:
                done(127, f"{argv[0]}: command not found")
            except subprocess.TimeoutExpired as e:
                done(124, f"timed out\n{e.stdout or ''}")
        elif kind == "reboot":
            done(0, "rebooting")
            time.sleep(3)
            subprocess.run(["systemctl", "reboot"])
        elif kind == "switch":
            if not self.want:
                return done(1, "no system from the server yet")
            self.failed.discard(self.want[0])
            ev, result = threading.Event(), []
            if not self.deploy(force=True, done=lambda ok: (result.append(ok), ev.set())):
                return done(1, "a switch is already running")
            ev.wait()
            done(0 if result and result[0] else 1, f"now running {current_system()}"
                 + ("" if result and result[0] else "; the switch failed: mos-fleet deployments " + socket.gethostname()))
        elif kind == "facts":
            ok = self.try_send({"t": "facts", "agent": VERSION, "system": current_system(), "facts": facts()})
            done(0 if ok else 1, "")
        elif kind == "relay":
            self.relay(m.get("token"))
        else:
            done(2, f"unknown job {kind!r}")

    def relay(self, token):
        """An admin's `mos-fleet shell`: our sshd, through the server."""
        if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
            return
        try:
            sock = socket.create_connection(("127.0.0.1", 22), timeout=10)
        except OSError as e:
            log(f"relay: {e}")
            return
        p = subprocess.Popen(ssh_cmd(self.cfg, "relay", token), stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        sock.settimeout(None)

        def up():
            try:
                while True:
                    d = os.read(p.stdout.fileno(), 1 << 16)
                    if not d:
                        break
                    sock.sendall(d)
            except OSError:
                pass
            finally:
                try:
                    sock.shutdown(socket.SHUT_WR)
                except OSError:
                    pass

        threading.Thread(target=up, daemon=True).start()
        try:
            while True:
                d = sock.recv(1 << 16)
                if not d:
                    break
                p.stdin.write(d)
                p.stdin.flush()
        except OSError:
            pass
        finally:
            try:
                p.stdin.close()
            except OSError:
                pass
            p.wait()
            sock.close()

    # ---- logs
    def send_logs(self):
        lg = self.cfg.get("logs", {})
        prio, units = int(lg.get("min_priority", 4)), set(lg.get("units", []))
        cursor = (read(CURSOR, 4096) or "").strip()
        cmd = ["journalctl", "-o", "json", "--no-pager"] + (
            [f"--after-cursor={cursor}"] if cursor else ["--since=-1h"])
        entries, last, size, lines = [], None, 0, 0
        budget = MAX_LINE - (64 << 10)  # what one message may hold, less room for the rest of it
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            for line in p.stdout:
                lines += 1
                if lines > CFG["log_batch"]:
                    break
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                cur = e.get("__CURSOR")
                unit = e.get("_SYSTEMD_UNIT") or e.get("SYSLOG_IDENTIFIER") or ""
                try:
                    pr = int(e.get("PRIORITY", 6))
                except ValueError:
                    pr = 6
                if pr > prio and unit not in units and unit.removesuffix(".service") not in units:
                    last = cur or last
                    continue
                msg = e.get("MESSAGE", "")
                if isinstance(msg, list):
                    msg = bytes(x & 0xFF for x in msg if isinstance(x, int)).decode(errors="replace")
                entry = {"time": int(e.get("__REALTIME_TIMESTAMP", 0)) / 1e6, "unit": unit, "prio": pr,
                         "msg": str(msg)[:4096], "boot": e.get("_BOOT_ID")}
                # Counted as sent (escapes, multibyte); full: the rest next time, from here.
                n = len(dumps(entry).encode()) + 1
                if size + n > budget:
                    break
                size += n
                entries.append(entry)
                last = cur or last
        finally:
            p.kill()
            p.wait()
        if cursor and not lines and p.returncode not in (0, -9):
            # A cursor this journal doesn't know (a reinstalled computer): start again from the last hour.
            log("the log cursor is not in this journal: sending from the last hour")
            os.remove(CURSOR)
            return
        if last and last != cursor:
            self.cursor_sent = last
            self.send({"t": "logs", "entries": entries, "cursor": last})

    # ---- mos-passwd
    def serve_socket(self):
        os.makedirs(RUN, mode=0o755, exist_ok=True)
        try:
            os.unlink(SOCK)
        except OSError:
            pass
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(SOCK)
        os.chmod(SOCK, 0o666)
        srv.listen(8)
        while True:
            conn, _ = srv.accept()
            threading.Thread(target=self.passwd_client, args=(conn,), daemon=True).start()

    def passwd_client(self, conn):
        def reply(ok, msg):
            conn.sendall((dumps({"ok": ok, "message": msg}) + "\n").encode())

        try:
            conn.settimeout(120)
            _, uid, _ = struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            person = pwd.getpwuid(uid).pw_name
            data = b""
            while not data.endswith(b"\n") and len(data) < 8192:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
            m = parse(data)
            old, new = m.get("old"), m.get("new")
            if uid < 1000 or not PERSON_RE.fullmatch(person):
                return reply(False, "only people of the organization change their password here")
            if not isinstance(old, str) or not isinstance(new, str) or not CFG["min_password"] <= len(new) <= 128 or new == old:
                return reply(False, f"the new password needs {CFG['min_password']} to 128 characters, and differ from the current one")
            h = subprocess.run(["mkpasswd", "-m", "yescrypt", "--stdin"], input=new, capture_output=True,
                               text=True).stdout.strip()
            if not HASH_RE.fullmatch(h):
                return reply(False, "could not hash the password")
            self.req += 1
            req = self.req
            ev = self.pending[req] = [threading.Event(), None]
            if not self.try_send({"t": "passwd", "req": req, "person": person, "old": old, "new_hash": h}):
                return reply(False, "not connected to the organization's server: try again later (on its network)")
            ev[0].wait(30)
            res = self.pending.pop(req, [None, None])[1]
            if not res:
                return reply(False, "the server didn't answer: try again")
            if res.get("ok"):
                if self.apply_passwords({**self.current_hashes(), person: h}):
                    return reply(False, "Password changed on the server, but not yet on this computer (it tries "
                                        "again by itself); other computers get it when they next connect.")
                return reply(True, "Password changed here and on the server; the organization's other "
                                   "computers get it when they next connect.")
            return reply(False, res.get("error") or "refused")
        except (OSError, Fail, KeyError, struct.error) as e:
            try:
                reply(False, f"{e}")
            except OSError:
                pass
        finally:
            conn.close()

    def current_hashes(self):
        out = {}
        for f in os.listdir(PASSWORDS) if os.path.isdir(PASSWORDS) else []:
            h = (read(os.path.join(PASSWORDS, f)) or "").strip()
            if h:
                out[f] = h
        return out


def main(argv=None):
    if os.geteuid() != 0:
        print("mos-fleet-agent runs as root (systemd: mos-fleet-agent.service).", file=sys.stderr)
        return 1
    try:
        return Agent().run()
    except KeyboardInterrupt:
        return 130


def passwd_main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    """mos-passwd: change your password, on every computer of the organization."""
    if not os.path.exists(SOCK):
        print("mos-passwd: this computer isn't managed by an organization (use passwd).", file=sys.stderr)
        return 1
    try:
        if argv == ["--stdin"]:  # for scripts: three lines, current / new / new again
            lines = sys.stdin.read().splitlines() + ["", "", ""]
            old, new, again = lines[:3]
        else:
            old = getpass.getpass("Current password: ")
            new = getpass.getpass("New password: ")
            again = getpass.getpass("New password again: ")
        if again != new:
            print("mos-passwd: the two new passwords differ; nothing changed.", file=sys.stderr)
            return 1
    except (EOFError, KeyboardInterrupt):
        return 130
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(SOCK)
    s.sendall((dumps({"old": old, "new": new}) + "\n").encode())
    data = b""
    while not data.endswith(b"\n"):
        chunk = s.recv(4096)
        if not chunk:
            break
        data += chunk
    try:
        r = json.loads(data)
    except ValueError:
        r = {"ok": False, "message": "no answer from the agent"}
    print(("" if r.get("ok") else "mos-passwd: ") + str(r.get("message")), file=sys.stdout if r.get("ok") else sys.stderr)
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
