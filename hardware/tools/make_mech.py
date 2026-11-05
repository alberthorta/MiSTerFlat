"""Mechanical drawing for the case design: A3 pages, 1:1, ordinate dimensions from the rear-left corner.

Run with KiCad's python. Writes SVG pages to the scratch dir given as argv[1]; convert with rsvg-convert.
"""
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design as D  # noqa: E402

PCB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "RevA5", f"{D.PROJECT}.kicad_pcb")
OUT = sys.argv[1]
b = pcbnew.LoadBoard(PCB)
fps = {f.GetReference(): f for f in b.GetFootprints()}

X0 = min(p[0] for p in D.OUTLINE)       # origin: rear-left corner
Y0 = D.Y0
W = max(p[0] for p in D.OUTLINE) - X0
H = D.Y_FRONT - Y0
OX, OY = 95.0, 75.0                      # where the origin sits on the A3 page (mm)


def bx(x):
    return OX + x - X0


def by(y):
    return OY + y - Y0


def c(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def fab_box(ref):
    fp = fps[ref]
    xs, ys = [], []
    for g in fp.GraphicalItems():
        if isinstance(g, pcbnew.PCB_SHAPE) and g.GetLayer() == pcbnew.F_Fab:
            bb = g.GetBoundingBox()
            xs += [pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetRight())]
            ys += [pcbnew.ToMM(bb.GetY()), pcbnew.ToMM(bb.GetBottom())]
    return min(xs), min(ys), max(xs), max(ys)


class Page:
    def __init__(self, title, subtitle=None):
        self.e = []
        self.text(OX, 22, title, 6, weight="bold")
        self.text(OX, 30, subtitle or "MisterFlat backplane Rev A5 - scale 1:1 on A3 - all dimensions in mm - "
                  "origin (0, 0) = rear-left corner of the board, X to the right, Y towards the front",
                  3.2)

    def text(self, x, y, s, size=2.5, anchor="start", rot=0, weight="normal", fill="black"):
        tr = f' transform="rotate({rot} {x:.3f} {y:.3f})"' if rot else ""
        s = s.replace("&", "&amp;").replace("<", "&lt;")
        self.e.append(f'<text x="{x:.3f}" y="{y:.3f}" font-family="Helvetica" font-size="{size}" '
                      f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{tr}>{s}</text>')

    def line(self, x1, y1, x2, y2, w=0.18, color="black", dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.e.append(f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" '
                      f'stroke="{color}" stroke-width="{w}"{d}/>')

    def rect(self, x0, y0, x1, y1, w=0.2, color="black", fill="none", dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.e.append(f'<rect x="{bx(x0):.3f}" y="{by(y0):.3f}" width="{x1 - x0:.3f}" height="{y1 - y0:.3f}" '
                      f'stroke="{color}" stroke-width="{w}" fill="{fill}"{d}/>')

    def circle(self, x, y, r, w=0.2, color="black", fill="none"):
        self.e.append(f'<circle cx="{bx(x):.3f}" cy="{by(y):.3f}" r="{r:.3f}" stroke="{color}" '
                      f'stroke-width="{w}" fill="{fill}"/>')

    def board(self, color="black", w=0.35):
        pts = " ".join(f"{bx(x):.3f},{by(y):.3f}" for x, y in D.OUTLINE)
        self.e.append(f'<polygon points="{pts}" stroke="{color}" stroke-width="{w}" fill="none"/>')
        wx0, wy0, wx1, wy1 = D.WINDOW
        self.rect(wx0, wy0, wx1, wy1, w, color)

    @staticmethod
    def tiers(values, gap=2.8):
        """Put a label one step further out when it would touch the previous one on the same step."""
        last = {}
        out = []
        for v in sorted(set(round(x, 2) for x in values)):
            t = 0
            while t in last and v - last[t] < gap:
                t += 1
            last[t] = v
            out.append((v, t))
        return out

    def xdims(self, xs):
        """Ordinate X dimensions above the board (text reads from the board outwards)."""
        for x, t in self.tiers(xs):
            ly = OY - 6 - 12 * t
            self.line(bx(x), OY - 1, bx(x), ly + 1, 0.12, "#555")
            self.text(bx(x) + 0.9, ly, c(x - X0), 2.3, rot=-90)

    def ydims(self, ys):
        for y, t in self.tiers(ys):
            lx = OX - 6 - 14 * t
            self.line(OX - 1, by(y), lx + 1, by(y), 0.12, "#555")
            self.text(lx, by(y) + 0.8, c(y - Y0), 2.3, anchor="end")

    def arrow(self, x, y, ux, uy, color):
        """Arrow head with its tip at page point (x, y), pointing along the unit vector (ux, uy)."""
        L, Wd = 1.6, 0.5
        pts = [(x, y), (x - ux * L - uy * Wd, y - uy * L + ux * Wd), (x - ux * L + uy * Wd, y - uy * L - ux * Wd)]
        self.e.append('<polygon points="%s" fill="%s"/>' % (" ".join(f"{a:.3f},{b:.3f}" for a, b in pts), color))

    def hdim(self, x1, x2, y_from, y_dim, color="#1a5fb4", label=None):
        """Horizontal dimension between board X positions x1 and x2, drawn at board Y y_dim.
        y_from is the Y where each extension line starts (one value or a pair)."""
        y_from = y_from if isinstance(y_from, tuple) else (y_from, y_from)
        for x, yf in zip((x1, x2), y_from):
            self.line(bx(x), by(yf), bx(x), by(y_dim) + (0.8 if y_dim > yf else -0.8), 0.1, color)
        self.line(bx(x1), by(y_dim), bx(x2), by(y_dim), 0.15, color)
        self.arrow(bx(x1), by(y_dim), -1, 0, color)
        self.arrow(bx(x2), by(y_dim), 1, 0, color)
        self.text(bx((x1 + x2) / 2), by(y_dim) - 0.7, label or c(abs(x2 - x1)), 2.3, "middle", fill=color)

    def vdim(self, y1, y2, x_from, x_dim, color="#1a5fb4", label=None):
        x_from = x_from if isinstance(x_from, tuple) else (x_from, x_from)
        for y, xf in zip((y1, y2), x_from):
            self.line(bx(xf), by(y), bx(x_dim) + (0.8 if x_dim > xf else -0.8), by(y), 0.1, color)
        self.line(bx(x_dim), by(y1), bx(x_dim), by(y2), 0.15, color)
        self.arrow(bx(x_dim), by(y1), 0, -1, color)
        self.arrow(bx(x_dim), by(y2), 0, 1, color)
        self.text(bx(x_dim) - 0.7, by((y1 + y2) / 2), label or c(abs(y2 - y1)), 2.3, "middle",
                  rot=-90, fill=color)

    def holes(self):
        for ref, (x, y, v) in D.HOLES.items():
            self.circle(x, y, 1.6, 0.3)
            self.line(bx(x) - 2.4, by(y), bx(x) + 2.4, by(y), 0.08)
            self.line(bx(x), by(y) - 2.4, bx(x), by(y) + 2.4, 0.08)
            self.text(bx(x) + 2.2, by(y) - 2.0, ref, 2.4, weight="bold")

    def table(self, x, y, rows, widths, size=2.6):
        for r, row in enumerate(rows):
            cx = x
            for cell, wcol in zip(row, widths):
                self.text(cx, y + r * (size * 1.55), str(cell), size, weight="bold" if r == 0 else "normal")
                cx += wcol

    def save(self, name):
        with open(os.path.join(OUT, name), "w") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<svg xmlns="http://www.w3.org/2000/svg" width="420mm" height="297mm" viewBox="0 0 420 297">\n'
                    '<rect width="420" height="297" fill="white"/>\n' + "\n".join(self.e) + "\n</svg>\n")


# ---------- page 1: outline, holes, notches, window ----------
p = Page("1 - Board outline, holes, notches and FPGA window")
p.board()
p.holes()
hx = [x for x, _, _ in D.HOLES.values()]
hy = [y for _, y, _ in D.HOLES.values()]
p.xdims([x for x, _ in D.OUTLINE] + [D.WINDOW[0], D.WINDOW[2]] + hx)
p.ydims([y for _, y in D.OUTLINE] + [D.WINDOW[1], D.WINDOW[3]] + hy)


def R(x, y):
    return x + X0, y + Y0


XR, YF = X0 + W, D.Y_FRONT
# standoff hole columns, chained from the left edge, and the overall width
cols = sorted({x for ref, (x, y, v) in D.HOLES.items() if int(ref[1:]) <= 8})
chain = [X0] + cols + [XR]
starts = [D.NET_FRONT] + [D.HOLES["H2"][1]] * len(cols) + [D.NOTCH_DONGLE[1]]
for (xa, ya), (xb, yb) in zip(zip(chain, starts), zip(chain[1:], starts[1:])):
    p.hdim(xa, xb, (ya, yb), YF + 8)
p.hdim(X0, XR, (D.NET_FRONT, D.NOTCH_DONGLE[1]), YF + 16)
# standoff hole rows on the right side, and the overall depth
ry = sorted({D.HOLES["H7"][1], D.HOLES["H8"][1]})
hx7 = D.HOLES["H7"][0]
for ya, yb, xa, xb in ((Y0, ry[0], XR, hx7), (ry[0], ry[1], hx7, hx7), (ry[1], YF, hx7, D.NOTCH_DONGLE[0])):
    p.vdim(ya, yb, (xa, xb), XR + 8)
p.vdim(Y0, YF, (XR, D.NOTCH_DONGLE[0]), XR + 16)
# notch and window sizes
n = D.NOTCH_JP7
p.hdim(n[0], n[2], n[3], n[3] + 3)
p.vdim(Y0, n[3], n[2], n[2] + 3)
n = D.NOTCH_RJ45
p.hdim(n[0], n[2], n[1], n[1] - 3)
p.vdim(n[1], YF, n[2], n[2] + 3)
n = D.NOTCH_DONGLE
p.hdim(n[0], XR, n[1], n[1] + 5)
p.vdim(n[1], YF, n[0], n[0] + 5)
p.hdim(X0, D.X_LEFT, D.NET_FRONT, D.NET_FRONT + 5)
p.vdim(D.NET_FRONT, YF, D.X_LEFT, D.X_LEFT - 5)
w = D.WINDOW
p.hdim(w[0], w[2], w[3], w[3] + 4)
p.vdim(w[1], w[3], w[0], w[0] - 4)
p.text(bx((w[0] + w[2]) / 2), by((w[1] + w[3]) / 2), "FPGA window", 3, "middle")
p.text(bx(X0) + 4, by(Y0) + 52, "12 holes, all 3.2 mm (M3):", 2.6, weight="bold")
p.text(bx(X0) + 4, by(Y0) + 56, "H1-H8 board standoffs, H9-H12 case fixing", 2.6)
p.text(bx(X0) + 4, by(Y0) + 60, "Blue = distances between features", 2.6, fill="#1a5fb4")
p.text(bx(X0) + 4, by(Y0) + 64, "Black numbers outside = position from (0, 0)", 2.6)
rows = [["Feature", "X from", "X to", "Y from", "Y to"],
        ["Board envelope", 0, c(W), 0, c(H)],
        ["Power jack notch (rear)", c(D.NOTCH_JP7[0] - X0), c(D.NOTCH_JP7[2] - X0), 0, c(D.NOTCH_JP7[3] - Y0)],
        ["Cyclone RJ45 notch (front)", c(D.NOTCH_RJ45[0] - X0), c(D.NOTCH_RJ45[2] - X0), c(D.NOTCH_RJ45[1] - Y0), c(H)],
        ["Dongle notch (front-right)", c(D.NOTCH_DONGLE[0] - X0), c(W), c(D.NOTCH_DONGLE[1] - Y0), c(H)],
        ["Network column recess (front-left)", 0, c(D.X_LEFT - X0), c(D.NET_FRONT - Y0), c(H)],
        ["FPGA window (through hole)", c(D.WINDOW[0] - X0), c(D.WINDOW[2] - X0), c(D.WINDOW[1] - Y0), c(D.WINDOW[3] - Y0)]]
p.table(OX, by(YF) + 26, rows, [62, 22, 22, 22, 22])
rows = [["Hole", "X", "Y", "Use"]]
for ref in sorted(D.HOLES, key=lambda s: int(s[1:])):
    x, y, v = D.HOLES[ref]
    rows.append([ref, c(x - X0), c(y - Y0), v])
p.table(OX + 160, by(YF) + 26, rows, [14, 18, 18, 40], 2.4)
p.text(OX, by(YF) + 26 + 8 * 4.1, "Board thickness 1.6 mm. Inside corners of the cut-outs have the router radius (about 1 mm).", 2.6)
p.save("p1.svg")

# ---------- page 2: holes ----------
p = Page("2 - Mounting holes (all 3.2 mm, M3)")
p.board("#999", 0.25)
p.holes()
for x, y, v in D.HOLES.values():
    p.circle(x, y, 3.3, 0.12, "#999")
H_ = D.HOLES
for a, b in (("H3", "H1"), ("H1", "H5"), ("H5", "H7")):
    p.hdim(H_[a][0], H_[b][0], H_[a][1], Y0 + 9)
for a, b in (("H4", "H2"), ("H2", "H6"), ("H6", "H8")):
    p.hdim(H_[a][0], H_[b][0], H_[a][1], H_[a][1] - 9)
p.vdim(H_["H3"][1], H_["H4"][1], H_["H3"][0], H_["H3"][0] + 9)
p.vdim(H_["H7"][1], H_["H8"][1], H_["H7"][0], H_["H7"][0] - 9)
p.xdims([x for x, _, _ in D.HOLES.values()])
p.ydims([y for _, y, _ in D.HOLES.values()])
rows = [["Hole", "X", "Y", "Diameter", "Use"]]
for ref in sorted(D.HOLES, key=lambda s: int(s[1:])):
    x, y, v = D.HOLES[ref]
    rows.append([ref, c(x - X0), c(y - Y0), "3.2", v])
p.table(OX, by(D.Y_FRONT) + 14, rows, [16, 22, 22, 22, 60])
p.text(OX + 150, by(D.Y_FRONT) + 14, "Grey circle: 6.6 mm copper-free area around each hole", 2.6)
p.text(OX + 150, by(D.Y_FRONT) + 18, "(room for a 5.5 mm hex standoff or an M3 screw head).", 2.6)
p.text(OX + 150, by(D.Y_FRONT) + 24, "H1-H4 carry the I/O Board, H5-H8 the Cyclone (about 11 mm", 2.6)
p.text(OX + 150, by(D.Y_FRONT) + 28, "standoffs, to measure). All of them can also fix the board to the case.", 2.6)
p.save("p2.svg")

# ---------- page 3: connectors and openings ----------
p = Page("3 - Connectors on the backplane and panel openings")
p.board("#999", 0.25)
conn = [("J20", "Network out RJ45, faces rear", "rear"), ("J22", "Rear USB-A, faces rear", "rear"),
        ("J21", "Network in RJ45, faces front (recess)", "front"), ("J9", "Wi-Fi USB-A, faces front (dongle notch)", "front"),
        ("J23", "Rear USB cable header, 90 deg, pins to front", ""), ("J7", "AUX USB header, 90 deg, pins to right", ""),
        ("J8", "DISPLAY USB header, 90 deg, pins to right", ""), ("J24", "Buttons / LEDs header 2x6, vertical", ""),
        ("U1", "Adafruit 5997 hub on sockets", "")]
rows = [["Ref", "What", "X from", "X to", "Y from", "Y to", "Height above PCB"]]
height = {"J20": "~13 (check part)", "J21": "~13 (check part)", "J22": "~7", "J9": "~7", "J23": "~2.5 (pins) + plug",
          "J7": "~2.5 (pins) + plug", "J8": "~2.5 (pins) + plug", "J24": "~8.5 (pins) + plug", "U1": "~8.5 sockets + 1.6 + parts"}
for ref, what, side in conn:
    x0, y0, x1, y1 = fab_box(ref)
    p.rect(x0, y0, x1, y1, 0.3, "#1a5fb4")
    p.text(bx((x0 + x1) / 2), by((y0 + y1) / 2) + 1, ref, 2.6, "middle", weight="bold", fill="#1a5fb4")
    rows.append([ref, what, c(x0 - X0), c(x1 - X0), c(y0 - Y0), c(y1 - Y0), height[ref]])
for bxo, label in ((D.X0_IO, "I/O Board V2.1 (upright, ~11 mm above)"), (D.X0_CY, "Cyclone V (flipped, ~11 mm above)")):
    p.rect(bxo, D.Y0, bxo + D.BASE_W, D.Y_FRONT, 0.2, "#888", dash="2,1.5")
    p.text(bx(bxo + D.BASE_W / 2), by(D.Y0) + 8, label, 2.4, "middle", fill="#666")
p.xdims([v for ref, _, _ in conn for v in (fab_box(ref)[0], fab_box(ref)[2])])
p.ydims([v for ref, _, _ in conn for v in (fab_box(ref)[1], fab_box(ref)[3])])
p.table(OX - 60, by(D.Y_FRONT) + 14, rows, [12, 78, 18, 18, 18, 18, 40], 2.5)
p.save("p3.svg")

# ---------- page 4: board connectors that reach the panels, heights ----------
p = Page("4 - QMTECH board connectors at the panels and heights (estimates, measure on the real boards)")
p.board("#999", 0.25)
est = []
for name, (dd, ee) in (("Cyclone HDMI (rear)", ((0.0, 12.5), (22.0, 37.5))),
                       ("Cyclone power jack (rear)", (D.JP7_D, D.JP7_E)),
                       ("Cyclone RJ45 (front)", (D.RJ45_D, D.RJ45_E)),
                       ("Cyclone USB-A J13 (front, unused)", (D.J13_D, D.J13_E)),
                       ("Cyclone mini-USB UART J4 (front)", ((101.0, 106.91), (45.8, 56.9)))):
    a, bb2 = D.cy(dd[0], ee[0]), D.cy(dd[1], ee[1])
    x0, x1 = sorted((a[0], bb2[0]))
    y0, y1 = sorted((a[1], bb2[1]))
    p.rect(x0, y0, x1, y1, 0.3, "#c64600")
    est.append([name, c(x0 - X0), c(x1 - X0), c(y0 - Y0), c(y1 - Y0)])
rows = [["Connector (on the QMTECH board)", "X from", "X to", "Y from", "Y to"]] + est
p.table(OX, by(D.Y_FRONT) + 14, rows, [70, 20, 20, 20, 20], 2.6)
z = [["Height stack (Z, from the backplane top face)", "mm"],
     ["Backplane PCB thickness", "1.6"],
     ["Cyclone component face (flipped board) above backplane", "~11 (socket 8.5 + header 2.5), measure"],
     ["Cyclone PCB top (its back side) above backplane", "~12.6 + its bottom parts (~2)"],
     ["I/O Board PCB bottom above backplane", "~11, measure"],
     ["I/O Board parts on top", "unknown, measure"],
     ["Heatsink / fan below the backplane (through the window)", "unknown, measure"],
     ["Standoffs H1-H8", "= mated connector height (~11)"]]
p.table(OX + 150, by(D.Y_FRONT) + 14, z, [92, 70], 2.6)
p.text(OX, by(D.Y_FRONT) + 14 + 9 * 4.1 + 4,
       "Orange boxes: QMTECH board connector bodies from the QMTECH drawing (raster estimate, +-0.5 mm). "
       "The I/O Board V2.1 rear connectors (VGA, audio) are not known yet.", 2.5)
p.save("p4.svg")

# ---------- page 5: front panel board, seen from the front (button side) ----------
import build_panel as FP  # noqa: E402

X0, Y0 = FP.OX, FP.OY
OX, OY = 120.0, 95.0
p = Page("5 - Front panel board (buttons and LEDs) - drilling template for the case front",
         "MisterFlat front panel Rev A - scale 1:1 on A3 - all dimensions in mm - seen from the front "
         "(button side) - origin (0, 0) = top-left corner of the board")
p.e.append(f'<rect x="{OX:.3f}" y="{OY:.3f}" width="{FP.W}" height="{FP.H}" stroke="black" stroke-width="0.35" fill="none"/>')
bxs, bys = [], []
for ref, (x, y) in FP.HOLES.items():
    p.circle(X0 + x, Y0 + y, 1.6, 0.3)
    p.text(bx(X0 + x), by(Y0 + y) + 5.0, ref, 2.4, "middle", weight="bold")
    bxs.append(X0 + x)
    bys.append(Y0 + y)
btn_y = (FP.BTN_SIG_Y + FP.BTN_GND_Y) / 2
for k, cc in enumerate(FP.COLS):
    p.rect(X0 + cc - 3, Y0 + btn_y - 3, X0 + cc + 3, Y0 + btn_y + 3, 0.15, "#888", dash="1,0.8")
    p.circle(X0 + cc, Y0 + btn_y, 1.75, 0.3, "#1a5fb4")
    p.circle(X0 + cc, Y0 + FP.LED_Y, 1.5, 0.3, "#c64600")
    p.text(bx(X0 + cc), by(Y0 + btn_y) - 4.2, FP.BUTTONS[k], 2.4, "middle")
    p.text(bx(X0 + cc), by(Y0 + FP.LED_Y) + 4.6, FP.LEDS[k].replace("LED ", ""), 2.4, "middle")
    bxs.append(X0 + cc)
bys += [Y0 + btn_y, Y0 + FP.LED_Y]
p.xdims([X0, X0 + FP.W] + bxs)
p.ydims([Y0, Y0 + FP.H] + bys)
p.hdim(X0, X0 + FP.W, Y0 + FP.H, Y0 + FP.H + 8)
p.vdim(Y0, Y0 + FP.H, X0 + FP.W, X0 + FP.W + 8)
p.hdim(X0 + FP.COLS[0], X0 + FP.COLS[1], Y0 + FP.LED_Y, Y0 + FP.H + 4)
p.hdim(X0 + FP.COLS[1], X0 + FP.COLS[2], Y0 + FP.LED_Y, Y0 + FP.H + 4)
rows = [["Feature", "X", "Y", "Size", "Case front hole"],
        ["Board", f"0 .. {c(FP.W)}", f"0 .. {c(FP.H)}", "1.6 thick", ""]]
for ref, (x, y) in FP.HOLES.items():
    rows.append([f"{ref} mounting hole", c(x), c(y), "3.2 (M3)", "M3 standoff or boss"])
for k, cc in enumerate(FP.COLS):
    rows.append([f"Button {FP.BUTTONS[k]}", c(cc), c(btn_y), "6x6 body, 3.5 stem", "4.5-5 for the stem"])
for k, cc in enumerate(FP.COLS):
    rows.append([FP.LEDS[k], c(cc), c(FP.LED_Y), "3 mm LED", "3.2, or 5 with a clip"])
p.table(OX, OY + FP.H + 22, rows, [42, 20, 20, 36, 40], 2.6)
notes = ["Blue circle: button stem (13 mm above the PCB). Orange circle: LED body. Dashed: 6x6 button body.",
         "The board stands upright behind the case front wall, buttons and LEDs facing out.",
         "J1 (IDC 2x6) is on the back side, at the top: leave about 12 mm behind the board for the ribbon plug.",
         "Board-to-wall distance: about 13 mm minus the wall thickness, so the stems come out about 1 mm.",
         "Solder the LEDs with long legs so they reach the wall, or use a light pipe."]
for i, t in enumerate(notes):
    p.text(OX, OY + FP.H + 22 + len(rows) * 4.1 + 6 + i * 4.2, t, 2.6)
p.save("p5.svg")
print("pages written to", OUT)
