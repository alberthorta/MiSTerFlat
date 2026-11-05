#!/usr/bin/env python3
"""End-to-end check of the native mode (our daemon) in a Linux container laid out like a MiSTer.

Runs inside the container started by run_e2e.sh. A pty stands in for the display at
/dev/ttyACM0 (config TTYDEV, since a container has no USB sysfs entry). Checks install.sh,
what the daemon sends for each kind of core, reconnection, the sleep file and uninstall.sh.
"""
import os
import re
import subprocess
import sys
import threading
import time

sys.path.insert(0, "/src/mister")
from pictures import decode_picture  # noqa: E402

FAT = "/media/fat"
failures = 0


def check(name, ok, detail=""):
    global failures
    print("{} {}{}".format("PASS" if ok else "FAIL", name, ("  " + detail) if detail and not ok else ""))
    if not ok:
        failures += 1


class FakeDisplay:
    """A pty whose slave is /dev/ttyACM0; collects everything the daemon writes and answers
    MDSPING like the firmware (MDSPONG;up=<uptime>)."""

    def __init__(self):
        self.master, self.slave = os.openpty()
        if os.path.lexists("/dev/ttyACM0"):
            os.remove("/dev/ttyACM0")
        os.symlink(os.ttyname(self.slave), "/dev/ttyACM0")
        self.data = bytearray()
        self.alive = True
        self.uptime = 100000
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        while self.alive:
            try:
                chunk = os.read(self.master, 65536)
            except OSError:
                time.sleep(0.01)
                continue
            self.data.extend(chunk)
            for _ in range(chunk.count(b"MDSPING\n")):
                self.uptime += 5000
                os.write(self.master, "MDSPONG;up={}\n".format(self.uptime).encode())
            for _ in range(chunk.count(b"CMDHWINF\n")):
                os.write(self.master, b"HWTDISPS3;MDS-9.8.7;\n")

    def unplug(self):
        os.remove("/dev/ttyACM0")
        self.alive = False


def sh(cmd):
    with open("/tmp/sh.log", "a") as log:
        return subprocess.run(["bash", "-c", cmd], stdout=log, stderr=subprocess.STDOUT).returncode


def set_core(name):
    with open("/tmp/CORENAME", "w") as f:
        f.write(name)
    time.sleep(0.8)


def main():
    os.makedirs(FAT + "/linux", exist_ok=True)
    with open("/tmp/CORENAME", "w") as f:
        f.write("MENU")

    rc = sh("bash /src/mister/install.sh --no-start")
    check("install.sh exit 0", rc == 0, open("/tmp/sh.log").read())
    check("tty2oled daemon disabled", os.path.exists(FAT + "/tty2oled/_S60tty2oled")
          and not os.path.exists(FAT + "/tty2oled/S60tty2oled"))
    sh("bash /src/mister/install.sh --no-start")  # a second install must not add a second line
    startup = open(FAT + "/linux/user-startup.sh").read()
    lines = [l for l in startup.splitlines() if "MiSTerLily/S60misterlily" in l]
    check("boot line added once, also after installing twice", len(lines) == 1, startup)
    cfg = open(FAT + "/MiSTerLily/config.ini").read()
    check("config records native mode", 'MDS_MODE="native"' in cfg and 'MDS_DISABLED_TTY2OLED="yes"' in cfg)
    ini = open(FAT + "/tty2oled/tty2oled-user.ini").read()
    check("tty2oled updater kept off", 'TTY2OLED_UPDATE="no"' in ini)

    # Colour picture for MDSTEST (it also has a tty2oled picture: colour must win).
    subprocess.run(["cp", "/src/tests/fixtures/art/MDSTEST.png", FAT + "/MiSTerLily/art/"], check=True)
    with open(FAT + "/MiSTerLily/config.ini", "a") as f:
        f.write('TTYDEV="/dev/ttyACM0"\n')

    disp = FakeDisplay()
    sh("bash {}/MiSTerLily/S60misterlily start".format(FAT))
    time.sleep(1.5)
    check("daemon running", sh("bash {}/MiSTerLily/S60misterlily status".format(FAT)) == 0)
    for core in ("MDSTEST", "SNES", "Atari5200"):
        set_core(core)
    data = bytes(disp.data)

    check("setup sequence", re.match(rb"CMDNULL\nCMDSTTYACK,0\nCMDCON,255\nCMDROT,0\nCMDSETTIME,\d+\n", data)
          is not None, repr(data[:80]))
    check("heartbeat pings sent", data.count(b"MDSPING\n") >= 1)
    check("MENU sent at start", b"MDSCORE,MENU\n" in data)
    check("firmware version asked", b"CMDHWINF\n" in data)
    check("firmware version file written", open("/tmp/misterlily_fw").read() == "9.8.7\n")
    check("board file written", open("/tmp/misterlily_board").read() == "HWTDISPS3\n")
    png = open("/src/tests/fixtures/art/MDSTEST.png", "rb").read()
    m = re.search(rb"MDSIMG,(\d+),([0-9a-f]{8}),png,MDSTEST\n", data)
    check("colour picture wins, sent as MDSIMG", m is not None and int(m.group(1)) == len(png)
          and data[m.end():m.end() + len(png)] == png)
    gsc = decode_picture(FAT + "/tty2oled/pics/GSC/SNES.gsc")
    check("tty2oled picture sent as CMDCOR", b"CMDCOR,SNES,-1\n" + gsc in data)
    check("core without picture sent as MDSCORE", data.endswith(b"MDSCORE,Atari5200\n"), repr(data[-40:]))

    # Unplug, plug in again: the daemon must notice, find it again and resend the current core.
    disp.unplug()
    time.sleep(1.0)
    check("version and board files removed when the display goes",
          not os.path.exists("/tmp/misterlily_fw") and not os.path.exists("/tmp/misterlily_board"))
    disp2 = FakeDisplay()
    time.sleep(4.0)
    data2 = bytes(disp2.data)
    check("reconnect: setup sent again", data2.startswith(b"CMDNULL\nCMDSTTYACK,0\n"), repr(data2[:40]))
    check("reconnect: current core sent again", b"MDSCORE,Atari5200\n" in data2, repr(data2[-60:]))
    log = open("/tmp/mister-display.log").read()
    check("log shows lost and connected twice", "display lost" in log and log.count("display connected") == 2, log)

    # The board restarts (watchdog, CMDRESET): the port stays, the uptime drops. The daemon must
    # set it up again and resend the core.
    disp2.uptime = 1000
    before = len(disp2.data)
    time.sleep(7.0)
    after = bytes(disp2.data[before:])
    check("restart: setup and core sent again", b"CMDSTTYACK,0\n" in after and b"MDSCORE,Atari5200\n" in after,
          repr(after[-60:]))
    check("restart logged", "display restarted" in open("/tmp/mister-display.log").read())

    # A touch button: the daemon must act on it. The container has no /dev/uinput, so the action
    # fails, which must be logged and not stop the daemon.
    os.write(disp2.master, b"MDSBTN,osd\n")
    time.sleep(0.5)
    log = open("/tmp/mister-display.log").read()
    check("touch button logged", "display button osd" in log, log[-200:])
    check("daemon survives a failing button", sh("bash {}/MiSTerLily/S60misterlily status".format(FAT)) == 0)

    # The sleep file (MiSTer SAM) pauses sending.
    open("/tmp/tty2oled_sleep", "w").close()
    time.sleep(0.3)
    before = len(disp2.data)
    set_core("SNES")
    check("sleep file pauses", b"SNES" not in bytes(disp2.data[before:]))
    before = len(disp2.data)
    os.remove("/tmp/tty2oled_sleep")
    time.sleep(0.8)
    check("resumes after the sleep file", gsc in bytes(disp2.data[before:]))

    rc = sh("bash {}/MiSTerLily/uninstall.sh".format(FAT))
    check("uninstall exit 0", rc == 0)
    check("daemon stopped", sh("bash {}/MiSTerLily/S60misterlily status".format(FAT)) != 0)
    check("tty2oled daemon restored", os.path.exists(FAT + "/tty2oled/S60tty2oled"))
    check("boot line removed", "MiSTerLily" not in open(FAT + "/linux/user-startup.sh").read())
    sh("bash {}/tty2oled/S60tty2oled stop".format(FAT))

    print("{} failure(s)".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
