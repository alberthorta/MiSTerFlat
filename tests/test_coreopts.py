import importlib.util
import os
import tempfile
import unittest

from mistermanager.coreopts import CoreOptions, CoreOptionsError, get_bits, set_bits

spec = importlib.util.spec_from_file_location(
    'build_core_catalog', os.path.join(os.path.dirname(__file__), '..', 'tools', 'build_core_catalog.py'))
catalog_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog_tool)

CONF = ('NEOGEO;;-;FS1,*,Load ROM set;H3OP,FM,ON,OFF;O1,System Type,Console(AES),Arcade(MVS);'
        'OM,BIOS,UniBIOS,Original;O3,Video Mode,NTSC,PAL;o9A,Input,A,B,C,D;P1,Audio & Video;'
        'd5P1o36,Crop Offset,0,2,4;O[16:15],Slot,1,2,3,4;RE,Reset;v,2;')


class CatalogParseTest(unittest.TestCase):
    def test_bit_codes_pages_and_version(self):
        entry = catalog_tool.parse(CONF)
        self.assertEqual(entry['cfg'], 'NEOGEO_v2.CFG')
        got = {o['label']: (o['bits'], o['page']) for o in entry['options']}
        self.assertEqual(got['FM'], ([25, 25], ''))
        self.assertEqual(got['System Type'], ([1, 1], ''))
        self.assertEqual(got['BIOS'], ([22, 22], ''))
        self.assertEqual(got['Input'], ([41, 42], ''))
        self.assertEqual(got['Crop Offset'], ([35, 38], 'Audio & Video'))
        self.assertEqual(got['Slot'], ([15, 16], ''))
        self.assertNotIn('Reset', got)


class CoreOptionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fat = self.tmp.name
        os.makedirs(os.path.join(self.fat, '_Console'))
        open(os.path.join(self.fat, '_Console', 'NeoGeo_20260603.rbf'), 'w').close()
        entry = catalog_tool.parse(CONF.replace('v,2;', ''))
        self.opts = CoreOptions(self.fat, os.path.join(self.fat, 'state'), {'NeoGeo': entry})

    def tearDown(self):
        self.tmp.cleanup()

    def test_bits(self):
        self.assertEqual(get_bits(0b1010, 1, 3), 0b101)
        self.assertEqual(set_bits(0, 41, 42, 3), 3 << 41)

    def test_defaults_then_write_little_endian(self):
        self.assertEqual(self.opts.installed()[0]['id'], 'NeoGeo')
        data = self.opts.get('NeoGeo')
        self.assertFalse(data['saved'])
        ids = {o['label']: o['id'] for o in data['options']}
        self.opts.set('NeoGeo', {str(ids['System Type']): 1, str(ids['Input']): 2})
        with open(os.path.join(self.fat, 'config', 'NEOGEO.CFG'), 'rb') as f:
            raw = f.read()
        self.assertEqual(len(raw), 16)
        self.assertEqual(int.from_bytes(raw, 'little'), (1 << 1) | (2 << 41))
        values = {o['label']: o['value'] for o in self.opts.get('NeoGeo')['options']}
        self.assertEqual((values['System Type'], values['Input'], values['BIOS']), (1, 2, 0))
        self.opts.set('NeoGeo', {str(ids['Video Mode']): 1})
        self.assertEqual(len(os.listdir(os.path.join(self.fat, 'state', 'backups', 'cores'))), 1)

    def test_bad_input(self):
        with self.assertRaises(CoreOptionsError):
            self.opts.set('NeoGeo', {'0': 9})
        with self.assertRaises(CoreOptionsError):
            self.opts.get('../etc')


if __name__ == '__main__':
    unittest.main()
