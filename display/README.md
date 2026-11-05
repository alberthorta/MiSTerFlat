# MiSTerLily

A colour status display for a MiSTer FPGA, built on a LILYGO T-Display-S3 (1.9" 320×170 TFT) or a
Waveshare ESP32-S3-Touch-LCD-2 (2" 320×240 touch TFT). When MiSTer loads a core, the display shows
that system's logo and name. On the touch board, a tap gives the MiSTer's RESET, OSD and USER
buttons, plus Bluetooth pairing, and in the MiSTer menu a Wi-Fi set-up with an on-screen keyboard
and a quick launch: swipe through the covers of your systems and games, tap one to start it (the
games are picked on the Systems page of MiSTerManager).

Website: **https://alberthorta.github.io/MiSTerFlat/** · How all the parts work together:
**[docs/how-it-works.md](docs/how-it-works.md)**

It speaks the serial protocol of [MiSTer_tty2oled](https://github.com/venice1200/MiSTer_tty2oled),
so the unmodified tty2oled daemon and its picture library drive it over native USB.

Status: in use on a real MiSTer (QMTECH Cyclone V). Colour pictures, our own MiSTer daemon with
heartbeat and reconnection, watchdog, stored settings, fades, a menu clock screen, idle sleep, a
"Waiting for MiSTer" screen, firmware updates from the MiSTer and touch buttons. tty2oled
compatibility mode works too.

## Hardware

One of:

| Board | Screen | Firmware environment | CMDHWINF id |
|---|---|---|---|
| **LILYGO T-Display-S3** (touch or non-touch; not the T-Display or the AMOLED) | ST7789 170×320, 8-bit parallel bus | `tdisplay_s3` | `HWTDISPS3` |
| **Waveshare ESP32-S3-Touch-LCD-2** | ST7789T3 240×320 on SPI, CST816D touch | `waveshare_lcd2` | `HWWSTLCD2` |

Both are ESP32-S3R8 (16 MB flash, 8 MB PSRAM) with native USB. The screens are used in landscape,
320 wide. The layouts were made for the 170-pixel T-Display-S3; on the 240-pixel Waveshare they are
centred vertically, and colour pictures made for 320×170 get black bars above and below.

Optional, Waveshare board: a 5 V relay module makes the display the MiSTer's power button
(standby screen, tap to power on, hold RESET to power off). See [docs/power.md](docs/power.md).

Waveshare board, firmware 0.6.0: the display joins a Wi-Fi network of its own and serves a
virtual display, the same screen on a phone, with touch, also while the MiSTer is off. Set the
network from MiSTerManager. See [docs/virtual-display.md](docs/virtual-display.md).

Plus a USB-C data cable. In the final build: a free port on the MiSTer's internal USB hub
(see [docs/wiring.md](docs/wiring.md)).

## Build and flash

Needs [PlatformIO](https://platformio.org/) (`brew install platformio`).

```sh
cd firmware
pio run                       # build (T-Display-S3)
pio run -t upload             # build and flash (auto-detects the port)
pio run -e waveshare_lcd2 -t upload   # the same for the Waveshare board
pio test -e native            # protocol unit tests on the computer, no board needed
```

Each board needs its own firmware; the board files are in `firmware/include/boards/`.

No buttons are needed to flash. If an upload fails: hold **BOOT**, press and release **RST**,
release **BOOT**, upload again.

`tdisplay_s3_debug` is the same firmware with a debug log on UART0 (GPIO43 TX, 115200 baud). The USB
port never carries debug output, because the MiSTer scripts read replies from it.

### Releases

A version tag builds the firmware of both boards on GitHub Actions and publishes a release with
`misterlily-<version>-tdisplay_s3.bin`, `misterlily-<version>-waveshare_lcd2.bin` and the MiSTer
installer `misterlily_install.sh` (`.github/workflows/release.yml`). The MiSTer can then flash the
display without a computer (see
[docs/mister-install.md](docs/mister-install.md#firmware-updates-from-the-mister)).

```sh
# set MDS_FW_VERSION in firmware/include/config.h, commit, then:
git tag v0.3.1 && git push origin main v0.3.1
```

The workflow stops if the tag and `MDS_FW_VERSION` differ.

## USB connection

The board uses the ESP32-S3 built-in USB Serial/JTAG controller: USB ID `303a:1001`,
"USB JTAG/serial debug unit", serial number = the chip's MAC address. No driver needed.

- macOS: `/dev/cu.usbmodem*`
- Linux / MiSTer: `/dev/ttyACM*` (MiSTer kernel: `CONFIG_USB_ACM=y`)

The baud rate is ignored. The firmware polls the USB FIFO directly, so a busy display makes the host
wait instead of losing data. Why not Arduino `Serial`: see [docs/research.md](docs/research.md) §6.

## Testing on a Mac (no MiSTer needed)

All tools use only the Python standard library (no pyserial), except `convert_asset.py` (Pillow).
Shared code lives in `mister/` (`mdsserial.py`, `pictures.py`), which also runs on the MiSTer.

```sh
python3 tools/usb_test.py   /dev/cu.usbmodemXXXX            # USB link checks
python3 tools/fake_mister.py /dev/cu.usbmodemXXXX PSX SNES  # behave like the tty2oled daemon
python3 tools/fake_mister.py /dev/cu.usbmodemXXXX --pics <tty2oled Pictures folder> --loop --interval 4 SNES PSX ATARI5200
python3 tools/send.py       /dev/cu.usbmodemXXXX CMDTEST "CMDCON,255"
python3 tools/screenshot.py /dev/cu.usbmodemXXXX screen.png # what the display shows, as PNG
```

`fake_mister.py` sends exactly what `tty2oled.sh` sends (checked byte for byte against the real
daemon, see below). Pictures: clone
[MiSTer_tty2oled_pictures](https://github.com/venice1200/MiSTer_tty2oled_pictures) and pass its
`Pictures` folder. Core names are the values MiSTer writes to `/tmp/CORENAME` (`PSX`, `SNES`,
`ATARI5200`, `Minimig`, ...).

Other tests:

```sh
bash tests/mister/test_find_display.sh                     # find-display.sh against a fake sysfs
bash tests/mister/run_e2e.sh                               # Docker: real tty2oled.sh, and our daemon
bash tests/mister/run_updater_test.sh                      # Docker: tty2oled updater after our installer
bash tests/mister/run_update_test.sh                       # Docker: misterlily_update against GitHub
python3 tests/mister/test_flash_image.py                   # firmware file check of misterlily_flash.py
python3 tests/mister/test_buttons.py                       # keys sent for the touch buttons
python3 tests/mister/test_wifi.py                          # Wi-Fi scan parsing and config changes
python3 tools/fake_mister.py --selftest <Pictures folder>  # picture decoding vs tail | xxd
python3 tests/fixtures/make_fixtures.py                    # rebuild the parser test fixtures
python3 tests/fixtures/make_art.py                         # rebuild the colour test pictures
```

## Installing on the MiSTer

See [docs/mister-install.md](docs/mister-install.md). Quickest: download `misterlily_install.sh` from
the [latest release](https://github.com/alberthorta/MiSTerFlat/releases/latest) (or build it with
`python3 tools/make_mister_installer.py`), copy it to `/media/fat/Scripts/` (or to the `Scripts`
folder of a fresh Mr. Fusion card) and run it once from the MiSTer Scripts menu. Then run `misterlily_update` from the
same menu: it downloads the tty2oled logo library and keeps MiSTerLily up to date from this repository. Colour pictures go to `/media/fat/MiSTerLily/art/<core>.png`.

The daemon can also run on a Mac/Linux PC for testing:

```sh
python3 mister/mister_display.py --device /dev/cu.usbmodemXXXX --corename /tmp/CORENAME --config my.ini -v
```

## Colour pictures

Besides the tty2oled logos, the display shows full-colour 320×170 PNG or JPEG pictures sent with the
`MDSIMG` command ([docs/protocol.md](docs/protocol.md)). Prepare them with:

```sh
python3 tools/convert_asset.py my_picture.png art/PSX.png    # any size -> 320x170, needs Pillow
python3 tools/convert_asset.py --check art/PSX.png           # can the display show it?
python3 tools/fake_mister.py /dev/cu.usbmodemXXXX --art art PSX
```

The file name is the core name. PNG for logos and sharp artwork; JPEG (baseline) for photos.
On the 320×240 Waveshare screen a 320×170 picture is centred with black bars; a 320×240 picture
fills it (and is cropped to the middle on the T-Display-S3).
The panel shows 16-bit colour; `--dither` avoids bands in smooth gradients.

## What the screen shows

- A core with a colour picture: the picture, full screen.
- A core with a tty2oled picture: the picture scaled to the full width (256×64 → 320×80, smoothed),
  centered, no text (the logos carry the name).
- A core without a picture, or a failed transfer: the system name, large, in the Commodore 64 font.
- Common systems get a friendly name (`PSX` → PLAYSTATION) with the MiSTer core name small below.
- Start-up: your own picture (stored on the board; 320×184 area on the Waveshare, 320×130 on the
  T-Display-S3) or "MiSTer / <board name>", and the
  firmware version; "Waiting for MiSTer" if nothing arrives within 10 s, or when our daemon stops
  answering for 15 s. Store the picture with `python3 tools/set_logo.py <port> logo.png`, or put it at
  `/media/fat/MiSTerLily/art/STARTUP.png` on the MiSTer (the daemon stores it when it changes).
- The MiSTer menu (native mode): a clock screen with time, date and the MiSTer's IP addresses, one
  line each with an Ethernet or Wi-Fi icon (checked every 10 s), unless you put an `art/MENU.png`.
- A short backlight dip when the core changes (can be turned off).
- Brightness, rotation and the options below are remembered across power cycles. Optional idle
  sleep, dark or with a dim clock (`IDLE_MINUTES` / `IDLE_SCREEN` in the daemon config).
- Touch board only: a tap fades in four round buttons over the dimmed screen: RESET (reboots the
  MiSTer; needs a second tap), OSD, USER (resets the core) and Bluetooth (the pairing menu). The
  native daemon does what the MiSTer's own buttons do (see
  [docs/mister-install.md](docs/mister-install.md#touch-buttons)). After RESET the screen goes
  dark and, 2 s later, shows the menu clock from its own clock while the MiSTer boots. A tap on a
  dark idle screen only wakes it.
- Touch board, in the MiSTer menu with a Wi-Fi dongle: USER (no core to reset there) becomes
  Wi-Fi. It scans, lists the networks (drag to scroll), takes the password on an on-screen keyboard
  and joins; the saved networks stay as a fallback (see
  [docs/mister-install.md](docs/mister-install.md#wi-fi-set-up)).

## tty2oled compatibility

| | Status |
|---|---|
| Core change with picture (`CMDCOR` + XBM/GSC) | works; transitions are ignored |
| Core change without picture (bare name) | works |
| Startup commands (`QWERTZ`, `CMDCON`, `CMDSETTIME`, `CMDSAVER`) | accepted; `CMDCON` sets brightness |
| `CMDCLS`, `CMDTXT`, `CMDGEO`, `CMDSPIC`, `CMDAPD`, `CMDTEST`, `CMDHWINF`, `CMDRESET`, `CMDROT` (`ROTATE="yes"`), `CMDDON`/`CMDDOFF`, `CMDCON` | work (checked on the board) |
| Screensaver, clock, transitions, d.ti board commands | not implemented (accepted, ignored) |
| tty2oled firmware updater | must be off (`TTY2OLED_UPDATE="no"`); our board answers `HWTDISPS3` so the updater does not recognise it |

Full command list: [docs/protocol.md](docs/protocol.md).

## Known limitations

- tty2oled pictures are monochrome/greyscale and 256×64. Scaled 1.25× with area averaging, edges
  are slightly soft. Colour pictures (`art/`) avoid that.
- If nobody reads the replies, one `ttyack;` stays in the USB FIFO and reaches the next reader first.
- tty2oled mode only: after unplugging/replugging the display, restart the tty2oled daemon (it sets
  the port up only at start). The native daemon reconnects by itself.

## Licence and credits

GPL-3.0, the same licence as tty2oled. See [LICENSE](LICENSE).

MiSTerLily builds on **[MiSTer_tty2oled](https://github.com/venice1200/MiSTer_tty2oled)** by
venice1200 and ojaksch: its protocol, its picture library and the idea itself. Thank you. The
tty2oled pictures are not included in this repository; the MiSTer downloads them from the tty2oled
server. Full list: [CREDITS.md](CREDITS.md).
