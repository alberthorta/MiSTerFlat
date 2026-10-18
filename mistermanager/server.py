"""HTTP server: a JSON API plus one static page."""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

from .artwork import IMAGE_EXTS
from .coreopts import CoreOptions, CoreOptionsError
from .control import Controller, LaunchError, Stats, current
from .library import Library
from .memcards import CARD_SIZE, CardError, MemoryCards, psx_game_folders
from .motion import DEVICES, MotionBlocker, controllers
from .settings import Settings, SettingsError

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
MAX_BODY = 64 * 1024


class App:
    def __init__(self, fat: str, state_dir: str, fifo: str):
        os.makedirs(state_dir, exist_ok=True)
        self.fat = fat
        self.library = Library(fat, os.path.join(state_dir, 'index.json'))
        self.controller = Controller(fat, state_dir, fifo=fifo)
        self.stats = Stats()
        self.settings = Settings(fat, state_dir, fifo)
        self.cores = CoreOptions(fat, state_dir)
        self.cards = MemoryCards(fat, state_dir)
        self.motion = MotionBlocker(os.path.join(state_dir, 'controllers.json'))


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'MiSTerManager'

        def log_message(self, fmt, *args):
            pass

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, code: int = 200):
            self._send(code, json.dumps(data).encode('utf-8'), 'application/json')

        def do_GET(self):
            url = urlparse(self.path)
            q = {k: v[-1] for k, v in parse_qs(url.query).items()}
            if url.path == '/api/status':
                self._json({'now': current(app.fat, app.controller.last_launch),
                            'system': app.stats.snapshot(app.fat),
                            'scanning': app.library.scanning,
                            'motion_blocked': app.motion.status(),
                            'indexed': app.library.index['built']})
            elif url.path == '/api/systems':
                self._json(app.library.summary())
            elif url.path == '/api/games':
                self._json(app.library.games(q.get('system', ''), q.get('q', ''),
                                             alternatives=q.get('alt') == '1'))
            elif url.path == '/api/recent':
                self._json(app.controller.recent())
            elif url.path == '/api/settings':
                self._json({'volume': app.settings.volume(), 'ini': app.settings.ini(),
                            'custom': app.settings.custom_presets()})
            elif url.path == '/api/controllers':
                try:
                    with open(DEVICES, encoding='utf-8', errors='replace') as f:
                        devices = controllers(f.read())
                except OSError:
                    devices = []
                blocked = set(app.motion.status())
                for d in devices:
                    d['ignored'] = d['address'].lower() in app.motion.ignored
                    for part in d['parts']:
                        part['blocked'] = part['node'] in blocked
                seen = {d['address'].lower() for d in devices}
                for address, name in sorted(app.motion.ignored.items()):
                    if address not in seen:
                        devices.append({'name': name or address, 'bus': '', 'id': '', 'address': address,
                                        'parts': [], 'ignored': True, 'offline': True})
                self._json({'devices': devices, 'block_motion_sensors': app.motion.enabled})
            elif url.path == '/api/psx/cards':
                try:
                    with open('/tmp/CORENAME', encoding='utf-8') as f:
                        running = f.read().strip() == 'PSX'
                except OSError:
                    running = False
                self._json({'cards': app.cards.list(psx_game_folders(app.library.index)), 'psx_running': running})
            elif url.path == '/api/psx/cards/download':
                try:
                    name = q.get('file', '')
                    data = app.cards.read(name)
                except CardError as e:
                    return self._json({'error': str(e)}, 404)
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Length', str(len(data)))
                # .mcd is the name most PC tools (MemcardRex, emulators) expect for this format.
                quoted = quote(name[:-4] + '.mcd')
                self.send_header('Content-Disposition', f"attachment; filename*=UTF-8''{quoted}")
                self.end_headers()
                self.wfile.write(data)
            elif url.path == '/api/cores':
                self._json(app.cores.installed())
            elif url.path == '/api/cores/options':
                try:
                    self._json(app.cores.get(q.get('core', '')))
                except CoreOptionsError as e:
                    self._json({'error': str(e)}, 404)
            elif url.path == '/api/settings/options':
                self._json(app.settings.options())
            elif url.path.startswith('/art/'):
                name = unquote(url.path[len('/art/'):])
                if os.path.splitext(name)[1].lower() not in IMAGE_EXTS:
                    return self._send(404, b'not found', 'text/plain')
                self._file(os.path.join(app.fat, 'docs'), name, cache=True)
            else:
                name = 'index.html' if url.path in ('', '/') else url.path.lstrip('/')
                self._file(STATIC, name)

        def do_POST(self):
            url = urlparse(self.path)
            length = int(self.headers.get('Content-Length') or 0)
            if url.path == '/api/psx/cards/upload':
                return self._upload_card(url, length)
            if length > MAX_BODY:
                return self._json({'error': 'body too large'}, 413)
            try:
                body = json.loads(self.rfile.read(length) or b'{}')
            except ValueError:
                return self._json({'error': 'bad json'}, 400)
            try:
                if url.path == '/api/launch':
                    game = app.library.find(str(body.get('system', '')), str(body.get('path', '')))
                    if not game:
                        return self._json({'error': 'unknown game'}, 404)
                    app.controller.launch(body['system'], game)
                    self._json({'ok': True})
                elif url.path == '/api/menu':
                    app.controller.menu()
                    self._json({'ok': True})
                elif url.path == '/api/rescan':
                    app.library.rescan_async()
                    self._json({'ok': True})
                elif url.path == '/api/settings/volume':
                    app.settings.set_volume(body.get('level'), body.get('mute'))
                    self._json({'ok': True})
                elif url.path == '/api/settings/ini':
                    app.settings.set_ini(str(body.get('section', '')), str(body.get('key', '')),
                                         str(body.get('value', '')))
                    self._json({'ok': True})
                elif url.path == '/api/settings/preset':
                    app.settings.write_preset(str(body.get('name', '')), body.get('fields') or {})
                    self._json({'ok': True})
                elif url.path == '/api/cores/options':
                    app.cores.set(str(body.get('core', '')), body.get('values') or {})
                    self._json({'ok': True})
                elif url.path == '/api/controllers/ignore':
                    app.motion.set_ignored(str(body.get('address', '')), str(body.get('name', '')),
                                           bool(body.get('ignore')))
                    self._json({'ok': True})
                elif url.path == '/api/controllers/motion':
                    app.motion.set_enabled(bool(body.get('enabled')))
                    self._json({'ok': True})
                elif url.path == '/api/reboot':
                    self._json({'ok': True})
                    # Answer first; the reboot takes the server down with it.
                    threading.Timer(1.0, lambda: subprocess.run(['reboot'])).start()
                else:
                    self._json({'error': 'not found'}, 404)
            except (LaunchError, SettingsError, CoreOptionsError, OSError, ValueError) as e:
                self._json({'error': str(e)}, 409)

        def _upload_card(self, url, length: int):
            if not 0 < length <= CARD_SIZE + 4096:
                return self._json({'error': 'file too large or empty'}, 413)
            name = {k: v[-1] for k, v in parse_qs(url.query).items()}.get('file', '')
            data = self.rfile.read(length)
            try:
                card_saves = app.cards.write(name, data)
            except (CardError, OSError) as e:
                return self._json({'error': str(e)}, 409)
            self._json({'ok': True, 'saves': card_saves})

        def _file(self, root: str, name: str, cache: bool = False):
            full = os.path.realpath(os.path.join(root, name))
            if not full.startswith(os.path.realpath(root) + os.sep) or not os.path.isfile(full):
                return self._send(404, b'not found', 'text/plain')
            with open(full, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', mimetypes.guess_type(full)[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(len(data)))
            # Artwork only changes with update_all; the page itself must not be cached.
            self.send_header('Cache-Control', 'max-age=86400' if cache else 'no-store')
            self.end_headers()
            self.wfile.write(data)

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description='Web page to see and drive a MiSTer.')
    parser.add_argument('--port', type=int, default=int(os.environ.get('MM_PORT', 80)))
    parser.add_argument('--bind', default='0.0.0.0')
    parser.add_argument('--fat', default=os.environ.get('MM_FAT', '/media/fat'))
    parser.add_argument('--state', default=None, help='folder for index.json and recent.json')
    parser.add_argument('--fifo', default='/dev/MiSTer_cmd')
    args = parser.parse_args(argv)
    state = args.state or os.path.join(args.fat, 'MiSTerManager')
    app = App(args.fat, state, args.fifo)
    # The cached index answers at once; the rescan picks up games copied since the last run.
    app.library.load_cache()
    app.library.rescan_async()
    app.motion.start()
    server = ThreadingHTTPServer((args.bind, args.port), make_handler(app))
    print(f'MiSTerManager on http://{args.bind}:{args.port}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
