"""mos-fleet server …: at the fleet server's own console (asks for sudo).

    server init [--lan CIDR]… [--admin-key FILE|LINE]
                         turn this MeccanicOS into the fleet server (safe to re-run)
    server admin-key FILE|LINE
                         let this SSH key act as an admin for a day (the first
                         admin, or one locked out): it may push the repository
    server status        the services, the repository, the computers
    server backup DIR    the repository, both databases, the keys

The databases belong to the account fleet: root never opens them (SQLite
would leave files root owns); it asks `mos-fleet-server` as fleet instead.
"""

import json
import os
import pwd
import shutil
import subprocess
import time

from . import settings
from .common import Fail, run, say, toml_dump, write_atomic
from .repo import Invalid, fingerprint, ssh_key

ETC_NIXOS = "/etc/nixos"
CONF = os.path.join(ETC_NIXOS, "fleet-server.toml")
MARK = "/etc/meccanicos/fleet-server"
CFG = settings.get("server")
STATE = os.environ.get("MOS_FLEET_STATE") or CFG["state"]
HOST_KEY = "/etc/ssh/ssh_host_ed25519_key.pub"


def as_fleet(*args, capture=True, check=True):
    return run(["runuser", "-u", "fleet", "--", "mos-fleet-server", *args], capture=capture, check=check)


def rebuild():
    say("   rebuilding the system (the first time downloads what it needs)…")
    run(["nixos-rebuild", "switch", "--flake", f"{ETC_NIXOS}#installed"], capture=False)


def read_key(x):
    p = os.path.expanduser(x)
    if os.path.isfile(p):
        x = open(p).read().strip()
    try:
        return ssh_key(x)
    except Invalid as e:
        raise Fail(f"Not an SSH public key ({e}).") from None


def add_bootstrap(key):
    path = os.path.join(STATE, "bootstrap.json")
    try:
        data = json.load(open(path))
    except (OSError, ValueError):
        data = []
    t = time.time()
    data = [e for e in data if e.get("expires", 0) > t and e.get("key") != key]
    hours = CFG["console_key_hours"]
    data.append({"key": key, "added": int(t), "expires": int(t + hours * 3600)})
    write_atomic(path, json.dumps(data, indent=1) + "\n", mode=0o600)
    pw = pwd.getpwnam("fleet")
    os.chown(path, pw.pw_uid, pw.pw_gid)
    say(f"   admin key {fingerprint(key)}: valid for {hours} hours, for the repository's first push (or a fix)")


def tang_thumbprint():
    r = subprocess.run(["tang-show-keys", str(CFG["tang_port"])], capture_output=True, text=True)
    return (r.stdout.split() or ["?"])[0] if r.returncode == 0 else "?"


def cmd_init(a):
    if not os.path.isfile(os.path.join(ETC_NIXOS, "flake.nix")):
        raise Fail("This is not an installed MeccanicOS (no /etc/nixos/flake.nix).")
    key = read_key(a.admin_key) if a.admin_key else None
    lan = a.lan or CFG["lan"]
    text = toml_dump({"lan": lan}, "# Written by mos-fleet server init. Read by fleet-server.nix.")
    say("== 1/3 The fleet server's settings: /etc/nixos/fleet-server.toml")
    if not os.path.exists(CONF) or open(CONF).read() != text or not os.path.exists(MARK):
        with open(CONF, "w") as fh:
            fh.write(text)
        rebuild()
    else:
        say("   (already there)")
    say("== 2/3 The repository, the databases")
    run(["systemctl", "restart", "mos-fleet-setup.service"])
    if key:
        add_bootstrap(key)
    say("== 3/3 Done")
    fp = fingerprint(ssh_key(open(HOST_KEY).read()))
    say(f"""
\033[1;32mThe fleet server is ready.\033[0m Note these two, for the admins' computers:

  this server's SSH key    {fp}
  Tang (disk unlocking)    {tang_thumbprint()}   (already put in fleet.toml by mos-fleet init)

Next, on your own computer (its SSH key given to --admin-key above):

  mos-fleet init --server {os.uname().nodename} --fingerprint {fp} \\
                 --organization "Your Organization" --admin YOU --full-name "Your Name"

DNS: the computers reach this server by the name given to --server.""")


def cmd_admin_key(a):
    add_bootstrap(read_key(a.key))
    as_fleet("refresh", check=False)


def cmd_status(a):
    say("== Services")
    for unit in ("sshd.service", "mos-fleet-setup.service", "mos-fleet-build.path", "mos-fleet-build.timer",
                 "mos-fleet-prune.timer", "tangd.socket"):
        st = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True).stdout.strip()
        say(f"   {'ok  ' if st == 'active' else 'FAIL'} {unit:28} {st}")
    say(as_fleet("status", check=False).rstrip())


def cmd_backup(a):
    dest = os.path.abspath(a.dir)
    os.makedirs(dest, mode=0o700, exist_ok=True)
    os.chmod(dest, 0o700)
    tmp = os.path.join(STATE, "backup.tmp")
    as_fleet("backup", tmp)
    for f in os.listdir(tmp):
        shutil.move(os.path.join(tmp, f), os.path.join(dest, f))
    os.rmdir(tmp)
    for src, name in (("/var/lib/tang", "tang"), ("/etc/ssh", "ssh-host-keys")):
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dest, name), dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("moduli", "ssh_config", "sshd_config", "*.d"))
    for f in ("fleet-server.toml",):
        if os.path.exists(os.path.join(ETC_NIXOS, f)):
            shutil.copy(os.path.join(ETC_NIXOS, f), dest)
    say(f"Backed up to {dest}: keep it offline. It holds password hashes and the server's keys.")


def dispatch(a):
    {"init": cmd_init, "admin-key": cmd_admin_key, "status": cmd_status, "backup": cmd_backup}[a.action](a)


def add_parsers(sub):
    s = sub.add_parser("server").add_subparsers(dest="action", required=True)
    x = s.add_parser("init")
    x.add_argument("--lan", action="append", help="the office network: who may reach Tang (repeat)")
    x.add_argument("--admin-key", help="the first admin's SSH public key (a file, or the line)")
    s.add_parser("admin-key").add_argument("key")
    s.add_parser("status")
    s.add_parser("backup").add_argument("dir")
