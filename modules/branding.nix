# The MeccanicOS look (style.nix): graphite, off-white and amber, on the login
# screen, wallpaper, GTK/icon/cursor theme, top bar and notifications.
# Artwork lives in ../branding — replace the PNGs with your own (same names),
# or regenerate them with branding/generate.py (icons: branding/icons.py).
{
  lib,
  pkgs,
  distro,
  ...
}:
let
  art = ../branding;
  style = import ./style.nix;

  # Graphite "default" variant = neutral grey/steel accents.
  # Window borders: Graphite paints them with the light "active_color_1";
  # use the title bar's dark "active_color_2" instead (no white frame).
  # Its one accent colour, #E0E0E0 (selection, focus, switches, progress,
  # sliders, checked buttons), becomes amber, with dark text on it as in
  # the terminal tools. Then MeccanicOS's own rules (shellCss) at the end.
  gtkTheme =
    (pkgs.graphite-gtk-theme.override {
      themeVariants = [ "default" ];
      colorVariants = [
        "dark"
      ];
      tweaks = [ "rimless" ];
    }).overrideAttrs
      (old: {
        postInstall = (old.postInstall or "") + ''
          find $out/share/themes -path '*/xfwm4/*.xpm' -type f -exec \
            sed -i 's/c gray88 s active_color_1/c #2C2C2C s active_color_2/' {} +
          # The active window's title bar: a thin amber edge along its top
          # (the two rows drawn in "."), like the top bar's workspaces.
          for f in $out/share/themes/*/xfwm4/title-[1-5]-active.xpm; do
            sed -i 's/^"\. c #2C2C2C s active_color_2",/". c ${style.amber}",/' "$f"
          done
          for css in $out/share/themes/*/gtk-3.0/gtk*.css; do
            sed -i 's/#E0E0E0/${style.amber}/g' "$css"
            cat ${shellCss} >> "$css"
          done
        '';
      });
  gtkThemeName = "Graphite-Dark";
  # The top bar: a thin inset line under it, and the workspace buttons
  # (keyboard.nix's pager, plugin 12) as 01 DEV  02 WEB …: dim, the current
  # one amber with an amber underline.
  shellCss = pkgs.writeText "meccanicos-gtk.css" ''

    /* ---- MeccanicOS (modules/branding.nix) ---- */
    .xfce4-panel.background {
      border-bottom: 1px solid ${style.line};
    }
    .xfce4-panel.background #pager-12 button {
      font-family: "${style.mono}";
      font-size: 9pt;
      font-weight: bold;
      color: ${style.dim};
      border-radius: 0;
      padding: 0 9px;
      margin: 0 1px;
      box-shadow: none;
    }
    .xfce4-panel.background #pager-12 button:hover {
      color: ${style.text};
      background-color: ${style.raised};
    }
    .xfce4-panel.background #pager-12 button:checked {
      color: ${style.amber};
      background-color: alpha(${style.amber}, 0.08);
      box-shadow: inset 0 -2px ${style.amber};
    }
    /* One shape everywhere: square popups (menus, popovers, tooltips,
       dialogs), controls only just softened, focus in amber. */
    tooltip, tooltip.background,
    menu, .menu, .context-menu,
    popover, popover.background, popover > contents,
    messagedialog, messagedialog.background, dialog.background,
    window.csd, window.csd decoration, decoration {
      border-radius: 0;
    }
    menu, .menu, .context-menu, popover.background {
      border: 1px solid ${style.line};
    }
    button, entry, spinbutton, combobox button, .linked > button,
    notebook > header tab, progressbar trough, progressbar progress,
    scale trough, switch, switch slider {
      border-radius: 2px;
    }
    entry:focus, spinbutton:focus {
      box-shadow: inset 0 -2px ${style.amber};
    }
    /* Log Out dialog (Log Out, Restart, Shut Down, Suspend, ...): square
       graphite buttons with a thin border, the amber underline of the top
       bar's workspaces on the one you point at or move to. */
    .xfsm-logout-dialog {
      background-color: ${style.base};
      border: 1px solid ${style.line};
    }
    .xfsm-logout-dialog .xfsm-logout-label {
      font-family: "${style.mono}";
      font-weight: bold;
      color: ${style.text};
    }
    .xfsm-logout-dialog button {
      background-image: none;
      background-color: ${style.raised};
      border: 1px solid ${style.line};
      border-radius: 0;
      box-shadow: none;
      color: ${style.text};
      padding: 8px 12px;
    }
    .xfsm-logout-dialog button:hover,
    .xfsm-logout-dialog button:focus {
      background-color: shade(${style.raised}, 1.25);
      box-shadow: inset 0 -2px ${style.amber};
    }
    .xfsm-logout-dialog button:disabled {
      color: ${style.dim};
      background-color: ${style.base};
    }
  '';
  # mos-look: after an upgrade that changes the look, asks at login whether
  # to bring the settings your account saved (window shadows, mc's skin) to
  # it. Raise lookVersion when a release changes a look default that users
  # keep a saved copy of.
  lookVersion = "2026-10-12";
  mos-look = pkgs.writeShellApplication {
    name = "mos-look";
    runtimeInputs = with pkgs; [
      xfconf
      libnotify
      gnused
      gnugrep
      coreutils
    ];
    runtimeEnv.MOS_LOOK_VERSION = lookVersion;
    text = (import ./not-root.nix).notRoot "mos-look" + builtins.readFile ../scripts/mos-look.sh;
  };
  # Notifications as MeccanicOS readouts: graphite, square, an amber edge,
  # the title in the monospace.
  notifyTheme = pkgs.writeTextDir "share/themes/MeccanicOS/xfce-notify-4.0/gtk.css" ''
    #XfceNotifyWindow {
      background-color: ${style.base};
      border: 1px solid ${style.line};
      border-left: 3px solid ${style.amber};
      border-radius: 0;
      padding: 12px 14px;
    }
    #XfceNotifyWindow:hover {
      border-color: ${style.dim};
      border-left-color: ${style.amber};
    }
    #XfceNotifyWindow label,
    #XfceNotifyWindow image {
      color: ${style.text};
    }
    #XfceNotifyWindow label#summary {
      font-family: "${style.mono}";
      font-weight: bold;
      font-size: 10pt;
    }
    #XfceNotifyWindow label#body {
      color: shade(${style.text}, 0.85);
    }
    #XfceNotifyWindow button {
      background-image: none;
      background-color: ${style.raised};
      border: 1px solid ${style.line};
      border-radius: 0;
      color: ${style.text};
    }
    #XfceNotifyWindow button:hover {
      background-color: ${style.amber};
      color: ${style.ink};
    }
    #XfceNotifyWindow progressbar progress {
      background-color: ${style.amber};
    }
  '';
  # "pgrey": shaded steel-grey folders. Kora lists its fallback themes as
  # build inputs, which drags Breeze's/Qt's development files (~0.1 GB) into
  # the system; the icons it really uses are reached through share/icons/breeze.
  # Kora falls back on Breeze for the icons it lacks (password, volume, many
  # menu actions): Breeze's are dark, drawn for light backgrounds, and nearly
  # vanish on our dark menus, so it falls back on Breeze Dark instead.
  iconTheme = pkgs.kora-icon-theme.overrideAttrs (old: {
    postFixup = (old.postFixup or "") + ''
      rm -f $out/nix-support/propagated-build-inputs
      ln -s "$(readlink $out/share/icons/breeze)-dark" $out/share/icons/breeze-dark
      sed -i 's/^Inherits=\(.*\)\bbreeze\b/Inherits=\1breeze-dark/' $out/share/icons/kora{,-pgrey}/index.theme
    '';
  });
  # MeccanicOS's own icons (branding/icons.py) for what you see all the
  # time, in front of Kora: glyph -> the icon names it answers to.
  icons = {
    terminal = [ "utilities-terminal" "org.xfce.terminal" "xfce4-terminal" ];
    files = [ "system-file-manager" "org.xfce.thunar" "Thunar" ];
    browser = [ "brave-browser" "web-browser" "internet-web-browser" ];
    vault = [ "drive-harddisk-encrypted" "system-lock-screen" "xfsm-lock" "org.xfce.ScreenSaver" ];
    software = [ "system-software-install" ];
    update = [ "system-software-update" ];
    network = [ "preferences-system-network" "network-transmit-receive" ];
    offline = [ "network-offline" ];
    ai = [ "mos-ai" ];
    settings = [ "preferences-system" "org.xfce.settings.manager" "org.xfce.settings.editor" ];
    # The Log Out dialog's buttons (xfce4-session's xfsm-* names), the lock.
    power = [ "system-shutdown" "xfsm-shutdown" ];
    restart = [ "system-reboot" "xfsm-reboot" ];
    suspend = [ "system-suspend" "xfsm-suspend" ];
    hibernate = [ "system-hibernate" "xfsm-hibernate" ];
    switch-user = [ "system-switch-user" "xfsm-switch-user" ];
    logout = [ "xfsm-logout" "system-log-out" ];
    install = [ "mos-install" ];
    info = [ "help-about" "org.xfce.about" ];
    restore = [ "document-revert" ];
    help = [ "help-browser" ];
    doctor = [ "system-help" ];
    key = [ "dialog-password" ];
    shield = [ "security-high" ];
    keyboard = [ "input-keyboard" "org.xfce.settings.keyboard" ];
    printer = [ "printer" ];
    monitor = [ "utilities-system-monitor" "org.xfce.taskmanager" ];
    editor = [ "accessories-text-editor" ];
    screenshot = [ "org.xfce.screenshooter" ];
    display = [ "org.xfce.settings.display" ];
    appearance = [ "org.xfce.settings.appearance" ];
    battery = [ "org.xfce.powermanager" ];
    disks = [ "org.gnome.DiskUtility" "gparted" ];
    code = [ "vscodium" ];
    clipboard = [ "xfce4-clipman-plugin" ];
    bluetooth = [ "blueman" ];
    archive = [ "org.gnome.FileRoller" ];
    image = [ "org.gnome.eog" "org.xfce.xfdesktop" ];
    document = [ "org.gnome.Evince" ];
    office = [ "onlyoffice-desktopeditors" ];
    mixer = [ "org.pulseaudio.pavucontrol" ];
    video = [ "io.github.celluloid_player.Celluloid" ];
    # The rest of the command bar: Xfce's settings and the other apps.
    speaker = [ "mos-read" ];
    gpu = [ "nvidia-settings" ];
    scanner = [ "org.gnome.SimpleScan" ];
    bell = [ "org.xfce.notification" ];
    panel = [ "org.xfce.panel" ];
    session = [ "org.xfce.session" ];
    accessibility = [ "org.xfce.settings.accessibility" ];
    color = [ "org.xfce.settings.color" ];
    defaults = [ "org.xfce.settings.default-applications" ];
    mouse = [ "org.xfce.settings.mouse" ];
    usb = [ "org.xfce.volman" ];
    workspaces = [ "org.xfce.workspaces" ];
    window = [ "org.xfce.xfwm4" "org.xfce.xfwm4-tweaks" ];
    sync = [ "syncthing" ];
    writer = [ "mos-office-word" ];
    spreadsheet = [ "mos-office-cell" ];
    slides = [ "mos-office-slide" ];
  };
  iconThemeName = style.iconTheme;
  mosIcons = pkgs.runCommand "${distro.id}-icons" { } ''
    d=$out/share/icons/${iconThemeName}
    mkdir -p $d/scalable/apps
    cat > $d/index.theme <<'EOF'
    [Icon Theme]
    Name=${iconThemeName}
    Comment=MeccanicOS's own icons, then Kora (pgrey)
    Inherits=kora-pgrey,hicolor
    Directories=scalable/apps

    [scalable/apps]
    Size=64
    MinSize=8
    MaxSize=512
    Type=Scalable
    Context=Applications
    EOF
    ${lib.concatStrings (
      lib.mapAttrsToList (
        glyph: names:
        lib.concatMapStrings (n: ''
          cp ${art}/icons/${glyph}.svg $d/scalable/apps/${n}.svg
        '') names
      ) icons
    )}
  '';
  iconThemes = pkgs.symlinkJoin {
    name = "${distro.id}-icon-themes";
    paths = [
      mosIcons
      iconTheme
    ];
  };
  cursorTheme = pkgs.graphite-cursors;
  cursorThemeName = "graphite-dark";

  wallpaper = pkgs.runCommand "${distro.id}-wallpapers" { } ''
    mkdir -p $out/share/backgrounds/${distro.id}
    cp ${art}/wallpaper.png ${art}/login.png $out/share/backgrounds/${distro.id}/
  '';
  wallpaperFile = "${wallpaper}/share/backgrounds/${distro.id}/wallpaper.png";
  # A path that stays the same across updates: what xfdesktop saves in a
  # user's settings must still exist after the store path changes.
  wallpaperPath = "/etc/${distro.id}/wallpaper.png";

in
{
  # ---- Login screen (LightDM GTK greeter) --------------------------------
  # Autologin is on, so you see it after logging out / switching user.
  services.xserver.displayManager.lightdm = {
    background = "${art}/login.png";
    greeters.gtk = {
      theme = {
        package = gtkTheme;
        name = gtkThemeName;
      };
      iconTheme = {
        package = iconThemes;
        name = iconThemeName;
      };
      cursorTheme = {
        package = cursorTheme;
        name = cursorThemeName;
        size = 24;
      };
      indicators = [
        "~host"
        "~spacer"
        "~clock"
        "~spacer"
        "~session"
        "~a11y"
        "~power"
      ];
      clock-format = "%a %d %b  %H:%M";
      extraConfig = ''
        font-name = Cantarell 11
        user-background = false
        round-user-image = true
        panel-position = top
      '';
    };
  };

  # ---- Desktop: theme defaults for every new user (via /etc/xdg) ---------
  environment.systemPackages = [
    mos-look
    gtkTheme
    iconThemes
    cursorTheme
    wallpaper
    notifyTheme
  ];
  environment.etc = {
    "xdg/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml".text = ''
      <?xml version="1.0" encoding="UTF-8"?>
      <channel name="xsettings" version="1.0">
        <property name="Net" type="empty">
          <property name="ThemeName" type="string" value="${gtkThemeName}"/>
          <property name="IconThemeName" type="string" value="${iconThemeName}"/>
        </property>
        <property name="Gtk" type="empty">
          <property name="CursorThemeName" type="string" value="${cursorThemeName}"/>
          <property name="CursorThemeSize" type="int" value="24"/>
          <property name="FontName" type="string" value="Cantarell 10"/>
          <property name="MonospaceFontName" type="string" value="DejaVu Sans Mono 10"/>
        </property>
      </channel>
    '';
    "xdg/xfce4/xfconf/xfce-perchannel-xml/xfwm4.xml".text = ''
      <?xml version="1.0" encoding="UTF-8"?>
      <channel name="xfwm4" version="1.0">
        <property name="general" type="empty">
          <property name="theme" type="string" value="${gtkThemeName}"/>
          <property name="title_font" type="string" value="${style.mono} Bold 9"/>
          <property name="workspace_count" type="int" value="4"/>
          <!-- The top bar shows them (keyboard.nix's pager). -->
          <property name="workspace_names" type="array">
            <value type="string" value="01 DEV"/>
            <value type="string" value="02 WEB"/>
            <value type="string" value="03 TERM"/>
            <value type="string" value="04 DOC"/>
          </property>
          <property name="scroll_workspaces" type="bool" value="false"/>
          <!-- No shadows: the compositor sometimes misses a menu or window
               closing and leaves its shadow on screen for good
               (mos-doctor display --reset clears it). -->
          <property name="show_popup_shadow" type="bool" value="false"/>
          <property name="show_frame_shadow" type="bool" value="false"/>
          <property name="show_dock_shadow" type="bool" value="false"/>
          <!-- Windows you are not using, a little see-through: the one you
               type into stands out. -->
          <property name="inactive_opacity" type="int" value="92"/>
        </property>
      </channel>
    '';
  };
  environment.etc."xdg/xfce4/xfconf/xfce-perchannel-xml/xfce4-notifyd.xml".text = ''
    <?xml version="1.0" encoding="UTF-8"?>
    <channel name="xfce4-notifyd" version="1.0">
      <property name="theme" type="string" value="MeccanicOS"/>
    </channel>
  '';
  environment.sessionVariables.XCURSOR_THEME = cursorThemeName;
  # Qt 6 apps take colours, fonts and file dialogs from GTK through
  # the gtk3 platform theme built into qtbase. (qt.platformTheme = "gtk2" would
  # add qtstyleplugins, which drags in a whole second Qt: Qt 5.)
  environment.sessionVariables.QT_QPA_PLATFORMTHEME = "gtk3";

  # ---- Wallpaper ------------------------------------------------------------
  # xfdesktop keeps a wallpaper per monitor connector and workspace; any
  # screen without one (a monitor plugged in later, a new output after
  # rotating, ...) gets the built-in default, which is ours instead of
  # Xfce's. Zoomed is already xfdesktop's default style.
  environment.etc."${distro.id}/wallpaper.png".source = wallpaperFile;
  nixpkgs.overlays = [
    (final: prev: {
      xfdesktop = prev.xfdesktop.overrideAttrs (old: {
        configureFlags = (old.configureFlags or [ ]) ++ [ "--with-default-backdrop-filename=${wallpaperPath}" ];
        # No "Create Document" in the desktop's right-click menu (it has no
        # setting): the item stays, hidden, so the code that fills it still works.
        # Xfce's own wallpapers: never shown (ours is the default, everywhere).
        postInstall = (old.postInstall or "") + ''
          rm -rf $out/share/backgrounds
        '';
        postPatch = (old.postPatch or "") + ''
          substituteInPlace src/xfdesktop-file-icon-manager.c --replace-fail \
            'GtkWidget *tmpl_menu = gtk_menu_new();' \
            'gtk_widget_set_no_show_all(tmpl_mi, TRUE); gtk_widget_hide(tmpl_mi); GtkWidget *tmpl_menu = gtk_menu_new();'
        '';
      });
    })
  ];
  environment.etc."xdg/autostart/${distro.id}-look.desktop".text = ''
    [Desktop Entry]
    Type=Application
    Name=${distro.name} look after an upgrade
    NoDisplay=true
    Exec=${mos-look}/bin/mos-look
  '';
  # At login: OnlyOffice in its dark theme (graphite, like everything else)
  # unless you picked one (its Settings > Appearance). It starts light; there
  # is no system-wide setting, and its launchers call it by full path.
  environment.etc."xdg/autostart/${distro.id}-office-theme.desktop".text = ''
    [Desktop Entry]
    Type=Application
    Name=${distro.name} office theme
    NoDisplay=true
    Exec=${pkgs.writeShellScript "office-theme" ''
      f=''${XDG_CONFIG_HOME:-$HOME/.config}/onlyoffice/DesktopEditors.conf
      ${pkgs.gnugrep}/bin/grep -q '^UITheme=' "$f" 2>/dev/null && exit 0
      ${pkgs.coreutils}/bin/mkdir -p "''${f%/*}"
      if ${pkgs.gnugrep}/bin/grep -q '^\[General\]' "$f" 2>/dev/null; then
        ${pkgs.gnused}/bin/sed -i '/^\[General\]/a UITheme=theme-dark' "$f"
      else
        printf '[General]\nUITheme=theme-dark\n' >>"$f"
      fi
    ''}
  '';
  # At login, repair saved settings that would show something else: a file
  # that no longer exists (an older ISO's store path, kept in a persistent
  # home) or one of Xfce's stock images. A wallpaper the user picked stays.
  environment.etc."xdg/autostart/${distro.id}-wallpaper.desktop".text = ''
    [Desktop Entry]
    Type=Application
    Name=${distro.name} wallpaper
    NoDisplay=true
    Exec=${pkgs.writeShellScript "set-wallpaper" ''
      PATH=${
        lib.makeBinPath [
          pkgs.xfconf
          pkgs.gnugrep
          pkgs.coreutils
        ]
      }
      for p in $(xfconf-query -c xfce4-desktop -l 2>/dev/null | grep '/last-image$'); do
        img=$(xfconf-query -c xfce4-desktop -p "$p")
        case $img in
        */share/backgrounds/xfce/*) ;;
        *) [ -e "$img" ] && continue ;;
        esac
        xfconf-query -c xfce4-desktop -p "$p" -s ${wallpaperPath}
      done
    ''}
  '';

  # Plymouth boot splash: a spinner under the MeccanicOS mark.
  boot.plymouth.theme = "spinner";
  boot.plymouth.logo = "${art}/mark.png";
}
