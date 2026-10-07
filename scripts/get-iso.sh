#!/bin/sh
# get-iso.sh - download the latest MeccanicOS ISO in one step (Linux, macOS).
#
#   curl -fsSL https://raw.githubusercontent.com/unofficialtools/meccanicos/main/scripts/get-iso.sh | sh
#
# GitHub limits release files to 2 GB, so the ISO is published in parts. This
# downloads every part (resuming any that stopped half way: just run it again),
# checks each against SHA256SUMS, joins them into the .iso in the current
# folder, checks the .iso, and deletes the parts.
set -eu

base=${MECCANICOS_RELEASE:-https://github.com/unofficialtools/meccanicos/releases/download/latest}

sum() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1
}
expected() { awk -v f="$1" '$2 == f { print $1 }' SHA256SUMS; }
ok() { [ -f "$1" ] && [ "$(sum "$1")" = "$(expected "$1")" ]; }

curl -fsSL "$base/SHA256SUMS" -o SHA256SUMS
iso=$(awk '$2 ~ /\.iso$/ { print $2; exit }' SHA256SUMS)
[ -n "$iso" ] || { echo "get-iso: no .iso listed in SHA256SUMS" >&2; exit 1; }
if ok "$iso"; then
    echo "$iso is already here and checks out."
    exit 0
fi

for part in $(awk '$2 ~ /\.iso\.part[0-9]+$/ { print $2 }' SHA256SUMS); do
    if ok "$part"; then
        echo "$part: already downloaded"
        continue
    fi
    echo "$part:"
    # -C -: carry on from where an earlier try stopped.
    curl -fL -C - "$base/$part" -o "$part" || true
    if ! ok "$part"; then
        # A damaged start can't be resumed: once more, from the beginning.
        rm -f "$part"
        curl -fL "$base/$part" -o "$part"
        ok "$part" || { echo "get-iso: $part does not match SHA256SUMS; run again" >&2; exit 1; }
    fi
done

echo "Joining the parts into $iso..."
cat "$iso".part* >"$iso"
ok "$iso" || { echo "get-iso: the joined $iso does not match SHA256SUMS" >&2; exit 1; }
rm -f "$iso".part*
echo "Done: $iso (checked). Next: write it to a USB stick (see the README)."
