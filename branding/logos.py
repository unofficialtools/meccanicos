#!/usr/bin/env python3
"""The MeccanicOS logos: the mark (the amber plate with the M, as in
generate.py) followed by MECCANICOS as the desktop's top bar writes it
(modules/keyboard.nix: mos-label): JetBrains Mono Bold (modules/style.nix:
mono), capitals, widely spaced; as outlines, on a transparent background.

  logo/meccanicos-logo-white.svg     white text, for dark backgrounds
  logo/meccanicos-logo-black.svg     black text, for light backgrounds
  logo/meccanicos-logo-black-qr.svg  black text and a QR code of meccanicos.com
                                     (light backgrounds only: a QR code needs one)

and a PNG of each (400 px high). Run from the repository:

  nix shell --impure --expr 'with import (builtins.getFlake "nixpkgs") {}; [ librsvg (python3.withPackages (p: [ p.fonttools p.uharfbuzz p.segno ])) ]' \\
    -c python3 branding/logos.py
"""
import os
import subprocess

import segno
import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "logo")
NAME = "MECCANICOS"
TRACKING = 0.12  # em between letters (the top bar has 0.26: letter_spacing="2400" at 9 pt)
URL = "https://meccanicos.com"

# modules/style.nix
AMBER = "#f8a800"
INK = "#121417"
WHITE = "#ffffff"
BLACK = "#000000"

H = 100  # the mark's size; everything else follows it
PNG_HEIGHT = 400


def mono_bold():
    """(path, index, font) of JetBrains Mono Bold (the top bar's
    JetBrainsMono Nerd Font is the same letters plus icons)."""
    store = subprocess.run(["nix", "build", "--no-link", "--print-out-paths", "nixpkgs#jetbrains-mono"],
                           capture_output=True, text=True, check=True).stdout.strip()
    path = os.path.join(store, "share/fonts/truetype/JetBrainsMono-Bold.ttf")
    return path, 0, TTFont(path)


def mark(x, y, s):
    """generate.py's mark(): a plate with chamfered corners, an M of two posts and a V."""
    k = s * 0.22
    plate = [(k, 0), (s, 0), (s, s - k), (s - k, s), (0, s), (0, k)]
    t = s * 0.13
    x0, x1, y0, y1 = s * 0.24, s * 0.76, s * 0.27, s * 0.75
    mx, my = s / 2, s * 0.56
    v = [(x0, y0), (x0 + t * 1.15, y0), (mx, my - t * 1.3), (x1 - t * 1.15, y0), (x1, y0), (mx, my)]

    def poly(points, fill):
        return f'<polygon fill="{fill}" points="' + " ".join(f"{x + px:.2f},{y + py:.2f}" for px, py in points) + '"/>'

    return "\n".join([
        poly(plate, AMBER),
        f'<rect fill="{INK}" x="{x + x0:.2f}" y="{y + y0:.2f}" width="{t:.2f}" height="{y1 - y0:.2f}"/>',
        f'<rect fill="{INK}" x="{x + x1 - t:.2f}" y="{y + y0:.2f}" width="{t:.2f}" height="{y1 - y0:.2f}"/>',
        poly(v, INK),
    ])


def text(font_path, index, font, x, baseline, cap):
    """NAME as one path, shaped by HarfBuzz and spaced by TRACKING, its capitals
    cap high; (svg, width)."""
    blob = hb.Blob.from_file_path(font_path)
    face = hb.Face(blob, index)
    hfont = hb.Font(face)
    buf = hb.Buffer()
    buf.add_str(NAME)
    buf.guess_segment_properties()
    hb.shape(hfont, buf, {"kern": True, "liga": True})
    scale = cap / font["OS/2"].sCapHeight
    glyphs = font.getGlyphSet()
    order = font.getGlyphOrder()
    pen = SVGPathPen(glyphs)
    pos = 0
    for info, p in zip(buf.glyph_infos, buf.glyph_positions):
        name = order[info.codepoint]
        # Font units, y up -> SVG, y down.
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x + (pos + p.x_offset) * scale, baseline)))
        pos += p.x_advance + TRACKING * font["head"].unitsPerEm
    pos -= TRACKING * font["head"].unitsPerEm  # none after the last letter
    return pen.getCommands(), pos * scale


def qr(x, y, s, fill):
    """A QR code of URL, s wide, as one path of its dark modules."""
    code = segno.make(URL, error="m", micro=False)
    rows = list(code.matrix)
    n = len(rows)
    m = s / n
    d = []
    for r, row in enumerate(rows):
        c = 0
        while c < n:
            if row[c]:
                start = c
                while c < n and row[c]:
                    c += 1
                d.append(f"M{x + start * m:.3f} {y + r * m:.3f}h{(c - start) * m:.3f}v{m:.3f}h{-(c - start) * m:.3f}z")
            else:
                c += 1
    return f'<path fill="{fill}" shape-rendering="crispEdges" d="{"".join(d)}"/>'


def logo(font_path, index, font, color, with_qr=False):
    # As in the top bar: a 20 px mark, 9 pt capitals centred on it, a space between.
    cap = H * 0.44
    gap = H * 0.45
    baseline = H / 2 + cap / 2
    path, width = text(font_path, index, font, H + gap, baseline, cap)
    parts = [mark(0, 0, H), f'<path fill="{color}" d="{path}"/>']
    w = H + gap + width
    if with_qr:
        side = H * 1.1  # a little taller than the mark: small, still scannable
        qx = w + H * 0.45
        parts.append(qr(qx, (H - side) / 2, side, color))
        w = qx + side
        top, bottom = (H - side) / 2, (H + side) / 2
    else:
        top, bottom = 0, H
    pad = H * 0.04
    vb = f"{-pad:.2f} {top - pad:.2f} {w + 2 * pad:.2f} {bottom - top + 2 * pad:.2f}"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}">\n'
            f"<title>MeccanicOS</title>\n" + "\n".join(parts) + "\n</svg>\n")


def main():
    font_path, index, font = mono_bold()
    os.makedirs(OUT, exist_ok=True)
    for name, color, with_qr in [("white", WHITE, False), ("black", BLACK, False), ("black-qr", BLACK, True)]:
        svg = os.path.join(OUT, f"meccanicos-logo-{name}.svg")
        with open(svg, "w") as f:
            f.write(logo(font_path, index, font, color, with_qr))
        png = svg[:-4] + ".png"
        subprocess.run(["rsvg-convert", "-h", str(PNG_HEIGHT), "-o", png, svg], check=True)
        print(svg, png)


if __name__ == "__main__":
    main()
