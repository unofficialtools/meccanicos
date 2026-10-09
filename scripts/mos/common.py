"""What mos-config and mos-doctor share: running programs, asking,
printing, and where things are.

Conventions for every mos-* command: -h, --help and `help` print the help;
exit code 0 = done, 1 = failed, 2 = wrong usage; messages go to stderr,
results (values, lists, JSON) to stdout.
"""

import json
import os
import shutil
import subprocess
import sys

# The shared library (mos_i18n): MECCANICOS_PYLIB from the Nix wrapper, else scripts/lib.
sys.path.insert(0, os.environ.get("MECCANICOS_PYLIB") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from mos_i18n import translator  # noqa: E402

T = translator("")  # texts shared by mos-config and mos-doctor

NAME = os.environ.get("MECCANICOS_NAME", "MeccanicOS")
HOME = os.path.expanduser("~")
CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config"), "meccanicos")
STATE_DIR = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.join(HOME, ".local", "state"), "meccanicos")
SETTINGS = os.path.join(CONFIG_DIR, "settings.toml")  # yours: every setting, for export
SYSTEM_TOML = os.environ.get("MECCANICOS_SYSTEM_TOML", "/etc/nixos/meccanicos.toml")  # modules/settings.nix


class UsageError(Exception):
    """Wrong command line: exit code 2."""


class Failed(Exception):
    """Something could not be done: exit code 1."""


def installed():
    """An installed system (vs the live USB): it has the flake in /etc/nixos."""
    if "MECCANICOS_LIVE" in os.environ:
        return os.environ["MECCANICOS_LIVE"] != "1"
    return os.path.exists("/etc/nixos/flake.nix")


def have(prog):
    return shutil.which(prog) is not None


# True while a full-screen view owns the terminal: sudo must not ask there.
NO_PROMPT = False


def run(*cmd, check=False, sudo=False, input=None, timeout=30):
    """Run a program; returns (exit code, output). Never raises for a
    missing program or a timeout: those come back as code 127 / 124."""
    cmd = [str(c) for c in cmd]
    if sudo and os.geteuid() != 0:
        # Passwordless for MeccanicOS's own user (wheel); asks otherwise.
        cmd = ["sudo", "-n", *cmd] if NO_PROMPT or not sys.stdin.isatty() else ["sudo", *cmd]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, input=input, timeout=timeout)
    except FileNotFoundError:
        if check:
            raise Failed(T("{program} is not installed").format(program=cmd[0]))
        return 127, ""
    except subprocess.TimeoutExpired:
        if check:
            raise Failed(T("{command} took too long").format(command=' '.join(cmd)))
        return 124, ""
    out = (p.stdout + p.stderr).strip()
    if check and p.returncode != 0:
        raise Failed(out.splitlines()[-1] if out else T("{command} failed").format(command=' '.join(cmd)))
    return p.returncode, out


def output(*cmd, sudo=False):
    """A program's output, or "" if it failed."""
    code, out = run(*cmd, sudo=sudo)
    return out if code == 0 else ""


# ---- talking to the user -----------------------------------------------------------
_color = sys.stderr.isatty() and os.environ.get("NO_COLOR") is None


def _paint(code, text):
    return f"\033[{code}m{text}\033[0m" if _color else text


def ok(msg):
    print(f"{_paint('32', '✓')} {msg}", file=sys.stderr)


def warn(msg):
    print(f"{_paint('33', '!')} {msg}", file=sys.stderr)


def bad(msg):
    print(f"{_paint('31', '✗')} {msg}", file=sys.stderr)


def info(msg):
    print(f"  {msg}", file=sys.stderr)


def title(msg):
    print(_paint("1", msg), file=sys.stderr)


def ask(question, default=True):
    """Yes/no; without a terminal, the default."""
    if not sys.stdin.isatty():
        return default
    hint = "[Y/n]" if default else "[y/N]"
    while True:
        try:
            a = input(f"{question} {hint} ").strip().lower()
        except EOFError:
            return default
        if not a:
            return default
        if a in ("y", "yes"):
            return True
        if a in ("n", "no"):
            return False


def choose(question, options):
    """Pick one of options (a list of labels); returns its index or None."""
    if not sys.stdin.isatty():
        return None
    print(question, file=sys.stderr)
    for i, o in enumerate(options, 1):
        print(f"  {i}) {o}", file=sys.stderr)
    try:
        a = input(T("Number (Enter to cancel): ")).strip()
    except EOFError:
        return None
    return int(a) - 1 if a.isdigit() and 1 <= int(a) <= len(options) else None


def log(name, msg):
    """One line in ~/.local/state/meccanicos/<name>.log, with the time."""
    import time
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(os.path.join(STATE_DIR, f"{name}.log"), "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}\n")


def print_json(data):
    json.dump(data, sys.stdout, indent=2)
    print()
