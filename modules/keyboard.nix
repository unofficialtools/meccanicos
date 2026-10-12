# Keyboard-first desktop: no applications menu, no desktop icons, a slim
# status bar, window shortcuts, a cheat sheet, and the command bar
# (Super+Space) as the way to start anything.
{
  pkgs,
  lib,
  distro,
  ...
}:
let
  inherit (import ./not-root.nix) notRoot;
  style = import ./style.nix;
  # ---- Command bar ---------------------------------------------------------
  # The command center: a header with the mark, MECCANICOS, this computer and
  # you, and the session · storage · network · battery · vaults readout
  # (mos-ask fills them in from mos-status --header when it opens);
  # then the search, the matches and a line of hints. Square, thin lines, the
  # chosen row marked by an amber edge.
  nameSpaced = lib.concatStringsSep " " (lib.stringToCharacters (lib.toUpper distro.name));
  rofiTheme = pkgs.writeText "mos-ask.rasi" ''
    * {
      ink: ${style.ink}f5;
      base: ${style.base}f7;
      raised: ${style.raised};
      line: ${style.line};
      text: ${style.text};
      dim: ${style.dim};
      amber: ${style.amber};
      background-color: transparent;
      text-color: @text;
      font: "${style.mono},DejaVu Sans Mono,monospace 18";
    }
    window {
      location: center;
      anchor: center;
      width: 60%;
      background-color: @base;
      border: 1px;
      border-color: @line;
      border-radius: 0;
      padding: 0;
    }
    mainbox { children: [ box-header, inputbar, listview, message ]; spacing: 0; }
    box-header {
      orientation: horizontal;
      children: [ icon-mark, textbox-name, textbox-status ];
      expand: false;
      spacing: 16px;
      padding: 16px 24px;
      background-color: @ink;
      border: 0 0 1px 0;
      border-color: @line;
    }
    icon-mark { filename: "${../branding/mark.png}"; size: 40px; expand: false; vertical-align: 0.5; }
    /* One quoted string per line: rofi reads a string up to the line's last quote.
       Two lines in one textbox (Pango markup): rofi draws a box of
       textboxes on top of each other. mos-ask adds the second line. */
    textbox-name {
      content: "<b>${nameSpaced}</b>";
      markup: true;
      font: "${style.mono} 13";
      text-color: @text;
      expand: false;
      vertical-align: 0.5;
    }
    textbox-status {
      content: "";
      font: "${style.mono} 10";
      text-color: @dim;
      horizontal-align: 1;
      vertical-align: 0.5;
      expand: true;
    }
    inputbar { children: [ prompt, entry ]; spacing: 14px; padding: 18px 24px 12px 24px; }
    prompt { text-color: @amber; }
    entry {
      placeholder: "Type an app, a command, a website… or just ask";
      placeholder-color: @dim;
      cursor: text;
    }
    listview { lines: 7; fixed-height: false; scrollbar: false; spacing: 2px; padding: 0 16px 12px 16px; }
    element { padding: 8px 12px; border: 0 0 0 3px; border-color: transparent; border-radius: 0; spacing: 14px; }
    element selected.normal { background-color: @raised; border-color: @amber; }
    element-icon { size: 1.3em; }
    element-text { font: "${style.sans} 15"; vertical-align: 0.5; highlight: bold ${style.amber}; }
    message { border: 1px 0 0 0; border-color: @line; padding: 10px 24px 12px 24px; background-color: @ink; }
    textbox { font: "${style.mono} 9"; text-color: @dim; }
  '';

  mos-ask = pkgs.writeShellApplication {
    name = "mos-ask";
    runtimeInputs = with pkgs; [
      mos-status
      rofi
      xfce4-terminal
      glib # gio
      gtk3 # gtk-launch
      gawk
      gnugrep
      gnused
      coreutils
      util-linux # setsid
    ];
    text = notRoot "mos-ask" + ''
      export MECCANICOS_ASK_THEME=${rofiTheme}
      export MECCANICOS_ASK_ICONS=${style.iconTheme} # rofi reads only gtk-3.0/settings.ini, not the desktop's setting
      export MECCANICOS_ASK_NAME=${lib.escapeShellArg nameSpaced}
      exec ${pkgs.bash}/bin/bash ${../scripts/mos-ask.sh} "$@"
    '';
  };

  mos-screenshot = pkgs.writeShellApplication {
    name = "mos-screenshot";
    runtimeInputs = with pkgs; [
      maim
      xdotool
      xclip
      libnotify
      coreutils
    ];
    text = notRoot "mos-screenshot" + builtins.readFile ../scripts/mos-screenshot.sh;
  };

  mos-hidpi = pkgs.writeShellApplication {
    name = "mos-hidpi";
    runtimeInputs = with pkgs; [
      xrandr
      xfconf
      gnugrep
      gawk
      coreutils
    ];
    text = notRoot "mos-hidpi" + builtins.readFile ../scripts/mos-hidpi.sh;
  };

  # Session (live, persistent, installed), storage (encrypted or not),
  # unlocked vaults, network, battery: the top bar and the command center.
  mos-status = pkgs.writeShellApplication {
    name = "mos-status";
    runtimeInputs = with pkgs; [
      util-linux # findmnt, lsblk
      networkmanager # nmcli
      gawk
      gnugrep
      gnused
      coreutils
    ];
    # The name every computer starts with: not shown as "its" name.
    runtimeEnv.MOS_DEFAULT_HOST = distro.hostName;
    text = builtins.readFile ../scripts/mos-status.sh;
  };

  # ---- Cheat sheet ("shortcuts" in the command bar) -------------------------
  keys = [
    [ "Super+Space  ·  Alt+F2" "Command bar: apps, websites, commands, web search" ]
    [ "shortcuts  (in the command bar)" "This cheat sheet" ]
    [ "Ctrl+Alt+T" "Terminal" ]
    [ "Super+E" "Files" ]
    [ "Super+← / →" "Snap window to the left / right half" ]
    [ "Alt+F10  ·  Alt+F9" "Maximize / restore  ·  minimize" ]
    [ "Alt+F7  ·  Alt+F8" "Move · resize window: mouse or arrows, Enter" ]
    [ "Alt+F11" "Fullscreen" ]
    [ "Alt+F4" "Close window" ]
    [ "Alt+Tab" "Switch window (this workspace)" ]
    [ "Super+Tab" "Next window of the same app" ]
    [ "Ctrl+F1 … F4" "Go to workspace 1–4" ]
    [ "Super+Shift+1 … 4" "Move window to workspace 1–4" ]
    [ "Ctrl+Alt+D" "Show desktop" ]
    [ "Ctrl+Alt+L" "Lock screen" ]
    [ "Super+P" "Displays" ]
    [ "Print  ·  Alt+Print  ·  Shift+Print" "Screenshot: screen · window · area (copied)" ]
    [ "Super+V" "Clipboard history" ]
    [ "Super+." "Emoji picker" ]
    [ "Ctrl+Alt+Del" "Log out, restart, shut down" ]
    [ "Super+Shift+Esc" "Disconnect everything (undo: Reconnect)" ]
  ];
  # The descriptions line up in one column, two spaces after the longest key.
  # builtins.stringLength counts bytes: the keys' non-ASCII characters count
  # as one each, and any other one fails the build (add it to the list).
  keyWidth =
    key:
    let
      ascii = builtins.replaceStrings [ "·" "←" "→" "…" "–" ] [ "." "<" ">" "." "-" ] key;
    in
    assert lib.assertMsg (builtins.match "[ -~]*" ascii != null) "cheat sheet: unknown character in ${key}";
    builtins.stringLength ascii;
  keyColumn = 2 + lib.foldl' lib.max 0 (map (k: keyWidth (builtins.elemAt k 0)) keys);
  cheatSheet = pkgs.writeText "mos-keys.txt" (
    lib.concatMapStringsSep "\n" (
      k:
      let
        key = builtins.elemAt k 0;
      in
      key + lib.fixedWidthString (keyColumn - keyWidth key) " " "" + builtins.elemAt k 1
    ) keys
  );
  keysTheme = pkgs.writeText "mos-keys.rasi" ''
    @import "${rofiTheme}"
    * { font: "JetBrainsMono Nerd Font,DejaVu Sans Mono,monospace 13"; }
    window { width: 72%; }
    mainbox { children: [ inputbar, listview ]; }
    inputbar { children: [ prompt ]; }
    prompt { text-color: @amber; font: "${style.mono} Bold 13"; }
    inputbar { padding: 18px 24px 12px 24px; }
    listview { padding: 0 16px 16px 16px; }
    listview { lines: 21; }
    element { padding: 3px 12px; }
    element-text { font: "JetBrainsMono Nerd Font,DejaVu Sans Mono,monospace 12"; }
    element selected.normal { background-color: transparent; border-color: transparent; }
  '';
  mos-keys = pkgs.writeShellScriptBin "mos-keys" ''
    ${notRoot "mos-keys"}
    case "''${1-}" in
      "") ;;
      -h | --help | help) printf '%s\n\n  %s\n' "mos-keys - show the keyboard shortcuts (also: shortcuts in the command bar; Esc closes)" "mos-keys   (no options)"; exit 0 ;;
      *) echo "mos-keys: unknown option $1 (mos-keys --help)" >&2; exit 2 ;;
    esac
    exec ${pkgs.rofi}/bin/rofi -dpi 0 -dmenu -no-custom -p "Keyboard shortcuts — Esc to close" \
      -theme ${keysTheme} < ${cheatSheet} >/dev/null
  '';

  # ---- Shortcuts: XFCE defaults + ours --------------------------------------
  esc = s: builtins.replaceStrings [ "<" ">" ] [ "\\&lt;" "\\&gt;" ] s;
  bind = key: action: ''          <property name="${esc key}" type="string" value="${action}"/>\'';
  commandBinds = [
    (bind "<Super>space" "mos-ask")
    (bind "<Alt>F2" "mos-ask")
    (bind "<Super>v" "xfce4-clipman-history")
    (bind "<Super>period" "rofimoji --skin-tone neutral")
    (bind "<Super><Shift>Escape" "mos-logins disconnect")
    (bind "Print" "mos-screenshot full")
    (bind "<Alt>Print" "mos-screenshot window")
    (bind "<Shift>Print" "mos-screenshot area")
  ];
  # xfwm4 keeps one key per action (the first it finds), so a second key for
  # an action that already has a default one never works reliably. Ours are
  # only for actions whose default needs a numeric keypad; those defaults are
  # removed below.
  wmBinds = [
    (bind "<Super>Left" "tile_left_key")
    (bind "<Super>Right" "tile_right_key")
  ]
  ++ map (n: bind "<Super><Shift>${toString n}" "move_window_workspace_${toString n}_key") (lib.range 1 4);
  insertAfterFirstDefault = binds: ''
    0,/<property name="default" type="empty">/s||&\
    ${lib.removeSuffix "\\" (lib.concatStringsSep "\n" binds)}|'';
  shortcuts = pkgs.runCommand "xfce4-keyboard-shortcuts.xml" { } ''
    src=${pkgs.libxfce4ui}/etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xfce4-keyboard-shortcuts.xml
    # The app finder (Alt+F2, Alt+F3, Super+R) is not there: the command bar
    # is Alt+F2. Nor are the keypad keys for the actions we bind (see wmBinds).
    sed -e '/name="&lt;Alt&gt;F2"/,/<\/property>/d' \
        -e '/name="&lt;Alt&gt;F3"/,/<\/property>/d' \
        -e '/name="&lt;Super&gt;r"/,/<\/property>/d' \
        -e '/value="xfce4-screenshooter/d' \
        -e '/value="tile_left_key"/d' -e '/value="tile_right_key"/d' \
        -e '/value="move_window_workspace_[1-4]_key"/d' "$src" > step1
    # Command shortcuts go into the first "default" block (commands) ...
    sed -e '${insertAfterFirstDefault commandBinds}' step1 > step2
    # ... window-manager shortcuts into the xfwm4 "default" block.
    sed -e '/<property name="xfwm4" type="empty">/,$ {
    ${insertAfterFirstDefault wmBinds}
    }' step2 > $out
    for v in mos-ask tile_left_key move_window_workspace_4_key "mos-screenshot area"; do
      grep -q "value=\"$v\"" $out || { echo "missing $v"; exit 1; }
    done
    # One key per window-manager action (see wmBinds).
    dups=$(sed -n '/<property name="xfwm4"/,$ s/.* value="\([a-z0-9_]*_key\)".*/\1/p' $out | sort | uniq -d)
    [ -z "$dups" ] || { echo "more than one key for: $dups"; exit 1; }
  '';

  # ---- Command bar entries for terminal tools ----------------------------
  # Each opens in its own terminal window that closes when the program exits.
  # hiPrio: these replace the stock btop.desktop / xfce4-terminal.desktop entries.
  termApp =
    {
      id,
      name,
      comment,
      icon,
      cmd,
    }:
    lib.hiPrio (
      pkgs.makeDesktopItem {
        name = id;
        desktopName = name;
        inherit comment icon;
        exec = "xfce4-terminal --class ${id} --title \"${name}\"" + lib.optionalString (cmd != "") " -x ${cmd}";
        categories = [
          "System"
          "Utility"
        ];
      }
    );
  # Command bar "Passwords": first run creates an age-encrypted gopass store,
  # then lists it and leaves a shell with the common commands.
  mos-passwords = pkgs.writeShellApplication {
    name = "mos-passwords";
    runtimeInputs = with pkgs; [
      gopass
      age
      git
    ];
    text = notRoot "mos-passwords" + ''
      case "''${1-}" in
        "") ;;
        -h | --help | help) printf '%s\n\n  %s\n' "mos-passwords - your passwords (gopass): lists them, then a shell with the common commands" "mos-passwords   (no options)"; exit 0 ;;
        *) echo "mos-passwords: unknown option $1 (mos-passwords --help)" >&2; exit 2 ;;
      esac
      if ! gopass ls >/dev/null 2>&1; then
        echo "No password store yet. Creating one, encrypted with age:"
        echo "choose a passphrase you will remember - it unlocks every password."
        echo
        gopass setup --crypto age --storage fs || { echo "Setup cancelled."; exec bash; }
        echo
      fi
      gopass ls
      cat <<'TIPS'

        gopass show -c web/github     copy a password (clears after 45 s)
        gopass generate web/github    new random password
        gopass insert web/github      type one in        gopass edit web/github
        gopass find github            search             gopass rm web/github
        gopass otp web/github         one-time code (store "otpauth://..." in the entry)

      Store: ~/.local/share/gopass/stores/root (keep it in the persistent home or a vault).
      TIPS
      exec bash
    '';
  };

  # ---- System Info: top bar "MeccanicOS" and the command bar --------------------
  # A terminal with this computer's MeccanicOS build, NixOS, kernel, CPU,
  # graphics driver, memory and disks; any key closes it.
  homepage = "https://github.com/unofficialtools/meccanicos";
  about = pkgs.writeShellApplication {
    name = "mos-about";
    runtimeInputs = with pkgs; [
      mos-status
      util-linux # lscpu, lsblk
      procps # free
      coreutils
      gawk
      gnused
    ];
    text = ''
      case "''${1-}" in
        "") ;;
        -h | --help | help) printf '%s\n\n  %s\n' "mos-about - this computer's ${distro.name} build, NixOS, kernel, CPU, graphics, memory and disks" "mos-about   (no options)"; exit 0 ;;
        *) echo "mos-about: unknown option $1 (mos-about --help)" >&2; exit 2 ;;
      esac
      t=$'\e[1;38;5;214m' k=$'\e[38;5;245m' r=$'\e[0m'
      row() { printf '  %s%-8s%s %s\n' "$k" "$1" "$r" "$2"; }
      iec() { numfmt --to=iec-i --suffix=B --format=%.1f "$1" | sed -E 's/([0-9])([KMGTP]?iB)$/\1 \2/'; }

      printf '\n  %s${distro.name}%s  ${homepage}\n\n' "$t" "$r"
      where=installed
      # shellcheck disable=SC1091
      [ -n "$(. /etc/os-release; echo "''${IMAGE_VERSION:-}")" ] && where="live USB"
      row ${distro.name} "built $(cat /etc/${distro.id}/version 2>/dev/null || echo "(unknown)"), $where"
      row Session "$(mos-status | sed -n 's/^status *//p')"
      row NixOS "$(nixos-version 2>/dev/null || echo "(unknown)")"
      row Kernel "$(uname -r)"
      row CPU "$(lscpu | sed -n 's/^Model name: *//p' | head -n1), $(nproc) threads"
      # Each graphics card's kernel driver, and mos-gpu-driver's choice for
      # NVIDIA cards (mos-doctor display shows the same).
      gfx=""
      for d in /sys/bus/pci/devices/*; do
        read -r class 2>/dev/null <"$d/class" || continue
        [[ $class == 0x03* ]] || continue # display controllers only
        vendor=$(cat "$d/vendor" 2>/dev/null || true)
        case $vendor in
          0x8086) vendor=Intel ;;
          0x1002) vendor=AMD ;;
          0x10de) vendor=NVIDIA ;;
          0x1af4) vendor=virtio ;;
          0x1234 | 0x1b36) vendor=QEMU ;;
          0x15ad) vendor=VMware ;;
          0x80ee) vendor=VirtualBox ;;
        esac
        drv="no driver"
        if [ -L "$d/driver" ]; then drv=$(basename "$(readlink "$d/driver")"); fi
        gfx="''${gfx:+$gfx, }$drv ($vendor)"
      done
      case $(mos-gpu-driver 2>/dev/null || true) in
        nvidia) gfx="''${gfx:-none found}; NVIDIA cards: nvidia, NVIDIA's own driver" ;;
        open) gfx="''${gfx:-none found}; NVIDIA cards: nouveau, the open driver" ;;
      esac
      row Graphics "''${gfx:-none found} (mos-gpu-driver)"
      read -r total avail < <(free -b | awk '/^Mem:/ {print $2, $7}')
      row RAM "$(iec "$total"), $(iec "$avail") free"
      # Every disk: its size, and how much of its mounted space is free.
      for d in $(lsblk -dnr -o NAME,TYPE | awk '$2 == "disk" && $1 !~ /^zram/ {print $1}'); do
        size=$(lsblk -dnb -o SIZE "/dev/$d")
        model=$(lsblk -dn -o MODEL "/dev/$d" | sed 's/ *$//')
        read -r fs av < <(lsblk -nbr -o FSSIZE,FSAVAIL "/dev/$d" | awk 'NF == 2 {s += $1; a += $2} END {print s + 0, a + 0}')
        if [ "$fs" -gt 0 ]; then free="$((100 * av / fs))% free"; else free="not mounted"; fi
        row Disk "$d  $(iec "$size")  $free''${model:+  ($model)}"
      done
      printf '\n  Press any key to close.'
      read -rsn1 || true
    '';
  };
  aboutWindow = "xfce4-terminal --class mos-about --title \"System Info (${distro.name})\" -x ${about}/bin/mos-about";
  aboutLauncher = pkgs.makeDesktopItem {
    name = "mos-about";
    desktopName = "System Info (${distro.name})";
    comment = "${distro.name} version, NixOS, kernel, CPU, graphics, memory and disks";
    icon = "help-about";
    exec = aboutWindow;
    categories = [ "System" ];
  };

  # btop refuses to start ("No UTF-8 locale detected!") without a UTF-8
  # locale, which programs started from the panel don't always get.
  mos-btop = pkgs.writeShellApplication {
    name = "mos-btop";
    runtimeInputs = [ pkgs.btop ];
    text = ''
      if [ -r /etc/locale.conf ]; then
        set -a
        # shellcheck disable=SC1091
        . /etc/locale.conf
        set +a
      fi
      case "''${LC_ALL:-''${LC_CTYPE:-''${LANG:-}}}" in
      *[Uu][Tt][Ff]-8 | *[Uu][Tt][Ff]8) ;;
      *) export LC_ALL=C.UTF-8 ;;
      esac
      exec btop "$@"
    '';
  };
  btopWindow = "xfce4-terminal --class btop --title \"System Utilization (btop)\" -x ${mos-btop}/bin/mos-btop";
  # Top bar CPU use: busy share of all cores since the previous call (every
  # 2 s; the first call averages since boot), in amber from 80 °C and red
  # from 90 °C (the CPU's own sensor: k10temp on AMD, coretemp on Intel, the
  # SoC's on ARM, else the x86_pkg_temp zone). Click: btop.
  mos-cpu = pkgs.writeShellScript "mos-cpu" ''
    read -r _ user nice system idle iowait irq softirq steal _ </proc/stat
    total=$((user + nice + system + idle + iowait + irq + softirq + steal))
    busy=$((total - idle - iowait))
    state=''${XDG_RUNTIME_DIR:-/tmp}/mos-cpu-$UID
    dt=$total db=$busy
    if read -r ptotal pbusy 2>/dev/null <"$state" && [ $((total - ptotal)) -gt 0 ]; then
      dt=$((total - ptotal)) db=$((busy - pbusy))
    fi
    echo "$total $busy" >"$state"
    temp=
    for h in /sys/class/hwmon/hwmon*; do
      case $(cat "$h/name" 2>/dev/null) in
        k10temp | coretemp | zenpower | cpu_thermal | soc_thermal)
          read -r temp 2>/dev/null <"$h/temp1_input" && break ;;
      esac
    done
    if [ -z "$temp" ]; then
      for z in /sys/class/thermal/thermal_zone*; do
        [ "$(cat "$z/type" 2>/dev/null)" = x86_pkg_temp ] && read -r temp 2>/dev/null <"$z/temp" && break
      done
    fi
    cpu="CPU $(((100 * db + dt / 2) / dt))%" tool="CPU use, average over all cores"
    if [ -n "$temp" ]; then
      temp=$((temp / 1000))
      tool="$tool; $temp °C"
      if [ "$temp" -ge 90 ]; then
        cpu="<span fgcolor='${style.red}'>$cpu</span>" tool="$tool: too hot"
      elif [ "$temp" -ge 80 ]; then
        cpu="<span fgcolor='${style.amber}'>$cpu</span>" tool="$tool: hot"
      fi
    fi
    printf '<txt>%s</txt><txtclick>%s</txtclick><tool>%s (click: btop)</tool>\n' \
      "$cpu" ${lib.escapeShellArg btopWindow} "$tool"
  '';
  # Top bar, left: the mark, the name and this computer's name (click: the
  # command bar, as Super+Space; "System Info" is in it), e.g.
  # [M] M E C C A N I C O S  // WORKSTATION.
  # The computer's name only once it has its own (not the default ${distro.hostName}).
  mos-label = pkgs.writeShellScript "mos-label" ''
    host=$(${pkgs.coreutils}/bin/uname -n)
    name=""
    if [ "$host" != ${distro.hostName} ]; then
      name="  <span fgcolor='${style.dim}' weight='normal'>//  $(echo "$host" | ${pkgs.coreutils}/bin/tr '[:lower:]' '[:upper:]')</span>"
    fi
    printf '<img>%s</img><click>%s</click><txt> <span letter_spacing="2400" fgcolor="${style.text}">%s</span>%s</txt><txtclick>%s</txtclick><tool>Start anything (Super+Space)</tool>\n' \
      ${../branding/mark-20.png} ${mos-ask}/bin/mos-ask ${lib.toUpper distro.name} "$name" ${mos-ask}/bin/mos-ask
  '';
  # Top bar, right: the session and whether your files are encrypted, e.g.
  # USB · NOT SAVED, INSTALLED · ENCRYPTED, and 1 VAULT OPEN in amber while a
  # vault is unlocked (click: System Info).
  mos-session = pkgs.writeShellScript "mos-session" ''
    MOS_STATUS_CLICK=${lib.escapeShellArg aboutWindow} exec ${mos-status}/bin/mos-status --panel
  '';
  terminalApps = [
    (termApp {
      id = "mos-passwords";
      name = "Passwords (gopass)";
      comment = "Password manager in the terminal (gopass, age encryption)";
      icon = "dialog-password";
      cmd = "${mos-passwords}/bin/mos-passwords";
    })
    (termApp {
      id = "mc";
      name = "Home Files (Midnight Commander)";
      comment = "Two-panel file manager in the terminal";
      icon = "system-file-manager";
      cmd = "mc";
    })
    (termApp {
      id = "yazi";
      name = "Home Files (yazi)";
      comment = "Terminal file manager with previews of images, videos, archives and code";
      icon = "system-file-manager";
      cmd = "yazi";
    })
    (termApp {
      id = "btop";
      name = "System Utilization (btop)";
      comment = "CPU, memory, disks, network and processes";
      icon = "utilities-system-monitor";
      cmd = "mos-btop";
    })
    (termApp {
      id = "mos-apps";
      name = "Apps Manager (apps)";
      comment = "Find, try, install, update and remove apps (needs the internet)";
      icon = "system-software-install";
      cmd = "apps manage";
    })
    (termApp {
      id = "mos-journal";
      name = "System Journal (journalctl)";
      comment = "System log for this boot, newest at the bottom (F follows new messages)";
      icon = "utilities-terminal";
      cmd = "journalctl -b -e";
    })
    (termApp {
      id = "xfce4-terminal";
      name = "Terminal (bash)";
      comment = "Xfce Terminal with Bash";
      icon = "utilities-terminal";
      cmd = "";
    })
  ];

  # ---- The top bar: graphite, one line of instrument readouts ---------------
  # Left: the mark, MECCANICOS // COMPUTER (click: the command bar), then the
  # workspaces as 01 DEV  02 WEB  03 TERM  04 DOC, the current one in amber
  # (click one to go there; Ctrl+F1…F4 too). Right: the session and storage
  # (USB · NOT SAVED, INSTALLED · ENCRYPTED, an open vault in amber), date,
  # window/workspace dropdown, CPU % (click: btop), tray, volume, battery,
  # Log Out. One panel: a clock in a separate panel on top of it got covered
  # whenever the bar took focus (e.g. opening the dropdown). No applications
  # menu or task buttons: the command bar starts things, Alt+Tab switches.
  # Readouts in the monospace, as in the command center and the terminal tools;
  # the bar's look (border, workspace buttons) is in branding.nix's CSS.
  barFont = "${style.mono} 9";
  barFontBold = "${style.mono} Bold 9";
  # The panel's background, #rrggbb as xfconf's four doubles.
  rgba =
    hex:
    let
      ch = i: (lib.fromHexString (builtins.substring (1 + 2 * i) 2 hex)) / 255.0;
    in
    map (i: ''<value type="double" value="${toString (ch i)}"/>'') [ 0 1 2 ]
    ++ [ ''<value type="double" value="1"/>'' ];
  panel = pkgs.writeText "xfce4-panel.xml" ''
    <?xml version="1.0" encoding="UTF-8"?>
    <channel name="xfce4-panel" version="1.0">
      <property name="configver" type="int" value="2"/>
      <property name="panels" type="array">
        <value type="int" value="1"/>
        <property name="dark-mode" type="bool" value="true"/>
        <property name="panel-1" type="empty">
          <property name="position" type="string" value="p=6;x=0;y=0"/>
          <property name="length" type="uint" value="100"/>
          <property name="position-locked" type="bool" value="true"/>
          <property name="icon-size" type="uint" value="16"/>
          <property name="size" type="uint" value="34"/>
          <property name="background-style" type="uint" value="1"/>
          <property name="background-rgba" type="array">
            ${lib.concatStringsSep "\n        " (rgba style.base)}
          </property>
          <property name="plugin-ids" type="array">
            <value type="int" value="11"/>
            <value type="int" value="3"/>
            <value type="int" value="13"/>
            <value type="int" value="12"/>
            <value type="int" value="5"/>
            <value type="int" value="14"/>
            <value type="int" value="15"/>
            <value type="int" value="4"/>
            <value type="int" value="16"/>
            <value type="int" value="10"/>
            <value type="int" value="2"/>
            <value type="int" value="6"/>
            <value type="int" value="7"/>
            <value type="int" value="8"/>
            <value type="int" value="9"/>
          </property>
        </property>
      </property>
      <property name="plugins" type="empty">
        <!-- Invisible: a little room between the screen's edge and "MeccanicOS". -->
        <property name="plugin-11" type="string" value="separator">
          <property name="expand" type="bool" value="false"/>
          <property name="style" type="uint" value="0"/>
        </property>
        <property name="plugin-3" type="string" value="genmon">
          <property name="command" type="string" value="${mos-label}"/>
          <property name="use-label" type="bool" value="false"/>
          <property name="font" type="string" value="${barFontBold}"/>
          <property name="update-period" type="int" value="86400000"/>
        </property>
        <!-- Invisible: room between the name and the workspaces. -->
        <property name="plugin-13" type="string" value="separator">
          <property name="expand" type="bool" value="false"/>
          <property name="style" type="uint" value="0"/>
        </property>
        <!-- Workspaces as buttons with their names (xfwm4's workspace_names). -->
        <property name="plugin-12" type="string" value="pager">
          <property name="rows" type="uint" value="1"/>
          <property name="miniature-view" type="bool" value="false"/>
          <property name="wrap-workspaces" type="bool" value="false"/>
          <property name="numbering" type="bool" value="false"/>
        </property>
        <!-- Expanding, invisible: pushes everything after it to the right. -->
        <property name="plugin-5" type="string" value="separator">
          <property name="expand" type="bool" value="true"/>
          <property name="style" type="uint" value="0"/>
        </property>
        <property name="plugin-14" type="string" value="genmon">
          <property name="command" type="string" value="${mos-session}"/>
          <property name="use-label" type="bool" value="false"/>
          <property name="font" type="string" value="${barFont}"/>
          <property name="update-period" type="int" value="5000"/>
        </property>
        <!-- Invisible: room between the session and the date. -->
        <property name="plugin-15" type="string" value="separator">
          <property name="expand" type="bool" value="false"/>
          <property name="style" type="uint" value="0"/>
        </property>
        <property name="plugin-4" type="string" value="clock">
          <property name="mode" type="uint" value="2"/>
          <property name="digital-layout" type="uint" value="3"/>
          <property name="digital-time-format" type="string" value="%a %d %b  %H:%M"/>
          <property name="digital-time-font" type="string" value="${barFont}"/>
        </property>
        <!-- Invisible: room between the time and the CPU. -->
        <property name="plugin-16" type="string" value="separator">
          <property name="expand" type="bool" value="false"/>
          <property name="style" type="uint" value="0"/>
        </property>
        <property name="plugin-2" type="string" value="windowmenu">
          <property name="style" type="uint" value="0"/>
        </property>
        <property name="plugin-10" type="string" value="genmon">
          <property name="command" type="string" value="${mos-cpu}"/>
          <property name="use-label" type="bool" value="false"/>
          <property name="font" type="string" value="${barFont}"/>
          <property name="update-period" type="int" value="2000"/>
        </property>
        <property name="plugin-6" type="string" value="systray">
          <property name="square-icons" type="bool" value="true"/>
        </property>
        <property name="plugin-7" type="string" value="pulseaudio"/>
        <property name="plugin-8" type="string" value="power-manager-plugin"/>
        <property name="plugin-9" type="string" value="actions">
          <property name="appearance" type="uint" value="0"/>
          <!-- Only "Log Out…": its dialog also offers restart, shut down,
               suspend and switch user. Ctrl+Alt+L locks the screen. -->
          <property name="items" type="array">
            <value type="string" value="-lock-screen"/>
            <value type="string" value="-switch-user"/>
            <value type="string" value="-separator"/>
            <value type="string" value="-suspend"/>
            <value type="string" value="-hibernate"/>
            <value type="string" value="-hybrid-sleep"/>
            <value type="string" value="-separator"/>
            <value type="string" value="-shutdown"/>
            <value type="string" value="-restart"/>
            <value type="string" value="-separator"/>
            <value type="string" value="+logout"/>
            <value type="string" value="-logout-dialog"/>
          </property>
        </property>
      </property>
    </channel>
  '';
  # Typing "shortcuts" in the command bar finds it.
  keysLauncher = pkgs.makeDesktopItem {
    name = "mos-keys";
    desktopName = "Keyboard Shortcuts";
    comment = "Every keyboard shortcut";
    icon = "input-keyboard";
    exec = "mos-keys";
    keywords = [
      "keys"
      "shortcuts"
      "hotkeys"
    ];
    categories = [ "Utility" ];
  };
in
{
  environment.systemPackages = [
    mos-ask
    mos-keys
    mos-status
    mos-passwords # also "Passwords" in the command bar; listed by `mos`
    keysLauncher
    mos-screenshot
    mos-hidpi
    mos-btop
    pkgs.rofi
    pkgs.rofimoji
    pkgs.xdotool # rofimoji types the chosen emoji
    pkgs.xfce4-clipman-plugin # clipboard history daemon
    pkgs.brightnessctl # screen brightness from the keyboard
    pkgs.xfce4-pulseaudio-plugin
    pkgs.xfce4-genmon-plugin # the top bar's name, session and CPU % readouts
  ]
  ++ [
    about
    aboutLauncher
  ]
  ++ terminalApps;
  services.udev.packages = [ pkgs.brightnessctl ]; # lets the "video" group set brightness
  programs.nm-applet.enable = true; # Wi-Fi in the tray
  powerManagement.enable = true; # battery icon + power manager

  environment.etc = {
    "xdg/xfce4/xfconf/xfce-perchannel-xml/xfce4-keyboard-shortcuts.xml".source = shortcuts;
    "xdg/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml".source = panel;
    # The lid belongs to logind (installed.nix: suspend; iso.nix: nothing).
    # By default XFCE's power manager takes it over with its own setting;
    # locked, so its settings dialog can't take it back.
    "xdg/xfce4/xfconf/xfce-perchannel-xml/xfce4-power-manager.xml".text = ''
      <?xml version="1.0" encoding="UTF-8"?>
      <channel name="xfce4-power-manager" version="1.0">
        <property name="xfce4-power-manager" type="empty">
          <property name="logind-handle-lid-switch" type="bool" value="true" locked="*"/>
        </property>
      </channel>
    '';
    # Desktop icons: only USB drives and other removable media, while they
    # are plugged in (click to open, right-click to eject), plus anything put
    # in ~/Desktop. No home, file system or trash icons.
    "xdg/xfce4/xfconf/xfce-perchannel-xml/xfce4-desktop.xml".text = ''
      <?xml version="1.0" encoding="UTF-8"?>
      <channel name="xfce4-desktop" version="1.0">
        <property name="desktop-icons" type="empty">
          <property name="style" type="int" value="2"/>
          <property name="file-icons" type="empty">
            <property name="show-home" type="bool" value="false"/>
            <property name="show-filesystem" type="bool" value="false"/>
            <property name="show-trash" type="bool" value="false"/>
            <property name="show-removable" type="bool" value="true"/>
            <property name="show-device-volume" type="bool" value="true"/>
            <property name="show-fixed-device-volume" type="bool" value="false"/>
            <property name="show-network-volume" type="bool" value="false"/>
          </property>
        </property>
      </channel>
    '';
  };

  # At login: scale the desktop for high-density screens. Again 20 s later:
  # right after login the screen can still be settling (a driver switching
  # modes, the installer's rotation being applied) or the settings service
  # not answering yet; the second run does nothing if the first one held.
  environment.etc."xdg/autostart/mos-hidpi.desktop".text = ''
    [Desktop Entry]
    Type=Application
    Name=Screen scaling
    NoDisplay=true
    Exec=${pkgs.writeShellScript "mos-hidpi-login" ''
      ${mos-hidpi}/bin/mos-hidpi
      ${pkgs.coreutils}/bin/sleep 20
      exec ${mos-hidpi}/bin/mos-hidpi
    ''}
  '';

  # First login: tell people how to drive the system.
  environment.etc."xdg/autostart/mos-welcome.desktop".text = ''
    [Desktop Entry]
    Type=Application
    Name=Keyboard tips
    NoDisplay=true
    Exec=${pkgs.writeShellScript "mos-welcome" ''
      stamp="''${XDG_CONFIG_HOME:-$HOME/.config}/meccanicos/welcomed"
      [ -e "$stamp" ] && exit 0
      mkdir -p "''${stamp%/*}" && touch "$stamp"
      sleep 4
      ${pkgs.libnotify}/bin/notify-send -i input-keyboard -t 15000 \
        "${lib.toUpper distro.name} // WELCOME" \
        "Super+Space: start anything.\nType shortcuts there for every keyboard shortcut."
    ''}
  '';
}
