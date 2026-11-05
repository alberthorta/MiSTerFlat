"""Quick launch: the games of the Systems button on the MiSTerLily touch display.

For each system of the display's picker, a short list of games from the SD card, in the order the
user picks, each with a portrait cover. Everything lives in /media/fat/MiSTerLily/quick:

    games.json                    {"version": 1, "systems": {"SNES": [game, ...], ...}}
    <system>/<game id>.mgl        what the display's daemon loads ("load_core <mgl>")
    <system>/<game id>.jpg        the cover, at most 320 px on its long side, in the shape of the
                                  picture (the page makes it: SNES boxes are wide, Mega Drive ones tall)

A game is {"id", "name", "path" (relative to /media/fat), "mgl", "cover" (relative to the quick
folder, or null), "crc" (of the cover, 0 for none)}. The daemon (MiSTerLily mister/menu_systems.py)
only reads this folder. The system keys are the display's: its picture names, not our system ids.

Covers can also come from the libretro thumbnail server: the page asks for names that match the
game, then for the picture, and makes the cover from it like from an upload.
"""
from __future__ import annotations

import binascii
import json
import os
import re
import threading
import time
import urllib.request
from typing import Dict, List, Optional
from urllib.parse import quote, unquote

from .artwork import DEFAULT_REGIONS, IMAGE_EXTS, KINDS, normalize, regions
from .control import make_mgl
from .systems import BY_ID

# (key on the display, our system id), in the display's order. Keep in step with SYSTEMS in
# MiSTerLily's mister/menu_systems.py.
PICKER = (('GAMEBOY', 'Gameboy'), ('GBA', 'GBA'), ('NES', 'NES'), ('SMS', 'SMS'), ('SNES', 'SNES'),
          ('MegaDrive', 'MegaDrive'), ('PSX', 'PSX'))
BY_KEY = dict(PICKER)
MAX_GAMES = 20
MAX_COVER = 300 * 1024

LIBRETRO = 'https://thumbnails.libretro.com'
LIBRETRO_SYSTEMS = {
    'Gameboy': 'Nintendo - Game Boy',
    'GBA': 'Nintendo - Game Boy Advance',
    'NES': 'Nintendo - Nintendo Entertainment System',
    'SMS': 'Sega - Master System - Mark III',
    'SNES': 'Nintendo - Super Nintendo Entertainment System',
    'MegaDrive': 'Sega - Mega Drive - Genesis',
    'PSX': 'Sony - PlayStation',
}
LISTING_MAX_AGE = 30 * 86400
MAX_BOXART = 4 * 1024 * 1024
HREF = re.compile(r'href="([^"?/]+\.png)"')


class QuickError(Exception):
    pass


def short_name(name: str) -> str:
    """The title without tags: "Super Mario World (U) [!]" -> "Super Mario World"."""
    return re.split(r'\s[\(\[]', name, 1)[0].strip() or name


def words(name: str) -> set:
    """The words of a title, without tags: for a loose match between two ways of writing it."""
    title = re.split(r'\s[\(\[]', name, 1)[0].lower().replace('&', ' ').replace('+', ' ')
    return set(re.findall(r'[a-z0-9]+', title)) - {'the', 'and', 'of'}


def fetch(url: str, limit: int, timeout: float = 20) -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent': 'MiSTerManager'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise QuickError('download too large')
    return data


class QuickLaunch:
    def __init__(self, fat: str, library, state_dir: str, fetcher=fetch):
        self.fat = fat
        self.library = library
        self.root = os.path.join(fat, 'MiSTerLily', 'quick')
        self.file = os.path.join(self.root, 'games.json')
        self.listing_dir = os.path.join(state_dir, 'libretro')
        self.fetch = fetcher
        self.lock = threading.Lock()

    # ---- storage
    def _load(self) -> Dict[str, List[dict]]:
        try:
            with open(self.file, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {}
        systems = data.get('systems') if isinstance(data, dict) else None
        return systems if isinstance(systems, dict) else {}

    def _save(self, systems: Dict[str, List[dict]]) -> None:
        os.makedirs(self.root, exist_ok=True)
        tmp = self.file + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'version': 1, 'systems': systems}, f, indent=1)
        os.replace(tmp, self.file)

    def _key(self, key: str) -> str:
        if key not in BY_KEY:
            raise QuickError('unknown system')
        return key

    def _find(self, games: List[dict], game_id: str) -> dict:
        for g in games:
            if g.get('id') == game_id:
                return g
        raise QuickError('game not in the list')

    def installed(self, key: str) -> bool:
        prefix = os.path.basename(BY_ID[BY_KEY[key]].rbf)
        folder = os.path.join(self.fat, '_Console')
        pattern = re.compile(re.escape(prefix) + r'_\d{8}\.rbf', re.IGNORECASE)
        try:
            return any(pattern.fullmatch(n) for n in os.listdir(folder))
        except OSError:
            return False

    # ---- reading
    def summary(self) -> List[dict]:
        systems = self._load()
        return [{'id': key, 'system': sid, 'name': BY_ID[sid].name, 'installed': self.installed(key),
                 'count': len(systems.get(key, [])), 'max': MAX_GAMES} for key, sid in PICKER]

    def games(self, key: str) -> dict:
        key = self._key(key)
        sid = BY_KEY[key]
        out = []
        for g in self._load().get(key, []):
            game = self.library.find(sid, g.get('path', ''))
            out.append({'id': g['id'], 'name': g['name'], 'path': g['path'], 'crc': g.get('crc', 0),
                        'cover': bool(g.get('cover')), 'art': game.get('art') if game else None,
                        'missing': game is None})
        return {'id': key, 'system': sid, 'name': BY_ID[sid].name, 'max': MAX_GAMES, 'games': out}

    def sd_pictures(self, key: str, game_id: str) -> List[dict]:
        """The pictures update_all put on the SD card for this game: box, title screen, screenshot."""
        key = self._key(key)
        g = self._find(self._load().get(key, []), game_id)
        game = self.library.find(BY_KEY[key], g['path'])
        art = game.get('art') if game else None
        if not art:
            return []
        folder, _, rest = art.partition('/')
        base = os.path.splitext(rest.partition('/')[2])[0]
        labels = dict(zip(KINDS, ('Box', 'Title screen', 'Screenshot')))
        out = []
        for kind in KINDS:
            for ext in IMAGE_EXTS:
                rel = '/'.join((folder, kind, base + ext))
                if os.path.isfile(os.path.join(self.fat, 'docs', rel)):
                    out.append({'kind': labels[kind], 'art': rel})
                    break
        return out

    def cover(self, key: str, game_id: str) -> Optional[str]:
        g = self._find(self._load().get(self._key(key), []), game_id)
        return os.path.join(self.root, g['cover']) if g.get('cover') else None

    # ---- changes
    def add(self, key: str, path: str) -> dict:
        key = self._key(key)
        sid = BY_KEY[key]
        game = self.library.find(sid, path)
        if not game:
            raise QuickError('unknown game')
        with self.lock:
            systems = self._load()
            games = systems.setdefault(key, [])
            game_id = '{:08x}'.format(binascii.crc32(path.encode('utf-8')) & 0xFFFFFFFF)
            if any(g.get('id') == game_id for g in games):
                raise QuickError('this game is already in the list')
            if len(games) >= MAX_GAMES:
                raise QuickError('the list is full ({} games)'.format(MAX_GAMES))
            folder = os.path.join(self.root, key)
            os.makedirs(folder, exist_ok=True)
            mgl = os.path.join(folder, game_id + '.mgl')
            with open(mgl, 'w', encoding='utf-8') as f:
                f.write(make_mgl(sid, os.path.join(self.fat, path)))
            entry = {'id': game_id, 'name': short_name(game['name']), 'path': path, 'mgl': mgl,
                     'cover': None, 'crc': 0}
            games.append(entry)
            self._save(systems)
        return entry

    def remove(self, key: str, game_id: str) -> None:
        key = self._key(key)
        with self.lock:
            systems = self._load()
            games = systems.get(key, [])
            g = self._find(games, game_id)
            games.remove(g)
            for name in (game_id + '.mgl', g.get('cover') and os.path.basename(g['cover'])):
                if name:
                    try:
                        os.remove(os.path.join(self.root, key, name))
                    except OSError:
                        pass
            self._save(systems)

    def move(self, key: str, game_id: str, delta: int) -> None:
        key = self._key(key)
        with self.lock:
            systems = self._load()
            games = systems.get(key, [])
            i = games.index(self._find(games, game_id))
            j = max(0, min(len(games) - 1, i + int(delta)))
            games.insert(j, games.pop(i))
            self._save(systems)

    def set_cover(self, key: str, game_id: str, data: bytes) -> int:
        key = self._key(key)
        if not 0 < len(data) <= MAX_COVER:
            raise QuickError('picture is empty or too large')
        if data[:2] == b'\xff\xd8':
            ext = '.jpg'
        elif data[:4] == b'\x89PNG':
            ext = '.png'
        else:
            raise QuickError('send a JPEG or PNG picture')
        with self.lock:
            systems = self._load()
            g = self._find(systems.get(key, []), game_id)
            folder = os.path.join(self.root, key)
            os.makedirs(folder, exist_ok=True)
            for old in (game_id + '.jpg', game_id + '.png'):
                try:
                    os.remove(os.path.join(folder, old))
                except OSError:
                    pass
            with open(os.path.join(folder, game_id + ext), 'wb') as f:
                f.write(data)
            g['cover'] = key + '/' + game_id + ext
            g['crc'] = binascii.crc32(data) & 0xFFFFFFFF
            self._save(systems)
            return g['crc']

    def clear_cover(self, key: str, game_id: str) -> None:
        key = self._key(key)
        with self.lock:
            systems = self._load()
            g = self._find(systems.get(key, []), game_id)
            if g.get('cover'):
                try:
                    os.remove(os.path.join(self.root, g['cover']))
                except OSError:
                    pass
            g['cover'], g['crc'] = None, 0
            self._save(systems)

    # ---- libretro thumbnails
    def _listing(self, sid: str) -> List[str]:
        """Box art names of one system on the thumbnail server, cached for a month."""
        path = os.path.join(self.listing_dir, sid + '.txt')
        try:
            if time.time() - os.path.getmtime(path) < LISTING_MAX_AGE:
                with open(path, encoding='utf-8') as f:
                    return f.read().splitlines()
        except OSError:
            pass
        url = '{}/{}/Named_Boxarts/'.format(LIBRETRO, quote(LIBRETRO_SYSTEMS[sid]))
        try:
            html = self.fetch(url, 16 * 1024 * 1024).decode('utf-8', 'replace')
        except (OSError, ValueError) as e:
            raise QuickError('cannot reach the libretro thumbnail server: {}'.format(e))
        names = sorted({unquote(m)[:-4] for m in HREF.findall(html)})
        os.makedirs(self.listing_dir, exist_ok=True)
        with open(path + '.tmp', 'w', encoding='utf-8') as f:
            f.write('\n'.join(names))
        os.replace(path + '.tmp', path)
        return names

    def boxart_search(self, key: str, game_id: str, limit: int = 8) -> List[str]:
        key = self._key(key)
        sid = BY_KEY[key]
        g = self._find(self._load().get(key, []), game_id)
        names = self._listing(sid)
        title = os.path.splitext(os.path.basename(g['path']))[0]
        if title in names:
            return [title]
        want = normalize(title)
        order = regions(title) + [r for r in DEFAULT_REGIONS if r not in regions(title)]

        def rank(name):
            found = regions(name)
            return (min((order.index(r) for r in found if r in order), default=len(order)),
                    '(' in name and len(name), name)
        same = sorted((n for n in names if normalize(n) == want), key=rank)
        if not same and want:
            same = sorted((n for n in names if normalize(n).startswith(want)), key=rank)
        if not same:
            # Words in common, for names written another way ("All Stars & World" against
            # "All-Stars + Super Mario World").
            mine = words(title)
            scored = []
            for n in names:
                theirs = words(n)
                score = len(mine & theirs) / len(mine | theirs) if mine else 0
                if score >= 0.5:
                    scored.append((-score, rank(n), n))
            same = [n for _, _, n in sorted(scored)]
        return same[:limit]

    def boxart(self, key: str, name: str) -> bytes:
        sid = BY_KEY[self._key(key)]
        if name not in self._listing(sid):
            raise QuickError('no such picture')
        url = '{}/{}/Named_Boxarts/{}.png'.format(LIBRETRO, quote(LIBRETRO_SYSTEMS[sid]), quote(name))
        try:
            return self.fetch(url, MAX_BOXART)
        except (OSError, ValueError) as e:
            raise QuickError('download failed: {}'.format(e))
