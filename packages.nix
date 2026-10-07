# ============================================================================
#  YOUR PACKAGE LIST
#
#  Everything listed here is baked into the ISO and works with no network.
#  Find package names at https://search.nixos.org/packages (channel 26.05),
#  or offline with:  nix search nixpkgs <word>
#
#  Shell setup (bash, prompt, atuin, zoxide, fzf, eza, bat, xfce4-terminal, tldr,
#  podman) lives in modules/shell.nix.
#
#  After editing, rebuild:  nix build .#iso
# ============================================================================
{
  lib,
  pkgs,
  ...
}:
{
  environment.systemPackages = with pkgs; [
    # --- Version control ---
    git
    git-lfs
    lazygit
    gh # GitHub CLI: PRs, issues, clone

    # --- Network / downloads ---
    curl
    wget
    openssh # ssh, scp, sftp, ssh-keygen
    rsync
    sshfs # mount a remote folder over SSH
    mosh # SSH that survives network changes and sleep

    # --- Terminal / editors ---
    tmux
    vim # vi, vim
    jed # default editor ($EDITOR, git, mc)
    less
    mc # Midnight Commander (modarin256-defbg-thin skin, edits with Jed: modules/shell.nix)
    dtach # detach/reattach a running program (tmux-lite)
    # VSCodium and its extensions: modules/vscodium.nix

    # --- Search / selection ---
    ripgrep # rg
    fd
    fzf

    # --- Text processing ---
    gnused # sed
    gawk # awk
    coreutils # sort, uniq, cut, paste, tee, timeout, sha256sum, du, df ...

    # --- Structured data ---
    jq
    yq-go # yq (mikefarah, the YAML/JSON/TOML one)
    sqlite # sqlite3

    # --- Automation / builds ---
    findutils # xargs, find
    parallel # GNU parallel
    entr
    procps # watch, ps, free
    just
    gnumake # make
    uv # Python package/project manager (fetches from PyPI when online)
    nodejs_24 # node, npm, npx
    readline # libraries for building native extensions
    libffi

    # --- System / debugging ---
    duf # disk usage overview (df)
    trash-cli # trash-put / trash-list / trash-restore instead of rm
    nix-tree # browse what takes space in a Nix system
    btop
    ncdu
    file
    lsof
    strace

    # --- Network diagnostics ---
    iproute2 # ss, ip
    dig # dig, nslookup, host
    netcat-openbsd # nc
    tcpdump
    nmap
    mtr

    # --- Script utilities ---
    util-linux # flock
    moreutils # sponge, ts, vipe, chronic
    diffutils # diff
    gnupatch # patch

    # --- Archives / compression ---
    gnutar
    zip
    unzip
    _7zz # 7zz
    gzip
    pigz
    bzip2
    xz
    zstd
    lz4
    unrar

    # --- Encryption / checksums ---
    age
    gnupg
    gocryptfs # encrypted folder (FUSE), e.g. inside a synced folder

    # --- Cloud / sync ---
    rclone # Dropbox, Google Drive, OneDrive, S3...: rclone config, mount, bisync
    syncthing # sync folders between your own devices, no cloud (web UI)

    # --- Images / PDF ---
    imagemagick # magick
    eog # Eye of GNOME: image viewer with menus and printing
    # PDFs: Evince views them and fills forms; these do the rest (merge,
    # split, text, images), with the same engine as Evince and yazi.
    poppler-utils # pdfunite, pdfseparate, pdftotext, pdfimages, pdftocairo, pdfinfo, pdffonts

    # --- Documents ---
    # Office suite: documents, spreadsheets, presentations and PDF forms, in
    # Microsoft's formats first (OpenDocument works too). One app with tabs;
    # the command bar also lists one entry per kind of document (below).
    onlyoffice-desktopeditors
    (makeDesktopItem {
      name = "mos-office-word";
      desktopName = "Word Processor (OnlyOffice)";
      comment = "Write a new document (.docx, .odt)";
      icon = "x-office-document";
      exec = "onlyoffice-desktopeditors --new:word";
      categories = [ "Office" ];
    })
    (makeDesktopItem {
      name = "mos-office-cell";
      desktopName = "Spreadsheet (OnlyOffice)";
      comment = "Make a new spreadsheet (.xlsx, .ods)";
      icon = "x-office-spreadsheet";
      exec = "onlyoffice-desktopeditors --new:cell";
      categories = [ "Office" ];
    })
    (makeDesktopItem {
      name = "mos-office-slide";
      desktopName = "Presentations (OnlyOffice)";
      comment = "Make a new presentation (.pptx, .odp)";
      icon = "x-office-presentation";
      exec = "onlyoffice-desktopeditors --new:slide";
      categories = [ "Office" ];
    })
    pandoc # convert between Markdown, HTML, DOCX, ODT, EPUB, LaTeX, …
    typst # PDF engine for pandoc: pandoc in.md -o out.pdf --pdf-engine=typst

    # --- Command help ---
    man
    tealdeer # tldr (pages bundled, see modules/shell.nix)

    # --- Desktop apps ---
    # Browser: Brave (modules/browser.nix).
    # rigx comes from its own flake (inputs in flake.nix).
    # Passwords: gopass + age (command bar "Passwords"; setup in modules/keyboard.nix)
    gopass
    evince
    # Video/music player (keyboard-driven, plays everything via FFmpeg).
    # Without yt-dlp + Deno for YouTube URLs (~0.17 GB); VLC was ~0.25 GB.
    (mpv.override { youtubeSupport = false; })
    celluloid # window with buttons, playlists and menus for mpv (replaces XFCE's Parole)

    # --- Disk & backup tools ---
    fsarchiver
    ddrescue
    testdisk
    pv

    # Add your own below, one per line, e.g.:
    # python3
    # nodejs
  ];

  # Run programs built for other Linux distros: the Pythons uv downloads,
  # binary wheels (numpy, torch...), VS Code server, prebuilt CLI tools.
  programs.nix-ld.enable = true;

  # programs.wireshark.enable = true;
}
