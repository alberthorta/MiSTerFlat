"""Read and write the saved OSD options of console and computer cores.

MiSTer Main keeps a core's options as a 128-bit status word and saves it, little-endian, in
/media/fat/config/<core name>.CFG (user_io.cpp). It loads that file when the core starts, so
a change here applies the next time the core loads. The option list per core comes from
cores.json, built by tools/build_core_catalog.py from each core's CONF_STR.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from typing import Dict, List, Optional

CATALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cores.json')
CORE_DIRS = ('_Console', '_Computer', '_Other')
STATUS_BYTES = 16
BACKUPS_KEPT = 20


class CoreOptionsError(Exception):
    pass


def load_catalog(path: str = CATALOG) -> Dict[str, dict]:
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def get_bits(status: int, lo: int, hi: int) -> int:
    return (status >> lo) & ((1 << (hi - lo + 1)) - 1)


def set_bits(status: int, lo: int, hi: int, value: int) -> int:
    mask = ((1 << (hi - lo + 1)) - 1) << lo
    return (status & ~mask) | ((value << lo) & mask)


class CoreOptions:
    def __init__(self, fat: str, state_dir: str, catalog: Optional[Dict[str, dict]] = None):
        self.fat = fat
        self.catalog = load_catalog() if catalog is None else catalog
        self.backup_dir = os.path.join(state_dir, 'backups', 'cores')

    def installed(self) -> List[dict]:
        found = set()
        for d in CORE_DIRS:
            try:
                names = os.listdir(os.path.join(self.fat, d))
            except OSError:
                continue
            for fn in names:
                m = re.fullmatch(r'(.+?)(?:_\d{8})?\.rbf', fn)
                if m:
                    found.add(m.group(1))
        return sorted(({'id': c, 'name': self.catalog[c]['name'], 'options': len(self.catalog[c]['options'])}
                       for c in found if c in self.catalog), key=lambda c: c['id'].lower())

    def _entry(self, core: str) -> dict:
        entry = self.catalog.get(core)
        if not entry or not re.fullmatch(r'[\w.-]+\.CFG', entry['cfg']):
            raise CoreOptionsError('unknown core')
        return entry

    def _path(self, entry: dict) -> str:
        return os.path.join(self.fat, 'config', entry['cfg'])

    def _status(self, entry: dict) -> int:
        try:
            with open(self._path(entry), 'rb') as f:
                return int.from_bytes(f.read(STATUS_BYTES).ljust(STATUS_BYTES, b'\0'), 'little')
        except OSError:
            return 0  # no saved settings: every option at its first value

    def get(self, core: str) -> dict:
        entry = self._entry(core)
        status = self._status(entry)
        options = []
        for i, opt in enumerate(entry['options']):
            lo, hi = opt['bits']
            options.append(dict(opt, id=i, value=get_bits(status, lo, hi)))
        try:
            with open('/tmp/CORENAME', encoding='utf-8') as f:
                running = f.read().strip() == entry['name']
        except OSError:
            running = False
        return {'id': core, 'name': entry['name'], 'cfg': entry['cfg'], 'saved': os.path.exists(self._path(entry)),
                'running': running, 'options': options}

    def set(self, core: str, values: Dict[str, int]) -> None:
        entry = self._entry(core)
        status = self._status(entry)
        for key, value in values.items():
            try:
                opt = entry['options'][int(key)]
                value = int(value)
            except (ValueError, IndexError, TypeError):
                raise CoreOptionsError('unknown option')
            if not 0 <= value < len(opt['values']):
                raise CoreOptionsError(f"{opt['label']}: value out of range")
            status = set_bits(status, opt['bits'][0], opt['bits'][1], value)
        path = self._path(entry)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            os.makedirs(self.backup_dir, exist_ok=True)
            shutil.copy2(path, os.path.join(self.backup_dir, entry['cfg'] + time.strftime('.%Y%m%d-%H%M%S')))
            old = sorted(f for f in os.listdir(self.backup_dir) if f.startswith(entry['cfg'] + '.'))
            for name in old[:-BACKUPS_KEPT]:
                os.remove(os.path.join(self.backup_dir, name))
        tmp = path + '.mm.tmp'
        with open(tmp, 'wb') as f:
            f.write(status.to_bytes(STATUS_BYTES, 'little'))
        os.replace(tmp, path)
