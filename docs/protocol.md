# Serial protocol implemented by the firmware

Source of truth for tty2oled behaviour: `MiSTer_SSD1322_USB.ino` (BuildVersion 230702) and
`tty2oled.sh` at venice1200/MiSTer_tty2oled `50c08ac`. Details and evidence: `docs/research.md`.
Implementation: `firmware/lib/protocol/` (pure C++, unit-tested with `pio test -e native`).

## Link

USB CDC-ACM (ESP32-S3 USB Serial/JTAG, 303a:1001). Baud rate and line settings are ignored.
The host should set the port raw (`stty ... raw -echo -hupcl`), like tty2oled does.

## Framing

- **Text line**: bytes up to `\n`. A trailing `\r` is removed. Empty lines are ignored.
  Like `Serial.readStringUntil('\n')` with a 500 ms timeout, an unterminated line is also accepted
  after 500 ms without new bytes.
- Lines longer than 255 bytes are dropped up to the next `\n`. Lines with control bytes (< 0x20,
  0x7F) are dropped: they are almost always the tail of a picture cut by a timeout.
- **Picture**: after a line starting with `CMDCOR` or `CMDAPD`, the next bytes are a raw picture
  with **no length header**:
  - 2048 bytes = XBM, 256×64, 1 bpp, 32 bytes/row, least significant bit = leftmost pixel;
  - 8192 bytes = GSC, 256×64, 4 bpp, 128 bytes/row, high nibble = left pixel, 0 black .. 15 white.

  The picture ends at 8192 bytes, or after 500 ms without a byte (then 2048 = XBM, anything else
  = error). If no byte arrives within 1 s of the command line, the picture is "missing".
  tty2oled.sh sleeps 0.2 s between the line and the data.
- Limitation inherited from tty2oled: a command sent less than 500 ms after an XBM picture is read
  as picture data (the result is then an error and the name is shown). tty2oled.sh never does this.

## Replies

- `ttyack;` (no newline) after every line and every picture. `CMDSTTYACK,0` turns it off.
- No `ttyrdy;` at boot (the sketch sends one; nothing reads it, and over USB it would sit in front
  of the next reply).
- Replies the host does not read within 300 ms are dropped, except up to 64 bytes already in the
  USB FIFO (in practice one `ttyack;`). Before a query, send `CMDNULL` and discard what comes back.

## tty2oled commands

| Command | Behaviour here |
|---|---|
| `<core name>` (any other line) | Show the core name (text screen) |
| `CMDCOR,<core>[,t]` + picture | Show the picture scaled to 320×80 (area-averaged), centered, no text; on a missing/bad picture show the name. `t` is accepted and ignored (no transitions yet) |
| `CMDAPD,<core>` + picture | Store the picture and name, do not draw |
| `CMDSPIC[,t]` | Show the stored core screen |
| `CMDSNAM` | Show the name screen |
| `CMDCLS`, `cls` | Clear the screen |
| `CMDCLSWU` | Clear the frame buffer, do not update the screen |
| `CMDDUPD` | Update the screen from the frame buffer |
| `CMDCLST,t,c` | Fill with grey level `c`, forget the stored picture |
| `CMDDOFF` / `CMDDON` | Backlight and panel off / on (content kept) |
| `CMDCON,<0..255>` | Brightness. T-Display-S3: one of the 16 backlight levels, 0 → level 3, 255 → level 16 (0 is dim, not black). Waveshare: PWM, same curve |
| `CMDROT,<0\|1>` | 1 = turned 180° |
| `CMDTXT,f,c,b,x,y,text` | Text in a 256×64 area centered on the screen; fonts mapped to similar ones; `f >= 100` = buffer only |
| `CMDGEO,g,c,x,y,i,j,k,l` | Figures 1..10 in the same 256×64 area; `g >= 100` = buffer only |
| `CMDSORG`, `sorg` | Start screen |
| `CMDTEST` | Colour bars, 16 greys, 1 px red frame |
| `CMDHWINF` | `<board id>;MDS-<version>;\n`: `HWTDISPS3` (T-Display-S3) or `HWWSTLCD2` (Waveshare ESP32-S3-Touch-LCD-2) |
| `CMDRESET` | Restart after 100 ms (the USB port stays; no re-enumeration) |
| `CMDSETTIME,<epoch>` | Sets the clock (tty2oled sends local time as an epoch). Used by the menu and idle clock screens. Our daemon sends it at setup, every 10 min, and at once when the MiSTer clock jumps (NTP sync after boot, `hwclock`, DST) |
| `QWERTZ` (also with leading noise), `CMDNULL`, `CMDSAVER`, `CMDSWSAVER`, `CMDSECD`, `CMDSHCD`, `CMDSHTIME`, `CMDSSCP`, `CMDBYE`, `bye` | Accepted, nothing visible yet |
| any other `CMD...` | Ignored (the sketch would draw it as a core name) |

Both ids are 9 characters, as `installer.sh` expects (`${BLA:0:9}`), and unknown to its flasher.
`BOARDS` in `mister/mdsserial.py` maps them to the firmware environments; `misterlily_flash.py`
only flashes a file built for the board that answers.
The version starts with a letter, so the installer sees it as newer than any tty2oled build and does
not offer an update.

## Colour pictures: `MDSIMG`

```
MDSIMG,<bytes>,<crc32>,<png|jpg>,<core>\n
<bytes> raw bytes of the file
```

- `<bytes>`: file length, 1..524288 (512 KB, the PSRAM buffer). A larger or unreadable value is a
  broken header: nothing is skipped, and the following bytes are dropped as non-printable lines.
- `<crc32>`: 8 hex digits, CRC-32 as computed by zlib / `python3 -c "import zlib; ..."`.
- `<png|jpg>`: PNG (any bit depth, palette, alpha, interlaced; alpha is blended on black) or
  **baseline** JPEG (progressive JPEG is not supported by the decoder).
- `<core>`: the core name, shown as text if the picture cannot be used.
- The picture is drawn centered on black at 1:1. `tools/convert_asset.py` makes 320×170 files.
- Unlike `CMDCOR`, the length is announced: the frame ends exactly after `<bytes>`, and a command may
  follow immediately. If the sender stops for 1 s before the end, the frame is `incomplete`.
- Reply: `MDSIMG;ok\n` or `MDSIMG;err=<header|size|incomplete|crc|format|decode>\n`, then `ttyack;`.
  On an error the core name is shown.
- Measured on the board (USB from a Mac): 9.5 KB JPEG 0.07 s, 16 KB PNG 0.08 s, 137 KB PNG 0.30 s,
  transfer and decoding included.

## MiSTerLily commands (prefix `MDS`, unused by tty2oled)

| Command | Reply |
|---|---|
| `MDSPING` | `MDSPONG;up=<uptime ms>\n`. Our daemon sends it every 5 s: a lower uptime means the board restarted (resend everything); once pings were seen, 15 s without one shows "Waiting for MiSTer". Pings do not wake an idle-sleeping screen |
| `MDSCFG` | `MDSCFG;contrast=<0..255>;rotate=<0\|1>;idle=<minutes>;fade=<0\|1>;idleclock=<0\|1>;screenbrightness=<0\|1>\n` (settings stored in flash). `screenbrightness=1`: the brightness was picked on the touch screen, and `CMDCON` is ignored from then on |
| `MDSCFG,idle,<minutes>` | Backlight off after `<minutes>` without a core change or display command (0 = never, the default; max 1440); replies like `MDSCFG` |
| `MDSCFG,fade,<0\|1>` | Short backlight dip on core changes (default 1). `CMDCOR,<core>,0` skips it for one change |
| `MDSCFG,idleclock,<0\|1>` | When idle: a dim clock instead of a dark screen (default 0; needs the time) |
| `MDSCFG,reset` | Default settings (brightness 255, no rotation, no idle sleep, fade on, no idle clock); `CMDCON` works again |
| `MDSLOGO` | `MDSLOGO;crc=<hex>;bytes=<n>;format=<png\|jpg>\n` or `MDSLOGO;none\n`: the stored start-up picture |
| `MDSLOGO,<bytes>,<crc32>,<png\|jpg>` + file | Store the start-up picture in flash (same framing as `MDSIMG`, max 256 KB). Reply `MDSLOGO;ok\n` or `MDSLOGO;err=<header\|size\|incomplete\|crc\|format\|storage>\n` |
| `MDSCFG,logo,0` | Delete the stored start-up picture (back to the text start screen) |
| `MDSNET,<text>` | The MiSTer's addresses for the menu clock screen (empty = none). Our daemon sends `eth=<ip> wifi=<ip>` (each part only when that interface has a link and an address); each shows on its own line with an icon, Ethernet first. A bare `<ip>` (older daemons) shows without an icon. Older firmware shows the text as it is |
| `MDSINFO` | `MDSINFO;fw=..;board=<T-Display-S3\|Waveshare LCD 2>;psram=..;fb=psram;uptime_ms=..;reset=..;lines=..;images=..;discards=..;txdrop=..;txstale=..;lastimg=<result>:<bytes>;core=..\n` |
| `MDSCORE,<core>` | Show the core name (no picture transfer) |
| `MDSSHOT` | `MDSSHOT,<w>,<h>,<bytes>\n`, then `ttyack;`, then the frame buffer (RGB565 big-endian, row-major). `tools/screenshot.py` saves it as PNG |

`lastimg` result: 0 = ok, 1 = no data, 2 = bad length. `asseterr`: last `MDSIMG` error or `none`.
`host`: `none` (no ping seen, e.g. stock tty2oled daemon), `ok` or `lost`. `idle`: `awake` or `sleep`.
`reset`: ESP-IDF reset reason (1 power-on, 3 software/`CMDRESET`, 6 task watchdog, ...).

`MDSHANG` exists only in the `tdisplay_s3_debug` build: it stops the main loop to check the watchdog.
`MDSBUTTONS,<held 0-3 or -1>,<armed 0|1>` and `MDSTAP,<x>,<y>` exist only in builds with
`MDS_TEST_COMMANDS`: the touch buttons in a given state, and a 100 ms touch at a point, for
screenshots and for walking the touch screens over the serial port.

## From the display: `MDSBTN` (touch board)

A tap shows four buttons; a tap on one sends

```
MDSBTN,<reset|osd|user|bt>\n
```

From firmware 0.4.0, two level rows sit under the buttons, each with -, a bar of 8 steps and +.

- Volume (only once the host has sent `MDSVOL`): `MDSBTN,voldown`, `MDSBTN,volup`, or
  `MDSBTN,vol,<0-7>` for a tap on the bar. The native daemon passes them to Main as
  `volume <n>` / `volume unmute` on `/dev/MiSTer_cmd`. Out of mute, - and + only unmute (like
  Main's volume keys).
- Brightness of the display itself: handled on the board, nothing is sent. It is stored in flash
  as the contrast (step n = n * 255 / 7), and from then on `CMDCON` is ignored.

`MDSVOL,<0-7>,<muted 0|1>` (host → display) gives the MiSTer's global volume, in the steps of
Main's `volume <n>` command (7 = loudest). The daemon sends it after `CMDHWINF` shows a touch board
with firmware 0.4.0 or later, after each volume tap, and when `Volume.dat` changes (checked every
2 s).

`reset` needs two taps on the display (the first one arms it for 3 s). The native daemon acts like
the MiSTer's own buttons (`mister/buttons.py`); the stock tty2oled daemon ignores the line.

After sending `reset` the display goes dark at once and forgets the addresses. The board stays
powered and keeps its clock while the MiSTer reboots, and a rebooted MiSTer starts in the menu, so
2 s later it shows the menu clock by itself, as if the MiSTer were back already. The daemon sends
the same screen and the addresses when it starts (about 19 s after the reset). "Waiting for MiSTer"
is held back for 60 s meanwhile. A tap lights a dark screen again.

## Wi-Fi set-up: `MDSWIFI` (touch board, firmware 0.3.0 and later)

Older firmware shows MDS lines it does not know as core names, so the daemon sends these only to a
touch board that answers `CMDHWINF` with version 0.3.0 or later. SSIDs and passwords travel in hex.

| Line | Direction | Meaning |
|---|---|---|
| `MDSWIFI,dongle,<0\|1>` | host → display | A Wi-Fi dongle is there (wlan0). With 1, in the MiSTer menu, USER becomes the Wi-Fi button |
| `MDSWIFI,scan` | display → host | Scan for networks |
| `MDSWIFI,scanning` | host → display | Scan started (the list is cleared) |
| `MDSWIFI,net,<dBm>,<secure 0\|1>,<linked 0\|1>,<ssid hex>` | host → display | One network, strongest first, the linked one first of all; at most 20 |
| `MDSWIFI,end` | host → display | End of the list |
| `MDSWIFI,join,<ssid hex>,<password hex>` | display → host | Join; empty password for an open network |
| `MDSWIFI,status,connecting` | host → display | Joining |
| `MDSWIFI,status,ok,<ip>` / `MDSWIFI,status,fail,<reason>` | host → display | Result |

The display gives up waiting after 45 s (scan) and 60 s (join).

## Device behaviour

- **Settings**: `CMDCON` (brightness) and `CMDROT` (rotation) are stored in flash, written only when
  they change, and applied before the first frame after boot. `CMDSTTYACK` is not stored.
- **Watchdog**: if the main loop stops for 8 s the board restarts. The USB port stays (no
  re-enumeration); the ROM boot text appears on the port. Our daemon notices the restart through
  `MDSPONG` and sends the core again. With the stock tty2oled daemon the start screen stays until
  the next core change (as with tty2oled's own hardware).
- **Idle sleep**: off by default (an LCD has no burn-in). `CMDDOFF`/`CMDDON` stay independent: a core
  change wakes an idle sleep, but not a `CMDDOFF`.
- **Start screen**: the stored start-up picture (centered in a 320×130 area at the top of the
  170-pixel layout, or in 320×184 at the top of a 240-line screen; text "MiSTer / <board name>" if
  there is none or it cannot be decoded), the firmware version small in the top-right
  corner, and after 10 s without any data "Waiting for MiSTer" (anti-aliased DejaVu 24) below the picture. The picture lives in LittleFS
  on the `spiffs` data partition, which firmware uploads do not touch.
- **Menu screen**: a core named `MENU` without a picture shows time, date, the addresses from
  `MDSNET` and the firmware version (once the time is known), redrawn every minute. The column is
  centred on the screen; on the 170-pixel T-Display-S3 the gaps shrink to fit two addresses.
- **Fade**: the backlight goes down (120 ms), the new frame is pushed, and it comes back (180 ms),
  in steps of the 16 backlight levels.
  The main loop keeps running during the fade.
