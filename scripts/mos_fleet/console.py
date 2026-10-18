"""mos-fleet server …: at the fleet server's own console (asks for sudo).

    server init [--lan CIDR]… [--admin-key FILE|LINE]
                         turn this MeccanicOS into the fleet server (safe to re-run)
    server admin-key FILE|LINE
                         let this SSH key act as an admin for a day (the first
                         admin, or one locked out): it may push the repository
    server status        the services, the repository, the computers
    server backup DIR    the repository, both databases, the keys
    server restore DIR [--yes]
                         put such a backup back (on a server after `server init`)

The databases belong to the account fleet: root never opens them (SQLite
would leave files root owns); it asks `mos-fleet-server` as fleet instead.
"""

import glob
import json
import os
import pwd
import shutil
import subprocess
import time
import tomllib

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


SERVICES = ["mos-fleet-build.path", "mos-fleet-build.timer", "mos-fleet-build.service", "mos-fleet-prune.timer"]


def cmd_restore(a):
    """A backup back in place: the repository (from its bundle), both databases,
    the server's SSH keys (so the computers, which pinned them, still trust it),
    Tang's keys (so disks still unlock) and fleet-server.toml. What was there
    is kept aside."""
    src = os.path.abspath(a.dir)
    for f in ("state.db", "secrets.db", "fleet.bundle"):
        if not os.path.isfile(os.path.join(src, f)):
            raise Fail(f"{src}: no {f} (a folder made by mos-fleet server backup)")
    aside = f"{STATE}.before-restore-{time.strftime('%Y%m%d-%H%M%S')}"
    say(f"This replaces the fleet server's repository, databases and keys with the backup in {src};\n"
        f"what is there now is moved to {aside}.")
    if not a.yes and input("Restore? [y/N] ").strip().lower() not in ("y", "yes"):
        raise Fail("Nothing changed.")
    conf = os.path.join(src, "fleet-server.toml")
    if os.path.isfile(conf) and (not os.path.isfile(CONF) or open(conf).read() != open(CONF).read()):
        say("== The server's settings (fleet-server.toml)")
        shutil.copy(conf, CONF)
        rebuild()
    fleet = pwd.getpwnam("fleet")
    say("== Stopping the fleet's services and connections")
    run(["systemctl", "stop", "sshd.service", *SERVICES], check=False)
    try:
        run(["pkill", "-KILL", "-u", "fleet"], check=False)  # agents' and admins' sessions: they reconnect
        time.sleep(1)
        say(f"== The repository and the databases ({STATE})")
        mode = os.stat(STATE).st_mode & 0o777 if os.path.isdir(STATE) else 0o700
        if os.path.isdir(STATE):
            os.rename(STATE, aside)
        os.mkdir(STATE, mode)
        os.chown(STATE, fleet.pw_uid, fleet.pw_gid)
        for f in ("state.db", "secrets.db", "fleet.bundle"):
            dst = os.path.join(STATE, f)
            shutil.copyfile(os.path.join(src, f), dst)
            os.chown(dst, fleet.pw_uid, fleet.pw_gid)
            os.chmod(dst, 0o600)
        git = ["runuser", "-u", "fleet", "--", "git", "--git-dir", os.path.join(STATE, "fleet.git")]
        run(["runuser", "-u", "fleet", "--", "git", "init", "-q", "--bare", "-b", "main",
             os.path.join(STATE, "fleet.git")])
        run([*git, "fetch", "-q", os.path.join(STATE, "fleet.bundle"), "refs/*:refs/*"])
        os.remove(os.path.join(STATE, "fleet.bundle"))
        say("== The server's SSH keys")
        for f in glob.glob(os.path.join(src, "ssh-host-keys", "ssh_host_*")):
            dst = os.path.join("/etc/ssh", os.path.basename(f))
            shutil.copyfile(f, dst)
            os.chown(dst, 0, 0)
            os.chmod(dst, 0o644 if f.endswith(".pub") else 0o600)
        tang = os.path.realpath("/var/lib/tang")
        keys = glob.glob(os.path.join(src, "tang", "*.jwk"))
        if keys and os.path.isdir(tang):
            say("== Tang's keys")
            # Owned as the ones they replace: tangd runs as its own user.
            old = glob.glob(os.path.join(tang, "*.jwk"))
            st = os.stat(old[0] if old else tang)
            for f in old:
                os.remove(f)
            for f in keys:
                dst = os.path.join(tang, os.path.basename(f))
                shutil.copyfile(f, dst)
                os.chown(dst, st.st_uid, st.st_gid)
                os.chmod(dst, st.st_mode & 0o777 if old else 0o400)
        elif keys:
            say(f"   ! Tang's keys not restored ({tang} doesn't exist yet): copy {src}/tang/*.jwk there")
    finally:
        say("== Starting the services again")
        run(["systemctl", "start", "sshd.service"], check=False)
        run(["systemctl", "restart", "mos-fleet-setup.service"], check=False)
        run(["systemctl", "start", *SERVICES[:2], SERVICES[3]], check=False)
    # Does the restored repository still name this server's keys? Computers trust only those.
    fp = fingerprint(ssh_key(open(HOST_KEY).read()))
    try:
        with open(os.path.join(STATE, "main", "fleet.toml"), "rb") as fh:
            f = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        f = {}
    problems = []
    if f.get("server_host_key") and fingerprint(ssh_key(f["server_host_key"])) != fp:
        problems.append(f"this server's SSH key ({fp}) is not the one fleet.toml names: computers won't connect")
    want = (f.get("tang") or {}).get("thumbprint")
    if want and want != tang_thumbprint():
        problems.append("Tang's key is not the one fleet.toml names: disks won't unlock by themselves")
    say(as_fleet("status", check=False).rstrip())
    for p in problems:
        say(f"\033[1;31m!\033[0m {p}")
    say(f"""
Restored from {src}. Next:
  - computers reconnect by themselves within a few minutes (mos-fleet status, from an admin's computer);
  - systems not in this server's store are built again (mos-fleet builds);
  - each database was copied consistently, but not at the same instant as the other and the
    repository: a push or password change made during the backup may be missing; push again
    from an admin's ~/fleet (every admin has a full copy) and set such a password again.
What was here before: {aside}.""")
    if problems:
        raise Fail("restored, but see the problems above")


def dispatch(a):
    {"init": cmd_init, "admin-key": cmd_admin_key, "status": cmd_status, "backup": cmd_backup,
     "restore": cmd_restore}[a.action](a)


def add_parsers(sub):
    s = sub.add_parser("server").add_subparsers(dest="action", required=True)
    x = s.add_parser("init")
    x.add_argument("--lan", action="append", help="the office network: who may reach Tang (repeat)")
    x.add_argument("--admin-key", help="the first admin's SSH public key (a file, or the line)")
    s.add_parser("admin-key").add_argument("key")
    s.add_parser("status")
    s.add_parser("backup").add_argument("dir")
    x = s.add_parser("restore")
    x.add_argument("dir")
    x.add_argument("--yes", action="store_true", help="don't ask")
