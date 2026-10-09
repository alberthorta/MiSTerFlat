#!/usr/bin/env python3
"""Make colour pictures for MiSTerLily from the names of the tty2oled pictures.

    python3 fetch.py                       # everything, keeps files already in out/art
    python3 fetch.py --only SNES outzone   # a few cores
    python3 fetch.py --force               # rebuild files already in out/art

For each tty2oled picture name:
- arcade (MAME set name): the marquee from the Arcade Database (adb.arcadeitalia.net), else the
  parent set's marquee, else the title screen;
- system: the colour logo from the Batocera Carbon theme (fabricecaruso/es-theme-carbon), using
  the table in systems.py.

Results go to out/art/<CORE>.png (320x170, ready for /media/fat/MiSTerLily/art/), with
out/review.html to compare them with the tty2oled pictures, and out/missing.txt.
Downloads are cached in cache/, so a second run only fetches what is new.
"""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from systems import SYSTEMS

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
OUT = os.path.join(HERE, "out")

PICTURES_URL = "https://www.tty2tft.de/MiSTer_tty2oled_pictures.7z"
ADB_QUERY = "https://adb.arcadeitalia.net/service_scraper.php?ajax=query_mame&game_name="
ADB_IMAGE = "https://adb.arcadeitalia.net/?mame={}&type={}&resize=0"
LOGO_URL = "https://raw.githubusercontent.com/fabricecaruso/es-theme-carbon/master/art/logos/"
USER_AGENT = "misterlily-art/1.0 (personal use)"
ADB_BATCH = 50
ADB_DELAY = 0.5  # free hobby service: one request at a time, with a pause
# The ADB answers 200 with this "no image" picture when it has nothing.
ADB_PLACEHOLDER_MD5 = "d252a22533bc2ebece7f45a82278f641"
DARK_LOGO = 0.2
PANEL_COLOUR = (230, 230, 230, 255)

# Same folders as tty2oled. XBM_TEXT holds the core name as text, nothing to colour.
PICTURE_FOLDERS = ["GSC_US", "XBM_US", "GSC", "XBM"]
ARCADE_NAME = re.compile(r"^[a-z0-9_]+$")
ALT_SUFFIX = re.compile(r"_alt\d+$")


def load_convert_asset(misterlily):
    sys.path.insert(0, os.path.join(misterlily, "tools"))
    try:
        import convert_asset
    except ImportError as e:
        sys.exit("cannot import tools/convert_asset.py from {}: {}".format(misterlily, e))
    return convert_asset


def download(url, path):
    """Cached download. Returns the path, or None on a 404."""
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return path


def get_pictures(pics):
    if pics:
        return pics
    pics = os.path.join(CACHE, "tty2oled")
    if os.path.isdir(os.path.join(pics, "GSC")):
        return pics
    try:
        import py7zr
    except ImportError:
        sys.exit("py7zr is needed to unpack the tty2oled pictures: python3 -m pip install py7zr")
    archive = download(PICTURES_URL, os.path.join(CACHE, "MiSTer_tty2oled_pictures.7z"))
    print("unpacking", archive)
    with py7zr.SevenZipFile(archive) as z:
        z.extractall(pics)
    return pics


def picture_names(pics):
    """{core name: tty2oled picture path}, first folder wins like in tty2oled."""
    names = {}
    for folder in PICTURE_FOLDERS:
        d = os.path.join(pics, folder)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            name, ext = os.path.splitext(f)
            if ext.lower() not in (".gsc", ".xbm") or ALT_SUFFIX.search(name):
                continue
            # 000-* are pack entries, MENU has its own MiSTerLily screen, and a one-letter
            # picture would become the prefix fallback for every core starting with that letter.
            if name.startswith("000-") or name.startswith("MENU") or len(name) < 2:
                continue
            names.setdefault(name, os.path.join(d, f))
    return names


def adb_info(games):
    """ADB records by set name, cached per game. Unknown games map to {}."""
    info, todo = {}, []
    for g in games:
        p = os.path.join(CACHE, "adb", g + ".json")
        if os.path.exists(p):
            with open(p) as f:
                info[g] = json.load(f)
        else:
            todo.append(g)
    for i in range(0, len(todo), ADB_BATCH):
        batch = todo[i:i + ADB_BATCH]
        print("ADB info {}-{} of {}".format(i + 1, i + len(batch), len(todo)))
        url = ADB_QUERY + urllib.parse.quote(";".join(batch), safe=";")
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as r:
            result = json.load(r).get("result", [])
        # Only found games come back, so match by name, not by position.
        found = {rec["game_name"]: rec for rec in result}
        os.makedirs(os.path.join(CACHE, "adb"), exist_ok=True)
        for g in batch:
            rec = found.get(g, {})
            with open(os.path.join(CACHE, "adb", g + ".json"), "w") as f:
                json.dump(rec, f)
            info[g] = rec
        time.sleep(ADB_DELAY)
    return info


def adb_image(game, kind):
    path = os.path.join(CACHE, kind, game + ".png")
    fresh = not os.path.exists(path)
    if not download(ADB_IMAGE.format(urllib.parse.quote(game), kind), path):
        return None
    if fresh:
        time.sleep(ADB_DELAY)
    with open(path, "rb") as f:
        if hashlib.md5(f.read()).hexdigest() == ADB_PLACEHOLDER_MD5:
            return None
    return path


def arcade_source(game, info):
    """(image path, source label) or (None, reason)."""
    rec = info.get(game) or {}
    if not rec:
        return None, "not in the Arcade Database"
    p = adb_image(game, "marquee")
    if p:
        return p, "marquee"
    parent = rec.get("cloneof")
    if parent:
        p = adb_image(parent, "marquee")
        if p:
            return p, "marquee of " + parent
    p = adb_image(game, "title")
    if p:
        return p, "title screen"
    return None, "no marquee or title screen"


def system_source(core, rsvg):
    logo = SYSTEMS.get(core)
    if not logo:
        return None, "no logo in systems.py"
    src = download(LOGO_URL + logo, os.path.join(CACHE, "logos", logo))
    if not src:
        return None, "logo {} not found".format(logo)
    if not logo.endswith(".svg"):
        return src, "logo " + logo
    if not rsvg:
        return None, "rsvg-convert not installed (brew install librsvg)"
    png = os.path.join(CACHE, "logos", logo[:-4] + ".png")
    if not os.path.exists(png):
        subprocess.run([rsvg, "-w", "1200", "-o", png, src], check=True)
    return png, "logo " + logo


def dark_share(img):
    """Share of the visible pixels that are near black."""
    px = [p for p in img.getdata() if p[3] > 128]
    dark = sum(1 for p in px if 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] < 50)
    return dark / max(1, len(px))


def on_panel(img):
    """Logo on a light rounded panel. Some theme logos (PlayStation, PC-FX) have black parts
    that vanish on the black screen."""
    from PIL import Image, ImageDraw
    pad = max(8, img.height // 8)
    panel = Image.new("RGBA", (img.width + 2 * pad, img.height + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle((0, 0, panel.width - 1, panel.height - 1), radius=pad,
                                            fill=PANEL_COLOUR)
    panel.alpha_composite(img, (pad, pad))
    return panel


def make_picture(ca, src, out, margin):
    from PIL import Image
    img = Image.open(src)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        box = img.getchannel("A").getbbox()
        if box:
            img = img.crop(box)
        if dark_share(img) > DARK_LOGO:
            img = on_panel(img)
    img = ca.flatten(img)
    w, h = img.size
    scale = min((ca.WIDTH - 2 * margin) / w, (ca.HEIGHT - 2 * margin) / h)
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    canvas = Image.new("RGB", (ca.WIDTH, ca.HEIGHT), (0, 0, 0))
    canvas.paste(img.resize(size, Image.LANCZOS), ((ca.WIDTH - size[0]) // 2, (ca.HEIGHT - size[1]) // 2))
    data = ca.encode(canvas, "png", 0)
    if len(data) > ca.MAX_BYTES:
        data = ca.encode(canvas, "jpg", 88)
        out = out[:-4] + ".jpg"
    with open(out, "wb") as f:
        f.write(data)
    return out


def mono_preview(picture, out):
    """tty2oled picture as a PNG, decoded like the firmware's LegacyArt."""
    from PIL import Image
    with open(picture, "rb") as f:
        lines = f.read().split(b"\n")
    data = bytes(int(h, 16) for h in re.findall(rb"0[xX]([0-9a-fA-F]{2})", b"\n".join(lines[3:])))
    img = Image.new("L", (256, 64))
    px = img.load()
    xbm = picture.lower().endswith(".xbm")
    if len(data) != (2048 if xbm else 8192):
        return None
    for y in range(64):
        for x in range(256):
            if xbm:
                v = 255 if (data[y * 32 + (x >> 3)] >> (x & 7)) & 1 else 0
            else:
                b = data[y * 128 + (x >> 1)]
                v = ((b & 0x0F) if x & 1 else (b >> 4)) * 17
            px[x, y] = v
    img.save(out)
    return out


def write_review(rows):
    cards = []
    for core, art, source, mono in rows:
        mono_img = '<img src="{}" class="mono">'.format(html.escape(os.path.relpath(mono, OUT))) if mono else ""
        art_img = ('<img src="{}" class="art">'.format(html.escape(os.path.relpath(art, OUT))) if art
                   else '<div class="miss">no picture</div>')
        cards.append('<figure class="{}">{}{}<figcaption><b>{}</b><br>{}</figcaption></figure>'.format(
            "ok" if art else "missing", mono_img, art_img, html.escape(core), html.escape(source)))
    page = """<!doctype html><meta charset="utf-8"><title>MiSTerLily art review</title>
<style>
body{{background:#111;color:#ddd;font:13px system-ui;margin:16px}}
main{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px}}
figure{{margin:0;padding:8px;background:#1c1c1c;border-radius:6px}}
img{{display:block;image-rendering:pixelated}} .mono{{width:320px;height:80px;margin-bottom:4px}}
.art{{width:320px;height:170px}} .miss{{width:320px;height:40px;color:#c66}}
label{{margin-right:12px}} body.hide-missing .missing{{display:none}}
</style>
<h1>MiSTerLily art review</h1>
<p>{} cores, {} with a colour picture.
<label><input type="checkbox" onchange="document.body.classList.toggle('hide-missing',this.checked)"> hide missing</label></p>
<main>{}</main>""".format(len(rows), sum(1 for r in rows if r[1]), "\n".join(cards))
    with open(os.path.join(OUT, "review.html"), "w") as f:
        f.write(page)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pics", help="unpacked tty2oled pictures (default: download to cache/)")
    ap.add_argument("--misterlily", default=os.path.join(os.path.dirname(HERE), "MISTerLily"),
                    help="MiSTerLily repo, for tools/convert_asset.py (default: ../MISTerLily)")
    ap.add_argument("--only", nargs="+", metavar="CORE", help="only these cores")
    ap.add_argument("--force", action="store_true", help="rebuild pictures already in out/art")
    ap.add_argument("--no-arcade", action="store_true", help="skip arcade cores")
    ap.add_argument("--no-systems", action="store_true", help="skip system cores")
    ap.add_argument("--logo-margin", type=int, default=12, help="border around system logos in px")
    opts = ap.parse_args()

    ca = load_convert_asset(os.path.expanduser(opts.misterlily))
    names = picture_names(get_pictures(opts.pics))
    if opts.only:
        unknown = [c for c in opts.only if c not in names]
        if unknown:
            sys.exit("no tty2oled picture for: " + " ".join(unknown))
        names = {c: names[c] for c in opts.only}
    arcade = sorted(c for c in names if ARCADE_NAME.match(c))
    systems = sorted(c for c in names if not ARCADE_NAME.match(c))
    if opts.no_arcade:
        arcade = []
    if opts.no_systems:
        systems = []
    print("{} arcade, {} system pictures".format(len(arcade), len(systems)))

    art_dir = os.path.join(OUT, "art")
    mono_dir = os.path.join(OUT, "mono")
    os.makedirs(art_dir, exist_ok=True)
    os.makedirs(mono_dir, exist_ok=True)
    info = adb_info(arcade) if arcade else {}
    rsvg = shutil.which("rsvg-convert")

    rows = []
    for n, core in enumerate(systems + arcade, 1):
        mono = mono_preview(names[core], os.path.join(mono_dir, core + ".png"))
        done = [os.path.join(art_dir, core + e) for e in (".png", ".jpg")]
        done = [p for p in done if os.path.exists(p)]
        if done and not opts.force:
            rows.append((core, done[0], "kept", mono))
            continue
        if any(os.path.exists(os.path.join(OUT, "rejected", core + e)) for e in (".png", ".jpg")):
            rows.append((core, None, "rejected in show.py --review", mono))
            continue
        try:
            if core in arcade:
                src, source = arcade_source(core, info)
            else:
                src, source = system_source(core, rsvg)
        except (urllib.error.URLError, subprocess.CalledProcessError, OSError) as e:
            src, source = None, "error: {}".format(e)
        art = None
        if src:
            title = (info.get(core) or {}).get("title")
            if title:
                source = "{} ({})".format(source, title)
            margin = 0 if core in arcade else opts.logo_margin
            art = make_picture(ca, src, os.path.join(art_dir, core + ".png"), margin)
        rows.append((core, art, source, mono))
        print("[{}/{}] {}: {}".format(n, len(systems) + len(arcade), core, source))

    write_review(rows)
    with open(os.path.join(OUT, "missing.txt"), "w") as f:
        for core, art, source, _ in rows:
            if not art:
                f.write("{}\t{}\n".format(core, source))
    print("{} of {} cores have a picture. Review: {}".format(
        sum(1 for r in rows if r[1]), len(rows), os.path.join(OUT, "review.html")))


if __name__ == "__main__":
    main()
