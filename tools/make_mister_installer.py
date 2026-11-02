#!/usr/bin/env python3
"""Build misterlily_install.sh: one self-contained script that installs MiSTerLily on a MiSTer.

    python3 tools/make_mister_installer.py              # writes dist/misterlily_install.sh

Put it in /media/fat/Scripts (or in the Scripts folder of a fresh Mr. Fusion card, which copies it
there during installation) and run it once from the MiSTer Scripts menu. It unpacks mister/ and
assets/STARTUP.png to a temporary folder and runs install.sh (native mode). An existing
config.ini and art/ folder are kept. No network needed.
"""
import base64
import io
import os
import subprocess
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MISTER_FILES = ["install.sh", "uninstall.sh", "misterlily_update.sh", "find-display.sh", "mister_display.py",
                "misterlily_flash.py", "mdsserial.py", "pictures.py", "buttons.py", "wifi.py", "menu_browse.py",
                "display_settings.py", "S60misterlily", "config.ini"]
OUT = os.path.join(ROOT, "dist", "misterlily_install.sh")

HEADER = r'''#!/bin/bash
# MiSTerLily installer ({version}). Run once from the MiSTer Scripts menu, or: bash misterlily_install.sh
# Installs the MiSTerLily display daemon to /media/fat/MiSTerLily (native mode) and the start-up
# picture. Keeps an existing config.ini and art/ folder. See docs/mister-install.md in the repository.
set -e
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
echo "Unpacking MiSTerLily..."
sed '1,/^__PAYLOAD__$/d' "$0" | base64 -d | tar -xzf - -C "$TMP"
if ! command -v python3 >/dev/null; then
  echo "python3 was not found on this MiSTer; MiSTerLily needs it." >&2
  exit 1
fi
bash "$TMP/mister/install.sh"
ART="${{MDS_FAT:-/media/fat}}/MiSTerLily/art"
if [ ! -e "$ART/STARTUP.png" ] && [ ! -e "$ART/STARTUP.jpg" ]; then
  cp "$TMP/STARTUP.png" "$ART/STARTUP.png"
  echo "Start-up picture installed; the daemon stores it on the display."
fi
echo
echo "MiSTerLily is installed and starts at every boot."
echo "Run misterlily_update from the Scripts menu to get the tty2oled core logos and later updates."
exit 0
__PAYLOAD__
'''


def main():
    version = subprocess.run(["git", "-C", ROOT, "describe", "--always", "--dirty"],
                             stdout=subprocess.PIPE).stdout.decode().strip() or "unknown"
    buf = io.BytesIO()
    # ustar: the plain format busybox tar on the MiSTer reads without warnings.
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.USTAR_FORMAT) as tar:
        for name in MISTER_FILES:
            info = tar.gettarinfo(os.path.join(ROOT, "mister", name), arcname="mister/" + name)
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            with open(os.path.join(ROOT, "mister", name), "rb") as f:
                tar.addfile(info, f)
        tar.add(os.path.join(ROOT, "assets", "STARTUP.png"), arcname="STARTUP.png")
        # The commit it was built from: misterlily_update.sh compares it with GitHub.
        sha = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], stdout=subprocess.PIPE).stdout.strip()
        info = tarfile.TarInfo("mister/VERSION")
        info.size = len(sha) + 1
        tar.addfile(info, io.BytesIO(sha + b"\n"))
    payload = base64.encodebytes(buf.getvalue()).decode()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="\n") as f:
        f.write(HEADER.format(version=version))
        f.write(payload)
    os.chmod(OUT, 0o755)
    print("{} ({} bytes, {})".format(OUT, os.path.getsize(OUT), version))
    return 0


if __name__ == "__main__":
    sys.exit(main())
