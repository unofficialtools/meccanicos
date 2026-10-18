#!/usr/bin/env bash
# mos-unlock - choose how the encrypted disk is unlocked at boot.
#
#   mos-unlock status      list the unlock methods enrolled on the disk
#   mos-unlock tpm         unlock automatically with this PC's TPM chip
#   mos-unlock key         unlock with a FIDO2 security key (YubiKey, Nitrokey, …)
#   mos-unlock recovery    create a printable recovery key (keep it safe!)
#   mos-unlock remove-tpm  stop unlocking with the TPM
#   mos-unlock remove-key  remove enrolled FIDO2 keys
#   mos-unlock remote [FILE]
#                            unlock over SSH at boot (wired network): allow the
#                            SSH keys in FILE (default: your ~/.ssh/authorized_keys)
#                            to reach the password prompt with ssh -p 2222 root@HOST
#   mos-unlock remove-remote  stop remote unlock
#
# Your password always keeps working as a fallback. Each command asks for a
# current password (or recovery key) to authorise the change.
set -euo pipefail

# Help needs no disk and no root.
case ${1:-} in
    -h | --help | help) sed -n '/^# mos-unlock - /,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
esac

# The encrypted partition this system runs from: the LUKS device under the
# root file system (lsblk -s walks from / down to the disk). Only when that
# finds none (the live USB) the partition label, which every MeccanicOS disk
# shares: with several such disks attached it would be a guess, so stop.
root_luks() {
    local src
    src=$(findmnt -nvo SOURCE /) || return 1
    lsblk -nlps -o NAME,FSTYPE "$src" 2>/dev/null | awk '$2 == "crypto_LUKS" { print $1; exit }'
}
DEV=$(root_luks || true)
if [[ -z $DEV ]]; then
    mapfile -t labelled < <(lsblk -nlp -o NAME,PARTLABEL 2>/dev/null | awk '$2 == "MOS_CRYPT" { print $1 }')
    case ${#labelled[@]} in
        0) echo "No MeccanicOS encrypted disk found." >&2; exit 1 ;;
        1) DEV=${labelled[0]} ;;
        *) echo "Several MeccanicOS encrypted disks are attached (${labelled[*]}):" >&2
           echo "start the MeccanicOS you want to change and run mos-unlock there." >&2
           exit 1 ;;
    esac
fi
if [[ $EUID -ne 0 ]]; then exec sudo "$(readlink -f "$0")" "$@"; fi

KEYS=/etc/nixos/remote-unlock-keys
HOSTKEY=/etc/secrets/initrd/ssh_host_ed25519_key

# Rebuild for the next boot: the boot stage (initrd) holds the SSH server.
rebuild() {
    echo "Rebuilding the boot stage (takes a minute)..."
    nixos-rebuild boot --flake /etc/nixos#installed
}

remote() {
    local src=${1:-}
    if [[ -z $src ]]; then
        src=$(getent passwd "${SUDO_USER:-root}" | cut -d: -f6)/.ssh/authorized_keys
    fi
    [[ -r $src ]] || { echo "No SSH keys found in $src (give a file: mos-unlock remote FILE)." >&2; exit 1; }
    grep -E '^(ssh-|ecdsa-|sk-)' "$src" > "$KEYS.tmp" || true
    [[ -s $KEYS.tmp ]] || { rm -f "$KEYS.tmp"; echo "No SSH public keys in $src." >&2; exit 1; }
    mv "$KEYS.tmp" "$KEYS"
    echo "Allowed keys ($(wc -l < "$KEYS")) saved in $KEYS."
    if [[ ! -f $HOSTKEY ]]; then
        mkdir -p "${HOSTKEY%/*}"
        chmod 700 "${HOSTKEY%/*}"
        ssh-keygen -q -t ed25519 -N "" -C "mos-initrd" -f "$HOSTKEY"
    fi
    rebuild
    echo
    echo "Done. From the next boot, on a wired network:"
    echo "    ssh -p 2222 root@<this machine>    then type the disk password"
    echo "This machine's addresses now: $(hostname -I 2>/dev/null || true)"
    echo "Give it a fixed address on your router (DHCP reservation) so it's easy to find."
    echo "Boot-stage host key: $(ssh-keygen -l -f "$HOSTKEY.pub")"
    echo "(different from the normal SSH host key, so ssh warns once: use a separate known_hosts entry)"
}

case ${1:-status} in
    status)
        systemd-cryptenroll "$DEV"
        echo "Disk: $DEV"
        if [[ -f $KEYS ]]; then
            # The boot stage that has it is the one built after the keys were
            # saved: saved since this boot started, it works from the next one.
            booted=$(awk '$1 == "btime" { print $2 }' /proc/stat)
            when="on"
            (( $(stat -c %Y "$KEYS") > booted )) && when="on from the next boot"
            echo "Remote unlock: $when (ssh -p 2222 root@HOST, $(wc -l < "$KEYS") key(s) in $KEYS)"
        else
            echo "Remote unlock: off (mos-unlock remote)"
        fi
        ;;
    remote) remote "${2:-}" ;;
    remove-remote)
        rm -f "$KEYS"
        rebuild
        echo "Remote unlock is off from the next boot."
        ;;
    tpm)
        echo "Binding the disk to this PC's TPM (PCR 7 = firmware/Secure Boot state)."
        echo "The disk then unlocks by itself on this PC; your login password still protects your account."
        echo "After firmware updates you may be asked for the disk password once; run this again then."
        systemd-cryptenroll --wipe-slot=tpm2 --tpm2-device=auto --tpm2-pcrs=7 "$DEV"
        echo "Done. Restart to try it."
        ;;
    key)
        echo "Insert your FIDO2 security key and touch it when it blinks."
        systemd-cryptenroll --fido2-device=auto --fido2-with-user-presence=yes "$DEV"
        echo "Done. At boot, insert the key and touch it (or type your password)."
        ;;
    recovery)
        echo "A recovery key will be shown ONCE. Write it down or print it and keep it somewhere safe."
        systemd-cryptenroll --recovery-key "$DEV"
        ;;
    remove-tpm) systemd-cryptenroll --wipe-slot=tpm2 "$DEV" ;;
    remove-key) systemd-cryptenroll --wipe-slot=fido2 "$DEV" ;;
    -h | --help | help) sed -n '/^# mos-unlock - /,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//' ;;
    *) echo "unknown command: $1 (try --help)" >&2; exit 2 ;;
esac
