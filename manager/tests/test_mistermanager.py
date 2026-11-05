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
from mistermanager.motion import MotionBlocker, controllers, sensor_nodes, wanted_nodes
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
        for n in (1, 2, 3):
            touch(self.fat, f'games/PSX/Final Fantasy VII (Spanish v3.2)/Final Fantasy VII (Spanish v3.2) (Disc {n}).chd')
            touch(self.fat, f'games/PSX/_alternatives/Final Fantasy VII (USA)/Final Fantasy VII (USA) (Disc {n}).chd')
        touch(self.fat, 'docs/PSX/Artwork/Final Fantasy VII (USA) (Disc 1).jpg')
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

    def test_multi_disc_games_show_once_and_console_alternatives(self):
        games = build_index(self.fat)['systems']['PSX']['games']
        self.assertEqual([(g['name'], g.get('alt', False), g['discs']) for g in games],
                         [('Final Fantasy VII (Spanish v3.2)', False, 3), ('Final Fantasy VII (USA)', True, 3)])
        self.assertTrue(games[0]['path'].endswith('(Disc 1).chd'))
        self.assertEqual(games[1]['art'], 'PSX/Artwork/Final Fantasy VII (USA) (Disc 1).jpg')

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

    def test_spectrum_tape_and_snapshot_slots(self):
        tape = ET.fromstring(make_mgl('ZXSpectrum', '/media/fat/games/Spectrum/V/Vikings.tap')).find('file')
        snap = ET.fromstring(make_mgl('ZXSpectrum', '/media/fat/games/Spectrum/A/Atic.z80')).find('file')
        self.assertEqual((tape.get('index'), snap.get('index')), ('2', '4'))

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

    def test_now_playing_carries_art_of_our_own_launch(self):
        from unittest import mock
        from mistermanager.control import current
        launch = {'system': 'NES', 'name': 'Super Mario Bros. (World)', 'path': 'games/NES/x.nes',
                  'art': 'NES/Artwork/x.jpg', 'time': int(__import__('time').time())}
        files = {'/tmp/CORENAME': 'NES', '/tmp/RBFNAME': 'NES', '/tmp/FULLPATH': 'games/NES/x.nes'}
        with mock.patch('mistermanager.control._read', side_effect=lambda path: files.get(path, '')):
            now = current(self.fat, launch)
            self.assertEqual((now['game'], now['system'], now['art']), (launch['name'], 'NES', 'NES/Artwork/x.jpg'))
            files['/tmp/CORENAME'] = 'MENU'
            self.assertNotIn('art', current(self.fat, None))

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



class MotionTest(unittest.TestCase):
    def test_only_motion_sensor_devices(self):
        text = ('I: Bus=0005 Vendor=054c Product=0ce6\nN: Name="DualSense Wireless Controller"\n'
                'H: Handlers=js0 event1 \n\n'
                'I: Bus=0005 Vendor=054c Product=0ce6\nN: Name="DualSense Wireless Controller Motion Sensors"\n'
                'H: Handlers=js1 event2 \n\n'
                'I: Bus=0005 Vendor=054c Product=0ce6\nN: Name="DualSense Wireless Controller Touchpad"\n'
                'H: Handlers=mouse1 event3 \n')
        self.assertEqual(sensor_nodes(text), ['/dev/input/event2'])

    def test_controllers_grouped_with_battery(self):
        text = ('I: Bus=0005 Vendor=054c Product=0ce6 Version=8100\nN: Name="DualSense Wireless Controller"\n'
                'U: Uniq=a0:ab:51:93:b8:20\nH: Handlers=js0 event1 \n\n'
                'I: Bus=0005 Vendor=054c Product=0ce6 Version=8100\nN: Name="DualSense Wireless Controller Motion Sensors"\n'
                'U: Uniq=a0:ab:51:93:b8:20\nH: Handlers=js1 event2 \n\n'
                'I: Bus=0003 Vendor=0000 Product=0000 Version=0004\nN: Name="MiSTer virtual input"\n'
                'U: Uniq=\nH: Handlers=sysrq kbd event4 \n')
        with tempfile.TemporaryDirectory() as power:
            bat = os.path.join(power, 'ps-controller-battery-a0:ab:51:93:b8:20')
            os.makedirs(bat)
            for name, value in (('capacity', '75\n'), ('status', 'Discharging\n')):
                with open(os.path.join(bat, name), 'w') as f:
                    f.write(value)
            pads = controllers(text, power)
        self.assertEqual(len(pads), 1)
        self.assertEqual((pads[0]['name'], pads[0]['bus'], pads[0]['battery']),
                         ('DualSense Wireless Controller', 'Bluetooth', 75))
        self.assertEqual([p['kind'] for p in pads[0]['parts']], ['gamepad', 'motion sensors'])

    def test_ignored_device_nodes(self):
        text = ('I: Bus=0005 Vendor=16c0 Product=05df\nN: Name="WorldTime Jitter"\nU: Uniq=48:27:e2:8e:af:c1\n'
                'H: Handlers=mouse0 event0 \n\n'
                'I: Bus=0005 Vendor=054c Product=0ce6\nN: Name="DualSense Wireless Controller Motion Sensors"\n'
                'U: Uniq=a0:ab:51:93:b8:20\nH: Handlers=js1 event2 \n')
        self.assertEqual(wanted_nodes(text, True, set()), {'/dev/input/event2'})
        self.assertEqual(wanted_nodes(text, False, {'48:27:e2:8e:af:c1'}), {'/dev/input/event0'})

    def test_ignore_list_is_remembered(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'controllers.json')
            m = MotionBlocker(path)
            m.set_ignored('48:27:E2:8E:AF:C1', 'WorldTime Jitter', True)
            self.assertEqual(MotionBlocker(path).ignored, {'48:27:e2:8e:af:c1': 'WorldTime Jitter'})
            with self.assertRaises(ValueError):
                m.set_ignored('../x', '', True)

    def test_switch_is_remembered(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'controllers.json')
            MotionBlocker(path).set_enabled(False)
            self.assertFalse(MotionBlocker(path).enabled)


if __name__ == '__main__':
    unittest.main()
