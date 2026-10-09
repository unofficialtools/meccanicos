#!/usr/bin/env bash
# mos-hidpi - scale the desktop's text to the screen (at every login).
#
#   mos-hidpi             measure and scale, if the screen changed
#   mos-hidpi --force     do it again
#   mos-hidpi --dry-run   only print what it measured
#   mos-hidpi --scale F   text F times its size (1, 1.25, ... 2.5) and keep
#                           it so ("manual"; mos-config display.scale)
#
# Text (fonts/DPI: the top bar, title bars, icon labels, terminals, the
# command bar) grows with the main screen: width/2048 on screens wider than
# 2048 pixels (2560: 1.25x, 3840: 1.875x), or more on small dense ones (a
# laptop's 2880 pixels in 13": 2x). The top bar grows to fit the text, title
# bars and the cursor follow; icons keep their size.
#
# Done again at login when the screen is not the one it was done for. A
# size picked in mos-config (display.scale) stays: it writes "manual" in
# the stamp. Settings → Appearance → Fonts changes it by hand too.
set -uo pipefail
# Translations (scripts/lib/mos_i18n.sh); without them, English.
# shellcheck source=/dev/null disable=SC2059
declare -F T >/dev/null || . "${MOS_I18N_SH:-$(dirname "$0")/lib/mos_i18n.sh}" 2>/dev/null ||
  { T() { printf '%s' "$1"; } && Tf() { local f=$1 && shift && printf -- "$f" "$@"; }; }

stamp="${XDG_CONFIG_HOME:-$HOME/.config}/meccanicos/hidpi-done"
force=0 dry=0 manual=""
while (($#)); do
    a=$1
    shift
    case $a in
        --force) force=1 ;;
        --dry-run) dry=1 ;;
        --scale)
            [[ ${1:-} =~ ^[0-9]+(\.[0-9]+)?$ ]] || { printf '%s\n' "$(T 'mos-hidpi: --scale needs a number, like 1.5')" >&2; exit 2; }
            # In hundredths, without bc: 1.5 -> 150.
            int=${1%%.*} frac=${1#*.}
            [[ $1 == *.* ]] || frac=0
            frac=${frac}00
            manual=$((10#$int * 100 + 10#${frac:0:2}))
            force=1
            shift
            ;;
        -h | --help | help) sed -n '/^# mos-hidpi - /,/^set -uo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
        *) Tf 'mos-hidpi: unknown option %s (mos-hidpi --help)\n' "$a" >&2; exit 2 ;;
    esac
done
[[ $force == 0 && $(cat "$stamp" 2>/dev/null) == manual ]] && exit 0

# "eDP-1 connected primary 2880x1800+0+0 (normal …) 302mm x 189mm"
# (|| true: a grep that finds nothing would end the script, as it runs with
# errexit and pipefail; often no screen is marked primary.)
line=$(xrandr --query | grep ' connected primary' | head -n1) || true
[[ -n $line ]] || line=$(xrandr --query | grep ' connected [0-9]' | head -n1) || true
[[ -n $line ]] || line=$(xrandr --query | grep ' connected' | head -n1) || true
px=$(grep -oE '[0-9]+x[0-9]+\+' <<<"$line" | head -n1 | cut -dx -f1) || true
mm=$(grep -oE '[0-9]+mm x [0-9]+mm' <<<"$line" | head -n1 | cut -dm -f1) || true
[[ -n $px ]] || { printf '%s\n' "$(T 'mos-hidpi: no screen found')" >&2; exit 1; }
[[ $force == 0 && $(cat "$stamp" 2>/dev/null) == "auto $px" ]] && exit 0

# The factor in hundredths: width/2048, at least 1, or the density's 1.5/2.
f=$((px * 100 / 2048))
[[ -n $manual ]] && f=$manual
((f < 100)) && f=100
dpi=unknown
if [[ -n $mm && $mm -gt 0 ]]; then
    dpi=$((px * 254 / (mm * 10)))
    if [[ -n $manual ]]; then :
    elif ((dpi >= 170 && f < 200)); then f=200
    elif ((dpi >= 135 && f < 150)); then f=150
    fi
fi
f=$(((f + 12) / 25 * 25)) # in steps of 0.25

xft=$((96 * f / 100))
cursor=$(((24 * f / 100 + 2) / 4 * 4))
panel=$((28 * f / 100))
# Title bars: the theme's own larger sizes.
if ((f >= 175)); then wm=Graphite-Dark-xhdpi
elif ((f >= 125)); then wm=Graphite-Dark-hdpi
else wm=Graphite-Dark
fi
echo "screen: ${px}px over ${mm:-?}mm (${dpi} dpi) -> x$((f / 100)).$(printf %02d $((f % 100))): Xft/DPI ${xft}, title bars ${wm}"
((dry)) && exit 0

xfconf-query -c xsettings -p /Xft/DPI -n -t int -s "$xft"
xfconf-query -c xsettings -p /Gtk/CursorThemeSize -n -t int -s "$cursor"
xfconf-query -c xfce4-panel -p /panels/panel-1/size -n -t uint -s "$panel"
xfconf-query -c xfce4-panel -p /panels/panel-1/icon-size -n -t uint -s 16 # icons stay as they are
xfconf-query -c xfwm4 -p /general/theme -n -t string -s "$wm"
mkdir -p "${stamp%/*}" && if [[ -n $manual ]]; then echo manual; else echo "auto $px"; fi >"$stamp"
