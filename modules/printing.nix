# Printing and scanning. Network printers and scanners are discovered
# automatically (IPP Everywhere / AirPrint / eSCL); common USB printer
# drivers are included. All drivers here are free software.
# Printers are managed with mos-printers (scripts/mos-printers.py): find
# and add them, the default one, the queue. `print FILE` prints.
{ pkgs, ... }:
let
  inherit (import ./not-root.nix) notRoot;
  mos-printers = pkgs.writeShellScriptBin "mos-printers" ''
    ${notRoot "mos-printers"}
    export MECCANICOS_PYLIB=${../scripts/lib}
    export MECCANICOS_TESTPAGE=${pkgs.cups}/share/cups/data/testprint
    exec ${pkgs.python3}/bin/python3 ${../scripts/mos-printers.py} "$@"
  '';
  launcher = pkgs.makeDesktopItem {
    name = "mos-printers";
    desktopName = "Printers (mos-printers)";
    comment = "Add printers, pick the default one, see and cancel what is waiting to print";
    icon = "printer";
    exec = ''xfce4-terminal --title "Printers" --geometry 110x30 -x mos-printers'';
    keywords = [
      "printer"
      "print"
      "queue"
      "cups"
    ];
    categories = [ "Settings" ];
  };
in
{
  services.printing = {
    enable = true;
    drivers = with pkgs; [
      # many Canon, Epson, HP, … inkjets; without its sample pictures
      (gutenprint.overrideAttrs (old: {
        postInstall = (old.postInstall or "") + "rm -rf $out/share/gutenprint/samples\n";
      }))
      (hplip.override { withQt5 = false; }) # HP; drivers only, no Qt 5 hp-toolbox GUI
      brlaser # Brother lasers
      epson-escpr2 # recent Epson inkjets
      splix # Samsung / Xerox lasers
      # Minolta, HP, Samsung, … host-based lasers. Its *-wrapper scripts record
      # the build-time PATH, which keeps GCC + binutils (~0.3 GB) installed for
      # nothing; drop those (unused) entries.
      (foo2zjs.overrideAttrs (old: {
        nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [ removeReferencesTo ];
        postFixup = (old.postFixup or "") + ''
          remove-references-to -t ${stdenv.cc.cc} -t ${stdenv.cc} \
            -t ${stdenv.cc.bintools} -t ${stdenv.cc.bintools.bintools} $out/bin/*
        '';
      }))
    ];
  };
  services.avahi = {
    enable = true;
    nssmdns4 = true;
    openFirewall = true; # discover network printers/scanners
  };

  hardware.sane = {
    enable = true;
    extraBackends = [ pkgs.sane-airscan ]; # driverless network/USB scanners
  };

  environment.systemPackages = with pkgs; [
    mos-printers
    launcher
    simple-scan # "Document Scanner"
  ];
}
