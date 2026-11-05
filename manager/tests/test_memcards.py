import json
import os
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from mistermanager.memcards import _sjis_latin, CARD_SIZE, CardError, MemoryCards, psx_game_folders, saves, unwrap
from mistermanager.server import App, make_handler


def make_card(title='ＦＩＮＡＬ ＦＡＮＴＡＳＹ', code='BASCUS-94163FF7-S01'):
    card = bytearray(CARD_SIZE)
    card[:2] = b'MC'
    entry = bytearray(128)
    entry[0] = 0x51
    entry[4:8] = (8192).to_bytes(4, 'little')
    entry[10:10 + len(code)] = code.encode()
    card[128:256] = entry
    card[8192:8194] = b'SC'
    raw = title.encode('shift_jis')
    card[8192 + 4:8192 + 4 + len(raw)] = raw
    return bytes(card)


class CardFormatTest(unittest.TestCase):
    def test_saves_and_title(self):
        self.assertEqual(saves(make_card()), [{'slot': 1, 'blocks': 1, 'code': 'BASCUS-94163FF7-S01',
                                               'title': 'FINAL FANTASY'}])

    def test_latin_decoder_without_codec(self):
        raw = 'ＦＩＮＡＬ　ＦＡＮＴＡＳＹ　ＶＩＩ　ＳＡＶＥ０１（ｘ）'.encode('shift_jis')
        self.assertEqual(_sjis_latin(raw), 'FINAL FANTASY VII SAVE01(x)')

    def test_wrapped_formats(self):
        card = make_card()
        self.assertEqual(unwrap(b'\0' * 3904 + card), card)   # DexDrive .gme
        self.assertEqual(unwrap(b'\0' * 0x80 + card), card)   # PSP .vmp
        with self.assertRaises(CardError):
            unwrap(b'x' * 1000)


class CardStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fat = self.tmp.name
        self.cards = MemoryCards(self.fat, os.path.join(self.fat, 'state'))

    def tearDown(self):
        self.tmp.cleanup()

    def test_list_write_backup(self):
        listing = self.cards.list(['Spyro the Dragon (USA)'])
        self.assertEqual([(c['game'], c['exists']) for c in listing], [('Spyro the Dragon (USA)', False)])
        self.cards.write('Spyro the Dragon (USA).sav', make_card())
        self.cards.write('Spyro the Dragon (USA).sav', make_card(title='SPYRO'))
        listing = self.cards.list(['Spyro the Dragon (USA)'])
        self.assertEqual(len(listing), 1)
        self.assertEqual(listing[0]['saves'][0]['title'], 'SPYRO')
        self.assertEqual(len(os.listdir(os.path.join(self.fat, 'state', 'backups', 'memcards'))), 1)
        for bad in ('../x.sav', 'x.txt', '.hidden.sav'):
            with self.assertRaises(CardError):
                self.cards.write(bad, make_card())

    def test_game_folders(self):
        index = {'systems': {'PSX': {'games': [
            {'path': 'games/PSX/Spyro (USA)/Spyro (USA).chd'},
            {'path': 'games/PSX/_alternatives/FF7 (USA)/FF7 (USA) (Disc 1).chd', 'alt': True},
            {'path': 'games/PSX/mister-loose.chd'}]}}}
        self.assertEqual(psx_game_folders(index), ['Spyro (USA)'])


class CardHttpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App(self.tmp.name, os.path.join(self.tmp.name, 'state'), os.path.join(self.tmp.name, 'fifo'))
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.app))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = 'http://127.0.0.1:%d' % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def test_upload_then_download(self):
        card = make_card()
        req = urllib.request.Request(self.base + '/api/psx/cards/upload?file=Spyro%20(USA).sav', card,
                                     {'Content-Type': 'application/octet-stream'})
        with urllib.request.urlopen(req) as r:
            self.assertEqual(json.loads(r.read())['saves'][0]['code'], 'BASCUS-94163FF7-S01')
        with urllib.request.urlopen(self.base + '/api/psx/cards/download?file=Spyro%20(USA).sav') as r:
            self.assertEqual(r.read(), card)
            self.assertIn('Spyro%20%28USA%29.mcd', r.headers['Content-Disposition'])
        bad = urllib.request.Request(self.base + '/api/psx/cards/upload?file=x.sav', b'nope')
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(bad)


if __name__ == '__main__':
    unittest.main()
