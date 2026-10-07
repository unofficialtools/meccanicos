# Menu and command bar names: what the app is for, then its name in
# brackets ("Web Browser (Brave)"), and every app listed once. Applied to the
# system's share/applications when it is put together, so it covers every
# package; MeccanicOS's own entries are named where they are defined.
{ lib, ... }:
let
  # desktop file -> new name
  names = {
    "blueman-manager.desktop" = "Bluetooth (Blueman)";
    "brave-browser.desktop" = "Web Browser (Brave)";
    "codium.desktop" = "IDE (VSCodium)";
    "gparted.desktop" = "Partition Editor (GParted)";
    "io.github.celluloid_player.Celluloid.desktop" = "Video Player (Celluloid)";
    "nm-connection-editor.desktop" = "Network Connections (NetworkManager)";
    "nvidia-settings.desktop" = "Graphics Card Settings (NVIDIA)";
    "org.gnome.DiskUtility.desktop" = "Disk Manager (GNOME Disks)";
    "org.gnome.eog.desktop" = "Image Viewer (eog)";
    "org.gnome.Evince.desktop" = "Document Viewer (Evince)";
    "org.gnome.FileRoller.desktop" = "Compress / Extract Files (File Roller)";
    "org.gnome.SimpleScan.desktop" = "Scanner (Simple Scan)";
    "onlyoffice-desktopeditors.desktop" = "Office Documents (OnlyOffice)";
    "org.pulseaudio.pavucontrol.desktop" = "Volume Control (pavucontrol)";
    "panel-preferences.desktop" = "Top Bar Settings (Xfce)";
    "syncthing-ui.desktop" = "File Sync (Syncthing)";
    "thunar.desktop" = "Home Files (Thunar)";
    "thunar-bulk-rename.desktop" = "Rename Many Files (Thunar)";
    "thunar-settings.desktop" = "File Manager Settings (Thunar)";
    "thunar-volman-settings.desktop" = "Removable Drives Settings (Xfce)";
    "xfce4-about.desktop" = "About the Desktop (Xfce)";
    "xfce4-accessibility-settings.desktop" = "Accessibility Settings (Xfce)";
    "xfce4-clipman.desktop" = "Clipboard History (Clipman)";
    "xfce4-clipman-settings.desktop" = "Clipboard History Settings (Clipman)";
    "xfce4-color-settings.desktop" = "Color Profile Settings (Xfce)";
    "xfce4-mime-settings.desktop" = "Default Apps Settings (Xfce)";
    "xfce4-notifyd-config.desktop" = "Notification Settings (Xfce)";
    "xfce4-power-manager-settings.desktop" = "Power Settings (Xfce)";
    "xfce4-screensaver-preferences.desktop" = "Screen Lock Settings (Xfce)";
    "xfce4-screenshooter.desktop" = "Screenshot (Xfce Screenshooter)";
    "xfce4-session-logout.desktop" = "Log Out (Xfce)";
    "xfce4-settings-editor.desktop" = "Advanced Settings Editor (Xfce)";
    "xfce4-taskmanager.desktop" = "Task Manager (Xfce)";
    "xfce-backdrop-settings.desktop" = "Wallpaper Settings (Xfce)";
    "xfce-display-settings.desktop" = "Display Settings (Xfce)";
    "xfce-keyboard-settings.desktop" = "Keyboard Settings (Xfce)";
    "xfce-mouse-settings.desktop" = "Mouse and Touchpad Settings (Xfce)";
    "xfce-session-settings.desktop" = "Session and Startup Settings (Xfce)";
    "xfce-settings-manager.desktop" = "All Settings (Xfce)";
    "xfce-ui-settings.desktop" = "Appearance Settings (Xfce)";
    "xfce-wm-settings.desktop" = "Window Settings (Xfce)";
    "xfce-wmtweaks-settings.desktop" = "Window Tweaks Settings (Xfce)";
    "xfce-workspaces-settings.desktop" = "Workspace Settings (Xfce)";
  };
  # Second entries for an app already listed, or not useful to start by hand.
  hidden = [
    "blueman-adapters.desktop" # reached from Bluetooth (Blueman)
    "cups.desktop" # CUPS's web page: Printers (mos-printers) does what it is for
    "mpv.desktop" # the player behind Video Player (Celluloid)
    "umpv.desktop" # mpv again
    "gtk3-demo.desktop" # GTK's developer demos
    "gtk3-icon-browser.desktop"
    "gtk3-widget-factory.desktop"
    "rofi.desktop" # the command bar itself
    "rofi-theme-selector.desktop"
  ];
  # Rewrites the entry's own [Desktop Entry] section (not its actions):
  # rename -> new Name, no translated names or generic names; hide -> NoDisplay.
  edit = file: awk: ''
    f=$out/share/applications/${file}
    if [ -e "$f" ]; then
      t=$(mktemp)
      awk -v name=${lib.escapeShellArg (names.${file} or "")} ${lib.escapeShellArg awk} "$f" >"$t"
      rm -f "$f"
      install -m 644 "$t" "$f"
      rm -f "$t"
    fi
  '';
  renameAwk = ''
    /^\[/ { main = ($0 == "[Desktop Entry]") }
    main && /^(Name|GenericName)(\[.*\])?=/ { if ($0 ~ /^Name=/) print "Name=" name; next }
    { print }
  '';
  hideAwk = ''
    /^\[/ { if (main) print "NoDisplay=true"; main = ($0 == "[Desktop Entry]") }
    main && /^NoDisplay=/ { next }
    { print }
    END { if (main) print "NoDisplay=true" }
  '';
in
{
  environment.extraSetup = lib.mkBefore ''
    if [ -d $out/share/applications ]; then
      ${lib.concatStrings (lib.mapAttrsToList (file: _: edit file renameAwk) names)}
      ${lib.concatMapStrings (file: edit file hideAwk) hidden}
    fi
  '';
}
