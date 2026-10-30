"""MiSTerLily display: firmware version and firmware updates.

The work is done by MiSTerLily's own misterlily_flash.py, so the Scripts menu and this page flash
the same way. It checks the file, stops the MiSTerLily daemon (which holds the USB port), flashes
with esptool and starts the daemon again. Its output is one event per line (STEP, PROGRESS, DONE,
ERROR); a flash runs in the background and the page polls the job.

The daemon writes the version of the connected board to /tmp/misterlily_fw.
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
# app0 in the board's partition table; misterlily_flash.py refuses larger files too.
MAX_FIRMWARE = 0x640000
LATEST_CACHE_SECONDS = 600


class LilyError(Exception):
    pass


class Lily:
    def __init__(self, fat: str, state_dir: str, fw_file: str = FW_FILE):
        self.tool = os.path.join(fat, 'MiSTerLily', 'misterlily_flash.py')
        self.upload_path = os.path.join(state_dir, 'misterlily-upload.bin')
        self.fw_file = fw_file
        self._lock = threading.Lock()
        self._job: Optional[dict] = None
        self._latest: Optional[dict] = None
        self._latest_at = 0.0

    def installed(self) -> bool:
        return os.path.isfile(self.tool)

    def board(self) -> Optional[str]:
        try:
            with open(self.fw_file) as f:
                return f.read().strip() or None
        except OSError:
            return None

    def latest(self, refresh: bool = False) -> dict:
        """{'latest': version or None, 'error': text or None}; asks GitHub at most every 10 min."""
        if refresh or self._latest is None or time.monotonic() - self._latest_at > LATEST_CACHE_SECONDS:
            try:
                out = subprocess.run([sys.executable, self.tool, 'check'], stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, timeout=60).stdout
                data = json.loads(out.decode('utf-8', 'replace').strip().splitlines()[-1])
                self._latest = {'latest': data.get('latest'), 'error': data.get('error')}
            except (OSError, ValueError, IndexError, subprocess.SubprocessError) as e:
                self._latest = {'latest': None, 'error': 'could not run misterlily_flash.py: {}'.format(e)}
            self._latest_at = time.monotonic()
        return dict(self._latest)

    def info(self, refresh: bool = False) -> dict:
        if not self.installed():
            return {'installed': False}
        out = {'installed': True, 'board': self.board(), 'job': self.job()}
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
