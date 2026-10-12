#!/usr/bin/env bash
# mos-status - what this session is and how your files are kept.
#
#   session   LIVE        from the USB stick, nothing kept at shutdown
#             PERSISTENT  from the USB stick, your home saved on it
#             INSTALLED   from this computer's disk
#   storage   ENCRYPTED   your home is on an encrypted (LUKS) device
#             RAM         your home is in memory: gone at shutdown
#             PLAIN       your home is on a disk that is not encrypted
#   vaults    how many USB vaults are unlocked right now
#   status    the two above in words: USB · NOT SAVED, USB · SAVED,
#             INSTALLED · ENCRYPTED or INSTALLED · NOT ENCRYPTED
#
#   mos-status            the above, one per line, plus network and battery
#   mos-status --panel    the top bar's indicator (xfce4-genmon XML)
#   mos-status --header   the command center's two header lines
#   mos-status --help     this help
#
# The top bar shows it next to the clock (click: System Info); the command
# center (Super+Space) shows it above the search.

set -euo pipefail

session() {
    if grep -Eq '^IMAGE_VERSION="?[^"]' /etc/os-release 2>/dev/null; then
        if [[ -e /dev/mapper/mos-home ]]; then echo PERSISTENT; else echo LIVE; fi
    else
        echo INSTALLED
    fi
}

storage() {
    local src
    src=$(findmnt -nvo SOURCE --target "$HOME" 2>/dev/null | head -n1) || true
    if [[ $src != /dev/* ]]; then
        echo RAM
    elif lsblk -nso TYPE "$src" 2>/dev/null | grep -qx crypt; then
        echo ENCRYPTED
    else
        echo PLAIN
    fi
}

vaults() {
    local n=0 m
    for m in /dev/mapper/usbvault-*; do [[ -e $m ]] && n=$((n + 1)); done
    echo "$n"
}

network() {
    local line
    line=$(nmcli -t -f TYPE,STATE,CONNECTION device 2>/dev/null | awk -F: '$2 == "connected" {print; exit}') || true
    case ${line%%:*} in
        wifi) echo "WI-FI ${line#*:connected:}" ;;
        ethernet) echo "ETHERNET" ;;
        "") echo "OFFLINE" ;;
        *) echo "${line%%:*}" | tr '[:lower:]' '[:upper:]' ;;
    esac
}

battery() {
    local b cap st
    for b in /sys/class/power_supply/BAT*; do
        [[ -r $b/capacity ]] || continue
        cap=$(<"$b/capacity") st=$(<"$b/status")
        case $st in Charging) echo "CHARGING ${cap}%" ;; *) echo "BATTERY ${cap}%" ;; esac
        return
    done
    echo "POWER"
}

# Session and storage in words, for the top bar and the command center.
summary() {
    case $1:$2 in
        LIVE:* | PERSISTENT:RAM) echo "USB · NOT SAVED" ;;
        PERSISTENT:*) echo "USB · SAVED" ;;
        *:ENCRYPTED) echo "INSTALLED · ENCRYPTED" ;;
        *) echo "INSTALLED · NOT ENCRYPTED" ;;
    esac
}

vaults_open() {
    case $1 in
        0) ;;
        1) echo "1 VAULT OPEN" ;;
        *) echo "$1 VAULTS OPEN" ;;
    esac
}

host() { uname -n | tr '[:lower:]' '[:upper:]'; }

# What each state means, for tooltips.
explain() {
    case $1 in
        LIVE) echo "Live session from the USB stick." ;;
        PERSISTENT) echo "Live session from the USB stick, with your home saved on it." ;;
        INSTALLED) echo "Installed on this computer." ;;
    esac
    case $2 in
        RAM) echo "Your files are in memory and are gone at shutdown (keep them: usb-vault create-home)." ;;
        ENCRYPTED) echo "Your files are on an encrypted disk." ;;
        PLAIN) echo "Your files are on a disk that is not encrypted." ;;
    esac
}

# Pango markup: & < > in names (a Wi-Fi network's) must not break it.
esc() { local s=${1//&/\&amp;}; s=${s//</\&lt;}; printf '%s' "${s//>/\&gt;}"; }

AMBER='#f8a800' DIM='#8b929a' TEXT='#e8e6e1'

panel() {
    local s st v lock sum txt tip
    s=$(session) st=$(storage) v=$(vaults)
    # Nerd Font lock / open lock
    if [[ $st == ENCRYPTED ]]; then lock=$''; else lock=$''; fi
    sum=$(summary "$s" "$st")
    txt="<span fgcolor='$DIM'>$lock</span> <span fgcolor='$TEXT'>${sum%% · *}</span><span fgcolor='$DIM'> · ${sum#* · }</span>"
    # An unlocked vault is something to lock before unplugging: amber.
    if ((v)); then
        txt+="  <span fgcolor='$AMBER'>$(vaults_open "$v")</span>"
    fi
    tip="$(explain "$s" "$st")"
    ((v)) && tip+=$'\n'"$v USB vault(s) unlocked (usb-vault close locks them)."
    printf '<txt>%s</txt><tool>%s</tool>' "$txt" "$(esc "$tip")"
    [[ -n ${MOS_STATUS_CLICK:-} ]] && printf '<txtclick>%s</txtclick>' "$MOS_STATUS_CLICK"
    printf '\n'
}

header() {
    local line v
    # The computer's name only once it has its own (as the top bar):
    # LIVE, not MECCANICOS // LIVE under MECCANICOS.
    local me
    me=$(whoami | tr '[:lower:]' '[:upper:]')
    if [[ $(uname -n) == "${MOS_DEFAULT_HOST:-}" ]]; then
        printf '%s\n' "$me"
    else
        printf '%s  //  %s\n' "$(host)" "$me"
    fi
    line="$(summary "$(session)" "$(storage)")   ·   $(network)   ·   $(battery)"
    v=$(vaults_open "$(vaults)")
    printf '%s\n' "$line${v:+   ·   $v}"
}

case ${1:-} in
    -h | --help | help) sed -n '/^# mos-status - /,/^$/p' "$0" | sed '$d; s/^# \{0,1\}//' ;;
    --panel) panel ;;
    --header) header ;;
    "")
        printf 'host      %s\n' "$(host)"
        printf 'session   %s\n' "$(session)"
        printf 'storage   %s\n' "$(storage)"
        printf 'status    %s\n' "$(summary "$(session)" "$(storage)")"
        printf 'vaults    %s unlocked\n' "$(vaults)"
        printf 'network   %s\n' "$(network)"
        printf 'power     %s\n' "$(battery)"
        ;;
    *) echo "mos-status: unknown option $1 (mos-status --help)" >&2; exit 2 ;;
esac
