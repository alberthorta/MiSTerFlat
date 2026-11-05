#!/usr/bin/env python3
"""Checks menu_systems.py: the list, the covers and the load command of the system picker.

    python3 tests/mister/test_menu_systems.py
"""
import binascii
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

items = m.build(art, cores)
check("only installed cores, in order", [i["core"] for i in items] == ["GAMEBOY", "SNES", "PSX"], str(items))
check("crc of the cover", items[1]["crc"] == binascii.crc32(b"\x89PNG snes") & 0xFFFFFFFF)
check("no cover: crc 0", items[0]["crc"] == 0 and items[0]["art"] is None)

lines = m.list_lines(items)
check("list lines", lines[0] == "MDSSYS,clear\n" and lines[2] == "MDSSYS,item,1,{:08x},Super Nintendo\n".format(items[1]["crc"]),
      str(lines))

frame = m.cover_frame(items, 2)
head, _, data = frame.partition(b"\n")
check("cover frame", head == "MDSSYSIMG,{},{:08x},jpg,2".format(len(data), items[2]["crc"]).encode() and data == b"\xff\xd8 psx",
      repr(head))
check("no cover frame", m.cover_frame(items, 0) is None and m.cover_frame(items, 9) is None)

fifo = os.path.join(base, "cmd")
os.mkfifo(fifo)
reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
m.load(items, 1, fifo)
check("load_core", os.read(reader, 200) == "load_core {}\n".format(items[1]["rbf"]).encode())
try:
    m.load(items, 7, fifo)
    check("bad index", False)
except ValueError:
    check("bad index", True)
os.close(reader)

print("{} failure(s)".format(failures))
sys.exit(1 if failures else 0)
