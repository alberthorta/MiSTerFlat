#!/usr/bin/env python3
"""Checks the firmware file test of misterlily_flash.py, which runs before the board is touched.

    python3 tests/mister/test_flash_image.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "mister"))
import misterlily_flash as mf  # noqa: E402

failures = 0


def image(chip=mf.ESP32S3_CHIP_ID, marker=b"HWTDISPS3;MDS-1.2.3;", size=4096):
    header = bytes([0xE9, 3, 2, 0x4F]) + bytes(8) + bytes([chip & 0xFF, chip >> 8]) + bytes(10)
    return (header + b"\0" * 100 + marker).ljust(size, b"\0")


def check(name, data, want):
    """want: the version, or None when the file must be refused."""
    global failures
    try:
        got = mf.image_version(data)
    except mf.FlashError as e:
        got, why = None, str(e)
    else:
        why = ""
    ok = got == want
    print("{} {}{}".format("PASS" if ok else "FAIL", name, "" if ok else "  got {!r} {}".format(got, why)))
    failures += not ok


check("MiSTerLily image", image(), "1.2.3")
check("pre-release version", image(marker=b"HWTDISPS3;MDS-0.2.0-rc1;"), "0.2.0-rc1")
check("no MiSTerLily reply inside", image(marker=b"HWESP32S3;230702;"), None)
check("other chip", image(chip=0), None)
check("not an image", b"\x89PNG\r\n\x1a\n".ljust(4096, b"\0"), None)
check("too large for app0", image(size=mf.APP_SIZE + 1), None)
check("empty", b"", None)
sys.exit(1 if failures else 0)
