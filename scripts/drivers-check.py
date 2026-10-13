#!/usr/bin/env python3
"""drivers-check - keep MeccanicOS's hardware support in step with EndeavourOS.

modules/drivers/endeavouros.txt is EndeavourOS's live-ISO package list at a
pinned commit; modules/drivers/map.toml says, for each of its packages, what
provides it in MeccanicOS (`by`) or why it isn't shipped (`skip`).

  ./start drivers-check              the map covers the snapshot exactly, and
                                     every `by` holds on the live ISO (Nix)
  ./start drivers-check --upstream   also: what changed upstream since the snapshot
  ./start drivers-check --update     move the snapshot to upstream's newest list
                                     (then map what's new, and check again)
Options: --no-nix (skip the evaluation), --report FILE (Markdown, for an issue).
Exit status 1 when something needs a decision.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT = os.path.join(ROOT, "modules", "drivers", "endeavouros.txt")
MAP = os.path.join(ROOT, "modules", "drivers", "map.toml")
REPO = "endeavouros-team/EndeavourOS-ISO"
FILE = "packages.x86_64"
CHECK_RE = re.compile(r"(option):([A-Za-z0-9_.-]+)(~([A-Za-z0-9_.+-]+))?|(package):([A-Za-z0-9_.+-]+)")

NIX = r"""
{ root, pathsJson }:
let
  f = builtins.getFlake root;
  c = f.nixosConfigurations.live.config;
  lib = f.inputs.nixpkgs.lib;
  name = p: if p ? pname then p.pname else (builtins.parseDrvName (p.name or "?")).name;
  pkgs = lib.concatMap lib.toList (with c; [
    environment.systemPackages hardware.firmware hardware.graphics.extraPackages services.udev.packages
    fonts.packages networking.networkmanager.plugins boot.extraModulePackages services.dbus.packages
    services.printing.drivers
  ]);
  get = p: lib.attrByPath (lib.splitString "." p) null c;
  show = v:
    if builtins.isList v then map (x: if builtins.isString x then x else if builtins.isAttrs x then name x else builtins.toJSON x) v
    else if builtins.isBool v then v
    else if v == null then false
    else if builtins.isString v then v != ""
    else true;
in {
  names = lib.unique (map name pkgs);
  options = lib.genAttrs (builtins.fromJSON pathsJson) (p: show (get p));
}
"""


def packages(text):
    """The package names in a packages.x86_64 (comments and blanks skipped)."""
    out = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line and line not in out:
            out.append(line)
    return out


def fetch(url):
    r = subprocess.run(["curl", "-fsSL", "--max-time", "60", "-A", "meccanicos-drivers-check", url],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"drivers-check: can't fetch {url}: {r.stderr.strip()}")
    return r.stdout


def upstream_head():
    d = json.loads(fetch(f"https://api.github.com/repos/{REPO}/commits/main"))
    return d["sha"], d["commit"]["committer"]["date"][:10]


def snapshot_commit():
    for line in open(SNAPSHOT):
        if line.startswith("#@ commit:"):
            return line.split()[2]
    return None


def check_map(snap, mapping, problems):
    for p in snap:
        if p not in mapping:
            problems.append(f"`{p}`: in EndeavourOS's list, not in map.toml (map it, or skip it with a reason)")
    for p, e in mapping.items():
        if p not in snap:
            problems.append(f"`{p}`: in map.toml, no longer in EndeavourOS's list (remove it)")
        if not isinstance(e, dict) or (("by" in e) == ("skip" in e)):
            problems.append(f"`{p}`: needs exactly one of `by` or `skip`")
            continue
        if "skip" in e and not (isinstance(e["skip"], str) and e["skip"].strip()):
            problems.append(f"`{p}`: `skip` needs a reason")
        for c in e.get("by", []):
            if not CHECK_RE.fullmatch(c):
                problems.append(f"`{p}`: `{c}` is not option:PATH, option:PATH~VALUE or package:NAME")
        extra = set(e) - {"by", "skip", "note"}
        if extra:
            problems.append(f"`{p}`: unknown keys {', '.join(sorted(extra))}")


def check_nix(mapping, problems):
    checks = {c for e in mapping.values() if isinstance(e, dict) for c in e.get("by", [])}
    paths = sorted({CHECK_RE.fullmatch(c).group(2) for c in checks if c.startswith("option:") and CHECK_RE.fullmatch(c)})
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "check.nix"), "w") as fh:
            fh.write(NIX)
        with open(os.path.join(tmp, "args.json"), "w") as fh:
            json.dump({"root": ROOT, "pathsJson": json.dumps(paths)}, fh)
        print("Evaluating the live ISO (nix)…", file=sys.stderr)
        r = subprocess.run(["nix", "eval", "--impure", "--json", "--expr",
                            f"(import {tmp}/check.nix) (builtins.fromJSON (builtins.readFile {tmp}/args.json))"],
                           capture_output=True, text=True)
    if r.returncode != 0:
        problems.append("the live ISO doesn't evaluate:\n\n```\n" + r.stderr.strip()[-2000:] + "\n```")
        return
    got = json.loads(r.stdout)
    names, options = set(got["names"]), got["options"]
    for p, e in sorted(mapping.items()):
        for c in e.get("by", []) if isinstance(e, dict) else []:
            m = CHECK_RE.fullmatch(c)
            if not m:
                continue
            if m.group(5):
                if m.group(6) not in names:
                    problems.append(f"`{p}`: `{c}`: no such package on the live ISO")
            else:
                v = options.get(m.group(2))
                ok = (m.group(4) in v) if (m.group(4) and isinstance(v, list)) else (bool(v) and not m.group(4))
                if not ok:
                    problems.append(f"`{p}`: `{c}`: not set on the live ISO (or no such option)")


def main(argv=None):
    p = argparse.ArgumentParser(prog="drivers-check", description=__doc__.split("\n\n")[0])
    p.add_argument("--upstream", action="store_true", help="compare with EndeavourOS's newest list")
    p.add_argument("--update", action="store_true", help="move the snapshot to EndeavourOS's newest list")
    p.add_argument("--no-nix", action="store_true", help="skip evaluating the live ISO")
    p.add_argument("--report", help="write a Markdown report here")
    a = p.parse_args(argv)

    problems, lines = [], []
    pinned = snapshot_commit()
    if a.upstream or a.update:
        sha, date = upstream_head()
        new = fetch(f"https://raw.githubusercontent.com/{REPO}/{sha}/{FILE}")
        old = packages(open(SNAPSHOT).read())
        added = [x for x in packages(new) if x not in old]
        removed = [x for x in old if x not in packages(new)]
        if sha == pinned:
            lines.append(f"EndeavourOS's list: unchanged since the snapshot ({sha[:12]}).")
        else:
            lines.append(f"EndeavourOS's list: snapshot {pinned[:12] if pinned else '?'}, upstream {sha[:12]} ({date}).")
            lines += [f"- added upstream: `{x}`" for x in added] + [f"- removed upstream: `{x}`" for x in removed]
            if not added and not removed:
                lines.append("- the same packages (only comments or order changed)")
            if a.update:
                with open(SNAPSHOT, "w") as fh:
                    fh.write(f"#@ upstream: {REPO.split('/')[0]}/{REPO.split('/')[1]} {FILE}\n#@ commit: {sha} ({date})\n"
                             "#@ MeccanicOS's answer to each package: map.toml. Refresh: ./start drivers-check --update\n" + new)
                lines.append(f"Snapshot updated to {sha[:12]}: map what's new in map.toml, then check again.")
            elif added or removed:
                problems.append(f"EndeavourOS changed its list since {pinned[:12] if pinned else '?'}: "
                                "./start drivers-check --update, then map the changes")
    snap = packages(open(SNAPSHOT).read())
    with open(MAP, "rb") as fh:
        mapping = tomllib.load(fh)
    check_map(snap, mapping, problems)
    if not a.no_nix:
        check_nix(mapping, problems)

    shipped = sum(1 for e in mapping.values() if isinstance(e, dict) and "by" in e)
    lines.append(f"{len(snap)} EndeavourOS packages: {shipped} provided, {len(mapping) - shipped} skipped with a reason.")
    lines += ["", "**Needs a decision:**", ""] + [f"- {x}" for x in problems] if problems else ["Nothing to do."]
    text = "\n".join(lines)
    print(text)
    if a.report:
        with open(a.report, "w") as fh:
            fh.write(text + "\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
