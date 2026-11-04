#!/usr/bin/env python3
"""MiSTerLily daemon: shows the running MiSTer core on the T-Display-S3.

Replaces the tty2oled daemon (and reuses its picture library). For every core change in
/tmp/CORENAME it sends, in this order of preference:
  1. a colour picture  <ART_DIR>/<core>.png|.jpg            -> MDSIMG
  2. a tty2oled picture <TTY2OLED_PICS>/...gsc|.xbm           -> CMDCOR + raw bytes
  3. the name only                                           -> MDSCORE,<core>
In the MiSTer menu it also shows the colour picture of the core under the cursor of the core
browser (menu_browse.py), and the menu screen again on a folder, on a core without a picture, or
after a minute without moving.

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
import fcntl
import os
import re
import signal
import socket
import struct
import subprocess
import sys
import termios
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from buttons import Buttons, Volume  # noqa: E402
from mdsserial import Port  # noqa: E402
from pictures import asset_frame, decode_picture, find_art, find_picture  # noqa: E402
import display_settings  # noqa: E402
import menu_browse  # noqa: E402
import wifi  # noqa: E402

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
    # In the MiSTer menu, show the picture of the core under the cursor (needs log_file_entry=1).
    "MENU_BROWSE": "yes",
    # Power relay on the display (docs/power.md): "yes" switches the MiSTer on as soon as the box
    # gets power, "no" waits in standby for a tap; "" = keep the board's (default no).
    "POWER_AUTO_ON": "",
}
SLEEP_FILE = "/tmp/tty2oled_sleep"
# Firmware version of the connected display, for misterlily_flash.py and MiSTerManager, which
# cannot ask the board themselves while the daemon holds the port. Removed when the display goes.
FW_FILE = "/tmp/misterlily_fw"
BOARD_FILE = "/tmp/misterlily_board"  # its CMDHWINF id, a key of BOARDS in mdsserial.py
TOUCH_BOARDS = {"HWWSTLCD2"}  # boards that send MDSBTN
# Firmware from this version on has the Wi-Fi screen (MDSWIFI). Older firmware shows any MDS line it
# does not know as a core name, so it never gets MDSWIFI lines.
WIFI_SINCE = (0, 3, 0)
VOLUME_SINCE = (0, 4, 0)  # the volume row on the touch buttons (MDSVOL)
SETTINGS_SINCE = (0, 4, 1)  # MDSCFG,brightness and MDSCFG,clockfont, for display_settings.py
# How often the display's settings are asked for, so a change on the touch screen reaches
# /tmp/misterlily_cfg; also how long a command from /tmp/misterlily_cmd may wait.
SETTINGS_CHECK_SECONDS = 2.0
# Volume changed some other way (keyboard, OSD menu) shows on the display after at most this long.
VOLUME_CHECK_SECONDS = 2.0
HWINF_RE = re.compile(rb"(HW[0-9A-Z]{7});MDS-([0-9A-Za-z.+-]{1,32});")
POLL_SECONDS = 0.1
RETRY_SECONDS = 2.0
PING_SECONDS = 5.0
# No answer for this long: give up on the port and look for the display again.
PONG_TIMEOUT_SECONDS = 15.0
# The board's clock drifts with its crystal; refresh it now and then.
TIME_RESEND_SECONDS = 600.0
# The daemon starts about 15 s after boot. Without a working RTC the system time is still wrong
# then, and NTP fixes it a few seconds later: the display showed the wrong time until the next
# resend. A jump of the local wall clock against the monotonic clock (NTP, hwclock, date, DST)
# larger than this sends the time at once.
CLOCK_JUMP_SECONDS = 2.0
# The cursor must rest on a core this long before its picture is sent: scrolling through the list
# does not queue a picture for every line it passes.
BROWSE_SETTLE_SECONDS = 0.3
# A picture from the menu cursor stays this long without a move, then the menu screen comes back.
BROWSE_IDLE_SECONDS = 60.0
# How often the network addresses are checked: an unplugged cable leaves the clock screen this fast.
IP_CHECK_SECONDS = 10.0
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


SIOCGIFADDR = 0x8915
NET_KINDS = (("eth", ("eth", "en")), ("wifi", ("wlan", "wl")))


def iface_ip(name):
    """IPv4 address of a network interface, "" if it has none."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        req = struct.pack("256s", name[:15].encode())
        return socket.inet_ntoa(fcntl.ioctl(s.fileno(), SIOCGIFADDR, req)[20:24])
    except OSError:
        return ""
    finally:
        s.close()


def network_text(net_dir="/sys/class/net"):
    """The MDSNET text: "eth=<ip> wifi=<ip>" for each wired or Wi-Fi interface that is connected
    and has an address. Older firmware shows the text as it is, which still reads well. Falls back
    to the bare address of the default route (other interface names, or no /sys)."""
    found = {}
    try:
        names = sorted(os.listdir(net_dir))
    except OSError:
        names = []
    for name in names:
        try:
            with open(os.path.join(net_dir, name, "carrier")) as f:
                if f.read().strip() != "1":
                    continue
        except OSError:
            continue
        for kind, prefixes in NET_KINDS:
            if name.startswith(prefixes) and kind not in found:
                ip = iface_ip(name)
                if ip:
                    found[kind] = ip
    parts = ["{}={}".format(kind, found[kind]) for kind, _ in NET_KINDS if kind in found]
    return " ".join(parts) or local_ip()


def write_fw_version(version, board=None):
    """None removes the files. Written through temporary files so readers never see half of one."""
    for path, value in ((FW_FILE, version), (BOARD_FILE, board)):
        try:
            if version is None:
                os.remove(path)
            else:
                with open(path + ".tmp", "w") as f:
                    f.write(value + "\n")
                os.replace(path + ".tmp", path)
        except OSError:
            pass


def version_tuple(version):
    """(0, 3, 0) for "0.3.0" or "0.3.0-rc1"; () when it does not start with a number."""
    out = []
    for part in version.split("-", 1)[0].split("."):
        if not part.isdigit():
            break
        out.append(int(part))
    return tuple(out)


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
        self.buttons = Buttons()
        self.volume = Volume()
        self.volume_row = False  # the board has the volume row
        self.sent_volume = None
        self.next_volume_check = 0.0
        self.settings_file = False  # the board takes MDSCFG,brightness/clockfont
        self.next_settings_check = 0.0
        self.wifi_screen = False  # the board has the Wi-Fi screen
        self.wifi_dongle = None  # last state sent to it
        self.wifi_busy = False
        # Lines from the Wi-Fi worker thread; only the main loop writes to the port.
        self.outbox = []
        self.outbox_lock = threading.Lock()

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
        if self.cfg["POWER_AUTO_ON"] in ("yes", "no"):
            self.port.write("MDSCFG,autoon,{}\n".format(1 if self.cfg["POWER_AUTO_ON"] == "yes" else 0))
        self.send_time()
        self.ip = None
        self.next_ip_check = 0.0
        self.wifi_dongle = None
        self.sync_logo()
        # After sync_logo: its read_until() would swallow the reply. drain() picks it up.
        self.port.write("CMDHWINF\n")
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
        write_fw_version(None)
        display_settings.write_state(None)
        self.settings_file = False

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
        self.flush_outbox()
        if now >= self.next_time or abs(wall_offset() - self.sent_offset) > CLOCK_JUMP_SECONDS:
            self.send_time()
        if now >= self.next_ip_check:
            self.next_ip_check = now + IP_CHECK_SECONDS
            ip = network_text()
            if ip != self.ip:
                self.ip = ip
                self.port.write("MDSNET,{}\n".format(ip))
                debug("ip {}".format(ip or "none"))
            if self.wifi_screen:
                dongle = wifi.dongle_present()
                if dongle != self.wifi_dongle:
                    self.wifi_dongle = dongle
                    self.port.write("MDSWIFI,dongle,{}\n".format(int(dongle)))
        if self.settings_file and now >= self.next_settings_check:
            self.next_settings_check = now + SETTINGS_CHECK_SECONDS
            for setting, value in display_settings.take_commands():
                self.port.write("MDSCFG,{},{}\n".format(setting, value))
                log("display {} set to {}".format(setting, value))
            self.port.write("MDSCFG\n")  # the reply goes to /tmp/misterlily_cfg (drain)
        if self.volume_row and now >= self.next_volume_check:
            self.next_volume_check = now + VOLUME_CHECK_SECONDS
            self.send_volume(self.volume.read())

    def send_volume(self, volume):
        if volume != self.sent_volume:
            self.sent_volume = volume
            self.port.write("MDSVOL,{},{}\n".format(volume[0], int(volume[1])))

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
            elif line.startswith(b"MDSCFG;"):
                if self.settings_file:
                    cfg = display_settings.parse_cfg(line)
                    if cfg:
                        display_settings.write_state(cfg)
            elif line.startswith(b"MDSIMG;err"):
                log("display: " + line.decode(errors="replace"))
            elif line.startswith(b"MDSWIFI,") and self.wifi_screen:
                self.wifi_request(line[len(b"MDSWIFI,"):].strip().decode(errors="replace"))
            elif line.startswith(b"MDSBTN,"):
                self.press(line[len(b"MDSBTN,"):].strip().decode(errors="replace"))
            elif HWINF_RE.search(line):
                board, version = (g.decode() for g in HWINF_RE.search(line).groups())
                write_fw_version(version, board)
                debug("display {} firmware {}".format(board, version))
                self.wifi_screen = board in TOUCH_BOARDS and version_tuple(version) >= WIFI_SINCE
                self.volume_row = board in TOUCH_BOARDS and version_tuple(version) >= VOLUME_SINCE
                self.settings_file = version_tuple(version) >= SETTINGS_SINCE
                self.next_settings_check = 0.0
                self.sent_volume = None
                self.next_volume_check = 0.0
                self.wifi_dongle = None
                self.next_ip_check = 0.0  # tell it about the dongle now
                if board in TOUCH_BOARDS:
                    try:
                        self.buttons.prepare()
                    except OSError as e:
                        log("touch buttons will not work: {}".format(e))
            elif line.strip():
                debug("display: {!r}".format(line))

    def wifi_request(self, request):
        """MDSWIFI,scan or MDSWIFI,join,<ssid hex>,<password hex> from the Wi-Fi screen. Scanning
        takes about 12 s and joining up to 30 s, so a thread does it; the replies go out from the
        main loop (flush_outbox)."""
        if self.wifi_busy:
            return
        parts = request.split(",")
        if parts[0] == "scan":
            target = self.wifi_scan
        elif parts[0] == "join" and len(parts) == 3:
            try:
                ssid, password = bytes.fromhex(parts[1]), bytes.fromhex(parts[2]).decode()
            except ValueError:
                return
            log("wifi: joining {}".format(ssid.decode(errors="replace")))
            target = lambda: self.wifi_join(ssid, password)  # noqa: E731
        else:
            return
        self.wifi_busy = True
        threading.Thread(target=target, daemon=True).start()

    def queue(self, line):
        with self.outbox_lock:
            self.outbox.append(line)

    def flush_outbox(self):
        with self.outbox_lock:
            lines, self.outbox = self.outbox, []
        for line in lines:
            self.port.write(line)

    def wifi_scan(self):
        self.queue("MDSWIFI,scanning\n")
        try:
            for ssid, signal, secure, linked in wifi.scan():
                self.queue("MDSWIFI,net,{},{},{},{}\n".format(signal, int(secure), int(linked), ssid.hex()))
        except (OSError, subprocess.SubprocessError) as e:
            log("wifi scan failed: {}".format(e))
        self.queue("MDSWIFI,end\n")
        self.wifi_busy = False

    def wifi_join(self, ssid, password):
        self.queue("MDSWIFI,status,connecting\n")
        try:
            ip = wifi.join(ssid, password, lambda: iface_ip(wifi.IFACE))
            log("wifi: on {} as {}".format(ssid.decode(errors="replace"), ip))
            self.queue("MDSWIFI,status,ok,{}\n".format(ip))
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            log("wifi: join failed: {}".format(e))
            self.queue("MDSWIFI,status,fail,{}\n".format(str(e)[:80].replace("\n", " ")))
        self.next_ip_check = 0.0  # show the new address on the clock at once
        self.wifi_busy = False

    def press(self, name):
        """A touch button on the display (boards with a touch panel)."""
        log("display button {}".format(name))
        try:
            if name in ("volup", "voldown"):
                self.send_volume(self.volume.step(name == "volup"))
                return
            if name.startswith("vol,"):
                self.send_volume(self.volume.set(int(name[4:])))
                return
            if name == "poweroff":
                # The display opens the power relay a while after MDSPOWER,halting; the sync
                # comes first, so the SD card is safe even if the shutdown is slow.
                self.buttons.power_off(lambda: self.port.write("MDSPOWER,halting\n"))
                return
            self.buttons.press(name)
        except (OSError, ValueError) as e:
            log("button {} failed: {}".format(name, e))

    def show_browse(self, core, art):
        """Picture of the core under the menu cursor; the menu screen when there is none."""
        if not art:
            self.show("MENU")
            return
        head, data = asset_frame(core, art)
        self.port.write(head + data)
        debug("menu cursor on {} -> {}".format(core, os.path.basename(art)))

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
    # Menu browser: the picture for the cursor position, since when, and the one on the display.
    pick, pick_since, browsed = None, 0.0, None
    # The /tmp files are read every poll; the folder and the art directory only when they change.
    last_sel, last_sel_core, last_sel_art, sel_since = None, None, None, 0.0
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
                    browsed = None  # show() put the plain menu screen (or a core) up
                if core == "MENU" and cfg["MENU_BROWSE"] == "yes":
                    sel = menu_browse.selection()
                    now = time.monotonic()
                    if sel != last_sel:
                        last_sel, sel_since = sel, now
                        last_sel_core = menu_browse.core_for(*sel) if sel else None
                        last_sel_art = find_art(cfg["ART_DIR"], last_sel_core) if last_sel_core else None
                    if last_sel_art != pick:
                        pick, pick_since = last_sel_art, now
                    # After a while without moving, the menu screen (clock) comes back.
                    want = None if now - sel_since >= BROWSE_IDLE_SECONDS else pick
                    if want != browsed and now - pick_since >= BROWSE_SETTLE_SECONDS:
                        display.show_browse(last_sel_core, want)
                        browsed = want
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
