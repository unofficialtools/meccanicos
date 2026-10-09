# mos-dropbox: Dropbox without the Dropbox app, through rclone (free
# software). Mount it live, or keep a two-way synced copy in ~/Dropbox.
# See scripts/mos-dropbox.sh.
{ pkgs, ... }:
let
  inherit (import ./not-root.nix) notRoot;
  tSh = import ./i18n-sh.nix pkgs;
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
    text = tSh "mos-dropbox" + notRoot "mos-dropbox" + builtins.readFile ../scripts/mos-dropbox.sh;
  };
in
{
  environment.systemPackages = [ mos-dropbox ];

  # Two-way sync every 5 minutes for users who ran `mos-dropbox sync`
  # (and haven't paused it); for everyone else it exits at once.
  systemd.user.services.mos-dropbox-sync = {
    description = "Sync ~/Dropbox (mos-dropbox)";
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${mos-dropbox}/bin/mos-dropbox tick";
      Nice = 10;
    };
  };
  systemd.user.timers.mos-dropbox-sync = {
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnStartupSec = "2min";
      OnUnitActiveSec = "5min";
    };
  };
}
