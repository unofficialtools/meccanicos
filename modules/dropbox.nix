# mos-dropbox: Dropbox without the Dropbox app, through rclone (free
# software). Mount it live, or keep a two-way synced copy in ~/Dropbox.
# See scripts/mos-dropbox.sh.
{ pkgs, ... }:
let
  inherit (import ./not-root.nix) notRoot;
  mos-dropbox = pkgs.writeShellApplication {
    name = "mos-dropbox";
    runtimeInputs = with pkgs; [
      rclone
      coreutils
      util-linux # mountpoint, flock
      gnugrep
      gnused
      systemd # journalctl
      # fusermount3 is the setuid wrapper in /run/wrappers/bin (already on PATH)
    ];
    text = notRoot "mos-dropbox" + builtins.readFile ../scripts/mos-dropbox.sh;
  };
in
{
  environment.systemPackages = [ mos-dropbox ];

  # Two-way sync every 5 minutes, only for users who ran `mos-dropbox sync`:
  # the timer is not wanted by default; `mos-dropbox sync`/`resume` enable it
  # per user and `pause`/`logout` disable it again. `tick` syncs the folder
  # that `mos-dropbox sync` remembered (~/.config/mos-dropbox/folder), so a
  # MECCANICOS_DROPBOX_DIR given by hand is used here too.
  systemd.user.services.mos-dropbox-sync = {
    description = "Sync the Dropbox folder (mos-dropbox)";
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${mos-dropbox}/bin/mos-dropbox tick";
      Nice = 10;
    };
  };
  systemd.user.timers.mos-dropbox-sync = {
    timerConfig = {
      OnStartupSec = "2min";
      OnUnitActiveSec = "5min";
    };
  };
}
