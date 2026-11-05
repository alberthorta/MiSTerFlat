import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

from convert_fbalpha import convert, load_dat, main


class ConvertTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = self.root / 'input'
        self.inputs.mkdir()
        self.output = self.root / 'output'
        self.dat = self.root / 'target.dat'
        self.data = b'fake ROM'
        self.crc = f'{zlib.crc32(self.data):08x}'

    def write_dat(self, body):
        self.dat.write_text('<datafile>' + body + '</datafile>')

    def rom(self, name='target.bin', crc=None, size=None):
        return f'<rom name="{name}" crc="{crc or self.crc}" size="{size or len(self.data)}"/>'

    def zip(self):
        with zipfile.ZipFile(self.inputs / 'source.zip', 'w') as z:
            z.writestr('original-name.bin', self.data)

    def test_crc_renaming_and_parent_dependency(self):
        self.zip()
        self.write_dat('<game name="bios">' + self.rom('bios.bin') + '</game>'
                       '<game name="game" romof="bios">' + self.rom() + '</game>')
        before = (self.inputs / 'source.zip').read_bytes()
        report = convert([self.inputs], self.output, self.dat)
        self.assertIn('game', report['complete'])
        with zipfile.ZipFile(self.output / 'game.zip') as z:
            self.assertEqual(set(z.namelist()), {'bios.bin', 'target.bin'})
            self.assertEqual(z.read('target.bin'), self.data)
        self.assertEqual((self.inputs / 'source.zip').read_bytes(), before)
        first = (self.output / 'game.zip').read_bytes()
        convert([self.inputs], self.output, self.dat)
        self.assertEqual(first, (self.output / 'game.zip').read_bytes())

    def test_size_mismatch_does_not_write_partial(self):
        self.zip()
        self.write_dat('<game name="game">' + self.rom() + self.rom('wrong-size.bin', size=999) + '</game>')
        report = convert([self.inputs], self.output, self.dat)
        self.assertEqual(len(report['incomplete']), 1)
        self.assertFalse((self.output / 'game.zip').exists())

    def test_dry_run(self):
        self.zip()
        self.write_dat('<game name="game">' + self.rom() + '</game>')
        report = convert([self.inputs], self.output, self.dat, dry_run=True)
        self.assertEqual(report['complete'], ['game'])
        self.assertFalse(list(self.output.glob('*.zip')))
        self.assertTrue((self.output / 'fbalpha-report.json').exists())

    def test_chd_sets_and_their_clones_do_not_block_other_games(self):
        self.zip()
        self.write_dat('<game name="kinstp47"><disk name="kinst"/>' + self.rom() + '</game>'
                       '<game name="clone" romof="kinstp47"/>'
                       '<game name="game">' + self.rom() + '</game>')
        report = convert([self.inputs], self.output, self.dat)
        self.assertEqual(report['complete'], ['game'])
        self.assertEqual({x['setname'] for x in report['unsupported']}, {'kinstp47', 'clone'})
        self.assertTrue((self.output / 'game.zip').exists())
        self.assertFalse((self.output / 'kinstp47.zip').exists())
        self.assertFalse((self.output / 'clone.zip').exists())

    def test_unsafe_dat_and_cycles(self):
        for body in ('<game name="../escape">' + self.rom() + '</game>',
                     '<game name="game">' + self.rom('../escape') + '</game>',
                     '<game name="a" romof="b"/><game name="b" romof="a"/>',
                     '<game name="a" romof="missing"/>'):
            self.write_dat(body)
            with self.assertRaises(ValueError):
                load_dat(self.dat)

    def test_overlapping_output_refused(self):
        self.write_dat('<game name="game">' + self.rom() + '</game>')
        self.assertEqual(main(['--input', str(self.inputs), '--output', str(self.inputs / 'out'), '--dat', str(self.dat)]), 1)
