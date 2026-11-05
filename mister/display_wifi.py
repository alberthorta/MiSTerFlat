"""The display board's own Wi-Fi, for MiSTerManager's Display page (Waveshare, firmware 0.6.0+).

Not the MiSTer's Wi-Fi: that one is wifi.py, used by the Wi-Fi screen on the display. This one
is the network the display board itself joins, to serve the virtual display at
http://misterlily.local/ even while the MiSTer is switched off.

The daemon holds the serial port, so other programs go through two files:
  /tmp/misterlily_sta      written by the daemon: the board's Wi-Fi state as JSON
  /tmp/misterlily_sta_cmd  written by others, one command per line:
                           "status", "scan", "join <ssid hex> <password hex>", "forget".
                           The daemon sends them (MDSSTA, docs/protocol.md) and removes the file.

Writers should write a temporary file and rename it. The password is in the command file only
until the daemon reads it (at most a few seconds), and /tmp is in RAM.
"""
import json
import os
import re
import time

STATE_FILE = "/tmp/misterlily_sta"
COMMAND_FILE = "/tmp/misterlily_sta_cmd"
HEX_RE = re.compile(r"^(?:[0-9a-fA-F]{2})*$")
MAX_NETWORKS = 20


def new_state():
    return {"state": "off", "ip": "", "rssi": 0, "ssid": "", "networks": [], "scanning": False,
            "error": "", "updated": 0}


def _unhex(text):
    try:
        return bytes.fromhex(text).decode("utf-8", "replace")
    except ValueError:
        return ""


def handle_line(line, state):
    """Updates state from one MDSSTA line of the board. True if it was one."""
    text = line.decode("utf-8", "replace").strip() if isinstance(line, bytes) else line.strip()
    if not text.startswith("MDSSTA,"):
        return False
    parts = text[len("MDSSTA,"):].split(",")
    kind = parts[0]
    if kind == "status" and len(parts) >= 5:
        if parts[1] == "fail":
            name = _unhex(parts[4]) or state.get("joining", "")
            state["error"] = "Could not join {}. Check the password.".format(name) if name else "Could not join the network."
        elif parts[1] == "ok":
            state["error"] = ""
        state.update(state=parts[1], ip=parts[2], rssi=int(parts[3]) if parts[3].lstrip("-").isdigit() else 0,
                     ssid=_unhex(parts[4]))
    elif kind == "scanning":
        state.update(scanning=True, networks=[])
    elif kind == "net" and len(parts) >= 4 and len(state["networks"]) < MAX_NETWORKS:
        name = _unhex(parts[3])
        if name and parts[1].lstrip("-").isdigit():
            state["networks"].append({"ssid": name, "rssi": int(parts[1]), "secure": parts[2] == "1"})
    elif kind == "end":
        state["scanning"] = False
    else:
        return False
    state["updated"] = int(time.time())
    return True


def write_state(state, path=STATE_FILE):
    """None removes the file (no board with its own Wi-Fi)."""
    try:
        if state is None:
            os.remove(path)
            return
        with open(path + ".tmp", "w") as f:
            json.dump({k: v for k, v in state.items() if k != "joining"}, f)
        os.replace(path + ".tmp", path)
    except OSError:
        pass


def take_commands(state, path=COMMAND_FILE):
    """MDSSTA lines for the board from the command file, which is removed. Bad lines are dropped."""
    try:
        with open(path) as f:
            text = f.read()
        os.remove(path)
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        parts = line.split()
        if parts == ["status"]:
            out.append("MDSSTA\n")
        elif parts == ["scan"]:
            out.append("MDSSTA,scan\n")
        elif parts == ["forget"]:
            out.append("MDSSTA,forget\n")
        elif (len(parts) in (2, 3) and parts[0] == "join" and parts[1] and len(parts[1]) <= 64
              and HEX_RE.match(parts[1]) and (len(parts) == 2 or (HEX_RE.match(parts[2]) and len(parts[2]) <= 128))):
            password = parts[2] if len(parts) == 3 else ""
            state["joining"] = _unhex(parts[1])
            state["error"] = ""
            out.append("MDSSTA,join,{},{}\n".format(parts[1].lower(), password.lower()))
    return out
