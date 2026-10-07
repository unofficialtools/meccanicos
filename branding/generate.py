#!/usr/bin/env python3
"""
Generate the brushed-metal artwork for the distro.

    nix-shell -p "python3.withPackages (p: [ p.numpy p.pillow ])" \
      --run "python3 branding/generate.py --name MECCANICOS"

Outputs (next to this script):
  wallpaper.png      3840x2160  desktop background
  login.png          1920x1080  LightDM login screen background
  boot-efi.png       1920x1080  UEFI boot menu splash (GRUB)
  boot-bios.png       800x600   legacy BIOS boot menu splash (syslinux)

Replace any of these PNGs with your own images if you prefer; the Nix
config only cares about the file names.
"""
import argparse
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))

# Steel palette (RGB, 0..1). Change these to shift the metal colour,
# e.g. bronze (0.80, 0.62, 0.42) or titanium (0.62, 0.66, 0.72).
STEEL_DARK = np.array([0.16, 0.18, 0.21])
STEEL_LIGHT = np.array([0.74, 0.77, 0.81])


def brushed(w, h, seed, brightness=1.0, sheen_angle=0.35):
    rng = np.random.default_rng(seed)
    # Fibre noise: random values smeared horizontally = brush strokes.
    noise = rng.normal(0.0, 1.0, (h, w)).astype(np.float32)
    # Different stroke lengths layered for a natural look.
    out = np.zeros_like(noise)
    for length, weight in ((w // 6, 0.55), (w // 25, 0.30), (9, 0.15)):
        k = np.cumsum(np.pad(noise, ((0, 0), (length, 0)), mode="wrap"), axis=1)
        smear = (k[:, length:] - k[:, :-length]) / np.sqrt(length)
        out += weight * smear
    out = (out - out.mean()) / (out.std() + 1e-6)
    # Fine per-row variation (rolled sheet texture).
    rows = rng.normal(0, 1, (h, 1)).astype(np.float32)
    rows = np.convolve(rows[:, 0], np.ones(3) / 3, mode="same")[:, None]
    tex = 0.09 * out + 0.04 * rows

    # Anisotropic sheen: soft diagonal light bands, like a lamp on steel.
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    u = (x / w) * np.cos(sheen_angle) + (y / h) * np.sin(sheen_angle)
    sheen = (
        0.50
        + 0.22 * np.exp(-((u - 0.38) ** 2) / 0.020)
        + 0.10 * np.exp(-((u - 0.82) ** 2) / 0.010)
        - 0.18 * u
    )
    # Vignette.
    cx, cy = (x / w - 0.5) * 1.6, (y / h - 0.5) * 1.6
    vig = 1.0 - 0.35 * (cx ** 2 + cy ** 2)

    v = np.clip((sheen + tex) * vig * brightness, 0, 1)[..., None]
    rgb = STEEL_DARK + (STEEL_LIGHT - STEEL_DARK) * v
    return Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8), "RGB")


def find_font(size):
    for path in (
        "/usr/share/fonts/truetype/google-fonts/Poppins-Medium.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-ExtraLight.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def engrave(img, text, size, y_frac, spacing=0.45):
    """Stamp text into the metal: dark recess + light bevel edge."""
    font = find_font(size)
    gap = int(size * spacing)
    widths = [font.getbbox(c)[2] - font.getbbox(c)[0] for c in text]
    total = sum(widths) + gap * (len(text) - 1)
    x0 = (img.width - total) // 2
    y0 = int(img.height * y_frac) - size // 2

    mask = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(mask)
    x = x0
    for c, cw in zip(text, widths):
        d.text((x - font.getbbox(c)[0], y0), c, font=font, fill=255)
        x += cw + gap

    shadow = mask.filter(ImageFilter.GaussianBlur(2))
    highlight = Image.new("L", img.size, 0)
    highlight.paste(mask, (0, max(1, size // 40)))
    highlight = highlight.filter(ImageFilter.GaussianBlur(1))

    dark = Image.new("RGB", img.size, (22, 25, 30))
    light = Image.new("RGB", img.size, (235, 240, 246))
    img = Image.composite(light, img, highlight.point(lambda p: p * 0.55))
    img = Image.composite(dark, img, shadow.point(lambda p: p * 0.70))
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="MECCANICOS", help="text stamped on login/boot art")
    ap.add_argument("--out", default=HERE)
    a = ap.parse_args()
    name = a.name.upper()

    wp = brushed(3840, 2160, seed=1)
    wp.save(os.path.join(a.out, "wallpaper.png"), optimize=True)

    login = brushed(1920, 1080, seed=2, brightness=0.82)
    login = engrave(login, name, 96, 0.22)
    login.save(os.path.join(a.out, "login.png"), optimize=True)

    efi = brushed(1920, 1080, seed=3, brightness=0.70)
    efi = engrave(efi, name, 110, 0.16)
    efi.save(os.path.join(a.out, "boot-efi.png"), optimize=True)

    bios = brushed(800, 600, seed=4, brightness=0.70)
    bios = engrave(bios, name, 44, 0.11)
    bios.save(os.path.join(a.out, "boot-bios.png"), optimize=True)
    # GRUB menu highlight bar (9-slice: west / centre / east)
    gdir = os.path.join(a.out, "grub")
    os.makedirs(gdir, exist_ok=True)
    h = 44
    grad = np.linspace(1.0, 0.75, h)[:, None]
    bar = np.zeros((h, 16, 4), np.uint8)
    bar[..., :3] = (np.array([200, 208, 218]) * grad[..., None]).astype(np.uint8)
    bar[..., 3] = 70
    bar[0, :, 3] = bar[-1, :, 3] = 150  # crisp top/bottom edge, like a bevel
    Image.fromarray(bar, "RGBA").save(os.path.join(gdir, "select_c.png"))
    edge = bar[:, :4].copy()
    edge[:, 0, 3] = 150
    Image.fromarray(edge, "RGBA").save(os.path.join(gdir, "select_w.png"))
    Image.fromarray(edge[:, ::-1].copy(), "RGBA").save(os.path.join(gdir, "select_e.png"))
    print("wrote artwork to", a.out)


if __name__ == "__main__":
    main()
