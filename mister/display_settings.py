"""Display settings for other programs on the MiSTer (MiSTerManager's Settings page).

The daemon holds the display's serial port, so other programs go through two files:
  /tmp/misterlily_cfg  written by the daemon: the display's settings as JSON, from its MDSCFG reply
                       (asked every few seconds, so a change on the touch screen shows up too)
  /tmp/misterlily_cmd  written by others: one "<setting> <value>" per line, for example
                       "brightness 5" or "clockfont 4". The daemon sends them and removes the file.

Writers should write a temporary file and rename it, so the daemon never reads half a command.
"""
import json
import os

STATE_FILE = "/tmp/misterlily_cfg"
COMMAND_FILE = "/tmp/misterlily_cmd"
# Same order as MenuScreen::kClockFonts in the firmware: the index is what MDSCFG,clockfont takes.
CLOCK_FONTS = ["c64", "7seg", "big", "sans", "orbitron", "serif", "mono", "retro16"]
BRIGHTNESS_MAX = 7
# Settings the commands may change, with their highest value.
LIMITS = {"brightness": BRIGHTNESS_MAX, "clockfont": len(CLOCK_FONTS) - 1}


def parse_cfg(line):
    """{'brightness': 7, 'clockfont': 0, ...} from an MDSCFG;k=v;... reply, or None."""
    text = line.decode("utf-8", "replace").strip() if isinstance(line, bytes) else line.strip()
    if not text.startswith("MDSCFG;") or "=" not in text:
        return None
    out = {}
    for field in text[len("MDSCFG;"):].split(";"):
        key, _, value = field.partition("=")
        if key and value.lstrip("-").isdigit():
            out[key] = int(value)
    return out or None


def write_state(cfg, path=STATE_FILE):
    """None removes the file (no display)."""
    try:
        if cfg is None:
            os.remove(path)
            return
        state = dict(cfg, clockfonts=CLOCK_FONTS, brightness_max=BRIGHTNESS_MAX)
        with open(path + ".tmp", "w") as f:
            json.dump(state, f)
        os.replace(path + ".tmp", path)
    except OSError:
        pass


def take_commands(path=COMMAND_FILE):
    """[(setting, value)] from the command file, which is removed. Unknown or bad lines are dropped."""
    try:
        with open(path) as f:
            text = f.read()
        os.remove(path)
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 2 or parts[0] not in LIMITS or not parts[1].isdigit():
            continue
        value = int(parts[1])
        if value <= LIMITS[parts[0]]:
            out.append((parts[0], value))
    return out
