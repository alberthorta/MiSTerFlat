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
    docs: str = ''             # folder under /media/fat/docs with update_all's game artwork
    method: str = 'f'          # MGL <file type>: f loads a file, s mounts a disc image
    # (extension, method, index) for cores that take each file type in a different OSD slot
    slots: Tuple[Tuple[str, str, int], ...] = ()


SYSTEMS = (
    System('NES', 'NES', '_Console/NES', 'NES', ('.nes',), index=1, delay=2, docs='NES'),
    System('SNES', 'Super Nintendo', '_Console/SNES', 'SNES', ('.sfc', '.smc', '.bin', '.bs'), delay=2, docs='SNES'),
    System('MegaDrive', 'Mega Drive', '_Console/MegaDrive', 'MegaDrive', ('.bin', '.gen', '.md'), index=1, docs='Genesis'),
    System('S32X', 'Sega 32X', '_Console/S32X', 'S32X', ('.32x', '.bin'), index=1, docs='S32X'),
    System('SMS', 'Master System', '_Console/SMS', 'SMS', ('.sms',), index=1, exclude='SG-1000', docs='SMS'),
    System('SG1000', 'SG-1000', '_Console/SMS', 'SMS', ('.sg',), index=1, subfolder='SG-1000', docs='SG-1000'),
    System('GameGear', 'Game Gear', '_Console/SMS', 'SMS', ('.gg',), index=2, docs='GameGear'),
    System('Gameboy', 'Game Boy', '_Console/Gameboy', 'GAMEBOY', ('.gb',), index=1, delay=2, docs='GAMEBOY'),
    System('GameboyColor', 'Game Boy Color', '_Console/Gameboy', 'GAMEBOY', ('.gbc',), index=1, delay=2, docs='GBC'),
    System('GBA', 'Game Boy Advance', '_Console/GBA', 'GBA', ('.gba',), index=1, delay=2, docs='GBA'),
    System('Atari2600', 'Atari 2600', '_Console/Atari7800', 'ATARI7800', ('.a26',), index=1, docs='Atari2600'),
    System('Atari7800', 'Atari 7800', '_Console/Atari7800', 'ATARI7800', ('.a78',), index=1, docs='ATARI7800'),
    System('N64', 'Nintendo 64', '_Console/N64', 'N64', ('.n64', '.z64', '.v64'), index=1, docs='N64'),
    System('TurboGrafx16', 'PC Engine', '_Console/TurboGrafx16', 'TGFX16', ('.pce', '.bin'), docs='TGFX16'),
    System('CDI', 'CD-i', '_Console/CDi', 'CD-i', ('.cue', '.chd'), index=1, method='s', docs='CD-i'),
    System('PSX', 'PlayStation', '_Console/PSX', 'PSX', ('.cue', '.chd'), index=1, method='s', docs='PSX'),
    System('MegaCD', 'Mega CD', '_Console/MegaCD', 'MegaCD', ('.cue', '.chd'), method='s', docs='MegaCD'),
    System('ZXSpectrum', 'ZX Spectrum', '_Computer/ZX-Spectrum', 'Spectrum', ('.tap', '.tzx', '.csw', '.z80', '.sna'),
           slots=(('.tap', 'f', 2), ('.tzx', 'f', 2), ('.csw', 'f', 2), ('.z80', 'f', 4), ('.sna', 'f', 4))),
)

# Not in SYSTEMS: arcade games are .mra files the fifo loads directly, and Neo Geo
# lists Darksoft folders by the names in romsets.xml.
ARCADE_ID = 'Arcade'
NEOGEO_ID = 'NeoGeo'
NEOGEO = System(NEOGEO_ID, 'Neo Geo', '_Console/NeoGeo', 'NEOGEO', ('.neo',), index=1, docs='NEOGEO')
ARCADE_DOCS = 'Arcade'

BY_ID = {s.id: s for s in SYSTEMS + (NEOGEO,)}
