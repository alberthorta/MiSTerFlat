#!/usr/bin/env python3
"""Checks menu_systems.py: the list, the covers and the load command of the system picker.

    python3 tests/mister/test_menu_systems.py
"""
import binascii
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "mister"))
import menu_systems as m  # noqa: E402

failures = 0


def check(name, ok, detail=""):
    global failures
    print("{} {}{}".format("PASS" if ok else "FAIL", name, "" if ok else "  " + detail))
    failures += not ok


def write(path, data=b""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


base = tempfile.mkdtemp()
cores = os.path.join(base, "_Console")
art = os.path.join(base, "art")
for name in ("Gameboy_20260603.rbf", "SNES_20250101.rbf", "SNES_20260823.rbf", "PSX_20260807.rbf",
             "SNES_20260823.rbf.bak", "MegaDrive.rbf"):
    write(os.path.join(cores, name))
write(os.path.join(art, "SNES.png"), b"\x89PNG snes")
write(os.path.join(art, "PSX.jpg"), b"\xff\xd8 psx")

check("newest rbf", m.find_rbf(cores, "SNES") == os.path.join(cores, "SNES_20260823.rbf"))
check("rbf name is case-insensitive", m.find_rbf(cores, "gameboy") is not None)
check("no rbf without a date", m.find_rbf(cores, "MegaDrive") is None)
check("no folder", m.find_rbf(os.path.join(base, "none"), "SNES") is None)

quick = os.path.join(base, "quick")
check("no games.json: no systems", m.build(art, cores, quick) == [])
mgl = os.path.join(quick, "SNES", "1.mgl")
write(mgl, b"<mistergamedescription/>")
write(os.path.join(quick, "SNES", "1.jpg"), b"\xff\xd8 cover")
write(os.path.join(quick, "PSX", "2.mgl"))
write(os.path.join(quick, "games.json"), json.dumps({"version": 1, "systems": {
    "SNES": [{"id": "1", "name": "Super Mario World", "mgl": mgl, "cover": "SNES/1.jpg", "crc": 77},
             {"id": "9", "name": "Gone", "mgl": os.path.join(quick, "SNES", "9.mgl"), "cover": None, "crc": 0}],
    "PSX": [{"id": "2", "name": "Ridge Racer", "mgl": os.path.join(quick, "PSX", "2.mgl"), "cover": None, "crc": 0}],
    "GAMEBOY": [],
    "NES": [{"id": "3", "name": "No core", "mgl": mgl}]}}).encode())
stamp = m.quick_stamp(quick)
check("stamp", stamp is not None)

items = m.build(art, cores, quick)
check("only systems with a core and games, in order", [i["core"] for i in items] == ["SNES", "PSX"], str(items))
check("missing .mgl dropped", [g["name"] for g in items[0]["games"]] == ["Super Mario World"])
check("crc of the system cover", items[0]["crc"] == binascii.crc32(b"\x89PNG snes") & 0xFFFFFFFF)

# The user's own name and cover of a system, from MiSTerManager.
with open(os.path.join(quick, "games.json")) as f:
    data = json.load(f)
write(os.path.join(quick, "SNES", "system.jpg"), b"\xff\xd8 mine")
data["custom"] = {"SNES": {"name": "SNES", "cover": "SNES/system.jpg", "crc": 1}}
write(os.path.join(quick, "games.json"), json.dumps(data).encode())
mine = m.build(art, cores, quick)
check("custom name and cover", mine[0]["name"] == "SNES" and mine[0]["art"].endswith("system.jpg")
      and mine[0]["crc"] == binascii.crc32(b"\xff\xd8 mine") & 0xFFFFFFFF, str(mine[0]))
data["custom"] = {"SNES": {"cover": "SNES/gone.jpg"}}
write(os.path.join(quick, "games.json"), json.dumps(data).encode())
check("missing custom cover: the art one", m.build(art, cores, quick)[0]["art"].endswith("SNES.png"))
del data["custom"]
write(os.path.join(quick, "games.json"), json.dumps(data).encode())

lines = m.list_lines(items)
check("list lines", lines[0] == "MDSSYS,clear\n" and lines[1] == "MDSSYS,item,0,{:08x},Super Nintendo\n".format(items[0]["crc"]),
      str(lines))
check("game lines", m.game_lines(items, 0) == ["MDSSYS,games,0,1\n", "MDSSYS,game,0,0,0000004d,Super Mario World\n"],
      str(m.game_lines(items, 0)))
check("unknown system: empty list", m.game_lines(items, 5) == ["MDSSYS,games,5,0\n"])

frame = m.cover_frame(items, 1)
head, _, data = frame.partition(b"\n")
check("system cover frame", head == "MDSSYSIMG,{},{:08x},jpg,1".format(len(data), items[1]["crc"]).encode()
      and data == b"\xff\xd8 psx", repr(head))
head, _, data = m.game_cover_frame(items, 0, 0).partition(b"\n")
check("game cover frame", head.startswith(b"MDSSYSIMG,") and head.endswith(b",jpg,0,0") and data == b"\xff\xd8 cover", repr(head))
check("no cover frames", m.game_cover_frame(items, 1, 0) is None and m.game_cover_frame(items, 0, 4) is None)

fifo = os.path.join(base, "cmd")
os.mkfifo(fifo)
reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
check("play returns the name", m.play(items, 0, 0, fifo) == "Super Mario World")
check("load_core with the mgl", os.read(reader, 300) == "load_core {}\n".format(mgl).encode())
try:
    m.play(items, 1, 3, fifo)
    check("bad index", False)
except ValueError:
    check("bad index", True)
os.close(reader)

print("{} failure(s)".format(failures))
sys.exit(1 if failures else 0)
