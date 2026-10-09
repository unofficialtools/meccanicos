# mos-usb — make a MeccanicOS USB drive

Downloads the latest MeccanicOS, makes a USB drive bootable with
[Ventoy](https://www.ventoy.net) and copies MeccanicOS onto it (Windows, Linux),
or writes MeccanicOS directly to the drive (macOS, where Ventoy does not run;
also the fallback if Ventoy cannot be downloaded). Then it explains how to start
a computer from the drive, and the firmware settings that can get in the way.

It uses only a drive plugged in **after** it says "Insert the USB drive". Before
erasing one it shows a big red warning naming it ("USB DRIVE (/dev/sdb)"; on
Windows "USB DRIVE (Disk 2)") and goes on only if the user types `YES` (any case). A drive that already has Ventoy is not erased: the
ISO is added and nothing on it is deleted, older MeccanicOS ISOs included (if there
is not enough room, mos-usb says so and changes nothing).

Users download it from the [latest release](https://github.com/unofficialtools/meccanicos/releases/tag/latest)
(see the main README, "Make a USB drive"); it is not on the ISO. The release
workflow builds it (`.github/workflows/release.yml`).

## Build and test

Plain Go, standard library only:

```bash
nix shell nixpkgs#go
CGO_ENABLED=0 go test ./...                          # no root, no USB drive needed
MOS_USB_NET=1 go test -run Ventoy -v ./...           # also download Ventoy
CGO_ENABLED=0 GOOS=windows go build -o mos-usb.exe . # any of windows, darwin, linux
```

For a test run against your own files: `MOS_USB_RELEASE=http://host/dir` (a folder
with `SHA256SUMS` and the ISO or its `.partNN` files) and `MOS_USB_CACHE=dir`
(where downloads go; default the user's cache folder).

| File | |
|---|---|
| `main.go` | the steps, waiting for the drive, asking before erasing it |
| `download.go` | SHA256SUMS, resumable checked downloads, joining the parts |
| `ventoy.go` | Ventoy's latest release; copying onto a Ventoy drive; writing directly |
| `guide.go` | how to start MeccanicOS from the drive, firmware gotchas |
| `disk_linux.go`, `disk_darwin.go`, `disk_windows.go` | finding USB drives, writing, Ventoy per system |
| `admin_*.go` | getting administrator rights (sudo; Windows' prompt) |
