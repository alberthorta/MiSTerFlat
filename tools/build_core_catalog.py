#!/usr/bin/env python3
"""Build mistermanager/cores.json: the OSD options of MiSTer cores, read from their source.

A core's option list (CONF_STR) is compiled into the .rbf and cannot be read on the MiSTer,
so this script reads it from the MiSTer-devel repositories on GitHub. Run it on a computer
with the GitHub CLI (`gh`) logged in:

    python3 tools/build_core_catalog.py NES SNES MegaDrive ...   # or --from-mister root@host
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'mistermanager' / 'cores.json'
# Core names whose repository is not "<name>_MiSTer".
REPOS = {
    'GameboyColor': 'Gameboy_MiSTer', 'Gameboy2P': 'Gameboy_MiSTer', 'GBA2P': 'GBA_MiSTer',
    'AtariLynx2P': 'AtariLynx_MiSTer', 'GameGear2P': 'SMS_MiSTer', 'ZX-Spectrum': 'ZX-Spectrum_MISTer',
    'CDi': 'CDi_MiSTer', 'TurboGrafx16': 'TurboGrafx16_MiSTer', 'NeoGeo': 'NeoGeo_MiSTer',
}
# Main loads these cores' settings its own way (tos_config / minimig config), not from <name>.CFG.
SKIP = {'AtariST', 'Minimig'}
BIT_CHARS = '0123456789ABCDEFGHIJKLMNOPQRSTUV'


def gh(*args: str) -> str:
    return subprocess.run(['gh', *args], check=True, capture_output=True, text=True).stdout


def fetch(repo: str, path: str) -> str:
    data = json.loads(gh('api', f'repos/MiSTer-devel/{repo}/contents/{path}'))
    return base64.b64decode(data['content']).decode('utf-8', 'replace')


def find_conf_str(repo: str) -> str:
    tree = json.loads(gh('api', f'repos/MiSTer-devel/{repo}/git/trees/HEAD'))
    candidates = [t['path'] for t in tree['tree'] if t['path'].endswith(('.sv', '.v'))]
    for path in candidates:
        text = fetch(repo, path)
        m = re.search(r'CONF_STR\s*=\s*\{(.*?)\}\s*;', text, re.S)
        if m:
            body = re.sub(r'//[^\n]*', '', m.group(1))
            return ''.join(re.findall(r'"((?:[^"\\]|\\.)*)"', body))
    raise LookupError('no CONF_STR')


def bit_range(code: str):
    """'O1' -> (1, 1), 'OAB' -> (10, 11), 'o9A' -> (41, 42), 'O[16:15]' -> (15, 16)."""
    m = re.fullmatch(r'([Oo])\[(\d+)(?::(\d+))?\]', code)
    if m:
        hi, lo = int(m.group(2)), int(m.group(3) if m.group(3) else m.group(2))
        return min(lo, hi), max(lo, hi)
    m = re.fullmatch(r'([Oo])([0-9A-V])([0-9A-V])?', code)
    if not m:
        return None
    base = 32 if m.group(1) == 'o' else 0
    lo = BIT_CHARS.index(m.group(2)) + base
    hi = BIT_CHARS.index(m.group(3)) + base if m.group(3) else lo
    return lo, hi


def parse(conf: str) -> dict:
    items = [i for i in conf.split(';')]
    name = items[0]
    version = ''
    pages = {}
    options = []
    for item in items[1:]:
        if not item:
            continue
        if re.match(r'^v,\d+', item):
            version = f"_v{int(item.split(',')[1])}" if int(item.split(',')[1]) else ''
            continue
        rest = item
        page = 0
        # Prefixes: Hn/hn/Dn/dn (hide/disable conditions) and Pn (sub-page), in any order.
        while True:
            m = re.match(r'^([HhDd])([0-9A-Z])', rest) or re.match(r'^(P)(\d+)(?=[Oo\[])', rest)
            if not m:
                break
            if m.group(1) == 'P':
                page = int(m.group(2))
            rest = rest[m.end():]
        m = re.match(r'^P(\d+),(.*)$', rest)
        if m:
            pages[int(m.group(1))] = m.group(2)
            continue
        parts = rest.split(',')
        rng = bit_range(parts[0])
        if not rng or len(parts) < 3:
            continue
        values = [v for v in parts[2:]]
        options.append({'label': parts[1], 'bits': list(rng), 'values': values, 'page': page})
    for opt in options:
        opt['page'] = pages.get(opt['page'], '') if opt['page'] else ''
    return {'name': name, 'cfg': f'{name}{version}.CFG', 'options': options}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('cores', nargs='*', help='rbf names without the date, e.g. NES SNES NeoGeo')
    ap.add_argument('--from-mister', help='ssh target; take the core names from its _Console, _Computer and _Other')
    args = ap.parse_args(argv)
    names = list(args.cores)
    if args.from_mister:
        out = subprocess.run(['ssh', '-o', 'BatchMode=yes', args.from_mister,
                              'cd /media/fat && ls _Console _Computer _Other'], check=True,
                             capture_output=True, text=True).stdout
        names += sorted({re.sub(r'_\d{8}\.rbf$', '', f) for f in out.split() if f.endswith('.rbf')})
    catalog = json.loads(OUT.read_text()) if OUT.exists() else {}
    for core in names:
        if core in SKIP:
            continue
        repo = REPOS.get(core, f'{core}_MiSTer')
        try:
            entry = parse(find_conf_str(repo))
        except (subprocess.CalledProcessError, LookupError, ValueError) as e:
            print(f'skip {core} ({repo}): {e}', file=sys.stderr)
            continue
        entry['repo'] = repo
        catalog[core] = entry
        print(f"{core}: {entry['cfg']}, {len(entry['options'])} options")
    OUT.write_text(json.dumps(catalog, indent=1, sort_keys=True) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
