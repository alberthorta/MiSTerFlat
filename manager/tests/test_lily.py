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

    def test_station(self):
        sta = os.path.join(self.tmp.name, 'sta')
        cmd = os.path.join(self.tmp.name, 'sta_cmd')
        lily = Lily(self.tmp.name, self.tmp.name, fw_file=self.fw, board_file=self.board_file, sta_file=sta,
                    sta_cmd_file=cmd)
        self.assertIsNone(lily.station())
        with self.assertRaises(LilyError):
            lily.station_command('scan')
        with open(sta, 'w') as f:
            json.dump({'state': 'ok', 'ip': '10.0.0.9', 'rssi': -61, 'ssid': 'Casa', 'scanning': False,
                       'networks': [{'ssid': 'Casa', 'rssi': -61, 'secure': True}], 'error': '', 'updated': 1}, f)
        self.assertEqual(lily.station()['ip'], '10.0.0.9')
        lily.station_command('scan')
        lily.station_command('join', 'Casa 5G', 'secret123')
        lily.station_command('join', 'Cafe')
        with open(cmd) as f:
            self.assertEqual(f.read().splitlines(), ['scan', 'join {} {}'.format('Casa 5G'.encode().hex(), 'secret123'.encode().hex()),
                                                     'join {}'.format('Cafe'.encode().hex())])
        self.assertEqual(os.stat(cmd).st_mode & 0o777, 0o600)
        for bad in (('join', '', 'secret123'), ('join', 'x' * 33, ''), ('join', 'Casa', 'short'), ('reboot', '', '')):
            with self.assertRaises(LilyError):
                lily.station_command(*bad)

    def test_station_scan_on_the_mister(self):
        sta = os.path.join(self.tmp.name, 'sta')
        cmd = os.path.join(self.tmp.name, 'sta_cmd')
        with open(sta, 'w') as f:
            json.dump({'state': 'off', 'ip': '', 'rssi': 0, 'ssid': '', 'scanning': False, 'networks': [],
                       'error': '', 'updated': 1}, f)
        with open(os.path.join(self.tmp.name, 'MiSTerLily', 'wifi.py'), 'w') as f:
            f.write('MHZ = 2437\n'
                    'def dongle_present():\n    return True\n'
                    'def scan_24ghz():\n    return [(b"Casa", -48, True, True), (b"Cafe", -70, False, False), (b"", -60, True, False)]\n'
                    'def link():\n    return (b"Casa", MHZ)\n'
                    'def saved_key(ssid):\n    return "ab" * 32 if ssid == b"Casa" else None\n')
        lily = Lily(self.tmp.name, self.tmp.name, fw_file=self.fw, board_file=self.board_file, sta_file=sta,
                    sta_cmd_file=cmd)
        lily.station_command('scan')
        for _ in range(50):
            if not lily.station()['scanning']:
                break
            time.sleep(0.02)
        self.assertEqual(lily.station()['networks'], [
            {'ssid': 'Casa', 'rssi': -48, 'secure': True, 'mister': True, 'known': True},
            {'ssid': 'Cafe', 'rssi': -70, 'secure': False, 'mister': False, 'known': False}])
        self.assertFalse(os.path.exists(cmd))  # the board was not asked to scan
        self.assertEqual(lily.station()['mister'], {'ssid': 'Casa', 'ok': True, 'reason': ''})
        # Copy: the MiSTer's network with its saved PSK; a known network joins without a password too.
        lily.station_command('copy')
        lily.station_command('join', 'Casa')
        with open(cmd) as f:
            self.assertEqual(f.read().splitlines(), ['join {} {}'.format(b'Casa'.hex(), ('ab' * 32).encode().hex())] * 2)
        lily._wifi_mod.MHZ = 5180
        self.assertFalse(lily.station()['mister']['ok'])
        with self.assertRaises(LilyError):
            lily.station_command('copy')


if __name__ == '__main__':
    unittest.main()
