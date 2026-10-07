# Brushed-metal look: boot menus, login screen, wallpaper, GTK/icon/cursor theme.
# Artwork lives in ../branding — replace the PNGs with your own (same names),
# or regenerate them with branding/generate.py.
{
  lib,
  pkgs,
  distro,
  ...
}:
let
  art = ../branding;

  # Graphite "default" variant = neutral grey/steel accents.
  # Window borders: Graphite paints them with the light "active_color_1";
  # use the title bar's dark "active_color_2" instead (no white frame).
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
        '';
      });
  gtkThemeName = "Graphite-Dark";
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
  iconThemeName = "kora-pgrey";
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
        package = iconTheme;
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
    gtkTheme
    iconTheme
    cursorTheme
    wallpaper
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
          <property name="title_font" type="string" value="Cantarell Bold 10"/>
          <property name="workspace_count" type="int" value="4"/>
          <property name="scroll_workspaces" type="bool" value="false"/>
          <!-- The compositor sometimes misses a menu closing and leaves its
               shadow on screen for good (mos-doctor display --reset clears it). -->
          <property name="show_popup_shadow" type="bool" value="false"/>
        </property>
      </channel>
    '';
  };
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

  # Plymouth boot splash: neutral spinner on dark steel.
  boot.plymouth.theme = "spinner";
}
