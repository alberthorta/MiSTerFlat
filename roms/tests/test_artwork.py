import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mister_arcade_builder.artwork import GamePage, enrich_report
from mister_arcade_builder.report_html import rows

PAGE = '''<table><tr><td>year</td><td><a>1993</a></td></tr>
<tr><th>genre</th><td>Beat-'Em-Up</td></tr>
<tr><td>manufacturer</td><td>Capcom</td></tr></table>
<img src="/img/titles/dino.png"><img src="/img/snap/dino.png">
<img src="https://example.com/img/snap/dino.png"><img src="/img/logo.png">'''
PNG = b'\x89PNG\r\n\x1a\n' + b'fake image for offline tests'


class ArtworkTests(unittest.TestCase):
    def test_page_parser(self):
        parser = GamePage()
        parser.feed(PAGE)
        self.assertEqual(parser.info, {'year': '1993', 'genre': "Beat-'Em-Up", 'manufacturer': 'Capcom'})
        self.assertEqual([i['label'] for i in parser.images], ['Title', 'In-game'])

    def test_download_cache_and_portable_report(self):
        with tempfile.TemporaryDirectory() as root:
            cache, output = Path(root) / 'cache', Path(root) / 'output'
            game = dict(name='Dino', path='dino.mra', setname='dino', rbf='cps1', zips=[])
            rep = {'complete': [game, dict(game)]}
            with patch('mister_arcade_builder.artwork.fetch', side_effect=[PAGE.encode(), PNG, PNG]) as fetch:
                enrich_report(rep, cache, output)
                self.assertEqual(fetch.call_count, 3)
            art = rep['artwork']['dino']
            self.assertEqual(art['year'], '1993')
            self.assertEqual(len(art['images']), 2)
            self.assertTrue((output / art['images'][0]['path']).is_file())
            self.assertEqual(rows(rep)[0]['art'], art)
            with patch('mister_arcade_builder.artwork.fetch') as fetch:
                enrich_report(rep, cache, Path(root) / 'moved', offline=True)
                fetch.assert_not_called()
            self.assertTrue((Path(root) / 'moved' / art['images'][0]['path']).is_file())

    def test_no_network_in_offline_or_dry_run(self):
        with tempfile.TemporaryDirectory() as root:
            rep = {'missing': [{'setname': 'dino'}, {'setname': '../unsafe'}]}
            with patch('mister_arcade_builder.artwork.fetch') as fetch:
                for mode in ({'offline': True}, {'dry_run': True}):
                    enrich_report(rep, Path(root), Path(root) / 'out', **mode)
                fetch.assert_not_called()
            self.assertEqual(rep['artwork']['dino']['images'], [])

    def test_invalid_images_do_not_break_report(self):
        with tempfile.TemporaryDirectory() as root:
            rep = {'complete': [{'setname': 'dino'}]}
            with patch('mister_arcade_builder.artwork.fetch', side_effect=[PAGE.encode(), b'error', b'error']):
                enrich_report(rep, Path(root) / 'cache', Path(root) / 'out')
            self.assertEqual(rep['artwork']['dino']['images'], [])
            self.assertEqual(rep['artwork']['dino']['year'], '1993')
