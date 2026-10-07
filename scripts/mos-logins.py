#!/usr/bin/env python3
"""mos-logins - who logged in, who tried, and what to do about it.

  mos-logins                  full screen: who is connected now, the history
  mos-logins list [DAYS]      logins and failed attempts (default: 7 days)
  mos-logins now              remote sessions and SSH connections right now
  mos-logins block IP [MIN]   refuse everything from IP (default: 60 minutes)
  mos-logins unblock IP       mos-logins blocked
  mos-logins trust IP|KEY     no alerts for this address or SSH key
  mos-logins disconnect       end remote sessions, stop SSH, cut every
                                network, lock the screen (also Super+Shift+Esc)
  mos-logins reconnect        networks back, and SSH if it was on
  mos-logins watch            the watcher (a user service, from login)
  mos-logins demo             a sample alert; nothing is changed

The watcher reads the system journal: SSH logins and attempts, wrong
passwords (lock screen, login screen, sudo) and wrong disk passwords at boot.
It tells you about:
  - an SSH login from an address or key not seen before: at once;
  - an SSH attack: many failures from one address on your network, or
    aimed at your own user name: at once, with Block / Stop SSH / Disconnect;
  - anything that happened while the screen was locked or you were logged
    out: one summary when you are back.
Internet scanners (random user names, any SSH server gets them) are only
counted: sshguard blocks them by itself. Alerts never pile up: one per
address per hour, at most 3 of each kind an hour, then one "see
mos-logins" (a flood of attacks never hides a new login).
mos-config set security.login_alerts off turns them off;
security.auto_disconnect on disconnects by itself on an unknown SSH login.
"""

import collections
import curses
import datetime
import ipaddress
import json
import locale
import os
import pwd
import re
import shutil
import subprocess
import sys
import threading
import time

# The look shared by MeccanicOS TUIs: MECCANICOS_PYLIB from the Nix wrapper, else next to this file.
sys.path.insert(0, os.environ.get("MECCANICOS_PYLIB") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import mos_tui as ui  # noqa: E402

SELF = os.environ.get("MECCANICOS_LOGINS_SELF") or os.path.abspath(sys.argv[0])
STATE = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "meccanicos", "logins.json")
SETTINGS = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "meccanicos", "settings.toml")
RUN = "/run/mos-logins"  # root's: was SSH on before a disconnect
ENV = dict(os.environ, LC_ALL="C")

# ---- what the journal says -----------------------------------------------------------
GREP = "Accepted |Invalid user |Failed (password|publickey|keyboard)|authenticating user|authentication failure|specified passphrase|No key available"
RULES = [
    ("ssh-ok", re.compile(r"Accepted (\S+) for (?P<user>\S+) from (?P<ip>\S+) port \d+(?: \w+)?(?:: \S+ (?P<key>\S+))?")),
    ("ssh-fail", re.compile(r"Invalid user (?P<user>\S*) from (?P<ip>\S+) port")),
    ("ssh-fail", re.compile(r"Failed \S+ for (?:invalid user )?(?P<user>\S+) from (?P<ip>\S+) port")),
    ("ssh-fail", re.compile(r"Connection (?:closed|reset) by (?:authenticating|invalid) user (?P<user>\S+) (?P<ip>\S+) port")),
    ("password-fail", re.compile(r"pam_unix\((?P<service>[^:]+):auth\): authentication failure.*?(?:\buser=(?P<user>\S+))?\s*$")),
    ("disk-fail", re.compile(r"Failed to activate with specified passphrase|No key available with this passphrase")),
]
PLACES = {"xfce4-screensaver": "the lock screen", "lightdm": "the login screen", "login": "the console",
          "sudo": "sudo", "su": "su", "polkit-1": "an administrator prompt"}


def parse(entry):
    """One journal entry (dict) -> an event dict, or None."""
    msg = entry.get("MESSAGE")
    if isinstance(msg, list):  # binary messages come as byte lists
        msg = bytes(msg).decode(errors="replace")
    if not isinstance(msg, str):
        return None
    for kind, rx in RULES:
        m = rx.search(msg)
        if m:
            g = m.groupdict()
            when = int(entry.get("__REALTIME_TIMESTAMP", "0")) / 1e6
            ev = {"time": when, "kind": kind, "user": g.get("user") or "", "ip": g.get("ip") or "",
                  "key": g.get("key") or "", "service": g.get("service") or "", "boot": entry.get("_BOOT_ID", "")}
            if kind == "password-fail" and ev["service"] in ("sshd", "sshd-session"):
                return None  # the sshd lines above say it better
            return ev
    return None


def journal(since=None, follow=False, boot=False, last=None):
    """Events from the system journal (newest last); follow: forever."""
    cmd = ["journalctl", "-o", "json", "--no-pager", "-q", "-g", GREP]
    if follow:
        cmd += ["-f", "-n", "0"]
    if since:
        cmd += ["--since", f"@{int(since)}"]
    if boot:
        cmd += ["-b"]
    if last:
        cmd += ["-n", str(last)]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=ENV)
    except OSError:
        return
    try:
        for line in p.stdout:
            try:
                ev = parse(json.loads(line))
            except ValueError:
                continue
            if ev:
                yield ev
    finally:
        p.kill()
        p.wait()


def private(ip):
    try:
        a = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    return a.is_private or a.is_link_local or a.is_loopback


def my_users():
    """Real accounts here (uid 1000+): attempts on them are aimed at you."""
    return {p.pw_name for p in pwd.getpwall() if 1000 <= p.pw_uid < 60000}


# ---- state and settings ---------------------------------------------------------------
def load_state():
    try:
        with open(STATE) as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {}
    s.setdefault("ips", [])
    s.setdefault("keys", [])
    s.setdefault("seen", 0)
    return s


def save_state(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".part"
    with open(tmp, "w") as f:
        json.dump(s, f, indent=1)
    os.replace(tmp, STATE)


def setting(name, default):
    """[security] name in ~/.config/meccanicos/settings.toml (mos-config)."""
    try:
        import tomllib
        with open(SETTINGS, "rb") as f:
            v = tomllib.load(f).get("security", {}).get(name)
    except (OSError, ValueError, ImportError):
        return default
    return default if v is None else bool(v)


def known(state, ip, key):
    return ip in state["ips"] or (key and key in state["keys"])


def trust(target):
    s = load_state()
    field = "keys" if target.startswith(("SHA256:", "MD5:")) else "ips"
    if target not in s[field]:
        s[field].append(target)
        save_state(s)


# ---- doing (root's part runs through sudo) ---------------------------------------------
def as_root(*args):
    """Run `mos-logins root ARGS` with sudo; (ok, output)."""
    cmd = [SELF, "root", *args] if os.geteuid() == 0 else ["sudo", "-n", SELF, "root", *args]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    out = (p.stdout + p.stderr).strip()
    if p.returncode != 0 and "password is required" in out:
        out = "needs an administrator: run it with sudo in a terminal"
    return p.returncode == 0, out


def lock_screen():
    for cmd in (["xflock4"], ["loginctl", "lock-session"]):
        if shutil.which(cmd[0]):
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return


def disconnect():
    ok, out = as_root("disconnect")
    lock_screen()
    return ok, out


def reconnect():
    return as_root("reconnect")


def ssh_on():
    return subprocess.run(["systemctl", "is-active", "--quiet", "sshd.service"]).returncode == 0


def network_on():
    try:
        return subprocess.run(["nmcli", "networking"], capture_output=True, text=True, env=ENV).stdout.strip() == "enabled"
    except OSError:
        return True


NFT = """table inet mos-logins {
  set blocked4 { type ipv4_addr; flags timeout; }
  set blocked6 { type ipv6_addr; flags timeout; }
  chain input {
    type filter hook input priority -5; policy accept;
    ip saddr @blocked4 drop
    ip6 saddr @blocked6 drop
  }
}
"""


def root_main(args):
    """What needs root (sudo mos-logins root ...): blocking, SSH, networks."""
    if os.geteuid() != 0:
        sys.exit("mos-logins root: run through sudo")
    cmd, rest = (args[0], args[1:]) if args else ("", [])

    def nft(*a, check=True):
        return subprocess.run(["nft", *a], capture_output=True, text=True, check=check)

    def table():
        if nft("list", "table", "inet", "mos-logins", check=False).returncode != 0:
            subprocess.run(["nft", "-f", "-"], input=NFT, text=True, check=True)

    def addr(text):
        a = ipaddress.ip_address(text.split("%")[0])
        return str(a), "blocked4" if a.version == 4 else "blocked6"

    def end_sessions():
        out = subprocess.run(["loginctl", "list-sessions", "--no-legend"], capture_output=True, text=True).stdout
        n = 0
        for line in out.splitlines():
            sid = line.split()[0] if line.split() else ""
            remote = subprocess.run(["loginctl", "show-session", sid, "-p", "Remote", "--value"],
                                    capture_output=True, text=True).stdout.strip()
            if sid and remote == "yes":
                subprocess.run(["loginctl", "terminate-session", sid])
                n += 1
        return n

    def stop_ssh():
        if subprocess.run(["systemctl", "is-active", "--quiet", "sshd.service"]).returncode == 0:
            os.makedirs(RUN, exist_ok=True)
            open(os.path.join(RUN, "ssh-was-on"), "w").close()
            subprocess.run(["systemctl", "stop", "sshd.service"])

    try:
        if cmd == "block":
            ip, s = addr(rest[0])
            minutes = int(rest[1]) if len(rest) > 1 else 60
            table()
            nft("add", "element", "inet", "mos-logins", s, f"{{ {ip} timeout {minutes}m }}")
            print(f"{ip} blocked for {minutes} minutes")
        elif cmd == "unblock":
            ip, s = addr(rest[0])
            nft("delete", "element", "inet", "mos-logins", s, f"{{ {ip} }}", check=False)
            print(f"{ip} unblocked")
        elif cmd == "blocked":
            for s in ("blocked4", "blocked6"):
                p = nft("-j", "list", "set", "inet", "mos-logins", s, check=False)
                if p.returncode == 0:
                    for item in json.loads(p.stdout)["nftables"]:
                        for e in item.get("set", {}).get("elem", []):
                            e = e.get("elem", e) if isinstance(e, dict) else e
                            ip = e.get("val") if isinstance(e, dict) else e
                            left = e.get("expires", "") if isinstance(e, dict) else ""
                            print(f"{ip}\t{left}")
        elif cmd == "end-sessions":
            print(f"{end_sessions()} remote session(s) ended")
        elif cmd == "stop-ssh":
            end_sessions()
            stop_ssh()
            print("SSH stopped (until you start it, or the next start)")
        elif cmd == "start-ssh":
            subprocess.run(["systemctl", "start", "sshd.service"], check=True)
            print("SSH started")
        elif cmd == "disconnect":
            end_sessions()
            stop_ssh()
            subprocess.run(["nmcli", "networking", "off"])
            subprocess.run(["rfkill", "block", "all"])
            print("Disconnected: remote sessions ended, SSH stopped, every network off")
        elif cmd == "reconnect":
            subprocess.run(["rfkill", "unblock", "all"])
            subprocess.run(["nmcli", "networking", "on"])
            flag = os.path.join(RUN, "ssh-was-on")
            if os.path.exists(flag):
                subprocess.run(["systemctl", "start", "sshd.service"])
                os.remove(flag)
            print("Reconnected")
        else:
            sys.exit(f"mos-logins root: unknown {cmd!r}")
    except (subprocess.CalledProcessError, ValueError, IndexError) as e:
        sys.exit(f"mos-logins: {e}")
    return 0


def blocked():
    ok, out = as_root("blocked")
    return [l.split("\t")[0] for l in out.splitlines() if l.strip()] if ok else []


def remote_now():
    """[{what, who, from}]: remote login sessions and SSH connections."""
    rows = []
    out = subprocess.run(["loginctl", "list-sessions", "--no-legend"], capture_output=True, text=True, env=ENV).stdout
    for line in out.splitlines():
        f = line.split()
        if not f:
            continue
        props = dict(l.split("=", 1) for l in subprocess.run(
            ["loginctl", "show-session", f[0], "-p", "Remote", "-p", "RemoteHost", "-p", "Name", "-p", "Service"],
            capture_output=True, text=True, env=ENV).stdout.splitlines() if "=" in l)
        if props.get("Remote") == "yes":
            rows.append({"what": f"session {f[0]} ({props.get('Service', '')})", "who": props.get("Name", ""),
                         "from": props.get("RemoteHost", "")})
    try:
        out = subprocess.run(["ss", "-tnH", "state", "established", "( sport = :22 )"],
                             capture_output=True, text=True, env=ENV).stdout
    except OSError:
        out = ""
    for line in out.splitlines():
        f = line.split()
        if len(f) >= 4:
            peer = f[-1].rsplit(":", 1)[0].strip("[]")
            if not any(r["from"] == peer for r in rows):
                rows.append({"what": "SSH connection", "who": "", "from": peer})
    return rows


# ---- notifications, without flooding ---------------------------------------------------
class Notifier:
    """At most one alert per topic (an address) per COOLDOWN; at most
    PER_HOUR of each kind (attacks, new logins, summaries: the kind is the
    topic before ":"), then one "see mos-logins" and quiet for that kind
    for an hour (so a flood of attacks can't hide a new login); a topic
    with an alert still on screen gets no second one."""
    COOLDOWN = 3600
    PER_HOUR = 3

    def __init__(self):
        self.last = {}  # topic -> when
        self.sent = collections.defaultdict(collections.deque)  # kind -> times
        self.open = set()
        self.muted_until = {}  # kind -> when
        self.lock = threading.Lock()

    def allow(self, topic):
        now = time.time()
        kind = topic.split(":", 1)[0]
        with self.lock:
            sent = self.sent[kind]
            while sent and now - sent[0] > 3600:
                sent.popleft()
            if topic in self.open or now - self.last.get(topic, 0) < self.COOLDOWN or now < self.muted_until.get(kind, 0):
                return False
            muted = len(sent) >= self.PER_HOUR
            if muted:
                self.muted_until[kind] = now + 3600
            else:
                self.last[topic] = now
                sent.append(now)
                self.open.add(topic)
        if muted:  # once, then quiet for an hour
            threading.Thread(target=self._show, daemon=True, args=(
                f"muted:{kind}", "Many login alerts", "More happened this hour: these alerts are paused for an "
                "hour. Open Logins (mos-logins) to see everything.", "normal", [("open", "Open Logins")])).start()
        return not muted

    def send(self, topic, title, body, urgency="normal", actions=(), on_action=None):
        if self.allow(topic):
            threading.Thread(target=self._show, args=(topic, title, body, urgency, actions, on_action),
                             daemon=True).start()

    def _show(self, topic, title, body, urgency, actions, on_action=None):
        cmd = ["notify-send", "-a", "Logins", "-i", "security-high", "-u", urgency]
        for name, label in actions:
            cmd.append(f"--action={name}={label}")
        cmd += ([] if actions else ["-t", "15000"]) + [title, body]
        try:
            chosen = subprocess.run(cmd, capture_output=True, text=True, timeout=3600).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            chosen = ""
        with self.lock:
            self.open.discard(topic)
        if chosen == "open":
            open_tui()
        elif chosen and on_action:
            on_action(chosen)


def open_tui():
    subprocess.Popen(["xfce4-terminal", "--title", "Logins", "--geometry", "110x30", "-x", SELF],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def when(t):
    return datetime.datetime.fromtimestamp(t).strftime("%a %H:%M")


def summary(events, state):
    """What a person coming back should know, or "" (scanners alone: nothing)."""
    lines = []
    oks = [e for e in events if e["kind"] == "ssh-ok"]
    new = [e for e in oks if not known(state, e["ip"], e["key"])]
    if new:
        lines.append(f"{len(new)} SSH login(s) from somewhere new: " +
                     ", ".join(sorted({f"{e['user']}@{e['ip']}" for e in new})[:3]))
    elif oks:
        lines.append(f"{len(oks)} SSH login(s) from known addresses")
    by_place = collections.Counter(PLACES.get(e["service"], e["service"]) for e in events if e["kind"] == "password-fail")
    for place, n in by_place.most_common():
        first = min(e["time"] for e in events if e["kind"] == "password-fail" and PLACES.get(e["service"], e["service"]) == place)
        lines.append(f"{n} wrong password(s) at {place} (from {when(first)})")
    disk = [e for e in events if e["kind"] == "disk-fail"]
    if disk:
        lines.append(f"The disk password was mistyped {len(disk)} time(s) at start-up ({when(disk[0]['time'])})")
    if not lines:
        return ""
    fails = sum(e["kind"] == "ssh-fail" for e in events)
    if fails:
        lines.append(f"Also {fails} failed SSH attempt(s): mos-logins lists them")
    return "\n".join(lines)


class Watcher:
    def __init__(self):
        self.state = load_state()
        self.notify = Notifier()
        self.fails = collections.defaultdict(collections.deque)  # ip -> failure times
        self.mine = my_users()
        self.locked_since = None
        self.during = []  # events while locked

    def act(self, choice, ip=""):
        if choice == "block" and ip:
            as_root("block", ip, "60")
        elif choice == "stop-ssh":
            as_root("stop-ssh")
        elif choice == "end":
            as_root("end-sessions")
        elif choice == "disconnect":
            disconnect()
        elif choice == "trust" and ip:
            trust(ip)
            self.state = load_state()

    def on_event(self, ev):
        if self.locked_since:
            self.during.append(ev)
        if not setting("login_alerts", True):
            return
        if ev["kind"] == "ssh-ok" and not known(self.state, ev["ip"], ev["key"]):
            if setting("auto_disconnect", False):
                disconnect()
                body = f"{ev['user']} logged in from {ev['ip']}. The computer was disconnected (auto_disconnect)."
                self.notify.send(f"ok:{ev['ip']}", "Unknown SSH login: disconnected", body, "critical",
                                 [("reconnect", "Reconnect"), ("open", "Open Logins")],
                                 lambda c: reconnect() if c == "reconnect" else None)
                return
            body = (f"{ev['user']} logged in from {ev['ip']}" + (f" with key {ev['key'][:20]}…" if ev["key"] else "") +
                    ": not an address or key seen before.")
            self.notify.send(f"ok:{ev['ip']}", "Unknown SSH login", body, "critical",
                             [("trust", "It's me"), ("end", "End remote sessions"), ("disconnect", "Disconnect")],
                             lambda c, ip=ev["ip"]: self.act(c, ip))
        elif ev["kind"] == "ssh-fail" and ev["ip"]:
            q = self.fails[ev["ip"]]
            q.append((ev["time"], ev["user"]))
            while q and ev["time"] - q[0][0] > 600:
                q.popleft()
            aimed = sum(u in self.mine for _, u in q)
            local = private(ev["ip"])
            if (local and len(q) >= 3) or aimed >= 5 or len(q) >= 20:
                why = "from your own network" if local else ("trying your user name" if aimed else "many times")
                body = f"{len(q)} failed SSH logins in 10 minutes from {ev['ip']}, {why}."
                self.notify.send(f"attack:{ev['ip']}", "SSH attack", body, "critical",
                                 [("block", "Block this address"), ("stop-ssh", "Stop SSH"), ("disconnect", "Disconnect")],
                                 lambda c, ip=ev["ip"]: self.act(c, ip))
        elif ev["kind"] == "disk-fail":
            pass  # reported in the summary at login (it happens before anyone is logged in)

    def screen_lock(self):
        """Follow the screensaver: a summary of what happened while locked."""
        if not shutil.which("dbus-monitor"):
            return
        p = subprocess.Popen(["dbus-monitor", "--session",
                              "type='signal',interface='org.xfce.ScreenSaver',member='ActiveChanged'"],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        expect = False
        for line in p.stdout:
            if "member=ActiveChanged" in line:
                expect = True
            elif expect and "boolean" in line:
                expect = False
                if "true" in line:
                    self.locked_since, self.during = time.time(), []
                elif self.locked_since:
                    text = summary(self.during, self.state)
                    self.locked_since, self.during = None, []
                    if text and setting("login_alerts", True):
                        self.notify.send(f"away:{int(time.time())}", "While you were away", text, "normal",
                                         [("open", "Open Logins")])

    def run(self):
        now = time.time()
        # Since last time (up to 30 days), and this start-up's disk passwords.
        since = max(self.state["seen"], now - 30 * 86400) if self.state["seen"] else now - 86400
        past = list(journal(since=since))
        past += [e for e in journal(boot=True) if e["kind"] == "disk-fail" and e["time"] < since]
        text = summary(past, self.state)
        if text and setting("login_alerts", True):
            self.notify.send("login", "Since you last logged in", text, "normal", [("open", "Open Logins")])
        threading.Thread(target=self.screen_lock, daemon=True).start()
        last_save = 0
        for ev in journal(follow=True):
            self.on_event(ev)
            if time.time() - last_save > 60:
                self.state = {**load_state(), "seen": time.time()}
                save_state(self.state)
                last_save = time.time()

    def stop(self):
        save_state({**load_state(), "seen": time.time()})


def demo():
    """A sample alert, as the watcher shows one, closed after a while
    (MECCANICOS_LOGINS_DEMO_SECONDS, 12); its buttons do nothing."""
    p = subprocess.Popen(["notify-send", "-p", "-a", "Logins", "-i", "security-high", "-u", "critical",
                          "--action=block=Block this address", "--action=stop-ssh=Stop SSH",
                          "--action=disconnect=Disconnect", "SSH attack (example)",
                          "14 failed SSH logins in 10 minutes from 192.168.1.66, from your own network."],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    nid = p.stdout.readline().strip()  # printed at once; then it waits for a click
    time.sleep(float(os.environ.get("MECCANICOS_LOGINS_DEMO_SECONDS", "12")))
    if nid.isdigit():  # urgent alerts stay until closed
        subprocess.run(["gdbus", "call", "--session", "--dest", "org.freedesktop.Notifications",
                        "--object-path", "/org/freedesktop/Notifications",
                        "--method", "org.freedesktop.Notifications.CloseNotification", nid],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    p.terminate()


# ---- full screen ----------------------------------------------------------------------------
NAMES = {"ssh-ok": "SSH login", "ssh-fail": "SSH attempt failed", "password-fail": "wrong password",
         "disk-fail": "wrong disk password"}


def history(days=7):
    evs = list(journal(since=time.time() - days * 86400, last=5000))
    evs.reverse()
    return evs


class App:
    def __init__(self, scr):
        self.scr = scr
        self.view = "now"  # history, blocked
        self.sel = {"now": 0, "history": 0, "blocked": 0}
        self.focus = 0
        self.msg, self.err = "", False
        self.state = load_state()
        self.load()

    def load(self):
        self.ssh, self.net = ssh_on(), network_on()
        self.rows_now = remote_now()
        self.rows_hist = history() if self.view == "history" else getattr(self, "rows_hist", [])
        self.rows_blocked = blocked() if self.view == "blocked" else getattr(self, "rows_blocked", [])

    def rows(self):
        return {"now": self.rows_now, "history": self.rows_hist, "blocked": self.rows_blocked}[self.view]

    def buttons(self):
        if self.view == "history":
            return [("Block address", "b", self.block), ("Trust", "t", self.trust),
                    ("Now", "n", lambda: self.go("now")), ("Quit", "q", None)]
        if self.view == "blocked":
            return [("Unblock", "u", self.unblock), ("Now", "n", lambda: self.go("now")), ("Quit", "q", None)]
        return [("History", "h", lambda: self.go("history")), ("Blocked", "b", lambda: self.go("blocked")),
                ("End remote sessions", "e", self.end),
                ("Stop SSH", "s", self.stop_ssh) if self.ssh else ("Start SSH", "s", self.start_ssh),
                ("Disconnect", "d", self.disconnect) if self.net else ("Reconnect", "c", self.reconnect),
                ("Quit", "q", None)]

    def go(self, view):
        self.view, self.focus = view, 0
        self.say("Reading the journal…" if view == "history" else "")
        self.draw()
        self.load()
        self.say("")

    def say(self, msg, err=False):
        self.msg, self.err = msg, err

    def done(self, ok, out):
        self.say(("✓ " if ok else "✗ ") + (out.splitlines()[-1] if out else ("done" if ok else "failed")), not ok)
        self.load()

    def chosen(self):
        rows = self.rows()
        return rows[self.sel[self.view]] if rows else None

    def block(self):
        e = self.chosen()
        if not e or not e.get("ip"):
            return self.say("Choose a line with an address.")
        self.done(*as_root("block", e["ip"], "60"))

    def trust(self):
        e = self.chosen()
        if not e or not (e.get("ip") or e.get("key")):
            return self.say("Choose a line with an address.")
        trust(e["key"] or e["ip"])
        self.say(f"✓ {e['key'] or e['ip']} trusted: no alerts for it.")

    def unblock(self):
        ip = self.chosen()
        if ip:
            self.done(*as_root("unblock", ip))

    def end(self):
        if ui.confirm(self.scr, "End every remote session (SSH)?", yes="End them"):
            self.done(*as_root("end-sessions"))

    def stop_ssh(self):
        if ui.confirm(self.scr, "Stop SSH? Remote sessions end; nobody can log in remotely\nuntil you start it again.",
                      yes="Stop SSH"):
            self.done(*as_root("stop-ssh"))

    def start_ssh(self):
        self.done(*as_root("start-ssh"))

    def disconnect(self):
        if ui.confirm(self.scr, "Disconnect? Remote sessions end, SSH stops, every network\n(Wi-Fi, cable, Bluetooth) "
                                "goes off and the screen locks.", yes="Disconnect"):
            self.done(*disconnect())

    def reconnect(self):
        self.done(*reconnect())

    def draw(self):
        s = self.scr
        s.erase()
        h, w = s.getmaxyx()
        if h < 12 or w < 60:
            ui.put(s, 0, 0, "Make the window larger.")
            s.refresh()
            return
        state = f"SSH {'on' if self.ssh else 'off'} · network {'on' if self.net else 'OFF'}"
        ui.bar(s, 0, {"now": "Logins › connected now", "history": "Logins › the last 7 days",
                      "blocked": "Logins › blocked addresses"}[self.view], state)
        y = 2
        rows = self.rows()
        if self.view == "now":
            head, empty = f"  {'What':<34}{'Who':<14}From", "Nobody is connected from another computer."
        elif self.view == "history":
            head, empty = f"  {'When':<16}{'What':<22}{'Who':<14}From", "Nothing in the last 7 days."
        else:
            head, empty = "  Address", "No address is blocked."
        ui.put(s, y, 0, head, ui.attr(ui.HEADING))
        ui.put(s, y + 1, 0, "─" * w, ui.attr(ui.BORDER))
        y += 2
        list_h = h - y - 5
        cur = self.sel[self.view] = min(self.sel[self.view], max(0, len(rows) - 1))
        top = max(0, cur - list_h + 1)
        if not rows:
            ui.put(s, y, 2, empty, ui.attr(ui.DIM))
        for i, r in enumerate(rows[top: top + list_h]):
            n = top + i
            if self.view == "now":
                line, a = f"  {r['what'][:33]:<34}{r['who'][:13]:<14}{r['from']}", ui.attr(ui.NORMAL)
            elif self.view == "history":
                what = NAMES.get(r["kind"], r["kind"])
                if r["kind"] == "password-fail":
                    what += f" ({PLACES.get(r['service'], r['service'])})"
                line = f"  {datetime.datetime.fromtimestamp(r['time']).strftime('%a %d %H:%M'):<16}{what[:21]:<22}{r['user'][:13]:<14}{r['ip']}"
                bad = r["kind"] != "ssh-ok" or not known(self.state, r["ip"], r["key"])
                a = ui.attr(ui.ERR if r["kind"] in ("password-fail", "disk-fail") or
                            (r["kind"] == "ssh-ok" and bad) else ui.DIM if r["kind"] == "ssh-fail" else ui.NORMAL)
            else:
                line, a = f"  {r}", ui.attr(ui.NORMAL)
            if n == cur:
                ui.row(s, y + i, 0, w, line, True)
            else:
                ui.put(s, y + i, 0, line, a)
        ui.put(s, h - 4, 0, "─" * w, ui.attr(ui.BORDER))
        ui.buttons(s, h - 3, 1, [(l, k) for l, k, _ in self.buttons()], self.focus)
        ui.message(s, h - 2, 1, ("✗ " if self.err and not self.msg.startswith("✗") else "") + self.msg)
        ui.keybar(s, h - 1, [("↑↓", "move"), ("←→", "button"), ("Enter", "press"), ("r", "reload"), ("q", "quit")])
        s.refresh()

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
                fn = self.buttons()[self.focus][2]
                if fn is None:
                    return
                fn()
            elif k == ui.ESC:
                if self.view == "now":
                    return
                self.go("now")
            elif k == "r":
                self.load()
                self.say("reloaded")
            elif isinstance(k, str):
                for i, (_, key, fn) in enumerate(self.buttons()):
                    if k.lower() == key:
                        self.focus = i
                        if fn is None:
                            return
                        fn()
                        break


# ---- command line ---------------------------------------------------------------------
def usage_error(problem):
    print(f"mos-logins: {problem} (mos-logins --help)", file=sys.stderr)
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
    if cmd == "root":
        return root_main(args)
    if cmd == "watch":
        w = Watcher()
        try:
            w.run()
        finally:
            w.stop()
        return 0
    if cmd == "demo":
        demo()
        return 0
    if cmd == "list":
        days = int(args[0]) if args and args[0].isdigit() else 7
        state = load_state()
        evs = list(journal(since=time.time() - days * 86400))
        if not evs:
            print(f"Nothing in the last {days} days.")
        for e in evs:
            what = NAMES[e["kind"]] + (f" ({PLACES.get(e['service'], e['service'])})" if e["service"] else "")
            mark = "" if e["kind"] != "ssh-ok" or known(state, e["ip"], e["key"]) else "  (new)"
            print(f"{datetime.datetime.fromtimestamp(e['time']):%Y-%m-%d %H:%M}  {what:<34} {e['user']:<12} {e['ip']}{mark}")
        return 0
    if cmd == "now":
        rows = remote_now()
        print(f"SSH {'on' if ssh_on() else 'off'}, network {'on' if network_on() else 'off'}.")
        if not rows:
            print("Nobody is connected from another computer.")
        for r in rows:
            print(f"{r['what']:<34} {r['who']:<12} {r['from']}")
        return 0
    if cmd == "trust":
        if len(args) != 1:
            usage_error("trust needs an IP or a key (SHA256:...)")
        trust(args[0])
        return 0
    if cmd in ("block", "unblock", "blocked", "disconnect", "reconnect"):
        if cmd in ("block", "unblock") and not args:
            usage_error(f"{cmd} needs an IP")
        if cmd in ("block", "unblock"):
            try:
                ipaddress.ip_address(args[0].split("%")[0])
            except ValueError:
                usage_error(f"not an IP address: {args[0]}")
        ok, out = disconnect() if cmd == "disconnect" else reconnect() if cmd == "reconnect" else as_root(cmd, *args)
        if out:
            print(out, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1
    usage_error(f"unknown command '{cmd}'")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
