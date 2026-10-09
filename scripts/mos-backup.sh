#!/usr/bin/env bash
# mos-backup - encrypted, incremental backups of your home folder (restic).
# What it does: the help, below.
set -euo pipefail

# Translations (scripts/lib/mos_i18n.sh); without them, English.
# shellcheck source=/dev/null disable=SC2059
declare -F T >/dev/null || . "${MOS_I18N_SH:-$(dirname "$0")/lib/mos_i18n.sh}" 2>/dev/null ||
  { T() { printf '%s' "$1"; } && Tf() { local f=$1 && shift && printf -- "$f" "$@"; }; }
help=$(T 'mos-backup - encrypted, incremental backups of your home folder (restic).

  mos-backup init DEST         set up a backup in folder DEST (an external disk,
                                 your USB vault, ~/Dropbox/backup, …) or in the
                                 cloud: REMOTE:FOLDER, any rclone account you have
                                 (dropbox:backup after mos-dropbox login); asks
                                 for a backup password
  mos-backup now               back up now
  mos-backup list              list snapshots
  mos-backup browse            get files back, full screen: pick a backup, browse
                                 it, mark files and folders, restore them
  mos-backup files [ID] [PATH] what is in folder PATH (default: ~) of snapshot ID
                                 (default: latest); PATH may be relative to ~
  mos-backup find NAME         which snapshots have a file called NAME (* and ? work)
  mos-backup versions FILE     the backed-up versions of FILE: when, size, changed
  mos-backup versions FILE --restore ID
                                 put that version next to FILE as
                                 "name (YYYY-MM-DD HHMM).ext"; FILE is not touched
  mos-backup versions FILE --menu
                                 pick a version full screen (Files: right-click,
                                 Versions from Backups…; yazi: B)
  mos-backup restore [ID] [TO] restore snapshot ID (default: latest) into folder TO
                                 (default: ~/Restored-<date>); never overwrites ~.
                                 In a terminal, with no ID: same as browse
  mos-backup restore ID [TO] --only PATH...
                                 restore only these files or folders (as files shows
                                 them, or relative to ~) into TO
  mos-backup mount             every backup as a read-only folder per date in
                                 ~/Backups, opened in Files
  mos-backup unmount           close ~/Backups
  mos-backup auto on|hourly|off
                                 automatic backups: nightly (on; a missed night
                                 runs at the next start), hourly, or none. They
                                 skip quietly when DEST is not reachable
  mos-backup status            where, when, how big, the next automatic backup

Backups are encrypted with your backup password and deduplicated, so daily
runs are fast and small. Lose the password and the backup cannot be read.
Old backups are thinned like Time Machine: all of the last 24 hours, then
one a day for a month, one a week for a year, one a month for two years.
A backup disk under /run/media (plugged in, opened by Files) is backed up
to when it appears, if the last backup is over 12 hours old; a new USB
disk, with no backup set up yet, gets one "Use it for backups?" notification.')

CONF="${XDG_CONFIG_HOME:-$HOME/.config}/meccanicos"
# systemctl --user (the automatic backups) also from `su - USER`, which has none.
[[ -n ${XDG_RUNTIME_DIR:-} || ! -d /run/user/$UID ]] || export XDG_RUNTIME_DIR=/run/user/$UID
ENV="$CONF/backup.env"
PASSFILE="$CONF/backup.pass"
LAST="$CONF/backup.last"     # when the last backup finished (seconds)
PRUNED="$CONF/backup.pruned" # when old data was last pruned (slow: weekly)
MNT="$HOME/Backups"          # mos-backup mount

load() {
    [[ -f $ENV ]] || { printf '%s\n' "$(T 'No backup set up yet. Run: mos-backup init /path/to/folder')" >&2; exit 1; }
    # shellcheck source=/dev/null
    . "$ENV"
    export RESTIC_REPOSITORY RESTIC_PASSWORD_FILE="$PASSFILE"
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
    local dest=${1:-}
    [[ -n $dest ]] || { printf '%s\n' "$(T 'usage: mos-backup init DEST')" >&2; exit 2; }
    local repo host remote remotes
    host=$(hostname)
    dest=${dest#rclone:}
    if [[ $dest =~ ^[A-Za-z0-9_.@+-]+: && ! -e $dest ]]; then
        # REMOTE:FOLDER, an rclone account (mos-dropbox login makes "dropbox")
        remote=${dest%%:*}
        remotes=$(rclone listremotes 2>/dev/null || true)
        grep -qxF "$remote:" <<<"$remotes" || {
            printf '%s\n' "$(Tf "No cloud account called '%s' (rclone listremotes). For Dropbox: mos-dropbox login" "$remote")" >&2; exit 1; }
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
    read -r -s -p "$(T 'Backup password: ')" p1; echo
    read -r -s -p "$(T 'Repeat password: ')" p2; echo
    [[ $p1 == "$p2" && ${#p1} -ge 8 ]] || { printf '%s\n' "$(T 'Passwords differ or are shorter than 8 characters.')" >&2; exit 1; }
    (umask 077; printf '%s' "$p1" >"$PASSFILE")
    (umask 077; printf 'RESTIC_REPOSITORY=%q\n' "$repo" >"$ENV")
    load
    if ! restic cat config >/dev/null 2>&1; then restic init; fi
    printf '%s\n' "$(Tf "Backup ready at %s. Run 'mos-backup now' (and 'mos-backup auto on' for nightly backups)." "$repo")"
}

# now [--auto | --plugged]: --auto (the timer) tells only of failures;
# --plugged (a disk appeared) backs up only if the last one is over 12 h old.
cmd_now() {
    local mode=${1:-manual}
    case $mode in manual | --auto | --plugged) ;; *) printf '%s\n' "$(T 'usage: mos-backup now')" >&2; exit 2 ;; esac
    load
    exec 9>"$CONF/backup.lock"
    flock -n 9 || { printf '%s\n' "$(T 'A backup is already running.')" >&2; exit 0; }
    reachable || { Tf 'Backup destination not available (disk unplugged? offline?): %s\n' "$RESTIC_REPOSITORY" >&2; exit 3; }
    if [[ $mode == --plugged ]] && (($(age) < 12 * 3600)); then exit 0; fi
    local ex rc=0
    ex=$(mktemp)
    excludes "$RESTIC_REPOSITORY" >"$ex"
    restic backup "$HOME" --exclude-file "$ex" --exclude-caches --one-file-system --tag meccanicos || rc=$?
    rm -f "$ex"
    # 3: saved, but some files could not be read (restic said which)
    if ((rc != 0 && rc != 3)); then
        [[ $mode == manual ]] || notify dialog-error "$(T 'Backup failed')" "$(T 'Run mos-backup now in a terminal to see why.')"
        exit 1
    fi
    date +%s >"$LAST"
    thin
    [[ $mode == --auto ]] || notify document-save "$(T 'Backup finished')" "$(T 'Your home folder is backed up.')"
}

# Time Machine's rule for which backups to keep (and every one of the last
# 24 h, so a backup made by hand is not merged into the hour's last one).
# Forgetting is quick; freeing
# the space (prune) reads much of the backup, so it runs at most weekly. Not
# while mos-backup mount has the backup open (it holds restic's lock).
thin() {
    mountpoint -q "$MNT" 2>/dev/null && return 0
    restic forget --tag meccanicos --keep-within 24h --keep-hourly 24 --keep-daily 30 --keep-weekly 52 --keep-monthly 24 >/dev/null ||
        { printf '%s\n' "$(T '(could not thin old backups this time)')" >&2; return 0; }
    local t
    t=$(cat "$PRUNED" 2>/dev/null || true)
    [[ $t =~ ^[0-9]+$ ]] || t=0
    if (($(date +%s) - t > 7 * 86400)); then
        if restic prune >/dev/null; then date +%s >"$PRUNED"; else printf '%s\n' "$(T '(could not prune this time)')" >&2; fi
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
                (($#)) || { printf '%s\n' "$(T 'usage: mos-backup restore ID [TO] --only PATH...')" >&2; exit 2; }
                only=("$@"); break ;;
            *) args+=("$1"); shift ;;
        esac
    done
    # Typed in a terminal without saying what: let them pick.
    if ((${#args[@]} == 0 && ${#only[@]} == 0)) && [[ -t 0 && -t 1 ]]; then cmd_browse; fi
    load
    local id=${args[0]:-latest} to=${args[1]:-$HOME/Restored-$(date +%Y%m%d-%H%M)}
    # Restored files land in TO/home/..., so TO=/ would overwrite them in place.
    [[ $(readlink -m "$to") != / ]] || { printf '%s\n' "$(T 'Restoring into / would overwrite your files: pick another folder.')" >&2; exit 2; }
    if ((${#args[@]} > 2)); then
        printf '%s\n' "$(T 'usage: mos-backup restore [ID] [TO] [--only PATH...]')" >&2; exit 2
    fi
    for p in "${only[@]}"; do
        p=$(snapshot_path "$p")
        in_snapshot "$id" "$p" || { Tf 'Not in backup %s: %s (see: mos-backup files %s)\n' "$id" "$p" "$id" >&2; exit 1; }
        inc+=(--include "$(literal "$p")")
    done
    mkdir -p "$to"
    restic restore "$id" --target "$to" "${inc[@]}"
    if ((${#only[@]})); then
        Tf 'Restored into %s:\n' "$to"
        for p in "${only[@]}"; do echo "  $to$(snapshot_path "$p")"; done
    else
        Tf 'Restored into %s (your files are under %s).\n' "$to" "$to$HOME"
    fi
}

cmd_files() {
    load
    local id=latest
    # One argument that does not look like a snapshot ID is a PATH.
    if (($# == 1)) && ! [[ $1 =~ ^(latest|[0-9a-f]{8,64})$ ]]; then set -- latest "$1"; fi
    (($# <= 2)) || { printf '%s\n' "$(T 'usage: mos-backup files [ID] [PATH]')" >&2; exit 2; }
    id=${1:-latest}
    local p out
    p=$(snapshot_path "${2:-$HOME}")
    out=$(restic ls -l "$id" "$p")
    [[ $out == *$'\n'* ]] || { Tf 'Not in backup %s: %s\n' "$id" "$p" >&2; exit 1; }
    printf '%s\n' "$out"
}

cmd_browse() {
    if [[ ! -f $ENV && -t 0 && -t 1 ]]; then
        # Started from the command bar: say why before the window closes.
        printf '%s\n' "$(T 'No backup set up yet. Run: mos-backup init /path/to/folder')"
        read -r -p "$(T 'Press Enter to close. ')" || true
        exit 1
    fi
    load
    [[ -t 0 && -t 1 ]] || { printf '%s\n' "$(T 'mos-backup browse needs a terminal (or: mos-backup files, mos-backup restore ID TO --only PATH)')" >&2; exit 2; }
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
        *) printf '%s\n' "$(T 'usage: mos-backup auto on|hourly|off')" >&2; exit 2 ;;
    esac
    mkdir -p "$CONF"
    rm -f "$CONF/backup.nightly" "$CONF/backup.hourly"
    [[ $mode == off ]] || : >"$CONF/backup.$mode"
    systemctl --user stop mos-backup.timer mos-backup-hourly.timer 2>/dev/null || true
    local later
    later=$(T '(it starts with your next login)')
    case $mode in
        nightly)
            systemctl --user start mos-backup.timer 2>/dev/null || echo "$later"
            printf '%s\n' "$(T 'Nightly backups on (around 02:30; a missed night is made up at the next start).')" ;;
        hourly)
            systemctl --user start mos-backup-hourly.timer 2>/dev/null || echo "$later"
            printf '%s\n' "$(T 'Hourly backups on.')" ;;
        off) printf '%s\n' "$(T 'Automatic backups off.')" ;;
    esac
}

schedule() {
    local mode timer=mos-backup.timer next
    mode=$(T 'off')
    if [[ -f $CONF/backup.hourly ]]; then mode=$(T 'hourly') timer=mos-backup-hourly.timer
    elif [[ -f $CONF/backup.nightly ]]; then mode=$(T 'nightly')
    else echo "$mode"; return 0; fi
    next=$(systemctl --user show "$timer" -p NextElapseUSecRealtime --value 2>/dev/null || true)
    if [[ -n $next && $next != n/a ]]; then Tf '%s, next: %s\n' "$mode" "$next"; else echo "$mode"; fi
}

cmd_status() {
    load
    Tf 'Destination: %s\n' "$RESTIC_REPOSITORY"
    Tf 'Automatic:   %s\n' "$(schedule)"
    if [[ $RESTIC_REPOSITORY == /run/media/* || $RESTIC_REPOSITORY == /media/* ]]; then
        printf '             %s\n' "$(T 'and when its disk is plugged in (if the last backup is over 12 h old)')"
    fi
    local a
    a=$(age)
    if [[ -s $LAST ]]; then Tf 'Last backup: %s h %s min ago\n' "$((a / 3600))" "$((a % 3600 / 60))"; fi
    timeout 60 restic snapshots --tag meccanicos --latest 1 2>/dev/null || printf '%s\n' "$(T '(destination not reachable right now)')"
    timeout 60 restic stats --mode raw-data 2>/dev/null | grep -i 'total size' || true
    if [[ -t 1 ]]; then printf '%s\n' "$(T 'Get files back: mos-backup browse (or versions FILE, or mount)')"; fi
}

# ---- mos-backup mount: every snapshot as a read-only folder -----------------
cmd_mount() {
    load
    if mountpoint -q "$MNT" 2>/dev/null; then
        Tf 'Already open: %s\n' "$MNT"
    else
        mkdir -p "$MNT"
        [[ -z $(ls -A "$MNT") ]] || { Tf '%s has files of its own: rename that folder first.\n' "$MNT" >&2; exit 1; }
        command -v fusermount3 >/dev/null || command -v fusermount >/dev/null ||
            { printf '%s\n' "$(T 'mos-backup mount needs FUSE (fusermount3).')" >&2; exit 1; }
        reachable || { Tf 'Backup destination not available (disk unplugged? offline?): %s\n' "$RESTIC_REPOSITORY" >&2; exit 3; }
        # restic stays in the background, serving the folder until unmount.
        setsid restic mount "$MNT" </dev/null >"$CONF/backup-mount.log" 2>&1 &
        local pid=$! i
        for ((i = 0; i < 120; i++)); do
            [[ -d $MNT/snapshots ]] && break
            kill -0 "$pid" 2>/dev/null || { tail -n 3 "$CONF/backup-mount.log" >&2; exit 1; }
            sleep 0.5
        done
        [[ -d $MNT/snapshots ]] || { Tf 'The backup did not open in time (see %s).\n' "$CONF/backup-mount.log" >&2; exit 1; }
    fi
    Tf 'Your backups, read-only, one folder per date: %s\n' "$MNT/snapshots"
    printf '%s\n' "$(T 'Copy out what you need; close it with: mos-backup unmount')"
    if [[ -n ${DISPLAY:-} ]] && command -v xdg-open >/dev/null; then
        setsid xdg-open "$MNT/snapshots" >/dev/null 2>&1 </dev/null &
    fi
    return 0
}

cmd_unmount() {
    mountpoint -q "$MNT" 2>/dev/null || { printf '%s\n' "$(T 'Not open.')"; return 0; }
    fusermount3 -u "$MNT" 2>/dev/null || fusermount -u "$MNT" 2>/dev/null || umount "$MNT" ||
        { Tf 'Could not close %s (is a window still showing it?).\n' "$MNT" >&2; exit 1; }
    rmdir "$MNT" 2>/dev/null || true
    Tf 'Closed %s.\n' "$MNT"
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
        load
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
            -A use="$(T 'Use for backups')" -A never="$(T "Don't ask again")" "$(Tf 'Use %s for backups?' "$name")" \
            "$(T 'Back up your home folder to it, encrypted, each time it is plugged in.')" 2>/dev/null || true)
        case $choice in
            use)
                # shellcheck disable=SC2016 # $1 is for the inner bash
                setsid xfce4-terminal --title "$(T 'Set up backups')" --hold -x bash -c \
                    'mos-backup init "$1" && mos-backup now && mos-backup auto on' _ "$target/MeccanicOS-backup" \
                    >/dev/null 2>&1 </dev/null & ;;
            never) : >"$CONF/backup.noask" ;;
        esac
        break # one question at a time
    done <<<"$mounts"
    return 0
}

cmd_versions() {
    [[ $# -gt 0 ]] || { printf '%s\n' "$(T 'usage: mos-backup versions FILE [--restore ID | --menu]')" >&2; exit 2; }
    if [[ " $* " == *" --menu "* && ! -f $ENV && -t 0 ]]; then
        # Started from Files or yazi: say why before the window closes.
        printf '%s\n' "$(T 'No backup set up yet. Run: mos-backup init /path/to/folder')"
        read -r -p "$(T 'Press Enter to close. ')" || true
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
    find) shift; [[ $# -gt 0 ]] || { printf '%s\n' "$(T 'usage: mos-backup find NAME')" >&2; exit 2; }; load; restic find --tag meccanicos "$@" ;;
    restore) shift; cmd_restore "$@" ;;
    versions) shift; cmd_versions "$@" ;;
    mount) cmd_mount ;;
    unmount | umount) cmd_unmount ;;
    plugged) cmd_plugged ;;
    auto) shift; cmd_auto "$@" ;;
    status) cmd_status ;;
    -h | --help | help) printf '%s\n' "$help" ;;
    *) Tf 'unknown command: %s (try --help)\n' "$1" >&2; exit 2 ;;
esac
