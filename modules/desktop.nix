# XFCE desktop with automatic login for the live user.
{
  lib,
  pkgs,
  distro,
  ...
}:
let
  mos-autorotate = pkgs.writeShellApplication {
    name = "mos-autorotate";
    runtimeInputs = with pkgs; [
      xrandr
      xinput
      gawk
      gnugrep
    ];
    text = builtins.readFile ../scripts/mos-autorotate.sh;
  };
in
{
  # xfce4-settings needs xapp, and xapp builds a MATE panel applet that pulls
  # in mate-panel + libmateweather (~0.15 GB). MeccanicOS has no MATE panel.
  nixpkgs.overlays = [
    (final: prev: {
      xapp = prev.xapp.overrideAttrs (old: {
        buildInputs = lib.filter (p: (p.pname or "") != "mate-panel") old.buildInputs;
        mesonFlags = (old.mesonFlags or [ ]) ++ [ "-Dmate=false" ];
      });
    })
  ];

  services.xserver = {
    enable = true;
    desktopManager.xfce.enable = true;
    xkb.layout = "us"; # change to e.g. "it", "de", "us,it"
  };
  services.displayManager.defaultSession = "xfce";

  services.xserver.displayManager.lightdm = {
    enable = true;
    greeters.gtk.enable = true;
  };
  # The login screen's accessibility bus (at-spi-bus-launcher) ignores SIGTERM,
  # so shutting down from the login screen waited systemd's full 90 s before
  # killing it. Give login sessions 10 s to exit; services keep the default.
  systemd.units."session-.scope" = {
    text = ''
      [Scope]
      TimeoutStopSec=10s
    '';
    overrideStrategy = "asDropin";
  };

  # Portrait-native panels (tablets, handhelds): turn them to landscape when X
  # starts, and again at login in case the session reset the screen.
  services.xserver.displayManager.setupCommands = "${mos-autorotate}/bin/mos-autorotate";
  environment.etc."xdg/autostart/mos-autorotate.desktop".text = ''
    [Desktop Entry]
    Type=Application
    Name=Screen rotation
    NoDisplay=true
    Exec=${mos-autorotate}/bin/mos-autorotate
  '';

  # Desktop plumbing: removable media, trash, thumbnails, keyring, printing-free
  services.gvfs.enable = true; # Thunar: mount USB disks, unlock LUKS by click
  services.udisks2.enable = true;
  services.tumbler.enable = true;
  services.blueman.enable = true;
  services.gnome.gnome-keyring.enable = true;
  programs.thunar.plugins = with pkgs; [
    thunar-archive-plugin
    thunar-volman
    thunar-media-tags-plugin
  ];
  programs.xfconf.enable = true;
  programs.dconf.enable = true;

  environment.systemPackages = with pkgs; [
    xfce4-whiskermenu-plugin
    xfce4-pulseaudio-plugin
    xfce4-battery-plugin
    xfce4-clipman-plugin
    xfce4-screenshooter
    xfce4-taskmanager
    file-roller
    xdg-user-dirs
    xdg-utils
    xclip
  ];

  fonts = {
    enableDefaultPackages = true;
    packages = with pkgs; [
      noto-fonts
      noto-fonts-cjk-sans
      noto-fonts-color-emoji
      dejavu_fonts
      liberation_ttf
      open-sans
      cantarell-fonts
    ];
  };

  i18n.defaultLocale = "en_US.UTF-8";

  # NixOS turns on the speech server (screen-reader voices, ~0.7 GB with the
  # MBROLA voices) for graphical desktops. Re-enable it if you need Orca.
  services.speechd.enable = false;
}
