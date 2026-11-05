# Virtual display (Waveshare board)

Firmware 0.6.0 or later, `waveshare_lcd2` build. The display board joins a Wi-Fi network of its
own and serves a web page with its screen: the same picture as the panel, pixel for pixel, and
touches on the page work like a finger on the panel. A phone becomes a second display.

The board is powered all the time (see power.md), so the page works while the MiSTer is switched
off: the standby screen shows, and a tap on it switches the MiSTer on.

## Set it up

1. Install MiSTerLily 0.6.0 and flash firmware 0.6.0 (MiSTerManager → Display → Update firmware).
2. MiSTerManager → Display → **Display Wi-Fi**: Find networks, pick one, type the password, Join.
   The board keeps the network only if it gets an address within 20 s; a wrong password goes
   back to the network it had.
3. Open the address shown there (or `http://misterlily.local/`). On a phone, "Add to Home Screen"
   gives it a full screen.

This Wi-Fi is not the MiSTer's. The MiSTer's own Wi-Fi (a USB dongle) is still set on the display:
the Wi-Fi button in the MiSTer menu.

## How it works

- Every drawing goes to a framebuffer in PSRAM (`DisplayManager`). While a page is open, each
  finished frame is copied, run-length coded (a flat screen is about 2 KB) and sent over a
  WebSocket, at most 15 frames per second. With no page open nothing is copied.
- Touches come back as `d x y` (down), `m x y` (move) and `u` (up). The page repeats a held touch
  every second; a touch not repeated for 2.5 s is lifted, so a locked phone does not leave a finger
  on the screen. A hold works like on the panel (2 s on RESET powers off).
- Up to 3 pages at a time. No password: anyone on the network can use it, as anyone in the room
  can touch the panel.
- Wi-Fi uses modem sleep (about 0.2 to 0.5 W more than without Wi-Fi) and turns it off while a
  page is open, for a quick reaction. Transmit power is 13 dBm, lower than the default, because the
  board's 3.3 V regulator dips on transmit peaks.
