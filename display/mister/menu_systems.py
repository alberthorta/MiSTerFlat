"""The system picker of the touch display (firmware 0.6.1 and later).

In the MiSTer menu, the Systems button of the display's clock opens a cover flow of systems; a tap
on one opens a cover flow of its games, and a tap on a game starts it. The games come from
MiSTerManager (its Systems page), which keeps them in QUICK_DIR:

    games.json            {"version": 1, "systems": {"SNES": [{"id", "name", "mgl", "cover", "crc"}, ...]}}
    <system>/<id>.mgl     loaded with "load_core <mgl>"
    <system>/<id>.jpg     the cover, 240x320

Only systems whose core is on the SD card and that have at least one game are offered; with
none, the display shows no Systems button. The protocol is in docs/protocol.md (MDSSYS).
"""
import binascii
import json
import os
import re

from pictures import find_art

# (key: the core's picture name, and the key in games.json; name on the display; .rbf name before
# the date). Keep in step with PICKER in MiSTerManager's mistermanager/quick.py.
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
QUICK_DIR = "/media/fat/MiSTerLily/quick"
MAX_GAMES = 20  # the display keeps this many per system
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


def quick_stamp(quick_dir=QUICK_DIR):
    """Changes when MiSTerManager saves the list (also for a new cover)."""
    try:
        st = os.stat(os.path.join(quick_dir, "games.json"))
        return (st.st_mtime, st.st_size)
    except OSError:
        return None


def load_games(quick_dir=QUICK_DIR):
    try:
        with open(os.path.join(quick_dir, "games.json"), encoding="utf-8") as f:
            systems = json.load(f).get("systems")
    except (OSError, ValueError, AttributeError):
        return {}
    return systems if isinstance(systems, dict) else {}


def build(art_dir, cores_dir=CORES_DIR, quick_dir=QUICK_DIR):
    """The systems to offer, in order: [{"core", "name", "art", "crc", "games": [...]}]."""
    stored = load_games(quick_dir)
    items = []
    for core, name, prefix in SYSTEMS:
        if not find_rbf(cores_dir, prefix):
            continue
        games = []
        for g in stored.get(core) or []:
            if not isinstance(g, dict) or not os.path.isfile(str(g.get("mgl", ""))):
                continue
            cover = os.path.join(quick_dir, g["cover"]) if g.get("cover") else None
            games.append({"name": str(g.get("name", "?")).replace("\n", " ")[:40], "mgl": g["mgl"],
                          "cover": cover if cover and os.path.isfile(cover) else None,
                          "crc": int(g.get("crc") or 0) if cover else 0})
        if not games:
            continue
        art = find_art(art_dir, core)
        try:
            crc = file_crc(art) if art else 0
        except OSError:
            art, crc = None, 0
        items.append({"core": core, "name": name, "art": art, "crc": crc, "games": games[:MAX_GAMES]})
    return items


def list_lines(items):
    lines = ["MDSSYS,clear\n"]
    for i, item in enumerate(items):
        lines.append("MDSSYS,item,{},{:08x},{}\n".format(i, item["crc"], item["name"]))
    return lines


def game_lines(items, index):
    """The game list of system `index`; an empty list for an unknown one."""
    games = items[index]["games"] if 0 <= index < len(items) else []
    lines = ["MDSSYS,games,{},{}\n".format(index, len(games))]
    for j, g in enumerate(games):
        lines.append("MDSSYS,game,{},{},{:08x},{}\n".format(index, j, g["crc"], g["name"]))
    return lines


def _frame(path, *indexes):
    with open(path, "rb") as f:
        data = f.read()
    fmt = "jpg" if path.lower().endswith((".jpg", ".jpeg")) else "png"
    head = "MDSSYSIMG,{},{:08x},{},{}\n".format(len(data), binascii.crc32(data) & 0xFFFFFFFF, fmt,
                                                ",".join(str(i) for i in indexes))
    return head.encode() + data


def cover_frame(items, index):
    """MDSSYSIMG line + file bytes for system `index`; None when there is no cover."""
    if not 0 <= index < len(items) or not items[index]["art"]:
        return None
    return _frame(items[index]["art"], index)


def game_cover_frame(items, index, game):
    if not 0 <= index < len(items) or not 0 <= game < len(items[index]["games"]):
        return None
    cover = items[index]["games"][game]["cover"]
    return _frame(cover, index, game) if cover else None


def play(items, index, game, fifo=CMD_FIFO):
    """Asks MiSTer Main to start a game. Returns its name."""
    if not 0 <= index < len(items) or not 0 <= game < len(items[index]["games"]):
        raise ValueError("no game {},{}".format(index, game))
    g = items[index]["games"][game]
    # O_NONBLOCK: when Main is not reading the fifo, fail instead of hanging the daemon.
    fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
    try:
        os.write(fd, "load_core {}\n".format(g["mgl"]).encode())
    finally:
        os.close(fd)
    return g["name"]
