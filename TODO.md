# Roadmap

## Next
- [x] **Ventoy support:** vaults and the persistent home as files in `meccanicos/` on
      the Ventoy partition, mounted through a device-mapper view of the partition
      (no `VTOY_LINUX_REMOUNT`); `usb-vault stick`; VM test (`checks.ventoy`).

## Ideas
- [x] Installed systems follow the MeccanicOS repository's latest release: `mos-upgrade`
      (`/etc/nixos` keeps only your files; `lib.mkInstalled` in `flake.nix`)
- [ ] Optional btrfs with snapshots in the installer
- [ ] Secure Boot (lanzaboote), making TPM unlock stronger
- [ ] Localised installer texts
