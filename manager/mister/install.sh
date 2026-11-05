#!/bin/bash
# Run on the MiSTer from the folder that holds the copied files: puts MiSTerManager in
# /media/fat/MiSTerManager, adds it to user-startup.sh and (re)starts it.
# Test hook: MM_FAT (default /media/fat).

set -eu
FAT="${MM_FAT:-/media/fat}"
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$FAT/MiSTerManager"
USER_STARTUP="$FAT/linux/user-startup.sh"
STARTUP_LINE="[[ -e $DEST/S60mistermanager ]] && $DEST/S60mistermanager \$1"

mkdir -p "$DEST"
[ -e "$DEST/S60mistermanager" ] && bash "$DEST/S60mistermanager" stop >/dev/null 2>&1 || true
if [ "$SRC" != "$DEST" ]; then
  rm -rf "$DEST/mistermanager"
  cp -R "$SRC/mistermanager" "$DEST/"
  cp -f "$SRC/S60mistermanager" "$SRC/install.sh" "$SRC/uninstall.sh" "$DEST/"
fi

mkdir -p "$(dirname "$USER_STARTUP")"
if [ ! -e "$USER_STARTUP" ]; then
  if [ -e "$FAT/linux/_user-startup.sh" ]; then cp "$FAT/linux/_user-startup.sh" "$USER_STARTUP"
  else printf '#!/bin/sh\n\necho "***" $1 "***"\n' >"$USER_STARTUP"; fi
fi
grep -v -F "$DEST/S60mistermanager" "$USER_STARTUP" | grep -v -x '# Startup MiSTerManager' >"$USER_STARTUP.mm.tmp" || true
mv -f "$USER_STARTUP.mm.tmp" "$USER_STARTUP"
[ -n "$(tail -c 1 "$USER_STARTUP")" ] && echo >>"$USER_STARTUP"
printf '# Startup MiSTerManager\n%s\n' "$STARTUP_LINE" >>"$USER_STARTUP"

if [ "${1:-}" != "--no-start" ]; then
  bash "$DEST/S60mistermanager" start
fi
echo "MiSTerManager installed in $DEST"
