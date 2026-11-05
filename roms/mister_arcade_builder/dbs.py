"""Download and cache the Downloader databases used by update_all, and their .mra files."""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import posixpath
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

log = logging.getLogger(__name__)

# The arcade databases update_all enables by default (src/update_all/databases.py).
DEFAULT_DBS = [
    "https://raw.githubusercontent.com/MiSTer-devel/Distribution_MiSTer/main/db.json.zip",
    "https://raw.githubusercontent.com/jotego/jtcores_mister/main/jtbindb.json.zip",
    "https://raw.githubusercontent.com/Coin-OpCollection/Distribution-MiSTerFPGA/db/db.json.zip",
]

USER_AGENT = "mister-arcade-builder"
RETRIES = 3


class DbError(Exception):
    pass


@dataclass
class MraSource:
    path: str  # logical path on the SD card, e.g. "_Arcade/_alternatives/_X/X (US).mra"
    db_id: str
    data: bytes


@dataclass
class DbResult:
    mras: List[MraSource] = field(default_factory=list)
    # .mra listed in a db that we could not get (network error, offline without cache, bad md5)
    unavailable: List[str] = field(default_factory=list)
    # paths shipped by more than one db; the later db in the list wins
    overlaps: List[str] = field(default_factory=list)
    downloaded: int = 0
    # .mra left out by a db's default filter, e.g. jotego beta cores ("!jtbeta"), per db_id
    filtered: Dict[str, int] = field(default_factory=dict)


def http_get(url: str) -> bytes:
    # urllib picks up HTTPS_PROXY / HTTP_PROXY from the environment by default.
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last: Optional[Exception] = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            last = e
        except (urllib.error.URLError, OSError) as e:
            last = e
        time.sleep(1 + attempt * 2)
    assert last is not None
    raise last


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def safe_relpath(path: str) -> Optional[str]:
    """Paths come from downloaded data; refuse anything that could escape the cache dir."""
    norm = posixpath.normpath(path.replace("\\", "/"))
    if norm.startswith("/") or norm == ".." or norm.startswith("../") or ":" in norm:
        return None
    return norm


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def norm_term(term: str) -> str:
    # Downloader compares filter terms and tags without case, "-" or "_".
    return term.lower().replace("-", "").replace("_", "")


def parse_filter(text: Optional[str]):
    """Downloader filter string -> (positive terms, negative terms).

    "[MiSTer]" means "also apply the global filter"; update_all leaves that empty.
    Only negative terms are used by the default filters; positive terms keep files
    with at least one of those tags, which is a simplification of Downloader.
    """
    pos, neg = set(), set()
    for raw in (text or "").split():
        if raw.startswith("[") and raw.endswith("]"):
            continue
        if raw.startswith("!"):
            neg.add(norm_term(raw[1:]))
        else:
            pos.add(norm_term(raw))
    return pos, neg


def file_tags(info: dict, tag_names: Dict[int, str]) -> set:
    return {norm_term(tag_names.get(t, str(t)) if isinstance(t, int) else str(t)) for t in info.get("tags", [])}


def url_key(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


class DbFetcher:
    def __init__(self, cache_dir: Path, offline: bool = False, jobs: int = 16,
                 fetch: Callable[[str], bytes] = http_get, use_filters: bool = True):
        self.use_filters = use_filters
        self.cache_dir = cache_dir
        self.offline = offline
        self.jobs = jobs
        self.fetch = fetch

    def load_db(self, url: str) -> dict:
        cached = self.cache_dir / "dbs" / f"{url_key(url)}.json.zip"
        data: Optional[bytes] = None
        if not self.offline:
            try:
                data = self.fetch(url)
                write_atomic(cached, data)
            except Exception as e:
                if not cached.exists():
                    raise DbError(f"cannot download database {url}: {e}") from e
                log.warning("cannot download %s (%s); using cached copy", url, e)
        if data is None:
            if not cached.exists():
                raise DbError(f"database {url} is not in the cache (offline mode)")
            data = cached.read_bytes()
        return parse_db_zip(data, url)

    def collect(self, urls: List[str]) -> DbResult:
        result = DbResult()
        by_path: Dict[str, MraSource] = {}
        for url in urls:
            db = self.load_db(url)
            db_id = str(db.get("db_id") or url_key(url))
            if safe_relpath(db_id) != db_id:
                db_id = url_key(url)
            mras = self._db_files(db, db_id, result) + self._db_archives(db, db_id, result)
            log.info("%s: %d .mra", db_id, len(mras))
            for m in mras:
                if m.path in by_path:
                    result.overlaps.append(m.path)
                by_path[m.path] = m
        result.mras = sorted(by_path.values(), key=lambda m: m.path)
        return result

    def _db_files(self, db: dict, db_id: str, result: DbResult) -> List[MraSource]:
        base = db.get("base_files_url", "")
        files = db.get("files") or {}
        tag_names = {v: k for k, v in (db.get("tag_dictionary") or {}).items()}
        pos, neg = parse_filter((db.get("default_options") or {}).get("filter")) if self.use_filters else (set(), set())
        wanted = []
        for path, info in files.items():
            if not path.lower().endswith(".mra"):
                continue
            if pos or neg:
                tags = file_tags(info, tag_names)
                if tags & neg or (pos and not tags & pos):
                    result.filtered[db_id] = result.filtered.get(db_id, 0) + 1
                    continue
            rel = safe_relpath(path)
            if rel is None:
                log.warning("%s: skipping unsafe path %r", db_id, path)
                continue
            url = info.get("url") or base + urllib.parse.quote(path)
            wanted.append((path, rel, url, (info.get("hash") or "").lower()))

        def get_one(item):
            path, rel, url, want_md5 = item
            local = self.cache_dir / "mra" / db_id / rel
            if local.exists():
                data = local.read_bytes()
                if self.offline or not want_md5 or md5(data) == want_md5:
                    return path, data, False
            if self.offline:
                return path, None, False
            try:
                data = self.fetch(url)
            except Exception as e:
                log.warning("cannot download %s: %s", path, e)
                return path, None, False
            if want_md5 and md5(data) != want_md5:
                log.warning("md5 mismatch for %s; skipping it", path)
                return path, None, False
            write_atomic(local, data)
            return path, data, True

        out = []
        with ThreadPoolExecutor(max_workers=self.jobs) as pool:
            for path, data, fresh in pool.map(get_one, wanted):
                if data is None:
                    result.unavailable.append(path)
                    continue
                result.downloaded += fresh
                out.append(MraSource(path, db_id, data))
        return out

    def _db_archives(self, db: dict, db_id: str, result: DbResult) -> List[MraSource]:
        out = []
        for name, arc in (db.get("archives") or {}).items():
            target = arc.get("target_folder") or ""
            if not target.startswith("_Arcade"):
                continue
            afile = arc.get("archive_file") or {}
            url, want_md5 = afile.get("url"), (afile.get("hash") or "").lower()
            if not url or arc.get("format", "zip") != "zip":
                continue
            local = self.cache_dir / "archives" / db_id / f"{name}.zip"
            data = None
            if local.exists():
                data = local.read_bytes()
                if not self.offline and want_md5 and md5(data) != want_md5:
                    data = None
            if data is None and not self.offline:
                try:
                    data = self.fetch(url)
                    if want_md5 and md5(data) != want_md5:
                        raise DbError("md5 mismatch")
                    write_atomic(local, data)
                    result.downloaded += 1
                except Exception as e:
                    log.warning("cannot download archive %s: %s", name, e)
                    data = None
            if data is None:
                result.unavailable.append(f"{db_id}:{name} (archive)")
                continue
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zf.infolist():
                    if info.is_dir() or not info.filename.lower().endswith(".mra"):
                        continue
                    path = safe_relpath(posixpath.join(target, info.filename))
                    if path is None:
                        continue
                    out.append(MraSource(path, db_id, zf.read(info)))
        return out


def parse_db_zip(data: bytes, url: str) -> dict:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [n for n in zf.namelist() if n.endswith(".json")]
            if not names:
                raise DbError(f"{url}: no .json inside the database zip")
            return json.loads(zf.read(names[0]))
    except zipfile.BadZipFile:
        # Some dbs are served as plain JSON.
        try:
            return json.loads(data)
        except ValueError as e:
            raise DbError(f"{url}: not a zip nor JSON") from e
