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
import threading
import time
from typing import Dict, List

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


class MotionBlocker:
    def __init__(self, state_path: str = ''):
        self.grabbed: Dict[str, int] = {}
        self._lock = threading.Lock()
        self.state_path = state_path
        self.enabled = True
        try:
            with open(state_path, encoding='utf-8') as f:
                self.enabled = bool(json.load(f).get('block_motion_sensors', True))
        except (OSError, ValueError):
            pass

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.enabled = enabled
            if not enabled:
                for fd in self.grabbed.values():
                    os.close(fd)  # closing the fd releases the grab
                self.grabbed.clear()
        if self.state_path:
            tmp = self.state_path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump({'block_motion_sensors': enabled}, f)
            os.replace(tmp, self.state_path)

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def status(self) -> List[str]:
        with self._lock:
            return sorted(self.grabbed)

    def _scan(self) -> None:
        try:
            with open(DEVICES, encoding='utf-8', errors='replace') as f:
                wanted = set(sensor_nodes(f.read()))
        except OSError:
            return
        with self._lock:
            if not self.enabled:
                return
            for node in list(self.grabbed):
                if node not in wanted:  # pad switched off; the node may come back as another device
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
            ready, _, _ = select.select(fds, [], [], 1.0)
            for fd in ready:
                try:
                    os.read(fd, 4096)
                except OSError:
                    pass
