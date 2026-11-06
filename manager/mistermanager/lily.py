"""MiSTerLily display: firmware version, firmware updates and the display's own settings.

The work is done by MiSTerLily's own misterlily_flash.py, so the Scripts menu and this page flash
the same way. It checks the file, stops the MiSTerLily daemon (which holds the USB port), flashes
with esptool and starts the daemon again. Its output is one event per line (STEP, PROGRESS, DONE,
ERROR); a flash runs in the background and the page polls the job.

The daemon writes the firmware version of the connected board to /tmp/misterlily_fw and its
CMDHWINF id to /tmp/misterlily_board. misterlily_flash.py picks the firmware for that board.

Display settings (firmware 0.4.1 and later) also go through the daemon, which holds the port: it
writes the display's settings as JSON to /tmp/misterlily_cfg every few seconds, and sends the lines
of /tmp/misterlily_cmd ("brightness 5", "clockfont 4") to the display.

Power off (Waveshare board, firmware 0.5.0 and later, with the power relay): the same path as the
hold on the display's RESET button. With /run/misterlily_poweroff in place the daemon is not
stopped by the shutdown scripts; on the last SIGTERM it tells the display (MDSPOWER,down), and the
display opens the relay when Linux has finished.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from typing import Optional

FW_FILE = '/tmp/misterlily_fw'
BOARD_FILE = '/tmp/misterlily_board'
CFG_FILE = '/tmp/misterlily_cfg'
CMD_FILE = '/tmp/misterlily_cmd'
POWEROFF_FLAG = '/run/misterlily_poweroff'
# The display board's own Wi-Fi (firmware 0.6.0+), through the daemon: MiSTerLily's display_wifi.py.
STA_FILE = '/tmp/misterlily_sta'
STA_CMD_FILE = '/tmp/misterlily_sta_cmd'
RELAY_BOARDS = {'HWWSTLCD2'}
RELAY_SINCE = (0, 5, 0)
MODELS = {'HWTDISPS3': 'LILYGO T-Display-S3', 'HWWSTLCD2': 'Waveshare ESP32-S3-Touch-LCD-2'}
# app0 in the board's partition table; misterlily_flash.py refuses larger files too.
MAX_FIRMWARE = 0x640000
LATEST_CACHE_SECONDS = 600


class LilyError(Exception):
    pass


class Lily:
    def __init__(self, fat: str, state_dir: str, fw_file: str = FW_FILE, board_file: str = BOARD_FILE,
                 cfg_file: str = CFG_FILE, cmd_file: str = CMD_FILE, sta_file: str = STA_FILE,
                 sta_cmd_file: str = STA_CMD_FILE):
        self.tool = os.path.join(fat, 'MiSTerLily', 'misterlily_flash.py')
        self.upload_path = os.path.join(state_dir, 'misterlily-upload.bin')
        self.fw_file = fw_file
        self.board_file = board_file
        self.cfg_file = cfg_file
        self.cmd_file = cmd_file
        self.sta_file = sta_file
        self.sta_cmd_file = sta_cmd_file
        self._lock = threading.Lock()
        self._job: Optional[dict] = None
        self._latest: Optional[dict] = None
        self._latest_at = 0.0
        self._latest_for: Optional[str] = None  # board id the cached answer is for
        # Networks for the display's Wi-Fi, scanned by the MiSTer's own dongle when it has one: the
        # two sit side by side and see the same networks, and the board's scan is the weak part.
        self.wifi_module = os.path.join(fat, 'MiSTerLily', 'wifi.py')
        self._scan: dict = {'running': False, 'networks': None}
        self._wifi_mod = None
        self._wifi_mtime = 0.0

    def installed(self) -> bool:
        return os.path.isfile(self.tool)

    @staticmethod
    def _read(path: str) -> Optional[str]:
        try:
            with open(path) as f:
                return f.read().strip() or None
        except OSError:
            return None

    def board(self) -> Optional[str]:
        return self._read(self.fw_file)

    def model(self) -> Optional[str]:
        board_id = self._read(self.board_file)
        return MODELS.get(board_id, board_id)

    def _station_file(self) -> Optional[dict]:
        """The display board's own Wi-Fi, or None (no such board, or an older firmware)."""
        try:
            with open(self.sta_file) as f:
                sta = json.load(f)
            return {'state': str(sta['state']), 'ip': str(sta['ip']), 'rssi': int(sta['rssi']),
                    'ssid': str(sta['ssid']), 'scanning': bool(sta['scanning']), 'error': str(sta.get('error', '')),
                    'networks': [{'ssid': str(n['ssid']), 'rssi': int(n['rssi']), 'secure': bool(n['secure'])}
                                 for n in sta['networks']]}
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _mister_wifi(self):
        """MiSTerLily's wifi.py, if the MiSTer has a Wi-Fi dongle; else None."""
        try:
            mtime = os.stat(self.wifi_module).st_mtime
            if self._wifi_mod is None or self._wifi_mtime != mtime:
                import importlib.util
                spec = importlib.util.spec_from_file_location('misterlily_wifi', self.wifi_module)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                self._wifi_mod, self._wifi_mtime = mod, mtime
            return self._wifi_mod if self._wifi_mod.dongle_present() else None
        except (OSError, ImportError, AttributeError, SyntaxError):
            return None

    def _scan_on_mister(self, wifi) -> None:
        # The board has 2.4 GHz only; MiSTerLily before 0.6.0 lists both bands.
        known = getattr(wifi, 'saved_key', lambda ssid: None)
        try:
            scan = getattr(wifi, 'scan_24ghz', None) or wifi.scan
            nets = [{'ssid': ssid.decode('utf-8', 'replace'), 'rssi': int(signal), 'secure': bool(secure),
                     'mister': bool(linked), 'known': known(ssid) is not None}
                    for ssid, signal, secure, linked in scan()]
            nets = [n for n in nets if 0 < len(n['ssid'].encode('utf-8')) <= 32]
        except Exception:  # noqa: BLE001 - iw missing or failed: fall back to the board's own scan
            nets = None
        with self._lock:
            self._scan = {'running': False, 'networks': nets}
        if nets is None:
            self._write_sta_command('scan')

    def _mister_network(self, wifi) -> Optional[dict]:
        """The network the MiSTer is on, and whether the board can take it as it is."""
        if not wifi or not hasattr(wifi, 'link'):
            return None
        here = wifi.link()
        if not here:
            return None
        ssid, mhz = here
        out = {'ssid': ssid.decode('utf-8', 'replace'), 'ok': False, 'reason': ''}
        if mhz >= 3000:
            out['reason'] = 'The MiSTer is on 5 GHz; the display has 2.4 GHz only. Pick a 2.4 GHz network below.'
        elif wifi.saved_key(ssid) is None:
            out['reason'] = 'The MiSTer has no saved password for this network.'
        else:
            out['ok'] = True
        return out

    def station(self) -> Optional[dict]:
        sta = self._station_file()
        if sta is None:
            return None
        sta['mister'] = self._mister_network(self._mister_wifi())
        with self._lock:
            scan = dict(self._scan)
        if scan['running'] or scan['networks'] is not None:
            sta['scanning'] = scan['running']
            sta['networks'] = scan['networks'] or []
        return sta

    def _write_sta_command(self, line: str) -> None:
        # As for the settings: pending lines are kept, and the file is renamed into place.
        try:
            with open(self.sta_cmd_file) as f:
                pending = f.read()
        except OSError:
            pending = ''
        fd = os.open(self.sta_cmd_file + '.tmp', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(pending + line + '\n')
        os.replace(self.sta_cmd_file + '.tmp', self.sta_cmd_file)

    def station_command(self, action: str, ssid: str = '', password: str = '') -> None:
        if self._station_file() is None:
            raise LilyError('the display has no Wi-Fi of its own (Waveshare board, firmware 0.6.0 or later)')
        if action == 'scan':
            wifi = self._mister_wifi()
            with self._lock:
                if self._scan['running']:
                    return
                self._scan = {'running': bool(wifi), 'networks': None}
            if wifi:
                threading.Thread(target=self._scan_on_mister, args=(wifi,), daemon=True).start()
                return
        if action == 'copy':
            # The MiSTer's own network with its saved key: nothing to scan or type.
            wifi = self._mister_wifi()
            net = self._mister_network(wifi)
            if not net:
                raise LilyError('the MiSTer is not on a Wi-Fi network')
            if not net['ok']:
                raise LilyError(net['reason'])
            action, ssid = 'join', net['ssid']
            password = wifi.saved_key(ssid.encode('utf-8'))
        elif action == 'join' and not password:
            # A network the MiSTer knows: its saved key (a 64-hex PSK or the passphrase).
            wifi = self._mister_wifi()
            if wifi and hasattr(wifi, 'saved_key'):
                password = wifi.saved_key(ssid.encode('utf-8')) or ''
        if action in ('scan', 'forget', 'status'):
            line = action
        elif action == 'join':
            ssid_b, pass_b = ssid.encode('utf-8'), password.encode('utf-8')
            if not 0 < len(ssid_b) <= 32:
                raise LilyError('network name missing or too long')
            psk = len(pass_b) == 64 and all(c in b'0123456789abcdefABCDEF' for c in pass_b)
            if pass_b and not (8 <= len(pass_b) <= 63 or psk):
                raise LilyError('a Wi-Fi password has 8 to 63 characters')
            line = 'join {} {}'.format(ssid_b.hex(), pass_b.hex()).rstrip()
        else:
            raise LilyError('unknown action')
        self._write_sta_command(line)

    def can_power_off(self) -> bool:
        """The connected board has the power relay. Whether a relay is wired cannot be seen from here."""
        if not self.installed() or self._read(self.board_file) not in RELAY_BOARDS:
            return False
        try:
            return tuple(int(n) for n in (self.board() or '').split('.')[:3]) >= RELAY_SINCE
        except ValueError:
            return False

    def power_off(self, flag: str = POWEROFF_FLAG) -> None:
        if not self.can_power_off():
            raise LilyError('power off needs the Waveshare display with firmware 0.5.0 or later')
        with open(flag, 'w'):
            pass
        os.sync()

    def latest(self, refresh: bool = False) -> dict:
        """{'latest': version or None, 'error': text or None}; asks GitHub at most every 10 min."""
        board_id = self._read(self.board_file)
        if (refresh or self._latest is None or board_id != self._latest_for
                or time.monotonic() - self._latest_at > LATEST_CACHE_SECONDS):
            try:
                out = subprocess.run([sys.executable, self.tool, 'check'], stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, timeout=60).stdout
                data = json.loads(out.decode('utf-8', 'replace').strip().splitlines()[-1])
                self._latest = {'latest': data.get('latest'), 'error': data.get('error')}
            except (OSError, ValueError, IndexError, subprocess.SubprocessError) as e:
                self._latest = {'latest': None, 'error': 'could not run misterlily_flash.py: {}'.format(e)}
            self._latest_at = time.monotonic()
            self._latest_for = board_id
        return dict(self._latest)

    def display(self) -> Optional[dict]:
        """{'brightness', 'brightness_max', 'clockfont', 'clockfonts'}, or None (no display, or a
        firmware or daemon without settings)."""
        try:
            with open(self.cfg_file) as f:
                cfg = json.load(f)
            return {'brightness': int(cfg['brightness']), 'brightness_max': int(cfg['brightness_max']),
                    'clockfont': int(cfg['clockfont']), 'clockfonts': [str(n) for n in cfg['clockfonts']]}
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def restart_display(self) -> None:
        if not self.board():
            raise LilyError('the display is not connected')
        self._write_cmd('restart')

    def _write_cmd(self, line: str) -> None:
        # Lines not taken by the daemon yet are kept, so two quick changes are both sent. Written to a
        # temporary file and renamed: the daemon never reads half a line.
        try:
            with open(self.cmd_file) as f:
                pending = f.read()
        except OSError:
            pending = ''
        with open(self.cmd_file + '.tmp', 'w') as f:
            f.write(pending + line + '\n')
        os.replace(self.cmd_file + '.tmp', self.cmd_file)

    def set_display(self, setting: str, value) -> None:
        cfg = self.display()
        if cfg is None:
            raise LilyError('the display does not take settings (firmware 0.4.1 or later is needed)')
        limits = {'brightness': cfg['brightness_max'], 'clockfont': len(cfg['clockfonts']) - 1}
        if setting not in limits:
            raise LilyError('unknown setting')
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= limits[setting]:
            raise LilyError('value out of range')
        self._write_cmd('{} {}'.format(setting, value))

    def info(self, refresh: bool = False) -> dict:
        if not self.installed():
            return {'installed': False}
        out = {'installed': True, 'board': self.board(), 'model': self.model(), 'job': self.job(),
               'display': self.display(), 'power_off': self.can_power_off(), 'station': self.station()}
        out.update(self.latest(refresh))
        return out

    def job(self) -> Optional[dict]:
        with self._lock:
            return dict(self._job, log=list(self._job['log'])) if self._job else None

    def flash_latest(self):
        self._start(['--latest'])

    def flash_file(self, data: bytes):
        if not data or len(data) > MAX_FIRMWARE:
            raise LilyError('file is empty or too large for the display')
        with open(self.upload_path, 'wb') as f:
            f.write(data)
        self._start([self.upload_path])

    def _start(self, args):
        if not self.installed():
            raise LilyError('MiSTerLily is not installed')
        with self._lock:
            if self._job and self._job['running']:
                raise LilyError('a flash is already running')
            self._job = {'running': True, 'progress': 0, 'step': 'starting', 'done': None, 'error': None,
                         'log': []}
        proc = subprocess.Popen([sys.executable, self.tool, 'flash'] + args, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        threading.Thread(target=self._follow, args=(proc,), daemon=True).start()

    def _follow(self, proc):
        for raw in proc.stdout:
            kind, _, text = raw.decode('utf-8', 'replace').strip().partition(' ')
            with self._lock:
                job = self._job
                job['log'] = (job['log'] + [kind + ' ' + text])[-30:]
                if kind == 'PROGRESS' and text.isdigit():
                    job['progress'] = int(text)
                elif kind == 'STEP':
                    job['step'] = text
                elif kind == 'DONE':
                    job['done'] = text
                elif kind == 'ERROR':
                    job['error'] = text
        code = proc.wait()
        with self._lock:
            job = self._job
            job['running'] = False
            if code != 0 and not job['error']:
                job['error'] = 'misterlily_flash.py stopped with exit code {}'.format(code)
        try:
            os.remove(self.upload_path)
        except OSError:
            pass
