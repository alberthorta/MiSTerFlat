#!/usr/bin/env python3
"""Flash MiSTerLily firmware onto the display from the MiSTer, over its USB cable.

  misterlily_flash.py check            board version and the latest release, as one JSON line
  misterlily_flash.py flash --latest   download the latest GitHub release and flash it
  misterlily_flash.py flash FILE       flash a firmware file (.pio/build/tdisplay_s3/firmware.bin)

Only the application is written (0x10000), plus a blank otadata so the board boots it. Settings and
the start-up picture live in the spiffs partition and stay. Before the board is touched, the file
must pass as a MiSTerLily image: ESP32-S3 image header, our HWTDISPS3;MDS-<version>; reply inside,
and small enough for the app partition.

esptool 3.3.3 (one file, as tty2oled uses) and pyserial 3.5 are downloaded on first use into
tools/, pinned by SHA-256; pyserial is imported straight from its wheel. The daemon holds the port,
so it is stopped for the flash and started again afterwards, also when the flash fails.

Output, one event per line (MiSTerManager reads it):
  STEP <text>   PROGRESS <0-100>   DONE <version>   ERROR <text>
Exit status 0 on success.
"""
import argparse
import fcntl
import hashlib
import json
import os
import re
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mister_display import FW_FILE, find_device, read_config  # noqa: E402

REPO = "alberthorta/MiSTerLily"
TOOLS_DIR = os.path.join(HERE, "tools")
TOOLS = {
    "esptool.py": ("https://raw.githubusercontent.com/espressif/esptool/v3.3.3/esptool.py",
                   "a0126f89209caf72098491e3dc714b7080c638b9fd18e78114b73592dcee60f2"),
    "pyserial-3.5-py2.py3-none-any.whl": (
        "https://files.pythonhosted.org/packages/07/bc/587a445451b253b285629263eb51c2d8e9bcea4fc97826266d186f96f558/"
        "pyserial-3.5-py2.py3-none-any.whl",
        "c4451db6ba391ca6ca299fb3ec7bae67a5c55dde170964c7a14ceefec02f2cf0"),
}
# default_16MB.csv, the partition table of the lilygo-t-display-s3 board.
OTADATA_OFFSET, OTADATA_SIZE = 0xE000, 0x2000
APP_OFFSET, APP_SIZE = 0x10000, 0x640000
ESP32S3_CHIP_ID = 9
VERSION_RE = re.compile(rb"HWTDISPS3;MDS-([0-9A-Za-z.+-]{1,32});")
LOCK_FILE = "/tmp/misterlily_flash.lock"
# The board leaves USB during the flash; the daemon finds it again and asks its version.
REAPPEAR_SECONDS = 30.0
CACERT = "/etc/ssl/certs/cacert.pem"  # the MiSTer CA bundle (update_all uses it too)


class FlashError(Exception):
    pass


def emit(kind, text=""):
    print("{} {}".format(kind, text).rstrip(), flush=True)


def fetch(url, timeout=30):
    ctx = ssl.create_default_context(cafile=CACERT if os.path.exists(CACERT) else None)
    req = urllib.request.Request(url, headers={"User-Agent": "MiSTerLily"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read()


def image_version(data):
    """The MiSTerLily version inside a firmware image; FlashError if it is not one."""
    if len(data) < 0x100 or data[0] != 0xE9:
        raise FlashError("not an ESP32 application image")
    chip = data[12] | data[13] << 8
    if chip != ESP32S3_CHIP_ID:
        raise FlashError("image is for another chip (id {}), not the ESP32-S3".format(chip))
    if len(data) > APP_SIZE:
        raise FlashError("image is larger than the app partition")
    m = VERSION_RE.search(data)
    if not m:
        raise FlashError("not a MiSTerLily firmware")
    return m.group(1).decode()


def board_version():
    try:
        with open(FW_FILE) as f:
            return f.read().strip() or None
    except OSError:
        return None


def latest_release():
    """(version, url of the .bin) of the latest GitHub release."""
    rel = json.loads(fetch("https://api.github.com/repos/{}/releases/latest".format(REPO)))
    for asset in rel.get("assets", []):
        if asset["name"].endswith(".bin"):
            return rel["tag_name"].lstrip("v"), asset["browser_download_url"]
    raise FlashError("release {} has no firmware file".format(rel.get("tag_name")))


def ensure_tools():
    os.makedirs(TOOLS_DIR, exist_ok=True)
    for name, (url, sha) in TOOLS.items():
        path = os.path.join(TOOLS_DIR, name)
        if os.path.exists(path):
            with open(path, "rb") as f:
                if hashlib.sha256(f.read()).hexdigest() == sha:
                    continue
        emit("STEP", "downloading {}".format(name))
        data = fetch(url)
        if hashlib.sha256(data).hexdigest() != sha:
            raise FlashError("{} download does not match its checksum".format(name))
        with open(path + ".tmp", "wb") as f:
            f.write(data)
        os.replace(path + ".tmp", path)


def daemon(action):
    subprocess.run(["bash", os.path.join(HERE, "S60misterlily"), action],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)


def run_esptool(device, image_path, blank_path):
    env = dict(os.environ, PYTHONPATH=os.path.join(TOOLS_DIR, "pyserial-3.5-py2.py3-none-any.whl"))
    cmd = [sys.executable, os.path.join(TOOLS_DIR, "esptool.py"), "--chip", "esp32s3", "--port", device,
           "--before", "default_reset", "--after", "hard_reset",
           "write_flash", hex(OTADATA_OFFSET), blank_path, hex(APP_OFFSET), image_path]
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    tail = []
    last = -1
    for raw in proc.stdout:
        line = raw.decode(errors="replace").strip()
        tail = (tail + [line])[-5:]
        m = re.match(r"Writing at 0x([0-9a-f]+)\.\.\. \((\d+) %\)", line)
        if m and int(m.group(1), 16) >= APP_OFFSET:
            pct = int(m.group(2))
            if last < 0:
                emit("STEP", "writing the firmware")
            if pct != last:
                emit("PROGRESS", pct)
                last = pct
        elif line.startswith(("Connecting", "Chip is", "Hash of data verified", "Hard resetting")):
            emit("STEP", line)
    if proc.wait() != 0:
        raise FlashError("esptool failed: " + " | ".join(l for l in tail if l))


def flash(data, args):
    version = image_version(data)
    emit("STEP", "firmware {}, {} bytes".format(version, len(data)))
    ensure_tools()
    cfg = read_config(args.config)
    device = args.device or find_device(cfg)
    if not device:
        raise FlashError("display not found on USB")
    with tempfile.TemporaryDirectory() as tmp:
        image_path = os.path.join(tmp, "app.bin")
        blank_path = os.path.join(tmp, "otadata.bin")
        with open(image_path, "wb") as f:
            f.write(data)
        with open(blank_path, "wb") as f:
            f.write(b"\xff" * OTADATA_SIZE)
        if not args.no_daemon:
            emit("STEP", "stopping the display daemon")
            daemon("stop")
        try:
            emit("STEP", "flashing {}".format(device))
            run_esptool(device, image_path, blank_path)
        finally:
            if not args.no_daemon:
                emit("STEP", "starting the display daemon")
                daemon("start")
    if args.no_daemon:
        return version
    # The new version only shows once the daemon has reconnected and asked the board.
    deadline = time.monotonic() + REAPPEAR_SECONDS
    while time.monotonic() < deadline:
        if board_version() == version:
            return version
        time.sleep(0.5)
    raise FlashError("flashed, but the display did not report version {} afterwards".format(version))


def main():
    parser = argparse.ArgumentParser(description="Flash MiSTerLily firmware onto the display.")
    parser.add_argument("--config", default=os.path.join(HERE, "config.ini"))
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    fl = sub.add_parser("flash")
    fl.add_argument("file", nargs="?")
    fl.add_argument("--latest", action="store_true")
    fl.add_argument("--device", help="serial device instead of auto-detection")
    fl.add_argument("--no-daemon", action="store_true", help="do not stop/start the daemon (bench use)")
    args = parser.parse_args()

    if args.cmd == "check":
        out = {"board": board_version(), "latest": None, "error": None}
        try:
            out["latest"] = latest_release()[0]
        except (OSError, ValueError, KeyError, FlashError) as e:
            out["error"] = "could not read the latest release: {}".format(e)
        print(json.dumps(out))
        return 0

    if bool(args.file) == args.latest:
        parser.error("give a firmware file or --latest")
    lock = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        emit("ERROR", "another flash is running")
        return 1
    try:
        if args.latest:
            version, url = latest_release()
            emit("STEP", "downloading firmware {}".format(version))
            data = fetch(url, timeout=120)
            if image_version(data) != version:
                raise FlashError("release {} contains firmware {}".format(version, image_version(data)))
        else:
            with open(args.file, "rb") as f:
                data = f.read(APP_SIZE + 1)
        emit("DONE", flash(data, args))
        return 0
    except (OSError, ValueError, KeyError, FlashError, subprocess.SubprocessError) as e:
        emit("ERROR", str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
