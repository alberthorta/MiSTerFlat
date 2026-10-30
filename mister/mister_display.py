#!/usr/bin/env python3
"""MiSTerLily daemon: shows the running MiSTer core on the T-Display-S3.

Replaces the tty2oled daemon (and reuses its picture library). For every core change in
/tmp/CORENAME it sends, in this order of preference:
  1. a colour picture  <ART_DIR>/<core>.png|.jpg            -> MDSIMG
  2. a tty2oled picture <TTY2OLED_PICS>/...gsc|.xbm           -> CMDCOR + raw bytes
  3. the name only                                           -> MDSCORE,<core>

It finds the display with find-display.sh, keeps the port open, reads every reply (so nothing
piles up in the device), and when the display disappears it waits for it, sets the port up again
and resends the current core. Every few seconds it sends MDSPING: the uptime in the answer shows a
board restart (watchdog, CMDRESET), after which the core is sent again; no answer at all for a while
means the display is stuck or gone, and the port is opened again. While /tmp/tty2oled_sleep exists
(MiSTer SAM) it sends nothing.

Usage (normally started by S60misterlily):
  python3 mister_display.py [--config FILE] [--device DEV] [--corename FILE] [-v]
"""
import argparse
import binascii
import os
import re
import signal
import socket
import subprocess
import sys
import termios
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mdsserial import Port  # noqa: E402
from pictures import asset_frame, decode_picture, find_art, find_picture  # noqa: E402

DEFAULTS = {
    "MDS_SERIAL": "",
    "TTYDEV": "",  # fixed device instead of auto-detection
    "ART_DIR": "/media/fat/MiSTerLily/art",
    "TTY2OLED_PICS": "/media/fat/tty2oled/pics",
    "USE_TTY2OLED_PICS": "yes",
    "USE_GSC_PICTURE": "yes",
    "USE_US_PICTURE": "no",
    "USE_TEXT_PICTURE": "no",
    "CONTRAST": "255",
    "ROTATE": "no",
    "IDLE_MINUTES": "",  # backlight off after this many minutes without a core change; "" = keep the board's
    "IDLE_SCREEN": "",  # what idle shows: "off" (dark) or "clock" (dim clock); "" = keep the board's
    "FADE": "",  # backlight dip on core changes: "yes"/"no"; "" = keep the board's (default yes)
    "MENU_SCREEN": "clock",  # MiSTer menu: "clock" (built-in clock screen) or "picture" (tty2oled MENU logo)
}
SLEEP_FILE = "/tmp/tty2oled_sleep"
POLL_SECONDS = 0.1
RETRY_SECONDS = 2.0
PING_SECONDS = 5.0
# No answer for this long: give up on the port and look for the display again.
PONG_TIMEOUT_SECONDS = 15.0
# The board's clock drifts with its crystal; refresh it now and then. Also how often the IP is checked.
TIME_RESEND_SECONDS = 600.0
# The daemon starts about 15 s after boot. Without a working RTC the system time is still wrong
# then, and NTP fixes it a few seconds later: the display showed the wrong time until the next
# resend. A jump of the local wall clock against the monotonic clock (NTP, hwclock, date, DST)
# larger than this sends the time at once.
CLOCK_JUMP_SECONDS = 2.0
IP_CHECK_SECONDS = 30.0
# A device node must exist this long before we open it: the kernel creates /dev/ttyACMn a moment
# before the port is usable.
SETTLE_SECONDS = 0.5

verbose = False


def log(msg):
    sys.stderr.write("{} {}\n".format(time.strftime("%H:%M:%S"), msg))
    sys.stderr.flush()


def debug(msg):
    if verbose:
        log(msg)


def read_config(path):
    """KEY="value" lines, as in config.ini (also shell-sourceable)."""
    cfg = dict(DEFAULTS)
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                cfg[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return cfg


def find_device(cfg):
    if cfg["TTYDEV"]:
        return cfg["TTYDEV"] if os.path.exists(cfg["TTYDEV"]) else None
    env = dict(os.environ, MDS_SERIAL=cfg["MDS_SERIAL"])
    try:
        out = subprocess.run(["bash", os.path.join(HERE, "find-display.sh"), "--quiet"], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    dev = out.decode(errors="replace").strip()
    return dev or None


def local_ip():
    """The address of the interface that would reach the internet; "" without a network.
    connect() on a UDP socket sends nothing, it only picks the route."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))  # TEST-NET-1, never actually contacted
        return s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()


def wall_offset():
    """Local wall clock minus the monotonic clock: constant until someone sets the time."""
    return time.time() + time.localtime().tm_gmtoff - time.monotonic()


def read_core(path):
    try:
        with open(path, "rb") as f:
            return f.read().decode("utf-8", "replace").strip()
    except OSError:
        return None


def core_stamp(path):
    """Changes whenever MiSTer rewrites the file, even with the same core (like inotify modify)."""
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size, st.st_ino)
    except OSError:
        return None


class Display:
    def __init__(self, cfg):
        self.cfg = cfg
        self.port = None
        self.path = None
        self.last_pong = 0.0
        self.next_ping = 0.0
        self.uptime = None
        self.pending = b""
        self.restarted = False  # set when a pong shows a lower uptime than before
        self.pending = b""  # a reply line split across reads
        self.next_time = 0.0
        self.sent_offset = 0.0
        self.next_ip_check = 0.0
        self.ip = None

    def connected(self):
        return self.port is not None

    def connect(self, path):
        self.port = Port(path)
        self.path = path
        log("display connected: {}".format(path))
        self.setup()

    def setup(self):
        """Settings the display needs after it was plugged in or restarted."""
        self.port.flush_stale()
        # We read every reply ourselves; acks would only add traffic.
        self.port.write("CMDSTTYACK,0\n")
        self.port.write("CMDCON,{}\n".format(self.cfg["CONTRAST"]))
        self.port.write("CMDROT,{}\n".format(1 if self.cfg["ROTATE"] == "yes" else 0))
        if self.cfg["IDLE_MINUTES"].isdigit():
            self.port.write("MDSCFG,idle,{}\n".format(int(self.cfg["IDLE_MINUTES"])))
        if self.cfg["IDLE_SCREEN"] in ("off", "clock"):
            self.port.write("MDSCFG,idleclock,{}\n".format(1 if self.cfg["IDLE_SCREEN"] == "clock" else 0))
        if self.cfg["FADE"] in ("yes", "no"):
            self.port.write("MDSCFG,fade,{}\n".format(1 if self.cfg["FADE"] == "yes" else 0))
        self.send_time()
        self.ip = None
        self.next_ip_check = 0.0
        self.sync_logo()
        self.last_pong = time.monotonic()
        self.next_ping = 0.0
        self.uptime = None

    def release(self):
        """Leaves the display as tty2oled expects it (acks on), e.g. before switching modes."""
        if self.port:
            try:
                self.port.write("CMDSTTYACK,1\n")
                self.port.close()
            except (OSError, termios.error):
                pass
            self.port = None

    def disconnect(self, why):
        if self.port:
            try:
                self.port.fd is not None and os.close(self.port.fd)
            except OSError:
                pass
            self.port.fd = None
            self.port = None
            log("display lost ({})".format(why))

    def still_there(self):
        return self.port is not None and os.path.exists(self.path)

    def sync_logo(self):
        """Stores <ART_DIR>/STARTUP.png|jpg as the display's start-up picture when it differs from
        what the display has. The display keeps it in flash, so it is written only on changes."""
        path = None
        for ext in ("png", "jpg"):
            p = os.path.join(self.cfg["ART_DIR"], "STARTUP." + ext)
            if os.path.exists(p):
                path = p
                break
        if not path:
            return
        with open(path, "rb") as f:
            data = f.read()
        crc = binascii.crc32(data) & 0xFFFFFFFF
        self.port.write("MDSLOGO\n")
        reply = self.port.read_until(b"MDSLOGO;", 2.0)
        reply = (reply or b"") + (self.port.read_until(b"\n", 1.0) or b"")
        m = re.search(rb"MDSLOGO;crc=([0-9a-f]{8})", reply)
        if m and int(m.group(1), 16) == crc:
            debug("start-up picture already on the display")
            return
        if not m and b"MDSLOGO;none" not in reply:
            log("display does not answer MDSLOGO (old firmware?), start-up picture not sent")
            return
        fmt = "jpg" if path.endswith(".jpg") else "png"
        self.port.write("MDSLOGO,{},{:08x},{}\n".format(len(data), crc, fmt).encode() + data)
        log("start-up picture {} sent ({} bytes)".format(os.path.basename(path), len(data)))

    def send_time(self):
        # Local wall time as epoch seconds, the tty2oled convention (CMDSETTIME).
        self.port.write("CMDSETTIME,{}\n".format(int(time.time() + time.localtime().tm_gmtoff)))
        self.sent_offset = wall_offset()
        self.next_time = time.monotonic() + TIME_RESEND_SECONDS

    def housekeeping(self, now):
        if now >= self.next_time or abs(wall_offset() - self.sent_offset) > CLOCK_JUMP_SECONDS:
            self.send_time()
        if now >= self.next_ip_check:
            self.next_ip_check = now + IP_CHECK_SECONDS
            ip = local_ip()
            if ip != self.ip:
                self.ip = ip
                self.port.write("MDSNET,{}\n".format(ip))
                debug("ip {}".format(ip or "none"))

    def heartbeat(self, now):
        """Pings the display; raises OSError if it stopped answering."""
        if now - self.last_pong > PONG_TIMEOUT_SECONDS:
            raise OSError("display not answering")
        if now >= self.next_ping:
            self.port.write("MDSPING\n")
            self.next_ping = now + PING_SECONDS

    def drain(self):
        """Reads replies; logs picture errors. Raises OSError if the device went away."""
        lines = (self.pending + self.port.read_available()).split(b"\n")
        self.pending = lines.pop()[-256:]  # unterminated tail; bounded in case of garbage
        for line in lines:
            if line.startswith(b"MDSPONG"):
                self.last_pong = time.monotonic()
                up = line.split(b"up=", 1)[1] if b"up=" in line else b""
                if up.isdigit():
                    if self.uptime is not None and int(up) < self.uptime:
                        log("display restarted (uptime {} ms)".format(int(up)))
                        self.restarted = True
                    self.uptime = int(up)
            elif line.startswith(b"MDSIMG;err"):
                log("display: " + line.decode(errors="replace"))
            elif line.strip():
                debug("display: {!r}".format(line))

    def show(self, core):
        cfg = self.cfg
        art = find_art(cfg["ART_DIR"], core)
        if art:
            head, data = asset_frame(core, art)
            self.port.write(head + data)
            log("{} -> colour picture {} ({} bytes)".format(core, os.path.basename(art), len(data)))
            return
        if core == "MENU" and cfg["MENU_SCREEN"] == "clock":
            # The display draws its clock screen for MENU when no picture comes with it.
            self.port.write("MDSCORE,MENU\n")
            log("MENU -> clock screen")
            return
        if cfg["USE_TTY2OLED_PICS"] == "yes":
            pic = find_picture(cfg["TTY2OLED_PICS"], core, cfg["USE_US_PICTURE"] == "yes",
                               cfg["USE_GSC_PICTURE"] == "yes", cfg["USE_TEXT_PICTURE"] == "yes")
            if pic:
                data = decode_picture(pic)
                # Our firmware switches to binary mode at once, no pause needed like tty2oled.sh.
                self.port.write("CMDCOR,{},-1\n".format(core).encode() + data)
                log("{} -> tty2oled picture {}".format(core, os.path.relpath(pic, cfg["TTY2OLED_PICS"])))
                return
        self.port.write("MDSCORE,{}\n".format(core))
        log("{} -> name only".format(core))


def run(args, display):
    cfg = display.cfg
    last_stamp = None
    shown = None  # core currently on the display
    next_search = 0.0
    sleeping = False
    log("started (config {}, corename {})".format(args.config, args.corename))

    while True:
        now = time.monotonic()
        if not display.connected():
            if now >= next_search:
                dev = find_device(cfg)
                if dev:
                    time.sleep(SETTLE_SECONDS)
                    try:
                        display.connect(dev)
                        shown = None  # resend the current core
                    except (OSError, termios.error) as e:
                        display.disconnect("open failed: {}".format(e))
                if not display.connected():
                    next_search = now + RETRY_SECONDS
            time.sleep(POLL_SECONDS)
            continue

        try:
            if not display.still_there():
                raise OSError("device node gone")
            display.drain()
            display.heartbeat(time.monotonic())
            display.housekeeping(time.monotonic())
            if display.restarted:
                # The board lost its settings and picture: set it up again and resend.
                display.restarted = False
                display.setup()
                shown = None

            if os.path.exists(SLEEP_FILE):
                if not sleeping:
                    log("sleep file present, pausing")
                    sleeping = True
            else:
                if sleeping:
                    log("sleep file gone, resuming")
                    sleeping = False
                    shown = None
                stamp = core_stamp(args.corename)
                core = read_core(args.corename) if stamp else None
                if core and (stamp != last_stamp or shown is None):
                    display.show(core)
                    shown = core
                    last_stamp = stamp
        except (OSError, termios.error) as e:  # tcdrain() raises termios.error on a dead port
            display.disconnect(str(e))
            next_search = time.monotonic() + RETRY_SECONDS
        time.sleep(POLL_SECONDS)


def main():
    global verbose
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=os.path.join(HERE, "config.ini"))
    ap.add_argument("--device", help="use this device instead of find-display.sh")
    ap.add_argument("--corename", default="/tmp/CORENAME")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    verbose = args.verbose
    cfg = read_config(args.config)
    if args.device:
        cfg["TTYDEV"] = args.device
    display = Display(cfg)
    # S60misterlily stop sends SIGTERM: leave the display in tty2oled's default state.
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        run(args, display)
    except KeyboardInterrupt:
        display.release()
        log("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
