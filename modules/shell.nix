# Terminal-first setup: Bash with an orange prompt, Atuin history,
# zoxide, fzf, eza/bat, Xfce Terminal as the default terminal, offline tldr.
{
  lib,
  pkgs,
  ...
}:
let
  inherit (import ./not-root.nix) notRoot;
  tSh = import ./i18n-sh.nix pkgs;
  # tldr pages bundled into the ISO so `tldr` works with no network.
  tldrPages = pkgs.fetchFromGitHub {
    owner = "tldr-pages";
    repo = "tldr";
    rev = "v2.3";
    hash = "sha256-uMQ9Bul2g86AEcFYmFD9sOnUJaz08fguy9HENnKLwik=";
  };
  toml = pkgs.formats.toml { };
  mos-open = pkgs.writeShellApplication {
    name = "mos-open";
    runtimeInputs = with pkgs; [
      coreutils
      util-linux # setsid
      file
      dbus # dbus-send: "show in file manager"
      xdg-utils
      _7zz # list archive contents
      less
    ];
    text = tSh "mos-open" + notRoot "mos-open" + ''exec ${pkgs.bash}/bin/bash ${../scripts/mos-open.sh} "$@"'';
  };
  # print: a menu of printers + "Save as PDF", then prints (scripts/mos-print.sh).
  # Brave, pandoc and typst (for conversions) come from the system.
  mos-print = pkgs.writeShellApplication {
    name = "mos-print";
    runtimeInputs = with pkgs; [
      coreutils
      util-linux # setsid
      gnused
      file
      fzf
      cups # lp, lpstat
      ghostscript # ps2pdf
    ];
    text = tSh "mos-print" + notRoot "mos-print" + ''exec ${pkgs.bash}/bin/bash ${../scripts/mos-print.sh} "$@"'';
  };
  # "File Editor (Jed)": Jed in its own terminal window (command bar, Open With).
  jedMimeTypes = [
    "text/plain"
    "text/markdown"
    "text/x-markdown"
    "text/x-log"
    "text/x-python"
    "text/x-csrc"
    "text/x-chdr"
    "text/x-c++src"
    "text/x-java"
    "text/x-rust"
    "text/x-go"
    "text/x-lua"
    "text/x-tex"
    "text/x-makefile"
    "text/x-nix"
    "text/css"
    "text/html"
    "application/xhtml+xml"
    "text/javascript"
    "application/x-shellscript"
    "application/json"
    "application/xml"
    "application/x-yaml"
    "application/toml"
    "application/javascript"
    "application/x-desktop"
    "inode/x-empty"
  ];

  # Double-click follows open.conf: every MIME type it names becomes a default
  # of the hidden "Open" entry (mos-open). The desktop has no wildcards, so
  # families (image/*, ...) are spelled out. Folders stay in Thunar.
  mimeFamilies = {
    text = lib.filter (lib.hasPrefix "text/") jedMimeTypes;
    image = map (t: "image/" + t) [
      "bmp"
      "gif"
      "jpeg"
      "png"
      "tiff"
      "webp"
      "heic"
      "x-portable-anymap"
      "x-tga"
    ];
    video = map (t: "video/" + t) [
      "mp4"
      "x-matroska"
      "webm"
      "quicktime"
      "x-msvideo"
      "mpeg"
      "ogg"
      "x-flv"
      "3gpp"
    ];
    audio = map (t: "audio/" + t) [
      "mpeg"
      "mp4"
      "flac"
      "ogg"
      "opus"
      "x-wav"
      "x-vorbis+ogg"
      "aac"
    ];
  };
  openMimeTypes =
    let
      rules = lib.filter (l: l != "" && !lib.hasPrefix "#" l) (
        map lib.trim (lib.splitString "\n" (builtins.readFile ../scripts/mos-open.conf))
      );
      patterns = lib.concatMap (l: lib.splitString "," (builtins.head (lib.splitString " " l))) rules;
      expand =
        p:
        if !(lib.hasInfix "/" p) || p == "inode/directory" then
          [ ]
        else if lib.hasSuffix "/*" p then
          mimeFamilies.${lib.removeSuffix "/*" p} or [ ]
        else
          [ p ];
    in
    lib.unique (lib.concatMap expand patterns);
  openLauncher = pkgs.makeDesktopItem {
    name = "mos-open";
    desktopName = "Open (MeccanicOS rules)";
    comment = "Open with the app chosen in /etc/meccanicos/open.conf";
    icon = "document-open";
    exec = "mos-open %f";
    noDisplay = true;
    mimeTypes = openMimeTypes;
  };
  jedLauncher = pkgs.makeDesktopItem {
    name = "mos-jed";
    desktopName = "File Editor (Jed)";
    comment = "Edit text and code in Jed, the terminal text editor";
    icon = "accessories-text-editor";
    exec = "xfce4-terminal --class jed --title Jed -x jed %f";
    mimeTypes = jedMimeTypes;
    categories = [
      "Utility"
      "TextEditor"
    ];
  };
  # yazi with MeccanicOS's config (/etc/xdg/yazi) unless the user has their own.
  # pkgs.yazi already brings what its docs list for previews and search
  # (ffmpeg, 7-Zip, jq, poppler, fd, rg, fzf, resvg, ImageMagick, chafa,
  # zoxide); the Nerd Font is the terminal's. Added here:
  #   ueberzugpp   pictures in the preview: xfce4-terminal can't draw images
  #                itself, so yazi puts a window over it (without it: nothing)
  #   xclip        cc / cd / cf copy paths to the clipboard
  #   dragon-drop  drag files out (e) and drop files in (i): see keymap.toml
  yaziWrapper = pkgs.writeShellScriptBin "yazi" ''
    if [ -z "''${YAZI_CONFIG_HOME:-}" ] && [ ! -d "''${XDG_CONFIG_HOME:-$HOME/.config}/yazi" ]; then
      export YAZI_CONFIG_HOME=/etc/xdg/yazi
    fi
    export PATH="${
      lib.makeBinPath [
        pkgs.ueberzugpp
        pkgs.xclip
        pkgs.dragon-drop
      ]
    }:$PATH"
    exec ${pkgs.yazi}/bin/yazi "$@"
  '';
  # yazi's i: a small window to drop files on (from Files, Brave, ...); they
  # are copied into the folder yazi shows. Dropping onto the terminal itself
  # only types the file's name, as in any terminal.
  yaziDropHere = pkgs.writeShellScript "yazi-drop-here" ''
    ${pkgs.dragon-drop}/bin/dragon-drop --target --and-exit --print-path --on-top |
      while IFS= read -r f; do
        case $f in /*) cp -rn -- "$f" . ;; esac
      done
  '';
  tldrCache = pkgs.runCommand "tldr-cache" { } ''
    mkdir -p $out/tldr-pages
    cp -r ${tldrPages}/pages $out/tldr-pages/pages.en
  '';
  # Jed in the colours of mc's "modarin256-defbg-thin" skin (256-colour
  # indices, terminal background): menus like mc's menu bar (light text,
  # orange hotkeys, light-on-teal selection), mc's teal status bar and marked
  # text, code coloured from mc's file-type palette.
  jedColors = pkgs.writeText "meccanicos.sl" ''
    $1 = "color250"; $2 = "default";
    set_color("normal", $1, $2);
    set_color("status", "color253", "color66");
    set_color("region", "color228", "color23");
    set_color("message", "color187", $2);
    set_color("error", "color203", $2);
    set_color("cursor", "color235", "color250");
    set_color("cursorovr", "color235", "color214");
    set_color("linenum", "color66", "color235");
    set_color("menu", $1, $2);
    set_color("menu_char", "color214", $2);
    set_color("menu_popup", "color252", "color239");
    set_color("menu_shadow", "color236", $2);
    set_color("menu_selection", "color253", "color23");
    set_color("menu_selection_char", "color214", "color23");
    set_color("operator", $1, $2);
    set_color("delimiter", $1, $2);
    set_color("number", "color216", $2);
    set_color("comment", "color245", $2);
    set_color("string", "color114", $2);
    set_color("keyword", "color180", $2);
    set_color("keyword1", "color109", $2);
    set_color("keyword2", "color144", $2);
    set_color("keyword3", "color153", $2);
    set_color("keyword4", "color141", $2);
    set_color("keyword5", $1, $2);
    set_color("keyword6", $1, $2);
    set_color("keyword7", $1, $2);
    set_color("keyword8", $1, $2);
    set_color("keyword9", $1, $2);
    set_color("preprocess", "color170", $2);
    set_color("dollar", "color170", $2);
    set_color("...", "color203", $2);
    set_color("url", "color45", $2);
    set_color("trailing_whitespace", "color56", "color234");
    set_color("tab", "color239", $2);
    set_color("italic", "color187", $2);
    set_color("underline", "color114", $2);
    set_color("bold", "color228", $2);
    set_color("html", "color180", $2);
  '';
in
{
  # ---- Midnight Commander defaults ------------------------------------------
  # Skin "modarin256-defbg-thin" (256 colours, terminal background, single
  # lines) and F4 opening $EDITOR (Jed) instead of mc's built-in editor.
  # Global mc.ini is only the starting point: a user's ~/.config/mc/ini takes
  # over once saved. (On a 16-colour console mc falls back to its default.)
  nixpkgs.overlays = [
    (final: prev: {
      mc = prev.mc.overrideAttrs (old: {
        postInstall = (old.postInstall or "") + ''
          cat > $out/etc/mc/mc.ini <<'EOF'
        [Midnight-Commander]
        skin=modarin256-defbg-thin
        use_internal_edit=false
        EOF
          # Enter opens documents, media, web pages and anything unknown
          # through `open`; archives, packages and man pages keep mc's own.
          sed -i -E \
            -e 's#^Open=.*/ext\.d/(doc|video|sound|image|web)\.sh .*#Open=mos-open %f#' \
            -e 's#^Open=$#Open=mos-open %f#' \
            $out/etc/mc/mc.ext.ini
        '';
      });
      # Jed loads lib/site.slc instead of site.sl when the .slc is "not older",
      # and a missing file counts as time 0. On the live ISO every store file
      # has mtime 0 (squashfs), so it picked the missing site.slc and started
      # without its library (no menus, "Unable to open site"). Only prefer
      # .slc files that exist.
      jed = prev.jed.overrideAttrs (old: {
        postPatch = (old.postPatch or "") + ''
          substituteInPlace src/ledit.c --replace-fail \
            'if (file_time_cmp(libfslc, libfsl) >= 0)' \
            'if ((1 == file_status (libfslc)) && (file_time_cmp(libfslc, libfsl) >= 0))'
        '';
        # Default colour scheme "meccanicos": the colours of mc's modarin256 skin
        # (see jedColors). A user's ~/.jedrc can still set_color_scheme(...).
        postInstall = (old.postInstall or "") + ''
          cp ${jedColors} $out/share/jed/lib/colors/meccanicos.sl
          echo '_Jed_Default_Color_Scheme = "meccanicos";' > $out/share/jed/lib/defaults.sl
        '';
      });
    })
  ];

  # git reads $EDITOR too; set it here as well for tools that clear the env.
  programs.git = {
    enable = true;
    config.core.editor = "jed";
  };

  # ---- Bash as the login shell for everyone -------------------------------
  users.defaultUserShell = pkgs.bashInteractive;
  # The same prompt inside nix-shell too, instead of its own [nix-shell:~]$.
  environment.variables.NIX_SHELL_PRESERVE_PROMPT = "1";
  programs.bash = {
    completion.enable = true;
    # In mc's skin colours: a teal bar (mc's selection, 253 on 23) with
    # user@host #1, the directory in sand (180, mc's headers) and [git branch] in orange
    # (214, mc's hotkeys); then an orange "> " on its own line.
    # \[ \] mark the colour codes as zero-width for line editing.
    # The [branch] only inside a git repository. The bar ends in a triangle
    # where it is exactly the line's height: Nerd Fonts draw it as tall as the
    # line, so only in xfce4-terminal (VTE) with a Nerd Font (VictorMono, as
    # set); elsewhere (the console, another font) the bar just ends.
    promptInit = ''
      _meccanicos_end=""
      if [ -n "''${VTE_VERSION:-}" ]; then
        case $(xfconf-query -c xfce4-terminal -p /font-name 2>/dev/null) in
          *"Nerd Font"*) _meccanicos_end='\[\e[0;38;5;23m\]' ;;
        esac
      fi
      PS1='\[\e[38;5;253;48;5;23m\] \u@\h #1 \[\e[38;5;180m\]\w \[\e[38;5;214m\]$(b=$(git branch -q --show-current 2>/dev/null) && [ -n "$b" ] && printf "[%s] " "$b")'"$_meccanicos_end"'\[\e[0m\]\n\[\e[38;5;214m\]>\[\e[0m\] '
      unset _meccanicos_end
    '';
    # fzf's keys load first so Atuin (below) gets to own Ctrl-R.
    interactiveShellInit = lib.mkBefore ''
      HISTSIZE=50000
      HISTFILESIZE=50000
      HISTCONTROL=ignoreboth # no duplicates, no lines starting with a space
      shopt -s histappend autocd # type a folder name to cd into it

      source ${pkgs.fzf}/share/fzf/key-bindings.bash   # Ctrl-T files, Alt-C dirs
      export FZF_DEFAULT_COMMAND='fd --type f --hidden --exclude .git'
      export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
      # y: yazi that leaves the shell in the folder you were in when you quit.
      y() {
        local tmp cwd
        tmp=$(mktemp -t yazi-cwd.XXXXXX)
        yazi "$@" --cwd-file="$tmp"
        IFS= read -r -d "" cwd < "$tmp"
        [[ -n $cwd && $cwd != "$PWD" ]] && builtin cd -- "$cwd"
        rm -f -- "$tmp"
      }
      export FZF_DEFAULT_OPTS='--height 40% --layout=reverse --border --color=bg+:#3a4049,fg+:#ffffff,hl:#9fb4c8,hl+:#cfe0f0,info:#8a96a3,prompt:#cfd6de,pointer:#cfd6de,marker:#9fb4c8,border:#5b6470 --bind "ctrl-o:execute(mos-open {+})"'
    '';
    shellAliases = {
      ls = "eza --group-directories-first";
      ll = "eza -l --git --group-directories-first";
      la = "eza -la --git --group-directories-first";
      lt = "eza --tree --level=2";
      cat = "bat --paging=never --style=plain";
      tldr = "tldr --quiet"; # pages are bundled; hide the "cache is old" nag
      trash = "trash-put"; # recoverable rm: trash-list, trash-restore, trash-empty
    };
  };

  # ---- open: one way to open files (shell, fzf, yazi, mc) -------------------
  # Rules in /etc/meccanicos/open.conf; ~/.config/meccanicos/open.conf (`open --config`)
  # overrides them.
  environment.etc."meccanicos/open.conf".source = ../scripts/mos-open.conf;

  # ---- yazi: terminal file manager with previews ---------------------------
  # Config in /etc/xdg/yazi, used until the user makes ~/.config/yazi.
  environment.etc."xdg/yazi/yazi.toml".source = toml.generate "yazi.toml" {
    # Panels: parent folder 20%, current folder 30%, preview 50%.
    mgr = {
      ratio = [
        2
        3
        5
      ];
      sort_dir_first = true;
    };
    # Everything opens through `open` (Enter); O offers the alternatives.
    # block: terminal programs (Jed, yazi for a folder) take over this
    # terminal; desktop apps are detached by `open` itself.
    opener = {
      open = [
        {
          run = "mos-open %s";
          block = true;
          desc = "Open";
        }
      ];
      code = [
        {
          run = "mos-open -e %s";
          orphan = true;
          desc = "VSCodium";
        }
      ];
      edit = [
        {
          run = "\${EDITOR:-vi} %s";
          block = true;
          desc = "Terminal editor ($EDITOR)";
        }
      ];
      print = [
        {
          run = "mos-print %s";
          block = true;
          desc = "Print…";
        }
      ];
      reveal = [
        {
          run = "mos-open -R %s1";
          orphan = true;
          desc = "Show in file manager";
        }
      ];
    };
    # Folders: Enter and Ctrl+O go into them; O offers "show in file manager".
    open.rules = [
      {
        url = "*/";
        use = [ "reveal" ];
      }
      {
        url = "*";
        use = [
          "open"
          "code"
          "edit"
          "print"
          "reveal"
        ];
      }
    ];
  };
  # Colours of mc's "modarin256-defbg-thin" skin (as in Jed and the prompt;
  # hex of the same 256-colour indices): the cursor line light on teal (253
  # on 23), orange (214) for keys and the active choice, sand (180) titles,
  # teal (66) borders and status, file types coloured like mc's panels.
  environment.etc."xdg/yazi/theme.toml".source =
    let
      c = {
        c23 = "#005f5f"; # teal: cursor line, selection
        c66 = "#5f8787"; # light teal: status bar, borders
        c45 = "#00d7ff"; # symlinks, links
        c109 = "#87afaf"; # source code
        c114 = "#87d787"; # executables
        c141 = "#af87ff"; # audio, video
        c172 = "#d78700"; # archives
        c180 = "#d7af87"; # sand: headers, titles
        c187 = "#d7d7af"; # input text
        c203 = "#ff5f5f"; # errors, broken links
        c214 = "#ffaf00"; # orange: hotkeys
        c216 = "#ffaf87"; # images
        c228 = "#ffff87"; # marked
        c235 = "#262626";
        c236 = "#303030";
        c239 = "#4e4e4e";
        c245 = "#8a8a8a"; # dim text
        c250 = "#bcbcbc"; # normal text
        c253 = "#dadada"; # text on teal
      };
      on = fg: bg: { inherit fg bg; };
      cursor = on c.c253 c.c23;
      frame = {
        border.fg = c.c66;
        title.fg = c.c180;
      };
    in
    toml.generate "theme.toml" {
      mgr = {
        cwd = {
          fg = c.c180;
          bold = true;
        };
        find_keyword = {
          fg = c.c228;
          bold = true;
        };
        find_position = {
          fg = c.c214;
          bold = true;
        };
        marker_copied = on c.c114 c.c114;
        marker_cut = on c.c203 c.c203;
        marker_marked = on c.c45 c.c45;
        marker_selected = on c.c228 c.c228;
        count_copied = on c.c235 c.c114;
        count_cut = on c.c235 c.c203;
        count_selected = on c.c235 c.c228;
        border_style.fg = c.c239;
      };
      tabs = {
        active = cursor // { bold = true; };
        inactive = on c.c250 c.c236;
      };
      mode = {
        normal_main = on c.c253 c.c66 // { bold = true; };
        normal_alt = on c.c253 c.c23;
        select_main = on c.c235 c.c214 // { bold = true; };
        select_alt = on c.c214 c.c236;
        unset_main = on c.c235 c.c203 // { bold = true; };
        unset_alt = on c.c203 c.c236;
      };
      indicator = {
        parent = cursor;
        current = cursor;
      };
      status = {
        perm_sep.fg = c.c239;
        perm_type.fg = c.c109;
        perm_read.fg = c.c228;
        perm_write.fg = c.c203;
        perm_exec.fg = c.c114;
        progress_normal = on c.c66 c.c236;
        progress_error = on c.c203 c.c236;
      };
      which = {
        mask.bg = c.c235;
        cand.fg = c.c214;
        rest.fg = c.c245;
        desc.fg = c.c250;
        separator_style.fg = c.c239;
      };
      confirm = frame;
      spot = frame // {
        tbl_col.fg = c.c180;
        tbl_cell = cursor;
      };
      pick = frame // {
        active = {
          fg = c.c214;
          bold = true;
        };
      };
      input = frame // {
        value.fg = c.c187;
        selected = on c.c228 c.c23;
      };
      cmp = frame // {
        active = cursor;
      };
      tasks = frame // {
        hovered = {
          fg = c.c214;
          bold = true;
        };
      };
      help = {
        on.fg = c.c214;
        run.fg = c.c180;
        hovered = cursor // { bold = true; };
        footer = on c.c253 c.c66;
      };
      notify = {
        title_info.fg = c.c114;
        title_warn.fg = c.c228;
        title_error.fg = c.c203;
      };
      filetype.rules = [
        {
          url = "*/";
          fg = c.c253;
          bold = true;
        }
        {
          url = "*";
          is = "orphan";
          fg = c.c203;
        }
        {
          url = "*";
          is = "link";
          fg = c.c45;
        }
        {
          url = "*";
          is = "exec";
          fg = c.c114;
        }
        {
          mime = "image/*";
          fg = c.c216;
        }
        {
          mime = "{audio,video}/*";
          fg = c.c141;
        }
        {
          mime = "application/{zip,rar,7z*,tar,gzip,xz,zstd,bzip*,lzma,compress,archive,cpio,arj,xar,ms-cab*}";
          fg = c.c172;
        }
        {
          url = "*.{c,h,cc,cpp,hpp,py,sh,rs,go,js,ts,java,lua,nix,pl,rb,el,sl}";
          fg = c.c109;
        }
        {
          mime = "vfs/{absent,stale}";
          fg = c.c245;
        }
      ];
    };
  environment.etc."xdg/yazi/keymap.toml".source = toml.generate "keymap.toml" {
    mgr.prepend_keymap = [
      {
        on = "<Enter>";
        run = "plugin smart-enter";
        desc = "Enter the folder, or open the file";
      }
      {
        on = "<C-o>";
        run = "plugin smart-enter";
        desc = "Enter the folder, or open the file";
      }
      # Drag and drop (e and i are free in yazi's own keys).
      {
        on = "e";
        run = ''shell --orphan -- dragon-drop --all --and-exit --on-top "$@"'';
        desc = "Drag the selected files out (to Files, Brave, an email, ...)";
      }
      {
        on = "i";
        run = "shell --orphan -- ${yaziDropHere}";
        desc = "Drop files here: copies what you drop on the window into this folder";
      }
      # B (free in yazi): the backed-up versions of the hovered file (mos-backup).
      {
        on = "B";
        run = "shell --block -- mos-backup versions %h --menu";
        desc = "Versions from backups: restore one next to the file";
      }
    ];
  };
  environment.etc."xdg/yazi/plugins/smart-enter.yazi".source = pkgs.yaziPlugins.smart-enter;

  # ---- tmux: one "main" session -------------------------------------------
  # Config lives in /etc/tmux.conf; ~/.tmux.conf, if present, adds to it.
  programs.tmux = {
    enable = true;
    extraConfig = ''
      set -g base-index 1
      setw -g pane-base-index 1

      # Easier splits
      bind | split-window -h
      bind - split-window -v

      # Easier pane movement
      bind h select-pane -L
      bind j select-pane -D
      bind k select-pane -U
      bind l select-pane -R

      # Reload config (system one, then your own if you have one)
      bind r source-file /etc/tmux.conf \; source-file -q ~/.tmux.conf \; display-message "tmux config reloaded"

      # Make status line simple
      set -g status-left '#S '
      set -g status-right '''

      source-file -q ~/.tmux.conf
    '';
  };
  # Plain `tmux` attaches to the "main" session, creating it if needed;
  # `tmux <anything>` (ls, new -s work, attach -t x, ...) works as usual.
  environment.interactiveShellInit = ''
    tmux() {
      if [ "$#" -eq 0 ]; then command tmux new-session -A -s main
      else command tmux "$@"; fi
    }
  '';

  # direnv + nix-direnv: a project's .envrc (e.g. `use flake`) loads when you
  # cd into it. Cached, so Nix dev shells open instantly after the first time.
  programs.direnv = {
    enable = true;
    silent = true;
  };

  # Atuin: full-text searchable history on Ctrl-R. Local only, no network.
  programs.atuin = {
    enable = true;
    flags = [ "--disable-up-arrow" ]; # keep classic Up-arrow behaviour
    settings = {
      auto_sync = false;
      update_check = false;
      style = "compact";
      inline_height = 20;
      search_mode = "fuzzy";
      filter_mode_shell_up_key_binding = "session";
    };
  };
  programs.zoxide.enable = true; # `z proj` / `zi` (interactive)
  programs.zoxide.flags = [ ];

  # ---- Xfce Terminal: default terminal, steel colours -----------------------
  # System defaults (xfconf channel "xfce4-terminal"); changes made in its
  # Preferences are saved per user and take over. TERM is xterm-256color.
  environment.etc."xdg/xfce4/xfconf/xfce-perchannel-xml/xfce4-terminal.xml".text = ''
    <?xml version="1.0" encoding="UTF-8"?>
    <channel name="xfce4-terminal" version="1.0">
      <property name="font-use-system" type="bool" value="false"/>
      <property name="font-name" type="string" value="VictorMono Nerd Font 11"/>
      <property name="misc-menubar-default" type="bool" value="false"/>
      <property name="shortcuts-no-menukey" type="bool" value="true"/>
      <property name="shortcuts-no-helpkey" type="bool" value="true"/>
      <property name="misc-bell" type="bool" value="false"/>
      <property name="misc-confirm-close" type="bool" value="false"/>
      <property name="misc-cursor-shape" type="string" value="TERMINAL_CURSOR_SHAPE_IBEAM"/>
      <property name="color-use-theme" type="bool" value="false"/>
      <property name="color-foreground" type="string" value="#d8dde4"/>
      <property name="color-background" type="string" value="#22262c"/>
      <property name="color-cursor-use-default" type="bool" value="false"/>
      <property name="color-cursor" type="string" value="#cfd6de"/>
      <property name="color-selection-use-default" type="bool" value="false"/>
      <property name="color-selection" type="string" value="#ffffff"/>
      <property name="color-selection-background" type="string" value="#4a525d"/>
      <property name="color-bold-is-bright" type="bool" value="true"/>
      <property name="color-palette" type="string" value="#2b2f36;#c0717a;#93ad86;#cdb688;#7f9bb6;#a58db3;#7fb0b4;#c3cad3;#5b6470;#d8909a;#aec7a1;#e0cba2;#9fb4c8;#bca8c9;#9ccace;#f2f5f8"/>
    </channel>
  '';
  # Make Xfce Terminal the terminal for Ctrl+Alt+T, the panel and Thunar "Open Terminal Here".
  environment.etc."xdg/xfce4/helpers.rc".text = ''
    TerminalEmulator=xfce4-terminal
    WebBrowser=brave-browser
  '';
  # One terminal: no xterm, and no "Terminal Emulator" entry in the command
  # bar (exo's shortcut that would just open Xfce Terminal again; exo-open
  # itself stays for Thunar's "Open Terminal Here"; hidden below).
  # One image viewer too: Eye of GNOME (prints; packages.nix) instead of Ristretto; one
  # media player: mpv with Celluloid (packages.nix) instead of Parole; one text
  # editor: Jed (below) instead of Mousepad; and one way to start apps: the
  # command bar (and the desktop's menu) instead of the Application Finder.
  environment.xfce.excludePackages = [
    pkgs.ristretto
    pkgs.parole
    pkgs.mousepad
    pkgs.xfce4-appfinder
  ];

  # Double-click in Thunar / on the desktop goes through open, like everything else.
  xdg.mime.defaultApplications = lib.genAttrs openMimeTypes (_: "mos-open.desktop");
  services.xserver.excludePackages = [ pkgs.xterm ];

  environment.sessionVariables = {
    TERMINAL = "xfce4-terminal";
    # Jed for everything that opens an editor: git, lazygit, mc (F4),
    # sudoedit, crontab -e, systemctl edit, less (v), ...
    EDITOR = "jed";
    VISUAL = "jed";
    PAGER = "less";
    LESS = "-R --mouse";
    MANPAGER = "sh -c 'col -bx | bat -l man -p'"; # coloured man pages
    MANROFFOPT = "-c";
    BAT_THEME = "Nord";
    TEALDEER_CONFIG_DIR = "/etc/tealdeer";
  };
  environment.etc."tealdeer/config.toml".text = ''
    [directories]
    cache_dir = "${tldrCache}"
    [updates]
    auto_update = false
    [display]
    compact = false
    use_pager = false
  '';

  # Only the four styles used (Regular, Bold, Italic, Bold Italic): of
  # "VictorMono Nerd Font", the terminal's (and so mc's, yazi's, Jed's), and
  # of "JetBrainsMono Nerd Font", the command bar's. The full packages also
  # have Mono/Propo families in many weights (~0.2 GB each).
  fonts.packages = [
    # Nerd Font icons (yazi, eza, the prompt) in any font: fontconfig takes
    # the glyphs a font lacks from here.
    pkgs.nerd-fonts.symbols-only
    (pkgs.runCommand "nerd-fonts-core" { } ''
      mkdir -p $out/share/fonts/truetype
      for s in Regular Bold Italic BoldItalic; do
        cp ${pkgs.nerd-fonts.jetbrains-mono}/share/fonts/truetype/NerdFonts/JetBrainsMono/JetBrainsMonoNerdFont-$s.ttf \
          ${pkgs.nerd-fonts.victor-mono}/share/fonts/truetype/NerdFonts/VictorMono/VictorMonoNerdFont-$s.ttf \
          $out/share/fonts/truetype/
      done
    '')
  ];

  # ---- Shell tooling --------------------------------------------------------
  environment.systemPackages = with pkgs; [
    # Hidden from the command bar (still runnable): exo's generic "Terminal
    # Emulator", "Mail Reader", "Web Browser" and "File Manager" shortcuts
    # (Brave and Files have their own entries; there is no mail app), and
    # Vim / GVim, which are for use from the shell (vi, vim).
    (lib.hiPrio (
      symlinkJoin {
        name = "hidden-desktop-entries";
        paths = map (
          e:
          writeTextDir "share/applications/${e.id}.desktop" ''
            [Desktop Entry]
            Type=Application
            Name=${e.name}
            Exec=${e.exec}
            NoDisplay=true
          ''
        ) [
          { id = "xfce4-terminal-emulator"; name = "Terminal Emulator"; exec = "exo-open --launch TerminalEmulator"; }
          { id = "xfce4-terminal-settings"; name = "Xfce Terminal Settings"; exec = "xfce4-terminal --preferences"; }
          { id = "xfce4-mail-reader"; name = "Mail Reader"; exec = "exo-open --launch MailReader %u"; }
          { id = "xfce4-web-browser"; name = "Web Browser"; exec = "exo-open --launch WebBrowser %u"; }
          { id = "xfce4-file-manager"; name = "File Manager"; exec = "exo-open --launch FileManager %u"; }
          { id = "vim"; name = "Vim"; exec = "vim %F"; }
          { id = "gvim"; name = "GVim"; exec = "gvim %F"; }
        ];
      }
    ))
    fzf
    eza
    bat
    mos-open
    (runCommand "open" { } "mkdir -p $out/bin; ln -s ${mos-open}/bin/mos-open $out/bin/open")
    mos-print
    jedLauncher
    openLauncher
    (runCommand "print" { } "mkdir -p $out/bin; ln -s ${mos-print}/bin/mos-print $out/bin/print")
    yazi
    (lib.hiPrio yaziWrapper)
    tealdeer
    man-pages
    man-pages-posix
  ];
  documentation.man.cache.enable = true; # `man -k` / apropos work offline
  # Man pages only: no /share/doc (~0.13 GB of package docs) or GNU info.
  documentation.doc.enable = false;
  documentation.info.enable = false;

  # Containers: podman (rootless, `docker` alias), works offline with local images.
  virtualisation.podman = {
    enable = true;
    dockerCompat = true;
    defaultNetwork.settings.dns_enabled = true;
  };
  virtualisation.containers.enable = true;
  # rootless podman: the live user gets a subuid/subgid range automatically
}
