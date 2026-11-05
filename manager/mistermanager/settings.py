"""General MiSTer settings: volume, a few MiSTer.ini keys and the custom video presets.

MiSTer Main reads MiSTer.ini and the preset files when a core loads, so changes here
apply from the next core load (or a reboot).
"""
from __future__ import annotations

import os
import re
import shutil
import time
from typing import Dict, List, Optional

from .control import send_command

# MiSTer.ini keys the page may change, with their allowed values. Only 1080p60 video modes
# are offered and sync options are left out: a wrong value there can leave the screen black.
INI_KEYS = {
    'vscale_mode': {'0': 'Fit to screen height', '1': 'Integer scale', '2': 'Steps of 0.5',
                    '3': 'Steps of 0.25', '4': 'Integer, core aspect', '5': 'Integer, display aspect'},
    'preset_default': None,  # any preset under Presets/, checked against the list
    # Same picture; CVT-RB timing has smaller blanking, which some PC monitors lock onto better.
    'video_mode': {'8': '1920x1080 60 Hz, TV timing (CEA)', '1920,1080,60': '1920x1080 60 Hz, PC timing (CVT-RB)'},
    # DVI drops audio and the HDMI info frames; some monitors resync less often with it.
    'dvi_mode': {'0': 'HDMI (with audio)', '1': 'DVI (no audio over HDMI)'},
}
GLOBAL_ONLY = ('vscale_mode', 'video_mode', 'dvi_mode')
INI_SECTIONS = ('MiSTer', 'arcade', 'arcade_vertical')
PRESET_FIELDS = ('hfilter', 'vfilter', 'sfilter', 'gamma', 'mask', 'maskmode')
MASK_MODES = ('off', '1x', '2x', '1x rotated', '2x rotated')
CUSTOM = 'Custom'
VERTICAL_SUFFIX = ' - Vertical'
BACKUPS_KEPT = 10


class SettingsError(Exception):
    pass


def _list_files(root: str, exts=('.txt',)) -> List[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith('.'))
        for fn in sorted(filenames):
            if fn.lower().endswith(exts) and not fn.startswith('.'):
                out.append(os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, '/'))
    return out


# --- MiSTer.ini -------------------------------------------------------------------------

def _split_lines(text: str) -> List[str]:
    # keepends: the stock MiSTer.ini mixes CRLF and LF, and both must survive an edit.
    return text.splitlines(keepends=True)


def _eol(line: str) -> str:
    return '\r\n' if line.endswith('\r\n') else '\n'


def ini_get(text: str, section: str, key: str) -> Optional[str]:
    current = None
    for line in _split_lines(text):
        stripped = line.strip()
        m = re.match(r'^\[([^\]]+)\]', stripped)
        if m:
            current = m.group(1)
            continue
        if current and current.lower() == section.lower():
            m = re.match(r'^' + re.escape(key) + r'\s*=\s*([^;]*)', stripped, re.I)
            if m:
                return m.group(1).strip()
    return None


def ini_set(text: str, section: str, key: str, value: str) -> str:
    """Set key in section, keeping comments after the value, and add what is missing."""
    lines = _split_lines(text)
    current, start, end, found = None, None, None, None
    for i, line in enumerate(lines):
        m = re.match(r'^\[([^\]]+)\]', line.strip())
        if m:
            if start is not None and end is None:
                end = i
            current = m.group(1)
            if current.lower() == section.lower():
                start = i
            continue
        if start is not None and end is None and re.match(r'^' + re.escape(key) + r'\s*=', line.strip(), re.I):
            found = i
    if start is not None and end is None:
        end = len(lines)
    if found is not None:
        line = lines[found]
        m = re.match(r'^(\s*' + re.escape(key) + r'\s*=\s*)([^;\r\n]*?)(\s*;[^\r\n]*)?(\r?\n)?$', line, re.I)
        lines[found] = m.group(1) + value + (m.group(3) or '') + (m.group(4) or '')
        return ''.join(lines)
    eol = _eol(lines[0]) if lines else '\n'
    if start is None:
        if lines and not lines[-1].endswith('\n'):
            lines[-1] += eol
        lines += [eol, f'[{section}]{eol}', f'{key}={value}{eol}']
        return ''.join(lines)
    # Put it right after the section header, before any commented example of the same key.
    lines.insert(start + 1, f'{key}={value}{_eol(lines[start])}')
    return ''.join(lines)


def ini_del(text: str, section: str, key: str) -> str:
    """Remove key from section, so the section falls back to the value of [MiSTer]."""
    out, current = [], None
    for line in _split_lines(text):
        m = re.match(r'^\[([^\]]+)\]', line.strip())
        if m:
            current = m.group(1)
        elif current and current.lower() == section.lower() and \
                re.match(r'^' + re.escape(key) + r'\s*=', line.strip(), re.I):
            continue
        out.append(line)
    return ''.join(out)


class Settings:
    def __init__(self, fat: str, state_dir: str, fifo: str):
        self.fat = fat
        self.fifo = fifo
        self.ini_path = os.path.join(fat, 'MiSTer.ini')
        self.backup_dir = os.path.join(state_dir, 'backups')

    # volume
    def volume(self) -> dict:
        try:
            with open(os.path.join(self.fat, 'config', 'Volume.dat'), 'rb') as f:
                raw = f.read(1)
        except OSError:
            raw = b''
        att = raw[0] if raw else 0
        # Volume.dat holds the attenuation (0 = loudest) and bit 4 for mute (audio.cpp).
        return {'level': 7 - (att & 7), 'muted': bool(att & 0x10), 'levels': 8}

    def set_volume(self, level: Optional[int] = None, mute: Optional[bool] = None) -> None:
        if mute is not None:
            send_command('volume mute' if mute else 'volume unmute', self.fifo)
        if level is not None:
            if not 0 <= int(level) <= 7:
                raise SettingsError('volume level must be 0-7')
            send_command(f'volume {int(level)}', self.fifo)

    # MiSTer.ini
    def _read_ini(self) -> str:
        try:
            with open(self.ini_path, encoding='utf-8', errors='surrogateescape', newline='') as f:
                return f.read()
        except OSError:
            return ''

    def presets(self) -> List[str]:
        return [p[:-4] for p in _list_files(os.path.join(self.fat, 'Presets'), ('.ini',))]

    def ini(self) -> dict:
        text = self._read_ini()
        return {'vscale_mode': ini_get(text, 'MiSTer', 'vscale_mode') or '0',
                'video_mode': ini_get(text, 'MiSTer', 'video_mode') or '',
                'dvi_mode': ini_get(text, 'MiSTer', 'dvi_mode') or '0',
                'preset_default': {s: ini_get(text, s, 'preset_default') or '' for s in INI_SECTIONS}}

    def set_ini(self, section: str, key: str, value: str) -> None:
        if section not in INI_SECTIONS or key not in INI_KEYS:
            raise SettingsError('setting not allowed')
        allowed = INI_KEYS[key]
        if allowed is not None and value not in allowed:
            raise SettingsError('value not allowed')
        if key == 'preset_default' and value and value not in self.presets():
            raise SettingsError('unknown preset')
        if key in GLOBAL_ONLY and section != 'MiSTer':
            raise SettingsError(f'{key} is set in [MiSTer] only')
        text = self._read_ini()
        if not text:
            raise SettingsError('MiSTer.ini not found')
        self._backup()
        new = ini_set(text, section, key, value) if value else ini_del(text, section, key)
        tmp = self.ini_path + '.mm.tmp'
        with open(tmp, 'w', encoding='utf-8', errors='surrogateescape', newline='') as f:
            f.write(new)
        os.replace(tmp, self.ini_path)

    def _backup(self) -> None:
        os.makedirs(self.backup_dir, exist_ok=True)
        shutil.copy2(self.ini_path, os.path.join(self.backup_dir, time.strftime('MiSTer.ini.%Y%m%d-%H%M%S')))
        old = sorted(f for f in os.listdir(self.backup_dir) if f.startswith('MiSTer.ini.'))
        for name in old[:-BACKUPS_KEPT]:
            os.remove(os.path.join(self.backup_dir, name))

    # presets
    def options(self) -> dict:
        return {'filters': _list_files(os.path.join(self.fat, 'Filters')),
                'gamma': _list_files(os.path.join(self.fat, 'Gamma')),
                'masks': _list_files(os.path.join(self.fat, 'Shadow_Masks')),
                'maskmodes': list(MASK_MODES),
                'vscale_modes': INI_KEYS['vscale_mode'],
                'video_modes': INI_KEYS['video_mode'],
                'dvi_modes': INI_KEYS['dvi_mode'],
                'presets': self.presets()}

    def _preset_path(self, name: str) -> str:
        if not re.fullmatch(r'[\w .,()&\'-]+', name):
            raise SettingsError('bad preset name')
        return os.path.join(self.fat, 'Presets', CUSTOM, name + '.ini')

    def custom_presets(self) -> Dict[str, dict]:
        out = {}
        root = os.path.join(self.fat, 'Presets', CUSTOM)
        for rel in _list_files(root, ('.ini',)):
            name = rel[:-4]
            if '/' in name or name.endswith(VERTICAL_SUFFIX):
                continue
            out[name] = self.read_preset(name)
        return out

    def read_preset(self, name: str) -> dict:
        fields = {}
        with open(self._preset_path(name), encoding='utf-8', errors='replace') as f:
            for line in f:
                key, sep, value = line.strip().partition('=')
                if sep and key in PRESET_FIELDS:
                    fields[key] = value.strip()
        return fields

    def write_preset(self, name: str, fields: dict) -> None:
        """Write a custom preset and its " - Vertical" twin, if there is one."""
        opts = self.options()
        valid = {'hfilter': opts['filters'], 'vfilter': opts['filters'], 'sfilter': opts['filters'] + ['same'],
                 'gamma': opts['gamma'] + ['off'], 'mask': opts['masks'], 'maskmode': opts['maskmodes']}
        clean = {}
        for key in PRESET_FIELDS:
            value = str(fields.get(key, '')).strip()
            if not value:
                continue
            if key in ('vfilter', 'sfilter') and value == 'same':
                clean[key] = value
            elif value not in valid[key]:
                raise SettingsError(f'{key}: unknown value')
            else:
                clean[key] = value
        path = self._preset_path(name)
        if not os.path.exists(path):
            raise SettingsError('only existing presets in Presets/Custom can be changed')
        self._write_preset_file(path, clean)
        vertical = self._preset_path(name + VERTICAL_SUFFIX)
        if os.path.exists(vertical):
            # On a rotated screen the scanlines run the other way: swap the two filters.
            v = dict(clean)
            if clean.get('vfilter') and clean['vfilter'] != 'same' and clean.get('hfilter'):
                v['hfilter'], v['vfilter'] = clean['vfilter'], clean['hfilter']
            if clean.get('maskmode') in ('1x', '2x'):
                v['maskmode'] = clean['maskmode'] + ' rotated'
            self._write_preset_file(vertical, {k: x for k, x in v.items() if x})

    @staticmethod
    def _write_preset_file(path: str, fields: dict) -> None:
        comments = []
        try:
            with open(path, encoding='utf-8', errors='replace') as f:
                comments = [line.rstrip('\r\n') for line in f if line.startswith('#')]
        except OSError:
            pass
        body = comments + [f'{k}={fields[k]}' for k in PRESET_FIELDS if k in fields]
        tmp = path + '.mm.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write('\n'.join(body) + '\n')
        os.replace(tmp, path)
