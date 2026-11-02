# Wiring

The display needs only USB: data and 5 V power come over the same cable. No extra wires. This is
the same for both boards (LILYGO T-Display-S3 and Waveshare ESP32-S3-Touch-LCD-2).

## Development

```
Mac (or MiSTer) ──USB-C cable──> display USB-C socket
```

Use a data cable (some USB-C cables are charge-only). On macOS the board appears as
`/dev/cu.usbmodem*`, on Linux as `/dev/ttyACM*`. Flashing and the display protocol use the same port.

## Final installation (inside the MiSTer case)

```
QMTECH MiSTer USB host ──> CH334F USB 2.0 hub (internal) ──┬──> TP-Link T2UB Nano (Wi-Fi/Bluetooth)
                                                            └──> display (USB-C)
```

- Connect the board through its **USB-C socket** with a short cable or a USB-C plug adapter from the
  hub's downstream port. The board is a normal USB 2.0 full-speed device; the hub needs no driver.
- Power: the board takes its 5 V from USB. If the hub's 5 V stays on while the MiSTer reboots (as on
  the MisterFlat backplane, fed from VIN), the display keeps running and keeps its clock through a
  reboot; the touch RESET uses that to show the menu clock while the MiSTer starts.
- Check that the hub port can supply the board together with the Wi-Fi/Bluetooth dongle.
- Orientation: rotation 0 reads correctly as checked on both boards (T-Display-S3: USB-C socket on
  the **right**). If the board must be mounted the other way round, set `ROTATE="yes"` in the
  daemon's `config.ini` (or in `tty2oled-user.ini` in tty2oled mode); the display turns the picture
  180°. The touch panel turns with it.
- The BOOT and RST buttons should stay reachable or be left alone; normal flashing does not need them.
- The Waveshare board has an IMU, a microSD slot and a camera socket; MiSTerLily does not use them.

## Not covered here

Soldering to the board's USB data pads (instead of using the USB-C socket) is **not** described: the
schematics have not been checked for this.
