# Phase 0 research

Date: 2026-10-08. Everything below comes from the source files listed here, not from memory.
Where the wiki and the source disagree, the source wins.

## Sources examined

| Repository | Commit | Files |
|---|---|---|
| github.com/venice1200/MiSTer_tty2oled | `50c08acab8d279e79c47a85e51ee00f14c1a12d0` (2026-08-06) | `tty2oled.sh`, `S60tty2oled`, `tty2oled-system.ini`, `tty2oled-user.ini`, `tty2oled-read.sh`, `tty2oled_cc.sh`, `installer.sh`, `update_tty2oled_script.sh`, `Pictures/c2gsc.sh`, `MiSTer_SSD1322_USB/MiSTer_SSD1322_USB.ino` (BuildVersion `230702`), `Testing/tty2oled.sh` |
| github.com/venice1200/MiSTer_tty2oled.wiki | `cedec82ec5c113560d1192d2115a47e9cf845252` (2026-10-01) | `Command_v2.md` |
| github.com/venice1200/MiSTer_tty2oled_pictures | `e20f6bb2ea97284e68935ea16e5030801b2564ee` (2026-09-09) | `Pictures/GSC/*.gsc`, `Pictures/XBM/*.xbm`, `Pictures/XBM_TEXT/*.xbm` (samples) |
| github.com/Xinyuan-LilyGO/T-Display-S3 | `ec889e789b3cf093412689a143f7f37b42b56af7` (2026-08-31) | `lib/TFT_eSPI/User_Setups/Setup206_LilyGo_T_Display_S3.h`, `examples/*/pin_config.h`, `examples/T-Display-S3-Queue/ST7789_Handler.h`, `boards/lilygo-t-display-s3.json`, `platformio.ini`, `schematic/T_Display_S3.pdf` (present, not yet read) |
| github.com/MiSTer-devel/Linux-Kernel_MiSTer | branch `master` | `arch/arm/configs/MiSTer_defconfig` |
| Local PlatformIO | `espressif32@6.13.0`, `framework-arduinoespressif32 3.20017.241212` (Arduino core 2.0.17) | `cores/esp32/HWCDC.cpp`, `cores/esp32/USBCDC.cpp`, `cores/esp32/main.cpp`, `boards/lilygo-t-display-s3.json` |

## 1. How the MiSTer side works (tty2oled.sh)

- Started by `S60tty2oled start` (copied to `/media/fat/tty2oled/`, launched from `user-startup.sh`).
  It waits up to 10 s for `TTYDEV` to exist (`-c`), then runs `tty2oled.sh` in the background.
- Config: `. tty2oled-system.ini` then `. tty2oled-user.ini` (user file overrides). Default
  `TTYDEV="/dev/ttyUSB0"`, `BAUDRATE="115200"`, `TTYPARAM="cs8 raw -parenb -cstopb -hupcl -echo"`,
  `WAITSECS="0.2"`. The shipped user ini already contains `#TTYDEV="/dev/ttyACM0"`.
- Startup sequence, each step followed by `sleep 0.2`:
  1. `stty -F $TTYDEV 115200 cs8 raw -parenb -cstopb -hupcl -echo`
  2. `QWERTZ\n` ("first transmission to clear the buffer")
  3. `CMDCON,<0..255>\n`
  4. `CMDROT,1\n` + `CMDSORG\n` + `sleep 4` (only if `ROTATE=yes`)
  5. `CMDSETTIME,<local epoch seconds>\n`
  6. `CMDSAVER,<mode bits>,<interval>,<start>\n`
- Main loop: read `/tmp/CORENAME`, call `senddata`, then block on `inotifywait -e modify /tmp/CORENAME`.
  There is no "core changed?" comparison (it is commented out); every modify sends again.
- Every write is a separate `echo ... > $TTYDEV`, so the device is **opened and closed for every
  message**. The stable daemon never reads from the device.
- `senddata <core>` picture lookup:
  1. `pics_pri/<core>.gsc`, then `pics_pri/<core>.xbm`
  2. folders `GSC_US XBM_US GSC XBM XBM_TEXT` (filtered by `USE_US_PICTURE`, `USE_GSC_PICTURE`,
     `USE_TEXT_PICTURE`); for each folder it tries the full core name, then shorter prefixes
     (`${newcore:0:$c}` for c = len..1) until a file exists.
  3. Optional random `_altN` variant (`USE_RANDOM_ALT`).
- If a picture exists:
  ```
  echo "CMDCOR,<core>,<TRANSITION>" > $TTYDEV      # TRANSITION default -1
  sleep 0.2
  tail -n +4 <file> | xxd -r -p > $TTYDEV          # raw bytes, no header, no length
  ```
- If no picture exists: `echo "<core>" > $TTYDEV` — **just the bare core name**, no `CMD` prefix.
- `/tmp/tty2oled_sleep` pauses the daemon (used by MiSTer SAM).

## 2. Picture transfer framing (the important part)

**The image length is never announced.** The firmware decides it from what arrives:

```cpp
// MiSTer_SSD1322_USB.ino, setup()
Serial.setTimeout(500);
// oled_readlogo(), called for CMDCOR and CMDAPD
bytesReadCount = Serial.readBytes((char*)logoBin, logoBytes4bpp);   // up to 8192 bytes
if (bytesReadCount == 2048) actPicType = XBM;
else if (bytesReadCount == 8192) actPicType = GSC;
else actPicType = 0;          // shows the "transfer error" picture
```

`Stream::readBytes` stops after 8192 bytes or after 500 ms without a new byte. So:

| Format | Payload | Layout |
|---|---|---|
| XBM | 2048 bytes | 256×64, 1 bpp, 32 bytes per row, **LSB = leftmost pixel** (`bitRead(b, i)` → x*8+i) |
| GSC | 8192 bytes | 256×64, 4 bpp, 128 bytes per row, **high nibble = left pixel**, 0 = black … 15 = full |

The host sleeps 0.2 s **before** the data, not inside it. The payload may contain `0x0A`, so after
`CMDCOR`/`CMDAPD` the receiver must switch to binary mode; a line reader would break the image.

Picture files are hex text. Lines 1–3 are a C header; `tail -n +4` drops it, `xxd -r -p` turns the
`0x00,`/`0X00,` tokens into bytes (it ignores the `0x`, commas, CR and LF). Verified on macOS:

```
tail -n +4 Pictures/XBM/SNES.xbm | xxd -r -p | wc -c   -> 2048
tail -n +4 Pictures/GSC/SNES.gsc | xxd -r -p | wc -c   -> 8192
```

GSC files have mixed CRLF/LF line endings (`c2gsc.sh` builds them from an image2lcd export).

## 3. Command handling in the firmware (source of truth)

The sketch reads a line with `Serial.readStringUntil('\n')` (500 ms timeout), then compares:

- `endsWith("QWERTZ")` → ignored (garbage may precede it).
- Exact matches: `CMDNULL`, `cls`, `sorg`, `bye`, `CMDCLS`, `CMDCLSWU`, `CMDSORG`, `CMDBYE`, `CMDSHCD`,
  `CMDSHSYSHW`, `CMDHWINF`, `CMDTEST`, `CMDSNAM`, `CMDSSCP`, `CMDDOFF`, `CMDDON`, `CMDDUPD`, `CMDRESET`, `CMDSHTIME`.
- Prefix matches (`startsWith`), in this order: `CMDCLST`, `CMDSECD`, `CMDSPIC`, `CMDTXT`, `CMDGEO`, `CMDAPD`,
  `CMDCOR`, `CMDSETTIME,`, `CMDCON`, `CMDROT`, `CMDSWSAVER`, `CMDSAVER`, `CMDSTTYACK`, plus d.ti-board-only ones.
- **Anything else is a core name** and is drawn as centered text (`oled_showcorename`). This is how the
  "no picture" path works. Upstream would also draw an unknown `CMDxxx` as a core name; we will ignore
  unknown `CMD*` lines instead, because the daemon sends commands we may not implement.
- Parameter parsing: `CMDCOR,<name>[,<t>]` (`substring(7)`, split at first `,`; t in -1..23, -1 = random);
  `CMDCON,<0..255>` (`substring(7)`); `CMDROT,<0|1>` (1 = 180°); `CMDTXT,f,c,b,x,y,text` (font, fg 0..15, bg 0..15,
  x, y baseline; `f >= 100` = draw to buffer only); `CMDSPIC[,t]`; `CMDSETTIME,<epoch>`; `CMDSAVER,<mode>,<ival>,<start>`.
- Replies, all on the same serial channel:
  - `ttyrdy;` once at the end of `setup()` (no newline).
  - `ttyack;` after **every** received line (no newline), unless disabled with `CMDSTTYACK,0`.
  - `CMDHWINF` → `Serial.println("HWESP32S3;" BuildVersion ";")`, e.g. `HWESP32S3;230702;\n`, followed by `ttyack;`.
- Readers of those replies: `installer.sh` (`echo CMDHWINF; read -t5 BLA; MCUtype=${BLA:0:9}; SWver=${BLA%;*}; SWver=${SWver:10}`)
  and `tty2oled_cc.sh` (`read -d ";"`). The HW id must therefore be exactly 9 characters.

## 4. Risk in the upstream updater

`update_tty2oled.sh` → `update_tty2oled_script.sh` runs `installer.sh UPDATER` when
`TTY2OLED_UPDATE="yes"` (the default). The installer:

1. runs `esptool.py flash_id` on `TTYDEV` (this **resets the board**),
2. sends `CMDHWINF` and, if the version is older than the published build, **offers to flash the
   tty2oled SSD1322 firmware** (9 s countdown, default "no").

Mitigation:
- Our firmware answers `CMDHWINF` with the 9-char id `HWTDISPS3` and a version starting with a letter
  (`MDS-x.y.z`). `flash()` has no case for that id, and `[[ "MDS-..." > "230702" ]]` is true, so the
  installer neither flashes nor asks.
- Users testing with the upstream scripts should still set `TTY2OLED_UPDATE="no"` in `tty2oled-user.ini`
  (picture updates are a separate step and keep working).

## 5. T-Display-S3 hardware (verified)

From `Setup206_LilyGo_T_Display_S3.h` and `examples/*/pin_config.h` — they agree with the brief:

| Signal | GPIO | | Signal | GPIO |
|---|---|---|---|---|
| LCD_BL | 38 | | D0 | 39 |
| LCD_RES | 5 | | D1 | 40 |
| LCD_CS | 6 | | D2 | 41 |
| LCD_DC | 7 | | D3 | 42 |
| LCD_WR | 8 | | D4 | 45 |
| LCD_RD | 9 | | D5 | 46 |
| POWER_ON | 15 | | D6 | 47 |
| BUTTON_1 (BOOT) | 0 | | D7 | 48 |
| BUTTON_2 | 14 | | BAT_VOLT | 4 |

- Panel: ST7789, 8-bit parallel (i80), native 170×320, colour inversion on, RGB order, CGRAM offset
  (LovyanGFX: `offset_x = 35`, `offset_rotation = 1`, `invert = true`, `rgb_order = false`).
- LILYGO's own examples use TFT_eSPI (bundled, patched copy), Arduino_GFX, and LovyanGFX (`T-Display-S3-Queue`,
  `-Piano`, `-USB-Device`, `-Gingoduino`, BLE examples).
- `GPIO15` (POWER_ON): LILYGO's `tft.ino` and `factory.ino` set it HIGH unconditionally; the Queue example
  notes it is needed for the backlight on battery. We set it HIGH before LCD init.
- LILYGO's board JSON adds `-DBOARD_HAS_PSRAM`; the PlatformIO built-in `lilygo-t-display-s3.json` does not,
  so we add it ourselves. Memory type `qio_opi` (8 MB OPI PSRAM).
- The schematic PDF is in the repo; it has **not** been checked for the USB D+/D- path yet. Until it is,
  the docs only describe connecting through the USB-C socket.

## 6. Native USB CDC on the ESP32-S3

Two options exist in the Arduino core:

| | HWCDC (`ARDUINO_USB_MODE=1`) | TinyUSB CDC (`ARDUINO_USB_MODE=0`) |
|---|---|---|
| USB IDs | fixed 303a:1001, product "USB JTAG/serial debug unit", serial = MAC | configurable VID/PID/strings |
| Survives a firmware crash | yes, it is a hardware block; flashing always works | no, needs BOOT button to recover |
| Reset/flash from host | automatic via DTR/RTS | 1200-baud touch, or BOOT button |
| RX overflow | ISR drops bytes when the queue is full | `xQueueSend` waits 10 ticks, then drops |

Both drop data on overflow, so neither gives real end-to-end flow control. **Decision: the
hardware USB Serial/JTAG controller** (`ARDUINO_USB_MODE=1`, the default of both board files), but
**not through Arduino's HWCDC**. Bench results on the board (2026-10-08, macOS host):

| Transport | Result |
|---|---|
| Arduino `HWCDC` (`Serial`) | 4 of 5 `MDSINFO` replies never reached the host, although `write()` reported success. Its "connected" state machine stranded data in its TX ring. |
| ESP-IDF v4.4.7 `usb_serial_jtag` driver | No reply at all until something wrote to the FIFO directly (a ROM `printf`): the install clears `IN_EMPTY`. With a manual FIFO flush after each write, replies still stalled ~10 s after boot (11 of 30 lost, reproducible): when its TX ISR runs with an empty ring it clears `IN_EMPTY` and disables itself. Its RX ISR also drops packets when the ring is full. |
| **Polling the 64-byte FIFO registers from the main loop** (`hal/usb_serial_jtag_ll.h`) | 0 lost replies in 200 queries and in 3×30 queries right after reset; 100 lines in one write all received; GSC (8192 B) and XBM (2048 B) pictures received complete, also a GSC followed by a command in the same write. |

Polling also gives **real flow control on RX**: bytes stay in the hardware FIFO until we read
them, and while it is full the controller NAKs the host, which simply retries. A busy loop (drawing)
can delay the host but cannot lose data. TX goes through a 1 KB RAM queue; replies the host does not
read within 300 ms are dropped, so stale acks do not pile up.

Other bench facts:
- `ESP.restart()` (our `CMDRESET`) does **not** re-enumerate: the port stays, an open file descriptor
  keeps working. So the "termios reset after reconnect" risk does not apply to resets, only to a real
  unplug. The ROM prints its boot log (`ESP-ROM:esp32s3-...`) on this port after every reset.
- Opening/closing the port 20 times (DTR/RTS changes) does not reset the board.
- Up to 64 bytes written while nobody reads stay in the hardware FIFO and reach the next reader first.
  In practice that is one `ttyack;`. `installer.sh` would then read `ttyack;HWTDISPS3;...` as one line.
  Our tools send `CMDNULL` and drain before every query.
- **macOS drops output queued in its CDC driver when the port is closed, even after `tcdrain()`**
  (8 of 10 lines arrived when closing right away, 10 of 10 after 50 ms). `tools/mdsserial.py` waits
  100 ms before closing. Linux `cdc-acm` waits for output to drain on close (`closing_wait`), so the
  per-message `echo > /dev/ttyACM0` of tty2oled.sh should not lose data; to be confirmed on the MiSTer.
- We do not send the sketch's `ttyrdy;` at boot: nothing upstream reads it, and it would sit in the
  FIFO in front of the next reply.
- Nothing unsolicited may appear on the CDC port: `CORE_DEBUG_LEVEL=0`, and our debug log goes to UART0
  (GPIO43/44, `Serial0`) behind a build flag.
- The device cannot be identified by its USB strings alone (any ESP32-S3/C3 in this mode looks the same:
  303a:1001 "USB JTAG/serial debug unit", manufacturer "Espressif", serial = MAC, e.g.
  `12:34:56:78:9A:BC`). Detection = VID/PID **plus** a `CMDHWINF` handshake expecting `HWTDISPS3`.

### Linux device name

- MiSTer kernel `MiSTer_defconfig`: `CONFIG_USB_ACM=y`, `CONFIG_USB_SERIAL_CP210X=y`, `CONFIG_USB_SERIAL_CH341=y`,
  `CONFIG_INOTIFY_USER=y`. 303a:1001 is a standard CDC-ACM interface → **`/dev/ttyACM<n>`**, not `ttyUSB`.
- `n` depends on enumeration order and on whether an old node is still held open. Detection must scan
  `/sys/class/tty/ttyACM*/device/..` (`idVendor`, `idProduct`, `serial`, `product`) instead of assuming
  `/dev/serial/by-id` exists (it needs udev; not confirmed on MiSTer).
- On macOS it appears as `/dev/cu.usbmodem<location>`.

### Still open (needs the MiSTer)

- After a physical unplug/replug the node comes back with default termios (cooked, `onlcr`, echo).
  Then an image byte `0x0A` would be sent as `0x0D 0x0A`. The upstream daemon runs `stty` only once at
  start, so our own daemon must re-apply it whenever the node changes.

## 7. Display library

**LovyanGFX**, pinned to a specific version. Reasons:
- The panel and the i80 bus (ESP32-S3 LCD peripheral with DMA) are configured in our own code. TFT_eSPI needs
  its `User_Setup` selected by editing the library or by many build flags, and LILYGO ships a patched copy.
- LILYGO's newest examples use LovyanGFX with the same config we will use.
- Sprites in PSRAM: one 320×170 RGB565 framebuffer (≈109 KB) pushed in one DMA transfer, no flicker.
- The backlight is not PWM: the board drives it through an AW9364 LED driver with 16 levels, set by
  pulses on GPIO 38 (LILYGO `examples/factory/factory.ino`, `setBrightness()`). LovyanGFX's `Light_PWM`
  looked fine with a fixed duty, but the fades changed the duty, the chip counted those edges as pulses,
  and the screen ended dim. `src/hal/BacklightAw9364.h` sends the pulses itself.

## 8. Rendering legacy artwork

- 256×64 into 320×170. A 1.25× scale (320×80) is not an integer, so nearest-neighbour makes pixel logos
  uneven. First version drew 1:1 with the name below; on the board the logo looked small (about 34 mm
  wide versus 77 mm on the 3.12" OLED). Decision (2026-10-08, with the user): scale to the full width
  with exact area averaging (`lib/legacyart`), center vertically, and draw no text.
- GSC levels 0..15 map to a tint ramp (default: white/grey on black). XBM 1 = foreground, 0 = background.
- Transition effects (`t` in `CMDCOR`) are parsed and ignored for now.

## 9. Licence

tty2oled is GPL-3.0. This project re-implements the serial protocol from the description above; no
drawing or parsing code is copied from the sketch. Picture files are not bundled; they stay on the MiSTer
(downloaded by the tty2oled updater). If code is ever copied, that part must be GPL-3.0 with attribution.

## 10. Proposed architecture

```
firmware/
  src/hal/Lgfx.h              LovyanGFX panel/bus/backlight config (pins from include/config.h)
  src/transport/SerialTransport  HWCDC wrapper: big RX buffer, bulk drain, non-blocking TX
  lib/protocol/ProtocolParser pure C++ (no Arduino.h), fed (bytes, len, now_ms); line mode,
                              binary-image mode with idle timeout, bounded buffers -> events
  lib/protocol/CommandDecoder "CMDCOR,name,t" etc. -> typed structs
  src/app/App                 small state machine: Boot -> WaitingForMister -> ShowingCore / Off
  src/ui/DisplayManager       panel + PSRAM RGB565 framebuffer, present(), brightness, rotation
  src/ui/CoreScreen           layout: artwork area + core name
  src/ui/TextRenderer         fitted, centered text for names and fallbacks
  src/ui/LegacyAssetRenderer  XBM (1 bpp) / GSC (4 bpp) 256x64 -> RGB565
  test/                       PlatformIO `native` env + Unity, parser tests with real tty2oled fixtures
mister/
  find-display.sh             sysfs scan of /sys/class/tty/ttyACM* (303a:1001) + CMDHWINF handshake
  install.sh / uninstall.sh   configure upstream tty2oled (TTYDEV, TTY2OLED_UPDATE=no), later our daemon
  mister-display.sh           own daemon (later): autodetect, re-apply stty on reconnect, colour assets
tools/
  fake_mister.py              replays the exact tty2oled byte stream from macOS/Linux, no pyserial needed
  convert_asset.py            PNG/JPEG -> native colour format (phase 5)
```

Data flow: CDC bytes -> ProtocolParser -> events -> App -> screens draw into the framebuffer -> present().
Serial parsing never calls rendering code directly.
