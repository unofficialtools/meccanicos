"""mos-config - MeccanicOS's common settings in one place.

  mos-config                       the settings, full screen: move to one,
                                     Enter to change it (in a terminal)
  mos-config list [--json]         the settings and their current values
  mos-config get KEY               one value
  mos-config set KEY VALUE         change it (system settings: asks, then rebuilds)
  mos-config set KEY               show the choices for KEY
  mos-config export [FILE] [--dotfiles] [--with-secrets]
  mos-config import FILE [--dotfiles]
  mos-config apply                 re-apply what only lives in your settings
                                     (at login; e.g. the keyboard on the live USB)

  mos-config network [--json]      the connection now, its address, internet, VPNs
  mos-config network wifi          the Wi-Fi networks in reach
  mos-config network connect NAME  join a Wi-Fi network (asks for its password)
  mos-config network signin        open the sign-in page of a hotel/café network
  mos-config network vpn           the VPNs set up, and what can be imported
  mos-config network vpn on|off NAME   connect / disconnect one
  mos-config network vpn import FILE   add one from a WireGuard/OpenVPN file
  mos-config network vpn add       add one in Network Connections

Each setting stays where the system keeps it (Xfce, PipeWire, systemd,
/etc/nixos/meccanicos.toml), so Settings windows and mos-config agree. Every
change is also written to ~/.config/meccanicos/settings.toml: that file is all
your settings in one place, to keep, edit, or bring to another computer
(export/import). On the live USB with a persistent home it follows you.

User settings apply at once. System settings change the whole computer: on
an installed system they go into /etc/nixos/meccanicos.toml and need a rebuild
(mos-config offers it; --no-rebuild to do it later with mos-rebuild).

Dotfiles: export --dotfiles also saves the files listed under [dotfiles] in
settings.toml (shell, git, editor, ... by default) to dotfiles.tar.gz next
to it. Keys, tokens and passwords are never included, unless --with-secrets:
then the archive is encrypted with a password (dotfiles.tar.gz.age).
"""

import fnmatch
import glob
import os
import re
import shutil
import sys
import tarfile
import tempfile

import common as c

# ---- reading and writing the small TOML files we use (flat sections) ---------------
try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = None


def read_toml(path):
    if not os.path.exists(path):
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def toml_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, list):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_toml(path, data, header=""):
    """data: {section: {key: value}} and top-level {key: value}."""
    lines = [header] if header else []
    for k, v in data.items():
        if not isinstance(v, dict):
            lines.append(f"{k} = {toml_value(v)}")
    for sec, kv in data.items():
        if isinstance(kv, dict):
            lines.append(f"\n[{sec}]")
            lines += [f"{k} = {toml_value(v)}" for k, v in kv.items()]
    text = "\n".join(lines).lstrip("\n") + "\n"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


# ---- the places settings live ------------------------------------------------------
def xfconf_get(channel, prop):
    return c.output("xfconf-query", "-c", channel, "-p", prop) or None


def xfconf_set(channel, prop, kind, value):
    c.run("xfconf-query", "-c", channel, "-p", prop, "-n", "-t", kind, "-s", value, check=True)


def system_toml():
    return read_toml(c.SYSTEM_TOML)


def set_system_toml(key, value):
    """Change one key of /etc/nixos/meccanicos.toml (as root)."""
    data = system_toml()
    data[key] = value
    tmp = tempfile.NamedTemporaryFile("w", delete=False, suffix=".toml")
    tmp.close()
    write_toml(tmp.name, data, "# Written by mos-config (modules/settings.nix reads it).")
    c.run("install", "-m", "644", tmp.name, c.SYSTEM_TOML, sudo=True, check=True)
    os.unlink(tmp.name)


# ---- the settings ------------------------------------------------------------------
class Setting:
    """key: "group.name"; system: needs root (and, installed, a rebuild);
    choices: allowed values, or a function checking one; runtime: lives only
    in settings.toml and is applied at login by `mos-config apply`."""

    def __init__(self, key, help, get, set, system=False, choices=None, rebuild=False,
                 runtime=False, live=True, example=None):
        self.key, self.help, self._get, self._set = key, help, get, set
        self.system, self.choices, self.rebuild, self.runtime, self.live = system, choices, rebuild, runtime, live
        self.example = example

    def available(self):
        return self.live or c.installed()

    def get(self):
        try:
            return self._get()
        except Exception:  # a missing device or program: no value
            return None

    def parse(self, text):
        """The value typed on the command line, checked."""
        ch = self.choices
        if callable(ch):
            return ch(text)
        if ch and text not in ch:
            raise c.UsageError(f"{self.key}: one of {', '.join(ch)}")
        return text


def onoff(text):
    t = text.lower()
    if t in ("on", "true", "yes", "1"):
        return True
    if t in ("off", "false", "no", "0"):
        return False
    raise c.UsageError("on or off")


def minutes(text):
    if text in ("never", "0"):
        return 0
    if text.isdigit():
        return int(text)
    raise c.UsageError("minutes, or never")


def ports(text):
    if text in ("", "none"):
        return []
    try:
        return sorted({int(p) for p in text.replace(",", " ").split()})
    except ValueError:
        raise c.UsageError("port numbers, e.g. 8080,8443 (or none)")


def percent_or_off(text):
    if text in ("off", "100"):
        return 100
    if text.isdigit() and 50 <= int(text) <= 100:
        return int(text)
    raise c.UsageError("50 to 100 (%), or off")


# display.scale -- the size of text, as mos-hidpi sets it (auto: from the
# screen's width and density, again whenever the screen changes). Icons stay.
SCALE_STEPS = ["1", "1.25", "1.5", "1.75", "2", "2.5"]


def get_scale():
    dpi = int(xfconf_get("xsettings", "/Xft/DPI") or 96)
    try:
        auto = open(os.path.join(c.CONFIG_DIR, "hidpi-done")).read().startswith("auto")
    except OSError:
        auto = True
    return "auto" if auto else f"{dpi / 96:g}"


def set_scale(v):
    # mos-hidpi does the work (and remembers auto or this size).
    c.run("mos-hidpi", *(["--force"] if v == "auto" else ["--scale", v]), check=True)


# display.resolution -- the main screen's mode, through xrandr. Xfce does not
# keep it, so it lives in settings.toml and `mos-config apply` sets it at login.
def screen():
    """(output, [modes], current mode, preferred mode) of the main screen."""
    out, modes, now, best = None, [], None, None
    for line in c.output("xrandr", "--query").splitlines():
        if m := re.match(r"(\S+) connected( primary)?", line):
            if out and not m.group(2):
                break  # the first connected screen, unless a later one is primary
            out, modes, now, best = m.group(1), [], None, None
        elif out and (m := re.match(r"\s+(\d+x\d+)\S*\s+(.*)", line)):
            if m.group(1) not in modes:
                modes.append(m.group(1))
            now = m.group(1) if "*" in m.group(2) else now
            best = m.group(1) if "+" in m.group(2) else best
    return out, modes, now, best


def get_resolution():
    out, _, now, best = screen()
    if not out:
        return None
    return "auto" if now == best else now


def resolution_choice(text):
    _, modes, _, _ = screen()
    if text == "auto" or text in modes:
        return text
    raise c.UsageError("auto, or one of " + ", ".join(modes) if modes else "no screen found (xrandr)")


def set_resolution(v):
    out, _, _, _ = screen()
    if not out:
        raise c.Failed("no screen found (xrandr)")
    c.run("xrandr", "--output", out, *(["--auto"] if v == "auto" else ["--mode", v]), check=True)
    c.run("mos-hidpi")  # the text size follows the new width, when it is on auto


# display.rotation -- landscape (wide) or portrait (tall), each also upside down.
# xrandr turns from the panel's own orientation, which is tall on many tablets.
ROTATIONS = ["landscape", "portrait", "landscape-flipped", "portrait-flipped"]
TURNS = ["normal", "left", "inverted", "right"]  # each a quarter turn more (xrandr)


def turns(native_wide):
    """{rotation: xrandr turn} for a panel that is wide or tall by itself."""
    if native_wide:
        return dict(zip(ROTATIONS, ["normal", "left", "inverted", "right"]))
    return dict(zip(ROTATIONS, ["right", "normal", "left", "inverted"]))


def native_wide(mode):
    w, h = map(int, mode.split("x"))
    return w >= h


def get_rotation():
    out, _, _, best = screen()
    if not out or not best:
        return None
    m = re.search(rf"^{re.escape(out)} connected (?:primary )?\S+ (\w+)? ?\(", c.output("xrandr", "--query"), re.M)
    turn = (m.group(1) if m and m.group(1) in TURNS else None) or "normal"
    return {t: r for r, t in turns(native_wide(best)).items()}[turn]


def set_rotation(v):
    out, _, _, best = screen()
    if not out or not best:
        raise c.Failed("no screen found (xrandr)")
    c.run("xrandr", "--output", out, "--rotate", turns(native_wide(best))[v], check=True)
    # Touchscreens and pens report positions on the panel: tell them it turned.
    for dev in c.output("xinput", "list", "--id-only").split():
        info = c.output("xinput", "list", "--long", dev)
        if "slave  pointer" in info and ("mode: direct" in info.lower() or
                                         re.search(r"pen|stylus", info.splitlines()[0], re.I)):
            c.run("xinput", "map-to-output", dev, out)
    c.run("mos-hidpi")  # the text size follows the new width, when it is on auto


# display.wallpaper -- xfdesktop's picture, on every screen and workspace.
DEFAULT_WALLPAPER = f"/etc/{os.environ.get('MECCANICOS_ID', 'meccanicos')}/wallpaper.png"
PICTURES = (".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".bmp", ".heic")


def wallpaper_props():
    """Every screen x workspace image property: the ones xfdesktop made,
    plus one per connected screen and workspace (a new screen has none yet)."""
    props = {p for p in c.output("xfconf-query", "-c", "xfce4-desktop", "-l").splitlines()
             if p.endswith("/last-image")}
    n = int(xfconf_get("xfwm4", "/general/workspace_count") or 1)
    for line in c.output("xrandr", "--query").splitlines():
        if m := re.match(r"(\S+) connected", line):
            props |= {f"/backdrop/screen0/monitor{m.group(1)}/workspace{w}/last-image" for w in range(n)}
    return sorted(props)


def get_wallpaper():
    for p in c.output("xfconf-query", "-c", "xfce4-desktop", "-l").splitlines():
        if p.endswith("/last-image"):
            img = xfconf_get("xfce4-desktop", p)
            return "default" if not img or img == DEFAULT_WALLPAPER else img.replace(c.HOME, "~", 1)
    return "default"


def wallpaper_choice(text):
    if text == "default":
        return text
    path = os.path.abspath(os.path.expanduser(text))
    if not os.path.isfile(path):
        raise c.UsageError(f"no file {text} (a picture, or default)")
    if not path.lower().endswith(PICTURES):
        raise c.UsageError(f"{text} is not a picture ({', '.join(PICTURES)})")
    return path.replace(c.HOME, "~", 1)


def set_wallpaper(v):
    img = DEFAULT_WALLPAPER if v == "default" else os.path.expanduser(v)
    for p in wallpaper_props():
        xfconf_set("xfce4-desktop", p, "string", img)


def pictures():
    """Pictures to offer as a wallpaper: ~/Pictures (not its subfolders)."""
    folder = os.path.join(c.HOME, "Pictures")
    try:
        names = sorted(n for n in os.listdir(folder) if n.lower().endswith(PICTURES))
    except OSError:
        return []
    return [f"~/Pictures/{n}" for n in names[:30]]


# screensaver -- xfce4-screensaver (what the screen shows when idle, and the lock).
SAVER = "xfce4-screensaver"


def saver_themes():
    """{name: id} of the installed animations (screensavers-<desktop file>)."""
    found = {}
    for d in (os.environ.get("XDG_DATA_DIRS") or "/run/current-system/sw/share").split(":"):
        for f in glob.glob(os.path.join(d, "applications", "screensavers", "*.desktop")):
            name = os.path.basename(f)[:-8].removeprefix("xfce-").replace("personal-", "")
            found.setdefault(name, "screensavers-" + os.path.basename(f)[:-8])
    return found


def get_saver_after():
    if xfconf_get(SAVER, "/saver/enabled") == "false" or xfconf_get(SAVER, "/saver/idle-activation/enabled") == "false":
        return 0
    return int(xfconf_get(SAVER, "/saver/idle-activation/delay") or 5)


def set_saver_after(m):
    xfconf_set(SAVER, "/saver/enabled", "bool", "true" if m else "false")
    xfconf_set(SAVER, "/saver/idle-activation/enabled", "bool", "true" if m else "false")
    if m:
        xfconf_set(SAVER, "/saver/idle-activation/delay", "int", m)


def get_saver_show():
    mode = xfconf_get(SAVER, "/saver/mode") or "0"
    if mode == "1":
        return "random"
    if mode == "2":
        ids = {v: k for k, v in saver_themes().items()}
        first = (xfconf_get(SAVER, "/saver/themes/list") or "").split("\n")[-1].strip()
        return ids.get(first, "blank")
    return "blank"


def saver_show_choice(text):
    if text in ("blank", "random") or text in saver_themes():
        return text
    raise c.UsageError("one of " + ", ".join(["blank", "random", *saver_themes()]))


def set_saver_show(v):
    if v in ("blank", "random"):
        xfconf_set(SAVER, "/saver/mode", "int", 0 if v == "blank" else 1)
        return
    c.run("xfconf-query", "-c", SAVER, "-p", "/saver/themes/list", "-n", "-t", "string", "-s",
          saver_themes()[v], "--force-array", check=True)
    xfconf_set(SAVER, "/saver/mode", "int", 2)


def get_saver_lock():
    return xfconf_get(SAVER, "/lock/enabled") != "false" and \
        xfconf_get(SAVER, "/lock/saver-activation/enabled") != "false"


def set_saver_lock(on):
    xfconf_set(SAVER, "/lock/enabled", "bool", "true" if on else "false")
    xfconf_set(SAVER, "/lock/saver-activation/enabled", "bool", "true" if on else "false")
    if on:
        xfconf_set(SAVER, "/lock/saver-activation/delay", "int", 0)  # locked as soon as it starts


# security.login_alerts / auto_disconnect -- read by mos-logins' watcher
# straight from settings.toml (remember() writes them there).
def login_setting(name, default):
    v = stored(mine(), f"security.{name}")
    return default if v is None else bool(v)


# keyboard -- setxkbmap now, and at every login (apply), from settings.toml.
SWITCH = {"alt-shift": "grp:alt_shift_toggle", "ctrl-shift": "grp:ctrl_shift_toggle",
          "caps": "grp:caps_toggle", "none": ""}


def xkb_query():
    q = dict(l.split(":", 1) for l in c.output("setxkbmap", "-query").splitlines() if ":" in l)
    return {k.strip(): v.strip() for k, v in q.items()}


def get_layout():
    return xkb_query().get("layout")


def get_switch():
    opts = xkb_query().get("options", "")
    for name, opt in SWITCH.items():
        if opt and opt in opts:
            return name
    return "none"


def apply_keyboard(layout=None, switch=None):
    layout = layout or get_layout() or "us"
    switch = switch if switch is not None else get_switch()
    cmd = ["setxkbmap", "-layout", layout, "-option", ""]
    if SWITCH.get(switch):
        cmd += ["-option", SWITCH[switch]]
    c.run(*cmd, check=True)
    # Installed: the login screen and display-setup read /etc/meccanicos/settings too.
    if c.installed() and os.path.exists("/etc/meccanicos/settings"):
        c.run("sed", "-i", f"s/^XKB_LAYOUT=.*/XKB_LAYOUT={layout}/", "/etc/meccanicos/settings", sudo=True)


def layout_choice(text):
    if not re.fullmatch(r"[a-z]{2,3}(\([a-z0-9_]+\))?(,[a-z]{2,3}(\([a-z0-9_]+\))?)*", text):
        raise c.UsageError("keyboard layouts like us, or us,it (see localectl list-x11-keymap-layouts)")
    return text


# touchpad -- xinput now; Xfce's pointers channel keeps it.
def touchpads():
    names = c.output("xinput", "list", "--name-only").splitlines()
    return [n for n in names if "touchpad" in n.lower()]


def get_touch(prop):
    pads = touchpads()
    if not pads:
        return None
    out = c.output("xinput", "list-props", pads[0])
    m = re.search(rf"libinput {prop} Enabled \(\d+\):\s*(\d)", out)
    return (m.group(1) == "1") if m else None


def set_touch(prop, on):
    pads = touchpads()
    if not pads:
        raise c.Failed("no touchpad found")
    for pad in pads:
        c.run("xinput", "set-prop", pad, f"libinput {prop} Enabled", int(on))
        xfconf_set("pointers", f"/{pad.replace(' ', '_')}/Properties/libinput_{prop.replace(' ', '_')}_Enabled",
                   "int", int(on))


# power -- Xfce's power manager (screen), powerprofilesctl, logind, sysfs.
PM = "xfce4-power-manager"


def get_screen_off():
    v = xfconf_get(PM, f"/{PM}/dpms-on-ac-off")
    return int(v) if v is not None else 15


def set_screen_off(m):
    for src in ("ac", "battery"):
        xfconf_set(PM, f"/{PM}/dpms-enabled", "bool", "true")
        xfconf_set(PM, f"/{PM}/dpms-on-{src}-sleep", "uint", m)
        xfconf_set(PM, f"/{PM}/dpms-on-{src}-off", "uint", m)
        xfconf_set(PM, f"/{PM}/blank-on-{src}", "int", m)


def get_suspend():
    v = xfconf_get(PM, f"/{PM}/inactivity-on-ac")
    v = int(v) if v is not None else 0
    return 0 if v < 15 else v  # the power manager: under 15 minutes = never


def set_suspend(m):
    if 0 < m < 15:
        raise c.UsageError("15 minutes or more, or never")
    for src in ("ac", "battery"):
        xfconf_set(PM, f"/{PM}/inactivity-sleep-mode-on-{src}", "uint", 1)  # 1 = suspend
        xfconf_set(PM, f"/{PM}/inactivity-on-{src}", "uint", m or 14)


def batteries():
    return glob.glob("/sys/class/power_supply/BAT*/charge_control_end_threshold")


def get_charge():
    files = batteries()
    if not files:
        return None
    return int(open(files[0]).read().strip() or 100)


def set_charge(v):
    files = batteries()
    if not files:
        raise c.Failed("this battery cannot stop charging early (no charge_control_end_threshold)")
    for f in files:
        c.run("tee", f, sudo=True, input=f"{v}\n", check=True)
    if c.installed():
        set_system_toml("charge_limit", v)


# sound -- PipeWire (wpctl); WirePlumber remembers the default.
def nodes(kind):
    """{id: name} of the audio Sinks (outputs) or Sources (inputs) in `wpctl status`."""
    out, top, section, found = c.output("wpctl", "status"), None, None, {}
    for line in out.splitlines():
        if re.match(r"\w", line):  # Audio, Video, Settings, ...: not indented
            top, section = line.strip(), None
            continue
        stripped = line.strip(" │├└─")
        if stripped.endswith(":"):
            section = stripped[:-1]
            continue
        m = re.match(r"\s*\*?\s*(\d+)\.\s+(.+?)(\s+\[vol:.*)?$", stripped)
        if top == "Audio" and section == kind and m:
            found[int(m.group(1))] = m.group(2).strip()
    return found


def get_audio(which):
    out = c.output("wpctl", "inspect", f"@DEFAULT_AUDIO_{which}@")
    m = re.search(r'node\.description = "([^"]+)"', out)
    return m.group(1) if m else None


def set_audio(kind, text):
    found = nodes(kind)
    match = [i for i, n in found.items() if text.lower() in n.lower()]
    if not match:
        there = "; ".join(found.values()) if found else "none found"
        raise c.UsageError(f"no such {'output' if kind == 'Sinks' else 'input'}; there are: {there}")
    c.run("wpctl", "set-default", match[0], check=True)


# clock, time, language
CLOCK = {"24h": "%a %d %b   %H:%M", "12h": "%a %d %b   %l:%M %p"}


def get_clock():
    fmt = xfconf_get("xfce4-panel", "/plugins/plugin-4/digital-time-format") or ""
    return "12h" if "%p" in fmt or "%I" in fmt or "%l" in fmt else "24h"


def set_clock(v):
    xfconf_set("xfce4-panel", "/plugins/plugin-4/digital-time-format", "string", CLOCK[v])


def zone_choice(text):
    if not os.path.exists(os.path.join("/etc/zoneinfo", text)) and \
            not os.path.exists(os.path.join("/usr/share/zoneinfo", text)) and \
            text not in c.output("timedatectl", "list-timezones").split():
        raise c.UsageError("a time zone like Europe/Rome (timedatectl list-timezones)")
    return text


def set_zone(v):
    c.run("timedatectl", "set-timezone", v, sudo=True, check=True)


def locale_choice(text):
    if not re.fullmatch(r"[a-z]{2,3}_[A-Z]{2}\.UTF-8", text):
        raise c.UsageError("a locale like it_IT.UTF-8 (locale -a)")
    return text


def get_formats():
    m = re.search(r"LC_TIME=(\S+)", c.output("localectl", "status"))
    return m.group(1) if m else (os.environ.get("LC_TIME") or os.environ.get("LANG"))


def set_formats(v):
    lang = re.search(r"LANG=(\S+)", c.output("localectl", "status"))
    lang = lang.group(1) if lang else "en_US.UTF-8"
    args = [f"LANG={lang}"] + [f"{k}={v}" for k in ("LC_TIME", "LC_NUMERIC", "LC_MONETARY", "LC_PAPER", "LC_MEASUREMENT")]
    c.run("localectl", "set-locale", *args, sudo=True, check=True)
    c.info("takes effect at the next login")


# system settings that live in /etc/nixos/meccanicos.toml (installed)
def from_system(key, default, current=None):
    def get():
        data = system_toml()
        if key in data:
            return data[key]
        return current() if current else default
    return get


def to_system(key):
    return lambda v: set_system_toml(key, v)


def ssh_running():
    return c.run("systemctl", "is-enabled", "sshd")[0] == 0


def get_remote_unlock():
    return "on" in c.output("mos-unlock", "status").lower().split("remote unlock:")[-1][:6]


def set_remote_unlock(on):
    c.run("mos-unlock", "remote" if on else "remove-remote", check=True)


def get_gpu():
    data = system_toml()
    return data.get("gpu", "auto")


SETTINGS = [
    Setting("display.scale", "size of text on screen (auto: from the screen's width; icons stay)", get_scale,
            set_scale, choices=["auto"] + SCALE_STEPS),
    Setting("display.resolution", "the main screen's resolution (auto: its best)", get_resolution,
            set_resolution, choices=resolution_choice, runtime=True, example="1920x1080"),
    Setting("display.rotation", "landscape or portrait (also -flipped: upside down)", get_rotation,
            set_rotation, choices=ROTATIONS, runtime=True),
    Setting("display.wallpaper", "the desktop picture (a file, or default)", get_wallpaper, set_wallpaper,
            choices=wallpaper_choice, example="~/Pictures/beach.jpg"),
    Setting("screensaver.after", "start the screensaver after this many idle minutes (never)",
            get_saver_after, set_saver_after, choices=minutes, example="10"),
    Setting("screensaver.show", "what it shows: blank, random, or one animation", get_saver_show,
            set_saver_show, choices=saver_show_choice, example="floaters"),
    Setting("screensaver.lock", "lock the screen when the screensaver starts (asks the password)",
            get_saver_lock, set_saver_lock, choices=onoff),
    Setting("keyboard.layout", "keyboard layouts, first is the default (us, us,it, ...)",
            get_layout, lambda v: apply_keyboard(layout=v), choices=layout_choice, runtime=True, example="us,it"),
    Setting("keyboard.switch", "keys that switch between layouts", get_switch,
            lambda v: apply_keyboard(switch=v), choices=list(SWITCH), runtime=True),
    Setting("touchpad.tap", "tap the touchpad to click", lambda: get_touch("Tapping"),
            lambda v: set_touch("Tapping", v), choices=onoff),
    Setting("touchpad.natural_scroll", "scroll like a phone (content follows the fingers)",
            lambda: get_touch("Natural Scrolling"), lambda v: set_touch("Natural Scrolling", v), choices=onoff),
    Setting("power.screen_off", "turn the screen off after this many minutes (never)", get_screen_off,
            set_screen_off, choices=minutes, example="10"),
    Setting("power.suspend", "suspend after this many idle minutes (never, or 15+)", get_suspend,
            set_suspend, choices=minutes, example="30"),
    Setting("power.profile", "performance, balanced or power-saver (changes with the charger)",
            lambda: c.output("powerprofilesctl", "get") or None,
            lambda v: c.run("powerprofilesctl", "set", v, check=True),
            choices=["performance", "balanced", "power-saver"]),
    Setting("sound.output", "where sound goes (part of its name)", lambda: get_audio("SINK"),
            lambda v: set_audio("Sinks", v), choices=lambda t: t, example="speakers"),
    Setting("sound.input", "which microphone is used (part of its name)", lambda: get_audio("SOURCE"),
            lambda v: set_audio("Sources", v), choices=lambda t: t, example="headset"),
    Setting("clock.format", "the top bar's clock", get_clock, set_clock, choices=list(CLOCK)),
    Setting("time.zone", "time zone", lambda: c.output("timedatectl", "show", "-p", "Timezone", "--value") or None,
            set_zone, system=True, choices=zone_choice, runtime=True, example="Europe/Rome"),
    Setting("time.formats", "how dates, numbers and money are written", get_formats, set_formats,
            system=True, live=False, choices=locale_choice, example="it_IT.UTF-8"),
    Setting("power.charge_limit", "stop charging the battery at this % (off = 100)", get_charge, set_charge,
            system=True, choices=percent_or_off, runtime=True, example="80"),
    Setting("power.lid", "closing the lid", from_system("lid", "suspend"), to_system("lid"),
            system=True, rebuild=True, live=False, choices=["suspend", "hibernate", "lock", "nothing"]),
    Setting("power.hibernate", "hibernate (suspend to disk) available", from_system("hibernate", True),
            to_system("hibernate"), system=True, rebuild=True, live=False, choices=onoff),
    Setting("updates.auto", "update in the background every week (applied at the next start)",
            from_system("auto_update", True), to_system("auto_update"), system=True, rebuild=True,
            live=False, choices=onoff),
    Setting("security.ssh", "SSH server: log in from other computers with a key",
            from_system("ssh", True, ssh_running), to_system("ssh"), system=True, rebuild=True, live=False,
            choices=onoff),
    Setting("security.tcp_ports", "TCP ports let in through the firewall (none)", from_system("tcp_ports", []),
            to_system("tcp_ports"), system=True, rebuild=True, live=False, choices=ports, example="8080,8443"),
    Setting("security.udp_ports", "UDP ports let in through the firewall (none)", from_system("udp_ports", []),
            to_system("udp_ports"), system=True, rebuild=True, live=False, choices=ports, example="none"),
    Setting("security.remote_unlock", "unlock the disk over SSH while starting (mos-unlock)",
            get_remote_unlock, set_remote_unlock, system=True, live=False, choices=onoff),
    Setting("security.login_alerts", "alerts on SSH logins from somewhere new and SSH attacks (mos-logins)",
            lambda: login_setting("login_alerts", True), lambda v: None, choices=onoff, runtime=True),
    Setting("security.auto_disconnect", "disconnect by itself when someone unknown logs in with SSH",
            lambda: login_setting("auto_disconnect", False), lambda v: None, choices=onoff, runtime=True,
            live=False),
    Setting("graphics.driver", "graphics driver: auto, nvidia or open (applies at the next start)",
            get_gpu, to_system("gpu"), system=True, rebuild=True, live=False, choices=["auto", "nvidia", "open"]),
]
BY_KEY = {s.key: s for s in SETTINGS}


def show(v, s=None):
    if s is not None and s.choices is minutes and isinstance(v, int):
        return "never" if v == 0 else f"{v} min"
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "on" if v else "off"
    if isinstance(v, list):
        return ",".join(map(str, v)) or "none"
    return str(v)


def setting(key):
    s = BY_KEY.get(key)
    if not s:
        near = [k for k in BY_KEY if key.split(".")[-1] in k]
        raise c.UsageError(f"no setting {key}" + (f" (did you mean {', '.join(near)}?)" if near else
                                                 " (mos-config list shows them)"))
    return s


# ---- settings.toml: your copy of every setting --------------------------------------
DOTFILES = [".bashrc", ".profile", ".gitconfig", ".jedrc", ".tmux.conf", ".config/yazi",
            ".config/meccanicos/open.conf", ".config/xfce4/terminal", ".config/aichat/roles"]
SECRETS = [".ssh/id_*", ".ssh/*.pem", "*token*", "*secret*", "*.pass", "*password*",
           ".config/rclone/*", ".config/mos-dropbox/*", ".local/share/keyrings/*",
           ".gnupg/*", ".password-store/*", ".config/BraveSoftware/*", ".config/aichat/config.yaml",
           ".config/meccanicos/backup.*", ".config/gh/hosts.yml", ".netrc", ".git-credentials"]


def mine():
    return read_toml(c.SETTINGS)


def remember(key, value):
    """Record a setting in settings.toml (sections by group)."""
    data = mine()
    group, name = key.split(".", 1)
    data.setdefault(group, {})[name] = value
    write_toml(c.SETTINGS, data, HEADER)


HEADER = f"""# Your {c.NAME} settings, kept by mos-config. Edit freely, then run
# `mos-config import ~/.config/meccanicos/settings.toml` to apply them.
# On another computer: copy this file, then the same import."""


def stored(data, key):
    group, name = key.split(".", 1)
    return data.get(group, {}).get(name)


def visible():
    """The settings this system has, grouped (groups in order of appearance)."""
    rows = [s for s in SETTINGS if s.available()]
    groups = list(dict.fromkeys(s.key.split(".")[0] for s in rows))
    return sorted(rows, key=lambda s: groups.index(s.key.split(".")[0]))


def change(s, value):
    """Set and record one (checked) value; True if it waits for a rebuild."""
    s._set(value)
    remember(s.key, value)
    c.log("config", f"set {s.key} = {show(value)}")
    return s.rebuild and c.installed()


# ---- network: NetworkManager (nmcli), the same as the network icon --------------------
# Not settings (nothing goes in settings.toml, nor in export): the connection now, Wi-Fi,
# signing in to hotel/café networks, VPNs. Changed only when you ask.
NM_VPN_DIR = "/etc/NetworkManager/VPN"  # a .name file per VPN plugin installed
# VPN kinds nmcli can import from a file: (what it is, how to recognize it).
IMPORTS = {"wireguard": "a WireGuard file (.conf)", "openvpn": "an OpenVPN file (.ovpn)",
           "vpnc": "a Cisco VPN file (.pcf)"}
PROBE = "http://neverssl.com"  # plain http: a sign-in page catches it
INTERNET = {"full": "yes", "portal": "sign in needed (mos-config network signin)",
            "limited": "no (only the local network)", "none": "no", "unknown": "not checked"}


def nm_split(line):
    """One line of nmcli -t: its fields (nmcli writes a : inside a field as \\:)."""
    return [f.replace("\\:", ":").replace("\\\\", "\\") for f in re.split(r"(?<!\\):", line)]


def nm_rows(fields, *args):
    return [nm_split(l) for l in c.output("nmcli", "-t", "-f", fields, *args).splitlines() if l]


def vpns():
    """[(name, active)]: the VPN and WireGuard connections set up."""
    return [(r[0], r[2] == "yes") for r in nm_rows("NAME,TYPE,ACTIVE", "connection", "show")
            if len(r) == 3 and r[1] in ("vpn", "wireguard")]


def net_status():
    """The network now: connection, device, address, internet, VPNs."""
    st = {"connection": None, "type": None, "device": None, "address": None, "signal": None,
          "internet": c.output("nmcli", "networking", "connectivity") or "unknown",
          "vpn_on": [], "vpns": []}
    for r in nm_rows("DEVICE,TYPE,STATE,CONNECTION", "device"):
        if len(r) == 4 and r[2].startswith("connected") and r[1] in ("wifi", "ethernet", "gsm", "bt"):
            st.update(device=r[0], type=r[1], connection=r[3])
            break
    if st["device"]:
        addr = c.output("nmcli", "-g", "IP4.ADDRESS", "device", "show", st["device"]) or \
            c.output("nmcli", "-g", "IP6.ADDRESS", "device", "show", st["device"])
        st["address"] = addr.split(" | ")[0].rsplit("/", 1)[0].replace("\\:", ":") or None
    if st["type"] == "wifi":
        on = [r for r in nm_rows("IN-USE,SSID,SIGNAL", "device", "wifi", "list", "--rescan", "no") if r[0] == "*"]
        if on and len(on[0]) == 3:
            st["connection"] = on[0][1] or st["connection"]
            st["signal"] = int(on[0][2]) if on[0][2].isdigit() else None
    for name, active in vpns():
        st["vpns"].append(name)
        if active:
            st["vpn_on"].append(name)
    return st


def net_summary(st):
    """One line: HomeWiFi (Wi-Fi 82%, 192.168.1.23), or not connected."""
    if not st["device"]:
        return "not connected"
    kind = {"wifi": "Wi-Fi", "ethernet": "wired", "gsm": "mobile", "bt": "Bluetooth"}.get(st["type"], st["type"])
    if st["signal"] is not None:
        kind += f" {st['signal']}%"
    return f"{st['connection']} ({kind}" + (f", {st['address']})" if st["address"] else ")")


def vpn_summary(st):
    if st["vpn_on"]:
        return "on: " + ", ".join(st["vpn_on"])
    return "off" if st["vpns"] else "none set up"


def wifi_networks():
    """[(ssid, signal, secured, in use)], strongest first, each name once
    (hidden networks have none: nmtui joins those)."""
    seen = {}
    for r in nm_rows("IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "auto"):
        if len(r) != 4 or not r[1]:
            continue
        sig = int(r[2]) if r[2].isdigit() else 0
        old = seen.get(r[1])
        if not old or sig > old[1] or r[0] == "*":
            seen[r[1]] = (r[1], sig, r[3] not in ("", "--"), r[0] == "*" or bool(old and old[3]))
    return sorted(seen.values(), key=lambda n: (not n[3], -n[1]))


def wifi_saved():
    """Names of the Wi-Fi connections NetworkManager remembers (usually the network's name)."""
    return {r[0] for r in nm_rows("NAME,TYPE", "connection", "show") if len(r) == 2 and r[1] == "802-11-wireless"}


def nm_error(out, default):
    return (out.splitlines() or [default])[-1].removeprefix("Error: ")


def wifi_profile(ssid):
    """The UUID of a remembered connection for this network, or None."""
    for uuid, kind in nm_rows("UUID,TYPE", "connection", "show"):
        if kind == "802-11-wireless" and \
                c.output("nmcli", "-g", "802-11-wireless.ssid", "connection", "show", "uuid", uuid) == ssid:
            return uuid
    return None


def wifi_connect(ssid, password=None):
    """Join a Wi-Fi network; NetworkManager remembers it (and its password).
    The password never goes on a command line (others could see it in the
    process list): nmcli reads it from a file only you can read, deleted
    right after. A new network that does not connect is forgotten again."""
    if not password:  # an open network, or one remembered with its password
        code, out = c.run("nmcli", "--wait", "45", "device", "wifi", "connect", ssid, timeout=60)
        c.log("config", f"network: join Wi-Fi {ssid}" + ("" if code == 0 else " (failed)"))
        if code != 0:
            raise c.Failed(nm_error(out, "could not connect"))
        return
    security = next((r[1] for r in nm_rows("SSID,SECURITY", "device", "wifi", "list", "--rescan", "no")
                     if len(r) == 2 and r[0] == ssid), "")
    if "802.1X" in security or ("WPA" not in security and security not in ("", "--")):
        raise c.Failed(f"{ssid} needs more than a password ({security}): use Other network (nmtui)")
    uuid, new = wifi_profile(ssid), False
    if not uuid:
        dev = next((r[0] for r in nm_rows("DEVICE,TYPE", "device") if len(r) == 2 and r[1] == "wifi"), None)
        if not dev:
            raise c.Failed("no Wi-Fi here")
        mgmt = "sae" if "WPA3" in security and "WPA2" not in security and "WPA1" not in security else "wpa-psk"
        code, out = c.run("nmcli", "connection", "add", "type", "wifi", "ifname", dev, "con-name", ssid,
                          "ssid", ssid, "wifi-sec.key-mgmt", mgmt)
        m = re.search(r"\(([0-9a-f-]{36})\)", out)
        if code != 0 or not m:
            raise c.Failed(nm_error(out, "could not add the network"))
        uuid, new = m.group(1), True
    run_dir = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    secret_file = os.path.join(run_dir, f"mos-wifi-{os.getpid()}")
    try:
        fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(f"802-11-wireless-security.psk:{password}\n")
        code, out = c.run("nmcli", "--wait", "45", "connection", "up", "uuid", uuid, "passwd-file", secret_file,
                          timeout=60)
    finally:
        try:
            os.unlink(secret_file)
        except OSError:
            pass
    c.log("config", f"network: join Wi-Fi {ssid}" + ("" if code == 0 else " (failed)"))
    if code != 0:
        if new:  # don't remember a wrong password
            c.run("nmcli", "connection", "delete", "uuid", uuid)
        raise c.Failed(nm_error(out, "could not connect"))


def portal_url():
    """The sign-in page of a hotel/café/airport network: where it sends a plain
    http request, else that plain http page itself (the browser gets sent on)."""
    import urllib.error
    import urllib.request

    class Stay(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kw):
            return None
    try:
        urllib.request.build_opener(Stay).open(PROBE, timeout=6).close()
    except urllib.error.HTTPError as e:
        where = e.headers.get("Location", "")
        if e.code in (301, 302, 303, 307, 308) and re.match(r"https?://", where):
            return where
    except Exception:  # no answer: the browser will show why
        pass
    return PROBE


def start(*cmd):
    """Start a window that outlives mos-config (the browser, Network Connections)."""
    import subprocess
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def open_url(url):
    if not os.environ.get("DISPLAY") or not c.have("xdg-open"):
        raise c.Failed(f"no desktop here: open {url} in a browser")
    start("xdg-open", url)


def vpn_kinds():
    """What can be imported here: WireGuard (part of NetworkManager), plus
    the kinds whose NetworkManager plugin is installed."""
    kinds = ["wireguard"]
    for f in sorted(glob.glob(os.path.join(NM_VPN_DIR, "*.name"))):
        try:
            m = re.search(r"^service=org\.freedesktop\.NetworkManager\.(\w+)", open(f).read(), re.M)
        except OSError:
            continue
        if m and m.group(1) in IMPORTS and m.group(1) not in kinds:
            kinds.append(m.group(1))
    return kinds


def vpn_kind(path):
    """wireguard, openvpn or vpnc, from the file itself."""
    text = open(path, errors="replace").read(200_000)
    if re.search(r"^\s*\[Interface\]", text, re.M):
        return "wireguard"
    if path.endswith(".ovpn") or re.search(r"^\s*(remote|client)\b", text, re.M):
        return "openvpn"
    if path.lower().endswith(".pcf") or "[main]" in text:
        return "vpnc"
    return None


def vpn_import(path):
    """Add a VPN from its file; returns its name. It is not turned on, and does
    not turn itself on at the next start: mos-config network vpn on NAME."""
    path = os.path.expanduser(path)
    if not os.path.isfile(path):
        raise c.Failed(f"no such file: {path}")
    kind, kinds = vpn_kind(path), vpn_kinds()
    if kind not in kinds:
        raise c.Failed(f"not a file {c.NAME} can import ({', '.join(IMPORTS[k] for k in kinds)})")
    tmp = None
    if kind == "wireguard":  # NetworkManager names the interface after the file: 15 letters at most
        tmp = tempfile.mkdtemp()
        name = re.sub(r"[^A-Za-z0-9_-]", "", os.path.splitext(os.path.basename(path))[0])[:15] or "wg0"
        shutil.copy(path, os.path.join(tmp, name + ".conf"))
        path = os.path.join(tmp, name + ".conf")
    try:
        code, out = c.run("nmcli", "connection", "import", "type", kind, "file", path)
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    if code != 0:
        raise c.Failed(nm_error(out, "could not import it"))
    m = re.search(r"Connection '(.+)' \(([0-9a-f-]+)\)", out)
    if m:
        c.run("nmcli", "connection", "modify", m.group(2), "connection.autoconnect", "no")
    c.log("config", f"network: VPN imported from {os.path.basename(path)}")
    return m.group(1) if m else os.path.basename(path)


def vpn_up(name):
    """Turn a VPN on; nmcli asks here for a password or code it needs (a terminal)."""
    import subprocess
    if name not in [n for n, _ in vpns()]:
        raise c.UsageError(f"no VPN {name} (mos-config network vpn lists them)")
    ask = ["--ask"] if sys.stdin.isatty() else []
    if subprocess.call(["nmcli", *ask, "connection", "up", "id", name]) != 0:
        raise c.Failed(f"VPN {name} did not connect")
    c.log("config", f"network: VPN {name} on")


def vpn_down(name):
    if name not in [n for n, _ in vpns()]:
        raise c.UsageError(f"no VPN {name} (mos-config network vpn lists them)")
    c.run("nmcli", "connection", "down", "id", name, check=True)
    c.log("config", f"network: VPN {name} off")


def vpn_add():
    """Network Connections (+, then the kind of VPN); without a desktop, nmtui."""
    if os.environ.get("DISPLAY") and c.have("nm-connection-editor"):
        start("nm-connection-editor")
        return True
    os.system("nmtui edit")
    return False


def show_status(st):
    rows = [("connection", net_summary(st))]
    if st["device"]:
        rows.append(("device", st["device"]))
    rows += [("internet", INTERNET.get(st["internet"], st["internet"])), ("vpn", vpn_summary(st))]
    if st["vpns"]:
        rows.append(("vpns", ", ".join(st["vpns"])))
    print("network")
    for k, v in rows:
        print(f"  {k:<10}  {v}")


def cmd_network(args):
    flags = [a for a in args if a.startswith("--")]
    args = [a for a in args if not a.startswith("--")]
    if {"-h", "--help", "help"} & set(flags + args):
        print("\n".join(l for l in __doc__.splitlines() if "mos-config network" in l))
        return
    if not c.have("nmcli"):
        raise c.Failed("NetworkManager (nmcli) is not installed")
    what = args[0] if args else "status"
    if what == "status" and len(args) <= 1:
        st = net_status()
        if "--json" in flags:
            c.print_json(st)
        else:
            show_status(st)
    elif what == "wifi" and len(args) == 1:
        nets = wifi_networks()
        if not nets:
            c.info("no Wi-Fi networks in reach (or no Wi-Fi here: mos-doctor network)")
        for ssid, sig, secured, on in nets:
            print(f"{'*' if on else ' '} {sig:>3}%  {'' if secured else 'open  '}{ssid}")
    elif what == "connect" and len(args) == 2:
        import subprocess
        # nmcli asks for the password itself (not shown, not in the process list).
        ask = ["--ask"] if sys.stdin.isatty() else []
        code = subprocess.call(["nmcli", *ask, "--wait", "45", "device", "wifi", "connect", args[1]])
        c.log("config", f"network: join Wi-Fi {args[1]}" + ("" if code == 0 else " (failed)"))
        if code:
            raise c.Failed(f"not connected to {args[1]}")
    elif what in ("signin", "sign-in") and len(args) == 1:
        from config_tui import ui  # mos_tui, found the way config_tui finds it
        with ui.spinning("Looking for the sign-in page…"):
            url = portal_url()
        open_url(url)
        c.ok(f"opened {url}: sign in there")
    elif what == "vpn" and len(args) == 1:
        for name, active in vpns():
            print(f"{name}  {'on' if active else 'off'}")
        c.info("import: " + ", ".join(IMPORTS[k] for k in vpn_kinds()))
    elif what == "vpn" and len(args) == 3 and args[1] in ("on", "up", "off", "down"):
        (vpn_up if args[1] in ("on", "up") else vpn_down)(args[2])
        c.ok(f"VPN {args[2]} {'on' if args[1] in ('on', 'up') else 'off'}")
    elif what == "vpn" and len(args) == 3 and args[1] == "import":
        c.ok(f"VPN added: {vpn_import(args[2])} (turn it on: mos-config network vpn on NAME)")
    elif what == "vpn" and args[1:] == ["add"]:
        if vpn_add():
            c.ok("Network Connections opened: + adds a connection, then pick the kind of VPN")
    else:
        raise c.UsageError("mos-config network [wifi | connect NAME | signin | vpn [on|off NAME | import FILE | add]]")


# ---- commands -----------------------------------------------------------------------
def cmd_list(args):
    as_json = "--json" in args
    rows = visible()
    if as_json:
        c.print_json({s.key: s.get() for s in rows})
        return
    values = {s.key: show(s.get(), s) for s in rows}
    width = max(len(s.key) for s in rows)
    vwidth = min(24, max(len(v) for v in values.values()))
    group = None
    for s in rows:
        g = s.key.split(".")[0]
        if g != group:
            print(f"\n{g}" if group else g)
            group = g
        v = values[s.key]
        v = v if len(v) <= vwidth else v[: vwidth - 1] + "…"
        tag = "  (system)" if s.system else ""
        print(f"  {s.key:<{width}}  {v:<{vwidth}}  {s.help}{tag}")
    if not c.installed():
        print(f"\nLive USB: settings for the installed system (SSH, updates, ...) appear once {c.NAME} is installed.")


def cmd_get(args):
    if len(args) != 1:
        raise c.UsageError("mos-config get KEY")
    s = setting(args[0])
    print(show(s.get(), s))


def cmd_set(args):
    flags = [a for a in args if a.startswith("--")]
    args = [a for a in args if not a.startswith("--")]
    if not args or len(args) > 2:
        raise c.UsageError("mos-config set KEY VALUE")
    s = setting(args[0])
    if not s.available():
        raise c.Failed(f"{s.key} is for the installed system")
    if len(args) == 1:
        ch = s.choices
        print(f"{s.key}: {s.help}\nnow: {show(s.get(), s)}")
        if isinstance(ch, list):
            print("choices: " + ", ".join(ch))
        elif ch is onoff:
            print("choices: on, off")
        if s.example:
            print(f"example: mos-config set {s.key} {s.example}")
        return
    value = s.parse(args[1])
    pending = change(s, value)
    c.ok(f"{s.key} = {show(value, s)}")
    if pending:
        rebuild("--no-rebuild" not in flags)


def rebuild(now):
    if now and c.ask("Apply it now (rebuilds the system, a few minutes)?"):
        code = os.system("mos-rebuild")
        if code:
            raise c.Failed("the rebuild failed; your previous system is still in the boot menu")
        c.ok("applied")
        return
    c.info("saved in /etc/nixos/meccanicos.toml: run mos-rebuild to apply it")


def cmd_apply(args):
    """At login: what lives only in settings.toml."""
    data = mine()
    res = stored(data, "display.resolution")
    if res and res != "auto":
        try:
            set_resolution(resolution_choice(res))
        except (c.Failed, c.UsageError) as e:  # another screen now: its own best
            c.warn(f"display.resolution: {e}")
    rot = stored(data, "display.rotation")
    if rot and rot != get_rotation():
        try:
            set_rotation(rot)
        except c.Failed as e:
            c.warn(f"display.rotation: {e}")
    kb = {k: stored(data, k) for k in ("keyboard.layout", "keyboard.switch")}
    if any(kb.values()):
        try:
            apply_keyboard(layout=kb["keyboard.layout"], switch=kb["keyboard.switch"])
        except c.Failed as e:
            c.warn(f"keyboard: {e}")
    if not c.installed():  # installed systems keep these themselves
        for key in ("time.zone", "power.charge_limit"):
            v = stored(data, key)
            if v is not None and show(BY_KEY[key].get()) != show(v):
                try:
                    BY_KEY[key]._set(v)
                except (c.Failed, c.UsageError) as e:
                    c.warn(f"{key}: {e}")


def cmd_export(args):
    flags = {a for a in args if a.startswith("--")}
    files = [a for a in args if not a.startswith("--")]
    path = os.path.abspath(files[0]) if files else c.SETTINGS
    data = mine()
    for s in SETTINGS:
        if s.available():
            v = s.get()
            if v is not None:
                group, name = s.key.split(".", 1)
                data.setdefault(group, {})[name] = v
    data.setdefault("dotfiles", {}).setdefault("include", DOTFILES)
    write_toml(path, data, HEADER)
    c.ok(f"settings: {path}")
    if "--dotfiles" in flags:
        export_dotfiles(os.path.dirname(path), data["dotfiles"]["include"], "--with-secrets" in flags)


def secret(rel):
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(os.path.basename(rel), p) for p in SECRETS)


def export_dotfiles(folder, include, secrets):
    picked, skipped = [], []
    for item in include:
        full = os.path.join(c.HOME, item)
        found = [full] if os.path.isfile(full) else \
            [os.path.join(d, f) for d, _, fs in os.walk(full) for f in fs] if os.path.isdir(full) else []
        for f in found:
            rel = os.path.relpath(f, c.HOME)
            (skipped if secret(rel) and not secrets else picked).append(rel)
    if secrets:
        picked += [os.path.relpath(f, c.HOME) for p in SECRETS
                   for f in glob.glob(os.path.join(c.HOME, p)) if os.path.isfile(f)]
    out = os.path.join(folder, "dotfiles.tar.gz")
    with tarfile.open(out, "w:gz") as tar:
        for rel in sorted(set(picked)):
            tar.add(os.path.join(c.HOME, rel), arcname=rel)
    if secrets:
        if not c.have("age"):
            os.unlink(out)
            raise c.Failed("age is not installed, so secrets cannot be encrypted")
        c.info("A password for the archive (it holds keys and passwords):")
        if os.system(f"age -p -o '{out}.age' '{out}'") != 0:
            os.unlink(out)
            raise c.Failed("not encrypted")
        os.unlink(out)
        out += ".age"
    c.ok(f"dotfiles: {out} ({len(set(picked))} files)")
    for rel in skipped:
        c.info(f"left out (a key or password): ~/{rel}")


def cmd_import(args):
    flags = {a for a in args if a.startswith("--")}
    files = [a for a in args if not a.startswith("--")]
    if len(files) != 1:
        raise c.UsageError("mos-config import FILE")
    data = read_toml(files[0])
    changes, needs_rebuild = [], False
    for s in SETTINGS:
        v = stored(data, s.key)
        if v is None or not s.available():
            continue
        if show(s.get()) != show(v):
            changes.append((s, v))
    if not changes:
        c.ok("nothing to change")
    else:
        c.title("These settings will change:")
        for s, v in changes:
            c.info(f"{s.key}: {show(s.get())} -> {show(v)}")
        if not c.ask("Go ahead?"):
            return
        for s, v in changes:
            try:
                s._set(v)
                remember(s.key, v)
                c.ok(f"{s.key} = {show(v)}")
                needs_rebuild |= s.rebuild
            except (c.Failed, c.UsageError) as e:
                c.bad(f"{s.key}: {e}")
        if needs_rebuild and c.installed():
            rebuild(True)
    if "--dotfiles" in flags:
        import_dotfiles(os.path.dirname(os.path.abspath(files[0])))


def import_dotfiles(folder):
    plain, enc = os.path.join(folder, "dotfiles.tar.gz"), os.path.join(folder, "dotfiles.tar.gz.age")
    tmp = None
    if os.path.exists(enc):
        tmp = tempfile.mktemp(suffix=".tar.gz")
        if os.system(f"age -d -o '{tmp}' '{enc}'") != 0:
            raise c.Failed("could not decrypt the dotfiles")
        plain = tmp
    if not os.path.exists(plain):
        raise c.Failed(f"no dotfiles.tar.gz next to the settings in {folder}")
    with tarfile.open(plain) as tar:
        members = [m for m in tar.getmembers() if m.isfile() and not m.name.startswith(("/", ".."))]
        clash = [m.name for m in members if os.path.exists(os.path.join(c.HOME, m.name))]
        c.info(f"{len(members)} files; {len(clash)} replace yours (kept as NAME.bak)")
        if c.ask("Restore them?"):
            for m in members:
                dst = os.path.join(c.HOME, m.name)
                if os.path.exists(dst):
                    shutil.copy2(dst, dst + ".bak")
                tar.extract(m, c.HOME, filter="data") if hasattr(tarfile, "data_filter") else tar.extract(m, c.HOME)
            c.ok("dotfiles restored")
    if tmp:
        os.unlink(tmp)


COMMANDS = {"list": cmd_list, "get": cmd_get, "set": cmd_set, "export": cmd_export,
            "import": cmd_import, "apply": cmd_apply, "network": cmd_network}


def main(argv):
    if argv and argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    if not argv and sys.stdin.isatty() and sys.stdout.isatty():
        import config_tui
        return config_tui.main()
    cmd = argv[0] if argv else "list"
    if cmd not in COMMANDS:
        raise c.UsageError(f"unknown command {cmd} (mos-config --help)")
    COMMANDS[cmd](argv[1:])
    return 0
