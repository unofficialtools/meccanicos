#!/usr/bin/env bash
# mos-update - bring an installed system up to the latest MeccanicOS.
# What it does: the help, below.
set -euo pipefail

# Translations (scripts/lib/mos_i18n.sh); without them, English.
# shellcheck source=/dev/null disable=SC2059
declare -F T >/dev/null || . "${MOS_I18N_SH:-$(dirname "$0")/lib/mos_i18n.sh}" 2>/dev/null ||
  { T() { printf '%s' "$1"; } && Tf() { local f=$1 && shift && printf -- "$f" "$@"; }; }
help=$(T 'mos-update - bring an installed system up to the latest MeccanicOS.

  mos-update            download the latest MeccanicOS, show what changed, apply it
  mos-update --boot     same, but switch at the next restart
  mos-update --check    only show what would change

/etc/nixos holds a copy of the MeccanicOS repository plus your own files.
This replaces the MeccanicOS part with the newest version from MECCANICOS_REPO
(set by the Nix wrapper from flake.nix), keeps your files (local.nix,
meccanicos.toml, hardware-configuration.nix, remote-unlock-keys) and rebuilds. The previous
/etc/nixos is kept in /etc/nixos.previous and restored if the rebuild fails;
older systems stay in the boot menu.

Needs a network connection. (mos-upgrade only refreshes NixOS packages.)')

REPO=${MECCANICOS_REPO:?}
BRANCH=${MECCANICOS_BRANCH:-main}
DEST=${MECCANICOS_NIXOS_DIR:-/etc/nixos}
KEEP=(local.nix meccanicos.toml hardware-configuration.nix remote-unlock-keys)

mode=switch
case ${1:-} in
    "") ;;
    --boot) mode=boot ;;
    --check) mode=check ;;
    -h | --help) printf '%s\n' "$help"; exit 0 ;;
    *) Tf 'unknown option: %s (try --help)\n' "$1" >&2; exit 2 ;;
esac
if [[ $EUID -ne 0 && $mode != check ]]; then exec sudo "$(readlink -f "$0")" "$@"; fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

Tf 'Downloading MeccanicOS from %s (%s)...\n' "$REPO" "$BRANCH"
git clone --quiet --depth 1 --branch "$BRANCH" "$REPO" "$tmp/new"
new=$(git -C "$tmp/new" rev-parse --short HEAD)
old=$(cat "$DEST/.mos-commit" 2>/dev/null || T 'the version you installed')
Tf 'Latest: %s  %s\n' "$new" "$(git -C "$tmp/new" log -1 --format='%cs  %s')"
Tf 'Yours:  %s\n' "$old"

excludes=(--exclude .git --exclude .mos-commit --exclude '*.previous')
for f in "${KEEP[@]}"; do excludes+=(--exclude "/$f"); done

changes=$(rsync -rlcn --delete --out-format='%n' "${excludes[@]}" "$tmp/new/" "$DEST/" | grep -v '/$' || true)
if [[ -z $changes && $old == "$new" ]]; then
    printf '%s\n' "$(T 'Already up to date.')"
    exit 0
fi
if [[ -n $changes ]]; then
    echo
    printf '%s\n' "$(T 'Files that change:')"
    while IFS= read -r f; do echo "  $f"; done <<<"$changes"
fi
[[ $mode == check ]] && exit 0

echo
printf '%s\n' "$(T 'Keeping the current /etc/nixos as /etc/nixos.previous')"
rm -rf "$DEST.previous"
cp -a "$DEST" "$DEST.previous"
rsync -rlc --delete "${excludes[@]}" "$tmp/new/" "$DEST/"
echo "$new" >"$DEST/.mos-commit"

Tf 'Building the new system (%s)...\n' "$mode"
if nixos-rebuild "$mode" --flake "$DEST#installed"; then
    echo
    if [[ $mode == boot ]]; then
        Tf 'Updated to MeccanicOS %s. Restart to use it.\n' "$new"
    else
        Tf 'Updated to MeccanicOS %s.\n' "$new"
    fi
    printf '%s\n' "$(T 'Something wrong? Pick the previous entry in the boot menu; the old files are in /etc/nixos.previous.')"
else
    echo
    printf '%s\n' "$(T 'The new version did not build: putting your previous /etc/nixos back.')" >&2
    rm -rf "$DEST"
    mv "$DEST.previous" "$DEST"
    exit 1
fi
