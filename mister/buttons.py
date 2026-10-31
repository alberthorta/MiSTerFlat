"""The MiSTer's RESET, OSD and USER buttons, done from Linux for the touch buttons on the display.

The display reports a tap as MDSBTN,<reset|osd|user|bt>; the daemon calls press() with the name.

- OSD: F12 on a virtual keyboard (uinput). Main_MiSTer opens the OSD for it as for any keyboard.
- USER: the keyboard reset combo. Main turns it into the same BUTTON2 that the USER button sends
  to the core (user_io_check_reset / user_io_send_buttons). MiSTer.ini reset_combo picks the combo.
  While the OSD is open the combo does not reach the core (checked on a real MiSTer), so an open
  OSD is closed first. Main writes /tmp/OSD_VISIBLE when log_file_entry is on.
- RESET: the physical button is an HPS cold reset (sys_top.v reset_hps_cold_req): instant. A plain
  reboot runs every init.d stop script first and takes several seconds more, and reboot -f hung the
  MiSTer (tried on a real one). The reset combo with Left Shift, held over a second, makes Main do its
  own cold reset (user_io_check_reset -> fpga_io.cpp reboot(): sync, then the reset register), as
  fast as the button. If the MiSTer is still up a few seconds later (Main not running), plain reboot.
- BT: the Bluetooth pairing menu, which the OSD button opens when held for 3 s. From a keyboard
  Main opens it with F11 while the OSD is open (menu.cpp), so the OSD is opened first if needed.

Standard library only: the legacy uinput API (write uinput_user_dev, then UI_DEV_CREATE).
"""
import fcntl
import os
import re
import struct
import subprocess
import time

UINPUT = "/dev/uinput"
UI_SET_EVBIT = 0x40045564  # _IOW('U', 100, int)
UI_SET_KEYBIT = 0x40045565  # _IOW('U', 101, int)
UI_DEV_CREATE = 0x5501  # _IO('U', 1)
EV_SYN, EV_KEY = 0, 1
BUS_VIRTUAL = 0x06

KEY_LEFTCTRL, KEY_LEFTSHIFT, KEY_LEFTALT, KEY_RIGHTALT = 29, 42, 56, 100
KEY_LEFTMETA, KEY_RIGHTMETA, KEY_DELETE, KEY_F11, KEY_F12 = 125, 126, 111, 87, 88
# MiSTer.ini reset_combo, as user_io_check_reset() lists them (0 is the default).
RESET_COMBOS = {
    0: (KEY_LEFTCTRL, KEY_LEFTALT, KEY_RIGHTALT),
    1: (KEY_LEFTCTRL, KEY_LEFTMETA, KEY_RIGHTMETA),
    2: (KEY_LEFTCTRL, KEY_LEFTALT, KEY_DELETE),
}
# Main_MiSTer finds new input devices through inotify; give it time before the first key.
NEW_DEVICE_SECONDS = 1.0
TAP_SECONDS = 0.05
# The core sees BUTTON2 only while the combo is held.
HOLD_SECONDS = 0.3
OSD_VISIBLE = "/tmp/OSD_VISIBLE"
# Main reboots once the cold reset combo has been held for 1 s.
COLD_RESET_HOLD_SECONDS = 1.5
# Still running this long after that: Main did not do it, reboot the plain way.
COLD_RESET_FALLBACK_SECONDS = 4.0
# Time for Main to draw the OSD after F12 before the next key.
OSD_SETTLE_SECONDS = 0.5


class VirtualKeyboard:
    def __init__(self, path=UINPUT):
        self.path = path
        self.fd = None
        self.ready_at = 0.0

    def open(self):
        """Creates the device now, so the first key does not wait for Main to find it."""
        if self.fd is None:
            self._open()

    def _open(self):
        fd = os.open(self.path, os.O_WRONLY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
            for key in {KEY_F11, KEY_F12, KEY_LEFTSHIFT} | {k for combo in RESET_COMBOS.values() for k in combo}:
                fcntl.ioctl(fd, UI_SET_KEYBIT, key)
            # struct uinput_user_dev: name[80], input_id, ff_effects_max, abs{max,min,fuzz,flat}[64]
            os.write(fd, struct.pack("=80sHHHHi256i", b"MiSTerLily buttons", BUS_VIRTUAL, 0, 0, 1, 0,
                                     *([0] * 256)))
            fcntl.ioctl(fd, UI_DEV_CREATE)
        except OSError:
            os.close(fd)
            raise
        self.fd = fd
        self.ready_at = time.monotonic() + NEW_DEVICE_SECONDS

    def _send(self, keys, value):
        for key in keys:
            # struct input_event: struct timeval (two longs), type, code, value
            os.write(self.fd, struct.pack("llHHi", 0, 0, EV_KEY, key, value))
        os.write(self.fd, struct.pack("llHHi", 0, 0, EV_SYN, 0, 0))

    def press(self, keys, hold):
        self.open()
        wait = self.ready_at - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._send(keys, 1)
        time.sleep(hold)
        self._send(reversed(keys), 0)


def reset_combo(ini_path):
    """The reset_combo value of the [MiSTer] section, 0 when unset or unknown."""
    try:
        with open(ini_path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return 0
    section = None
    for line in text.splitlines():
        line = line.split(";", 1)[0].strip()
        if line.startswith("["):
            section = line.strip("[]").strip().lower()
        elif section == "mister":
            m = re.match(r"reset_combo\s*=\s*(\d+)", line, re.I)
            if m and int(m.group(1)) in RESET_COMBOS:
                return int(m.group(1))
    return 0


class Buttons:
    def __init__(self, ini_path="/media/fat/MiSTer.ini", keyboard=None, reboot=("reboot",),
                 osd_file=OSD_VISIBLE, sleep=time.sleep):
        self.ini_path = ini_path
        self.keyboard = keyboard or VirtualKeyboard()
        self.reboot = list(reboot)
        self.osd_file = osd_file
        self.sleep = sleep

    def prepare(self):
        """For a display with touch buttons: create the virtual keyboard ahead of the first tap.
        Raises OSError when there is no uinput."""
        self.keyboard.open()

    def osd_open(self):
        try:
            with open(self.osd_file) as f:
                return f.read().strip() == "1"
        except OSError:
            return False

    def press(self, name):
        """Raises OSError (no uinput) or ValueError (unknown name)."""
        if name == "osd":
            self.keyboard.press((KEY_F12,), TAP_SECONDS)
        elif name == "user":
            if self.osd_open():
                self.keyboard.press((KEY_F12,), TAP_SECONDS)
                time.sleep(OSD_SETTLE_SECONDS)
            self.keyboard.press(RESET_COMBOS[reset_combo(self.ini_path)], HOLD_SECONDS)
        elif name == "bt":
            if not self.osd_open():
                self.keyboard.press((KEY_F12,), TAP_SECONDS)
                time.sleep(OSD_SETTLE_SECONDS)
            self.keyboard.press((KEY_F11,), TAP_SECONDS)
        elif name == "reset":
            combo = RESET_COMBOS[reset_combo(self.ini_path)]
            self.keyboard.press((KEY_LEFTSHIFT,) + combo, COLD_RESET_HOLD_SECONDS)
            self.sleep(COLD_RESET_FALLBACK_SECONDS)
            subprocess.Popen(self.reboot)
        else:
            raise ValueError("unknown button {!r}".format(name))
