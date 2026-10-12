#!/usr/bin/env python3
"""
Generate MeccanicOS's own icons: the ones you see all the time (terminal,
files, browser, vault, settings, ...), drawn like the wallpaper.

    python3 branding/icons.py          (no dependencies)

Writes branding/icons/<glyph>.svg. Each is a brushed graphite plate with a
thin border, the symbol in off-white lines and one detail in amber (what is
current or needs you, as everywhere else). The colours are
modules/style.nix's. modules/branding.nix installs them as the MeccanicOS
icon theme, under the icon names in its `icons` list; every other icon
comes from Kora (pgrey), which the theme inherits.
"""
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# modules/style.nix
TEXT = "#e8e6e1"
DIM = "#8b929a"
AMBER = "#f8a800"
LINE = "#3a4048"

W = 3.5  # line width, in a 64 x 64 drawing


def line(d, color=TEXT, width=W, extra=""):
    return (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" '
            f'stroke-linecap="round" stroke-linejoin="round"{extra}/>')


def amber(d, width=W):
    return line(d, AMBER, width)


def dot(x, y, r=2.6, color=AMBER):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}"/>'


def circle(x, y, r, color=TEXT, width=W):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="none" stroke="{color}" stroke-width="{width}"/>'


def rect(x, y, w, h, color=TEXT, width=W, rx=1.5):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="none" '
            f'stroke="{color}" stroke-width="{width}"/>')


def gear(cx, cy, r_root, r_tip, teeth):
    """A spur gear's outline, as in the wallpaper's drawing."""
    pts = []
    for i in range(teeth):
        a = 2 * math.pi * i / teeth
        step = 2 * math.pi / teeth
        for frac, r in ((0.0, r_root), (0.18, r_tip), (0.5, r_tip), (0.68, r_root)):
            t = a + frac * step
            pts.append(f"{cx + r * math.cos(t):.2f} {cy + r * math.sin(t):.2f}")
    return "M" + " L".join(pts) + " Z"


GLYPHS = {
    # A prompt and an amber cursor.
    "terminal": line("M18 22 L28 32 L18 42") + amber("M32 43 H46"),
    # A folder; its tab in amber.
    "files": line("M14 26 V46 H50 V26 Z") + amber("M14 26 V20 H26 L30 26"),
    # A globe; the equator in amber.
    "browser": circle(32, 32, 16) + line("M32 16 C23 22 23 42 32 48 C41 42 41 22 32 16")
    + amber("M16 32 H48"),
    # A padlock; the keyhole in amber.
    "vault": line("M24 30 V24 A8 8 0 0 1 40 24 V30") + rect(19, 30, 26, 19)
    + dot(32, 38, 2.8) + amber("M32 40 V44", 3),
    # A box being filled: install an app.
    "software": line("M16 26 L32 18 L48 26 V42 L32 50 L16 42 Z M16 26 L32 34 L48 26 M32 34 V50")
    + amber("M24 22 L40 30"),
    # Two arrows round: update.
    "update": line("M45 30 A13 13 0 0 0 21 24 M19 34 A13 13 0 0 0 43 40")
    + amber("M45 20 V30 H35") + amber("M19 44 V34 H29"),
    # Three connected nodes; the one you are on in amber.
    "network": line("M32 22 L20 42 M32 22 L44 42 M20 42 H44") + circle(20, 42, 4.5)
    + circle(44, 42, 4.5) + f'<circle cx="32" cy="22" r="5.5" fill="{AMBER}"/>',
    # The same, cut.
    "offline": line("M32 22 L20 42 M20 42 H27 M37 42 H44") + circle(20, 42, 4.5)
    + circle(44, 42, 4.5) + circle(32, 22, 5) + amber("M16 16 L48 48"),
    # A chip; its core in amber.
    "ai": rect(21, 21, 22, 22)
    + line("M27 21 V15 M37 21 V15 M27 43 V49 M37 43 V49 M21 27 H15 M21 37 H15 M43 27 H49 M43 37 H49")
    + f'<rect x="28" y="28" width="8" height="8" fill="{AMBER}"/>',
    # A gear; its hub in amber.
    "settings": line(gear(32, 32, 12.5, 17, 10), width=3) + circle(32, 32, 5, AMBER),
    # Power.
    "power": line("M23 21 A14 14 0 1 0 41 21") + amber("M32 14 V31"),
    # An arrow into a drive: install MeccanicOS.
    "install": rect(14, 40, 36, 10) + dot(43, 45, 2.2) + amber("M32 13 V32 M24 24 L32 32 L40 24"),
    # i.
    "info": circle(32, 32, 16) + line("M32 30 V42") + dot(32, 24, 2.8),
    # A clock turning back: restore from a backup.
    "restore": line("M18 34 A14 14 0 1 0 22 22") + line("M16 16 V24 H24") + amber("M32 24 V33 L38 37"),
    # ?
    "help": circle(32, 32, 16) + line("M26.5 27 A5.5 5.5 0 1 1 34 32 C32.5 33 32 34 32 36")
    + dot(32, 42, 2.6),
    # A wrench: fix the configuration.
    "doctor": line("M20 44 L33 31 M30 25 A9 9 0 0 0 39 37 L44 32 L39 30 L37 25 L42 20 A9 9 0 0 0 30 25",
                   width=3.2) + amber("M17 47 L22 42", 5),
    # A key.
    "key": circle(23, 32, 7) + line("M30 32 H49 M43 32 V38 M48 32 V36") + dot(23, 32, 2.4),
    # A shield; the check in amber.
    "shield": line("M32 14 L47 20 V30 C47 40 40 47 32 50 C24 47 17 40 17 30 V20 Z")
    + amber("M25 32 L30 37 L39 27"),
    # A keyboard; the space bar in amber.
    "keyboard": rect(12, 21, 40, 23)
    + line("M19 28 H20 M26 28 H27 M32 28 H33 M38 28 H39 M44 28 H45", width=3.2) + amber("M23 37 H41"),
    # A printer; its light in amber.
    "printer": line("M22 26 V16 H42 V26 M22 40 H16 V26 H48 V40 H42") + rect(22, 36, 20, 13)
    + dot(42, 31, 2.2),
    # A trace on axes.
    "monitor": line("M14 16 V48 H50") + amber("M18 38 H24 L28 28 L34 44 L39 32 L42 36 H48"),
    # A page; the line being written in amber.
    "editor": line("M20 14 H38 L46 22 V50 H20 Z M38 14 V22 H46 M25 32 H40 M25 38 H40 M25 44 H33")
    + amber("M25 26 H32"),
    # Crop marks round a lens.
    "screenshot": line("M14 22 V14 H22 M42 14 H50 V22 M50 42 V50 H42 M22 50 H14 V42") + circle(32, 32, 7, AMBER),
    # A screen.
    "display": rect(12, 16, 40, 26) + line("M32 42 V48 M24 48 H40") + amber("M18 36 H28"),
    # Light and dark, the look.
    "appearance": circle(32, 32, 16) + f'<path d="M32 16 A16 16 0 0 1 32 48 Z" fill="{TEXT}"/>'
    + dot(24, 32, 2.6),
    # A battery, its charge in amber.
    "battery": rect(13, 24, 34, 16) + line("M47 29 H50 V35 H47")
    + f'<rect x="18" y="29" width="16" height="6" fill="{AMBER}"/>',
    # A drive; its light in amber.
    "disks": rect(12, 22, 40, 20) + line("M18 32 H32") + dot(44, 32, 2.6),
    # </>.
    "code": line("M24 22 L14 32 L24 42 M40 22 L50 32 L40 42") + amber("M36 18 L28 46"),
    # A clipboard, its clip in amber.
    "clipboard": line("M24 17 H18 V50 H46 V17 H40 M24 30 H40 M24 37 H40 M24 44 H33")
    + f'<rect x="25" y="13" width="14" height="7" rx="1.5" fill="{AMBER}"/>',
    # The Bluetooth rune.
    "bluetooth": line("M23 24 L41 40 L32 48 V16 L41 24 L23 40") + dot(18, 32, 2.2) + dot(46, 32, 2.2),
    # A box with an amber zip: archives.
    "archive": rect(16, 18, 32, 30) + line("M16 26 H48")
    + line("M32 26 V40", AMBER, 3.5, ' stroke-dasharray="2 3"'),
    # A picture; the sun in amber.
    "image": rect(13, 17, 38, 30) + line("M17 43 L27 32 L35 40 L40 35 L47 42") + dot(40, 25, 3.4),
    # A page under a lens.
    "document": line("M33 50 H18 V14 H34 L42 22 V31 M34 14 V22 H42")
    + circle(39, 41, 6, AMBER) + amber("M43.5 45.5 L49 51"),
    # Two pages: office documents.
    "office": line("M24 14 H42 L48 20 V44 H24 Z M42 14 V20 H48") + line("M24 20 H16 V50 H40 V44")
    + amber("M29 28 H43 M29 34 H43 M29 40 H37", 3),
    # Three sliders; one knob in amber.
    "mixer": line("M20 14 V50 M32 14 V50 M44 14 V50", DIM, 3)
    + f'<rect x="15" y="34" width="10" height="6" rx="1" fill="{TEXT}"/>'
    + f'<rect x="27" y="20" width="10" height="6" rx="1" fill="{AMBER}"/>'
    + f'<rect x="39" y="28" width="10" height="6" rx="1" fill="{TEXT}"/>',
    # A screen with play and a progress line.
    "video": rect(12, 16, 40, 30) + line("M28 24 L38 31 L28 38 Z") + amber("M12 52 H34", 3)
    + line("M34 52 H52", DIM, 3),
    # The door out.
    "logout": line("M30 16 H16 V48 H30") + amber("M26 32 H48 M40 24 L48 32 L40 40"),
    # A speaker, the sound in amber: read aloud.
    "speaker": line("M14 26 H22 L32 18 V46 L22 38 H14 Z") + amber("M38 26 A8 8 0 0 1 38 38 M43 21 A15 15 0 0 1 43 43"),
    # A graphics card, its fan in amber.
    "gpu": rect(10, 20, 44, 22) + line("M14 42 V48 M22 42 V46 M28 42 V46") + circle(38, 31, 6, AMBER)
    + line("M16 27 H26 M16 33 H26", DIM, 3),
    # A flatbed scanner, the light bar in amber.
    "scanner": line("M12 36 H52 V46 H12 Z M16 36 L44 18") + amber("M18 41 H40", 3),
    # A bell, its clapper in amber.
    "bell": line("M20 42 V30 A12 12 0 0 1 44 30 V42 L48 46 H16 Z M32 18 V15") + amber("M28 50 H36", 3),
    # A screen with its top bar in amber: the top bar's settings.
    "panel": rect(12, 16, 40, 30) + amber("M14 21 H50", 3) + line("M18 30 H32 M18 36 H28", DIM, 3),
    # A list with an amber play mark: what starts with the session.
    "session": line("M28 20 H48 M28 32 H48 M28 44 H48") + amber("M15 26 L23 32 L15 38 Z"),
    # A figure in a circle.
    "accessibility": circle(32, 32, 17) + dot(32, 22, 2.8, TEXT) + line("M22 28 H42 M32 28 V38 L26 46 M32 38 L38 46")
    + amber("M22 28 H42"),
    # Three overlapping circles, one in amber: colour.
    "color": circle(26, 26, 9) + circle(38, 26, 9) + circle(32, 37, 9, AMBER),
    # A page with an amber tick: the apps that open things.
    "defaults": line("M20 14 H38 L46 22 V50 H20 Z M38 14 V22 H46") + amber("M25 34 L30 40 L40 28"),
    # A mouse, its wheel in amber.
    "mouse": line("M22 26 A10 10 0 0 1 42 26 V38 A10 10 0 0 1 22 38 Z M22 30 H42") + amber("M32 20 V25", 3),
    # A USB plug, its contacts in amber: removable drives.
    "usb": line("M22 30 H42 V50 H22 Z M26 30 V16 H38 V30") + amber("M30 21 V25 M34 21 V25", 3),
    # Four workspaces, the current one in amber.
    "workspaces": rect(13, 15, 17, 15) + rect(34, 15, 17, 15) + rect(13, 34, 17, 15)
    + f'<rect x="34" y="34" width="17" height="15" rx="1.5" fill="{AMBER}"/>',
    # A window, its title bar in amber.
    "window": rect(12, 16, 40, 32) + amber("M14 22 H50", 4) + line("M42 22 H44", TEXT, 2),
    # Two arrows passing: files kept in sync.
    "sync": amber("M14 25 H46 M38 17 L46 25 L38 33") + line("M50 39 H18 M26 31 L18 39 L26 47"),
    # A page of text, the line being typed in amber.
    "writer": line("M20 14 H38 L46 22 V50 H20 Z M38 14 V22 H46 M25 32 H40 M25 38 H40 M25 44 H35")
    + amber("M25 26 H33"),
    # A grid, one cell in amber.
    "spreadsheet": rect(13, 15, 38, 34) + line("M13 26 H51 M13 37 H51 M26 15 V49 M38 15 V49", width=2.5)
    + f'<rect x="27.5" y="27.5" width="9" height="8" fill="{AMBER}"/>',
    # A slide with a chart, one bar in amber.
    "slides": rect(11, 15, 42, 28) + line("M32 43 V49 M24 49 H40") + line("M20 36 V30 M27 36 V26", TEXT, 4)
    + amber("M34 36 V21", 4),
    # One arrow round, its head in amber: restart.
    "restart": line("M32 18 A14 14 0 1 0 44.1 25") + amber("M27 12 L33 18 L27 24"),
    # A crescent moon and an amber z: suspend.
    "suspend": line("M34 17 A15 15 0 1 0 47 37 A12 12 0 0 1 34 17 Z") + amber("M40 14 H48 L40 22 H48", 3),
    # The moon over a drive: hibernate (memory saved to disk).
    "hibernate": rect(14, 40, 36, 10) + dot(43, 45, 2.2, TEXT)
    + amber("M33 13 A10 10 0 1 0 42 28 A8 8 0 0 1 33 13 Z"),
    # Two people, the other one in amber: switch user.
    "switch-user": circle(25, 23, 6) + line("M14 45 C14 34 36 34 36 45")
    + circle(41, 30, 6, AMBER) + amber("M30 51 C30 40 52 40 52 51"),
}

# The plate: brushed graphite (a soft vertical sheen and a few fine
# horizontal strokes), a thin border, slightly rounded like the rest.
PLATE = f"""<defs>
  <linearGradient id="g" x1="0" y1="0" x2="0.3" y2="1">
    <stop offset="0" stop-color="#2e333a"/>
    <stop offset="0.45" stop-color="#23272c"/>
    <stop offset="1" stop-color="#181b1f"/>
  </linearGradient>
</defs>
<rect x="4" y="4" width="56" height="56" rx="5" fill="url(#g)" stroke="{LINE}" stroke-width="1.5"/>
<path d="M8 13 H40 M18 23 H56 M8 37 H30 M24 49 H56" stroke="#ffffff" stroke-opacity="0.025" stroke-width="1"/>
<path d="M9 5.5 H55" stroke="#ffffff" stroke-opacity="0.08" stroke-width="1"/>
"""


def svg(body):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">\n'
            f"{PLATE}{body}\n</svg>\n")


def main():
    out = os.path.join(HERE, "icons")
    os.makedirs(out, exist_ok=True)
    for name, body in GLYPHS.items():
        with open(os.path.join(out, f"{name}.svg"), "w") as f:
            f.write(svg(body))
    print(f"wrote {len(GLYPHS)} icons to {out}")


if __name__ == "__main__":
    main()
