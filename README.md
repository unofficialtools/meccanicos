# MeccanicOS

<p align="center"><img src="www/MeccanicOS.png" alt="MeccanicOS" width="320"></p>

<p align="center"><a href="https://meccanicos.com"><b>meccanicos.com</b></a> ·
<a href="#1-make-a-usb-drive">Make a USB drive</a> ·
<a href="https://github.com/unofficialtools/meccanicos/releases/tag/latest">Latest release</a></p>

<p align="center"><a href="https://github.com/unofficialtools/meccanicos/actions/workflows/ci.yml?query=branch%3Amain"><img src="https://github.com/unofficialtools/meccanicos/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI on main: passing or failing"></a></p>

**A keyboard-first Linux you carry on a USB stick** — built on NixOS 26.05 with
XFCE, broad hardware support, AI chat, encrypted storage on the stick itself,
and a one-page installer.

- **Runs from USB without a network** — the desktop, the [included apps](#more-apps--apps-needs-the-internet) and the drivers are on the stick, and installing needs no network. Getting *more* apps (`apps`) and local AI models needs the internet once.
- **Keyboard first** — `Super+Space` opens a command bar: type an app, a website, a command, or a search.
- **AI chat, after a one-time download** — `mos-ai-setup` downloads Qwen3 (~2.5 GB) for [Ollama](https://ollama.com); after that it works offline and nothing leaves the computer. Or Claude, ChatGPT or Grok with your API key (your questions go to that company). Chat with [aichat](https://github.com/sigoden/aichat) from the command bar.
- **Encrypted storage on the stick** — vaults, and an optional *persistent home* for your files and settings (see [what survives a restart](#what-survives-a-restart)).
- **Installs offline from one page** — one TUI page; full-disk encryption (LUKS2), unlock by password, TPM or security key.
- **Brushed-metal look** — custom boot menus, login screen, wallpaper and a steel GTK theme.
- **Broad hardware support** — a large collection of drivers and firmware, all of it freely redistributable (see [Licensing](#10-licensing)): Mesa/Vulkan, Intel/AMD video acceleration, PipeWire, Bluetooth, printers and scanners, and NVIDIA's driver picked automatically.
- **Convenient defaults, stated plainly** — passwordless `sudo` (live and installed), and on an installed system an SSH server that accepts keys only. Both can be changed; see [Security](#security-what-is-protected-and-what-is-not).
- **Reproducible** — the whole system is one Nix flake; `flake.lock` pins every package.

<p align="center">
  <img src="www/screenshots/desktop.png" alt="The command bar (Super+Space) over OnlyOffice, btop and yazi" width="100%">
</p>

---

## Contents

1. [Make a USB drive](#1-make-a-usb-drive)
2. [Write it to a USB stick](#2-write-it-to-a-usb-stick)
3. [Start it](#3-start-it)
4. [Using MeccanicOS: keyboard, command bar, AI chat, opening and printing files, settings](#4-using-meccanicos)
5. [Encrypted storage on the stick (`usb-vault`)](#5-encrypted-storage-on-the-stick)
6. [Install to a hard disk](#6-install-to-a-hard-disk)
7. [Living with an installed system](#7-living-with-an-installed-system)
8. [Customise and build](#8-customise-and-build)
9. [Tests and CI](#9-tests-and-ci)
10. [Licensing](#10-licensing) · [Roadmap](#roadmap) · [Credits](#credits)

---

## 1. Make a USB drive

### The easy way: `mos-usb`

One small program, for Windows, macOS and Linux, does it all. It downloads the
latest MeccanicOS (and checks it), tells you to insert a USB drive (16 GB or
larger), makes the drive bootable with [Ventoy](https://www.ventoy.net) and copies
MeccanicOS onto it, then explains how to start a computer from it. Before erasing
a drive it shows a big red warning naming it (for example "USB DRIVE (/dev/sdb)"),
and goes on only if you type `YES`. A drive that already has Ventoy keeps all its files, older MeccanicOS ISOs included. On macOS, where
Ventoy does not run, it writes MeccanicOS directly to the drive (erasing it).

| Your computer | Get it | Run it |
|---|---|---|
| **Windows** | [mos-usb-windows.exe](https://github.com/unofficialtools/meccanicos/releases/download/latest/mos-usb-windows.exe) | Double-click, and allow it to make changes. If Windows warns about an unknown publisher: *More info* → *Run anyway*. |
| **macOS** | [Apple silicon](https://github.com/unofficialtools/meccanicos/releases/download/latest/mos-usb-macos-arm64) · [Intel](https://github.com/unofficialtools/meccanicos/releases/download/latest/mos-usb-macos-x86_64) | In Terminal, with the commands below (a downloaded program needs them on a Mac). |
| **Linux** | [x86_64](https://github.com/unofficialtools/meccanicos/releases/download/latest/mos-usb-linux-x86_64) · [ARM64](https://github.com/unofficialtools/meccanicos/releases/download/latest/mos-usb-linux-arm64) | In a terminal, with the commands below. |

```bash
# macOS (Apple silicon; on an Intel Mac use mos-usb-macos-x86_64)
curl -fLO https://github.com/unofficialtools/meccanicos/releases/download/latest/mos-usb-macos-arm64 && chmod +x mos-usb-macos-arm64 && ./mos-usb-macos-arm64
# Linux (on ARM: mos-usb-linux-arm64)
curl -fLO https://github.com/unofficialtools/meccanicos/releases/download/latest/mos-usb-linux-x86_64 && chmod +x mos-usb-linux-x86_64 && ./mos-usb-linux-x86_64
```

It always comes from the [latest release](../../releases/tag/latest), not from
MeccanicOS itself; its source is in [`tools/mos-usb`](tools/mos-usb). The other
ways below do the same by hand.

### Download the ISO

**[The latest release](../../releases/tag/latest)** (every release keeps its own
dated tag too, like `v2026-10-08`).

The ISO is about 4.5 GB. GitHub limits release files to 2 GB, so it is published
in parts; one command downloads them all (and resumes if interrupted), joins
them and checks the result:

```bash
# Linux / macOS
curl -fsSL https://raw.githubusercontent.com/unofficialtools/meccanicos/main/scripts/get-iso.sh | sh
```
```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/unofficialtools/meccanicos/main/scripts/get-iso.ps1 | iex
```

**By hand:** open the [latest release](../../releases/tag/latest), download **all**
`….iso.partNN` files and `SHA256SUMS`, then join them and check the download:

**Linux / macOS**
```bash
name=$(ls *.iso.part01 | sed 's/\.part01$//')
cat "$name".part* > "$name"
sha256sum -c SHA256SUMS --ignore-missing    # macOS: shasum -a 256 -c SHA256SUMS --ignore-missing
```

**Windows** (Command Prompt, in the download folder)
```bat
copy /b "mos-*.iso.part*" meccanicos.iso
certutil -hashfile meccanicos.iso SHA256
```
Compare the printed hash with the `.iso` line in `SHA256SUMS`.

ISO names carry the build date and the start of the ISO's own SHA-256, e.g.
`meccanicos-26.05-20261004-x86_64-linux-1a2b3c4d.iso`; a running system shows
its build date as `IMAGE_VERSION` in `/etc/os-release`.

MeccanicOS contains only freely redistributable software (see [Licensing](#10-licensing)),
so you may share any ISO you build.

### …or build it yourself

Any Linux with [Nix](https://nixos.org/download) works (NixOS, Fedora, Ubuntu, …), ~60 GB free disk:

```bash
# Nix, once (skip if installed); then enable flakes
sh <(curl -L https://nixos.org/nix/install) --daemon
echo "experimental-features = nix-command flakes" | sudo tee -a /etc/nix/nix.conf
sudo systemctl restart nix-daemon

git clone https://github.com/<you>/meccanicos && cd meccanicos
./start iso                   # first build: 30–90 min, mostly downloads
ls -lh dist/                  # → meccanicos-26.05-<build date>-x86_64-linux-<hash>.iso
```

## 2. Write it to a USB stick

Use a **16 GB or larger** stick (32 GB+ if you want a persistent home). Writing
the ISO **erases the whole stick**. Write it as a raw image ("DD mode") — that is
what makes the encrypted storage on the stick possible.

### Linux

**Terminal**
```bash
lsblk -d -o NAME,SIZE,MODEL,TRAN          # find your stick, e.g. sdb (TRAN = usb)
sudo dd if=meccanicos.iso of=/dev/sdX bs=4M status=progress oflag=sync conv=fsync
```
Replace `sdX` with your stick — **double-check: the wrong letter wipes that disk.**

**GNOME Disks:** select the stick → ⋮ menu → *Restore Disk Image…* → choose the ISO → *Start Restoring*.

**KDE / others:** [balenaEtcher](https://etcher.balena.io) (below) works the same everywhere.

### macOS
```bash
diskutil list                              # find the stick, e.g. /dev/disk4 (external, physical)
diskutil unmountDisk /dev/disk4
sudo dd if=meccanicos.iso of=/dev/rdisk4 bs=4m status=progress   # note the "r" in rdisk
diskutil eject /dev/disk4
```
If macOS says the disk is "not readable" afterwards, click **Ignore** — that's expected.
[balenaEtcher](https://etcher.balena.io) is the point-and-click alternative.

### Windows

**[Rufus](https://rufus.ie)** (recommended)
1. *Device*: your stick. *Boot selection*: **SELECT** → the ISO.
2. Leave the other settings, click **START**.
3. When asked *"ISOHybrid image detected"*, choose **Write in DD Image mode** → OK.

**[balenaEtcher](https://etcher.balena.io)**: *Flash from file* → ISO → *Select target* → stick → *Flash!*

### Ventoy

Copy the `.iso` file onto a [Ventoy](https://www.ventoy.net) stick and boot it from
Ventoy's menu. Nothing else to configure (no `VTOY_LINUX_REMOUNT` needed).

From a checkout of this repository, `./start ventoy /dev/sdX` does it for you: it copies
the newest ISO from `dist/` onto a Ventoy stick (deleting nothing on it, older MeccanicOS ISOs
included), or, if the stick isn't a Ventoy stick yet, installs Ventoy
first (this erases the stick: a big red warning, and you type `YES`; `./start burn` asks the same way). `./start ventoy` alone lists the
USB disks and marks the Ventoy ones. Ventoy comes from the pinned nixpkgs, which labels it
unfree and insecure (prebuilt binaries); it is allowed for this command only.

- **Your stick's files:** Ventoy keeps its partition busy while MeccanicOS runs (it serves the
  ISO file from it), so a normal mount fails. `usb-vault stick` (or *USB Vault* →
  *Open the USB stick's files*) mounts it anyway, at `/run/usb-vault/data`.
- **Encrypted storage** lives as files in a `meccanicos/` folder on the Ventoy partition:
  `meccanicos/mos-home.luks` (persistent home) and `meccanicos/<name>.luks` (vaults). They
  survive replacing the ISO file, and you can copy them like any file.
- Vault *partitions* aren't available on Ventoy (Ventoy's partitions are left alone).

### Updating the stick later

**Back up first** (`usb-vault backup /path/to/other/disk`, or copy the `.luks`
files): the steps below are designed to keep your vaults, but they are not yet
covered by the automated tests, and a stick is easy to lose or wear out.

- **Ventoy stick:** replace the ISO file. Vaults and the persistent home are
  ordinary files in the `meccanicos/` folder and are not touched (this is tested:
  `checks.ventoy`).
- **Stick written in DD mode:** writing a newer ISO over the stick rewrites the
  start of the stick, including its partition table. The vault partitions start
  4 GB after the end of the ISO that created them, and a copy of their partition
  table is kept in the last MiB of the stick; after re-flashing, MeccanicOS offers
  to restore them at login (or run `usb-vault recover`). This works only while
  the new ISO is at most 4 GB larger than that one. If a write is interrupted,
  write the ISO again, then recover; if the stick was repartitioned by another
  tool, the copy of the table may be gone — restore from your backup.

## 3. Start it

1. Plug in the stick, turn the PC on and open the **boot menu**
   (usually `F12`, `F11`, `F10`, `F8` or `Esc` right after power-on; on Macs hold `Option`).
2. Pick the **UEFI** entry for the stick (needed for installing; the live system also boots in legacy BIOS mode).
3. In the MeccanicOS menu choose **MeccanicOS**, or *nomodeset* if the screen stays black,
   *copytoram* to run from RAM and unplug the stick.

There is one entry for all graphics cards. When the only GPU is an NVIDIA
GTX 16xx / RTX or newer, NVIDIA's open driver is used; everything else (Intel, AMD,
older NVIDIA, laptops with Intel/AMD + NVIDIA) uses the open-source drivers.
`mos-gpu-driver` prints the choice. To force it, press `e` (UEFI) or `Tab` (BIOS)
in the boot menu and add `meccanicos.gpu=nvidia` or `meccanicos.gpu=open`.

You land on the desktop as user `live` (no password; `sudo` works without one).
To set a password, press `e` (UEFI) or `Tab` (BIOS) in the boot menu and add `live.passwd=yoursecret`.

**Secure Boot:** NixOS isn't signed for Secure Boot; disable it in the firmware settings if the stick doesn't show up.

## 4. Using MeccanicOS

**Help** in the command bar opens this manual and an overview, offline and
for the version you are running; `mos help TOPIC` opens it at a topic
(`mos help backups`), and over SSH shows it in the terminal.

There is no applications menu; everything starts from the keyboard. The only
desktop icons are USB drives, shown while they are plugged in. The top bar shows
MeccanicOS on the left (click it for System Info: MeccanicOS build, NixOS, kernel, CPU,
memory, disks) and, on the right, the date, CPU use in % (click it for btop),
the window/workspace list, the tray, volume, battery and Log Out.

Apps are named by what they do, then the program: "Web Browser (Brave)",
"Home Files (Thunar)", "File Editor (Jed)" (list in `modules/menu.nix`).

**New to MeccanicOS?** Double-click **Tutorial.mp4** on the desktop: a
video tour, with subtitles — the ideas behind MeccanicOS, then a demo
on the desktop (the command bar, a terminal, yazi, pictures, video, Jed,
printing to PDF, nix-shell, reading aloud, the trash, settings and the
doctor) and previews of trying an app, the persistent home and the installer. `./start tutorial-video`
films it again in a VM (`modules/tutorial-recorder.nix`; KVM and internet).

### Command bar — `Super+Space` (or `Alt+F2`)

| You type | What happens |
|---|---|
| part of an app name (`fil`, `video`, `pass`) | apps are listed as you type, most used first — Enter starts it |
| `github.com`, `https://…`, `localhost:3000` | opens in Brave |
| `btop`, `ls -la`, `git log --oneline` | runs in the terminal |
| a path: `~/Documents`, `/etc/nixos` | opens it in yazi, in a terminal (if it exists) |
| anything else (`convert png to jpg linux`) | searches the web |
| `?…` | ask the local AI (aichat) |
| `!…` | runs it as a command in a new bash shell; Enter closes the window |
| **Ctrl+Enter** | use exactly what you typed, even if an app matches |

### Shortcuts — type `shortcuts` in the command bar to see them all

| Keys | Action |
|---|---|
| `Super+←/→` · `Alt+F10` · `Alt+F9` | snap left/right · maximize · minimize |
| `Alt+F7` · `Alt+F8` | move · resize the window (mouse or arrow keys, then click or Enter) |
| `Alt+F11` · `Alt+F4` | fullscreen · close window |
| `Ctrl+F1…F4` · `Super+Shift+1…4` | go to / move window to workspace |
| `Alt+Tab` · `Super+Tab` | switch window (this workspace) · next window of the same app |
| `Ctrl+Alt+D` · `Ctrl+Alt+L` · `Super+E` | desktop · lock · files |
| `Super+V` · `Super+.` | clipboard history · emoji picker |
| `Print` · `Alt+Print` · `Shift+Print` | screenshot screen · window · area (saved + copied) |
| `Ctrl+Alt+T` · `Ctrl+Alt+Del` | terminal · log out / shut down |
| `Super+Shift+Esc` | disconnect: remote sessions end, every network off (Reconnect in the command bar) |

### AI chat — local Qwen3, or Claude, ChatGPT, Grok

No model ships with MeccanicOS. One command sets it up (needs network once):

```bash
mos-ai-setup                # local (default): downloads qwen3:4b (~2.5 GB) for Ollama
mos-ai-setup claude         # or: chatgpt, grok — asks for your API key (paid, online)
mos-ai-setup local qwen3:1.7b   # any Ollama or provider model as the 2nd argument
mos-ai-setup status         # what is set up, where your questions go, local models and their size
mos-ai-setup remove qwen3:4b    # delete a local model (asks first)
```

Then **AI Chat** in the command bar starts a chat, `?question` in the command bar
answers one question (a lone `?` opens a chat), and `mos-ai` does the same in a
terminal (`mos-ai -e "find big files in my home"` suggests a shell command and
asks before running it). The last AI set up is the default; in a chat, `.model`
switches between all those you set up. API keys are kept in `~/.config/meccanicos/ai`
(readable only by you).

The local model is free, offline and private. Ollama starts when needed (no
password) and listens on `localhost:11434`; it is not started at boot. Add
`/no_think` to a Qwen3 prompt to skip its reasoning step (much faster on a CPU).
On a live stick without a persistent home, downloaded models are lost at shutdown.

### The terminal

Bash with an orange prompt (`user@host`, folder and git branch); `Ctrl+R`
full-history search (Atuin); `Ctrl+T` fuzzy file search (fzf); `z <dir>` jumps
(zoxide); `ll`/`lt` (eza); `cat` with colours (bat); `tldr` that works offline.
`tmux` attaches to (or creates) the `main` session; Jed is the editor for git,
mc and everything else. yazi (`yazi`, or "Home Files (yazi)" in the command
bar) is the terminal file manager with previews; its panels are 20% / 30% / 50%
(parent, folder, preview), pictures show in the preview (through
ueberzugpp: the terminal can't draw them itself), `e` drags the selected files
out to another app and `i` opens a window to drop files on (copied into the
folder). Your own `~/.config/yazi` replaces MeccanicOS's settings in `/etc/xdg/yazi`.
Terminals use VictorMono Nerd Font.

Python 3.13 is preinstalled and behaves like on any Linux:
`python3 -m venv .venv && .venv/bin/pip install …` works with normal PyPI wheels,
and `uv` uses the same Python.

### Opening and printing files

`open FILE|FOLDER|URL` works like on a Mac. One rule file decides which app opens
what, everywhere: the shell (`open`), **yazi** (`Enter` or `Ctrl+O`; a folder is
entered), **mc** (`Enter`), **fzf** (`Ctrl+O` in any file list) and double-click in
**Thunar** or on the **desktop**.

| Files | Open in |
|---|---|
| Text, code, local web pages (`.html`) | Jed |
| Folders | yazi (Thunar keeps folders when you double-click in it) |
| Links (`https://…`), SVG drawings | Brave |
| Pictures | Eye of GNOME (prints with `Ctrl+P`) |
| Videos, music | Celluloid |
| Spreadsheets/CSV · Word files · presentations | OnlyOffice |
| PDF, e-books | Evince |
| Archives | their contents listed in the terminal |

Text, folders and archive listings stay in the terminal you typed in (from the
desktop they get a terminal window of their own); everything else opens in a
window. Thunar's right-click **Open in Browser** shows any file or folder in Brave.

`open -R` shows a file in the file manager, `-e` opens it in VSCodium, `-t` in Jed,
`-a APP` with any app, `-n` prints what would run, and `open --list` shows every
file type with its app and the keys in each program.
The rules are in `/etc/meccanicos/open.conf` (source:
[`scripts/mos-open.conf`](scripts/mos-open.conf)); `open --config` gives you
your own copy (`~/.config/meccanicos/open.conf`) that takes precedence, double-click
included.

`print FILE…` asks where to print — one of the printers, or **Save as PDF** (not
offered for PDFs) — then prints it; office documents, web pages and Markdown are
made into a PDF first, and code saved as PDF gets page numbers. `print -d PRINTER
FILE` and `print --pdf FILE` skip the menu, `-n N` prints N copies, `print -l`
lists the printers; in yazi it is under `O`.

**Printers** in the command bar (`mos-printers`) manages them, full screen:
**Add printers** finds printers on the network and on USB and adds the one you
pick (network printers need no driver; USB ones use the drivers MeccanicOS ships),
**Make default**, **Test page**, **Remove**, and **Queue** shows what is waiting
to print and cancels it. The same from the command line: `mos-printers list`,
`discover`, `add URI`, `default NAME`, `queue`, `cancel JOB|--all`.

Every full-screen tool (Printers, Apps Manager, USB Vault, Configuration
Management, the installer, Read Aloud) looks and works the same way, in the
prompt's colours: a teal title bar, the keys at the bottom, and whatever Enter
acts on — the chosen row, button or field — in orange
([`scripts/lib/mos_tui.py`](scripts/lib/mos_tui.py)).

### Read aloud

**Read Clipboard Aloud** in the command bar reads the copied text aloud with an
offline voice (Piper, "Amy"): `Space` pauses, `←`/`→` skip a sentence, `+`/`-`
change the speed, `q` stops. In a terminal: `mos-read [file]` or `say "text"`.

### What's included

Brave · OnlyOffice (documents, spreadsheets, presentations, PDF forms) · VSCodium (with direnv, Nix, Prettier, GitLens, Live Server,
Markdown All in One, and Open Remote - SSH from Open VSX once online) · gopass (passwords) · mpv + Celluloid ·
Evince · Xfce Terminal · mc, yazi (file managers; `y` returns to the folder you left) · Jed (default editor), Vim · Git, lazygit · pandoc + Typst ·
ImageMagick, poppler-utils (pdfunite, pdfseparate, pdftotext) · jq, yq, sqlite · ripgrep, fd, fzf · btop,
ncdu, strace, lsof · tcpdump, nmap, mtr, dig · Podman (rootless, `docker` alias) ·
[rigx](https://github.com/unofficialtools/rigx) · uv · restic · rclone (Dropbox, Google Drive, …; `mos-dropbox`) · Syncthing · and
[more](packages.nix). Add your own in `packages.nix`, or with `apps` (below).

### More apps — `apps` (needs the internet)

**Apps Manager (apps)** in the command bar lists the apps you installed, with
Uninstall, Update, Update all and Undo, and searches nixpkgs' ~120 000 packages
with **Install** and **Try it** (runs it once, nothing installed). The same from
the terminal:

```bash
apps search video editor     # find (search.nixos.org)
apps try shotcut             # run it without installing
apps install shotcut         # install for you: no password, no restart
apps list | apps update | apps remove shotcut | apps undo
```

Apps go into your own Nix profile from the system's nixpkgs, so they show up in
the command bar. On the live USB they last until you shut down.

**Apps for one folder.** `--here` gives a folder (a project) its own tools,
there and in the folders inside it — in every terminal and in VSCodium — and
nowhere else:

```bash
cd ~/myproject
apps install --here gcc python3   # downloaded now; ready from the next prompt
apps list --here | apps remove --here gcc | apps update --here
```

They go into the folder's `.envrc` (`use nix -p gcc python3`, between two
`mos-apps` lines; the rest of the file is left alone), which direnv loads.
Commit `.envrc` and anyone with direnv and Nix gets the same tools. Desktop apps
started from the command bar don't see them: for those, plain `apps install`.

### Dropbox (without the Dropbox app)

`mos-dropbox` connects your Dropbox account through rclone:

```bash
mos-dropbox login            # once; over SSH it explains how to sign in from your own computer
mos-dropbox mount            # Dropbox live in ~/Dropbox (online)   · mos-dropbox unmount
mos-dropbox sync             # a local copy in ~/Dropbox, synced both ways every 5 minutes
mos-dropbox pause | resume   # stop / restart the automatic sync
mos-dropbox status | logout
```

### Settings and fixes — `mos-config`, `mos-doctor`

`mos` lists every `mos-*` command (each one answers `--help`).
**Configuration Management** in the menu (`mos-config`) shows the common
settings in one place — screen scale, resolution and rotation (landscape or
portrait), wallpaper, screensaver and lock, keyboard layouts, touchpad, power, sound,
clock, time zone and, once installed, the lid, hibernation, updates, SSH and
firewall ports, the graphics driver:

In a terminal, `mos-config` opens them full screen: move with the arrows, Enter
changes the one under the cursor (pick from a list, flip on/off, or type it),
`e`/`i` export and import, `d` runs the doctor, `q` quits. The same from the command line:

```bash
mos-config list                     # every setting and its value (--json too)
mos-config set keyboard.layout us,it
mos-config set power.lid            # without a value: what it does, the choices
mos-config set display.rotation portrait
mos-config set display.wallpaper ~/Pictures/beach.jpg
mos-config export ~/stick/settings.toml --dotfiles   # take them to another computer…
mos-config import ~/stick/settings.toml --dotfiles   # …and bring them back
mos-config network                  # the connection, internet yes/no, VPNs
mos-config network connect NAME     # join a Wi-Fi network (asks for the password)
mos-config network signin           # open the sign-in page of a hotel/airport network
mos-config network vpn on|off NAME | vpn import FILE | vpn add
```

The **Network** rows at the top of the full screen do the same: Enter on the
connection lists the Wi-Fi networks in reach, on *internet* opens the sign-in
page, on *VPN* turns one on or off or adds one (WireGuard, and OpenVPN files).

Settings stay where the system keeps them, so the Xfce settings windows agree;
every change is also recorded in `~/.config/meccanicos/settings.toml`. System settings
on an installed system go into `/etc/nixos/meccanicos.toml` and need a rebuild, which
`mos-config` offers. `--dotfiles` also saves your shell, git, editor and terminal
files, never keys or passwords (unless `--with-secrets`: then it asks for a password
and encrypts them).

**Configuration Doctor** (`mos-doctor`) checks Wi-Fi and the internet, Bluetooth,
sound, the screen (including which graphics driver is used; details:
`mos-gpu-driver`, also in **System Info**) and disk space, explains what's wrong and offers a fix
(it asks first; every fix is logged in `~/.local/state/meccanicos/doctor.log`).
`mos-doctor sound --reset` restarts one area from scratch; `--check` only reports;
`--report` saves a file to ask for help, with serial numbers and addresses removed.

### Updates — `mos-updates`

**Updates** in the command bar (`mos-updates`; `mos-updates status` as text)
shows everything that can change, in one place, and how to undo it:

- **The system** (installed): the build you run, whether automatic updates are
  on, and *Check for updates* (`mos-upgrade --check`), *Update now* (`mos-upgrade`),
  *Update at next restart* (`mos-upgrade --boot`). Every
  update keeps the system before it: *Go back to the previous system* lists them
  and switches back (`nixos-rebuild switch --rollback`); they are also in the
  boot menu. On the live USB, the system is updated by writing a newer ISO
  ([Updating the stick later](#updating-the-stick-later)).
- **Your apps**: *Update all* (`apps update`) and *Undo the last change* (`apps undo`).

Nothing changes without asking first, and changes run in the terminal so you
see what they do.

### Backups — `mos-backup`

Encrypted, deduplicated backups of your home folder (restic), in the spirit of
macOS Time Machine: to an external disk, a vault, or the cloud.

```bash
mos-backup init /run/media/live/MyDisk/backup   # once; asks for a backup password
mos-backup init dropbox:backup      # or the cloud: any rclone account (after mos-dropbox login)
mos-backup now                      # back up now
mos-backup auto on                  # every night (02:30; a missed night runs at the next start)
mos-backup auto hourly              # or every hour; auto off: none
mos-backup browse                   # get files back, full screen (also: Restore Files from a Backup)
mos-backup versions report.odt      # the backed-up versions of one file…
mos-backup versions report.odt --restore ID   # …put back next to it as "report (2026-10-01 0230).odt"
mos-backup mount                    # every backup as a folder per date in ~/Backups; unmount closes it
mos-backup files [ID] [PATH] | find 'report*.pdf' | restore ID --only Documents/report.pdf
```

- **Nothing is overwritten:** restores go into a new `~/Restored-<date>` folder,
  or next to the file with the backup's date in its name.
- **Versions of a file:** right-click a file in Files → *Versions from Backups…*,
  or `B` in yazi.
- **Plug in the disk, and it backs up** (if the last backup is more than 12 hours
  old), with a notification when it is done. With no backup set up yet, a newly
  plugged USB disk gets one "Use it for backups?" notification (never the
  MeccanicOS stick or an internal disk).
- **Old backups thin out:** everything from the last 24 hours, then one a day
  for a month, one a week for a year, one a month for two years.
- **Encrypted** with your backup password (also file names and folders); the
  password is saved in `~/.config/meccanicos/backup.pass` (readable only by you)
  so that automatic backups can run. Write it down somewhere else: without it a
  backup cannot be read.

## 5. Encrypted storage on the stick

`usb-vault` (also in the command bar as **Encrypted Storage (USB Vault)**) stores encrypted data in
the free space of the stick you booted from. Everything is LUKS2 (argon2id) —
useless to anyone without the password.

```bash
usb-vault create-home --size 16G    # persistent home: files & settings survive reboots
usb-vault create-partition --size 8G
usb-vault create-file --size 4G --name docs   # docs.luks on an exFAT partition (readable from Windows/macOS)
usb-vault open | close [--all] | status
usb-vault backup /media/other-disk  # full copy, still encrypted
usb-vault restore /media/other-disk/mos-usb-backup-…   # e.g. onto a new stick
usb-vault recover                   # after re-flashing the stick
usb-vault stick                     # mount the stick's own files (also on Ventoy)
```

- **Persistent home:** at start-up you're asked for its password on the boot
  screen; press Enter on an empty password for a fresh, throw-away session.
- **Vaults** mount at `~/Vault` (and `~/Vault-<name>`); at login MeccanicOS offers to unlock them.
- A stick has 4 partition slots and the system uses 2. When they run out, the
  persistent home is created as a `mos-home.luks` file automatically.
- **Ventoy sticks:** everything is a file in `meccanicos/` on the Ventoy partition
  (see [Ventoy](#ventoy)). `usb-vault stick` opens the stick's files.

### What survives a restart

The live system runs from the stick with its changes in memory: anything not in
the home folder, a vault or the stick's files is gone when you shut down.

| | Live, no persistent home | Live, persistent home | Installed |
|---|---|---|---|
| Your files and settings (home folder) | lost at shutdown | **kept**, encrypted on the stick | **kept** |
| Vaults (`~/Vault…`) | **kept** on the stick | **kept** on the stick | **kept** on the stick |
| Apps you added (`apps install`) | lost at shutdown | lost at shutdown (the package store is in memory); the list is kept, and `apps update` downloads them again | **kept** |
| Folder apps (`apps install --here`) | lost | the list is kept (`.envrc`); downloaded again when you enter the folder | **kept** |
| Local AI models (`mos-ai-setup`) | lost at shutdown | lost at shutdown (kept by the system, not in your home); `mos-ai-setup` downloads them again | **kept** |
| The apps that come with MeccanicOS | always there | always there | always there |

`usb-vault summary` (also at the end of `usb-vault status`, and at the top of
**USB Vault** in the command bar) shows this for the system you are running,
with the space used and left.

## 6. Install to a hard disk

Run **Installer** (desktop icon, or type `install` in the command bar).
One page, no wizard:

```
  Country          Italy               ← fills in language, time zone, keyboard
  Language         English (United States)
  Time zone        Europe/Rome
  Keyboard         Italian             ← switches immediately, so passwords match at boot
  Screen           Landscape / Portrait
  Wi-Fi network    (scanned list)      Wi-Fi password  ••••
  Full name / Username / Password
  Disk password    ••••••••            ← full-disk encryption, asked at every boot
  Target disk      nvme0n1  512.1 GB  Samsung SSD …
  Filesystem       ext4 on LUKS2 (encrypted), EFI boot
                       [  Install now  ]
```

`↑↓` move, `Enter` edits (long lists filter as you type), **Install now**; a big red warning
names the disk (for example "HARD DRIVE (/dev/nvme0n1)"), and you type `YES` to erase it.
It downloads nothing — the installed system is prebuilt inside the ISO.

You get: GPT disk (1 GB EFI + LUKS2/ext4), systemd-boot,
zram swap plus a RAM-sized swap file for hibernation, your user with **passwordless sudo**, root login disabled, and **SSH
on with key login only** (add keys to `~/.ssh/authorized_keys`), and your own SSH key pair
(`~/.ssh/id_ed25519`, to log in to other machines). Requires UEFI.
The firewall lets everything out but nothing unsolicited in, except SSH (TCP 22,
installed systems only) and printer/scanner discovery (mDNS, UDP 5353); pings are
ignored.

### Security: what is protected and what is not

| | Live session | Persistent home / vaults | Installed system |
|---|---|---|---|
| Your data at rest | not written anywhere (memory only) | encrypted (LUKS2, argon2id) | whole disk encrypted (LUKS2), incl. swap/hibernation |
| Login password | none (set one with `live.passwd=` in the boot menu) | the home's password at start-up | yours |
| `sudo` | no password | no password | **no password** (convenience: anyone at your unlocked session is root) |
| SSH server | off | off | **on, keys only** (no passwords; `mos-config set security.ssh off` turns it off) |

The trade-offs are deliberate: a single-user workstation where the disk
password and the screen lock are the barriers. If others use your computer
unlocked, or you want a password for `sudo`, set
`security.sudo.wheelNeedsPassword = true` in `/etc/nixos/local.nix` and run
`mos-rebuild`. The stick's system part is not encrypted (it is the same ISO
everyone downloads); only your vaults and persistent home are.

### Logins and SSH attacks

A watcher in your session reads the system journal and tells you what matters
([`scripts/mos-logins.py`](scripts/mos-logins.py)):

- an **SSH login from an address or key not seen before**: an alert at once,
  with **It's me** (no alerts for it again), **End remote sessions** and
  **Disconnect**;
- an **SSH attack aimed at you** — failures from your own network, or on your
  user name — with **Block this address** (an hour), **Stop SSH**, **Disconnect**;
- what happened **while the screen was locked or you were logged out** — wrong
  passwords at the lock screen, login screen or sudo, wrong disk passwords at
  start-up, SSH logins — in one summary when you are back.

Internet scanners (random user names: every SSH server gets them) are only
counted, and **sshguard** blocks addresses that keep failing by itself. Alerts
never flood you: one per address per hour, at most three of each kind an hour,
then a single "see Logins"; a flood of attacks can't hide a new login.

**Logins** in the command bar (`mos-logins`) shows who is connected now, the
last 7 days and the blocked addresses, with the same buttons. **Disconnect**
(command bar, or `Super+Shift+Esc`) is the panic button: remote sessions end, SSH
stops, every network (Wi-Fi, cable, Bluetooth) goes off and the screen locks;
**Reconnect** brings it all back. `mos-config set security.login_alerts off`
silences the alerts. `security.auto_disconnect on` disconnects by itself when
someone unknown logs in — off by default, because an unfamiliar login is not
necessarily an attack, and disconnecting can lock out the owner working
remotely. `mos-doctor logins` checks it all.

### Security hardening

On by default, live and installed ([`modules/hardening.nix`](modules/hardening.nix));
chosen so that nothing stops working. Hardware comes first: no driver, device or
firmware is affected; hibernation, Brave's sandbox, podman, VMs and external disks
all behave as before:

- **Kernel**: no kernel addresses or kernel log for ordinary users, eBPF for root
  only (and its compiled code hardened), programs may only debug their own
  children (`ptrace_scope=1`), no replacing the running kernel (kexec), safer
  shared folders (`protected_fifos`/`protected_regular`), no core dumps of setuid
  programs.
- **Memory**: full ASLR with the most randomness the CPU allows (`mmap_rnd_bits`),
  memory zeroed when allocated (`init_on_alloc`), kernel caches kept apart
  (`slab_nomerge`), randomized page and kernel stack layout, no legacy vsyscall
  page. About 1–3% CPU.
- **Network**: no ICMP redirects or source routing, SYN cookies, broadcast pings
  ignored (on top of the firewall and its reverse-path check).
- **Unused network protocols** can't be loaded (DCCP, SCTP, RDS, TIPC, …): only
  ones no device needs; every driver and filesystem stays.
- **dbus-broker** instead of the reference D-Bus daemon: the same bus, faster
  and sturdier.

Left out on purpose, as they break things: kernel lockdown (hibernation and
unsigned drivers such as NVIDIA's), debugfs=off (hardware tools), a hardened memory allocator (Brave, VSCodium), the hardened kernel and
no user namespaces (Brave's sandbox, podman). `meccanicos.hardening.enable = false;`
in the configuration turns all of the above off.

## 7. Living with an installed system

`/etc/nixos` holds only your own files — `local.nix` (your installer choices, edit freely),
`hardware-configuration.nix`, `meccanicos.toml` (mos-config's system settings) and
`remote-unlock-keys` — and a small `flake.nix` that takes everything else from this repository
at its **latest release** (the `latest` tag, moved by each release), pinned in `flake.lock`.

| Task | Command |
|---|---|
| Apply your edits (`local.nix`, …) | `mos-rebuild` |
| Everything about updates, in one place | `mos-updates` (or **Updates** in the command bar) |
| Update now | `mos-upgrade`: the newest MeccanicOS release and NixOS packages (`--check` shows yours and the newest, `--boot` applies at the next restart; `mos-update` is the same) |
| Automatic updates | weekly in the background, applied at the next restart (notification); off with `mos-config set updates.auto off` |
| SSH, firewall ports, lid, hibernation, graphics driver | `mos-config set security.ssh off`, `mos-config set security.tcp_ports 8080` … (`mos-config` lists them) |
| Something isn't working | `mos-doctor` |
| Roll back | `mos-updates` → *Go back to the previous system*, or pick an older entry in the boot menu |
| Backups | `mos-backup init /media/disk` → `mos-backup now` → `mos-backup auto on` (nightly); `mos-backup browse` or *Versions from Backups…* to get files back |
| Unlock the disk with the TPM / a security key | `mos-unlock tpm` / `mos-unlock key` (password keeps working) |
| Recovery key | `mos-unlock recovery` |
| Unlock over SSH at boot (wired network) | `mos-unlock remote` (allows your `~/.ssh/authorized_keys`); then after each restart `ssh -p 2222 root@<machine>` and type the disk password. Off: `mos-unlock remove-remote` |
| Clean-ups | automatic: old system versions and unused packages weekly (older than 30 days); crash dumps — only the newest is kept |

Updates (`mos-upgrade`, and the weekly automatic ones) bring both the newest **MeccanicOS**
release (tools, settings, fixes), the newest **packages** of its NixOS release and the newest
rigx, as one
rebuild: `nix flake update` in `/etc/nixos`, then `nixos-rebuild`. If the rebuild fails, the
previous `flake.lock` is put back; the previous system stays in the boot menu. When a release
moves to a newer NixOS (26.05 → 26.11), `mos-upgrade` follows it. Rebuilds without updating
(`mos-rebuild`, a mos-config system setting) work offline: the source of the version you run
stays on the disk.

Closing the lid **suspends**, on battery and on power. With an external screen connected,
closing the lid does nothing and you keep working on the external screen. Laptops switch
to the power-saver profile on battery.
**Hibernate** only when you ask for it: *Log Out…* dialog → *Hibernate* (or
`systemctl hibernate`). Memory is saved to a swap file inside the encrypted disk, and the
next start asks for the disk password (also over SSH with remote unlock) and picks up
where you left off. The swap file is created at boot, as large as the RAM, unless
that would leave less than 10 GB free.
Text grows with the screen, at every login on a screen it was not done for: width/2048 on screens wider than 2048 pixels (2560: 1.25×, 3840: 1.875×), or 1.5×/2× on small dense ones; title bars, the top bar and the cursor follow, icons keep their size. `mos-config set display.scale 1.5` picks a size by hand (and keeps it); `auto` goes back.

## 8. Customise and build

| What | Where |
|---|---|
| Name, live user, labels | `distro = { … }` in [`flake.nix`](flake.nix) |
| Packages | [`packages.nix`](packages.nix) — names from [search.nixos.org](https://search.nixos.org/packages?channel=26.05) |
| Artwork | PNGs in [`branding/`](branding) (same names), or regenerate with `branding/generate.py --name YOURNAME` |
| Theme, login screen, wallpaper | [`modules/branding.nix`](modules/branding.nix) |
| Command bar, shortcuts, top bar | [`scripts/mos-ask.sh`](scripts/mos-ask.sh), [`modules/keyboard.nix`](modules/keyboard.nix) |
| Which app opens which file (shell, yazi, mc, fzf, double-click) | [`scripts/mos-open.conf`](scripts/mos-open.conf); turned into the desktop's defaults in [`modules/shell.nix`](modules/shell.nix) |
| `print` | [`scripts/mos-print.sh`](scripts/mos-print.sh) |
| AI chat (`mos-ai-setup`, `mos-ai`) | [`modules/ai.nix`](modules/ai.nix) |
| Drivers, kernel | [`modules/drivers.nix`](modules/drivers.nix), [`modules/iso.nix`](modules/iso.nix) |
| Smaller ISO | `isoImage.squashfsCompression = "xz -Xdict-size 100%";` in `modules/iso.nix` |

Options you can set in any module (or `/etc/nixos/local.nix`):

| Option | Default | Effect |
|---|---|---|
| `meccanicos.autoUpgrade` | `true` | weekly background updates (installed system) |
| `meccanicos.hibernate` | `true` | RAM-sized swap file on the encrypted disk, for hibernation (installed system) |
| `meccanicos.remoteUnlock` | on after `mos-unlock remote` | SSH server on port 2222 at boot to type the disk password remotely (installed system) |

Build output: `nix build .#iso`. A plain `nix build` stamps the ISO with the last commit's date and leaves it in `result/iso/`;
`./start iso` stamps today's date (`MECCANICOS_BUILD_DATE=YYYYMMDD`, via `--impure`) and copies
it to `dist/` with its hash in the name.

<details>
<summary>Project layout</summary>

```
flake.nix                distro settings, outputs (ISOs, systems, tests)
packages.nix             your package list
modules/
  iso.nix                live-USB plumbing, live user, persistent-home unlock
  installed.nix          the installed system: LUKS, boot, SSH, updates, power
  installer.nix          ships the prebuilt installed system + installer in the ISO
  drivers.nix            hardware support (mapped from EndeavourOS packages.x86_64)
  desktop.nix            XFCE, LightDM, fonts
  keyboard.nix           command bar, shortcuts, cheat sheet, top bar, HiDPI, screenshots
  branding.nix           theme, login screen, wallpaper   (branding-boot.nix: boot menus)
  ai.nix                 Ollama + aichat, mos-ai-setup, AI Chat (no model shipped)
  shell.nix              bash, prompt, terminal, tmux, mc, yazi, fzf, open + print, Jed, tldr, podman
  hardening.nix          kernel, memory and network hardening; dbus-broker
  logins.nix             login alerts, Logins, Disconnect / Reconnect, sshguard
  mos-cli.nix          meccanicos, mos-config (+ full-screen view), mos-doctor (scripts/mos/)
  settings.nix           installed: applies /etc/nixos/meccanicos.toml (written by mos-config)
  vscodium.nix           VSCodium and its extensions (installed at first start)
  vault.nix backup.nix printing.nix browser.nix
scripts/                 usb-vault, mos-install, mos-ask, mos-open (+ open.conf), mos-print, mos-backup, mos-unlock, mos-vm, …
branding/                artwork + generator
tutorial/tutorial.mp4    the tutorial video (./start tutorial-video)
tests/                   VM tests
```
</details>

## 9. Tests and CI

VM tests boot the real ISO under QEMU (need KVM):

```bash
nix build .#checks.x86_64-linux.live -L      # desktop, command bar, local AI, vault, persistent home across reboots
nix build .#checks.x86_64-linux.install -L   # installer → reboot → LUKS password → user/sudo/SSH/locale checks
nix build .#checks.x86_64-linux.ventoy -L    # the ISO as a file on a Ventoy stick: boot, vault, persistent home
```
Screenshots land in `result/`.

### Try it in a VM / record a video

```bash
nix run .#vm                         # builds the ISO if needed and boots it (UEFI, 1920×1080, sound, network)
nix run .#vm -- --res 2560x1440      # recording resolution
nix run .#vm -- --disk 64G           # add an empty disk to film the installer
nix run .#vm -- --installed          # afterwards: boot the installed system
nix run .#vm -- --offline --fresh    # no network; start from a clean stick
nix run .#vm -- --help               # all options (--mem, --cpus, --gl, --fullscreen, --bios, …)
```
The virtual USB stick is kept between runs (vaults and the persistent home survive;
`--fresh` resets). Click into the window and press **Ctrl+Alt+G** so shortcuts such as
`Super+Space` reach MeccanicOS. To record, capture the QEMU window with
[OBS Studio](https://obsproject.com) (*Window Capture*) or your desktop's recorder.
Needs KVM (virtualization enabled in the BIOS; your user in the `kvm` group).

GitHub Actions: [`CI`](.github/workflows/ci.yml), on every push to any branch and every pull
request, runs shellcheck (every severity) and pyflakes, checks that the tutorial's scenes match
their narration (`python3 tests/tutorial_points.py`), checks and cross-builds `mos-usb`
(gofmt, go vet for Linux/Windows/macOS, go test), and evaluates everything; on `main` it also
runs the three VM tests (screenshots are kept as artifacts). The badge at the top shows `main`.
For another branch, the same badge with `?branch=NAME`, or
`https://github.com/unofficialtools/meccanicos/actions/workflows/ci.yml?query=branch%3ANAME`,
shows whether its last push passed.

[`Web page`](.github/workflows/pages.yml) publishes [meccanicos.com](https://meccanicos.com)
with GitHub Pages: on every push to `main` that changes `www/` (the page, its screenshots in
`www/screenshots/`) or the tutorial video. One-time setup: Settings → Pages → Source
"GitHub Actions", custom domain `meccanicos.com`, "Enforce HTTPS"; in the domain's DNS, `A`
records for `meccanicos.com` to 185.199.108.153, 185.199.109.153, 185.199.110.153 and
185.199.111.153 (optionally `AAAA` to 2606:50c0:8000::153 … 2606:50c0:8003::153), and
`www.meccanicos.com` as a `CNAME` to `unofficialtools.github.io`. [`Release`](.github/workflows/release.yml) builds the public ISO when you push a
tag like `v2026-10-08` and publishes it (and again as `latest`), split into parts with `SHA256SUMS`. Builds use the
runner's large scratch disk; add a free [Cachix](https://cachix.org) cache (repository
variable `CACHIX_CACHE` + secret `CACHIX_AUTH_TOKEN`) to make them much faster.
Commit `flake.lock` (`nix flake lock`) so every build is pinned.

## 10. Licensing

The MeccanicOS configuration, scripts and artwork are under the [BSD 3-Clause License](LICENSE).
Built ISOs contain software under many licenses (GPL, MIT, BSD, Apache-2.0, MPL, …):
NixOS/nixpkgs (MIT), Linux (GPL-2.0), XFCE (GPL), Brave (MPL-2.0), Ollama (MIT),
aichat (MIT/Apache-2.0), OnlyOffice (AGPL-3.0), and NVIDIA's driver and linux-firmware
(proprietary but redistributable).

Everything on the ISO may be redistributed. Software that may not (VS Code's Microsoft
build, Dropbox, and firmware for Broadcom Bluetooth, b43 Wi-Fi, the Xbox wireless
dongle and Apple FaceTime cameras) is left out; VSCodium replaces VS Code.

## Roadmap

See [TODO.md](TODO.md) for the full list,
and [CONTRIBUTING.md](CONTRIBUTING.md) before sending a pull request.

## Credits

Built on [NixOS](https://nixos.org). Driver selection mirrors
[EndeavourOS](https://endeavouros.com)'s live ISO. Local AI by
[Ollama](https://ollama.com) and [aichat](https://github.com/sigoden/aichat).
Theme [Graphite](https://github.com/vinceliuice/Graphite-gtk-theme), icons
[Kora](https://github.com/bikass/kora),
command bar [rofi](https://github.com/davatorium/rofi).
