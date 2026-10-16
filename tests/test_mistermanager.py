import json
import os
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from xml.etree import ElementTree as ET

from mistermanager.artwork import normalize
from mistermanager.control import Controller, LaunchError, inside, make_mgl
from mistermanager.library import Library, build_index
from mistermanager.server import App, make_handler


def touch(root, rel, data=b'x'):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)
    return path


class Card(unittest.TestCase):
    """A fake /media/fat with a few systems."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fat = self.tmp.name
        touch(self.fat, 'games/NES/Super Mario Bros. (World).nes')
        touch(self.fat, 'games/NES/readme.txt')
        touch(self.fat, 'games/NES/mister-boot.nes')
        touch(self.fat, 'games/SNES/Otros/BM3.SMC')
        touch(self.fat, 'games/SMS/Alex Kidd (UE) [!].sms')
        touch(self.fat, 'games/SMS/SG-1000/Bank Panic (Japan).sg')
        touch(self.fat, 'games/NEOGEO/2020bb/prom')
        touch(self.fat, 'games/NEOGEO/menu/prom')
        touch(self.fat, 'games/NEOGEO/romsets.xml',
              b'<romsets><!-- <romset name="hidden"/> -->'
              b'<romset name="2020bb" altname="2020 Super Baseball"/></romsets>')
        touch(self.fat, '_Arcade/Golden Axe (set 6, US).mra', b'<misterromdescription><setname>goldnaxe</setname></misterromdescription>')
        touch(self.fat, 'games/MegaDrive/Addams Family (U) [!].bin')
        touch(self.fat, 'docs/Arcade/Artwork/goldnaxe.jpg')
        touch(self.fat, 'docs/NEOGEO/Titles/2020bb.png')
        touch(self.fat, 'docs/NES/Artwork/Super Mario Bros. (World).jpg')
        touch(self.fat, 'docs/NES/Titles/Super Mario Bros. (World).png')
        touch(self.fat, 'docs/NES/README.md')
        touch(self.fat, 'docs/Genesis/Artwork/Addams Family, The (Europe).jpg')
        touch(self.fat, 'docs/Genesis/Artwork/Addams Family, The (USA).jpg')
        touch(self.fat, '_Arcade/_alternatives/_Golden Axe/Golden Axe (set 1, World).mra')
        touch(self.fat, '_Arcade/cores/jts16b_20260101.rbf')
        self.fifo = os.path.join(self.fat, 'cmd')
        os.mkfifo(self.fifo)

    def tearDown(self):
        self.tmp.cleanup()

    def read_fifo_after(self, action):
        out = {}

        def read():
            with open(self.fifo) as f:
                out['cmd'] = f.read()
        reader = threading.Thread(target=read)
        reader.start()
        # The writer opens with O_NONBLOCK, which needs the reader to be there first.
        for _ in range(100):
            try:
                action()
                break
            except LaunchError as e:
                if 'No such device' not in str(e) and 'ENXIO' not in str(e) and 'Device not configured' not in str(e):
                    raise
                threading.Event().wait(0.01)
        reader.join(2)
        return out.get('cmd', '')


class IndexTest(Card):
    def test_systems_and_names(self):
        systems = build_index(self.fat)['systems']
        self.assertEqual([g['name'] for g in systems['NES']['games']], ['Super Mario Bros. (World)'])
        self.assertEqual(systems['SNES']['games'][0]['path'], 'games/SNES/Otros/BM3.SMC')
        self.assertEqual([g['name'] for g in systems['SMS']['games']], ['Alex Kidd (UE) [!]'])
        self.assertEqual([g['name'] for g in systems['SG1000']['games']], ['Bank Panic (Japan)'])
        self.assertEqual([(g['name'], g['path']) for g in systems['NeoGeo']['games']],
                         [('2020 Super Baseball', 'games/NEOGEO/2020bb')])

    def test_arcade_skips_cores_and_marks_alternatives(self):
        games = build_index(self.fat)['systems']['Arcade']['games']
        self.assertEqual([(g['name'], g['alt']) for g in games],
                         [('Golden Axe (set 6, US)', False), ('Golden Axe (set 1, World)', True)])

    def test_search_and_cache(self):
        cache = os.path.join(self.fat, 'index.json')
        lib = Library(self.fat, cache)
        lib.rescan()
        self.assertEqual(len(lib.games('Arcade', 'golden')), 1)
        self.assertEqual(len(lib.games('Arcade', 'golden', alternatives=True)), 2)
        self.assertEqual(lib.games('NES', 'mario world')[0]['name'], 'Super Mario Bros. (World)')
        again = Library(self.fat, cache)
        self.assertTrue(again.load_cache())
        self.assertEqual(again.summary(), lib.summary())


class ArtworkTest(Card):
    def test_exact_set_name_and_loose_title_with_region(self):
        systems = build_index(self.fat)['systems']
        art = {g['name']: g.get('art') for s in systems.values() for g in s['games']}
        self.assertEqual(art['Super Mario Bros. (World)'], 'NES/Artwork/Super Mario Bros. (World).jpg')
        self.assertEqual(art['Golden Axe (set 6, US)'], 'Arcade/Artwork/goldnaxe.jpg')
        self.assertEqual(art['2020 Super Baseball'], 'NEOGEO/Titles/2020bb.png')
        self.assertEqual(art['Addams Family (U) [!]'], 'Genesis/Artwork/Addams Family, The (USA).jpg')
        self.assertIsNone(art['Alex Kidd (UE) [!]'])

    def test_normalize(self):
        self.assertEqual(normalize("Knuckles' Chaotix (Europe, USA)"), normalize('Knuckles Chaotix 32X (5) [!]'))
        self.assertEqual(normalize('Addams Family, The (USA)'), normalize('Addams Family (U) [!]'))
        self.assertEqual(normalize('Act Raiser (U)'), normalize('ActRaiser (USA)'))


class LaunchTest(Card):
    def test_mgl_is_valid_xml_with_absolute_path(self):
        root = ET.fromstring(make_mgl('SG1000', '/media/fat/games/SMS/SG-1000/A & B "x".sg'))
        self.assertEqual(root.findtext('rbf'), '_Console/SMS')
        f = root.find('file')
        self.assertEqual((f.get('type'), f.get('index'), f.get('path')),
                         ('f', '1', '/media/fat/games/SMS/SG-1000/A & B "x".sg'))

    def test_cd_systems_mount_the_image(self):
        f = ET.fromstring(make_mgl('CDI', '/media/fat/games/CD-i/Link/Link.cue')).find('file')
        self.assertEqual((f.get('type'), f.get('index')), ('s', '1'))

    def test_console_launch_writes_mgl_and_command(self):
        ctl = Controller(self.fat, self.fat, fifo=self.fifo, mgl_path=os.path.join(self.fat, 'x.mgl'))
        game = {'name': 'Super Mario Bros. (World)', 'path': 'games/NES/Super Mario Bros. (World).nes'}
        cmd = self.read_fifo_after(lambda: ctl.launch('NES', game))
        self.assertEqual(cmd, 'load_core ' + os.path.join(self.fat, 'x.mgl') + '\n')
        mgl = ET.parse(os.path.join(self.fat, 'x.mgl')).getroot()
        self.assertEqual(mgl.find('file').get('path'), os.path.join(self.fat, game['path']))
        self.assertEqual(ctl.recent()[0]['path'], game['path'])

    def test_arcade_launch_loads_mra(self):
        ctl = Controller(self.fat, self.fat, fifo=self.fifo)
        game = {'name': 'Golden Axe', 'path': '_Arcade/Golden Axe (set 6, US).mra'}
        cmd = self.read_fifo_after(lambda: ctl.launch('Arcade', game))
        self.assertEqual(cmd, 'load_core ' + os.path.join(self.fat, game['path']) + '\n')

    def test_paths_outside_are_refused(self):
        ctl = Controller(self.fat, self.fat, fifo=self.fifo)
        with self.assertRaises(LaunchError):
            ctl.launch('NES', {'name': 'x', 'path': 'games/SNES/Otros/BM3.SMC'})
        with self.assertRaises(LaunchError):
            ctl.launch('Arcade', {'name': 'x', 'path': '_Arcade/../menu.rbf'})
        self.assertFalse(inside('/a/b/../../etc', '/a'))

    def test_missing_fifo_is_an_error_not_a_hang(self):
        ctl = Controller(self.fat, self.fat, fifo=os.path.join(self.fat, 'nofifo'))
        with self.assertRaises(LaunchError):
            ctl.menu()


class HttpTest(Card):
    def setUp(self):
        super().setUp()
        self.app = App(self.fat, os.path.join(self.fat, 'state'), self.fifo)
        self.app.library.rescan()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.app))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = 'http://127.0.0.1:%d' % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as r:
            return r.status, r.read()

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(), {'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_pages_and_api(self):
        status, page = self.get('/')
        self.assertEqual(status, 200)
        self.assertIn(b'MiSTer', page)
        _, systems = self.get('/api/systems')
        self.assertEqual(json.loads(systems)[0]['id'], 'Arcade')
        _, games = self.get('/api/games?system=NES&q=mario')
        self.assertEqual(len(json.loads(games)), 1)
        _, status_json = self.get('/api/status')
        self.assertIn('system', json.loads(status_json))

    def test_artwork_route_serves_only_images(self):
        status, _ = self.get('/art/Arcade/Artwork/goldnaxe.jpg')
        self.assertEqual(status, 200)
        for bad in ('/art/NES/README.md', '/art/../games/NES/readme.txt'):
            with self.assertRaises(urllib.error.HTTPError):
                self.get(bad)

    def test_search_all_systems(self):
        _, body = self.get('/api/games?q=a')
        found = {(g['system'], g['name']) for g in json.loads(body)}
        self.assertIn(('MegaDrive', 'Addams Family (U) [!]'), found)
        self.assertIn(('SMS', 'Alex Kidd (UE) [!]'), found)

    def test_unknown_game_and_static_escape(self):
        code, body = self.post('/api/launch', {'system': 'NES', 'path': '../../etc/passwd'})
        self.assertEqual(code, 404)
        with self.assertRaises(urllib.error.HTTPError):
            self.get('/../server.py')


if __name__ == '__main__':
    unittest.main()
