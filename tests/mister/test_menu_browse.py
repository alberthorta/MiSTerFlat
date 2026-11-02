#!/usr/bin/env python3
"""Checks menu_browse.py: the core under the cursor of the MiSTer core browser.

    python3 tests/mister/test_menu_browse.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "mister"))
import menu_browse as m  # noqa: E402

failures = 0


def check(name, ok, detail=""):
    global failures
    print("{} {}{}".format("PASS" if ok else "FAIL", name, "" if ok else "  " + detail))
    failures += not ok


def write(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


base = tempfile.mkdtemp()
tmp = tempfile.mkdtemp()
console = os.path.join(base, "_Console")
write(os.path.join(console, "SNES_20260823.rbf"))
write(os.path.join(console, "TurboGrafx16_20260603.rbf"))
write(os.path.join(console, "Atari 2600.mgl"),
      "<mistergamedescription>\n\t<rbf>_Console/Atari7800</rbf>\n\t<setname>Atari2600</setname>\n</mistergamedescription>\n")
write(os.path.join(console, "NoSet.mgl"), "<mistergamedescription><rbf>_Console/GnW</rbf></mistergamedescription>")
write(os.path.join(base, "_Arcade", "1942 (Revision B).mra"),
      "<misterromdescription><name>1942</name><setname>1942</setname><rbf>jt1942</rbf></misterromdescription>")
os.makedirs(os.path.join(base, "_Arcade", "_alternatives"))
write(os.path.join(base, "games", "SNES", "Mario.sfc"))

check("rbf: date dropped by Main, name kept", m.core_for("_Console", "SNES", base) == "SNES")
check("rbf: alias to the CONF_STR name", m.core_for("_Console", "TurboGrafx16", base) == "TGFX16")
check("mgl: setname", m.core_for("_Console", "Atari 2600", base) == "Atari2600")
check("mgl without setname: rbf name, aliased", m.core_for("_Console", "NoSet", base) == "GameNWatch")
check("mra: setname", m.core_for("_Arcade", "1942 (Revision B)", base) == "1942")
check("folder: nothing", m.core_for("_Arcade", "_alternatives", base) is None)
check("top level folder: nothing", m.core_for("", "_Console", base) is None)
check("game file: nothing", m.core_for("games/SNES", "Mario", base) is None)
check("unknown item: nothing", m.core_for("_Console", "Missing", base) is None)
check("rbf name must match before the date", m.core_for("_Console", "SNE", base) is None)

check("no FILESELECT: no selection", m.selection(tmp) is None)
write(os.path.join(tmp, "FILESELECT"), "active")
write(os.path.join(tmp, "FULLPATH"), "_Console")
write(os.path.join(tmp, "CURRENTPATH"), "SNES")
check("active browser: folder and item", m.selection(tmp) == ("_Console", "SNES"), repr(m.selection(tmp)))
write(os.path.join(tmp, "FULLPATH"), "")
check("top level: empty folder", m.selection(tmp) == ("", "SNES"))
write(os.path.join(tmp, "FILESELECT"), "selected")
check("after a choice: no selection", m.selection(tmp) is None)
write(os.path.join(tmp, "FILESELECT"), "cancelled")
check("after cancel: no selection", m.selection(tmp) is None)

print("{} failure(s)".format(failures))
sys.exit(1 if failures else 0)
