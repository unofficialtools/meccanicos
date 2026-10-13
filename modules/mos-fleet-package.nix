# mos-fleet: the fleet tools (scripts/mos_fleet), one Python package, several
# commands:
#   mos-fleet          the admins' command line (and `server …` at the server's console)
#   mos-fleet-agent    the agent on managed computers (systemd)
#   mos-passwd         change your password on every computer of the organization
#   mos-fleet-serve    the server's forced SSH command (sshd runs it)
#   mos-fleet-keys     the server's AuthorizedKeysCommand
#   mos-fleet-hook     the server repository's git hooks
#   mos-fleet-server   the server's services (setup, build, prune; as fleet)
# Python runs isolated (-E -s): no PYTHON* variables, no user site, whoever
# starts it (sshd, git, a user).
{
  lib,
  runCommand,
  python3,
  git,
  openssh,
  age,
  mkpasswd,
  util-linux,
  coreutils,
  gnutar,
  iproute2,
  shadow,
  libxcrypt,
  tang,
}:
let
  py = python3.withPackages (p: [ p.pydal ]);
  src = runCommand "mos-fleet-src" { } ''
    mkdir -p $out
    cp -r ${../scripts/mos_fleet} $out/mos_fleet
  '';
  path = lib.makeBinPath [
    git
    openssh
    age
    mkpasswd
    util-linux
    coreutils
    gnutar
    iproute2
    shadow
    tang
  ];
  # nix and systemd's tools: the running system's own (/run/current-system/sw/bin).
  commands = {
    mos-fleet = "cli:main";
    mos-fleet-agent = "agent:main";
    mos-passwd = "agent:passwd_main";
    mos-fleet-serve = "server:serve_main";
    mos-fleet-keys = "keys:main";
    mos-fleet-hook = "server:hook_main";
    mos-fleet-server = "server:service_main";
  };
  wrapper =
    name: target:
    let
      parts = lib.splitString ":" target;
    in
    ''
      cat > $out/bin/${name} <<EOF
      #!/bin/sh
      export PATH="${path}:/run/wrappers/bin:/run/current-system/sw/bin"
      export MOS_FLEET_SERVE="$out/bin/mos-fleet-serve"
      export MOS_FLEET_HOOK="$out/bin/mos-fleet-hook"
      export MOS_FLEET_LIBCRYPT="${libxcrypt}/lib/libcrypt.so.2"
      exec ${py}/bin/python3 -E -s -c 'import sys; sys.path.insert(0, "${src}"); from mos_fleet.${builtins.elemAt parts 0} import ${builtins.elemAt parts 1} as m; sys.exit(m())' "\$@"
      EOF
      chmod 755 $out/bin/${name}
    '';
in
runCommand "mos-fleet"
  {
    meta.description = "MeccanicOS fleet management: git repository, SSH, SQLite";
    passthru = { inherit src py; };
  }
  ''
    mkdir -p $out/bin
    ${lib.concatStrings (lib.mapAttrsToList wrapper commands)}
  ''
