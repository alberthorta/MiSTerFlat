#!/usr/bin/env python3
"""Rebuild FB Alpha ZIPs from a collection using the target core's XML DAT."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath

from mister_arcade_builder.build import CrcMismatch, copy_entry
from mister_arcade_builder.index import Entry, scan_zip


def safe_name(name: str) -> bool:
    return bool(name) and '\\' not in name and not any(ord(c) < 32 for c in name) and not PurePosixPath(name).is_absolute() and all(p not in ('', '.', '..') for p in name.split('/'))


def load_dat(path: Path):
    root = ET.parse(path).getroot()
    games = {}
    for node in list(root.findall('game')) + list(root.findall('machine')):
        name = node.get('name', '')
        if not safe_name(name) or '/' in name or ':' in name:
            raise ValueError(f'unsafe set name in DAT: {name!r}')
        if name in games:
            raise ValueError(f'duplicate set in DAT: {name}')
        games[name] = node
    if not games:
        raise ValueError('DAT must be XML with <game> or <machine> entries')
    resolved = {}

    def requirements(name, trail=()):
        if name in trail:
            raise ValueError('cyclic DAT dependency: ' + ' -> '.join(trail + (name,)))
        if name in resolved:
            return resolved[name]
        if name not in games:
            raise ValueError(f'DAT dependency not found: {name}')
        node = games[name]
        parent = node.get('romof') or node.get('cloneof')
        roms = dict(requirements(parent, trail + (name,))) if parent else {}
        for rom in node.findall('rom'):
            filename = rom.get('name', '')
            if not safe_name(filename) or ':' in filename:
                raise ValueError(f'{name}: unsafe ROM name: {filename!r}')
            if rom.get('optional') == 'yes':
                continue
            crc = rom.get('crc', '').lower()
            size = rom.get('size')
            merged = roms.get(rom.get('merge', ''))
            if merged:
                crc = crc or merged['crc']
                size = size if size is not None else merged['size']
            if crc and not re.fullmatch(r'[0-9a-f]{1,8}', crc):
                raise ValueError(f'{name}/{filename}: invalid CRC')
            if size is None or int(size) < 0:
                raise ValueError(f'{name}/{filename}: missing or invalid size')
            roms[filename] = {'name': filename, 'crc': crc.zfill(8) if crc else '',
                              'size': int(size), 'nodump': rom.get('status') == 'nodump'}
        resolved[name] = roms
        return roms

    for name in games:
        requirements(name)
    return games, resolved


def convert(inputs, output, dat, only=None, dry_run=False):
    games, requirements = load_dat(dat)
    index, bad, input_sets = {}, [], set()
    for root in inputs:
        for path in sorted(root.rglob('*')):
            if not path.is_file() or path.suffix.lower() != '.zip':
                continue
            input_sets.add(path.stem)
            try:
                for filename, crc, size in scan_zip(str(path)):
                    index.setdefault((crc, size), []).append(Entry(str(path), filename, size))
            except (OSError, ValueError, zipfile.BadZipFile) as exc:
                bad.append({'path': str(path), 'error': str(exc)})
    report = {'dat': str(dat), 'dry_run': dry_run, 'complete': [], 'incomplete': [],
              'errors': [], 'unsupported': [], 'bad_input_zips': bad,
              'input_names_not_in_dat': sorted(input_sets - set(games))}
    def disk_requirements(name):
        node = games[name]
        disks = [d.get('name', '') for d in node.findall('disk') if d.get('optional') != 'yes']
        parent = node.get('romof') or node.get('cloneof')
        if parent:
            disks += disk_requirements(parent)
        return sorted(set(disks))

    for name in sorted(games):
        if only and not (only.search(name) or only.search(games[name].findtext('description', ''))):
            continue
        disks = disk_requirements(name)
        if disks:
            report['unsupported'].append({'setname': name, 'reason': 'CHD required', 'disks': disks})
            continue
        roms = requirements[name]
        if not roms:
            continue
        missing = [r for r in roms.values() if r['nodump'] or (r['crc'], r['size']) not in index]
        # Report represented sets, plus explicitly requested sets. Avoid listing
        # every absent game in a large DAT for a small input collection.
        represented = any((r['crc'], r['size']) in index for r in roms.values())
        named = any((root / (name + '.zip')).exists() for root in inputs)
        if not represented and not named and not only:
            continue
        if missing:
            report['incomplete'].append({'setname': name, 'missing': missing})
            continue
        if dry_run:
            report['complete'].append(name)
            continue
        handles = {}
        tmp = None
        try:
            output.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=output, suffix='.tmp', delete=False) as f:
                tmp = Path(f.name)
            with zipfile.ZipFile(tmp, 'w') as archive:
                for filename, rom in sorted(roms.items()):
                    copy_entry(index[(rom['crc'], rom['size'])][0], rom['crc'], archive, filename, handles)
            os.replace(tmp, output / (name + '.zip'))
            report['complete'].append(name)
        except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, CrcMismatch) as exc:
            report['errors'].append({'setname': name, 'error': str(exc)})
        finally:
            for archive in handles.values():
                archive.close()
            if tmp is not None:
                tmp.unlink(missing_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    target = output / 'fbalpha-report.json'
    tmp_report = target.with_suffix('.json.tmp')
    tmp_report.write_text(json.dumps(report, indent=2), encoding='utf-8')
    os.replace(tmp_report, target)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, action='append', type=Path, help='ZIP folder (repeatable, read only)')
    parser.add_argument('--output', required=True, type=Path, help='separate folder for rebuilt ZIPs and report')
    parser.add_argument('--dat', required=True, type=Path, help='XML DAT matching the exact FB Alpha core/version')
    parser.add_argument('--only', help='regular expression matching set name or description')
    parser.add_argument('--dry-run', action='store_true', help='write report without creating ZIPs')
    args = parser.parse_args(argv)
    inputs = [p.expanduser().resolve() for p in args.input]
    output = args.output.expanduser().resolve()
    dat = args.dat.expanduser().resolve()
    try:
        for root in inputs:
            if not root.is_dir():
                raise ValueError(f'input folder does not exist: {root}')
            if output == root or root in output.parents or output in root.parents:
                raise ValueError('--input and --output folders must not overlap')
        if output == dat.parent or output in dat.parents:
            raise ValueError('--dat must be outside the output folder')
        only = re.compile(args.only, re.IGNORECASE) if args.only else None
        report = convert(inputs, output, dat, only=only, dry_run=args.dry_run)
    except (OSError, ValueError, ET.ParseError, re.error) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1
    print(f"Complete: {len(report['complete'])}; incomplete: {len(report['incomplete'])}; "
          f"unsupported (CHD): {len(report['unsupported'])}; errors: {len(report['errors'])}")
    print(f"Report: {output / 'fbalpha-report.json'}")
    return 1 if report['errors'] or report['bad_input_zips'] else 2 if report['incomplete'] or report['unsupported'] else 0


if __name__ == '__main__':
    sys.exit(main())
