#!/bin/bash
# Undo install.sh: stop our daemon, remove its boot line and the tty2oled-user.ini block, and
# give the display back to tty2oled if we had disabled it. With --purge, also delete
# /media/fat/MiSTerLily (including your art/ folder).
# Test hook: MDS_FAT (default /media/fat).

set -u
FAT="${MDS_FAT:-/media/fat}"
DEST="$FAT/MiSTerLily"
T2O="$FAT/tty2oled"
USER_INI="$T2O/tty2oled-user.ini"
USER_STARTUP="$FAT/linux/user-startup.sh"
BEGIN_MARK="# >>> MiSTerLily (managed by MiSTerLily/install.sh, remove with uninstall.sh)"
END_MARK="# <<< MiSTerLily"

purge=no
[ "${1:-}" = "--purge" ] && purge=yes

[ -e "$DEST/S60misterlily" ] && bash "$DEST/S60misterlily" stop
rm -f "$FAT/Scripts/misterlily_update.sh"

if [ -f "$USER_STARTUP" ]; then
  grep -v -F "$DEST/S60misterlily" "$USER_STARTUP" | grep -v -x '# Startup MiSTerLily' >"$USER_STARTUP.mds.tmp" &&
    mv -f "$USER_STARTUP.mds.tmp" "$USER_STARTUP"
fi

if [ -f "$USER_INI" ]; then
  awk -v b="$BEGIN_MARK" -v e="$END_MARK" '
    $0 == b { skip = 1; next }
    $0 == e { skip = 0; next }
    !skip { print }' "$USER_INI" >"$USER_INI.mds.tmp" && mv -f "$USER_INI.mds.tmp" "$USER_INI"
  echo "Removed the MiSTerLily block from $USER_INI"
fi

if grep -q "# MiSTerLily placeholder" "$T2O/_S60tty2oled" 2>/dev/null; then
  rm -f "$T2O/_S60tty2oled"
elif grep -q '^MDS_DISABLED_TTY2OLED="yes"' "$DEST/config.ini" 2>/dev/null && [ -e "$T2O/_S60tty2oled" ]; then
  mv -f "$T2O/_S60tty2oled" "$T2O/S60tty2oled"
  echo "Enabled the tty2oled daemon again."
fi
[ -e "$T2O/S60tty2oled" ] && bash "$T2O/S60tty2oled" restart

if [ "$purge" = yes ]; then
  rm -rf "$DEST"
  echo "Deleted $DEST"
fi
