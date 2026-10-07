#!/usr/bin/env bash
# mos-autorotate - turn portrait-native screens into landscape.
#
#   mos-autorotate        (no options; runs by itself when X starts)
#
# Turns natively portrait panels (taller than wide, as on many tablets and
# handhelds) 90° clockwise into landscape, and maps touchscreens and pens to
# the rotated screen. Mice and touchpads follow the rotation by themselves.
# Runs when X starts (greeter) and again at login; does nothing on screens
# that are already landscape or rotated, or when the installer's
# "Screen: Portrait" was chosen (ORIENTATION=portrait in /etc/meccanicos/settings).
set -uo pipefail

case ${1-} in
    "") ;;
    -h | --help | help) sed -n '/^# mos-autorotate - /,/^set -uo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
    *) echo "mos-autorotate: unknown option $1 (mos-autorotate --help)" >&2; exit 2 ;;
esac

ORIENTATION=
# shellcheck disable=SC1091
[[ -r /etc/meccanicos/settings ]] && . /etc/meccanicos/settings
[[ $ORIENTATION == portrait ]] && exit 0

# "eDP-1 connected primary 800x1280+0+0 (normal left inverted right …) 155mm x 248mm"
# An unrotated output has "(" right after its geometry; a rotated one has
# "left"/"right"/"inverted" there.
rotated=()
while read -r out _; do
    xrandr --output "$out" --rotate right && rotated+=("$out")
done < <(xrandr --query | awk '
    / connected/ {
        for (i = 3; i <= NF; i++) if ($i ~ /^[0-9]+x[0-9]+\+/) break
        if (i > NF || $(i + 1) !~ /^\(/) next
        split($i, g, /[x+]/)
        if (g[2] + 0 > g[1] + 0) print $1
    }')
((${#rotated[@]})) || exit 0

# Touchscreens/pens report absolute positions, so they must be told about the
# rotation. Map them to the built-in panel if it was rotated, else the first.
target=${rotated[0]}
for o in "${rotated[@]}"; do
    [[ $o == eDP* || $o == DSI* || $o == LVDS* ]] && target=$o && break
done
for id in $(xinput list --id-only 2>/dev/null); do
    info=$(xinput list --long "$id" 2>/dev/null) || continue
    grep -q 'slave  pointer' <<<"$info" || continue
    if grep -qi 'mode: direct' <<<"$info" || grep -qiE 'pen|stylus' <<<"${info%%$'\n'*}"; then
        xinput map-to-output "$id" "$target" || true
    fi
done
exit 0
