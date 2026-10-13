"""Shared by the server, the agent and the command line."""

import datetime
import json
import os
import re
import shlex
import subprocess
import sys

VERSION = "2"

# A system built for a computer: what the server may tell an agent to run.
SYSTEM_RE = re.compile(r"/nix/store/[0-9a-df-np-sv-z]{32}-nixos-system-[A-Za-z0-9._+-]{1,200}")
STORE_PATH_RE = re.compile(r"/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9._+?=-]{1,211}")
# Password hashes accepted: yescrypt ($y$, NixOS's default) and SHA-512 ($6$).
HASH_RE = re.compile(r"\$(y\$[./A-Za-z0-9]{1,20}\$[./A-Za-z0-9]{1,100}\$[./A-Za-z0-9]{43}"
                     r"|6\$(rounds=[0-9]{4,9}\$)?[./A-Za-z0-9]{1,16}\$[./A-Za-z0-9]{86})")
REV_RE = re.compile(r"[0-9a-f]{40}")
TOKEN_RE = re.compile(r"[0-9a-f]{32}")

MAX_LINE = 4 << 20  # one protocol message
SERVER_ALIAS = "mos-fleet-server"  # HostKeyAlias: the pinned key, whatever the address


class Fail(Exception):
    pass


def say(text=""):
    print(text, flush=True)


def warn(text):
    print(text, file=sys.stderr, flush=True)


def now():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)


def run(cmd, check=True, capture=True, input=None, env=None, cwd=None, timeout=None):
    """Run a command (a list: never a shell). Returns stdout (captured)."""
    r = subprocess.run(cmd, input=input, text=True, capture_output=capture, cwd=cwd, timeout=timeout,
                       env=None if env is None else {**os.environ, **env})
    if check and r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip() if capture else ""
        raise Fail(f"{shlex.join(cmd[:4])}{' …' if len(cmd) > 4 else ''} failed ({r.returncode})"
                   + (f":\n{err[-2000:]}" if err else ""))
    return r.stdout if capture else ""


def dumps(obj):
    return json.dumps(obj, separators=(",", ":"), default=str)


class Lines:
    """Newline-delimited JSON on a pair of file descriptors, with a size cap."""

    def __init__(self, rfd, wfd):
        self.rfd, self.wfd, self.buf = rfd, wfd, b""

    def send(self, obj):
        data = (dumps(obj) + "\n").encode()
        while data:
            n = os.write(self.wfd, data)
            data = data[n:]

    def feed(self, chunk):
        """Add bytes read; return the complete messages (dicts)."""
        self.buf += chunk
        out = []
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            if line.strip():
                out.append(parse(line))
        if len(self.buf) > MAX_LINE:
            raise Fail("message too long")
        return out


def parse(line):
    if len(line) > MAX_LINE:
        raise Fail("message too long")
    try:
        obj = json.loads(line)
    except ValueError:
        raise Fail("not JSON") from None
    if not isinstance(obj, dict):
        raise Fail("not a JSON object")
    return obj


def clip(s, n):
    """A string from the network, made safe to store: str, at most n chars."""
    if s is None:
        return None
    s = s if isinstance(s, str) else str(s)
    return s[:n]


def write_atomic(path, text, mode=0o600):
    tmp = f"{path}.tmp{os.getpid()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def ssh_known_hosts(key):
    return f"{SERVER_ALIAS} {key}\n"


def split_server(server):
    """'hq.example.com:2222' -> ('hq.example.com', '2222')."""
    host, _, port = server.partition(":")
    return host, port or "22"


def toml_value(x):
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, int):
        return str(x)
    if isinstance(x, list):
        return "[" + ", ".join(toml_value(i) for i in x) + "]"
    return json.dumps(x, ensure_ascii=False)  # a JSON string is a TOML basic string


def toml_dump(d, header=""):
    """A small TOML writer: top-level keys, then tables (one level)."""
    lines = [header] if header else []
    lines += [f"{k} = {toml_value(v)}" for k, v in d.items()
              if not isinstance(v, dict) and v is not None and not k.startswith("_")]
    for k, v in d.items():
        if isinstance(v, dict):
            lines += ["", f"[{k}]"] + [f"{kk} = {toml_value(vv)}" for kk, vv in v.items()
                                       if vv is not None and not kk.startswith("_")]
    return "\n".join(lines).lstrip("\n") + "\n"
