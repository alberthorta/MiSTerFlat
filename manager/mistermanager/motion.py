"""Connected input devices, and keeping PlayStation pad motion sensors away from MiSTer Main.

DualShock 4 and DualSense pads show up as three input devices: the pad, the touchpad and
"... Motion Sensors". Main drops the touchpad's extra axes, but the accelerometer reports
ABS_X/ABS_Y like a stick, and at rest gravity alone reads about 25% of full scale, so the
character walks by itself. Grabbing the sensor device (EVIOCGRAB) makes the kernel send its
events only to us; the pad and touchpad are not touched.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import select
import subprocess
import threading
import time
from typing import Dict, List, Set

EVIOCGRAB = 0x40044590  # _IOW('E', 0x90, int)
DEVICES = '/proc/bus/input/devices'
POWER = '/sys/class/power_supply'
SCAN_SECONDS = 3
BUSES = {'0003': 'USB', '0005': 'Bluetooth'}


def parse_devices(text: str) -> List[dict]:
    out = []
    for block in text.strip().split('\n\n'):
        fields = {}
        for line in block.splitlines():
            key, _, value = line.partition(': ')
            if key == 'I':
                fields.update(dict(part.split('=', 1) for part in value.split() if '=' in part))
            elif key == 'N':
                fields['name'] = value.partition('=')[2].strip('"')
            elif key in ('U', 'H'):
                k, _, v = value.partition('=')
                fields[k.lower()] = v.strip()
        if fields.get('name'):
            out.append(fields)
    return out


def _kind(handlers: str, name: str) -> str:
    if name.endswith('Motion Sensors'):
        return 'motion sensors'
    if name.endswith('Touchpad'):
        return 'touchpad'
    words = handlers.split()
    if any(w.startswith('js') for w in words):
        return 'gamepad'
    if any(w.startswith('mouse') for w in words):
        return 'mouse'
    if 'kbd' in words:
        return 'keyboard'
    return 'other'


def controllers(text: str, power_root: str = POWER) -> List[dict]:
    """Physical devices, each with the input devices Linux made for it."""
    groups: Dict[tuple, dict] = {}
    for dev in parse_devices(text):
        if dev['name'] == 'MiSTer virtual input':
            continue
        key = (dev.get('Vendor'), dev.get('Product'), dev.get('uniq') or dev['name'])
        group = groups.get(key)
        if group is None:
            group = groups[key] = {'name': dev['name'], 'bus': BUSES.get(dev.get('Bus', ''), dev.get('Bus', '')),
                                   'id': f"{dev.get('Vendor', '')}:{dev.get('Product', '')}",
                                   'address': dev.get('uniq', ''), 'parts': []}
        node = next((h for h in dev.get('handlers', '').split() if h.startswith('event')), '')
        group['parts'].append({'kind': _kind(dev.get('handlers', ''), dev['name']),
                               'node': '/dev/input/' + node if node else ''})
        if len(dev['name']) < len(group['name']):
            group['name'] = dev['name']
    for group in groups.values():
        battery = os.path.join(power_root, 'ps-controller-battery-' + group['address'].lower())
        try:
            with open(os.path.join(battery, 'capacity')) as f:
                group['battery'] = int(f.read().strip())
            with open(os.path.join(battery, 'status')) as f:
                group['charging'] = f.read().strip() == 'Charging'
        except (OSError, ValueError):
            pass
    return list(groups.values())


def sensor_nodes(text: str) -> List[str]:
    """/dev/input/eventN of every device whose name ends in "Motion Sensors"."""
    nodes = []
    for block in text.split('\n\n'):
        name = re.search(r'^N: Name="(.*)"$', block, re.M)
        handlers = re.search(r'^H: Handlers=(.*)$', block, re.M)
        if name and handlers and name.group(1).endswith('Motion Sensors'):
            for h in handlers.group(1).split():
                if h.startswith('event'):
                    nodes.append('/dev/input/' + h)
    return nodes


def wanted_nodes(text: str, motion: bool, ignored: Set[str]) -> Set[str]:
    """Event nodes to hold: pad motion sensors (if motion) and every device of an ignored address."""
    nodes = set(sensor_nodes(text)) if motion else set()
    for dev in parse_devices(text):
        if dev.get('uniq', '').lower() in ignored:
            nodes.update('/dev/input/' + h for h in dev.get('handlers', '').split() if h.startswith('event'))
    return nodes


class MotionBlocker:
    """Holds (EVIOCGRAB) the input devices MiSTer Main must not see.

    Two kinds: the motion sensors of PlayStation pads, and devices the user chose to ignore by
    address. An ignored Bluetooth device is also blocked in bluez, but that block is lost when
    the device pairs again (it happened with a device that is always pairable), so the grab
    is what keeps it out, and the block is applied again each time the device shows up.
    """

    def __init__(self, state_path: str = ''):
        self.grabbed: Dict[str, int] = {}
        self._lock = threading.Lock()
        self.state_path = state_path
        self.enabled = True
        self.ignored: Dict[str, str] = {}  # address -> name
        self._blocked_at: Dict[str, float] = {}
        try:
            with open(state_path, encoding='utf-8') as f:
                data = json.load(f)
            self.enabled = bool(data.get('block_motion_sensors', True))
            self.ignored = {d['address'].lower(): d.get('name', '') for d in data.get('ignored', [])}
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass

    def _save(self) -> None:
        if not self.state_path:
            return
        tmp = self.state_path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'block_motion_sensors': self.enabled,
                       'ignored': [{'address': a, 'name': n} for a, n in sorted(self.ignored.items())]}, f)
        os.replace(tmp, self.state_path)

    def _release_all(self) -> None:
        for fd in self.grabbed.values():
            os.close(fd)  # closing the fd releases the grab
        self.grabbed.clear()

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.enabled = enabled
            self._release_all()  # the next scan grabs again what is still wanted
            self._save()

    def set_ignored(self, address: str, name: str, ignore: bool) -> None:
        address = address.lower()
        if not re.fullmatch(r'[0-9a-f]{2}(:[0-9a-f]{2}){5}', address):
            raise ValueError('bad device address')
        with self._lock:
            if ignore:
                self.ignored[address] = name
            else:
                self.ignored.pop(address, None)
                self._blocked_at.pop(address, None)
                bluetoothctl('unblock', address)
            self._release_all()
            self._save()

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def status(self) -> List[str]:
        with self._lock:
            return sorted(self.grabbed)

    def _scan(self) -> None:
        try:
            with open(DEVICES, encoding='utf-8', errors='replace') as f:
                text = f.read()
        except OSError:
            return
        with self._lock:
            wanted = wanted_nodes(text, self.enabled, set(self.ignored))
            for dev in parse_devices(text):
                address = dev.get('uniq', '').lower()
                if address in self.ignored and dev.get('Bus') == '0005' and \
                        time.time() - self._blocked_at.get(address, 0) > 30:
                    self._blocked_at[address] = time.time()
                    bluetoothctl('block', address)
            for node in list(self.grabbed):
                if node not in wanted:  # device gone; the node may come back as another device
                    os.close(self.grabbed.pop(node))
            for node in wanted - set(self.grabbed):
                try:
                    fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
                except OSError:
                    continue
                try:
                    fcntl.ioctl(fd, EVIOCGRAB, 1)
                except OSError:
                    os.close(fd)
                    continue
                self.grabbed[node] = fd

    def _run(self) -> None:
        next_scan = 0.0
        while True:
            if time.time() >= next_scan:
                self._scan()
                next_scan = time.time() + SCAN_SECONDS
            with self._lock:
                fds = list(self.grabbed.values())
            if not fds:
                time.sleep(SCAN_SECONDS)
                continue
            # Drain the events so the kernel buffer never fills; their content is not used.
            try:
                ready, _, _ = select.select(fds, [], [], 1.0)
            except (OSError, ValueError):  # an fd was closed by set_enabled/set_ignored
                continue
            for fd in ready:
                try:
                    os.read(fd, 4096)
                except OSError:
                    pass


def bluetoothctl(action: str, address: str) -> None:
    try:
        subprocess.run(['bluetoothctl', action, address.upper()], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass
