# mos-fleet's settings on this computer: /etc/mos-fleet/config.toml, over the
# defaults in scripts/mos_fleet/defaults.toml (same tables and keys). Shared
# by the fleet server (fleet-server.nix) and managed computers (managed.nix).
# MeccanicOS sets admin.meccanicos from its own repository (flake.nix).
{
  config,
  lib,
  pkgs,
  ...
}:
let
  settings = pkgs.formats.toml { };
in
{
  options.meccanicos.fleet.config = lib.mkOption {
    type = settings.type;
    default = { };
    example = {
      admin.repo = "~/work/fleet";
      server.keep_jobs_days = 90;
      agent.reconnect_max_seconds = 120;
    };
    description = "mos-fleet's settings (/etc/mos-fleet/config.toml), over scripts/mos_fleet/defaults.toml.";
  };
  config = {
    environment.etc."mos-fleet/config.toml".source =
      settings.generate "mos-fleet-config.toml" config.meccanicos.fleet.config;
  };
}
