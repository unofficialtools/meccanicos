# Hardware support, in step with EndeavourOS

MeccanicOS's hardware support (`../drivers.nix`, and parts of `iso.nix` and
`desktop.nix`) started as a translation of the
[EndeavourOS](https://endeavouros.com) live ISO's package list. This folder
keeps that translation honest:

| File | What |
|---|---|
| `endeavouros.txt` | EndeavourOS's `packages.x86_64`, at the commit named in its header: the list we follow |
| `map.toml` | for every package there: what provides it here (`by`, checked), or why it isn't shipped (`skip`, with the reason) |
| `../../scripts/drivers-check.py` | the check (`./start drivers-check`) |

## The check

```sh
./start drivers-check              # the map covers the snapshot exactly; every `by` holds on the live ISO
./start drivers-check --upstream   # also: did EndeavourOS change its list since the snapshot?
./start drivers-check --update     # move the snapshot to EndeavourOS's newest list
```

A `by` entry is checked on the evaluated live ISO, so a nixpkgs update that
drops or renames something fails the check instead of going unnoticed:
`option:PATH` (set), `option:PATH~VALUE` (a list containing VALUE),
`package:NAME` (installed: system packages, firmware, graphics drivers,
fonts, udev rules, NetworkManager plugins).

**Every Monday**, GitHub Actions runs `--upstream`
(`.github/workflows/drivers.yml`). When something needs a decision it opens
one issue, labelled `drivers` (later runs comment on it), listing exactly
which packages.

## When EndeavourOS changes its list

1. `./start drivers-check --update`: the snapshot moves to the newest list,
   and the check names the packages added or removed.
2. For each one added, find what it is for. Hardware (a driver, firmware, a
   VM's guest tools)? Usually ship it: add it to `drivers.nix` (an option, or a
   package) and map it with `by`. Otherwise, map it to what already does the
   job here, or `skip` it with the reason.
3. Remove the entries of packages that left the list (and consider whether
   what provided them can go too).
4. `./start drivers-check` until it says *Nothing to do*; commit the
   snapshot, the map and `drivers.nix` together.

## At each NixOS release

When `flake.nix` moves to a new `nixos-YY.05`, by hand, besides
`./start drivers-check`:

- **NVIDIA:** is `nvidiaPackages.stable` still the right branch? Does the
  open driver still start at Turing (device id `0x1e00`, in `mos-gpu-driver`,
  `drivers.nix`)? Did nixpkgs drop a legacy branch (older cards then run
  nouveau, which is fine, but say so in the release notes)?
- **Firmware:** did any firmware change licence (redistributable or not)?
  MeccanicOS ships only what can be shared (`enableRedistributableFirmware`,
  never `enableAllFirmware`).
- **The release notes' backward-incompatible changes** for `hardware.*`,
  `services.pipewire`, `networking.networkmanager`, `boot.initrd`: options
  renamed or moved show up as failing `by` entries here.
- **The VM tests** (`nix flake check`): the live ISO, the installer, Ventoy.
