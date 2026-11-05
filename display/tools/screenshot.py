#!/usr/bin/env python3
"""Save what the display currently shows as a PNG (via the MDSSHOT command).

    python3 tools/screenshot.py /dev/cu.usbmodemXXXX screen.png
"""
import os
import struct
import sys
import time
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mister"))
from mdsserial import Port  # noqa: E402


def write_png(path, width, height, rgb_rows):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + row for row in rgb_rows)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw, 9)))
        f.write(chunk(b"IEND", b""))


def rgb565_be_to_rgb(data, width, height):
    rows = []
    for y in range(height):
        row = bytearray()
        line = data[y * width * 2:(y + 1) * width * 2]
        for (v,) in struct.iter_unpack(">H", line):
            r, g, b = (v >> 11) & 0x1F, (v >> 5) & 0x3F, v & 0x1F
            row += bytes(((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)))
        rows.append(bytes(row))
    return rows


def grab(port, timeout=10.0):
    port.flush_stale()
    port.write("MDSSHOT\n")
    head = port.read_until("\n", 2.0)
    if not head:
        raise SystemExit("no MDSSHOT reply")
    start = head.index(b"MDSSHOT,")
    line, rest = head[start:].split(b"\n", 1)
    _, w, h, n = line.decode().split(",")
    w, h, n = int(w), int(h), int(n)
    if n == 0:
        raise SystemExit("display has no framebuffer (or a screenshot is already running)")
    data = bytearray(rest)
    end = time.monotonic() + timeout
    # The ttyack for the MDSSHOT line is queued after the header, before the pixels.
    ack = b"ttyack;"
    while len(data) < len(ack) and time.monotonic() < end:
        data += port.read_for(0.05)
    if data.startswith(ack):
        del data[:len(ack)]
    while len(data) < n and time.monotonic() < end:
        data += port.read_for(0.05)
    if len(data) < n:
        raise SystemExit("short screenshot: {} of {} bytes".format(len(data), n))
    return w, h, bytes(data[:n])


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    with Port(sys.argv[1]) as port:
        t = time.monotonic()
        w, h, data = grab(port)
    write_png(sys.argv[2], w, h, rgb565_be_to_rgb(data, w, h))
    print("{}x{} saved to {} in {:.1f} s".format(w, h, sys.argv[2], time.monotonic() - t))


if __name__ == "__main__":
    main()
