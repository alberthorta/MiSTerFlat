# mister-arcade-builder

Build MiSTer arcade ROM zips from your own ROM collection. The zips match the
`.mra` files that update_all installs on the SD card. The tool also writes a
report (JSON, text and HTML) with what is complete, what is partial and what
is missing.

Python 3.9+ and only the standard library. It never changes the input folders
and only downloads ROMs when explicitly requested with `--download`.

## How it works

1. Downloads the same Downloader databases that update_all uses by default
   (cached in `~/.cache/mister-arcade-builder`):
   - MiSTer-devel `Distribution_MiSTer`
   - Jotego `jtcores_mister` (default filter: no `jtbeta` cores)
   - Coin-Op Collection `Distribution-MiSTerFPGA` (default filter: no alpha/beta)
2. Downloads and parses every `.mra` in those databases, including the
   `_alternatives` archives.
3. Indexes the input folders by CRC32 (zip entries and loose files). The index
   is cached, so a second run is fast.
4. For each `.mra`, finds every part by CRC and plans the output zips the same
   way MiSTer looks for them (`games/mame/<zip>`, or `games/<path>` when the
   zip name starts with `/`, for example `/hbmame/x.zip`).
5. Writes the zips (checks the CRC of every entry, atomic writes, same bytes
   on every run) and the report.

## Usage

```bash
python3 mister_arcade.py \
  --input "/Volumes/Extreme SSD/ROMs/Mame Roms" \
  --input "/Volumes/Extreme SSD/ROMs/Neo Geo CPS 1 & more roms" \
  --input "/Volumes/Extreme SSD/ROMs/CPS2 keys" \
  --output ~/Desktop/roms --complete-only --verify
```

Then copy `<output>/games/` to the root of the MiSTer SD card.

Main options:

| Option | What it does |
|---|---|
| `--input DIR` | ROM folder to read (repeat it for more folders) |
| `--output DIR` | where `games/` and the reports go |
| `--complete-only` | only write zips for games with every part found |
| `--one-per-game` | keep one revision per game: complete first, then by region |
| `--prefer-region LIST` | region order for `--one-per-game` (default `World,Europe,USA,Japan,Asia`) |
| `--verify` | build each complete ROM like the MiSTer loader and check its `md5` |
| `--dry-run` | only write the report |
| `--only REGEX` | only `.mra` whose file name, name or setname matches |
| `--db URL` / `--no-default-dbs` | add other databases / do not use the default ones |
| `--no-db-filters` | ignore the default filters of the databases |
| `--offline` | use only cached data |
| `--download` | try downloading missing ROMs from MDK split sets, then rebuild the resolution and reports |
| `--artwork` | download MDK screenshots, year, genre and manufacturer for the HTML report |
| `--cache DIR`, `--jobs N`, `-v` | cache folder, threads, more logging |

Exit codes: `0` ok, `1` error, `2` some `.mra` could not be parsed, `3`
`--verify` found problems.

Reports: `mister-arcade-report.json`, `.txt` and `.html` in the output folder.
The HTML page has filters, search, sorting and a "most wanted" list (the
missing files that would complete the most games).

With `--download`, the tool tries the set, parent and BIOS ZIP names listed by
incomplete `.mra` files at https://mdk.cab/download/split/. Archives are stored
in `<cache>/downloads/mdk/`; input folders are never modified. Every downloaded
archive is CRC checked before it is used, and parts are matched by the CRC
requested by the `.mra`, even when their names differ. MDK's current MAME sets
may not contain every version needed by MiSTer: unavailable or incompatible
parts remain missing in the reports. Downloads happen before `--one-per-game`
selection so newly completed revisions can be chosen. `--offline` uses cached
archives only; `--dry-run` also uses only cached archives and does not download.

To include game images and information in the report:

```bash
python3 mister_arcade.py --input "/path/to/ROMs" --output ~/Desktop/roms --artwork
```

`--artwork` is independent of `--download`: it does not download ROMs. It uses
each reported game's setname to read its MDK page and download available
screenshots and image assets. The HTML shows an in-game thumbnail, year, genre
and manufacturer, plus an image gallery in the expanded row and a source link.
Unavailable images or metadata are omitted. Results are cached in
`<cache>/artwork/mdk/`, with up to four simultaneous requests. `--offline` and
`--dry-run` reuse cached data without downloading. Images are copied to
`<output>/mister-arcade-assets/`: keep this folder beside the HTML when moving
or sharing the report to preserve offline viewing. MDK artwork ZIP archives
are not downloaded; only individual images linked by the game page are used.

## Rebuild ZIPs for FB Alpha

`convert_fbalpha.py` is a separate offline tool. It requires an **XML DAT for
the exact destination core/version**, rather than guessing from ZIP names:

```bash
python3 convert_fbalpha.py \
  --input ~/Desktop/roms/games/mame \
  --output ~/Desktop/fbalpha-roms \
  --dat /path/to/fbalpha.xml
```

Inputs are scanned recursively and `--input` can be repeated. ROMs are matched
by CRC32 and size, renamed according to the DAT and CRC checked while writing.
ZIPs include parent/BIOS requirements from `romof` (or `cloneof` when `romof`
is absent); child entries override parent entries with the same name. This can
include extra parent ROMs. Existing output ZIPs for complete sets are replaced
atomically; incomplete sets are not written and their existing ZIPs, if any,
are left untouched. Inputs and output must not overlap. The tool never changes
inputs or downloads ROMs.

`--only REGEX` restricts set names/descriptions; `--dry-run` writes only the
`fbalpha-report.json` report. By default, sets with any matching ROM or a named
input ZIP are considered; sets without any matching data are omitted unless
requested with `--only`. The report includes missing pieces, build errors and
input ZIP names absent from the DAT (these might still supply useful ROMs).
Exit codes: `0` complete, `1` error, `2` incomplete or unsupported sets.

Use a DAT exported for your target FB Alpha build, in Logiqx/ClrMamePro XML
format (`<datafile><game ...>` or `<machine ...>`). Plain text DATs and CHDs are
not supported. Games requiring CHDs (including inherited dependencies) are
listed under `unsupported` in the report and skipped; other games are still
converted. Repacking cannot create missing data or add support for games
the destination core does not emulate. FB Alpha, FB Alpha 2012 CPS-1 and
FinalBurn Neo are distinct targets; do not interchange their DATs.

## CPS2 keys

CPS2 games need a `<setname>.key` file inside the zip. `tools/cps2_keys.py`
makes them from the `keys.txt` list of the no-battery-cps2 project. It only
writes a key when its CRC matches the one a cached `.mra` asks for, so run the
main tool once first (to fill the cache).

```bash
python3 tools/cps2_keys.py --output "/Volumes/Extreme SSD/ROMs/CPS2 keys"
```

Known keys that do not match their `.mra` and are skipped: `1944`, `19xx`,
`batcirj`, `spf2t`.

## Code

| File | Role |
|---|---|
| `mister_arcade_builder/dbs.py` | download and cache databases and `.mra` files, apply db filters |
| `mister_arcade_builder/mra.py` | parse `.mra` files (with fallbacks for broken XML) |
| `mister_arcade_builder/index.py` | CRC index of the input folders |
| `mister_arcade_builder/resolve.py` | match `.mra` parts to files, plan the zips |
| `mister_arcade_builder/build.py` | write the zips |
| `mister_arcade_builder/verify.py` | port of MiSTer `mra_loader.cpp` for `--verify` |
| `mister_arcade_builder/select.py` | `--one-per-game` choice |
| `mister_arcade_builder/report.py`, `report_html.py` | reports |
| `mister_arcade_builder/cli.py` | command line |

## Behaviour that matches the MiSTer loader

These details come from `mra_loader.cpp` and were checked with real data:

- `zip="a.zip|b.zip"`: zips are tried in order. Inside a zip, a part is found
  by CRC first, then by name. Many `.mra` list several zips (clone, parent),
  so the tool puts all parts in the zip named after the setname.
- Several `<rom index="0">` blocks can exist; MiSTer uses the first one whose
  `md5` is right. The tool uses the block with the fewest missing parts.
- Roms with an index other than 0 are also needed (for example ST-V).
- `md5` is the md5 of the data stream before interleave. Jotego's `asm_md5` is
  the md5 after interleave but before `<patch>`.
- Tags and attributes are case-insensitive; numbers are read like `strtoul`.
- MiSTer finds `_Arcade/cores` from the first `/_` folder in the `.mra` path,
  so any custom `.mra` folder must be inside `_Arcade`.

## "Only shared" games

A game is "only shared" when all the files found for it are also used by more
than 2 other game families (BIOS, sound ROMs like `qsound_hle.zip`). These
games are not counted as partial, because in practice nothing of the game
itself is there.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

The tests run offline. `tests/fixtures/1941.mra` is the real Jotego 1941 file.
ROM data in the tests is fake, with forged CRC32 values.

## Notes and status

- Tested on a Mac only; no MiSTer hardware test yet. First hardware tests to
  do: 1941 (World), Dungeons & Dragons: Tower of Doom (CPS2 with key) and a
  game with a BIOS (Neo Geo or ST-V).
- The SD card can be prepared from a Mac with the Downloader PC Launcher.
- The zips are for MiSTer. RetroArch MAME cores need sets for their own MAME
  version.
- `qsound_hle.zip` (with `dl-1425.bin`) is the QSound file the CPS cores use.
- Idea not done yet: `--mra-folder`, to copy the chosen `.mra` files to
  `<output>/_Arcade/_<name>/` (it must be inside `_Arcade`).

## Analogue Pocket arcade ROMs

`pocket_arcade.py` writes the `.rom` files that Pocket arcade cores load: jotego's and the other
authors' ports of MiSTer arcade cores. Each core has one instance `.json` per game in
`Assets/<platform>/<author.core>/` naming a `.rom` in `Assets/<platform>/common/`; that file is the
ROM MiSTer assembles from the game's `.mra` (index 0, interleaves and patches), so it is built with
the same loader as `--verify` and written only when the md5 matches (or the `.mra` has none).
The `.mra` is found by set name (the `.rom` name, without a `_ap` suffix), then by game title.

```bash
python3 pocket_arcade.py --pocket /Volumes/Analogue \
  --games ~/.cache/pocket/mister_games --games ~/Desktop/roms/games \
  --mra ~/.cache/mister-arcade-builder/mra --mra ~/.cache/pocket/core_mras
```

`--games` (repeatable, tried in order) is a folder with `mame/` (and `hbmame/`) zips; the same zip
name can differ between collections, so each folder is tried before a game is given up.
`--mra` (repeatable) adds `.mra` folders; Pocket-only cores keep theirs in their own GitHub
repository. Only the main games are written: every version is a full ROM, and the
`_alternatives` ones do not fit on a small card (`--alternatives` adds them). It stops when the
card has less than `--keep-free` GB free.
