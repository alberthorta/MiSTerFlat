#!/bin/bash
# Install MiSTerLily on a MiSTer.
#
#   install.sh             native mode (default): our daemon shows colour pictures from
#                          /media/fat/MiSTerLily/art, falls back to the tty2oled pictures, then the
#                          core name. The tty2oled daemon is disabled the way tty2oled itself does it
#                          (S60tty2oled -> _S60tty2oled); its pictures and updater keep working.
#   install.sh --tty2oled  compatibility mode: keep the unmodified tty2oled daemon and only point it
#                          at the display (TTYDEV in tty2oled-user.ini).
#   install.sh --no-start  do not start anything now (it starts at the next boot).
#
# In both modes tty2oled-user.ini gets a marked block with TTYDEV and TTY2OLED_UPDATE="no", so the
# tty2oled updater never tries to flash its own firmware onto this board.
# Run it again to switch modes; uninstall.sh undoes everything.
# Test hook: MDS_FAT (default /media/fat).

set -u
FAT="${MDS_FAT:-/media/fat}"
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$FAT/MiSTerLily"
T2O="$FAT/tty2oled"
USER_INI="$T2O/tty2oled-user.ini"
USER_STARTUP="$FAT/linux/user-startup.sh"
BEGIN_MARK="# >>> MiSTerLily (managed by MiSTerLily/install.sh, remove with uninstall.sh)"
END_MARK="# <<< MiSTerLily"
STARTUP_LINE="[[ -e $DEST/S60misterlily ]] && $DEST/S60misterlily \$1"
# tty2oled's updater does not install its daemon when this file exists (its own "disabled" marker).
PLACEHOLDER_MARK="# MiSTerLily placeholder"

mode=native
start=yes
for arg in "$@"; do
  case "$arg" in
    --tty2oled) mode=tty2oled ;;
    --native) mode=native ;;
    --no-start|--no-restart) start=no ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

# Sets KEY="value" in config.ini, keeping every other line.
set_config() {
  local tmp="$DEST/config.ini.tmp"
  grep -v "^$1=" "$DEST/config.ini" 2>/dev/null >"$tmp"
  echo "$1=\"$2\"" >>"$tmp"
  mv -f "$tmp" "$DEST/config.ini"
}
get_config() { sed -n "s/^$1=\"\{0,1\}\([^\"]*\)\"\{0,1\}[[:space:]]*\$/\1/p" "$DEST/config.ini" 2>/dev/null | tail -n 1; }

remove_block() {  # file
  [ -f "$1" ] || return 0
  awk -v b="$BEGIN_MARK" -v e="$END_MARK" '
    $0 == b { skip = 1; next }
    $0 == e { skip = 0; next }
    !skip { print }' "$1" >"$1.mds.tmp" && mv -f "$1.mds.tmp" "$1"
}

# 1. Files
mkdir -p "$DEST/art"
if [ "$SRC" != "$DEST" ]; then
  for f in find-display.sh uninstall.sh install.sh misterlily_update.sh mister_display.py misterlily_flash.py \
           mdsserial.py pictures.py S60misterlily; do
    cp -f "$SRC/$f" "$DEST/"
  done
  # The commit this copy came from, for misterlily_update.sh.
  [ -e "$SRC/VERSION" ] && cp -f "$SRC/VERSION" "$DEST/VERSION"
  [ -e "$DEST/config.ini" ] || cp -f "$SRC/config.ini" "$DEST/"
fi
chmod +x "$DEST"/*.sh "$DEST/S60misterlily" 2>/dev/null || true  # FAT may refuse; bash runs them anyway
# The updater goes in the MiSTer Scripts menu.
mkdir -p "$FAT/Scripts"
cp -f "$DEST/misterlily_update.sh" "$FAT/Scripts/misterlily_update.sh"

# 2. Stop whatever talks to the display now
[ -x "$DEST/S60misterlily" ] && bash "$DEST/S60misterlily" stop >/dev/null 2>&1
[ -e "$T2O/S60tty2oled" ] && bash "$T2O/S60tty2oled" stop >/dev/null 2>&1

# 3. Identify the display and remember its USB serial number
echo "Looking for the display..."
serial="$(MDS_CONFIG=/dev/null bash "$DEST/find-display.sh" --probe --quiet --serial)"
if [ -n "$serial" ]; then
  echo "Found it (USB serial $serial)."
  set_config MDS_SERIAL "$serial"
else
  echo "No MiSTerLily display answered. It will be used as soon as it is plugged in."
fi

# 4. tty2oled-user.ini block (both modes). In native mode it is written even before tty2oled is
# installed, so its updater never offers to flash this board.
[ "$mode" = native ] && mkdir -p "$T2O"
if [ -d "$T2O" ]; then
  touch "$USER_INI"
  remove_block "$USER_INI"
  cat >>"$USER_INI" <<EOF
$BEGIN_MARK
TTYDEV="\$(bash $DEST/find-display.sh --quiet 2>/dev/null || echo /dev/ttyACM0)"
TTY2OLED_UPDATE="no"
$END_MARK
EOF
  echo "Updated $USER_INI"
fi

# 5. Who runs at boot
mkdir -p "$(dirname "$USER_STARTUP")"
if [ ! -e "$USER_STARTUP" ]; then
  if [ -e "$FAT/linux/_user-startup.sh" ]; then cp "$FAT/linux/_user-startup.sh" "$USER_STARTUP"
  else printf '#!/bin/sh\n\necho "***" $1 "***"\n' >"$USER_STARTUP"; fi
fi
grep -v -F "$DEST/S60misterlily" "$USER_STARTUP" | grep -v -x '# Startup MiSTerLily' >"$USER_STARTUP.mds.tmp" &&
  mv -f "$USER_STARTUP.mds.tmp" "$USER_STARTUP"

if [ "$mode" = native ]; then
  [ -n "$(tail -c 1 "$USER_STARTUP")" ] && echo >>"$USER_STARTUP"  # no newline at the end
  printf '# Startup MiSTerLily\n%s\n' "$STARTUP_LINE" >>"$USER_STARTUP"
  if [ -e "$T2O/S60tty2oled" ]; then
    mv -f "$T2O/S60tty2oled" "$T2O/_S60tty2oled"
    set_config MDS_DISABLED_TTY2OLED yes
    echo "Disabled the tty2oled daemon (S60tty2oled -> _S60tty2oled); its pictures stay in use."
  elif [ ! -e "$T2O/_S60tty2oled" ]; then
    # tty2oled not installed yet: if it is installed later for its pictures, its updater must not
    # install a second daemon that fights ours for the display.
    printf '#!/bin/bash
%s: keeps the tty2oled updater from installing its daemon.
' "$PLACEHOLDER_MARK" \
      >"$T2O/_S60tty2oled"
    set_config MDS_DISABLED_TTY2OLED placeholder
  fi
  set_config MDS_MODE native
  [ "$start" = yes ] && bash "$DEST/S60misterlily" start
else
  if grep -q "$PLACEHOLDER_MARK" "$T2O/_S60tty2oled" 2>/dev/null; then
    rm -f "$T2O/_S60tty2oled"
  elif [ "$(get_config MDS_DISABLED_TTY2OLED)" = yes ] && [ -e "$T2O/_S60tty2oled" ]; then
    mv -f "$T2O/_S60tty2oled" "$T2O/S60tty2oled"
    echo "Enabled the tty2oled daemon again."
  fi
  set_config MDS_DISABLED_TTY2OLED no
  set_config MDS_MODE tty2oled
  if [ ! -e "$T2O/S60tty2oled" ]; then
    echo "tty2oled is not installed: install it first (docs/mister-install.md)."
    exit 1
  fi
  [ "$start" = yes ] && bash "$T2O/S60tty2oled" start
fi
echo "Done ($mode mode). Test with: echo SNES > /tmp/CORENAME"
