#!/usr/bin/env python3
"""Show the pictures of out/art on the MiSTerLily board connected to this computer.

    python3 show.py                        # slideshow of all pictures, 3 s each
    python3 show.py 'sf2*' SNES --interval 5 --loop
    python3 show.py --shuffle --loop
    python3 show.py --review               # one by one, with keys (below)

Review keys: Enter/Space/Right = next, b/Left = back, d = reject (moves the picture to
out/rejected/, fetch.py does not make it again), m = show the tty2oled picture, q = quit.
Review starts where the last review stopped; --start CORE starts somewhere else.

Patterns are shell-style (fnmatch) and match the core name. Without --port, the first
/dev/cu.usbmodem* is used.
"""
import argparse
import fnmatch
import glob
import json
import os
import random
import shutil
import sys
import termios
import time
import tty

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
ART = os.path.join(OUT, "art")
REJECTED = os.path.join(OUT, "rejected")
POSITION = os.path.join(OUT, ".review_position")


def load_misterlily(path):
    sys.path.insert(0, os.path.join(path, "mister"))
    try:
        import mdsserial
        import pictures
    except ImportError as e:
        sys.exit("cannot import mister/mdsserial.py and pictures.py from {}: {}".format(path, e))
    return mdsserial, pictures


def find_port():
    ports = sorted(glob.glob("/dev/cu.usbmodem*"))
    if not ports:
        sys.exit("no /dev/cu.usbmodem* found: is the board connected? Or use --port")
    return ports[0]


def art_files(patterns):
    files = {}
    for f in sorted(os.listdir(ART)):
        core, ext = os.path.splitext(f)
        if ext.lower() in (".png", ".jpg"):
            files[core] = os.path.join(ART, f)
    if patterns:
        files = {c: p for c, p in files.items() if any(fnmatch.fnmatchcase(c, pat) for pat in patterns)}
    return files


def title(core):
    p = os.path.join(HERE, "cache", "adb", core + ".json")
    try:
        with open(p) as f:
            return json.load(f).get("title", "")
    except (OSError, ValueError):
        return ""


class Board:
    def __init__(self, mdsserial, pictures, port):
        self.pictures = pictures
        self.port = mdsserial.Port(port)
        self.port.flush_stale()

    def close(self):
        self.port.close()

    def show(self, core, path):
        head, data = self.pictures.asset_frame(core, path)
        self.port.write(head + data)
        reply = (self.port.read_until(b"MDSIMG;", timeout=5.0) or b"") + self.port.read_for(0.2)
        text = reply.decode(errors="replace")
        if "MDSIMG;ok" not in text:
            return "error: " + (text.strip() or "no reply")
        return "ok"

    def show_mono(self, core, pics):
        pic = self.pictures.find_picture(pics, core) if pics else None
        if not pic:
            return "no tty2oled picture"
        self.port.write("CMDCOR,{},-1\n".format(core))
        time.sleep(0.2)
        self.port.write(self.pictures.decode_picture(pic))
        self.port.read_for(0.3)
        return "tty2oled " + os.path.relpath(pic, pics)


def read_key():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            ch += sys.stdin.read(2)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return {"\r": "next", " ": "next", "\x1b[C": "next", "b": "back", "\x1b[D": "back",
            "d": "reject", "m": "mono", "q": "quit", "\x03": "quit"}.get(ch, "")


def slideshow(board, files, opts):
    cores = list(files)
    while True:
        if opts.shuffle:
            random.shuffle(cores)
        for i, core in enumerate(cores, 1):
            status = board.show(core, files[core])
            print("[{}/{}] {} {} {}".format(i, len(cores), core, title(core), "" if status == "ok" else status))
            time.sleep(opts.interval)
        if not opts.loop:
            return


def review(board, files, opts):
    cores = list(files)
    start = opts.start
    if not start and os.path.exists(POSITION):
        with open(POSITION) as f:
            start = f.read().strip()
    i = cores.index(start) if start in cores else 0
    rejected = 0
    print("Enter/Space next, b back, d reject, m tty2oled picture, q quit")
    while 0 <= i < len(cores):
        core = cores[i]
        status = board.show(core, files[core])
        print("[{}/{}] {} {} {}".format(i + 1, len(cores), core, title(core), "" if status == "ok" else status))
        with open(POSITION, "w") as f:
            f.write(core)
        key = read_key()
        while key == "mono":
            print("   " + board.show_mono(core, opts.pics))
            key = read_key()
            if key == "mono":
                board.show(core, files[core])
                key = read_key()
        if key == "quit":
            break
        if key == "back":
            i = max(0, i - 1)
        elif key == "reject":
            os.makedirs(REJECTED, exist_ok=True)
            shutil.move(files[core], os.path.join(REJECTED, os.path.basename(files[core])))
            del cores[i]
            rejected += 1
            print("   rejected")
        else:
            i += 1
    if i >= len(cores) and os.path.exists(POSITION):
        os.remove(POSITION)
    print("{} rejected in this review".format(rejected))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("patterns", nargs="*", metavar="CORE", help="core names or patterns (default: all)")
    ap.add_argument("--port", help="serial device (default: first /dev/cu.usbmodem*)")
    ap.add_argument("--misterlily", default=os.path.join(os.path.dirname(HERE), "MISTerLily"),
                    help="MiSTerLily repo (default: ../MISTerLily)")
    ap.add_argument("--interval", type=float, default=3.0, help="seconds per picture in a slideshow")
    ap.add_argument("--shuffle", action="store_true", help="random order")
    ap.add_argument("--loop", action="store_true", help="repeat until Ctrl-C")
    ap.add_argument("--review", action="store_true", help="one by one with keys")
    ap.add_argument("--start", metavar="CORE", help="review: start at this core")
    ap.add_argument("--pics", default=os.path.join(HERE, "cache", "tty2oled"),
                    help="tty2oled pictures for the m key (default: cache/tty2oled)")
    opts = ap.parse_args()

    mdsserial, pictures = load_misterlily(os.path.expanduser(opts.misterlily))
    files = art_files(opts.patterns)
    if not files:
        sys.exit("no pictures in {} match".format(ART))
    if opts.pics and not os.path.isdir(opts.pics):
        opts.pics = None
    board = Board(mdsserial, pictures, opts.port or find_port())
    try:
        if opts.review:
            review(board, files, opts)
        else:
            slideshow(board, files, opts)
    except KeyboardInterrupt:
        print()
    finally:
        board.close()


if __name__ == "__main__":
    main()
