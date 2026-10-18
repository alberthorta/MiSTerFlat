"""PlayStation memory cards: list, read, download and replace the PSX core's card files.

The PSX core keeps one card per game folder in /media/fat/saves/PSX/<folder>.sav, as a raw
128 KB card image (the .mcd/.mcr format). Uploads also take the two common wrapped formats:
DexDrive .gme (3904-byte header) and PSP/PS3 .vmp (128-byte header).
"""
from __future__ import annotations

import os
import re
import shutil
import time
import unicodedata
from typing import List, Optional

CARD_SIZE = 128 * 1024
BLOCK = 8192
FRAME = 128
WRAPPERS = {CARD_SIZE + 3904: 3904, CARD_SIZE + 0x80: 0x80}  # .gme, .vmp
BACKUPS_KEPT = 10


class CardError(Exception):
    pass


def unwrap(data: bytes) -> bytes:
    if len(data) in WRAPPERS:
        data = data[WRAPPERS[len(data)]:]
    if len(data) != CARD_SIZE or data[:2] != b'MC':
        raise CardError('not a PlayStation memory card (expected a 128 KB .mcd/.mcr/.sav, .gme or .vmp file)')
    return data


# Full-width Shift-JIS characters PlayStation save titles use for Latin text. MiSTer's Python
# is built without the CJK codecs, so these are decoded by hand when shift_jis is missing.
SJIS_PUNCT = {0x8140: ' ', 0x8143: ',', 0x8144: '.', 0x8146: ':', 0x8147: ';', 0x8148: '?', 0x8149: '!',
              0x815B: '-', 0x815C: '-', 0x815D: '-', 0x815E: '/', 0x8160: '~', 0x8166: "'", 0x8168: '"',
              0x8169: '(', 0x816A: ')', 0x816D: '[', 0x816E: ']', 0x817B: '+', 0x817C: '-', 0x8181: '=',
              0x8183: '<', 0x8184: '>', 0x8190: '$', 0x8193: '%', 0x8194: '#', 0x8195: '&', 0x8196: '*', 0x8197: '@'}


def _sjis_latin(raw: bytes) -> str:
    out, i = [], 0
    while i < len(raw):
        b = raw[i]
        if (0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEF) and i + 1 < len(raw):
            code = (b << 8) | raw[i + 1]
            i += 2
            if 0x824F <= code <= 0x8258:
                out.append(chr(ord('0') + code - 0x824F))
            elif 0x8260 <= code <= 0x8279:
                out.append(chr(ord('A') + code - 0x8260))
            elif 0x8281 <= code <= 0x829A:
                out.append(chr(ord('a') + code - 0x8281))
            else:
                out.append(SJIS_PUNCT.get(code, '\u00b7'))
        else:
            out.append(chr(b) if 0x20 <= b < 0x7F else '')
            i += 1
    return ''.join(out)


def _title(raw: bytes) -> str:
    raw = raw.split(b'\0', 1)[0]
    try:
        # NFKC turns full-width "ＦＩＮＡＬ" into "FINAL".
        text = unicodedata.normalize('NFKC', raw.decode('shift_jis', 'replace'))
    except LookupError:
        text = _sjis_latin(raw)
    return re.sub(r'\s+', ' ', text).strip()


def saves(card: bytes) -> List[dict]:
    """The saves on a card: directory frames 1-15, first block state 0x51."""
    out = []
    for slot in range(1, 16):
        entry = card[slot * FRAME:(slot + 1) * FRAME]
        if entry[0] != 0x51:
            continue
        size = int.from_bytes(entry[4:8], 'little')
        code = entry[10:30].split(b'\0', 1)[0].decode('ascii', 'replace')
        header = card[slot * BLOCK:slot * BLOCK + BLOCK]
        title = _title(header[4:68]) if header[:2] == b'SC' else ''
        out.append({'slot': slot, 'blocks': max(1, size // BLOCK), 'code': code, 'title': title})
    return out


class MemoryCards:
    def __init__(self, fat: str, state_dir: str):
        self.dir = os.path.join(fat, 'saves', 'PSX')
        self.backup_dir = os.path.join(state_dir, 'backups', 'memcards')

    def path(self, name: str) -> str:
        if not re.fullmatch(r'[^/\\\0]+\.sav', name) or name.startswith('.'):
            raise CardError('bad card name')
        return os.path.join(self.dir, name)

    def list(self, game_folders: List[str]) -> List[dict]:
        """Every card on the SD, plus one empty entry per PSX game folder without a card yet."""
        out, seen = [], set()
        try:
            files = sorted(f for f in os.listdir(self.dir) if f.lower().endswith('.sav'))
        except OSError:
            files = []
        for fn in files:
            full = os.path.join(self.dir, fn)
            try:
                with open(full, 'rb') as f:
                    data = f.read()
                card_saves = saves(unwrap(data))
                error = ''
            except (OSError, CardError) as e:
                card_saves, error = [], str(e)
            st = os.stat(full)
            out.append({'file': fn, 'game': fn[:-4], 'exists': True, 'size': st.st_size,
                        'modified': int(st.st_mtime), 'saves': card_saves, 'error': error})
            seen.add(fn[:-4].lower())
        for folder in sorted(set(game_folders)):
            if folder.lower() not in seen:
                out.append({'file': folder + '.sav', 'game': folder, 'exists': False, 'saves': []})
        out.sort(key=lambda c: c['game'].lower())
        return out

    def read(self, name: str) -> bytes:
        try:
            with open(self.path(name), 'rb') as f:
                return f.read()
        except FileNotFoundError:
            raise CardError('card not found')

    def write(self, name: str, data: bytes) -> List[dict]:
        card = unwrap(data)
        path = self.path(name)
        os.makedirs(self.dir, exist_ok=True)
        if os.path.exists(path):
            os.makedirs(self.backup_dir, exist_ok=True)
            shutil.copy2(path, os.path.join(self.backup_dir, name + time.strftime('.%Y%m%d-%H%M%S')))
            old = sorted(f for f in os.listdir(self.backup_dir) if f.startswith(name + '.'))
            for f in old[:-BACKUPS_KEPT]:
                os.remove(os.path.join(self.backup_dir, f))
        tmp = path + '.mm.tmp'
        with open(tmp, 'wb') as f:
            f.write(card)
        os.replace(tmp, path)
        return saves(card)


def psx_game_folders(index: dict) -> List[str]:
    """Card names the core will use: the folder that holds each PSX game (its parent dir)."""
    games = index.get('systems', {}).get('PSX', {}).get('games', [])
    folders = []
    for g in games:
        parent = os.path.basename(os.path.dirname(g['path']))
        if parent and parent != 'PSX' and not g.get('alt'):
            folders.append(parent)
    return folders
