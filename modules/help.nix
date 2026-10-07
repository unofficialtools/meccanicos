# help: the README as an offline manual, the same version as the system that
# carries it. "Help" in the command bar and `mos help [TOPIC]` open it
# (scripts/mos/main.py); over SSH `mos help` shows the README in the terminal.
# Built from the repo's own files, so it never drifts from them. The web page
# (www/) is not on the ISO, nor does it affect it; the tutorial video is on the
# desktop (tutorial.nix).
{ pkgs, distro, ... }:
let
  dir = "share/${distro.id}/help";
  blob = "${distro.repo}/blob/main";
  help =
    pkgs.runCommand "${distro.id}-help"
      {
        nativeBuildInputs = [ pkgs.pandoc ];
      }
      ''
        mkdir -p $out/${dir}
        # The README's links that only work on GitHub (other files of the repo,
        # its Releases page) become full addresses; its pictures (in www/, which
        # is not on the ISO) come from GitHub when online.
        sed -E \
          -e 's#\]\(\.\./\.\./([^)]*)\)#](${distro.repo}/\1)#g' \
          -e 's#\]\(((modules|scripts|tests|branding|tools)/[^)#]*|LICENSE|CONTRIBUTING\.md|TODO\.md|flake\.nix|packages\.nix)\)#](${blob}/\1)#g' \
          -e 's#src="www/#src="https://raw.githubusercontent.com/unofficialtools/meccanicos/main/www/#g' \
          ${../README.md} >README.md
        cp README.md $out/${dir}/README.md
        pandoc --from gfm --to html5 --standalone \
          --metadata pagetitle="${distro.name} manual" \
          --css manual.css \
          README.md -o $out/${dir}/manual.html
        cp ${./help-manual.css} $out/${dir}/manual.css
      '';
  launcher = pkgs.makeDesktopItem {
    name = "${distro.id}-help";
    desktopName = "Help (${distro.name})";
    comment = "The ${distro.name} manual, offline";
    icon = "help-browser";
    exec = "mos help";
    categories = [ "Utility" ];
  };
in
{
  environment.systemPackages = [
    help
    launcher
  ];
  # /run/current-system/sw/share/<id> (also tutorial.nix): where `mos help` looks.
  environment.pathsToLink = [ "/share/${distro.id}" ];
}
