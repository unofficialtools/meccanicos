# MeccanicOS on a Raspberry Pi (SD card): the work it takes

A plan, not a feature yet. Target: a **Raspberry Pi 4 or 5 with 2 GB of RAM
or more**, booting MeccanicOS from an SD card, with **no office suite**.
Everything else stays as close to the PC version as the hardware allows.

## Which Pi

| Model | CPU | Verdict |
|---|---|---|
| Pi Zero / Zero W | ARMv6, 512 MB | No: NixOS has no prebuilt ARMv6 packages (everything compiled from source) and Brave/Chromium don't run on it. |
| Pi Zero 2 W | aarch64, 512 MB | No: too little memory for Xfce and a browser. |
| **Pi 4 (2 GB+)** | aarch64, Cortex-A72 | Yes. No AES instructions: disk encryption needs Adiantum (below). |
| **Pi 5 (2 GB+)** | aarch64, Cortex-A76 | Yes, and noticeably faster. Has AES instructions. Recommended. |

With 2 GB: Xfce (about 400 MB) and Brave with a few tabs, with zram (compressed
swap in RAM). 4 GB is comfortable.

## Where things stand (checked 2026-10-18)

The installed system was evaluated for `aarch64-linux` (the flake's
`installed` configuration with `nixpkgs.hostPlatform = "aarch64-linux"`):

- Of its 476 packages, only **OnlyOffice** has no ARM build in nixpkgs. It is
  left out on ARM (no office suite).
- **`modules/drivers.nix`** stops the evaluation: Intel's graphics libraries
  (`intel-media-driver`, `vpl-gpu-rt`, via `intel-gmmlib`) and the NVIDIA
  driver exist only for x86.
- With both left out, the whole system evaluates. Brave, VSCodium, Piper,
  Ollama, rclone (mos-dropbox), CUPS and the rest have ARM builds.
- **`modules/python.nix`** evaluates but downloads the **x86** build of
  python-build-standalone: on ARM it needs the
  `aarch64-unknown-linux-gnu` file and its hash.

## Same repository

The Pi version lives in this repository, built by the same flake from the
same modules, not in a separate one:

- Nearly everything is shared: only `drivers.nix` and OnlyOffice stop the
  ARM build. The other modules, the `mos-*` tools, mos-look, the fleet agent,
  the shell course and most tests carry over unchanged.
- One version: a tag builds both the ISO and the SD image, so a fix reaches
  both at once, with one set of release notes and one `mos-upgrade --to <tag>`.
- Installed systems follow this repository's `latest` release; a Pi follows
  the same tag and takes its own architecture's build. A fleet can mix PCs
  and Pis in one `hosts.toml`.
- A separate repository could import this flake and copy nothing, but would
  need its own releases and CI, and would lag behind it. Worth it only if
  other people maintain the Pi version on their own schedule.

The cost here: an ARM job in CI (in parallel, on GitHub's free ARM runners),
one more file in each release, and the Pi inputs (`nixos-raspberrypi`,
probably `nixos-hardware`) in `flake.lock`. PC builds don't use them, and
Nix should then not fetch them.

Layout:

```
modules/                 shared by both (desktop, branding, shell, browser, …)
  hardware/
    pc.nix               from drivers.nix: microcode, Intel/AMD/NVIDIA, xf86 drivers,
                         enableAllHardware; also the x86 parts of installed.nix
                         (systemd-boot/EFI, hibernation, TPM)
    pi.nix               boot (nixos-raspberrypi / nixos-hardware), zram,
                         Wi-Fi and Bluetooth settings (section 4)
    pi-gpio.nix          GPIO, I²C, SPI: packages, groups, udev, overlays (section 5)
  drivers.nix            what's left of it: firmware, Mesa, PipeWire, Bluetooth
  iso.nix, installer.nix, branding-boot.nix    PC only, as now
  firstboot.nix          Pi only: the first-boot setup (section 6)
```

The flake builds each system from the shared modules plus one hardware
module: `mkSystem { system = "x86_64-linux"; hardware = ./modules/hardware/pc.nix; }`
or `{ system = "aarch64-linux"; hardware = ./modules/hardware/pi.nix; }`.
Small differences inside shared modules (the office entry, `nvidia-settings`,
the Python download) use `pkgs.stdenv.hostPlatform.isx86`/`isAarch64`
instead of new files.

## The work

### 1. The flake: build for two architectures

- `flake.nix` hard-codes `system = "x86_64-linux"` (used for
  `nixpkgs.hostPlatform`, `legacyPackages`, the checks). Make it a
  parameter: `common` takes the system, and the PC and Pi systems are built
  from it.
- New outputs: `nixosConfigurations.pi` (the system) and
  `packages.aarch64-linux.sd-image` (the card image).
- `lib.mkInstalled` and the fleet's `mkFleet` take a `system` (a fleet may
  mix PCs and Pis; a host's `profiles/*.nix` or `hosts.toml` entry says which).
- `nixosConfigurations.live`, `recorder` and the ISO stay x86 only.

### 2. Modules: what changes on ARM

Gate with `lib.mkIf pkgs.stdenv.hostPlatform.isx86` (as
`services.thermald` in `installed.nix` already is), or split a module in two.

| Module | On ARM |
|---|---|
| `drivers.nix` | Split: keep firmware, Mesa, PipeWire, Bluetooth, printing pieces; x86 only: microcode, Intel VA-API/QuickSync, NVIDIA (`hardware.nvidia`, `mos-gpu-driver`, the nouveau/nvidia modprobe hooks), `xf86-video-*`. The Pi uses Mesa's `v3d`/`vc4` with `modesetting`. `hardware.enableAllHardware` is x86-minded: replace with the Pi's modules. |
| `branding.nix`, `menu.nix` | No `office` entry (OnlyOffice) and no OnlyOffice dark-theme step at login; no `nvidia-settings` (`gpu`). |
| `python.nix` | The aarch64 python-build-standalone file, chosen by `hostPlatform`. |
| `browser.nix` | Recheck the GPU flags (`--enable-unsafe-swiftshader`, `--ignore-gpu-blocklist`) on the Pi's V3D GPU. |
| `ai.nix` | Ollama runs on the CPU only: suggest small models (1–3 B parameters); `mos-ai-setup` should say so and check free memory. |
| `installed.nix` | Boot, disk layout, hibernation and unlock change (sections 3 and 6). |
| `branding-boot.nix`, `iso.nix`, `installer.nix` | Not used (no ISO, no GRUB/syslinux). |
| `vault.nix` | The USB vault works as is (any USB stick plugged into the Pi). |
| `scripts/mos-vm.sh` | Runs `qemu-system-x86_64` and the x86 ISO: leave out on ARM, or run an aarch64 image. |
| `scripts/mos-doctor`, `mos-config` | Check every x86 assumption (EFI variables, TPM, `efibootmgr`, battery, hibernation). |

New on ARM: zram swap (`zramSwap.enable`, about 50–100 % of RAM), the Pi's
firmware and kernel, and the boot configuration.

### 3. Boot and the card image

- **Pi 4**: the generic NixOS aarch64 SD image works (firmware, U-Boot,
  extlinux); `nixos-hardware`'s `raspberry-pi-4` module adds the device tree
  and GPU settings. The mainline LTS kernel supports it.
- **Pi 5**: U-Boot support is limited; the firmware boots the kernel
  directly. The `nixos-raspberrypi` flake (vendor kernel, `config.txt`,
  firmware) is the practical route. Mainline support for the Pi 5 (its RP1
  chip: USB, Ethernet, GPIO) is still arriving: test before relying on it.
- The image: NixOS's `sd-image` module (a FAT firmware partition and an ext4
  root, grown to fill the card at first boot), compressed with zstd.
- Boot branding: Plymouth as on the PC; the firmware's rainbow screen off
  (`disable_splash=1`).

### 4. Wi-Fi and Bluetooth

Both Pis have the same Broadcom/Cypress chip (CYW43455: Wi-Fi 5 on SDIO,
Bluetooth 5 on a UART), driven by the kernel's `brcmfmac` and `hci_uart`.

**Firmware.** Nothing to add: `drivers.nix` sets
`hardware.enableRedistributableFirmware`, which on ARM also installs
`raspberrypiWirelessFirmware` (nixpkgs, `all-firmware.nix`). It holds the
Wi-Fi firmware, the board files the driver looks for by model
(`brcmfmac43455-sdio.raspberrypi,4-model-b.txt`, `…5-model-b…`), the
`clm_blob` with each country's channels, and the Bluetooth patch
(`BCM4345C0.hcd`). It is redistributable, so it fits MeccanicOS's
"nothing that can't be shared" rule; update the comment in `drivers.nix`
("no Broadcom BT") to say the Pi's is included.

**The device tree.** Wi-Fi and Bluetooth only appear if the device tree
describes them:

- Pi 5 with `nixos-raspberrypi`: its vendor device tree does.
- Pi 4 on the generic image: `nixos-hardware`'s `raspberry-pi-4` module
  provides the right `bcm2711-rpi-4-b.dtb`. Bluetooth needs the UART
  assigned to it (the default; don't enable the serial console on the same
  pins: `enable_uart=1` or `console=ttyAMA0` takes them).

**Settings.**

- Wi-Fi country: set the regulatory domain from the setup's time zone or
  country (`networking.wireless.regulatoryDomain`, or
  `cfg80211.ieee80211_regdom=IT` on the kernel command line). Without it the
  chip stays on the world-safe channels and 5 GHz may be missing.
- NetworkManager as on the PC. Turn off Wi-Fi power saving, which makes
  `brcmfmac` drop connections or lag:
  `networking.networkmanager.wifi.powersave = false;`.
- WPA3: `brcmfmac` handles SAE in the chip's firmware, and support depends
  on the firmware version; test WPA3-only networks, and fall back to
  WPA2/WPA3 mixed if they fail.
- Bluetooth: `hardware.bluetooth.enable` and blueman as on the PC. The UART
  link is slower than USB: Bluetooth audio works, but Wi-Fi and Bluetooth
  share one antenna, so heavy Wi-Fi traffic can make audio stutter.

**Checks** (a "Pi" section in `mos-doctor`):

```
dmesg | grep -i brcmfmac        # firmware loaded, no "-2" (file missing)
nmcli device                    # wlan0 present
iw reg get                      # the right country
bluetoothctl show               # a controller, Powered: yes
```

### 5. GPIO (the 40-pin header)

**The interface.** The kernel's GPIO character device
(`/dev/gpiochip*`) with **libgpiod**. Not the old `/sys/class/gpio` (removed
from current kernels) and not `RPi.GPIO` (doesn't work on the Pi 5, whose
header is wired through its RP1 chip).

- Pi 4: the header's chip is `pinctrl-bcm2711`.
- Pi 5: the header's chip is `pinctrl-rp1`; its number (`gpiochip0` or
  `gpiochip4`) has changed between kernels.
- So programs should find pins **by name**, not by chip number: the Pi's
  device trees name the lines `GPIO17`, etc., the same on both models.

**Packages** (all in nixpkgs for aarch64):

| Package | What |
|---|---|
| `libgpiod` (2.2) | `gpiodetect`, `gpioinfo`, `gpioget`, `gpioset`, `gpiomon` |
| `python3Packages.libgpiod` | the official Python binding |
| `python3Packages.gpiozero` (2.0) + `lgpio` | the beginner-friendly library; `lgpio` is its backend on both Pis |
| `python3Packages.rpi-lgpio` | an `RPi.GPIO`-compatible layer, for old tutorials' code |
| `libraspberrypi` / `raspberrypifw` | the Pi's own tools (`vcgencmd` for temperature, clocks, throttling) |

MeccanicOS's own `python3` is python-build-standalone with pip
(`python.nix`), not Nix's Python: in a venv, `pip install gpiozero lgpio`
needs the `lgpio` C library at build time. Simplest: also ship a Nix Python
with these modules as `python3-gpio` (or put them on the standalone Python's
path), and say so in the help.

**Permissions.** GPIO devices are root-only by default. Add a `gpio` group
and a udev rule, and put the user in it (the first-boot setup does, like
`networkmanager`):

```nix
users.groups.gpio = { };
services.udev.extraRules = ''
  SUBSYSTEM=="gpio", KERNEL=="gpiochip*", GROUP="gpio", MODE="0660"
'';
hardware.i2c.enable = true;   # /dev/i2c-*, group i2c
```

Same for SPI (`spidev`, group `spi`) and PWM if wanted.

**I²C, SPI, 1-Wire, PWM.** These are switched on in the device tree:

- Pi 5 with `nixos-raspberrypi`: as on Raspberry Pi OS, `config.txt`
  settings (`dtparam=i2c_arm=on`, `dtparam=spi=on`,
  `dtoverlay=w1-gpio`, `dtoverlay=pwm-2chan`), set from Nix.
- Pi 4 on the generic image: U-Boot passes NixOS's own device tree, so
  `config.txt` lines have no effect. Use `hardware.deviceTree.overlays`
  (or `nixos-hardware`'s `hardware.raspberry-pi."4".i2c1.enable`,
  `.apply-overlays-dtmerge.enable`).
- A `mos-config` setting (`pi.i2c`, `pi.spi`, `pi.onewire`: on/off) that
  writes these, so nobody edits Nix for it.

**Check** (an LED with a resistor between GPIO17, pin 11, and ground, pin 9):

```
gpiodetect                      # the header's chip is listed
gpioinfo | grep GPIO17          # the line, by name
gpioset GPIO17=1                # LED on (Ctrl+C ends it)
python3-gpio -c 'from gpiozero import LED; from time import sleep; l = LED(17); l.on(); sleep(2)'
```

Tests: a VM has no GPIO; libgpiod's `gpio-sim` kernel module provides a
fake chip, so the `gpio` group and udev rule can be tested in the aarch64 VM
test. The real header goes on the hardware checklist before each Pi release.

### 6. What the card is: one system, not live + installer

The PC version is a live USB that installs onto the computer's disk. On a Pi
the card **is** the computer's disk, so:

- The card image is the **installed system**, with a first-boot setup
  replacing the installer: name, user, password, computer name, Wi-Fi,
  time zone (the same questions and checks as `mos-install`).
- **Encryption**: an SD image can't ship encrypted with the user's
  password. Options, in order of effort:
  1. Encrypt only `/home`: at first boot, create a LUKS partition in the
     free space (as the USB's MOS-HOME is) and move the user's home into it.
  2. Full-disk: boot the card, then install onto a USB SSD or the Pi 5's
     NVMe with the normal LUKS layout (an ARM `mos-install` without GRUB/EFI),
     and boot from that.
  - On the **Pi 4**, LUKS must use Adiantum
    (`--cipher xchacha12,aes-adiantum-plain64`): without AES instructions,
    AES-XTS is several times slower. The Pi 5 uses the usual AES-XTS.
- **No hibernation** (no firmware support), **no TPM** (`mos-unlock tpm`,
  `tpm-pin` unavailable; FIDO2 and remote unlock over SSH still work).
- Card wear: keep `/tmp` and logs in RAM or limited; recommend a USB SSD for
  daily use.

### 7. Updates on a 2 GB Pi

`mos-upgrade` runs `nix flake update` and rebuilds **on the computer**.
Evaluating a NixOS system needs about 1–2 GB of memory, which a 2 GB Pi
barely has. Options:

- zram plus a swap file, to get through the evaluation (slow but works);
- better: CI builds the Pi system for each release and pushes it to a binary
  cache (e.g. Cachix, or the fleet server's), and `mos-upgrade` on a Pi
  downloads the built system (`nix copy` of the release's `toplevel`) instead
  of evaluating it. Fleet-managed Pis can get theirs from the fleet server the
  same way.

### 8. Releases and CI

- Build the image on GitHub's **ARM runners** (`ubuntu-24.04-arm`, free for
  public repositories): native, no emulation.
- Release files: `meccanicos-<release>-aarch64-linux-…-sd.img.zst` (split
  under 2 GB like the ISO), in the same `SHA256SUMS`. `get-iso` and the
  README gain a Pi section.
- `mos-usb`: a "write an SD card" mode (raw write and verify, no Ventoy) for
  Linux, macOS and Windows. Alternatively, document Raspberry Pi Imager's
  "Use custom" option.
- **Tests**: NixOS VM tests need KVM. Whether GitHub's ARM runners offer it is
  uncertain; without it they run under emulation (slow). Options: a reduced
  aarch64 test, or a self-hosted Pi 5 runner; plus a boot test on real
  hardware before each Pi release.

### 9. Docs and the tutorial

- README: a "Raspberry Pi" section (which models, writing the card, first
  boot, what's missing: office suite, hibernation, TPM).
- The shell course and the cheat sheet are unchanged; the tutorial video stays
  the PC one.

## Suggested order

1. Make `system` a parameter in the flake; gate `drivers.nix`, OnlyOffice and
   `nvidia-settings`; fix `python.nix`. Goal: `nixosConfigurations.pi`
   evaluates. (About a day.)
2. Build an SD image for the **Pi 5** with `nixos-raspberrypi`; boot it on a
   real Pi with the desktop, Wi-Fi, Bluetooth, sound and Brave working
   (section 4's checks).
3. GPIO: the packages, the `gpio` group and udev rule, `python3-gpio`, and
   the LED check (section 5); then I²C/SPI through `mos-config`.
4. First-boot setup and the encrypted `/home` (section 6, option 1).
5. Updates through a binary cache; zram tuning for 2 GB.
6. CI on ARM runners, release files, `mos-usb` SD-card mode, README.
7. Pi 4 support (U-Boot path, Adiantum), then full-disk install to SSD/NVMe.
