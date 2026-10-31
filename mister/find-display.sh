#!/bin/bash
# Find the MiSTerLily display (LILYGO T-Display-S3) among the USB serial devices.
#
#   find-display.sh            list candidates, then print the chosen device
#   find-display.sh --quiet    print only the device path (for TTYDEV in tty2oled-user.ini)
#   find-display.sh --probe    also ask each candidate CMDHWINF and keep only real MiSTerLily displays
#   find-display.sh --serial   print the USB serial number of the chosen device instead of its path
#
# Default mode only reads sysfs: no serial I/O. It is safe to run while the tty2oled daemon is
# running, and it is what tty2oled-user.ini calls each time any tty2oled script sources it.
# In --quiet mode stdout carries the path and nothing else; messages go to stderr.
#
# The ESP32-S3 USB Serial/JTAG port is 303a:1001 on every ESP32-S3/C3 board, so the USB IDs alone
# cannot tell our display from another one. If MDS_SERIAL is set (install.sh stores the board's
# USB serial number, its MAC address, in config.ini), that device wins. --probe asks the device.
#
# Exit status: 0 found, 1 nothing found.
# Test hooks: SYSFS_ROOT (default /sys) and DEV_ROOT (default /dev).

SYSFS_ROOT="${SYSFS_ROOT:-/sys}"
DEV_ROOT="${DEV_ROOT:-/dev}"
VID="303a"
PID="1001"
# CMDHWINF ids of the supported boards (BOARDS in mdsserial.py): T-Display-S3, Waveshare LCD 2.
HW_IDS="HWTDISPS3|HWWSTLCD2"
CONFIG="${MDS_CONFIG:-$(dirname "$0")/config.ini}"

quiet=no
probe=no
want_serial=no
for arg in "$@"; do
  case "$arg" in
    --quiet|-q) quiet=yes ;;
    --probe) probe=yes ;;
    --serial) want_serial=yes ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

# MDS_SERIAL may come from the environment or from config.ini (KEY="value" lines).
if [ -z "${MDS_SERIAL}" ] && [ -r "$CONFIG" ]; then
  MDS_SERIAL="$(sed -n 's/^MDS_SERIAL="\{0,1\}\([^"]*\)"\{0,1\}[[:space:]]*$/\1/p' "$CONFIG" | tail -n 1)"
fi

say() { [ "$quiet" = yes ] || echo "$@" >&2; }
lower() { printf '%s' "$1" | tr 'A-Z' 'a-z'; }
attr() { [ -r "$1/$2" ] && head -n 1 "$1/$2" 2>/dev/null; }

# Asks the device for CMDHWINF over one read/write descriptor. True if it answers as our firmware.
# A background cat collects the replies: `read -t` on a tty is unreliable in old bash (macOS 3.2),
# and old replies still queued in the device do not matter when we just search the output.
probe_device() {
  local dev="$1" out reader i ok=1
  out="$(mktemp 2>/dev/null || echo "/tmp/find-display.$$")"
  # stty before opening: on Linux the settings persist between opens, so our descriptor is raw
  # from the start and cannot echo queued device output back to it (it would arrive as a core name).
  stty -F "$dev" 115200 cs8 raw -parenb -cstopb -hupcl -echo 2>/dev/null ||
    stty -f "$dev" 115200 cs8 raw -parenb -cstopb -hupcl -echo 2>/dev/null
  exec 3<>"$dev" || return 1
  cat <&3 >"$out" 2>/dev/null &
  reader=$!
  # CMDNULL first: the device only releases queued old replies when it writes again.
  printf 'CMDNULL\n' >&3
  sleep 0.2
  printf 'CMDHWINF\n' >&3
  for i in 1 2 3 4 5 6 7 8 9 10; do
    sleep 0.2
    if grep -qE "($HW_IDS);MDS-" "$out" 2>/dev/null; then ok=0; break; fi
  done
  kill "$reader" 2>/dev/null
  wait "$reader" 2>/dev/null
  exec 3<&-
  rm -f "$out"
  return $ok
}

found=""
found_serial=""
pinned=""
pinned_serial=""
for tty in "$SYSFS_ROOT"/class/tty/ttyACM*; do
  [ -e "$tty/device" ] || continue
  name="$(basename "$tty")"
  dev="$DEV_ROOT/$name"
  # .../ttyACMn/device is the USB interface; its parent is the USB device with the IDs.
  usb="$(cd -P "$tty/device/.." 2>/dev/null && pwd -P)"
  vid="$(lower "$(attr "$usb" idVendor)")"
  pid="$(lower "$(attr "$usb" idProduct)")"
  serial="$(attr "$usb" serial)"
  product="$(attr "$usb" product)"
  manufacturer="$(attr "$usb" manufacturer)"
  say "$dev  ${vid:-????}:${pid:-????}  ${manufacturer:-?} / ${product:-?}  serial ${serial:-?}"

  [ "$vid" = "$VID" ] && [ "$pid" = "$PID" ] || continue
  [ -c "$dev" ] || { say "  (no device node $dev)"; continue; }
  if [ "$probe" = yes ]; then
    if probe_device "$dev"; then
      say "  answers as a MiSTerLily display"
    else
      say "  is not a MiSTerLily display, skipped"
      continue
    fi
  fi
  if [ -n "$MDS_SERIAL" ] && [ "$(lower "$serial")" = "$(lower "$MDS_SERIAL")" ]; then
    pinned="$dev"
    pinned_serial="$serial"
  elif [ -z "$found" ]; then
    found="$dev"
    found_serial="$serial"
  fi
done

if [ -n "$pinned" ]; then
  found="$pinned"
  found_serial="$pinned_serial"
elif [ -n "$MDS_SERIAL" ] && [ -n "$found" ]; then
  say "configured serial $MDS_SERIAL not present, using $found"
fi

if [ -z "$found" ]; then
  say "no MiSTerLily display found"
  exit 1
fi
[ "$quiet" = yes ] || say "display: $found"
if [ "$want_serial" = yes ]; then
  echo "$found_serial"
else
  echo "$found"
fi
exit 0
