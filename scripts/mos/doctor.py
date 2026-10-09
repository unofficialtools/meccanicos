"""mos-doctor - find and fix common problems: network, Bluetooth, sound,
display, disk.

  mos-doctor                 check everything, offer to fix what's wrong;
                               if nothing is, ask what isn't working
  mos-doctor AREA            check one area: network (wifi), bluetooth,
                               sound (audio), display (video), disk
  mos-doctor AREA --reset    also restart it from scratch (service, driver)
  mos-doctor --check [--json]  only report, change nothing
  mos-doctor --fix           fix everything it can without asking
  mos-doctor --report [FILE] save a report for asking for help (serial
                               numbers and addresses left out)

Every fix is shown before it is made, asks first (unless --fix), and is
written to ~/.local/state/meccanicos/doctor.log.
"""

import datetime
import glob
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

import common as c
from mos_i18n import translator, N_  # noqa: E402  (common puts scripts/lib on sys.path)

T = translator("mos-doctor")
RESET = "reset requested"  # what= of a reset asked for (--reset): not a problem, never shown


class Problem:
    """What is wrong; the fix (a description and a function), if there is one."""

    def __init__(self, area, what, fix=None, how=None, advice=None):
        self.area, self.what, self.fix, self.how, self.advice = area, what, fix, how, advice


# ---- network ------------------------------------------------------------------------
def rfkill():
    """{type: (soft, hard)} blocked, from rfkill."""
    out = c.output("rfkill", "-rn", "-o", "TYPE,SOFT,HARD")
    blocked = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3:
            t, soft, hard = parts
            s, h = blocked.get(t, (False, False))
            blocked[t] = (s or soft == "blocked", h or hard == "blocked")
    return blocked


def nm_devices():
    """[(device, type, state)] from NetworkManager."""
    out = c.output("nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device")
    return [tuple(l.split(":")[:3]) for l in out.splitlines() if l.count(":") >= 2]


def driverless(kind):
    """PCI devices of a kind ("Network", "Audio", "VGA|3D") with no driver."""
    out, found, dev = c.output("lspci", "-k"), [], None
    for line in out.splitlines():
        if not line.startswith("\t"):
            dev = line if re.search(kind, line) else None
            if dev:
                found.append(dev)
        elif dev and "Kernel driver in use" in line:
            found.remove(dev)
            dev = None
    return [re.sub(r"^\S+\s+", "", d) for d in found]


def firmware_errors(word=""):
    log = c.output("journalctl", "-k", "-b", "--no-pager", "-q")
    lines = [l for l in log.splitlines() if re.search(r"firmware: failed to load|Direct firmware load .* failed", l)]
    return [l for l in lines if word in l.lower()][-3:]


def driver_of(dev):
    link = f"/sys/class/net/{dev}/device/driver/module"
    return os.path.basename(os.readlink(link)) if os.path.islink(link) else None


def reload_module(mod):
    c.run("modprobe", "-r", mod, sudo=True, check=True)
    c.run("modprobe", mod, sudo=True, check=True)


def reconnect():
    for name in c.output("nmcli", "-t", "-f", "NAME", "connection", "show", "--active").splitlines():
        c.run("nmcli", "connection", "down", name)
        c.run("nmcli", "connection", "up", name, check=True)


def check_network(reset=False):
    probs = []
    if c.run("systemctl", "is-active", "--quiet", "NetworkManager")[0] != 0:
        probs.append(Problem("network", T("the network service (NetworkManager) is not running"),
                             lambda: c.run("systemctl", "restart", "NetworkManager", sudo=True, check=True),
                             T("restart NetworkManager")))
        return probs
    soft, hard = rfkill().get("wlan", (False, False))
    if hard:
        probs.append(Problem("network", T("Wi-Fi is switched off by a key or switch on the computer"),
                             advice=T("press the Wi-Fi key (often Fn + an antenna key) or flip the switch")))
    elif soft:
        probs.append(Problem("network", T("Wi-Fi is turned off (blocked)"),
                             lambda: c.run("rfkill", "unblock", "wlan", sudo=True, check=True), T("unblock Wi-Fi")))
    if c.output("nmcli", "radio", "wifi") == "disabled" and not hard:
        probs.append(Problem("network", T("Wi-Fi is turned off in the network settings"),
                             lambda: c.run("nmcli", "radio", "wifi", "on", check=True), T("turn Wi-Fi on")))
    devs = nm_devices()
    wifi = [d for d in devs if d[1] == "wifi"]
    if not wifi:
        missing = driverless("Network")
        if missing:
            fw = firmware_errors()
            probs.append(Problem("network", T("Wi-Fi hardware without a driver: {device}").format(device=missing[0]),
                                 advice=T("missing firmware: {error}").format(error=fw[-1].split("]")[-1].strip())
                                 if fw else
                                 T("it may need a driver that isn't included; mos-doctor --report helps ask for one")))
    for dev, _, state in wifi + [d for d in devs if d[1] == "ethernet"]:
        if state == "unmanaged":
            probs.append(Problem("network", T("{device} is not managed by NetworkManager").format(device=dev),
                                 lambda d=dev: c.run("nmcli", "device", "set", d, "managed", "yes", check=True),
                                 T("let NetworkManager manage {device}").format(device=dev)))
        elif state == "unavailable" and not soft and not hard and wifi and dev == wifi[0][0]:
            mod = driver_of(dev)
            if mod:
                probs.append(Problem("network", T("the Wi-Fi card ({device}) is not ready").format(device=dev),
                                     lambda m=mod: reload_module(m), T("reload its driver ({driver})").format(driver=mod)))
    connected = any(state == "connected" for _, _, state in devs)
    if connected:
        state = c.output("nmcli", "networking", "connectivity", "check")
        if state == "portal":
            probs.append(Problem("network", T("connected, but the network wants you to sign in (a hotel/café page)"),
                                 advice=T("open the Web Browser (or mos-config network signin): the sign-in page "
                                          "should appear")))
        elif state in ("none", "limited"):
            probs.append(Problem("network", T("connected, but no internet"), reconnect, T("reconnect")))
        elif not c.output("getent", "hosts", "nixos.org"):
            probs.append(Problem("network", T("internet works, but names (like nixos.org) are not found (DNS)"),
                                 lambda: c.run("systemctl", "restart", "NetworkManager", sudo=True, check=True),
                                 T("restart NetworkManager")))
    elif wifi and not any(p.area == "network" for p in probs):
        probs.append(Problem("network", T("not connected to any network"),
                             advice=T("pick a network from the network icon in the top bar, or in mos-config")))
    if reset and wifi:
        mod = driver_of(wifi[0][0])
        probs.append(Problem("network", RESET,
                             lambda m=mod: (c.run("systemctl", "restart", "NetworkManager", sudo=True, check=True),
                                            m and reload_module(m)),
                             T("restart NetworkManager and reload the Wi-Fi driver ({driver})").format(driver=mod or "?")))
    return probs


# ---- bluetooth ----------------------------------------------------------------------
def check_bluetooth(reset=False):
    probs = []
    soft, hard = rfkill().get("bluetooth", (False, False))
    if hard:
        probs.append(Problem("bluetooth", T("Bluetooth is switched off by a key or switch"),
                             advice=T("press the Bluetooth/airplane key (often Fn + a key)")))
    elif soft:
        probs.append(Problem("bluetooth", T("Bluetooth is turned off (blocked)"),
                             lambda: c.run("rfkill", "unblock", "bluetooth", sudo=True, check=True),
                             T("unblock Bluetooth")))
    if c.run("systemctl", "is-active", "--quiet", "bluetooth")[0] != 0:
        probs.append(Problem("bluetooth", T("the Bluetooth service is not running"),
                             lambda: c.run("systemctl", "restart", "bluetooth", sudo=True, check=True),
                             T("restart it")))
    elif not c.output("bluetoothctl", "list"):
        if not soft and not hard:
            loaded = "btusb" in c.output("lsmod")
            probs.append(Problem("bluetooth", T("no Bluetooth adapter found"),
                                 (lambda: reload_module("btusb")) if loaded else None,
                                 T("reload the Bluetooth driver (btusb)"),
                                 None if loaded else T("this computer may not have Bluetooth")))
    elif "Powered: no" in c.output("bluetoothctl", "show"):
        probs.append(Problem("bluetooth", T("the Bluetooth adapter is off"),
                             lambda: c.run("bluetoothctl", "power", "on", check=True), T("turn it on")))
    if reset:
        probs.append(Problem("bluetooth", RESET,
                             lambda: (c.run("systemctl", "restart", "bluetooth", sudo=True, check=True),
                                      "btusb" in c.output("lsmod") and reload_module("btusb")),
                             T("restart Bluetooth and reload its driver")))
    return probs


# ---- sound --------------------------------------------------------------------------
AUDIO_SERVICES = ["pipewire", "pipewire-pulse", "wireplumber"]


def restart_audio():
    c.run("systemctl", "--user", "restart", *AUDIO_SERVICES, check=True)


def reset_audio():
    state = os.path.join(c.HOME, ".local", "state", "wireplumber")
    if os.path.isdir(state):
        shutil.move(state, state + ".bak-" + datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
    restart_audio()


def check_sound(reset=False):
    probs = []
    down = [s for s in AUDIO_SERVICES if c.run("systemctl", "--user", "is-active", "--quiet", s)[0] != 0]
    if down:
        probs.append(Problem("sound", T("the sound system is not running ({services})").format(services=", ".join(down)),
                             restart_audio, T("restart it")))
        return probs
    cards = open("/proc/asound/cards").read() if os.path.exists("/proc/asound/cards") else ""
    sinks = c.output("wpctl", "status")
    if "no soundcards" in cards or not cards.strip():
        missing = driverless("Audio")
        probs.append(Problem("sound", T("no sound card found"),
                             advice=T("sound hardware without a driver: {device}").format(device=missing[0])
                             if missing else
                             T("for USB or Bluetooth headphones, plug them in or connect them")))
    elif "Dummy Output" in sinks or "auto_null" in sinks:
        probs.append(Problem("sound", T("there is a sound card, but no output is active (its profile is off)"),
                             reset_audio, T("restart sound with fresh settings (yours are kept as .bak)")))
    vol = c.output("wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@")
    if "[MUTED]" in vol:
        probs.append(Problem("sound", T("sound is muted"),
                             lambda: c.run("wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0", check=True), T("unmute")))
    m = re.search(r"Volume: ([\d.]+)", vol)
    if m and float(m.group(1)) < 0.1:
        probs.append(Problem("sound", T("the volume is very low ({percent}%)").format(
                                 percent=f"{float(m.group(1)) * 100:.0f}"),
                             lambda: c.run("wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "0.5", check=True),
                             T("set it to 50%")))
    if reset:
        probs.append(Problem("sound", RESET, reset_audio,
                             T("restart sound with fresh settings (yours are kept as .bak)")))
    return probs


# ---- display ------------------------------------------------------------------------
def detach(*cmd):
    """Start a program that outlives mos-doctor (the window manager, the desktop)."""
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def reset_desktop():
    c.run("xfconf-query", "-c", "displays", "-p", "/", "-r", "-R")
    detach("xfwm4", "--replace")
    c.run("xfdesktop", "--quit")
    detach("xfdesktop")


VENDORS = {"0x8086": "Intel", "0x1002": "AMD", "0x10de": "NVIDIA", "0x1af4": "virtio", "0x1234": "QEMU",
           "0x15ad": "VMware", "0x80ee": "VirtualBox", "0x1b36": "QEMU"}


def graphics_drivers():
    """[(maker, kernel driver in use or None)] for each graphics card (PCI display controller)."""
    found = []
    for d in sorted(glob.glob("/sys/bus/pci/devices/*")):
        try:
            if not open(f"{d}/class").read().startswith("0x03"):
                continue
            vendor = open(f"{d}/vendor").read().strip()
        except OSError:
            continue
        drv = os.path.join(d, "driver")
        found.append((VENDORS.get(vendor, vendor), os.path.basename(os.readlink(drv)) if os.path.islink(drv) else None))
    return found


def graphics_summary():
    """The drivers in use, and mos-gpu-driver's choice for NVIDIA cards (System Info shows the same)."""
    cards = graphics_drivers()
    used = ", ".join(f"{drv or T('no driver')} ({maker})" for maker, drv in cards) or T("no graphics card found")
    want = {"nvidia": T("nvidia, NVIDIA's own"), "open": T("nouveau, the open one")}.get(c.output("mos-gpu-driver"))
    if want:
        return T("{drivers}; driver for NVIDIA cards: {choice}. Details: mos-gpu-driver --help").format(
            drivers=used, choice=want)
    return T("{drivers}. Details: mos-gpu-driver --help").format(drivers=used)


def force_gpu(driver):
    """How to make the next start use this graphics driver."""
    if c.installed():
        return f"`mos-config set graphics.driver {driver}`"
    return T("{option} at the start (in the boot menu press e, or Tab, and add it)").format(
        option=f"meccanicos.gpu={driver}")


def check_display(reset=False):
    probs = []
    want = c.output("mos-gpu-driver")
    loaded = c.output("lsmod")
    if want == "nvidia" and not re.search(r"^nvidia\b", loaded, re.M):
        probs.append(Problem("display", T("the NVIDIA driver should be in use, but it isn't loaded"),
                             advice=T("restart; if it persists, try {fix}").format(fix=force_gpu("open"))))
    renderer = re.search(r"OpenGL renderer string: (.+)", c.output("glxinfo", "-B"))
    if renderer and re.search(r"llvmpipe|softpipe", renderer.group(1)) and not os.path.exists("/sys/class/drm/card0-Virtual-1"):
        probs.append(Problem("display", T("graphics run without hardware acceleration (slow)"),
                             advice=T("the driver didn't start: try {fix} (or open), "
                                      "or mos-doctor --report to ask for help").format(fix=force_gpu("nvidia"))))
    line = next((l for l in c.output("xrandr", "--query").splitlines() if " connected" in l), "")
    px = re.search(r"(\d+)x\d+\+", line)
    mm = re.search(r"(\d+)mm x \d+mm", line)
    dpi_now = int(c.output("xfconf-query", "-c", "xsettings", "-p", "/Xft/DPI") or 96)
    if px and mm and int(mm.group(1)) > 0:
        dpi = int(px.group(1)) * 25.4 / int(mm.group(1))
        if dpi >= 135 and dpi_now <= 96:
            probs.append(Problem("display", T("a sharp screen ({dpi} dpi) shown at normal size: text is tiny").format(
                    dpi=f"{dpi:.0f}"), lambda: c.run("mos-hidpi", "--force", check=True), T("scale it up to fit")))
        elif dpi < 120 and dpi_now >= 144:
            probs.append(Problem("display", T("everything is shown larger than this screen needs"),
                                 lambda: c.run("mos-config", "set", "display.scale", "1", check=True),
                                 T("back to normal size")))
    xlog = os.path.join(c.HOME, ".local/share/xorg/Xorg.0.log")
    if os.path.exists(xlog):
        errors = [l for l in open(xlog, errors="replace") if "(EE)" in l and "Failed to load module" not in l]
        if errors:
            probs.append(Problem("display", T("the display server reported errors: {error}").format(error=errors[-1].strip()[:90]),
                                 advice=T("mos-doctor --report collects them to ask for help")))
    if reset:
        probs.append(Problem("display", RESET, reset_desktop,
                             T("restart the window manager and the desktop (clears leftover menu shadows "
                               "and menus that no longer open) and forget screen arrangements")))
    return probs


# ---- disk ---------------------------------------------------------------------------
def check_disk(reset=False):
    probs = []
    for path, full in (("/", N_("the system disk is almost full ({free} GB free)")),
                       (c.HOME, N_("your home is almost full ({free} GB free)"))):
        st = os.statvfs(path)
        free = st.f_bavail * st.f_frsize
        total = st.f_blocks * st.f_frsize
        if total and free / total < 0.05:
            gb = free / 2**30
            fix = None
            if c.installed() and path == "/":
                fix = lambda: c.run("nix-collect-garbage", "--delete-older-than", "30d", sudo=True, check=True, timeout=1800)
            probs.append(Problem("disk", T(full).format(free=f"{gb:.1f}"), fix,
                                 T("remove system versions older than 30 days and unused downloads"),
                                 None if fix else T("empty the trash (trash-empty) and delete what you don't need")))
            break
    return probs


# ---- logins ---------------------------------------------------------------------------
def check_logins(reset=False):
    """Disconnected on purpose, SSH logins from somewhere new, SSH under attack
    (mos-logins reads the journal)."""
    probs = []
    if c.output("nmcli", "networking").strip() == "disabled":
        probs.append(Problem("logins", T("every network is off (Disconnect)"),
                             lambda: c.run("mos-logins", "reconnect", check=True), T("reconnect")))
    week = c.output("mos-logins", "list", "7").splitlines()
    new = [l for l in week if l.endswith("(new)")]
    if new:
        probs.append(Problem("logins", T("{count} SSH login(s) from an address or key not seen before this week").format(
            count=len(new)), advice=T("see who in Logins (mos-logins); if it was you: mos-logins trust ADDRESS")))
    day = c.output("mos-logins", "list", "1").splitlines()
    fails = sum("SSH attempt failed" in l for l in day)
    if fails >= 100:
        probs.append(Problem("logins", T("SSH had {count} failed logins from other computers today").format(count=fails),
                             advice=T("they can't get in with a key only, and sshguard blocks them; if you never log "
                                      "in from elsewhere: mos-config set security.ssh off")))
    return probs


AREAS = {"network": check_network, "bluetooth": check_bluetooth, "sound": check_sound,
         "display": check_display, "disk": check_disk, "logins": check_logins}
ALIASES = {"wifi": "network", "internet": "network", "net": "network", "bt": "bluetooth",
           "audio": "sound", "video": "display", "screen": "display", "graphics": "display",
           "ssh": "logins", "security": "logins"}
LABELS = {"network": N_("Wi-Fi or internet"), "bluetooth": "Bluetooth", "sound": N_("Sound"),
          "display": N_("Screen or graphics"), "disk": N_("Disk space"), "logins": N_("Logins and SSH")}


# ---- report -------------------------------------------------------------------------
REDACT = [
    (re.compile(r"\b([0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b", re.I), "XX:XX:XX:XX:XX:XX"),  # MAC addresses
    (re.compile(r"(serial[^:=\n]*[:=]\s*)\S+", re.I), r"\1<removed>"),
    (re.compile(r"(uuid[^:=\n]*[:=]\s*)\S+", re.I), r"\1<removed>"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "x.x.x.x"),
]


def report(path):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    path = path or os.path.join(c.HOME, f"mos-report-{stamp}.tar.gz")
    parts = {
        "version": ["cat", "/etc/meccanicos/version"],
        "hardware": ["inxi", "-Fxxz", "-c0"],
        "pci": ["lspci", "-nnk"],
        "usb": ["lsusb"],
        "graphics-driver": ["mos-gpu-driver"],
        "glx": ["glxinfo", "-B"],
        "screens": ["xrandr", "--query"],
        "rfkill": ["rfkill"],
        "network": ["nmcli", "general", "status"],
        "network-devices": ["nmcli", "device"],
        "bluetooth": ["bluetoothctl", "show"],
        "sound": ["wpctl", "status"],
        "kernel-log": ["journalctl", "-k", "-b", "--no-pager", "-p", "warning"],
        "system-log": ["journalctl", "-b", "--no-pager", "-p", "err", "-n", "300"],
        "settings": ["mos-config", "list"],
        "checks": [sys.executable, sys.argv[0], "--check"],
    }
    tmp = tempfile.mkdtemp()
    for name, cmd in parts.items():
        _, out = c.run(*cmd, timeout=60)
        for pat, rep in REDACT:
            out = pat.sub(rep, out)
        with open(os.path.join(tmp, name + ".txt"), "w") as f:
            f.write(out + "\n")
    with tarfile.open(path, "w:gz") as tar:
        tar.add(tmp, arcname=f"mos-report-{stamp}")
    shutil.rmtree(tmp)
    c.ok(T("report: {file}").format(file=path))
    for line in T("It lists your hardware, settings and recent errors, with serial numbers and\n"
                  "network addresses removed. Look inside before sharing it.").splitlines():
        c.info(line)


# ---- main ---------------------------------------------------------------------------
def run_checks(areas, reset=False):
    found = []
    for a in areas:
        try:
            found += AREAS[a](reset)
        except Exception as e:  # a check must never stop the others
            c.warn(T("{area}: could not check ({error})").format(area=a, error=e))
    return found


def fix(p, force):
    if not p.fix:
        c.info(f"→ {p.advice}" if p.advice else "→ " + T("no automatic fix"))
        return False
    if not force and not c.ask("  " + T("Fix: {fix}?").format(fix=p.how)):
        return False
    try:
        p.fix()
        c.ok(T("done: {fix}").format(fix=p.how))
        c.log("doctor", f"{p.area}: {p.what} -> {p.how}")
        return True
    except (c.Failed, OSError) as e:
        c.bad(T("could not {fix}: {error}").format(fix=p.how, error=e))
        c.log("doctor", f"{p.area}: {p.what} -> {p.how} FAILED: {e}")
        return False


def main(argv):
    if argv and argv[0] in ("-h", "--help", "help"):
        print(T(__doc__).strip())
        return 0
    flags = {a for a in argv if a.startswith("--")}
    words = [a for a in argv if not a.startswith("--")]
    unknown = flags - {"--check", "--json", "--fix", "--reset", "--report"}
    if unknown:
        raise c.UsageError(T("unknown option {option} (mos-doctor --help)").format(option=sorted(unknown)[0]))
    if "--report" in flags:
        report(words[0] if words else None)
        return 0
    areas = []
    for w in words:
        a = ALIASES.get(w, w)
        if a not in AREAS:
            raise c.UsageError(T("unknown area {area}: one of {areas}").format(area=w, areas=", ".join(AREAS)))
        areas.append(a)
    asked = bool(areas)
    areas = areas or list(AREAS)
    probs = run_checks(areas, "--reset" in flags)
    if "--json" in flags:
        c.print_json([{"area": p.area, "problem": p.what, "fix": p.how, "advice": p.advice} for p in probs])
        return 1 if any(p.what != RESET for p in probs) else 0
    for a in areas:
        mine = [p for p in probs if p.area == a and p.what != RESET]
        if mine:
            c.bad(T("{area}: {count} problem(s)").format(area=T(LABELS[a]), count=len(mine)))
        else:
            c.ok(T("{area}: OK").format(area=T(LABELS[a])))
        if a == "display":  # which driver runs the screen, for asking for help
            try:
                c.info(T("graphics driver: {summary}").format(summary=graphics_summary()))
            except Exception:
                pass
        for p in mine:
            c.info(f"• {p.what}")
    if "--check" in flags:
        return 1 if any(p.what != RESET for p in probs) else 0
    real = [p for p in probs if p.what != RESET]
    for p in probs:
        if p.what == RESET:
            c.title("\n" + T("Reset {area}:").format(area=T(LABELS[p.area]).lower()))
        else:
            c.title(f"\n{p.what}")
        fix(p, "--fix" in flags)
    if not real and not asked and "--fix" not in flags:
        i = c.choose("\n" + T("Nothing obviously wrong. What isn't working?"),
                     [T(LABELS[a]) for a in AREAS] + [T("Something else")])
        if i is not None and i < len(AREAS):
            area = list(AREAS)[i]
            for p in run_checks([area], reset=True):
                c.title("\n" + (T("Reset {area}").format(area=T(LABELS[area]).lower())
                                 if p.what == RESET else p.what))
                fix(p, False)
        elif i is not None:
            c.info(T("mos-doctor --report saves what's needed to ask for help."))
    return 0
