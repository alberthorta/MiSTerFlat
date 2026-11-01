# Installing on the MiSTer

Two modes:

- **Native (default)**: our daemon (`mister_display.py`) shows colour pictures from
  `/media/fat/MiSTerLily/art`, falls back to the tty2oled pictures, then to the core name.
  It finds the display itself, and reconnects when it is unplugged and plugged in again.
- **tty2oled compatibility** (`install.sh --tty2oled`): the unmodified tty2oled daemon drives the
  display; we only tell it where the display is. Grey logos only.

> Status: both modes are tested on Linux in a container (the real `tty2oled.sh`; our daemon with
> reconnection), and the daemon is tested against the board from a Mac (including unplug/replug).
> **Not yet tested on a real MiSTer.**

Needs `python3` on the MiSTer (native mode). The MiSTer Linux image has it: `update_all` is a Python
program run directly by the system.

## Quick way: the one-file installer

`python3 tools/make_mister_installer.py` builds `dist/misterlily_install.sh`, a single script with
everything inside (daemon, scripts, default config, start-up picture). Copy it to
`/media/fat/Scripts/` and run it once from the MiSTer Scripts menu. Then run **`misterlily_update`**
(also in the Scripts menu now): it downloads the tty2oled logo library and, later, updates
MiSTerLily from GitHub (github.com/alberthorta/MiSTerLily, branch `main`). That is all you need;
the tty2oled updater is not required. It does steps 1 and 3 below,
also before tty2oled is installed: it writes `TTY2OLED_UPDATE="no"` and a `_S60tty2oled` marker,
so a later tty2oled install (for its logos) never installs a second daemon or flashes the board.

**On a fresh Mr. Fusion card** (before its first boot), put the file in the `Scripts` folder of the
`MRFUSION` drive. Mr. Fusion re-partitions the card on first boot and keeps only the files in
`Scripts/` (plus `config/`, `wpa_supplicant.conf`, `samba.sh`), so it ends up in
`/media/fat/Scripts`. After the MiSTer menu appears, run it from the Scripts menu once.
When copying from a Mac, make sure no `._misterlily_install.sh` file is left next to it
(`xattr -c` the file and delete the `._` file); Mr. Fusion would copy it as a broken script.

## 1. Protect the board from the tty2oled firmware updater

The tty2oled updater can flash its own (OLED) firmware onto any ESP32 it finds, and it resets the
board while checking. If you use tty2oled pictures (recommended), turn that off **before** its first run:

```sh
mkdir -p /media/fat/tty2oled
echo 'TTY2OLED_UPDATE="no"' >> /media/fat/tty2oled/tty2oled-user.ini
```

The updater only creates `tty2oled-user.ini` when it is missing, so this setting stays.
If a menu titled "Flash tool for ESP devices" ever appears, choose **Exit**.

## Updates and the logo library: `misterlily_update`

`/media/fat/Scripts/misterlily_update.sh` (installed by `install.sh`):

1. compares the installed version (`/media/fat/MiSTerLily/VERSION`) with the latest commit on GitHub
   and, if it differs, downloads and installs it (`config.ini` and `art/` are kept);
2. downloads the tty2oled picture archive (about 9 MB) into `/media/fat/tty2oled/pics` when the file
   on tty2tft.de changed since the last download; nothing else from tty2oled is installed;
3. restarts the daemon.

## Firmware updates from the MiSTer

`/media/fat/MiSTerLily/misterlily_flash.py` flashes the display over its USB cable, so the board can
stay inside the case. MiSTerManager has the same thing as buttons in Settings.

```sh
python3 /media/fat/MiSTerLily/misterlily_flash.py check            # board version and latest release
python3 /media/fat/MiSTerLily/misterlily_flash.py flash --latest   # flash the latest GitHub release
python3 /media/fat/MiSTerLily/misterlily_flash.py flash FILE.bin   # flash a file (pio run output)
```

- Only the program is written (`0x10000`, plus a blank `otadata`). Settings and the start-up picture
  are in the spiffs partition and stay.
- The file is checked first: ESP32-S3 image, a MiSTerLily version inside, small enough for `app0`,
  and built for the board that is connected (the daemon writes its id to `/tmp/misterlily_board`).
  Anything else is refused before the board is touched.
- A release has one file per board (`misterlily-<version>-tdisplay_s3.bin`,
  `misterlily-<version>-waveshare_lcd2.bin`); `--latest` takes the one for the connected board.
- esptool 3.3.3 and pyserial 3.5 are downloaded on first use into `MiSTerLily/tools/`, pinned by
  SHA-256. Nothing is installed in the MiSTer system folders.
- The daemon is stopped during the flash and started again, also when the flash fails. It writes the
  board's version to `/tmp/misterlily_fw`, and the script waits until the new version shows there.
- A flash takes about 15 s. If it is cut in the middle, the program is broken but the bootloader is
  not touched: flash again. If the board does not answer, hold **BOOT** while you plug it in.

## Touch buttons

On the Waveshare ESP32-S3-Touch-LCD-2, a tap shows four round buttons. The native daemon
(`mister/buttons.py`) does what the MiSTer's own buttons do:

| Button | On the MiSTer | How |
|---|---|---|
| RESET (red, two taps) | Reboots the MiSTer, like the RESET button (an HPS cold reset) | The reset combo with Left Shift, held for 1.5 s: Main does its own cold reset (sync, then a hardware reset), as fast as the button. If the MiSTer is still up 4 s later, `reboot`. (A plain `reboot` runs every stop script first and is slower; `reboot -f` hung the MiSTer.) |
| OSD (orange) | Opens or closes the OSD | F12 on a virtual keyboard (`/dev/uinput`) |
| USER (green) | Resets the core, like the USER button | The keyboard reset combo of `MiSTer.ini` `reset_combo` (default Left Ctrl + Left Alt + Right Alt). An open OSD is closed first: Main does not pass the combo to the core while the OSD is open |
| Bluetooth (blue) | The BT pairing menu, as when the OSD button is held for 3 s | F11 with the OSD open (opened first if needed) |

The daemon creates the virtual keyboard as soon as a touch display connects, because Main_MiSTer
needs about a second to find a new input device.
`/tmp/OSD_VISIBLE` (written by Main when `log_file_entry` is on) tells whether the OSD is open.

With two displays on one MiSTer, `MDS_SERIAL` in `config.ini` picks the one the daemon uses.

## Wi-Fi set-up

In the MiSTer menu there is no core to reset, so when a Wi-Fi dongle is plugged in (wlan0), the
USER button becomes a Wi-Fi button (`mister/wifi.py` does the work):

- **Scan**: `iw dev wlan0 scan`, about 12 s. Hidden networks are left out.
- **Join**: the password is typed on the screen (shown as typed; 8 characters at least). The
  network is added to `/media/fat/linux/wpa_supplicant.conf` with the highest priority; the saved
  networks stay, so they are a fallback. The SSID is written in hex and the PSK is derived on the
  MiSTer (as `wpa_passphrase` does): the password itself is not stored. The old file is kept as
  `wpa_supplicant.conf.misterlily.bak`.
- wpa_supplicant runs without a control interface on the MiSTer, so it is restarted with its own
  command line; dhcpcd then gets an address. If wlan0 is not on the new network with an address
  within 30 s, the old file is put back and wpa_supplicant restarted again.
- The scan and the join run in a thread, so the daemon keeps pinging the display meanwhile.

## 2. Alternative: install tty2oled (for its picture library)

Not needed when you use `misterlily_update`. If you prefer tty2oled's own updater:

From the MiSTer command line (F9) or SSH:

```sh
wget https://raw.githubusercontent.com/venice1200/MiSTer_tty2oled/main/update_tty2oled.sh -O /media/fat/Scripts/update_tty2oled.sh
/media/fat/Scripts/update_tty2oled.sh
```

This downloads the core pictures to `/media/fat/tty2oled/pics`. Run it again later for new pictures;
in native mode it keeps the tty2oled daemon disabled.

Without tty2oled the native mode still works with colour pictures and core names.

## 3. Install MiSTerLily

Plug the display in. Copy the `mister/` folder of this repository to the MiSTer (for example
`scp -r mister root@mister:/media/fat/MiSTerLily`) and run:

```sh
bash /media/fat/MiSTerLily/install.sh              # native mode
bash /media/fat/MiSTerLily/install.sh --tty2oled   # or: tty2oled compatibility mode
```

Native mode:
1. copies the files to `/media/fat/MiSTerLily` (an existing `config.ini` is kept) and creates `art/`;
2. asks every ESP32-S3 serial port `CMDHWINF` and stores the USB serial number of ours in `config.ini`;
3. adds a marked block to `tty2oled-user.ini` (`TTYDEV` and `TTY2OLED_UPDATE="no"`);
4. disables the tty2oled daemon the way tty2oled does it (`S60tty2oled` → `_S60tty2oled`);
5. adds `S60misterlily` to `/media/fat/linux/user-startup.sh` and starts the daemon.

Running `install.sh` again switches modes. `bash /media/fat/MiSTerLily/uninstall.sh` undoes
everything and gives the display back to tty2oled (`--purge` also deletes the folder and your art).

## 4. Colour pictures

Make them on a computer with `tools/convert_asset.py` (any PNG/JPEG → 320×170) and copy them to
`/media/fat/MiSTerLily/art/<core>.png` (or `.jpg`). `<core>` is the name in `/tmp/CORENAME`;
like tty2oled, shorter prefixes also match (`art/Genesis.png` is used for a core named `Genesis_xyz`).
New files are used at the next core change; no restart needed.

`art/STARTUP.png` (or `.jpg`) is special: it is the display's own start-up picture, shown before the
MiSTer is ready. Make it 320×130 (it is centered in that area; the line below holds "Waiting for
MiSTer", and the version is drawn small in the top-right corner). The daemon stores it on the display when it connects and the file has changed.

## 5. Check it

```sh
bash /media/fat/MiSTerLily/find-display.sh       # lists ACM devices and the chosen one
/media/fat/MiSTerLily/S60misterlily status
echo SNES > /tmp/CORENAME                         # shows SNES now
cat /tmp/mister-display.log                       # what was sent, connections, picture errors
```

Settings are in `/media/fat/MiSTerLily/config.ini`: brightness, rotation, fade, idle sleep (dark or a
dim clock), the menu screen (clock with time/date/IP, or the tty2oled MENU logo), picture folders, a
fixed `TTYDEV`. Restart with `S60misterlily restart` after a change.

The daemon pings the display every 5 s. If the display restarts (watchdog), it sends the core again;
if it stops answering, the daemon opens the port again. If the daemon stops (or MiSTer shuts down
while the display keeps power), the display shows "Waiting for MiSTer" after 15 s.

In tty2oled mode, use tty2oled's own log instead: `debug="true"` in `tty2oled-user.ini`, restart with
`/media/fat/tty2oled/S60tty2oled restart`, read `/tmp/tty2oled`. Brightness there comes from
tty2oled's `CONTRAST` (default 100 ≈ half): add `CONTRAST="255"` to `tty2oled-user.ini`.

## How the device is found

- The board is a USB CDC-ACM device, `303a:1001` (Espressif USB Serial/JTAG). The MiSTer kernel has
  `CONFIG_USB_ACM=y`, so it appears as `/dev/ttyACM<n>`, not `/dev/ttyUSB0` (tty2oled's default).
- `find-display.sh` reads `/sys/class/tty/ttyACM*/device/..` (`idVendor`, `idProduct`, `serial`).
  It does not rely on `/dev/serial/by-id` (that needs udev).
- Every ESP32-S3/C3 board has the same USB IDs. If several are connected, the serial number stored by
  `install.sh` picks ours; `find-display.sh --probe` asks each one `CMDHWINF`.
- If detection fails on the MiSTer, set `TTYDEV="/dev/ttyACM0"` (or the right number) in `config.ini`.

## Not verified yet (needs the MiSTer)

- The sysfs layout and `/dev/ttyACM<n>` number on the MiSTer kernel.
- `python3` version and modules on the current MiSTer image (the daemon uses only `os`, `select`,
  `termios`, `binascii`, `subprocess`, `argparse`).
- tty2oled mode only: `S60tty2oled` waits up to 10 s for `TTYDEV` at boot; a late hub can miss it.
  It also sets the port up only at start, so restart it after replugging the display.
  (Native mode waits and reconnects by itself.)
- Linux `cdc-acm` closing behaviour with tty2oled's one-`echo`-per-message writes (native mode keeps
  the port open, so it is not affected).
