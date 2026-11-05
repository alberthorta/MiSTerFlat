# Changelog

## Rev A5 update (2026-10-20)

- Fit test on the 1:1 print with the real boards: I/O Board and Cyclone
  pins, holes and notches match. JP6 pinout checked with a multimeter.
  Heatsink, dongle and Adafruit 5997 fit.
- Gap between the boards 21 -> 31 mm: the Cyclone microSD slot faces
  the I/O J12 and needs finger room. J22/J23, J24 and R1-R6 stay centred
  in the gap. The board is now 220 mm wide.
- New front panel board (`PanelRevA/`, 48 x 32 mm, 2 layers): 3 tactile
  buttons and 3 LEDs, cabled to J24 with a 12-wire IDC ribbon. The IDC
  header is on the back at the top, so the M3 holes are symmetric.
- J24 is now a boxed IDC header 2x6 (same pins, same routing). Its pin
  labels moved to the front panel board.
- `tools/make_outputs.sh` regenerates both boards and every output.
- Mechanical PDF page 5: front panel drilling template.

## Rev A5 update (2026-10-10)

- J21 (front network jack) moved 1.35 mm right, lined up with J20.
- Front panel resistors in 2 rows of 3 (buttons, then LEDs), centred
  between the boards, 5.6 mm apart. LED anodes now on B.Cu; the JP6-to-J6
  5V link moved up to y 106. Labels moved under J24, larger.
- C1 moved 1.5 mm away from C2.
- J7 (AUX) and J8 (DISPLAY) moved 1.5 mm left; a mated Dupont housing now
  ends 3 mm before the right edge.

## Rev A5 update (2026-10-09)

- No SMD parts left, everything is through-hole for hand soldering:
  R1–R6 are standing 1/4 W resistors, C1 is a 47 µF 16 V radial
  electrolytic, C2 a 100 nF ceramic disc. The front panel signals now
  end directly on the J24 pads (7 vias fewer).

- Front panel header J24 (2x6) in the gap, near the front: RESET, OSD and
  USER buttons (J10 pins 17, 13, 15, 10 kΩ pull-ups) and USER, DISK and
  POWER LEDs (J10 pins 1, 3, 5, 1 kΩ from 3V3). The GPIO_1 lanes open to
  1.2 mm in the gap so the signals can drop to In2. The I/O USB pair
  moved lower in that zone.

- Gap between the boards 5 -> 21 mm. A rear USB-A (J22) sits between the
  two rear standoffs. Right behind it, a 90° 1x4 header (J23: VIN, D-,
  D+, GND, with VIN and GND marked) has its pins facing the front, so a
  cable can run forward in the gap. Everything right of the gap moved
  16 mm; the board is now 210 mm wide.

- Network extension on the left: J21 (faces the front, in a recess)
  takes a short patch cable from the Cyclone RJ45, and J20 brings the
  network to the rear edge. Pin N to pin N, no vias. The board grows
  23 mm to the left (to x = -4), and the column is 5 mm away from the
  I/O Board. The column stops at y = 105 for the cable plug. New case
  hole H12.
- Silkscreen: the Cyclone rear label now says POWER 5V instead of JP7.

- J7 (AUX) and J8 (DISPLAY) moved inside the board, to x = 170.5. Their
  pins and a mated Dupont housing no longer stick out of the right edge.
- Rerouted the hub area for this: Wi-Fi pair moved west, AUX and DISPLAY
  pairs enter from the east under the header bodies, upstream pair lane
  moved to y = 84, C1/C2 moved above the USB-A.
- Two more M3 case holes in the hub section: H8 (187.5, 22.5) at the
  rear-right corner and H9 (186.5, 85.5) under the headers. The hub
  courtyard now follows the real module outline (rounded corners), so H8
  fits.
- I/O Board standoff holes added as the mirror of the base holes (H1–H4).
  They replace the two generic case holes on the left. The end of the
  I/O USB pair was rerouted to keep clear of the front-right hole.
- Silkscreen: "QMTECH I/O BOARD V2.1 mounts here upright" and "QMTECH
  CYCLONE V SoC mounts here FLIPPED". Rear labels: VGA / AUDIO on the I/O
  side, HDMI / POWER 5V on the Cyclone side. "I/O USB?" is now "I/O USB".
- `verify.py` now checks that every part is on the top side, the same
  side as the two QMTECH boards.

## Rev A5 (2026-10-09) - prototype, not for fabrication

New project in `RevA5/`. It is generated from `tools/design.py`. The A4
files in `handoff/` are kept as they were.

Geometry
- Fixed the flip: in A4 the Cyclone connectors were placed as if the
  board was **not** flipped, and the I/O ones as if it **was**. Now the
  I/O Board is upright and the Cyclone is mirrored about the front–rear
  axis. Both J12 connectors are now in the middle and both J10 connectors
  at the outer edges. A4 had them the other way round.
- Pin positions come from the vector dimension drawing (J12 pin 1,
  J10 pin 1, JP6, holes, FPGA centre). They are no longer estimates from
  the raster image.
- JP6: pins 1 and 2 sit along the header length, not across it. It moved
  to the front-left of the Cyclone.
- Gap between boards: 3 mm -> 5 mm.
- Fan window: 54 x 54 -> 38.5 x 38.5 mm (half the margin). It is now
  centred on the real FPGA centre (A4 was 2 mm off). At the correct
  position, the A4 window was 0.4 mm from the J10 pads.
- New notches for the Cyclone RJ45 (front) and DC jack JP7 (rear).
- Added the 4 Cyclone M3 standoff holes and the case holes, each with a
  copper keepout.
- Board is 1 mm wider on the left (J10 pads were 0.7 mm from the edge)
  and ends at x = 190 on the right.

Electrical
- Real schematic: KiCad library symbols, one Adafruit 5997 symbol, real
  net names. ERC is clean.
- Fixed the J12 table: pins 12 and 30 are GND, pin 32 is LED5.
- Power and GND are real nets now (A4 had 80 single-pin nets).
- Hub power comes from JP6 pin 2 (USB_5V). The same net feeds the I/O
  USB header, AUX, DISPLAY and the USB-A.
- Hub ports: P1 = I/O, P2 = DISPLAY, P3 = Wi-Fi USB-A, P4 = AUX. P3 and
  P4 are swapped against the brief, so no USB pair needs a via.
- Added 47 µF + 100 nF at the USB-A.

Footprints
- Standard KiCad footprints: PinHeader/PinSocket 2x20 and 2x2, 1x4
  right angle, Molex 67643 USB-A, MountingHole M3.
- New `MisterFlat:Adafruit_5997_CH334F_Socketed`. Pads come from the
  official Adafruit Eagle board, checked against its copper.

Layout
- 4 layers, two solid inner GND planes, everything routed. USB pairs at
  0.30/0.18 mm, no vias.
- DRC with schematic parity: 0 errors, 0 unconnected. The remaining
  warnings are silkscreen that overhangs the edge on purpose.
- Mechanical PDF: page 1 now shows all 12 holes and real dimension lines (hole spacing, notch, recess and window sizes, overall size); page 2 adds hole-to-hole distances.
