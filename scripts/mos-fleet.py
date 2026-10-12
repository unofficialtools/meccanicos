#!/usr/bin/env python3
"""
mos-fleet - run an organization's fleet of MeccanicOS computers (EXPERIMENTAL)

On the fleet server (asks for sudo):
  mos-fleet server init --domain DOMAIN --organization NAME [--lan CIDR]...
                        [--meccanicos FLAKEREF]
                                   set it all up: Kanidm, Forgejo, Fleet, Tang,
                                   the cache, the fleet repository (safe to re-run)
  mos-fleet server status          services, and what each computer runs
  mos-fleet status [HOST]          the computers: built? reporting to Fleet?
  mos-fleet person add NAME "Full Name" [--group GROUP]...
                                   a person (prints their setup link)
  mos-fleet person password NAME   set their password for logging in to computers
  mos-fleet person reset NAME      a new setup link
  mos-fleet person remove NAME | person list
  mos-fleet group add NAME | group list
  mos-fleet member add|remove GROUP NAME
  mos-fleet kit                    print the admin kit (for `connect`)

On your own computer (as yourself):
  mos-fleet connect [USER@]SERVER  fetch the admin kit, clone the fleet repository
  mos-fleet admin-key              your recovery key pair; public key into admins.txt
  mos-fleet profile add NAME       profiles/NAME.nix, and the Kanidm group NAME
  mos-fleet prepare HOST --profile NAME --unlock tang|tpm-pin|fido2
                    [--disk-serial SERIAL] [--to DIR]
                                   the stick's corporate.config for a new computer
  mos-fleet add HOST [--from DIR]  after installing: the computer into the repository
  mos-fleet recover HOST           its disk recovery key (needs your admin key)
  mos-fleet upgrade [--testing]    the newest MeccanicOS for the whole fleet
  mos-fleet retire HOST            take a computer out of the fleet
  mos-fleet doctor                 check names, servers, the kit and the repository

Server commands typed on your own computer run on the server, over SSH.
The stick: `usb-vault stick` mounts the MeccanicOS stick's files (Ventoy or
data partition); bundles go in meccanicos/fleet/HOST there.
Guide: docs/fleet/ADMIN-GUIDE.md in the MeccanicOS repository.
"""

import argparse
import base64
import datetime
import getpass
import glob
import json
import os
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request

STATE = "/var/lib/meccanicos-fleet"  # on the server
SERVER_INFO = "/etc/meccanicos/fleet-server"  # written by fleet-server.nix
ETC_NIXOS = "/etc/nixos"
CONF = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "mos-fleet")
KIT = os.path.join(CONF, "kit.toml")
CA = os.path.join(CONF, "ca.crt")
ADMIN_KEY = os.path.join(CONF, "admin.key")
STICK = "/run/usb-vault/data"
NAME_RE = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")
PERSON_RE = re.compile(r"[a-z][a-z0-9_.-]{0,62}")
UNLOCK = ("tang", "tpm-pin", "fido2")
DEFAULT_MECCANICOS = "github:unofficialtools/meccanicos/latest"  # the latest release
KIT_BEGIN, KIT_END = "-----BEGIN MOS-FLEET KIT-----", "-----END MOS-FLEET KIT-----"


class Fail(Exception):
    pass


# ------------------------------------------------------------------ helpers --
def say(text=""):
    print(text, flush=True)


def step(text):
    print(f"\n\033[1m== {text}\033[0m", flush=True)


def run(cmd, check=True, capture=True, input=None, env=None, cwd=None):
    """Run a command. Returns its stdout (captured) or "" (passed through)."""
    r = subprocess.run(
        cmd,
        input=input,
        text=True,
        capture_output=capture,
        env=None if env is None else {**os.environ, **env},
        cwd=cwd,
    )
    if check and r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip() if capture else ""
        raise Fail(f"{shlex.join(cmd[:4])}{' …' if len(cmd) > 4 else ''} failed ({r.returncode})" + (f":\n{err[-1500:]}" if err else ""))
    return r.stdout if capture else ""


def toml_value(x):
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, int):
        return str(x)
    if isinstance(x, list):
        return "[" + ", ".join(toml_value(i) for i in x) + "]"
    if isinstance(x, str) and "\n" in x:
        return "'''\n" + x + "'''"
    return json.dumps(x, ensure_ascii=False)


def toml_dump(d, header=""):
    """A small TOML writer: top-level keys, then one level of tables."""
    lines = [header] if header else []
    lines += [f"{k} = {toml_value(v)}" for k, v in d.items() if not isinstance(v, dict) and v is not None]
    for k, v in d.items():
        if isinstance(v, dict):
            lines += ["", f"[{k}]"] + [f"{kk} = {toml_value(vv)}" for kk, vv in v.items() if vv is not None]
    return "\n".join(lines) + "\n"


def write_private(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    try:
        os.chmod(path, 0o600)
    except OSError:  # FAT/exFAT sticks
        pass


def password(n=20):
    """Random, and acceptable to Fleet's rules (letters, a digit, a symbol)."""
    return secrets.token_urlsafe(n) + "-7a"


def http(url, method="GET", data=None, token=None, cafile=None, ok=(200, 201, 204)):
    req = urllib.request.Request(url, method=method)
    if token:
        req.add_header("Authorization", f"token {token}")
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    import ssl

    ctx = ssl.create_default_context(cafile=cafile) if cafile else None
    try:
        with urllib.request.urlopen(req, body, timeout=20, context=ctx) as r:
            txt = r.read().decode()
            return r.status, (json.loads(txt) if txt.strip().startswith(("{", "[")) else txt)
    except urllib.error.HTTPError as e:
        if e.code in ok:
            return e.code, None
        return e.code, e.read().decode(errors="replace")
    except (urllib.error.URLError, OSError) as e:
        return 0, str(e)


def wait_for(what, check, seconds=300):
    say(f"   waiting for {what}…")
    end = time.time() + seconds
    while time.time() < end:
        if check():
            return
        time.sleep(3)
    raise Fail(f"{what} did not come up in {seconds // 60} minutes (journalctl -b -u … on the server says why).")


# ------------------------------------------------------------- server side --
def on_server():
    return os.path.exists(SERVER_INFO)


def server_info():
    info = {}
    for line in open(SERVER_INFO):
        if "=" in line:
            k, v = line.rstrip("\n").split("=", 1)
            info[k] = v
    return info


def load_state():
    try:
        return json.load(open(os.path.join(STATE, "server-state.json")))
    except (OSError, ValueError):
        return {}


def save_state(st):
    write_private(os.path.join(STATE, "server-state.json"), json.dumps(st, indent=2) + "\n")


def need_root(argv):
    if os.geteuid() != 0:
        os.execvp("sudo", ["sudo", "mos-fleet"] + argv)  # the wrapper: its PATH


def via_server(argv):
    """A server command typed on an admin computer: run it there."""
    kit = load_kit()
    target = kit.get("server")
    if not target:
        raise Fail("Not the fleet server, and no server in the kit (mos-fleet connect SERVER).")
    os.execvp("ssh", ["ssh", "-t", target, "sudo", "mos-fleet"] + [shlex.quote(a) for a in argv])


def kanidm_env(st):
    return {
        "KANIDM_NAME": "idm_admin",
        "KANIDM_PASSWORD": st["kanidm_idm_admin"],
        "KANIDM_CA_PATH": f"{STATE}/tls/ca.crt",
    }


def kanidm(st, *args, capture=True, check=True):
    env = kanidm_env(st)
    run(["kanidm", "login", "-D", "idm_admin"], env=env)
    return run(["kanidm", *args, "-D", "idm_admin"], env=env, capture=capture, check=check)


def fleetctl(*args, capture=True, check=True):
    return run(["fleetctl", *args, "--config", f"{STATE}/fleetctl.yml"], capture=capture, check=check)


def forgejo_cli(*args):
    return run(["fleet-forgejo", *args])


def rebuild():
    say("   rebuilding the system (the first time takes a while)…")
    run(["nixos-rebuild", "switch", "--flake", f"{ETC_NIXOS}#installed"], capture=False)


def cmd_server_init(a):
    if not os.path.isdir(ETC_NIXOS) or not os.path.exists(os.path.join(ETC_NIXOS, "flake.nix")):
        raise Fail("This is not an installed MeccanicOS (no /etc/nixos/flake.nix).")
    if not NAME_RE.fullmatch(a.domain.split(".")[0]) or "." not in a.domain:
        raise Fail(f"--domain {a.domain!r}: a domain like corp.example.com")
    st = load_state()

    step("1/8 The server's settings: /etc/nixos/fleet-server.toml")
    conf = {"domain": a.domain, "organization": a.organization, "lan": a.lan or ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]}
    path = os.path.join(ETC_NIXOS, "fleet-server.toml")
    text = toml_dump(conf, "# Written by mos-fleet server init. Read by fleet-server.nix.")
    if not os.path.exists(path) or open(path).read() != text:
        open(path, "w").write(text)
        rebuild()
    elif not on_server():
        rebuild()

    step("2/8 The organization's certificate authority")
    wait_for("the keys and certificates", lambda: os.path.exists(f"{STATE}/tls/ca.crt"), 120)
    ca = open(f"{STATE}/tls/ca.crt").read()
    etc_ca = os.path.join(ETC_NIXOS, "ca.crt")
    if not os.path.exists(etc_ca) or open(etc_ca).read() != ca:
        open(etc_ca, "w").write(ca)
        rebuild()  # now this machine trusts its own services
    d = a.domain

    def up(url):
        return http(url, cafile=f"{STATE}/tls/ca.crt")[0] == 200

    wait_for("Kanidm", lambda: up(f"https://idm.{d}/status"))
    wait_for("Forgejo", lambda: up("http://127.0.0.1:3000/api/v1/version"))
    wait_for("Fleet", lambda: up("http://127.0.0.1:8080/healthz"))
    wait_for("the cache", lambda: up("http://127.0.0.1:5000/nix-cache-info"))

    step("3/8 Kanidm: its administrators, the fleet-admins group")
    for acct, key in (("admin", "kanidm_admin"), ("idm_admin", "kanidm_idm_admin")):
        if key not in st:
            out = run(["runuser", "-u", "kanidm", "--", "kanidmd", "scripting", "recover-account", acct],
                      env={"KANIDM_CONFIG": "/etc/kanidm/server.toml"})
            res = json.loads(out.strip().splitlines()[-1])
            if res.get("status") != "ok":
                raise Fail(f"kanidmd recover-account {acct}: {out}")
            st[key] = res["output"]
            save_state(st)
    if "fleet-admins" not in kanidm(st, "group", "list", check=False):
        kanidm(st, "group", "create", "fleet-admins")
    kanidm(st, "group", "posix", "set", "fleet-admins", check=False)

    step("4/8 Forgejo: the fleet repository fleet/config")
    api = "http://127.0.0.1:3000/api/v1"
    if "forgejo_admin_token" not in st:
        st["forgejo_admin_password"] = password()
        forgejo_cli("admin", "user", "create", "--admin", "--username", "fleet-admin", "--email", f"fleet-admin@{d}",
                    "--password", st["forgejo_admin_password"], "--must-change-password=false")
        st["forgejo_admin_token"] = forgejo_cli("admin", "user", "generate-access-token", "--username", "fleet-admin",
                                                "--token-name", "mos-fleet", "--scopes", "all", "--raw").strip()
        save_state(st)
    tok = st["forgejo_admin_token"]
    if http(f"{api}/orgs/fleet", token=tok)[0] != 200:
        code, r = http(f"{api}/orgs", "POST", {"username": "fleet", "visibility": "private", "full_name": a.organization}, tok)
        if code not in (200, 201):
            raise Fail(f"Forgejo: creating the organization fleet: {code} {r}")
    if http(f"{api}/repos/fleet/config", token=tok)[0] != 200:
        code, r = http(f"{api}/orgs/fleet/repos", "POST",
                       {"name": "config", "private": True, "default_branch": "main",
                        "description": f"{a.organization}'s MeccanicOS computers"}, tok)
        if code not in (200, 201):
            raise Fail(f"Forgejo: creating the repository: {code} {r}")
    if "repo_token" not in st:
        forgejo_cli("admin", "user", "create", "--username", "fleet-reader", "--email", f"fleet-reader@{d}",
                    "--password", password(), "--must-change-password=false")
        code, r = http(f"{api}/repos/fleet/config/collaborators/fleet-reader", "PUT", {"permission": "read"}, tok)
        if code not in (200, 201, 204):
            raise Fail(f"Forgejo: giving fleet-reader read access: {code} {r}")
        st["repo_token"] = forgejo_cli("admin", "user", "generate-access-token", "--username", "fleet-reader",
                                       "--token-name", "computers", "--scopes", "read:repository", "--raw").strip()
        save_state(st)
    write_private(f"{STATE}/repo.token", st["repo_token"] + "\n")

    step("5/8 Fleet: the administrator and the enroll secret")
    if "fleet_password" not in st:
        st["fleet_password"] = password()
        save_state(st)
        run(["fleetctl", "config", "set", "--config", f"{STATE}/fleetctl.yml", "--address", f"https://fleet.{d}",
             "--rootca", f"{STATE}/tls/ca.crt", "--email", f"fleet-admin@{d}"])
        fleetctl("setup", "--email", f"fleet-admin@{d}", "--name", "Fleet admin", "--password", st["fleet_password"],
                 "--org-name", a.organization)
    if "enroll_secret" not in st:
        out = fleetctl("get", "enroll_secret", "--json", check=False)
        try:
            secret = json.loads(out)["spec"]["secrets"][0]["secret"]
        except (ValueError, KeyError, IndexError, TypeError):
            secret = secrets.token_urlsafe(32)
            spec = f"apiVersion: v1\nkind: enroll_secret\nspec:\n  secrets:\n  - secret: {secret}\n"
            path = f"{STATE}/enroll-secret.yml"
            write_private(path, spec)
            fleetctl("apply", "-f", path)
            os.remove(path)
        st["enroll_secret"] = secret
        save_state(st)

    step("6/8 Tang and the cache")
    thp = run(["tang-show-keys", "7654"]).split()
    if not thp:
        raise Fail("tang-show-keys printed no key (systemctl status tangd.socket).")
    st["tang_thumbprint"] = thp[0]
    st["cache_public_key"] = open(f"{STATE}/cache.pub").read().strip()
    save_state(st)

    step("7/8 The fleet repository's first files")
    head = http(f"{api}/repos/fleet/config/branches/main", token=tok)[0]
    if head != 200:
        seed_repository(a, st)
    else:
        say("   (already there)")

    step("8/8 The admin kit")
    kit = {
        "version": 1,
        "organization": a.organization,
        "domain": d,
        "repo_url": f"https://git.{d}/fleet/config.git",
        "repo_token": st["repo_token"],
        "push_token": st["forgejo_admin_token"],
        "cache_url": f"https://cache.{d}",
        "cache_public_key": st["cache_public_key"],
        "fleet_url": f"https://fleet.{d}",
        "enroll_secret": st["enroll_secret"],
        "kanidm_url": f"https://idm.{d}",
        "tang_url": f"http://tang.{d}:7654",
        "tang_thumbprint": st["tang_thumbprint"],
        "ca": ca,
    }
    write_private(f"{STATE}/kit.toml", toml_dump(kit, "# mos-fleet admin kit: SECRET (tokens, enroll secret)."))
    say(f"""
\033[1;32mThe fleet server is ready.\033[0m Keep these in the company password manager
(also in {STATE}/server-state.json, readable by root only):

  Kanidm   admin       {st['kanidm_admin']}
  Kanidm   idm_admin   {st['kanidm_idm_admin']}    (people and groups)
  Forgejo  fleet-admin {st['forgejo_admin_password']}    https://git.{d}
  Fleet    fleet-admin@{d}  {st['fleet_password']}    https://fleet.{d}

Next:
  • DNS: idm, git, cache, fleet, tang .{d} -> this server's address
  • yourself, as a fleet admin:  mos-fleet person add YOU "Your Name" --group fleet-admins
  • on your own computer:        mos-fleet connect {getpass.getuser() if os.geteuid() else os.environ.get('SUDO_USER', 'you')}@{socket.gethostname()}
                                 mos-fleet admin-key
                                 mos-fleet profile add office""")


def seed_repository(a, st):
    tmp = os.path.join(STATE, "seed")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.join(tmp, "profiles"))
    os.makedirs(os.path.join(tmp, "hosts"))
    files = {
        "flake.nix": FLAKE_NIX.replace("@ORG@", a.organization).replace("@MECCANICOS@", a.meccanicos),
        "common.nix": COMMON_NIX,
        "admins.txt": ADMINS_TXT,
        "README.md": README_MD.replace("@ORG@", a.organization),
        "hosts/.keep": "",
    }
    for name, text in files.items():
        open(os.path.join(tmp, name), "w").write(text)
    say("   pinning the MeccanicOS version (nix flake lock)…")
    run(["nix", "flake", "lock"], cwd=tmp)
    push_new_repo(tmp, "http://127.0.0.1:3000/fleet/config.git", st["forgejo_admin_token"])
    shutil.rmtree(tmp, ignore_errors=True)


def git_identity():
    return ["-c", "user.name=mos-fleet", "-c", f"user.email=mos-fleet@{socket.gethostname()}"]


def push_new_repo(path, url, token):
    run(["git", "init", "-q", "-b", "main"], cwd=path)
    run(["git", "add", "-A"], cwd=path)
    run(["git", *git_identity(), "commit", "-q", "-m", "The fleet repository"], cwd=path)
    run(["git", "-c", f"http.extraHeader=Authorization: token {token}", "push", "-q", url, "main"], cwd=path)


def cmd_kit(a):
    try:
        data = open(f"{STATE}/kit.toml", "rb").read()
    except OSError:
        raise Fail("No kit yet: run mos-fleet server init first.")
    say(KIT_BEGIN)
    say(base64.b64encode(data).decode())
    say(KIT_END)


def cmd_server_status(a):
    info = server_info()
    step("Services")
    for unit in ("meccanicos-fleet-secrets", "nginx", "kanidm", "forgejo", "harmonia", "mysql",
                 "redis-fleet", "fleet", "tangd.socket", "fleet-build.timer"):
        state = run(["systemctl", "is-active", unit], check=False).strip()
        say(f"   {'ok  ' if state == 'active' else 'FAIL'} {unit:28} {state}")
    say(f"\n   Fleet repository: https://git.{info.get('domain')}/fleet/config")
    cmd_status(a)


def build_status():
    out = {}
    for f in glob.glob("/var/lib/fleet-build/status/*"):
        first = open(f).readline().rstrip("\n").split("\t")
        out[os.path.basename(f)] = (first[0], first[1] if len(first) > 1 else "")
    return out


def cmd_status(a):
    builds = build_status()
    hosts = {}
    out = fleetctl("get", "hosts", "--json", check=False)
    for line in out.splitlines():
        try:
            spec = json.loads(line).get("spec", {})
        except ValueError:
            continue
        hosts[spec.get("hostname", "").split(".")[0]] = spec
    names = sorted(set(builds) | set(hosts))
    if a.host:
        names = [n for n in names if n == a.host]
    step("Computers")
    if not names:
        say("   (none yet)")
    for n in names:
        b = builds.get(n, ("not built", ""))
        h = hosts.get(n, {})
        fleet = f"{h.get('status', 'not in Fleet')}, seen {h.get('seen_time', '-')[:16]}" if h else "not in Fleet"
        say(f"   {n:20} build: {b[0]:18} Fleet: {fleet}  {h.get('os_version', '')}")
    if a.host and a.host in builds and builds[a.host][0].startswith("failed"):
        say("\n" + open(f"/var/lib/fleet-build/status/{a.host}").read())


def cmd_person(a):
    st = load_state()
    if a.action == "add":
        if not PERSON_RE.fullmatch(a.name):
            raise Fail("NAME: lowercase letters, digits and . _ -, starting with a letter.")
        kanidm(st, "person", "create", a.name, a.fullname)
        kanidm(st, "person", "posix", "set", a.name)
        for g in a.group or []:
            kanidm(st, "group", "add-members", g, a.name)
        say(f"{a.name} created{', in ' + ', '.join(a.group) if a.group else ''}.")
        say(kanidm(st, "person", "credential", "create-reset-token", a.name).strip())
        say(f"\nSend them that link: they set a password or passkey there. For logging in to a\n"
            f"computer they also need a Linux password:  mos-fleet person password {a.name}")
    elif a.action == "password":
        kanidm(st, "person", "posix", "set-password", a.name, capture=False)
    elif a.action == "reset":
        say(kanidm(st, "person", "credential", "create-reset-token", a.name).strip())
    elif a.action == "remove":
        kanidm(st, "person", "delete", a.name)
        say(f"{a.name} removed (computers forget them when their cache expires).")
    elif a.action == "list":
        say(kanidm(st, "person", "list").strip())


def cmd_group(a):
    st = load_state()
    if a.action == "add":
        if not NAME_RE.fullmatch(a.name):
            raise Fail("NAME: lowercase letters, digits and -.")
        kanidm(st, "group", "create", a.name)
        kanidm(st, "group", "posix", "set", a.name)
        say(f"Group {a.name} created.")
    else:
        say(kanidm(st, "group", "list").strip())


def cmd_member(a):
    st = load_state()
    kanidm(st, "group", "add-members" if a.action == "add" else "remove-members", a.group, a.name)
    say(f"{a.name} {'added to' if a.action == 'add' else 'removed from'} {a.group}.")


# -------------------------------------------------------------- admin side --
def load_kit():
    try:
        with open(KIT, "rb") as fh:
            return tomllib.load(fh)
    except OSError:
        raise Fail("No admin kit here yet: mos-fleet connect SERVER") from None


def repo_dir(kit=None):
    kit = kit or load_kit()
    return os.path.expanduser(kit.get("repo_dir", "~/fleet"))


def git(*args, cwd=None, capture=True):
    return run(["git", *git_identity(), *args], cwd=cwd or repo_dir(), capture=capture)


def pull():
    git("pull", "-q", "--ff-only")


def commit_push(message, paths=("-A",)):
    d = repo_dir()
    git("add", *paths, cwd=d)
    if not git("status", "--porcelain", cwd=d).strip():
        say("   (nothing changed)")
        return
    git("commit", "-q", "-m", message, cwd=d)
    git("push", "-q", cwd=d)
    say(f"   pushed: {message}")


def cmd_connect(a):
    say(f"Fetching the admin kit from {a.server} (ssh {a.server} sudo -n mos-fleet kit)…")
    r = subprocess.run(["ssh", a.server, "sudo", "-n", "mos-fleet", "kit"], capture_output=True, text=True)
    m = re.search(re.escape(KIT_BEGIN) + r"\s*(.*?)\s*" + re.escape(KIT_END), r.stdout, re.S)
    if not m:
        raise Fail(f"No kit from {a.server}:\n{(r.stderr or r.stdout).strip()[-800:]}\n"
                   "(Your account there needs sudo without a password, the MeccanicOS default.)")
    data = base64.b64decode(m.group(1)).decode()
    kit = tomllib.loads(data)
    kit["server"] = a.server
    kit["repo_dir"] = a.repo_dir or kit.get("repo_dir", "~/fleet")
    os.makedirs(CONF, mode=0o700, exist_ok=True)
    write_private(KIT, toml_dump(kit, "# mos-fleet admin kit: SECRET (tokens, enroll secret)."))
    write_private(CA, kit["ca"])
    say(f"   kit saved in {KIT}")
    d = repo_dir(kit)
    auth = f"Authorization: token {kit['push_token']}"
    if not os.path.isdir(os.path.join(d, ".git")):
        run(["git", "-c", f"http.extraHeader={auth}", "-c", f"http.sslCAInfo={CA}", "clone", "-q", kit["repo_url"], d])
    prefix = kit["repo_url"].split("/fleet/")[0] + "/"
    run(["git", "-C", d, "config", f"http.{prefix}.extraHeader", auth])
    run(["git", "-C", d, "config", f"http.{prefix}.sslCAInfo", CA])
    say(f"   the fleet repository: {d}  (plain git works there too)")
    if not os.path.exists(ADMIN_KEY):
        say("\nNext: mos-fleet admin-key   (your key for reading recovery keys)")


def admins_txt():
    return os.path.join(repo_dir(), "admins.txt")


def admin_publics():
    try:
        return [l.split()[0] for l in open(admins_txt()) if l.strip().startswith("age1")]
    except OSError:
        return []


def cmd_admin_key(a):
    load_kit()
    pull()
    if not os.path.exists(ADMIN_KEY):
        os.makedirs(CONF, mode=0o700, exist_ok=True)
        run(["age-keygen", "-o", ADMIN_KEY])
        os.chmod(ADMIN_KEY, 0o600)
        say(f"Your admin key: {ADMIN_KEY}")
        say("BACK IT UP NOW, offline (a printed copy in the safe): without it you cannot read recovery keys.")
    pub = run(["age-keygen", "-y", ADMIN_KEY]).strip()
    if pub in admin_publics():
        say(f"Your public key is already in admins.txt: {pub}")
        return
    with open(admins_txt(), "a") as fh:
        fh.write(f"# {getpass.getuser()}@{socket.gethostname()}, {datetime.date.today()}\n{pub}\n")
    commit_push(f"admins.txt: {getpass.getuser()}@{socket.gethostname()}", ["admins.txt"])
    say("Computers installed from now on get recovery keys you can read.")


def cmd_profile(a):
    if not NAME_RE.fullmatch(a.name):
        raise Fail("NAME: lowercase letters, digits and -.")
    pull()
    path = os.path.join(repo_dir(), "profiles", f"{a.name}.nix")
    if os.path.exists(path):
        say(f"profiles/{a.name}.nix is already there.")
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").write(PROFILE_NIX.replace("@NAME@", a.name))
        commit_push(f"Profile {a.name}", [path])
    say(f"The Kanidm group {a.name} (who may log in on these computers):")
    if on_server():
        cmd_group(argparse.Namespace(action="add", name=a.name))
    else:
        r = subprocess.run(["ssh", "-t", load_kit()["server"], "sudo", "mos-fleet", "group", "add", a.name])
        if r.returncode:
            say("   (could not create it; on the server: mos-fleet group add " + a.name + ")")
    say(f"Edit {path} for its software; mos-fleet member add {a.name} PERSON lets people log in.")


def stick_fleet_dir(to=None):
    if to:
        base = to
    else:
        r = subprocess.run(["usb-vault", "stick"], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.ismount(STICK):
            raise Fail("No MeccanicOS stick found (usb-vault stick). Plug it in, or give --to DIR.")
        base = STICK
    return os.path.join(base, "meccanicos", "fleet")


def cmd_prepare(a):
    kit = load_kit()
    if not NAME_RE.fullmatch(a.host):
        raise Fail("HOST: lowercase letters, digits and -.")
    pull()
    d = repo_dir(kit)
    if not os.path.exists(os.path.join(d, "profiles", f"{a.profile}.nix")):
        raise Fail(f"No profile {a.profile} (profiles/{a.profile}.nix): mos-fleet profile add {a.profile}")
    if os.path.isdir(os.path.join(d, "hosts", a.host)) and not a.force:
        raise Fail(f"{a.host} is already in the fleet (hosts/{a.host}). A new installation: --force")
    keys = admin_publics()
    if not keys:
        raise Fail("admins.txt has no admin key yet: mos-fleet admin-key")
    conf = {
        "version": 1,
        "organization": kit["organization"],
        "hostname": a.host,
        "profile": a.profile,
        "install": {"disk_serial": a.disk_serial} if a.disk_serial else None,
        "repo": {"url": kit["repo_url"], "branch": "main", "username": "fleet-reader"},
        "cache": {"url": kit["cache_url"], "public_key": kit["cache_public_key"]},
        "fleet": {"url": kit["fleet_url"]},
        "kanidm": {"url": kit["kanidm_url"]},
        "unlock": {"method": a.unlock, **({"tang_url": kit["tang_url"], "tang_thumbprint": kit["tang_thumbprint"]}
                                          if a.unlock == "tang" else {})},
    }
    out = os.path.join(stick_fleet_dir(a.to), a.host)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    head = f"# Written by mos-fleet prepare on {datetime.date.today()}. For mos-install (organization install)."
    write_private(os.path.join(out, "corporate.config"), toml_dump(conf, head))
    write_private(os.path.join(out, "ca.crt"), kit["ca"])
    write_private(os.path.join(out, "repo.token"), kit["repo_token"] + "\n")
    write_private(os.path.join(out, "fleet.secret"), kit["enroll_secret"] + "\n")
    shutil.copyfile(admins_txt(), os.path.join(out, "admins.txt"))
    run(["sync"], check=False)
    say(f"Ready: {out}")
    say(f"   {a.host}: profile {a.profile}, unlock {a.unlock}" + (f", disk {a.disk_serial}" if a.disk_serial else ", disk: chosen at install"))
    say("Boot the computer from this stick and choose Install: it offers the organization install.")
    say("The stick now holds the repository token and the enroll secret: keep it with you.")
    say(f"After the installation: mos-fleet add {a.host}")


def cmd_add(a):
    kit = load_kit()
    pull()
    # The installer's result/ folder: on the stick (meccanicos/fleet/HOST/result),
    # or wherever --from points (that folder itself, or a copy of the stick's).
    base = a.src or stick_fleet_dir()
    candidates = [base, os.path.join(base, "result"), os.path.join(base, a.host, "result"),
                  os.path.join(base, "meccanicos", "fleet", a.host, "result")]
    res = next((c for c in candidates if os.path.exists(os.path.join(c, "local.nix"))), candidates[2])
    need = ("hardware-configuration.nix", "local.nix", "fleet.toml", "ca.crt", "recovery.age")
    missing = [f for f in need if not os.path.exists(os.path.join(res, f))]
    if missing:
        raise Fail(f"Not in {res}: {', '.join(missing)} (was the installation finished?)")
    dst = os.path.join(repo_dir(kit), "hosts", a.host)
    os.makedirs(dst, exist_ok=True)
    for f in need:
        shutil.copyfile(os.path.join(res, f), os.path.join(dst, f))
    git("add", dst)  # a flake only sees files git knows
    say("   checking that it builds (evaluating)…")
    run(["nix", "eval", "--raw", f"{repo_dir(kit)}#nixosConfigurations.{a.host}.config.system.build.toplevel.drvPath"],
        cwd=repo_dir(kit))
    with open(os.path.join(dst, "fleet.toml"), "rb") as fh:
        profile = tomllib.load(fh).get("profile", "?")
    commit_push(f"Add {a.host} ({profile})", [dst])
    if os.path.basename(res) == "result" and res.startswith(STICK):
        shutil.rmtree(os.path.dirname(res), ignore_errors=True)
        say("   its folder is removed from the stick")
    say(f"The server builds it within minutes; then {a.host} takes its configuration (mos-fleet status {a.host}).")


def cmd_recover(a):
    pull()
    d = repo_dir()
    for where in ("hosts", "retired"):
        f = os.path.join(d, where, a.host, "recovery.age")
        if os.path.exists(f):
            break
    else:
        raise Fail(f"No recovery key for {a.host} in hosts/ or retired/.")
    if not os.path.exists(ADMIN_KEY):
        raise Fail(f"No admin key at {ADMIN_KEY} (restore your backup there).")
    key = run(["age", "-d", "-i", ADMIN_KEY, f]).strip()
    say(f"Recovery key for {a.host} (type it at the disk prompt):\n\n    {key}\n")


def cmd_upgrade(a):
    d = repo_dir()
    pull()
    if a.testing:
        git("checkout", "-q", "-B", "testing", "origin/main", cwd=d)
    try:
        run(["nix", "flake", "update", "meccanicos"], cwd=d, capture=False)
        say("   checking that every computer still evaluates…")
        run(["nix", "eval", "--json", ".#nixosConfigurations", "--apply",
             "cs: builtins.mapAttrs (_: c: c.config.system.build.toplevel.drvPath) cs"], cwd=d)
        git("add", "flake.lock", cwd=d)
        if not git("status", "--porcelain", cwd=d).strip():
            say("Already the newest MeccanicOS.")
            return
        git("commit", "-q", "-m", "Newest MeccanicOS", cwd=d)
        if a.testing:
            git("push", "-q", "-f", "origin", "testing", cwd=d)
            say("Pushed to the testing branch: computers whose fleet.toml says branch = \"testing\" take it.\n"
                "When they are fine: mos-fleet upgrade (for everyone).")
        else:
            git("push", "-q", cwd=d)
            say("Pushed: every computer takes it within minutes (kernel changes: at the next restart).")
    finally:
        if a.testing:
            git("checkout", "-q", "main", cwd=d)


def cmd_retire(a):
    pull()
    d = repo_dir()
    src = os.path.join(d, "hosts", a.host)
    if not os.path.isdir(src):
        raise Fail(f"No {a.host} in hosts/.")
    os.makedirs(os.path.join(d, "retired"), exist_ok=True)
    git("mv", src, os.path.join(d, "retired", a.host), cwd=d)
    commit_push(f"Retire {a.host}")
    say(f"{a.host} no longer gets updates. Its recovery key stays in retired/{a.host} until its\n"
        f"disk is wiped. Delete it in Fleet too: https://fleet.{load_kit()['domain']} > Hosts.")


def cmd_doctor(a):
    kit = load_kit()
    ok = True

    def check(what, good, hint=""):
        nonlocal ok
        ok &= good
        say(f"   {'ok  ' if good else 'FAIL'} {what}" + ("" if good or not hint else f"   ({hint})"))

    step("Names (DNS)")
    for n in ("idm", "git", "cache", "fleet", "tang"):
        host = f"{n}.{kit['domain']}"
        try:
            check(f"{host} -> {socket.gethostbyname(host)}", True)
        except OSError:
            check(host, False, "ask whoever runs the company DNS")
    step("Servers")
    for name, url in (("Kanidm", kit["kanidm_url"] + "/status"), ("Forgejo", kit["repo_url"].split("/fleet/")[0] + "/api/v1/version"),
                      ("cache", kit["cache_url"] + "/nix-cache-info"), ("Fleet", kit["fleet_url"] + "/healthz"),
                      ("Tang", kit["tang_url"] + "/adv")):
        code, _ = http(url, cafile=CA)
        check(f"{name:8} {url}", code == 200, f"HTTP {code}" if code else "unreachable")
    step("You")
    check(f"fleet repository at {repo_dir(kit)}", os.path.isdir(os.path.join(repo_dir(kit), ".git")), "mos-fleet connect")
    has = os.path.exists(ADMIN_KEY)
    check(f"admin key {ADMIN_KEY}", has, "mos-fleet admin-key")
    if has:
        pub = run(["age-keygen", "-y", ADMIN_KEY]).strip()
        check("your public key is in admins.txt", pub in admin_publics(), "mos-fleet admin-key")
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", kit.get("server", "?"), "sudo", "-n", "true"], capture_output=True)
    check(f"ssh {kit.get('server')} with sudo", r.returncode == 0, "SSH key and passwordless sudo on the server")
    if not ok:
        raise Fail("Some checks failed.")


# ---------------------------------------------------------- repository files --
FLAKE_NIX = """# @ORG@'s MeccanicOS computers (managed with mos-fleet).
#
#   hosts/<name>/   one folder per computer: what its installer wrote
#                   (local.nix, hardware-configuration.nix, fleet.toml naming its
#                   profile, ca.crt) and its disk recovery key, encrypted for the
#                   admins (recovery.age)
#   profiles/       one file per kind of computer (software, settings)
#   common.nix      every computer
#   admins.txt      the admins' age public keys (recovery keys)
#
# Every computer pulls this repository (comin) and switches to its own
# configuration; the fleet server builds them all first, for its cache.
# flake.lock pins the MeccanicOS version: mos-fleet upgrade.
{
  description = "@ORG@ MeccanicOS fleet";
  inputs.meccanicos.url = "@MECCANICOS@";

  outputs =
    { meccanicos, ... }:
    let
      lib = meccanicos.inputs.nixpkgs.lib;
      hosts = lib.attrNames (lib.filterAttrs (_: t: t == "directory") (builtins.readDir ./hosts));
      profileOf = name: (builtins.fromTOML (builtins.readFile (./hosts + "/${name}/fleet.toml"))).profile;
      machine =
        name:
        meccanicos.lib.mkInstalled {
          root = ./hosts + "/${name}";
          modules = [
            ./common.nix
            (./profiles + "/${profileOf name}.nix")
          ];
        };
    in
    {
      nixosConfigurations = lib.genAttrs hosts machine;
    };
}
"""

COMMON_NIX = """# Every computer of the fleet. (fleet-admins may log in everywhere, with
# sudo, and each profile's group on its computers: built into MeccanicOS's
# managed mode.)
{ pkgs, ... }:
{
  # environment.systemPackages = [ pkgs.htop ];
  # meccanicos.managed.fleetScripts = true;   # let Fleet run scripts (as root)
}
"""

PROFILE_NIX = """# Profile @NAME@: the computers whose fleet.toml says profile = "@NAME@".
# Who may log in: the Kanidm group @NAME@ (mos-fleet member add @NAME@ PERSON),
# and fleet-admins.
{ pkgs, ... }:
{
  environment.systemPackages = with pkgs; [
    # libreoffice
  ];
}
"""

ADMINS_TXT = """# The admins' age public keys, one per line (mos-fleet admin-key).
# Each computer's disk recovery key is encrypted for all of them when it is
# installed (hosts/<name>/recovery.age).
"""

README_MD = """# @ORG@ fleet

MeccanicOS computers managed with `mos-fleet` (experimental). Change a file,
commit, push: the fleet server builds it and the computers take it within
minutes. See `flake.nix` for the layout.
"""


# -------------------------------------------------------------------- main --
SERVER_COMMANDS = {"server", "status", "person", "group", "member", "kit"}


def main(argv):
    p = argparse.ArgumentParser(prog="mos-fleet", add_help=False)
    p.add_argument("-h", "--help", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("server")
    ssub = s.add_subparsers(dest="action", required=True)
    i = ssub.add_parser("init")
    i.add_argument("--domain", required=True)
    i.add_argument("--organization", required=True)
    i.add_argument("--lan", action="append")
    i.add_argument("--meccanicos", default=DEFAULT_MECCANICOS)
    ssub.add_parser("status").add_argument("host", nargs="?")
    sub.add_parser("status").add_argument("host", nargs="?")
    sub.add_parser("kit")
    pe = sub.add_parser("person")
    psub = pe.add_subparsers(dest="action", required=True)
    x = psub.add_parser("add")
    x.add_argument("name")
    x.add_argument("fullname")
    x.add_argument("--group", action="append")
    for act in ("password", "reset", "remove"):
        psub.add_parser(act).add_argument("name")
    psub.add_parser("list")
    g = sub.add_parser("group")
    gsub = g.add_subparsers(dest="action", required=True)
    gsub.add_parser("add").add_argument("name")
    gsub.add_parser("list")
    m = sub.add_parser("member")
    m.add_argument("action", choices=("add", "remove"))
    m.add_argument("group")
    m.add_argument("name")
    c = sub.add_parser("connect")
    c.add_argument("server")
    c.add_argument("--repo-dir")
    sub.add_parser("admin-key")
    pr = sub.add_parser("profile")
    pr.add_argument("action", choices=("add",))
    pr.add_argument("name")
    pp = sub.add_parser("prepare")
    pp.add_argument("host")
    pp.add_argument("--profile", required=True)
    pp.add_argument("--unlock", required=True, choices=UNLOCK)
    pp.add_argument("--disk-serial")
    pp.add_argument("--to")
    pp.add_argument("--force", action="store_true")
    ad = sub.add_parser("add")
    ad.add_argument("host")
    ad.add_argument("--from", dest="src")
    sub.add_parser("recover").add_argument("host")
    sub.add_parser("upgrade").add_argument("--testing", action="store_true")
    sub.add_parser("retire").add_argument("host")
    sub.add_parser("doctor")

    a = p.parse_args(argv)
    if a.help or not a.cmd:
        print(__doc__.strip())
        return 0
    if a.cmd in SERVER_COMMANDS:
        if a.cmd == "server" and a.action == "init":
            need_root(argv)
        elif not on_server():
            via_server(argv)
        else:
            need_root(argv)
    elif os.geteuid() == 0:
        raise Fail("Run this as yourself, not root: it uses your own kit and admin key.")
    handler = {
        "kit": cmd_kit,
        "status": cmd_status,
        "person": cmd_person,
        "group": cmd_group,
        "member": cmd_member,
        "connect": cmd_connect,
        "admin-key": cmd_admin_key,
        "profile": cmd_profile,
        "prepare": cmd_prepare,
        "add": cmd_add,
        "recover": cmd_recover,
        "upgrade": cmd_upgrade,
        "retire": cmd_retire,
        "doctor": cmd_doctor,
    }
    if a.cmd == "server":
        {"init": cmd_server_init, "status": cmd_server_status}[a.action](a)
    else:
        handler[a.cmd](a)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Fail as e:
        print(f"\033[1;31mmos-fleet:\033[0m {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
