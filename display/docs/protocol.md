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
| `MDSCFG` | `MDSCFG;contrast=<0..255>;rotate=<0\|1>;idle=<minutes>;fade=<0\|1>;idleclock=<0\|1>;screenbrightness=<0\|1>;clockfont=<n>;brightness=<0..7>;autoon=<0\|1>\n` (settings stored in flash). `autoon` from firmware 0.5.0. `screenbrightness=1`: the brightness was picked on the touch screen or with `MDSCFG,brightness`, and `CMDCON` is ignored from then on. `brightness` is the contrast in the 8 steps of the touch row. `clockfont` and `brightness` from firmware 0.4.1 |
| `MDSCFG,idle,<minutes>` | Backlight off after `<minutes>` without a core change or display command (0 = never, the default; max 1440); replies like `MDSCFG` |
| `MDSCFG,fade,<0\|1>` | Short backlight dip on core changes (default 1). `CMDCOR,<core>,0` skips it for one change |
| `MDSCFG,idleclock,<0\|1>` | When idle: a dim clock instead of a dark screen (default 0; needs the time) |
| `MDSCFG,brightness,<0-7>` | Backlight, like the brightness row of the touch buttons (0.4.1); `CMDCON` is ignored after it, so the daemon's `CONTRAST` does not undo it |
| `MDSCFG,clockfont,<n>` | Font of the time on the clock screen (0.4.1): 0 c64 (default), 1 7seg, 2 big, 3 sans, 4 orbitron, 5 serif, 6 mono, 7 retro16 |
| `MDSCFG,autoon,<0\|1>` | Power relay (0.5.0, [power.md](power.md)): 1 switches the MiSTer on as soon as the box gets power; 0 (default) waits in standby for a tap |
| `MDSCFG,reset` | Default settings (brightness 255, no rotation, no idle sleep, fade on, no idle clock, c64 clock font); `CMDCON` works again |
| `MDSLOGO` | `MDSLOGO;crc=<hex>;bytes=<n>;format=<png\|jpg>\n` or `MDSLOGO;none\n`: the stored start-up picture |
| `MDSLOGO,<bytes>,<crc32>,<png\|jpg>` + file | Store the start-up picture in flash (same framing as `MDSIMG`, max 256 KB). Reply `MDSLOGO;ok\n` or `MDSLOGO;err=<header\|size\|incomplete\|crc\|format\|storage>\n` |
| `MDSCFG,logo,0` | Delete the stored start-up picture (back to the text start screen) |
| `MDSNET,<text>` | The MiSTer's addresses for the menu clock screen (empty = none). Our daemon sends `eth=<ip> wifi=<ip>` (each part only when that interface has a link and an address); each shows on its own line with an icon, Ethernet first. A bare `<ip>` (older daemons) shows without an icon. Older firmware shows the text as it is |
| `MDSINFO` | `MDSINFO;fw=..;board=<T-Display-S3\|Waveshare LCD 2>;psram=..;fb=psram;uptime_ms=..;reset=..;lines=..;images=..;discards=..;txdrop=..;txstale=..;lastimg=<result>:<bytes>;asseterr=..;host=..;idle=..;power=..;core=..\n` |
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

From firmware 0.6.1, while a core runs, the first button leaves it instead (`MDSBTN,menu`, after a
second tap); the native daemon loads `menu.rbf`. Power off (and the restart) is only offered in the
MiSTer menu.

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

### Power relay (firmware 0.5.0, Waveshare board)

With a relay on GPIO 18 ([power.md](power.md)), holding RESET for 2 s sends

```
MDSBTN,poweroff\n
```

The native daemon runs `sync`, answers `MDSPOWER,halting\n` and then runs `poweroff`. The display
shows "Shutting down". Before `poweroff` the daemon writes `/run/misterlily_poweroff`, so
`S60misterlily stop` leaves it running through the init.d stop scripts and `umount -a -r`. Busybox
init then sends SIGTERM to every process; the daemon answers it with `MDSPOWER,down\n`, and the
display opens the relay 1.5 s later (init still syncs and kills the rest for about a second).

Safety limits: 30 s after `MDSPOWER,halting` if `down` never comes, 8 s after the request if no
answer comes at all. With no daemon (no ping for 15 s, or none ever) the relay opens after 1 s.
`MDSPOWER,halting` or `MDSPOWER,down` from the host at any other time starts the same countdown.

On a MiSTer the SD card can never be fully unmounted (the Linux root is a file on it), so the
kernel reports the exFAT volume as "not properly unmounted" at the next boot. A plain `reboot` does
the same; the card is mounted with `sync`, so the data is already written.

While the relay is open the display shows a standby screen; a tap closes the relay. Any data from
the host while the relay is open closes it too (the MiSTer has power some other way). `MDSINFO`
reports `power=<none|on|stopping|off>`.

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

## The display's own Wi-Fi: `MDSSTA` (Waveshare board, firmware 0.6.0 and later)

Not the MiSTer's Wi-Fi above: this is the network of the display board itself, for the virtual
display (`docs/virtual-display.md`). The host sets it; the board stores it in its flash only after
it got an address on it. SSIDs and passwords travel in hex.

| Line | Direction | Meaning |
|---|---|---|
| `MDSSTA` | host → display | Send the status line |
| `MDSSTA,scan` | host → display | Scan for networks (the board scans itself) |
| `MDSSTA,join,<ssid hex>,<password hex>` | host → display | Join; empty password for an open network. A password has 8 to 63 bytes |
| `MDSSTA,forget` | host → display | Leave the network, erase it, Wi-Fi off |
| `MDSSTA,status,<off\|connecting\|ok\|fail>,<ip>,<dBm>,<ssid hex>` | display → host | On every change and after `MDSSTA`. `fail`: a new network gave no address in 20 s; the board then goes back to the stored one |
| `MDSSTA,scanning` | display → host | Scan started |
| `MDSSTA,net,<dBm>,<secure 0\|1>,<ssid hex>` | display → host | One network, strongest first, one line per name; at most 20 |
| `MDSSTA,end,<n>` | display → host | End of the list; n is the raw scan result (access points seen, -2 = scan failed). The board tries a failed scan 3 more times first |

`MDSINFO` has `sta=<none|off|connecting|ok|fail>`.

## Quick launch: `MDSSYS` (touch board, firmware 0.6.1 and later)

In the MiSTer menu, the clock screen has a Systems button at the bottom once the host sent at least
one system. It opens a cover flow of the systems; a tap on the middle one opens a cover flow of its
games, and a tap on the middle game starts it. Drag to move, tap a side cover to bring it to the
middle. The back button (top left) goes from the games to the systems and from there to the clock;
10 s without a touch goes back to the clock.

The games come from the Systems page of MiSTerManager, which keeps them in
`/media/fat/MiSTerLily/quick` (a `games.json`, one `.mgl` and one cover per game). The
native daemon reads that folder (`mister/menu_systems.py`). It offers only systems whose `.rbf` is in
`_Console` and that have at least one game, and sends the list again within 3 s of a change.

| Line | Direction | Meaning |
|---|---|---|
| `MDSSYS,clear` | host → display | Empty the list (no Systems button). Closes the picker if it is open |
| `MDSSYS,item,<i>,<crc32>,<name>` | host → display | System `i` (0, 1, ... in order, at most 12). `crc32` of its cover, `00000000` for none |
| `MDSSYS,img,<i>` | display → host | Send the cover of system `i` (only covers the display does not have with that crc) |
| `MDSSYS,games,<i>` | display → host | Send the games of system `i` |
| `MDSSYS,games,<i>,<n>` | host → display | The list of system `i` follows: `n` games (at most 20) |
| `MDSSYS,game,<i>,<j>,<crc32>,<name>` | host → display | Game `j` of system `i`, in order |
| `MDSSYS,gimg,<i>,<j>` | display → host | Send the cover of game `j` of system `i` |
| `MDSSYSIMG,<bytes>,<crc32>,<png\|jpg>,<i>[,<j>]` + file | host → display | A cover, framed like `MDSIMG`: a system's (320×240, kept at 200×150) or, with `j`, a game's (at most 320 px on its long side; it keeps its shape, scaled to fit 180×168). No reply |
| `MDSSYS,play,<i>,<j>` | display → host | Start game `j` of system `i` |

The daemon sends the systems after `CMDHWINF` shows a touch board with firmware 0.6.1 or later.
Game covers are kept for one system at a time.

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

## Display settings for other programs (native daemon)

The daemon holds the serial port, so other programs on the MiSTer (MiSTerManager's Settings page)
use two files. With firmware 0.4.1 or later, the daemon asks for `MDSCFG` every 2 s and writes the
reply as JSON to `/tmp/misterlily_cfg`, with the font names (`clockfonts`) and `brightness_max`. It
also reads `/tmp/misterlily_cmd`, one `brightness <0-7>` or `clockfont <n>` per line, sends each as
`MDSCFG,<setting>,<value>` and removes the file. Write that file through a temporary file and a
rename. `mister/display_settings.py` has the details.
