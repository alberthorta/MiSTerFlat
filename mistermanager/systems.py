"""Systems MiSTerManager knows how to list and launch.

Core paths and MGL slot numbers come from the Zaparoo core catalog
(ZaparooProject/zaparoo-core, mister/catalog/catalog.json), which is tested on
real hardware. Where the core source says otherwise, the core source wins
(SG-1000: the SMS core loads .sg through its F1 slot, see SMS_MiSTer SMS.sv).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class System:
    id: str
    name: str
    rbf: str                   # core path for the MGL file, relative to /media/fat
    folder: str                # under /media/fat/games
    extensions: Tuple[str, ...]
    index: int = 0             # MGL <file index>: which F option of the core gets the file
    delay: int = 1             # seconds MiSTer waits after loading the core
    subfolder: str = ''        # only this subfolder of `folder`, if set
    exclude: str = ''          # skip this subfolder of `folder`


SYSTEMS = (
    System('NES', 'NES', '_Console/NES', 'NES', ('.nes',), index=1, delay=2),
    System('SNES', 'Super Nintendo', '_Console/SNES', 'SNES', ('.sfc', '.smc', '.bin', '.bs'), delay=2),
    System('MegaDrive', 'Mega Drive', '_Console/MegaDrive', 'MegaDrive', ('.bin', '.gen', '.md'), index=1),
    System('S32X', 'Sega 32X', '_Console/S32X', 'S32X', ('.32x', '.bin'), index=1),
    System('SMS', 'Master System', '_Console/SMS', 'SMS', ('.sms',), index=1, exclude='SG-1000'),
    System('SG1000', 'SG-1000', '_Console/SMS', 'SMS', ('.sg',), index=1, subfolder='SG-1000'),
    System('GameGear', 'Game Gear', '_Console/SMS', 'SMS', ('.gg',), index=2),
    System('Gameboy', 'Game Boy', '_Console/Gameboy', 'GAMEBOY', ('.gb',), index=1, delay=2),
    System('GameboyColor', 'Game Boy Color', '_Console/Gameboy', 'GAMEBOY', ('.gbc',), index=1, delay=2),
    System('GBA', 'Game Boy Advance', '_Console/GBA', 'GBA', ('.gba',), index=1, delay=2),
    System('Atari2600', 'Atari 2600', '_Console/Atari7800', 'ATARI7800', ('.a26',), index=1),
    System('Atari7800', 'Atari 7800', '_Console/Atari7800', 'ATARI7800', ('.a78',), index=1),
    System('N64', 'Nintendo 64', '_Console/N64', 'N64', ('.n64', '.z64', '.v64'), index=1),
    System('TurboGrafx16', 'PC Engine', '_Console/TurboGrafx16', 'TGFX16', ('.pce', '.bin')),
)

# Not in SYSTEMS: arcade games are .mra files the fifo loads directly, and Neo Geo
# lists Darksoft folders by the names in romsets.xml.
ARCADE_ID = 'Arcade'
NEOGEO_ID = 'NeoGeo'
NEOGEO = System(NEOGEO_ID, 'Neo Geo', '_Console/NeoGeo', 'NEOGEO', ('.neo',), index=1)

BY_ID = {s.id: s for s in SYSTEMS + (NEOGEO,)}
