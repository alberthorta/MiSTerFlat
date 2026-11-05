"""Write the output zips."""
from __future__ import annotations

import logging
import os
import posixpath
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .index import Entry, crc_hex
from .mra import zip_output_path
from .resolve import COMPLETE, Resolution, ZipPlan

log = logging.getLogger(__name__)

CHUNK = 1 << 20
# Fixed timestamp so the same input always gives the same bytes.
ZIP_DATE = (1980, 1, 1, 0, 0, 0)
WRITTEN, UPDATED, UNCHANGED = "written", "updated", "unchanged"


class CrcMismatch(Exception):
    pass


@dataclass
class BuildResult:
    written: List[str] = field(default_factory=list)    # new zips
    updated: List[str] = field(default_factory=list)    # existing zips that got new entries
    unchanged: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)    # --complete-only
    errors: List[Tuple[str, str]] = field(default_factory=list)
    unsafe: List[str] = field(default_factory=list)     # zip names that would escape --output
    foreign: List[str] = field(default_factory=list)    # zips in output not planned by any .mra


def safe_output_path(rel: str) -> Optional[str]:
    norm = posixpath.normpath(rel)
    if not norm.startswith("games/") or "/../" in f"/{norm}/" or not norm.lower().endswith(".zip"):
        return None
    return norm


def read_existing(path: Path) -> Optional[Dict[str, str]]:
    try:
        with zipfile.ZipFile(path) as zf:
            return {i.filename: crc_hex(i.CRC) for i in zf.infolist() if not i.is_dir()}
    except (OSError, zipfile.BadZipFile):
        return None


def copy_entry(src: Entry, crc: str, out: zipfile.ZipFile, name: str, zips: Dict[str, zipfile.ZipFile]) -> None:
    info = zipfile.ZipInfo(name, ZIP_DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    if src.name is None:
        reader = open(src.container, "rb")
    else:
        zf = zips.get(src.container)
        if zf is None:
            zf = zips[src.container] = zipfile.ZipFile(src.container)
        reader = zf.open(src.name)
    value = 0
    with reader, out.open(info, "w") as w:
        while True:
            chunk = reader.read(CHUNK)
            if not chunk:
                break
            value = zlib.crc32(chunk, value)
            w.write(chunk)
    got = crc_hex(value)
    if got != crc:
        where = src.container + (f" -> {src.name}" if src.name else "")
        raise CrcMismatch(f"{where}: crc {got}, expected {crc} (did the file change since indexing?)")


def build_one(plan: ZipPlan, output: Path, dry_run: bool, keep: Optional[Set[str]] = None) -> str:
    """keep: only write entries with these CRCs (the ones the selected .mra need)."""
    target = output / plan.path
    wanted = {name: plan.entries[name] for name in plan.sources
              if keep is None or plan.entries[name] in keep}
    existing = read_existing(target) if target.exists() else None
    if existing is None and target.exists():
        raise OSError("existing zip cannot be read; not overwriting it")
    if existing is not None and all(existing.get(n) == c for n, c in wanted.items()):
        return UNCHANGED
    status = WRITTEN if existing is None else UPDATED
    if dry_run:
        return status

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    opened: Dict[str, zipfile.ZipFile] = {}
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
            for name in sorted(wanted):
                copy_entry(plan.sources[name], wanted[name], out, name, opened)
            # Never drop what was already there. An old entry whose name we now use for
            # other content is kept as "<name>.<crc>"; MiSTer finds files by CRC first.
            if existing is not None:
                keep = [n for n, c in existing.items() if wanted.get(n) != c]
                if keep:
                    with zipfile.ZipFile(target) as old:
                        for n in keep:
                            new_name = n if n not in wanted else f"{n}.{existing[n]}"
                            if new_name in wanted:
                                continue
                            copy_entry(Entry(str(target), n, 0), existing[n], out, new_name,
                                       {str(target): old})
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    finally:
        for zf in opened.values():
            zf.close()
    return status


def build_zips(res: Resolution, output: Path, dry_run: bool = False, complete_only: bool = False,
               jobs: int = 8, selected: Optional[Set[str]] = None) -> BuildResult:
    """selected: paths of the .mra to build zips for (--one-per-game); None means all."""
    result = BuildResult()
    filtering = complete_only or selected is not None
    # zip path -> CRCs needed by the .mra that pass the filters
    useful: Dict[str, Set[str]] = {}
    if filtering:
        for s in res.statuses:
            if complete_only and s.status != COMPLETE:
                continue
            if selected is not None and s.mra.path not in selected:
                continue
            for p in s.mra.parts:
                useful.setdefault(zip_output_path(p.zip), set()).add(p.crc)

    todo: List[ZipPlan] = []
    for path, plan in sorted(res.zips.items()):
        if not plan.sources:
            continue
        if safe_output_path(path) != path:
            result.unsafe.append(path)
            continue
        if filtering and not any(plan.entries[n] in useful.get(path, ()) for n in plan.sources):
            result.skipped.append(path)
            continue
        todo.append(plan)

    def run(plan: ZipPlan):
        try:
            keep = useful.get(plan.path) if selected is not None else None
            return plan.path, build_one(plan, output, dry_run, keep), None
        except (CrcMismatch, OSError, zipfile.BadZipFile, RuntimeError) as e:
            return plan.path, None, str(e)

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for path, status, err in pool.map(run, todo):
            if err is not None:
                log.error("%s: %s", path, err)
                result.errors.append((path, err))
            else:
                {WRITTEN: result.written, UPDATED: result.updated, UNCHANGED: result.unchanged}[status].append(path)

    planned = set(res.zips)
    for folder in ("games/mame", "games/hbmame"):
        base = output / folder
        if base.is_dir():
            for p in sorted(base.rglob("*.zip")):
                rel = p.relative_to(output).as_posix()
                if rel not in planned:
                    result.foreign.append(rel)
    return result
