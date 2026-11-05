"""Wi-Fi from the touch display: scan, then join a network with a password typed on the screen.

The MiSTer runs wpa_supplicant on wlan0 with /media/fat/linux/wpa_supplicant.conf and no control
interface (wpa_cli does not work), like its own Scripts/wifi.sh expects. So:

- scan: `iw dev wlan0 scan` (about 12 s with a dual-band dongle);
- join: add a network block to the config, keeping the saved ones (a new network gets the highest
  priority, so the old ones stay as a fallback), restart wpa_supplicant with its own command line,
  and wait until wlan0 is on the new network with an address. If it does not get there, the old
  config is put back and wpa_supplicant restarted again.

The PSK is derived here (PBKDF2, as wpa_passphrase does), so the password is never written to the
card or passed on a command line. SSIDs are written in hex, which wpa_supplicant accepts for any
bytes.
"""
import hashlib
import os
import re
import shutil
import subprocess
import time

CONF = "/media/fat/linux/wpa_supplicant.conf"
PID_FILE = "/run/wpa_supplicant.wlan0.pid"
IFACE = "wlan0"
MAX_NETWORKS = 20
JOIN_TIMEOUT_SECONDS = 30.0


def dongle_present(iface=IFACE, net_dir="/sys/class/net"):
    return os.path.isdir(os.path.join(net_dir, iface))


def psk(ssid, password):
    """The 256-bit PSK of WPA/WPA2-Personal, as wpa_passphrase prints it."""
    return hashlib.pbkdf2_hmac("sha1", password.encode(), ssid, 4096, 32).hex()


def parse_scan(text):
    """[(ssid bytes, signal dBm, secure, connected)] from `iw dev <if> scan`, strongest first,
    one entry per name, hidden networks left out."""
    nets = {}
    cur = None

    def keep(entry):
        # Hidden networks send an empty name, or one of zero bytes.
        if entry and entry["ssid"].strip(b"\x00"):
            old = nets.get(entry["ssid"])
            if old is None or entry["connected"] or (not old[3] and entry["signal"] > old[1]):
                nets[entry["ssid"]] = (entry["ssid"], entry["signal"], entry["secure"],
                                       entry["connected"] or bool(old and old[3]))

    for line in text.splitlines():
        if line.startswith("BSS "):
            keep(cur)
            cur = {"ssid": b"", "signal": -100, "secure": False, "connected": "associated" in line}
        elif cur is not None:
            s = line.strip()
            if s.startswith("SSID:"):
                cur["ssid"] = decode_iw_ssid(s[5:].strip())
            elif s.startswith("signal:"):
                m = re.match(r"signal:\s*(-?\d+)", s)
                if m:
                    cur["signal"] = int(m.group(1))
            elif s.startswith(("RSN:", "WPA:")) or (s.startswith("capability:") and "Privacy" in s):
                cur["secure"] = True
    keep(cur)
    return sorted(nets.values(), key=lambda n: (not n[3], -n[1]))[:MAX_NETWORKS]


def decode_iw_ssid(text):
    """iw prints non-printable SSID bytes as \\xNN."""
    out = bytearray()
    i = 0
    raw = text.encode("utf-8", "surrogateescape")
    while i < len(raw):
        if raw[i:i + 2] == b"\\x" and i + 4 <= len(raw):
            try:
                out.append(int(raw[i + 2:i + 4], 16))
                i += 4
                continue
            except ValueError:
                pass
        out.append(raw[i])
        i += 1
    return bytes(out)


def scan(iface=IFACE):
    out = subprocess.run(["iw", "dev", iface, "scan"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         timeout=40).stdout
    return parse_scan(out.decode("utf-8", "surrogateescape"))


def only_24ghz(text):
    """`iw dev <if> scan` output without the 5 GHz (and 6 GHz) access points: for the display board,
    whose ESP32-S3 has 2.4 GHz only."""
    out, keep = [], True
    for line in text.splitlines():
        if line.startswith("BSS "):
            keep = True
        m = re.match(r"\s*freq:\s*(\d+)", line)
        if m and int(m.group(1)) >= 3000:
            keep = False
            # Drop what was already taken from this block.
            while out and not out[-1].startswith("BSS "):
                out.pop()
            if out:
                out.pop()
            continue
        if keep:
            out.append(line)
    return "\n".join(out)


def scan_24ghz(iface=IFACE):
    out = subprocess.run(["iw", "dev", iface, "scan"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         timeout=40).stdout
    return parse_scan(only_24ghz(out.decode("utf-8", "surrogateescape")))


def link(iface=IFACE):
    """(ssid bytes, MHz) of the network the dongle is on, or None."""
    try:
        text = subprocess.run(["iw", "dev", iface, "link"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              timeout=5).stdout.decode("utf-8", "surrogateescape")
    except (OSError, subprocess.SubprocessError):
        return None
    ssid = re.search(r"^\s*SSID:\s*(.*)$", text, re.M)
    freq = re.search(r"^\s*freq:\s*(\d+)", text, re.M)
    if not ssid:
        return None
    return decode_iw_ssid(ssid.group(1).strip()), int(freq.group(1)) if freq else 0


def saved_key(ssid, conf=CONF):
    """The key wpa_supplicant.conf has for ssid (bytes): the 64-hex PSK as wpa_supplicant takes it,
    the passphrase of a quoted psk, "" for an open network, or None if the network is not there."""
    try:
        with open(conf, encoding="utf-8", errors="surrogateescape") as f:
            text = f.read()
    except OSError:
        return None
    for block in split_conf(text)[1]:
        if block_ssid(block) != ssid:
            continue
        m = re.search(r'^\s*psk\s*=\s*(.+?)\s*$', block, re.M)
        if not m:
            return "" if re.search(r'^\s*key_mgmt\s*=\s*NONE', block, re.M) else None
        value = m.group(1)
        if value.startswith('"') and value.endswith('"'):
            return value[1:-1]
        return value if re.fullmatch(r"[0-9a-fA-F]{64}", value) else None
    return None


def split_conf(text):
    """(lines before the first network block, [block text]) of a wpa_supplicant.conf."""
    head, blocks, cur, depth = [], [], None, 0
    for line in text.splitlines():
        if cur is None and re.match(r"\s*network\s*=\s*\{", line):
            cur, depth = [line], line.count("{") - line.count("}")
            if depth <= 0:
                blocks.append("\n".join(cur))
                cur = None
            continue
        if cur is not None:
            cur.append(line)
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                blocks.append("\n".join(cur))
                cur = None
            continue
        head.append(line)
    if cur:
        blocks.append("\n".join(cur))
    return head, blocks


def block_ssid(block):
    m = re.search(r'^\s*ssid\s*=\s*(.+?)\s*$', block, re.M)
    if not m:
        return None
    value = m.group(1)
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1].encode("utf-8", "surrogateescape")
    try:
        return bytes.fromhex(value)
    except ValueError:
        return None


def block_priority(block):
    m = re.search(r'^\s*priority\s*=\s*(-?\d+)', block, re.M)
    return int(m.group(1)) if m else 0


def add_network(text, ssid, password):
    """The config with this network added (or replaced) at the highest priority."""
    head, blocks = split_conf(text)
    blocks = [b for b in blocks if block_ssid(b) != ssid]
    priority = max([block_priority(b) for b in blocks] + [0]) + 1
    lines = ["network={", "\tssid={}".format(ssid.hex())]
    if password:
        lines.append("\tpsk={}".format(psk(ssid, password)))
    else:
        lines.append("\tkey_mgmt=NONE")
    lines += ["\tpriority={}".format(priority), "}"]
    body = [line for line in head if line.strip()] + blocks + ["\n".join(lines)]
    return "\n".join(body) + "\n"


def link_ssid(iface=IFACE):
    """SSID wlan0 is associated with now, or None."""
    try:
        out = subprocess.run(["iw", "dev", iface, "link"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=10).stdout.decode("utf-8", "surrogateescape")
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"^\s*SSID:\s*(.*)$", out, re.M)
    return decode_iw_ssid(m.group(1).strip()) if m else None


def restart_supplicant(pid_file=PID_FILE):
    """Restarts wpa_supplicant with the command line it was started with (it reads the config only
    at start). dhcpcd keeps running and asks for an address on the new network by itself."""
    with open(pid_file) as f:
        pid = int(f.read().strip())
    with open("/proc/{}/cmdline".format(pid), "rb") as f:
        cmd = [a.decode() for a in f.read().split(b"\0") if a]
    os.kill(pid, 15)
    for _ in range(50):
        if not os.path.exists("/proc/{}".format(pid)):
            break
        time.sleep(0.1)
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)


def join(ssid, password, address, conf=CONF):
    """Joins the network; returns the new address. address(): wlan0's IPv4, "" if none.
    Raises OSError with a short reason, after putting the old config back."""
    with open(conf, encoding="utf-8", errors="surrogateescape") as f:
        old = f.read()
    backup = conf + ".misterlily.bak"
    shutil.copyfile(conf, backup)
    new = add_network(old, ssid, password)
    with open(conf + ".tmp", "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(new)
    os.replace(conf + ".tmp", conf)
    restart_supplicant()
    deadline = time.monotonic() + JOIN_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(1.0)
        if link_ssid() == ssid:
            ip = address()
            if ip:
                return ip
    # Not on the new network: put the old config back so the saved networks work again.
    with open(conf + ".tmp", "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(old)
    os.replace(conf + ".tmp", conf)
    restart_supplicant()
    raise OSError("could not connect" + (" (wrong password?)" if password else ""))
