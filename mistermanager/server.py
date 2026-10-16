"""HTTP server: a JSON API plus one static page."""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .control import Controller, LaunchError, Stats, current
from .library import Library

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
MAX_BODY = 64 * 1024


class App:
    def __init__(self, fat: str, state_dir: str, fifo: str):
        os.makedirs(state_dir, exist_ok=True)
        self.fat = fat
        self.library = Library(fat, os.path.join(state_dir, 'index.json'))
        self.controller = Controller(fat, state_dir, fifo=fifo)
        self.stats = Stats()


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
                            'indexed': app.library.index['built']})
            elif url.path == '/api/systems':
                self._json(app.library.summary())
            elif url.path == '/api/games':
                self._json(app.library.games(q.get('system', ''), q.get('q', ''),
                                             alternatives=q.get('alt') == '1'))
            elif url.path == '/api/recent':
                self._json(app.controller.recent())
            else:
                self._static(url.path)

        def do_POST(self):
            url = urlparse(self.path)
            length = int(self.headers.get('Content-Length') or 0)
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
                else:
                    self._json({'error': 'not found'}, 404)
            except LaunchError as e:
                self._json({'error': str(e)}, 409)

        def _static(self, path: str):
            name = 'index.html' if path in ('', '/') else path.lstrip('/')
            full = os.path.realpath(os.path.join(STATIC, name))
            if not full.startswith(os.path.realpath(STATIC) + os.sep) or not os.path.isfile(full):
                return self._send(404, b'not found', 'text/plain')
            with open(full, 'rb') as f:
                data = f.read()
            self._send(200, data, mimetypes.guess_type(full)[0] or 'application/octet-stream')

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
    server = ThreadingHTTPServer((args.bind, args.port), make_handler(app))
    print(f'MiSTerManager on http://{args.bind}:{args.port}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
