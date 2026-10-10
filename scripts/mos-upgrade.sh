#!/usr/bin/env bash
# mos-upgrade - bring this computer up to the newest MeccanicOS and NixOS packages.
#
#   mos-upgrade           download the newest, rebuild, switch to it
#   mos-upgrade --boot    the same, used from the next start
#   mos-upgrade --check   what you have and what the newest is (changes nothing)
#
# mos-update is the same command. /etc/nixos holds your own files (local.nix,
# hardware-configuration.nix, meccanicos.toml, remote-unlock-keys) and a
# flake.nix that takes the rest of the system from the MeccanicOS repository
# at its latest release, and the NixOS packages from its NixOS release. This
# moves both to the newest (flake.lock) and rebuilds. The system before stays
# in the boot menu; if the rebuild fails, the previous flake.lock is put back.
# When a release moves to a newer NixOS (26.05 -> 26.11), this follows it.
#
# Needs a network connection. --auto (the weekly mos-auto-upgrade) builds for
# the next start.
set -euo pipefail

DEST=${MECCANICOS_NIXOS_DIR:-/etc/nixos}
NAME=${MECCANICOS_NAME:-MeccanicOS}

mode=switch
case ${1:-} in
    "") ;;
    --boot) mode=boot ;;
    --check) mode=check ;;
    --auto) mode=auto ;;
    -h | --help | help) sed -n '/^# mos-upgrade - /,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
    *) echo "mos-upgrade: unknown option $1 (mos-upgrade --help)" >&2; exit 2 ;;
esac
locked() { jq -r "$1 // empty" "$DEST/flake.lock" 2>/dev/null; }
day() { [[ -n $1 ]] && date -d "@$1" +%F || echo "?"; }
# The repository /etc/nixos/flake.nix follows (owner/repo), from flake.lock.
GITHUB=$(locked '.nodes.meccanicos.original | select(.owner) | "\(.owner)/\(.repo)"')
[[ -n $GITHUB ]] ||
    { echo "mos-upgrade: $DEST/flake.lock does not follow a MeccanicOS release (see flake.nix: mkInstalled)" >&2; exit 1; }
if [[ $EUID -ne 0 && $mode != check ]]; then exec sudo "$(readlink -f "$0")" "$@"; fi

if [[ $mode == check ]]; then
    latest=$(nix flake metadata --json --refresh "github:$GITHUB/latest") ||
        { echo "mos-upgrade: cannot reach github:$GITHUB (offline?)" >&2; exit 1; }
    ref=$(locked .nodes.nixpkgs.original.ref)
    packages=$(nix flake metadata --json --refresh "github:NixOS/nixpkgs/${ref:-nixos-unstable}" 2>/dev/null || echo '{}')
    echo "Yours:  $NAME $(locked .nodes.meccanicos.locked.rev | cut -c1-7) of $(day "$(locked .nodes.meccanicos.locked.lastModified)")"
    echo "Newest: $NAME $(jq -r '.revision' <<<"$latest" | cut -c1-7) of $(day "$(jq -r '.lastModified' <<<"$latest")")"
    echo "NixOS packages ($ref): yours of $(day "$(locked .nodes.nixpkgs.locked.lastModified)"), newest of $(day "$(jq -r '.lastModified // empty' <<<"$packages")")"
    exit 0
fi

# Put things back as they were: on any way out but success (a failed
# download or rebuild, an error, Ctrl+C).
undo() {
    [[ -e $DEST/flake.lock.previous ]] && cp "$DEST/flake.lock.previous" "$DEST/flake.lock"
    [[ -e $DEST/flake.nix.previous ]] && cp "$DEST/flake.nix.previous" "$DEST/flake.nix"
    return 0
}
finished=0 # set once it worked; until then, any way out puts things back
on_exit() {
    if ((!finished)); then
        echo "Putting the previous $DEST back." >&2
        undo
    fi
}
trap 'exit 130' INT TERM
trap on_exit EXIT

cp "$DEST/flake.nix" "$DEST/flake.nix.previous"
cp "$DEST/flake.lock" "$DEST/flake.lock.previous" 2>/dev/null || rm -f "$DEST/flake.lock.previous"
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

if cmp -s "$DEST/flake.lock" "$DEST/flake.lock.previous"; then
    finished=1
    rm -f "$DEST/flake.nix.previous"
    echo "Already up to date: $NAME $(locked .nodes.meccanicos.locked.rev | cut -c1-7)."
    exit 0
fi

how=switch
[[ $mode == switch ]] || how=boot
echo "Building the new system ($how)..."
if nixos-rebuild "$how" --flake "$DEST#installed"; then
    finished=1
    rm -f "$DEST/flake.nix.previous"
    echo
    new=$(locked .nodes.meccanicos.locked.rev | cut -c1-7)
    if [[ $how == boot ]]; then
        echo "Updated to $NAME ${new:-(newest)}. Restart to use it."
    else
        echo "Updated to $NAME ${new:-(newest)}."
    fi
    echo "Something wrong? Pick the previous entry in the boot menu when the computer starts."
else
    echo >&2
    echo "The new version did not build." >&2
    exit 1
fi
