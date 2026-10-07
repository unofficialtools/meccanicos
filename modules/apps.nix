# apps: find, try, install, update and remove apps without editing Nix files
# (scripts/mos-apps.py; needs the internet). Installs go into the user's
# own Nix profile; "Apps Manager (apps)" in the command bar runs `apps manage`.
{ pkgs, ... }:
let
  inherit (import ./not-root.nix) notRoot;
  apps = pkgs.writeShellScriptBin "apps" ''
    ${notRoot "apps"}
    export MECCANICOS_PYLIB=${../scripts/lib}
    exec ${pkgs.python3}/bin/python3 ${../scripts/mos-apps.py} "$@"
  '';
in
{
  environment.systemPackages = [ apps ];
}
