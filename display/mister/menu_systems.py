"""The system picker of the touch display (firmware 0.6.1 and later).

In the MiSTer menu, the Systems button of the display's clock opens a cover flow of a few
systems; a tap on one loads its core. The daemon sends the list (only systems whose core is on
the SD card), sends a cover when the display asks for it, and loads the core.

    display <- MDSSYS,clear / MDSSYS,item,<i>,<crc32 of the cover>,<name>
    display -> MDSSYS,img,<i>    display <- MDSSYSIMG,<bytes>,<crc32>,<png|jpg>,<i> + file
    display -> MDSSYS,load,<i>   the core goes to MiSTer Main as "load_core <rbf>"

The covers are the colour pictures of the art folder (320x240 for this display).
"""
import binascii
import os
import re

from pictures import find_art

# (core name, for the picture; name on the display; .rbf file name before the date)
SYSTEMS = [
    ("GAMEBOY", "Game Boy", "Gameboy"),
    ("GBA", "Game Boy Advance", "GBA"),
    ("NES", "NES", "NES"),
    ("SMS", "Master System", "SMS"),
    ("SNES", "Super Nintendo", "SNES"),
    ("MegaDrive", "Mega Drive", "MegaDrive"),
    ("PSX", "PlayStation", "PSX"),
]
CORES_DIR = "/media/fat/_Console"
# MiSTer Main reads commands from this fifo.
CMD_FIFO = "/dev/MiSTer_cmd"


def find_rbf(cores_dir, prefix):
    """The newest <prefix>_<date>.rbf in cores_dir (update_all keeps one, but old ones can stay)."""
    pattern = re.compile(re.escape(prefix) + r"_\d{8}\.rbf", re.IGNORECASE)
    try:
        names = sorted(n for n in os.listdir(cores_dir) if pattern.fullmatch(n))
    except OSError:
        return None
    return os.path.join(cores_dir, names[-1]) if names else None


def file_crc(path):
    with open(path, "rb") as f:
        return binascii.crc32(f.read()) & 0xFFFFFFFF


def build(art_dir, cores_dir=CORES_DIR):
    """The systems to offer, in order: [{"core", "name", "rbf", "art", "crc"}]."""
    items = []
    for core, name, prefix in SYSTEMS:
        rbf = find_rbf(cores_dir, prefix)
        if not rbf:
            continue
        art = find_art(art_dir, core)
        try:
            crc = file_crc(art) if art else 0
        except OSError:
            art, crc = None, 0
        items.append({"core": core, "name": name, "rbf": rbf, "art": art, "crc": crc})
    return items


def list_lines(items):
    lines = ["MDSSYS,clear\n"]
    for i, item in enumerate(items):
        lines.append("MDSSYS,item,{},{:08x},{}\n".format(i, item["crc"], item["name"]))
    return lines


def cover_frame(items, index):
    """MDSSYSIMG line + file bytes for item `index`; None when there is no cover."""
    if not 0 <= index < len(items) or not items[index]["art"]:
        return None
    path = items[index]["art"]
    with open(path, "rb") as f:
        data = f.read()
    fmt = "jpg" if path.lower().endswith((".jpg", ".jpeg")) else "png"
    head = "MDSSYSIMG,{},{:08x},{},{}\n".format(len(data), binascii.crc32(data) & 0xFFFFFFFF, fmt, index)
    return head.encode() + data


def load(items, index, fifo=CMD_FIFO):
    """Asks MiSTer Main to load the core of item `index`. Returns the .rbf path."""
    if not 0 <= index < len(items):
        raise ValueError("no system {}".format(index))
    rbf = items[index]["rbf"]
    # O_NONBLOCK: when Main is not reading the fifo, fail instead of hanging the daemon.
    fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
    try:
        os.write(fd, "load_core {}\n".format(rbf).encode())
    finally:
        os.close(fd)
    return rbf
