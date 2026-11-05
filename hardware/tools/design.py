"""Single source of truth for MisterFlat Rev A5: geometry, parts and netlist.

Imported by build_sch.py (system python) and build_pcb.py (KiCad python).
All coordinates are KiCad board mm. Rear (HDMI/JP7) is y = 20, front is y = 126.91.
"""

REV = "A5"
PROJECT = "MisterFlat_RevA5"

# --- QMTECH base board, drawing frame -------------------------------------
# d: mm from the HDMI/JP7 edge, e: mm from the J12 edge (top side up).
# Values extracted from the vector Dimension_Top PDF, see docs/RevA4_audit.md.
BASE_L = 106.91
BASE_W = 68.58
PITCH = 2.54
E_ODD = 4.063           # J12 odd row (inner)
E_EVEN = 1.523          # J12 even row (outer, next to the board edge)
D_PIN1 = 23.29          # J12 pin 1 / J10 pin 39
HOLE_D = (3.22, 103.70)
HOLE_E = (3.17, 65.40)
FPGA_D, FPGA_E = 47.09, 36.29
FPGA_BODY = 23.0

# Raster estimates (+-0.5 mm), to be measured on the real board.
RJ45_D, RJ45_E = (85.1, 106.91), (24.8, 41.5)
JP7_D, JP7_E = (0.0, 14.5), (8.6, 17.7)
KEY2_D, KEY2_E = (84.7, 91.8), (0.1, 4.2)      # tact switch next to JP6
J13_D, J13_E = (90.9, 106.91), (7.8, 21.3)     # USB-A, shares D+/D- with JP6

# --- Backplane parameters --------------------------------------------------
Y0 = 20.0
X0_IO = 20.0            # left edge of the I/O virtual outline (same outline as the base)
GAP = 31.0              # gap between the boards: finger room for the Cyclone microSD slot, which faces the I/O J12
X0_CY = X0_IO + BASE_W + GAP
DX = round(X0_CY - 93.58, 3)        # shift of everything right of the gap against the 5 mm-gap layout


def sx(x):
    """x coordinate of the Cyclone / hub side, written for the 5 mm-gap layout."""
    return round(x + DX, 3)


AXIS2 = X0_IO + BASE_W + X0_CY      # mirror: x' = AXIS2 - x
X_LEFT = X0_IO - 1.0                # 1 mm margin so the J10 pads are not on the edge
X_RIGHT = 190.0 + DX
Y_FRONT = Y0 + BASE_L
NOTCH_MARGIN = 1.0
WINDOW_MARGIN = (54.0 - FPGA_BODY) / 2 / 2   # half of the A4 margin -> 7.75 mm


def io(d, e):
    """I/O Board upright: same top view as the base in the original stack."""
    return (round(X0_IO + BASE_W - e, 3), round(Y0 + d, 3))


def cy(d, e):
    """Cyclone flipped about the front-rear axis: x mirrors, y keeps."""
    return (round(X0_CY + e, 3), round(Y0 + d, 3))


def mirror_x(x):
    return round(AXIS2 - x, 3)


FPGA_C = cy(FPGA_D, FPGA_E)
WIN_HALF = FPGA_BODY / 2 + WINDOW_MARGIN
WINDOW = (FPGA_C[0] - WIN_HALF, FPGA_C[1] - WIN_HALF, FPGA_C[0] + WIN_HALF, FPGA_C[1] + WIN_HALF)

_rx = sorted(cy(0, e)[0] for e in RJ45_E)
NOTCH_RJ45 = (round(_rx[0] - NOTCH_MARGIN, 2), round(cy(RJ45_D[0], 0)[1] - NOTCH_MARGIN, 2),
              round(_rx[1] + NOTCH_MARGIN, 2), Y_FRONT)
_jx = sorted(cy(0, e)[0] for e in JP7_E)
NOTCH_JP7 = (round(_jx[0] - NOTCH_MARGIN, 2), Y0,
             round(_jx[1] + NOTCH_MARGIN, 2), round(cy(JP7_D[1], 0)[1] + NOTCH_MARGIN, 2))
NOTCH_DONGLE = (166.0 + DX, 108.2, X_RIGHT, Y_FRONT)

# Network extension column on the left: a jack at the rear (to the rear panel) and a jack facing
# the front, fed by a short patch cable from the Cyclone RJ45. The column stops before the front
# edge so the cable plug has room.
NET_X_LEFT = -4.0                # 5 mm extra gap between the network lines and the I/O J10 pins
NET_FRONT = 105.0

OUTLINE = [
    (NET_X_LEFT, Y0), (NOTCH_JP7[0], Y0), (NOTCH_JP7[0], NOTCH_JP7[3]), (NOTCH_JP7[2], NOTCH_JP7[3]),
    (NOTCH_JP7[2], Y0), (X_RIGHT, Y0), (X_RIGHT, NOTCH_DONGLE[1]), (NOTCH_DONGLE[0], NOTCH_DONGLE[1]),
    (NOTCH_DONGLE[0], Y_FRONT), (NOTCH_RJ45[2], Y_FRONT), (NOTCH_RJ45[2], NOTCH_RJ45[1]),
    (NOTCH_RJ45[0], NOTCH_RJ45[1]), (NOTCH_RJ45[0], Y_FRONT), (X_LEFT, Y_FRONT),
    (X_LEFT, NET_FRONT), (NET_X_LEFT, NET_FRONT),
]

# --- Base connector pin positions -----------------------------------------
def j12_de(pin):
    k = (pin - 1) // 2
    return (D_PIN1 + PITCH * k, E_ODD if pin % 2 else E_EVEN)


def j10_de(pin):
    k = (pin - 1) // 2
    return (D_PIN1 + PITCH * (19 - k), BASE_W - (E_ODD if pin % 2 else E_EVEN))


def jp6_de(pin):
    return {1: (96.95, E_ODD), 2: (94.41, E_ODD), 3: (96.95, E_EVEN), 4: (94.41, E_EVEN)}[pin]


# --- Netlist ---------------------------------------------------------------
J12_NETS = {
    1: "Arduino_IO13", 2: "Arduino_IO12", 3: "Arduino_IO14", 4: "ADC_SDO", 5: "ADC_SDI",
    6: "Arduino_Reset_n", 7: "Arduino_IO6", 8: "Arduino_IO7", 9: "Arduino_IO2", 10: "Arduino_IO3",
    11: "VIN", 12: "GND", 13: "Arduino_IO15", 14: "Arduino_IO0", 15: "ADC_CONVST", 16: "ADC_SCK",
    17: "Arduino_IO5", 18: "Arduino_IO1", 19: "Arduino_IO4", 20: "Arduino_IO10", 21: "Arduino_IO11",
    22: "Arduino_IO9", 23: "Arduino_IO8", 24: "LED3", 25: "LED2", 26: "LED6", 27: "LED1", 28: "LED4",
    29: "3V3", 30: "GND", 31: "LED7", 32: "LED5", 33: "HPS_SPIM_MOSI", 34: "HPS_SPIM_SS",
    35: "HPS_SPIM_CLK", 36: "HPS_SPIM_MISO", 37: "HPS_I2C0_SDAT", 38: "HPS_I2C0_SCLK",
    39: "HPS_I2C1_SDAT", 40: "HPS_I2C1_SCLK",
}


def _j10_net(pin):
    if pin <= 10:
        return f"GPIO_1_D{pin - 1}"
    if pin in (12, 30):
        return "GND"
    # Same copper as VIN / 3V3 on both QMTECH boards. Kept as own nets so the backplane
    # needs no cross link between the J12 and J10 power pins.
    if pin == 11:
        return "J10_VIN"
    if pin == 29:
        return "J10_3V3"
    if pin <= 28:
        return f"GPIO_1_D{pin - 3}"
    return f"GPIO_1_D{pin - 5}"


J10_NETS = {p: _j10_net(p) for p in range(1, 41)}
JP6_NETS = {1: "USB_UP_D-", 2: "USB_5V", 3: "USB_UP_D+", 4: "GND"}
IOUSB_NETS = {1: "USB_IO_D-", 2: "USB_5V", 3: "USB_IO_D+", 4: "GND"}

# Adafruit 5997, pin order on every 1x4 group: 5V, D+, D-, GND.
# Pads keep their own names; VBUS and GND are repeated pad numbers (one copper net on the module).
# Hub port use (ports are equivalent on the CH334F; 3 and 4 swapped against the brief so that no
# USB pair needs a via, see docs/CHANGELOG.md):
HUB_PORT_USE = {1: "IO", 2: "DISP", 3: "WIFI", 4: "AUX"}
U1_NETS = {"VBUS": "USB_5V", "GND": "GND", "UP_D+": "USB_UP_D+", "UP_D-": "USB_UP_D-"}
for _p, _u in HUB_PORT_USE.items():
    U1_NETS[f"P{_p}_D+"] = f"USB_{_u}_D+"
    U1_NETS[f"P{_p}_D-"] = f"USB_{_u}_D-"

# Our own 1x4 USB headers: 1 = 5V, 2 = D-, 3 = D+, 4 = GND (as in the brief).
AUX_NETS = {1: "USB_5V", 2: "USB_AUX_D-", 3: "USB_AUX_D+", 4: "GND"}
DISP_NETS = {1: "USB_5V", 2: "USB_DISP_D-", 3: "USB_DISP_D+", 4: "GND"}
USBA_NETS = {"1": "USB_5V", "2": "USB_WIFI_D-", "3": "USB_WIFI_D+", "4": "GND", "SH": "GND"}

# Straight-through RJ45 extension, pin N to pin N. Pairs: 1-2, 3-6, 4-5, 7-8.
ETH_NETS = {1: "ETH_A+", 2: "ETH_A-", 3: "ETH_B+", 4: "ETH_C+", 5: "ETH_C-", 6: "ETH_B-",
            7: "ETH_D+", 8: "ETH_D-"}

# Rear USB-A between the two boards, broken out to a 1x4 header for a cable.
REAR_USB_NETS = {"1": "USB_REAR_VBUS", "2": "USB_REAR_D-", "3": "USB_REAR_D+", "4": "GND", "SH": "GND"}
# 90 deg header right behind the USB-A, pins facing the front. Same pin order as the USB-A.
REAR_HDR_NETS = {"1": "USB_REAR_VBUS", "2": "USB_REAR_D-", "3": "USB_REAR_D+", "4": "GND"}
REAR_USB_X = round((io(HOLE_D[0], HOLE_E[0])[0] + cy(HOLE_D[0], HOLE_E[0])[0]) / 2, 3)   # middle of the two rear standoffs
REAR_USB_OVERHANG = 1.0     # face 1 mm past the rear edge, into the panel cut-out

# Front panel buttons and LEDs (from the Cyclone J10), in the gap between the boards, near the front.
# Buttons: 10k pull-up to 3V3, button to GND. LEDs: 3V3 - 1k - LED - FPGA pin (on when the pin is low).
# Columns west to east: (function, J10 pin, kind)
PANEL = [("RESET", 17, "btn"), ("OSD", 13, "btn"), ("USER", 15, "btn"),
         ("LED USER", 1, "led"), ("LED DISK", 3, "led"), ("LED POWER", 5, "led")]
PANEL_X0 = round(X0_IO + BASE_W + GAP / 2 - 2.5 * PITCH, 3)   # first column, header centred in the gap
PANEL_ROW_Y = 117.5                        # north row of J24; south row is +2.54
PANEL_RAIL_Y = 107.0                       # 3V3 rail on F.Cu
# Standing resistors in 2 rows of 3, centred in the gap. Pads side by side: pad 1 (3V3) west.
_gap_c = X0_IO + BASE_W + GAP / 2
GAP_C = _gap_c
PANEL_R_ROWS = (108.6, 111.75)             # buttons (R1-R3) north row, LEDs (R4-R6) south row
PANEL_R_CX = [round(_gap_c + 5.6 * _k, 3) for _k in (-1, 0, 1)]
PANEL_CROSS_X = [round(_gap_c + _o, 3) for _o in (-8.08, -5.6, -2.8, 0.0, 2.8, 5.6)]  # In2 through the rows
GAP_SPREAD = tuple(round(_gap_c + _o, 3) for _o in (-4.58, 8.92, 6.92))   # bus spread zone: west x, F east x, B east x
PANEL_TAP_X = [round(_gap_c - 2.58 + 1.2 * _k, 3) for _k in range(6)]   # tap vias on the spread lanes, same order as PANEL
PANEL_3V3_X = round(_gap_c + 9.92, 3)      # 3V3 tap on the J12 3V3 lane, then In2 down to the rail


def panel_col_x(i):
    return round(PANEL_X0 + PITCH * i, 3)


PANEL_NETS = {}       # J24 pin -> net
PANEL_R = {}          # ref -> (value, net on pin 2)
for _i, (_name, _pin, _kind) in enumerate(PANEL):
    _q = 5 - _i                    # the 2x6 header numbers its pairs from the east end
    _sig = J10_NETS[_pin]
    if _kind == "btn":
        PANEL_NETS[str(2 * _q + 1)] = _sig
        PANEL_NETS[str(2 * _q + 2)] = "GND"
        PANEL_R[f"R{_i + 1}"] = ("10k", _sig)
    else:
        _anode = "LED_" + _name.split()[1] + "_A"
        PANEL_NETS[str(2 * _q + 1)] = _sig          # cathode side, FPGA pin
        PANEL_NETS[str(2 * _q + 2)] = _anode
        PANEL_R[f"R{_i + 1}"] = ("1k", _anode)

# --- Placement -------------------------------------------------------------
HUB_C = (176.5 + DX, 41.24)          # centre of the Adafruit PCB (20.32 x 30.48)
# 90 deg headers point to the right edge but stay inside it, with a mated
# Dupont housing (pins end at +10.2 mm, a 14 mm housing ends at +18.0 mm).
AUX_PIN1 = (169.0 + DX, 60.0)
DISP_PIN1 = (169.0 + DX, 72.0)
DUPONT_LEN = 14.0
USBA_PIN1_X = 174.5 + DX            # y is computed from the footprint so the face meets the notch edge
NET_REAR_PIN1_X = 10.0          # J20, face flush with the rear edge
NET_FRONT_PIN1_X = 1.11         # J21, face on the column front edge (y = NET_FRONT), body on the left edge

KICAD_FP = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/"
KICAD_SYM = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols/"

# ref: (value, symbol, footprint, pin->net, extra fields)
PARTS = {
    "J1": ("I/O J12 2x20 male", "Connector_Generic:Conn_02x20_Odd_Even",
           "Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical",
           {str(p): n for p, n in J12_NETS.items()},
           {"Note": "Mates I/O Board V2.1 J12 socket (bottom side)"}),
    "J2": ("Cyclone J12 2x20 female", "Connector_Generic:Conn_02x20_Odd_Even",
           "Connector_PinSocket_2.54mm:PinSocket_2x20_P2.54mm_Vertical",
           {str(p): n for p, n in J12_NETS.items()},
           {"Note": "Receives Cyclone J12 male pins, board flipped"}),
    "J3": ("I/O J10 2x20 male", "Connector_Generic:Conn_02x20_Odd_Even",
           "Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical",
           {str(p): n for p, n in J10_NETS.items()},
           {"Note": "Mates I/O Board V2.1 GPIO_1 socket"}),
    "J4": ("Cyclone J10 2x20 female", "Connector_Generic:Conn_02x20_Odd_Even",
           "Connector_PinSocket_2.54mm:PinSocket_2x20_P2.54mm_Vertical",
           {str(p): n for p, n in J10_NETS.items()},
           {"Note": "Receives Cyclone J10 (GPIO_1) male pins, board flipped"}),
    "J5": ("Cyclone JP6 2x2 female", "Connector_Generic:Conn_02x02_Odd_Even",
           "Connector_PinSocket_2.54mm:PinSocket_2x02_P2.54mm_Vertical",
           {str(p): n for p, n in JP6_NETS.items()},
           {"Note": "USB host from Cyclone JP6: 1 DM, 2 5V, 3 DP, 4 GND"}),
    "J6": ("I/O USB 2x2 male (PROVISIONAL)", "Connector_Generic:Conn_02x02_Odd_Even",
           "Connector_PinHeader_2.54mm:PinHeader_2x02_P2.54mm_Vertical",
           {str(p): n for p, n in IOUSB_NETS.items()},
           {"Note": "Mirror of JP6. Only valid if I/O V2.1 has a 2x2 socket over JP6"}),
    "U1": ("Adafruit 5997 CH334F 4-port hub", "MisterFlat:Adafruit_5997",
           "MisterFlat:Adafruit_5997_CH334F_Socketed", dict(U1_NETS),
           {"Note": "Module on 2x 1x8 + 1x4 female sockets"}),
    "J7": ("USB AUX 1x4 90deg male", "Connector_Generic:Conn_01x04",
           "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Horizontal",
           {str(p): n for p, n in AUX_NETS.items()}, {"Note": "1 5V, 2 D-, 3 D+, 4 GND"}),
    "J8": ("USB DISPLAY 1x4 90deg male", "Connector_Generic:Conn_01x04",
           "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Horizontal",
           {str(p): n for p, n in DISP_NETS.items()}, {"Note": "T-Display-S3. 1 5V, 2 D-, 3 D+, 4 GND"}),
    "J9": ("USB-A Wi-Fi/BT", "Connector:USB_A", "Connector_USB:USB_A_Molex_67643_Horizontal",
           dict(USBA_NETS), {"MPN": "Molex 67643-0910"}),
    "J20": ("RJ45 NET OUT (rear)", "Connector:8P8C", "Connector_RJ:RJ45_Amphenol_54602-x08_Horizontal",
            {str(p): n for p, n in ETH_NETS.items()}, {"MPN": "Amphenol 54602-908 (no magnetics)"}),
    "J21": ("RJ45 NET IN (from Cyclone)", "Connector:8P8C", "Connector_RJ:RJ45_Amphenol_54602-x08_Horizontal",
            {str(p): n for p, n in ETH_NETS.items()},
            {"MPN": "Amphenol 54602-908 (no magnetics)", "Note": "Patch cable from the Cyclone RJ45 P1"}),
    "J22": ("USB-A rear (cable to J23)", "Connector:USB_A", "Connector_USB:USB_A_Molex_67643_Horizontal",
            dict(REAR_USB_NETS), {"MPN": "Molex 67643-0910"}),
    "J23": ("Rear USB 1x4 90deg male (VIN, D-, D+, GND)", "Connector_Generic:Conn_01x04",
            "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Horizontal",
            dict(REAR_HDR_NETS), {"Note": "1 VIN, 2 D-, 3 D+, 4 GND (VIN and GND marked)"}),
    "J24": ("Front panel IDC 2x6", "Connector_Generic:Conn_02x06_Odd_Even",
            "Connector_IDC:IDC-Header_2x06_P2.54mm_Vertical", dict(PANEL_NETS),
            {"Note": "Pairs from west: RESET, OSD, USER (sig/GND), LED USER, DISK, POWER (cathode/anode)"}),
    "C1": ("47uF 16V", "Device:C_Polarized", "Capacitor_THT:CP_Radial_D5.0mm_P2.00mm",
           {"1": "USB_5V", "2": "GND"}, {}),
    "C2": ("100nF", "Device:C", "Capacitor_THT:C_Disc_D3.0mm_W1.6mm_P2.50mm",
           {"1": "USB_5V", "2": "GND"}, {}),
}

# The I/O Board holes are the mirror of the base holes (it sits on the base in the original
# stack). Both sets carry standoffs and can also fix the backplane to the case.
for _ref, (_val, _net) in PANEL_R.items():
    PARTS[_ref] = (_val, "Device:R", "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical",
                   {"1": "3V3", "2": _net}, {"Note": "1/4 W, mounted standing"})

HOLES = {}
_BASE_HOLES = [(HOLE_D[0], HOLE_E[0]), (HOLE_D[1], HOLE_E[0]), (HOLE_D[0], HOLE_E[1]), (HOLE_D[1], HOLE_E[1])]
for _i, (_d, _e) in enumerate(_BASE_HOLES):
    HOLES[f"H{1 + _i}"] = io(_d, _e) + ("I/O M3 standoff",)
for _i, (_d, _e) in enumerate(_BASE_HOLES):
    HOLES[f"H{5 + _i}"] = cy(_d, _e) + ("Cyclone M3 standoff",)
# Right section: next to the USB-A, the hub corner, and under the headers (cables are plugged there).
HOLES["H9"] = (164.0 + DX, 104.0, "Case M3")
HOLES["H10"] = (187.5 + DX, 22.5, "Case M3")
HOLES["H11"] = (186.5 + DX, 85.5, "Case M3")
HOLES["H12"] = (-0.5, 62.0, "Case M3")
for _ref, (_x, _y, _v) in HOLES.items():
    PARTS[_ref] = (_v, "Mechanical:MountingHole", "MountingHole:MountingHole_3.2mm_M3", {}, {})


def pad_targets():
    """Expected absolute pad centres for every connector that mates a QMTECH board."""
    t = {}
    for p in range(1, 41):
        t[("J1", str(p))] = io(*j12_de(p))
        t[("J2", str(p))] = cy(*j12_de(p))
        t[("J3", str(p))] = io(*j10_de(p))
        t[("J4", str(p))] = cy(*j10_de(p))
    for p in range(1, 5):
        t[("J5", str(p))] = cy(*jp6_de(p))
        t[("J6", str(p))] = io(*jp6_de(p))
    return t
