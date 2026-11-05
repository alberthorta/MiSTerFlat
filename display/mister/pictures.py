"""Where the picture for a core comes from, and how it goes over the wire.

Shared by the MiSTer daemon (mister_display.py) and the desktop tools (tools/fake_mister.py).
Standard library only: it runs with the Python 3 of the MiSTer.

- Colour pictures (MiSTerLily): <art>/<core>.png or .jpg, sent as
  MDSIMG,<bytes>,<crc32>,<png|jpg>,<core> + the file.
- tty2oled pictures: lookup and decoding exactly like tty2oled.sh senddata()
  (venice1200/MiSTer_tty2oled 50c08ac): <pics>/pics_pri/<core>.gsc|.xbm, then the folders
  GSC_US XBM_US GSC XBM XBM_TEXT, full core name first, then shorter prefixes; files decoded like
  `tail -n +4 file | xxd -r -p`.
"""
import binascii
import os
import re

PICTURE_FOLDERS = ["GSC_US", "XBM_US", "GSC", "XBM", "XBM_TEXT"]
HEX_TOKEN = re.compile(rb"0[xX]([0-9a-fA-F]{2})")


def decode_picture(path):
    """Bytes that `tail -n +4 path | xxd -r -p` would produce for a tty2oled picture file."""
    with open(path, "rb") as f:
        lines = f.read().split(b"\n")
    body = b"\n".join(lines[3:])
    return bytes(int(h, 16) for h in HEX_TOKEN.findall(body))


def find_picture(pics, core, use_us=False, use_gsc=True, use_text=False):
    if not pics:
        return None
    pri = os.path.join(pics, "pics_pri")
    for ext in ("gsc", "xbm"):
        p = os.path.join(pri, "{}.{}".format(core, ext))
        if os.path.exists(p):
            return p
    folders = list(PICTURE_FOLDERS)
    if not use_us:
        folders = [f for f in folders if not f.endswith("_US")]
    if not use_gsc:
        folders = [f for f in folders if not f.startswith("GSC")]
    if not use_text:
        folders = [f for f in folders if f != "XBM_TEXT"]
    for folder in folders:
        ext = folder[:3].lower()
        for c in range(len(core), 0, -1):  # full name, then shorter prefixes
            p = os.path.join(pics, folder, "{}.{}".format(core[:c], ext))
            if os.path.exists(p):
                return p
    return None


def find_art(art, core):
    """Native colour picture for `core` in `art`: full name first, then shorter prefixes."""
    if not art:
        return None
    for c in range(len(core), 0, -1):
        for ext in ("png", "jpg"):
            p = os.path.join(art, "{}.{}".format(core[:c], ext))
            if os.path.exists(p):
                return p
    return None


def asset_frame(core, path):
    """MDSIMG header line + file bytes."""
    with open(path, "rb") as f:
        data = f.read()
    fmt = "jpg" if path.lower().endswith((".jpg", ".jpeg")) else "png"
    head = "MDSIMG,{},{:08x},{},{}\n".format(len(data), binascii.crc32(data) & 0xFFFFFFFF, fmt, core)
    return head.encode(), data
