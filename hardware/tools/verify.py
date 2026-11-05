"""Independent checks on the generated board. Run with KiCad's python."""
import collections
import math
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design as D  # noqa: E402

PCB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "RevA5", f"{D.PROJECT}.kicad_pcb")
b = pcbnew.LoadBoard(PCB)
fps = {f.GetReference(): f for f in b.GetFootprints()}
fail = []


def pad(ref, num):
    return [p for p in fps[ref].Pads() if p.GetNumber() == num][0]


def xy(p):
    return (pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y))


# 1. Pin for pin: same net on both sides, equal to the QMTECH schematic table.
for a, c, table in (("J1", "J2", D.J12_NETS), ("J3", "J4", D.J10_NETS)):
    for n in range(1, 41):
        na, nc = pad(a, str(n)).GetNetname(), pad(c, str(n)).GetNetname()
        if not (na == nc == table[n]):
            fail.append(f"{a}/{c} pin {n}: {na} / {nc} / expected {table[n]}")
for n in range(1, 9):
    if not (pad("J20", str(n)).GetNetname() == pad("J21", str(n)).GetNetname() == D.ETH_NETS[n]):
        fail.append(f"J20/J21 pin {n}")
for i, (name, pin, kind) in enumerate(D.PANEL):
    q = 5 - i
    if pad("J24", str(2 * q + 1)).GetNetname() != pad("J4", str(pin)).GetNetname():
        fail.append(f"J24 {name}")
    r = pad(f"R{i + 1}", "1").GetNetname()
    if r != "3V3":
        fail.append(f"R{i + 1} not on 3V3")
for n, net in D.JP6_NETS.items():
    if pad("J5", str(n)).GetNetname() != net:
        fail.append(f"J5 pin {n}")
print("pin-for-pin J12/J10/JP6/RJ45/front panel nets:", "OK" if not fail else "FAIL")

# 2. Physical pad positions against the QMTECH-derived geometry.
worst = 0.0
for (ref, num), t in D.pad_targets().items():
    p = xy(pad(ref, num))
    worst = max(worst, math.hypot(p[0] - t[0], p[1] - t[1]))
print(f"pad position error vs QMTECH drawing: max {worst:.4f} mm")
if worst > 0.01:
    fail.append("pad positions")

# 3. Mirror symmetry: every J12/J10 pin N on the I/O side is the mirror of the Cyclone pin N.
sym = max(abs(xy(pad(a, str(n)))[0] - D.mirror_x(xy(pad(c, str(n)))[0])) + abs(xy(pad(a, str(n)))[1] - xy(pad(c, str(n)))[1])
          for a, c in (("J1", "J2"), ("J3", "J4"), ("J6", "J5")) for n in range(1, 41 if a != "J6" else 5))
print(f"mirror symmetry error: {sym:.4f} mm")

# 4. Copper connectivity of every net.
b.BuildConnectivity()
conn = b.GetConnectivity()
print("unrouted connections:", conn.GetUnconnectedCount(False))
if conn.GetUnconnectedCount(False):
    fail.append("unrouted")

# 5. Track lengths per net.
length = collections.defaultdict(float)
for t in b.GetTracks():
    if t.GetClass() == "PCB_TRACK":
        length[t.GetNetname()] += pcbnew.ToMM(t.GetLength())
print("USB pairs (mm, skew):")
for base in ("USB_UP", "USB_IO", "USB_DISP", "USB_WIFI", "USB_AUX"):
    lp, ln = length[base + "_D+"], length[base + "_D-"]
    print(f"  {base:9s} D+ {lp:7.2f}  D- {ln:7.2f}  skew {abs(lp - ln):5.2f}")
eth = {n: length[n] for n in D.ETH_NETS.values()}
print("Ethernet lines (mm):", ", ".join(f"{n} {v:.1f}" for n, v in eth.items()))
gpio = {n: length[n] for n in length if n.startswith("GPIO_1_")}
print(f"GPIO_1 bus: {len(gpio)} nets, length {min(gpio.values()):.1f} .. {max(gpio.values()):.1f} mm, "
      f"spread {max(gpio.values()) - min(gpio.values()):.1f} mm")
j12 = {n: length[n] for n in D.J12_NETS.values() if n in length and n not in ("VIN", "3V3", "GND")}
print(f"J12 signals: {len(j12)} nets, length {min(j12.values()):.1f} .. {max(j12.values()):.1f} mm")

# 6. Window and notches: nearest copper to their edges.
w = D.WINDOW
def dist_rect(p, r):
    dx = max(r[0] - p[0], 0, p[0] - r[2])
    dy = max(r[1] - p[1], 0, p[1] - r[3])
    return math.hypot(dx, dy)
near = min(min(dist_rect(xy(p), w) - pcbnew.ToMM(p.GetSize(pcbnew.F_Cu).x) / 2 for p in f.Pads())
           for f in b.GetFootprints() if f.GetReference() in ("J2", "J4"))
print(f"window {w[2] - w[0]:.1f} x {w[3] - w[1]:.1f} mm, nearest connector pad edge {near:.2f} mm")
# 7. Everything is mounted on the top side, like the two QMTECH boards.
bottom = [f.GetReference() for f in b.GetFootprints() if f.GetLayer() != pcbnew.F_Cu]
print("footprints on the bottom side:", bottom or "none")
if bottom:
    fail.append("bottom-side parts")

# 8. 90 deg headers: pins and a mated Dupont housing stay inside the right edge.
for ref in ("J7", "J8"):
    x1 = xy(pad(ref, "1"))[0]
    pins_end = pcbnew.ToMM(fps[ref].GetCourtyard(pcbnew.F_CrtYd).BBox().GetRight())
    plug_end = x1 + 4.04 + D.DUPONT_LEN
    print(f"{ref}: courtyard ends at x {pins_end:.2f}, mated housing at x {plug_end:.2f}, edge {D.X_RIGHT}")
    if max(pins_end, plug_end) > D.X_RIGHT:
        fail.append(f"{ref} overhangs")
# Front panel board: every J1 pin must do the same job as the J24 pin it is cabled to (pin N to pin N).
PANEL_PCB = os.path.join(os.path.dirname(PCB), "..", "PanelRevA", "MisterFlat_Panel_RevA.kicad_pcb")
if os.path.exists(PANEL_PCB):
    pb = pcbnew.LoadBoard(PANEL_PCB)
    pf = {f.GetReference(): f for f in pb.GetFootprints()}
    j1 = {p.GetNumber(): p.GetNetname() for p in pf["J1"].Pads()}
    job = {}                                    # net on the panel -> what it must be on J24
    for i, (name, pin, kind) in enumerate(D.PANEL):
        q = 5 - i
        sig, other = str(2 * q + 1), str(2 * q + 2)
        ref = [f for f in pf.values() if f.GetValue() == name][0]
        if kind == "btn":
            job[sig] = (D.J10_NETS[pin], {p.GetNetname() for p in ref.Pads() if p.GetNumber() == "1"})
            job[other] = ("GND", {"GND"})
        else:
            job[sig] = (D.J10_NETS[pin], {p.GetNetname() for p in ref.Pads() if p.GetNumber() == "1"})
            # anode: on J24 this pin is the 1k resistor output
            job[other] = (D.PANEL_NETS[other], {p.GetNetname() for p in ref.Pads() if p.GetNumber() == "2"})
    bad = [n for n, (j24net, panel) in job.items() if D.PANEL_NETS[n] != j24net or j1[n] not in panel]
    print("front panel J1 vs J24:", "OK" if not bad else f"MISMATCH on pins {bad}")
    if bad:
        fail.append("front panel pinout")

print("RESULT:", "PASS" if not fail else "FAIL " + "; ".join(fail))
