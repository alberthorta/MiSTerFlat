#!/usr/bin/env python3
"""Prepare a colour picture for the display: 320x170, PNG or baseline JPEG, alpha on black.

    python3 tools/convert_asset.py input.png art/PSX.png
    python3 tools/convert_asset.py photo.jpg art/SNES.jpg --fit cover --quality 85
    python3 tools/convert_asset.py logo.png art/MENU.png --dither
    python3 tools/convert_asset.py --check art/PSX.png

The output name is the MiSTer core name (as in /tmp/CORENAME) plus .png or .jpg; copy it to
/media/fat/MiSTerLily/art/ on the MiSTer. Needs Pillow (pip install Pillow).

--fit contain (default) keeps the whole picture and fills the rest with black.
--fit cover fills the screen and crops what does not fit.
--dither reduces colours to what the RGB565 panel can show, with error diffusion, so smooth
gradients do not show bands. Without it the display rounds each pixel.
"""
import argparse
import io
import os
import sys

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is needed: python3 -m pip install Pillow")

WIDTH, HEIGHT = 320, 170
MAX_BYTES = 512 * 1024  # firmware asset buffer (proto::kMaxAssetBytes)


def flatten(img):
    """RGB on black. Transparency is blended here so the display only gets opaque pixels."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        black = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
        return Image.alpha_composite(black, rgba).convert("RGB")
    return img.convert("RGB")


def fit(img, mode):
    w, h = img.size
    if (w, h) == (WIDTH, HEIGHT):
        return img
    if mode == "cover":
        scale = max(WIDTH / w, HEIGHT / h)
    else:
        scale = min(WIDTH / w, HEIGHT / h)
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    resized = img.resize(size, Image.LANCZOS)
    canvas = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    canvas.paste(resized, ((WIDTH - size[0]) // 2, (HEIGHT - size[1]) // 2))
    return canvas


def dither_rgb565(img):
    """Floyd-Steinberg error diffusion to the 5-6-5 levels of the panel."""
    px = [list(map(float, p)) for p in img.getdata()]
    steps = (8.0, 4.0, 8.0)  # 256 / 32, 256 / 64, 256 / 32
    for y in range(HEIGHT):
        for x in range(WIDTH):
            i = y * WIDTH + x
            old = px[i]
            new = [min(255.0, max(0.0, round(old[c] / steps[c]) * steps[c])) for c in range(3)]
            px[i] = new
            err = [old[c] - new[c] for c in range(3)]
            for dx, dy, wgt in ((1, 0, 7 / 16), (-1, 1, 3 / 16), (0, 1, 5 / 16), (1, 1, 1 / 16)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < WIDTH and ny < HEIGHT:
                    j = ny * WIDTH + nx
                    for c in range(3):
                        px[j][c] += err[c] * wgt
    out = Image.new("RGB", (WIDTH, HEIGHT))
    out.putdata([tuple(int(v) for v in p) for p in px])
    return out


def encode(img, fmt, quality):
    buf = io.BytesIO()
    if fmt == "png":
        img.save(buf, "PNG", optimize=True)
    else:
        # Baseline, no progressive: the display's JPEG decoder (TJpgDec) needs that.
        img.save(buf, "JPEG", quality=quality, progressive=False, optimize=True, subsampling="4:2:0")
    return buf.getvalue()


def check(path):
    """Problems that would stop the display from showing the file. Empty list = fine."""
    problems = []
    data = open(path, "rb").read()
    if len(data) > MAX_BYTES:
        problems.append("{} bytes, the display accepts at most {}".format(len(data), MAX_BYTES))
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as e:  # noqa: BLE001 - report any decoder error
        return problems + ["cannot decode: {}".format(e)]
    if img.format not in ("PNG", "JPEG"):
        problems.append("format {} (use PNG or JPEG)".format(img.format))
    if img.size != (WIDTH, HEIGHT):
        problems.append("size {}x{} (expected {}x{}; smaller is centered, larger is cropped)".format(
            img.size[0], img.size[1], WIDTH, HEIGHT))
    if img.format == "JPEG" and (img.info.get("progressive") or img.info.get("progression")):
        problems.append("progressive JPEG (the display needs baseline; convert it)")
    if img.format == "JPEG" and img.mode == "CMYK":
        problems.append("CMYK JPEG (convert it)")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output", nargs="?")
    ap.add_argument("--fit", choices=("contain", "cover"), default="contain")
    ap.add_argument("--format", choices=("png", "jpg"), help="default: from the output extension")
    ap.add_argument("--quality", type=int, default=88, help="JPEG quality (default 88)")
    ap.add_argument("--dither", action="store_true", help="dither to RGB565 (smooth gradients)")
    ap.add_argument("--check", action="store_true", help="only check that the display can show INPUT")
    opts = ap.parse_args()

    if opts.check:
        problems = check(opts.input)
        for p in problems:
            print("problem: " + p)
        print("ok" if not problems else "{} problem(s)".format(len(problems)))
        return 1 if problems else 0

    if not opts.output:
        ap.error("output is required")
    fmt = opts.format or ("jpg" if opts.output.lower().endswith((".jpg", ".jpeg")) else "png")
    img = fit(flatten(Image.open(opts.input)), opts.fit)
    if opts.dither:
        img = dither_rgb565(img)
    data = encode(img, fmt, opts.quality)
    if len(data) > MAX_BYTES:
        sys.exit("result is {} bytes, over the {} byte limit; try JPEG".format(len(data), MAX_BYTES))
    os.makedirs(os.path.dirname(os.path.abspath(opts.output)), exist_ok=True)
    with open(opts.output, "wb") as f:
        f.write(data)
    print("{} -> {} ({}x{} {}, {} bytes)".format(opts.input, opts.output, WIDTH, HEIGHT, fmt.upper(), len(data)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
