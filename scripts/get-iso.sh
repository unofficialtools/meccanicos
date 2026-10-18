#!/bin/sh
# get-iso.sh - download the latest MeccanicOS ISO in one step (Linux, macOS).
#
#   curl -fsSL https://raw.githubusercontent.com/unofficialtools/meccanicos/main/scripts/get-iso.sh | sh
#
# GitHub limits release files to 2 GB, so the ISO is published in parts. This
# downloads every part (resuming any that stopped half way: just run it again),
# checks each against SHA256SUMS, joins them (exactly the parts SHA256SUMS
# lists, in order) into the .iso in the current folder, checks the .iso before
# it replaces anything, and deletes the parts.
set -eu

base=${MECCANICOS_RELEASE:-https://github.com/unofficialtools/meccanicos/releases/download/latest}

sum() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "./$1"; else shasum -a 256 "./$1"; fi | cut -d' ' -f1
}
expected() { awk -v f="$1" '$2 == f { print $1 }' "$sums"; }
ok() { [ -f "$1" ] && [ "$(sum "$1")" = "$(expected "$1")" ]; }

# Files this run makes and does not keep: removed on any way out.
made=""
trap 'rm -f $made' EXIT
trap 'exit 130' INT TERM
set -f # names from SHA256SUMS are never globs

# SHA256SUMS, checked before it is used: "SHA256  NAME" lines, plain file
# names (no folders, no "..", none starting with "-"), each once. It replaces
# the SHA256SUMS here once it names an ISO and its parts.
new=SHA256SUMS.download.$$
sums=$new.ok
made="$made $new $sums"
curl -fsSL "$base/SHA256SUMS" -o "$new"
awk 'function bad(m) { print "get-iso: SHA256SUMS line " NR ": " m > "/dev/stderr"; exit 1 }
    NF == 0 { next }
    NF != 2 { bad("not \"SHA256  NAME\"") }
    { h = tolower($1); n = $2; sub(/^\*/, "", n) }
    length(h) != 64 || h ~ /[^0-9a-f]/ { bad("not a SHA256: " $1) }
    n == "" || n ~ /[\/\\]/ || n ~ /\.\./ || n ~ /^-/ { bad("not a plain file name: " n) }
    n in seen { bad(n " is listed twice") }
    { seen[n] = 1; print h "  " n }' "$new" >"$sums"
iso=$(awk '$2 ~ /\.iso$/ { print $2; exit }' "$sums")
[ -n "$iso" ] || { echo "get-iso: no .iso listed in SHA256SUMS" >&2; exit 1; }
# Exactly this ISO's parts, in order (ISO.part01, ISO.part02, ...).
parts=$(awk -v p="$iso.part" 'index($2, p) == 1 && substr($2, length(p) + 1) ~ /^[0-9]+$/ {
        print substr($2, length(p) + 1) + 0, $2 }' "$sums" | sort -n |
    awk '$1 == last { print "get-iso: SHA256SUMS lists part " $1 " twice" > "/dev/stderr"; exit 1 } { last = $1; print $2 }')
[ -n "$parts" ] || { echo "get-iso: SHA256SUMS lists no parts of $iso" >&2; exit 1; }
mv -f "$sums" SHA256SUMS
sums=SHA256SUMS
if ok "$iso"; then
    echo "$iso is already here and checks out."
    exit 0
fi

for part in $parts; do
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
# Into a file of its own, moved into place once checked.
joined=$iso.joining.$$
made="$made $joined"
: >"$joined"
for part in $parts; do cat "./$part" >>"$joined"; done
[ "$(sum "$joined")" = "$(expected "$iso")" ] ||
    { echo "get-iso: the joined $iso does not match SHA256SUMS" >&2; exit 1; }
mv -f "$joined" "$iso"
for part in $parts; do rm -f "./$part"; done
echo "Done: $iso (checked). Next: write it to a USB stick (see the README)."
