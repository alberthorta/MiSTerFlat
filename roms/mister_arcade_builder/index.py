"""Index the input collection by CRC32 without decompressing zips."""
from __future__ import annotations

import json
import logging
import os
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

log = logging.getLogger(__name__)

INDEX_CACHE_VERSION = 1
# Big or useless for MRA matching; hashing CHDs alone could take minutes.
SKIP_EXTS = {".chd", ".dat", ".xml", ".txt", ".nfo", ".md", ".htm", ".html", ".pdf",
             ".jpg", ".jpeg", ".png", ".gif", ".ini", ".cfg", ".mra", ".rar"}
CHUNK = 1 << 20


@dataclass(frozen=True)
class Entry:
    container: str      # absolute path of the zip or loose file
    name: Optional[str]  # entry name inside the zip; None for a loose file
    size: int


@dataclass
class Index:
    by_crc: Dict[str, List[Entry]] = field(default_factory=dict)
    containers: List[str] = field(default_factory=list)
    bad_zips: List[Tuple[str, str]] = field(default_factory=list)
    skipped_7z: List[str] = field(default_factory=list)
    entry_count: int = 0

    def add(self, crc: str, entry: Entry) -> None:
        self.by_crc.setdefault(crc, []).append(entry)
        self.entry_count += 1


def crc_hex(value: int) -> str:
    return f"{value & 0xFFFFFFFF:08x}"


def scan_zip(path: str) -> List[Tuple[str, str, int]]:
    with zipfile.ZipFile(path) as zf:
        return [(i.filename, crc_hex(i.CRC), i.file_size)
                for i in zf.infolist() if not i.is_dir()]


def scan_loose(path: str) -> List[Tuple[None, str, int]]:
    crc, size = 0, 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            crc = zlib.crc32(chunk, crc)
            size += len(chunk)
    return [(None, crc_hex(crc), size)]


def walk(inputs: Iterable[Path], exclude: Iterable[Path]) -> Iterable[Path]:
    excluded = [p.resolve() for p in exclude]
    for root in inputs:
        for dirpath, dirnames, filenames in os.walk(root):
            here = Path(dirpath).resolve()
            if any(here == e or e in here.parents for e in excluded):
                dirnames[:] = []
                continue
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for fn in sorted(filenames):
                if not fn.startswith("."):
                    yield here / fn


def build_index(inputs: List[Path], cache_dir: Path, exclude: Iterable[Path] = (),
                jobs: int = 16) -> Index:
    cache_file = cache_dir / "input_index.json"
    old = load_cache(cache_file)
    new: Dict[str, dict] = {}
    index = Index()

    todo = []
    for path in walk(inputs, exclude):
        ext = path.suffix.lower()
        if ext == ".7z":
            index.skipped_7z.append(str(path))
            continue
        if ext in SKIP_EXTS:
            continue
        try:
            st = path.stat()
        except OSError as e:
            log.warning("cannot stat %s: %s", path, e)
            continue
        key = str(path)
        hit = old.get(key)
        if hit and hit["mtime_ns"] == st.st_mtime_ns and hit["size"] == st.st_size:
            new[key] = hit
        else:
            todo.append((key, ext == ".zip", st))

    def scan(item):
        key, is_zip, st = item
        try:
            entries = scan_zip(key) if is_zip else scan_loose(key)
            return key, {"mtime_ns": st.st_mtime_ns, "size": st.st_size, "entries": entries}, None
        except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, ValueError) as e:
            return key, None, str(e)

    log.info("indexing input: %d cached, %d to scan", len(new), len(todo))
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for key, rec, err in pool.map(scan, todo):
            if err is not None:
                index.bad_zips.append((key, err))
            else:
                new[key] = rec

    for key in sorted(new):
        index.containers.append(key)
        for name, crc, size in new[key]["entries"]:
            index.add(crc, Entry(key, name, size))

    save_cache(cache_file, new)
    return index


def load_cache(path: Path) -> Dict[str, dict]:
    try:
        data = json.loads(path.read_text())
        if data.get("version") == INDEX_CACHE_VERSION:
            return data["files"]
    except (OSError, ValueError, KeyError):
        pass
    return {}


def save_cache(path: Path, files: Dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"version": INDEX_CACHE_VERSION, "files": files}))
    os.replace(tmp, path)
