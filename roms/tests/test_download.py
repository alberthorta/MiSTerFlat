import io
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest.mock import patch

from mister_arcade_builder.download import download_missing
from mister_arcade_builder.index import Index
from mister_arcade_builder.mra import Mra, Part
from mister_arcade_builder.resolve import COMPLETE, resolve


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)
        data = b'fake ROM data'
        self.crc = f'{zlib.crc32(data):08x}'
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('different-name.bin', data)
        self.payload = stream.getvalue()
        self.mra = Mra('game.mra', setname='game',
                       parts=[Part('game.zip', 'rom.bin', self.crc)],
                       zip_names={'game.zip'})
        self.index = Index()

    def run_download(self, **kwargs):
        return download_missing(resolve([self.mra], self.index), self.index,
                                self.cache, **kwargs)

    def test_download_resolves_by_crc_and_reuses_cache(self):
        with patch('urllib.request.urlopen', return_value=io.BytesIO(self.payload)) as fetch:
            self.assertEqual(self.run_download(), 1)
            self.assertEqual(fetch.call_count, 1)
        self.assertEqual(resolve([self.mra], self.index).statuses[0].status, COMPLETE)
        self.index = Index()
        with patch('urllib.request.urlopen') as fetch:
            self.assertEqual(self.run_download(offline=True), 1)
            fetch.assert_not_called()
        self.assertEqual(resolve([self.mra], self.index).statuses[0].status, COMPLETE)

    def test_invalid_response_is_not_cached(self):
        with patch('urllib.request.urlopen', return_value=io.BytesIO(b'<html>error</html>')):
            self.assertEqual(self.run_download(), 0)
        self.assertFalse((self.cache / 'downloads/mdk/game.zip').exists())
        self.assertFalse(list(self.cache.rglob('*.tmp')))
        self.assertNotIn(self.crc, self.index.by_crc)

    def test_offline_and_dry_run_do_not_download(self):
        with patch('urllib.request.urlopen') as fetch:
            self.assertEqual(self.run_download(offline=True), 0)
            self.assertEqual(self.run_download(dry_run=True), 0)
            fetch.assert_not_called()

    def test_http_failure_leaves_missing(self):
        from urllib.error import HTTPError
        with patch('urllib.request.urlopen', side_effect=HTTPError('url', 404, 'missing', {}, None)):
            self.assertEqual(self.run_download(), 0)
        self.assertTrue(resolve([self.mra], self.index).statuses[0].missing)
