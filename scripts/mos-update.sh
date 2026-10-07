#!/usr/bin/env bash
# mos-update - bring an installed system up to the latest MeccanicOS.
#
#   mos-update            download the latest MeccanicOS, show what changed, apply it
#   mos-update --boot     same, but switch at the next restart
#   mos-update --check    only show what would change
#
# /etc/nixos holds a copy of the MeccanicOS repository plus your own files.
# This replaces the MeccanicOS part with the newest version from MECCANICOS_REPO
# (set by the Nix wrapper from flake.nix), keeps your files (local.nix,
# meccanicos.toml, hardware-configuration.nix, remote-unlock-keys) and rebuilds. The previous
# /etc/nixos is kept in /etc/nixos.previous and restored if the rebuild fails;
# older systems stay in the boot menu.
#
# Needs a network connection. (mos-upgrade only refreshes NixOS packages.)
set -euo pipefail

REPO=${MECCANICOS_REPO:?}
BRANCH=${MECCANICOS_BRANCH:-main}
DEST=${MECCANICOS_NIXOS_DIR:-/etc/nixos}
KEEP=(local.nix meccanicos.toml hardware-configuration.nix remote-unlock-keys)

mode=switch
case ${1:-} in
    "") ;;
    --boot) mode=boot ;;
    --check) mode=check ;;
    -h | --help) sed -n '/^# mos-update - /,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
esac
if [[ $EUID -ne 0 && $mode != check ]]; then exec sudo "$(readlink -f "$0")" "$@"; fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

echo "Downloading MeccanicOS from $REPO ($BRANCH)..."
git clone --quiet --depth 1 --branch "$BRANCH" "$REPO" "$tmp/new"
new=$(git -C "$tmp/new" rev-parse --short HEAD)
old=$(cat "$DEST/.mos-commit" 2>/dev/null || echo "the version you installed")
echo "Latest: $new  $(git -C "$tmp/new" log -1 --format='%cs  %s')"
echo "Yours:  $old"

excludes=(--exclude .git --exclude .mos-commit --exclude '*.previous')
for f in "${KEEP[@]}"; do excludes+=(--exclude "/$f"); done

changes=$(rsync -rlcn --delete --out-format='%n' "${excludes[@]}" "$tmp/new/" "$DEST/" | grep -v '/$' || true)
if [[ -z $changes && $old == "$new" ]]; then
    echo "Already up to date."
    exit 0
fi
if [[ -n $changes ]]; then
    echo
    echo "Files that change:"
    while IFS= read -r f; do echo "  $f"; done <<<"$changes"
fi
[[ $mode == check ]] && exit 0

echo
echo "Keeping the current /etc/nixos as /etc/nixos.previous"
rm -rf "$DEST.previous"
cp -a "$DEST" "$DEST.previous"
rsync -rlc --delete "${excludes[@]}" "$tmp/new/" "$DEST/"
echo "$new" >"$DEST/.mos-commit"

echo "Building the new system ($mode)..."
if nixos-rebuild "$mode" --flake "$DEST#installed"; then
    echo
    if [[ $mode == boot ]]; then
        echo "Updated to MeccanicOS $new. Restart to use it."
    else
        echo "Updated to MeccanicOS $new."
    fi
    echo "Something wrong? Pick the previous entry in the boot menu; the old files are in /etc/nixos.previous."
else
    echo
    echo "The new version did not build: putting your previous /etc/nixos back." >&2
    rm -rf "$DEST"
    mv "$DEST.previous" "$DEST"
    exit 1
fi
