# Rev A4 audit and corrected geometry

Status: audit only. Nothing here is fabrication data.

## Sources and how values were obtained

- `QMTECH_Cyclone_V_SoC_KFB_Dimension_Top_20240607_V01.pdf` is a vector PDF.
  Pad, hole and BGA ball centres were extracted from the vector paths
  (pdftocairo -svg, scale fixed by the 2.54 mm header pitch = 21.0 units).
  Results agree with every printed dimension (106.91, 68.58, 100.48, 62.23, 20.07, 0.89).
- Schematic pages 5 (J12, J10), 8 (power) and 9 (USB, JP6).
- Adafruit CH334F 4-port Eagle board (github.com/adafruit/Adafruit-CH334F-Breakout-PCB).

## Base board frame (drawing view, top side up, HDMI/JP7 edge on the left)

`d` = mm from the HDMI/JP7 edge (along 106.91), `e` = mm from the J12 edge (along 68.58).

| Feature | d | e | Notes |
|---|---|---|---|
| J12 pin 1 (square) | 23.29 | 4.06 | odd pins = inner row, e = 4.06 |
| J12 pin 2 | 23.29 | 1.52 | even pins = outer row, near board edge |
| J12 pin 39/40 | 71.55 | 4.06 / 1.52 | pitch 2.54 along d |
| J10 pin 1 (square) | 71.55 | 64.51 | odd = inner row; pin numbers grow towards the HDMI edge |
| J10 pin 2 | 71.55 | 67.05 | |
| J10 pin 39/40 | 23.29 | 64.51 / 67.05 | |
| JP6 pin 1 USB_DM (square) | 96.95 | 4.06 | |
| JP6 pin 2 USB_5V | 94.41 | 4.06 | |
| JP6 pin 3 USB_DP | 96.95 | 1.52 | |
| JP6 pin 4 GND | 94.41 | 1.52 | matches the user's photo sketch |
| Mounting holes (M3) | 3.22 / 103.70 | 3.17 / 65.40 | |
| FPGA U1 (BGA 28x28, 0.8 mm) centre | 47.09 | 36.29 | 672 balls found in the PDF |

Approximate (raster estimate, about ±0.5 mm), top side:

| Part | d range | e range | Typical height |
|---|---|---|---|
| P1 RJ45 HanRun HR911130A | 85–107 (overhangs) | 25–41.5 | ~13.5 mm |
| J13 USB-A | 91–107 (overhangs) | 8–21 | ~7 mm (verify) |
| JP7 DC jack | 0–14.5 | 8.6–17.7 | ~11 mm (verify) |
| P3 HDMI | 0–12.5 | 22–37.5 | ~6 mm |
| J14 JTAG 2x5 right angle | 0–4 | 49–62 | ~5 mm |
| U27/U28/U29/U12 slide switches | 80–101 | 58–67 | verify |

## Backplane frame

KiCad coordinates, rear (HDMI/JP7) at y = 20, front at y = 126.91.
Parameters: I/O virtual base origin X0 = 20, inter-board gap g = 3.00 (to be measured).

- I/O Board, upright: `x = 20 + 68.58 - e`, `y = 20 + d`.
- Cyclone, flipped about the front–rear axis: `x = 91.58 + e`, `y = 20 + d`.

Result (with g = 3):

| Connector | odd-row x | even-row x | pin 1 y | pin 39 y |
|---|---|---|---|---|
| I/O J12 male | 84.52 | 87.06 | 43.29 | 91.55 |
| Cyclone J12 female | 95.64 | 93.10 | 43.29 | 91.55 |
| I/O J10 male | 24.07 | 21.53 | 91.55 | 43.29 |
| Cyclone J10 female | 156.09 | 158.63 | 91.55 | 43.29 |

- Cyclone JP6 female: pin1 (95.64, 116.95), pin2 (95.64, 114.41), pin3 (93.10, 116.95), pin4 (93.10, 114.41).
- Mirror of JP6 on the I/O side (only valid if the I/O V2.1 really has a 2x2 socket over JP6):
  pin1 (84.52, 116.95), pin2 (84.52, 114.41), pin3 (87.06, 116.95), pin4 (87.06, 114.41).
- Cyclone holes: (94.75, 23.22), (156.98, 23.22), (94.75, 123.70), (156.98, 123.70).
- FPGA centre: (127.87, 67.09).

J12 pairs are next to each other in the middle; J10 pairs are at the two outer edges.
Every pin N sits at the same y on both connectors of a pair, so the layout is mirror symmetric about x = 90.08.

## Pinouts (schematic page 5)

J12: 1 IO13, 2 IO12, 3 IO14, 4 ADC_SDO, 5 ADC_SDI, 6 Arduino_Reset_n, 7 IO6, 8 IO7, 9 IO2, 10 IO3,
11 VIN, 12 GND, 13 IO15, 14 IO0, 15 ADC_CONVST, 16 ADC_SCK, 17 IO5, 18 IO1, 19 IO4, 20 IO10,
21 IO11, 22 IO9, 23 IO8, 24 LED3, 25 LED2, 26 LED6, 27 LED1, 28 LED4, 29 3V3, 30 GND,
31 LED7, 32 LED5, 33 HPS_SPIM_MOSI, 34 HPS_SPIM_SS, 35 HPS_SPIM_CLK, 36 HPS_SPIM_MISO,
37 HPS_I2C0_SDAT, 38 HPS_I2C0_SCLK, 39 HPS_I2C1_SDAT, 40 HPS_I2C1_SCLK.

The handoff table is wrong on pins 12, 30 and 32 (it says NC / LED5 / NC).

J10 (standard Terasic GPIO layout): 1..10 = D0..D9, 11 VIN, 12 GND, 13..28 = D10..D25,
29 3V3, 30 GND, 31..40 = D26..D35.

## Adafruit 5997 facts (from the Eagle files)

- PCB 20.32 x 30.48 mm, four 2.5 mm plated holes at (2.54, 2.54), (17.78, 2.54), (2.54, 27.94), (17.78, 27.94).
- USBHOST pads JP5 at the bottom edge, PORT1..4 = JP2, JP1, JP3, JP4 on the two long edges, all 1x4 at 2.54 mm, drill 1.0.
- Pin order on all of them: 1 = 5V, 2 = D+, 3 = D-, 4 = GND (not the 5V, D-, D+, GND order of our own headers).
- The 5V pin of USBHOST and the 5V pin of every PORT are the same copper net (VBUS).
  The 2 A PTC is only between the USB-C connector and VBUS. Feeding the hub from the header pins means no fuse and no per-port switching.

## Base USB / power facts (schematic pages 8 and 9)

- JP6 and J13 share USB_DP / USB_DM of the single USB3300 PHY. J13 must stay empty.
- USB_5V comes from U13 (TPS25221 or TPS2553, R_ILIM = 20k), shared by JP6 and J13. Current limit around 1 A, to be checked.
- VIN is the raw 5 V from JP7 (marked "REGULATED 5V ONLY") with no protection on the base.

## Checks when the boards arrive

- JP6 pinout: J13 pins are wired straight to JP6 (page 9). Continuity J13 VCC ↔ JP6.2, D- ↔ JP6.1, D+ ↔ JP6.3, GND ↔ JP6.4.
- Mated height: Cyclone header shoulder + backplane socket. With a standard 8.5 mm socket the Cyclone component face is ~11 mm above the backplane.
- Real heights of P1 RJ45, JP7 jack, J13, slide switches and KEY buttons (they all face the backplane after the flip).
- Heatsink/fan: footprint, height above the FPGA, whether it is glued, airflow direction.
- I/O V2.1: outline relative to its sockets, holes, socket height, bottom-side parts, any socket over JP6, how it gets USB.
- If the I/O V2.1 has the same outline and holes as the base, its holes would be at (85.41, 23.22), (23.18, 23.22), (85.41, 123.70), (23.18, 123.70). Not confirmed.
- Minimum gap between the two boards (g, now 3.00 mm).
