#!/usr/bin/env python3
"""Checks buttons.py: which keys each touch button sends, and the reset_combo of MiSTer.ini.

    python3 tests/mister/test_buttons.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "mister"))
import buttons as b  # noqa: E402

failures = 0


def check(name, ok, detail=""):
    global failures
    print("{} {}{}".format("PASS" if ok else "FAIL", name, "" if ok else "  " + detail))
    failures += not ok


class FakeKeyboard:
    def __init__(self):
        self.presses = []

    def open(self):
        pass

    def press(self, keys, hold):
        self.presses.append((tuple(keys), hold))


def ini(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".ini", delete=False)
    f.write(text)
    f.close()
    return f.name


check("no MiSTer.ini -> combo 0", b.reset_combo("/nonexistent/MiSTer.ini") == 0)
check("reset_combo=1", b.reset_combo(ini("[MiSTer]\r\nreset_combo=1 ; lctrl+lgui+rgui\r\n")) == 1)
check("commented out", b.reset_combo(ini("[MiSTer]\n;reset_combo=2\n")) == 0)
check("other section ignored", b.reset_combo(ini("[MiSTer]\nvideo_mode=8\n[arcade]\nreset_combo=2\n")) == 0)
check("unknown value -> 0", b.reset_combo(ini("[MiSTer]\nreset_combo=7\n")) == 0)

osd = ini("0")
kb = FakeKeyboard()
buttons = b.Buttons(ini_path=ini("[MiSTer]\nreset_combo=2\n"), keyboard=kb, reboot=("true",), osd_file=osd,
                    sleep=lambda s: None)
buttons.press("osd")
buttons.press("user")
check("osd taps F12", kb.presses[0] == ((b.KEY_F12,), b.TAP_SECONDS), repr(kb.presses))
check("user holds the reset combo of MiSTer.ini",
      kb.presses[1] == ((b.KEY_LEFTCTRL, b.KEY_LEFTALT, b.KEY_DELETE), b.HOLD_SECONDS), repr(kb.presses))
buttons.press("reset")
check("reset holds the cold reset combo (with Left Shift) over a second",
      kb.presses[2] == ((b.KEY_LEFTSHIFT, b.KEY_LEFTCTRL, b.KEY_LEFTALT, b.KEY_DELETE), b.COLD_RESET_HOLD_SECONDS)
      and b.COLD_RESET_HOLD_SECONDS > 1.0, repr(kb.presses))
del kb.presses[2:]
with open(osd, "w") as f:
    f.write("1")
kb.presses.clear()
buttons.press("user")
check("user with the OSD open closes it first",
      [k for k, _ in kb.presses] == [(b.KEY_F12,), (b.KEY_LEFTCTRL, b.KEY_LEFTALT, b.KEY_DELETE)], repr(kb.presses))
kb.presses.clear()
buttons.press("bt")
check("bt with the OSD open: F11 only", [k for k, _ in kb.presses] == [(b.KEY_F11,)], repr(kb.presses))
with open(osd, "w") as f:
    f.write("0")
kb.presses.clear()
buttons.press("bt")
check("bt with the OSD closed: F12 then F11", [k for k, _ in kb.presses] == [(b.KEY_F12,), (b.KEY_F11,)],
      repr(kb.presses))
try:
    buttons.press("power")
    check("unknown button refused", False)
except ValueError:
    check("unknown button refused", True)

event = len(b.struct.pack("llHHi", 0, 0, b.EV_KEY, b.KEY_F12, 1))
check("input_event size matches this platform's struct", event == (16 if b.struct.calcsize("l") == 4 else 24))
check("uinput_user_dev is 1116 bytes", b.struct.calcsize("=80sHHHHi256i") == 1116)
sys.exit(1 if failures else 0)
