#!/usr/bin/env python3
"""Write the .rom files that Analogue Pocket arcade cores load.

Pocket arcade cores ship one instance .json per game in Assets/<platform>/<author.core>/,
naming a .rom in Assets/<platform>/common/. For jotego's cores, and for most other ports of
MiSTer arcade cores, that file is the ROM the MiSTer loader assembles from the game's .mra
(index 0, interleaves and patches applied), so it is built here with the same port of
mra_loader.cpp that --verify uses. The .mra is found by set name (the .rom name, without a
"_ap" suffix), then by game title.

    python3 pocket_arcade.py --pocket /Volumes/Analogue --games ~/Desktop/roms/games
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from mister_arcade_builder.mra import parse_xml
from mister_arcade_builder.verify import MISMATCH, NO_MD5, NOT_FOUND, OK, ZipCache, load_rom, to_int


def pocket_games(pocket: Path, alternatives: bool = False):
    """(core folder, rom file name, game title) for every jotego instance json.

    Each version of a game needs its own full .rom, so the _alternatives folders (8 Bubble
    Bobble sets, for example) are left out unless asked for: on a 32 GB card they do not fit.
    """
    out = []
    for js in sorted(pocket.glob('Assets/*/*/**/*.json')):
        if js.relative_to(pocket / 'Assets').parts[1] == 'common':
            continue
        if not alternatives and '_alternatives' in js.parts:
            continue
        try:
            inst = json.loads(js.read_text(encoding='utf-8', errors='replace'))['instance']
            slots = inst['data_slots']
        except (ValueError, KeyError, TypeError):
            continue
        sub = (inst.get('data_path') or '').strip('/')
        for slot in slots:
            name = slot.get('filename', '')
            if name.endswith('.rom') and '/' not in name and '..' not in sub:
                folder, author_core = js.relative_to(pocket / 'Assets').parts[:2]
                out.append((f'{folder}/common/{sub}' if sub else f'{folder}/common', name, js.stem, author_core))
    return out


def norm(title: str) -> str:
    title = re.sub(r'\s*[\(\[].*$', '', title.lower())
    return re.sub(r'[^a-z0-9]', '', re.sub(r'^the\s+|,\s*the$', '', title))


def mra_index(mra_root: Path):
    """setname -> [(path, title, rbf)], from every cached .mra; plus a title index."""
    index = defaultdict(list)
    for path in mra_root.rglob('*.mra'):
        try:
            root = parse_xml(path.read_bytes())
        except Exception:
            continue
        setname = (root.findtext('setname') or '').strip()
        if setname:
            entry = (path, path.stem, (root.findtext('rbf') or '').strip())
            index[setname].append(entry)
            index['title:' + norm(path.stem)].append(entry)
    return index


def candidates_for(index, rom_name: str, title: str, author_core: str = '', platform: str = ''):
    stem = rom_name[:-4]
    for key in (stem, re.sub(r'_ap$', '', stem)):
        if index.get(key):
            return pick(index[key], title, author_core, platform)
    return pick(index.get('title:' + norm(title), []), title, author_core, platform)


def pick(mras, title: str, author_core: str = '', platform: str = ''):
    """Best .mra first: one for the same core family as the Pocket core, then the same title.

    Two cores can share a set name with different ROM layouts (jotego's jtriders and Coin-Op's
    tmnt2 both load "tmnt2"); a Coin-Op core fed jotego's layout boots to a black screen.
    """
    jotego = author_core.lower().startswith('jotego.')

    def family(m):
        rbf = m[2].lower()
        if 'core_mras' in m[0].parts:  # published by the Pocket core's own repository
            return -1
        if jotego:
            return 0 if rbf.startswith('jt') else 1
        if rbf.startswith('jt'):
            return 2
        return 0 if platform and platform.lower() in rbf else 1
    return sorted(mras, key=lambda m: (family(m), m[1] != title, '_alternatives' in m[0].parts, str(m[0])))


def build(mra_path: Path, zips: ZipCache):
    """The first index-0 ROM that loads with a matching (or absent) md5, like MiSTer picks it."""
    root = parse_xml(mra_path.read_bytes())
    last = None
    for rom in root.iter('rom'):
        if not rom.get('zip') or to_int(rom.get('index')) != 0:
            continue
        check = load_rom(rom, zips, keep_data=True)
        if check.status in (OK, NO_MD5):
            return check
        last = check
    return last


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--pocket', required=True, type=Path, help='Pocket SD card root')
    ap.add_argument('--games', required=True, type=Path, action='append',
                    help='folder with mame/ (and hbmame/) zips; repeat it to try more folders in order')
    ap.add_argument('--mra', type=Path, action='append',
                    help='folder with .mra files, repeatable (default: the builder cache); '
                         'some Pocket-only cores keep theirs in their own repository')
    ap.add_argument('--list-sets', action='store_true', help='only print the set names the card needs')
    ap.add_argument('--alternatives', action='store_true', help='also write the ROMs of the _alternatives games')
    ap.add_argument('--alt-skip', action='append', default=[], metavar='PLATFORM',
                    help='with --alternatives, leave out this platform folder (e.g. jtcps2, whose '
                         'regional versions take about 9 GB)')
    ap.add_argument('--keep-free', type=float, default=1.0, help='stop when the card has less free space (GB)')
    args = ap.parse_args(argv)

    wanted = pocket_games(args.pocket, args.alternatives)
    main_roms = {(c, r) for c, r, _, _ in pocket_games(args.pocket)}
    if args.list_sets:
        print('\n'.join(sorted({rom[:-4] for _, rom, _, _ in wanted})))
        return 0
    index = defaultdict(list)
    for folder in args.mra or [Path('~/.cache/mister-arcade-builder/mra').expanduser()]:
        for key, entries in mra_index(folder).items():
            index[key].extend(entries)
    zips = [ZipCache(root) for root in args.games]
    stats, missing = Counter(), []
    done = set()
    for core, rom_name, title, author_core in wanted:
        if args.alt_skip and core.split('/')[0] in args.alt_skip and (core, rom_name) not in main_roms:
            continue
        target = args.pocket / 'Assets' / core / rom_name
        if (core, rom_name) in done:
            continue
        done.add((core, rom_name))
        candidates = candidates_for(index, rom_name, title, author_core, core.split('/')[0])
        if not candidates:
            stats['no .mra'] += 1
            continue
        check = None
        # A zip with the same name can differ between collections (one may lack an EEPROM
        # file the .mra wants), so every folder is tried before giving up on a game.
        for mra_path, _, _ in candidates:
            for z in zips:
                check = build(mra_path, z)
                if check and check.status in (OK, NO_MD5):
                    break
            if check and check.status in (OK, NO_MD5):
                break
        if not check or check.status not in (OK, NO_MD5):
            stats['missing ROMs' if check and check.status == NOT_FOUND else 'md5 mismatch'] += 1
            missing.append(f'{core}/{rom_name} ({title})')
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        st = os.statvfs(args.pocket)
        if st.f_bavail * st.f_frsize - len(check.data) < args.keep_free * 1e9:
            stats['skipped: card full'] += 1
            continue
        if target.exists() and target.read_bytes() == check.data:
            stats['already there'] += 1
            continue
        with tempfile.NamedTemporaryFile(dir=target.parent, suffix='.tmp', delete=False) as f:
            f.write(check.data)
        os.replace(f.name, target)
        stats['written (md5 ok)' if check.status == OK else 'written (no md5 to check)'] += 1
    for z in zips:
        z.close()
    print(dict(stats))
    if missing:
        print(f'{len(missing)} games without all their ROMs, e.g.:', *missing[:15], sep='\n  ')
    return 0


if __name__ == '__main__':
    sys.exit(main())
