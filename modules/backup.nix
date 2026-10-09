# mos-backup: encrypted, incremental backups of your home folder (restic),
# to an external disk, the USB vault, a Dropbox folder or the cloud (rclone).
# Like Time Machine: nightly (`mos-backup auto on`) or hourly, per user; when
# the backup disk is plugged in; old backups thinned; versions of a file from
# Files (right-click) or yazi (B); every backup as a folder (`mos-backup mount`).
{ lib, pkgs, ... }:
let
  inherit (import ./not-root.nix) notRoot;
  tSh = import ./i18n-sh.nix pkgs;
  mos-backup = pkgs.writeShellApplication {
    name = "mos-backup";
    runtimeInputs = with pkgs; [
      restic
      rclone # cloud backups: restic runs `rclone serve restic`
      libnotify
      coreutils
      hostname
      systemd
      util-linux # flock, findmnt, lsblk, mountpoint, setsid
      gawk
      gnugrep
      gnused
      # not fuse3: restic mount needs the setuid fusermount3 in /run/wrappers/bin
    ];
    # `mos-backup browse` (and `restore` in a terminal) is scripts/mos-backup-restore.py.
    text = tSh "mos-backup" + notRoot "mos-backup" + ''
      export MECCANICOS_PYLIB=${../scripts/lib}
      export MOS_BACKUP_PYTHON=${pkgs.python3}/bin/python3
      export MOS_BACKUP_BROWSE=${../scripts/mos-backup-restore.py}
    ''
    + builtins.readFile ../scripts/mos-backup.sh;
  };
  restoreLauncher = pkgs.makeDesktopItem {
    name = "mos-backup-restore";
    desktopName = "Restore Files from a Backup (mos-backup)";
    comment = "Pick a backup, browse it and get files or folders back into ~/Restored-<date>";
    icon = "document-revert";
    exec = ''xfce4-terminal --title "Restore from backup" --geometry 110x32 -x mos-backup browse'';
    keywords = [
      "backup"
      "restore"
      "recover"
      "undelete"
      "snapshot"
      "restic"
    ];
    categories = [ "System" ];
  };
in
{
  environment.systemPackages = [
    mos-backup
    restoreLauncher
  ];

  # restic mount (mos-backup mount); on by default in NixOS, needed here.
  programs.fuse.enable = lib.mkDefault true;

  # Automatic backups: the timers are always there but only run while the
  # user's choice is on file (mos-backup auto writes backup.nightly or
  # backup.hourly), so it survives restarts without `systemctl enable`.
  systemd.user.services.mos-backup = {
    description = "MeccanicOS home backup";
    unitConfig.ConditionPathExists = "%h/.config/meccanicos/backup.env";
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${mos-backup}/bin/mos-backup now --auto";
      Nice = 15;
      IOSchedulingClass = "idle";
      SuccessExitStatus = "3"; # destination not plugged in: try again next time
    };
  };
  systemd.user.timers.mos-backup = {
    description = "Nightly MeccanicOS home backup";
    wantedBy = [ "timers.target" ];
    unitConfig.ConditionPathExists = "%h/.config/meccanicos/backup.nightly";
    timerConfig = {
      OnCalendar = "*-*-* 02:30:00";
      Persistent = true; # asleep or off at 02:30: at the next start or wake
      RandomizedDelaySec = "10min";
    };
  };
  systemd.user.timers.mos-backup-hourly = {
    description = "Hourly MeccanicOS home backup";
    wantedBy = [ "timers.target" ];
    unitConfig.ConditionPathExists = "%h/.config/meccanicos/backup.hourly";
    timerConfig = {
      OnCalendar = "hourly";
      Persistent = true;
      RandomizedDelaySec = "5min";
      Unit = "mos-backup.service";
    };
  };

  # A disk mounted under /run/media/<user> (udisks, as Files does it): back up
  # to it if it is the backup disk and the last backup is over 12 h old, or,
  # with no backup set up, offer a new USB disk once (mos-backup plugged).
  systemd.user.paths.mos-backup-plugged = {
    description = "Watch for the backup disk";
    wantedBy = [ "default.target" ];
    pathConfig.PathChanged = "/run/media/%u";
  };
  systemd.user.services.mos-backup-plugged = {
    description = "Back up to the disk just plugged in";
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${mos-backup}/bin/mos-backup plugged";
      Nice = 15;
      IOSchedulingClass = "idle";
      SuccessExitStatus = "3";
    };
  };
}
