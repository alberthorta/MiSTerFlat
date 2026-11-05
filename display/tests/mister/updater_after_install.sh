#!/bin/bash
# Runs INSIDE a Debian container (see run_updater_test.sh). Network needed.
# 1. installs MiSTerLily with dist/misterlily_install.sh (as on a fresh MiSTer, no tty2oled yet);
# 2. runs the real tty2oled updater twice (first: picture archive; second: rsync update);
# 3. checks that nothing of ours was overwritten and that tty2oled did not install its daemon.

FAT=/media/fat
fails=0
check() { if eval "$2"; then echo "PASS $1"; else echo "FAIL $1"; fails=$((fails + 1)); fi; }
snapshot() {
  (cd "$FAT" && find MiSTerLily -type f ! -name '*.pyc' | sort | xargs md5sum
   md5sum tty2oled/_S60tty2oled
   sed -n '/^# >>> MiSTerLily/,/^# <<< MiSTerLily/p' tty2oled/tty2oled-user.ini | md5sum
   grep -F 'MiSTerLily' linux/user-startup.sh | md5sum)
}

mkdir -p "$FAT/Scripts" "$FAT/linux" /etc/init.d
touch /etc/init.d/S99user  # the updater only builds user-startup.sh on a real MiSTer image
echo -n MENU > /tmp/CORENAME

bash /dist/misterlily_install.sh >/tmp/install.log 2>&1
check "MiSTerLily installer" "[ $? -eq 0 ]"
before="$(snapshot)"

wget -q https://raw.githubusercontent.com/venice1200/MiSTer_tty2oled/main/update_tty2oled.sh -O "$FAT/Scripts/update_tty2oled.sh"
for run in 1 2; do
  echo "== tty2oled updater, run $run"
  bash "$FAT/Scripts/update_tty2oled.sh" </dev/null >/tmp/updater$run.log 2>&1
  echo "   exit $? ; last lines:"
  grep -v '^$' /tmp/updater$run.log | sed 's/\x1b\[[0-9;?]*[a-zA-Z]//g' | tail -4 | sed 's/^/   | /'
done

after="$(snapshot)"
check "our files, ini block, placeholder and boot line unchanged" '[ "$before" = "$after" ]'
[ "$before" = "$after" ] || diff <(echo "$before") <(echo "$after")
check "tty2oled daemon not installed (no S60tty2oled)" "[ ! -e $FAT/tty2oled/S60tty2oled ]"
check "updater said it skipped the disabled daemon" "grep -q 'Found disabled init script' /tmp/updater1.log"
check "TTY2OLED_UPDATE still no (sourced)" '[ "$(bash -c ". $FAT/tty2oled/tty2oled-system.ini; . $FAT/tty2oled/tty2oled-user.ini; echo \$TTY2OLED_UPDATE")" = no ]'
check "firmware installer never ran" "! grep -qi 'esptool\|Flash tool\|identify device' /tmp/updater1.log /tmp/updater2.log"
check "no tty2oled daemon process" "! pgrep -f tty2oled.sh >/dev/null"
check "MiSTerLily daemon still running" "bash $FAT/MiSTerLily/S60misterlily status >/dev/null"
n=$(find "$FAT/tty2oled/pics" -name '*.gsc' -o -name '*.xbm' 2>/dev/null | wc -l)
check "tty2oled pictures downloaded ($n files)" "[ $n -gt 1000 ]"
echo "--- user-startup.sh:"; cat "$FAT/linux/user-startup.sh"
echo "$fails failure(s)"
exit $fails
