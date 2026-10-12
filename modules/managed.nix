# Managed mode (EXPERIMENTAL): a computer that belongs to an organization's
# fleet. On by itself when /etc/nixos/fleet.toml exists (the installer writes
# it from the corporate.config found on the USB stick; see
# docs/fleet/ADMIN-GUIDE.md and mos-fleet).
#
#   comin ....... pulls the organization's fleet repository and switches to
#                 its configuration for this computer (nixosConfigurations.<hostname>),
#                 downloading it from the organization's cache
#   Fleet ....... the agent (fleetd/orbit) reports to the Fleet server
#   Kanidm ...... people log in with their organization account (cached
#                 for offline use). Who may log in: the Kanidm group named
#                 after the profile, and fleet-admins (who also get sudo);
#                 more with meccanicos.managed.loginGroups
#   disk unlock . TPM + PIN, FIDO2 key or Tang (enrolled by the installer);
#                 Tang needs the network in the boot stage, set up here
#
# Secrets live outside the store, in /etc/secrets/meccanicos: repo.token
# (read-only access to the repository), fleet.secret (Fleet enroll secret),
# cryptroot.jwe (Tang/TPM-sealed disk key, Tang machines only).
#
# fleet.toml (all keys written by the installer):
#   organization = "Example Corp"
#   profile = "office"                        # profiles/office.nix in the repository
#   [repo]   url, branch ("main"), username ("fleet-reader")
#   [cache]  url, public_key
#   [fleet]  url
#   [kanidm] url
#   [unlock] method = "tang" | "tpm-pin" | "fido2"
# The organization's CA certificate is /etc/nixos/ca.crt.
{
  config,
  lib,
  pkgs,
  meccanicosRoot,
  cominSrc,
  ...
}:
let
  cfg = config.meccanicos.managed;
  file = meccanicosRoot + "/fleet.toml";
  caFile = meccanicosRoot + "/ca.crt";
  s = if builtins.pathExists file then builtins.fromTOML (builtins.readFile file) else { };
  get =
    path: default:
    lib.attrByPath path default s;
  secrets = "/etc/secrets/meccanicos";
  unlock = get [ "unlock" "method" ] "";
in
{
  imports = [
    ./vendor/orbit.nix
    (import "${cominSrc}/nix/module.nix" { self.packages = { }; })
  ];

  options.meccanicos.managed = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default = builtins.pathExists file;
      description = "Managed mode: this computer follows its organization's fleet repository (on when /etc/nixos/fleet.toml exists).";
    };
    loginGroups = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      example = [
        "office"
        "fleet-admins"
      ];
      description = "More Kanidm groups whose members may log in on this computer (besides fleet-admins and the profile's group).";
    };
    fleetDesktop = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Fleet Desktop: a tray icon showing the user what Fleet knows about this computer.";
    };
    fleetScripts = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Let Fleet administrators run scripts on this computer (as root).";
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = s ? repo.url && s ? cache.url && s ? fleet.url && s ? kanidm.url;
        message = "managed.nix: ${toString file} needs [repo] url, [cache] url, [fleet] url and [kanidm] url.";
      }
      {
        assertion = builtins.pathExists caFile;
        message = "managed.nix: the organization's CA certificate ${toString caFile} is missing.";
      }
    ];

    # The fleet repository decides what runs here, and when: no MeccanicOS
    # updates of its own (the repository pins the MeccanicOS version).
    meccanicos.autoUpgrade = lib.mkForce false;

    environment.etc."meccanicos/fleet".text = ''
      organization=${get [ "organization" ] ""}
      profile=${get [ "profile" ] ""}
      repo=${get [ "repo" "url" ] ""}
      fleet=${get [ "fleet" "url" ] ""}
      kanidm=${get [ "kanidm" "url" ] ""}
      unlock=${unlock}
    '';

    # ---- Trust: the organization's CA and binary cache ---------------------
    security.pki.certificateFiles = [ caFile ];
    nix.settings = {
      extra-substituters = [ (get [ "cache" "url" ] "") ];
      extra-trusted-public-keys = [ (get [ "cache" "public_key" ] "") ];
    };

    # ---- Configuration: comin pulls the fleet repository --------------------
    services.comin = {
      enable = true;
      package = pkgs.callPackage "${cominSrc}/nix/package.nix" { };
      remotes = [
        {
          name = "origin";
          url = get [ "repo" "url" ] "";
          auth = {
            access_token_path = "${secrets}/repo.token";
            username = get [ "repo" "username" ] "fleet-reader";
          };
          branches.main.name = get [ "repo" "branch" ] "main";
        }
      ];
    };

    # ---- Inventory: the Fleet agent ----------------------------------------
    services.orbit = {
      enable = true;
      orbitPackage = pkgs.callPackage ./vendor/fleet-orbit/package.nix { };
      fleetUrl = get [ "fleet" "url" ] "";
      enrollSecretPath = "${secrets}/fleet.secret";
      fleetCertificate = config.security.pki.caBundle;
      desktop.enable = cfg.fleetDesktop;
      enableScripts = cfg.fleetScripts;
      hostIdentifier = "uuid";
    };

    # ---- People: Kanidm accounts, cached for offline logins ------------------
    # Already right after the installation, before the fleet repository has
    # this computer: its profile's people, and the fleet admins (with sudo).
    meccanicos.managed.loginGroups = [ "fleet-admins" ] ++ lib.optional (s ? profile) s.profile;
    security.sudo.extraRules = [
      {
        groups = [ "fleet-admins" ];
        commands = [ "ALL" ];
      }
    ];
    services.kanidm = {
      package = pkgs.kanidm_1_11;
      client.enable = true;
      client.settings = {
        uri = get [ "kanidm" "url" ] "";
        ca_path = "${caFile}";
      };
      unix.enable = true;
      unix.sshIntegration = true;
      unix.settings = {
        kanidm.pam_allowed_login_groups = cfg.loginGroups;
        # Plain names (mrossi, office), not mrossi@idm.example.com.
        uid_attr_map = "name";
        gid_attr_map = "name";
        home_alias = "name";
        default_shell = "/run/current-system/sw/bin/bash";
        use_etc_skel = true;
      };
    };
    # No local accounts to pick from: the login screen asks for the name.
    services.xserver.displayManager.lightdm.extraSeatDefaults = ''
      greeter-show-manual-login=true
      greeter-hide-users=true
    '';

    # ---- Disk unlock with Tang (+ TPM): the sealed key and the boot-stage network
    boot.initrd.clevis = lib.mkIf (unlock == "tang") {
      enable = true;
      useTang = true;
      devices.cryptroot.secretFile = "${secrets}/cryptroot.jwe";
    };
    meccanicos.initrdNetwork = lib.mkIf (unlock == "tang") true;
    # Away from the office network, don't wait long for it: the recovery key
    # is asked for instead.
    boot.initrd.systemd.network.wait-online = lib.mkIf (unlock == "tang") {
      anyInterface = true;
      timeout = 30;
    };
  };
}
