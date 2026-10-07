#!/usr/bin/env bash
# mos-vm - boot MeccanicOS in QEMU, e.g. to try it or record a demo video.
#
#   nix run .#vm                          # builds the ISO if needed, boots it
#   nix run .#vm -- --res 2560x1440       # any options below after "--"
#
# Options
#   --iso PATH        ISO to boot (default: the one built by this flake)
#   --res WxH         screen resolution inside the VM (default 1920x1080)
#   --mem SIZE        RAM (default 6G)
#   --cpus N          CPU cores (default: half of the host's, max 8)
#   --disk SIZE       also attach an empty hard disk (e.g. 64G) to film the installer
#   --installed       boot the hard disk only (after installing), no USB stick
#   --fresh           start over: new USB stick, disk and firmware settings
#   --offline         no network (show that everything works offline)
#   --gl              GPU-accelerated display (smoother; needs working host OpenGL)
#   --fullscreen      start full screen (toggle with Ctrl+Alt+F)
#   --no-audio        no sound device
#   --bios            legacy BIOS instead of UEFI (live USB only)
#   --state DIR       where the VM's stick/disk/firmware live (default ~/.cache/mos-vm)
#   --dry-run         print the QEMU command instead of running it
#
# The virtual USB stick is copy-on-write on top of the ISO and is kept between
# runs, so vaults and the persistent home you create survive (--fresh resets).
#
# In the window: click inside, then press Ctrl+Alt+G so keys like Super+Space
# go to MeccanicOS instead of your own desktop (Ctrl+Alt+G again to release).
# Recording: capture the QEMU window with OBS Studio (Window Capture), or your
# desktop's recorder (GNOME: Ctrl+Shift+Alt+R; KDE: Spectacle; macOS: Cmd+Shift+5).
set -euo pipefail

ISO="${MECCANICOS_VM_ISO:-}"
RES=1920x1080 MEM=6G DISK="" INSTALLED=0 FRESH=0 OFFLINE=0 GL=0 FULL=0 AUDIO=1 BIOS=0 DRY=0
STATE="${XDG_CACHE_HOME:-$HOME/.cache}/mos-vm"
ncpu=$(nproc)
CPUS=$((ncpu / 2 > 8 ? 8 : (ncpu / 2 < 2 ? 2 : ncpu / 2)))
OVMF_CODE="${MECCANICOS_VM_OVMF_CODE:-}"
OVMF_VARS="${MECCANICOS_VM_OVMF_VARS:-}"

die() { echo "mos-vm: $*" >&2; exit 1; }
usage() {
    awk '/^# mos-vm - /{p=1} p && /^set -euo/{exit} p{sub(/^# ?/, ""); print}' "$0"
    exit 0
}

while (($#)); do
    case $1 in
        --iso) ISO=$2; shift 2 ;;
        --res) RES=$2; shift 2 ;;
        --mem) MEM=$2; shift 2 ;;
        --cpus) CPUS=$2; shift 2 ;;
        --disk) DISK=$2; shift 2 ;;
        --installed) INSTALLED=1; shift ;;
        --fresh) FRESH=1; shift ;;
        --offline) OFFLINE=1; shift ;;
        --gl) GL=1; shift ;;
        --fullscreen) FULL=1; shift ;;
        --no-audio) AUDIO=0; shift ;;
        --bios) BIOS=1; shift ;;
        --state) STATE=$2; shift 2 ;;
        --dry-run) DRY=1; shift ;;
        -h | --help) usage ;;
        *) die "unknown option $1 (try --help)" ;;
    esac
done

[[ $RES =~ ^([0-9]+)x([0-9]+)$ ]] || die "--res must look like 1920x1080"
XRES=${BASH_REMATCH[1]} YRES=${BASH_REMATCH[2]}
((INSTALLED && BIOS)) && die "the installed system needs UEFI; drop --bios"

mkdir -p "$STATE"
if ((FRESH)); then
    rm -f "$STATE"/stick.qcow2 "$STATE"/disk.qcow2 "$STATE"/OVMF_VARS.fd
    echo "Starting fresh."
fi

drives=()
if ((!INSTALLED)); then
    [[ -n $ISO ]] || die "no ISO given (use --iso PATH, or run it as: nix run .#vm)"
    [[ -f $ISO ]] || die "ISO not found: $ISO"
    ISO=$(readlink -f "$ISO")
    stick="$STATE/stick.qcow2"
    # Re-create the stick when the ISO changed (new build), keeping nothing stale.
    if [[ -f $stick ]] && [[ $(cat "$STATE/stick.iso" 2>/dev/null) != "$ISO" ]]; then
        echo "New ISO: resetting the virtual USB stick."
        rm -f "$stick"
    fi
    if [[ ! -f $stick ]]; then
        qemu-img create -q -f qcow2 -b "$ISO" -F raw "$stick" 16G
        echo "$ISO" >"$STATE/stick.iso"
    fi
    drives+=(-drive "id=stick,file=$stick,format=qcow2,if=none"
        -device "usb-storage,drive=stick,removable=on,bootindex=1")
fi
if [[ -n $DISK ]] || ((INSTALLED)); then
    disk="$STATE/disk.qcow2"
    if [[ ! -f $disk ]]; then
        ((INSTALLED)) && die "no installed disk yet: run once with --disk 64G and install"
        qemu-img create -q -f qcow2 "$disk" "$DISK"
        echo "Created an empty $DISK hard disk for the installer (shows up as /dev/vda)."
    fi
    drives+=(-drive "id=hd,file=$disk,format=qcow2,if=none"
        -device "virtio-blk-pci,drive=hd,bootindex=$((INSTALLED ? 1 : 2))")
fi

firmware=()
if ((!BIOS)); then
    [[ -n $OVMF_CODE && -f $OVMF_CODE ]] || die "UEFI firmware (OVMF) not found; run via 'nix run .#vm'"
    vars="$STATE/OVMF_VARS.fd"
    [[ -f $vars ]] || { cp "$OVMF_VARS" "$vars"; chmod u+w "$vars"; }
    firmware=(-drive "if=pflash,format=raw,unit=0,readonly=on,file=$OVMF_CODE"
        -drive "if=pflash,format=raw,unit=1,file=$vars")
fi

accel=(-machine "q35,accel=kvm" -cpu host)
if [[ ! -r /dev/kvm || ! -w /dev/kvm ]]; then
    echo "warning: /dev/kvm not usable, falling back to (very slow) emulation." >&2
    echo "         Enable virtualization in the BIOS and add yourself to the 'kvm' group." >&2
    accel=(-machine "q35,accel=tcg" -cpu max)
fi

if ((GL)); then
    video=(-device "virtio-vga-gl,xres=$XRES,yres=$YRES" -display "gtk,gl=on,zoom-to-fit=off")
else
    video=(-device "virtio-vga,xres=$XRES,yres=$YRES" -display "gtk,zoom-to-fit=off")
fi
((FULL)) && video[-1]+=",full-screen=on"

net=(-nic "user,model=virtio-net-pci")
((OFFLINE)) && net=(-nic none)

sound=()
if ((AUDIO)); then
    if pactl info >/dev/null 2>&1; then
        sound=(-audiodev "pa,id=snd0" -device intel-hda -device "hda-duplex,audiodev=snd0")
    else
        echo "note: no PulseAudio/PipeWire server found, starting without sound." >&2
    fi
fi

cmd=(qemu-system-x86_64 -name "MeccanicOS" "${accel[@]}" -smp "$CPUS" -m "$MEM"
    -device qemu-xhci -device usb-tablet -device virtio-rng-pci
    "${firmware[@]}" "${drives[@]}" "${video[@]}" "${net[@]}" "${sound[@]}"
    -boot menu=on)

if ((DRY)); then
    printf '%q ' "${cmd[@]}"
    echo
    exit 0
fi
echo "Booting MeccanicOS (${XRES}x${YRES}, ${MEM} RAM, ${CPUS} CPUs). Ctrl+Alt+G grabs the keyboard."
exec "${cmd[@]}"
