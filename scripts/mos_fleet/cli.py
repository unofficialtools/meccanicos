"""mos-fleet: an organization's MeccanicOS computers, from one git repository.

On your own computer (as yourself), in the fleet repository (~/fleet):
  init --server S --fingerprint FP --organization O --admin YOU --full-name N
                                 a new fleet repository, pushed to the server
  clone SERVER [--fingerprint FP]  the repository, for another admin
  admin-key                      your key for reading recovery keys (age)
  person add|edit|disable|enable|remove|show|list …   people (people/NAME.toml)
  group add|edit|remove|list …   groups: who may log in where, with sudo
  member add|remove GROUP NAME
  profile add|remove|list NAME   kinds of computers (profiles/NAME.nix)
  host prepare NAME --profile P --unlock tang|tpm-pin|fido2|password
                                 a one-time key and settings on the stick
  host add NAME                  after its installation: into the repository
  host set|retire|list|pending …
  validate [--no-eval]           check the files, and evaluate every computer
  diff [BASE..TARGET]            what changes on which computer (default: unpushed)
  push [--no-eval]               validate, then git push
  upgrade [--testing]            the newest MeccanicOS for the fleet
  password set NAME              someone's password (only its hash leaves)
  recover HOST                   a computer's disk recovery key (your admin key)
  status [HOST] | logs HOST [-f] | builds [HOST] | deployments HOST
  run --host H|--profile P -- CMD…   a command as root, at once where online
  reboot|switch|facts HOST…  |  jobs [HOST] | job ID | cancel ID
  shell HOST [--user U]          SSH to a computer, through the server
  audit | info

At the fleet server's console (asks for sudo):
  server init [--lan CIDR]… [--admin-key FILE]   set it up (safe to re-run)
  server admin-key FILE          an admin key for a day (the first, or a fix)
  server status | server backup DIR

Edits are checked and committed; `--push` (or mos-fleet push) sends them.
Guide: docs/fleet/ADMIN-GUIDE.md in the MeccanicOS repository.
"""

import argparse
import os
import sys

from . import admin, console
from .common import Fail
from .repo import Invalid


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    p = argparse.ArgumentParser(prog="mos-fleet", add_help=False)
    p.add_argument("-h", "--help", action="store_true")
    p.add_argument("--repo", help="the fleet repository (default: the one you're in, or ~/fleet)")
    sub = p.add_subparsers(dest="cmd")
    admin.add_parsers(sub)
    console.add_parsers(sub)
    a = p.parse_args(argv)
    if a.help or not a.cmd:
        print(__doc__.strip())
        return 0
    try:
        if a.cmd == "server":
            if os.geteuid() != 0:
                os.execvp("sudo", ["sudo", "mos-fleet", *argv])
            if a.action != "init" and not os.path.exists(console.MARK):
                raise Fail("This isn't the fleet server (mos-fleet server init).")
            console.dispatch(a)
        else:
            if os.geteuid() == 0:
                raise Fail("Run this as yourself, not root: it uses your SSH key and your admin key.")
            admin.dispatch(a)
    except (Fail, Invalid) as e:
        print(f"\033[1;31mmos-fleet:\033[0m {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
