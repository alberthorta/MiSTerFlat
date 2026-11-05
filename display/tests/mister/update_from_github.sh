#!/bin/bash
# Runs INSIDE a Debian container (see run_update_test.sh). Network needed (GitHub, tty2tft.de).
# Installs with dist/misterlily_install.sh, pretends to be an older version, runs
# misterlily_update.sh twice: the first run must update from GitHub and fetch the pictures, the
# second must find everything up to date. config.ini and art/ must survive.

FAT=/media/fat
fails=0
check() { if eval "$2"; then echo "PASS $1"; else echo "FAIL $1"; fails=$((fails + 1)); fi; }

mkdir -p "$FAT/Scripts" "$FAT/linux"
echo -n MENU >/tmp/CORENAME
bash /dist/misterlily_install.sh >/tmp/install.log 2>&1
check "installer" "[ $? -eq 0 ]"
check "updater in the Scripts menu" "[ -e $FAT/Scripts/misterlily_update.sh ]"
check "VERSION installed" "grep -qE '^[0-9a-f]{40}$' $FAT/MiSTerLily/VERSION"

echo 'CONTRAST="77"' >>"$FAT/MiSTerLily/config.ini"
cp /etc/hostname "$FAT/MiSTerLily/art/MYCORE.png"  # stands in for a user's picture
echo 0000000000000000000000000000000000000000 >"$FAT/MiSTerLily/VERSION"

echo "== update, run 1"
bash "$FAT/Scripts/misterlily_update.sh" 2>&1 | tee /tmp/update1.log | sed 's/^/   | /'
check "run 1 exit 0" "[ ${PIPESTATUS[0]} -eq 0 ]"
latest="$(curl -fsSL https://api.github.com/repos/alberthorta/MiSTerLily/commits/main | sed -n 's/^  "sha": "\([0-9a-f]\{40\}\)",$/\1/p' | head -n 1)"
check "updated to GitHub main ($latest)" "[ \"\$(cat $FAT/MiSTerLily/VERSION)\" = \"$latest\" ]"
check "config.ini kept" "grep -q 'CONTRAST=\"77\"' $FAT/MiSTerLily/config.ini"
check "art kept" "[ -e $FAT/MiSTerLily/art/MYCORE.png ] && [ -e $FAT/MiSTerLily/art/STARTUP.png ]"
n=$(find "$FAT/tty2oled/pics" -name '*.gsc' -o -name '*.xbm' | wc -l)
check "pictures downloaded ($n)" "[ $n -gt 1000 ]"
check "daemon running" "bash $FAT/MiSTerLily/S60misterlily status >/dev/null"
check "one boot line" "[ \$(grep -c 'S60misterlily \\\$1' $FAT/linux/user-startup.sh) -eq 1 ]"

echo "== update, run 2"
bash "$FAT/Scripts/misterlily_update.sh" 2>&1 | tee /tmp/update2.log | sed 's/^/   | /'
check "run 2: MiSTerLily up to date" "grep -q 'up to date' /tmp/update2.log && ! grep -q 'updating' /tmp/update2.log"
check "run 2: pictures not downloaded again" "! grep -q 'downloading' /tmp/update2.log"
echo "$fails failure(s)"
exit $fails
