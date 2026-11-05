"""Pick one .mra per game (--one-per-game)."""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, Iterable, List, Sequence, Set

from .mra import Mra
from .resolve import COMPLETE, MISSING, NO_ROMS, ONLY_SHARED, PARTIAL, MraStatus

DEFAULT_REGIONS = ("World", "Europe", "USA", "Japan", "Asia")
STATUS_RANK = {COMPLETE: 0, NO_ROMS: 1, PARTIAL: 2, ONLY_SHARED: 3, MISSING: 4}
# A zip listed by more games than this is shared (BIOS, sound chip) and does not link games.
SHARED_ZIP_GAMES = 3
UNWANTED = re.compile(r"bootleg|hack|phoenix edition|prototype|hbmame|\bdemo\b", re.IGNORECASE)
# Spellings seen in .mra names, e.g. "(US, Rev C)", "(Euro)", "(World 900227)".
REGION_ALIASES = {
    "world": ("world",),
    "usa": ("usa", "us"),
    "europe": ("europe", "euro"),
    "japan": ("japan",),
    "asia": ("asia",),
}


def name_tags(name: str) -> List[str]:
    """Words inside the (...) parts of a game name, lowercase."""
    words: List[str] = []
    for group in re.findall(r"\(([^)]*)\)", name):
        words += re.findall(r"[a-z]+", group.lower())
    return words


def region_rank(name: str, regions: Sequence[str]) -> int:
    tags = name_tags(name)
    for i, region in enumerate(regions):
        aliases = REGION_ALIASES.get(region.lower(), (region.lower(),))
        if any(a in tags for a in aliases):
            return i
    return len(regions)


def sort_key(s: MraStatus, regions: Sequence[str]):
    title = s.mra.name or s.mra.path.rsplit("/", 1)[-1]
    return (
        STATUS_RANK.get(s.status, 9),
        len(s.missing),
        bool(UNWANTED.search(title)),
        region_rank(title, regions),
        "/_alternatives/" in s.mra.path,       # then the main .mra
        title.lower(),
    )


def game_keys(mras: Iterable[Mra]) -> Dict[str, str]:
    """.mra path -> game key.

    The key is Mra.family. Some _alternatives folders are spelled unlike their main
    .mra ("_Final Fight Revenge" vs "Final Fight Revenge - Final Revenge (...)"): such
    a folder joins the main .mra whose setname zip its members list most often (clones
    list the parent zip, e.g. zip="1941r1.zip|1941.zip"). Zips used by many games
    (BIOS like pgm.zip) do not count.
    """
    mras = list(mras)
    families_by_zip: Dict[str, Set[str]] = {}
    for m in mras:
        for z in m.zip_names:
            families_by_zip.setdefault(z, set()).add(m.family)
    main_families = {m.family for m in mras if "/_alternatives/" not in m.path}
    main_by_zip: Dict[str, str] = {}
    for m in mras:
        z = m.setname.lower() + ".zip"
        if "/_alternatives/" not in m.path and m.setname and len(families_by_zip.get(z, ())) <= SHARED_ZIP_GAMES:
            main_by_zip[z] = m.family

    votes: Dict[str, Counter] = {}
    for m in mras:
        if "/_alternatives/" in m.path and m.family not in main_families:
            hits = {main_by_zip[z] for z in m.zip_names if z in main_by_zip}
            votes.setdefault(m.family, Counter()).update(hits)
    remap: Dict[str, str] = {}
    for fam, counter in votes.items():
        top = counter.most_common(2)
        if top and (len(top) == 1 or top[0][1] > top[1][1]):
            remap[fam] = top[0][0]
    return {m.path: remap.get(m.family, m.family) for m in mras}


def one_per_game(statuses: List[MraStatus], regions: Sequence[str] = DEFAULT_REGIONS) -> Dict[str, MraStatus]:
    """game key -> the chosen .mra of that game."""
    keys = game_keys(s.mra for s in statuses)
    by_game: Dict[str, List[MraStatus]] = {}
    for s in statuses:
        by_game.setdefault(keys[s.mra.path], []).append(s)
    return {key: min(group, key=lambda s: sort_key(s, regions)) for key, group in by_game.items()}
