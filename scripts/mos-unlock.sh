#!/usr/bin/env bash
# mos-unlock - choose how the encrypted disk is unlocked at boot.
# What it does: the help, below.
set -euo pipefail

# Translations (scripts/lib/mos_i18n.sh); without them, English.
# shellcheck source=/dev/null disable=SC2059
declare -F T >/dev/null || . "${MOS_I18N_SH:-$(dirname "$0")/lib/mos_i18n.sh}" 2>/dev/null ||
  { T() { printf '%s' "$1"; } && Tf() { local f=$1 && shift && printf -- "$f" "$@"; }; }
help=$(T "mos-unlock - choose how the encrypted disk is unlocked at boot.

  mos-unlock status      list the unlock methods enrolled on the disk
  mos-unlock tpm         unlock automatically with this PC's TPM chip
  mos-unlock key         unlock with a FIDO2 security key (YubiKey, Nitrokey, …)
  mos-unlock recovery    create a printable recovery key (keep it safe!)
  mos-unlock remove-tpm  stop unlocking with the TPM
  mos-unlock remove-key  remove enrolled FIDO2 keys
  mos-unlock remote [FILE]
                           unlock over SSH at boot (wired network): allow the
                           SSH keys in FILE (default: your ~/.ssh/authorized_keys)
                           to reach the password prompt with ssh -p 2222 root@HOST
  mos-unlock remove-remote  stop remote unlock

Your password always keeps working as a fallback. Each command asks for a
current password (or recovery key) to authorise the change.")

# Help needs no disk and no root.
case ${1:-} in
    -h | --help | help) printf '%s\n' "$help"; exit 0 ;;
esac

DEV=/dev/disk/by-partlabel/MOS_CRYPT
[[ -e $DEV ]] || { Tf 'No MeccanicOS encrypted disk found (%s).\n' "$DEV" >&2; exit 1; }
if [[ $EUID -ne 0 ]]; then exec sudo "$(readlink -f "$0")" "$@"; fi

KEYS=/etc/nixos/remote-unlock-keys
HOSTKEY=/etc/secrets/initrd/ssh_host_ed25519_key

# Rebuild for the next boot: the boot stage (initrd) holds the SSH server.
rebuild() {
    printf '%s\n' "$(T 'Rebuilding the boot stage (takes a minute)...')"
    nixos-rebuild boot --flake /etc/nixos#installed
}

remote() {
    local src=${1:-}
    if [[ -z $src ]]; then
        src=$(getent passwd "${SUDO_USER:-root}" | cut -d: -f6)/.ssh/authorized_keys
    fi
    [[ -r $src ]] || { Tf 'No SSH keys found in %s (give a file: mos-unlock remote FILE).\n' "$src" >&2; exit 1; }
    grep -E '^(ssh-|ecdsa-|sk-)' "$src" > "$KEYS.tmp" || true
    [[ -s $KEYS.tmp ]] || { rm -f "$KEYS.tmp"; Tf 'No SSH public keys in %s.\n' "$src" >&2; exit 1; }
    mv "$KEYS.tmp" "$KEYS"
    Tf 'Allowed keys (%s) saved in %s.\n' "$(wc -l < "$KEYS")" "$KEYS"
    if [[ ! -f $HOSTKEY ]]; then
        mkdir -p "${HOSTKEY%/*}"
        chmod 700 "${HOSTKEY%/*}"
        ssh-keygen -q -t ed25519 -N "" -C "mos-initrd" -f "$HOSTKEY"
    fi
    rebuild
    echo
    printf '%s\n' "$(T 'Done. From the next boot, on a wired network:')"
    printf '    %s\n' "$(T 'ssh -p 2222 root@<this machine>    then type the disk password')"
    printf '%s %s\n' "$(T "This machine's addresses now:")" "$(hostname -I 2>/dev/null || true)"
    printf '%s\n' "$(T "Give it a fixed address on your router (DHCP reservation) so it's easy to find.")"
    Tf 'Boot-stage host key: %s\n' "$(ssh-keygen -l -f "$HOSTKEY.pub")"
    printf '%s\n' "$(T '(different from the normal SSH host key, so ssh warns once: use a separate known_hosts entry)')"
}

case ${1:-status} in
    status)
        systemd-cryptenroll "$DEV"
        if [[ -f $KEYS ]]; then
            Tf 'Remote unlock: on (ssh -p 2222 root@HOST, %s key(s) in %s)\n' "$(wc -l < "$KEYS")" "$KEYS"
        else
            printf '%s\n' "$(T 'Remote unlock: off (mos-unlock remote)')"
        fi
        ;;
    remote) remote "${2:-}" ;;
    remove-remote)
        rm -f "$KEYS"
        rebuild
        printf '%s\n' "$(T 'Remote unlock is off from the next boot.')"
        ;;
    tpm)
        printf '%s\n' "$(T "Binding the disk to this PC's TPM (PCR 7 = firmware/Secure Boot state).")"
        printf '%s\n' "$(T 'The disk then unlocks by itself on this PC; your login password still protects your account.')"
        printf '%s\n' "$(T 'After firmware updates you may be asked for the disk password once; run this again then.')"
        systemd-cryptenroll --wipe-slot=tpm2 --tpm2-device=auto --tpm2-pcrs=7 "$DEV"
        printf '%s\n' "$(T 'Done. Restart to try it.')"
        ;;
    key)
        printf '%s\n' "$(T 'Insert your FIDO2 security key and touch it when it blinks.')"
        systemd-cryptenroll --fido2-device=auto --fido2-with-user-presence=yes "$DEV"
        printf '%s\n' "$(T 'Done. At boot, insert the key and touch it (or type your password).')"
        ;;
    recovery)
        printf '%s\n' "$(T 'A recovery key will be shown ONCE. Write it down or print it and keep it somewhere safe.')"
        systemd-cryptenroll --recovery-key "$DEV"
        ;;
    remove-tpm) systemd-cryptenroll --wipe-slot=tpm2 "$DEV" ;;
    remove-key) systemd-cryptenroll --wipe-slot=fido2 "$DEV" ;;
    -h | --help | help) printf '%s\n' "$help" ;;
    *) Tf 'unknown command: %s (try --help)\n' "$1" >&2; exit 2 ;;
esac
