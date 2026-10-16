import os
import tempfile
import unittest

from mistermanager.settings import Settings, SettingsError, ini_del, ini_get, ini_set

INI = ('[MiSTer]\r\n'
       'vscale_mode=0          ; 0 - scale to fit the screen height.\r\n'
       ';preset_default=General Hardware/Console - 3rdGen\r\n'
       'video_mode=8\n'
       '\r\n'
       '[arcade]\r\n'
       'afilter_default=Arcade LPF/x.txt\r\n')


def touch(root, rel, text='x'):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', newline='') as f:
        f.write(text)
    return path


class IniTest(unittest.TestCase):
    def test_replace_keeps_comment_and_line_ends(self):
        out = ini_set(INI, 'MiSTer', 'vscale_mode', '1')
        self.assertIn('vscale_mode=1          ; 0 - scale to fit the screen height.\r\n', out)
        self.assertIn('video_mode=8\n\r\n', out)
        self.assertEqual(ini_get(out, 'MiSTer', 'vscale_mode'), '1')

    def test_add_to_section_and_new_section(self):
        out = ini_set(INI, 'arcade', 'preset_default', 'Custom/A')
        self.assertEqual(ini_get(out, 'arcade', 'preset_default'), 'Custom/A')
        self.assertIsNone(ini_get(out, 'MiSTer', 'preset_default'))
        out = ini_set(out, 'arcade_vertical', 'preset_default', 'Custom/A - Vertical')
        self.assertEqual(ini_get(out, 'arcade_vertical', 'preset_default'), 'Custom/A - Vertical')
        self.assertEqual(ini_get(out, 'arcade', 'preset_default'), 'Custom/A')
        out = ini_del(out, 'arcade', 'preset_default')
        self.assertIsNone(ini_get(out, 'arcade', 'preset_default'))
        self.assertEqual(ini_get(out, 'arcade', 'afilter_default'), 'Arcade LPF/x.txt')


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fat = self.tmp.name
        touch(self.fat, 'MiSTer.ini', INI)
        touch(self.fat, 'Filters/Upscaling/Sharp.txt')
        touch(self.fat, 'Filters/Scanlines - Adaptive/SLA_Dk_080_Br_080.txt')
        touch(self.fat, 'Gamma/Contrast/Boost_2.txt')
        touch(self.fat, 'Shadow_Masks/Simple/Grille.txt')
        touch(self.fat, 'Presets/General Hardware/Arcade 90s.ini')
        touch(self.fat, 'Presets/Custom/Mine.ini', '#my look\nhfilter=Upscaling/Sharp.txt\n')
        touch(self.fat, 'Presets/Custom/Mine - Vertical.ini', 'hfilter=x\n')
        self.s = Settings(self.fat, os.path.join(self.fat, 'state'), os.path.join(self.fat, 'nofifo'))

    def tearDown(self):
        self.tmp.cleanup()

    def test_volume_from_volume_dat(self):
        self.assertEqual(self.s.volume()['level'], 7)
        with open(touch(self.fat, 'config/Volume.dat'), 'wb') as f:
            f.write(bytes([0x13]))  # attenuation 3, mute bit set
        self.assertEqual(self.s.volume(), {'level': 4, 'muted': True, 'levels': 8})

    def test_set_ini_checks_values_and_backs_up(self):
        self.s.set_ini('MiSTer', 'preset_default', 'General Hardware/Arcade 90s')
        self.assertEqual(self.s.ini()['preset_default']['MiSTer'], 'General Hardware/Arcade 90s')
        self.assertEqual(len(os.listdir(os.path.join(self.fat, 'state', 'backups'))), 1)
        for args in (('MiSTer', 'video_mode', '0'), ('MiSTer', 'vscale_mode', '9'),
                     ('arcade', 'preset_default', 'Nope'), ('evil', 'vscale_mode', '1')):
            with self.assertRaises(SettingsError):
                self.s.set_ini(*args)

    def test_write_preset_updates_vertical_twin(self):
        self.assertEqual(list(self.s.custom_presets()), ['Mine'])
        self.s.write_preset('Mine', {'hfilter': 'Upscaling/Sharp.txt',
                                     'vfilter': 'Scanlines - Adaptive/SLA_Dk_080_Br_080.txt',
                                     'sfilter': 'same', 'gamma': 'off',
                                     'mask': 'Simple/Grille.txt', 'maskmode': '1x'})
        with open(os.path.join(self.fat, 'Presets/Custom/Mine.ini')) as f:
            text = f.read()
        self.assertTrue(text.startswith('#my look\nhfilter=Upscaling/Sharp.txt\nvfilter=Scanlines'))
        v = self.s.read_preset('Mine - Vertical')
        self.assertEqual((v['hfilter'], v['vfilter'], v['maskmode']),
                         ('Scanlines - Adaptive/SLA_Dk_080_Br_080.txt', 'Upscaling/Sharp.txt', '1x rotated'))
        with self.assertRaises(SettingsError):
            self.s.write_preset('Mine', {'hfilter': '../../etc/passwd'})
        with self.assertRaises(SettingsError):
            self.s.write_preset('../General Hardware/Arcade 90s', {})


if __name__ == '__main__':
    unittest.main()
