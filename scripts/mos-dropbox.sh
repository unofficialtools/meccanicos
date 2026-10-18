#!/usr/bin/env bash
# mos-dropbox - Dropbox without the Dropbox app (through rclone).
#
#   mos-dropbox login [--browser]   connect your Dropbox account (once)
#   mos-dropbox mount               show Dropbox live in ~/Dropbox (online only)
#   mos-dropbox unmount             stop showing it
#   mos-dropbox sync                keep a local copy in ~/Dropbox, two-way:
#                                     now, then every 5 minutes (also after a restart)
#   mos-dropbox sync --resync       start the copy over (merge both sides again),
#                                     after changing the folder
#   mos-dropbox pause | resume      stop / restart the automatic sync
#   mos-dropbox status              account, mount, sync and the last sync
#   mos-dropbox logout              unmount, stop syncing, forget the account
#
# The folder is ~/Dropbox (MECCANICOS_DROPBOX_DIR to change it at login, mount or
# sync: it is remembered, and the automatic sync uses it too) and is created if
# needed. Mount and sync both use it, so only one of them at a time.
#
# Over SSH (no browser on this machine), login offers two ways:
#   - on your own computer run  rclone authorize "dropbox"  (or with Nix:
#     nix run nixpkgs#rclone -- authorize dropbox), sign in, paste the token;
#   - or reconnect with  ssh -L 53682:localhost:53682 ...,  run
#     mos-dropbox login --browser  and open the printed link locally.
set -euo pipefail

REMOTE=dropbox
STATE=${XDG_CONFIG_HOME:-$HOME/.config}/mos-dropbox
SYNC_STATE=$STATE/sync # "on" or "paused"; absent = not syncing
FOLDER=$STATE/folder   # the folder chosen (the timer has no MECCANICOS_DROPBOX_DIR)
RESYNCED=$STATE/resynced # "REMOTE: FOLDER" that the first sync merged
UNIT=mos-dropbox-sync
DIR=${MECCANICOS_DROPBOX_DIR:-$(cat "$FOLDER" 2>/dev/null || true)}
DIR=$(realpath -m -- "${DIR:-$HOME/Dropbox}")

die() { echo "mos-dropbox: $*" >&2; exit 1; }
have_remote() { rclone listremotes 2>/dev/null | grep -qx "$REMOTE:"; }
need_remote() { have_remote || die "not connected to Dropbox yet: run  mos-dropbox login"; }
is_mounted() { mountpoint -q "$DIR" 2>/dev/null; }
sync_state() { cat "$SYNC_STATE" 2>/dev/null || echo off; }
save_folder() { mkdir -p "$STATE" && printf '%s\n' "$DIR" >"$FOLDER"; }

# Run a command with a spinner and a note on stderr until it is done (for
# quiet waits on the network); just the note when stderr is not a terminal.
spin() {
    local note=$1 pid i=0 rc=0
    shift
    if [[ ! -t 2 ]]; then echo "$note" >&2; "$@"; return; fi
    local f=(⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏)
    [[ ${TERM:-} == linux ]] && f=("|" / - "\\") # no braille in the console font
    "$@" &
    pid=$!
    while kill -0 "$pid" 2>/dev/null; do
        printf '\r\033[K%s %s' "${f[i++ % ${#f[@]}]}" "$note" >&2
        sleep 0.1
    done
    wait "$pid" || rc=$?
    printf '\r\033[K' >&2
    return "$rc"
}

login() {
    if have_remote && [[ ${1:-} != --force ]]; then
        echo "Already connected to Dropbox (mos-dropbox logout first to use another account)."
        return
    fi
    if [[ ${1:-} == --browser || ( -n ${DISPLAY:-} && -z ${SSH_CONNECTION:-} ) ]]; then
        echo "Sign in to Dropbox in the browser (over SSH: open the link below on your computer,"
        echo "connected with  ssh -L 53682:localhost:53682 ...)."
        rclone config create "$REMOTE" dropbox >/dev/null
    else
        cat <<'EOF'
No browser here (SSH). On your own computer, with a browser, run:

    rclone authorize "dropbox"
      (no rclone there but Nix?  nix run nixpkgs#rclone -- authorize dropbox)

Sign in; it then prints a token like {"access_token":"...",...}.
Paste that whole line here. (Or: reconnect with  ssh -L 53682:localhost:53682 ...
and run  mos-dropbox login --browser .)
EOF
        local token
        read -r -p "Token: " token
        [[ $token == '{'*'}' ]] || die "that does not look like a token (it starts with { and ends with })."
        rclone config create "$REMOTE" dropbox token "$token" --non-interactive >/dev/null
    fi
    have_remote || die "the Dropbox account was not saved."
    save_folder
    echo "Connected. Next:  mos-dropbox mount  (live, online)  or  mos-dropbox sync  (local copy)"
}

mount_it() {
    need_remote
    is_mounted && { echo "Dropbox is already mounted at $DIR"; return; }
    [[ $(sync_state) == off ]] ||
        die "$DIR is your synced copy ($(sync_state)); to mount instead, first: mos-dropbox logout or move it"
    mkdir -p "$DIR"
    [[ -z $(ls -A "$DIR") ]] || die "$DIR is not empty; mount needs an empty folder (MECCANICOS_DROPBOX_DIR=... to use another)."
    spin "Connecting to Dropbox..." rclone mount "$REMOTE:" "$DIR" --vfs-cache-mode full --daemon
    save_folder
    echo "Dropbox is mounted at $DIR  (mos-dropbox unmount to stop)."
}

unmount_it() {
    is_mounted || { echo "Dropbox is not mounted."; return; }
    fusermount3 -u "$DIR" 2>/dev/null || fusermount -u "$DIR" ||
        die "could not unmount $DIR (files still open?)"
    echo "Unmounted $DIR"
}

# One two-way sync run (also what the timer runs). The first run merges both
# sides (--resync); after that, changes go both ways and newer edits win. The
# merge is for one account and folder: another folder needs sync --resync.
sync_once() {
    need_remote
    mkdir -p "$DIR" "$STATE"
    local first=() pair="$REMOTE: $DIR" was
    if [[ -e $RESYNCED ]]; then
        was=$(cat "$RESYNCED")
        # (empty: made by an older mos-dropbox, for the folder of then)
        [[ -z $was || $was == "$pair" ]] ||
            die "the synced copy is ${was#*: }, not $DIR (mos-dropbox sync --resync to start over with $DIR)"
    else
        first=(--resync)
    fi
    [[ -t 2 ]] && first+=(--stats 5s --stats-one-line) # by hand: show it is working
    flock -n "$STATE/lock" rclone bisync "$REMOTE:" "$DIR" "${first[@]}" \
        --create-empty-src-dirs --resilient --recover --conflict-resolve newer --verbose ||
        return 1
    printf '%s\n' "$pair" >"$RESYNCED"
}

# Sync is "on" only once the first sync worked and the timer is enabled.
sync_on() {
    need_remote
    is_mounted && die "Dropbox is mounted at $DIR; unmount it first (mos-dropbox unmount)."
    if [[ ${1:-} == --resync ]]; then
        [[ $(sync_state) == off ]] || echo paused >"$SYNC_STATE" # no timer run in between
        rm -f "$RESYNCED"
    elif [[ -n ${1:-} ]]; then
        echo "mos-dropbox: unknown option: $1 (mos-dropbox --help)" >&2
        exit 2
    fi
    echo "Syncing $DIR now (the first time copies everything; it can take a while)..."
    sync_once || die "the sync did not finish, so automatic sync is not turned on (mos-dropbox sync to try again)."
    save_folder # for the timer
    timer on || die "synced once, but automatic sync could not be turned on (mos-dropbox sync to try again)."
    echo on >"$SYNC_STATE"
    echo "Done. From now on it syncs every 5 minutes (mos-dropbox pause to stop)."
}

# The 5-minute timer runs only for users who sync: on with sync/resume,
# off with pause/logout (it is not enabled for anyone by default).
timer() {
    local verb=enable
    [[ $1 == on ]] || verb=disable
    systemctl --user "$verb" --now "$UNIT.timer" >/dev/null 2>&1 && return
    echo "mos-dropbox: could not $verb the $UNIT timer (systemctl --user $verb --now $UNIT.timer)" >&2
    return 1
}

case ${1:-status} in
    login) login "${2:-}" ;;
    mount) mount_it ;;
    unmount | umount) unmount_it ;;
    sync) sync_on "${2:-}" ;;
    pause)
        [[ $(sync_state) != off ]] || die "not syncing (mos-dropbox sync to start)."
        echo paused >"$SYNC_STATE" # the timer does nothing while paused, even if it stays enabled
        timer off || true
        echo "Sync paused (mos-dropbox resume to continue)."
        ;;
    resume)
        [[ $(sync_state) != off ]] || die "not syncing (mos-dropbox sync to start)."
        echo "Syncing now..."
        sync_once || die "the sync did not finish; still paused (mos-dropbox resume to try again)."
        timer on || die "synced, but automatic sync could not be turned on; still paused."
        echo on >"$SYNC_STATE"
        echo "Sync resumed."
        ;;
    tick) # run by the timer: the folder that was synced by hand
        [[ $(sync_state) == on ]] && have_remote || exit 0
        [[ -s $FOLDER ]] && DIR=$(cat "$FOLDER")
        sync_once
        ;;
    status)
        if have_remote; then echo "Account : connected"; else echo "Account : not connected (mos-dropbox login)"; fi
        echo "Folder  : $DIR"
        if is_mounted; then echo "Mount   : mounted"; else echo "Mount   : not mounted"; fi
        echo "Sync    : $(sync_state)"
        if [[ $(sync_state) != off ]]; then
            echo "Last sync:"
            journalctl --user -u "$UNIT" -n 3 --no-pager -o cat 2>/dev/null | sed 's/^/  /' || true
        fi
        ;;
    logout)
        is_mounted && unmount_it
        rm -f "$SYNC_STATE" "$RESYNCED" "$FOLDER"
        timer off || true
        have_remote && rclone config delete "$REMOTE"
        echo "Logged out. Your files in $DIR stay where they are."
        ;;
    -h | --help | help) sed -n '/^# mos-dropbox - /,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//' ;;
    *) echo "mos-dropbox: unknown command: $1 (mos-dropbox --help)" >&2; exit 2 ;;
esac
