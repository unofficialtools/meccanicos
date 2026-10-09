# logins: who logged in, who tried, and what to do about it
# (scripts/mos-logins.py). A watcher in every desktop session alerts on an
# SSH login from somewhere new and on SSH attacks aimed at you, and sums up
# wrong passwords (lock screen, login, sudo, the disk at start-up) when you
# are back; never more than a few alerts an hour. "Logins" in the command
# bar shows who is connected and the history; "Disconnect" (also
# Super+Shift+Esc) ends remote sessions, stops SSH, cuts every network and
# locks the screen; "Reconnect" undoes it. sshguard blocks addresses that
# keep failing at SSH by itself.
{
  config,
  lib,
  pkgs,
  ...
}:
let
  inherit (import ./not-root.nix) notRoot';
  tSh = import ./i18n-sh.nix pkgs;
  mos-logins = pkgs.writeShellScriptBin "mos-logins" ''
    ${tSh "mos-logins"}
    ${notRoot' "mos-logins" [ "root" "watch" ]}
    export MECCANICOS_PYLIB=${../scripts/lib}
    export MECCANICOS_LOGINS_SELF=/run/current-system/sw/bin/mos-logins
    export PATH="${
      lib.makeBinPath (
        with pkgs;
        [
          systemd # journalctl, loginctl, systemctl
          libnotify # notify-send
          dbus # dbus-monitor
          glib # gdbus (demo: closes its alert)
          nftables
          iproute2 # ss
          util-linux # rfkill
          networkmanager # nmcli
        ]
      )
    }:$PATH"
    exec ${pkgs.python3}/bin/python3 ${../scripts/mos-logins.py} "$@"
  '';
  entry =
    {
      id,
      name,
      comment,
      icon,
      exec,
    }:
    pkgs.makeDesktopItem {
      name = id;
      desktopName = name;
      inherit comment icon exec;
      categories = [ "System" ];
    };
in
{
  environment.systemPackages = [
    mos-logins
    (entry {
      id = "mos-logins";
      name = "Logins (mos-logins)";
      comment = "Who is connected, who logged in and who tried; block, stop SSH, disconnect";
      icon = "security-high";
      exec = ''xfce4-terminal --title "Logins" --geometry 110x30 -x mos-logins'';
    })
    (entry {
      id = "mos-disconnect";
      name = "Disconnect (end remote sessions, networks off)";
      comment = "Panic button: end remote sessions, stop SSH, turn every network off, lock the screen";
      icon = "network-offline";
      exec = "mos-logins disconnect";
    })
    (entry {
      id = "mos-reconnect";
      name = "Reconnect (networks back on)";
      comment = "Undo Disconnect: networks back, and SSH if it was on";
      icon = "network-transmit-receive";
      exec = "mos-logins reconnect";
    })
  ];

  # The watcher: in every graphical session, restarted if it ever stops.
  systemd.user.services.mos-logins = {
    description = "Login alerts (mos-logins watch)";
    wantedBy = [ "graphical-session.target" ];
    partOf = [ "graphical-session.target" ];
    after = [ "graphical-session.target" ];
    serviceConfig = {
      ExecStart = "${mos-logins}/bin/mos-logins watch";
      Restart = "always";
      RestartSec = 30;
    };
  };

  # Addresses that keep failing at SSH are blocked for a while (longer each
  # time); only where SSH runs (installed systems, unless turned off).
  services.sshguard.enable = config.services.openssh.enable;
}
