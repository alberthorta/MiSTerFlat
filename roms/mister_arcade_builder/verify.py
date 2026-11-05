"""Load .mra files from the output folder the way MiSTer does, and check the md5.

This is a port of the ROM assembly in Main_MiSTer support/arcade/mra_loader.cpp
(xml_send_rom, rom_data, rom_file, rom_patch). Quirks are kept on purpose: the
goal is to get the same bytes MiSTer would send to the core, not "correct" ones.

- md5 in <rom md5="..."> is what MiSTer checks. MiSTer computes it over the data
  in the order it is read (files and inline bytes), before interleaving.
- asm_md5 (jotego .mra files) is the md5 of the assembled ROM after interleave but
  before <patch>: checked on 6 jotego .mra with patches, all match only that way.
"""
from __future__ import annotations

import hashlib
from collections import OrderedDict
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET

from .mra import parse_xml, split_zips

RECENT_ENTRIES = 8
OK, MISMATCH, NOT_FOUND, NO_MD5 = "ok", "md5_mismatch", "file_not_found", "no_md5"


def hexstr_to_bytes(text: str) -> bytes:
    """Same algorithm as hexstr_to_char(): two characters per byte, separators only between pairs."""
    out = bytearray()
    s = text or ""
    i, n = 0, len(s)

    def val(ch: str) -> int:
        return (ord(ch) % 32 + 9) % 25

    while i < n:
        while i < n and s[i] in "\n\r ,\t":
            i += 1
        if i >= n:
            break
        v1 = val(s[i]) * 16
        i += 1
        if i >= n:
            out.append(val(s[i - 1]) & 0xFF)
            break
        out.append((v1 + val(s[i])) & 0xFF)
        i += 1
    return bytes(out)


class ZipCache:
    def __init__(self, games_root: Path):
        self.root = games_root  # the folder that holds mame/ and hbmame/
        self.zips: Dict[Path, Optional[zipfile.ZipFile]] = {}
        # .mra files often read one big file many times with offset/length;
        # keep the last few decompressed entries.
        self.recent: "OrderedDict[tuple, bytes]" = OrderedDict()

    def path_for(self, zip_name: str) -> Path:
        if zip_name.startswith("/"):
            return self.root / zip_name.lstrip("/")
        return self.root / "mame" / zip_name

    def read(self, zip_name: str, part_name: str, crc: int) -> Optional[bytes]:
        """FileOpenZip(): look up by CRC first, then by name."""
        path = self.path_for(zip_name)
        if path not in self.zips:
            try:
                self.zips[path] = zipfile.ZipFile(path)
            except (OSError, zipfile.BadZipFile):
                self.zips[path] = None
        zf = self.zips[path]
        if zf is None:
            return None
        info = None
        if crc:
            info = next((i for i in zf.infolist() if i.CRC == crc), None)
        if info is None:
            try:
                info = zf.getinfo(part_name)
            except KeyError:
                return None
        key = (path, info.filename)
        data = self.recent.get(key)
        if data is None:
            data = zf.read(info)
            self.recent[key] = data
            if len(self.recent) > RECENT_ENTRIES:
                self.recent.popitem(last=False)
        else:
            self.recent.move_to_end(key)
        return data

    def close(self) -> None:
        for zf in self.zips.values():
            if zf is not None:
                zf.close()


class RomBuilder:
    """rom_start / rom_data / rom_patch with the same lane bookkeeping as MiSTer."""

    def __init__(self):
        self.data = bytearray()
        self.romlen = [0] * 8
        self.unitlen = 1
        self.stream_md5 = hashlib.md5()
        self.unpatched: Optional[bytes] = None

    def sync_lanes(self) -> None:
        for i in range(1, 8):
            self.romlen[i] = self.romlen[0]

    def add(self, buf: bytes, mapping: int) -> bool:
        self.stream_md5.update(buf)
        if not mapping:
            mapping = 1
        idx, reg = 0, mapping
        for _ in range(self.unitlen):
            if reg & 0xF:
                break
            reg >>= 4
            idx += 1
        if idx >= self.unitlen:
            return False  # illegal map

        offsets: List[int] = []
        reg, first, gaps = mapping, True, 0
        for _ in range(self.unitlen):
            if reg & 0xF:
                offsets.append(idx + (reg & 0xF) - 1 + gaps)
                first = False
            elif not first:
                gaps += 1
            reg >>= 4

        # Same result as MiSTer's byte loop, with strided slices so that tens of MB stay fast.
        u, k = self.unitlen, len(offsets)
        units, rem = divmod(len(buf), k)
        base = self.romlen[idx]
        need = base + u * (units + (1 if rem else 0))
        if need > len(self.data):
            self.data.extend(bytes(need - len(self.data)))
        for j, off in enumerate(offsets):
            start = base + off
            self.data[start:start + u * units:u] = buf[j:k * units:k]
        for j in range(rem):
            self.data[base + u * units + offsets[j]] = buf[k * units + j]
        self.romlen[idx] = need
        return True

    def add_repeated(self, buf: bytes, mapping: int, repeat: int) -> None:
        # One call with the bytes repeated gives the same result as `repeat` calls,
        # unless a call ends in the middle of a unit; .mra padding can repeat millions of times.
        if repeat > 1 and buf and len(buf) % max(self.bytes_per_unit(mapping), 1) == 0:
            self.add(buf * repeat, mapping)
            return
        for _ in range(repeat):
            self.add(buf, mapping)

    def bytes_per_unit(self, mapping: int) -> int:
        reg, n = mapping or 1, 0
        for _ in range(self.unitlen):
            if reg & 0xF:
                n += 1
            reg >>= 4
        return n

    def patch(self, buf: bytes, offset: int, xor: bool) -> None:
        if self.unpatched is None:
            self.unpatched = self.rom()
        if offset + len(buf) > self.romlen[0]:
            return
        for i, b in enumerate(buf):
            self.data[offset + i] = (self.data[offset + i] ^ b) if xor else b

    def rom(self) -> bytes:
        return bytes(self.data[: self.romlen[0]])


def strtoul(value: str, base: int) -> int:
    """C strtoul(): leading whitespace, then as many valid digits as there are; base 0 detects 0x and octal."""
    s = value.lstrip()
    if base == 0:
        if s[:2].lower() == "0x":
            base, s = 16, s[2:]
        elif s.startswith("0"):
            base = 8
        else:
            base = 10
    elif base == 16 and s[:2].lower() == "0x":
        s = s[2:]
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"[:base]
    n = 0
    for ch in s.lower():
        if ch not in digits:
            break
        n = n * base + digits.index(ch)
    return n & 0xFFFFFFFF


def to_int(value: Optional[str], default: int = 0) -> int:
    """An attribute read with strtoul(value, NULL, 0), or the default when it is absent."""
    if value is None:
        return default
    return strtoul(value, 0)


@dataclass
class RomCheck:
    index: int
    status: str
    md5: str = ""
    asm_md5: str = ""
    got_md5: str = ""
    got_asm_md5: str = ""
    not_found: List[str] = field(default_factory=list)
    data: Optional[bytes] = None  # the assembled ROM, patches applied (keep_data=True)


@dataclass
class MraCheck:
    path: str
    status: str
    roms: List[RomCheck] = field(default_factory=list)


def load_rom(rom: ET.Element, zips: ZipCache, keep_data: bool = False) -> RomCheck:
    b = RomBuilder()
    rom_zips = rom.get("zip") or ""
    not_found: List[str] = []

    def part(el: ET.Element, inside_interleave: bool, imap_default: int) -> None:
        name = (el.get("name") or "").strip()
        offset = to_int(el.get("offset"))
        length = to_int(el.get("length"), -1)
        repeat = to_int(el.get("repeat"), 1)
        crc = strtoul(el.get("crc") or "", 16)
        map_attr = el.get("map")
        imap = strtoul(map_attr, 16) if map_attr is not None else 0
        if map_attr is not None and imap and not inside_interleave:
            b.unitlen = min(len(map_attr), 8)
            b.sync_lanes()

        if name:
            zip_list = el.get("zip") or rom_zips
            found = False
            for z in split_zips(zip_list):
                data = zips.read(z, name, crc)
                if data is None:
                    continue
                if offset:
                    data = data[offset:]
                if 0 < length < len(data):
                    data = data[:length]
                b.add_repeated(data, imap, repeat)
                found = True
                break
            if not found and "ignore_crc" not in el.attrib:
                not_found.append(f"{name} ({crc:08x})")
        else:
            b.add_repeated(hexstr_to_bytes(el.text or ""), imap, repeat)

        if not inside_interleave:
            b.unitlen = 1

    def walk(el: ET.Element, inside_interleave: bool) -> None:
        for child in el:
            if not isinstance(child.tag, str):
                continue
            if child.tag == "part":
                part(child, inside_interleave, 0)
            elif child.tag == "interleave":
                ifrom = to_int(child.get("input"), 8)
                ito = to_int(child.get("output"), 0)
                valid = ifrom == 8 and 8 <= ito <= 64 and not ito & 7 and ito >= ifrom
                b.unitlen = ito // ifrom if valid and ifrom else 1
                b.sync_lanes()
                walk(child, valid)
                b.unitlen = 1
            elif child.tag == "patch":
                b.patch(hexstr_to_bytes(child.text or ""), to_int(child.get("offset")),
                        (child.get("operation") or "").lower() == "xor")
            else:
                walk(child, inside_interleave)

    walk(rom, False)

    md5 = (rom.get("md5") or "").strip().lower()
    asm = (rom.get("asm_md5") or "").strip().lower()
    md5 = "" if md5 == "none" else md5
    asm = "" if asm == "none" else asm
    got = b.stream_md5.hexdigest()
    got_asm = hashlib.md5(b.unpatched if b.unpatched is not None else b.rom()).hexdigest()
    if not_found:
        status = NOT_FOUND
    elif not md5 and not asm:
        status = NO_MD5
    elif (md5 and md5 != got) or (asm and asm != got_asm):
        status = MISMATCH
    else:
        status = OK
    return RomCheck(to_int(rom.get("index")), status, md5, asm, got, got_asm, not_found,
                    b.rom() if keep_data else None)


def verify_mra(path: str, data: bytes, zips: ZipCache) -> MraCheck:
    root = parse_xml(data)
    checks: List[RomCheck] = []
    rom0_ok = False
    for rom in root.iter("rom"):
        if not rom.get("zip"):
            continue
        index = to_int(rom.get("index"))
        # Once a rom 0 with a good md5 loaded, MiSTer skips the next rom 0 blocks.
        if index == 0 and rom0_ok:
            continue
        check = load_rom(rom, zips)
        if index == 0 and check.status == OK and check.md5:
            rom0_ok = True
        checks.append(check)

    if rom0_ok:
        checks = [c for c in checks if not (c.index == 0 and c.status != OK)]
    statuses = {c.status for c in checks}
    for s in (NOT_FOUND, MISMATCH, OK):
        if s in statuses:
            return MraCheck(path, s, checks)
    return MraCheck(path, NO_MD5, checks)


def verify_complete(res, sources: Dict[str, bytes], games_root: Path, jobs: int = 4) -> List[MraCheck]:
    """Verify every complete .mra of a Resolution against the zips under games_root."""
    from concurrent.futures import ThreadPoolExecutor
    from .resolve import COMPLETE

    todo = [s.mra.path for s in res.statuses if s.status == COMPLETE and s.mra.path in sources]

    def run(chunk: List[str]) -> List[MraCheck]:
        zips = ZipCache(games_root)
        try:
            return [verify_mra(path, sources[path], zips) for path in chunk]
        finally:
            zips.close()

    # One ZipCache per worker (ZipFile objects are not thread safe).
    jobs = max(1, jobs)
    chunks = [todo[i::jobs] for i in range(jobs)]
    out: List[MraCheck] = []
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for part in pool.map(run, chunks):
            out.extend(part)
    return sorted(out, key=lambda c: c.path)
