import json
import os
import tempfile
import unittest

from mistermanager.library import Library
from mistermanager.quick import MAX_GAMES, QuickError, QuickLaunch, short_name


def touch(root, rel, data=b'x'):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)
    return path


LISTING = ('<a href="Super%20Mario%20World%20(Europe).png">x</a>'
           '<a href="Super%20Mario%20World%20(USA).png">x</a>'
           '<a href="Super%20Mario%20World%202%20-%20Yoshi%27s%20Island%20(USA).png">x</a>'
           '<a href="F-Zero%20(USA).png">x</a><a href="?C=N;O=D">sort</a>'
           '<a href="Super%20Mario%20All-Stars%20%2B%20Super%20Mario%20World%20(USA).png">x</a>')


class QuickTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fat = os.path.join(self.tmp.name, 'fat')
        self.state = os.path.join(self.tmp.name, 'state')
        touch(self.fat, 'games/SNES/Super Mario World (U) [!].smc')
        touch(self.fat, 'games/SNES/F-Zero (USA).sfc')
        touch(self.fat, 'games/SNES/Super Mario All Stars & World (U).smc')
        touch(self.fat, '_Console/SNES_20260823.rbf')
        self.library = Library(self.fat, os.path.join(self.tmp.name, 'index.json'))
        self.library.rescan()
        self.fetched = []

        def fetcher(url, limit, timeout=20):
            self.fetched.append(url)
            return LISTING.encode() if url.endswith('/') else b'\x89PNG box'
        self.quick = QuickLaunch(self.fat, self.library, self.state, fetcher)

    def tearDown(self):
        self.tmp.cleanup()

    def stored(self):
        with open(os.path.join(self.fat, 'MiSTerLily/quick/games.json')) as f:
            return json.load(f)['systems']

    def test_summary(self):
        s = {x['id']: x for x in self.quick.summary()}
        self.assertEqual([x['id'] for x in self.quick.summary()],
                         ['GAMEBOY', 'GBA', 'NES', 'SMS', 'SNES', 'MegaDrive', 'PSX'])
        self.assertTrue(s['SNES']['installed'])
        self.assertFalse(s['NES']['installed'])
        self.assertEqual(s['SNES']['count'], 0)

    def test_add_writes_an_mgl_and_keeps_order(self):
        a = self.quick.add('SNES', 'games/SNES/Super Mario World (U) [!].smc')
        b = self.quick.add('SNES', 'games/SNES/F-Zero (USA).sfc')
        self.assertEqual(a['name'], 'Super Mario World')
        with open(a['mgl']) as f:
            self.assertIn('Super Mario World (U) [!].smc', f.read())
        self.assertEqual([g['id'] for g in self.stored()['SNES']], [a['id'], b['id']])
        self.quick.move('SNES', b['id'], -1)
        self.assertEqual([g['id'] for g in self.quick.games('SNES')['games']], [b['id'], a['id']])
        with self.assertRaises(QuickError):
            self.quick.add('SNES', 'games/SNES/F-Zero (USA).sfc')  # already there
        with self.assertRaises(QuickError):
            self.quick.add('SNES', '../../etc/passwd')
        with self.assertRaises(QuickError):
            self.quick.add('N64', 'games/SNES/F-Zero (USA).sfc')
        self.quick.remove('SNES', a['id'])
        self.assertFalse(os.path.exists(a['mgl']))
        self.assertEqual(len(self.stored()['SNES']), 1)

    def test_full_list(self):
        for i in range(MAX_GAMES + 1):
            touch(self.fat, 'games/SNES/Game {}.sfc'.format(i))
        self.library.rescan()
        for i in range(MAX_GAMES):
            self.quick.add('SNES', 'games/SNES/Game {}.sfc'.format(i))
        with self.assertRaises(QuickError):
            self.quick.add('SNES', 'games/SNES/Game {}.sfc'.format(MAX_GAMES))

    def test_cover(self):
        g = self.quick.add('SNES', 'games/SNES/F-Zero (USA).sfc')
        crc = self.quick.set_cover('SNES', g['id'], b'\xff\xd8 jpeg')
        self.assertEqual(self.stored()['SNES'][0]['crc'], crc)
        path = self.quick.cover('SNES', g['id'])
        with open(path, 'rb') as f:
            self.assertEqual(f.read(), b'\xff\xd8 jpeg')
        self.quick.set_cover('SNES', g['id'], b'\x89PNG png')
        self.assertFalse(os.path.exists(path))  # the .jpg went away
        with self.assertRaises(QuickError):
            self.quick.set_cover('SNES', g['id'], b'GIF89a')
        self.quick.clear_cover('SNES', g['id'])
        self.assertIsNone(self.quick.cover('SNES', g['id']))
        self.assertEqual(self.stored()['SNES'][0]['crc'], 0)

    def test_boxart_search(self):
        g = self.quick.add('SNES', 'games/SNES/Super Mario World (U) [!].smc')
        f = self.quick.add('SNES', 'games/SNES/F-Zero (USA).sfc')
        # GoodTools name: the bare title matches, the game's own region first.
        self.assertEqual(self.quick.boxart_search('SNES', g['id']),
                         ['Super Mario World (USA)', 'Super Mario World (Europe)'])
        self.assertEqual(self.quick.boxart_search('SNES', f['id']), ['F-Zero (USA)'])
        m = self.quick.add('SNES', 'games/SNES/Super Mario All Stars & World (U).smc')
        self.assertEqual(self.quick.boxart_search('SNES', m['id'])[0], 'Super Mario All-Stars + Super Mario World (USA)')
        self.assertEqual(len(self.fetched), 1)  # the listing is cached
        self.assertEqual(self.quick.boxart('SNES', 'F-Zero (USA)'), b'\x89PNG box')
        self.assertTrue(self.fetched[-1].endswith('/Named_Boxarts/F-Zero%20%28USA%29.png'))
        with self.assertRaises(QuickError):
            self.quick.boxart('SNES', '../secret')

    def test_short_name(self):
        self.assertEqual(short_name('7th Saga, The (U) [!]'), '7th Saga, The')
        self.assertEqual(short_name('(Prototype)'), '(Prototype)')


if __name__ == '__main__':
    unittest.main()
