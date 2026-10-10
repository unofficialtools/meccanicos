#!/usr/bin/env bash
# mos-backup - encrypted, incremental backups of your home folder (restic).
#
#   mos-backup init DEST         set up a backup in folder DEST (an external disk,
#                                  your USB vault, ~/Dropbox/backup, …) or in the
#                                  cloud: REMOTE:FOLDER, any rclone account you have
#                                  (dropbox:backup after mos-dropbox login); asks
#                                  for a backup password, kept so automatic
#                                  backups can run
#   mos-backup init DEST --ask-password
#                                  the same, but the password is kept nowhere:
#                                  every command that opens the backup asks for
#                                  it (for one-off backups; none automatic)
#   mos-backup now               back up now
#   mos-backup list              list snapshots
#   mos-backup browse            get files back, full screen: pick a backup, browse
#                                  it, mark files and folders, restore them
#   mos-backup files [ID] [PATH] what is in folder PATH (default: ~) of snapshot ID
#                                  (default: latest); PATH may be relative to ~
#   mos-backup find NAME         which snapshots have a file called NAME (* and ? work)
#   mos-backup versions FILE     the backed-up versions of FILE: when, size, changed
#   mos-backup versions FILE --restore ID
#                                  put that version next to FILE as
#                                  "name (YYYY-MM-DD HHMM).ext"; FILE is not touched
#   mos-backup versions FILE --menu
#                                  pick a version full screen (Files: right-click,
#                                  Versions from Backups…; yazi: B)
#   mos-backup restore [ID] [TO] restore snapshot ID (default: latest) into folder TO
#                                  (default: ~/Restored-<date>); never overwrites ~.
#                                  In a terminal, with no ID: same as browse
#   mos-backup restore ID [TO] --only PATH...
#                                  restore only these files or folders (as files shows
#                                  them, or relative to ~) into TO
#   mos-backup mount             every backup as a read-only folder per date in
#                                  ~/Backups, opened in Files
#   mos-backup unmount           close ~/Backups
#   mos-backup auto on|hourly|off
#                                  automatic backups: nightly (on; a missed night
#                                  runs at the next start), hourly, or none. They
#                                  skip quietly when DEST is not reachable
#   mos-backup status            where, when, how big, the next automatic backup
#
# Backups are encrypted with your backup password and deduplicated, so daily
# runs are fast and small. Lose the password and the backup cannot be read.
# Old backups are thinned like Time Machine: all of the last 24 hours, then
# one a day for a month, one a week for a year, one a month for two years.
# A backup disk under /run/media (plugged in, opened by Files) is backed up
# to when it appears, if the last backup is over 12 hours old; a new USB
# disk, with no backup set up yet, gets one "Use it for backups?" notification.
set -euo pipefail

CONF="${XDG_CONFIG_HOME:-$HOME/.config}/meccanicos"
# systemctl --user (the automatic backups) also from `su - USER`, which has none.
[[ -n ${XDG_RUNTIME_DIR:-} || ! -d /run/user/$UID ]] || export XDG_RUNTIME_DIR=/run/user/$UID
ENV="$CONF/backup.env"
PASSFILE="$CONF/backup.pass"
LAST="$CONF/backup.last"     # when the last backup finished (seconds)
PRUNED="$CONF/backup.pruned" # when old data was last pruned (slow: weekly)
MNT="$HOME/Backups"          # mos-backup mount

# Where the backup is (RESTIC_REPOSITORY), without its password.
load_repo() {
    [[ -f $ENV ]] || { echo "No backup set up yet. Run: mos-backup init /path/to/folder" >&2; exit 1; }
    # shellcheck source=/dev/null
    . "$ENV"
    export RESTIC_REPOSITORY
}

# Where it is and its password: the saved one, or (init --ask-password) asked
# now and kept only in this command's memory (restic, and the browse window,
# get it from RESTIC_PASSWORD).
load() {
    load_repo
    if [[ -f $PASSFILE ]]; then
        export RESTIC_PASSWORD_FILE="$PASSFILE"
        return
    fi
    if [[ -z ${RESTIC_PASSWORD:-} ]]; then
        [[ -t 0 ]] || { echo "This backup's password is not saved (init --ask-password): run mos-backup in a terminal." >&2; exit 4; }
        read -r -s -p "Backup password: " RESTIC_PASSWORD
        echo >&2
    fi
    export RESTIC_PASSWORD
}

excludes() {
    local repo=$1
    printf '%s\n' \
        "$HOME/.cache" "$HOME/.local/share/Trash" "$HOME/.dropbox-dist" \
        "$HOME/.local/share/containers" "$HOME/Vault" "$HOME/Vault-*" \
        "$HOME/.mozilla/firefox/*/cache2" "$HOME/.config/BraveSoftware/*/*/Cache" \
        "$HOME/Restored-*"
    # never back the backup up into itself (nor mos-backup mount's view of it;
    # a folder of your own called Backups is backed up as usual)
    [[ $repo == "$HOME"/* ]] && echo "$repo"
    mountpoint -q "$MNT" 2>/dev/null && echo "$MNT"
    return 0
}

# A cloud backup (restic's rclone backend)?
cloud() { [[ $RESTIC_REPOSITORY == rclone:* ]]; }

# Can the backup be reached right now? Never hangs: the cloud gets 30 s.
reachable() {
    if cloud; then
        timeout 30 rclone lsf --max-depth 1 --contimeout 10s --timeout 20s --retries 1 \
            --low-level-retries 1 "${RESTIC_REPOSITORY#rclone:}" >/dev/null 2>&1
    else
        [[ -d ${RESTIC_REPOSITORY%/*} ]]
    fi
}

# A desktop notification, if there is a desktop; never fails.
notify() {
    command -v notify-send >/dev/null && [[ -n ${DISPLAY:-} || -n ${DBUS_SESSION_BUS_ADDRESS:-} ]] || return 0
    timeout 10 notify-send -a Backup -i "$1" "$2" "$3" 2>/dev/null || true
}

# Seconds since the last backup finished (a lot if never).
age() {
    local t
    t=$(cat "$LAST" 2>/dev/null || true)
    [[ $t =~ ^[0-9]+$ ]] || t=0
    echo $(($(date +%s) - t))
}

cmd_init() {
    local dest="" ask=0 a
    for a in "$@"; do
        case $a in
            --ask-password) ask=1 ;;
            -*) echo "usage: mos-backup init DEST [--ask-password]" >&2; exit 2 ;;
            *) [[ -z $dest ]] || { echo "usage: mos-backup init DEST [--ask-password]" >&2; exit 2; }; dest=$a ;;
        esac
    done
    [[ -n $dest ]] || { echo "usage: mos-backup init DEST [--ask-password]" >&2; exit 2; }
    local repo host remote remotes
    host=$(hostname)
    dest=${dest#rclone:}
    if [[ $dest =~ ^[A-Za-z0-9_.@+-]+: && ! -e $dest ]]; then
        # REMOTE:FOLDER, an rclone account (mos-dropbox login makes "dropbox")
        remote=${dest%%:*}
        remotes=$(rclone listremotes 2>/dev/null || true)
        grep -qxF "$remote:" <<<"$remotes" || {
            echo "No cloud account called '$remote' (rclone listremotes). For Dropbox: mos-dropbox login" >&2; exit 1; }
        [[ $dest == *: ]] || dest="${dest%/}/"
        repo="rclone:${dest}mos-backup-$host-$USER"
        mkdir -p "$CONF"
    else
        dest=$(readlink -f "$dest")
        mkdir -p "$dest" "$CONF"
        repo="$dest/mos-backup-$host-$USER"
    fi
    chmod 700 "$CONF"
    local p1 p2
    read -r -s -p "Backup password: " p1; echo
    read -r -s -p "Repeat password: " p2; echo
    [[ $p1 == "$p2" && ${#p1} -ge 8 ]] || { echo "Passwords differ or are shorter than 8 characters." >&2; exit 1; }
    (umask 077; printf 'RESTIC_REPOSITORY=%q\n' "$repo" >"$ENV")
    if ((ask)); then
        rm -f "$PASSFILE"
        export RESTIC_PASSWORD=$p1
        [[ -f $CONF/backup.nightly || -f $CONF/backup.hourly ]] && cmd_auto off
    else
        (umask 077; printf '%s' "$p1" >"$PASSFILE")
    fi
    load
    if ! restic cat config >/dev/null 2>&1; then restic init; fi
    if ((ask)); then
        echo "Backup ready at $repo. Its password is not saved: 'mos-backup now' (and every"
        echo "command that opens the backup) asks for it. No automatic backups."
    else
        echo "Backup ready at $repo. Run 'mos-backup now' (and 'mos-backup auto on' for nightly backups)."
    fi
}

# now [--auto | --plugged]: --auto (the timer) tells only of failures;
# --plugged (a disk appeared) backs up only if the last one is over 12 h old.
cmd_now() {
    local mode=${1:-manual}
    case $mode in manual | --auto | --plugged) ;; *) echo "usage: mos-backup now" >&2; exit 2 ;; esac
    if [[ $mode != manual && ! -f $PASSFILE ]]; then
        # No password to back up with by itself (init --ask-password): say so.
        if [[ $mode == --plugged ]] && (($(age) >= 12 * 3600)); then
            notify drive-removable-media "Backup disk plugged in" "Run mos-backup now in a terminal to back up (it asks for the password)."
        fi
        exit 0
    fi
    load
    exec 9>"$CONF/backup.lock"
    flock -n 9 || { echo "A backup is already running." >&2; exit 0; }
    reachable || { echo "Backup destination not available (disk unplugged? offline?): $RESTIC_REPOSITORY" >&2; exit 3; }
    if [[ $mode == --plugged ]] && (($(age) < 12 * 3600)); then exit 0; fi
    local ex rc=0
    ex=$(mktemp)
    excludes "$RESTIC_REPOSITORY" >"$ex"
    restic backup "$HOME" --exclude-file "$ex" --exclude-caches --one-file-system --tag meccanicos || rc=$?
    rm -f "$ex"
    # 3: saved, but some files could not be read (restic said which)
    if ((rc != 0 && rc != 3)); then
        [[ $mode == manual ]] || notify dialog-error "Backup failed" "Run mos-backup now in a terminal to see why."
        exit 1
    fi
    date +%s >"$LAST"
    thin
    [[ $mode == --auto ]] || notify document-save "Backup finished" "Your home folder is backed up."
}

# Time Machine's rule for which backups to keep (and every one of the last
# 24 h, so a backup made by hand is not merged into the hour's last one).
# Forgetting is quick; freeing
# the space (prune) reads much of the backup, so it runs at most weekly. Not
# while mos-backup mount has the backup open (it holds restic's lock).
thin() {
    mountpoint -q "$MNT" 2>/dev/null && return 0
    restic forget --tag meccanicos --keep-within 24h --keep-hourly 24 --keep-daily 30 --keep-weekly 52 --keep-monthly 24 >/dev/null ||
        { echo "(could not thin old backups this time)" >&2; return 0; }
    local t
    t=$(cat "$PRUNED" 2>/dev/null || true)
    [[ $t =~ ^[0-9]+$ ]] || t=0
    if (($(date +%s) - t > 7 * 86400)); then
        if restic prune >/dev/null; then date +%s >"$PRUNED"; else echo "(could not prune this time)" >&2; fi
    fi
    return 0
}

# PATH as it is in a snapshot: relative ones are under ~
snapshot_path() {
    local p=$1
    [[ $p == /* ]] || p="$HOME/$p"
    while [[ $p == */ && $p != / ]]; do p=${p%/}; done
    printf '%s' "$p"
}

# restic --include takes patterns: escape them so PATH matches only itself
literal() { printf '%s' "$1" | sed 's/[][\\*?]/\\&/g'; }

# Is PATH in snapshot ID? (restic ls lists nothing for a missing one)
in_snapshot() {
    local n
    n=$(restic ls --json "$1" "$2" 2>/dev/null | grep -c '"struct_type":"node"' || true)
    [[ ${n:-0} -gt 0 ]]
}

cmd_restore() {
    local args=() only=() inc=() p
    while (($#)); do
        case $1 in
            --only)
                shift
                (($#)) || { echo "usage: mos-backup restore ID [TO] --only PATH..." >&2; exit 2; }
                only=("$@"); break ;;
            *) args+=("$1"); shift ;;
        esac
    done
    # Typed in a terminal without saying what: let them pick.
    if ((${#args[@]} == 0 && ${#only[@]} == 0)) && [[ -t 0 && -t 1 ]]; then cmd_browse; fi
    load
    local id=${args[0]:-latest} to=${args[1]:-$HOME/Restored-$(date +%Y%m%d-%H%M)}
    # Restored files land in TO/home/..., so TO=/ would overwrite them in place.
    [[ $(readlink -m "$to") != / ]] || { echo "Restoring into / would overwrite your files: pick another folder." >&2; exit 2; }
    if ((${#args[@]} > 2)); then
        echo "usage: mos-backup restore [ID] [TO] [--only PATH...]" >&2; exit 2
    fi
    for p in "${only[@]}"; do
        p=$(snapshot_path "$p")
        in_snapshot "$id" "$p" || { echo "Not in backup $id: $p (see: mos-backup files $id)" >&2; exit 1; }
        inc+=(--include "$(literal "$p")")
    done
    mkdir -p "$to"
    restic restore "$id" --target "$to" "${inc[@]}"
    if ((${#only[@]})); then
        echo "Restored into $to:"
        for p in "${only[@]}"; do echo "  $to$(snapshot_path "$p")"; done
    else
        echo "Restored into $to (your files are under $to$HOME)."
    fi
}

cmd_files() {
    load
    local id=latest
    # One argument that does not look like a snapshot ID is a PATH.
    if (($# == 1)) && ! [[ $1 =~ ^(latest|[0-9a-f]{8,64})$ ]]; then set -- latest "$1"; fi
    (($# <= 2)) || { echo "usage: mos-backup files [ID] [PATH]" >&2; exit 2; }
    id=${1:-latest}
    local p out
    p=$(snapshot_path "${2:-$HOME}")
    out=$(restic ls -l "$id" "$p")
    [[ $out == *$'\n'* ]] || { echo "Not in backup $id: $p" >&2; exit 1; }
    printf '%s\n' "$out"
}

cmd_browse() {
    if [[ ! -f $ENV && -t 0 && -t 1 ]]; then
        # Started from the command bar: say why before the window closes.
        echo "No backup set up yet. Run: mos-backup init /path/to/folder"
        read -r -p "Press Enter to close. " || true
        exit 1
    fi
    load
    [[ -t 0 && -t 1 ]] || { echo "mos-backup browse needs a terminal (or: mos-backup files, mos-backup restore ID TO --only PATH)" >&2; exit 2; }
    export MECCANICOS_PYLIB
    exec "${MOS_BACKUP_PYTHON:-python3}" "${MOS_BACKUP_BROWSE:-$(dirname "$(readlink -f "$0")")/mos-backup-restore.py}"
}

# The timers (modules/backup.nix) run only while their file is in $CONF:
# backup.nightly or backup.hourly. That keeps the choice across restarts.
cmd_auto() {
    local mode=${1:-}
    case $mode in
        on | nightly) mode=nightly ;;
        hourly | off) ;;
        *) echo "usage: mos-backup auto on|hourly|off" >&2; exit 2 ;;
    esac
    if [[ $mode != off && -f $ENV && ! -f $PASSFILE ]]; then
        echo "Automatic backups need the password saved; this backup asks for it each time." >&2
        echo "To save it: mos-backup init DEST again, without --ask-password (same DEST and password)." >&2
        exit 1
    fi
    mkdir -p "$CONF"
    rm -f "$CONF/backup.nightly" "$CONF/backup.hourly"
    [[ $mode == off ]] || : >"$CONF/backup.$mode"
    systemctl --user stop mos-backup.timer mos-backup-hourly.timer 2>/dev/null || true
    local later="(it starts with your next login)"
    case $mode in
        nightly)
            systemctl --user start mos-backup.timer 2>/dev/null || echo "$later"
            echo "Nightly backups on (around 02:30; a missed night is made up at the next start)." ;;
        hourly)
            systemctl --user start mos-backup-hourly.timer 2>/dev/null || echo "$later"
            echo "Hourly backups on." ;;
        off) echo "Automatic backups off." ;;
    esac
}

schedule() {
    local mode=off timer=mos-backup.timer next
    if [[ -f $CONF/backup.hourly ]]; then mode=hourly timer=mos-backup-hourly.timer
    elif [[ -f $CONF/backup.nightly ]]; then mode=nightly; fi
    if [[ $mode != off ]]; then
        next=$(systemctl --user show "$timer" -p NextElapseUSecRealtime --value 2>/dev/null || true)
        [[ -n $next && $next != n/a ]] && mode="$mode, next: $next"
    fi
    echo "$mode"
}

cmd_status() {
    load_repo
    echo "Destination: $RESTIC_REPOSITORY"
    echo "Automatic:   $(schedule)"
    if [[ $RESTIC_REPOSITORY == /run/media/* || $RESTIC_REPOSITORY == /media/* ]]; then
        echo "             and when its disk is plugged in (if the last backup is over 12 h old)"
    fi
    local a
    a=$(age)
    if [[ -s $LAST ]]; then echo "Last backup: $((a / 3600)) h $((a % 3600 / 60)) min ago"; fi
    if [[ ! -f $PASSFILE ]]; then
        echo "Password:    not saved, asked each time (mos-backup list shows the backups)"
        return 0
    fi
    export RESTIC_PASSWORD_FILE="$PASSFILE"
    timeout 60 restic snapshots --tag meccanicos --latest 1 2>/dev/null || echo "(destination not reachable right now)"
    timeout 60 restic stats --mode raw-data 2>/dev/null | grep -i 'total size' || true
    if [[ -t 1 ]]; then echo "Get files back: mos-backup browse (or versions FILE, or mount)"; fi
}

# ---- mos-backup mount: every snapshot as a read-only folder -----------------
cmd_mount() {
    load
    if mountpoint -q "$MNT" 2>/dev/null; then
        echo "Already open: $MNT"
    else
        mkdir -p "$MNT"
        [[ -z $(ls -A "$MNT") ]] || { echo "$MNT has files of its own: rename that folder first." >&2; exit 1; }
        command -v fusermount3 >/dev/null || command -v fusermount >/dev/null ||
            { echo "mos-backup mount needs FUSE (fusermount3)." >&2; exit 1; }
        reachable || { echo "Backup destination not available (disk unplugged? offline?): $RESTIC_REPOSITORY" >&2; exit 3; }
        # restic stays in the background, serving the folder until unmount.
        setsid restic mount "$MNT" </dev/null >"$CONF/backup-mount.log" 2>&1 &
        local pid=$! i
        for ((i = 0; i < 120; i++)); do
            [[ -d $MNT/snapshots ]] && break
            kill -0 "$pid" 2>/dev/null || { tail -n 3 "$CONF/backup-mount.log" >&2; exit 1; }
            sleep 0.5
        done
        [[ -d $MNT/snapshots ]] || { echo "The backup did not open in time (see $CONF/backup-mount.log)." >&2; exit 1; }
    fi
    echo "Your backups, read-only, one folder per date: $MNT/snapshots"
    echo "Copy out what you need; close it with: mos-backup unmount"
    if [[ -n ${DISPLAY:-} ]] && command -v xdg-open >/dev/null; then
        setsid xdg-open "$MNT/snapshots" >/dev/null 2>&1 </dev/null &
    fi
    return 0
}

cmd_unmount() {
    mountpoint -q "$MNT" 2>/dev/null || { echo "Not open."; return 0; }
    fusermount3 -u "$MNT" 2>/dev/null || fusermount -u "$MNT" 2>/dev/null || umount "$MNT" ||
        { echo "Could not close $MNT (is a window still showing it?)." >&2; exit 1; }
    rmdir "$MNT" 2>/dev/null || true
    echo "Closed $MNT."
}

# ---- a disk appeared under /run/media (mos-backup-plugged.path) -------------
# A removable disk that is not the MeccanicOS stick: hot-plugged (USB, …), and
# no partition labelled like the stick's or holding the system.
removable() {
    local disk parts
    disk=$(lsblk -nsrpo NAME,TYPE "$1" 2>/dev/null | awk '$2 == "disk" { print $1; exit }' || true)
    [[ -n $disk && $(lsblk -ndo HOTPLUG "$disk" 2>/dev/null | tr -d ' ') == 1 ]] || return 1
    parts=$(lsblk -nrpo LABEL,MOUNTPOINT "$disk" 2>/dev/null || true)
    ! grep -qE '^(MOS-|[^ ]*_LIVE|Ventoy|VTOYEFI)|(^| )(/|/iso|/boot|/nix/store|/home)$' <<<"$parts"
}

cmd_plugged() {
    sleep "${MOS_BACKUP_SETTLE:-5}" # udisks makes the folder, then mounts on it
    if [[ -f $ENV ]]; then
        load_repo
        # Only for a backup on a plugged-in disk; cmd_now checks it is here and old.
        [[ $RESTIC_REPOSITORY == /run/media/* || $RESTIC_REPOSITORY == /media/* ]] || exit 0
        reachable || exit 0
        cmd_now --plugged
        exit
    fi
    # No backup yet: offer a newly plugged disk, once per disk.
    [[ -f $CONF/backup.noask ]] && exit 0
    command -v notify-send >/dev/null && [[ -n ${DISPLAY:-} || -n ${DBUS_SESSION_BUS_ADDRESS:-} ]] || exit 0
    local target src uuid name choice mounts
    mounts=$(findmnt -rn -o TARGET,SOURCE,UUID 2>/dev/null || true)
    while read -r target src uuid; do
        target=$(printf '%b' "$target") # findmnt writes a space as \x20
        [[ $target == "/run/media/$USER/"* && -n $uuid && -w $target ]] || continue
        grep -qxF "$uuid" "$CONF/backup.asked" 2>/dev/null && continue
        removable "$src" || continue
        mkdir -p "$CONF"
        echo "$uuid" >>"$CONF/backup.asked"
        name=${target##*/}
        choice=$(timeout 300 notify-send -a Backup -i drive-removable-media -t 120000 --wait \
            -A use="Use for backups" -A never="Don't ask again" "Use $name for backups?" \
            "Back up your home folder to it, encrypted, each time it is plugged in." 2>/dev/null || true)
        case $choice in
            use)
                # shellcheck disable=SC2016 # $1 is for the inner bash
                setsid xfce4-terminal --title "Set up backups" --hold -x bash -c \
                    'mos-backup init "$1" && mos-backup now && mos-backup auto on' _ "$target/MeccanicOS-backup" \
                    >/dev/null 2>&1 </dev/null & ;;
            never) : >"$CONF/backup.noask" ;;
        esac
        break # one question at a time
    done <<<"$mounts"
    return 0
}

cmd_versions() {
    [[ $# -gt 0 ]] || { echo "usage: mos-backup versions FILE [--restore ID | --menu]" >&2; exit 2; }
    if [[ " $* " == *" --menu "* && ! -f $ENV && -t 0 ]]; then
        # Started from Files or yazi: say why before the window closes.
        echo "No backup set up yet. Run: mos-backup init /path/to/folder"
        read -r -p "Press Enter to close. " || true
        exit 1
    fi
    load
    export MECCANICOS_PYLIB
    exec "${MOS_BACKUP_PYTHON:-python3}" "${MOS_BACKUP_BROWSE:-$(dirname "$(readlink -f "$0")")/mos-backup-restore.py}" versions "$@"
}

case ${1:-status} in
    init) shift; cmd_init "$@" ;;
    now) shift; cmd_now "$@" ;;
    list) load; restic snapshots --tag meccanicos ;;
    browse) cmd_browse ;;
    files) shift; cmd_files "$@" ;;
    find) shift; [[ $# -gt 0 ]] || { echo "usage: mos-backup find NAME" >&2; exit 2; }; load; restic find --tag meccanicos "$@" ;;
    restore) shift; cmd_restore "$@" ;;
    versions) shift; cmd_versions "$@" ;;
    mount) cmd_mount ;;
    unmount | umount) cmd_unmount ;;
    plugged) cmd_plugged ;;
    auto) shift; cmd_auto "$@" ;;
    status) cmd_status ;;
    -h | --help | help) sed -n '/^# mos-backup - /,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//' ;;
    *) echo "unknown command: $1 (try --help)" >&2; exit 2 ;;
esac
