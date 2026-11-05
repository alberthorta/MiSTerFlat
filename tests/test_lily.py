import json
import os
import tempfile
import time
import unittest

from mistermanager.lily import Lily, LilyError

# Stands in for MiSTerLily's misterlily_flash.py: same commands, same output lines.
FAKE_TOOL = r'''
import json, sys, time
if sys.argv[1] == "check":
    print(json.dumps({"board": "0.1.0", "latest": "0.2.0", "error": None}))
    sys.exit(0)
src = sys.argv[2]
if src != "--latest" and open(src, "rb").read() != b"good":
    print("ERROR not a MiSTerLily firmware", flush=True)
    sys.exit(1)
print("STEP flashing /dev/ttyACM0", flush=True)
for p in (25, 50, 100):
    print("PROGRESS %d" % p, flush=True)
    time.sleep(0.05)
print("DONE 0.2.0", flush=True)
'''


class LilyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        os.makedirs(os.path.join(root, 'MiSTerLily'))
        self.tool = os.path.join(root, 'MiSTerLily', 'misterlily_flash.py')
        with open(self.tool, 'w') as f:
            f.write(FAKE_TOOL)
        self.fw = os.path.join(root, 'fw')
        with open(self.fw, 'w') as f:
            f.write('0.1.0\n')
        self.board_file = os.path.join(root, 'board')
        with open(self.board_file, 'w') as f:
            f.write('HWWSTLCD2\n')
        self.cfg = os.path.join(root, 'cfg')
        self.cmd = os.path.join(root, 'cmd')
        self.lily = Lily(root, root, fw_file=self.fw, board_file=self.board_file, cfg_file=self.cfg,
                         cmd_file=self.cmd)

    def write_cfg(self):
        # As MiSTerLily's daemon writes it from the MDSCFG reply.
        with open(self.cfg, 'w') as f:
            json.dump({'contrast': 182, 'clockfont': 4, 'brightness': 5, 'brightness_max': 7,
                       'clockfonts': ['c64', '7seg', 'big', 'sans', 'orbitron', 'serif', 'mono', 'retro16']}, f)

    def tearDown(self):
        self.tmp.cleanup()

    def wait(self):
        for _ in range(100):
            job = self.lily.job()
            if not job['running']:
                return job
            time.sleep(0.05)
        self.fail('flash job did not end')

    def test_not_installed(self):
        os.remove(self.tool)
        self.assertEqual(self.lily.info(), {'installed': False})
        with self.assertRaises(LilyError):
            self.lily.flash_latest()

    def test_info(self):
        info = self.lily.info()
        self.assertEqual((info['board'], info['latest'], info['job']), ('0.1.0', '0.2.0', None))
        self.assertEqual(info['model'], 'Waveshare ESP32-S3-Touch-LCD-2')
        os.remove(self.fw)
        os.remove(self.board_file)
        info = self.lily.info()
        self.assertEqual((info['board'], info['model']), (None, None))

    def test_flash_latest(self):
        self.lily.flash_latest()
        job = self.wait()
        self.assertEqual((job['progress'], job['done'], job['error']), (100, '0.2.0', None))
        self.assertEqual(job['step'], 'flashing /dev/ttyACM0')

    def test_flash_file_refused_by_tool(self):
        self.lily.flash_file(b'bad')
        job = self.wait()
        self.assertEqual(job['error'], 'not a MiSTerLily firmware')
        self.assertIsNone(job['done'])
        self.assertFalse(os.path.exists(self.lily.upload_path))

    def test_flash_file_ok(self):
        self.lily.flash_file(b'good')
        self.assertEqual(self.wait()['done'], '0.2.0')

    def test_one_flash_at_a_time(self):
        self.lily.flash_latest()
        with self.assertRaises(LilyError):
            self.lily.flash_latest()
        self.wait()

    def test_empty_or_huge_file(self):
        with self.assertRaises(LilyError):
            self.lily.flash_file(b'')
        with self.assertRaises(LilyError):
            self.lily.flash_file(b'x' * (0x640000 + 1))

    def test_display_settings(self):
        self.assertIsNone(self.lily.info()['display'])
        self.write_cfg()
        d = self.lily.info()['display']
        self.assertEqual((d['brightness'], d['clockfont'], d['clockfonts'][4]), (5, 4, 'orbitron'))

    def test_set_display(self):
        with self.assertRaises(LilyError):  # no settings file: old firmware or daemon
            self.lily.set_display('brightness', 3)
        self.write_cfg()
        self.lily.set_display('brightness', 3)
        self.lily.set_display('clockfont', 7)
        with open(self.cmd) as f:
            self.assertEqual(f.read(), 'brightness 3\nclockfont 7\n')
        for setting, value in (('brightness', 8), ('clockfont', 8), ('brightness', -1), ('brightness', '3'),
                               ('brightness', True), ('volume', 3)):
            with self.assertRaises(LilyError):
                self.lily.set_display(setting, value)

    def set_fw(self, version):
        with open(self.fw, 'w') as f:
            f.write(version + '\n')

    def test_power_off_needs_relay_firmware(self):
        self.assertFalse(self.lily.can_power_off())  # 0.1.0
        self.set_fw('0.5.0')
        self.assertTrue(self.lily.can_power_off())
        with open(self.board_file, 'w') as f:
            f.write('HWTDISPS3\n')
        self.assertFalse(self.lily.can_power_off())

    def test_power_off_writes_flag(self):
        flag = os.path.join(self.tmp.name, 'poweroff')
        with self.assertRaises(LilyError):
            self.lily.power_off(flag)
        self.assertFalse(os.path.exists(flag))
        self.set_fw('0.10.1')
        self.lily.power_off(flag)
        self.assertTrue(os.path.exists(flag))


if __name__ == '__main__':
    unittest.main()
