# MisterFlat Rev A5 – fabrication package (PROTOTYPE)

This is a **prototype**. ERC, DRC and the pin checks pass. A 1:1 print
was checked against the real QMTECH boards (pins, holes, notches, JP6
pinout). The silkscreen still says "PROTOTYPE, NOT VALIDATED".

## Files

| File | Use |
|---|---|
| `MisterFlat_RevA5_gerbers.zip` | Upload this to JLCPCB (Gerbers + PTH/NPTH drill) |
| `gerbers/` | Same files unzipped, plus drill maps and the Gerber job file |
| `BOM_JLCPCB.csv` | BOM in JLC format, only needed for assembly |
| `CPL_JLCPCB.csv` | Pick-and-place in JLC format, only needed for assembly |
| `positions_raw.csv` | KiCad position export the CPL comes from |

## PCB order options (JLCPCB)

| Option | Value |
|---|---|
| Base material | FR-4 (standard TG is fine) |
| Layers | 4 |
| Dimensions | 220 x 106.9 mm (the site reads it from the Gerbers) |
| PCB thickness | 1.6 mm |
| Impedance control | Yes, stackup JLC04161H-7628 |
| Outer / inner copper | 1 oz / 0.5 oz |
| Via covering | Tented |
| Surface finish | HASL lead free (ENIG optional) |
| Min. track / space | 0.2 / 0.2 mm (DRC rule floor 0.15) |
| Min. hole | 0.3 mm |
| Remove order number | Specify a location, or "Yes" if offered for free |
| Quantity | 5 |

The board has internal cut-outs (FPGA window) and edge notches (RJ45,
power jack, dongle, network column). All of them are on Edge.Cuts; JLC
mills them as part of the outline.

Before ordering, open the JLC impedance calculator with JLC04161H-7628
and check the USB pairs: 0.30 mm track, 0.18 mm gap, outer layer over
In1. Target 90 Ω differential.

## Assembly

All parts are through-hole, made for hand soldering. Order bare boards.
Solder the low parts first (standing resistors, C2, C1), then the
headers, sockets, USB-A and RJ45 jacks. C1 is polarised: the + lead goes
to the square pad.

`BOM_JLCPCB.csv` and `CPL_JLCPCB.csv` are only there in case you ever
want JLC to assemble. That would need their THT assembly service.
U1 is never assembled: buy the Adafruit 5997 and plug it into its sockets.

## Front panel board

`../../PanelRevA/fab/MisterFlat_Panel_RevA_gerbers.zip` is a second,
small board (48 x 32 mm, 2 layers). Add it to the same JLC order as a
separate item: 2 layers, 1.6 mm, FR-4, HASL, quantity 5. It is cheap.

## Not on the board, buy separately

- Adafruit 5997 hub, plus 2x 1x8 and 1x4 male strips soldered on it.
- 8x M3 standoffs (height = mated connector stack, about 11 mm, measure).
- Short RJ45 patch cable (25–30 cm, flat Cat6).
- Dupont cables for J7, J8 and J23.
- 12-wire IDC ribbon with a 2x6 female plug at both ends (15-20 cm), for
  J24 to the front panel board.
- For the front panel board: 1 boxed IDC header 2x6, 3 tactile switches
  6x6 mm 13 mm high, 3 LEDs 3 mm.

## Before you order, even for a prototype

1. Print the board 1:1 (Edge.Cuts + F.Cu + User.Drawings PDFs in
   `../reports/pcb_layers_pdf/`) and put the boards you have on it.
2. Check the JP6 pinout with a multimeter (J13 to JP6).
3. Read `../../docs/RevA5_design_notes.md` section 8 for the full list.
