# The fleet, end to end, in three VMs (nix build .#checks.x86_64-linux.fleet -L):
#
#   hq      the fleet server (modules/fleet-server.nix)
#   admin   an admin's computer: mos-fleet as the user mrossi
#   ws1     a new computer: enrolls with the stick's one-time key, is added,
#           and switches to the system the server built for it
#
# Following docs/fleet/ADMIN-GUIDE.md: server init, init, profiles, people,
# host prepare / add, updates, passwords (mos-passwd), jobs, shell, logs,
# retire; and what must be refused (invalid pushes, rewriting main, another
# computer's system, a used enrollment key, forwarding, unknown keys).
#
# No network: the systems hq builds for ws1 are computed here ahead of time
# (from fleet/repo-a and fleet/repo-b, the repository's expected contents)
# and put in hq's store; the test checks that the build in the VM gives
# exactly those. For that, ws1's system in the fleet is this very test's ws1
# node with the fleet's modules (mkSystem, below), and the fleet repository's
# flake.nix (fleet/flake.nix.in) uses mkSystem too.
{
  self,
  nixpkgs,
  system,
}:
let
  pkgs = nixpkgs.legacyPackages.${system};
  lib = nixpkgs.lib;
  keys = ./fleet/keys;
  rigx = self.inputs.rigx;

  # Fixed keys (tests only): installed with the right modes at activation.
  hostKey = name: {
    services.openssh = {
      enable = true;
      settings = {
        PasswordAuthentication = false;
        KbdInteractiveAuthentication = false;
      };
      hostKeys = [
        {
          path = "/etc/ssh/ssh_host_ed25519_key";
          type = "ed25519";
        }
      ];
    };
    system.activationScripts.testHostKey = ''
      install -D -m 600 ${keys}/${name} /etc/ssh/ssh_host_ed25519_key
      install -m 644 ${keys}/${name}.pub /etc/ssh/ssh_host_ed25519_key.pub
    '';
  };
  offline = {
    nix.settings = {
      experimental-features = [
        "nix-command"
        "flakes"
      ];
      substituters = lib.mkForce [ ];
    };
    virtualisation.writableStore = true;
  };
  sources = [
    self.outPath
    nixpkgs.outPath
    rigx.outPath
  ];

  # ws1, in any of its lives.
  ws1Common =
    { pkgs, ... }:
    {
      imports = [
        (hostKey "ws1")
        offline
      ];
      environment.etc."nixos/hardware-configuration.nix".text = "{ ... }: { }\n";
      # Test VMs leave switch-to-configuration out; real systems have it.
      # (No bootloader to install: the test boots the kernel directly.)
      system.switch.enable = true;
      boot.loader.grub.enable = false;
      environment.systemPackages = [
        pkgs.perl
        pkgs.age
      ];
      meccanicos.fleet.config.agent = {
        reconnect_max_seconds = 15;
        logs_every_seconds = 10;
      };
      virtualisation = {
        memorySize = 2048;
        diskSize = 6144;
      };
    };
  # Just installed (what mos-install's organization install leaves).
  bootstrap = ./fleet/bootstrap;

  nodesWith = ws1: {
    hq =
      { pkgs, ... }:
      {
        imports = [
          ../modules/fleet-server.nix
          (hostKey "hq")
          offline
        ];
        _module.args.meccanicosRoot = ./fleet/keys; # no fleet-server.toml: enabled below
        meccanicos.fleetServer = {
          enable = true;
          lan = [ "192.168.0.0/16" ];
        };
        environment.systemPackages = [ pkgs.git ];
        environment.etc."test-keys/mrossi.pub".source = "${keys}/mrossi.pub";
        virtualisation = {
          memorySize = 3072;
          diskSize = 8192;
          additionalPaths = sources ++ [
            expected.a
            expected.b
          ];
        };
      };
    admin =
      { pkgs, ... }:
      {
        imports = [
          ../modules/fleet-server.nix # off: only the mos-fleet command
          offline
        ];
        _module.args.meccanicosRoot = ./fleet/keys;
        users.users.mrossi = {
          isNormalUser = true;
          description = "Mario Rossi";
        };
        environment.systemPackages = [ pkgs.git ];
        environment.etc."test-fleet/flake.nix".source = ./fleet/flake.nix.in;
        system.activationScripts.testUserKeys = ''
          install -d -o mrossi -m 700 /home/mrossi/.ssh /home/mrossi/.config /home/mrossi/.config/mos-fleet
          install -o mrossi -m 600 ${keys}/mrossi /home/mrossi/.ssh/id_ed25519
          install -o mrossi -m 644 ${keys}/mrossi.pub /home/mrossi/.ssh/id_ed25519.pub
          install -o mrossi -m 600 ${keys}/mrossi.age /home/mrossi/.config/mos-fleet/admin.key
        '';
        virtualisation = {
          memorySize = 3072;
          diskSize = 6144;
          additionalPaths = sources;
        };
      };
    inherit ws1;
  };

  testWith =
    ws1: script:
    pkgs.testers.runNixOSTest {
      name = "mos-fleet";
      nodes = nodesWith ws1;
      testScript = script;
    };

  # lib.mkFleet's mkSystem: the fleet's ws1 is the test's ws1 with the
  # fleet's modules (so it keeps the VM's disks, network and test hooks).
  mkSystem =
    {
      name,
      root,
      modules,
    }:
    {
      config =
        (testWith {
          imports = [
            ws1Common
            ../modules/managed.nix
          ]
          ++ modules;
          _module.args.meccanicosRoot = root;
        } "").nodes.${name};
    };

  build = repo: (self.lib.mkFleet { inherit repo mkSystem; }).nixosConfigurations.ws1.config.system.build.toplevel;
  expected = {
    a = build ./fleet/repo-a;
    b = build ./fleet/repo-b;
  };

  test = testWith {
    imports = [
      ws1Common
      ../modules/managed.nix
    ];
    _module.args.meccanicosRoot = bootstrap;
  } (''
    EXPECTED_A = "${expected.a}"
    EXPECTED_B = "${expected.b}"
    MECCANICOS = "${self.outPath}"
  '' + builtins.readFile ./fleet/test.py);
in
{
  inherit mkSystem expected test;
}
