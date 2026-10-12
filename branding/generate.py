#!/usr/bin/env python3
"""
Generate the distro's artwork: clean brushed graphite metal, the logo on the
login and boot screens (--drawing: a technical drawing etched on it;
--flat: plain graphite instead of metal).

    nix-shell -p "python3.withPackages (p: [ p.numpy p.pillow ])" \
      --run "python3 branding/generate.py --name MECCANICOS"

Outputs (next to this script):
  wallpaper.png      3840x2160  desktop background (--drawing: a drafting
                                sheet with an exploded view of a gearbox)
  login.png          1920x1080  LightDM login screen background: the mark
                                and the name, centred above the login box
  boot-efi.png       1920x1080  UEFI boot menu splash (GRUB)
  boot-bios.png       800x600   legacy BIOS boot menu splash (syslinux)
  mark.png            256x256   the MeccanicOS mark (panel, command center,
  mark-20.png          20x20    boot splash, notifications)
  grub/select_*.png             GRUB's highlight bar (amber edge)

Every image shares one surface, and with --drawing one sheet: a fine grid,
a frame with zone letters and numbers, crop marks and a title block. Only
the mark is amber.
The colours are modules/style.nix's. Replace any PNG with your own; the Nix
config only cares about the file names.
"""
import argparse
import math
import os
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))

# modules/style.nix
INK = (0x12, 0x14, 0x17)
LINE = (0x3A, 0x40, 0x48)
TEXT = (0xE8, 0xE6, 0xE1)
DIM = (0x8B, 0x92, 0x9A)
AMBER = (0xF8, 0xA8, 0x00)


def font_file(family, style="Regular"):
    try:
        path = subprocess.run(["fc-match", "-f", "%{file}", f"{family}:style={style}"],
                              capture_output=True, text=True, check=True).stdout.strip()
        if path and os.path.exists(path):
            return path
    except (OSError, subprocess.CalledProcessError):
        pass
    return None


MONO = font_file("JetBrainsMono Nerd Font") or font_file("DejaVu Sans Mono")
MONO_BOLD = font_file("JetBrainsMono Nerd Font", "Bold") or MONO


def font(size, bold=False):
    path = MONO_BOLD if bold else MONO
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()


def rgba(c, a):
    return (*c, int(round(255 * a)))


# ---- the sheet ------------------------------------------------------------------
def sheet(w, h, seed, title="GENERAL ARRANGEMENT", number="MOS-001"):
    """Graphite, grid, frame with zones, crop marks, title block."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    # A soft light from the upper left, and a little grain against banding.
    light = 1.0 + 0.22 * np.exp(-(((x / w) - 0.3) ** 2 + ((y / h) - 0.25) ** 2) / 0.18)
    vig = 1.0 - 0.25 * (((x / w) - 0.5) ** 2 + ((y / h) - 0.5) ** 2)
    grain = rng.normal(0, 0.6, (h, w)).astype(np.float32)
    base = np.array(INK, np.float32)[None, None, :] * (light * vig)[..., None] + grain[..., None]
    if METAL:
        base = brushed(w, h, rng) * (light * vig)[..., None]
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    if not DRAWING:
        return img, int(56 * w / 1920)

    s = w / 1920  # 1 at 1920 wide
    o = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(o)
    # Margin: the frame clears the top bar.
    m = int(56 * s)
    # Grid, aligned on the frame.
    minor, major = int(24 * s), int(24 * s) * 5
    for gx in range(m, w - m + 1, minor):
        d.line([(gx, m), (gx, h - m)], fill=rgba(TEXT, 0.045 if (gx - m) % major else 0.075), width=1)
    for gy in range(m, h - m + 1, minor):
        d.line([(m, gy), (w - m, gy)], fill=rgba(TEXT, 0.045 if (gy - m) % major else 0.075), width=1)

    # Frame: a heavy outer line and a thin inner one, zones between them.
    band = int(18 * s)
    lw = max(1, int(2 * s))
    d.rectangle([m - band, m - band, w - m + band, h - m + band], outline=rgba(TEXT, 0.20), width=lw)
    d.rectangle([m, m, w - m, h - m], outline=rgba(TEXT, 0.14), width=max(1, lw // 2))
    zf = font(int(10 * s))
    cols, rows = 8, 4
    for i in range(cols):
        cx = m + (w - 2 * m) * (i + 0.5) / cols
        for yy in (m - band / 2, h - m + band / 2):
            d.text((cx, yy), str(i + 1), font=zf, fill=rgba(TEXT, 0.28), anchor="mm")
        if i:
            bx = m + (w - 2 * m) * i / cols
            d.line([(bx, m - band), (bx, m)], fill=rgba(TEXT, 0.20), width=1)
            d.line([(bx, h - m), (bx, h - m + band)], fill=rgba(TEXT, 0.20), width=1)
    for j in range(rows):
        cy = m + (h - 2 * m) * (j + 0.5) / rows
        for xx in (m - band / 2, w - m + band / 2):
            d.text((xx, cy), "ABCD"[j], font=zf, fill=rgba(TEXT, 0.28), anchor="mm")
        if j:
            by = m + (h - 2 * m) * j / rows
            d.line([(m - band, by), (m, by)], fill=rgba(TEXT, 0.20), width=1)
            d.line([(w - m, by), (w - m + band, by)], fill=rgba(TEXT, 0.20), width=1)
    # Centring marks on each side of the frame.
    for (ax, ay, bx2, by2) in (
        (w / 2, m - band, w / 2, m + int(14 * s)), (w / 2, h - m - int(14 * s), w / 2, h - m + band),
        (m - band, h / 2, m + int(14 * s), h / 2), (w - m - int(14 * s), h / 2, w - m + band, h / 2),
    ):
        d.line([(ax, ay), (bx2, by2)], fill=rgba(TEXT, 0.30), width=lw)
    # Crop marks outside the frame's corners.
    c, g = int(14 * s), int(6 * s)
    for (px, py, sx, sy) in ((m - band, m - band, -1, -1), (w - m + band, m - band, 1, -1),
                             (m - band, h - m + band, -1, 1), (w - m + band, h - m + band, 1, 1)):
        d.line([(px + sx * g, py), (px + sx * (g + c), py)], fill=rgba(TEXT, 0.30), width=1)
        d.line([(px, py + sy * g), (px, py + sy * (g + c))], fill=rgba(TEXT, 0.30), width=1)

    # Title block, bottom right, on the frame.
    tb_w, tb_h = int(380 * s), int(84 * s)
    x1, y1 = w - m, h - m
    x0, y0 = x1 - tb_w, y1 - tb_h
    d.rectangle([x0, y0, x1, y1], fill=rgba(INK, 0.85), outline=rgba(TEXT, 0.22), width=max(1, lw // 2))
    r1 = y0 + int(38 * s)
    d.line([(x0, r1), (x1, r1)], fill=rgba(TEXT, 0.18), width=1)
    split = x0 + int(250 * s)
    d.line([(split, r1), (split, y1)], fill=rgba(TEXT, 0.18), width=1)
    mid = r1 + (y1 - r1) // 2
    d.line([(split, mid), (x1, mid)], fill=rgba(TEXT, 0.18), width=1)
    pad = int(10 * s)
    small = font(int(8 * s))
    # The mark and the name in the top row.
    ms = int(22 * s)
    o.alpha_composite(mark(ms), (x0 + pad, y0 + (r1 - y0 - ms) // 2))
    d.text((x0 + pad + ms + int(10 * s), (y0 + r1) / 2), spaced(NAME), font=font(int(14 * s), True),
           fill=rgba(TEXT, 0.70), anchor="lm")
    d.text((x0 + pad, r1 + int(6 * s)), "TITLE", font=small, fill=rgba(TEXT, 0.30))
    d.text((x0 + pad, y1 - int(8 * s)), title, font=font(int(11 * s)), fill=rgba(TEXT, 0.55), anchor="ls")
    d.text((split + pad, r1 + int(4 * s)), "DWG NO.", font=small, fill=rgba(TEXT, 0.30))
    d.text((x1 - pad, mid - int(4 * s)), number, font=font(int(10 * s)), fill=rgba(TEXT, 0.55), anchor="rs")
    d.text((split + pad, mid + int(4 * s)), "SHEET", font=small, fill=rgba(TEXT, 0.30))
    d.text((x1 - pad, y1 - int(6 * s)), "1 / 1", font=font(int(10 * s)), fill=rgba(TEXT, 0.55), anchor="rs")
    img.alpha_composite(o)
    return img, m


NAME = "MECCANICOS"
METAL = True  # --flat: plain graphite instead of brushed metal
DRAWING = False  # --drawing: the drafting sheet and the gearbox on it


def brushed(w, h, rng):
    """Dark brushed graphite metal (RGB floats, 0..255): noise smeared along
    the rows at several lengths, like brush strokes, under a soft diagonal
    sheen. Between INK and LINE, so the drawing and the top bar stay clear."""
    noise = rng.normal(0.0, 1.0, (h, w)).astype(np.float32)
    tex = np.zeros_like(noise)
    for length, weight in ((w // 6, 0.55), (w // 25, 0.30), (9, 0.15)):
        k = np.cumsum(np.pad(noise, ((0, 0), (length, 0)), mode="wrap"), axis=1)
        tex += weight * (k[:, length:] - k[:, :-length]) / np.sqrt(length)
    tex = (tex - tex.mean()) / (tex.std() + 1e-6)
    rows = np.convolve(rng.normal(0, 1, h).astype(np.float32), np.ones(3) / 3, mode="same")[:, None]
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    u = (x / w) * np.cos(0.35) + (y / h) * np.sin(0.35)
    sheen = 0.30 + 0.25 * np.exp(-((u - 0.38) ** 2) / 0.02) + 0.10 * np.exp(-((u - 0.82) ** 2) / 0.01) - 0.12 * u
    v = np.clip(sheen + 0.10 * tex + 0.04 * rows, 0, 1)[..., None]
    lo, hi = np.array(INK, np.float32) * 0.9, np.array(LINE, np.float32) * 1.15
    return lo + (hi - lo) * v


def spaced(text):
    return " ".join(text)


# ---- the mark -------------------------------------------------------------------------
def mark(size, fg=AMBER, bg=INK):
    """An amber plate with chamfered corners and an M cut out of it."""
    ss = 8
    S = size * ss
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    k = S * 0.22  # chamfer
    d.polygon([(k, 0), (S, 0), (S, S - k), (S - k, S), (0, S), (0, k)], fill=(*fg, 255))
    # The M: two posts and a V, all straight cuts, like a stamped part.
    t = S * 0.13  # stroke
    x0, x1 = S * 0.24, S * 0.76
    y0, y1 = S * 0.27, S * 0.75
    c = (*bg, 255)
    d.rectangle([x0, y0, x0 + t, y1], fill=c)
    d.rectangle([x1 - t, y0, x1, y1], fill=c)
    mx, my = S / 2, S * 0.56
    d.polygon([(x0, y0), (x0 + t * 1.15, y0), (mx, my - t * 1.3), (x1 - t * 1.15, y0), (x1, y0),
               (mx, my)], fill=c)
    return im.resize((size, size), Image.LANCZOS)


# ---- the exploded view --------------------------------------------------------------
def gear_points(cx, cy, r_root, r_tip, teeth, phase=0.0):
    pts = []
    for i in range(teeth):
        a = 2 * math.pi * i / teeth + phase
        step = 2 * math.pi / teeth
        for frac, r in ((0.00, r_root), (0.18, r_tip), (0.50, r_tip), (0.68, r_root)):
            aa = a + frac * step
            pts.append((cx + r * math.cos(aa), cy + r * math.sin(aa)))
    return pts


def dashed(d, p0, p1, fill, width, pattern):
    """A line with a dash pattern, e.g. (40, 8, 6, 8) for a centre line."""
    (x0, y0), (x1, y1) = p0, p1
    length = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    t, i = 0.0, 0
    while t < length:
        seg = pattern[i % len(pattern)]
        if i % 2 == 0:
            e = min(length, t + seg)
            d.line([(x0 + ux * t, y0 + uy * t), (x0 + ux * e, y0 + uy * e)], fill=fill, width=width)
        t += seg
        i += 1


def arrow(d, tip, direction, size, fill):
    ux, uy = direction
    px, py = -uy, ux
    tx, ty = tip
    d.polygon([(tx, ty), (tx - ux * size + px * size * 0.32, ty - uy * size + py * size * 0.32),
               (tx - ux * size - px * size * 0.32, ty - uy * size - py * size * 0.32)], fill=fill)


def exploded_view(w, h):
    """A gearbox shaft pulled apart along its axis: housing flange, bearing,
    gear, spacer, pinion, nut. Thin off-white lines, centre lines, balloons
    and one diameter, drawn at 3x and scaled down for clean curves."""
    ss = 3
    W, H = w * ss, h * ss
    s = W / 1920
    o = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(o)
    stroke = rgba(TEXT, 0.16)
    faint = rgba(TEXT, 0.09)
    lw = max(1, int(1.6 * s))
    # The axis runs from lower left to upper right; parts are ellipses (a
    # circle seen at an angle), spaced along it.
    ang = math.radians(-14)
    ux, uy = math.cos(ang), math.sin(ang)
    ox, oy = W * 0.40, H * 0.60
    axis_len = W * 0.56
    dashed(d, (ox - ux * W * 0.06, oy - uy * W * 0.06), (ox + ux * axis_len, oy + uy * axis_len),
           rgba(TEXT, 0.14), lw, (int(46 * s), int(10 * s), int(8 * s), int(10 * s)))
    tilt = 0.42  # ellipse squash: how far the discs lean towards us

    def disc(t, r, teeth=0, r_in=0, ring=0):
        cx, cy = ox + ux * t, oy + uy * t
        pts = []
        if teeth:
            pts = gear_points(0, 0, r * 0.90, r, teeth)
        else:
            pts = [(r * math.cos(a), r * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 180)]

        def place(p):
            # x across the disc squashed (it faces along the axis), then turned.
            px, py = p[0] * tilt, p[1]
            return (cx + px * math.cos(ang) - py * math.sin(ang), cy + px * math.sin(ang) + py * math.cos(ang))
        d.line([place(p) for p in pts] + [place(pts[0])], fill=stroke, width=lw)
        for rr in (r_in, ring):
            if rr:
                q = [(rr * math.cos(a), rr * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 120)]
                d.line([place(p) for p in q] + [place(q[0])], fill=faint, width=lw)
        return (cx, cy), place

    s_ = W / 1920
    parts = [
        # (position along the axis, outer radius, teeth, bore, inner ring)
        (W * 0.00, 230 * s_, 0, 60 * s_, 180 * s_),   # housing flange
        (W * 0.10, 120 * s_, 0, 60 * s_, 92 * s_),    # bearing
        (W * 0.22, 300 * s_, 42, 60 * s_, 230 * s_),  # gear
        (W * 0.34, 82 * s_, 0, 60 * s_, 0),           # spacer
        (W * 0.43, 150 * s_, 18, 60 * s_, 0),         # pinion
        (W * 0.52, 70 * s_, 6, 40 * s_, 0),           # nut
    ]
    centres = []
    for t, r, teeth, r_in, ring in parts:
        c, place = disc(t, r, teeth, r_in, ring)
        centres.append((c, r, place))
    # Flange bolt holes on their pitch circle.
    _, r0, place0 = centres[0]
    for a in np.linspace(0, 2 * math.pi, 9)[:-1]:
        bx, by = 205 * s_ * math.cos(a), 205 * s_ * math.sin(a)
        q = [(bx + 9 * s_ * math.cos(b), by + 9 * s_ * math.sin(b)) for b in np.linspace(0, 2 * math.pi, 24)]
        d.line([place0(p) for p in q] + [place0(q[0])], fill=faint, width=lw)
    # Balloons: a leader from each part's rim to a numbered circle above it.
    bf = font(int(13 * s_ * 1.0))
    for i, ((cx, cy), r, place) in enumerate(centres):
        rim = place((0, -r))
        bx, by = rim[0] + 40 * s_, rim[1] - (90 + 18 * (i % 2)) * s_
        rad = 16 * s_
        d.line([rim, (bx - rad * 0.7, by + rad * 0.7)], fill=faint, width=lw)
        d.ellipse([rim[0] - 3 * s_, rim[1] - 3 * s_, rim[0] + 3 * s_, rim[1] + 3 * s_], fill=stroke)
        d.ellipse([bx - rad, by - rad, bx + rad, by + rad], outline=stroke, width=lw)
        d.text((bx, by), str(i + 1), font=ImageFont.truetype(MONO, int(14 * s_)) if MONO else bf,
               fill=rgba(TEXT, 0.30), anchor="mm")
    # One diameter on the gear: extension lines, a dimension line, arrows.
    (gx, gy), gr, gplace = centres[2]
    top, bot = gplace((0, -gr)), gplace((0, gr))
    off = 140 * s_
    e1 = (top[0] - ux * off, top[1] - uy * off)
    e2 = (bot[0] - ux * off, bot[1] - uy * off)
    d.line([top, (e1[0] - ux * 14 * s_, e1[1] - uy * 14 * s_)], fill=faint, width=lw)
    d.line([bot, (e2[0] - ux * 14 * s_, e2[1] - uy * 14 * s_)], fill=faint, width=lw)
    d.line([e1, e2], fill=stroke, width=lw)
    L = math.hypot(e2[0] - e1[0], e2[1] - e1[1])
    vx, vy = (e2[0] - e1[0]) / L, (e2[1] - e1[1]) / L
    arrow(d, e1, (-vx, -vy), 18 * s_, stroke)
    arrow(d, e2, (vx, vy), 18 * s_, stroke)
    mx, my = (e1[0] + e2[0]) / 2, (e1[1] + e2[1]) / 2
    label = Image.new("RGBA", (int(160 * s_), int(40 * s_)), (0, 0, 0, 0))
    ImageDraw.Draw(label).text((label.width / 2, label.height / 2), "Ø 600 h7",
                               font=ImageFont.truetype(MONO, int(16 * s_)) if MONO else bf,
                               fill=rgba(TEXT, 0.30), anchor="mm")
    rot = label.rotate(-math.degrees(math.atan2(vy, vx)) + 180 if vx < 0 else -math.degrees(math.atan2(vy, vx)),
                       expand=True, resample=Image.BICUBIC)
    o.alpha_composite(rot, (int(mx - ux * 26 * s_ - rot.width / 2), int(my - uy * 26 * s_ - rot.height / 2)))
    return o.resize((w, h), Image.LANCZOS)


def wordmark(img, y_frac, size, sub=None):
    """The mark and the spaced name, centred; a short amber rule under them."""
    d = ImageDraw.Draw(img)
    f = font(size, True)
    text = spaced(NAME)
    tw = d.textlength(text, font=f)
    ms = int(size * 1.5)
    gap = int(size * 0.8)
    total = ms + gap + tw
    x = (img.width - total) / 2
    y = img.height * y_frac
    img.alpha_composite(mark(ms), (int(x), int(y - ms / 2)))
    d.text((x + ms + gap, y), text, font=f, fill=rgba(TEXT, 0.92), anchor="lm")
    if sub:
        d.text((img.width / 2, y + ms * 0.95), sub, font=font(int(size * 0.42)), fill=rgba(DIM, 1.0),
               anchor="mm")
    return img


def main():
    global NAME, METAL, DRAWING
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="MECCANICOS", help="name on the title block, login and boot art")
    ap.add_argument("--out", default=HERE)
    ap.add_argument("--flat", action="store_true", help="plain graphite instead of brushed metal")
    ap.add_argument("--drawing", action="store_true", help="etch the technical drawing on the art")
    a = ap.parse_args()
    NAME = a.name.upper()
    METAL = not a.flat
    DRAWING = a.drawing
    out = lambda f: os.path.join(a.out, f)  # noqa: E731

    wp, _ = sheet(3840, 2160, seed=1)
    if DRAWING:
        wp.alpha_composite(exploded_view(3840, 2160))
    wp.convert("RGB").save(out("wallpaper.png"), optimize=True)

    login, _ = sheet(1920, 1080, seed=2, title="ACCESS", number="MOS-002")
    login = wordmark(login, 0.20, 40)
    login.convert("RGB").save(out("login.png"), optimize=True)

    efi, _ = sheet(1920, 1080, seed=3, title="START", number="MOS-000")
    efi = wordmark(efi, 0.20, 44)
    efi.convert("RGB").save(out("boot-efi.png"), optimize=True)

    bios, _ = sheet(800, 600, seed=4, title="START", number="MOS-000")
    bios = wordmark(bios, 0.13, 22)
    bios.convert("RGB").save(out("boot-bios.png"), optimize=True)

    mark(256).save(out("mark.png"), optimize=True)
    mark(20).save(out("mark-20.png"), optimize=True)

    # GRUB menu highlight bar (9-slice: west / centre / east): a raised
    # graphite row with an amber edge on the left, like the command center's.
    gdir = os.path.join(a.out, "grub")
    os.makedirs(gdir, exist_ok=True)
    h = 44
    bar = np.zeros((h, 16, 4), np.uint8)
    bar[..., :3] = (0x24, 0x28, 0x2D)
    bar[..., 3] = 235
    Image.fromarray(bar, "RGBA").save(os.path.join(gdir, "select_c.png"))
    west = bar[:, :4].copy()
    west[..., :3] = AMBER
    west[..., 3] = 255
    Image.fromarray(west, "RGBA").save(os.path.join(gdir, "select_w.png"))
    Image.fromarray(bar[:, :4].copy(), "RGBA").save(os.path.join(gdir, "select_e.png"))
    print("wrote artwork to", a.out)


if __name__ == "__main__":
    main()
