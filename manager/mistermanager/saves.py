"""Game saves and save states of every core: list, download, replace and delete.

MiSTer Main keeps them per core name (the CONF_STR name, the same as /tmp/CORENAME):
/media/fat/saves/<core>/<game>.sav (or .sra, .eep, ... for N64) and
/media/fat/savestates/<core>/<game>_<slot>.ss. It makes the saves folder the first time a core
loads, so a folder there is how we know a core keeps saves.

Every replace and delete copies the old file to the backup folder first. PlayStation memory
cards have their own module (memcards.py) for the card contents and the wrapped formats; delete
goes through here like for any other core.
"""
from __future__ import annotations

import os
import re
import shutil
import time
from typing import Dict, List, Optional

KINDS = {'saves': 'saves', 'states': 'savestates'}
MAX_SAVE = 16 * 1024 * 1024
BACKUPS_KEPT = 10
STATE_RE = re.compile(r'(.+)_(\d+)\.ss', re.IGNORECASE)


class SaveError(Exception):
    pass


def running_core() -> str:
    try:
        with open('/tmp/CORENAME', encoding='utf-8') as f:
            return f.read().strip()
    except OSError:
        return ''


class Saves:
    def __init__(self, fat: str, state_dir: str):
        self.fat = fat
        self.backup_dir = os.path.join(state_dir, 'backups', 'saves')

    def _root(self, kind: str) -> str:
        if kind not in KINDS:
            raise SaveError('unknown kind')
        return os.path.join(self.fat, KINDS[kind])

    def folders(self) -> Dict[str, Dict[str, int]]:
        """{core folder: {'saves': n, 'states': n}} for every folder in saves/ and savestates/."""
        out: Dict[str, Dict[str, int]] = {}
        for kind in KINDS:
            root = self._root(kind)
            try:
                names = os.listdir(root)
            except OSError:
                continue
            for name in names:
                if name.startswith('.') or not os.path.isdir(os.path.join(root, name)):
                    continue
                counts = out.setdefault(name, {'saves': 0, 'states': 0})
                counts[kind] = len(self._files(kind, name))
        return out

    def _dir(self, kind: str, core: str) -> str:
        root = self._root(kind)
        # Only a folder that is really there: the name never builds a path by itself.
        try:
            if core and not core.startswith('.') and core in os.listdir(root):
                return os.path.join(root, core)
        except OSError:
            pass
        raise SaveError('no saves for this core')

    def _files(self, kind: str, core: str) -> List[str]:
        try:
            d = self._dir(kind, core)
            names = os.listdir(d)
        except (SaveError, OSError):
            return []
        keep = []
        for n in names:
            if n.startswith('.') or n.endswith('.mm.tmp') or not os.path.isfile(os.path.join(d, n)):
                continue
            if kind == 'states' and not n.lower().endswith('.ss'):
                continue  # thumbnails and other files the core keeps next to the states
            keep.append(n)
        return keep

    def list(self, core: str) -> dict:
        out = {'core': core, 'running': running_core() == core, 'saves': [], 'states': []}
        found = False
        for kind in KINDS:
            try:
                d = self._dir(kind, core)
                found = True
            except SaveError:
                continue
            for n in self._files(kind, core):
                st = os.stat(os.path.join(d, n))
                item = {'file': n, 'game': os.path.splitext(n)[0], 'size': st.st_size, 'modified': int(st.st_mtime)}
                if kind == 'states':
                    m = STATE_RE.fullmatch(n)
                    if m:
                        item.update(game=m.group(1), slot=int(m.group(2)))
                out[kind].append(item)
            out[kind].sort(key=lambda i: (i['game'].lower(), i.get('slot', 0)))
        if not found:
            raise SaveError('no saves for this core')
        return out

    def path(self, kind: str, core: str, name: str) -> str:
        if name not in self._files(kind, core):
            raise SaveError('save not found')
        return os.path.join(self._dir(kind, core), name)

    def read(self, kind: str, core: str, name: str) -> bytes:
        with open(self.path(kind, core, name), 'rb') as f:
            return f.read()

    def _backup(self, kind: str, core: str, path: str) -> None:
        dest = os.path.join(self.backup_dir, kind, core)
        os.makedirs(dest, exist_ok=True)
        name = os.path.basename(path)
        shutil.copy2(path, os.path.join(dest, name + time.strftime('.%Y%m%d-%H%M%S')))
        old = sorted(f for f in os.listdir(dest) if f.startswith(name + '.'))
        for f in old[:-BACKUPS_KEPT]:
            os.remove(os.path.join(dest, f))

    def replace(self, core: str, name: str, data: bytes) -> None:
        """A game save only: a save state is a memory dump of one core build, not a file to bring in."""
        if not 0 < len(data) <= MAX_SAVE:
            raise SaveError('file is empty or too large')
        path = self.path('saves', core, name)
        self._backup('saves', core, path)
        tmp = path + '.mm.tmp'
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, path)

    def delete(self, kind: str, core: str, name: str) -> None:
        path = self.path(kind, core, name)
        self._backup(kind, core, path)
        os.remove(path)


def merge_cores(installed: List[dict], folders: Dict[str, Dict[str, int]]) -> List[dict]:
    """The cores list with save counts. A core folder with saves but without OSD options in the
    catalog (CD-i, NEOGEO) is added as a core of its own, so its saves can be reached."""
    out = []
    by_folder = {f.lower(): f for f in folders}
    used = set()
    for c in installed:
        folder = by_folder.get(c['name'].lower())
        counts = folders.get(folder, {}) if folder else {}
        if folder:
            used.add(folder)
        out.append(dict(c, folder=folder, saves=counts.get('saves', 0), states=counts.get('states', 0)))
    for folder, counts in folders.items():
        if folder not in used and (counts['saves'] or counts['states']):
            out.append({'id': folder, 'name': folder, 'options': 0, 'folder': folder,
                        'saves': counts['saves'], 'states': counts['states']})
    out.sort(key=lambda c: c['id'].lower())
    return out
