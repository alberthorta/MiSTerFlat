# Power button (Waveshare board)

The MiSTer has no power switch: it runs as soon as it gets 5 V. With a relay, the touch display
becomes the power button. The display stays powered all the time (standby), and switches the
MiSTer's 5 V on and off.

Firmware 0.5.0 or later, `waveshare_lcd2` build. The T-Display-S3 has no touch panel and no relay pin.

## How it works

- **Standby**: the relay is open, the MiSTer has no power. The display shows a dim power symbol,
  the time (if it got it from the MiSTer before) and "Tap to power on".
- **Power on**: a tap closes the relay. The display shows "Starting MiSTer" until the daemon is
  there (about 20 s), then works as usual.
- **Power off**: open the touch buttons and hold the red RESET button for 2 s. A ring fills around
  it; letting go before it is full does nothing. The daemon runs `sync`, tells the display and
  runs `poweroff`. The display shows "Shutting down" and opens the relay when Linux has finished:
  the daemon stays up to the end of the shutdown and reports it (`MDSPOWER,down`, see
  protocol.md). At most 30 s.
- **MiSTer not answering** (hung, or no daemon): the same hold works. Without an answer the relay
  opens after 8 s; with no daemon at all, after 1 s.
- **Restart** (two taps on RESET) does not touch the relay.

The relay state is kept in flash and the pin is held (`gpio_hold_en`) through a software or
watchdog reset of the display board. The hold does **not** survive the reset that a firmware flash
does (tried: the MiSTer went off in the middle of the flash). The latch resistor below fixes that:
while the MiSTer runs, its own 3.3 V keeps the relay closed, whatever the display pin does.

When the whole box gets power, the MiSTer waits in standby. `POWER_AUTO_ON="yes"` in `config.ini`
(or `MDSCFG,autoon,1`) switches it on at once instead, as without a relay.

## Wiring

```
 Panel DC jack 5 V ──┬─────────────────────────► Waveshare P1 "5V"
 (always on)         ├─────────────────────────► relay DC+
                     └─────────────────────────► relay COM
                                relay NO ──────► MiSTer 5 V in (QMTECH: JP5 VIN)
 GND ────────────────┬─────────────────────────► Waveshare P1 "GND"
                     ├─────────────────────────► relay DC-
                     └─────────────────────────► MiSTer GND (QMTECH: JP5 GND)
 Waveshare P1 "18" ──────────────┬─────────────► relay IN
 MiSTer 3.3 V ──[ 330 Ω ]────────┘   (latch, see below)

 Waveshare USB-C ──► MiSTer USB hub: D+, D-, GND only. VBUS not connected.
```

- **Relay module**: 1 channel, 5 V coil, high-level trigger (an H/L jumper set to H). Contacts
  10 A. With the input floating (display board starting) the relay must stay open.
- **Only +5 V goes through the relay.** GND goes straight to everything.
- **No VBUS in the USB cable.** On the Waveshare board, P1 "5V" and the USB-C VBUS are the same
  net, with no diode. With VBUS in the cable, the always-on 5 V would feed the MiSTer's USB hub
  while the MiSTer is off.
- **Supply**: regulated 5 V, 3 A or more. The QMTECH board's own DC jack is not used (cover it).
- **Latch resistor**: 330 Ω from a 3.3 V point that only has power while the MiSTer runs, to
  the relay input. On the MisterFlat backplane: the 3V3 end of R1-R6 (front panel resistors),
  or J10 pin 29. While the MiSTer runs it keeps the relay closed by itself, so a reset or a
  flash of the display does not cut it. To switch off, the display drives the pin low (about
  10 mA, it wins over the resistor); the relay opens and the MiSTer's 3.3 V goes away. After a
  cold start (brownout) the firmware reads the pin first: high means the MiSTer is on.
  The value: with the relay alone, 3.3 V through the resistor to IN must close the relay
  firmly; take one step below the largest value that works.
- Wire for the 5 V path (jack, COM, NO, JP5 and its GND): 22 AWG or thicker.

### A low-level relay module instead

Modules with an optocoupler and no H/L jumper usually switch on with the input low. With 5 V on
their VCC, 3.3 V from the ESP32 does not switch them off fully. Remove the JD-VCC jumper, put
3.3 V (P2 pin 1) on VCC and 5 V on JD-VCC, and set `kMisterPowerOnLevel = 0` in
`firmware/include/boards/waveshare_lcd2.h`. The pin then goes low only while the MiSTer is on.

## Check before connecting the MiSTer

1. Relay module alone: DC+ to 5 V, DC- to GND. IN to 3.3 V: it clicks. IN to GND or open: it
   releases.
2. Flash firmware 0.5.0, wire the relay, MiSTer not connected yet. The display starts in standby.
   A tap: click, "Starting MiSTer". After 60 s without a MiSTer, "Waiting for MiSTer".
3. Hold RESET for 2 s: "Shutting down", and after 1 s (no MiSTer) the relay releases and the
   standby screen comes back.
4. Connect the MiSTer. Power on, wait for the clock, then flash the display from the MiSTer
   (`misterlily_flash.py flash FILE.bin`): the MiSTer must stay on during and after the flash.
