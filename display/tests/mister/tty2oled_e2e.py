#!/usr/bin/env python3
"""End-to-end check of the UNMODIFIED upstream tty2oled daemon against our MiSTer-side setup.

Runs inside a Linux container (see run_tty2oled_e2e.sh), laid out like a MiSTer:
  /media/fat/tty2oled      upstream tty2oled.sh, S60tty2oled, *.ini  (copied from a clone)
  /media/fat/tty2oled/pics a few pictures
  /src                     this repository

A pty stands in for the display: /dev/ttyACM0 -> pty slave. We run our mister/install.sh
(which writes the tty2oled-user.ini block and starts the daemon), write /tmp/CORENAME like the
MiSTer main binary does, and compare every byte the daemon sends with what
tools/fake_mister.py produces for the same cores.
"""
import os
import re
import subprocess
import sys
import threading
import time

sys.path.insert(0, "/src/mister")
from pictures import decode_picture, find_picture  # noqa: E402

PICS = "/media/fat/tty2oled/pics"
CORES = ["SNES", "Atari5200", "MDSTEST", "PSX"]  # Atari5200 has no picture -> bare name

failures = 0


def check(name, ok, detail=""):
    global failures
    print("{} {}{}".format("PASS" if ok else "FAIL", name, ("  " + detail) if detail and not ok else ""))
    if not ok:
        failures += 1


def main():
    master, slave = os.openpty()
    slave_name = os.ttyname(slave)
    if os.path.lexists("/dev/ttyACM0"):
        os.remove("/dev/ttyACM0")
    os.symlink(slave_name, "/dev/ttyACM0")

    received = bytearray()
    stop = False

    def reader():
        while not stop:
            try:
                data = os.read(master, 65536)
            except OSError:
                time.sleep(0.01)
                continue
            received.extend(data)

    threading.Thread(target=reader, daemon=True).start()

    with open("/tmp/CORENAME", "w") as f:
        f.write("MENU")

    # Output to a file, not a pipe: the daemon that install.sh starts in the background would keep
    # a pipe open and run() would never return.
    with open("/tmp/install.log", "w") as log:
        rc = subprocess.run(["bash", "/src/mister/install.sh", "--tty2oled"], stdout=log, stderr=subprocess.STDOUT).returncode
    print(open("/tmp/install.log").read())
    check("install.sh exit 0", rc == 0)

    ini = open("/media/fat/tty2oled/tty2oled-user.ini").read()
    check("user ini has the MiSTerLily block", "# >>> MiSTerLily" in ini and 'TTY2OLED_UPDATE="no"' in ini)

    # What TTYDEV becomes when tty2oled sources its ini files (no display in sysfs here -> fallback).
    ttydev = subprocess.run(["bash", "-c", ". /media/fat/tty2oled/tty2oled-system.ini; "
                             ". /media/fat/tty2oled/tty2oled-user.ini; echo \"$TTYDEV|$TTY2OLED_UPDATE\""],
                            stdout=subprocess.PIPE).stdout.decode().strip()
    check("sourced TTYDEV falls back to /dev/ttyACM0", ttydev == "/dev/ttyACM0|no", ttydev)

    time.sleep(2.5)  # startup sequence: 4 commands, 0.2 s apart, then MENU
    for core in CORES:
        with open("/tmp/CORENAME", "w") as f:
            f.write(core)
        time.sleep(1.5)

    subprocess.run(["bash", "/media/fat/tty2oled/S60tty2oled", "stop"], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    stop = True
    data = bytes(received)

    # Expected stream, built with the same helpers fake_mister.py uses.
    m = re.match(rb"QWERTZ\nCMDCON,100\nCMDSETTIME,(\d+)\nCMDSAVER,0,0,0\n", data)
    check("startup sequence", m is not None, repr(data[:80]))
    if not m:
        return 1
    expected = bytearray(m.group(0))
    expected += b"MENU\n"
    for core in CORES:
        pic = find_picture(PICS, core)
        if pic:
            expected += "CMDCOR,{},-1\n".format(core).encode() + decode_picture(pic)
        else:
            expected += (core + "\n").encode()
    check("daemon bytes == fake_mister bytes ({} bytes)".format(len(expected)), data == bytes(expected),
          "got {} bytes, first difference at {}".format(
              len(data), next((i for i, (a, b) in enumerate(zip(data, expected)) if a != b), min(len(data), len(expected)))))

    # Installing twice keeps one block; uninstall removes it and keeps the user's own lines.
    with open("/tmp/install.log", "w") as log:
        subprocess.run(["bash", "/src/mister/install.sh", "--tty2oled", "--no-start"], stdout=log, stderr=subprocess.STDOUT)
    ini = open("/media/fat/tty2oled/tty2oled-user.ini").read()
    check("install twice -> one block", ini.count("# >>> MiSTerLily") == 1 and ini.count("# <<< MiSTerLily") == 1)
    with open("/tmp/uninstall.log", "w") as log:
        subprocess.run(["bash", "/media/fat/MiSTerLily/uninstall.sh"], stdout=log, stderr=subprocess.STDOUT)
    subprocess.run(["bash", "/media/fat/tty2oled/S60tty2oled", "stop"], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    ini = open("/media/fat/tty2oled/tty2oled-user.ini").read()
    check("uninstall removes the block", "MiSTerLily" not in ini and "TTY2OLED_UPDATE" not in ini)
    check("uninstall keeps the user's lines", '#TTYDEV="/dev/ttyACM0"' in ini)

    print("{} failure(s)".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
