"""The fleet repository: the source of truth for computers, profiles, people
and groups. Reading it and checking it, without Nix (`validate` adds an
evaluation of every computer on top).

    fleet.toml                  organization, server, check-in and log settings
    groups.toml                 [group] gid, profiles (or "*"), sudo
    people/NAME.toml            name, uid, groups, ssh_keys, age_recipient, disabled
    profiles/NAME.nix           a kind of computer
    hosts/NAME/host.toml        profile, branch, unlock, host_key, disk_serial
    hosts/NAME/*.nix            hardware-configuration.nix, local.nix (optional)
    common.nix, flake.nix, flake.lock

The same rules run on an admin's computer (mos-fleet validate, before every
commit), in the server's pre-receive hook (nothing invalid gets in), and
when the server reads the repository (whose keys may log in).
"""

import base64
import os
import re
import struct
import tomllib

HOST_RE = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")
PERSON_RE = re.compile(r"[a-z_][a-z0-9_-]{0,31}")
GROUP_RE = PERSON_RE
PROFILE_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
BRANCH_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,62}")
SERVER_RE = re.compile(r"[A-Za-z0-9]([A-Za-z0-9.-]{0,252})(:[0-9]{1,5})?")
AGE_RE = re.compile(r"age1[02-9ac-hj-np-z]{58,}")
THUMBPRINT_RE = re.compile(r"[A-Za-z0-9_-]{20,100}")
UNIT_RE = re.compile(r"[A-Za-z0-9@._:-]{1,128}")
UNLOCK = ("tang", "tpm-pin", "fido2", "password")
ADMINS = "fleet-admins"
HOST_FILES = ("hardware-configuration.nix", "local.nix", "meccanicos.toml")

# Names a person can't have: NixOS's own accounts and ours.
RESERVED = {
    "root", "fleet", "nobody", "daemon", "bin", "sys", "sshd", "messagebus", "polkituser",
    "nscd", "dhcpcd", "avahi", "rtkit", "geoclue", "colord", "lightdm", "pulse", "pipewire",
    "nm-openvpn", "nm-iodine", "tss", "cups", "saned", "tang", "users", "wheel", "live",
}

KEY_TYPES = {
    "ssh-ed25519", "sk-ssh-ed25519@openssh.com", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521", "sk-ecdsa-sha2-nistp256@openssh.com", "ssh-rsa",
}


class Invalid(Exception):
    pass


# ----------------------------------------------------------------- keys --
def ssh_key(line):
    """An SSH public key line -> "TYPE BASE64" (the comment dropped). Strict:
    no options, no line breaks, the blob must decode and name its own type
    (these lines end up in sshd's answer to AuthorizedKeysCommand)."""
    if not isinstance(line, str) or any(c in line.strip() for c in "\r\n\0\"\\"):
        raise Invalid("not one line")
    parts = line.strip().split()
    if len(parts) < 2:
        raise Invalid("expected: TYPE BASE64 [comment]")
    kind, blob = parts[0], parts[1]
    if kind not in KEY_TYPES:
        raise Invalid(f"unsupported key type {kind[:40]!r}")
    if not re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", blob) or len(blob) > 4096:
        raise Invalid("the key isn't base64")
    try:
        raw = base64.b64decode(blob, validate=True)
        (n,) = struct.unpack(">I", raw[:4])
        inner = raw[4 : 4 + n].decode()
    except (ValueError, struct.error, UnicodeDecodeError):
        raise Invalid("the key doesn't decode") from None
    if inner != kind:
        raise Invalid("the key's type and its contents disagree")
    if kind == "ssh-rsa":
        fields, pos = [], 4 + n
        for _ in range(2):
            (m,) = struct.unpack(">I", raw[pos : pos + 4])
            fields.append(raw[pos + 4 : pos + 4 + m])
            pos += 4 + m
        if (len(fields[1].lstrip(b"\0")) * 8) < 2048:
            raise Invalid("RSA keys need at least 2048 bits")
    return f"{kind} {blob}"


def fingerprint(key):
    """SHA256:… as ssh-keygen -l prints it."""
    import hashlib

    raw = base64.b64decode(key.split()[1])
    return "SHA256:" + base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")


# ----------------------------------------------------------------- reading --
def read_toml(path):
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as e:
        raise Invalid(f"{e}") from None


class Repo:
    """A checked-out fleet repository (a working tree, or an archive of one
    commit). `errors` lists everything wrong with it; empty means valid."""

    def __init__(self, root):
        self.root = root
        self.errors = []
        self.fleet, self.groups, self.people, self.hosts = {}, {}, {}, {}
        self.profiles = set()
        self._load()
        if not self.errors:
            self._check()

    # ---- helpers
    def err(self, where, what):
        self.errors.append(f"{where}: {what}")

    def path(self, *p):
        return os.path.join(self.root, *p)

    def _table(self, where, data, schema, required=()):
        """Check keys and types; schema: key -> (type or tuple of types)."""
        if not isinstance(data, dict):
            self.err(where, "expected a table")
            return False
        ok = True
        for k in data:
            if k not in schema:
                self.err(where, f"unknown key {k!r}")
                ok = False
        for k, t in schema.items():
            if k in data and not (isinstance(data[k], t) and not (t is int and isinstance(data[k], bool))):
                self.err(where, f"{k} has the wrong type")
                ok = False
        for k in required:
            if k not in data:
                self.err(where, f"{k} is missing")
                ok = False
        return ok

    def _list_of(self, where, key, value, kind=str):
        if not isinstance(value, list) or not all(isinstance(x, kind) for x in value):
            self.err(where, f"{key} must be a list of {kind.__name__}")
            return []
        return value

    # ---- loading
    def _load(self):
        if not os.path.isfile(self.path("fleet.toml")):
            self.err("fleet.toml", "missing (not a fleet repository?)")
            return
        for name, attr in (("fleet.toml", "fleet"), ("groups.toml", "groups")):
            try:
                setattr(self, attr, read_toml(self.path(name)))
            except (OSError, Invalid) as e:
                self.err(name, e)
        for f in sorted(_ls(self.path("people"))):
            name, ext = os.path.splitext(f)
            if ext != ".toml":
                if not f.startswith("."):
                    self.err(f"people/{f}", "only NAME.toml files belong here")
                continue
            try:
                self.people[name] = read_toml(self.path("people", f))
            except (OSError, Invalid) as e:
                self.err(f"people/{f}", e)
        for f in sorted(_ls(self.path("profiles"))):
            name, ext = os.path.splitext(f)
            if ext == ".nix":
                self.profiles.add(name)
        for d in sorted(_ls(self.path("hosts"))):
            if d.startswith(".") or not os.path.isdir(self.path("hosts", d)):
                continue
            try:
                self.hosts[d] = read_toml(self.path("hosts", d, "host.toml"))
            except (OSError, Invalid) as e:
                self.err(f"hosts/{d}/host.toml", e)

    # ---- checking
    def _check(self):
        f = self.fleet
        if self._table("fleet.toml", f, {"organization": str, "server": str, "server_host_key": str,
                                         "tang": dict, "checkin": dict, "logs": dict},
                       ("organization", "server", "server_host_key")):
            if not 0 < len(f["organization"]) <= 100:
                self.err("fleet.toml", "organization: 1 to 100 characters")
            if not SERVER_RE.fullmatch(f["server"]):
                self.err("fleet.toml", "server: a name or address, optionally :PORT")
            try:
                f["server_host_key"] = ssh_key(f["server_host_key"])
            except Invalid as e:
                self.err("fleet.toml", f"server_host_key: {e}")
            t = f.get("tang")
            if t is not None and self._table("fleet.toml [tang]", t, {"url": str, "thumbprint": str}, ("url", "thumbprint")):
                if not re.fullmatch(r"http://[A-Za-z0-9.-]+(:[0-9]{1,5})?", t["url"]):
                    self.err("fleet.toml [tang]", "url: http://NAME[:PORT]")
                if not THUMBPRINT_RE.fullmatch(t["thumbprint"]):
                    self.err("fleet.toml [tang]", "thumbprint: as tang-show-keys prints it")
            c = f.get("checkin", {})
            if self._table("fleet.toml [checkin]", c, {"interval": int}):
                if not 30 <= c.get("interval", 300) <= 3600:
                    self.err("fleet.toml [checkin]", "interval: 30 to 3600 seconds")
            lg = f.get("logs", {})
            if self._table("fleet.toml [logs]", lg, {"min_priority": int, "units": list, "keep_days": int}):
                if not 0 <= lg.get("min_priority", 4) <= 7:
                    self.err("fleet.toml [logs]", "min_priority: 0 (emerg) to 7 (debug)")
                if not 1 <= lg.get("keep_days", 30) <= 3650:
                    self.err("fleet.toml [logs]", "keep_days: 1 to 3650")
                for u in self._list_of("fleet.toml [logs]", "units", lg.get("units", [])):
                    if not UNIT_RE.fullmatch(u):
                        self.err("fleet.toml [logs]", f"units: bad unit name {u!r}")

        gids = {}
        for g, t in self.groups.items():
            w = f"groups.toml [{g}]"
            if not GROUP_RE.fullmatch(g) or g in RESERVED:
                self.err(w, "a group name: lowercase letters, digits, - and _ (not a system name)")
            if not self._table(w, t, {"gid": int, "profiles": list, "sudo": bool, "description": str}, ("gid",)):
                continue
            if not 1000 <= t["gid"] <= 59999:
                self.err(w, "gid: 1000 to 59999")
            if t["gid"] in gids:
                self.err(w, f"gid {t['gid']} is also {gids[t['gid']]}'s")
            gids[t["gid"]] = g
            for p in self._list_of(w, "profiles", t.get("profiles", [])):
                if p != "*" and p not in self.profiles:
                    self.err(w, f"no profile {p!r} (profiles/{p}.nix)")
        a = self.groups.get(ADMINS)
        if not isinstance(a, dict):
            self.err("groups.toml", f"the group {ADMINS} is missing")
        elif a.get("sudo") is not True or a.get("profiles") != ["*"]:
            self.err(f"groups.toml [{ADMINS}]", 'needs sudo = true and profiles = ["*"]')

        for p in self.profiles:
            if not PROFILE_RE.fullmatch(p):
                self.err(f"profiles/{p}.nix", "a profile name: lowercase letters, digits and -")

        uids, keys = {}, {}
        try:
            keys[ssh_key(f.get("server_host_key", ""))] = "the server"
        except Invalid:
            pass
        for n, p in self.people.items():
            w = f"people/{n}.toml"
            if not PERSON_RE.fullmatch(n) or n in RESERVED or n.startswith(("nixbld", "systemd-")):
                self.err(w, "a user name: lowercase letters, digits, - and _ (not a system name)")
            if not self._table(w, p, {"name": str, "email": str, "uid": int, "groups": list, "ssh_keys": list,
                                      "age_recipient": str, "disabled": bool}, ("name", "uid")):
                continue
            if not 1000 <= p["uid"] <= 59999:
                self.err(w, "uid: 1000 to 59999")
            if p["uid"] in uids:
                self.err(w, f"uid {p['uid']} is also {uids[p['uid']]}'s")
            uids[p["uid"]] = n
            if not 0 < len(p["name"]) <= 100 or any(c in p["name"] for c in ":\n\r\0"):
                self.err(w, "name: 1 to 100 characters, no ':'")
            for g in self._list_of(w, "groups", p.get("groups", [])):
                if g not in self.groups:
                    self.err(w, f"no group {g!r} in groups.toml")
            clean = []
            for k in self._list_of(w, "ssh_keys", p.get("ssh_keys", [])):
                try:
                    k = ssh_key(k)
                except Invalid as e:
                    self.err(w, f"ssh_keys: {e}")
                    continue
                if k in keys:
                    self.err(w, f"ssh_keys: this key is also {keys[k]}'s")
                keys[k] = n
                clean.append(k)
            p["_keys"] = clean
            if "age_recipient" in p and not AGE_RE.fullmatch(p["age_recipient"]):
                self.err(w, "age_recipient: an age public key (age1…)")

        for h, t in self.hosts.items():
            w = f"hosts/{h}/host.toml"
            if not HOST_RE.fullmatch(h):
                self.err(f"hosts/{h}", "a computer name: lowercase letters, digits and -")
            if not self._table(w, t, {"profile": str, "branch": str, "unlock": str, "host_key": str,
                                      "disk_serial": str, "description": str}, ("profile", "unlock", "host_key")):
                continue
            if t["profile"] not in self.profiles:
                self.err(w, f"no profile {t['profile']!r} (profiles/{t['profile']}.nix)")
            if not BRANCH_RE.fullmatch(t.get("branch", "main")):
                self.err(w, "branch: lowercase letters, digits, . _ -")
            if t["unlock"] not in UNLOCK:
                self.err(w, f"unlock: one of {', '.join(UNLOCK)}")
            try:
                k = ssh_key(t["host_key"])
                if k in keys:
                    self.err(w, f"host_key: this key is also {keys[k]}'s")
                keys[k] = h
                t["_key"] = k
            except Invalid as e:
                self.err(w, f"host_key: {e}")

        admins = self.admins()
        if not any(p.get("_keys") for p in admins.values()):
            self.err(f"groups.toml [{ADMINS}]", "no member with an SSH key: nobody could reach the server")
        if not any(p.get("age_recipient") for p in admins.values()):
            self.err(f"groups.toml [{ADMINS}]", "no member with an age_recipient: nobody could read recovery keys")

    # ---- questions
    def setting(self, table, key, default):
        return self.fleet.get(table, {}).get(key, default)

    def admins(self):
        return {n: p for n, p in self.people.items()
                if ADMINS in p.get("groups", []) and not p.get("disabled", False)}

    def allows(self, group, profile):
        t = self.groups.get(group, {})
        ps = t.get("profiles", [])
        return "*" in ps or profile in ps

    def allowed(self, host):
        """People who may log in on this computer: {name: sudo}."""
        profile = self.hosts[host]["profile"]
        out = {}
        for n, p in self.people.items():
            if p.get("disabled", False):
                continue
            gs = [g for g in p.get("groups", []) if self.allows(g, profile)]
            if gs:
                out[n] = any(self.groups[g].get("sudo", False) for g in gs)
        return out

    def recipients(self):
        """The admins' age public keys: recovery keys are encrypted for these."""
        return sorted(p["age_recipient"] for p in self.admins().values() if p.get("age_recipient"))

    def hosts_of(self, profile):
        return sorted(h for h, t in self.hosts.items() if t.get("profile") == profile)


def _ls(d):
    try:
        return os.listdir(d)
    except OSError:
        return []


def load(root):
    return Repo(root)
