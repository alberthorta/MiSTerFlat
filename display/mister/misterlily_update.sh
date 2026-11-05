#!/bin/bash
# MiSTerLily updater. Appears in the MiSTer Scripts menu as "misterlily_update".
#
#  1. updates MiSTerLily from GitHub (only when the main branch has a new commit); config.ini and
#     your art/ folder are kept;
#  2. downloads or updates the tty2oled picture library (only when the archive changed) into
#     /media/fat/tty2oled/pics, without installing anything else from tty2oled;
#  3. restarts the MiSTerLily daemon.
#
# Needs network. Test hook: MDS_FAT (default /media/fat).

REPO="alberthorta/MiSTerLily"
BRANCH="main"
PICTURES_URL="https://www.tty2tft.de/MiSTer_tty2oled_pictures.7z"
FAT="${MDS_FAT:-/media/fat}"
DEST="$FAT/MiSTerLily"
PICS="$FAT/tty2oled/pics"

CURL=(curl -fsSL --retry 2 --connect-timeout 15)
# The MiSTer keeps its CA bundle here (update_all uses the same file).
[ -e /etc/ssl/certs/cacert.pem ] && CURL+=(--cacert /etc/ssl/certs/cacert.pem)

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
failed=0

echo "MiSTerLily update"
echo "================="

# 1. MiSTerLily itself
echo "Checking MiSTerLily on GitHub ($REPO)..."
latest="$("${CURL[@]}" "https://api.github.com/repos/$REPO/commits/$BRANCH" 2>/dev/null |
  sed -n 's/^  "sha": "\([0-9a-f]\{40\}\)",$/\1/p' | head -n 1)"
current="$(cat "$DEST/VERSION" 2>/dev/null)"
if [ -z "$latest" ]; then
  echo "  could not reach GitHub, MiSTerLily not updated"
  failed=1
elif [ "$latest" = "$current" ]; then
  echo "  up to date (${current:0:7})"
else
  echo "  updating ${current:0:7} -> ${latest:0:7}"
  if "${CURL[@]}" "https://codeload.github.com/$REPO/tar.gz/$latest" -o "$TMP/src.tar.gz" &&
     tar -xzf "$TMP/src.tar.gz" -C "$TMP"; then
    src="$(ls -d "$TMP"/*/mister 2>/dev/null | head -n 1)"
    echo "$latest" >"$src/VERSION"
    if bash "$src/install.sh" --no-start >"$TMP/install.log" 2>&1; then
      art="$DEST/art"
      if [ ! -e "$art/STARTUP.png" ] && [ ! -e "$art/STARTUP.jpg" ] && [ -e "$src/../assets/STARTUP.png" ]; then
        cp "$src/../assets/STARTUP.png" "$art/STARTUP.png"
      fi
      echo "  installed"
    else
      echo "  install failed:"; sed 's/^/    /' "$TMP/install.log"
      failed=1
    fi
  else
    echo "  download failed"
    failed=1
  fi
fi

# 2. tty2oled picture library
echo "Checking the tty2oled picture library..."
stamp="$PICS/.misterlily_archive"
remote="$("${CURL[@]}" -I "$PICTURES_URL" 2>/dev/null | tr -d '\r' | sed -n 's/^[Ll]ast-[Mm]odified: //p')"
if [ -z "$remote" ]; then
  echo "  could not reach the picture server, pictures not updated"
  failed=1
elif [ -d "$PICS/GSC" ] && [ "$remote" = "$(cat "$stamp" 2>/dev/null)" ]; then
  echo "  up to date ($remote)"
else
  SEVENZ="$(command -v 7zr || command -v 7za || command -v 7z)"
  if [ -z "$SEVENZ" ]; then
    echo "  7zr not found, pictures not updated"
    failed=1
  else
    echo "  downloading ($remote)..."
    if "${CURL[@]}" "$PICTURES_URL" -o "$TMP/pictures.7z" &&
       mkdir -p "$PICS" && "$SEVENZ" x -y -bso0 -bsp0 -o"$PICS" "$TMP/pictures.7z" >/dev/null; then
      echo "$remote" >"$stamp"
      echo "  $(find "$PICS" -name '*.gsc' -o -name '*.xbm' | wc -l | tr -d ' ') pictures"
    else
      echo "  download or unpack failed"
      failed=1
    fi
  fi
fi

# 3. Settings guard and daemon (install.sh is idempotent: keeps config, art and the boot line)
if [ -e "$DEST/install.sh" ]; then
  bash "$DEST/install.sh" --no-start >/dev/null 2>&1
  bash "$DEST/S60misterlily" restart
fi

echo
[ "$failed" = 0 ] && echo "Done." || echo "Done, with problems (see above)."
exit $failed
