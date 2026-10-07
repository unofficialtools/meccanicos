# Encrypted storage on the boot USB stick: the `usb-vault` tool, its
# full-screen menu (the launcher), and a login prompt that offers to unlock
# an existing vault.
{ pkgs, distro, ... }:
let
  usb-vault = pkgs.writeShellApplication {
    name = "usb-vault";
    runtimeInputs = with pkgs; [
      coreutils
      util-linux # lsblk, blkid, findmnt, partx, sfdisk, wipefs, isosize, fallocate
      cryptsetup
      e2fsprogs
      exfatprogs
      rsync
      gnused
      gawk
      findutils
      gnugrep
      systemd # udevadm
      lvm2 # dmsetup: mount the Ventoy partition alongside Ventoy's own map
      xdg-utils # "Open the USB stick's files"
      zenity
      # sudo is NOT listed: the setuid one lives in /run/wrappers/bin (already on PATH)
    ];
    # Labels come from flake.nix so the ISO, the tool and udev agree.
    text = ''
      export VAULT_LABEL="''${VAULT_LABEL:-${distro.vaultLabel}}"
      export DATA_LABEL="''${DATA_LABEL:-${distro.dataLabel}}"
      export HOME_LABEL="''${HOME_LABEL:-${distro.homeLabel}}"
      USB_VAULT_SELF="$(readlink -f "$0")"
      export USB_VAULT_SELF
      export ISO_LABEL="''${ISO_LABEL:-${pkgs.lib.toUpper distro.id}_LIVE}"
      export MECCANICOS_PYLIB=${../scripts/lib}
      export USB_VAULT_MENU="${pkgs.python3}/bin/python3 ${../scripts/usb-vault-menu.py}"
      exec ${pkgs.bash}/bin/bash ${../scripts/usb-vault.sh} "$@"
    '';
  };

  launcher = pkgs.makeDesktopItem {
    name = "usb-vault";
    desktopName = "Encrypted Storage (USB Vault)";
    comment = "Create, unlock or lock encrypted storage on this USB stick";
    # The full-screen menu (scripts/usb-vault-menu.py); `usb-vault gui` is the zenity one.
    exec = ''xfce4-terminal --title "USB Vault" --geometry 90x32 -x usb-vault menu'';
    icon = "drive-harddisk-encrypted";
    categories = [
      "System"
      "Security"
    ];
  };

  autostart = pkgs.makeAutostartItem {
    name = "usb-vault-autostart";
    package = pkgs.makeDesktopItem {
      name = "usb-vault-autostart";
      desktopName = "Unlock USB Vault";
      exec = "env USB_VAULT_GUI=1 usb-vault autostart";
      noDisplay = true;
    };
  };
in
{
  environment.systemPackages = [
    usb-vault
    launcher
    autostart
    pkgs.cryptsetup
    pkgs.gnome-disk-utility # alternative GUI: can also unlock/create LUKS
  ];

  # dm-crypt & friends available without network (they are in the kernel,
  # but make sure the modules load early enough for udisks/Thunar too).
  boot.kernelModules = [
    "dm_crypt"
    "loop"
  ];
}
