# Roadmap

## Next
- [x] **Ventoy support:** vaults and the persistent home as files in `meccanicos/` on
      the Ventoy partition, mounted through a device-mapper view of the partition
      (no `VTOY_LINUX_REMOUNT`); `usb-vault stick`; VM test (`checks.ventoy`).

## Drivers: keeping up with EndeavourOS
`modules/drivers.nix` was mapped by hand from EndeavourOS's live-ISO package list
(`packages.x86_64`); nothing records which version, so drift goes unnoticed.
- [ ] **Snapshot:** `modules/drivers/endeavouros.txt`, upstream's list at a pinned
      EndeavourOS commit (recorded in the file).
- [ ] **Mapping:** `modules/drivers/map.toml`, every Arch package either mapped to what
      replaces it (`nixos = "hardware.enableRedistributableFirmware"`) or skipped with a
      reason (`skip = "not redistributable"`); nothing left unchecked.
- [ ] **`./start drivers-check`:** upstream side: fetch the current list, diff it with the
      snapshot, fail on new, removed or unmapped packages (the to-do list); our side:
      evaluate the ISO and check each mapped entry is really there (option set, package
      in the closure, kernel module built), so a nixpkgs bump can't drop one silently.
- [ ] **Weekly GitHub Actions job** running it, opening an issue (or a PR updating the
      snapshot) with the packages that need a decision.
- [ ] **At each NixOS release** (nixos-YY.05), by hand: the NVIDIA open-driver cut-off
      (`0x1e00`, Turing, in `mos-gpu-driver`), legacy NVIDIA branches nixpkgs drops,
      newly unfree firmware.
- [ ] Later: `mos-hw-report` (lspci/lsusb, "firmware failed to load" lines; to the stick
      or an issue): what breaks on real machines; a `mos-fleet hardware` summary from the
      fleet's logs; the installer suggesting the matching `nixos-hardware` module (DMI
      vendor/model) in `local.nix`.

## Ideas
- [x] Installed systems follow the MeccanicOS repository's latest release: `mos-upgrade`
      (`/etc/nixos` keeps only your files; `lib.mkInstalled` in `flake.nix`)
- [ ] Optional btrfs with snapshots in the installer
- [ ] Secure Boot (lanzaboote), making TPM unlock stronger
- [ ] Localised installer texts
