"""Keep PlayStation pad motion sensors away from MiSTer Main.

DualShock 4 and DualSense pads show up as three input devices: the pad, the touchpad and
"... Motion Sensors". Main drops the touchpad's extra axes, but the accelerometer reports
ABS_X/ABS_Y like a stick, and at rest gravity alone reads about 25% of full scale, so the
character walks by itself. Grabbing the sensor device (EVIOCGRAB) makes the kernel send its
events only to us; the pad and touchpad are not touched.
"""
from __future__ import annotations

import fcntl
import os
import re
import select
import threading
import time
from typing import Dict, List

EVIOCGRAB = 0x40044590  # _IOW('E', 0x90, int)
DEVICES = '/proc/bus/input/devices'
SCAN_SECONDS = 3


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
    def __init__(self):
        self.grabbed: Dict[str, int] = {}
        self._lock = threading.Lock()

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
