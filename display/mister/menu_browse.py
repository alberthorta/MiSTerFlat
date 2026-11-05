"""Which core the cursor is on in the MiSTer core browser.

With log_file_entry=1 in MiSTer.ini, Main_MiSTer rewrites three files every time the cursor moves in
a file browser (menu.cpp, MENU_FILE_SELECT1):
  /tmp/FILESELECT   "active" while a browser is open, "selected" or "cancelled" after it
  /tmp/FULLPATH     the folder, relative to /media/fat ("_Console", "" for the top level)
  /tmp/CURRENTPATH  the item under the cursor as the menu shows it: no extension, and for .rbf
                    no _YYYYMMDD date ("SNES" for SNES_20260823.rbf, "Atari 2600" for the .mgl)

The same files are written when a running core browses its game files, so the caller only uses
this while /tmp/CORENAME is MENU.

The picture of a loaded core is found by the name the core gives itself (CONF_STR), and some cores
name their .rbf differently. CORE_ALIASES maps the .rbf name to that name.
"""
import os
import re

BASE = "/media/fat"
TMP = "/tmp"
# .rbf name (without date) -> core name in CONF_STR, where they differ.
CORE_ALIASES = {
    "TurboGrafx16": "TGFX16",
    "AdventureVision": "AVision",
    "ColecoVision": "Coleco",
    "GameAndWatch": "Game and Watch",
    "GnW": "GameNWatch",
    "Super_Vision_8000": "SuperVision8000",
    "CDi": "CD-i",
}
SETNAME_RE = re.compile(r"<setname>\s*([^<]*?)\s*</setname>", re.IGNORECASE)
RBF_RE = re.compile(r"<rbf>\s*([^<]*?)\s*</rbf>", re.IGNORECASE)


def _read(path):
    try:
        with open(path, "rb") as f:
            return f.read().decode("utf-8", "replace").strip()
    except OSError:
        return None


def _xml_core(path):
    """Core name for an .mgl or .mra: its <setname>, else the file name of its <rbf>."""
    try:
        with open(path, "rb") as f:
            text = f.read(65536).decode("utf-8", "replace")
    except OSError:
        return None
    m = SETNAME_RE.search(text)
    if m and m.group(1):
        return m.group(1)
    m = RBF_RE.search(text)
    if m and m.group(1):
        name = os.path.basename(m.group(1))
        return CORE_ALIASES.get(name, name)
    return None


def _rbf_exists(folder, name):
    prefix = name + "_"
    try:
        for entry in os.listdir(folder):
            low = entry.lower()
            if low.endswith(".rbf") and (low == name.lower() + ".rbf" or low.startswith(prefix.lower())):
                return True
    except OSError:
        pass
    return False


def selection(tmp=TMP):
    """(folder, item) under the cursor while a browser is open, else None."""
    if _read(os.path.join(tmp, "FILESELECT")) != "active":
        return None
    item = _read(os.path.join(tmp, "CURRENTPATH"))
    if not item:
        return None
    return (_read(os.path.join(tmp, "FULLPATH")) or "", item)


def core_for(folder, item, base=BASE):
    """Core name for the browser item, or None (a folder, a game file, nothing known)."""
    path = os.path.join(base, folder)
    if os.path.isdir(os.path.join(path, item)):
        return None
    for ext in (".mgl", ".mra"):
        p = os.path.join(path, item + ext)
        if os.path.isfile(p):
            return _xml_core(p)
    if _rbf_exists(path, item):
        return CORE_ALIASES.get(item, item)
    return None
