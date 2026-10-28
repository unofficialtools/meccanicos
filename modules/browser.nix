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
        "--enable-gpu-rasterization"
        "--enable-zero-copy"
        # Hardware video decode where available.
        "--enable-features=AcceleratedVideoDecodeLinuxGL,AcceleratedVideoDecodeLinuxZeroCopyGL"
        # No "Restore pages?" after a live USB is switched off without quitting.
        "--hide-crash-restore-bubble"
        # No welcome tour ("Set Brave as default?", import bookmarks): on the
        # live USB every start would be a first run.
        "--no-first-run"
      ]
      # The live USB, on whatever machine it is plugged into: use the GPU even
      # if Chromium's blocklist distrusts the driver (common on older
      # Intel/AMD), and with no usable GPU (VMs) still provide WebGL via
      # SwiftShader (software rendering) instead of disabling it. An installed
      # system keeps Chromium's own judgement: the blocklist names drivers
      # known to crash or misdraw.
      ++ lib.optionals config.meccanicos.browserForceGpu [
        "--ignore-gpu-blocklist"
        "--enable-unsafe-swiftshader"
      ]
      # No keyring: with no login password there is nothing to unlock it, and
      # the "choose a password for the new keyring" prompt would come up instead.
      ++ lib.optional config.meccanicos.browserBasicPasswordStore "--password-store=basic"
    );
  };

  # Started from the menu, the command bar or a shell without a link: a new
  # tab (in the open window, if there is one). Brave's "New Window" and
  # "New Private Window" menu actions stay as they were.
  # An update (mos-upgrade) while Brave is open leaves the old version
  # running, and a new start would only hand it the link (with "Failed
  # sending zygote boot message: Broken pipe"): so an older Brave on the same
  # profile is closed first (SIGTERM: it saves its tabs, as when quitting)
  # and this one brings its tabs back.
  # A lock left in the profile by a Brave that did not quit (SingletonLock:
  # "<computer name>-<process>") stops every later start once the computer's
  # name has changed ("in use ... on another computer", and no dialog to say
  # so): with no Brave running on the profile, it is removed.
  newTab = pkgs.writeShellScript "brave" ''
    PATH=${
      lib.makeBinPath [
        pkgs.coreutils
        pkgs.procps
        pkgs.gnused
        pkgs.gnugrep
      ]
    }:$PATH
    # Chromium rewrites its helpers' command lines into one string with spaces.
    args() { printf ' %s ' "$(tr '\0' ' ' <"/proc/$1/cmdline" 2>/dev/null)"; }
    profile() { args "$1" | grep -o -- ' --user-data-dir=[^ ]*' | tail -n1 | sed 's/^ --user-data-dir=//'; }
    want=""
    for a in "$@"; do case $a in --user-data-dir=*) want=''${a#--user-data-dir=} ;; esac; done
    old="" running=""
    for pid in $(pgrep -u "$(id -u)" -x brave); do
      exe=$(readlink "/proc/$pid/exe" 2>/dev/null) || continue
      case $exe in */opt/brave.com/brave/brave) ;; *) continue ;; esac
      case $(args "$pid") in *" --type="*) continue ;; esac # a helper, not the browser
      [ "$(profile "$pid")" = "$want" ] || continue
      case $exe in
        ${braveWithArgs}/*) running=1 ;; # this version
        *) old="$old $pid" ;; # an older (or other) Brave
      esac
    done
    if [ -n "$old" ]; then
      # shellcheck disable=SC2086
      kill -TERM $old 2>/dev/null || true
      for _ in $(seq 50); do # up to 10 s for it to save and quit
        alive=""
        for p in $old; do [ -e "/proc/$p" ] && alive=1; done
        [ -z "$alive" ] && break
        sleep 0.2
      done
      [ -n "$alive" ] && running=1 # still saving: leave its lock alone
      set -- --restore-last-session "$@"
    elif [ $# -eq 0 ]; then
      set -- brave://newtab
    fi
    dir=''${want:-''${XDG_CONFIG_HOME:-$HOME/.config}/BraveSoftware/Brave-Browser}
    if [ -z "$running" ] && [ -L "$dir/SingletonLock" ]; then
      rm -f "$dir/SingletonLock" "$dir/SingletonCookie" "$dir/SingletonSocket"
    fi
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
  options.meccanicos.browserForceGpu = lib.mkEnableOption "Brave using the GPU despite Chromium's blocklist, and WebGL in software without one";

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
