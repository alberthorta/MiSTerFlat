#!/usr/bin/env python3
"""Store the start-up picture in the display's flash (it is shown before the MiSTer connects).

    python3 tools/set_logo.py /dev/cu.usbmodemXXXX logo.png     # store (PNG or baseline JPEG)
    python3 tools/set_logo.py /dev/cu.usbmodemXXXX --status     # what is stored
    python3 tools/set_logo.py /dev/cu.usbmodemXXXX --clear      # back to the text start screen

The picture is drawn centred in the logo area: 320x184 at the top of a 240-line screen, 320x130 on
the 170-line T-Display-S3 (a 320x184 picture shows its middle 130 lines there). The line below is
kept for "Waiting for MiSTer", and the version goes in the top-right corner. Larger pictures are
cropped. On the MiSTer,
put the file at /media/fat/MiSTerLily/art/STARTUP.png and the daemon stores it when it changes.
"""
import argparse
import binascii
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mister"))
from mdsserial import Port  # noqa: E402

MAX_BYTES = 256 * 1024  # StartupLogo::kMaxBytes


def logo_frame(path):
    with open(path, "rb") as f:
        data = f.read()
    fmt = "jpg" if path.lower().endswith((".jpg", ".jpeg")) else "png"
    head = "MDSLOGO,{},{:08x},{}\n".format(len(data), binascii.crc32(data) & 0xFFFFFFFF, fmt)
    return head.encode(), data


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("device")
    ap.add_argument("picture", nargs="?")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--clear", action="store_true")
    opts = ap.parse_args()

    with Port(opts.device) as port:
        port.write("CMDSTTYACK,1\n")
        if opts.clear:
            print(port.query("MDSCFG,logo,0").decode().strip())
        elif opts.picture:
            head, data = logo_frame(opts.picture)
            if len(data) > MAX_BYTES:
                sys.exit("{} bytes, the display accepts at most {}".format(len(data), MAX_BYTES))
            port.flush_stale()
            port.write(head + data)
            reply = port.read_until(b"ttyack;", 10)
            print((reply or b"no reply").decode(errors="replace").replace("ttyack;", "").strip())
        print(port.query("MDSLOGO").decode().strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
