#!/usr/bin/env bash
# mos-look - bring your saved settings to this release's look.
#
#   mos-look           at login: if this release changed the look and your
#                      saved settings still differ from it, ask (a
#                      notification: Apply / Keep mine); asked once per change
#   mos-look apply     apply it now, without asking
#   mos-look --help    this help
#
# What it changes (only what your account saved; everything else follows
# the system on its own): no shadows under windows, menus and the top bar
# (the compositor sometimes leaves them on screen), and mc in MeccanicOS's
# colours (skin meccanicos256). New users start with these already.
set -uo pipefail

LOOK=${MOS_LOOK_VERSION:-0}
stamp="${XDG_CONFIG_HOME:-$HOME/.config}/meccanicos/look-version"
mcini="${XDG_CONFIG_HOME:-$HOME/.config}/mc/ini"
shadows=(show_frame_shadow show_dock_shadow show_popup_shadow)

# What differs from the look, one word each (nothing: all as it should be).
differs() {
    local s
    for s in "${shadows[@]}"; do
        [[ $(xfconf-query -c xfwm4 -p "/general/$s" 2>/dev/null) == true ]] && { echo shadows; break; }
    done
    if [[ -r $mcini ]] && grep -q '^skin=' "$mcini" && ! grep -qx 'skin=meccanicos256' "$mcini"; then
        echo mc
    fi
}

done_() { mkdir -p "${stamp%/*}" && echo "$LOOK" >"$stamp"; }

apply() {
    local s
    for s in "${shadows[@]}"; do
        xfconf-query -c xfwm4 -p "/general/$s" -n -t bool -s false
    done
    [[ -w $mcini ]] && sed -i 's/^skin=.*/skin=meccanicos256/' "$mcini"
    done_
}

case ${1:-} in
    -h | --help | help) sed -n '/^# mos-look - /,/^set -uo/p' "$0" | sed '$d; s/^# \{0,1\}//' ;;
    apply) apply && echo "mos-look: done (mc: the next time it starts)" ;;
    "")
        [[ $(cat "$stamp" 2>/dev/null) == "$LOOK" ]] && exit 0
        what=$(differs)
        [[ -z $what ]] && { done_; exit 0; }
        # Wait for the desktop's notifications to be up.
        sleep 15
        list=${what//$'\n'/, }
        list=${list/shadows/no shadows under windows}
        list=${list/mc/Midnight Commander in the new colours}
        choice=$(notify-send -a MeccanicOS -i preferences-system -u normal \
            --action=apply="Apply the new look" --action=keep="Keep mine" \
            "MECCANICOS // NEW LOOK" \
            "This update changes how MeccanicOS looks. Your account still has the old settings for: $list. Apply the new look? (Later: mos-look apply)")
        case $choice in
            apply) apply ;;
            keep) done_ ;;
        esac # closed without a choice: asked again at the next login
        ;;
    *) echo "mos-look: unknown option $1 (mos-look --help)" >&2; exit 2 ;;
esac
