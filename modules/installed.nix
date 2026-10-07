# MeccanicOS installed on a disk by `mos-install`.
#
# This configuration is prebuilt into the ISO so installation needs no
# network. Everything the installer asks (language, time zone, keyboard,
# Wi-Fi, user, orientation) is applied as runtime state, and also written to
# /etc/nixos/local.nix so future `nixos-rebuild` runs bake it in.
{
  config,
  lib,
  pkgs,
  distro,
  ...
}:
let
  # Applies the keyboard layout and screen orientation chosen at install time
  # (stored in /etc/meccanicos/settings) to the running X server.
  displaySetup = pkgs.writeShellScript "mos-display-setup" ''
    export PATH=${
      lib.makeBinPath [
        pkgs.setxkbmap
        pkgs.xrandr
        pkgs.gawk
        pkgs.coreutils
      ]
    }
    XKB_LAYOUT=us XKB_VARIANT= ORIENTATION=landscape
    [ -r /etc/meccanicos/settings ] && . /etc/meccanicos/settings
    setxkbmap -layout "$XKB_LAYOUT" ''${XKB_VARIANT:+-variant "$XKB_VARIANT"} || true
    if [ "$ORIENTATION" = portrait ]; then
      for o in $(xrandr --listmonitors | awk 'NR>1 {print $NF}'); do
        xrandr --output "$o" --rotate left || true
      done
    fi
  '';
  # Written by `mos-unlock remote` (absent in the repo).
  remoteUnlockKeys = ../remote-unlock-keys;
in
{
  options.meccanicos.autoUpgrade = lib.mkOption {
    type = lib.types.bool;
    default = true;
    description = "Weekly background update, applied at the next boot.";
  };
  # Unlock the encrypted disk over SSH while the machine boots (wired network).
  # On by itself once `mos-unlock remote` has saved the allowed SSH keys
  # in /etc/nixos/remote-unlock-keys.
  options.meccanicos.remoteUnlock = lib.mkOption {
    type = lib.types.bool;
    default = builtins.pathExists remoteUnlockKeys;
    description = "Unlock the disk at boot over SSH (port 2222, wired network). See mos-unlock remote.";
  };
  options.meccanicos.hibernate = lib.mkOption {
    type = lib.types.bool;
    default = true;
    description = "Hibernate (suspend to disk) into a RAM-sized swap file on the encrypted root.";
  };

  config = {
  # ---- Disk layout created by the installer (GPT partition labels) --------
  #   MOS_EFI   1 GiB FAT32  -> /boot
  #   MOS_CRYPT rest  LUKS2  -> /dev/mapper/cryptroot (ext4) -> /
  boot.initrd.luks.devices.cryptroot = {
    device = "/dev/disk/by-partlabel/MOS_CRYPT";
    allowDiscards = true;
  };
  fileSystems."/" = {
    device = "/dev/mapper/cryptroot";
    fsType = "ext4";
    options = [ "noatime" ];
  };
  fileSystems."/boot" = {
    device = "/dev/disk/by-partlabel/MOS_EFI";
    fsType = "vfat";
    options = [
      "umask=0077"
      "nofail"
    ];
  };
  zramSwap.enable = true; # compressed RAM swap, no swap partition needed

  # ---- Hibernation ----------------------------------------------------------
  # A swap file as large as the RAM, inside the encrypted root, so the
  # hibernation image is encrypted too. Made at boot (the installed system is
  # prebuilt, so its size can't be known in advance) and remade when the RAM
  # changes; skipped when the disk would be left with less than 10 GiB free.
  # Hibernation is only ever explicit (Log Out dialog, systemctl hibernate);
  # resuming needs the disk password, like any start.
  # zram stays the everyday swap (priority 5); the file has priority 0.
  # Resume needs no kernel parameters: systemd stores the file's location in
  # the HibernateLocation EFI variable, and the initrd resumes from it right
  # after the disk is unlocked.
  systemd.services.mos-swapfile = lib.mkIf config.meccanicos.hibernate {
    description = "Swap file for hibernation";
    wantedBy = [ "multi-user.target" ];
    after = [ "local-fs.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = with pkgs; [
      util-linux
      coreutils
      gawk
    ];
    script = ''
      file=/var/lib/swap/hibernate
      gib=$((1024 * 1024 * 1024))
      ram=$(awk '/^MemTotal:/ {print $2 * 1024}' /proc/meminfo)
      size=$(((ram + gib - 1) / gib * gib)) # rounded up to whole GiB
      mkdir -p -m 700 /var/lib/swap
      if [ "$(stat -c %s "$file" 2>/dev/null)" != "$size" ]; then
        swapoff "$file" 2>/dev/null || true
        rm -f "$file" "$file.tmp"
        free=$(df -B1 --output=avail /var/lib/swap | tail -n1)
        if [ "$free" -lt $((size + 10 * gib)) ]; then
          echo "Not enough free disk space for a $((size / gib)) GiB swap file: hibernation is off"
          exit 0
        fi
        fallocate -l "$size" "$file.tmp"
        chmod 600 "$file.tmp"
        mkswap -q "$file.tmp"
        mv "$file.tmp" "$file"
        echo "Created a $((size / gib)) GiB swap file for hibernation"
      fi
      grep -q "^$file " /proc/swaps || swapon -p 0 "$file"
    '';
  };
  services.fstrim.enable = true;

  # ---- Boot ---------------------------------------------------------------
  boot.loader.systemd-boot = {
    enable = true;
    configurationLimit = 10;
    editor = false; # no editing kernel cmdline at boot (security)
  };
  boot.loader.efi.canTouchEfiVariables = true;
  boot.initrd.systemd.enable = true;
  boot.plymouth.enable = true; # graphical LUKS passphrase prompt
  boot.kernelPackages = pkgs.linuxPackages; # LTS, same as the ISO (see iso.nix)
  hardware.enableAllHardware = true; # boots on any machine, like the ISO

  # ---- Identity / locale (runtime-adjustable) ----------------------------
  networking.hostName = lib.mkDefault distro.hostName;
  networking.networkmanager.enable = true;
  time.timeZone = lib.mkDefault null; # /etc/localtime written by the installer
  # Every language the installer offers (scripts/mos-install.py) works
  # without rebuilding; "all" would add ~0.2 GB of locales nobody can pick.
  i18n.supportedLocales = [
    "C.UTF-8/UTF-8"
    "be_BY.UTF-8/UTF-8"
    "bg_BG.UTF-8/UTF-8"
    "cs_CZ.UTF-8/UTF-8"
    "da_DK.UTF-8/UTF-8"
    "de_AT.UTF-8/UTF-8"
    "de_CH.UTF-8/UTF-8"
    "de_DE.UTF-8/UTF-8"
    "el_GR.UTF-8/UTF-8"
    "en_AU.UTF-8/UTF-8"
    "en_CA.UTF-8/UTF-8"
    "en_GB.UTF-8/UTF-8"
    "en_IE.UTF-8/UTF-8"
    "en_NZ.UTF-8/UTF-8"
    "en_SG.UTF-8/UTF-8"
    "en_US.UTF-8/UTF-8"
    "en_ZA.UTF-8/UTF-8"
    "es_AR.UTF-8/UTF-8"
    "es_ES.UTF-8/UTF-8"
    "es_MX.UTF-8/UTF-8"
    "et_EE.UTF-8/UTF-8"
    "fi_FI.UTF-8/UTF-8"
    "fr_BE.UTF-8/UTF-8"
    "fr_CA.UTF-8/UTF-8"
    "fr_FR.UTF-8/UTF-8"
    "he_IL.UTF-8/UTF-8"
    "hr_HR.UTF-8/UTF-8"
    "hu_HU.UTF-8/UTF-8"
    "is_IS.UTF-8/UTF-8"
    "it_IT.UTF-8/UTF-8"
    "ja_JP.UTF-8/UTF-8"
    "kk_KZ.UTF-8/UTF-8"
    "ko_KR.UTF-8/UTF-8"
    "lt_LT.UTF-8/UTF-8"
    "lv_LV.UTF-8/UTF-8"
    "mk_MK.UTF-8/UTF-8"
    "mt_MT.UTF-8/UTF-8"
    "nb_NO.UTF-8/UTF-8"
    "nl_NL.UTF-8/UTF-8"
    "pl_PL.UTF-8/UTF-8"
    "pt_BR.UTF-8/UTF-8"
    "pt_PT.UTF-8/UTF-8"
    "ro_RO.UTF-8/UTF-8"
    "ru_RU.UTF-8/UTF-8"
    "sk_SK.UTF-8/UTF-8"
    "sl_SI.UTF-8/UTF-8"
    "sr_RS/UTF-8" # glibc's name for sr_RS.UTF-8
    "sv_SE.UTF-8/UTF-8"
    "tr_TR.UTF-8/UTF-8"
    "uk_UA.UTF-8/UTF-8"
    "zh_CN.UTF-8/UTF-8"
    "zh_TW.UTF-8/UTF-8"
  ];
  # /etc/locale.conf and /etc/vconsole.conf are plain files written by the
  # installer (editable, or via localectl). (i18n.imperativeLocale would do
  # this, but it fails to evaluate in nixpkgs 26.05.)
  environment.etc."locale.conf".enable = false;
  environment.etc."vconsole.conf".enable = false;
  # Shells and the desktop session take LANG/LC_* from /etc/locale.conf,
  # overriding the build-time default.
  environment.extraInit = ''
    if [ -r /etc/locale.conf ]; then set -a; . /etc/locale.conf; set +a; fi
  '';
  services.xserver.displayManager.setupCommands = "${displaySetup}"; # greeter
  environment.etc."xdg/autostart/mos-display-setup.desktop".text = ''
    [Desktop Entry]
    Type=Application
    Name=Keyboard and screen setup
    NoDisplay=true
    Exec=${displaySetup}
  '';

  # ---- Users & security ---------------------------------------------------
  users.mutableUsers = true; # installer creates the user; passwords stay local
  users.users.root.hashedPassword = "!"; # no root login; use sudo
  security.sudo.wheelNeedsPassword = lib.mkDefault false; # passwordless sudo for wheel (local.nix may say true)
  services.openssh = {
    enable = true;
    openFirewall = true;
    settings = {
      # Keys only (~/.ssh/authorized_keys): no passwords, no keyboard-
      # interactive prompts, no root login.
      AuthenticationMethods = "publickey";
      PubkeyAuthentication = true;
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitEmptyPasswords = false;
      PermitRootLogin = "no";
    };
  };

  # ---- Updating the installed system --------------------------------------
  # /etc/nixos holds the distro flake + local.nix (your install-time choices).
  environment.systemPackages = [
    (pkgs.writeShellApplication {
      name = "mos-unlock";
      runtimeInputs = [
        pkgs.systemd
        pkgs.openssh
        pkgs.coreutils
        pkgs.gnugrep
        pkgs.hostname
        config.system.build.nixos-rebuild
      ];
      text = builtins.readFile ../scripts/mos-unlock.sh;
    })
    # Newest MeccanicOS from distro.repo (flake.nix), keeping local.nix & co.
    (pkgs.writeShellApplication {
      name = "mos-update";
      runtimeInputs = [
        pkgs.git
        pkgs.rsync
        pkgs.coreutils
        pkgs.gnused
        pkgs.gnugrep
        config.system.build.nixos-rebuild
      ];
      text = ''
        export MECCANICOS_REPO=''${MECCANICOS_REPO:-${distro.repo}}
      '' + builtins.readFile ../scripts/mos-update.sh;
    })
    (pkgs.writeShellScriptBin "mos-rebuild" ''
      # Apply changes made in /etc/nixos (packages.nix, local.nix, modules/…)
      case "''${1-}" in
        -h | --help)
          echo "mos-rebuild - apply the changes made in /etc/nixos (packages.nix, local.nix, modules/...)"
          echo
          echo "  mos-rebuild [NIXOS-REBUILD OPTIONS]   sudo nixos-rebuild switch --flake /etc/nixos#installed ..."
          exit 0 ;;
      esac
      exec sudo nixos-rebuild switch --flake /etc/nixos#installed "$@"
    '')
    (pkgs.writeShellScriptBin "mos-upgrade" ''
      # Pull the newest packages for the pinned NixOS release, then rebuild
      case "''${1-}" in
        -h | --help)
          echo "mos-upgrade - pull the newest packages for the pinned NixOS release, then rebuild"
          echo
          echo "  mos-upgrade [NIXOS-REBUILD OPTIONS]   nix flake update, then mos-rebuild ..."
          exit 0 ;;
      esac
      set -e
      sudo nix flake update --flake /etc/nixos
      exec sudo nixos-rebuild switch --flake /etc/nixos#installed "$@"
    '')
  ];

  # ---- Disk unlock with TPM / FIDO2 key (mos-unlock) --------------------
  # Enrolled tokens are used automatically at boot; the password always works.
  boot.initrd.systemd.tpm2.enable = true;
  boot.initrd.systemd.fido2.enable = true;
  security.tpm2.enable = true;

  # ---- Remote unlock over SSH (mos-unlock remote) -------------------------
  # The boot stage that asks for the disk password also gets a wired network
  # (DHCP) and an SSH server on port 2222: `ssh -p 2222 root@<machine>` goes
  # straight to the password prompt. Keys: /etc/nixos/remote-unlock-keys plus
  # every user's keys in local.nix. Its host key lives outside the store, in
  # /etc/secrets/initrd (made by mos-unlock remote).
  boot.initrd.systemd.network = lib.mkIf config.meccanicos.remoteUnlock {
    enable = true;
    networks."10-wired" = {
      matchConfig.Type = "ether";
      networkConfig.DHCP = "yes";
    };
  };
  boot.initrd.network.ssh = lib.mkIf config.meccanicos.remoteUnlock {
    enable = true;
    port = 2222;
    hostKeys = [ "/etc/secrets/initrd/ssh_host_ed25519_key" ];
    authorizedKeys = lib.concatMap (u: u.openssh.authorizedKeys.keys) (
      lib.filter (u: u.isNormalUser) (lib.attrValues config.users.users)
    );
    authorizedKeyFiles = lib.optional (builtins.pathExists remoteUnlockKeys) remoteUnlockKeys;
  };
  boot.initrd.systemd.users.root.shell = lib.mkIf config.meccanicos.remoteUnlock "/bin/systemd-tty-ask-password-agent";
  # Wired network cards (and USB adapters) common on PCs, laptops and VMs.
  boot.initrd.availableKernelModules = lib.mkIf config.meccanicos.remoteUnlock [
    "e1000e"
    "igb"
    "igc"
    "ixgbe"
    "i40e"
    "r8169"
    "tg3"
    "bnx2"
    "bnxt_en"
    "atlantic"
    "alx"
    "virtio_net"
    "r8152"
    "ax88179_178a"
    "asix"
    "cdc_ether"
    "cdc_ncm"
  ];

  # ---- Crash dumps: keep only the newest ------------------------------------
  # Whenever a new dump lands, delete the older ones. (systemd also expires
  # dumps after two weeks.)
  systemd.paths.mos-coredump-cleanup = {
    wantedBy = [ "paths.target" ];
    pathConfig.PathChanged = "/var/lib/systemd/coredump";
  };
  systemd.services.mos-coredump-cleanup = {
    description = "Keep only the newest crash dump";
    serviceConfig.Type = "oneshot";
    path = [
      pkgs.coreutils
      pkgs.findutils
    ];
    script = ''
      cd /var/lib/systemd/coredump 2>/dev/null || exit 0
      ls -1t -- core.* 2>/dev/null | tail -n +2 | xargs -r rm -f --
    '';
  };

  # ---- Automatic updates ----------------------------------------------------
  # Weekly: update /etc/nixos/flake.lock and build the new system for the next
  # boot (nothing changes under your feet). A notification asks you to restart.
  # Turn off in /etc/nixos/local.nix with:  meccanicos.autoUpgrade = false;
  systemd.services.mos-auto-upgrade = lib.mkIf config.meccanicos.autoUpgrade {
    description = "Update MeccanicOS (applied at next boot)";
    wants = [ "network-online.target" ];
    after = [ "network-online.target" ];
    unitConfig.ConditionACPower = true; # not on battery
    path = [
      config.nix.package
      config.system.build.nixos-rebuild
      pkgs.git
      pkgs.coreutils
    ];
    serviceConfig = {
      Type = "oneshot";
      Nice = 15;
      IOSchedulingClass = "idle";
    };
    script = ''
      cd /etc/nixos || exit 1
      cp flake.lock flake.lock.previous 2>/dev/null || true
      nix flake update --flake /etc/nixos
      nixos-rebuild boot --flake /etc/nixos#installed
    '';
  };
  systemd.timers.mos-auto-upgrade = lib.mkIf config.meccanicos.autoUpgrade {
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnCalendar = "weekly";
      Persistent = true;
      RandomizedDelaySec = "6h";
    };
  };
  # Tell the logged-in user when a newer system is waiting for a restart.
  systemd.user.services.mos-update-notice = {
    description = "Tell the user an update is ready";
    serviceConfig.Type = "oneshot";
    path = [
      pkgs.libnotify
      pkgs.coreutils
    ];
    script = ''
      next=$(readlink -f /nix/var/nix/profiles/system)
      now=$(readlink -f /run/current-system)
      [ "$next" != "$now" ] || exit 0
      seen="''${XDG_CACHE_HOME:-$HOME/.cache}/meccanicos/update-notified"
      mkdir -p "''${seen%/*}"
      [ "$(cat "$seen" 2>/dev/null)" = "$next" ] && exit 0
      notify-send -i system-software-update -t 0 "${distro.name} update ready" \
        "Restart the computer to finish updating."
      echo "$next" > "$seen"
    '';
  };
  systemd.user.timers.mos-update-notice = {
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnStartupSec = "2min";
      OnUnitActiveSec = "1h";
    };
  };

  # ---- Laptops ----------------------------------------------------------------
  # Closing the lid suspends, on battery and on AC (never hibernates). With an
  # external screen connected (or a dock), it does nothing: work goes on there.
  # Only logind acts on the lid: XFCE's power manager leaves it alone
  # (modules/keyboard.nix).
  services.logind.settings.Login = {
    HandleLidSwitch = "suspend";
    HandleLidSwitchExternalPower = "suspend";
    HandleLidSwitchDocked = "ignore"; # logind: "docked" = a dock or a second screen
  };
  services.thermald.enable = pkgs.stdenv.hostPlatform.isx86; # Intel thermal management (idles on AMD)
  # Power-saver profile on battery, balanced on AC.
  services.udev.extraRules = ''
    SUBSYSTEM=="power_supply", ATTR{type}=="Mains", ATTR{online}=="0", RUN+="${pkgs.power-profiles-daemon}/bin/powerprofilesctl set power-saver"
    SUBSYSTEM=="power_supply", ATTR{type}=="Mains", ATTR{online}=="1", RUN+="${pkgs.power-profiles-daemon}/bin/powerprofilesctl set balanced"
  '';

  # ---- Nix ----------------------------------------------------------------
  nix.settings = {
    experimental-features = [
      "nix-command"
      "flakes"
    ];
    auto-optimise-store = true;
    trusted-users = [ "@wheel" ];
  };
  # /tmp and builds (mos-update, nixos-rebuild) on the disk, never in RAM: a
  # system rebuild can need several GB. (The live USB keeps them in RAM.)
  boot.tmp.useTmpfs = false;
  nix.settings.build-dir = "/nix/var/nix/builds";
  nix.gc = {
    automatic = true;
    dates = "weekly";
    options = "--delete-older-than 30d";
  };
  nixpkgs.config.allowUnfree = true;
  documentation.nixos.enable = true;

  # VM guest helpers (harmless on real hardware).
  services.spice-vdagentd.enable = true;
  services.qemuGuest.enable = true;

  # Same kernel/ZFS caveat as the ISO.
  boot.supportedFilesystems.zfs = lib.mkForce false;

  system.stateVersion = "26.05";
  };
}
