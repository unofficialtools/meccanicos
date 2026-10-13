# The fleet server (EXPERIMENTAL): one account, `fleet`, reached over SSH,
# and two SQLite databases. No web services. On by itself when
# /etc/nixos/fleet-server.toml exists (`sudo mos-fleet server init` writes it).
#
#   ssh fleet@SERVER    sshd asks mos-fleet-keys who each key belongs to:
#                       a computer (its host key, in the repository), an admin
#                       (fleet-admins), a computer being installed (a one-time
#                       key from the stick). Each gets a forced command,
#                       mos-fleet-serve, and nothing else: no shell, no forwarding.
#   fleet.git           the fleet repository, the source of truth; admins push
#                       to it (its hooks refuse anything invalid). The server
#                       only reads it.
#   mos-fleet-build     builds every computer's system from the branch it
#                       follows; computers fetch theirs over SSH.
#   state.db            what computers report (facts, logs, deployments, jobs),
#                       and an audit log
#   secrets.db          password hashes, disk recovery keys (encrypted for the admins)
#   Tang                automatic disk unlocking, office network only (port 7654)
#
# Everything lives in /var/lib/mos-fleet (and /var/lib/tang): back them up,
# with `mos-fleet server backup DIR`.
#
# fleet-server.toml:
#   lan = ["10.0.0.0/24"]       # who may reach Tang
#
# On every installed system: the mos-fleet command, and /etc/mos-fleet/config.toml
# (meccanicos.fleet.config: mos-fleet's settings, see scripts/mos_fleet/defaults.toml).
{
  config,
  lib,
  pkgs,
  meccanicosRoot,
  ...
}:
let
  cfg = config.meccanicos.fleetServer;
  file = meccanicosRoot + "/fleet-server.toml";
  s = if builtins.pathExists file then builtins.fromTOML (builtins.readFile file) else { };
  mos-fleet = pkgs.callPackage ./mos-fleet-package.nix { };
  state = "/var/lib/mos-fleet";
  serverDefaults = (builtins.fromTOML (builtins.readFile ../scripts/mos_fleet/defaults.toml)).server;
in
{
  imports = [ ./fleet-config.nix ];

  options.meccanicos.fleetServer = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default = builtins.pathExists file;
      description = "The fleet server (on when /etc/nixos/fleet-server.toml exists).";
    };
    lan = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = s.lan or serverDefaults.lan;
      description = "Networks whose computers may reach Tang (automatic disk unlocking).";
    };
  };
  config = lib.mkMerge [
    { environment.systemPackages = [ mos-fleet ]; }

    (lib.mkIf cfg.enable {
      environment.etc."meccanicos/fleet-server".text = ''
        state=${state}
      '';

      users.users.fleet = {
        isSystemUser = true;
        group = "fleet";
        home = state;
        createHome = true;
        homeMode = "700";
        # sshd runs forced commands through the login shell.
        shell = pkgs.bashInteractive;
        description = "MeccanicOS fleet server";
      };
      users.groups.fleet = { };

      # Only keys, only through mos-fleet-keys, only forced commands.
      services.openssh.extraConfig = lib.mkAfter ''
        Match User fleet
          AuthorizedKeysFile none
          AuthorizedKeysCommand /etc/ssh/mos-fleet-keys %u %t %k
          AuthorizedKeysCommandUser fleet
          AuthenticationMethods publickey
          PasswordAuthentication no
          KbdInteractiveAuthentication no
          PermitTTY no
          AllowTcpForwarding no
          AllowStreamLocalForwarding no
          AllowAgentForwarding no
          X11Forwarding no
          PermitTunnel no
          PermitUserRC no
          ClientAliveInterval 30
          ClientAliveCountMax 3
      '';
      services.openssh.enable = true;
      # sshd wants the command, and every folder above it, root's alone: a
      # copy in /etc (/nix/store is writable by the nixbld group).
      environment.etc."ssh/mos-fleet-keys" = {
        mode = "0555";
        text = ''
          #!/bin/sh
          exec ${mos-fleet}/bin/mos-fleet-keys "$@"
        '';
      };
      networking.firewall.allowedTCPPorts = [ 7654 ];

      # The repository, its hooks, the databases (as fleet, at boot).
      systemd.services.mos-fleet-setup = {
        description = "Fleet server: repository and databases";
        wantedBy = [ "multi-user.target" ];
        before = [ "sshd.service" ];
        path = [ pkgs.git ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          User = "fleet";
          Group = "fleet";
          ExecStart = "${mos-fleet}/bin/mos-fleet-server setup";
        };
      };

      # Every computer's system, after every push (and every 10 minutes).
      systemd.services.mos-fleet-build = {
        description = "Fleet server: build the computers' systems";
        after = [
          "mos-fleet-setup.service"
          "network-online.target"
        ];
        wants = [ "network-online.target" ];
        path = [
          pkgs.git
          config.nix.package
        ];
        serviceConfig = {
          Type = "oneshot";
          User = "fleet";
          Group = "fleet";
          ExecStart = "${mos-fleet}/bin/mos-fleet-server build";
          Nice = 10;
          # A computer that fails to build is recorded, not an error; this is
          # for crashes (a full disk, the daemon away).
          Restart = "on-failure";
          RestartSec = 30;
        };
      };
      systemd.paths.mos-fleet-build = {
        wantedBy = [ "multi-user.target" ];
        pathConfig.PathChanged = "${state}/build.trigger";
      };
      systemd.timers.mos-fleet-build = {
        wantedBy = [ "timers.target" ];
        timerConfig = {
          OnBootSec = "2min";
          OnUnitActiveSec = "10min";
        };
      };

      systemd.services.mos-fleet-prune = {
        description = "Fleet server: drop old logs and reports";
        serviceConfig = {
          Type = "oneshot";
          User = "fleet";
          Group = "fleet";
          ExecStart = "${mos-fleet}/bin/mos-fleet-server prune";
        };
      };
      systemd.timers.mos-fleet-prune = {
        wantedBy = [ "timers.target" ];
        timerConfig = {
          OnCalendar = "daily";
          Persistent = true;
        };
      };

      # Builds run as fleet: an ordinary Nix user (the daemon builds), not trusted.

      # ---- Tang: automatic disk unlock, office network only --------------------
      services.tang = {
        enable = true;
        ipAddressAllow = cfg.lan ++ [
          "127.0.0.0/8" # mos-fleet (tang-show-keys)
          "::1/128"
        ];
      };
    })
  ];
}
