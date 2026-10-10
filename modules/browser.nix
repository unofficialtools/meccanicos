# Brave as the only browser, default for all links, with WebGL forced on.
{
  config,
  lib,
  pkgs,
  ...
}:
let
  braveWithArgs = pkgs.brave.override {
    commandLineArgs = builtins.concatStringsSep " " (
      [
        # Use the GPU even if Chromium's blocklist distrusts the driver
        # (common on older Intel/AMD and fresh-from-USB setups).
        "--ignore-gpu-blocklist"
        "--enable-gpu-rasterization"
        "--enable-zero-copy"
        # Machines/VMs with no usable GPU: still provide WebGL via SwiftShader
        # (software rendering) instead of disabling it.
        "--enable-unsafe-swiftshader"
        # Hardware video decode where available.
        "--enable-features=AcceleratedVideoDecodeLinuxGL,AcceleratedVideoDecodeLinuxZeroCopyGL"
        # No "Restore pages?" after a live USB is switched off without quitting.
        "--hide-crash-restore-bubble"
        # No welcome tour ("Set Brave as default?", import bookmarks): on the
        # live USB every start would be a first run.
        "--no-first-run"
      ]
      # No keyring: with no login password there is nothing to unlock it, and
      # the "choose a password for the new keyring" prompt would come up instead.
      ++ lib.optional config.meccanicos.browserBasicPasswordStore "--password-store=basic"
    );
  };

  # Started from the menu, the command bar or a shell without a link: a new
  # tab (in the open window, if there is one). Brave's "New Window" and
  # "New Private Window" menu actions stay as they were.
  newTab = pkgs.writeShellScript "brave" ''
    [ $# -eq 0 ] && set -- brave://newtab
    exec ${braveWithArgs}/bin/brave "$@"
  '';
  brave = pkgs.symlinkJoin {
    name = "brave-${braveWithArgs.version}";
    paths = [ braveWithArgs ];
    postBuild = ''
      rm $out/bin/brave
      ln -s ${newTab} $out/bin/brave
      f=$out/share/applications/brave-browser.desktop
      cp --remove-destination "$(readlink -f $f)" $f
      sed -i 's|^Exec=.*/bin/brave %U$|Exec=${newTab} %U|' $f
    '';
    inherit (braveWithArgs) meta;
  };

  # XFCE "Preferred Applications" helper, so panel/Whisker web launchers open Brave.
  # Named as Brave's own entry: Brave asks xdg-settings whether
  # brave-browser.desktop is the default, which on Xfce reads WebBrowser= in
  # helpers.rc (shell.nix) and looks for a helper of that name.
  xfceHelper = pkgs.writeTextDir "share/xfce4/helpers/brave-browser.desktop" ''
    [Desktop Entry]
    Version=1.0
    Type=X-XFCE-Helper
    Name=Brave
    Icon=brave-browser
    StartupNotify=true
    X-XFCE-Category=WebBrowser
    X-XFCE-Binaries=brave;
    X-XFCE-Commands=%B;
    X-XFCE-CommandsWithParameter=%B "%s";
  '';
in
{
  options.meccanicos.browserBasicPasswordStore = lib.mkEnableOption "Brave keeping its passwords and cookies without the keyring";

  config = {
    environment.systemPackages = [
      brave
      xfceHelper
    ];
    environment.pathsToLink = [ "/share/xfce4" ];

    # Local web pages open in Jed like other text (open.conf); Thunar's right-click
    # "Open in Browser" shows any file or folder in Brave, "Versions from
    # Backups…" lists a file's backed-up versions (mos-backup). Thunar reads the
    # first uca.xml it finds, so this one keeps its stock "Open Terminal Here".
    environment.etc."xdg/Thunar/uca.xml".text = ''
      <?xml version="1.0" encoding="UTF-8"?>
      <actions>
        <action>
          <icon>utilities-terminal</icon>
          <patterns>*</patterns>
          <name>Open Terminal Here</name>
          <unique-id>mos-terminal</unique-id>
          <command>exo-open --working-directory %f --launch TerminalEmulator</command>
          <description>Open a terminal in this folder</description>
          <startup-notify/>
          <directories/>
        </action>
        <action>
          <icon>brave-browser</icon>
          <patterns>*</patterns>
          <name>Open in Browser</name>
          <unique-id>mos-browser</unique-id>
          <command>brave %F</command>
          <description>Show it in Brave</description>
          <startup-notify/>
          <directories/>
          <audio-files/>
          <image-files/>
          <other-files/>
          <text-files/>
          <video-files/>
        </action>
        <action>
          <icon>document-revert</icon>
          <patterns>*</patterns>
          <name>Versions from Backups…</name>
          <unique-id>mos-backup-versions</unique-id>
          <command>xfce4-terminal --title "Versions" --geometry 100x24 -x mos-backup versions %f --menu</command>
          <description>Earlier versions of this file in your backups (mos-backup); restore one next to it</description>
          <audio-files/>
          <image-files/>
          <other-files/>
          <text-files/>
          <video-files/>
        </action>
      </actions>
    '';

    # Managed policy: never let WebGL / 3D APIs or GPU acceleration be switched off.
    environment.etc."brave/policies/managed/webgl.json".text = builtins.toJSON {
      Disable3DAPIs = false;
      HardwareAccelerationModeEnabled = true;
    };
    # Every start is a new tab: the tabs of last time are not brought back.
    environment.etc."brave/policies/managed/startup.json".text = builtins.toJSON {
      RestoreOnStartup = 5; # open the New Tab page
    };
    # Brave is already the default (below): no "Set Brave as default?" prompt.
    environment.etc."brave/policies/managed/default-browser.json".text = builtins.toJSON {
      DefaultBrowserSettingEnabled = false;
    };

    # Links clicked in other apps go straight to Brave.
    xdg.mime.defaultApplications = {
      "x-scheme-handler/http" = "brave-browser.desktop";
      "x-scheme-handler/https" = "brave-browser.desktop";
      "x-scheme-handler/about" = "brave-browser.desktop";
    };
    # Every file type follows open.conf, also on double-click (shell.nix).
    environment.sessionVariables.BROWSER = "brave";
    # Eye of GNOME reads pictures through gdk-pixbuf: add WebP and HEIC (iPhone).
    programs.gdk-pixbuf.modulePackages = [
      pkgs.webp-pixbuf-loader
      pkgs.libheif.lib
    ];
  };
}
