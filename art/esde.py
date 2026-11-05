#!/usr/bin/env python3
"""Show the system or game picked in ES-DE on the MiSTerLily board connected to this computer.

    python3 esde.py --install       # writes the hooks into ~/ES-DE/scripts/
    python3 esde.py --uninstall
    python3 esde.py game-start '/path/1942.zip' '1942' mame 'MAME'   # what a hook runs

ES-DE runs the hooks on its custom events (enable "Custom event scripts" in Other settings;
"Browsing custom events" adds system-select and game-select while scrolling).

What is shown:
  - arcade games (mame, fbneo, neogeo...): out/art/<set>.png, then the tty2oled picture
    <set>.gsc/.xbm, then the game name. Neo Geo falls back to its system logo.
  - other games and systems: the system picture out/art/<CORE>.png (SYSTEMS below), else its name.
  - startup and quit: the clock screen.

No MDSPING is ever sent: after one the board expects a ping every few seconds and shows
"Waiting for MiSTer" when they stop. Without one, a picture stays until the next one.
"""
import fcntl
import glob
import os
import stat
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "out", "art")
PICS = os.path.join(HERE, "cache", "tty2oled")
MISTERLILY = os.path.join(os.path.dirname(HERE), "display")
STATE = os.path.join(HERE, "out", ".esde")
LOG = os.path.join(HERE, "out", "esde.log")
ESDE_SCRIPTS = os.path.expanduser("~/ES-DE/scripts")
EVENTS = ["startup", "quit", "system-select", "game-select", "game-start", "game-end"]
HOOK_NAME = "misterlily.sh"

# ES-DE system name -> MiSTer core picture name in out/art.
SYSTEMS = {
    "3do": "3DO", "amiga": "Minimig", "amstradcpc": "Amstrad", "atari2600": "ATARI2600",
    "atari5200": "ATARI5200", "atari7800": "ATARI7800", "atarijaguar": "Jaguar",
    "atarilynx": "AtariLynx", "atarist": "AtariST", "c64": "C64", "colecovision": "Coleco",
    "fds": "FDS", "famicom": "NES", "gamegear": "GameGear", "gb": "GAMEBOY", "gba": "GBA",
    "gbc": "GBC", "genesis": "Genesis", "intellivision": "Intellivision", "mastersystem": "SMS",
    "megacd": "MegaCD", "megadrive": "MegaDrive", "msx": "MSX", "n64": "N64", "neogeo": "NEOGEO",
    "nes": "NES", "pcengine": "TGFX16", "pokemini": "PokemonMini", "psx": "PSX", "saturn": "Saturn",
    "sega32x": "S32X", "segacd": "MegaCD", "sfc": "SNES", "sg-1000": "SG1000", "snes": "SNES",
    "tg16": "TGFX16", "vectrex": "VECTREX", "vic20": "VIC20", "wonderswan": "WONDERSWAN",
    "x68000": "X68000", "zx81": "ZX81", "zxspectrum": "Spectrum",
}
# ROM file names in these systems are MAME set names, like the tty2oled arcade pictures.
ARCADE = {"arcade", "mame", "fbneo", "fba", "neogeo", "cps1", "cps2", "cps3", "naomi", "atomiswave"}
ARCADE_LABELS = {"fbneo": "FinalBurn Neo", "neogeo": "Neo Geo"}


def log(msg):
    try:
        if os.path.getsize(LOG) > 200_000:
            os.replace(LOG, LOG + ".old")
    except OSError:
        pass
    with open(LOG, "a") as f:
        f.write("{} {}\n".format(time.strftime("%Y-%m-%d %H:%M:%S"), msg))


def art(name):
    p = os.path.join(ART, name + ".png")
    return p if os.path.exists(p) else None


def tty2oled_picture(name):
    # Exact name only: the prefix search of the MiSTer daemon would match unrelated sets here.
    for folder in ("GSC", "XBM"):
        p = os.path.join(PICS, folder, "{}.{}".format(name, folder.lower()))
        if os.path.exists(p):
            return p
    return None


def label(text):
    return text.replace(",", " ").replace("\n", " ").strip()[:40]


def system_target(system, full_name):
    core = SYSTEMS.get(system)
    if core and art(core):
        return ("art", core, art(core))
    if system in ARCADE:
        return ("text", ARCADE_LABELS.get(system, "Arcade"), None)
    return ("text", label(full_name or system), None)


def game_target(rom, name, system, full_name):
    if system in ARCADE:
        game = os.path.splitext(os.path.basename(rom.rstrip("/")))[0]
        if art(game):
            return ("art", game, art(game))
        if tty2oled_picture(game):
            return ("mono", game, tty2oled_picture(game))
        if system != "neogeo":
            return ("text", label(name or game), None)
    return system_target(system, full_name)


def target_for(event, args):
    args = list(args) + [""] * 5
    if event in ("startup", "quit"):
        return ("clock", "MENU", None)
    if event == "system-select":
        return system_target(args[0], args[1])
    if event in ("game-select", "game-start", "game-end"):
        if not args[2]:
            return None  # ES-DE sends game-select with blank arguments when fast scrolling starts
        if event == "game-end":
            return system_target(args[2], args[3])
        return game_target(args[0], args[1], args[2], args[3])
    return None


def send(port, pictures, target):
    kind, name, path = target
    if kind == "art":
        head, data = pictures.asset_frame(name, path)
        port.write(head + data)
    elif kind == "mono":
        port.write("CMDCOR,{},-1\n".format(name).encode() + pictures.decode_picture(path))
    elif kind == "clock":
        # Local wall time, as the MiSTer daemon sends it; without it the clock screen has no time.
        port.write("CMDSETTIME,{}\n".format(int(time.time() + time.localtime().tm_gmtoff)))
        port.write("MDSCORE,MENU\n")
    else:
        port.write("MDSCORE,{}\n".format(name))


def show(event, args):
    target = target_for(event, args)
    if not target:
        return
    key = "|".join(t or "" for t in target[:2])
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    # Browsing events run in parallel when ES-DE does not wait for them. The last request wins,
    # and only one process talks to the board at a time.
    with open(STATE + ".want", "w") as f:
        f.write(key)
    with open(STATE + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with open(STATE + ".want") as f:
            if f.read() != key:
                return
        try:
            with open(STATE + ".shown") as f:
                shown = f.read()
        except OSError:
            shown = ""
        if key == shown and event != "startup":
            return
        ports = sorted(glob.glob("/dev/cu.usbmodem*"))
        if not ports:
            log("{}: no board connected".format(event))
            return
        sys.path.insert(0, os.path.join(MISTERLILY, "mister"))
        import mdsserial
        import pictures
        with mdsserial.Port(ports[0]) as port:
            port.flush_stale()
            send(port, pictures, target)
        with open(STATE + ".shown", "w") as f:
            f.write(key)
        log("{} {} -> {} {}".format(event, args, target[0], target[1]))


def install():
    python = sys.executable
    for event in EVENTS:
        d = os.path.join(ESDE_SCRIPTS, event)
        os.makedirs(d, exist_ok=True)
        hook = os.path.join(d, HOOK_NAME)
        with open(hook, "w") as f:
            f.write('#!/bin/sh\nexec "{}" "{}" {} "$@"\n'.format(python, os.path.abspath(__file__), event))
        os.chmod(hook, os.stat(hook).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print("wrote " + hook)
    print('Now enable "Custom event scripts" in ES-DE: Main menu > Other settings.')


def uninstall():
    for event in EVENTS:
        hook = os.path.join(ESDE_SCRIPTS, event, HOOK_NAME)
        if os.path.exists(hook):
            os.remove(hook)
            print("removed " + hook)


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        sys.exit(__doc__)
    if sys.argv[1] == "--install":
        return install()
    if sys.argv[1] == "--uninstall":
        return uninstall()
    try:
        show(sys.argv[1], sys.argv[2:])
    except Exception as e:  # never let a display problem disturb ES-DE
        log("{} {}: {}: {}".format(sys.argv[1], sys.argv[2:], type(e).__name__, e))


if __name__ == "__main__":
    main()
