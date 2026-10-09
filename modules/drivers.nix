# Hardware support matching the EndeavourOS live ISO package list
# (https://github.com/endeavouros-team/EndeavourOS-ISO/blob/main/packages.x86_64).
# Each block notes the Arch packages it replaces.
{
  config,
  lib,
  pkgs,
  ...
}:
let
  tSh = import ./i18n-sh.nix pkgs;
  # "nvidia" or "open": which kernel driver should run NVIDIA GPUs (see below).
  # Its stdout is read by modprobe (below) and mos-about: only the help and
  # the error are translated, and only they load the translations.
  mos-gpu-driver = pkgs.writeShellScriptBin "mos-gpu-driver" ''
    if [ -n "''${1-}" ]; then
      ${tSh "mos-gpu-driver"}
    fi
    case "''${1-}" in
      "") ;;
      -h | --help | help)
        echo "$(T 'mos-gpu-driver - print which kernel driver runs NVIDIA GPUs: nvidia or open')"
        echo
        echo "  $(T 'mos-gpu-driver   (no options; meccanicos.gpu=nvidia|open at boot overrides it)')"
        exit 0 ;;
      *) Tf 'mos-gpu-driver: unknown option %s (mos-gpu-driver --help)\n' "$1" >&2; exit 2 ;;
    esac
    case " $(< /proc/cmdline) " in
      *" meccanicos.gpu=nvidia "*) echo nvidia; exit 0 ;;
      *" meccanicos.gpu=open "*) echo open; exit 0 ;;
    esac
    nvidia=0 other=0
    for d in /sys/bus/pci/devices/*; do
      read -r class < "$d/class" || continue
      [[ $class == 0x03* ]] || continue # display controllers only
      read -r vendor < "$d/vendor"
      read -r device < "$d/device"
      if [[ $vendor == 0x10de ]]; then
        ((device >= 0x1e00)) && nvidia=1 # Turing and newer: NVIDIA's open driver
      else
        other=1 # Intel/AMD/other GPU: hybrid laptop or iGPU in use
      fi
    done
    if ((nvidia && !other)); then echo nvidia; else echo open; fi
  '';
in
{
  # All kernel modules usable in the initrd for booting arbitrary hardware
  # (USB/SATA/NVMe/virtio/MMC controllers, keyboards, etc).
  hardware.enableAllHardware = true;

  # linux-firmware, sof-firmware, alsa-firmware, wireless-regdb ...
  # Redistributable firmware only (MeccanicOS ships nothing that can't be shared):
  # no Broadcom BT, b43 Wi-Fi, Xbox wireless dongle or FaceTime camera firmware.
  hardware.enableRedistributableFirmware = true;
  hardware.wirelessRegulatoryDatabase = true;

  # amd-ucode, intel-ucode
  hardware.cpu.intel.updateMicrocode = true;
  hardware.cpu.amd.updateMicrocode = true;

  # mesa, vulkan-intel, vulkan-radeon, vulkan-nouveau, vulkan-swrast,
  # vulkan-virtio (all part of mesa in nixpkgs). No 32-bit variants: they are
  # only for Steam/Wine and cost ~1.3 GB (second Mesa + LLVM, NVIDIA lib32).
  hardware.graphics = {
    enable = true;
    enable32Bit = false;
    extraPackages = with pkgs; [
      intel-media-driver # intel-media-driver (VA-API, Broadwell+)
      intel-vaapi-driver # libva-intel-driver (older Intel)
      vpl-gpu-rt # vpl-gpu-rt (Intel QuickSync)
      libvdpau-va-gl
    ];
  };
  # xf86-video-amdgpu / ati / intel / nouveau / vmware / qxl, modesetting,
  # plus NVIDIA's driver. Xorg tries each in turn; "nvidia" only works when
  # its kernel module was loaded (see below).
  services.xserver.videoDrivers = [
    "nvidia"
    "amdgpu"
    "radeon"
    "nouveau"
    "modesetting"
    "fbdev"
  ];

  # nvidia-open + nvidia-utils, in the one and only boot entry.
  # At boot, mos-gpu-driver picks the kernel driver for NVIDIA cards:
  #   - NVIDIA's open driver when the only GPU is an NVIDIA Turing (GTX 16xx /
  #     RTX 20xx) or newer card;
  #   - nouveau otherwise: older NVIDIA cards, and laptops whose panel hangs
  #     off an Intel/AMD GPU next to the NVIDIA one.
  # Override with the kernel parameter meccanicos.gpu=nvidia or meccanicos.gpu=open.
  hardware.nvidia = {
    open = true;
    modesetting.enable = true;
    nvidiaSettings = true;
    package = config.boot.kernelPackages.nvidiaPackages.stable;
  };
  # The NVIDIA module blacklists nouveau; the install hooks below decide
  # instead. (usblp: from printing.nix, which ipp-usb replaces.)
  boot.blacklistedKernelModules = lib.mkForce [
    "nova_core"
    "nvidiafb"
    "usblp"
  ];
  boot.extraModprobeConfig =
    let
      modprobe = "${pkgs.kmod}/bin/modprobe";
      when = driver: module: ''
        install ${module} if [ "$(${mos-gpu-driver}/bin/mos-gpu-driver)" = ${driver} ]; then ${modprobe} --ignore-install ${module} $CMDLINE_OPTS; fi
      '';
    in
    lib.concatMapStrings (when "nvidia") [
      "nvidia"
      "nvidia_modeset"
      "nvidia_drm"
      "nvidia_uvm"
    ]
    + when "open" "nouveau";
  # Audio: pipewire, pipewire-alsa/-pulse/-jack, wireplumber, rtkit
  services.pulseaudio.enable = false;
  security.rtkit.enable = true;
  services.pipewire = {
    enable = true;
    alsa.enable = true;
    alsa.support32Bit = false; # 32-bit PipeWire + FFmpeg, … (~0.6 GB) only for Steam/Wine, like enable32Bit above
    pulse.enable = true;
    jack.enable = true;
    wireplumber.enable = true;
  };

  # Network: networkmanager (+openvpn/openconnect/vpnc), modemmanager,
  # usb_modeswitch, nss-mdns, wpa_supplicant
  networking.networkmanager.plugins = with pkgs; [
    networkmanager-openvpn
    networkmanager-openconnect
    networkmanager-l2tp
  ];
  networking.modemmanager.enable = true;
  hardware.usb-modeswitch.enable = true;
  services.avahi = {
    enable = true;
    nssmdns4 = true;
  };
  # Inbound: nothing unsolicited, except SSH (installed systems, keys only)
  # and mDNS 5353 (network printer/scanner discovery). Outbound: all allowed,
  # so browsing, Nix downloads and upgrades just work. Pings are ignored.
  networking.firewall = {
    enable = true;
    allowPing = false;
  };

  # Bluetooth: bluez, bluez-utils
  hardware.bluetooth.enable = true;
  hardware.bluetooth.powerOnBoot = true;

  # power-profiles-daemon, fwupd, smartmontools, gpm, upower
  services.power-profiles-daemon.enable = true;
  services.upower.enable = true;
  services.fwupd.enable = true;
  services.gpm.enable = true;

  # Filesystems: btrfs-progs, dosfstools, e2fsprogs, exfatprogs, f2fs-tools,
  # jfsutils, lvm2, mdadm, nfs-utils, nilfs-utils, ntfs-3g, xfsprogs
  boot.supportedFilesystems = [
    "btrfs"
    "vfat"
    "exfat"
    "ext4"
    "f2fs"
    "jfs"
    "nfs"
    "nilfs2"
    "ntfs"
    "xfs"
  ];
  services.lvm.enable = true;
  boot.swraid.enable = true;
  boot.swraid.mdadmConf = "PROGRAM ${pkgs.coreutils}/bin/true"; # silence mdadm warning

  environment.systemPackages = with pkgs; [
    mos-gpu-driver # prints the NVIDIA driver choice (see above), for support
    # filesystem tools
    btrfs-progs
    dosfstools
    e2fsprogs
    exfatprogs
    f2fs-tools
    jfsutils
    lvm2
    mtools
    nfs-utils
    nilfs-utils
    ntfs3g
    xfsprogs
    cryptsetup
    gptfdisk
    parted
    gparted
    # hardware inspection: lsscsi, sg3_utils, smartmontools, usbutils,
    # dmidecode, hwinfo, inxi, hdparm, ethtool
    lsscsi
    sg3_utils
    smartmontools
    usbutils
    pciutils
    dmidecode
    hwinfo
    inxi
    hdparm
    ethtool
    efibootmgr
    lshw
    # glxinfo only (OpenGL diagnostics), not the rest of mesa-demos
    (runCommand "glxinfo-${mesa-demos.version}" { } ''
      mkdir -p $out/bin
      cp ${mesa-demos}/bin/glxinfo $out/bin/glxinfo
    '')
    vulkan-tools
    libva-utils
    # audio: alsa-utils, pavucontrol
    alsa-utils
    pavucontrol
    # gstreamer codecs: gst-libav, gst-plugins-bad/ugly, gst-plugin-va
    gst_all_1.gst-libav
    gst_all_1.gst-plugins-good
    gst_all_1.gst-plugins-bad
    gst_all_1.gst-plugins-ugly
    gst_all_1.gst-vaapi
    # bluetooth GUI, network applet
    blueman
    networkmanagerapplet
  ];
}
