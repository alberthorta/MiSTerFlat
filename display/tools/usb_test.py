#!/usr/bin/env python3
"""Phase 2 USB CDC check against a connected T-Display-S3.

    python3 tools/usb_test.py /dev/cu.usbmodemXXXX        (macOS)
    python3 tools/usb_test.py /dev/ttyACM0                (Linux / MiSTer)

Checks: MDSPING, MDSINFO, CMDHWINF (tty2oled format), ttyack after every line, a burst of
commands in one write, and that opening/closing the port many times does not reset the board.
Exit code 0 when every check passes.
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mister"))
from mdsserial import BOARDS, Port  # noqa: E402

failures = 0


def check(name, ok, detail=""):
    global failures
    print("{} {}{}".format("PASS" if ok else "FAIL", name, "  " + detail if detail else ""))
    if not ok:
        failures += 1


def info(port):
    reply = port.query("MDSINFO")
    if not reply:
        return None
    m = re.search(rb"MDSINFO;(.*)\n", reply)
    if not m:
        return None
    return dict(kv.split("=", 1) for kv in m.group(1).decode().split(";") if "=" in kv)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    path = sys.argv[1]

    with Port(path) as port:
        port.write("CMDSTTYACK,1\n")  # our daemon turns acks off while it runs
        reply = port.query("MDSPING", token="ttyack;")
        check("MDSPING -> MDSPONG;up=<ms> + ttyack",
              reply is not None and re.match(rb"^MDSPONG;up=\d+\nttyack;", reply) is not None, repr(reply))

        before = info(port)
        check("MDSINFO", before is not None and before.get("fw") is not None, str(before))

        reply = port.query("CMDHWINF")
        m = reply and re.match(rb"^(HW[0-9A-Z]{7});MDS-[0-9.]+;\n", reply)
        check("CMDHWINF -> <board id>;MDS-x.y.z;", bool(m) and m.group(1).decode() in BOARDS, repr(reply))
        port.read_until("ttyack;", 1.0)
        if reply:
            line = reply.decode().split("\n")[0]
            # The same slicing installer.sh does.
            mcu, ver = line[:9], line.rsplit(";", 1)[0][10:]
            check("installer.sh parse", mcu in BOARDS and ver.startswith("MDS-"), "MCUtype={} SWver={}".format(mcu, ver))

        port.drain()
        burst = "QWERTZ\nCMDCON,255\nCMDSETTIME,1759939200\nCMDSAVER,0,0,0\nCMDNULL\n"
        port.write(burst)
        got = port.read_for(0.5)
        check("5 commands in one write -> 5 acks", got.count(b"ttyack;") == 5, repr(got))

    # tty2oled.sh opens and closes the device for every message.
    uptime_before = int(before["uptime_ms"]) if before else 0
    for _ in range(20):
        with Port(path) as p:
            p.write("CMDNULL\n")
        time.sleep(0.05)
    time.sleep(0.3)
    with Port(path) as port:
        after = info(port)
    ok = after is not None and before is not None and int(after["uptime_ms"]) > uptime_before
    check("20 open/close cycles do not reset the board", ok,
          "uptime {} -> {}".format(uptime_before, after.get("uptime_ms") if after else None))

    # What installer.sh sees: the stable daemon never reads, so acks pile up in the device and
    # arrive in front of the CMDHWINF reply. Informational only.
    for _ in range(10):
        with Port(path) as p:
            p.write("CMDNULL\n")
    with Port(path) as port:
        port.write("CMDHWINF\n")
        first = port.read_until("\n", 2.0)
        port.flush_stale()
    print("INFO first line after 10 unread acks: {!r}".format(first))

    print("{} failure(s)".format(failures))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
