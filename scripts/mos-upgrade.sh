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
# An /etc/nixos that is still a full copy of the repository (installed before
# this way of updating) is moved to it first: your files stay, the old copy is
# kept in /etc/nixos.previous (and put back if the rebuild fails).
#
# Needs a network connection. --auto (the weekly mos-auto-upgrade) builds for
# the next start and leaves an older /etc/nixos as it is.
set -euo pipefail

DEST=${MECCANICOS_NIXOS_DIR:-/etc/nixos}
NAME=${MECCANICOS_NAME:-MeccanicOS}
KEEP=(local.nix meccanicos.toml hardware-configuration.nix remote-unlock-keys)

mode=switch
case ${1:-} in
    "") ;;
    --boot) mode=boot ;;
    --check) mode=check ;;
    --auto) mode=auto ;;
    -h | --help | help) sed -n '/^# mos-upgrade - /,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
    *) echo "mos-upgrade: unknown option $1 (mos-upgrade --help)" >&2; exit 2 ;;
esac
[[ -n ${MECCANICOS_ETC_NIXOS:-} ]] ||
    { echo "mos-upgrade: MECCANICOS_ETC_NIXOS is not set (the mos-upgrade wrapper sets it)" >&2; exit 1; }
TEMPLATE=$MECCANICOS_ETC_NIXOS/flake.nix
GITHUB=$(sed -n 's|.*url = "github:\([^"]*\)/latest".*|\1|p' "$TEMPLATE") # owner/repo
if [[ $EUID -ne 0 && $mode != check ]]; then exec sudo "$(readlink -f "$0")" "$@"; fi

# /etc/nixos in the current layout (vs a full copy of the repository).
thin() { grep -q 'meccanicos.lib.mkInstalled' "$DEST/flake.nix" 2>/dev/null; }
locked() { jq -r "$1 // empty" "$DEST/flake.lock" 2>/dev/null; }
day() { [[ -n $1 ]] && date -d "@$1" +%F || echo "?"; }

if [[ $mode == check ]]; then
    latest=$(nix flake metadata --json --refresh "github:$GITHUB/latest") ||
        { echo "mos-upgrade: cannot reach github:$GITHUB (offline?)" >&2; exit 1; }
    ref=$(locked .nodes.nixpkgs.original.ref)
    packages=$(nix flake metadata --json --refresh "github:NixOS/nixpkgs/${ref:-nixos-unstable}" 2>/dev/null || echo '{}')
    if thin; then
        echo "Yours:  $NAME $(locked .nodes.meccanicos.locked.rev | cut -c1-7) of $(day "$(locked .nodes.meccanicos.locked.lastModified)")"
    else
        echo "Yours:  $NAME $(cat "$DEST/.mos-commit" 2>/dev/null || echo "?") (/etc/nixos is a full copy: mos-upgrade moves it to the new layout)"
    fi
    echo "Newest: $NAME $(jq -r '.revision' <<<"$latest" | cut -c1-7) of $(day "$(jq -r '.lastModified' <<<"$latest")")"
    echo "NixOS packages ($ref): yours of $(day "$(locked .nodes.nixpkgs.locked.lastModified)"), newest of $(day "$(jq -r '.lastModified // empty' <<<"$packages")")"
    exit 0
fi

migrated=0
if ! thin && [[ $mode != auto ]]; then
    echo "Moving $DEST to the new layout: your own files stay; the rest comes from"
    echo "$NAME's latest release from now on. The old copy is kept in $DEST.previous."
    rm -rf "$DEST.previous"
    cp -a "$DEST" "$DEST.previous"
    keep=()
    for f in "${KEEP[@]}"; do keep+=(! -name "$f"); done
    find "$DEST" -mindepth 1 -maxdepth 1 "${keep[@]}" -exec rm -rf {} +
    install -m 644 "$TEMPLATE" "$DEST/flake.nix"
    migrated=1
fi

# Put things back as they were (the rebuild failed, or Ctrl+C).
undo() {
    if ((migrated)); then
        rm -rf "$DEST"
        mv "$DEST.previous" "$DEST"
    else
        [[ -e $DEST/flake.lock.previous ]] && cp "$DEST/flake.lock.previous" "$DEST/flake.lock"
        [[ -e $DEST/flake.nix.previous ]] && cp "$DEST/flake.nix.previous" "$DEST/flake.nix"
    fi
    return 0
}
trap 'echo; echo "Stopped: putting the previous $DEST back." >&2; undo; exit 130' INT TERM

cp "$DEST/flake.nix" "$DEST/flake.nix.previous"
cp "$DEST/flake.lock" "$DEST/flake.lock.previous" 2>/dev/null || rm -f "$DEST/flake.lock.previous"
echo "Downloading the newest $NAME and NixOS packages..."
if ! nix flake update --flake "$DEST"; then
    undo
    echo "mos-upgrade: could not download the newest (offline?). Nothing changed." >&2
    exit 1
fi

# A release on a newer NixOS: follow it (its modules are written for it).
if thin; then
    src=$(nix flake archive --json "$DEST" | jq -r '.inputs.meccanicos.path')
    want=$(jq -r '.nodes.nixpkgs.original.ref // empty' "$src/flake.lock")
    have=$(locked .nodes.nixpkgs.original.ref)
    if [[ -n $want && -n $have && $want != "$have" ]]; then
        echo "$NAME now uses NixOS ${want#nixos-} (was ${have#nixos-}): following it."
        sed -i "s|github:NixOS/nixpkgs/$have\"|github:NixOS/nixpkgs/$want\"|" "$DEST/flake.nix"
        nix flake update --flake "$DEST"
    fi
fi

if ((!migrated)) && cmp -s "$DEST/flake.lock" "$DEST/flake.lock.previous"; then
    rm -f "$DEST/flake.nix.previous"
    echo "Already up to date: $NAME $(locked .nodes.meccanicos.locked.rev | cut -c1-7)."
    exit 0
fi

how=switch
[[ $mode == switch ]] || how=boot
echo "Building the new system ($how)..."
if nixos-rebuild "$how" --flake "$DEST#installed"; then
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
    echo "The new version did not build: putting the previous $DEST back." >&2
    undo
    exit 1
fi
