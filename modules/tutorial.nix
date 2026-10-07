# tutorial: a video tour of MeccanicOS (tutorial/tutorial.mp4, with subtitles) on
# the desktop of every user, live and installed; double-click plays it.
# Filmed in a VM by `./start tutorial-video` (modules/tutorial-recorder.nix).
# Also an example video and picture (branding/samples.sh: the Earth at night) in ~/Pictures and
# ~/Videos, the ones the tutorial opens.
{
  lib,
  pkgs,
  distro,
  ...
}:
let
  video = ../tutorial/tutorial.mp4;
  hasVideo = builtins.pathExists video;
  dir = "/run/current-system/sw/share/${distro.id}";
  share = pkgs.runCommand "${distro.id}-tutorial" { } (
    ''
      mkdir -p $out/share/${distro.id}
      cp ${../branding/samples/example.png} $out/share/${distro.id}/example.png
      cp ${../branding/samples/example.mp4} $out/share/${distro.id}/example.mp4
    ''
    + lib.optionalString hasVideo ''
      cp ${video} $out/share/${distro.id}/tutorial.mp4
    ''
  );
in
{
  environment.systemPackages = [ share ];
  # /run/current-system/sw only has the share/ folders listed here: without
  # it the desktop's link pointed nowhere (and the files weren't on the ISO).
  environment.pathsToLink = [ "/share/${distro.id}" ];
  # Put there once per user: what you delete stays deleted.
  environment.etc."xdg/autostart/${distro.id}-tutorial-video.desktop".text = ''
    [Desktop Entry]
    Type=Application
    Name=${distro.name} tutorial and examples
    NoDisplay=true
    Exec=${pkgs.writeShellScript "tutorial-video" ''
      flag=''${XDG_STATE_HOME:-$HOME/.local/state}/${distro.id}/tutorial-video
      [ -e "$flag" ] && exit 0
      where() { ${pkgs.xdg-user-dirs}/bin/xdg-user-dir "$1" 2>/dev/null || echo "$HOME/$2"; }
      desk=$(where DESKTOP Desktop) pics=$(where PICTURES Pictures) vids=$(where VIDEOS Videos)
      mkdir -p "$desk" "$pics" "$vids" "''${flag%/*}"
      cp -n ${dir}/example.png "$pics/Earth at night.png"
      cp -n ${dir}/example.mp4 "$vids/Earth at night.mp4"
      chmod u+w "$pics/Earth at night.png" "$vids/Earth at night.mp4"
      ${lib.optionalString hasVideo ''ln -sfn ${dir}/tutorial.mp4 "$desk/Tutorial.mp4"''}
      touch "$flag"
    ''}
  '';
}
