#!/usr/bin/env python3
"""Build MiSTer NeoGeo .neo files from a ROM collection using MAME's neogeo.xml software list."""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path

from mister_arcade_builder.index import Entry, build_index

# Area order is the order load_neo() in Main_MiSTer reads the body.
AREAS = ('maincpu', 'fixed', 'audiocpu', 'ymsnd:adpcma', 'ymsnd:adpcmb', 'sprites')
HEADER = struct.Struct('<4B10I33s17s')
HEADER_SIZE = 4096
# Encrypted or bootleg boards need decryption the converter does not do. rom_kof98 and
# rom_mslugx are protected P ROMs that MAME patches at load time.
UNSUPPORTED_SLOTS = ('cmc', 'sma', 'pvc', 'pcm2', 'k2k2', 'boot_', 'rom_kof98', 'rom_mslugx')
# rom_fatfur2 is handled by the core from the NGH number (quirk table in neogeo_loader.cpp).
KNOWN_LOADFLAGS = {None, 'load16_word_swap', 'load16_byte', 'continue', 'fill', 'ignore'}


class Unsupported(Exception):
    pass


def num(text: str) -> int:
    return int(text, 0)


def load_softlist(path: Path) -> dict:
    root = ET.parse(path).getroot()
    games = {}
    for sw in root.findall('software'):
        name = sw.get('name', '')
        if not re.fullmatch(r'[a-z0-9_]+', name):
            raise ValueError(f'unsafe software name in list: {name!r}')
        part = sw.find('part')
        info = {i.get('name'): i.get('value', '') for i in sw.findall('info')}
        slot = next((f.get('value', '') for f in (part.findall('feature') if part is not None else [])
                     if f.get('name') == 'slot'), '')
        areas = {}
        for area in (part.findall('dataarea') if part is not None else []):
            areas[area.get('name')] = [dict(r.attrib) for r in area.findall('rom')]
        games[name] = {
            'name': name,
            'description': sw.findtext('description', ''),
            'year': sw.findtext('year', ''),
            'publisher': sw.findtext('publisher', ''),
            'serial': info.get('serial', ''),
            'slot': slot,
            'areas': areas,
        }
    return games


def unsupported_reason(game: dict):
    if game['slot'].startswith(UNSUPPORTED_SLOTS):
        return f"special board: {game['slot']}"
    extra = set(game['areas']) - set(AREAS)
    if extra:
        return f"extra areas: {', '.join(sorted(extra))}"
    for roms in game['areas'].values():
        for rom in roms:
            if rom.get('loadflag') not in KNOWN_LOADFLAGS:
                return f"loadflag {rom.get('loadflag')}"
            if rom.get('name') and rom.get('status') == 'nodump':
                return f"no dump of {rom['name']}"
    if not game['areas'].get('maincpu') or not game['areas'].get('fixed'):
        return 'no P or S ROM'
    return None


def required_roms(game: dict):
    """Named ROMs with their whole file size: continue and ignore lines read more of the same file."""
    out = []
    for roms in game['areas'].values():
        last = None
        for rom in roms:
            if rom.get('name'):
                last = dict(rom, file_size=num(rom['size']))
                out.append(last)
            elif last is not None and rom.get('loadflag') in ('continue', 'ignore'):
                last['file_size'] += num(rom['size'])
            else:
                last = None
    return out


def read_rom(entry: Entry, crc: str, handles: dict) -> bytes:
    if entry.name is None:
        data = Path(entry.container).read_bytes()
    else:
        zf = handles.get(entry.container)
        if zf is None:
            zf = handles[entry.container] = zipfile.ZipFile(entry.container)
        data = zf.read(entry.name)
    got = f'{zlib.crc32(data) & 0xFFFFFFFF:08x}'
    if got != crc:
        raise ValueError(f'{entry.container} -> {entry.name}: crc {got}, expected {crc}')
    return data


def build_area(roms: list, fetch) -> bytes:
    """Lay out one data area like MAME does, keeping gaps so tile and sample addresses stay right."""
    out = bytearray()
    data, pos, step = b'', 0, 1

    def put(offset: int, chunk: bytes, stride: int):
        end = offset + (len(chunk) - 1) * stride + 1 if chunk else offset
        if len(out) < end:
            out.extend(bytes(end - len(out)))
        out[offset:end:stride] = chunk

    for rom in roms:
        flag = rom.get('loadflag')
        size = num(rom['size'])
        if flag == 'fill':
            put(num(rom.get('offset', '0')), bytes([num(rom.get('value', '0')) & 0xFF]) * size, 1)
            continue
        if flag == 'ignore':
            pos += size
            continue
        if flag != 'continue':
            data = fetch(rom)
            pos = 0
            step = 2 if flag == 'load16_byte' else 1
        chunk = data[pos:pos + size]
        if len(chunk) != size:
            raise ValueError(f'continue past end of {rom.get("name", "previous ROM")}')
        put(num(rom['offset']), chunk, step)
        pos += size
    return bytes(out)


def ngh_from_serial(serial: str):
    m = re.search(r'\b(?:NGM|NGH)-(\d{3})', serial)
    return int(m.group(1), 16) if m else None


def make_neo(game: dict, fetch) -> bytes:
    body = [build_area(game['areas'].get(a, []), fetch) for a in AREAS]
    p = body[0]
    # The cart header keeps the NGH number at 0x108; P is stored in MAME file order (byte-swapped words).
    ngh = struct.unpack_from('<H', p, 0x108)[0] if len(p) >= 0x10A else 0
    year = int(game['year']) if game['year'].isdigit() else 0
    # Name[33] is what the MiSTer file browser shows; the serial only wastes those bytes.
    title = re.sub(r'\s*\((?:NG[MH]|ADM|NGM)-[^)]*\)', '', game['description']).strip()
    header = HEADER.pack(ord('N'), ord('E'), ord('O'), 1, *(len(b) for b in body), year, 0, 0, ngh,
                         title.encode('ascii', 'replace')[:32],
                         game['publisher'].encode('ascii', 'replace')[:16])
    return header.ljust(HEADER_SIZE, b'\0') + b''.join(body)


def convert(inputs, output: Path, softlist: Path, cache_dir: Path, only=None, dry_run=False) -> dict:
    games = load_softlist(softlist)
    index = build_index(inputs, cache_dir, exclude=[output])
    by_key = {}
    for crc, entries in index.by_crc.items():
        for e in entries:
            by_key.setdefault((crc, e.size), e)
    report = {'complete': [], 'incomplete': [], 'unsupported': [], 'errors': [], 'warnings': [],
              'bad_input_zips': [{'path': p, 'error': e} for p, e in index.bad_zips]}
    for name, game in sorted(games.items()):
        if only and not (only.search(name) or only.search(game['description'])):
            continue
        roms = required_roms(game)
        found = [r for r in roms if (r.get('crc'), r['file_size']) in by_key]
        if not found:
            continue
        reason = unsupported_reason(game)
        if reason:
            report['unsupported'].append({'setname': name, 'reason': reason})
            continue
        missing = [r['name'] for r in roms if r not in found]
        if missing:
            report['incomplete'].append({'setname': name, 'missing': missing})
            continue
        if dry_run:
            report['complete'].append(name)
            continue
        handles, tmp = {}, None
        try:
            sizes = {r['name']: r['file_size'] for r in roms}
            neo = make_neo(game, lambda r: read_rom(by_key[(r['crc'], sizes[r['name']])], r['crc'], handles))
            ngh = struct.unpack_from('<I', neo, 40)[0]
            expected = ngh_from_serial(game['serial'])
            if expected is not None and expected != ngh:
                report['warnings'].append(f'{name}: NGH 0x{ngh:03x} in P ROM, serial says 0x{expected:03x}')
            output.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=output, suffix='.tmp', delete=False) as f:
                tmp = Path(f.name)
                f.write(neo)
            os.replace(tmp, output / f'{name}.neo')
            tmp = None
            report['complete'].append(name)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            report['errors'].append({'setname': name, 'error': str(exc)})
        finally:
            for zf in handles.values():
                zf.close()
            if tmp is not None:
                tmp.unlink(missing_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    target = output / 'neo-report.json'
    tmp_report = target.with_suffix('.json.tmp')
    tmp_report.write_text(json.dumps(report, indent=2), encoding='utf-8')
    os.replace(tmp_report, target)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, action='append', type=Path, help='ROM folder (repeatable, read only)')
    parser.add_argument('--output', required=True, type=Path, help='folder for .neo files and neo-report.json')
    parser.add_argument('--softlist', required=True, type=Path, help="MAME hash/neogeo.xml")
    parser.add_argument('--cache-dir', type=Path, default=Path('~/.cache/mister-arcade-builder/neo'))
    parser.add_argument('--only', help='regular expression matching set name or description')
    parser.add_argument('--dry-run', action='store_true', help='write the report without creating .neo files')
    args = parser.parse_args(argv)
    inputs = [p.expanduser().resolve() for p in args.input]
    output = args.output.expanduser().resolve()
    try:
        for root in inputs:
            if not root.is_dir():
                raise ValueError(f'input folder does not exist: {root}')
            if output == root or root in output.parents or output in root.parents:
                raise ValueError('--input and --output folders must not overlap')
        only = re.compile(args.only, re.IGNORECASE) if args.only else None
        report = convert(inputs, output, args.softlist.expanduser().resolve(),
                         args.cache_dir.expanduser(), only=only, dry_run=args.dry_run)
    except (OSError, ValueError, ET.ParseError, re.error) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1
    print(f"Complete: {len(report['complete'])}; incomplete: {len(report['incomplete'])}; "
          f"unsupported: {len(report['unsupported'])}; errors: {len(report['errors'])}; "
          f"warnings: {len(report['warnings'])}")
    print(f"Report: {output / 'neo-report.json'}")
    return 1 if report['errors'] or report['bad_input_zips'] else 2 if report['incomplete'] or report['unsupported'] else 0


if __name__ == '__main__':
    sys.exit(main())
