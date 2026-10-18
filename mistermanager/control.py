"""Talks to MiSTer Main and reads the state of the Linux side."""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import time
from typing import Optional
from xml.sax.saxutils import quoteattr

from .systems import ARCADE_ID, BY_ID

# MiSTer Main reads commands from this fifo (input.cpp): "load_core <.rbf|.mra|.mgl>".
CMD_FIFO = '/dev/MiSTer_cmd'
MGL_PATH = '/tmp/mistermanager.mgl'


class LaunchError(Exception):
    pass


def make_mgl(system_id: str, game_path: str) -> str:
    """MGL text that loads the system's core and then the game.

    game_path must be absolute: a relative path is read from the core's home folder,
    which is wrong for files outside it (SG-1000 games live in games/SMS/SG-1000).
    """
    system = BY_ID[system_id]
    method, index = system.method, system.index
    ext = os.path.splitext(game_path)[1].lower()
    for slot_ext, slot_method, slot_index in system.slots:
        if slot_ext == ext:
            method, index = slot_method, slot_index
    return ('<mistergamedescription>\n'
            f'    <rbf>{system.rbf}</rbf>\n'
            f'    <file delay="{system.delay}" type="{method}" index="{index}" path={quoteattr(game_path)}/>\n'
            '</mistergamedescription>\n')


def inside(path: str, root: str) -> bool:
    path, root = os.path.realpath(path), os.path.realpath(root)
    return path == root or path.startswith(root + os.sep)


def send_command(command: str, fifo: str = CMD_FIFO) -> None:
    # O_NONBLOCK: if MiSTer Main is not reading the fifo, fail instead of hanging the server.
    try:
        fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
    except OSError as e:
        raise LaunchError(f'cannot open {fifo}: {e}')
    try:
        os.write(fd, (command + '\n').encode('utf-8'))
    finally:
        os.close(fd)


class Controller:
    def __init__(self, fat: str, state_dir: str, fifo: str = CMD_FIFO, mgl_path: str = MGL_PATH):
        self.fat = fat
        self.fifo = fifo
        self.mgl_path = mgl_path
        self.recent_path = os.path.join(state_dir, 'recent.json')
        self.last_launch: Optional[dict] = None

    def launch(self, system_id: str, game: dict) -> None:
        """game comes from the library index, never straight from the client."""
        full = os.path.join(self.fat, game['path'])
        if system_id == ARCADE_ID:
            if not (inside(full, os.path.join(self.fat, '_Arcade')) and full.lower().endswith('.mra')):
                raise LaunchError('not an arcade .mra')
            target = full
        else:
            system = BY_ID.get(system_id)
            if system is None or not inside(full, os.path.join(self.fat, 'games', system.folder)):
                raise LaunchError('path outside the system folder')
            if not os.path.exists(full):
                raise LaunchError('file not found')
            with open(self.mgl_path, 'w', encoding='utf-8') as f:
                f.write(make_mgl(system_id, full))
            target = self.mgl_path
        send_command(f'load_core {target}', self.fifo)
        self.last_launch = {'system': system_id, 'name': game['name'], 'path': game['path'],
                            'art': game.get('art'), 'time': int(time.time())}
        self._remember(self.last_launch)

    def relaunch_psx(self) -> str:
        """Load the running PlayStation disc again, so the core reads its memory card from the SD.

        The PSX core mounts the card when a disc loads; a reset keeps the card it has in memory.
        """
        try:
            with open('/tmp/FULLPATH', encoding='utf-8') as f:
                full = f.read().strip()
        except OSError:
            full = ''
        # After a server restart last_launch is gone; recent.json still has it.
        last = self.last_launch or next(iter(self.recent()), None)
        if last and last.get('system') == 'PSX':
            mtime = os.stat('/tmp/FULLPATH').st_mtime if full else 0
            if not full or last.get('time', 0) >= mtime - 15:
                full = os.path.join(self.fat, last['path'])
        root = os.path.join(self.fat, 'games', 'PSX')
        if not full or not inside(full, root) or not os.path.isfile(full):
            raise LaunchError('cannot tell which PlayStation game is running')
        with open(self.mgl_path, 'w', encoding='utf-8') as f:
            f.write(make_mgl('PSX', full))
        send_command(f'load_core {self.mgl_path}', self.fifo)
        return os.path.splitext(os.path.basename(full))[0]

    def menu(self) -> None:
        send_command(f'load_core {os.path.join(self.fat, "menu.rbf")}', self.fifo)
        self.last_launch = None

    def _remember(self, entry: dict) -> None:
        recent = [r for r in self.recent() if r.get('path') != entry['path']]
        recent.insert(0, entry)
        tmp = self.recent_path + '.tmp'
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(recent[:30], f)
            os.replace(tmp, self.recent_path)
        except OSError:
            pass

    def recent(self) -> list:
        try:
            with open(self.recent_path, encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []


def _read(path: str) -> str:
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            return f.read().strip()
    except OSError:
        return ''


class Stats:
    """CPU use needs two samples of /proc/stat; keep the previous one between requests."""

    def __init__(self):
        self._cpu = None

    def cpu_percent(self) -> Optional[float]:
        line = _read('/proc/stat').split('\n', 1)[0].split()
        if not line or line[0] != 'cpu':
            return None
        values = [int(v) for v in line[1:]]
        idle, total = values[3] + (values[4] if len(values) > 4 else 0), sum(values)
        prev, self._cpu = self._cpu, (idle, total)
        if prev is None or total == prev[1]:
            return None
        return round(100.0 * (1 - (idle - prev[0]) / (total - prev[1])), 1)

    def snapshot(self, fat: str) -> dict:
        mem = {}
        for line in _read('/proc/meminfo').splitlines():
            key, _, value = line.partition(':')
            mem[key] = int(value.split()[0]) if value.split() else 0
        try:
            st = os.statvfs(fat)
            disk = {'total': st.f_blocks * st.f_frsize, 'free': st.f_bavail * st.f_frsize}
        except OSError:
            disk = None
        uptime = _read('/proc/uptime').split()
        wifi = None
        for line in _read('/proc/net/wireless').splitlines()[2:]:
            parts = line.split()
            if parts:
                wifi = {'iface': parts[0].rstrip(':'), 'quality': float(parts[2].rstrip('.')),
                        'level': float(parts[3].rstrip('.'))}
        if wifi:
            m = re.search(r'SSID: (.+)', _iw_link(wifi['iface']))
            wifi['ssid'] = m.group(1).strip() if m else ''
        return {
            'cpu': self.cpu_percent(),
            'load': _read('/proc/loadavg').split()[:3],
            'mem': {'total': mem.get('MemTotal', 0) * 1024, 'available': mem.get('MemAvailable', 0) * 1024},
            'disk': disk,
            'uptime': float(uptime[0]) if uptime else None,
            'ip': _local_ip(),
            'wifi': wifi,
            'kernel': os.uname().release,
        }


def _iw_link(iface: str) -> str:
    try:
        return subprocess.run(['iw', 'dev', iface, 'link'], capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return ''


def _local_ip() -> str:
    # No packet is sent: connecting a UDP socket only picks the outgoing interface.
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('192.0.2.1', 9))
        return s.getsockname()[0]
    except OSError:
        return ''
    finally:
        s.close()


def current(fat: str, last_launch: Optional[dict]) -> dict:
    core = _read('/tmp/CORENAME')
    info = {'core': core, 'rbf': _read('/tmp/RBFNAME'), 'game': None}
    if core and core.upper() != 'MENU':
        # Main writes FULLPATH when a file is picked in the OSD (also for our MGL launches).
        # For arcade .mra launches it does not, so our own record is the better source there.
        try:
            picked = os.stat('/tmp/FULLPATH').st_mtime
        except OSError:
            picked = 0
        if last_launch and last_launch['time'] >= picked - 15:
            info['game'] = last_launch['name']
        elif picked:
            info['game'] = os.path.splitext(os.path.basename(_read('/tmp/FULLPATH')))[0]
    return info
