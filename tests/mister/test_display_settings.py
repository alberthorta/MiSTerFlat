#!/usr/bin/env python3
"""Checks display_settings.py: the MDSCFG reply as JSON, and the command file.

    python3 tests/mister/test_display_settings.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "mister"))
import display_settings as ds  # noqa: E402

failures = 0


def check(name, ok, detail=""):
    global failures
    print("{} {}{}".format("PASS" if ok else "FAIL", name, "" if ok else "  " + detail))
    failures += not ok


reply = b"MDSCFG;contrast=182;rotate=0;idle=0;fade=1;idleclock=0;screenbrightness=1;clockfont=4;brightness=5\n"
cfg = ds.parse_cfg(reply)
check("reply parsed", cfg and cfg["brightness"] == 5 and cfg["clockfont"] == 4 and cfg["contrast"] == 182, repr(cfg))
check("other lines ignored", ds.parse_cfg(b"MDSPONG;up=5") is None)
check("error reply ignored", ds.parse_cfg(b"MDSCFG;err=args") is None)

d = tempfile.mkdtemp()
state = os.path.join(d, "cfg")
ds.write_state(cfg, state)
with open(state) as f:
    data = json.load(f)
check("state has the font names", data["clockfonts"][4] == "orbitron" and data["brightness_max"] == 7)
check("no temporary file left", os.listdir(d) == ["cfg"], repr(os.listdir(d)))
ds.write_state(None, state)
check("None removes the state", not os.path.exists(state))

cmd = os.path.join(d, "cmd")
check("no command file: nothing", ds.take_commands(cmd) == [])
with open(cmd, "w") as f:
    f.write("brightness 3\nclockfont 7\nclockfont 8\nbrightness -1\nvolume 5\nbrightness\nclockfont x\n")
got = ds.take_commands(cmd)
check("valid commands only", got == [("brightness", 3), ("clockfont", 7)], repr(got))
check("command file removed", not os.path.exists(cmd))

print("{} failure(s)".format(failures))
sys.exit(1 if failures else 0)
