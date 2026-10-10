# Updates: one place for what can change and how to undo it
# (scripts/mos-updates.py). The system (mos-upgrade, automatic
# updates and going back to an earlier system, from modules/installed.nix;
# on the live USB: how to write a newer ISO) and your apps (apps update /
# apps undo). It only runs those commands, after asking.
# `mos-updates status` prints the same as text.
{ pkgs, distro, ... }:
let
  inherit (import ./not-root.nix) notRoot;
  mos-updates = pkgs.writeShellScriptBin "mos-updates" ''
    ${notRoot "mos-updates"}
    export MECCANICOS_PYLIB=${../scripts/lib}
    export MECCANICOS_NAME=${pkgs.lib.escapeShellArg distro.name} MECCANICOS_ID=${distro.id}
    export MECCANICOS_REPO=${pkgs.lib.escapeShellArg distro.repo}
    exec ${pkgs.python3}/bin/python3 ${../scripts/mos-updates.py} "$@"
  '';
  launcher = pkgs.makeDesktopItem {
    name = "mos-updates";
    desktopName = "Updates (mos-updates)";
    comment = "Update ${distro.name} and your apps, or go back to an earlier version";
    icon = "system-software-update";
    exec = ''xfce4-terminal --title "Updates" --geometry 110x36 -x mos-updates'';
    keywords = [
      "update"
      "upgrade"
      "rollback"
      "undo"
      "version"
    ];
    categories = [ "Settings" ];
  };
in
{
  environment.systemPackages = [
    mos-updates
    launcher
  ];
}
