{
  description = "MeccanicOS - a NixOS-based live USB distro (XFCE, broad hardware support, LUKS vault, offline installer)";

  inputs = {
    # Pin to the current NixOS stable release. Bump this (and run
    # `nix flake update`) to move to a newer release.
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    # rigx: Nix-backed declarative build system (rigx.toml)
    rigx = {
      url = "github:unofficialtools/rigx";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      rigx,
    }:
    let
      system = "x86_64-linux";
      lib = nixpkgs.lib;

      # ---- Customise your distro here ------------------------------------
      distro = {
        name = "MeccanicOS"; # shown in boot menu, /etc/os-release, login screen
        id = "meccanicos"; # lowercase, no spaces
        hostName = "meccanicos";
        liveUser = "live"; # auto-logged-in desktop user on the USB stick
        vaultLabel = "MOS-VAULT"; # LUKS label of the encrypted USB partition
        dataLabel = "MOS-DATA"; # label of the plain USB partition holding .luks files (max 11 chars)
        homeLabel = "MOS-HOME"; # LUKS label of the persistent-home partition
        repo = "https://github.com/unofficialtools/meccanicos"; # installed systems follow its latest release (mkInstalled)
      };
      # --------------------------------------------------------------------

      # Build date (YYYYMMDD) and time, for /etc/meccanicos/version.
      # `./start iso` passes today's date (MECCANICOS_BUILD_DATE, needs --impure);
      # a plain `nix build .#iso` uses the date of the last commit.
      buildDate =
        let
          env = builtins.getEnv "MECCANICOS_BUILD_DATE";
        in
        if env == "" then
          builtins.substring 0 8 (self.lastModifiedDate or "19700101")
        else if builtins.match "[0-9]{8}" env != null then
          env
        else
          throw "MECCANICOS_BUILD_DATE must be YYYYMMDD, got '${env}'";
      # ...and the time (HHMM, UTC), for /etc/meccanicos/version: MECCANICOS_BUILD_TIME,
      # else the time of the last commit.
      buildTime =
        let
          env = builtins.getEnv "MECCANICOS_BUILD_TIME";
        in
        if env == "" then
          builtins.substring 8 4 (self.lastModifiedDate or "197001010000")
        else if builtins.match "[0-9]{4}" env != null then
          env
        else
          throw "MECCANICOS_BUILD_TIME must be HHMM, got '${env}'";
      # Which release this is (ISO name, /etc/os-release, /etc/meccanicos/version):
      # the release workflow passes its tag (v2026-10-16) as MECCANICOS_RELEASE,
      # `./start iso` the tag or the branch; else "dev".
      release =
        let
          env = builtins.getEnv "MECCANICOS_RELEASE";
        in
        if env == "" then
          "dev"
        else if builtins.match "[a-z0-9._-]+" env != null then
          env
        else
          throw "MECCANICOS_RELEASE must be lowercase letters, digits, '.', '_' or '-', got '${env}'";
      # ...and its commit (with -dirty when built from uncommitted changes).
      commit = self.shortRev or self.dirtyShortRev or "unknown";

      # Shared by the live USB and the installed system.
      common = [
        {
          system.nixos.distroName = distro.name;
          system.nixos.distroId = distro.id;
          nixpkgs.hostPlatform = system;
          # Pin `nix shell nixpkgs#…` and rebuilds to the exact nixpkgs used
          # here; its source ships on the ISO so it is available offline.
          nix.registry.nixpkgs.flake = nixpkgs;
          nix.nixPath = [ "nixpkgs=${nixpkgs}" ];
          environment.systemPackages = [ rigx.packages.${system}.rigx ];
        }
        ./modules/drivers.nix
        ./modules/desktop.nix
        ./modules/branding.nix
        ./modules/vault.nix
        ./modules/shell.nix
        ./modules/browser.nix
        ./modules/ai.nix
        ./modules/voice.nix
        ./modules/python.nix
        ./modules/keyboard.nix
        ./modules/menu.nix
        ./modules/apps.nix
        ./modules/vscodium.nix
        ./modules/tutorial.nix
        ./modules/help.nix
        ./modules/mos-cli.nix
        ./modules/printing.nix
        ./modules/updates.nix
        ./modules/backup.nix
        ./modules/dropbox.nix
        ./modules/hardening.nix
        ./modules/dns.nix
        ./modules/logins.nix
        ./packages.nix
      ];

      # ---- The installed system ------------------------------------------
      # An installed computer's /etc/nixos holds only its own files (local.nix,
      # hardware-configuration.nix, meccanicos.toml, remote-unlock-keys) and a
      # small flake.nix (etcNixos below) that takes everything else from this
      # repository at its latest release:
      #   nixosConfigurations.installed = meccanicos.lib.mkInstalled { root = ./.; };
      # So mos-upgrade (nix flake update + rebuild) brings the newest MeccanicOS
      # and NixOS packages together. root: the folder with those files.
      mkInstalled =
        {
          root,
          modules ? [ ],
        }:
        let
          mine = name: lib.optional (builtins.pathExists (root + "/${name}")) (root + "/${name}");
        in
        lib.nixosSystem {
          specialArgs = {
            inherit distro;
            meccanicosRoot = root;
          };
          modules =
            common
            ++ [
              ./modules/installed.nix
              ./modules/settings.nix
              # Fleet management (experimental): a managed machine (fleet.toml)
              # and the fleet server (fleet-server.toml). Off without those files.
              ./modules/managed.nix
              ./modules/fleet-server.nix
              # New fleets (mos-fleet init) follow this distribution's releases.
              { meccanicos.fleet.config.admin.meccanicos = lib.mkDefault "github:${github}/latest"; }
              # Keep these sources on the disk: rebuilds then work offline.
              {
                system.extraDependencies = [
                  self.outPath
                  rigx.outPath
                ];
              }
            ]
            ++ mine "hardware-configuration.nix"
            ++ mine "local.nix"
            ++ modules;
        };

      # ---- A fleet's computers ------------------------------------------
      # The fleet repository's flake.nix (mos-fleet init) is
      #   outputs = { meccanicos, ... }: meccanicos.lib.mkFleet { repo = ./.; };
      # One system per hosts/NAME: an installed MeccanicOS (mkInstalled, its
      # root hosts/NAME: hardware-configuration.nix, local.nix, meccanicos.toml),
      # managed (modules/managed.nix, final), with common.nix, its profile, and
      # the people whose groups may log in on that profile (groups.toml).
      # scripts/mos_fleet/repo.py checks the same files by the same rules.
      # mkSystem { name, root, modules }: builds one in place of mkInstalled
      # (the VM test's small systems, tests/fleet.nix).
      mkFleet =
        {
          repo,
          mkSystem ? null,
          modules ? [ ],
        }:
        let
          toml = f: builtins.fromTOML (builtins.readFile f);
          fleet = toml (repo + "/fleet.toml");
          groups = toml (repo + "/groups.toml");
          dir = d: if builtins.pathExists (repo + "/${d}") then builtins.readDir (repo + "/${d}") else { };
          people = lib.mapAttrs' (f: _: lib.nameValuePair (lib.removeSuffix ".toml" f) (toml (repo + "/people/${f}"))) (
            lib.filterAttrs (f: t: t == "regular" && lib.hasSuffix ".toml" f) (dir "people")
          );
          hosts = lib.attrNames (lib.filterAttrs (n: t: t == "directory" && !(lib.hasPrefix "." n)) (dir "hosts"));
          known = g: builtins.filter (x: groups ? ${x}) g;
          host =
            name:
            let
              root = repo + "/hosts/${name}";
              h = toml (root + "/host.toml");
              allows =
                g:
                let
                  ps = groups.${g}.profiles or [ ];
                in
                groups ? ${g} && (builtins.elem "*" ps || builtins.elem h.profile ps);
              allowed = lib.filterAttrs (_: p: !(p.disabled or false) && builtins.any allows (p.groups or [ ])) people;
              fleetModule = {
                networking.hostName = name;
                meccanicos.managed = {
                  enable = true;
                  final = true;
                  host = name;
                  profile = h.profile;
                  organization = fleet.organization;
                  server = fleet.server;
                  serverHostKey = fleet.server_host_key;
                  unlock.method = h.unlock;
                  interval = fleet.checkin.interval or 300;
                  logs.minPriority = fleet.logs.min_priority or 4;
                  logs.units = fleet.logs.units or [ "mos-fleet-agent" ];
                  people = lib.mapAttrs (_: p: {
                    fullName = p.name;
                    inherit (p) uid;
                    groups = known (p.groups or [ ]);
                    sshKeys = p.ssh_keys or [ ];
                    sudo = builtins.any (g: allows g && (groups.${g}.sudo or false)) (p.groups or [ ]);
                  }) allowed;
                  groups = lib.genAttrs (lib.unique (lib.concatMap (p: known (p.groups or [ ])) (lib.attrValues allowed))) (
                    g: { inherit (groups.${g}) gid; }
                  );
                };
              };
              mine = f: lib.optional (builtins.pathExists (root + "/${f}")) (root + "/${f}");
              extra = [
                fleetModule
                (repo + "/profiles/${h.profile}.nix")
              ]
              ++ lib.optional (builtins.pathExists (repo + "/common.nix")) (repo + "/common.nix")
              ++ modules;
            in
            if mkSystem == null then
              mkInstalled {
                inherit root;
                modules = extra;
              }
            else
              mkSystem {
                inherit name root;
                modules = mine "hardware-configuration.nix" ++ mine "local.nix" ++ extra;
              };
        in
        {
          nixosConfigurations = lib.genAttrs hosts host;
        };

      # What the installer puts in /etc/nixos: the flake.nix, and a
      # flake.lock pinned to this very commit, whose source the ISO carries, so
      # the installed system rebuilds offline. A build from uncommitted changes
      # has no commit to pin: then the first rebuild locks the latest release.
      github = lib.removePrefix "https://github.com/" distro.repo; # owner/repo
      repoLock = builtins.fromJSON (builtins.readFile ./flake.lock);
      etcNixos =
        let
          pkgs = nixpkgs.legacyPackages.${system};
          owner = builtins.head (lib.splitString "/" github);
          repo = lib.last (lib.splitString "/" github);
          flake = ''
            # ${distro.name} on this computer. Your own files are here: local.nix (your
            # choices, edit freely), hardware-configuration.nix, meccanicos.toml
            # (mos-config's system settings) and remote-unlock-keys (mos-unlock).
            # Everything else comes from ${distro.repo}
            # at its latest release, pinned in flake.lock.
            #   mos-upgrade   the newest ${distro.name} and NixOS packages, then rebuild
            #   mos-rebuild   apply changes made to the files here
            {
              inputs = {
                nixpkgs.url = "github:NixOS/nixpkgs/${repoLock.nodes.nixpkgs.original.ref}";
                rigx = {
                  url = "github:${repoLock.nodes.rigx.original.owner}/${repoLock.nodes.rigx.original.repo}";
                  inputs.nixpkgs.follows = "nixpkgs";
                };
                meccanicos = {
                  url = "github:${github}/latest";
                  inputs.nixpkgs.follows = "nixpkgs";
                  inputs.rigx.follows = "rigx";
                };
              };
              outputs =
                { meccanicos, ... }:
                {
                  nixosConfigurations.installed = meccanicos.lib.mkInstalled { root = ./.; };
                };
            }
          '';
          lock = {
            version = 7;
            root = "root";
            nodes = {
              root.inputs = {
                meccanicos = "meccanicos";
                nixpkgs = "nixpkgs";
                rigx = "rigx";
              };
              inherit (repoLock.nodes) nixpkgs;
              meccanicos = {
                inputs = {
                  nixpkgs = [ "nixpkgs" ];
                  rigx = [ "rigx" ];
                };
                locked = {
                  type = "github";
                  inherit owner repo;
                  rev = self.rev;
                  inherit (self) narHash lastModified;
                };
                original = {
                  type = "github";
                  inherit owner repo;
                  ref = "latest";
                };
              };
              rigx = repoLock.nodes.rigx // {
                inputs.nixpkgs = [ "nixpkgs" ];
              };
            };
          };
        in
        pkgs.runCommand "${distro.id}-etc-nixos" { } (
          ''
            mkdir $out
            cp ${pkgs.writeText "flake.nix" flake} $out/flake.nix
          ''
          + lib.optionalString (self ? rev) ''
            cp ${pkgs.writeText "flake.lock" (builtins.toJSON lock)} $out/flake.lock
          ''
        );

      # The system installed to disk by `mos-install`, prebuilt into the ISO
      # (none of an installed computer's own files yet).
      installed = mkInstalled {
        root = ./.;
        modules = [ ./modules/redistributable.nix ]; # it ships inside the ISO
      };

      # MeccanicOS-README.pdf, next to MeccanicOS on the USB drive (the ISO's root; Ventoy
      # sticks: mos-usb, ./start ventoy; each release publishes it): thanks,
      # starting from the drive, the firmware settings, where to get help.
      readmePdf =
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        pkgs.runCommand "MeccanicOS-README.pdf"
          {
            nativeBuildInputs = [ pkgs.typst ];
            fonts = "${pkgs.inter}/share/fonts:${pkgs.jetbrains-mono}/share/fonts";
          }
          ''
            cp ${./docs/usb-readme/README.typ} README.typ
            cp ${./branding/logo/meccanicos-logo-black.svg} logo.svg
            typst compile --ignore-system-fonts --font-path "$fonts" README.typ $out
          '';

      # The live USB system, carrying the prebuilt installed system.
      live = lib.nixosSystem {
        specialArgs = {
          inherit
            distro
            buildDate
            buildTime
            release
            commit
            readmePdf
            ;
          installedSystem = installed.config.system.build.toplevel;
          inherit etcNixos;
          flakeCommit = commit;
        };
        modules = common ++ [
          ./modules/redistributable.nix
          ./modules/iso.nix
          ./modules/branding-boot.nix
          ./modules/installer.nix
        ];
      };
      # The live system that films the tutorial video (never shipped).
      recorder = live.extendModules { modules = [ ./modules/tutorial-recorder.nix ]; };
    in
    {
      nixosConfigurations = {
        inherit installed live recorder;
      };

      # For an installed computer's /etc/nixos/flake.nix (see mkInstalled).
      lib = { inherit mkInstalled mkFleet; };

      packages.${system} = {
        iso = self.nixosConfigurations.live.config.system.build.isoImage; # nix build .#iso
        default = self.packages.${system}.iso;
        readme-pdf = readmePdf; # nix build .#readme-pdf (on the USB drive as MeccanicOS-README.pdf)
        # Screenshots of the mos-* tools for www/, taken in a VM (./start www).
        www-screenshots = (import ./tests { inherit self nixpkgs system; }).screenshots;
      };

      apps.${system} = {
        # Boot MeccanicOS in QEMU (try it, record a demo):  nix run .#vm  [-- --help]
        vm =
          let
            pkgs = nixpkgs.legacyPackages.${system};
            vm = pkgs.writeShellApplication {
              name = "mos-vm";
              runtimeInputs = [
                pkgs.qemu
                pkgs.pulseaudio # pactl, to detect a sound server
                pkgs.coreutils
                pkgs.gnused
              ];
              text = ''
                export MECCANICOS_VM_ISO="''${MECCANICOS_VM_ISO:-${self.packages.${system}.iso}/iso/${live.config.image.fileName}}"
                export MECCANICOS_VM_OVMF_CODE="${pkgs.OVMF.fd}/FV/OVMF_CODE.fd"
                export MECCANICOS_VM_OVMF_VARS="${pkgs.OVMF.fd}/FV/OVMF_VARS.fd"
              ''
              + builtins.readFile ./scripts/mos-vm.sh;
            };
          in
          {
            type = "app";
            program = "${vm}/bin/mos-vm";
            meta.description = "Boot MeccanicOS in QEMU";
          };

        # Film the tutorial video in a VM:  nix run .#tutorial-video  (or ./start tutorial-video)
        tutorial-video =
          let
            pkgs = nixpkgs.legacyPackages.${system};
            film = pkgs.writeShellApplication {
              name = "mos-tutorial-video";
              runtimeInputs = with pkgs; [
                qemu
                mtools
                dosfstools
                ffmpeg-full
                python3
                coreutils
                gnused
                gawk
              ];
              text = ''
                export MECCANICOS_RECORDER_ISO="${recorder.config.system.build.isoImage}/iso/${recorder.config.image.fileName}"
                export MECCANICOS_MESA=${pkgs.mesa}
                export MECCANICOS_VM_OVMF_CODE="${pkgs.OVMF.fd}/FV/OVMF_CODE.fd"
                export MECCANICOS_VM_OVMF_VARS="${pkgs.OVMF.fd}/FV/OVMF_VARS.fd"
                export MECCANICOS_TUTORIAL_ENCODE=${./scripts/mos-tutorial-encode.py}
                export MECCANICOS_SUBTITLE_FONTS=${pkgs.dejavu_fonts}/share/fonts/truetype
              ''
              + builtins.readFile ./scripts/mos-tutorial-video.sh;
            };
          in
          {
            type = "app";
            program = "${film}/bin/mos-tutorial-video";
            meta.description = "Film the tutorial video in a VM";
          };
      };

      # Automated VM tests: nix flake check  (or nix build .#checks.x86_64-linux.<name>)
      checks.${system} = removeAttrs (import ./tests {
        inherit self nixpkgs system;
      }) [ "screenshots" ];
    };
}
