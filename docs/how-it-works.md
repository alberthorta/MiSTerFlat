# How MiSTerLily works

This page puts all the parts together: what runs where, how they talk, what each file on the MiSTer
does, and what to check when something does not work. The details are in
[protocol.md](protocol.md) (every serial line), [mister-install.md](mister-install.md) (installing
and the MiSTer side) and [wiring.md](wiring.md) (cables).

## The parts

```
 MiSTer (Linux side)                                              Display (ESP32-S3)
 ┌──────────────────────────────────────────────┐   USB serial   ┌───────────────────────────┐
 │ Main_MiSTer ── writes /tmp/CORENAME           │◀─────────────▶│ MiSTerLily firmware        │
 │                                               │  text lines    │  - draws every screen      │
 │ mister_display.py (the daemon)                │  + pictures    │  - keeps its own clock     │
 │   - sends the core, its picture, time, IPs    │                │  - touch buttons, Wi-Fi    │
 │   - acts on touch buttons (buttons.py)        │                │    screen (touch board)    │
 │   - scans and joins Wi-Fi (wifi.py)           │                └───────────────────────────┘
 │ misterlily_flash.py: flashes the display      │
 │ misterlily_update.sh: updates all of this     │
 │ MiSTerManager (optional web page): firmware   │
 │   update buttons, through misterlily_flash.py │
 └──────────────────────────────────────────────┘
```

- **Firmware** (`firmware/`, C++ with PlatformIO and LovyanGFX): one code base, one build per board.
  It draws everything; the MiSTer only sends what to show.
- **Daemon** (`mister/mister_display.py`, Python 3 standard library only): runs on the MiSTer from
  boot, watches the running core and keeps the display up to date.
- **Scripts** (`mister/`): install, update, uninstall, find the display, flash its firmware.
- **MiSTerManager** (separate project): its Settings page shows the display model and firmware and
  can update it. It calls `misterlily_flash.py`; it does not talk to the display itself.

The display also speaks the protocol of tty2oled, so it can run with the unmodified tty2oled
daemon instead of ours ("tty2oled mode", see the README). Everything below is about our daemon
("native mode").

## Boards

| | LILYGO T-Display-S3 | Waveshare ESP32-S3-Touch-LCD-2 |
|---|---|---|
| Screen | 1.9" 320×170, 8-bit parallel bus | 2" 320×240, SPI |
| Touch | no | yes (CST816D) |
| Firmware build | `tdisplay_s3` | `waveshare_lcd2` |
| Answers `CMDHWINF` with | `HWTDISPS3;MDS-<version>;` | `HWWSTLCD2;MDS-<version>;` |
| Board file | `firmware/include/boards/tdisplay_s3.h` | `firmware/include/boards/waveshare_lcd2.h` |

Each board needs its own firmware; the flash tool refuses a file built for the other board. Both
have the same USB IDs (the ESP32-S3's own USB, `303a:1001`). With two displays on one MiSTer,
`MDS_SERIAL` in `config.ini` (the board's MAC address, set by `install.sh`) picks the one the daemon
uses.

## Files on the MiSTer

| Path | What it is |
|---|---|
| `/media/fat/MiSTerLily/mister_display.py` | The daemon |
| `/media/fat/MiSTerLily/buttons.py` | Touch buttons: RESET, OSD, USER, Bluetooth |
| `/media/fat/MiSTerLily/wifi.py` | Wi-Fi scan and join for the Wi-Fi screen |
| `/media/fat/MiSTerLily/misterlily_flash.py` | Flashes the display's firmware |
| `/media/fat/MiSTerLily/mdsserial.py`, `pictures.py` | Serial port and tty2oled picture decoding |
| `/media/fat/MiSTerLily/find-display.sh` | Finds the display among the USB serial devices |
| `/media/fat/MiSTerLily/S60misterlily` | Starts and stops the daemon (`start`, `stop`, `restart`, `status`) |
| `/media/fat/MiSTerLily/install.sh`, `uninstall.sh` | Install / remove (see mister-install.md) |
| `/media/fat/MiSTerLily/config.ini` | Your settings; kept by updates |
| `/media/fat/MiSTerLily/art/` | Your colour pictures (`<core>.png`/`.jpg`, `STARTUP.png`); kept by updates |
| `/media/fat/MiSTerLily/tools/` | esptool and pyserial, downloaded the first time you flash |
| `/media/fat/MiSTerLily/VERSION` | Commit installed, for the updater |
| `/media/fat/Scripts/misterlily_update.sh` | The updater, in the MiSTer Scripts menu |
| `/media/fat/linux/user-startup.sh` | Two lines start the daemon at boot (added by `install.sh`) |
| `/media/fat/tty2oled/pics/` | The tty2oled logo library (downloaded by the updater) |
| `/tmp/mister-display.log` | The daemon's log (lost at reboot) |
| `/tmp/misterlily_fw`, `/tmp/misterlily_board` | Firmware version and board id of the connected display, written by the daemon |
| `/media/fat/linux/wpa_supplicant.conf.misterlily.bak` | The Wi-Fi config before the last change from the Wi-Fi screen |

## What happens at boot

1. The MiSTer's own boot runs `/media/fat/linux/user-startup.sh` near the end (about 17 s after the
   reset on a QMTECH board); it starts `S60misterlily`, which starts the daemon.
2. The daemon finds the display (`find-display.sh`: USB IDs, then `MDS_SERIAL`), opens the port and
   sets it up: `CMDSTTYACK,0` (no acks), `CMDCON` (brightness), `CMDROT` (rotation), the idle and
   fade settings from `config.ini`, `CMDSETTIME` (local time), the start-up picture if
   `art/STARTUP.png` changed, and `CMDHWINF` (which board and firmware; written to `/tmp`).
3. It sends the current core and the network addresses.

Until the daemon is there the display shows its start screen; after 10 s without data,
"Waiting for MiSTer".

## While running

- **Core changes**: Main writes the core name to `/tmp/CORENAME`. The daemon sends, in this order of
  preference: a colour picture from `art/`, a tty2oled logo, or just the name. In the menu it sends
  `MDSCORE,MENU` and the display draws its clock screen.
- **Heartbeat**: `MDSPING` every 5 s. The answer carries the board's uptime: if it went down, the
  board restarted and the daemon sends everything again. If the display stops answering for 15 s,
  or its device node goes, the daemon looks for it again. If the display misses the pings for 15 s,
  it shows "Waiting for MiSTer".
- **Time**: sent at set-up, every 10 minutes, and at once when the MiSTer's clock jumps (NTP after
  boot, `hwclock`, summer time). The display keeps counting by itself in between.
- **Network**: every 10 s the daemon reads which wired and Wi-Fi interfaces have a link and an
  address and sends them (`MDSNET,eth=… wifi=…`) when they change. The clock screen shows one line
  each, Ethernet first, with an icon.

## Touch board

A tap fades in four round buttons over the dimmed screen. A tap elsewhere, or 5 s without a tap,
fades them out. The daemon does what the MiSTer's own buttons do:

| Button | Does | How (`buttons.py`) |
|---|---|---|
| RESET (red) | Reboots the MiSTer. Needs a second tap ("Tap again") | The keyboard reset combo with Left Shift, held 1.5 s: Main does its cold reset. Plain `reboot` if the MiSTer is still up 4 s later |
| OSD (orange) | Opens/closes the OSD | F12 on a virtual keyboard (`/dev/uinput`) |
| USER (green) | Resets the core | The reset combo of `MiSTer.ini` (`reset_combo`); an open OSD is closed first |
| Bluetooth (blue) | BT pairing menu | F11 with the OSD open (opened first if needed) |
| Wi-Fi (turquoise) | Wi-Fi set-up. Takes USER's place in the MiSTer menu when a Wi-Fi dongle is plugged in | See below |

The virtual keyboard ("MiSTerLily buttons") is created when the touch display connects, because
Main needs about a second to find a new input device.

**Power button** (firmware 0.5.0, with a relay on GPIO 18): holding RESET for 2 s shuts the
MiSTer down and then cuts its 5 V; a tap on the standby screen switches it on again. See
[power.md](power.md).

**After RESET** the display goes dark at once and forgets the addresses. It stays powered and keeps
its clock while the MiSTer reboots, and a rebooted MiSTer starts in the menu, so after 2 s it shows
the menu clock by itself. When the daemon is back (about 19 s after the reset) it sends the same
screen and the addresses. "Waiting for MiSTer" is held back for 60 s meanwhile.

**Wi-Fi set-up**: the display asks the daemon to scan (`iw`, about 12 s) and lists the networks:
strongest first, the current one in orange at the top, hidden ones left out; drag to scroll. A
network with a password opens an on-screen keyboard (letters, digits, symbols; the password is
shown as typed; Connect needs 8 characters). The daemon adds the network to
`/media/fat/linux/wpa_supplicant.conf` with the highest priority, keeping the saved ones, and
restarts wpa_supplicant. The display shows "Connected" with the new address, or "Could not
connect"; then the old file has been put back, so the MiSTer is on its old network again. Only the
derived key (PSK) is stored, never the password. Loading a game closes the Wi-Fi screen.

## Firmware updates

`misterlily_flash.py` on the MiSTer flashes the display over its USB cable, so it can stay in the
case:

```sh
python3 /media/fat/MiSTerLily/misterlily_flash.py check            # board, its version, latest release
python3 /media/fat/MiSTerLily/misterlily_flash.py flash --latest   # newest release for this board
python3 /media/fat/MiSTerLily/misterlily_flash.py flash FILE.bin   # a build of your own
```

MiSTerManager's Settings page has the same as buttons ("Update to v…", "Flash a file…").

- The file is checked before the board is touched: ESP32-S3 image, a MiSTerLily version inside,
  small enough, and built for the board that is connected.
- Only the program is written. Settings and the start-up picture stay.
- The daemon is stopped during the flash (it holds the port) and started again, also on failure.
  The script waits until the board reports the new version.
- A flash takes about 15 s. If it is cut, the bootloader is still there: flash again.

## Updating the MiSTer side

`misterlily_update` in the Scripts menu (`/media/fat/Scripts/misterlily_update.sh`):

1. compares `VERSION` with the latest commit of this repository's `main` branch and, if it differs,
   downloads it and runs its `install.sh` (your `config.ini` and `art/` are kept);
2. updates the tty2oled logo library when it changed;
3. restarts the daemon.

The display's firmware is updated separately (above): a new release of the firmware does not
change the MiSTer side, and the other way round.

## Making a release (maintainers)

1. Set `MDS_FW_VERSION` in `firmware/include/config.h`, commit and push to `main`.
2. `git tag vX.Y.Z && git push origin vX.Y.Z`.
3. `.github/workflows/release.yml` checks that the tag matches `MDS_FW_VERSION`, builds both boards,
   checks the images as the MiSTer will, builds `misterlily_install.sh`, and publishes the release
   with `misterlily-X.Y.Z-tdisplay_s3.bin`, `misterlily-X.Y.Z-waveshare_lcd2.bin` and the installer.

Pushing to `main` alone is enough for MiSTer-side changes: `misterlily_update` takes them from there.

## When something does not work

| Symptom | Look at |
|---|---|
| Display stays on "Waiting for MiSTer" | `S60misterlily status`; `/tmp/mister-display.log`; `bash /media/fat/MiSTerLily/find-display.sh` (does it list the board?); `MDS_SERIAL` in `config.ini` matches the board (two displays?) |
| Wrong time after boot | It corrects itself when NTP sets the clock. Without network, the MiSTer needs a working RTC battery |
| No addresses on the clock | None of eth*/wlan* has a link and an address; they are checked every 10 s |
| Touch buttons do nothing on the MiSTer | Log lines `display button …`; `ls /dev/uinput`; firmware older than 0.2.0 has no touch buttons |
| No Wi-Fi button in the menu | Only on the touch board, firmware 0.3.0 or later, with a Wi-Fi dongle (`/sys/class/net/wlan0`) |
| Wi-Fi join fails | The log shows the reason; the old config was put back. `wpa_supplicant.conf.misterlily.bak` holds the one before the last change |
| Flash refused | The message says why: not a MiSTerLily image, wrong board, or the daemon has not seen the display (`--board` when it is not running) |
