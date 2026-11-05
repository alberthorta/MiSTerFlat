#!/usr/bin/env python3
"""Make MAME-style CPS2 <setname>.key files from the key list of the no-battery-cps2 project.

That project publishes the 20-byte keys to re-program CPS2 B boards whose battery
died. MAME and the jtcps2 MiSTer core use the same 20 bytes as "<setname>.key".
Keys whose CRC does not match what the downloaded .mra files ask for are skipped:
a few entries in keys.txt differ from the MAME dumps.
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.request
import zlib
from pathlib import Path

KEYS_URL = "https://raw.githubusercontent.com/artemiourbina/no-battery-cps2/HEAD/keys.txt"
LINE = re.compile(r"\{([^}]*)\}.*//\s*(\S+)")
MRA_KEY = re.compile(r'name="([^"]+)\.key"\s+crc="([0-9a-fA-F]+)"', re.IGNORECASE)


def parse_keys(text: str) -> dict:
    keys = {}
    for line in text.splitlines():
        m = LINE.search(line)
        if not m:
            continue
        data = bytes(int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{2})", m.group(1)))
        if len(data) == 20:
            keys[m.group(2).strip().lower()] = data
    return keys


def wanted_crcs(mra_dir: Path) -> dict:
    out = {}
    for p in mra_dir.rglob("*.mra"):
        for name, crc in MRA_KEY.findall(p.read_text(encoding="utf-8", errors="replace")):
            out[name.lower()] = crc.lower().zfill(8)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--output", required=True, type=Path, help="folder for the .key files")
    p.add_argument("--keys", help="local keys.txt (default: download it)")
    p.add_argument("--cache", type=Path, default=Path("~/.cache/mister-arcade-builder").expanduser(),
                   help="mister_arcade.py cache, to check keys against the .mra files")
    args = p.parse_args()

    if args.keys:
        text = Path(args.keys).read_text()
    else:
        with urllib.request.urlopen(KEYS_URL, timeout=60) as resp:
            text = resp.read().decode()
    keys = parse_keys(text)

    wanted = wanted_crcs(args.cache / "mra")
    if not wanted:
        print("no .mra in the cache: run mister_arcade.py once first", file=sys.stderr)
        return 1

    args.output.mkdir(parents=True, exist_ok=True)
    written, skipped, unused = 0, [], 0
    for name, data in sorted(keys.items()):
        crc = f"{zlib.crc32(data):08x}"
        if name not in wanted:
            unused += 1
            continue
        if wanted[name] != crc:
            skipped.append(f"{name} (crc {crc}, the .mra wants {wanted[name]})")
            continue
        target = args.output / f"{name}.key"
        if not target.exists() or target.read_bytes() != data:
            target.write_bytes(data)
        written += 1

    print(f"{written} .key files in {args.output}")
    if unused:
        print(f"{unused} keys not used by any .mra")
    for s in skipped:
        print(f"skipped {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
