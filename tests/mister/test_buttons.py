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


def volume_file(byte):
    f = tempfile.NamedTemporaryFile("wb", suffix=".dat", delete=False)
    f.write(bytes([byte]))
    f.close()
    return f.name


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def fifo():
    path = os.path.join(tempfile.mkdtemp(), "MiSTer_cmd")
    os.mkfifo(path)
    reader = os.open(path, os.O_RDONLY | os.O_NONBLOCK)  # Main's end, so writes do not fail
    return path, reader


cmd, reader = fifo()
clock = Clock()
vol = b.Volume(path=volume_file(3), cmd=cmd, clock=clock)
check("Volume.dat 3 -> level 4", vol.read() == (4, False), repr(vol.read()))
check("no Volume.dat -> full volume", b.Volume(path="/nonexistent", cmd=cmd).read() == (7, False))
check("mute bit", b.Volume(path=volume_file(0x12), cmd=cmd).read() == (5, True))
check("up one step", vol.step(True) == (5, False))
check("sends volume 5", os.read(reader, 100) == b"volume 5\n")
check("our change wins while Main has not saved it yet", vol.step(True) == (6, False))
os.read(reader, 100)
clock.now += b.VOLUME_TRUST_SECONDS + 1
check("then the file again", vol.read() == (4, False))
top = b.Volume(path=volume_file(0), cmd=cmd, clock=clock)
check("up at the top stays at 7", top.step(True) == (7, False))
os.read(reader, 100)
bottom = b.Volume(path=volume_file(7), cmd=cmd, clock=clock)
check("down at the bottom stays at 0", bottom.step(False) == (0, False))
os.read(reader, 100)
muted = b.Volume(path=volume_file(0x13), cmd=cmd, clock=clock)
check("out of mute the first step only unmutes", muted.step(False) == (4, False))
check("sends volume unmute", os.read(reader, 100) == b"volume unmute\n")
muted = b.Volume(path=volume_file(0x13), cmd=cmd, clock=clock)
b.COMMAND_GAP_SECONDS = 0
check("bar tap out of mute", muted.set(2) == (2, False))
check("sends unmute, then the level", os.read(reader, 100) == b"volume unmute\nvolume 2\n")
check("bar tap clamps", b.Volume(path=volume_file(3), cmd=cmd).set(9) == (7, False))
check("sends volume 7", os.read(reader, 100) == b"volume 7\n")
os.close(reader)
try:
    b.Volume(path=volume_file(3), cmd=cmd).step(True)
    check("no reader on MiSTer_cmd raises OSError", False)
except OSError:
    check("no reader on MiSTer_cmd raises OSError", True)
order = []
pb = b.Buttons(keyboard=FakeKeyboard(), poweroff=("true",), sync=lambda: order.append("sync"))
real_popen = b.subprocess.Popen
b.subprocess.Popen = lambda cmd: order.append(("run", tuple(cmd)))
pb.power_off(lambda: order.append("notify"))
b.subprocess.Popen = real_popen
check("poweroff: sync, then tell the display, then poweroff",
      order == ["sync", "notify", ("run", ("true",))], repr(order))
sys.exit(1 if failures else 0)
