#!/usr/bin/env python3
"""
mos-install - one-page TUI installer.

Installs the prebuilt MeccanicOS system (shipped inside the ISO) onto a disk:
GPT -> 1 GiB EFI + LUKS2 -> ext4, systemd-boot. No network needed.

Environment (set by the Nix wrapper):
  MECCANICOS_SYSTEM   store path of the installed system's toplevel
  MECCANICOS_SYSTEM_DISK_BYTES  space it takes on the target (for the progress bar)
  MECCANICOS_FLAKE    store path of the distro flake (copied to /etc/nixos)
  MECCANICOS_NAME     distro name, e.g. "MeccanicOS"
  MECCANICOS_ISO_LABEL  volume label of the live USB (excluded from targets)
Testing:
  MECCANICOS_INSTALL_TEST=1   run disk steps but skip nixos-install / nixos-enter
  --config FILE.json     skip the TUI, install with these answers
"""

import curses
import datetime
import json
import os
import re
import shlex
import subprocess
import sys
import time

# The look shared by MeccanicOS TUIs: MECCANICOS_PYLIB from the Nix wrapper, else next to this file.
sys.path.insert(0, os.environ.get("MECCANICOS_PYLIB") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import mos_tui as ui  # noqa: E402

NAME = os.environ.get("MECCANICOS_NAME", "MeccanicOS")
SYSTEM = os.environ.get("MECCANICOS_SYSTEM", "")
FLAKE = os.environ.get("MECCANICOS_FLAKE", "")
ISO_LABEL = os.environ.get("MECCANICOS_ISO_LABEL", "MECCANICOS_LIVE")
TEST = os.environ.get("MECCANICOS_INSTALL_TEST") == "1"
LUKS_MIN = 16  # minimum disk password length
TARGET = "/mnt/mos-target"
MAPPER = "mos-target"
LOG = "/tmp/mos-install.log"
USER_GROUPS = "wheel,networkmanager,video,audio,input,dialout,lp,scanner"

# ----------------------------------------------------------------- data ----
# (label, xkb layout, xkb variant, console keymap)
KEYBOARDS = [
    ("English (US)", "us", "", "us"),
    ("English (US, international)", "us", "intl", "us"),
    ("English (UK)", "gb", "", "uk"),
    ("English (Ireland)", "ie", "", "ie"),
    ("English (Dvorak)", "us", "dvorak", "dvorak"),
    ("English (Colemak)", "us", "colemak", "us"),
    ("English (India)", "in", "eng", "us"),
    ("Italian", "it", "", "it"),
    ("German", "de", "", "de-latin1"),
    ("German (Switzerland)", "ch", "", "sg-latin1"),
    ("French", "fr", "", "fr-latin1"),
    ("French (Switzerland)", "ch", "fr", "fr_CH-latin1"),
    ("French (Canada)", "ca", "", "cf"),
    ("Belgian", "be", "", "be-latin1"),
    ("Spanish", "es", "", "es"),
    ("Spanish (Latin America)", "latam", "", "la-latin1"),
    ("Portuguese", "pt", "", "pt-latin1"),
    ("Portuguese (Brazil)", "br", "", "br-abnt2"),
    ("Dutch", "nl", "", "nl"),
    ("Danish", "dk", "", "dk-latin1"),
    ("Norwegian", "no", "", "no-latin1"),
    ("Swedish", "se", "", "sv-latin1"),
    ("Finnish", "fi", "", "fi"),
    ("Icelandic", "is", "", "is-latin1"),
    ("Estonian", "ee", "", "et"),
    ("Latvian", "lv", "", "lv"),
    ("Lithuanian", "lt", "", "lt"),
    ("Polish", "pl", "", "pl2"),
    ("Czech", "cz", "", "cz"),
    ("Slovak", "sk", "", "sk-qwertz"),
    ("Hungarian", "hu", "", "hu"),
    ("Romanian", "ro", "", "ro"),
    ("Croatian", "hr", "", "croat"),
    ("Slovenian", "si", "", "slovene"),
    ("Serbian", "rs", "", "sr-cy"),
    ("Macedonian", "mk", "", "mk"),
    ("Bulgarian", "bg", "", "bg_bds-utf8"),
    ("Greek", "gr", "", "gr"),
    ("Turkish", "tr", "", "trq"),
    ("Russian", "ru", "", "ru"),
    ("Ukrainian", "ua", "", "ua"),
    ("Belarusian", "by", "", "by"),
    ("Kazakh", "kz", "", "kazakh"),
    ("Hebrew", "il", "", "il"),
    ("Japanese", "jp", "", "jp106"),
    ("Korean", "kr", "", "us"),
    ("Chinese", "cn", "", "us"),
    ("Maltese", "mt", "", "us"),
]

# (label, locale)
LANGUAGES = [
    ("English (United States)", "en_US.UTF-8"),
    ("English (United Kingdom)", "en_GB.UTF-8"),
    ("English (Canada)", "en_CA.UTF-8"),
    ("English (Australia)", "en_AU.UTF-8"),
    ("English (Ireland)", "en_IE.UTF-8"),
    ("English (India)", "en_IN"),
    ("Italiano", "it_IT.UTF-8"),
    ("Deutsch", "de_DE.UTF-8"),
    ("Deutsch (Schweiz)", "de_CH.UTF-8"),
    ("Deutsch (Österreich)", "de_AT.UTF-8"),
    ("Français", "fr_FR.UTF-8"),
    ("Français (Canada)", "fr_CA.UTF-8"),
    ("Français (Belgique)", "fr_BE.UTF-8"),
    ("Español", "es_ES.UTF-8"),
    ("Español (México)", "es_MX.UTF-8"),
    ("Español (Argentina)", "es_AR.UTF-8"),
    ("Português", "pt_PT.UTF-8"),
    ("Português (Brasil)", "pt_BR.UTF-8"),
    ("Nederlands", "nl_NL.UTF-8"),
    ("Dansk", "da_DK.UTF-8"),
    ("Norsk bokmål", "nb_NO.UTF-8"),
    ("Svenska", "sv_SE.UTF-8"),
    ("Suomi", "fi_FI.UTF-8"),
    ("Íslenska", "is_IS.UTF-8"),
    ("Eesti", "et_EE.UTF-8"),
    ("Latviešu", "lv_LV.UTF-8"),
    ("Lietuvių", "lt_LT.UTF-8"),
    ("Polski", "pl_PL.UTF-8"),
    ("Čeština", "cs_CZ.UTF-8"),
    ("Slovenčina", "sk_SK.UTF-8"),
    ("Magyar", "hu_HU.UTF-8"),
    ("Română", "ro_RO.UTF-8"),
    ("Hrvatski", "hr_HR.UTF-8"),
    ("Slovenščina", "sl_SI.UTF-8"),
    ("Српски", "sr_RS.UTF-8"),
    ("Македонски", "mk_MK.UTF-8"),
    ("Български", "bg_BG.UTF-8"),
    ("Ελληνικά", "el_GR.UTF-8"),
    ("Türkçe", "tr_TR.UTF-8"),
    ("Русский", "ru_RU.UTF-8"),
    ("Українська", "uk_UA.UTF-8"),
    ("Беларуская", "be_BY.UTF-8"),
    ("Қазақ", "kk_KZ.UTF-8"),
    ("עברית", "he_IL.UTF-8"),
    ("日本語", "ja_JP.UTF-8"),
    ("한국어", "ko_KR.UTF-8"),
    ("中文 (简体)", "zh_CN.UTF-8"),
    ("中文 (繁體)", "zh_TW.UTF-8"),
    ("Malti", "mt_MT.UTF-8"),
]

# (label, ISO code, language locale, formats locale, time zone, keyboard label)
COUNTRIES = [
    ("United States", "US", "en_US.UTF-8", "en_US.UTF-8", "America/Los_Angeles", "English (US)"),
    ("United Kingdom", "GB", "en_GB.UTF-8", "en_GB.UTF-8", "Europe/London", "English (UK)"),
    ("Canada", "CA", "en_CA.UTF-8", "en_CA.UTF-8", "America/Toronto", "English (US)"),
    ("Australia", "AU", "en_AU.UTF-8", "en_AU.UTF-8", "Australia/Sydney", "English (US)"),
    ("New Zealand", "NZ", "en_NZ.UTF-8", "en_NZ.UTF-8", "Pacific/Auckland", "English (US)"),
    ("Ireland", "IE", "en_IE.UTF-8", "en_IE.UTF-8", "Europe/Dublin", "English (Ireland)"),
    ("India", "IN", "en_IN", "en_IN", "Asia/Kolkata", "English (India)"),
    ("Italy", "IT", "it_IT.UTF-8", "it_IT.UTF-8", "Europe/Rome", "Italian"),
    ("Germany", "DE", "de_DE.UTF-8", "de_DE.UTF-8", "Europe/Berlin", "German"),
    ("Austria", "AT", "de_AT.UTF-8", "de_AT.UTF-8", "Europe/Vienna", "German"),
    ("Switzerland", "CH", "de_CH.UTF-8", "de_CH.UTF-8", "Europe/Zurich", "German (Switzerland)"),
    ("France", "FR", "fr_FR.UTF-8", "fr_FR.UTF-8", "Europe/Paris", "French"),
    ("Belgium", "BE", "fr_BE.UTF-8", "fr_BE.UTF-8", "Europe/Brussels", "Belgian"),
    ("Spain", "ES", "es_ES.UTF-8", "es_ES.UTF-8", "Europe/Madrid", "Spanish"),
    ("Mexico", "MX", "es_MX.UTF-8", "es_MX.UTF-8", "America/Mexico_City", "Spanish (Latin America)"),
    ("Argentina", "AR", "es_AR.UTF-8", "es_AR.UTF-8", "America/Argentina/Buenos_Aires", "Spanish (Latin America)"),
    ("Portugal", "PT", "pt_PT.UTF-8", "pt_PT.UTF-8", "Europe/Lisbon", "Portuguese"),
    ("Brazil", "BR", "pt_BR.UTF-8", "pt_BR.UTF-8", "America/Sao_Paulo", "Portuguese (Brazil)"),
    ("Netherlands", "NL", "nl_NL.UTF-8", "nl_NL.UTF-8", "Europe/Amsterdam", "English (US, international)"),
    ("Denmark", "DK", "da_DK.UTF-8", "da_DK.UTF-8", "Europe/Copenhagen", "Danish"),
    ("Norway", "NO", "nb_NO.UTF-8", "nb_NO.UTF-8", "Europe/Oslo", "Norwegian"),
    ("Sweden", "SE", "sv_SE.UTF-8", "sv_SE.UTF-8", "Europe/Stockholm", "Swedish"),
    ("Finland", "FI", "fi_FI.UTF-8", "fi_FI.UTF-8", "Europe/Helsinki", "Finnish"),
    ("Iceland", "IS", "is_IS.UTF-8", "is_IS.UTF-8", "Atlantic/Reykjavik", "Icelandic"),
    ("Estonia", "EE", "et_EE.UTF-8", "et_EE.UTF-8", "Europe/Tallinn", "Estonian"),
    ("Latvia", "LV", "lv_LV.UTF-8", "lv_LV.UTF-8", "Europe/Riga", "Latvian"),
    ("Lithuania", "LT", "lt_LT.UTF-8", "lt_LT.UTF-8", "Europe/Vilnius", "Lithuanian"),
    ("Poland", "PL", "pl_PL.UTF-8", "pl_PL.UTF-8", "Europe/Warsaw", "Polish"),
    ("Czechia", "CZ", "cs_CZ.UTF-8", "cs_CZ.UTF-8", "Europe/Prague", "Czech"),
    ("Slovakia", "SK", "sk_SK.UTF-8", "sk_SK.UTF-8", "Europe/Bratislava", "Slovak"),
    ("Hungary", "HU", "hu_HU.UTF-8", "hu_HU.UTF-8", "Europe/Budapest", "Hungarian"),
    ("Romania", "RO", "ro_RO.UTF-8", "ro_RO.UTF-8", "Europe/Bucharest", "Romanian"),
    ("Croatia", "HR", "hr_HR.UTF-8", "hr_HR.UTF-8", "Europe/Zagreb", "Croatian"),
    ("Slovenia", "SI", "sl_SI.UTF-8", "sl_SI.UTF-8", "Europe/Ljubljana", "Slovenian"),
    ("Serbia", "RS", "sr_RS.UTF-8", "sr_RS.UTF-8", "Europe/Belgrade", "Serbian"),
    ("North Macedonia", "MK", "mk_MK.UTF-8", "mk_MK.UTF-8", "Europe/Skopje", "Macedonian"),
    ("Bulgaria", "BG", "bg_BG.UTF-8", "bg_BG.UTF-8", "Europe/Sofia", "Bulgarian"),
    ("Greece", "GR", "el_GR.UTF-8", "el_GR.UTF-8", "Europe/Athens", "Greek"),
    ("Turkey", "TR", "tr_TR.UTF-8", "tr_TR.UTF-8", "Europe/Istanbul", "Turkish"),
    ("Russia", "RU", "ru_RU.UTF-8", "ru_RU.UTF-8", "Europe/Moscow", "Russian"),
    ("Ukraine", "UA", "uk_UA.UTF-8", "uk_UA.UTF-8", "Europe/Kyiv", "Ukrainian"),
    ("Belarus", "BY", "be_BY.UTF-8", "be_BY.UTF-8", "Europe/Minsk", "Belarusian"),
    ("Kazakhstan", "KZ", "kk_KZ.UTF-8", "kk_KZ.UTF-8", "Asia/Almaty", "Kazakh"),
    ("Israel", "IL", "he_IL.UTF-8", "he_IL.UTF-8", "Asia/Jerusalem", "Hebrew"),
    ("Japan", "JP", "ja_JP.UTF-8", "ja_JP.UTF-8", "Asia/Tokyo", "Japanese"),
    ("South Korea", "KR", "ko_KR.UTF-8", "ko_KR.UTF-8", "Asia/Seoul", "Korean"),
    ("China", "CN", "zh_CN.UTF-8", "zh_CN.UTF-8", "Asia/Shanghai", "Chinese"),
    ("Taiwan", "TW", "zh_TW.UTF-8", "zh_TW.UTF-8", "Asia/Taipei", "English (US)"),
    ("Singapore", "SG", "en_SG.UTF-8", "en_SG.UTF-8", "Asia/Singapore", "English (US)"),
    ("South Africa", "ZA", "en_ZA.UTF-8", "en_ZA.UTF-8", "Africa/Johannesburg", "English (US)"),
    ("Malta", "MT", "mt_MT.UTF-8", "mt_MT.UTF-8", "Europe/Malta", "Maltese"),
]

KB = {k[0]: k for k in KEYBOARDS}
LANG = {label: loc for label, loc in LANGUAGES}
LANG_BY_LOCALE = {loc: label for label, loc in LANGUAGES}
COUNTRY = {c[0]: c for c in COUNTRIES}


def run(cmd, check=True, input=None, capture=False, quiet=False):
    """Run a command, log it, raise on failure."""
    if isinstance(cmd, str):
        shown, args, shell = cmd, cmd, True
    else:
        shown, args, shell = " ".join(shlex.quote(c) for c in cmd), cmd, False
    with open(LOG, "a") as log:
        log.write(f"$ {shown}\n")
    r = subprocess.run(
        args,
        shell=shell,
        input=input.encode() if isinstance(input, str) else input,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    out = r.stdout.decode(errors="replace")
    with open(LOG, "a") as log:
        log.write(out)
    if not quiet and not capture and out.strip():
        for line in out.rstrip().splitlines()[-15:]:
            print("    " + line)
    if check and r.returncode != 0:
        raise RuntimeError(f"command failed ({r.returncode}): {shown}\n{out[-2000:]}")
    return out


def closure_bytes(path):
    """Total size of a store path and everything it needs (0 if unknown)."""
    try:
        out = subprocess.run(
            ["nix", "--extra-experimental-features", "nix-command", "path-info", "--json", "--recursive", path],
            capture_output=True, text=True, check=True,
        ).stdout
        info = json.loads(out)
        items = info.values() if isinstance(info, dict) else info
        return sum(i.get("narSize", 0) for i in items if i)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return 0


def used_bytes(path):
    st = os.statvfs(path)
    return (st.f_blocks - st.f_bfree) * st.f_frsize


def run_with_progress(cmd, total, where):
    """Run a long command (nixos-install) showing a progress bar, measured by
    how much `where` has filled up against the expected `total` bytes."""
    shown = " ".join(shlex.quote(c) for c in cmd)
    with open(LOG, "a") as log:
        log.write(f"$ {shown}\n")
        log.flush()
        base = used_bytes(where)
        start = time.time()
        p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        width = 30
        while p.poll() is None:
            time.sleep(1)
            done = max(0, used_bytes(where) - base)
            secs = time.time() - start
            if total > 0:
                frac = min(done / total, 0.99)
                bar = "#" * int(frac * width) + "." * (width - int(frac * width))
                rate = done / secs if secs > 0 else 0
                if frac >= 0.99:
                    tail = "finishing (boot loader, settings)…"
                elif rate > 0:
                    left = (total - done) / rate
                    tail = f"{rate / 1e6:5.0f} MB/s, about {int(left // 60)}:{int(left % 60):02d} left"
                else:
                    tail = ""
                line = f"    [{bar}] {frac * 100:3.0f}%  {done / 1e9:4.1f} of {total / 1e9:.1f} GB  {tail}"
            else:
                line = f"    {done / 1e9:4.1f} GB copied, {int(secs // 60)}:{int(secs % 60):02d} elapsed"
            print("\r" + line.ljust(96)[:96], end="", flush=True)
        rc = p.returncode
    if total > 0 and rc == 0:
        print("\r" + f"    [{'#' * width}] 100%  done".ljust(96)[:96], flush=True)
    else:
        print(flush=True)
    if rc != 0:
        tail = open(LOG, errors="replace").read()[-2000:]
        raise RuntimeError(f"command failed ({rc}): {shown}\n{tail}")


# ------------------------------------------------------ system discovery ----
def boot_disk():
    """Disk the live system booted from (never offered as a target)."""
    src = ""
    try:
        src = subprocess.run(["findmnt", "-n", "-o", "SOURCE", "/iso"], capture_output=True, text=True).stdout.strip()
    except FileNotFoundError:
        pass
    if not src:
        src = subprocess.run(["blkid", "-t", f"LABEL={ISO_LABEL}", "-o", "device"], capture_output=True, text=True).stdout.split("\n")[0].strip()
    if not src:
        return ""
    pk = subprocess.run(["lsblk", "-dno", "PKNAME", src], capture_output=True, text=True).stdout.strip()
    return "/dev/" + pk if pk else src


def list_disks():
    out = subprocess.run(
        ["lsblk", "-J", "-b", "-d", "-o", "NAME,PATH,SIZE,MODEL,TYPE,TRAN,RO"], capture_output=True, text=True
    ).stdout
    skip = boot_disk()
    disks = []
    for d in json.loads(out or '{"blockdevices":[]}')["blockdevices"]:
        if d.get("type") != "disk" or d.get("ro") in (True, "1", 1):
            continue
        if d["path"] == skip or re.match(r"/dev/(loop|zram|sr|ram|fd)", d["path"]):
            continue
        size = int(d.get("size") or 0)
        if size < 8 * 1024**3:
            continue
        model = (d.get("model") or "").strip() or "disk"
        tran = d.get("tran") or ""
        label = f"{d['name']}  {size / 1e9:6.1f} GB  {model}" + (f"  ({tran})" if tran else "")
        disks.append((label, d["path"], size))
    return disks


def list_timezones():
    try:
        out = subprocess.run(["timedatectl", "list-timezones", "--no-pager"], capture_output=True, text=True, timeout=5).stdout
        zones = [z for z in out.split() if "/" in z]
        if zones:
            return zones
    except Exception:
        pass
    zones = []
    root = next((r for r in ("/etc/zoneinfo", "/usr/share/zoneinfo") if os.path.isdir(r)), "/etc/zoneinfo")
    for dirpath, _, files in os.walk(root, followlinks=True):
        rel = os.path.relpath(dirpath, root)
        if rel == "." or rel.split("/")[0] in ("posix", "right", "Etc", "SystemV", "US"):
            continue
        if not rel[0].isupper():
            continue
        zones += [f"{rel}/{f}" for f in files if f[0].isupper()]
    return sorted(zones) or ["UTC"]


def scan_wifi():
    """[(ssid, signal, security)] strongest first. Empty if no Wi-Fi/nmcli."""
    try:
        subprocess.run(["nmcli", "device", "wifi", "rescan"], capture_output=True, timeout=10)
        time.sleep(1)
        out = subprocess.run(
            ["nmcli", "-t", "-e", "yes", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"],
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout
    except Exception:
        return []
    nets = {}
    for line in out.splitlines():
        parts = re.split(r"(?<!\\):", line)
        if len(parts) < 3 or not parts[0]:
            continue
        ssid = parts[0].replace("\\:", ":").replace("\\\\", "\\")
        sig = int(parts[1] or 0)
        sec = parts[2] or ""
        if ssid not in nets or nets[ssid][0] < sig:
            nets[ssid] = (sig, sec)
    return sorted(((s, v[0], v[1]) for s, v in nets.items()), key=lambda x: -x[1])


def apply_keyboard_live(kb):
    """Switch the live session to the chosen layout so passwords are typed
    with the same layout the installed system will use."""
    _, layout, variant, keymap = kb
    if os.environ.get("DISPLAY"):
        cmd = ["setxkbmap", "-layout", layout] + (["-variant", variant] if variant else [])
        subprocess.run(cmd, capture_output=True)
    elif os.isatty(0) and os.environ.get("TERM") == "linux":
        subprocess.run(["loadkeys", keymap], capture_output=True)


# ---------------------------------------------------------------- the TUI ----
class Form:
    def __init__(self):
        c = COUNTRY["United States"]
        self.v = {
            "country": c[0],
            "language": LANG_BY_LOCALE[c[2]],
            "timezone": c[4],
            "keyboard": c[5],
            "screen": "Landscape",
            "wifi": "",
            "wifi_security": "",
            "wifi_password": "",
            "fullname": "",
            "username": "",
            "password": "",
            "luks_password": "",
            "disk": "",
            "disk_label": "",
        }
        self.touched = set()  # fields the user set explicitly (not overwritten by country)
        self.fields = [
            ("country", "Country"),
            ("language", "Language"),
            ("timezone", "Time zone"),
            ("keyboard", "Keyboard"),
            ("screen", "Screen"),
            ("wifi", "Wi-Fi network"),
            ("wifi_password", "Wi-Fi password"),
            ("fullname", "Full name"),
            ("username", "Username"),
            ("password", "Password"),
            ("luks_password", "Disk password"),
            ("disk", "Target disk"),
            ("fs", "Filesystem"),
            ("install", None),
        ]
        self.sel = 0
        self.msg = "Keyboard changes apply immediately, so passwords match at boot."
        self.err = False
        self._tz = None
        self._disks = None

    # -- display text for each field
    def show(self, key):
        v = self.v
        if key in ("password", "luks_password"):
            return "•" * min(len(v[key]), 24) if v[key] else "(not set)"
        if key == "wifi_password":
            if not v["wifi"]:
                return "—"
            if not v["wifi_security"]:
                return "(open network)"
            return "•" * min(len(v[key]), 24) if v[key] else "(not set)"
        if key == "wifi":
            return v["wifi"] or "(none — set up later)"
        if key == "disk":
            return v["disk_label"] or "(choose a disk)"
        if key == "fs":
            return "ext4 on LUKS2 (encrypted), EFI boot"
        if key == "fullname":
            return v["fullname"] or "(optional)"
        if key == "username":
            return v["username"] or "(not set)"
        return v.get(key, "")


def draw(scr, f):
    scr.erase()
    h, w = scr.getmaxyx()
    ui.bar(scr, 0, f"{NAME} installer")
    top = 2
    labw = 16
    for i, (key, label) in enumerate(f.fields):
        y = top + i + (1 if key == "install" else 0)
        if y >= h - 2:
            break
        if key == "install":
            btn = "  Install now  "
            ui.button(scr, y, max(2, (w - len(btn) - 2) // 2), btn, f.sel == i)
            continue
        line = f"  {label:<{labw}} {f.show(key)}"
        ui.row(scr, y, 0, w - 1, line, f.sel == i, ui.attr(ui.DIM if key == "fs" else ui.NORMAL))
    ui.keybar(scr, h - 1, [("↑↓", "move"), ("Enter", "change"), ("Tab", "next"), ("Ctrl-C", "quit")])
    if f.msg:
        ui.message(scr, h - 2, 1, ("✗ " if f.err and not f.msg.startswith("✗") else "") + f.msg[: w - 5])
    scr.refresh()


def popup_list(scr, title, items, current=None, filterable=True):
    """Choose from items (list of str). Type to filter. Returns index or None."""
    query = ""
    h, w = scr.getmaxyx()
    ph = min(h - 4, max(8, len(items) + 4))
    pw = min(w - 4, max(40, len(title) + 8, max((len(i) for i in items), default=10) + 6))
    y0, x0 = (h - ph) // 2, (w - pw) // 2
    win = curses.newwin(ph, pw, y0, x0)
    win.keypad(True)
    idx_list = list(range(len(items)))
    sel = items.index(current) if current in items else 0
    scroll = 0
    while True:
        q = query.lower()
        idx_list = [i for i, s in enumerate(items) if q in s.lower()] if q else list(range(len(items)))
        if sel not in idx_list:
            sel = idx_list[0] if idx_list else -1
        hdr = f"{title} " + (f"— filter: {query}_" if filterable and query else ("— type to filter" if filterable else ""))
        ui.frame(win, hdr[: pw - 6])
        rows = ph - 2
        pos = idx_list.index(sel) if sel in idx_list else 0
        if pos < scroll:
            scroll = pos
        if pos >= scroll + rows:
            scroll = pos - rows + 1
        for r, i in enumerate(idx_list[scroll : scroll + rows]):
            ui.row(win, 1 + r, 1, pw - 2, " " + items[i], i == sel)
        if not idx_list:
            ui.put(win, 1, 2, "(no match)", ui.attr(ui.DIM))
        win.refresh()
        k = win.get_wch()
        if k in (curses.KEY_UP,) and idx_list:
            sel = idx_list[max(0, pos - 1)]
        elif k in (curses.KEY_DOWN,) and idx_list:
            sel = idx_list[min(len(idx_list) - 1, pos + 1)]
        elif k == curses.KEY_PPAGE and idx_list:
            sel = idx_list[max(0, pos - rows)]
        elif k == curses.KEY_NPAGE and idx_list:
            sel = idx_list[min(len(idx_list) - 1, pos + rows)]
        elif k in ("\n", "\r", curses.KEY_ENTER):
            return sel if sel >= 0 else None
        elif k == "\x1b":
            if query:
                query = ""
            else:
                return None
        elif k in (curses.KEY_BACKSPACE, "\x7f", "\b"):
            query = query[:-1]
        elif filterable and isinstance(k, str) and k.isprintable():
            query += k


def popup_input(scr, title, value="", secret=False, hint=""):
    h, w = scr.getmaxyx()
    pw = min(w - 4, 64)
    win = curses.newwin(5 if hint else 4, pw, h // 2 - 2, (w - pw) // 2)
    win.keypad(True)
    buf = list(value)
    curses.curs_set(1)
    try:
        while True:
            ui.frame(win, title[: pw - 6])
            at = ui.field(win, 1, 2, pw - 4, "".join(buf), True, secret)
            if hint:
                ui.put(win, 3, 2, hint[: pw - 4], ui.attr(ui.DIM))
            win.move(1, at)
            win.refresh()
            k = win.get_wch()
            if k in ("\n", "\r", curses.KEY_ENTER):
                return "".join(buf)
            if k == "\x1b":
                return None
            if k in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                if buf:
                    buf.pop()
            elif k == "\x15":  # Ctrl-U
                buf = []
            elif isinstance(k, str) and k.isprintable():
                buf.append(k)
    finally:
        curses.curs_set(0)


def popup_message(scr, title, text, confirm_word=None):
    """Show text. If confirm_word, user must type it; returns True/False."""
    h, w = scr.getmaxyx()
    lines = []
    pw = min(w - 4, 72)
    for para in text.split("\n"):
        while len(para) > pw - 4:
            cut = para.rfind(" ", 0, pw - 4)
            cut = cut if cut > 0 else pw - 4
            lines.append(para[:cut])
            para = para[cut:].lstrip()
        lines.append(para)
    ph = len(lines) + (5 if confirm_word else 3)
    win = curses.newwin(ph, pw, max(0, (h - ph) // 2), (w - pw) // 2)
    win.keypad(True)
    typed = ""
    while True:
        ui.frame(win, title)
        for i, l in enumerate(lines):
            ui.put(win, 1 + i, 2, l, ui.attr(ui.NORMAL))
        if confirm_word:
            ui.put(win, ph - 3, 2, f"Type {confirm_word} to continue, Esc to go back:", ui.attr(ui.KEY))
            ui.field(win, ph - 2, 2, pw - 4, typed, True)
        else:
            ui.button(win, ph - 2, pw - 9, "OK", True)
        win.refresh()
        k = win.get_wch()
        if not confirm_word:
            return True
        if k == "\x1b":
            return False
        if k in ("\n", "\r", curses.KEY_ENTER):
            if typed == confirm_word:
                return True
            typed = ""
        elif k in (curses.KEY_BACKSPACE, "\x7f", "\b"):
            typed = typed[:-1]
        elif isinstance(k, str) and k.isprintable():
            typed += k


def ask_password(scr, title, minlen):
    p1 = popup_input(scr, title, secret=True, hint=f"At least {minlen} characters.")
    if p1 is None:
        return None, ""
    if len(p1) < minlen:
        return None, f"{title}: use at least {minlen} characters."
    p2 = popup_input(scr, title + " (repeat)", secret=True)
    if p2 is None:
        return None, ""
    if p1 != p2:
        return None, f"{title}: the two entries did not match."
    return p1, ""


def edit(scr, f, key):
    v = f.v
    f.msg, f.err = "", False
    if key == "country":
        names = [c[0] for c in COUNTRIES]
        i = popup_list(scr, "Country", names, v["country"])
        if i is None:
            return
        c = COUNTRIES[i]
        v["country"] = c[0]
        # Fill sensible defaults unless the user already chose them.
        if "language" not in f.touched:
            v["language"] = LANG_BY_LOCALE.get(c[2], v["language"])
        if "timezone" not in f.touched:
            v["timezone"] = c[4]
        if "keyboard" not in f.touched:
            v["keyboard"] = c[5]
            apply_keyboard_live(KB[v["keyboard"]])
        f.msg = "Language, time zone and keyboard follow the country unless you change them."
    elif key == "language":
        names = [l[0] for l in LANGUAGES]
        i = popup_list(scr, "Language", names, v["language"])
        if i is not None:
            v["language"] = names[i]
            f.touched.add(key)
    elif key == "timezone":
        if f._tz is None:
            f._tz = list_timezones()
        i = popup_list(scr, "Time zone", f._tz, v["timezone"])
        if i is not None:
            v["timezone"] = f._tz[i]
            f.touched.add(key)
    elif key == "keyboard":
        names = [k[0] for k in KEYBOARDS]
        i = popup_list(scr, "Keyboard layout", names, v["keyboard"])
        if i is not None:
            v["keyboard"] = names[i]
            f.touched.add(key)
            apply_keyboard_live(KEYBOARDS[i])
            f.msg = f"Keyboard switched to {names[i]}. Test it: type in any field."
    elif key == "screen":
        opts = ["Landscape", "Portrait"]
        i = popup_list(scr, "Screen orientation", opts, v["screen"], filterable=False)
        if i is not None:
            v["screen"] = opts[i]
    elif key == "wifi":
        f.msg = "Scanning for Wi-Fi networks..."
        draw(scr, f)
        nets = scan_wifi()
        items = ["(none — set up later)"] + [
            f"{s}   {'▂▄▆█'[: max(1, min(4, sig // 25 + 1))]:<4} {sig:3d}%  {sec or 'open'}" for s, sig, sec in nets
        ] + ["Other network (type the name)…"]
        f.msg = "" if nets else "No networks found (no Wi-Fi card, or switched off). You can type a name."
        i = popup_list(scr, "Wi-Fi network", items, None)
        if i is None:
            return
        if i == 0:
            v["wifi"], v["wifi_security"], v["wifi_password"] = "", "", ""
        elif i == len(items) - 1:
            s = popup_input(scr, "Wi-Fi network name (SSID)", v["wifi"])
            if s:
                v["wifi"], v["wifi_security"] = s, "WPA2"
        else:
            s, _, sec = nets[i - 1]
            v["wifi"], v["wifi_security"] = s, sec
            if not sec:
                v["wifi_password"] = ""
        if v["wifi"] and v["wifi_security"] and not v["wifi_password"]:
            edit(scr, f, "wifi_password")
    elif key == "wifi_password":
        if not v["wifi"]:
            f.msg = "Choose a Wi-Fi network first."
            return
        if not v["wifi_security"]:
            f.msg = "This network is open; no password needed."
            return
        p = popup_input(scr, f"Password for {v['wifi']}", v["wifi_password"], secret=True)
        if p is not None:
            v["wifi_password"] = p
    elif key == "fullname":
        s = popup_input(scr, "Full name (optional)", v["fullname"])
        if s is not None:
            v["fullname"] = s.strip()
            if not v["username"] and s.strip():
                guess = re.sub(r"[^a-z0-9]", "", s.strip().split()[0].lower())
                if guess and guess[0].isalpha():
                    v["username"] = guess
    elif key == "username":
        s = popup_input(scr, "Username", v["username"], hint="lowercase letters, digits, - and _")
        if s is not None:
            v["username"] = s.strip()
    elif key == "password":
        p, err = ask_password(scr, "User password", 1)
        if p is not None:
            v["password"] = p
        elif err:
            f.msg, f.err = err, True
    elif key == "luks_password":
        p, err = ask_password(scr, "Disk encryption password", LUKS_MIN)
        if p is not None:
            v["luks_password"] = p
        elif err:
            f.msg, f.err = err, True
    elif key == "disk":
        disks = list_disks()
        if not disks:
            f.msg, f.err = "No suitable disk found (needs 8 GB+, the USB stick itself is excluded).", True
            return
        labels = [d[0] for d in disks]
        i = popup_list(scr, "Install on (ALL DATA WILL BE ERASED)", labels, v["disk_label"], filterable=False)
        if i is not None:
            v["disk_label"], v["disk"] = disks[i][0], disks[i][1]
    elif key == "fs":
        f.msg = "MeccanicOS installs ext4 inside full-disk LUKS2 encryption."


def validate(v):
    errs = []
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", v["username"] or ""):
        errs.append("Username: lowercase letters/digits, starting with a letter.")
    elif v["username"] in ("root", "nixos", "nobody", "daemon", "bin", "sys", "messagebus", "sshd", "nixbld"):
        errs.append(f"Username '{v['username']}' is reserved.")
    if not v["password"]:
        errs.append("Set a user password.")
    if len(v["luks_password"]) < LUKS_MIN:
        errs.append(f"Set a disk password ({LUKS_MIN}+ characters).")
    if not v["disk"]:
        errs.append("Choose the target disk.")
    if v["wifi"] and v["wifi_security"] and len(v["wifi_password"]) < 8:
        errs.append("Wi-Fi password must be at least 8 characters.")
    return errs


def tui(scr):
    ui.init()
    scr.keypad(True)
    f = Form()
    apply_keyboard_live(KB[f.v["keyboard"]])
    n = len(f.fields)
    while True:
        draw(scr, f)
        k = scr.get_wch()
        if k in (curses.KEY_UP, curses.KEY_BTAB):
            f.sel = (f.sel - 1) % n
        elif k in (curses.KEY_DOWN, "\t"):
            f.sel = (f.sel + 1) % n
        elif k == curses.KEY_RESIZE:
            pass
        elif k in ("\n", "\r", curses.KEY_ENTER, " "):
            key = f.fields[f.sel][0]
            if key != "install":
                edit(scr, f, key)
                continue
            errs = validate(f.v)
            if errs:
                popup_message(scr, "Almost there", "\n".join("• " + e for e in errs))
                continue
            ok = popup_message(
                scr,
                "Erase disk?",
                f"ALL DATA on {f.v['disk_label'].strip()} will be erased and {NAME} installed.\n\n"
                f"User: {f.v['username']} (passwordless sudo)   Keyboard: {f.v['keyboard']}\n"
                f"Language: {f.v['language']}   Time zone: {f.v['timezone']}",
                confirm_word="YES",
            )
            if ok:
                return f.v
        elif k in ("q", "Q"):
            if popup_message(scr, "Quit", "Leave the installer without changing anything?", confirm_word="y"):
                return None


# ------------------------------------------------------------- backend ----
def answers_to_settings(v):
    c = COUNTRY[v["country"]]
    kb = KB[v["keyboard"]]
    lang = LANG.get(v["language"], v["language"])
    return {
        "country": c[1],
        "lang": lang,
        "formats": c[3],
        "timezone": v["timezone"],
        "xkb_layout": kb[1],
        "xkb_variant": kb[2],
        "keymap": kb[3],
        "portrait": v["screen"] == "Portrait",
    }


def step(n, total, text):
    print(f"\n\033[1;37;100m [{n}/{total}] {text} \033[0m", flush=True)


def partitions_of(disk):
    out = subprocess.run(["lsblk", "-lnpo", "NAME,TYPE", disk], capture_output=True, text=True).stdout
    return [l.split()[0] for l in out.splitlines() if l.split()[1:] == ["part"]]


def release_disk(disk):
    """Unmount/close anything using the target disk."""
    out = subprocess.run(["lsblk", "-lnpo", "NAME,TYPE,MOUNTPOINTS", disk], capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.split(None, 2)
        name, typ = parts[0], parts[1]
        if len(parts) > 2 and parts[2].strip():
            for mp in parts[2].split("\\x0a"):
                if mp.strip() == "[SWAP]":
                    run(["swapoff", name], check=False, quiet=True)
                elif mp.strip():
                    run(["umount", "-R", mp.strip()], check=False, quiet=True)
        if typ == "crypt":
            run(["cryptsetup", "close", name], check=False, quiet=True)


def install(v):
    s = answers_to_settings(v)
    disk = v["disk"]
    total = 8
    open(LOG, "w").close()
    os.chmod(LOG, 0o600)
    print(f"\033[1m{NAME} installer\033[0m — log: {LOG}")

    if not TEST:
        if not os.path.isdir("/sys/firmware/efi"):
            raise RuntimeError(
                "This PC started the USB stick in legacy BIOS mode.\n"
                "Reboot, open the firmware boot menu and pick the UEFI entry for the stick."
            )
        if not SYSTEM or not os.path.exists(SYSTEM):
            raise RuntimeError("Prebuilt system not found on the ISO (MECCANICOS_SYSTEM).")

    step(1, total, f"Partitioning {disk}")
    release_disk(disk)
    run(["wipefs", "-af", disk], quiet=True)
    layout = (
        "label: gpt\n"
        'size=1GiB, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, name="MOS_EFI"\n'
        'type=CA7D7CCB-63ED-4C53-861C-1742536059CC, name="MOS_CRYPT"\n'
    )
    run(["sfdisk", "--wipe", "always", "--wipe-partitions", "always", disk], input=layout)
    run(["udevadm", "settle"], check=False, quiet=True)
    run(["partx", "-u", disk], check=False, quiet=True)
    time.sleep(1)
    parts = partitions_of(disk)
    if len(parts) < 2:
        raise RuntimeError(f"Expected 2 partitions on {disk}, found {parts}")
    efi, crypt = parts[0], parts[1]

    step(2, total, "Encrypting (LUKS2)")
    pw = v["luks_password"]
    run(["cryptsetup", "luksFormat", "--batch-mode", "--type", "luks2", "--label", "MOS_CRYPT", "--key-file", "-", crypt], input=pw)
    run(["cryptsetup", "open", "--allow-discards", "--key-file", "-", crypt, MAPPER], input=pw)

    step(3, total, "Creating filesystems")
    run(["mkfs.fat", "-F", "32", "-n", "MOS_EFI", efi])
    run(["mkfs.ext4", "-q", "-F", "-L", "MECCANICOS_ROOT", f"/dev/mapper/{MAPPER}"])
    os.makedirs(TARGET, exist_ok=True)
    run(["mount", f"/dev/mapper/{MAPPER}", TARGET])
    os.makedirs(f"{TARGET}/boot", exist_ok=True)
    run(["mount", "-o", "umask=0077", efi, f"{TARGET}/boot"])

    step(4, total, f"Copying {NAME} to disk (no download needed)")
    if TEST:
        print("    [test mode] skipping nixos-install")
        os.makedirs(f"{TARGET}/etc", exist_ok=True)
        os.makedirs(f"{TARGET}/boot/loader/entries", exist_ok=True)
        with open(f"{TARGET}/boot/loader/entries/nixos-generation-1.conf", "w") as fh:
            fh.write("title MeccanicOS\nlinux /EFI/nixos/kernel.efi\noptions init=/nix/store/x/init loglevel=4\n")
    else:
        try:
            total = int(os.environ.get("MECCANICOS_SYSTEM_DISK_BYTES", "0"))
        except ValueError:
            total = 0
        if not total:  # plain size, plus ~10% for ext4's 4 KiB blocks
            total = int(closure_bytes(SYSTEM) * 1.1)
        if total:
            print(f"    {total / 1e9:.1f} GB to copy")
        run_with_progress(
            ["nixos-install", "--root", TARGET, "--system", SYSTEM, "--no-root-passwd", "--no-channel-copy"],
            total,
            TARGET,
        )

    step(5, total, "Language, keyboard, time zone, screen")
    write_runtime_config(v, s)

    step(6, total, f"Creating user {v['username']}")
    create_user(v)

    step(7, total, "Saving your configuration to /etc/nixos")
    write_nixos_config(v, s)

    step(8, total, "Finishing")
    with open(LOG) as src, open(f"{TARGET}/etc/meccanicos/install.log", "w") as dst:
        dst.write(src.read())
    # When the ISO it was installed from was built (System Info shows it).
    if os.path.exists("/etc/meccanicos/version"):
        with open("/etc/meccanicos/version") as src, open(f"{TARGET}/etc/meccanicos/version", "w") as dst:
            dst.write(src.read())
    run(["sync"])
    run(["umount", "-R", TARGET], check=False)
    run(["cryptsetup", "close", MAPPER], check=False)
    return True


def write(path, text, mode=0o644):
    full = TARGET + path
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as fh:
        fh.write(text)
    os.chmod(full, mode)


def write_runtime_config(v, s):
    lc = s["formats"]
    locale_conf = f"LANG={s['lang']}\n"
    if lc != s["lang"]:
        for var in ("LC_TIME", "LC_NUMERIC", "LC_MONETARY", "LC_PAPER", "LC_MEASUREMENT", "LC_ADDRESS", "LC_TELEPHONE"):
            locale_conf += f"{var}={lc}\n"
    write("/etc/locale.conf", locale_conf)
    write("/etc/vconsole.conf", f"KEYMAP={s['keymap']}\n")
    lt = TARGET + "/etc/localtime"
    if os.path.lexists(lt):
        os.remove(lt)
    os.symlink(f"/etc/zoneinfo/{s['timezone']}", lt)
    write(
        "/etc/meccanicos/settings",
        f"# Written by mos-install. Read at login for keyboard/screen setup.\n"
        f"COUNTRY={s['country']}\nXKB_LAYOUT={s['xkb_layout']}\nXKB_VARIANT={s['xkb_variant']}\n"
        f"ORIENTATION={'portrait' if s['portrait'] else 'landscape'}\n",
    )
    write("/etc/modprobe.d/mos-regdom.conf", f"options cfg80211 ieee80211_regdom={s['country']}\n")

    if v["wifi"]:
        ssid = v["wifi"]
        fname = re.sub(r"[^A-Za-z0-9._-]", "_", ssid) or "wifi"
        sec = ""
        if v["wifi_security"]:
            sec = f"\n[wifi-security]\nkey-mgmt=wpa-psk\npsk={v['wifi_password']}\n"
        uuid = open("/proc/sys/kernel/random/uuid").read().strip()
        write(
            f"/etc/NetworkManager/system-connections/{fname}.nmconnection",
            f"[connection]\nid={ssid}\nuuid={uuid}\ntype=wifi\nautoconnect=true\n\n"
            f"[wifi]\nmode=infrastructure\nssid={ssid}\n{sec}\n[ipv4]\nmethod=auto\n\n[ipv6]\nmethod=auto\n",
            mode=0o600,
        )
        print(f"    Wi-Fi '{ssid}' will connect automatically.")

    # Make the first boot use the right keyboard for the LUKS prompt and the
    # right console rotation. (local.nix bakes these into later generations.)
    extra = f"vconsole.keymap={s['keymap']}" + (" fbcon=rotate:1" if s["portrait"] else "")
    entries = f"{TARGET}/boot/loader/entries"
    for e in sorted(os.listdir(entries)) if os.path.isdir(entries) else []:
        p = os.path.join(entries, e)
        lines = open(p).read().splitlines()
        lines = [l + " " + extra if l.startswith("options ") and extra not in l else l for l in lines]
        open(p, "w").write("\n".join(lines) + "\n")
    print(f"    {s['lang']}, keyboard {s['xkb_layout']}{'/' + s['xkb_variant'] if s['xkb_variant'] else ''}, {s['timezone']}")


def enter(cmd, input=None):
    """Run a shell command inside the installed system."""
    if TEST:
        print(f"    [test mode] nixos-enter: {cmd}")
        return ""
    return run(["nixos-enter", "--root", TARGET, "-c", cmd], input=input)


def create_user(v):
    u = v["username"]
    name = v["fullname"].replace(":", " ")
    enter(f"useradd -m -g users -G {USER_GROUPS} -s /run/current-system/sw/bin/bash -c {shlex.quote(name)} {u}")
    enter("chpasswd", input=f"{u}:{v['password']}\n")
    # The user's own SSH key, to log in to other machines: Ed25519 (OpenSSH's
    # default; no key-size or nonce pitfalls). No passphrase: it is on the
    # encrypted disk. -a 100 hardens one added later with ssh-keygen -p.
    ssh = f"/home/{u}/.ssh"
    enter(
        f"install -d -m 700 -o {u} -g users {ssh} && "
        f"ssh-keygen -q -t ed25519 -a 100 -N '' -C {shlex.quote(u + '@' + NAME.lower())} -f {ssh}/id_ed25519 && "
        f"chown {u}:users {ssh}/id_ed25519 {ssh}/id_ed25519.pub"
    )
    print(f"    {u}: member of wheel (passwordless sudo). Root login is disabled.")
    print("    SSH key: ~/.ssh/id_ed25519.pub")


def nix_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("${", "\\${") + '"'


def write_nixos_config(v, s):
    dst = TARGET + "/etc/nixos"
    if FLAKE and os.path.isdir(FLAKE):
        run(["cp", "-rT", "--no-preserve=mode,ownership", FLAKE, dst], quiet=True)
    else:
        os.makedirs(dst, exist_ok=True)
    if not TEST:
        hw = run(
            ["nixos-generate-config", "--root", TARGET, "--no-filesystems", "--show-hardware-config"],
            capture=True,
        )
        write("/etc/nixos/hardware-configuration.nix", hw)
    extra = ""
    if s["formats"] != s["lang"]:
        extra = "  i18n.extraLocaleSettings = {\n" + "".join(
            f"    {k} = {nix_str(s['formats'])};\n"
            for k in ("LC_TIME", "LC_NUMERIC", "LC_MONETARY", "LC_PAPER", "LC_MEASUREMENT", "LC_ADDRESS", "LC_TELEPHONE")
        ) + "  };\n"
    params = [f"vconsole.keymap={s['keymap']}"] + (["fbcon=rotate:1"] if s["portrait"] else [])
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    local = f"""# Choices made in mos-install on {stamp}.
# Edit freely, then apply with:  mos-rebuild
{{ ... }}:
{{
  time.timeZone = {nix_str(s['timezone'])};
  i18n.defaultLocale = {nix_str(s['lang'])};
{extra}  console.keyMap = {nix_str(s['keymap'])};
  services.xserver.xkb = {{
    layout = {nix_str(s['xkb_layout'])};
    variant = {nix_str(s['xkb_variant'])};
  }};
  boot.kernelParams = [ {' '.join(nix_str(p) for p in params)} ];
  boot.extraModprobeConfig = "options cfg80211 ieee80211_regdom={s['country']}";
  # meccanicos.autoUpgrade = false;   # uncomment to stop weekly background updates
  users.users.{v['username']} = {{
    isNormalUser = true;
    description = {nix_str(v['fullname'])};
    extraGroups = [ {' '.join(nix_str(g) for g in USER_GROUPS.split(','))} ];
    # Password is managed with `passwd` (users.mutableUsers = true).
    # SSH is key-only: add keys here or in ~/.ssh/authorized_keys
    openssh.authorizedKeys.keys = [ ];
  }};
}}
"""
    write("/etc/nixos/local.nix", local)
    # The MeccanicOS version /etc/nixos came from (mos-update shows what changed).
    write("/etc/nixos/.mos-commit", os.environ.get("MECCANICOS_COMMIT", "unknown") + "\n")
    print("    /etc/nixos is a copy of the distro flake + local.nix with these choices.")


def main():
    if os.geteuid() != 0 and not TEST:
        print("Run as root (the mos-install wrapper does this for you).")
        return 1
    if len(sys.argv) > 2 and sys.argv[1] == "--config":
        v = json.load(open(sys.argv[2]))
    else:
        os.environ.setdefault("ESCDELAY", "25")
        v = curses.wrapper(tui)
        if v is None:
            print("Nothing was changed.")
            return 0
    try:
        install(v)
    except (Exception, KeyboardInterrupt) as e:  # noqa: BLE001
        if isinstance(e, KeyboardInterrupt):
            print(f"\n\033[1;31mInstallation cancelled.\033[0m The disk is incomplete. Full log: {LOG}")
        else:
            print(f"\n\033[1;31mInstallation failed:\033[0m {e}\nFull log: {LOG}")
        run(["umount", "-R", TARGET], check=False, quiet=True)
        run(["cryptsetup", "close", MAPPER], check=False, quiet=True)
        input("\nPress Enter to close.")
        return 1
    print(f"\n\033[1;32m{NAME} is installed.\033[0m Remove the USB stick and reboot.")
    print("At boot, type your disk password; then log in as", v["username"])
    if not TEST and sys.stdin.isatty():
        a = input("\nReboot now? [Y/n] ").strip().lower()
        if a in ("", "y", "yes"):
            subprocess.run(["systemctl", "reboot"])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:  # Ctrl+C: curses.wrapper has restored the terminal
        sys.exit(130)
