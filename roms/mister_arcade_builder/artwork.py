"""MDK game information and screenshots for the offline HTML report."""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path

log = logging.getLogger(__name__)
BASE = 'https://mdk.cab'
SAFE_SET = re.compile(r'[a-zA-Z0-9_-]+\Z')
CATEGORIES = {'titles': 'Title', 'snap': 'In-game', 'howto': 'How to play',
              'select': 'Select', 'versus': 'Versus', 'gameover': 'Game over',
              'scores': 'High scores', 'warning': 'Warning', 'bosses': 'Bosses',
              'ends': 'Ending', 'marquees': 'Marquee', 'flyers': 'Flyer',
              'cabinets': 'Cabinet', 'cpanel': 'Control panel'}


class GamePage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.info = {}
        self.images = []
        self.cells = []
        self.cell = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'tr':
            self.cells = []
        elif tag in ('td', 'th'):
            self.cell = []
        elif tag == 'img':
            url = urllib.parse.urljoin(BASE, attrs.get('src', ''))
            parsed = urllib.parse.urlparse(url)
            parts = parsed.path.strip('/').split('/')
            if (parsed.scheme == 'https' and parsed.netloc == 'mdk.cab' and
                    len(parts) == 3 and parts[0] == 'img' and parts[1] in CATEGORIES):
                item = {'url': url, 'label': CATEGORIES[parts[1]]}
                if item not in self.images:
                    self.images.append(item)

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.cells.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and len(self.cells) >= 2:
            key = self.cells[0].strip().lower().rstrip(':')
            if key in ('year', 'genre', 'manufacturer'):
                self.info[key] = self.cells[1]


def fetch(url: str, limit: int) -> bytes:
    request = urllib.request.Request(url, headers={'User-Agent': 'mister-arcade-builder'})
    with urllib.request.urlopen(request, timeout=20) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('response exceeds size limit')
    return data


def image_extension(data: bytes) -> str:
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    if data.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    if data.startswith((b'GIF87a', b'GIF89a')):
        return '.gif'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP':
        return '.webp'
    raise ValueError('response is not a supported image')


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def enrich_report(rep: dict, cache: Path, output: Path, offline: bool = False,
                  dry_run: bool = False, jobs: int = 4) -> None:
    """Fetch once per set; copy cached images beside the portable report."""
    sets = {m['setname'].lower() for status in ('complete', 'partial', 'missing', 'only_shared', 'no_roms')
            for m in rep.get(status, []) if SAFE_SET.fullmatch(m['setname'])}
    folder = cache / 'artwork' / 'mdk'

    def collect(setname):
        name = setname.lower()
        record = folder / name / 'info.json'
        result = {'source': BASE + '/game/' + name, 'images': []}
        try:
            if record.exists():
                page = json.loads(record.read_text(encoding='utf-8'))
            elif offline or dry_run:
                return setname, result
            else:
                parser = GamePage()
                parser.feed(fetch(result['source'], 2 * 1024 * 1024).decode('utf-8', errors='replace'))
                page = dict(parser.info, images=parser.images)
                atomic_write(record, json.dumps(page).encode('utf-8'))
            result.update({k: page[k] for k in ('year', 'genre', 'manufacturer') if k in page})
            for i, item in enumerate(page.get('images', [])[:16]):
                try:
                    url = item['url']
                    parsed = urllib.parse.urlparse(url)
                    if parsed.scheme != 'https' or parsed.netloc != 'mdk.cab' or not parsed.path.startswith('/img/'):
                        continue
                    cached = folder / name / f'image-{i}'
                    if cached.exists():
                        data = cached.read_bytes()
                    elif offline or dry_run:
                        continue
                    else:
                        data = fetch(url, 8 * 1024 * 1024)
                        image_extension(data)
                        atomic_write(cached, data)
                    ext = image_extension(data)
                    relative = f'mister-arcade-assets/{name}/{i}{ext}'
                    atomic_write(output / relative, data)
                    result['images'].append({'path': relative, 'label': item['label']})
                except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
                    log.debug('MDK image unavailable for %s: %s', name, exc)
        except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
            log.debug('MDK information unavailable for %s: %s', name, exc)
        return setname, result

    log.info('loading MDK artwork and information for %d sets', len(sets))
    with ThreadPoolExecutor(max_workers=max(1, min(jobs, 4))) as pool:
        rep['artwork'] = dict(pool.map(collect, sorted(sets)))
    log.info('MDK images available for %d sets',
             sum(bool(v['images']) for v in rep['artwork'].values()))
