#!/usr/bin/env bash
# mos-upgrade - bring this computer up to the newest MeccanicOS and NixOS packages.
#
#   mos-upgrade                  the newest of what you follow (normally: the
#                                latest release), rebuild, switch to it
#   mos-upgrade --boot           the same, used from the next start
#   mos-upgrade --check          what you have and what the newest is (changes nothing)
#   mos-upgrade --list           the releases, newest first (changes nothing)
#   mos-upgrade --to RELEASE     go to that release (v2026-10-12) and stay on it
#   mos-upgrade --to COMMIT      go to that commit (5b31f5e) and stay on it
#   mos-upgrade --to main        follow the newest development version (untested)
#   mos-upgrade --to latest      follow the releases again (the usual)
#
# --to goes with --boot too. mos-update is the same command.
#
# /etc/nixos holds your own files (local.nix, hardware-configuration.nix,
# meccanicos.toml, remote-unlock-keys) and a flake.nix that takes the rest of
# the system from the MeccanicOS repository, and the NixOS packages from its
# NixOS release. What it follows is the end of its meccanicos url: latest (the
# newest release: a tag GitHub moves once a release's ISO is built), main, a
# release or a commit; --to changes it. This moves both to the newest
# (flake.lock) and rebuilds. Staying on a release or commit, the NixOS packages
# still get their fixes. The system before stays in the boot menu; if the
# rebuild fails, the previous flake.nix and flake.lock are put back (that does
# not undo a system that was partly switched to: pick the previous entry in the
# boot menu). One update at a time: one started meanwhile says so and stops,
# changing nothing. When a release moves to a newer NixOS (26.05 -> 26.11),
# this follows it.
#
# Needs a network connection. --auto (the weekly mos-auto-upgrade) builds for
# the next start.
set -euo pipefail

DEST=${MECCANICOS_NIXOS_DIR:-/etc/nixos}
NAME=${MECCANICOS_NAME:-MeccanicOS}

mode=switch to=""
args=("$@")
while (($#)); do
    case $1 in
        --boot) mode=boot ;;
        --check) mode=check ;;
        --list) mode=list ;;
        --auto) mode=auto ;;
        --to) [[ -n ${2:-} ]] || { echo "mos-upgrade: --to needs a release, a commit, main or latest" >&2; exit 2; }
            to=$2; shift ;;
        --to=*) to=${1#--to=} ;;
        -h | --help | help) sed -n '/^# mos-upgrade - /,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
        *) echo "mos-upgrade: unknown option $1 (mos-upgrade --help)" >&2; exit 2 ;;
    esac
    shift
done
[[ -z $to || $mode == switch || $mode == boot ]] ||
    { echo "mos-upgrade: --to goes with --boot only" >&2; exit 2; }
locked() { jq -r "$1 // empty" "$DEST/flake.lock" 2>/dev/null; }
day() { [[ -n $1 ]] && date -d "@$1" +%F || echo "?"; }
# The repository /etc/nixos/flake.nix follows (owner/repo), from flake.lock.
GITHUB=$(locked '.nodes.meccanicos.original | select(.owner) | "\(.owner)/\(.repo)"')
[[ -n $GITHUB ]] ||
    { echo "mos-upgrade: $DEST/flake.lock does not follow a MeccanicOS release (see flake.nix: mkInstalled)" >&2; exit 1; }
if [[ $EUID -ne 0 && $mode != check && $mode != list ]]; then exec sudo "$(readlink -f "$0")" "${args[@]}"; fi
# One update at a time (this, the weekly mos-auto-upgrade, another terminal):
# a lock on $DEST, held from reading flake.nix to the end of the rebuild.
if [[ $mode != check && $mode != list ]]; then
    exec 9<"$DEST"
    flock -n 9 ||
        { echo "mos-upgrade: another update is running (perhaps the weekly one: systemctl status mos-auto-upgrade). Try again when it is done. Nothing changed." >&2; exit 1; }
fi

# What flake.nix follows: latest, main, a release (v2026-10-12) or a commit.
following() {
    sed -n "s|.*\"github:$GITHUB/\([^\"?]*\)\".*|\1|p" "$DEST/flake.nix" | head -n1 | grep . || echo main
}
# The repository's branches and tags: "<commit> <name>" (annotated tags: the
# commit they name), from GitHub.
REFS=""
refs() {
    [[ -n $REFS ]] && return 0
    REFS=$(git ls-remote --heads --tags "https://github.com/$GITHUB" 2>/dev/null |
        sed -E 's#^([0-9a-f]+)\s+refs/(heads|tags)/#\1 #' |
        awk '{ sub(/\^\{\}$/, "", $2); name[$2] = $1 } END { for (n in name) print name[n], n }') ||
        { echo "mos-upgrade: cannot reach github.com/$GITHUB (offline?)" >&2; exit 1; }
}
# The releases (v... tags), newest first: "<commit> <name>".
releases() { refs; awk '$2 ~ /^v/' <<<"$REFS" | sort -k2,2 -V -r; }
# "v2026-10-12 (5b31f5e)" for a commit: the release it is, else main if it is
# main's head, else just the commit.
describe() {
    local rev=$1 name
    refs
    name=$(awk -v r="$rev" '$1 == r && $2 ~ /^v/ { print $2 }' <<<"$REFS" | sort -V | tail -n1)
    [[ -n $name ]] || name=$(awk -v r="$rev" '$1 == r && $2 == "main" { print "main" }' <<<"$REFS")
    if [[ -n $name ]]; then echo "$name (${rev:0:7})"; else echo "${rev:0:7}"; fi
}
what() {
    case $1 in
        latest) echo "the latest release" ;;
        main) echo "main, the newest development version (untested)" ;;
        v*) echo "release $1 (stays on it)" ;;
        *) echo "commit ${1:0:7} (stays on it)" ;;
    esac
}

if [[ $mode == list ]]; then
    refs
    have=$(locked .nodes.meccanicos.locked.rev)
    newest=$(awk '$2 == "latest" { print $1 }' <<<"$REFS")
    echo "$NAME releases, newest first (mos-upgrade --to RELEASE):"
    while read -r rev name; do
        mark=""
        [[ $rev == "$newest" ]] && mark+="  latest"
        [[ $rev == "$have" ]] && mark+="  ← yours"
        printf '  %-16s %s%s\n' "$name" "${rev:0:7}" "$mark"
    done < <(releases | head -n 20)
    main=$(awk '$2 == "main" { print $1 }' <<<"$REFS")
    printf '  %-16s %s%s\n' "main" "${main:0:7}" "$([[ $main == "$have" ]] && echo "  ← yours")"
    echo "Following: $(what "$(following)")."
    exit 0
fi

if [[ $mode == check ]]; then
    ref=$(following)
    newest=$(nix flake metadata --json --refresh "github:$GITHUB/$ref" 2>/dev/null) ||
        { echo "mos-upgrade: cannot reach github:$GITHUB (offline?)" >&2; exit 1; }
    pkgs=$(locked .nodes.nixpkgs.original.ref)
    packages=$(nix flake metadata --json --refresh "github:NixOS/nixpkgs/${pkgs:-nixos-unstable}" 2>/dev/null || echo '{}')
    refs
    echo "Following: $(what "$ref")"
    echo "Yours:     $NAME $(describe "$(locked .nodes.meccanicos.locked.rev)") of $(day "$(locked .nodes.meccanicos.locked.lastModified)")"
    echo "Newest:    $NAME $(describe "$(jq -r '.revision' <<<"$newest")") of $(day "$(jq -r '.lastModified' <<<"$newest")")"
    if [[ $ref != latest ]]; then
        latest=$(releases | head -n1)
        [[ -z $latest ]] || echo "Latest release: ${latest#* } (${latest:0:7}); follow the releases again: mos-upgrade --to latest"
    fi
    echo "NixOS packages ($pkgs): yours of $(day "$(locked .nodes.nixpkgs.locked.lastModified)"), newest of $(day "$(jq -r '.lastModified // empty' <<<"$packages")")"
    exit 0
fi

# --to: what to follow from now on. latest and main as they are; a release
# or commit is checked on GitHub, and a short commit written out in full.
if [[ -n $to ]]; then
    case $to in
        latest | main) ;;
        *)
            meta=$(nix flake metadata --json --refresh "github:$GITHUB/$to" 2>/dev/null) ||
                { echo "mos-upgrade: no release or commit '$to' in github.com/$GITHUB (mos-upgrade --list), or offline" >&2; exit 1; }
            if [[ ! $to =~ ^v ]]; then
                refs
                if awk -v n="$to" '$2 == n { found = 1 } END { exit !found }' <<<"$REFS"; then
                    [[ $to == latest || $to == main ]] || { echo "mos-upgrade: $to is a branch; only main, latest, releases (v...) and commits" >&2; exit 2; }
                else
                    to=$(jq -r '.revision' <<<"$meta")
                fi
            fi
            ;;
    esac
fi

# Put things back as they were: on any way out but success (a failed
# download or rebuild, an error, Ctrl+C). From this run's own copy, so two
# runs never restore each other's files.
SAVED=$(mktemp -d)
undo() {
    [[ -e $SAVED/flake.lock ]] && cp "$SAVED/flake.lock" "$DEST/flake.lock"
    [[ -e $SAVED/flake.nix ]] && cp "$SAVED/flake.nix" "$DEST/flake.nix"
    return 0
}
finished=0 # set once it worked; until then, any way out puts things back
on_exit() {
    if ((!finished)); then
        echo "Putting the previous $DEST/flake.nix and flake.lock back." >&2
        undo
    fi
    rm -rf "$SAVED"
}
trap 'exit 130' INT TERM
trap on_exit EXIT

cp "$DEST/flake.nix" "$SAVED/flake.nix"
cp "$DEST/flake.lock" "$SAVED/flake.lock" 2>/dev/null || true
# The flake.lock before, kept in $DEST once the update worked (mos-updates).
keep_previous() {
    [[ -e $SAVED/flake.lock ]] || return 0
    cp "$SAVED/flake.lock" "$DEST/flake.lock.previous.new" && mv -f "$DEST/flake.lock.previous.new" "$DEST/flake.lock.previous"
}
if [[ -n $to && $to != "$(following)" ]]; then
    sed -i -E "s|\"github:$GITHUB(/[^\"?]*)?\"|\"github:$GITHUB/$to\"|" "$DEST/flake.nix"
    [[ $(following) == "$to" ]] ||
        { echo "mos-upgrade: could not change what $DEST/flake.nix follows (its meccanicos url)" >&2; exit 1; }
    echo "From now on following $(what "$to")."
fi
echo "Downloading the newest $NAME and NixOS packages..."
if ! nix flake update --flake "$DEST"; then
    echo "mos-upgrade: could not download the newest (offline?). Nothing changed." >&2
    exit 1
fi

# A release on a newer NixOS: follow it (its modules are written for it).
src=$(nix flake archive --json "$DEST" | jq -r '.inputs.meccanicos.path // empty')
want=$(jq -r '.nodes.nixpkgs.original.ref // empty' "$src/flake.lock" 2>/dev/null || true)
have=$(locked .nodes.nixpkgs.original.ref)
if [[ -n $want && -n $have && $want != "$have" ]]; then
    echo "$NAME now uses NixOS ${want#nixos-} (was ${have#nixos-}): following it."
    sed -i "s|github:NixOS/nixpkgs/$have\"|github:NixOS/nixpkgs/$want\"|" "$DEST/flake.nix"
    nix flake update --flake "$DEST"
fi

if cmp -s "$DEST/flake.lock" "$SAVED/flake.lock"; then
    finished=1
    echo "Already up to date: $NAME $(describe "$(locked .nodes.meccanicos.locked.rev)" 2>/dev/null || locked .nodes.meccanicos.locked.rev | cut -c1-7)."
    exit 0
fi

how=switch
[[ $mode == switch ]] || how=boot
# The system before, to tell afterwards whether a failed rebuild got as far as
# putting the new one in place.
PROFILE=${MECCANICOS_SYSTEM_PROFILE:-/nix/var/nix/profiles/system}
system() { readlink -f "$PROFILE" 2>/dev/null || true; readlink -f /run/current-system 2>/dev/null || true; }
before=$(system)
echo "Building the new system ($how)..."
if nixos-rebuild "$how" --flake "$DEST#installed"; then
    finished=1
    keep_previous || true
    echo
    new=$(describe "$(locked .nodes.meccanicos.locked.rev)" 2>/dev/null || locked .nodes.meccanicos.locked.rev | cut -c1-7)
    if [[ $how == boot ]]; then
        echo "Updated to $NAME ${new:-(newest)}. Restart to use it."
    else
        echo "Updated to $NAME ${new:-(newest)}."
    fi
    echo "Something wrong? Pick the previous entry in the boot menu when the computer starts."
else
    echo >&2
    if [[ $(system) == "$before" ]]; then
        echo "The new version did not build." >&2
    else
        echo "The new version was built and partly put in place, then failed." >&2
        echo "Putting flake.nix and flake.lock back does not undo that. If something is wrong," >&2
        echo "restart and pick the previous entry in the boot menu, or: sudo nixos-rebuild switch --rollback" >&2
    fi
    exit 1
fi
