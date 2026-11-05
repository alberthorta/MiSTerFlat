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
                 cfg_file: str = CFG_FILE, cmd_file: str = CMD_FILE):
        self.tool = os.path.join(fat, 'MiSTerLily', 'misterlily_flash.py')
        self.upload_path = os.path.join(state_dir, 'misterlily-upload.bin')
        self.fw_file = fw_file
        self.board_file = board_file
        self.cfg_file = cfg_file
        self.cmd_file = cmd_file
        self._lock = threading.Lock()
        self._job: Optional[dict] = None
        self._latest: Optional[dict] = None
        self._latest_at = 0.0
        self._latest_for: Optional[str] = None  # board id the cached answer is for

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

    def set_display(self, setting: str, value) -> None:
        cfg = self.display()
        if cfg is None:
            raise LilyError('the display does not take settings (firmware 0.4.1 or later is needed)')
        limits = {'brightness': cfg['brightness_max'], 'clockfont': len(cfg['clockfonts']) - 1}
        if setting not in limits:
            raise LilyError('unknown setting')
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= limits[setting]:
            raise LilyError('value out of range')
        # Lines not taken by the daemon yet are kept, so two quick changes are both sent. Written to a
        # temporary file and renamed: the daemon never reads half a line.
        try:
            with open(self.cmd_file) as f:
                pending = f.read()
        except OSError:
            pending = ''
        with open(self.cmd_file + '.tmp', 'w') as f:
            f.write(pending + '{} {}\n'.format(setting, value))
        os.replace(self.cmd_file + '.tmp', self.cmd_file)

    def info(self, refresh: bool = False) -> dict:
        if not self.installed():
            return {'installed': False}
        out = {'installed': True, 'board': self.board(), 'model': self.model(), 'job': self.job(),
               'display': self.display(), 'power_off': self.can_power_off()}
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
