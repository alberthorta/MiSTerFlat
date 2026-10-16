"""Game index: walks the SD card once and keeps the result in memory and on disk."""
from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Dict, List, Optional

from .systems import ARCADE_ID, NEOGEO, NEOGEO_ID, SYSTEMS, System

INDEX_VERSION = 1


def _walk(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith('.'))
        for fn in sorted(filenames):
            if not fn.startswith('.'):
                yield dirpath, fn


def _title(filename: str) -> str:
    return os.path.splitext(filename)[0]


def scan_system(fat: str, system: System) -> List[dict]:
    root = os.path.join(fat, 'games', system.folder)
    if system.subfolder:
        root = os.path.join(root, system.subfolder)
    if not os.path.isdir(root):
        return []
    games = []
    for dirpath, fn in _walk(root):
        rel = os.path.relpath(os.path.join(dirpath, fn), fat)
        if system.exclude and rel.startswith(os.path.join('games', system.folder, system.exclude) + os.sep):
            continue
        if os.path.splitext(fn)[1].lower() in system.extensions:
            games.append({'name': _title(fn), 'path': rel})
    return games


def scan_arcade(fat: str) -> List[dict]:
    root = os.path.join(fat, '_Arcade')
    if not os.path.isdir(root):
        return []
    games = []
    for dirpath, fn in _walk(root):
        if not fn.lower().endswith('.mra'):
            continue
        rel = os.path.relpath(os.path.join(dirpath, fn), fat)
        parts = rel.split(os.sep)
        # _Arcade/cores holds the .rbf files; _Arcade/_alternatives/_Game/ holds other versions.
        if 'cores' in parts[1:2]:
            continue
        alt = '_alternatives' in parts
        games.append({'name': _title(fn), 'path': rel, 'alt': alt})
    return games


def neogeo_names(fat: str) -> Dict[str, str]:
    """Set name -> title from games/NEOGEO/romsets.xml (comments ignored)."""
    path = os.path.join(fat, 'games', NEOGEO.folder, 'romsets.xml')
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            text = f.read()
    except OSError:
        return {}
    text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    names = {}
    for tag in re.findall(r'<romset\b[^>]*>', text):
        name = re.search(r'\bname="([^"]+)"', tag)
        alt = re.search(r'\baltname="([^"]+)"', tag)
        if name:
            for one in name.group(1).split(','):
                names[one.strip()] = alt.group(1) if alt else one.strip()
    return names


def scan_neogeo(fat: str) -> List[dict]:
    root = os.path.join(fat, 'games', NEOGEO.folder)
    if not os.path.isdir(root):
        return []
    names = neogeo_names(fat)
    games = []
    for entry in sorted(os.listdir(root)):
        full = os.path.join(root, entry)
        rel = os.path.relpath(full, fat)
        if os.path.isdir(full) and entry in names:
            games.append({'name': names[entry], 'path': rel})
        elif os.path.isfile(full) and entry.lower().endswith('.neo'):
            games.append({'name': _title(entry), 'path': rel})
    return games


def build_index(fat: str) -> dict:
    systems = {}
    for system in SYSTEMS:
        games = scan_system(fat, system)
        if games:
            systems[system.id] = {'name': system.name, 'games': games}
    neo = scan_neogeo(fat)
    if neo:
        systems[NEOGEO_ID] = {'name': NEOGEO.name, 'games': neo}
    arcade = scan_arcade(fat)
    if arcade:
        systems[ARCADE_ID] = {'name': 'Arcade', 'games': arcade}
    for entry in systems.values():
        entry['games'].sort(key=lambda g: (g.get('alt', False), g['name'].lower()))
    return {'version': INDEX_VERSION, 'built': int(time.time()), 'systems': systems}


class Library:
    def __init__(self, fat: str, cache_path: str):
        self.fat = fat
        self.cache_path = cache_path
        self._index: Optional[dict] = None
        self._lock = threading.Lock()
        self.scanning = False

    def load_cache(self) -> bool:
        try:
            with open(self.cache_path, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            return False
        if data.get('version') != INDEX_VERSION:
            return False
        self._index = data
        return True

    def rescan(self) -> None:
        with self._lock:
            if self.scanning:
                return
            self.scanning = True
        try:
            index = build_index(self.fat)
            self._index = index
            tmp = self.cache_path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(index, f)
            os.replace(tmp, self.cache_path)
        finally:
            self.scanning = False

    def rescan_async(self) -> None:
        threading.Thread(target=self.rescan, daemon=True).start()

    @property
    def index(self) -> dict:
        return self._index or {'version': INDEX_VERSION, 'built': 0, 'systems': {}}

    def summary(self) -> List[dict]:
        out = [{'id': sid, 'name': s['name'], 'count': len(s['games'])}
               for sid, s in self.index['systems'].items()]
        out.sort(key=lambda s: (s['id'] != ARCADE_ID, s['name'].lower()))
        return out

    def games(self, system_id: str, query: str = '', alternatives: bool = False,
              limit: int = 500) -> List[dict]:
        system = self.index['systems'].get(system_id)
        if not system:
            return []
        words = query.lower().split()
        out = []
        for game in system['games']:
            if game.get('alt') and not alternatives:
                continue
            name = game['name'].lower()
            if all(w in name for w in words):
                out.append(game)
                if len(out) >= limit:
                    break
        return out

    def find(self, system_id: str, path: str) -> Optional[dict]:
        system = self.index['systems'].get(system_id)
        if not system:
            return None
        return next((g for g in system['games'] if g['path'] == path), None)
