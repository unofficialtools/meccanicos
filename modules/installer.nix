# Offline disk installer for the live USB.
{
  config,
  lib,
  pkgs,
  distro,
  installedSystem,
  flakeSource,
  flakeCommit,
  ...
}:
let
  python = pkgs.python3;

  # Bytes the installed system will take on the target's ext4 (each file
  # rounded up to 4 KiB blocks), for the installer's progress bar. ~10% more
  # than its plain size; worked out here once instead of at install time.
  installedDiskBytes = pkgs.runCommand "mos-installed-disk-bytes" { } ''
    find $(cat ${pkgs.closureInfo { rootPaths = [ installedSystem ]; }}/store-paths) -printf '%y %s\n' |
      ${pkgs.gawk}/bin/awk '
        $1 == "f" { t += int(($2 + 4095) / 4096) * 4096 }
        $1 == "d" { t += 4096 }
        $1 == "l" && $2 >= 60 { t += 4096 }
        END { printf "%d", t }' > $out
  '';

  mos-install = pkgs.writeShellApplication {
    name = "mos-install";
    runtimeInputs = with pkgs; [
      python
      util-linux # lsblk, sfdisk, wipefs, findmnt, partx, mount
      cryptsetup
      e2fsprogs
      dosfstools
      systemd # udevadm, timedatectl
      networkmanager # nmcli
      setxkbmap
      kbd # loadkeys
      coreutils
      config.system.build.nixos-install
      nixos-enter
      config.system.build.nixos-generate-config
    ];
    text = ''
      if [ "$(id -u)" -ne 0 ]; then
        exec /run/wrappers/bin/sudo --preserve-env=DISPLAY,XAUTHORITY,TERM "$(readlink -f "$0")" "$@"
      fi
      export MECCANICOS_SYSTEM=${installedSystem}
      MECCANICOS_SYSTEM_DISK_BYTES=$(cat ${installedDiskBytes})
      export MECCANICOS_SYSTEM_DISK_BYTES
      export MECCANICOS_FLAKE=${flakeSource}
      export MECCANICOS_COMMIT=${flakeCommit}
      export MECCANICOS_NAME=${lib.escapeShellArg distro.name}
      export MECCANICOS_PYLIB=${../scripts/lib}
      export MECCANICOS_ISO_LABEL=${lib.escapeShellArg config.isoImage.volumeID}
      exec ${python}/bin/python3 ${../scripts/mos-install.py} "$@"
    '';
  };

  launcher = pkgs.makeDesktopItem {
    name = "mos-install";
    desktopName = "Installer"; # the desktop icon's name (also in the menu and command bar)
    comment = "Install ${distro.name} on this computer's disk";
    exec = "xfce4-terminal --class mos-install --title \"Install ${distro.name}\" --geometry 100x32 -x mos-install";
    icon = "${../branding/install.svg}"; # steel plate, matches the metal theme
    categories = [ "System" ];
  };
in
{
  # The installed system is prebuilt and shipped inside the ISO, so
  # installing needs no network and no compiling.
  isoImage.storeContents = [ installedSystem ];

  environment.systemPackages = [
    mos-install
    launcher
  ];

  # "Installer" is a desktop icon: ~/Desktop holds its launcher, and the
  # desktop already shows icons (keyboard.nix).

  # Desktop shortcut for the live user.
  systemd.tmpfiles.rules = [
    "d /home/${distro.liveUser}/Desktop 0755 ${distro.liveUser} users -"
    "L+ /home/${distro.liveUser}/Desktop/install-${distro.id}.desktop - - - - ${launcher}/share/applications/mos-install.desktop"
  ];
}
