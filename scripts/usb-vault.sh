#!/usr/bin/env bash
# usb-vault - encrypted storage on the same USB stick the live system booted from.
# What it does, its commands, Ventoy and safety: help_text below (usb-vault --help).

# Translations (scripts/lib/mos_i18n.sh); without them, English.
# shellcheck source=/dev/null disable=SC2059
declare -F T >/dev/null || . "${MOS_I18N_SH:-$(dirname "$0")/lib/mos_i18n.sh}" 2>/dev/null ||
  { T() { printf '%s' "$1"; } && Tf() { local f=$1 && shift && printf -- "$f" "$@"; }; }

set -euo pipefail

VAULT_LABEL="${VAULT_LABEL:-MOS-VAULT}"
DATA_LABEL="${DATA_LABEL:-MOS-DATA}"
HOME_LABEL="${HOME_LABEL:-MOS-HOME}"
HOME_FILE="mos-home.luks" # persistent home as a file on the data partition
HEADROOM="${USB_VAULT_HEADROOM:-4G}"
MAP_MAGIC="MOS-VAULT-MAP-1"
ISO_LABEL="${ISO_LABEL:-MECCANICOS_LIVE}"
DATA_MNT="${DATA_MNT:-/run/usb-vault/data}"
GUI="${USB_VAULT_GUI:-0}"
VENTOY_MAP=mos-ventoy # our device-mapper view of the Ventoy partition

# The help, one translatable text per paragraph.
help_text() {
    printf '%s\n\n' "$(T 'usb-vault - encrypted storage on the same USB stick the live system booted from.')"
    printf '%s\n\n' "$(T 'Two kinds of vault, use either or both:
  * partition vault : a LUKS2 partition created in the free space after the ISO
  * file vault      : a LUKS2 container file (*.luks) stored on a plain exFAT
                      "data" partition, also in the free space after the ISO.
                      exFAT means the file can be copied/backed up from
                      Windows/macOS too.')"
    printf '%s\n\n' "$(T "Commands
  usb-vault status                         show the stick, free space and vaults,
                                           then the summary below
  usb-vault summary                        what survives a restart (files, apps,
                                           AI models, vaults) and the space left;
                                           also on an installed system
  usb-vault open [VAULT]                   unlock + mount (asks which if several)
  usb-vault close [VAULT|--all]            unmount + lock
  usb-vault create-partition [--size 8G]   new LUKS partition (default: all free space)
  usb-vault create-file [--size 4G] [--name vault.luks] [--data-size 16G]
                                           new container file on the data partition
                                           (creates the data partition if needed)
  usb-vault create-home [--size 16G] [--file]
                                           encrypted *persistent home*: your files and
                                           settings survive reboots (unlocked at boot).
                                           A partition, or a mos-home.luks file on the
                                           data partition (--file, or when the stick's
                                           4 partition slots are used up)
  usb-vault stick                          mount the stick's own files (the data
                                           partition, or the Ventoy partition) and
                                           show where
  usb-vault backup DIR                     copy all vaults (+ data partition) to DIR
  usb-vault restore DIR                    recreate them from DIR (e.g. on a new stick)
  usb-vault recover                        after re-flashing the stick: put the vault
                                           partitions back into the partition table
  usb-vault menu                           full-screen menu in the terminal (the
                                           \"Encrypted Storage (USB Vault)\" launcher)
  usb-vault list                           vaults, one per line: open|locked, path, mount
  usb-vault gui                            graphical menu (zenity)
  usb-vault autostart                      used at login: offer to unlock / recover")"
    printf '%s\n\n' "$(T "Ventoy: when MeccanicOS was booted from an ISO file on a Ventoy stick, vaults and
the persistent home are files in a \"meccanicos\" folder on the Ventoy partition
(meccanicos/mos-home.luks, meccanicos/*.luks); partitions are never added. Ventoy
keeps that partition busy (it maps the ISO file out of it), so a plain mount
fails; usb-vault mounts it through a second device-mapper view of the whole
partition, which the kernel allows alongside Ventoy's (no Ventoy options or
VTOY_LINUX_REMOUNT needed).")"
    printf '%s\n\n' "$(T 'Safety: the first partition is placed HEADROOM (default 4G) after the ISO so a
bigger future ISO can be written without touching it, and a copy of the vault
partition table is kept in the last MiB of the stick for `recover`.')"
    printf '%s\n\n' "$(T 'VAULT can be a device (/dev/sdb3), a container file path, or a name shown by
`status`. Set USB_VAULT_DISK=/dev/sdX to work on a different USB stick.')"
}

# ---------------------------------------------------------------- helpers ----
die() {
    if [[ $GUI == 1 ]]; then z --error --width=420 --no-markup --text="$*" 2>/dev/null || true; fi
    echo "usb-vault: $*" >&2
    exit 1
}
usage() { echo "usb-vault: $* (usb-vault --help)" >&2; exit 2; } # wrong usage
info() {
    if [[ $GUI == 1 ]]; then z --info --width=420 --no-markup --text="$*" 2>/dev/null || true; fi
    echo "$*"
}
need_root() {
    if [[ $EUID -ne 0 ]]; then
        # USB_VAULT_SELF is set by the Nix wrapper, which also restores PATH.
        exec sudo --preserve-env=USB_VAULT_DISK,USB_VAULT_VENTOY,USB_VAULT_GUI,USB_VAULT_YES,MECCANICOS_LIVE,MECCANICOS_I18N,LANG,LANGUAGE,LC_ALL,LC_MESSAGES,DISPLAY,XAUTHORITY,DBUS_SESSION_BUS_ADDRESS \
            "${USB_VAULT_SELF:-$(readlink -f "$0")}" "$@"
    fi
}
# The desktop user who should own mounted vaults (USB_VAULT_USER: boot service).
target_user() { echo "${USB_VAULT_USER:-${SUDO_USER:-${USER:-root}}}"; }
target_home() { getent passwd "$(target_user)" | cut -d: -f6; }

# Run zenity as the desktop user even when we are root via sudo.
z() {
    if [[ $EUID -eq 0 && -n ${SUDO_USER:-} ]]; then
        sudo -u "$SUDO_USER" --preserve-env=DISPLAY,XAUTHORITY,DBUS_SESSION_BUS_ADDRESS zenity "$@"
    else
        zenity "$@"
    fi
}

human() { numfmt --to=iec --suffix=B "$1"; }

# An installed system (vs the live USB): it has the flake in /etc/nixos.
# MECCANICOS_LIVE=1/0 overrides (as in scripts/mos/common.py).
installed() {
    if [[ -n ${MECCANICOS_LIVE:-} ]]; then [[ $MECCANICOS_LIVE != 1 ]]; return; fi
    [[ -e /etc/nixos/flake.nix ]]
}

# "1.2GB used, 14GB free" for the filesystem holding $1; nothing if df can't tell.
space() {
    local u a
    read -r u a < <(df --output=used,avail -B1 "$1" 2>/dev/null | tail -n1) || return 0
    [[ ${u:-} =~ ^[0-9]+$ && ${a:-} =~ ^[0-9]+$ ]] || return 0
    echo "$(human "$u") used, $(human "$a") free"
}

# --------------------------------------------------------- find the stick ----
# The Ventoy partition we were booted from ("" when not booted through Ventoy).
# Ventoy serves the ISO as /dev/mapper/ventoy, a map of the ISO file's sectors
# on that partition. USB_VAULT_VENTOY=/dev/sdX1 overrides.
ventoy_part() {
    if [[ -n ${USB_VAULT_VENTOY:-} ]]; then
        echo "$USB_VAULT_VENTOY"
        return
    fi
    [[ -e /dev/mapper/ventoy ]] || return 0
    local dev
    dev=$(dmsetup deps -o devname ventoy 2>/dev/null | sed -n 's/.*(\([^)]*\)).*/\1/p' | head -n1)
    [[ -n $dev && -b /dev/$dev ]] && echo "/dev/$dev"
}
is_ventoy() { [[ -n $(ventoy_part) ]]; }

# Where vault files live: the data partition's root, or meccanicos/ on Ventoy.
data_dir() { if is_ventoy; then echo "$DATA_MNT/meccanicos"; else echo "$DATA_MNT"; fi; }

boot_disk() {
    if [[ -n ${USB_VAULT_DISK:-} ]]; then
        echo "$USB_VAULT_DISK"
        return
    fi
    local vp
    vp=$(ventoy_part)
    if [[ -n $vp ]]; then
        echo "/dev/$(lsblk -dno PKNAME "$vp")"
        return
    fi
    local src
    src=$(findmnt -n -o SOURCE /iso 2>/dev/null || true)
    [[ -b $src ]] || src=$(blkid -t LABEL="$ISO_LABEL" -o device 2>/dev/null | head -n1 || true)
    [[ -b $src ]] || die "$(Tf "Cannot find the boot USB (no /iso mount, no '%s' label).
Set USB_VAULT_DISK=/dev/sdX to choose the stick manually." "$ISO_LABEL")"
    if [[ $(lsblk -dno TYPE "$src") == part ]]; then
        echo "/dev/$(lsblk -dno PKNAME "$src")"
    else
        echo "$src"
    fi
}

# Partition device node for partition number N of DISK (sdb3, nvme0n1p3, mmcblk0p3, loop0p3)
part_dev() {
    local disk=$1 n=$2
    if [[ $disk =~ [0-9]$ ]]; then echo "${disk}p${n}"; else echo "${disk}${n}"; fi
}

# "START SIZE" lines (sectors) of every partition in the stick's MBR.
partitions() {
    sfdisk -d "$1" 2>/dev/null | sed -n 's/.*start= *\([0-9]*\), *size= *\([0-9]*\).*/\1 \2/p'
}

# Sector where the live ISO ends (the ISO9660 image and its partitions).
iso_end() {
    local disk=$1 end s z
    end=$(isosize -d 512 "$disk" 2>/dev/null || echo 0)
    while read -r s z; do
        ((s < end && s + z > end)) && end=$((s + z))
    done < <(partitions "$disk")
    echo "$end"
}

# Last usable sector + 1: the final MiB holds the vault map; MBR stops at 2 TiB.
usable_end() {
    local total
    total=$(blockdev --getsz "$1")
    ((total > 4294967295)) && total=4294967295
    echo $((total - 2048))
}

# Prints "START SIZE" (sectors) of the free space after the last partition,
# aligned to 1 MiB. The first vault partition starts HEADROOM after the ISO.
free_space() {
    local disk=$1 end=0 s z e isoend limit start size head
    while read -r s z; do
        e=$((s + z))
        ((e > end)) && end=$e
    done < <(partitions "$disk")
    isoend=$(iso_end "$disk")
    ((isoend > end)) && end=$isoend
    limit=$(usable_end "$disk")
    if ((end == isoend)) && ((isoend > 0)); then
        head=$(($(to_bytes "$HEADROOM") / 512))
        # Shrink the headroom on small sticks rather than refusing.
        while ((head > 0 && limit - (end + head) < 2048 * 1024)); do head=$((head / 2)); done
        end=$((end + head))
    fi
    start=$(((end + 2047) / 2048 * 2048))
    size=$((limit - start))
    ((size < 0)) && size=0
    echo "$start $size"
}

# ---- vault map: a copy of our partition entries in the stick's last MiB ----
# Lines: "start size type label"
current_map() {
    local disk=$1 isoend s z t n=0 dev label
    isoend=$(iso_end "$disk")
    while IFS= read -r line; do
        n=$((n + 1))
        s=$(sed -n 's/.*start= *\([0-9]*\).*/\1/p' <<<"$line")
        z=$(sed -n 's/.*size= *\([0-9]*\).*/\1/p' <<<"$line")
        t=$(sed -n 's/.*type= *\([0-9a-fA-F]*\).*/\1/p' <<<"$line")
        [[ -n $s ]] && ((s >= isoend)) || continue
        dev=$(part_dev "$disk" "$n")
        label=$(blkid -p -o value -s LABEL "$dev" 2>/dev/null || true)
        echo "$s $z ${t:-83} ${label:--}"
    done < <(sfdisk -d "$disk" 2>/dev/null | grep 'start=')
}

write_map() {
    local disk=$1 tmp total
    total=$(blockdev --getsz "$disk")
    tmp=$(mktemp)
    { echo "$MAP_MAGIC"; current_map "$disk"; echo "END"; } >"$tmp"
    truncate -s 1M "$tmp"
    dd if="$tmp" of="$disk" bs=512 seek=$((total - 2048)) conv=notrunc,fsync status=none ||
        echo "$(T 'warning: could not save the vault map')" >&2
    rm -f "$tmp"
}

read_map() {
    local disk=$1 total
    total=$(blockdev --getsz "$disk")
    dd if="$disk" bs=512 skip=$((total - 2048)) count=2048 status=none 2>/dev/null |
        tr -d '\000' | awk -v m="$MAP_MAGIC" 'NR==1 && $0!=m {exit} NR>1 && $0=="END" {exit} NR>1 {print}'
}

# Map entries that are no longer in the partition table (e.g. after re-flashing).
missing_from_table() {
    local disk=$1 s z t l
    while read -r s z t l; do
        [[ -n $s ]] || continue
        partitions "$disk" | awk -v s="$s" '$1==s {f=1} END {exit !f}' || echo "$s $z $t $l"
    done < <(read_map "$disk")
}

partition_count() { sfdisk -d "$1" 2>/dev/null | grep -c 'start=' || true; }

# Parse "8G", "500M", "1T" to bytes
to_bytes() { numfmt --from=iec "${1%B}"; }

# Append a primary MBR partition. $1 disk, $2 size in sectors (0 = all), $3 type id.
# Prints the new partition's device node.
append_partition() {
    local disk=$1 want=$2 type=$3 start=${4:-} avail n
    if [[ -z $start ]]; then
        read -r start avail < <(free_space "$disk")
        ((avail >= 2048 * 64)) || die "$(Tf 'Less than 64 MiB free on %s. Use a bigger USB stick.' "$disk")"
        ((want == 0 || want > avail)) && want=$avail
        want=$((want / 2048 * 2048))
    fi
    n=$(partition_count "$disk")
    ((n < 4)) || die "$(Tf '%s already uses all 4 partition slots (2 are the live system). Use a vault file instead: usb-vault create-file (or create-home --file).' "$disk")"

    # The hybrid ISO carries an MBR (used by Linux and BIOS) plus a GPT whose
    # backup header no longer matches the stick size. We only touch the MBR,
    # exactly like other live-USB persistence tools do.
    echo "start=$start, size=$want, type=$type" |
        sfdisk --append --no-reread --no-tell-kernel --label dos -q "$disk" >/dev/null 2>&1 ||
        die "$(Tf 'sfdisk failed to add a partition on %s' "$disk")"
    n=$((n + 1))
    # Tell the kernel about just the new partition (the others are busy/mounted).
    partx --add --nr "$n" "$disk" 2>/dev/null || partx --update --nr "$n" "$disk" 2>/dev/null || true
    udevadm settle 2>/dev/null || true
    local dev
    dev=$(part_dev "$disk" "$n")
    for _ in $(seq 20); do [[ -b $dev ]] && break; sleep 0.5; done
    [[ -b $dev ]] || die "$(Tf "Kernel did not pick up new partition %s (try unplug/replug, then 'usb-vault open')." "$dev")"
    [[ -n ${4:-} ]] || wipefs -aq "$dev" 2>/dev/null || true
    echo "$dev"
}

confirm() {
    local msg=$1
    # The menu (usb-vault-menu.py) has already asked.
    [[ ${USB_VAULT_YES:-0} == 1 ]] && return 0
    if [[ $GUI == 1 ]]; then
        z --question --width=460 --title="USB Vault" --text="$msg" 2>/dev/null
    else
        echo "$msg"
        read -r -p "$(T 'Type YES to continue: ')" ans
        [[ $ans == YES ]]
    fi
}

# read_secret VAR PROMPT - hidden input on a terminal; one line from stdin
# otherwise (so the tool can be scripted: printf 'pass\n' | usb-vault open).
read_secret() {
    local -n _out=$1
    if [[ -t 0 ]]; then
        read -r -s -p "$2" _out; echo >&2
    else
        IFS= read -r _out || true
    fi
}

# Read a new passphrase (twice). Prints it on stdout.
new_passphrase() {
    local p1 p2
    if [[ $GUI == 1 ]]; then
        p1=$(z --password --title="$(T 'New vault passphrase')" 2>/dev/null) || exit 1
        p2=$(z --password --title="$(T 'Repeat passphrase')" 2>/dev/null) || exit 1
    else
        read_secret p1 "$(T 'New passphrase: ')"
        read_secret p2 "$(T 'Repeat passphrase: ')"
    fi
    [[ $p1 == "$p2" ]] || die "$(T 'Passphrases do not match.')"
    ((${#p1} >= 16)) || die "$(T 'Use at least 16 characters.')"
    printf '%s' "$p1"
}

ask_passphrase() {
    local what=$1 p
    if [[ $GUI == 1 ]]; then
        p=$(z --password --title="$(Tf 'Unlock %s' "$what")" 2>/dev/null) || exit 1
    else
        read_secret p "$(Tf 'Passphrase for %s: ' "$what")"
    fi
    printf '%s' "$p"
}

# ------------------------------------------------------------- the vaults ----
# Mount DEV on DATA_MNT, owned by the desktop user where the filesystem allows.
mount_data() {
    local dev=$1 u
    mkdir -p "$DATA_MNT"
    u=$(id -u "$(target_user)")
    mount -o "uid=$u,gid=$(id -g "$(target_user)"),fmask=0077,dmask=0077" "$dev" "$DATA_MNT" 2>/dev/null ||
        mount "$dev" "$DATA_MNT"
}

# The Ventoy partition: Ventoy holds it, so mount it through our own
# device-mapper view of the whole partition (sharing Ventoy's claim).
mount_ventoy() {
    local part=$1
    mount_data "$part" 2>/dev/null && return 0 # not held (e.g. Ventoy memdisk mode)
    if [[ ! -e /dev/mapper/$VENTOY_MAP ]]; then
        dmsetup create "$VENTOY_MAP" --table "0 $(blockdev --getsz "$part") linear $part 0" ||
            return 1
        udevadm settle 2>/dev/null || true
    fi
    mount_data "/dev/mapper/$VENTOY_MAP"
}

# Mount the stick's data area (data partition, or Ventoy partition). Prints DATA_MNT.
mount_data_partition() {
    if ! findmnt -n "$DATA_MNT" >/dev/null 2>&1; then
        local vp dev
        vp=$(ventoy_part)
        if [[ -n $vp ]]; then
            mount_ventoy "$vp" || return 1
        else
            dev=$(blkid -t LABEL="$DATA_LABEL" -o device 2>/dev/null | head -n1 || true)
            [[ -n $dev ]] || return 1
            mount_data "$dev" || return 1
        fi
    fi
    echo "$DATA_MNT"
}

# One vault per line: "<source>"  (device node or container file path)
list_vaults() {
    local disk
    disk=$(boot_disk 2>/dev/null || true)
    # LUKS partitions carrying our label (on any disk) ...
    blkid -t LABEL="$VAULT_LABEL" -o device 2>/dev/null || true
    # ... plus any other LUKS partition on the boot stick (not on Ventoy:
    # its disk holds nothing of ours outside the files).
    if [[ -n $disk ]] && ! is_ventoy; then
        lsblk -lnpo NAME,FSTYPE "$disk" 2>/dev/null | awk '$2=="crypto_LUKS"{print $1}' || true
    fi
    # Container files at the top of the data partition (and a vaults/ folder).
    if mount_data_partition >/dev/null 2>&1; then
        local d
        d=$(data_dir)
        find "$d" "$d/vaults" -maxdepth 1 -type f -name '*.luks' 2>/dev/null || true
    fi
}
is_home() {
    [[ $(basename "$1") == "$HOME_FILE" ]] && return 0
    [[ -b $1 && $(blkid -p -o value -s LABEL "$1" 2>/dev/null) == "$HOME_LABEL" ]]
}
vaults() {
    local v
    list_vaults | awk 'NF && !seen[$0]++' | while read -r v; do is_home "$v" || echo "$v"; done
}

mapper_name() {
    local src=$1
    if [[ -b $src ]]; then
        echo "usbvault-$(basename "$src")"
    else
        local b
        b=$(basename "$src" .luks)
        echo "usbvault-file-${b//[^A-Za-z0-9_-]/_}"
    fi
}

mount_point() {
    local src=$1 home
    home=$(target_home)
    if [[ -b $src ]]; then
        echo "$home/Vault"
    else
        echo "$home/Vault-$(basename "$src" .luks)"
    fi
}

is_open() { [[ -e /dev/mapper/$(mapper_name "$1") ]]; }

do_open() {
    local src=$1 name mp pass
    name=$(mapper_name "$src")
    mp=$(mount_point "$src")
    if ! is_open "$src"; then
        pass=$(ask_passphrase "$(basename "$src")")
        printf '%s' "$pass" | cryptsetup open --key-file=- "$src" "$name" ||
            die "$(Tf 'Wrong passphrase, or %s is not a LUKS vault.' "$src")"
    fi
    mkdir -p "$mp"
    if ! findmnt -n "$mp" >/dev/null 2>&1; then
        mount "/dev/mapper/$name" "$mp"
    fi
    chown "$(target_user):" "$mp" 2>/dev/null || true
    # mkfs's root-only lost+found: file managers say "Permission denied" on it
    # (fsck makes it again if ever needed). Only removed while empty.
    rmdir "$mp/lost+found" 2>/dev/null || true
    info "$(Tf 'Vault unlocked and mounted at %s' "$mp")"
}

do_close() {
    local src=$1 name mp
    name=$(mapper_name "$src")
    mp=$(mount_point "$src")
    sync
    if findmnt -n "$mp" >/dev/null 2>&1; then umount "$mp" || die "$(Tf 'Cannot unmount %s (files still open?)' "$mp")"; fi
    rmdir "$mp" 2>/dev/null || true
    if [[ -e /dev/mapper/$name ]]; then cryptsetup close "$name"; fi
    Tf 'Locked %s\n' "$src"
}

# Create LUKS2 + ext4 on $1 (device or file), mount it.
format_vault() {
    local src=$1 label=${2:-$VAULT_LABEL} pass name
    pass=$(new_passphrase)
    local label_args=()
    [[ -b $src ]] && label_args=(--label "$label")
    echo "$(T 'Encrypting (LUKS2, argon2id)...')"
    printf '%s' "$pass" | cryptsetup luksFormat -q --type luks2 "${label_args[@]}" --key-file=- "$src" ||
        die "$(Tf 'cryptsetup luksFormat failed on %s' "$src")"
    name=$(mapper_name "$src")
    printf '%s' "$pass" | cryptsetup open --key-file=- "$src" "$name" ||
        die "$(Tf 'Created %s but could not unlock it (is the dm_crypt kernel module available?)' "$src")"
    mkfs.ext4 -q -L vault -m 0 "/dev/mapper/$name" || die "$(T 'mkfs.ext4 failed inside the vault')"
    local mp
    mp=$(mount_point "$src")
    mkdir -p "$mp"
    mount "/dev/mapper/$name" "$mp"
    chown "$(target_user):" "$mp"
    rmdir "$mp/lost+found" 2>/dev/null || true # see do_open
    sync
    info "$(Tf "Created vault: %s
Mounted at: %s
Lock it with 'usb-vault close' (or just shut down)." "$src" "$mp")"
}

pick_vault() {
    # Prints the vault to unlock (asks which when there are several).
    local list n
    mapfile -t list < <(vaults)
    n=${#list[@]}
    ((n > 0)) || die "$(T 'No vault found on this USB stick. Create one with: usb-vault create-partition  (or create-file)')"
    if ((n == 1)); then echo "${list[0]}"; return; fi
    if [[ $GUI == 1 ]]; then
        z --list --title="USB Vault" --text="$(T 'Choose a vault to unlock')" --column="$(T 'Vault')" "${list[@]}" 2>/dev/null || exit 1
    else
        local i=1 v
        for v in "${list[@]}"; do echo "  $i) $v" >&2; i=$((i + 1)); done
        read -r -p "$(Tf 'Which vault to unlock? [1-%s] ' "$n")" i
        echo "${list[$((i - 1))]}"
    fi
}

resolve() {
    local arg=$1 v
    [[ -e $arg ]] && { readlink -f "$arg"; return; }
    while read -r v; do
        [[ $(basename "$v") == "$arg" || $(basename "$v" .luks) == "$arg" ]] && { echo "$v"; return; }
    done < <(vaults)
    die "$(Tf 'No such vault: %s' "$arg")"
}

# ---------------------------------------------------------------- commands ----
cmd_status() {
    stick_status
    echo
    cmd_summary
}

# What survives a restart, for the system running now. The live USB keeps
# everything outside the persistent home in RAM: / and the writable part of
# /nix/store (where `apps install` downloads to) are tmpfs (iso-image.nix),
# and Ollama's models are in /var/lib/ollama (services.ollama, modules/ai.nix).
# The menu (usb-vault-menu.py) shows these lines at its top: keep the
# "Label : kept|lost ..." shape. Like stick_status, in English: the menu
# reads them (the first line, "kept"/"lost at shutdown"; "Home", "Recover").
cmd_summary() {
    local GUI=0 v list n open=0 home_open=0 home_made=0 sp
    mapfile -t list < <(vaults 2>/dev/null || true)
    n=${#list[@]}
    for v in "${list[@]}"; do is_open "$v" && open=$((open + 1)); done
    findmnt -n /dev/mapper/mos-home >/dev/null 2>&1 && home_open=1
    if [[ -n $(blkid -t LABEL="$HOME_LABEL" -o device 2>/dev/null || true) ]] ||
        { findmnt -n "$DATA_MNT" >/dev/null 2>&1 && [[ -f $(data_dir)/$HOME_FILE ]]; }; then
        home_made=1
    fi
    local vtext="none yet"
    installed && vtext="none found"
    ((n)) && vtext="$n found, $open open"
    if installed; then
        echo "What survives a restart (installed system):"
        echo "  Files and settings : kept, on this computer's disk"
        echo "  Apps you installed : kept"
        echo "  AI models          : kept (in /var/lib/ollama)"
        echo "  Vaults             : kept, encrypted, on the USB stick ($vtext)"
        echo "Space:"
        sp=$(space /)
        [[ -n $sp ]] && echo "  This computer      : $sp"
        if [[ $(findmnt -n -o SOURCE --target "$(target_home)" 2>/dev/null || true) != "$(findmnt -n -o SOURCE / 2>/dev/null || true)" ]]; then
            sp=$(space "$(target_home)")
            [[ -n $sp ]] && echo "  Home folder        : $sp"
        fi
    else
        if ((home_open)); then
            echo "What survives a restart (live USB, persistent home open):"
            echo "  Files and settings : kept, encrypted, in your persistent home on the stick"
            echo "  Apps you installed : lost at shutdown (in RAM); the list is kept: apps update"
            echo "  AI models          : lost at shutdown (in RAM); mos-ai-setup gets them again"
        else
            echo "What survives a restart (live USB, no persistent home open):"
            if ((home_made)); then
                echo "  Files and settings : lost at shutdown (persistent home not in use)"
            else
                echo "  Files and settings : lost at shutdown (in RAM; a persistent home keeps them)"
            fi
            echo "  Apps you installed : lost at shutdown (in RAM)"
            echo "  AI models          : lost at shutdown (in RAM)"
        fi
        echo "  Vaults             : kept, encrypted, on the stick ($vtext)"
        echo "Space:"
        if ((home_open)); then
            sp=$(space "$(target_home)")
            [[ -n $sp ]] && echo "  Persistent home    : $sp"
        fi
        if findmnt -n "$DATA_MNT" >/dev/null 2>&1; then
            sp=$(space "$DATA_MNT")
            [[ -n $sp ]] && echo "  Stick files area   : $sp"
        fi
        sp=$(space /)
        [[ -n $sp ]] && echo "  RAM, files/models  : $sp"
        if findmnt -n /nix/.rw-store >/dev/null 2>&1; then
            sp=$(space /nix/.rw-store)
            [[ -n $sp ]] && echo "  RAM, new apps      : $sp"
        fi
    fi
    return 0
}

# In English, like cmd_summary: the menu reads its "Home" and "Recover" lines.
stick_status() {
    local disk start avail
    disk=$(boot_disk)
    if is_ventoy; then
        local vp d
        vp=$(ventoy_part)
        echo "Boot USB : $disk  ($(lsblk -dno MODEL,SIZE "$disk" 2>/dev/null | xargs)), booted through Ventoy"
        echo "Ventoy   : $vp ($(blkid -p -o value -s LABEL "$vp" 2>/dev/null || echo no label))"
        if mount_data_partition >/dev/null 2>&1; then
            d=$(data_dir)
            echo "Free     : $(human "$(df --output=avail -B1 "$DATA_MNT" | tail -n1)") on the Ventoy partition"
            echo "Files    : $d/  (usb-vault stick)"
        else
            echo "Files    : the Ventoy partition could not be mounted"
            d=/nonexistent
        fi
        echo "Home     : $([[ -f $d/$HOME_FILE ]] && echo "$d/$HOME_FILE" || echo none)$(findmnt -n /dev/mapper/mos-home >/dev/null 2>&1 && echo " (in use as your home folder)")"
        echo "Vaults   :"
        local v any=0
        while read -r v; do
            [[ -n $v ]] || continue
            any=1
            if is_open "$v"; then echo "  [open]   $v -> $(mount_point "$v")"; else echo "  [locked] $v"; fi
        done < <(vaults)
        ((any)) || echo "  (none)"
        return
    fi
    read -r start avail < <(free_space "$disk")
    echo "Boot USB : $disk  ($(lsblk -dno MODEL,SIZE "$disk" 2>/dev/null | xargs))"
    echo "Free     : $(human $((avail * 512))) unpartitioned after the ISO"
    echo "Data part: $(blkid -t LABEL="$DATA_LABEL" -o device 2>/dev/null | head -n1 || echo none)"
    local h
    h=$(blkid -t LABEL="$HOME_LABEL" -o device 2>/dev/null | head -n1 || true)
    echo "Home     : ${h:-none}$([[ -n $h ]] && findmnt -n /dev/mapper/mos-home >/dev/null 2>&1 && echo " (in use as your home folder)")"
    local miss
    miss=$(missing_from_table "$disk" | wc -l)
    ((miss)) && echo "Recover  : $miss vault partition(s) can be restored: usb-vault recover"
    echo "Vaults   :"
    local v any=0
    while read -r v; do
        [[ -n $v ]] || continue
        any=1
        if is_open "$v"; then echo "  [open]   $v -> $(mount_point "$v")"; else echo "  [locked] $v"; fi
    done < <(vaults)
    ((any)) || echo "  (none)"
}

# For the menu: "ventoy" or "stick", then each vault as open|locked<TAB>path<TAB>mount.
cmd_list() {
    local v
    boot_disk >/dev/null
    if is_ventoy; then echo ventoy; else echo stick; fi
    while read -r v; do
        [[ -n $v ]] || continue
        if is_open "$v"; then printf 'open\t%s\t%s\n' "$v" "$(mount_point "$v")"; else printf 'locked\t%s\t\n' "$v"; fi
    done < <(vaults)
}

cmd_create_partition() {
    is_ventoy && die "$(T "On a Ventoy stick vaults are files (Ventoy's partitions must not change): usb-vault create-file")"
    local size=0 disk
    while (($#)); do case $1 in
        --size) size=$(($(to_bytes "$2") / 512)); shift 2 ;;
        *) usage "$(Tf 'unknown option %s' "$1")" ;;
    esac done
    disk=$(boot_disk)
    local start avail
    read -r start avail < <(free_space "$disk")
    ((avail >= 2048 * 64)) || die "$(Tf 'Less than 64 MiB free on %s. Use a bigger USB stick, or store a vault file instead (create-file).' "$disk")"
    local show=$avail
    ((size > 0 && size < avail)) && show=$size
    confirm "$(Tf 'Create an encrypted partition of %s on
%s (%s)?

Only free space after the live system is used; nothing existing is erased.' \
        "$(human $((show * 512)))" "$disk" "$(lsblk -dno MODEL "$disk" 2>/dev/null | xargs)")" || exit 1
    local dev
    dev=$(append_partition "$disk" "$size" 83)
    format_vault "$dev"
    write_map "$disk"
}

cmd_create_file() {
    local size=4G name=vault.luks data_size=0 path=""
    while (($#)); do case $1 in
        --size) size=$2; shift 2 ;;
        --name) name=$2; shift 2 ;;
        --data-size) data_size=$(($(to_bytes "$2") / 512)); shift 2 ;;
        --path) path=$2; shift 2 ;;
        *) usage "$(Tf 'unknown option %s' "$1")" ;;
    esac done
    [[ $name == *.luks ]] || name="$name.luks"

    if [[ -z $path ]] && is_ventoy; then
        mount_data_partition >/dev/null || die "$(T 'Cannot mount the Ventoy partition.')"
        mkdir -p "$(data_dir)"
        path="$(data_dir)/$name"
    fi
    if [[ -z $path ]]; then
        if ! mount_data_partition >/dev/null 2>&1; then
            local disk start avail show
            disk=$(boot_disk)
            read -r start avail < <(free_space "$disk")
            ((avail >= 2048 * 64)) || die "$(Tf 'No data partition and less than 64 MiB free on %s.' "$disk")"
            show=$avail
            ((data_size > 0 && data_size < avail)) && show=$data_size
            confirm "$(Tf "No data partition yet. Create a %s exFAT partition
'%s' on %s to hold vault files?

Only free space after the live system is used; nothing existing is erased." "$(human $((show * 512)))" "$DATA_LABEL" "$disk")" || exit 1
            local dev
            dev=$(append_partition "$disk" "$data_size" 7)
            mkfs.exfat -q -L "$DATA_LABEL" "$dev" >/dev/null 2>&1 || mkfs.exfat -n "$DATA_LABEL" "$dev" >/dev/null
            udevadm settle 2>/dev/null || true
            write_map "$disk"
            mkdir -p "$DATA_MNT"
            mount -o "uid=$(id -u "$(target_user)"),gid=$(id -g "$(target_user)"),fmask=0077,dmask=0077" "$dev" "$DATA_MNT"
        fi
        path="$DATA_MNT/$name"
    fi
    [[ ! -e $path ]] || die "$(Tf '%s already exists.' "$path")"
    local bytes
    bytes=$(to_bytes "$size")
    local freeb
    freeb=$(df --output=avail -B1 "$(dirname "$path")" | tail -n1)
    ((bytes < freeb)) || die "$(Tf 'Not enough space: want %s, have %s.' "$(human "$bytes")" "$(human "$freeb")")"
    Tf 'Allocating %s for %s ...\n' "$(human "$bytes")" "$path"
    fallocate -l "$bytes" "$path" 2>/dev/null || truncate -s "$bytes" "$path"
    format_vault "$path"
}

cmd_open() {
    local v
    if (($#)); then v=$(resolve "$1"); else v=$(pick_vault); fi
    do_open "$v"
}

cmd_close() {
    local v
    if [[ ${1:-} == --all ]]; then
        while read -r v; do is_open "$v" && do_close "$v"; done < <(vaults)
        # also anything we opened that is no longer listed
        for m in /dev/mapper/usbvault-*; do [[ -e $m ]] || continue
            umount "/dev/mapper/$(basename "$m")" 2>/dev/null || true
            cryptsetup close "$(basename "$m")" || true
        done
    elif (($#)); then
        do_close "$(resolve "$1")"
    else
        local open=()
        while read -r v; do is_open "$v" && open+=("$v"); done < <(vaults)
        ((${#open[@]})) || { info "$(T 'No vault is open.')"; return; }
        for v in "${open[@]}"; do do_close "$v"; done
    fi
    findmnt -n "$DATA_MNT" >/dev/null 2>&1 && umount "$DATA_MNT" 2>/dev/null || true
    [[ $GUI == 1 ]] && info "$(T 'Vault locked. It is safe to remove the USB stick after shutdown.')"
    return 0
}

cmd_create_home() {
    local size=0 disk user as_file=0
    while (($#)); do case $1 in
        --size) size=$(($(to_bytes "$2") / 512)); shift 2 ;;
        --file) as_file=1; shift ;;
        *) usage "$(Tf 'unknown option %s' "$1")" ;;
    esac done
    disk=$(boot_disk)
    if is_ventoy; then
        as_file=1 # Ventoy: always a file in meccanicos/ on the Ventoy partition
        mount_data_partition >/dev/null || die "$(T 'Cannot mount the Ventoy partition.')"
        mkdir -p "$(data_dir)"
    else
        blkid -t LABEL="$HOME_LABEL" -o device >/dev/null 2>&1 && die "$(T 'This stick already has a persistent home.')"
        ((as_file == 0 && $(partition_count "$disk") >= 4)) && as_file=1
    fi
    if mount_data_partition >/dev/null 2>&1 && [[ -e $(data_dir)/$HOME_FILE ]]; then
        die "$(Tf 'This stick already has a persistent home (%s).' "$HOME_FILE")"
    fi
    local target show
    if ((as_file)); then
        mount_data_partition >/dev/null 2>&1 ||
            die "$(T 'No data partition for the home file. Create one first: usb-vault create-file --data-size 16G')"
        ((size > 0)) || size=$((8 * 1024 * 1024 * 2)) # default 8 GiB
        local freeb
        freeb=$(df --output=avail -B1 "$DATA_MNT" | tail -n1)
        ((size * 512 < freeb)) || die "$(Tf 'Not enough space on the data partition: %s free.' "$(human "$freeb")")"
        show=$size
        target="$(data_dir)/$HOME_FILE"
    else
        local start avail
        read -r start avail < <(free_space "$disk")
        ((avail >= 2048 * 1024)) || die "$(Tf 'Need at least 1 GiB free on %s for a persistent home.' "$disk")"
        show=$avail
        ((size > 0 && size < avail)) && show=$size
    fi
    local question
    if ((as_file)); then
        question=$(Tf "Create an encrypted persistent home of %s on %s (as the file %s)?

Your files and settings (browser, desktop, documents) will be kept
on the stick. At every start-up you'll be asked for its password; leave the
password empty to start a fresh session instead." "$(human $((show * 512)))" "$disk" "$HOME_FILE")
    else
        question=$(Tf "Create an encrypted persistent home of %s on %s?

Your files and settings (browser, desktop, documents) will be kept
on the stick. At every start-up you'll be asked for its password; leave the
password empty to start a fresh session instead." "$(human $((show * 512)))" "$disk")
    fi
    confirm "$question" || exit 1
    local pass
    if ((as_file)); then
        Tf 'Allocating %s...\n' "$(human $((show * 512)))"
        fallocate -l $((show * 512)) "$target" 2>/dev/null || truncate -s $((show * 512)) "$target"
    else
        target=$(append_partition "$disk" "$size" 83)
    fi
    pass=$(new_passphrase)
    echo "$(T 'Encrypting (LUKS2, argon2id)...')"
    printf '%s' "$pass" | cryptsetup luksFormat -q --type luks2 --label "$HOME_LABEL" --key-file=- "$target"
    printf '%s' "$pass" | cryptsetup open --key-file=- "$target" mos-home-new
    mkfs.ext4 -q -L home -m 0 /dev/mapper/mos-home-new
    mkdir -p /run/usb-vault/newhome
    mount /dev/mapper/mos-home-new /run/usb-vault/newhome
    user=$(target_user)
    echo "$(T 'Copying your current settings into it...')"
    rsync -a --exclude .cache --exclude Vault --exclude 'Vault-*' "$(target_home)/" /run/usb-vault/newhome/ || true
    rm -rf /run/usb-vault/newhome/lost+found
    chown -R "$user:" /run/usb-vault/newhome
    chmod 700 /run/usb-vault/newhome
    umount /run/usb-vault/newhome
    cryptsetup close mos-home-new
    ((as_file)) || write_map "$disk"
    sync
    info "$(Tf "Persistent home created (%s).
Restart the computer: you'll be asked for its password during start-up." "$target")"
}

cmd_recover() {
    is_ventoy && { info "$(T 'Nothing to recover on a Ventoy stick: vaults are files and survive updating the ISO.')"; return 0; }
    local disk s z t l n=0 dev isoend sig
    disk=$(boot_disk)
    isoend=$(iso_end "$disk")
    local -a todo=()
    while read -r s z t l; do [[ -n $s ]] && todo+=("$s $z $t $l"); done < <(missing_from_table "$disk")
    ((${#todo[@]})) || { info "$(T 'Nothing to recover: every saved vault partition is in the table.')"; return 0; }
    for e in "${todo[@]}"; do
        read -r s z t l <<<"$e"
        if ((s < isoend)); then
            Tf '  ✗ %s: overwritten by the new ISO (it ends past this partition). Restore it from a backup.\n' "$l"
            continue
        fi
        sig=$(blkid -p -o value -s TYPE -O $((s * 512)) "$disk" 2>/dev/null || true)
        if [[ $sig != crypto_LUKS && $sig != exfat ]]; then
            echo "$(Tf "  ✗ %s: no vault found at its old place (found '%s'). Restore it from a backup." "$l" "${sig:-$(T 'nothing')}")"
            continue
        fi
        dev=$(append_partition "$disk" "$z" "$t" "$s")
        Tf '  ✓ %s restored as %s\n' "$l" "$dev"
        n=$((n + 1))
    done
    ((n)) && write_map "$disk"
    info "$(Tf 'Recovered %s vault partition(s).' "$n")"
}

backup_dir_check() {
    local d=$1
    [[ -n $d ]] || usage "$(T 'missing DIR')"
    [[ -d $d ]] || die "$(Tf '%s is not a folder.' "$d")"
}

cmd_backup() {
    local dest=${1:-} disk out n=0 s z t l dev
    backup_dir_check "$dest"
    disk=$(boot_disk)
    out="$dest/mos-usb-backup-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$out"
    echo "$(T 'Locking vaults so the copy is consistent...')"
    cmd_close --all >/dev/null 2>&1 || true
    if is_ventoy; then
        mount_data_partition >/dev/null || die "$(T 'Cannot mount the Ventoy partition.')"
        local excl=()
        if findmnt -n /dev/mapper/mos-home >/dev/null 2>&1; then
            excl=(--exclude "/$HOME_FILE")
            Tf '  (skipping %s: it is your home folder right now)\n' "$HOME_FILE"
        fi
        echo "ventoy" >"$out/map.txt"
        rsync -a --info=progress2 "${excl[@]}" "$(data_dir)/" "$out/meccanicos.files/"
        sync
        info "$(Tf 'Backed up the vault files to %s' "$out")"
        return
    fi
    current_map "$disk" >"$out/map.txt"
    local i=0
    while IFS= read -r line; do
        i=$((i + 1))
        s=$(sed -n 's/.*start= *\([0-9]*\).*/\1/p' <<<"$line")
        ((s >= $(iso_end "$disk"))) || continue
        dev=$(part_dev "$disk" "$i")
        l=$(blkid -p -o value -s LABEL "$dev" 2>/dev/null || echo part$i)
        t=$(blkid -p -o value -s TYPE "$dev" 2>/dev/null || true)
        if [[ $t == exfat ]]; then
            Tf 'Copying files of %s...\n' "$l"
            mount_data_partition >/dev/null
            local excl=()
            if findmnt -n /dev/mapper/mos-home >/dev/null 2>&1; then
                excl=(--exclude "/$HOME_FILE")
                Tf '  (skipping %s: it is your home folder right now)\n' "$HOME_FILE"
            fi
            rsync -a --info=progress2 "${excl[@]}" "$DATA_MNT/" "$out/$l.files/"
            umount "$DATA_MNT" 2>/dev/null || true
        elif [[ $l == "$HOME_LABEL" ]] && findmnt -n /dev/mapper/mos-home >/dev/null 2>&1; then
            Tf 'Skipping %s: it is your home folder right now (back it up from a fresh session).\n' "$l"
            continue
        else
            Tf 'Copying %s (still encrypted)...\n' "$l"
            dd if="$dev" of="$out/$l.img" bs=4M status=progress conv=fsync
        fi
        n=$((n + 1))
    done < <(sfdisk -d "$disk" 2>/dev/null | grep 'start=')
    sync
    info "$(Tf 'Backed up %s item(s) to %s' "$n" "$out")"
}

cmd_restore() {
    local src=${1:-} disk s z t l dev n=0
    backup_dir_check "$src"
    [[ -f $src/map.txt ]] || die "$(Tf '%s does not look like a usb-vault backup (no map.txt).' "$src")"
    disk=$(boot_disk)
    if is_ventoy; then
        [[ -d $src/meccanicos.files ]] || die "$(T 'Only file vaults can be restored onto a Ventoy stick (this backup has partitions).')"
        mount_data_partition >/dev/null || die "$(T 'Cannot mount the Ventoy partition.')"
        confirm "$(Tf 'Copy the vault files from %s into %s?' "$src" "$(data_dir)")" || exit 1
        mkdir -p "$(data_dir)"
        rsync -a --ignore-existing --info=progress2 "$src/meccanicos.files/" "$(data_dir)/"
        info "$(T 'Restored the vault files (existing files were kept).')"
        return
    fi
    confirm "$(Tf 'Restore the vaults from %s onto %s?
New partitions are created after the live system; nothing existing is erased.' "$src" "$disk")" || exit 1
    while read -r s z t l; do
        [[ -n $s ]] || continue
        if [[ -f $src/$l.img ]]; then
            local sectors=$(($(stat -c %s "$src/$l.img") / 512))
            dev=$(append_partition "$disk" "$sectors" "$t")
            Tf 'Writing %s to %s...\n' "$l" "$dev"
            dd if="$src/$l.img" of="$dev" bs=4M status=progress conv=fsync
        elif [[ -d $src/$l.files ]]; then
            dev=$(append_partition "$disk" "$z" 7)
            mkfs.exfat -q -L "$l" "$dev" >/dev/null 2>&1 || mkfs.exfat -n "$l" "$dev" >/dev/null
            udevadm settle 2>/dev/null || true
            mkdir -p "$DATA_MNT"
            mount "$dev" "$DATA_MNT"
            rsync -a --info=progress2 "$src/$l.files/" "$DATA_MNT/"
            umount "$DATA_MNT"
        else
            Tf '  (no copy of %s in the backup, skipped)\n' "$l"
            continue
        fi
        n=$((n + 1))
    done <"$src/map.txt"
    write_map "$disk"
    info "$(Tf 'Restored %s item(s).' "$n")"
}

cmd_stick() {
    mount_data_partition >/dev/null ||
        die "$(T 'This stick has no files area yet (no data partition; not booted through Ventoy). Create one with: usb-vault create-file')"
    if [[ $GUI == 1 && -n ${SUDO_USER:-} ]]; then
        sudo -u "$SUDO_USER" --preserve-env=DISPLAY,XAUTHORITY,DBUS_SESSION_BUS_ADDRESS xdg-open "$DATA_MNT" >/dev/null 2>&1 &
    fi
    echo "The USB stick's files are at $DATA_MNT" # English: the menu reads the folder from it
}

cmd_gui() {
    GUI=1
    local choice unlock lock files partition file home backup recover status
    unlock=$(T 'Unlock vault')
    lock=$(T 'Lock vault')
    files=$(T "Open the USB stick's files")
    partition=$(T 'Create encrypted partition')
    file=$(T 'Create encrypted container file')
    home=$(T 'Create persistent home (keep files and settings)')
    backup=$(T 'Back up vaults to another disk')
    recover=$(T 'Recover vaults after re-flashing')
    status=$(T 'Show status')
    choice=$(z --list --title="USB Vault" --width=460 --height=320 \
        --text="$(T 'Encrypted storage on your boot USB stick')" \
        --column="$(T 'Action')" \
        "$unlock" "$lock" "$files" "$partition" "$file" "$home" "$backup" "$recover" "$status" 2>/dev/null) || exit 0
    case $choice in
        "$unlock") cmd_open ;;
        "$lock") cmd_close ;;
        "$files") cmd_stick ;;
        "$partition")
            local s
            s=$(z --entry --title="$(T 'Partition size')" --text="$(T 'Size (e.g. 8G). Leave empty to use all free space.')" 2>/dev/null) || exit 0
            if [[ -n $s ]]; then cmd_create_partition --size "$s"; else cmd_create_partition; fi ;;
        "$file")
            local s n
            s=$(z --entry --title="$(T 'Container size')" --text="$(T 'Size of the vault file:')" --entry-text=4G 2>/dev/null) || exit 0
            n=$(z --entry --title="$(T 'Container name')" --text="$(T 'File name:')" --entry-text=vault.luks 2>/dev/null) || exit 0
            cmd_create_file --size "$s" --name "$n" ;;
        "$home")
            local s
            s=$(z --entry --title="$(T 'Home size')" --text="$(T 'Size (e.g. 16G). Leave empty to use all free space.')" 2>/dev/null) || exit 0
            if [[ -n $s ]]; then cmd_create_home --size "$s"; else cmd_create_home; fi ;;
        "$backup")
            local d
            d=$(z --file-selection --directory --title="$(T 'Choose a folder on another disk')" 2>/dev/null) || exit 0
            cmd_backup "$d" ;;
        "$recover") cmd_recover ;;
        "$status") z --info --width=520 --no-markup --text="$(cmd_status 2>&1)" 2>/dev/null ;;
    esac
}

cmd_autostart() {
    # Silent unless this session was started from a MeccanicOS stick: on an
    # installed system (stick removed) there is nothing to offer, so no
    # "cannot find the boot USB" dialog at login.
    GUI=0
    local list v disk
    disk=$(boot_disk 2>/dev/null) || exit 0
    GUI=1
    if ! is_ventoy && [[ -n $(missing_from_table "$disk" 2>/dev/null) ]]; then
        z --question --width=440 --title="USB Vault" \
            --text="$(T 'This stick was re-flashed and its vault partitions are hidden.\n\nRestore them now? (Nothing is erased.)')" 2>/dev/null &&
            cmd_recover
    fi
    mapfile -t list < <(vaults 2>/dev/null)
    ((${#list[@]})) || exit 0
    for v in "${list[@]}"; do is_open "$v" && exit 0; done
    z --question --width=420 --title="USB Vault" \
        --text="$(T 'An encrypted vault was found on this USB stick.\n\nUnlock it now?')" 2>/dev/null || exit 0
    cmd_open
}

main() {
    local cmd=${1:-status}
    (($#)) && shift
    # The menu runs as you; it calls usb-vault (and so sudo) for each step.
    [[ $cmd == menu ]] && exec ${USB_VAULT_MENU:?usb-vault menu needs the MeccanicOS wrapper} "$@"
    case $cmd in
        -h | --help | help) help_text; exit 0 ;;
        status | summary | list | open | unlock | close | lock | create-partition | create-file | create-home | backup | restore | \
            recover | stick | mount-stick | data-dir | gui | autostart) ;;
        *) usage "$(Tf "unknown command '%s'" "$cmd")" ;;
    esac
    need_root "$cmd" "$@"
    case $cmd in
        status) cmd_status ;;
        summary) cmd_summary ;;
        list) cmd_list ;;
        open | unlock) cmd_open "$@" ;;
        close | lock) cmd_close "$@" ;;
        create-partition) cmd_create_partition "$@" ;;
        create-file) cmd_create_file "$@" ;;
        create-home) cmd_create_home "$@" ;;
        backup) cmd_backup "$@" ;;
        restore) cmd_restore "$@" ;;
        recover) cmd_recover ;;
        stick | mount-stick) cmd_stick ;;
        data-dir) mount_data_partition >/dev/null && data_dir ;; # for the boot-time home unlock
        gui) cmd_gui ;;
        autostart) cmd_autostart ;;
    esac
}

main "$@"
