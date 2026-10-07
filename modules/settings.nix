# settings: the installed system's settings that need a rebuild, from
# /etc/nixos/meccanicos.toml. `meccanicos config set` writes that file and rebuilds;
# it is absent in the repo and until something is changed, so the defaults
# below are what an untouched system runs. Keys (all optional):
#
#   ssh = true                 SSH server, keys only (installed.nix)
#   tcp_ports = [8080]         let these in through the firewall
#   udp_ports = []
#   hibernate = true           meccanicos.hibernate
#   auto_update = true         meccanicos.autoUpgrade
#   lid = "suspend"            closing the lid: suspend | hibernate | lock | nothing
#   charge_limit = 80          stop charging the battery at this %, if it can
#   gpu = "auto"               auto | nvidia | open  (the meccanicos.gpu= boot option)
{
  config,
  lib,
  pkgs,
  ...
}:
let
  file = ../meccanicos.toml;
  s = if builtins.pathExists file then builtins.fromTOML (builtins.readFile file) else { };
  has = k: s ? ${k};
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
    (lib.mkIf (has "tcp_ports") { networking.firewall.allowedTCPPorts = s.tcp_ports; })
    (lib.mkIf (has "udp_ports") { networking.firewall.allowedUDPPorts = s.udp_ports; })
    (lib.mkIf (has "hibernate") { meccanicos.hibernate = s.hibernate; })
    (lib.mkIf (has "auto_update") { meccanicos.autoUpgrade = s.auto_update; })
    (lib.mkIf (has "lid") {
      services.logind.settings.Login = {
        HandleLidSwitch = lib.mkForce lidAction.${s.lid};
        HandleLidSwitchExternalPower = lib.mkForce lidAction.${s.lid};
      };
    })
    (lib.mkIf (has "gpu" && s.gpu != "auto") { boot.kernelParams = [ "meccanicos.gpu=${s.gpu}" ]; })
    # Laptops that can stop charging early expose the threshold in sysfs.
    (lib.mkIf (has "charge_limit") {
      systemd.services.mos-charge-limit = {
        description = "Stop charging the battery at ${toString s.charge_limit}%";
        wantedBy = [ "multi-user.target" ];
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
