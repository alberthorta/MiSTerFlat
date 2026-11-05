"""Build the text and JSON reports."""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Optional, Tuple

from .build import BuildResult
from .dbs import DbResult
from .index import Index
from .report_html import render as render_html
from .resolve import COMPLETE, MISSING, NO_ROMS, ONLY_SHARED, PARTIAL, Resolution

STATUSES = (COMPLETE, PARTIAL, ONLY_SHARED, MISSING, NO_ROMS)
MOST_WANTED = 50


def build_report(res: Resolution, index: Index, dbs: DbResult,
                 parse_errors: List[Tuple[str, str]], built: BuildResult, dry_run: bool,
                 checks: Optional[list] = None, selected: Optional[set] = None) -> dict:
    totals = Counter(s.status for s in res.statuses)
    by_core = defaultdict(Counter)
    for s in res.statuses:
        by_core[s.mra.rbf or "?"][s.status] += 1

    def mra_info(s):
        info = {"path": s.mra.path, "name": s.mra.name, "setname": s.mra.setname,
                "rbf": s.mra.rbf, "zips": sorted({p.zip for p in s.mra.parts})}
        if selected is not None:
            info["selected"] = s.mra.path in selected
        return info

    partial = []
    for s in res.statuses:
        if s.status == PARTIAL:
            info = mra_info(s)
            info["missing"] = [{"zip": p.zip, "name": p.name, "crc": p.crc} for p in s.missing]
            info["found"] = len(s.found)
            partial.append(info)
    partial.sort(key=lambda m: (len(m["missing"]), m["path"]))

    # Files that would help the most .mra, grouped by CRC: the same file (a QSound
    # DSP, a BIOS) is often wanted under one name in many different zips.
    wanted_count, wanted_alone, wanted_names = Counter(), Counter(), defaultdict(Counter)
    for s in res.statuses:
        if s.status != PARTIAL:
            continue
        for p in s.missing:
            wanted_count[p.crc] += 1
            wanted_names[p.crc][p.name] += 1
        if len({p.crc for p in s.missing}) == 1:
            wanted_alone[s.missing[0].crc] += 1
    most_wanted = [{"crc": c, "name": wanted_names[c].most_common(1)[0][0], "mra_count": n,
                    "last_missing_for": wanted_alone[c]}
                   for c, n in sorted(wanted_count.items(), key=lambda kv: (-kv[1], kv[0]))[:MOST_WANTED]]

    optional_missing = Counter()
    for s in res.statuses:
        if s.status in (COMPLETE, PARTIAL):
            for p in s.missing_optional:
                optional_missing[(p.zip, p.name, p.crc)] += 1

    zips = []
    for path, plan in sorted(res.zips.items()):
        zips.append({"path": path, "entries": len(plan.entries),
                     "found": len(plan.sources)})

    verify = None
    if checks is not None:
        verify = {
            "counts": dict(Counter(c.status for c in checks)),
            "problems": [{"path": c.path, "status": c.status,
                          "roms": [{"index": r.index, "status": r.status, "md5": r.md5, "asm_md5": r.asm_md5,
                                    "got_md5": r.got_md5, "got_asm_md5": r.got_asm_md5,
                                    "not_found": r.not_found} for r in c.roms if r.status != "ok"]}
                         for c in checks if c.status not in ("ok", "no_md5")],
            "ok": [c.path for c in checks if c.status == "ok"],
            "no_md5": [c.path for c in checks if c.status == "no_md5"],
        }

    one_per_game = None
    if selected is not None:
        chosen = [s for s in res.statuses if s.mra.path in selected]
        one_per_game = {
            "games": len(chosen),
            **{k: sum(1 for s in chosen if s.status == k) for k in STATUSES},
            "selected": sorted(s.mra.path for s in chosen),
        }

    return {
        "dry_run": dry_run,
        "verify": verify,
        "one_per_game": one_per_game,
        "summary": {
            "mra_total": len(res.statuses),
            **{k: totals.get(k, 0) for k in STATUSES},
            "parse_errors": len(parse_errors),
            "mra_unavailable": len(dbs.unavailable),
            "mra_filtered_by_db": dbs.filtered,
            "input_files": len(index.containers),
            "input_entries": index.entry_count,
            "input_files_unused": len(index.containers) - len(res.used_containers),
            "zips_with_content": sum(1 for z in zips if z["found"]),
        },
        "by_core": {core: {k: c.get(k, 0) for k in STATUSES} for core, c in sorted(by_core.items())},
        "complete": [mra_info(s) for s in res.statuses if s.status == COMPLETE],
        "partial": partial,
        "most_wanted": most_wanted,
        "only_shared": [dict(mra_info(s), found=[p.name for p in s.found])
                        for s in res.statuses if s.status == ONLY_SHARED],
        "missing": [mra_info(s) for s in res.statuses if s.status == MISSING],
        "no_roms": [mra_info(s) for s in res.statuses if s.status == NO_ROMS],
        "zips": zips,
        "optional_missing": [{"zip": z, "name": n, "crc": c, "mra_count": k}
                             for (z, n, c), k in sorted(optional_missing.items())],
        "build": {
            "written": built.written,
            "updated": built.updated,
            "unchanged": built.unchanged,
            "skipped_not_complete": built.skipped,
            "errors": [{"path": p, "error": e} for p, e in built.errors],
            "unsafe_names": built.unsafe,
            "output_zips_not_planned": built.foreign,
        },
        "conflicts": res.conflicts,
        "parse_errors": [{"path": p, "error": e} for p, e in parse_errors],
        "mra_unavailable": dbs.unavailable,
        "db_overlaps": dbs.overlaps,
        "input_unused": sorted(set(index.containers) - res.used_containers),
        "input_bad_zips": [{"path": p, "error": e} for p, e in index.bad_zips],
        "input_skipped_7z": index.skipped_7z,
    }


def summary_text(rep: dict) -> str:
    s = rep["summary"]
    lines = [
        f".mra: {s['mra_total']}  complete: {s['complete']}  partial: {s['partial']}  "
        f"only shared files: {s['only_shared']}  missing: {s['missing']}  no ROMs needed: {s['no_roms']}",
        f"input: {s['input_files']} files, {s['input_entries']} ROM entries, "
        f"{s['input_files_unused']} files not used by any .mra",
        f"zips that would get content: {s['zips_with_content']}",
    ]
    b = rep["build"]
    lines.append(f"zips: {len(b['written'])} new, {len(b['updated'])} updated, "
                 f"{len(b['unchanged'])} already up to date"
                 + (" (dry run: nothing written)" if rep["dry_run"] else ""))
    if b["skipped_not_complete"]:
        lines.append(f"zips skipped by --complete-only / --one-per-game: {len(b['skipped_not_complete'])}")
    if b["errors"]:
        lines.append(f"ERROR: {len(b['errors'])} zips could not be built")
    o = rep.get("one_per_game")
    if o is not None:
        lines.append(f"one per game: {o['games']} games, {o[COMPLETE]} of them complete")
    v = rep.get("verify")
    if v is not None:
        c = v["counts"]
        lines.append(f"verify (complete .mra loaded like MiSTer): {c.get('ok', 0)} md5 ok, "
                     f"{c.get('md5_mismatch', 0)} md5 different, {c.get('file_not_found', 0)} file not found, "
                     f"{c.get('no_md5', 0)} without md5 to check")
    if s["parse_errors"]:
        lines.append(f"WARNING: {s['parse_errors']} .mra could not be parsed")
    if s["mra_unavailable"]:
        lines.append(f"WARNING: {s['mra_unavailable']} .mra could not be downloaded")
    if rep["input_bad_zips"]:
        lines.append(f"WARNING: {len(rep['input_bad_zips'])} input files could not be read")
    if rep["input_skipped_7z"]:
        lines.append(f"NOTE: {len(rep['input_skipped_7z'])} .7z files skipped (not supported yet)")
    return "\n".join(lines)


def full_text(rep: dict) -> str:
    out = ["mister-arcade-builder report" + (" (dry run)" if rep["dry_run"] else ""), "",
           summary_text(rep), "",
           "\"only shared files\": the only files found are ones many games use (BIOS,",
           "sound chips, jtbeta.zip), so the game itself is not in your collection.", "",
           f"  {'core':<20} {'complete':>8} {'partial':>8} {'shared':>8} {'missing':>8} {'no ROMs':>8}"]
    for core, c in rep["by_core"].items():
        out.append(f"  {core:<20}" + "".join(f"{c[k]:>9}" for k in STATUSES))

    out += ["", f"Most wanted files (most partial .mra need them; \"last\" = the only file missing):"]
    for w in rep["most_wanted"]:
        out.append(f"  crc {w['crc']}  {w['name']:<24} needed by {w['mra_count']:>4}, last for {w['last_missing_for']:>4}")

    out += ["", f"Partial .mra ({len(rep['partial'])}): missing parts, fewest missing first"]
    for m in rep["partial"]:
        out.append(f"  {m['path']}  [{m['setname']}]")
        for p in m["missing"]:
            out.append(f"      {p['zip']}: {p['name']}  crc {p['crc']}")

    v = rep.get("verify")
    if v is not None and v["problems"]:
        out += ["", f"Verify problems ({len(v['problems'])})"]
        for pr in v["problems"]:
            out.append(f"  {pr['path']}: {pr['status']}")
            for r in pr["roms"]:
                if r["not_found"]:
                    out.append(f"      rom {r['index']}: not found: {', '.join(r['not_found'])}")
                else:
                    out.append(f"      rom {r['index']}: md5 {r['md5'] or '-'} got {r['got_md5']}, "
                               f"asm_md5 {r['asm_md5'] or '-'} got {r['got_asm_md5']}")

    sections = [
        ("Complete .mra", [m["path"] for m in rep["complete"]]),
        ("Only shared files found", [f"{m['path']}  (found: {', '.join(m['found'])})"
                                    for m in rep["only_shared"]]),
        ("Missing .mra (no part found)", [m["path"] for m in rep["missing"]]),
        ("Optional files not found (ignore_crc)",
         [f"{o['zip']}: {o['name']}  crc {o['crc']}  (used by {o['mra_count']} usable .mra)"
          for o in rep["optional_missing"]]),
        ("Zips that could not be built", [f"{e['path']}: {e['error']}" for e in rep["build"]["errors"]]),
        ("New zips", rep["build"]["written"]),
        ("Updated zips (existing entries kept)", rep["build"]["updated"]),
        ("Zips skipped by --complete-only / --one-per-game", rep["build"]["skipped_not_complete"]),
        ("Selected .mra, one per game", (rep.get("one_per_game") or {}).get("selected", [])),
        ("Zip names refused (outside games/)", rep["build"]["unsafe_names"]),
        ("Zips already in the output that no .mra uses (not touched)",
         rep["build"]["output_zips_not_planned"]),
        ("Name conflicts inside a zip", [f"{c['zip']}: {c['name']} crcs {', '.join(c['crcs'])} ({c['mra']})"
                                         for c in rep["conflicts"]]),
        (".mra that could not be parsed", [f"{e['path']}: {e['error']}" for e in rep["parse_errors"]]),
        (".mra that could not be downloaded", rep["mra_unavailable"]),
        ("Paths shipped by more than one db (later db wins)", rep["db_overlaps"]),
        ("Input files not used by any .mra", rep["input_unused"]),
        ("Input files that could not be read", [f"{e['path']}: {e['error']}" for e in rep["input_bad_zips"]]),
        ("Skipped .7z files", rep["input_skipped_7z"]),
    ]
    for title, items in sections:
        if items:
            out += ["", f"{title} ({len(items)})"] + [f"  {i}" for i in items]
    return "\n".join(out) + "\n"


def write_reports(rep: dict, output: Path) -> Tuple[Path, Path, Path]:
    output.mkdir(parents=True, exist_ok=True)
    jpath = output / "mister-arcade-report.json"
    tpath = output / "mister-arcade-report.txt"
    hpath = output / "mister-arcade-report.html"
    for path, text in ((jpath, json.dumps(rep, indent=1, ensure_ascii=False)), (tpath, full_text(rep)),
                       (hpath, render_html(rep))):
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    return jpath, tpath, hpath
