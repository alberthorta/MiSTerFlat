"""Fetch candidate split sets from MDK and index validated cached archives."""
from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from .index import Entry, Index, scan_zip
from .resolve import Resolution

log = logging.getLogger(__name__)
BASE_URL = "https://mdk.cab/download/split/"
SAFE_SET = re.compile(r"[a-zA-Z0-9_-]+\.zip\Z")


def download_missing(res: Resolution, index: Index, cache: Path,
                     offline: bool = False, dry_run: bool = False) -> int:
    """Try each candidate once; failures leave requirements missing.

    Archives stay in the cache, never in input folders. Reading every member
    validates its CRC before an archive can become a source for the builder.
    """
    candidates = set()
    for status in res.statuses:
        if status.missing:
            candidates.update(status.mra.zip_names)
            candidates.update(p.zip.rsplit("/", 1)[-1].lower() for p in status.missing)
            if status.mra.setname:
                candidates.add(status.mra.setname.lower() + ".zip")
    folder = cache / "downloads" / "mdk"
    added = 0
    for name in sorted(candidates):
        if not SAFE_SET.fullmatch(name):
            log.warning("skipping invalid MDK set name: %s", name)
            continue
        path = folder / name
        tmp = None
        try:
            if not path.exists():
                if offline or dry_run:
                    continue
                folder.mkdir(parents=True, exist_ok=True)
                log.info("downloading MDK set: %s", name)
                request = urllib.request.Request(BASE_URL + name,
                                                 headers={"User-Agent": "mister-arcade-builder"})
                with tempfile.NamedTemporaryFile(dir=folder, suffix=".tmp", delete=False) as target:
                    tmp = Path(target.name)
                    with urllib.request.urlopen(request, timeout=60) as response:
                        shutil.copyfileobj(response, target)
                validate_zip(tmp)
                os.replace(tmp, path)
                tmp = None
            else:
                validate_zip(path)
            entries = scan_zip(str(path))
            if str(path) in index.containers:
                continue
            index.containers.append(str(path))
            for member, crc, size in entries:
                index.add(crc, Entry(str(path), member, size))
            added += 1
        except (OSError, ValueError, EOFError, RuntimeError, zipfile.BadZipFile,
                urllib.error.URLError) as exc:
            log.warning("cannot use MDK set %s: %s", name, exc)
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
    log.info("%d MDK archives added to the ROM index", added)
    return added


def validate_zip(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise zipfile.BadZipFile("CRC mismatch: " + bad)
