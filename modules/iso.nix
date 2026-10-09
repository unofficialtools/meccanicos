# Live-ISO plumbing: boot image, naming, live user, offline behaviour.
{
  config,
  lib,
  pkgs,
  modulesPath,
  distro,
  buildDate,
  buildTime,
  ...
}:
{
  imports = [
    "${modulesPath}/installer/cd-dvd/iso-image.nix"
    "${modulesPath}/profiles/base.nix" # handy CLI tools, filesystems, cryptsetup...
  ];

  # ---- Identity -----------------------------------------------------------
  networking.hostName = distro.hostName;
  # meccanicos-26.05-<build date>-x86_64-linux; `./start iso` and the
  # release workflow append the ISO's own hash when copying it out.
  image.baseName = lib.mkForce (lib.concatStringsSep "-" (
    [
      distro.id
      config.system.nixos.release
      buildDate
      pkgs.stdenv.hostPlatform.system
    ]
  ));
  # /etc/os-release: IMAGE_ID=meccanicos, IMAGE_VERSION=<build date>
  system.image.id = distro.id;
  system.image.version = buildDate;
  # When this ISO was built, e.g. "2026-10-06 17:23 UTC" (System Info).
  # The installer copies it to the installed system.
  environment.etc."${distro.id}/version".text =
    let
      d = buildDate;
      t = buildTime;
    in
    "${builtins.substring 0 4 d}-${builtins.substring 4 2 d}-${builtins.substring 6 2 d} ${builtins.substring 0 2 t}:${builtins.substring 2 2 t} UTC\n";
  isoImage.volumeID = lib.mkForce (lib.toUpper distro.id + "_LIVE"); # max 32 chars

  # ---- Boot ---------------------------------------------------------------
  isoImage.makeEfiBootable = true; # UEFI
  isoImage.makeUsbBootable = true; # legacy BIOS from USB
  isoImage.makeBiosBootable = true;
  # zstd: much faster to build than xz, still small. Use "xz -Xdict-size 100%"
  # for the smallest possible ISO.
  isoImage.squashfsCompression = "zstd -Xcompression-level 15";
  boot.loader.grub.memtest86.enable = true;
  # Long-term-support kernel (6.18): one kernel for both boot entries, since
  # NVIDIA's driver lags the newest kernels. Saves ~0.25 GB vs. two kernels.
  boot.kernelPackages = pkgs.linuxPackages;
  # ZFS (pulled in by profiles/base.nix) often lags the newest kernel and
  # EndeavourOS doesn't ship it either.
  boot.supportedFilesystems.zfs = lib.mkForce false;
  boot.plymouth.enable = true;
  boot.initrd.systemd.enable = true;

  # The live system lives in RAM + squashfs; no swap, no LUKS at boot.
  swapDevices = lib.mkImageMediaOverride [ ];
  fileSystems = lib.mkImageMediaOverride config.lib.isoFileSystems;
  boot.initrd.luks.devices = lib.mkImageMediaOverride { };
  # On a DD-written stick both the whole disk (sda) and its first partition
  # (sda1) carry the ISO label. Mounting /iso from the whole disk would make the
  # kernel refuse exclusive access to every partition on the stick, so usb-vault
  # could not create or open vault partitions. Make the partition win: a whole
  # disk with this label that has partitions gets a lower link priority and is
  # not "ready" for systemd, so the mount waits for the partition. A CD (sr0)
  # or a Ventoy-mapped ISO has no partitions and is used as before. The kernel
  # creates the partitions before announcing the disk, so the test is reliable.
  boot.initrd.services.udev.rules = ''
    SUBSYSTEM=="block", ENV{DEVTYPE}=="disk", ENV{ID_FS_LABEL}=="${config.isoImage.volumeID}", TEST=="%k1", OPTIONS+="link_priority=-100", ENV{SYSTEMD_READY}="0"
    SUBSYSTEM=="block", ENV{DEVTYPE}=="disk", ENV{ID_FS_LABEL}=="${config.isoImage.volumeID}", TEST=="%kp1", OPTIONS+="link_priority=-100", ENV{SYSTEMD_READY}="0"
  '';
  # The stick's own system and persistent-home partitions are not "a USB drive
  # you plugged in": keep them off the desktop and out of Thunar's side pane.
  services.udev.extraRules = ''
    SUBSYSTEM=="block", ENV{ID_FS_LABEL}=="${config.isoImage.volumeID}", ENV{UDISKS_IGNORE}="1"
    SUBSYSTEM=="block", ENV{ID_FS_LABEL}=="${distro.homeLabel}", ENV{UDISKS_IGNORE}="1"
  '';

  # ---- Live user ----------------------------------------------------------
  users.mutableUsers = false;
  users.users.${distro.liveUser} = {
    isNormalUser = true;
    description = "${distro.name} Live";
    extraGroups = [
      "wheel"
      "networkmanager"
      "video"
      "audio"
      "input"
      "disk"
      "dialout"
      "lp"
      "scanner"
    ];
    initialHashedPassword = ""; # empty password; set one at boot with live.passwd=XYZ
    uid = 1000;
  };
  users.users.root.initialHashedPassword = "";
  # The lock screen (Ctrl+Alt+L, idle, suspend) and the login screen accept the
  # empty password; otherwise only "Switch user" got back in. A password set
  # with live.passwd= still works there.
  security.pam.services.xfce4-screensaver.allowNullPassword = true;
  security.pam.services.lightdm.allowNullPassword = true;
  security.sudo.wheelNeedsPassword = false;
  # Let wheel do privileged desktop actions (mounting, gparted...) without prompts.
  security.polkit.enable = true;
  security.polkit.extraConfig = ''
    polkit.addRule(function(action, subject) {
      if (subject.isInGroup("wheel")) { return polkit.Result.YES; }
    });
  '';
  # Optional kernel parameter `live.passwd=secret` sets the live user's password.
  boot.postBootCommands = ''
    for o in $(</proc/cmdline); do
      case "$o" in
        live.passwd=*)
          echo "${distro.liveUser}:''${o#live.passwd=}" | ${pkgs.shadow}/bin/chpasswd ;;
      esac
    done
  '';

  # Autologin leaves the keyring locked: Brave would ask for a keyring password.
  meccanicos.browserBasicPasswordStore = true;

  # Log straight into XFCE; don't suspend a live session behind the user's back.
  services.displayManager.autoLogin = {
    enable = true;
    user = distro.liveUser;
  };
  services.logind.settings.Login = {
    HandleLidSwitch = "ignore";
    IdleAction = "ignore";
  };

  # No fixed time zone (UTC until one is picked), so `mos-config set
  # time.zone` can write /etc/localtime; a persistent home re-applies it.
  time.timeZone = lib.mkDefault null;

  # ---- Persistent home (usb-vault create-home) ------------------------------
  # If the stick has an encrypted home partition, ask for its password on the
  # boot screen and mount it as the live user's home before the desktop starts.
  # An empty password (or 3 wrong ones) starts a normal fresh session.
  systemd.services.mos-persistent-home = {
    description = "Unlock the persistent home on the USB stick";
    wantedBy = [ "multi-user.target" ];
    # Nothing logs in (desktop or a console) until the home is decided.
    before = [
      "display-manager.service"
      "systemd-user-sessions.service"
      "getty@tty1.service"
    ];
    after = [
      "systemd-udevd.service"
      "local-fs.target"
    ];
    unitConfig.DefaultDependencies = false;
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      TimeoutStartSec = "infinity";
    };
    path = with pkgs; [
      util-linux # dmesg
      cryptsetup
      systemd
      coreutils
      kbd # chvt
      config.boot.plymouth.package
    ];
    script = ''
      udevadm settle --timeout=10 || true
      # A home partition, or a mos-home.luks file on the stick's data
      # partition (or in meccanicos/ on the Ventoy partition when booted through
      # Ventoy; usb-vault knows where).
      dev=$(blkid -t LABEL=${distro.homeLabel} -o device | head -n1 || true)
      if [ -z "$dev" ]; then
        mountpoint -q /run/usb-vault/data || mounted_data=1
        dir=$(USB_VAULT_USER=${distro.liveUser} /run/current-system/sw/bin/usb-vault data-dir 2>/dev/null || true)
        if [ -n "$dir" ] && [ -f "$dir/mos-home.luks" ]; then
          dev=$dir/mos-home.luks
        fi
      fi
      # Leave nothing mounted unless the home was unlocked.
      cleanup() {
        if [ ! -e /dev/mapper/mos-home ] && [ -n "''${mounted_data:-}" ]; then
          umount /run/usb-vault/data || true
        fi
      }
      trap cleanup EXIT
      [ -n "$dev" ] || exit 0
      # Ask on the text console, in plain sight. With the boot splash up,
      # systemd leaves the question to Plymouth, which on some machines
      # (text-mode splash, some graphics) never draws it: the boot looked
      # stuck at "Show Plymouth Boot Screen" while it waited for this.
      plymouth quit 2>/dev/null || true
      chvt 1 2>/dev/null || true
      dmesg -n 1 2>/dev/null || true # no kernel messages on top of the prompt
      printf '\033[2J\033[H' >/dev/tty1 2>/dev/null || true # a clear screen
      systemd-tty-ask-password-agent --watch --console=/dev/tty1 &
      agent=$!
      trap 'kill $agent 2>/dev/null || true; cleanup' EXIT
      for try in 1 2 3; do
        pass=$(systemd-ask-password --timeout=0 --id=mos-home \
          "Password for your saved ${distro.name} home (Enter to skip):") || exit 0
        [ -n "$pass" ] || { echo "Skipped: fresh session"; exit 0; }
        if printf '%s' "$pass" | cryptsetup open --key-file=- "$dev" mos-home; then
          break
        fi
        echo "Wrong password ($try/3)"
        echo "Wrong password ($try/3)" >/dev/tty1 2>/dev/null || true
      done
      [ -e /dev/mapper/mos-home ] || exit 0
      home=/home/${distro.liveUser}
      mkdir -p "$home"
      mount -o noatime /dev/mapper/mos-home "$home"
      chown ${distro.liveUser}:users "$home"
      chmod 700 "$home"
      echo "Persistent home mounted on $home"
    '';
  };

  # ---- Fully offline ------------------------------------------------------
  # Everything is baked into the squashfs; nothing is fetched at boot.
  # Avoid services that block or spam logs without a network.
  systemd.services.NetworkManager-wait-online.enable = false;
  networking.networkmanager.enable = true;
  services.timesyncd.enable = lib.mkDefault true; # harmless offline, syncs when online
  nix.settings.experimental-features = [
    "nix-command"
    "flakes"
  ];
  # Docs (man pages, NixOS manual) are included so help works offline.
  documentation.enable = true;
  documentation.man.enable = true;
  documentation.nixos.enable = true;

  # VM guest helpers (EndeavourOS ships these too).
  services.spice-vdagentd.enable = true;
  services.qemuGuest.enable = true;
  virtualisation.vmware.guest.enable = true;
  virtualisation.hypervGuest.enable = true;
  # hypervGuest force-loads the Hyper-V drivers in the initrd, which fails on
  # every other machine ("Failed to start Load Kernel Modules"). Ship them
  # instead: udev loads hv_vmbus from its ACPI id on Hyper-V, and the rest
  # follow from the VMBus devices it finds.
  boot.initrd.kernelModules = lib.mkForce [
    "dm_mod"
    "loop"
    "nls_cp437"
    "nls_iso8859-1"
    "overlay"
    "vfat"
    "vmw_pvscsi"
  ];
  boot.initrd.availableKernelModules = [
    "hv_balloon"
    "hv_netvsc"
    "hv_storvsc"
    "hv_utils"
    "hv_vmbus"
  ];

  nixpkgs.config.allowUnfree = true; # firmware + NVIDIA, like EndeavourOS
  system.stateVersion = "26.05";
}
