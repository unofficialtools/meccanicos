# settings: the installed system's settings that need a rebuild, from
# /etc/nixos/meccanicos.toml. `meccanicos config set` writes that file and rebuilds;
# it is absent in the repo and until something is changed, so the defaults
# below are what an untouched system runs. Keys (all optional):
#
#   ssh = false                SSH server, keys only (installed.nix): off unless true
#   firewall = "managed"      managed (also when absent): mos-config manages the firewall:
#                              the same ports come in on every network card, no port ranges,
#                              loopback and everything going out allowed. Absent, the ports are
#                              the system's own (drivers.nix and the modules' openFirewall);
#                              "managed" written by mos-config: exactly tcp_ports and udp_ports.
#                              "not-managed": the system's own firewall, not touched.
#   tcp_ports = [22, 8080]     with firewall = "managed", the ports let in
#   udp_ports = [5353]         (absent firewall, from an older mos-config: added to the
#                              system's own ports, as before)
#   hibernate = true           meccanicos.hibernate
#   auto_update = true         meccanicos.autoUpgrade
#   public_dns = false         meccanicos.dns.public (dns.nix)
#   lid = "suspend"            closing the lid: suspend | hibernate | lock | nothing
#   charge_limit = 80          stop charging the battery at this %, if it can
#   gpu = "auto"               auto | nvidia | open  (the meccanicos.gpu= boot option)
{
  config,
  lib,
  pkgs,
  meccanicosRoot,
  ...
}:
let
  file = meccanicosRoot + "/meccanicos.toml"; # /etc/nixos (flake.nix: mkInstalled)
  s = if builtins.pathExists file then builtins.fromTOML (builtins.readFile file) else { };
  has = k: s ? ${k};
  firewall = s.firewall or "managed"; # "managed" | "not-managed"
  listed = firewall == "managed" && has "firewall"; # mos-config wrote the ports: exactly those
  fw = config.networking.firewall;
  lidAction = {
    suspend = "suspend";
    hibernate = "hibernate";
    lock = "lock";
    nothing = "ignore";
  };
in
{
  config = lib.mkMerge [
    (lib.mkIf (has "ssh") { services.openssh.enable = lib.mkForce s.ssh; })
    # What the system lets in by itself, for mos-config to start from when it lists the ports.
    (lib.mkIf (!listed) {
      environment.etc."meccanicos/firewall.json".text = builtins.toJSON {
        tcp = fw.allowedTCPPorts;
        udp = fw.allowedUDPPorts;
      };
    })
    (lib.mkIf (firewall == "managed") {
      # The same ports whichever network card they arrive on: no port ranges, and loopback
      # (lo) the only trusted interface (everything on it allowed). The NixOS firewall accepts
      # replies to connections made from here, and filters nothing going out. Rules for
      # virtual interfaces stay (podman0: DNS for containers).
      networking.firewall = {
        enable = lib.mkForce true;
        allowedTCPPortRanges = lib.mkForce [ ];
        allowedUDPPortRanges = lib.mkForce [ ];
        trustedInterfaces = lib.mkForce [ "lo" ];
      };
    })
    (lib.mkIf listed {
      networking.firewall.allowedTCPPorts = lib.mkForce (s.tcp_ports or [ ]);
      networking.firewall.allowedUDPPorts = lib.mkForce (s.udp_ports or [ ]);
    })
    (lib.mkIf (!has "firewall" && has "tcp_ports") { networking.firewall.allowedTCPPorts = s.tcp_ports; })
    (lib.mkIf (!has "firewall" && has "udp_ports") { networking.firewall.allowedUDPPorts = s.udp_ports; })
    (lib.mkIf (has "hibernate") { meccanicos.hibernate = s.hibernate; })
    (lib.mkIf (has "auto_update") { meccanicos.autoUpgrade = s.auto_update; })
    (lib.mkIf (has "public_dns") { meccanicos.dns.public = s.public_dns; })
    (lib.mkIf (has "lid") (
      let
        # Hibernation turned off: closing the lid suspends instead of doing nothing.
        off = s.lid == "hibernate" && !config.meccanicos.hibernate;
        action = if off then "suspend" else lidAction.${s.lid};
      in
      {
        services.logind.settings.Login = {
          HandleLidSwitch = lib.mkForce action;
          HandleLidSwitchExternalPower = lib.mkForce action;
        };
        warnings = lib.optional off "lid = \"hibernate\" but hibernate = false: closing the lid suspends.";
      }
    ))
    # Over local.nix's (the installer writes one there).
    (lib.mkIf (has "hostname") { networking.hostName = lib.mkForce s.hostname; })
    (lib.mkIf (has "gpu" && s.gpu != "auto") { boot.kernelParams = [ "meccanicos.gpu=${s.gpu}" ]; })
    # Laptops that can stop charging early expose the threshold in sysfs.
    # Some firmware forgets it while asleep: set again after each wake-up.
    (lib.mkIf (has "charge_limit") {
      systemd.services.mos-charge-limit = {
        description = "Stop charging the battery at ${toString s.charge_limit}%";
        wantedBy = [
          "multi-user.target"
          "post-resume.target"
        ];
        after = [ "post-resume.target" ];
        serviceConfig.Type = "oneshot";
        script = ''
          for f in /sys/class/power_supply/BAT*/charge_control_end_threshold; do
            [ -w "$f" ] && echo ${toString s.charge_limit} > "$f" || true
          done
        '';
      };
    })
  ];
}
