#!/usr/bin/env python3
"""Send command lines to the display and print what it answers.

    python3 tools/send.py /dev/cu.usbmodemXXXX CMDTEST
    python3 tools/send.py /dev/cu.usbmodemXXXX "CMDROT,1" "CMDCON,255" MDSINFO

On macOS prefer this over `echo ... > /dev/cu.*`: closing the port right after writing can drop
the data there (see docs/research.md section 6).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mister"))
from mdsserial import Port  # noqa: E402


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    with Port(sys.argv[1]) as port:
        port.flush_stale()
        for line in sys.argv[2:]:
            port.write(line + "\n")
            reply = port.read_for(0.3)
            print("{} -> {}".format(line, reply.decode(errors="replace") if reply else "(no reply)"))


if __name__ == "__main__":
    main()
