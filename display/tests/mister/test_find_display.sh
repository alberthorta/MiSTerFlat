#!/bin/bash
# Tests for mister/find-display.sh against a fake sysfs tree. Runs with bash 3.2 (macOS) and 5.
# Usage: bash tests/mister/test_find_display.sh

HERE="$(cd "$(dirname "$0")" && pwd)"
FIND="$HERE/../../mister/find-display.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
failures=0

# make_acm <n> <vid> <pid> <serial> [product]: mimics /sys/class/tty/ttyACMn -> USB interface -> USB device
make_acm() {
  local n="$1" usb="$WORK/sys/devices/usb1/1-1.$1"
  mkdir -p "$usb/1-1.$n:1.0/tty/ttyACM$n" "$WORK/sys/class/tty" "$WORK/dev"
  printf '%s\n' "$2" > "$usb/idVendor"
  printf '%s\n' "$3" > "$usb/idProduct"
  printf '%s\n' "$4" > "$usb/serial"
  printf '%s\n' "${5:-USB JTAG/serial debug unit}" > "$usb/product"
  printf 'Espressif\n' > "$usb/manufacturer"
  ln -s "../../../1-1.$n:1.0" "$usb/1-1.$n:1.0/tty/ttyACM$n/device"
  ln -s "../../devices/usb1/1-1.$n/1-1.$n:1.0/tty/ttyACM$n" "$WORK/sys/class/tty/ttyACM$n"
  # A character device cannot be created without root; /dev/null stands in for the node.
  ln -s /dev/null "$WORK/dev/ttyACM$n"
}

run() { SYSFS_ROOT="$WORK/sys" DEV_ROOT="$WORK/dev" MDS_CONFIG=/nonexistent bash "$FIND" "$@"; }

check() {
  if [ "$2" = "$3" ]; then echo "PASS $1"; else echo "FAIL $1: expected '$2', got '$3'"; failures=$((failures + 1)); fi
}

out="$(run --quiet)"; status=$?
check "nothing found -> empty output" "" "$out"
check "nothing found -> exit 1" "1" "$status"

make_acm 0 2341 0043 "75833353934351F0E1A0" "Arduino Uno"
out="$(run --quiet)"
check "other ACM device is ignored" "" "$out"

make_acm 1 303A 1001 "12:34:56:78:9A:BC"
out="$(run --quiet)"; status=$?
check "ESP32-S3 found (upper-case VID)" "$WORK/dev/ttyACM1" "$out"
check "found -> exit 0" "0" "$status"
check "quiet mode prints one line" "1" "$(run --quiet | wc -l | tr -d ' ')"
check "quiet mode prints nothing on stderr" "" "$(run --quiet 2>&1 >/dev/null)"
check "--serial" "12:34:56:78:9A:BC" "$(run --quiet --serial)"

make_acm 2 303a 1001 "AA:BB:CC:DD:EE:FF"
check "two ESP32-S3: first one without a pin" "$WORK/dev/ttyACM1" "$(run --quiet)"
check "serial pin picks the matching one" "$WORK/dev/ttyACM2" "$(MDS_SERIAL=aa:bb:cc:dd:ee:ff run --quiet)"
check "missing pinned serial falls back" "$WORK/dev/ttyACM1" "$(MDS_SERIAL=11:22:33:44:55:66 run --quiet)"

printf '# comment\nMDS_SERIAL="AA:BB:CC:DD:EE:FF"\n' > "$WORK/config.ini"
check "serial pin from config.ini" "$WORK/dev/ttyACM2" \
  "$(SYSFS_ROOT="$WORK/sys" DEV_ROOT="$WORK/dev" MDS_CONFIG="$WORK/config.ini" bash "$FIND" --quiet)"

# The fake device nodes are /dev/null: they never answer CMDHWINF.
check "--probe skips devices that do not answer" "" "$(run --probe --quiet)"

out="$(run 2>&1 >/dev/null)"
case "$out" in *"303a:1001"*"display: "*) r=ok ;; *) r="$out" ;; esac
check "verbose listing on stderr" "ok" "$r"

echo "$failures failure(s)"
[ "$failures" -eq 0 ]
