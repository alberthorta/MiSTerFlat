"""Match .mra requirements against the input index."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .index import Entry, Index
from .mra import Mra, Part, zip_output_path

COMPLETE, PARTIAL, MISSING, NO_ROMS = "complete", "partial", "missing", "no_roms"
# Found something, but only files many games use (BIOS, sound chips, jtbeta.zip):
# in practice the game itself is not in the collection.
ONLY_SHARED = "only_shared"
# A file needed by more games than this is "shared". Tuned on a real collection:
# 2, 3 or 5 give almost the same split, and clones of one game do not count
# because they share a family.
SHARED_FAMILIES = 2


@dataclass
class MraStatus:
    mra: Mra
    status: str
    found: List[Part]
    missing: List[Part]
    missing_optional: List[Part]


@dataclass
class ZipPlan:
    zip: str
    path: str  # relative to the SD card root, e.g. games/mame/1941.zip
    entries: Dict[str, str] = field(default_factory=dict)       # entry name -> crc
    sources: Dict[str, Entry] = field(default_factory=dict)      # entry name -> where to read it


@dataclass
class Resolution:
    statuses: List[MraStatus]
    zips: Dict[str, ZipPlan]  # by output path
    conflicts: List[dict]
    used_containers: Set[str]


def pick_source(entries: List[Entry]) -> Entry:
    # Prefer entries inside zips over loose files, then a stable order.
    return sorted(entries, key=lambda e: (e.name is None, e.container, e.name or ""))[0]


def best_rom0_block(mra: Mra, index: Index) -> List[Part]:
    """Required parts, using the <rom index="0"> block that has the fewest missing files."""
    req = [p for p in mra.parts if not p.optional]
    if mra.rom0_blocks <= 1:
        return req
    best: List[Part] = []
    best_missing = None
    for block in range(mra.rom0_blocks):
        parts = [p for p in req if p.rom0_block in (-1, block)]
        n = sum(1 for p in parts if p.crc not in index.by_crc)
        if best_missing is None or n < best_missing:
            best, best_missing = parts, n
    return best


def families_by_crc(mras: List[Mra]) -> Dict[str, Set[str]]:
    out: Dict[str, Set[str]] = {}
    for mra in mras:
        fam = mra.family
        for p in mra.parts:
            out.setdefault(p.crc, set()).add(fam)
    return out


def resolve(mras: List[Mra], index: Index, all_mras: Optional[List[Mra]] = None) -> Resolution:
    """all_mras: the full corpus, so "shared" does not depend on an --only filter."""
    families = families_by_crc(all_mras if all_mras is not None else mras)
    statuses: List[MraStatus] = []
    zips: Dict[str, ZipPlan] = {}
    conflicts: List[dict] = []
    used: Set[str] = set()

    for mra in mras:
        req = best_rom0_block(mra, index)
        found = [p for p in req if p.crc in index.by_crc]
        missing = [p for p in req if p.crc not in index.by_crc]
        missing_opt = [p for p in mra.parts if p.optional and p.crc not in index.by_crc]
        if not req:
            status = NO_ROMS
        elif not missing:
            status = COMPLETE
        elif found and all(len(families.get(p.crc, ())) > SHARED_FAMILIES for p in found):
            status = ONLY_SHARED
        elif found:
            status = PARTIAL
        else:
            status = MISSING
        statuses.append(MraStatus(mra, status, found, missing, missing_opt))

        for part in mra.parts:
            out = zip_output_path(part.zip)
            plan = zips.setdefault(out, ZipPlan(part.zip, out))
            name = part.name
            have = plan.entries.get(name)
            if have is not None and have != part.crc:
                alt = f"{name}.{part.crc}"
                if alt not in plan.entries:
                    conflicts.append({"zip": part.zip, "name": name, "crcs": [have, part.crc],
                                      "mra": mra.path})
                name = alt
            plan.entries[name] = part.crc
            hits = index.by_crc.get(part.crc)
            if hits and name not in plan.sources:
                plan.sources[name] = pick_source(hits)

    needed = {crc for plan in zips.values() for crc in plan.entries.values()}
    for crc, entries in index.by_crc.items():
        if crc in needed:
            used.update(e.container for e in entries)
    return Resolution(statuses, zips, conflicts, used)
