# hardening: kernel and network settings that make attacks harder without
# changing what MeccanicOS does. Hardware support comes first: no driver, device
# or firmware is affected; nor hibernation, Brave's sandbox, podman, VMs; the riskier ideas (a
# hardened allocator, the hardened kernel, lockdown, firejail) are left out
# (README: Security). meccanicos.hardening.enable = false turns it all off.
{
  config,
  lib,
  pkgs,
  ...
}:
let
  # Network protocols no device needs, old or rare, where kernel bugs have
  # been found: not loadable at all (a plain blacklist only stops them
  # loading by themselves). Hardware comes first, so nothing a device uses is
  # here: not ATM (USB DSL modems), the amateur radio protocols, 802.15.4
  # (Zigbee/Thread sticks), serial HDLC, nor any filesystem (old disks, CDs).
  unused = [
    "dccp"
    "sctp"
    "rds"
    "tipc"
    "x25"
    "decnet"
    "econet"
    "ipx"
    "appletalk"
    "psnap"
    "p8023"
    "p8022"
  ];
in
{
  options.meccanicos.hardening.enable = lib.mkOption {
    type = lib.types.bool;
    default = true;
    description = "Kernel, memory and network hardening that keeps everything working.";
  };

  config = lib.mkIf config.meccanicos.hardening.enable {
    boot.kernel.sysctl = {
      # What the kernel shows: no kernel addresses, no kernel log for users.
      "kernel.kptr_restrict" = 2;
      "kernel.dmesg_restrict" = 1;
      # eBPF only for root, and its compiled code hardened.
      "kernel.unprivileged_bpf_disabled" = 1;
      "net.core.bpf_jit_harden" = 2;
      # A program may only debug its own children (gdb ./prog still works).
      "kernel.yama.ptrace_scope" = 1;
      # No replacing the running kernel (kexec).
      "kernel.kexec_load_disabled" = 1;
      # Files in shared folders like /tmp: no writing others' FIFOs and files.
      "fs.protected_fifos" = 2;
      "fs.protected_regular" = 2;
      "fs.protected_symlinks" = 1;
      "fs.protected_hardlinks" = 1;
      # No core dumps of setuid programs (they may hold secrets).
      "fs.suid_dumpable" = 0;

      # ASLR: on (the default, made sure of) and with all the randomness the
      # CPU allows.
      "kernel.randomize_va_space" = 2;
      "vm.mmap_rnd_bits" = 32;
      "vm.mmap_rnd_compat_bits" = 16;

      # Network: no ICMP redirects or source routing (a router telling us
      # where to send traffic), SYN-flood cookies. Reverse-path filtering is
      # the firewall's (networking.firewall.checkReversePath).
      "net.ipv4.conf.all.accept_redirects" = 0;
      "net.ipv4.conf.default.accept_redirects" = 0;
      "net.ipv4.conf.all.secure_redirects" = 0;
      "net.ipv4.conf.default.secure_redirects" = 0;
      "net.ipv6.conf.all.accept_redirects" = 0;
      "net.ipv6.conf.default.accept_redirects" = 0;
      "net.ipv4.conf.all.send_redirects" = 0;
      "net.ipv4.conf.default.send_redirects" = 0;
      "net.ipv4.conf.all.accept_source_route" = 0;
      "net.ipv4.conf.default.accept_source_route" = 0;
      "net.ipv6.conf.all.accept_source_route" = 0;
      "net.ipv6.conf.default.accept_source_route" = 0;
      "net.ipv4.tcp_syncookies" = 1;
      "net.ipv4.tcp_rfc1337" = 1;
      "net.ipv4.icmp_echo_ignore_broadcasts" = 1;
    };

    # Memory: freshly allocated memory is zeroed, kernel caches of the same
    # size are kept apart, page and stack layouts randomized; no legacy
    # vsyscall page. About 1-3% CPU; drivers don't notice. (Not here:
    # init_on_free, the slowest; lockdown, which would stop hibernation and
    # unsigned drivers such as NVIDIA's; debugfs=off and ldisc_autoload, which
    # some hardware tools and serial devices use.)
    boot.kernelParams = [
      "slab_nomerge"
      "init_on_alloc=1"
      "page_alloc.shuffle=1"
      "randomize_kstack_offset=on"
      "vsyscall=none"
    ];

    boot.extraModprobeConfig = lib.concatMapStrings (m: "install ${m} ${pkgs.coreutils}/bin/false\n") unused;

    # dbus-broker: the same D-Bus, faster and sturdier (Fedora's and Arch's).
    services.dbus.implementation = "broker";
  };
}
