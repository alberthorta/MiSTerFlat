#!/usr/bin/env python3
"""Synthetic colour test pictures (no trademarks) for the native asset path.

Writes sources to tests/fixtures/art/src/ and display-ready files to tests/fixtures/art/,
using tools/convert_asset.py like a user would. Needs Pillow.
"""
import math
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(HERE, "art", "src")
OUT = os.path.join(HERE, "art")
CONVERT = os.path.join(ROOT, "tools", "convert_asset.py")


def font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def banner():
    """320x170, full colour: hue gradient, shapes, text. Exercises PNG RGB."""
    img = Image.new("RGB", (320, 170))
    px = img.load()
    for x in range(320):
        for y in range(170):
            h = x / 320
            r = int(127 + 127 * math.cos(2 * math.pi * h))
            g = int(127 + 127 * math.cos(2 * math.pi * (h - 1 / 3)))
            b = int(127 + 127 * math.cos(2 * math.pi * (h - 2 / 3)))
            k = 0.35 + 0.65 * (1 - y / 170)
            px[x, y] = (int(r * k), int(g * k), int(b * k))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((20, 40, 300, 130), radius=18, fill=(10, 10, 20), outline=(255, 255, 255), width=3)
    d.text((160, 85), "MiSTerLily", font=font(40), fill=(255, 200, 40), anchor="mm")
    d.ellipse((4, 4, 30, 30), fill=(255, 0, 0))
    d.ellipse((290, 4, 316, 30), fill=(0, 255, 0))
    d.ellipse((4, 140, 30, 166), fill=(0, 0, 255))
    d.ellipse((290, 140, 316, 166), fill=(255, 255, 255))
    return img


def logo_with_alpha():
    """200x100 RGBA with soft edges. Exercises contain-fit and alpha flattening."""
    img = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i in range(12):
        a = int(255 * (i + 1) / 12)
        d.rounded_rectangle((i, i, 199 - i, 99 - i), radius=30, outline=(40, 160, 255, a), width=1)
    d.rounded_rectangle((12, 12, 187, 87), radius=24, fill=(40, 160, 255, 255))
    d.text((100, 50), "ALPHA", font=font(32), fill=(255, 255, 255, 255), anchor="mm")
    return img


def photo():
    """640x480 smooth, noisy picture: compresses badly as PNG, well as JPEG."""
    img = Image.new("RGB", (640, 480))
    px = img.load()
    seed = 12345
    for y in range(480):
        for x in range(640):
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            n = (seed >> 16) % 24 - 12
            r = int(120 + 100 * math.sin(x / 70) + n)
            g = int(110 + 90 * math.sin(y / 50 + 1) + n)
            b = int(140 + 80 * math.sin((x + y) / 90 + 2) + n)
            px[x, y] = (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))
    return img


def main():
    os.makedirs(SRC, exist_ok=True)
    banner().save(os.path.join(SRC, "banner.png"))
    logo_with_alpha().save(os.path.join(SRC, "logo_alpha.png"))
    photo().save(os.path.join(SRC, "photo.png"))
    jobs = [
        ("banner.png", "MDSTEST.png", []),
        ("logo_alpha.png", "MDSALPHA.png", []),
        ("photo.png", "MDSPHOTO.jpg", ["--fit", "cover"]),
    ]
    for src, out, extra in jobs:
        subprocess.run([sys.executable, CONVERT, os.path.join(SRC, src), os.path.join(OUT, out)] + extra, check=True)
    # The 640x480 source is only needed to rebuild; keep the repo small.
    os.remove(os.path.join(SRC, "photo.png"))


if __name__ == "__main__":
    main()
