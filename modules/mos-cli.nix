# mos-cli: mos (the list of mos-* commands), mos-config (common
# settings in one place, full screen or by command; export/import) and
# mos-doctor (find and fix problems), from scripts/mos/. Also mos-
# names for the commands that had none (usb-vault, apps, say: those names
# stay too).
{ pkgs, distro, ... }:
let
  inherit (import ./not-root.nix) notRoot;
  src = ../scripts/mos;
  tool =
    name: prog:
    pkgs.writeShellScriptBin name ''
      ${notRoot name}
      export MECCANICOS_PYLIB=${../scripts/lib}
      export MECCANICOS_PROG=${prog} MECCANICOS_NAME=${pkgs.lib.escapeShellArg distro.name} MECCANICOS_ID=${distro.id}
      export PATH="$PATH:${
        pkgs.lib.makeBinPath (
          with pkgs;
          [
            age # encrypted dotfiles (mos-config export --with-secrets)
            pciutils
            usbutils
            util-linux # rfkill
            xinput
            setxkbmap
            mesa-demos # glxinfo
            inxi
            power-profiles-daemon
          ]
        )
      }"
      exec ${pkgs.python3}/bin/python3 ${src}/main.py "$@"
    '';
  alias = name: target: pkgs.writeShellScriptBin name ''exec ${target} "$@"'';
  # In the menu and the command bar: each opens a terminal.
  configLauncher = pkgs.makeDesktopItem {
    name = "mos-config";
    desktopName = "Configuration Management (mos-config)";
    comment = "Common settings in one place: see them, change them, take them to another computer";
    icon = "preferences-system";
    exec = ''xfce4-terminal --title "Configuration Management" --geometry 110x36 -x mos-config'';
    categories = [ "Settings" ];
  };
  doctorLauncher = pkgs.makeDesktopItem {
    name = "mos-doctor";
    desktopName = "Configuration Doctor (mos-doctor)";
    comment = "Find and fix problems with Wi-Fi, Bluetooth, sound, the screen and disk space";
    icon = "system-help";
    exec = ''xfce4-terminal --title "Configuration Doctor" --geometry 100x32 -x bash -c "mos-doctor; echo; read -rsn1 -p 'Press any key to close.'"'';
    categories = [ "Settings" ];
  };
in
{
  environment.systemPackages = [
    configLauncher
    doctorLauncher
    (tool "mos" "mos")
    (tool "mos-config" "config")
    (tool "mos-doctor" "doctor")
    (alias "mos-vault" "usb-vault")
    (alias "mos-apps" "apps")
    (alias "mos-say" "say")
  ];
  # Settings that live only in ~/.config/meccanicos/settings.toml (the keyboard;
  # on the live USB also the time zone and battery limit) come back at login.
  environment.etc."xdg/autostart/${distro.id}-config-apply.desktop".text = ''
    [Desktop Entry]
    Type=Application
    Name=${distro.name} settings
    NoDisplay=true
    Exec=mos-config apply
  '';
}
