#!/bin/bash
# Stops MiSTerManager, removes it from user-startup.sh and deletes /media/fat/MiSTerManager.
set -u
FAT="${MM_FAT:-/media/fat}"
DEST="$FAT/MiSTerManager"
USER_STARTUP="$FAT/linux/user-startup.sh"

[ -e "$DEST/S60mistermanager" ] && bash "$DEST/S60mistermanager" stop
if [ -f "$USER_STARTUP" ]; then
  grep -v -F "$DEST/S60mistermanager" "$USER_STARTUP" | grep -v -x '# Startup MiSTerManager' >"$USER_STARTUP.mm.tmp"
  mv -f "$USER_STARTUP.mm.tmp" "$USER_STARTUP"
fi
rm -rf "$DEST"
rm -f /tmp/mistermanager.mgl
echo "MiSTerManager removed"
