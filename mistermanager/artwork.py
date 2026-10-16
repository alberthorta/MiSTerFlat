"""Match games to the artwork update_all installs in /media/fat/docs/<system>/.

The Game Artwork DBs (chipster6502) use No-Intro names for consoles and the MAME set
name for arcade and Neo Geo. Games with older GoodTools names ("Addams Family (U) [!]")
fall back to a match on the bare title, preferring the region of the game.
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional

# Box art first; title and in-game screens when there is no box.
KINDS = ('Artwork', 'Titles', 'Screenshots')
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp')

# GoodTools region codes and the No-Intro words they stand for.
REGION_CODES = {'u': 'usa', 'e': 'europe', 'j': 'japan', 'ue': 'usa', 'ju': 'japan', 'w': 'world',
                'b': 'brazil', 'k': 'korea', 'a': 'australia', 'f': 'france', 'g': 'germany'}
DEFAULT_REGIONS = ('europe', 'world', 'usa', 'japan')


def normalize(name: str) -> str:
    """Bare title for loose matching: no tags, no leading/trailing "The", only letters and digits."""
    title = re.split(r'\s[\(\[]', name, 1)[0].lower()
    title = re.sub(r',\s*the$|^the\s+', '', title)
    title = re.sub(r'\s+32x$', '', title)  # GoodGen puts "32X" in the title of 32X games
    title = title.replace('&', 'and')
    return re.sub(r'[^a-z0-9]', '', title)


def regions(name: str) -> List[str]:
    words = []
    for tag in re.findall(r'\(([^)]*)\)', name):
        for part in re.split(r'[,\s]+', tag.lower()):
            if part in REGION_CODES:
                words.append(REGION_CODES[part])
            elif part in ('usa', 'europe', 'japan', 'world', 'brazil', 'korea', 'australia',
                          'spain', 'france', 'germany', 'italy'):
                words.append(part)
    return words


class ArtFolder:
    """Images of one docs/<system> folder, read once."""

    def __init__(self, docs_root: str, folder: str):
        self.exact: Dict[str, str] = {}
        self.loose: Dict[str, List[str]] = {}
        for kind in KINDS:
            path = os.path.join(docs_root, folder, kind)
            try:
                names = sorted(os.listdir(path))
            except OSError:
                continue
            for fn in names:
                base, ext = os.path.splitext(fn)
                if ext.lower() not in IMAGE_EXTS:
                    continue
                rel = '/'.join((folder, kind, fn))
                # setdefault keeps the first kind (box art) when several exist.
                self.exact.setdefault(base.lower(), rel)
                bases = self.loose.setdefault(normalize(base), [])
                if base not in bases:
                    bases.append(base)

    def find(self, name: str, key: Optional[str] = None) -> Optional[str]:
        for candidate in (key, name):
            if candidate and candidate.lower() in self.exact:
                return self.exact[candidate.lower()]
        bases = self.loose.get(normalize(name))
        if not bases:
            return None
        wanted = regions(name) or list(DEFAULT_REGIONS)
        for region in wanted + list(DEFAULT_REGIONS):
            for base in bases:
                if region in regions(base):
                    return self.exact[base.lower()]
        return self.exact[bases[0].lower()]


class ArtIndex:
    def __init__(self, fat: str):
        self.root = os.path.join(fat, 'docs')
        self._folders: Dict[str, ArtFolder] = {}

    def find(self, folder: str, name: str, key: Optional[str] = None) -> Optional[str]:
        if not folder:
            return None
        if folder not in self._folders:
            self._folders[folder] = ArtFolder(self.root, folder)
        return self._folders[folder].find(name, key)
