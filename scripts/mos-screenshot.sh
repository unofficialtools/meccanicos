#!/usr/bin/env bash
# mos-screenshot - take a screenshot.
#
#   mos-screenshot [full]   the whole screen
#   mos-screenshot window   the active window
#   mos-screenshot area     an area you select with the mouse
#
# Saves to ~/Pictures/Screenshots and copies the image to the clipboard.
set -uo pipefail

mode=${1:-full}
case $mode in
    -h | --help | help) sed -n '/^# mos-screenshot - /,/^set -uo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
    full | window | area) ;;
    *) echo "mos-screenshot: unknown mode $mode (mos-screenshot --help)" >&2; exit 2 ;;
esac
dir="${XDG_PICTURES_DIR:-$HOME/Pictures}/Screenshots"
mkdir -p "$dir"
file="$dir/Screenshot_$(date +%Y-%m-%d_%H-%M-%S).png"

case $mode in
    full) maim --hidecursor "$file" ;;
    window) maim --hidecursor --window "$(xdotool getactivewindow)" "$file" ;;
    area) maim --hidecursor --select --bordersize=2 --color=0.62,0.71,0.78 "$file" || exit 0 ;;
esac || exit 1

xclip -selection clipboard -t image/png -i "$file"
notify-send -i "$file" -t 4000 "Screenshot copied" "Saved as ${file/#$HOME/\~}"
