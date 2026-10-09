# Automated VM tests (need KVM):
#
#   nix build .#checks.x86_64-linux.live     -L   # boot the ISO, desktop, vault, persistent home
#   nix build .#checks.x86_64-linux.install  -L   # install to a virtual disk, boot it with LUKS
#   nix build .#checks.x86_64-linux.ventoy   -L   # boot the ISO file from a Ventoy stick
#   nix flake check -L                            # both
#
# Screenshots end up in ./result/ (desktop.png, command-bar.png, cheat-sheet.png).
# The tests use copies of the live and installed systems with NixOS's test
# instrumentation added (a control channel for the test driver); everything
# else is exactly what ships.
{
  self,
  nixpkgs,
  system,
}:
let
  pkgs = nixpkgs.legacyPackages.${system};
  lib = nixpkgs.lib;
  qemu-common = import "${nixpkgs}/nixos/lib/qemu-common.nix" { inherit lib; inherit (pkgs) stdenv; };
  qemu = qemu-common.qemuBinary pkgs.qemu_test;

  instrumented =
    { lib, ... }:
    {
      imports = [ "${nixpkgs}/nixos/modules/testing/test-instrumentation.nix" ];
      # Plain-text password prompts on the serial console instead of the splash.
      boot.plymouth.enable = lib.mkForce false;
      # Make the serial port the primary console so stage-2 prompts reach it too.
      boot.kernelParams = lib.mkAfter [ "console=ttyS0,115200" ];
      users.users.root.hashedPassword = lib.mkForce null;
      # After resuming from hibernation the old control channel points at the
      # previous QEMU; restart it so the test driver can reconnect (as in
      # NixOS's own hibernate test).
      powerManagement.resumeCommands = "systemctl --no-block restart backdoor.service";
    };

  installed = self.nixosConfigurations.installed.extendModules { modules = [ instrumented ]; };
  live = self.nixosConfigurations.live.extendModules {
    modules = [ instrumented ];
    specialArgs.installedSystem = installed.config.system.build.toplevel;
  };
  iso = "${live.config.system.build.isoImage}/iso/${live.config.image.fileName}";

  # Ventoy, only to prepare a Ventoy stick in the ventoy test (never shipped):
  # nixpkgs marks it unfree and insecure (prebuilt binaries).
  ventoy =
    (import nixpkgs {
      inherit system;
      config = {
        allowUnfree = true;
        allowInsecurePredicate = p: (p.pname or "") == "ventoy";
      };
    }).ventoy;

  # Shared Python helpers: UEFI firmware with writable variables, disks.
  prelude = ''
    import os, shlex, shutil, subprocess

    tmp = os.environ.get("TMPDIR", "/tmp")
    vars_file = os.path.join(tmp, "OVMF_VARS.fd")
    shutil.copy("${pkgs.OVMF.variables}", vars_file)
    os.chmod(vars_file, 0o644)

    def qcow(name, size, backing=None):
        path = os.path.join(tmp, name)
        cmd = ["${pkgs.qemu_test}/bin/qemu-img", "create", "-f", "qcow2"]
        if backing:
            cmd += ["-b", backing, "-F", "raw"]
        subprocess.run(cmd + [path, size], check=True)
        return path

    def start_command(*drives, memory=4096):
        cmd = [
            "${qemu}", "-m", str(memory), "-smp", "4",
            "-drive", "if=pflash,format=raw,unit=0,readonly=on,file=${pkgs.OVMF.firmware}",
            "-drive", f"if=pflash,format=raw,unit=1,file={vars_file}",
            "-netdev", "user,id=net0", "-device", "virtio-net-pci,netdev=net0",
            "-device", "qemu-xhci", "-vga", "virtio",
        ]
        return " ".join(cmd + list(drives))

    # The ISO, written to a 16 GB "USB stick" (copy-on-write, the ISO stays untouched).
    usb_stick = qcow("usb.qcow2", "16G", backing="${iso}")
    usb = f"-drive id=usb,file={usb_stick},format=qcow2,if=none -device usb-storage,drive=usb,removable=on"

    # Answer a boot-time password prompt (the persistent home) through systemd's
    # password agent protocol, from the test shell: typing on the serial console
    # races the login prompt that also reads it.
    def answer_password(machine, password, timeout=900):
        machine.wait_until_succeeds("ls /run/systemd/ask-password/ask.* >/dev/null 2>&1", timeout=timeout)
        machine.succeed(
            "for f in /run/systemd/ask-password/ask.*; do "
            "s=$(sed -n 's/^Socket=//p' \"$f\"); "
            f"printf '%s' {shlex.quote(password)} | "
            "/run/current-system/systemd/lib/systemd/systemd-reply-password 1 \"$s\"; done"
        )

    # Checks pipe into `grep >/dev/null`, not `grep -q`: commands run with
    # pipefail, and grep -q quits at the first match, so the writer can die of
    # a broken pipe and fail the check at random.

    # usb-vault mounts vaults for the desktop user (the test shell is root).
    def as_live(cmd):
        return f"su - live -c {shlex.quote(cmd)}"
  '';
in
{
  live = pkgs.testers.runNixOSTest {
    name = "mos-live";
    nodes = { };
    testScript = prelude + ''
      machine = create_machine(start_command(usb), name="live")
      machine.start()

      with subtest("boots to the XFCE desktop as the live user"):
          machine.wait_for_unit("multi-user.target")
          machine.wait_for_unit("display-manager.service")
          machine.wait_until_succeeds("pgrep -u live xfce4-panel", timeout=600)
          machine.wait_for_x()
          machine.sleep(10)
          machine.screenshot("desktop")

      with subtest("command bar routes apps, URLs, commands and questions"):
          assert machine.succeed(as_live("mos-ask --classify github.com")).startswith("url\thttps://github.com")
          assert machine.succeed(as_live("mos-ask --classify 'ls -la'")).startswith("run\t")
          # Terminal tools by their short name: their launcher, whose window closes when they end.
          assert machine.succeed(as_live("mos-ask --classify btop")).startswith("app\t")
          assert machine.succeed(as_live("mos-ask --classify 'find big files in my home'")).startswith("search\t")
          assert machine.succeed(as_live("mos-ask --classify '?what is 1+1'")).startswith("ask\t")
          assert machine.succeed(as_live("mos-ask --classify '!ls -la'")).startswith("shell\tls -la")
          assert machine.succeed(as_live("mos-ask --classify '~'")).startswith("path\t/home/live")
          assert machine.succeed(as_live("mos-ask --classify /etc")).startswith("path\t/etc")
          # AI: no setup yet -> a hint; a cloud provider writes aichat's config (no network needed).
          machine.succeed(as_live("mos-ai 2>&1 | grep >/dev/null mos-ai-setup"))
          machine.succeed(as_live("printf 'test-key\\n' | mos-ai-setup grok >/dev/null"))
          machine.succeed(as_live("grep -q '^model: grok:grok-4' ~/.config/aichat/config.yaml"))
          # mos-ai-setup status: where questions go; the key itself never shown.
          machine.succeed(as_live("mos-ai-setup status >/tmp/ai.txt; grep -q 'API key set' /tmp/ai.txt && grep -q xAI /tmp/ai.txt && ! grep -q test-key /tmp/ai.txt"))
          machine.succeed(as_live("mos-ai-setup remove; test $? = 2"))
          machine.succeed(as_live("rm -rf ~/.config/aichat ~/.config/meccanicos/ai"))
          machine.succeed(as_live("mos-ask --apps | grep >/dev/null '^Installer'"))
          machine.send_key("meta_l-spc")
          machine.sleep(3)
          machine.screenshot("command-bar")
          machine.send_key("esc")
          machine.send_key("meta_l-slash")
          machine.sleep(3)
          machine.screenshot("cheat-sheet")
          machine.send_key("esc")

      with subtest("tools are present and offline-ready"):
          machine.fail("systemctl is-active ollama.service")  # installed, not started
          machine.succeed("systemctl start ollama.service")
          machine.wait_for_open_port(11434)
          machine.succeed("command -v aichat")
          assert machine.succeed("mos-gpu-driver").strip() == "open"  # QEMU: no NVIDIA GPU
          machine.fail("lsmod | grep >/dev/null '^nvidia'")
          machine.succeed("systemctl is-active systemd-modules-load.service")  # NVIDIA hooks skip cleanly
          machine.succeed("ollama list | wc -l | grep >/dev/null -x 1")  # header only: no model shipped
          machine.succeed(as_live("tldr --quiet tar | grep >/dev/null -i archive"))
          machine.succeed("test -L /home/live/Desktop/install-meccanicos.desktop")
          machine.succeed("test -s '/home/live/Desktop/Tutorial.mp4'")  # the video tour
          machine.succeed("command -v rigx pandoc typst codium rclone syncthing brave mos-install")
          # mos lists the commands; mos-config / mos-doctor: settings, checks, usage errors.
          machine.succeed(as_live("mos | grep >/dev/null mos-doctor"))
          machine.succeed(as_live("mos-config list | grep >/dev/null display.scale"))
          machine.succeed(as_live("mos-config list --json | python3 -c 'import json,sys; assert \"time.zone\" in json.load(sys.stdin)'"))
          machine.fail(as_live("mos-config list | grep >/dev/null security.ssh"))  # installed-only
          machine.succeed(as_live("mos-config set time.zone Europe/Rome"))
          machine.succeed(as_live("mos-config get time.zone | grep >/dev/null -x Europe/Rome"))
          machine.succeed(as_live("grep -q 'zone = \"Europe/Rome\"' ~/.config/meccanicos/settings.toml"))
          machine.succeed(as_live("mos-config set no.such 1; test $? = 2"))
          machine.succeed(as_live("mos-doctor --check --json | python3 -c 'import json,sys; json.load(sys.stdin)'"))
          machine.succeed(as_live("mos-doctor nowhere; test $? = 2"))
          # VSCodium installs its bundled extensions (offline, from .vsix) on first start.
          machine.succeed(as_live("codium --list-extensions | grep >/dev/null -x mkhl.direnv"))
          # apps --here: only app names go into .envrc (bash runs it).
          machine.succeed(as_live("apps install --here 'a;b'; test $? = 2"))
          # open: rules route by type; yazi is there with MeccanicOS's config.
          machine.succeed("printf 'a,b\\n1,2\\n' > /tmp/t.csv && open -n /tmp/t.csv | grep >/dev/null onlyoffice-desktopeditors")
          machine.succeed("open -n https://nixos.org | grep >/dev/null brave")
          machine.succeed("printf 'x\\n' > /tmp/t.txt && open -n /tmp/t.txt | grep >/dev/null 'term: jed'")
          machine.succeed("open -n /tmp | grep >/dev/null 'term: yazi'")
          machine.succeed("printf '<p>x</p>\\n' > /tmp/t.html && open -n /tmp/t.html | grep >/dev/null 'term: jed'")
          machine.succeed("grep -q 'text/html=mos-open.desktop' /etc/xdg/mimeapps.list && grep -q 'video/mp4=mos-open.desktop' /etc/xdg/mimeapps.list")
          machine.succeed("open --list | grep >/dev/null 'Spreadsheets'")
          # print: Save as PDF without the menu (text via typst); no printers in the VM.
          machine.succeed("printf 'print me\\n' > /tmp/p.txt && print --pdf /tmp/p.txt && file /tmp/p.pdf | grep >/dev/null PDF")
          machine.succeed("print -l | grep >/dev/null 'No printers'")
          machine.succeed(as_live("mos-printers list | grep >/dev/null 'No printers yet'"))
          # Logins: the watcher runs in the session; blocking an address works.
          machine.wait_until_succeeds("systemctl --user -M live@ is-active mos-logins.service", timeout=60)
          machine.succeed(as_live("mos-logins now | grep >/dev/null 'Nobody is connected'"))
          machine.succeed(as_live("mos-logins block 198.51.100.7 5 && mos-logins blocked | grep >/dev/null 198.51.100.7"))
          machine.succeed(as_live("mos-logins unblock 198.51.100.7"))
          machine.succeed(as_live("mos-printers queue | grep >/dev/null 'Nothing is waiting'"))
          machine.succeed("command -v yazi ya && grep -q 'ratio = \\[2, 3, 5\\]' /etc/xdg/yazi/yazi.toml")
          # Network status (no Wi-Fi in the VM), Updates, the graphics driver in System Info.
          machine.succeed(as_live("mos-config network --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert \"vpns\" in d and \"internet\" in d'"))
          machine.succeed(as_live("mos-config network nope; test $? = 2"))
          machine.succeed(as_live("mos-updates status | grep >/dev/null 'writing a newer ISO'"))
          machine.succeed("test -e /run/current-system/sw/share/applications/mos-updates.desktop")
          machine.succeed(as_live("mos-about </dev/null | grep >/dev/null 'Graphics.*mos-gpu-driver'"))
          # Help, offline: the page and the manual; `mos help TOPIC` without a desktop shows the manual.
          machine.succeed("test -s /run/current-system/sw/share/meccanicos/help/manual.html")
          machine.succeed("grep -q 'id=\"backups--mos-backup\"' /run/current-system/sw/share/meccanicos/help/manual.html")
          # (The test shell exports DISPLAY; without it, as over SSH, the text comes out.)
          machine.succeed(as_live("env -u DISPLAY mos help backups </dev/null | grep >/dev/null 'mos-backup browse'"))
          # Backups: restore only the chosen files, into a new folder; never over the home folder.
          machine.succeed(as_live("printf 'backup-pass-sixteen\\nbackup-pass-sixteen\\n' | mos-backup init /tmp/bk && echo keep-me > ~/bk-note.txt && mkdir -p ~/bk-dir && echo x > ~/bk-dir/x.txt && mos-backup now"))
          machine.succeed(as_live("mos-backup files | grep >/dev/null bk-note.txt"))
          machine.succeed(as_live("mos-backup restore latest /tmp/r1 --only bk-note.txt && grep -q keep-me /tmp/r1/home/live/bk-note.txt && ! test -e /tmp/r1/home/live/bk-dir"))
          machine.succeed(as_live("! mos-backup restore latest /tmp/r2 --only no-such-file && ! test -e /tmp/r2"))
          machine.succeed(as_live("! mos-backup restore latest /"))
          # Like Time Machine: versions of a file, put back next to it; nightly schedule; the timeline.
          machine.succeed(as_live("echo changed > ~/bk-note.txt && mos-backup versions ~/bk-note.txt | grep >/dev/null changed"))
          machine.succeed(as_live("mos-backup versions ~/bk-note.txt --restore latest && grep -q keep-me ~/bk-note\\ \\(*\\).txt && grep -q changed ~/bk-note.txt"))
          machine.succeed(as_live("mos-backup auto on && test -f ~/.config/meccanicos/backup.nightly && mos-backup status | grep >/dev/null 'Automatic:   nightly'"))
          machine.succeed("systemctl --user -M live@ is-active mos-backup.timer")
          machine.succeed(as_live("mos-backup auto off && ! test -e ~/.config/meccanicos/backup.nightly"))
          machine.succeed(as_live("mos-backup mount </dev/null; ls ~/Backups/snapshots | grep >/dev/null latest"))
          machine.succeed(as_live("mos-backup unmount && ! mountpoint -q ~/Backups"))
          machine.succeed(as_live("! mos-backup init nosuchremote:backup </dev/null"))
          # The desktop reaches user services (notifications, the "Use for backups?" terminal).
          machine.succeed("systemctl --user -M live@ show-environment | grep >/dev/null '^DISPLAY='")

      with subtest("usb-vault: vault + persistent home on the boot stick"):
          machine.succeed("printf 'YES\\nvault-pass-sixteen\\nvault-pass-sixteen\\n' | USB_VAULT_USER=live usb-vault create-partition --size 1G")
          machine.succeed("echo hello-vault > /home/live/Vault/proof.txt && USB_VAULT_USER=live usb-vault close")
          machine.succeed("printf 'YES\\nhome-pass-sixteen\\nhome-pass-sixteen\\n' | USB_VAULT_USER=live usb-vault create-home --size 1G")
          machine.succeed("USB_VAULT_USER=live usb-vault status | tee /dev/stderr | grep >/dev/null 'Home'")
          # What survives a restart: the home is made, but not in use until the next start.
          machine.succeed("USB_VAULT_USER=live usb-vault status | grep >/dev/null 'What survives a restart (live USB'")
          machine.succeed("usb-vault summary | grep >/dev/null 'persistent home not in use'")
          machine.succeed("usb-vault summary | grep >/dev/null 'Apps you installed : lost at shutdown'")

      machine.shutdown()

      with subtest("persistent home is unlocked at boot and keeps files"):
          machine = create_machine(start_command(usb), name="live2")
          machine.start()
          answer_password(machine, "home-pass-sixteen")
          machine.wait_for_unit("multi-user.target")
          machine.succeed("findmnt /home/live | grep >/dev/null mos-home")
          machine.succeed(as_live("echo i-persist > ~/persist.txt"))
          machine.succeed("usb-vault summary | grep >/dev/null 'Files and settings : kept, encrypted'")
          machine.succeed("printf 'vault-pass-sixteen\\n' | USB_VAULT_USER=live usb-vault open /dev/sda3 && grep -q hello-vault /home/live/Vault/proof.txt")
          machine.shutdown()

          machine = create_machine(start_command(usb), name="live3")
          machine.start()
          answer_password(machine, "home-pass-sixteen")
          machine.wait_for_unit("multi-user.target")
          machine.succeed("grep -q i-persist /home/live/persist.txt")
          machine.shutdown()
    '';
  };

  install = pkgs.testers.runNixOSTest {
    name = "mos-install";
    nodes = { };
    testScript = prelude + ''
      import json
      disk = qcow("disk.qcow2", "48G")
      hdd = f"-drive id=hd,file={disk},format=qcow2,if=virtio"

      machine = create_machine(start_command(usb, hdd), name="installer")
      machine.start()
      machine.wait_for_unit("multi-user.target")

      with subtest("installer runs unattended to completion"):
          answers = {
              "country": "Italy", "language": "English (United States)", "timezone": "Europe/Rome",
              "keyboard": "English (US)", "screen": "Landscape",
              "wifi": "", "wifi_security": "", "wifi_password": "",
              "fullname": "Test User", "username": "tester", "password": "user-pass-1",
              "luks_password": "luks-test-pass-sixteen", "disk": "/dev/vda", "disk_label": "vda test disk",
          }
          machine.succeed(f"echo {shlex.quote(json.dumps(answers))} > /tmp/answers.json")
          machine.succeed("mos-install --config /tmp/answers.json < /dev/null", timeout=3600)
          machine.succeed("lsblk -o NAME,PARTLABEL,FSTYPE /dev/vda | tee /dev/stderr | grep >/dev/null crypto_LUKS")
      machine.shutdown()

      with subtest("installed system boots with the disk password"):
          machine = create_machine(start_command(hdd), name="installed")
          machine.start()
          machine.wait_for_console_text("assphrase for")
          machine.send_console("luks-test-pass-sixteen\n")
          machine.wait_for_unit("multi-user.target")
          machine.wait_for_unit("display-manager.service")

      with subtest("user, sudo, SSH policy, settings"):
          machine.succeed("id tester | grep >/dev/null wheel")
          machine.succeed("su - tester -c 'sudo -n true'")                      # passwordless sudo
          machine.succeed("sshd -T | grep >/dev/null -i '^passwordauthentication no'")     # keys only
          # /tmp and nix builds on the disk, not in RAM (the live USB keeps them in RAM).
          machine.succeed("nix config show build-dir | grep >/dev/null -x /nix/var/nix/builds")
          machine.succeed("mkdir -p /nix/var/nix/builds && test \"$(stat -f -c %T /nix/var/nix/builds)\" != tmpfs")
          machine.succeed("test \"$(stat -f -c %T /tmp)\" != tmpfs")
          machine.succeed("sshd -T | grep >/dev/null -i '^permitrootlogin no'")
          machine.succeed("sshd -T | grep >/dev/null -i '^authenticationmethods publickey'")
          machine.succeed("sshd -T | grep >/dev/null -i '^kbdinteractiveauthentication no'")
          # The user's own key pair, made by the installer.
          machine.succeed("su - tester -c 'ssh-keygen -l -f ~/.ssh/id_ed25519' | grep >/dev/null ED25519")
          machine.succeed("stat -c '%U %a' /home/tester/.ssh /home/tester/.ssh/id_ed25519 | tr '\\n' ' ' | grep >/dev/null -x 'tester 700 tester 600 '")
          # mos-config writes system settings to /etc/nixos/meccanicos.toml (applied by the next rebuild).
          machine.succeed("su - tester -c 'mos-config set security.tcp_ports 8080,8443 --no-rebuild'")
          machine.succeed("grep -qx 'tcp_ports = \\[8080, 8443\\]' /etc/nixos/meccanicos.toml")
          machine.succeed("su - tester -c 'mos-config get security.tcp_ports' | grep >/dev/null -x 8080,8443")
          machine.succeed("rm /etc/nixos/meccanicos.toml")
          # firewall: SSH and mDNS only; no LAN-sync port, no mosh, no ping
          machine.succeed("iptables -S nixos-fw | grep >/dev/null -- '--dport 22 '")
          machine.fail("iptables -S nixos-fw | grep >/dev/null -- '17500'")
          machine.fail("iptables -S nixos-fw | grep >/dev/null -- '60000:61000'")
          machine.fail("iptables -S nixos-fw | grep >/dev/null -- 'icmp-type 8'")
          machine.succeed("grep -q 'LC_TIME=it_IT.UTF-8' /etc/locale.conf")
          machine.succeed("readlink /etc/localtime | grep >/dev/null Europe/Rome")
          machine.succeed("test -f /etc/nixos/flake.nix -a -f /etc/nixos/local.nix -a -f /etc/nixos/hardware-configuration.nix")
          machine.succeed("cryptsetup status cryptroot | grep >/dev/null LUKS2")
          machine.succeed("mos-unlock status")
          machine.succeed("systemctl list-timers | grep >/dev/null mos-auto-upgrade")
          # Updates: what can change and how to go back; what survives a restart.
          machine.succeed("mos-updates status | grep >/dev/null 'mos-update --check'")
          machine.succeed("mos-updates status | grep >/dev/null 'running'")
          machine.succeed("usb-vault summary | grep >/dev/null 'installed system'")
          machine.screenshot("installed-login")

      with subtest("hibernates and resumes through the encrypted disk"):
          machine.wait_for_unit("mos-swapfile.service")
          machine.succeed("grep -q '^/var/lib/swap/hibernate ' /proc/swaps")
          machine.succeed("busctl call org.freedesktop.login1 /org/freedesktop/login1 org.freedesktop.login1.Manager CanHibernate | grep >/dev/null yes")
          for key, action in [("HandleLidSwitch", "suspend"), ("HandleLidSwitchExternalPower", "suspend"),
                              ("HandleLidSwitchDocked", "ignore")]:  # external screen: keep working
              machine.succeed(f"busctl get-property org.freedesktop.login1 /org/freedesktop/login1 org.freedesktop.login1.Manager {key} | grep >/dev/null {action}")
          machine.succeed("mos-unlock status | grep >/dev/null 'Remote unlock: off'")
          machine.succeed("systemctl is-active mos-coredump-cleanup.path")
          machine.succeed("grep -q 'logind-handle-lid-switch.*value=\"true\".*locked' /etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xfce4-power-manager.xml")
          machine.succeed("echo 'kept in RAM only' > /dev/shm/hibernate-marker")
          machine.execute("systemctl hibernate >&2 &", check_return=False)
          machine.wait_for_shutdown()
          machine.start()
          machine.wait_for_console_text("assphrase for")
          machine.send_console("luks-test-pass-sixteen\n")
          machine.wait_for_unit("multi-user.target")
          machine.succeed("grep -q 'kept in RAM only' /dev/shm/hibernate-marker")  # resumed, not rebooted
      machine.shutdown()
    '';
  };

  # The ISO as a file on a Ventoy stick: Ventoy holds the stick's partition,
  # usb-vault still mounts it, keeps vaults and the persistent home as files.
  ventoy = pkgs.testers.runNixOSTest {
    name = "mos-ventoy";
    nodes.maker = {
      environment.systemPackages = [ ventoy ];
      virtualisation.emptyDiskImages = [ 12288 ]; # MiB: becomes the Ventoy stick
      virtualisation.memorySize = 2048;
    };
    testScript = prelude + ''
      import json

      with subtest("make a Ventoy stick holding the MeccanicOS ISO file"):
          maker.start()
          maker.wait_for_unit("multi-user.target")
          maker.succeed("{ yes y || true; } | ventoy -I /dev/vdb >&2")
          maker.succeed("udevadm settle; mkdir -p /mnt && mount /dev/vdb1 /mnt")
          maker.succeed("cp ${iso} /mnt/meccanicos.iso")
          # Boot the ISO straight away: no menu, no "normal mode" question.
          control = {"control": [
              {"VTOY_DEFAULT_IMAGE": "/meccanicos.iso"},
              {"VTOY_MENU_TIMEOUT": "1"},
              {"VTOY_SECONDARY_BOOT_MENU": "0"},
          ]}
          maker.succeed(f"mkdir -p /mnt/ventoy && echo {shlex.quote(json.dumps(control))} > /mnt/ventoy/ventoy.json")
          maker.succeed("sync && umount /mnt")
          maker.shutdown()
      stick_img = os.path.join(maker.state_dir, "empty0.qcow2")
      stick = f"-drive id=vstick,file={stick_img},format=qcow2,if=none -device usb-storage,drive=vstick,removable=on"

      with subtest("boots through Ventoy; the stick's partition is mountable"):
          machine = create_machine(start_command(stick), name="ventoy")
          machine.start()
          machine.wait_for_unit("multi-user.target", timeout=1200)
          machine.succeed("test -e /dev/mapper/ventoy")
          machine.fail("mount /dev/sda1 /mnt")  # Ventoy holds it: the old problem
          machine.succeed("USB_VAULT_USER=live usb-vault status | tee /dev/stderr | grep >/dev/null 'booted through Ventoy'")
          machine.succeed("USB_VAULT_USER=live usb-vault stick && test -f /run/usb-vault/data/meccanicos.iso")

      with subtest("vault and persistent home as files on the Ventoy partition"):
          machine.succeed("printf 'vault-pass-sixteen\\nvault-pass-sixteen\\n' | USB_VAULT_USER=live usb-vault create-file --size 64M --name test.luks")
          machine.succeed("echo hello-ventoy > /home/live/Vault-test/proof.txt && USB_VAULT_USER=live usb-vault close")
          machine.succeed("test -f /run/usb-vault/data/meccanicos/test.luks || (USB_VAULT_USER=live usb-vault stick && test -f /run/usb-vault/data/meccanicos/test.luks)")
          machine.fail("printf 'YES\\n' | USB_VAULT_USER=live usb-vault create-partition")  # partitions are refused on Ventoy
          machine.succeed("printf 'YES\\nhome-pass-sixteen\\nhome-pass-sixteen\\n' | USB_VAULT_USER=live usb-vault create-home --size 512M")
          machine.succeed("USB_VAULT_USER=live usb-vault status | tee /dev/stderr | grep >/dev/null 'meccanicos/mos-home.luks'")
          machine.shutdown()

      with subtest("persistent home unlocks at boot from the Ventoy partition"):
          machine = create_machine(start_command(stick), name="ventoy2")
          machine.start()
          # What the screen shows while it waits for the password.
          machine.wait_until_succeeds("ls /run/systemd/ask-password/ask.* >/dev/null 2>&1", timeout=900)
          machine.sleep(5)
          machine.screenshot("ventoy-home-prompt")
          answer_password(machine, "home-pass-sixteen")
          machine.wait_for_unit("multi-user.target")
          machine.succeed("findmnt /home/live | grep >/dev/null mos-home")
          machine.succeed("printf 'vault-pass-sixteen\\n' | USB_VAULT_USER=live usb-vault open test.luks && grep -q hello-ventoy /home/live/Vault-test/proof.txt")
          machine.shutdown()
    '';
  };

  # Not a test: screenshots of each mos-* tool for the web page (www/),
  # taken in the live system as in the tutorial (VictorMono, 1920x1080).
  #   nix build .#www-screenshots && cp result/screenshots/*.png www/screenshots/
  # (./start www does both.) Left out of `nix flake check`.
  screenshots = pkgs.testers.runNixOSTest {
    name = "mos-screenshots";
    nodes = { };
    testScript = prelude + ''
      import base64
      machine = create_machine(start_command(usb, memory=6144), name="live")
      machine.start()
      machine.wait_until_succeeds("pgrep -u live xfce4-panel", timeout=600)
      machine.wait_for_x()
      machine.sleep(15)

      # The desktop session's environment, for commands run from the test shell.
      env = machine.succeed(
          "tr '\\0' '\\n' </proc/$(pgrep -u live -o xfce4-panel)/environ"
          " | grep -E '^(DISPLAY|XAUTHORITY|DBUS_SESSION_BUS_ADDRESS|XDG_RUNTIME_DIR)='"
      ).split()
      ENV = "export " + " ".join(shlex.quote(e) for e in env) + "; "

      def x(cmd, check=True):
          run = machine.succeed if check else machine.execute
          return run(as_live(ENV + cmd))

      x("xrandr -s 1920x1080 || true")
      x("xfconf-query -c xfce4-terminal -p /font-name -n -t string -s 'VictorMono Nerd Font 14'")
      x("xfconf-query -c xfce4-terminal -p /misc-cursor-blinks -n -t bool -s false")
      machine.succeed("mkdir -p /tmp/shots && chmod 777 /tmp/shots")
      # For the web page: memory in use on the idle desktop, a minute after login.
      machine.sleep(60)
      machine.succeed("free -m >/tmp/shots/idle-memory.txt")
      machine.sleep(3)

      # Never fatal, never waiting forever: a missing window only loses its picture.
      def find(args):
          return x(f"timeout 30 xdotool search --sync --onlyvisible {args} | head -n1", check=False)[1].strip()

      def shot(name, wid):
          if not wid:
              print(f"!!! no window for {name}")
              return
          x(f"import -frame -window {wid} /tmp/shots/{name}.png", check=False)

      n = [0]

      # Every tool's screenshot is the same size: one terminal size for all.
      SIZE = "110x36"

      # A terminal window, found by a class of its own (programs change titles).
      def term(title, cmd=None, geometry=SIZE, font=None):
          n[0] += 1
          cls = f"shot{n[0]}"
          run = f"-x {cmd}" if cmd else ""
          fnt = f"--font {shlex.quote(font)}" if font else ""
          x(f"setsid xfce4-terminal --disable-server --class {cls} --title {shlex.quote(title)} --geometry {geometry} {fnt} {run} >/dev/null 2>&1 &")
          wid = find(f"--class '^{cls}$'")
          if wid:
              x(f"timeout 10 xdotool windowactivate --sync {wid}", check=False)
          machine.sleep(2)
          return wid

      def typed(text):
          x(f"xdotool type --delay 25 {shlex.quote(text)}", check=False)
          x("xdotool key Return", check=False)

      def close(wid):
          if wid:
              x(f"xdotool windowkill {wid}", check=False)
          machine.sleep(1)

      # A command typed at the prompt, as in the tutorial.
      def command(name, cmd, wait=3, geometry=SIZE):
          wid = term("Terminal", geometry=geometry)
          typed(cmd)
          machine.sleep(wait)
          shot(name, wid)
          close(wid)

      # A full-screen tool, in a window of its own as its launcher opens it.
      def tool(name, title, cmd, geometry=SIZE, keys=(), wait=4):
          wid = term(title, cmd, geometry)
          machine.sleep(wait)
          for k in keys:
              x(f"xdotool key {k}", check=False)
              machine.sleep(1)
          shot(name, wid)
          close(wid)

      # Something to show: two printers (one paused, with two jobs waiting),
      # login history (an SSH key login and attempts on the SSH port), a file
      # to read aloud. Nothing leaves the VM.
      machine.execute("lpadmin -p Office_Laser -E -v socket://192.0.2.10:9100 -m raw -D 'Office laser' -L '2nd floor'")
      machine.execute("lpadmin -p Kitchen_Inkjet -E -v socket://192.0.2.11:9100 -m raw -D 'Kitchen inkjet' -L Kitchen")
      machine.execute("lpadmin -d Office_Laser && cupsdisable Kitchen_Inkjet")
      x("printf 'Quarterly report\\n' >/tmp/report.txt && lp -d Kitchen_Inkjet -t report.pdf /tmp/report.txt && lp -d Kitchen_Inkjet -t photo.png /tmp/report.txt", check=False)
      machine.execute("systemctl --user -M live@ stop mos-logins.service")
      machine.execute("logger -p authpriv.info -t sshd 'Accepted publickey for live from 192.168.1.20 port 50122 ssh2: ED25519 SHA256:q3Vb1aKx'")
      for ip, user in (("203.0.113.45", "root"), ("203.0.113.45", "admin"), ("198.51.100.23", "oracle"), ("203.0.113.45", "root")):
          machine.execute(f"logger -p authpriv.info -t sshd 'Failed password for {user} from {ip} port 51234 ssh2'")
      x("printf '%s\\n' 'Welcome to MeccanicOS. Copy any text, and MeccanicOS can read it aloud with an offline voice.' 'Space pauses, the arrows skip a sentence.' >~/notes.txt")

      # The command bar and the shortcuts (rofi).
      machine.send_key("meta_l-spc")
      machine.sleep(3)
      x("xdotool type --delay 80 fil", check=False)
      machine.sleep(2)
      shot("mos-ask", find("--class rofi"))
      machine.send_key("esc")
      machine.sleep(1)
      x("setsid mos-keys >/dev/null 2>&1 &")
      machine.sleep(3)
      shot("mos-keys", find("--class rofi"))
      machine.send_key("esc")
      machine.sleep(1)

      # A backup to restore from, an online AI set up (a made-up key: nothing is sent),
      # and mos-unlock (installed systems only) for its help.
      x("printf 'backup-pass-sixteen\\nbackup-pass-sixteen\\n' | mos-backup init /tmp/backup && mos-backup now >/dev/null", check=False)
      x("printf 'demo-key\\n' | mos-ai-setup grok >/dev/null", check=False)
      unlock = base64.b64encode(open("${../scripts/mos-unlock.sh}", "rb").read()).decode()
      machine.succeed(f"echo {unlock} | base64 -d >/home/live/.mos-unlock && chown live:users /home/live/.mos-unlock")
      x("echo \"alias mos-unlock='bash ~/.mos-unlock'\" >>~/.bashrc")

      tool("mos-config", "Configuration Management", "mos-config")
      tool("mos-updates", "Updates", "mos-updates")
      tool("mos-backup", "Restore from backup", "mos-backup browse", keys=("Return",))
      tool("mos-apps", "Apps Manager", "apps manage")
      tool("mos-printers", "Printers", "mos-printers")
      # The same in Chinese, for the web page's languages line (i18n/).
      tool("mos-printers-zh", "Printers", "env LANGUAGE=zh_CN mos-printers")
      tool("mos-logins", "Logins", "mos-logins", keys=("h",))
      tool("mos-vault", "USB Vault", "usb-vault menu")
      tool("mos-install", "Install MeccanicOS", "mos-install")
      tool("mos-read", "Read from clipboard", "mos-read /home/live/notes.txt", wait=6)

      command("mos", "mos")
      command("mos-doctor", "mos-doctor --check", wait=15)
      command("mos-open", "open --list | head -n 22")
      command("mos-about", "mos-about", wait=4)
      command("mos-ai", "mos-ai")
      command("mos-ai-setup", "mos-ai-setup status", wait=6)
      command("mos-unlock", "mos-unlock --help")
      command("mos-dropbox", "mos-dropbox --help")
      command("mos-passwords", "mos-passwords --help")
      command("mos-screenshot", "mos-screenshot --help")

      # print: its menu, then Esc.
      wid = term("Terminal")
      typed("print ~/notes.txt")
      machine.sleep(3)
      shot("mos-print", wid)
      x("xdotool key Escape", check=False)
      close(wid)

      # The whole screen, for the top of the page: a spreadsheet, btop, and
      # yazi showing a picture.
      # The sample picture and video, sent in pieces through the test shell
      # (this VM has no shared folder).
      def send(src, dest):
          data = base64.b64encode(open(src, "rb").read()).decode()
          machine.succeed("rm -f /tmp/send.b64")
          for i in range(0, len(data), 60000):
              machine.succeed(f"printf %s {data[i:i + 60000]} >>/tmp/send.b64")
          machine.succeed(f"base64 -d /tmp/send.b64 >{dest} && rm /tmp/send.b64")

      machine.succeed("mkdir -p /home/live/Pictures")
      send("${../branding/samples/example.png}", "/home/live/Pictures/earth-at-night.png")
      send("${../branding/samples/example.mp4}", "/home/live/Pictures/earth-at-night.mp4")
      machine.succeed("cp /home/live/notes.txt /home/live/Pictures/ && chown -R live:users /home/live/Pictures")
      x("printf '%s\\n' 'Month,Visitors,Downloads,Stars' 'January,1200,340,85' 'February,1850,520,130'"
        " 'March,2600,810,210' 'April,3900,1240,330' 'May,5200,1730,470' 'June,7400,2380,640' >~/Pictures/growth.csv")
      x("setsid onlyoffice-desktopeditors /home/live/Pictures/growth.csv >/dev/null 2>&1 &")
      sheet = find("--class ONLYOFFICE")
      machine.sleep(12)
      x("xdotool key Return", check=False)  # the CSV import dialog: OK
      machine.sleep(6)
      x("xdotool key Escape", check=False)  # OnlyOffice's "New: ..." tip
      machine.sleep(1)
      small = "VictorMono Nerd Font 10"
      btop = term("btop", "btop", "100x30", font=small)
      files = term("yazi", "yazi /home/live/Pictures", "100x30", font=small)
      # OnlyOffice's "New: ..." tip: its "Got it" button (where it is in this
      # window size), then the mouse out of the way.
      x(f"xdotool windowsize {sheet} 1060 1030 windowmove {sheet} 10 40", check=False)
      machine.sleep(2)
      x("xdotool mousemove 695 482 click 1 sleep 1 mousemove 1500 1075", check=False)
      machine.sleep(2)
      # The spreadsheet on the left, btop and yazi wide on the right.
      x(f"xdotool windowsize {sheet} 530 1030 windowmove {sheet} 10 40", check=False)
      x(f"xdotool windowsize {btop} 1360 530 windowmove {btop} 550 40", check=False)
      x(f"xdotool windowsize {files} 1360 490 windowmove {files} 550 580", check=False)
      machine.sleep(3)
      x(f"timeout 10 xdotool windowactivate --sync {files}", check=False)
      # Down to the picture (the files are sorted: earth-at-night.mp4, .png, ...).
      x("xdotool key j", check=False)
      machine.sleep(4)
      # ...and the command bar, while "terminal" is typed.
      machine.send_key("meta_l-spc")
      machine.sleep(3)
      x("xdotool type --delay 80 terminal", check=False)
      machine.sleep(2)
      x("import -window root /tmp/shots/desktop.png")
      machine.send_key("esc")

      # The windows that are not terminals (command bar, shortcuts): shrunk
      # if larger, then centred on the page's frame colour, at the terminals' size.
      size = x("magick identify -format %wx%h /tmp/shots/mos-config.png", check=False)[1].strip()
      if size:
          for name in ("mos-ask", "mos-keys"):
              x(f"magick /tmp/shots/{name}.png -resize '{size}>' -background '#15191a' -gravity center -extent {size} /tmp/shots/{name}.png", check=False)

      # Back to the host the same way: no shared folder.
      outdir = os.path.join(str(machine.out_dir), "screenshots")
      os.makedirs(outdir, exist_ok=True)
      for name in machine.succeed("ls /tmp/shots").split():
          data = machine.succeed(f"base64 -w0 /tmp/shots/{name}")
          with open(os.path.join(outdir, name), "wb") as f:
              f.write(base64.b64decode(data))
      machine.shutdown()
    '';
  };
}
