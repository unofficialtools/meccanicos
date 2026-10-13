# Roadmap

## Next
- [x] **Ventoy support:** vaults and the persistent home as files in `meccanicos/` on
      the Ventoy partition, mounted through a device-mapper view of the partition
      (no `VTOY_LINUX_REMOUNT`); `usb-vault stick`; VM test (`checks.ventoy`).

## Drivers: keeping up with EndeavourOS
`modules/drivers.nix` was mapped by hand from EndeavourOS's live-ISO package list
(`packages.x86_64`); nothing records which version, so drift goes unnoticed.
- [x] **Snapshot:** `modules/drivers/endeavouros.txt`, upstream's list at a pinned
      EndeavourOS commit (recorded in the file).
- [x] **Mapping:** `modules/drivers/map.toml`, every package either provided
      (`by = ["option:hardware.enableRedistributableFirmware"]`, `"package:…"`) or skipped
      with a reason (`skip = "not redistributable"`): 165 provided, 72 skipped.
- [x] **`./start drivers-check`** (`scripts/drivers-check.py`): the map covers the snapshot
      exactly, and every `by` holds on the evaluated live ISO (option set, package
      installed), so a nixpkgs update can't drop one silently; `--upstream` compares with
      EndeavourOS's newest list, `--update` moves the snapshot.
- [x] **Weekly GitHub Actions job** (`.github/workflows/drivers.yml`): one issue, labelled
      `drivers`, listing what needs a decision (later runs comment on it).
- [x] **At each NixOS release** (nixos-YY.05), by hand: the checklist in
      `modules/drivers/README.md` (NVIDIA branch and open-driver cut-off, legacy branches,
      firmware licences, renamed options).
- [ ] Not checked yet: kernel modules themselves (e.g. that the kernel still builds one a
      driver needs); only options and packages are.
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
