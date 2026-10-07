#!/usr/bin/env bash
# mos-tutorial-video - film the tutorial video in a VM (needs KVM and internet).
#
#   ./start tutorial-video                  # writes tutorial/tutorial.mp4
#   nix run .#tutorial-video -- [OUT.mp4] [--show]
#
# Boots the recorder ISO (the live system + modules/tutorial-recorder.nix) in
# QEMU with no window (--show: watch it), lets it play the tour while it
# records its own screen and sound, then makes OUT.mp4: H.264 1920x1080, AAC,
# the spoken lines burnt in as subtitles, waits and pauses left out. About 20 minutes.
set -euo pipefail

OUT=tutorial/tutorial.mp4 SHOW=0
for a in "$@"; do
    case $a in
        --show) SHOW=1 ;;
        -h | --help) awk '/^# mos-tutorial-video/{p=1} p && /^set -euo/{exit} p{sub(/^# ?/, ""); print}' "$0"; exit 0 ;;
        *) OUT=$a ;;
    esac
done
[[ -n ${MECCANICOS_RECORDER_ISO:-} && -f $MECCANICOS_RECORDER_ISO ]] || { echo "run it as: nix run .#tutorial-video" >&2; exit 1; }
[[ -r /dev/kvm && -w /dev/kvm ]] || { echo "needs KVM (/dev/kvm)" >&2; exit 1; }

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
qemu-img create -q -f qcow2 -b "$(readlink -f "$MECCANICOS_RECORDER_ISO")" -F raw "$work/stick.qcow2" 16G
# The recording comes back on a FAT disk: mtools reads it without mounting.
truncate -s 8G "$work/rec.img"
mkfs.vfat -F 32 -n MECCOSREC "$work/rec.img" >/dev/null
cp "$MECCANICOS_VM_OVMF_VARS" "$work/vars.fd"
chmod u+w "$work/vars.fd"

display=(-display none)
((SHOW)) && display=(-display "gtk,zoom-to-fit=on")
gpu=(-device "virtio-vga,xres=1920,yres=1080")
# The host's GPU for the VM's OpenGL (virgl), when QEMU can use it: without it
# the VM draws OpenGL on the CPU, and the Video Player films black. Nix's
# Mesa: on other distributions QEMU from Nix does not find the host's drivers.
# Off unless MECCANICOS_TUTORIAL_GPU=1: with it, Brave showed its first-run
# page and the tour fell out of step (2026-10-08).
render=/dev/dri/renderD128
if [[ ${MECCANICOS_TUTORIAL_GPU:-0} == 1 && -n ${MECCANICOS_MESA:-} && -r $render && -w $render ]]; then
    export GBM_BACKENDS_PATH=$MECCANICOS_MESA/lib/gbm LIBGL_DRIVERS_PATH=$MECCANICOS_MESA/lib/dri \
        __EGL_VENDOR_LIBRARY_FILENAMES=$MECCANICOS_MESA/share/glvnd/egl_vendor.d/50_mesa.json
    # Works if QEMU is still running after 5 seconds (it stops at once if not).
    rc=0
    timeout 5 qemu-system-x86_64 -machine q35,accel=kvm -nodefaults -m 256 -device virtio-vga-gl \
        -display "egl-headless,rendernode=$render" -S -monitor none -serial none >/dev/null 2>&1 || rc=$?
    if ((rc == 124)); then
        gpu=(-device "virtio-vga-gl,xres=1920,yres=1080")
        display=(-display "egl-headless,rendernode=$render")
        ((SHOW)) && display=(-display "gtk,gl=on,zoom-to-fit=on")
        echo "Using the GPU for the VM's graphics."
    else
        echo "The GPU is not usable from QEMU here: the VM draws on the CPU."
    fi
fi
echo "Filming the tutorial in a VM (about 15 minutes)..."
timeout 3600 qemu-system-x86_64 -name "MeccanicOS tutorial" -machine q35,accel=kvm -cpu host \
    -smp "$(nproc)" -m 8G \
    -drive "if=pflash,format=raw,unit=0,readonly=on,file=$MECCANICOS_VM_OVMF_CODE" \
    -drive "if=pflash,format=raw,unit=1,file=$work/vars.fd" \
    -device qemu-xhci -device usb-tablet -device virtio-rng-pci \
    -drive "id=stick,file=$work/stick.qcow2,format=qcow2,if=none" \
    -device "usb-storage,drive=stick,removable=on,bootindex=1" \
    -drive "file=$work/rec.img,format=raw,if=virtio" \
    "${gpu[@]}" "${display[@]}" \
    -nic "user,model=virtio-net-pci" \
    -audiodev none,id=snd0 -device intel-hda -device hda-duplex,audiodev=snd0 \
    -serial "file:$work/serial.log" ||
    echo "the VM did not stop by itself"

for f in record.log tour.err start cues.tsv raw.mkv; do
    mcopy -n -i "$work/rec.img" "::$f" "$work/$f" 2>/dev/null || true
done
[[ -s $work/record.log ]] && sed 's/^/  vm: /' "$work/record.log"
[[ -s $work/tour.err ]] && sed 's/^/  tour: /' "$work/tour.err"
if [[ ! -s $work/raw.mkv || ! -s $work/cues.tsv ]]; then
    keep="${XDG_CACHE_HOME:-$HOME/.cache}/mos-tutorial-video"
    rm -rf "$keep" && mkdir -p "$keep"
    cp "$work"/serial.log "$work"/record.log "$work"/cues.tsv "$keep"/ 2>/dev/null || true
    echo "no recording came back; the VM's logs are in $keep" >&2
    exit 1
fi

# Leave out waits and pauses, burn in the subtitles (scripts/mos-tutorial-encode.py).
mkdir -p "$(dirname "$OUT")"
if ! python3 "$MECCANICOS_TUTORIAL_ENCODE" "$work" "$work/out.mp4" "$MECCANICOS_SUBTITLE_FONTS"; then
    # Keep the recording: it can be encoded again without filming again.
    keep="${XDG_CACHE_HOME:-$HOME/.cache}/mos-tutorial-video"
    rm -rf "$keep" && mkdir -p "$keep"
    cp "$work"/raw.mkv "$work"/cues.tsv "$work"/start "$keep"/
    echo "encoding failed; the recording is kept in $keep:" >&2
    echo "  python3 scripts/mos-tutorial-encode.py $keep OUT.mp4 FONTDIR" >&2
    exit 1
fi
mv "$work/out.mp4" "$OUT"
echo "Done: $OUT ($(du -h "$OUT" | cut -f1), $(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT" | cut -d. -f1) s)"
