# dns: names are looked up through a local cache (systemd-resolved, on
# 127.0.0.53), so a name looked up once answers at once. It asks the servers
# the network hands out, so hotel/café sign-in pages, VPN-only names and the
# router's names (nas.lan) work; public resolvers (Cloudflare, Google) only
# when a network gives none. *.localhost answers 127.0.0.1 (local web apps);
# .local names go through Avahi (printers, fleet servers). With a cable and
# Wi-Fi both connected, the cable's servers answer.
# meccanicos.dns.public (mos-config network.public_dns): always the public
# resolvers, over every connection's (Wi-Fi, wired, VPN); then sign-in pages
# may not appear and names only a VPN or the router knows are not found.
{
  config,
  lib,
  ...
}:
let
  cfg = config.meccanicos.dns;
in
{
  options.meccanicos.dns = {
    public = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Always use the public resolvers, never the network's.";
    };
    servers = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [
        "1.1.1.1"
        "8.8.8.8"
        "2606:4700:4700::1111"
        "2001:4860:4860::8888"
      ];
      description = "The public resolvers, in order (IPv4 or IPv6 addresses).";
    };
  };

  config = lib.mkMerge [
    {
      services.resolved = {
        enable = true; # NetworkManager hands it DNS (networking.networkmanager.dns)
        settings.Resolve = {
          Cache = true;
          FallbackDNS = cfg.servers;
          # Avahi answers .local (drivers.nix, printing.nix); LLMNR is a
          # Windows-era protocol any machine on the network can answer falsely.
          MulticastDNS = false;
          LLMNR = false;
        };
      };
      # Wired and Wi-Fi both up: names go to the wired network's servers, not
      # both. Wi-Fi's priority is worse (bigger) than the default 100, so only
      # the wired connection gets the catch-all "~."; Wi-Fi still answers its
      # own search domains, and takes over when the cable comes out.
      networking.networkmanager.settings."connection-wifi-dns" = {
        match-device = "type:wifi";
        "ipv4.dns-priority" = 200;
        "ipv6.dns-priority" = 200;
      };
    }
    (lib.mkIf cfg.public {
      networking.nameservers = cfg.servers;
      # Overrides every connection's DNS servers.
      networking.networkmanager.settings."global-dns-domain-*".servers =
        lib.concatStringsSep "," cfg.servers;
    })
  ];
}
