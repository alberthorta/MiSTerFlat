# MiSTerLily

A colour status display for a MiSTer FPGA, built on a LILYGO T-Display-S3 (1.9" 320×170 TFT).
When MiSTer loads a core, the display shows that system's logo and name.

Website: **https://alberthorta.github.io/MiSTerLily/**

It speaks the serial protocol of [MiSTer_tty2oled](https://github.com/venice1200/MiSTer_tty2oled),
so the unmodified tty2oled daemon and its picture library drive it over native USB.

Status: **Phase 6** done — colour pictures, our own MiSTer daemon with heartbeat and reconnection,
watchdog, stored settings, fades, a menu clock screen, idle sleep and a "Waiting for MiSTer" screen
work on the bench (board on a Mac, scripts in Linux containers). tty2oled compatibility mode works
too. Not yet tested on a real MiSTer.

## Hardware

- **LILYGO T-Display-S3**, ESP32-S3R8 (16 MB flash, 8 MB PSRAM), ST7789 170×320 on the 8-bit
  parallel bus. Touch or non-touch version. Not the T-Display (ESP32) or T-Display-S3 AMOLED.
- A USB-C data cable. In the final build: a free port on the MiSTer's internal USB hub
  (see [docs/wiring.md](docs/wiring.md)).

## Build and flash

Needs [PlatformIO](https://platformio.org/) (`brew install platformio`).

```sh
cd firmware
pio run                       # build
pio run -t upload             # build and flash (auto-detects the port)
pio test -e native            # protocol unit tests on the computer, no board needed
```

No buttons are needed to flash. If an upload fails: hold **BOOT**, press and release **RST**,
release **BOOT**, upload again.

`tdisplay_s3_debug` is the same firmware with a debug log on UART0 (GPIO43 TX, 115200 baud). The USB
port never carries debug output, because the MiSTer scripts read replies from it.

### Releases

A version tag builds the firmware on GitHub Actions and publishes it as a release
(`.github/workflows/release.yml`). The MiSTer can then flash it without a computer (see
[docs/mister-install.md](docs/mister-install.md#firmware-updates-from-the-mister)).

```sh
# set MDS_FW_VERSION in firmware/include/config.h, commit, then:
git tag v0.2.0 && git push origin v0.2.0
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
python3 tools/fake_mister.py --selftest <Pictures folder>  # picture decoding vs tail | xxd
python3 tests/fixtures/make_fixtures.py                    # rebuild the parser test fixtures
python3 tests/fixtures/make_art.py                         # rebuild the colour test pictures
```

## Installing on the MiSTer

See [docs/mister-install.md](docs/mister-install.md). Quickest: `python3 tools/make_mister_installer.py`,
copy `dist/misterlily_install.sh` to `/media/fat/Scripts/` (or to the `Scripts` folder of a fresh
Mr. Fusion card) and run it once from the MiSTer Scripts menu. Then run `misterlily_update` from the
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
The panel shows 16-bit colour; `--dither` avoids bands in smooth gradients.

## What the screen shows

- A core with a colour picture: the picture, full screen.
- A core with a tty2oled picture: the picture scaled to the full width (256×64 → 320×80, smoothed),
  centered, no text (the logos carry the name).
- A core without a picture, or a failed transfer: the system name, large, in the Commodore 64 font.
- Common systems get a friendly name (`PSX` → PLAYSTATION) with the MiSTer core name small below.
- Start-up: your own picture (stored on the board, 320×130 area) or "MiSTer / T-Display-S3", and the
  firmware version; "Waiting for MiSTer" if nothing arrives within 10 s, or when our daemon stops
  answering for 15 s. Store the picture with `python3 tools/set_logo.py <port> logo.png`, or put it at
  `/media/fat/MiSTerLily/art/STARTUP.png` on the MiSTer (the daemon stores it when it changes).
- The MiSTer menu (native mode): a clock screen with time, date and the MiSTer's IP address, unless
  you put an `art/MENU.png`.
- A short backlight dip when the core changes (can be turned off).
- Brightness, rotation and the options below are remembered across power cycles. Optional idle
  sleep, dark or with a dim clock (`IDLE_MINUTES` / `IDLE_SCREEN` in the daemon config).

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

- Not tested on a MiSTer yet (the QMTECH board has not arrived). Open points are listed at the end
  of [docs/mister-install.md](docs/mister-install.md).
- tty2oled pictures are monochrome/greyscale and 256×64. Scaled 1.25× with area averaging, edges
  are slightly soft. Native colour artwork is Phase 5.
- If nobody reads the replies, one `ttyack;` stays in the USB FIFO and reaches the next reader first.
- tty2oled mode only: after unplugging/replugging the display, restart the tty2oled daemon (it sets
  the port up only at start). The native daemon reconnects by itself.

## Licence and credits

GPL-3.0, the same licence as tty2oled. See [LICENSE](LICENSE).

MiSTerLily builds on **[MiSTer_tty2oled](https://github.com/venice1200/MiSTer_tty2oled)** by
venice1200 and ojaksch: its protocol, its picture library and the idea itself. Thank you. The
tty2oled pictures are not included in this repository; the MiSTer downloads them from the tty2oled
server. Full list: [CREDITS.md](CREDITS.md).
