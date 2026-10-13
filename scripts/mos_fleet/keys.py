"""sshd's AuthorizedKeysCommand for the account `fleet` on the fleet server:

    AuthorizedKeysCommand mos-fleet-keys %u %t %k

Given the key a client offers, answer with one authorized_keys line that
pins what that key may do (a forced command, `restrict`: no shell, no
forwarding), or nothing. Who's who comes from keys.json, which the server
writes from the newest valid main branch of the fleet repository (people in
fleet-admins, computers) and from pending enrollments; bootstrap.json holds
admin keys added at the server's console, valid for a day.

Kept small and without third-party imports: sshd runs it for every login.
"""

import json
import os
import sys
import time

from . import settings
from .repo import Invalid, ssh_key

STATE = os.environ.get("MOS_FLEET_STATE") or settings.get("server")["state"]


def lookup(key, data, bootstrap, now):
    found = []
    for name, keys in data.get("admins", {}).items():
        if key in keys:
            found.append(("admin", name))
    for name, k in data.get("hosts", {}).items():
        if k == key:
            found.append(("host", name))
    for name, e in data.get("enroll", {}).items():
        if e.get("key") == key and e.get("expires", 0) > now:
            found.append(("enroll", name))
    if not found:  # a console key, once in the repository, is that person
        for e in bootstrap:
            if e.get("key") == key and e.get("expires", 0) > now:
                found.append(("bootstrap", "console"))
                break
    return found[0] if len(found) == 1 else None  # ambiguous: nobody


def load(name, default):
    try:
        with open(os.path.join(STATE, name)) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 3 or argv[0] != "fleet":
        return 0
    try:
        key = ssh_key(f"{argv[1]} {argv[2]}")
    except Invalid:
        return 0
    hit = lookup(key, load("keys.json", {}), load("bootstrap.json", []), time.time())
    serve = os.environ.get("MOS_FLEET_SERVE", "")
    if hit and serve.startswith("/nix/store/"):
        role, name = hit
        print(f'restrict,command="{serve} {role} {name}" {key}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
