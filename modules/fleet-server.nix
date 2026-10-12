# The fleet server (EXPERIMENTAL): everything an organization's managed
# MeccanicOS computers need, on one MeccanicOS machine. On by itself when
# /etc/nixos/fleet-server.toml exists; `sudo mos-fleet server init` writes it
# and does the rest (accounts, repository, enroll secret).
#
#   idm.DOMAIN    Kanidm    people, groups, passwords, passkeys
#   git.DOMAIN    Forgejo   the fleet repository (fleet/config)
#   cache.DOMAIN  Harmonia  the systems built by fleet-build, signed
#   fleet.DOMAIN  Fleet     inventory (+ Redis)
#
# One database server, MySQL 8.4, for Forgejo and Fleet: Fleet supports
# nothing else (no PostgreSQL, no MariaDB), and Forgejo supports MySQL too.
#   tang.DOMAIN   Tang      automatic disk unlock, office network only (port 7654)
#
# HTTPS through one nginx, with the organization's own CA: made at boot by
# meccanicos-fleet-secrets in /var/lib/meccanicos-fleet (with every other key),
# server certificate renewed when it is about to expire. Back that folder up,
# and /var/lib/tang: see docs/fleet/ADMIN-GUIDE.md.
#
# fleet-server.toml:
#   domain = "corp.example.com"            # the five names above, under it
#   organization = "Example Corp"
#   lan = ["10.0.0.0/8"]                   # who may reach Tang
{
  config,
  lib,
  pkgs,
  meccanicosRoot,
  ...
}:
let
  file = meccanicosRoot + "/fleet-server.toml";
  enabled = builtins.pathExists file;
  s = if enabled then builtins.fromTOML (builtins.readFile file) else { };
  domain = s.domain or "example.com";
  organization = s.organization or "MeccanicOS fleet";
  lan =
    s.lan or [
      "10.0.0.0/8"
      "172.16.0.0/12"
      "192.168.0.0/16"
    ];
  state = "/var/lib/meccanicos-fleet";
  tlsDir = "${state}/tls";
  # The CA, copied next to fleet-server.toml by mos-fleet server init, so that
  # this machine trusts its own services too.
  caFile = meccanicosRoot + "/ca.crt";
  repoUrl = "https://git.${domain}/fleet/config.git";
  forgejo = config.services.forgejo;
  tls = {
    forceSSL = true;
    sslCertificate = "${tlsDir}/server-chain.pem";
    sslCertificateKey = "${tlsDir}/server.key";
  };

  # Forgejo's command line, as its own user, with its settings.
  fleet-forgejo = pkgs.writeShellScriptBin "fleet-forgejo" ''
    exec ${pkgs.util-linux}/bin/runuser -u ${forgejo.user} -- \
      ${forgejo.package}/bin/forgejo --work-path ${forgejo.stateDir} \
      --config ${forgejo.customDir}/conf/app.ini "$@"
  '';

  # mos-fleet: on every installed system (the server, and admin computers).
  mos-fleet = pkgs.writeShellScriptBin "mos-fleet" ''
    export PATH="${
      lib.makeBinPath (
        with pkgs;
        [
          git
          age
          openssh
          openssl
          curl
          util-linux
          coreutils
        ]
      )
    }:$PATH"
    exec ${pkgs.python3}/bin/python3 ${../scripts/mos-fleet.py} "$@"
  '';
in
{
  config = lib.mkMerge [
    { environment.systemPackages = [ mos-fleet ]; }

    (lib.mkIf enabled {
      environment.etc."meccanicos/fleet-server".text = ''
        domain=${domain}
        organization=${organization}
        repo=${repoUrl}
        state=${state}
      '';
      environment.systemPackages = [
        fleet-forgejo
        pkgs.fleetctl
        pkgs.tang
        config.services.kanidm.package
      ];
      security.pki.certificateFiles = lib.optional (builtins.pathExists caFile) caFile;
      # Its own names, whatever the company DNS says (set up, builds, checks).
      networking.hosts."127.0.0.1" = map (n: "${n}.${domain}") [
        "idm"
        "git"
        "cache"
        "fleet"
        "tang"
      ];
      networking.firewall.allowedTCPPorts = [
        80
        443
        7654
      ];

      # ---- Keys and certificates, made once (server certificate: renewed) ----
      users.groups.certs.members = [
        "nginx"
        "kanidm"
      ];
      systemd.services.meccanicos-fleet-secrets = {
        description = "Fleet server keys and certificates";
        wantedBy = [ "multi-user.target" ];
        before = [
          "nginx.service"
          "kanidm.service"
          "harmonia.service"
          "fleet.service"
          "fleet-db-setup.service"
        ];
        requiredBy = [
          "nginx.service"
          "kanidm.service"
          "harmonia.service"
          "fleet.service"
        ];
        path = [
          pkgs.openssl
          pkgs.coreutils
          config.nix.package
        ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
        };
        script = ''
          set -euo pipefail
          umask 077
          mkdir -p ${tlsDir}
          cd ${tlsDir}
          if [ ! -s ca.crt ]; then
            openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
              -days 3650 -subj "/CN=${organization} CA" \
              -addext "basicConstraints=critical,CA:TRUE" \
              -addext "keyUsage=critical,keyCertSign,cRLSign" \
              -keyout ca.key -out ca.crt
          fi
          # The server certificate: *.${domain}, 2 years, renewed 30 days before.
          if [ ! -s server.crt ] || ! openssl x509 -checkend 2592000 -noout -in server.crt; then
            openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
              -subj "/CN=*.${domain}" -keyout server.key -out server.csr
            printf '%s\n' "subjectAltName=DNS:*.${domain},DNS:${domain}" \
              "basicConstraints=critical,CA:FALSE" "keyUsage=critical,digitalSignature" \
              "extendedKeyUsage=serverAuth" > server.ext
            openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
              -days 730 -extfile server.ext -out server.crt
            cat server.crt ca.crt > server-chain.pem
          fi
          chown root:certs . server.key server-chain.pem
          chmod 750 .
          chmod 640 server.key
          chmod 644 ca.crt server.crt server-chain.pem
          cd ${state}
          chmod 755 .
          [ -s cache.sec ] || nix-store --generate-binary-cache-key cache.${domain}-1 cache.sec cache.pub
          chmod 644 cache.pub
          [ -s fleet-mysql.pass ] || openssl rand -hex 24 > fleet-mysql.pass
          chown root:fleet fleet-mysql.pass
          chmod 640 fleet-mysql.pass
          [ -s fleet.env ] || echo "FLEET_SERVER_PRIVATE_KEY=$(openssl rand -base64 32)" > fleet.env
          chmod 600 fleet.env
        '';
      };
      systemd.tmpfiles.rules = [ "d ${state} 0755 root root -" ];

      # ---- HTTPS front door ----------------------------------------------------
      services.nginx = {
        enable = true;
        recommendedProxySettings = true;
        recommendedTlsSettings = true;
        virtualHosts = {
          "idm.${domain}" = tls // {
            locations."/".proxyPass = "https://127.0.0.1:8443";
          };
          "git.${domain}" = tls // {
            locations."/".proxyPass = "http://127.0.0.1:3000";
            extraConfig = "client_max_body_size 512M;";
          };
          "cache.${domain}" = tls // {
            locations."/".proxyPass = "http://127.0.0.1:5000";
          };
          "fleet.${domain}" = tls // {
            locations."/" = {
              proxyPass = "http://127.0.0.1:8080";
              proxyWebsockets = true;
            };
          };
        };
      };

      # ---- Kanidm: people and groups -----------------------------------------
      services.kanidm = {
        package = pkgs.kanidm_1_11; # upgrade one minor version at a time
        server.enable = true;
        server.settings = {
          origin = "https://idm.${domain}";
          domain = "idm.${domain}";
          bindaddress = "127.0.0.1:8443";
          tls_chain = "${tlsDir}/server-chain.pem";
          tls_key = "${tlsDir}/server.key";
        };
        client.enable = true; # the `kanidm` command, used by mos-fleet
        client.settings.uri = "https://idm.${domain}";
      };

      # ---- Forgejo: the fleet repository --------------------------------------
      services.forgejo = {
        enable = true;
        database.type = "mysql"; # its own database and socket-authenticated user, in the shared MySQL
        settings = {
          server = {
            DOMAIN = "git.${domain}";
            ROOT_URL = "https://git.${domain}/";
            HTTP_ADDR = "127.0.0.1";
            HTTP_PORT = 3000;
          };
          service.DISABLE_REGISTRATION = true; # accounts: mos-fleet / the admin page
          session.COOKIE_SECURE = true;
        };
      };

      # ---- Harmonia: the binary cache -----------------------------------------
      services.harmonia.cache = {
        enable = true;
        signKeyPaths = [ "${state}/cache.sec" ];
        settings.bind = "127.0.0.1:5000";
      };

      # ---- fleet-build: every machine's system, built for the cache -----------
      # Every 5 minutes: fetch the fleet repository and build each machine.
      # Result per machine in /var/lib/fleet-build/status/<host> (mos-fleet status).
      systemd.services.fleet-build = {
        description = "Build every fleet machine's system for the cache";
        path = [
          pkgs.git
          pkgs.jq
          pkgs.coreutils
          config.nix.package
        ];
        environment.GIT_SSL_CAINFO = config.security.pki.caBundle;
        serviceConfig = {
          Type = "oneshot";
          StateDirectory = "fleet-build";
        };
        script = ''
          set -uo pipefail
          token=${state}/repo.token
          [ -s "$token" ] || { echo "No repository yet (mos-fleet server init)."; exit 0; }
          cd /var/lib/fleet-build
          auth="http.extraHeader=Authorization: token $(cat "$token")"
          if [ ! -d repo ]; then
            git -c "$auth" clone -q ${repoUrl} repo || exit 1
          fi
          cd repo
          git -c "$auth" fetch -q origin || exit 1
          git reset -q --hard origin/HEAD
          mkdir -p ../roots ../status
          hosts=$(nix eval --json .#nixosConfigurations --apply builtins.attrNames | jq -r '.[]') || exit 1
          failed=0
          for h in $hosts; do
            rev=$(git rev-parse --short HEAD)
            if [ "$(cut -f1 "../status/$h" 2>/dev/null)" = "ok $rev" ]; then continue; fi
            echo "building $h ($rev)"
            if out=$(nix build ".#nixosConfigurations.$h.config.system.build.toplevel" \
                --out-link "../roots/$h" 2>&1); then
              printf 'ok %s\t%s\n' "$rev" "$(date -Is)" > "../status/$h"
            else
              echo "FAILED: $h"
              echo "$out" | tail -20
              printf 'failed %s\t%s\n%s\n' "$rev" "$(date -Is)" "$(echo "$out" | tail -20)" > "../status/$h"
              failed=1
            fi
          done
          exit $failed
        '';
      };
      systemd.timers.fleet-build = {
        wantedBy = [ "timers.target" ];
        timerConfig = {
          OnBootSec = "5min";
          OnUnitActiveSec = "5min";
        };
      };

      # ---- The database server: MySQL 8.4, for Fleet and Forgejo -----------------
      # (Fleet supports MySQL 8 only: not MariaDB, which Forgejo's module would pick.)
      services.mysql = {
        enable = true;
        package = pkgs.mysql84;
        settings.mysqld.bind-address = "127.0.0.1";
        ensureDatabases = [ "fleet" ];
      };
      services.redis.servers.fleet = {
        enable = true;
        port = 6379;
        bind = "127.0.0.1";
      };
      users.users.fleet = {
        isSystemUser = true;
        group = "fleet";
      };
      users.groups.fleet = { };
      systemd.services.fleet-db-setup = {
        description = "Fleet's MySQL account";
        after = [
          "mysql.service"
          "meccanicos-fleet-secrets.service"
        ];
        requires = [ "mysql.service" ];
        before = [ "fleet.service" ];
        requiredBy = [ "fleet.service" ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
        };
        script = ''
          pass=$(cat ${state}/fleet-mysql.pass)
          ${config.services.mysql.package}/bin/mysql -u root <<SQL
          CREATE USER IF NOT EXISTS 'fleet'@'127.0.0.1' IDENTIFIED BY '$pass';
          ALTER USER 'fleet'@'127.0.0.1' IDENTIFIED BY '$pass';
          GRANT ALL PRIVILEGES ON fleet.* TO 'fleet'@'127.0.0.1';
          SQL
        '';
      };
      systemd.services.fleet = {
        description = "Fleet device management server";
        after = [
          "network.target"
          "mysql.service"
          "redis-fleet.service"
          "fleet-db-setup.service"
        ];
        requires = [
          "mysql.service"
          "redis-fleet.service"
        ];
        wantedBy = [ "multi-user.target" ];
        environment = {
          FLEET_MYSQL_ADDRESS = "127.0.0.1:3306";
          FLEET_MYSQL_DATABASE = "fleet";
          FLEET_MYSQL_USERNAME = "fleet";
          FLEET_MYSQL_PASSWORD_PATH = "${state}/fleet-mysql.pass";
          FLEET_REDIS_ADDRESS = "127.0.0.1:6379";
          FLEET_SERVER_ADDRESS = "127.0.0.1:8080";
          FLEET_SERVER_TLS = "false"; # nginx does HTTPS
          FLEET_LOGGING_JSON = "true";
        };
        serviceConfig = {
          User = "fleet";
          Group = "fleet";
          EnvironmentFile = "${state}/fleet.env";
          ExecStartPre = "${pkgs.fleet}/bin/fleet prepare db --no-prompt";
          ExecStart = "${pkgs.fleet}/bin/fleet serve";
          Restart = "on-failure";
          RestartSec = 10;
        };
      };

      # ---- Tang: automatic disk unlock, office network only --------------------
      services.tang = {
        enable = true;
        ipAddressAllow = lan ++ [
          "127.0.0.0/8" # mos-fleet (tang-show-keys)
          "::1/128"
        ];
      };

      # ---- Database dumps, for the backup (/var/backup) -------------------------
      services.mysqlBackup = {
        enable = true;
        databases = [
          "fleet"
          forgejo.database.name
        ];
      };
    })
  ];
}
