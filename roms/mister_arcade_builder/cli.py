"""Command line entry point."""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .artwork import enrich_report
from .build import build_zips
from .dbs import DEFAULT_DBS, DbError, DbFetcher
from .download import download_missing
from .index import build_index
from .mra import MraParseError, parse_mra
from .report import build_report, summary_text, write_reports
from .resolve import resolve
from .select import DEFAULT_REGIONS, one_per_game
from .verify import MISMATCH, NOT_FOUND, verify_complete

EXIT_OK, EXIT_ERROR, EXIT_PARSE_ERRORS, EXIT_VERIFY = 0, 1, 2, 3

log = logging.getLogger("mister_arcade_builder")


def parse_args(argv: Optional[List[str]]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="mister_arcade.py",
        description="Build MiSTer arcade ROM zips from your own collection, "
                    "matching the .mra files installed by update_all.")
    p.add_argument("--input", action="append", required=True, type=Path, metavar="DIR",
                   help="folder with your ROMs (repeatable); it is only read")
    p.add_argument("--output", required=True, type=Path, metavar="DIR",
                   help="root of the MiSTer SD card layout to write")
    p.add_argument("--cache", type=Path, metavar="DIR",
                   default=Path(os.path.expanduser("~/.cache/mister-arcade-builder")))
    p.add_argument("--db", action="append", default=[], metavar="URL",
                   help="extra Downloader database (repeatable)")
    p.add_argument("--no-default-dbs", action="store_true",
                   help="use only the databases given with --db")
    p.add_argument("--no-db-filters", action="store_true",
                   help="ignore the default filter of each database (update_all applies them; "
                        "e.g. jotego beta cores are left out)")
    p.add_argument("--offline", action="store_true", help="use only cached data, no network")
    p.add_argument("--download", action="store_true",
                   help="try MDK split sets for missing ROMs (cached; CRC checked)")
    p.add_argument("--artwork", action="store_true",
                   help="download MDK screenshots and game information for the offline report")
    p.add_argument("--dry-run", action="store_true", help="do not write zips, only the report")
    p.add_argument("--complete-only", action="store_true",
                   help="only write zips used by at least one complete .mra")
    p.add_argument("--one-per-game", action="store_true",
                   help="build zips for one .mra per game: complete first, then the main .mra, "
                        "then not bootleg/hack, then --prefer-region")
    p.add_argument("--prefer-region", default=",".join(DEFAULT_REGIONS), metavar="LIST",
                   help="region order for --one-per-game (default: %(default)s)")
    p.add_argument("--verify", action="store_true",
                   help="load each complete .mra from the output zips like MiSTer does and check its md5")
    p.add_argument("--only", metavar="REGEX", help="only .mra whose file name, name or setname matches")
    p.add_argument("--jobs", type=int, default=16, metavar="N")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--version", action="version", version=__version__)
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s: %(message)s")

    inputs = [i.expanduser().resolve() for i in args.input]
    for i in inputs:
        if not i.is_dir():
            log.error("input folder does not exist: %s", i)
            return EXIT_ERROR
    output = args.output.expanduser().resolve()
    cache = args.cache.expanduser().resolve()
    for i in inputs:
        if output == i or i in output.parents:
            log.error("--output must not be inside an --input folder: %s", output)
            return EXIT_ERROR

    urls = ([] if args.no_default_dbs else list(DEFAULT_DBS)) + args.db
    if not urls:
        log.error("no databases: use --db or drop --no-default-dbs")
        return EXIT_ERROR
    only = None
    if args.only:
        try:
            only = re.compile(args.only, re.IGNORECASE)
        except re.error as e:
            log.error("bad --only regex: %s", e)
            return EXIT_ERROR

    try:
        dbs = DbFetcher(cache, offline=args.offline, jobs=args.jobs, use_filters=not args.no_db_filters).collect(urls)
    except DbError as e:
        log.error("%s", e)
        return EXIT_ERROR
    log.info("%d .mra available (%d downloaded now)", len(dbs.mras), dbs.downloaded)
    for db_id, n in sorted(dbs.filtered.items()):
        log.info("%s: %d .mra left out by the db default filter (use --no-db-filters to include them)", db_id, n)

    all_mras, mras, parse_errors = [], [], []
    for src in dbs.mras:
        try:
            mra = parse_mra(src.path, src.data)
        except MraParseError as e:
            parse_errors.append((src.path, str(e)))
            continue
        all_mras.append(mra)
        if only and not (only.search(os.path.basename(mra.path)) or only.search(mra.name)
                         or only.search(mra.setname)):
            continue
        mras.append(mra)

    index = build_index(inputs, cache, exclude=[output, cache], jobs=args.jobs)
    res = resolve(mras, index, all_mras)
    if args.download:
        download_missing(res, index, cache, offline=args.offline, dry_run=args.dry_run)
        res = resolve(mras, index, all_mras)
    selected = None
    if args.one_per_game:
        regions = [r.strip() for r in args.prefer_region.split(",") if r.strip()]
        selected = {s.mra.path for s in one_per_game(res.statuses, regions).values()}
    built = build_zips(res, output, dry_run=args.dry_run, complete_only=args.complete_only,
                       jobs=args.jobs, selected=selected)
    checks = None
    if args.verify:
        if args.dry_run:
            log.warning("--verify with --dry-run checks the zips already in the output")
        log.info("verifying complete .mra against %s", output / "games")
        sources = {m.path: m.data for m in dbs.mras}
        if selected is not None:
            sources = {k: v for k, v in sources.items() if k in selected}
        checks = verify_complete(res, sources, output / "games", jobs=min(args.jobs, os.cpu_count() or 4))
    rep = build_report(res, index, dbs, parse_errors, built, dry_run=args.dry_run, checks=checks,
                       selected=selected)
    if args.artwork:
        enrich_report(rep, cache, output, offline=args.offline,
                      dry_run=args.dry_run, jobs=args.jobs)
    jpath, tpath, hpath = write_reports(rep, output)

    print(summary_text(rep))
    print(f"report: {hpath}")
    print(f"        {tpath}")
    print(f"        {jpath}")
    if built.errors:
        return EXIT_ERROR
    if checks and any(c.status in (MISMATCH, NOT_FOUND) for c in checks):
        return EXIT_VERIFY
    return EXIT_PARSE_ERRORS if parse_errors else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
