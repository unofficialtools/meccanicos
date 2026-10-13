# Managed mode (EXPERIMENTAL): a computer of an organization's fleet.
#
# Two stages:
#   just installed  /etc/nixos/fleet.toml (written by the installer from the
#                   stick's corporate.config) turns this on: the agent
#                   introduces the computer to the fleet server, once, and
#                   waits for an admin to add it to the fleet repository.
#                   Nobody can log in yet.
#   in the fleet    the fleet server builds this computer's system from the
#                   repository (meccanicos.lib.mkFleet sets the options
#                   below, `final`), and the agent switches to it: its people,
#                   its profile, the organization's settings.
#
# The agent (mos-fleet-agent) keeps one SSH connection to the server, with
# this computer's SSH host key; the server's key is pinned. People's
# passwords come from the server as hashes (/var/lib/mos-fleet/passwords,
# hashedPasswordFile); mos-passwd changes one's own, everywhere.
#
# fleet.toml (just installed):
#   organization = "Example Corp"
#   hostname = "ws-001"
#   profile = "office"
#   server = "hq.corp.example.com"          # [:PORT]
#   server_host_key = "ssh-ed25519 AAAA…"
#   [unlock] method = "tang" | "tpm-pin" | "fido2" | "password"
#            (tang: tang_url, tang_thumbprint; the sealed key in
#             /etc/secrets/meccanicos/cryptroot.jwe)
{
  config,
  options,
  lib,
  pkgs,
  meccanicosRoot,
  ...
}:
let
  cfg = config.meccanicos.managed;
  file = meccanicosRoot + "/fleet.toml";
  s = if builtins.pathExists file then builtins.fromTOML (builtins.readFile file) else { };
  get = path: default: lib.attrByPath path default s;
  mos-fleet = pkgs.callPackage ./mos-fleet-package.nix { };
  secrets = "/etc/secrets/meccanicos";
  # A person's groups on a MeccanicOS desktop (as the installer gives them).
  desktopGroups = [
    "networkmanager"
    "video"
    "audio"
    "input"
    "dialout"
    "lp"
    "scanner"
  ];
  has = path: lib.hasAttrByPath path options;
  str = lib.types.str;
in
{
  imports = [ ./fleet-config.nix ];

  options.meccanicos.managed = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default = builtins.pathExists file;
      description = "Managed mode: this computer belongs to an organization's fleet.";
    };
    final = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Built from the fleet repository (people, profile), not just installed.";
    };
    organization = lib.mkOption {
      type = str;
      default = get [ "organization" ] "";
    };
    host = lib.mkOption {
      type = str;
      default = get [ "hostname" ] config.networking.hostName;
    };
    profile = lib.mkOption {
      type = str;
      default = get [ "profile" ] "";
    };
    server = lib.mkOption {
      type = str;
      default = get [ "server" ] "";
      description = "The fleet server: NAME or NAME:PORT (SSH).";
    };
    serverHostKey = lib.mkOption {
      type = str;
      default = get [ "server_host_key" ] "";
      description = "The fleet server's SSH host key (pinned).";
    };
    unlock = {
      method = lib.mkOption {
        type = str;
        default = get [ "unlock" "method" ] "";
      };
    };
    interval = lib.mkOption {
      type = lib.types.int;
      default = 300;
      description = "Seconds between facts reports.";
    };
    logs = {
      minPriority = lib.mkOption {
        type = lib.types.int;
        default = 4;
      };
      units = lib.mkOption {
        type = lib.types.listOf str;
        default = [ "mos-fleet-agent" ];
      };
    };
    people = lib.mkOption {
      default = { };
      description = "Who may log in here (from the fleet repository).";
      type = lib.types.attrsOf (
        lib.types.submodule {
          options = {
            fullName = lib.mkOption { type = str; };
            uid = lib.mkOption { type = lib.types.int; };
            groups = lib.mkOption {
              type = lib.types.listOf str;
              default = [ ];
            };
            sshKeys = lib.mkOption {
              type = lib.types.listOf str;
              default = [ ];
            };
            sudo = lib.mkOption {
              type = lib.types.bool;
              default = false;
            };
          };
        }
      );
    };
    groups = lib.mkOption {
      default = { };
      type = lib.types.attrsOf (
        lib.types.submodule { options.gid = lib.mkOption { type = lib.types.int; }; }
      );
    };
  };

  config = lib.mkIf cfg.enable (
    lib.mkMerge [
      {
        assertions = [
          {
            assertion = cfg.server != "" && cfg.serverHostKey != "";
            message = "managed.nix: the fleet server and its SSH key are needed (fleet.toml: server, server_host_key).";
          }
        ];

        environment.etc."mos-fleet/client.json".text = builtins.toJSON {
          inherit (cfg) organization host profile server interval;
          final = cfg.final;
          logs = {
            min_priority = cfg.logs.minPriority;
            inherit (cfg.logs) units;
          };
        };
        environment.etc."mos-fleet/known_hosts".text = "mos-fleet-server ${cfg.serverHostKey}\n";
        environment.etc."meccanicos/fleet".text = ''
          organization=${cfg.organization}
          profile=${cfg.profile}
          server=${cfg.server}
        '';

        environment.systemPackages = [ mos-fleet ];
        # The agent uses this computer's SSH host key as its identity.
        services.openssh.enable = true;

        systemd.services.mos-fleet-agent = {
          description = "MeccanicOS fleet agent";
          wantedBy = [ "multi-user.target" ];
          wants = [ "network-online.target" ];
          after = [
            "network-online.target"
            "sshd-keygen.service"
            "sshd.service"
          ];
          # Switching the system must not restart it mid-switch: it restarts
          # itself once the switch is reported.
          restartIfChanged = false;
          path = [
            config.nix.package
            config.systemd.package
            pkgs.shadow
            pkgs.util-linux
            pkgs.iproute2
            pkgs.openssh
            pkgs.mkpasswd
          ];
          serviceConfig = {
            ExecStart = "${mos-fleet}/bin/mos-fleet-agent";
            Restart = "always";
            RestartSec = 10;
            StateDirectory = "mos-fleet";
            StateDirectoryMode = "0700";
            RuntimeDirectory = "mos-fleet";
            RuntimeDirectoryMode = "0755";
          };
        };

        # ---- Disk unlock with Tang (+ TPM): the sealed key and the boot-stage network
        boot.initrd.clevis = lib.mkIf (cfg.unlock.method == "tang") {
          enable = true;
          useTang = true;
          devices.cryptroot.secretFile = "${secrets}/cryptroot.jwe";
        };
        # Away from the office network, don't wait long for it: the recovery
        # key is asked for instead.
        boot.initrd.systemd.network.wait-online = lib.mkIf (cfg.unlock.method == "tang") {
          anyInterface = true;
          timeout = 30;
        };
      }

      # MeccanicOS's own options, when this is MeccanicOS (not in the tests' small systems).
      (lib.optionalAttrs (has [ "meccanicos" "autoUpgrade" ]) {
        # The fleet repository decides what runs here, and when.
        meccanicos.autoUpgrade = lib.mkForce false;
      })
      (lib.optionalAttrs (has [ "meccanicos" "initrdNetwork" ]) {
        meccanicos.initrdNetwork = lib.mkIf (cfg.unlock.method == "tang") true;
      })

      # ---- People, from the repository -------------------------------------
      (lib.mkIf cfg.final {
        users.mutableUsers = lib.mkForce false;
        users.users = lib.mapAttrs (name: p: {
          isNormalUser = true;
          inherit (p) uid;
          description = p.fullName;
          extraGroups = desktopGroups ++ p.groups ++ lib.optional p.sudo "wheel";
          openssh.authorizedKeys.keys = p.sshKeys;
          # Written by the agent from the server; read at every activation.
          hashedPasswordFile = "/var/lib/mos-fleet/passwords/${name}";
        }) cfg.people;
        users.groups = lib.mapAttrs (_: g: { inherit (g) gid; }) cfg.groups;
        # People have passwords now: sudo asks for it.
        security.sudo.wheelNeedsPassword = lib.mkForce true;
        services.xserver.displayManager.lightdm.extraSeatDefaults = ''
          greeter-show-manual-login=true
          greeter-hide-users=true
        '';
        environment.shellAliases.passwd = "mos-passwd";
      })
    ]
  );
}
