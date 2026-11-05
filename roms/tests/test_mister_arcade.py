import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

from mister_arcade_builder import cli
from mister_arcade_builder.dbs import DbFetcher
from mister_arcade_builder.build import build_zips
from mister_arcade_builder.index import build_index
from mister_arcade_builder.select import one_per_game
from mister_arcade_builder.mra import MraParseError, parse_mra, zip_output_path
from mister_arcade_builder.verify import (MISMATCH as V_MISMATCH, NOT_FOUND as V_NOT_FOUND, OK as V_OK,
                                          RomBuilder, ZipCache, hexstr_to_bytes, strtoul, verify_mra)
from mister_arcade_builder.resolve import COMPLETE, MISSING, NO_ROMS, ONLY_SHARED, PARTIAL, resolve

FIXTURES = Path(__file__).parent / "fixtures"


def crc(data: bytes) -> str:
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08x}"


def forge(prefix: bytes, target: str) -> bytes:
    """Append 4 bytes to prefix so that its CRC32 is target (CRC32 is affine over GF(2))."""
    base = zlib.crc32(prefix + b"\0\0\0\0")
    cols = []
    for bit in range(32):
        x = (1 << bit).to_bytes(4, "little")
        cols.append((zlib.crc32(prefix + x) ^ base, 1 << bit))
    want = int(target, 16) ^ base
    # Gaussian elimination: rows are (crc contribution, chosen input bits).
    basis = {}
    for v, x in cols:
        for b in reversed(range(32)):
            if not (v >> b) & 1:
                continue
            if b in basis:
                bv, bx = basis[b]
                v, x = v ^ bv, x ^ bx
            else:
                basis[b] = (v, x)
                break
    x = 0
    for b in reversed(range(32)):
        if (want >> b) & 1:
            bv, bx = basis[b]
            want, x = want ^ bv, x ^ bx
    out = prefix + x.to_bytes(4, "little")
    assert crc(out) == target
    return out


def make_zip(path: Path, entries: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)


def snapshot(root: Path) -> dict:
    return {str(p): (p.stat().st_mtime_ns, hashlib.md5(p.read_bytes()).hexdigest())
            for p in sorted(root.rglob("*")) if p.is_file()}


A, B, C, D, E = (f"blob-{i}".encode() * 50 for i in range(5))

TEST_MRA = f"""<?xml version="1.0"?>
<!-- comment with -- inside, which strict XML rejects -->
<misterromdescription>
  <name>Test Game &amp; Friends</name>
  <setname>testg</setname>
  <rbf>testcore</rbf>
  <rom index="0" zip="bios.zip|testg.zip" md5="None">
    <part> 00 01 02 </part>
    <interleave output="16">
      <part name="a.bin" crc="{crc(A)}" map="01"/>
      <part name="b.bin" crc="{crc(B)}" map="10"/>
    </interleave>
    <group><part name="none" crc="{crc(C)}"/></group>
    <PART name="d.bin" crc="{crc(D)}" zip="shared.zip"></PART>
    <part name="a.bin" crc="{crc(A)}"/>
    <part name="voice.wav" crc="{crc(E)}" ignore_crc=""/>
  </rom>
  <rom index="1"><part>05 80</part></rom>
</misterromdescription>
""".encode()


class MraTest(unittest.TestCase):
    def test_parse_rules(self):
        m = parse_mra("_Arcade/Test.mra", TEST_MRA)
        self.assertEqual((m.name, m.setname, m.rbf), ("Test Game & Friends", "testg", "testcore"))
        got = {(p.zip, p.name, p.crc, p.optional, p.by_crc) for p in m.parts}
        self.assertEqual(got, {
            ("testg.zip", "a.bin", crc(A), False, False),
            ("testg.zip", "b.bin", crc(B), False, False),
            ("testg.zip", f"{crc(C)}.bin", crc(C), False, True),
            ("shared.zip", "d.bin", crc(D), False, False),
            ("testg.zip", "voice.wav", crc(E), True, False),
        })

    def test_first_zip_when_setname_not_listed(self):
        m = parse_mra("x.mra", b'<misterromdescription><setname>zz</setname>'
                               b'<rom index="0" zip="one.zip|two.zip"><part name="p" crc="0x1234"/>'
                               b'</rom></misterromdescription>')
        self.assertEqual([(p.zip, p.crc) for p in m.parts], [("one.zip", "00001234")])

    def test_family(self):
        self.assertEqual(parse_mra("_Arcade/720 Degrees (rev 4).mra", TEST_MRA).family, "720degrees")
        self.assertEqual(parse_mra("_Arcade/_alternatives/_720_Degrees/720 Degrees (German).mra",
                                   TEST_MRA).family, "720degrees")

    def test_absolute_zip_path(self):
        m = parse_mra("x.mra", b'<misterromdescription><setname>puckman</setname>'
                               b'<rom index="0" zip="namco51.zip|/hbmame/puckman.zip">'
                               b'<part name="p" crc="1"/></rom></misterromdescription>')
        self.assertEqual(m.parts[0].zip, "/hbmame/puckman.zip")
        self.assertEqual(zip_output_path(m.parts[0].zip), "games/hbmame/puckman.zip")
        self.assertEqual(zip_output_path("1941.zip"), "games/mame/1941.zip")

    def test_mismatched_tag_case(self):
        m = parse_mra("x.mra", b'<misterromdescription><rom index="0" zip="z.zip">'
                               b'<part name="p" crc="deadbeef"/></ROM></misterromdescription>')
        self.assertEqual(len(m.parts), 1)

    def test_broken_mra(self):
        with self.assertRaises(MraParseError):
            parse_mra("x.mra", b"<misterromdescription><rom></misterromdescription")

    def test_real_1941(self):
        m = parse_mra("1941.mra", (FIXTURES / "1941.mra").read_bytes())
        self.assertEqual(m.setname, "1941")
        self.assertEqual({p.zip for p in m.parts}, {"1941.zip"})
        self.assertEqual(len(m.parts), 12)


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.input = self.tmp / "in"
        self.cache = self.tmp / "cache"
        self.output = self.tmp / "out"
        self.input.mkdir()

    def tearDown(self):
        self._tmp.cleanup()


class IndexTest(TempDirTest):
    def test_index_zip_loose_bad_and_7z(self):
        make_zip(self.input / "sub" / "g.zip", {"a.bin": A, "dir/b.bin": B})
        (self.input / "c.rom").write_bytes(C)
        (self.input / "broken.zip").write_bytes(b"not a zip")
        (self.input / "x.7z").write_bytes(b"7z")
        (self.input / ".DS_Store").write_bytes(b"junk")
        idx = build_index([self.input], self.cache)
        self.assertEqual(idx.by_crc[crc(A)][0].name, "a.bin")
        self.assertEqual(idx.by_crc[crc(B)][0].name, "dir/b.bin")
        self.assertIsNone(idx.by_crc[crc(C)][0].name)
        self.assertEqual(len(idx.bad_zips), 1)
        self.assertEqual(len(idx.skipped_7z), 1)
        self.assertEqual(idx.entry_count, 3)

    def test_cache_is_reused(self):
        make_zip(self.input / "g.zip", {"a.bin": A})
        build_index([self.input], self.cache)
        from mister_arcade_builder import index as index_mod
        orig = index_mod.scan_zip
        index_mod.scan_zip = lambda p: self.fail("zip scanned again")
        try:
            idx = build_index([self.input], self.cache)
        finally:
            index_mod.scan_zip = orig
        self.assertIn(crc(A), idx.by_crc)


class ResolveTest(TempDirTest):
    def test_statuses_and_conflicts(self):
        make_zip(self.input / "old.zip", {"renamed_a": A, "b.bin": B, "c": C, "d": D})
        partial_mra = (b'<misterromdescription><setname>p</setname><rom index="0" zip="p.zip">'
                       b'<part name="a.bin" crc="%s"/><part name="x" crc="00000001"/></rom>'
                       b'</misterromdescription>' % crc(A).encode())
        missing_mra = (b'<misterromdescription><rom index="0" zip="m.zip">'
                       b'<part name="x" crc="00000002"/></rom></misterromdescription>')
        conflict_mra = (b'<misterromdescription><rom index="0" zip="testg.zip">'
                        b'<part name="a.bin" crc="%s"/></rom></misterromdescription>' % crc(B).encode())
        no_roms_mra = b'<misterromdescription><rom index="0"><part>00</part></rom></misterromdescription>'
        two_rom0 = (b'<misterromdescription><rom index="0" zip="t.zip"><part name="q" crc="00000003"/></rom>'
                    b'<rom index="0" zip="t.zip"><part name="d" crc="%s"/></rom>'
                    b'</misterromdescription>' % crc(D).encode())
        mras = [parse_mra("full.mra", TEST_MRA), parse_mra("partial.mra", partial_mra),
                parse_mra("missing.mra", missing_mra), parse_mra("conflict.mra", conflict_mra),
                parse_mra("none.mra", no_roms_mra), parse_mra("two.mra", two_rom0)]
        res = resolve(mras, build_index([self.input], self.cache))
        st = {s.mra.path: s.status for s in res.statuses}
        self.assertEqual(st, {"full.mra": COMPLETE, "partial.mra": PARTIAL, "missing.mra": MISSING,
                              "conflict.mra": COMPLETE, "none.mra": NO_ROMS, "two.mra": COMPLETE})
        partial = next(s for s in res.statuses if s.mra.path == "partial.mra")
        self.assertEqual([p.crc for p in partial.missing], ["00000001"])
        self.assertEqual(len(res.conflicts), 1)
        plan = res.zips["games/mame/testg.zip"]
        self.assertEqual(plan.entries["a.bin"], crc(A))
        self.assertEqual(plan.entries[f"a.bin.{crc(B)}"], crc(B))
        self.assertEqual(plan.sources["a.bin"].name, "renamed_a")


class SharedTest(TempDirTest):
    def test_only_shared_and_most_wanted(self):
        bios = forge(b"bios", "0b105000")
        own = forge(b"own", "000a0000")
        make_zip(self.input / "bios.zip", {"bios.bin": bios})
        make_zip(self.input / "g0.zip", {"own.bin": own})

        def game(i, own_crc="0000000%d" % 0):
            return parse_mra(f"_Arcade/Game {i}.mra", (
                f'<misterromdescription><setname>g{i}</setname><rom index="0" zip="g{i}.zip|bios.zip">'
                f'<part name="bios.bin" crc="0b105000"/><part name="own{i}.bin" crc="{own_crc}"/>'
                f'<part name="dsp.bin" crc="d5900000"/></rom></misterromdescription>').encode())

        # g0 has its own file, g1..g3 only the BIOS; all four miss the same DSP file.
        mras = [game(0, "000a0000")] + [game(i, f"0000000{i}") for i in (1, 2, 3)]
        res = resolve(mras, build_index([self.input], self.cache))
        self.assertEqual([s.status for s in res.statuses], [PARTIAL, ONLY_SHARED, ONLY_SHARED, ONLY_SHARED])
        # With --only, sharing is still judged on the whole corpus.
        res = resolve(mras[1:2], build_index([self.input], self.cache), all_mras=mras)
        self.assertEqual(res.statuses[0].status, ONLY_SHARED)
        res = resolve(mras[1:2], build_index([self.input], self.cache))
        self.assertEqual(res.statuses[0].status, PARTIAL)


class VerifyTest(TempDirTest):
    def test_hex_and_strtoul_like_mister(self):
        self.assertEqual(hexstr_to_bytes("00 01\n0203,ff"), bytes([0, 1, 2, 3, 255]))
        self.assertEqual(hexstr_to_bytes("abc"), bytes([0xAB, 0x0C]))
        self.assertEqual(strtoul("none", 16), 0)
        self.assertEqual(strtoul("0x100", 0), 256)
        self.assertEqual(strtoul("010", 0), 8)
        self.assertEqual(strtoul("12zz", 0), 12)

    def write_games(self, entries: dict) -> Path:
        games = self.tmp / "games"
        make_zip(games / "mame" / "g.zip", entries)
        return games

    def test_interleave_patch_and_md5s(self):
        lo, hi, tail = b"\x00\x02\x04\x06", b"\x01\x03\x05\x07", b"\xaa\xbb\xcc"
        games = self.write_games({"lo.bin": lo, "hi.bin": hi, "tail.bin": tail})
        assembled = b"\x10\x10" + bytes(range(8)) + tail[1:] * 2
        stream = b"\x10\x10" + lo + hi + tail[1:] + tail[1:]
        patched = bytearray(assembled)
        patched[0] = 0x99
        mra = f"""<misterromdescription><rom index="0" zip="other.zip|g.zip"
              md5="{hashlib.md5(stream).hexdigest()}" asm_md5="{hashlib.md5(assembled).hexdigest()}">
            <part repeat="2">10</part>
            <interleave output="16">
              <part name="renamed" crc="{crc(lo)}" map="01"/>
              <part name="hi.bin" crc="0" map="10"/>
            </interleave>
            <part name="tail.bin" crc="{crc(tail)}" offset="1" length="0x2" repeat="2"/>
            <patch offset="0">99</patch>
          </rom></misterromdescription>""".encode()
        zips = ZipCache(games)
        check = verify_mra("t.mra", mra, zips)
        self.assertEqual(check.status, V_OK, check.roms)
        rom = check.roms[0]
        self.assertEqual(rom.got_md5, hashlib.md5(stream).hexdigest())
        self.assertEqual(rom.got_asm_md5, hashlib.md5(assembled).hexdigest())

        bad = mra.replace(b'name="hi.bin" crc="0"', b'name="nope.bin" crc="0"')
        self.assertEqual(verify_mra("t.mra", bad, zips).status, V_NOT_FOUND)
        wrong = mra.replace(hashlib.md5(stream).hexdigest().encode(), b"0" * 32)
        self.assertEqual(verify_mra("t.mra", wrong, zips).status, V_MISMATCH)
        zips.close()

    def test_repeat_fast_path_matches_loop(self):
        for unitlen, mapping in [(1, 0), (2, 0x10), (4, 0x2100), (8, 0x00000021)]:
            a, b = RomBuilder(), RomBuilder()
            a.unitlen = b.unitlen = unitlen
            a.add_repeated(b"\x01\x02", mapping, 300)
            for _ in range(300):
                b.add(b"\x01\x02", mapping)
            self.assertEqual((a.data, a.romlen), (b.data, b.romlen))
            self.assertEqual(a.stream_md5.hexdigest(), b.stream_md5.hexdigest())


def simple_mra(path: str, name: str, setname: str, zips: str, crcs) -> bytes:
    parts = "".join(f'<part name="p{i}" crc="{c}"/>' for i, c in enumerate(crcs))
    return (f'<misterromdescription><name>{name}</name><setname>{setname}</setname>'
            f'<rom index="0" zip="{zips}">{parts}</rom></misterromdescription>').encode()


class OnePerGameTest(TempDirTest):
    def statuses(self, specs):
        make_zip(self.input / "have.zip", {f"f{i}": forge(b"x%d" % i, f"0000aa{i:02x}") for i in range(8)})
        mras = [parse_mra(path, simple_mra(path, *rest)) for path, *rest in specs]
        return resolve(mras, build_index([self.input], self.cache)).statuses

    def chosen(self, specs, **kw):
        return sorted(s.mra.path for s in one_per_game(self.statuses(specs), **kw).values())

    def test_complete_alternative_beats_partial_main(self):
        got = self.chosen([
            ("_Arcade/Game (USA).mra", "Game (USA)", "game", "game.zip", ["0000aa00", "deadbeef"]),
            ("_Arcade/_alternatives/_Game/Game (Japan).mra", "Game (Japan)", "gamej", "gamej.zip|game.zip",
             ["0000aa01"]),
            ("_Arcade/_alternatives/_Game/Game (Asia).mra", "Game (Asia)", "gamea", "gamea.zip|game.zip",
             ["0000aa02", "deadbee0"]),
        ])
        self.assertEqual(got, ["_Arcade/_alternatives/_Game/Game (Japan).mra"])

    def test_region_order_then_main_then_no_bootleg(self):
        specs = [
            ("_Arcade/Shot (USA).mra", "Shot (USA)", "shot", "shot.zip", ["0000aa00"]),
            ("_Arcade/_alternatives/_Shot/Shot (Europe).mra", "Shot (Europe)", "shote", "shote.zip", ["0000aa01"]),
            ("_Arcade/_alternatives/_Shot/Shot (World, bootleg).mra", "Shot (World, bootleg)", "shotb",
             "shotb.zip", ["0000aa02"]),
        ]
        self.assertEqual(self.chosen(specs), ["_Arcade/_alternatives/_Shot/Shot (Europe).mra"])
        self.assertEqual(self.chosen(specs, regions=["USA"]), ["_Arcade/Shot (USA).mra"])

    def test_alternatives_folder_spelled_differently_joins_its_parent(self):
        got = self.chosen([
            ("_Arcade/Big Fight - Final Round (World).mra", "Big Fight - Final Round (World)", "bigf",
             "bigf.zip", ["0000aa00", "deadbeef"]),
            ("_Arcade/_alternatives/_Big Fight/Big Fight (Japan).mra", "Big Fight (Japan)", "bigfj",
             "bigfj.zip|bigf.zip", ["0000aa01"]),
        ])
        self.assertEqual(got, ["_Arcade/_alternatives/_Big Fight/Big Fight (Japan).mra"])

    def test_build_only_selected(self):
        make_zip(self.input / "have.zip", {"a": A, "b": B})
        a = parse_mra("_Arcade/G (World).mra", simple_mra("x", "G (World)", "g", "g.zip", [crc(A)]))
        b = parse_mra("_Arcade/_alternatives/_G/G (Japan).mra",
                      simple_mra("x", "G (Japan)", "gj", "gj.zip|g.zip", [crc(B)]))
        res = resolve([a, b], build_index([self.input], self.cache))
        chosen = {s.mra.path for s in one_per_game(res.statuses).values()}
        self.assertEqual(chosen, {"_Arcade/G (World).mra"})
        built = build_zips(res, self.output, selected=chosen)
        self.assertEqual(built.written, ["games/mame/g.zip"])
        self.assertEqual(built.skipped, ["games/mame/gj.zip"])


def fake_db(files: dict, archive: bytes = None) -> bytes:
    db = {"db_id": "fake", "base_files_url": "https://x/",
          "files": {p: {"hash": hashlib.md5(d).hexdigest(), "size": len(d)} for p, d in files.items()}}
    if archive is not None:
        db["archives"] = {"mra_alternatives": {
            "archive_file": {"url": "https://x/alt.zip", "hash": hashlib.md5(archive).hexdigest()},
            "format": "zip", "target_folder": "_Arcade/"}}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("db.json", json.dumps(db))
    return buf.getvalue()


class FakeNet:
    def __init__(self, urls: dict):
        self.urls = urls
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        if url not in self.urls:
            raise OSError("404")
        return self.urls[url]


class DbTest(TempDirTest):
    def setUp(self):
        super().setUp()
        alt = io.BytesIO()
        with zipfile.ZipFile(alt, "w") as zf:
            zf.writestr("_alternatives/_T/T (US).mra", b"<misterromdescription/>")
        self.alt = alt.getvalue()
        self.net = FakeNet({
            "https://db": fake_db({"_Arcade/T.mra": TEST_MRA, "_Arcade/Bad md5.mra": b"x",
                                   "games/other.rom": b"r"}, self.alt),
            "https://x/_Arcade/T.mra": TEST_MRA,
            "https://x/_Arcade/Bad%20md5.mra": b"different",
            "https://x/alt.zip": self.alt,
        })

    def test_download_cache_and_offline(self):
        res = DbFetcher(self.cache, fetch=self.net).collect(["https://db"])
        self.assertEqual([m.path for m in res.mras],
                         ["_Arcade/T.mra", "_Arcade/_alternatives/_T/T (US).mra"])
        self.assertEqual(res.unavailable, ["_Arcade/Bad md5.mra"])
        self.assertEqual(res.downloaded, 2)

        self.net.calls.clear()
        res = DbFetcher(self.cache, fetch=self.net).collect(["https://db"])
        self.assertEqual(res.downloaded, 0)
        self.assertEqual(sorted(self.net.calls), ["https://db", "https://x/_Arcade/Bad%20md5.mra"])

        self.net.calls.clear()
        res = DbFetcher(self.cache, offline=True, fetch=self.net).collect(["https://db"])
        self.assertEqual(self.net.calls, [])
        self.assertEqual(len(res.mras), 2)


class DbFilterTest(TempDirTest):
    def test_default_filter_leaves_out_tagged_files(self):
        mra = b"<misterromdescription/>"
        db = {"db_id": "jt", "base_files_url": "https://x/", "tag_dictionary": {"jtbeta": 7, "arcade": 1},
              "default_options": {"filter": "[MiSTer] !jt-Beta"},
              "files": {"_Arcade/Beta.mra": {"hash": hashlib.md5(mra).hexdigest(), "tags": [1, 7]},
                        "_Arcade/Stable.mra": {"hash": hashlib.md5(mra).hexdigest(), "tags": [1]}}}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("db.json", json.dumps(db))
        net = FakeNet({"https://db": buf.getvalue(), "https://x/_Arcade/Beta.mra": mra,
                       "https://x/_Arcade/Stable.mra": mra})
        res = DbFetcher(self.cache, fetch=net).collect(["https://db"])
        self.assertEqual([m.path for m in res.mras], ["_Arcade/Stable.mra"])
        self.assertEqual(res.filtered, {"jt": 1})
        res = DbFetcher(self.cache, fetch=net, use_filters=False).collect(["https://db"])
        self.assertEqual(len(res.mras), 2)


class AcceptanceTest(TempDirTest):
    """The case that started this: an old 1941.zip with four files under other names or missing."""

    RENAMED = {"41em_30.11f": "4249ec61", "41em_35.11h": "ddbee5eb",
               "41em_31.12f": "584e88e5", "41em_36.12h": "3cfc31d0"}

    def setUp(self):
        super().setUp()
        mra = (FIXTURES / "1941.mra").read_bytes()
        net = FakeNet({"https://db": fake_db({"_Arcade/1941.mra": mra}),
                       "https://x/_Arcade/1941.mra": mra})
        DbFetcher(self.cache, fetch=net).collect(["https://db"])
        self.parts = {p.name: p.crc for p in parse_mra("1941.mra", mra).parts}
        old = {n: forge(n.encode(), c) for n, c in self.parts.items() if n not in self.RENAMED}
        old["41e_30.rom"] = b"old dump, other crc"
        make_zip(self.input / "1941.zip", old)

    def run_cli(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(["--input", str(self.input), "--output", str(self.output),
                             "--cache", str(self.cache), "--offline",
                             "--no-default-dbs", "--db", "https://db", *extra])
        return code, json.loads((self.output / "mister-arcade-report.json").read_text())

    def test_reports_the_four_missing_parts(self):
        before = snapshot(self.input)
        code, rep = self.run_cli("--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(snapshot(self.input), before)
        self.assertFalse((self.output / "games").exists())
        self.assertEqual(rep["build"]["written"], ["games/mame/1941.zip"])
        self.assertEqual(rep["summary"]["partial"], 1)
        missing = {(p["zip"], p["name"], p["crc"]) for p in rep["partial"][0]["missing"]}
        self.assertEqual(missing, {("1941.zip", n, c) for n, c in self.RENAMED.items()})
        self.assertTrue((self.output / "mister-arcade-report.txt").exists())
        page = (self.output / "mister-arcade-report.html").read_text()
        self.assertIn("1941: Counter Attack (World 900227)", page)
        data = json.loads(page.split('type="application/json">')[1].split("</script>")[0])
        self.assertEqual(data["summary"]["partial"], 1)

    def add_clone(self):
        make_zip(self.input / "1941u.zip", {f"clone_{i}": forge(n.encode(), c)
                                            for i, (n, c) in enumerate(self.RENAMED.items())})

    def output_zip(self) -> dict:
        with zipfile.ZipFile(self.output / "games/mame/1941.zip") as zf:
            self.assertIsNone(zf.testzip())
            return {i.filename: f"{i.CRC:08x}" for i in zf.infolist()}

    def test_found_in_a_clone_zip_under_other_names(self):
        self.add_clone()
        before = snapshot(self.input)
        code, rep = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(snapshot(self.input), before)
        self.assertEqual(rep["summary"]["complete"], 1)
        self.assertEqual(rep["zips"], [{"path": "games/mame/1941.zip", "entries": 12, "found": 12}])
        self.assertEqual(self.output_zip(), self.parts)

    def test_verify_flag(self):
        self.add_clone()
        code, rep = self.run_cli("--verify")
        # The fixture's asm_md5 is for the real ROMs, not for these forged ones.
        self.assertEqual(code, 3)
        self.assertEqual(rep["verify"]["counts"], {"md5_mismatch": 1})

    def test_second_run_writes_nothing(self):
        self.add_clone()
        self.run_cli()
        before = snapshot(self.output / "games")
        code, rep = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(rep["build"]["unchanged"], ["games/mame/1941.zip"])
        self.assertEqual(rep["build"]["written"] + rep["build"]["updated"], [])
        self.assertEqual(snapshot(self.output / "games"), before)

    def test_partial_zip_is_written_unless_complete_only(self):
        code, rep = self.run_cli("--complete-only")
        self.assertEqual(rep["build"]["skipped_not_complete"], ["games/mame/1941.zip"])
        self.assertFalse((self.output / "games/mame/1941.zip").exists())
        self.run_cli()
        self.assertEqual(len(self.output_zip()), 8)

    def test_existing_entries_are_kept(self):
        make_zip(self.output / "games/mame/1941.zip", {"mine.txt": b"keep me", "41-32m.8h": b"old"})
        code, rep = self.run_cli()
        self.assertEqual(rep["build"]["updated"], ["games/mame/1941.zip"])
        got = self.output_zip()
        self.assertEqual(got["mine.txt"], crc(b"keep me"))
        self.assertEqual(got["41-32m.8h"], self.parts["41-32m.8h"])
        self.assertEqual(got[f"41-32m.8h.{crc(b'old')}"], crc(b"old"))
        self.assertEqual(rep["build"]["output_zips_not_planned"], [])

    def test_unreadable_existing_zip_is_not_overwritten(self):
        target = self.output / "games/mame/1941.zip"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"garbage")
        code, rep = self.run_cli()
        self.assertEqual(code, 1)
        self.assertEqual(len(rep["build"]["errors"]), 1)
        self.assertEqual(target.read_bytes(), b"garbage")

    def test_crc_mismatch_leaves_no_file(self):
        self.run_cli("--dry-run")  # fill the index cache
        src = self.input / "1941.zip"
        st = src.stat()
        # Same size and mtime, other content: the cached index is now wrong.
        old = {n: forge(n.encode(), c) for n, c in self.parts.items() if n not in self.RENAMED}
        old["41-32m.8h"] = forge(b"X" + b"41-32m.8h"[1:], "00000000")
        old["41e_30.rom"] = b"old dump, other crc"
        make_zip(src, old)
        os.utime(src, ns=(st.st_atime_ns, st.st_mtime_ns))
        if src.stat().st_size != st.st_size:
            self.skipTest("rebuilt zip has another size")
        code, rep = self.run_cli()
        self.assertEqual(code, 1)
        self.assertEqual(len(rep["build"]["errors"]), 1)
        self.assertEqual(list((self.output / "games/mame").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
