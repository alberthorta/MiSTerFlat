"""Generate RevA5/MisterFlat_RevA5.kicad_pcb and the project footprint. Run with KiCad's python."""
import math
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design as D  # noqa: E402
import build_sch  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "RevA5")
LIB = os.path.join(OUT, "lib", "MisterFlat.pretty")
MM = pcbnew.FromMM


def V(x, y):
    return pcbnew.VECTOR2I(MM(x), MM(y))


# --------------------------------------------------------------------------
# Project footprint: Adafruit 5997 on female sockets
# --------------------------------------------------------------------------
def hub_pads():
    """pad name -> (x, y) relative to the module centre, from the Adafruit Eagle board."""
    p = {}
    host = [("VBUS", 3.81), ("UP_D+", 1.27), ("UP_D-", -1.27), ("GND", -3.81)]
    for n, x in host:
        p.setdefault(n, []).append((x, 12.7))
    cols = {1: (-7.62, -8.89), 2: (7.62, -8.89), 3: (-7.62, 1.27), 4: (7.62, 1.27)}
    for port, (x, y1) in cols.items():
        for i, n in enumerate(["VBUS", f"P{port}_D+", f"P{port}_D-", "GND"]):
            p.setdefault(n, []).append((x, y1 + 2.54 * i))
    return p


def add_line(fp_or_board, layer, a, b, w):
    s = pcbnew.PCB_SHAPE(fp_or_board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(V(*a))
    s.SetEnd(V(*b))
    s.SetLayer(layer)
    s.SetWidth(MM(w))
    fp_or_board.Add(s)
    return s


def add_rect(parent, layer, x0, y0, x1, y1, w):
    for a, b in [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]:
        add_line(parent, layer, a, b, w)


def add_text(parent, layer, txt, x, y, size=1.0, thick=0.15, angle=0, fp_text=False):
    t = pcbnew.PCB_TEXT(parent)
    t.SetText(txt)
    t.SetPosition(V(x, y))
    t.SetLayer(layer)
    t.SetTextSize(V(size, size))
    t.SetTextThickness(MM(thick))
    if angle:
        t.SetTextAngleDegrees(angle)
    if layer == pcbnew.B_SilkS:
        t.SetMirrored(True)
    parent.Add(t)
    return t


def build_hub_footprint():
    fp = pcbnew.FOOTPRINT(None)
    fp.SetFPID(pcbnew.LIB_ID("MisterFlat", "Adafruit_5997_CH334F_Socketed"))
    fp.SetLibDescription("Adafruit #5997 CH334F 4-port USB hub breakout (20.32 x 30.48 mm) on 2x 1x8 + 1x4 "
                         "2.54 mm female sockets. Pad map from the official Eagle board. "
                         "All 5V pads are one net on the module, all GND pads too.")
    fp.SetKeywords("Adafruit 5997 CH334F USB hub")
    fp.SetAttributes(pcbnew.FP_THROUGH_HOLE)
    fp.SetDuplicatePadNumbersAreJumpers(True)
    for name, pts in hub_pads().items():
        for (x, y) in pts:
            pad = pcbnew.PAD(fp)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            sq = name == "VBUS"
            pad.SetShape(pcbnew.PAD_SHAPE_RECT if sq else pcbnew.PAD_SHAPE_CIRCLE)
            pad.SetSize(V(1.7, 1.7))
            pad.SetDrillSize(V(1.0, 1.0))
            pad.SetLayerSet(pad.PTHMask())
            pad.SetNumber(name)
            pad.SetFPRelativePosition(V(x, y))
            fp.Add(pad)
    add_rect(fp, pcbnew.F_Fab, -10.16, -15.24, 10.16, 15.24, 0.1)
    add_rect(fp, pcbnew.F_Fab, -4.5, -15.24 - 1.0, 4.5, -15.24 + 6.5, 0.1)   # USB-C receptacle (unused)
    add_rect(fp, pcbnew.F_SilkS, -10.3, -15.4, 10.3, 15.4, 0.12)
    # Courtyard follows the real module outline (2.54 mm corner radius) plus the USB-C overhang,
    # so a case screw fits at the corner.
    crt = []
    r = 2.54 + 0.25
    for cx, cy_, a0 in ((7.62, 12.7, 0), (-7.62, 12.7, 90), (-7.62, -12.7, 180), (7.62, -12.7, 270)):
        for i in range(9):
            a = math.radians(a0 + 90 * i / 8)
            crt.append((cx + r * math.cos(a), cy_ + r * math.sin(a)))
        if a0 == 180:
            crt += [(-4.75, -15.49), (-4.75, -16.5), (4.75, -16.5), (4.75, -15.49)]
    poly = pcbnew.PCB_SHAPE(fp)
    poly.SetShape(pcbnew.SHAPE_T_POLY)
    poly.SetPolyPoints([V(x, y) for x, y in crt])
    poly.SetLayer(pcbnew.F_CrtYd)
    poly.SetWidth(MM(0.05))
    poly.SetFilled(False)
    fp.Add(poly)
    for txt, x, y in [("HOST", 0, 10.9), ("P1", -5.4, -5.1), ("P2", 5.4, -5.1), ("P3", -5.4, 5.1),
                      ("P4", 5.4, 5.1), ("ADAFRUIT 5997", 0, -1.0)]:
        add_text(fp, pcbnew.F_SilkS, txt, x, y, 0.8, 0.12)
    ref = fp.Reference()
    ref.SetPosition(V(0, -17.3))
    ref.SetTextSize(V(1, 1))
    fp.Value().SetPosition(V(0, 1.0))
    fp.Value().SetLayer(pcbnew.F_Fab)
    sock = "${KICAD10_3DMODEL_DIR}/Connector_PinSocket_2.54mm.3dshapes/PinSocket_1x%02d_P2.54mm_Vertical.step"
    for n, (ox, oy), rot in ((8, (-7.62, 8.89), 0), (8, (7.62, 8.89), 0), (4, (3.81, -12.7), 90)):
        m = pcbnew.FP_3DMODEL()
        m.m_Filename = sock % n
        m.m_Offset = pcbnew.VECTOR3D(ox, oy, 0)
        m.m_Rotation = pcbnew.VECTOR3D(0, 0, rot)
        fp.Models().push_back(m)
    os.makedirs(LIB, exist_ok=True)
    io = pcbnew.PCB_IO_MGR.FindPlugin(pcbnew.PCB_IO_MGR.KICAD_SEXP)
    io.FootprintSave(LIB, fp)


# --------------------------------------------------------------------------
# Geometry helpers for routing
# --------------------------------------------------------------------------
def chamfer(pts, c):
    if c <= 0 or len(pts) < 3:
        return list(pts)
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, b, n = pts[i - 1], pts[i], pts[i + 1]
        d1 = (b[0] - a[0], b[1] - a[1])
        d2 = (n[0] - b[0], n[1] - b[1])
        l1, l2 = math.hypot(*d1), math.hypot(*d2)
        dot = (d1[0] * d2[0] + d1[1] * d2[1]) / (l1 * l2)
        if abs(dot) > 0.01:          # only square corners get a chamfer
            out.append(b)
            continue
        cc = min(c, 0.45 * l1, 0.45 * l2)
        out.append((b[0] - d1[0] / l1 * cc, b[1] - d1[1] / l1 * cc))
        out.append((b[0] + d2[0] / l2 * cc, b[1] + d2[1] / l2 * cc))
    out.append(pts[-1])
    return out


def offset(pts, d):
    """Offset a polyline to its left-hand side (travel direction, y down) by d."""
    def normal(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        l = math.hypot(dx, dy)
        return (dy / l, -dx / l)
    out = []
    for i, p in enumerate(pts):
        if i == 0:
            n = normal(pts[0], pts[1])
            out.append((p[0] + n[0] * d, p[1] + n[1] * d))
        elif i == len(pts) - 1:
            n = normal(pts[-2], pts[-1])
            out.append((p[0] + n[0] * d, p[1] + n[1] * d))
        else:
            n1, n2 = normal(pts[i - 1], p), normal(p, pts[i + 1])
            m = (n1[0] + n2[0], n1[1] + n2[1])
            k = d / (1 + n1[0] * n2[0] + n1[1] * n2[1])
            out.append((p[0] + m[0] * k, p[1] + m[1] * k))
    return out


class Router:
    def __init__(self, board, nets):
        self.b = board
        self.nets = nets
        self.segments = []      # (a, b, width, layer) for the stitching check

    def track(self, pts, width, layer, net, cham=0.0):
        clean = [pts[0]]
        for p in pts[1:]:
            if math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 1e-4:
                clean.append(p)
        pts = chamfer(clean, cham) if cham else clean
        for a, b in zip(pts, pts[1:]):
            if math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-4:
                continue
            t = pcbnew.PCB_TRACK(self.b)
            t.SetStart(V(*a))
            t.SetEnd(V(*b))
            t.SetWidth(MM(width))
            t.SetLayer(layer)
            t.SetNet(self.nets[net])
            self.b.Add(t)
            self.segments.append((a, b, width, layer))

    def via(self, x, y, net, size=0.6, drill=0.3):
        v = pcbnew.PCB_VIA(self.b)
        v.SetPosition(V(x, y))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetDrill(MM(drill))
        v.SetWidth(pcbnew.F_Cu, MM(size))
        v.SetNet(self.nets[net])
        self.b.Add(v)
        self.segments.append(((x, y), (x, y), size, None))

    def pair(self, center, layer, left_net, right_net, w=0.30, gap=0.18, cham=1.0,
             start_bk=None, end_bk=None):
        """start_bk/end_bk: {net: [points from the offset end towards the pad]}"""
        c = chamfer(center, cham)
        s = (w + gap) / 2
        for net, d in ((left_net, s), (right_net, -s)):
            body = offset(c, d)
            pts = list(body)
            if start_bk and net in start_bk:
                pts = list(reversed(start_bk[net](body[0]))) + pts[1:]
            if end_bk and net in end_bk:
                pts = pts[:-1] + end_bk[net](body[-1])
            self.track(pts, w, layer, net)


def bk_axis(pad, axis, extra=None):
    """Breakout from an offset end point to a pad: one 45 deg segment, then straight into the pad."""
    def f(p):
        dx, dy = pad[0] - p[0], pad[1] - p[1]
        if axis == "y":
            r = (pad[0], p[1] + math.copysign(abs(dx), dy))
        else:
            r = (p[0] + math.copysign(abs(dy), dx), pad[1])
        pts = [p] + (extra or []) + [r, pad]
        return pts
    return f


def bk_path(*pts):
    """Fixed breakout: offset end point, then the given points, ending on the pad."""
    return lambda p: [p] + list(pts)


# --------------------------------------------------------------------------
# Board
# --------------------------------------------------------------------------
def place(board, nets, ref, sym_uuid):
    value, sym, fpid, pinnets, fields = D.PARTS[ref]
    lib, name = fpid.split(":")
    path = LIB if lib == "MisterFlat" else os.path.join(D.KICAD_FP, lib + ".pretty")
    fp = pcbnew.FootprintLoad(path, name)
    assert fp, fpid
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    fp.SetReference(ref)
    fp.SetValue(value)
    fp.SetPath(pcbnew.KIID_PATH(f"/{sym_uuid}"))
    fp.SetSheetname("/")
    fp.SetSheetfile(f"{D.PROJECT}.kicad_sch")
    board.Add(fp)
    fp.SetField("Datasheet", "~")
    for k, v in fields.items():
        fp.SetField(k, v)
        fp.GetField(k).SetVisible(False)
    for pad in fp.Pads():
        n = pad.GetNumber()
        if n in pinnets:
            pad.SetNet(nets[pinnets[n]])
        elif n:
            raise SystemExit(f"{ref} pad {n} has no net")
    return fp


def pad_xy(fp, num):
    pads = [p for p in fp.Pads() if p.GetNumber() == num]
    p = pads[0].GetPosition()
    return (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))


def solve_orientation(fp, ref, targets):
    """Find the rotation that puts every pad on its QMTECH-derived position."""
    pin1 = targets[(ref, "1")]
    for rot in (0, 90, 180, 270):
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(V(0, 0))
        p1 = pad_xy(fp, "1")
        fp.SetPosition(V(pin1[0] - p1[0], pin1[1] - p1[1]))
        err = max(math.hypot(pad_xy(fp, n)[0] - t[0], pad_xy(fp, n)[1] - t[1])
                  for (r, n), t in targets.items() if r == ref)
        if err < 0.01:
            return rot
    raise SystemExit(f"{ref}: no rotation matches the QMTECH pin geometry")


def build():
    build_hub_footprint()
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    tb = board.GetTitleBlock()
    tb.SetTitle("QMTECH MiSTer flat backplane")
    tb.SetRevision(D.REV)
    tb.SetDate("2026-10-09")
    tb.SetCompany("PROTOTYPE - NOT VALIDATED - DO NOT FABRICATE")
    tb.SetComment(0, "I/O Board V2.1 left (upright), Cyclone V SoC right (flipped)")
    tb.SetComment(1, "Generated by tools/build_pcb.py from tools/design.py")

    # Drill/place origin at the rear-left corner of the board: used for the STEP and mechanical exports.
    board.GetDesignSettings().SetAuxOrigin(V(min(p[0] for p in D.OUTLINE), D.Y0))

    netnames = sorted({n for p in D.PARTS.values() for n in p[3].values()})
    nets = {}
    for n in netnames:
        ni = pcbnew.NETINFO_ITEM(board, n)
        board.Add(ni)
        nets[n] = ni

    targets = D.pad_targets()
    fps = {}
    for ref in D.PARTS:
        fps[ref] = place(board, nets, ref, build_sch.uid("sym", ref))
    for ref in ("J1", "J2", "J3", "J4", "J5", "J6"):
        rot = solve_orientation(fps[ref], ref, targets)
        print(f"{ref}: rotation {rot}")
    fps["U1"].SetPosition(V(*D.HUB_C))
    fps["J7"].SetPosition(V(*D.AUX_PIN1))
    fps["J8"].SetPosition(V(*D.DISP_PIN1))

    # USB-A: front face on the dongle notch edge (+0.5 mm overhang).
    j9 = fps["J9"]
    face = max(max(pcbnew.ToMM(g.GetStart().y), pcbnew.ToMM(g.GetEnd().y)) for g in j9.GraphicalItems()
               if isinstance(g, pcbnew.PCB_SHAPE) and g.GetLayer() == pcbnew.F_Fab)
    yp = round(D.NOTCH_DONGLE[1] + 0.5 - face, 3)
    j9.SetPosition(V(D.USBA_PIN1_X, yp))
    print("J9 pin row y =", yp, "front face offset", face)

    place_net_jacks(fps)
    place_rear_usb(fps)
    place_panel(fps)

    fps["C1"].SetPosition(V(D.sx(171.5), 86.0))     # electrolytic, pad 1 (+) west
    fps["C2"].SetPosition(V(D.sx(178.0), 86.0))
    for ref, (x, y, _) in D.HOLES.items():
        fps[ref].SetPosition(V(x, y))

    for fp in fps.values():
        for item in [fp.Reference(), fp.Value()]:
            item.SetTextSize(V(1.0, 1.0))
            item.SetTextThickness(MM(0.15))
        fp.Value().SetVisible(False)
    ref_pos = {"J1": (85.8, 95.6), "J2": (D.sx(96.4), 95.6), "J3": (22.8, 95.6), "J4": (D.sx(159.4), 95.6),
               "J5": (D.sx(100.2), 116.0), "J6": (81.6, 116.0), "J9": (D.sx(178.0), 101.0),
               "C1": (D.sx(172.5), 82.6), "C2": (D.sx(179.25), 84.0), "U1": (D.sx(176.5), 23.4),
               "J22": (D.REAR_USB_X, 26.0), "J24": (D.GAP_C + 8.92, 113.4)}
    for ref, (x, y) in ref_pos.items():
        fps[ref].Reference().SetPosition(V(x, y))
        fps[ref].Reference().SetTextAngleDegrees(0)
    for ref in list(D.HOLES) + ["J7", "J8", "J23"] + list(D.PANEL_R):
        fps[ref].Reference().SetVisible(False)

    # --- outline and window ---
    o = D.OUTLINE
    for a, b in zip(o, o[1:] + o[:1]):
        add_line(board, pcbnew.Edge_Cuts, a, b, 0.1)
    add_rect(board, pcbnew.Edge_Cuts, *D.WINDOW, 0.1)

    r = Router(board, nets)
    route_j12(r)
    spread = route_j10(r)
    route_usb(r, fps, yp)
    route_eth(r, fps)
    route_rear_usb(r, fps)
    route_panel(r, fps, spread)
    add_zones(board, nets)
    add_keepouts(board)
    stitch(r, board, fps)
    add_drawings(board, yp, fps)

    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    path = os.path.join(OUT, f"{D.PROJECT}.kicad_pcb")
    pcbnew.SaveBoard(path, board)
    print("saved", path, "tracks", len(board.GetTracks()))


# --------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------
TRACE = 0.2
POWER_W = 0.5
CLR = 0.2


def route_j12(r):
    io_odd, io_even = D.io(*D.j12_de(1))[0], D.io(*D.j12_de(2))[0]
    cy_odd, cy_even = D.cy(*D.j12_de(1))[0], D.cy(*D.j12_de(2))[0]
    for row in range(20):
        y = D.Y0 + D.D_PIN1 + D.PITCH * row
        odd, even = 2 * row + 1, 2 * row + 2
        ne, no = D.J12_NETS[even], D.J12_NETS[odd]
        if ne != "GND":
            r.track([(io_even, y), (cy_even, y)], 0.25, pcbnew.F_Cu, ne)
        lane = [(io_odd, y), (io_odd + 1.27, y + 1.27), (cy_odd - 1.27, y + 1.27), (cy_odd, y)]
        if no in ("VIN", "3V3"):
            r.track(lane, 0.4, pcbnew.B_Cu, no)
            r.track(lane, 0.4, pcbnew.F_Cu, no)
        else:
            r.track(lane, 0.25, pcbnew.B_Cu, no)


def route_j10(r):
    cy_odd = D.cy(*D.j10_de(1))[0]
    cy_even = D.cy(*D.j10_de(2))[0]
    m = D.mirror_x
    spread = {}
    xr = cy_odd - 0.85 - CLR - TRACE / 2 - 0.05      # right-most corridor track
    groups = {
        ("front", pcbnew.F_Cu): (list(range(0, 10)), 93.0, +1),
        ("front", pcbnew.B_Cu): (list(range(0, 10)), 93.6, +1),
        ("rear", pcbnew.F_Cu): (list(range(19, 9, -1)), 41.9, -1),
        ("rear", pcbnew.B_Cu): (list(range(19, 9, -1)), 41.9, -1),
    }
    for (side, layer), (rows, lane0, sgn) in groups.items():
        items = []
        for k in rows:
            pin = 2 * k + 1 if layer == pcbnew.F_Cu else 2 * k + 2
            net = D.J10_NETS[pin]
            if net == "GND":
                continue
            items.append((k, pin, net, POWER_W if net in ("J10_VIN", "J10_3V3") else TRACE))
        # corridor x: first item is the right-most
        xs, x, prev_w = [], xr, None
        for (_, _, _, w) in items:
            if prev_w is not None:
                x -= prev_w / 2 + CLR + w / 2
            xs.append(x)
            prev_w = w
        # lanes: the left-most vertical takes the lane nearest the window
        lanes, y, prev_w = {}, lane0, None
        for idx in range(len(items) - 1, -1, -1):
            w = items[idx][3]
            if prev_w is not None:
                y += sgn * (prev_w / 2 + CLR + w / 2)
            lanes[idx] = y
            prev_w = w
        n = len(items)
        for idx, (k, pin, net, w) in enumerate(items):
            yk = D.Y0 + D.j10_de(pin)[0]
            xc, ly = xs[idx], lanes[idx]
            run = [(xc, ly), (m(xc), ly)]
            if side == "front":
                # In the gap between the boards the lanes open to a 1.2 mm pitch (B lanes sit halfway
                # between F lanes), so the front panel signals can drop to In2 through a via.
                west, f_east, b_east = D.GAP_SPREAD
                east = f_east if layer == pcbnew.F_Cu else b_east
                ys = lane0 + 1.2 * (n - 1 - idx)
                dy = ys - ly
                run = [(xc, ly), (east + dy, ly), (east, ys), (west, ys), (west - dy, ly), (m(xc), ly)]
                spread[net] = ys
            if layer == pcbnew.F_Cu:
                pts = [(cy_odd, yk), (xc, yk)] + run + [(m(xc), yk), (m(cy_odd), yk)]
            else:
                yj = yk + sgn * 1.27
                pts = [(cy_even, yk), (cy_even - 1.27, yj), (xc, yj)] + run + [
                       (m(xc), yj), (m(cy_even - 1.27), yj), (m(cy_even), yk)]
            r.track(pts, w, layer, net, cham=0.4)
    return spread


def route_usb(r, fps, yp):
    U = fps["U1"]
    hub = lambda n: pad_xy(U, n)  # noqa: E731
    j5 = lambda n: pad_xy(fps["J5"], n)  # noqa: E731
    j6 = lambda n: pad_xy(fps["J6"], n)  # noqa: E731
    j9 = lambda n: pad_xy(fps["J9"], n)  # noqa: E731
    F, B = pcbnew.F_Cu, pcbnew.B_Cu

    # Upstream: Cyclone JP6 -> hub USBHOST, bottom layer. Left net when travelling to the hub: D-.
    dm, dp = j5("1"), j5("3")
    S = D.sx
    r.pair([(S(99.2), 119.3), (S(100.9), 119.3), (S(100.9), 99.1), (S(165.2), 99.1), (S(165.2), 84.0),
            (S(176.5), 84.0), (S(176.5), 57.0)], B, "USB_UP_D-", "USB_UP_D+",
           start_bk={"USB_UP_D-": bk_axis(dm, "y"),
                     "USB_UP_D+": lambda p: [p, (dp[0] + p[1] - (dp[1] + 1.39), p[1]), (dp[0], dp[1] + 1.39), dp]},
           end_bk={"USB_UP_D-": bk_axis(hub("UP_D-"), "y"), "USB_UP_D+": bk_axis(hub("UP_D+"), "y")})

    # Port 1 -> I/O Board (J6), top layer. Left net when travelling to the I/O: D-.
    p1p, p1m = hub("P1_D+"), hub("P1_D-")
    jm, jp = j6("1"), j6("3")
    xm = (jm[0] + jp[0]) / 2
    # Ends heading west under the J6 data row: D+ peels off first, D- goes on to pin 1.
    # Kept above y = 119.3 so it stays clear of the I/O front standoff keepout.
    r.pair([(S(166.9), 36.16), (S(164.2), 36.16), (S(164.2), 98.8), (S(102.0), 98.8), (S(102.0), 105.6),
            (90.6, 105.6), (90.6, 118.9),
            (jp[0] + 1.15, 118.9)], F, "USB_IO_D-", "USB_IO_D+",
           start_bk={"USB_IO_D-": bk_axis(p1m, "x"), "USB_IO_D+": bk_axis(p1p, "x")},
           end_bk={"USB_IO_D+": bk_axis(jp, "y"),
                   "USB_IO_D-": lambda p: [p, (jm[0] + (p[1] - jm[1]) - 1.0, p[1]),
                                           (jm[0], jm[1] + 1.0), jm]})

    # Port 3 -> Wi-Fi USB-A, top layer. Left net when travelling to the USB-A: D+.
    p3p, p3m = hub("P3_D+"), hub("P3_D-")
    xa = (j9("2")[0] + j9("3")[0]) / 2
    r.pair([(S(170.785), 49.0), (S(170.785), 58.0), (S(167.0), 58.0), (S(167.0), 89.5), (xa, 89.5), (xa, yp - 2.2)],
           F, "USB_WIFI_D+", "USB_WIFI_D-",
           start_bk={"USB_WIFI_D-": bk_axis(p3m, "x"),
                     "USB_WIFI_D+": lambda p: [p, (p[0], p3p[1] + p[0] - S(169.8)), (S(169.8), p3p[1]), p3p]},
           end_bk={"USB_WIFI_D-": bk_axis(j9("2"), "y"), "USB_WIFI_D+": bk_axis(j9("3"), "y")})

    # Port 4 -> AUX header (J7), top layer, enters the pins from the east.
    p4p, p4m = hub("P4_D+"), hub("P4_D-")
    a_m, a_p = pad_xy(fps["J7"], "2"), pad_xy(fps["J7"], "3")
    ya = (a_m[1] + a_p[1]) / 2
    r.pair([(S(186.2), 49.2), (S(186.2), ya), (a_m[0] + 2.3, ya)], F, "USB_AUX_D+", "USB_AUX_D-",
           start_bk={"USB_AUX_D-": bk_axis(p4m, "x"),
                     "USB_AUX_D+": bk_path((S(186.44), 46.49), (S(185.0), p4p[1]), p4p)},
           end_bk={"USB_AUX_D-": bk_axis(a_m, "x"), "USB_AUX_D+": bk_axis(a_p, "x")})

    # Port 2 -> DISPLAY header (J8), top layer, outer lane.
    p2p, p2m = hub("P2_D+"), hub("P2_D-")
    d_m, d_p = pad_xy(fps["J8"], "2"), pad_xy(fps["J8"], "3")
    yd = (d_m[1] + d_p[1]) / 2
    r.pair([(S(187.9), 39.4), (S(187.9), yd), (d_m[0] + 2.3, yd)], F, "USB_DISP_D+", "USB_DISP_D-",
           start_bk={"USB_DISP_D-": bk_path((S(187.66), 38.89), (S(186.2), p2m[1]), p2m),
                     "USB_DISP_D+": bk_path((S(188.14), 36.58), (S(186.45), p2p[1]), p2p)},
           end_bk={"USB_DISP_D-": bk_axis(d_m, "x"), "USB_DISP_D+": bk_axis(d_p, "x")})

    # USB_5V (JP6 pin 2) to the hub, the I/O USB header, the headers and the USB-A.
    v5 = j5("2")
    hub_v = hub_vbus(U)
    r.track([v5, (v5[0], 97.9), (S(163.4), 97.9), (S(163.4), hub_v["P1"][1]), hub_v["P1"]], 0.8, B, "USB_5V", cham=0.6)
    # link to the I/O USB header above the front panel resistors (they need this space)
    r.track([(v5[0], 106.0), (j6("2")[0], 106.0), j6("2")], 0.8, B, "USB_5V", cham=0.6)
    tx = S(182.2)
    r.track([hub_v["P4"], (tx, hub_v["P4"][1]), (tx, 92.0), (j9("1")[0], 92.0), j9("1")], 0.6, B, "USB_5V", cham=0.6)
    # 5V to the header pin 1: via on the bottom trunk, then top layer (the upstream pair
    # runs on the bottom layer between the trunk and the headers).
    for ref in ("J7", "J8"):
        p = pad_xy(fps[ref], "1")
        r.via(tx, p[1], "USB_5V")
        r.track([(tx, p[1]), p], 0.6, F, "USB_5V")
    # bulk capacitors above the USB-A
    c1p, c1g = pad_xy(fps["C1"], "1"), pad_xy(fps["C1"], "2")
    c2p, c2g = pad_xy(fps["C2"], "1"), pad_xy(fps["C2"], "2")
    # through-hole: + pads join the bottom 5V trunk, - pads go to the GND planes
    r.track([c1p, (c1p[0], 92.0), (j9("1")[0], 92.0)], 0.6, B, "USB_5V")
    r.track([c2p, (c2p[0], 92.0)], 0.6, B, "USB_5V")


def fab_max_y(fp):
    """Mouth of a horizontal jack: largest local y of its F.Fab drawing (footprint at the origin)."""
    return max(max(pcbnew.ToMM(g.GetStart().y), pcbnew.ToMM(g.GetEnd().y)) for g in fp.GraphicalItems()
               if isinstance(g, pcbnew.PCB_SHAPE) and g.GetLayer() == pcbnew.F_Fab)


def place_rel(fp, rot, pin1, want):
    """Rotate, put pad 1 on pin1, then check pad offsets {num: (dx, dy)} relative to pad 1."""
    fp.SetOrientationDegrees(rot)
    fp.SetPosition(V(0, 0))
    p1 = pad_xy(fp, "1")
    fp.SetPosition(V(pin1[0] - p1[0], pin1[1] - p1[1]))
    for n, (dx, dy) in want.items():
        p = pad_xy(fp, n)
        if math.hypot(p[0] - pin1[0] - dx, p[1] - pin1[1] - dy) > 0.01:
            return False
    return True


def place_net_jacks(fps):
    """J20: mouth to the rear edge. J21: mouth to the front (column front edge)."""
    j20, j21 = fps["J20"], fps["J21"]
    j20.SetOrientationDegrees(0)
    j20.SetPosition(V(0, 0))
    mouth = fab_max_y(j20)
    pin1 = (D.NET_REAR_PIN1_X, D.Y0 + mouth)
    assert place_rel(j20, 180, pin1, {"3": (-2.54, 0), "2": (-1.27, 2.54)}), "J20 orientation"
    pin1_f = (D.NET_FRONT_PIN1_X, D.NET_FRONT - mouth)
    assert place_rel(j21, 0, pin1_f, {"3": (2.54, 0), "2": (1.27, -2.54)}), "J21 orientation"
    print(f"J20 pin 1 {pin1}, J21 pin 1 {pin1_f}")


def place_rear_usb(fps):
    """J22 USB-A faces the rear between the two rear standoffs. J23, a 90 deg 1x4 header, sits right
    behind it with the pins facing the front. Same pin order as the USB-A: VIN, D-, D+, GND from east."""
    j22, j23 = fps["J22"], fps["J23"]
    j22.SetOrientationDegrees(0)
    j22.SetPosition(V(0, 0))
    shapes = [g for g in j22.GraphicalItems() if isinstance(g, pcbnew.PCB_SHAPE) and g.GetLayer() == pcbnew.F_Fab]
    face = max(max(pcbnew.ToMM(g.GetStart().y), pcbnew.ToMM(g.GetEnd().y)) for g in shapes)
    back = min(min(pcbnew.ToMM(g.GetStart().y), pcbnew.ToMM(g.GetEnd().y)) for g in shapes)
    pins_mid = (pad_xy(j22, "1")[0] + pad_xy(j22, "4")[0]) / 2
    j22.SetOrientationDegrees(180)
    pin_y = D.Y0 - D.REAR_USB_OVERHANG + face
    j22.SetPosition(V(D.REAR_USB_X + pins_mid, pin_y))
    body_back = pin_y - back
    hdr_y = 36.7        # between the USB-A courtyard and the rear GPIO_1 lanes (y >= 37.9)
    p1 = (D.REAR_USB_X + 1.5 * D.PITCH, hdr_y)
    # pins must point to the front (+y): pad 2 west of pad 1, and the body on the front side
    for rot in (90, 270):
        if place_rel(j23, rot, p1, {"2": (-D.PITCH, 0)}):
            bb = j23.GetCourtyard(pcbnew.F_CrtYd).BBox()
            if pcbnew.ToMM(bb.GetBottom()) > hdr_y + 5:
                break
    else:
        raise SystemExit("J23 orientation")
    tip = pcbnew.ToMM(j23.GetCourtyard(pcbnew.F_CrtYd).BBox().GetBottom())
    print(f"J22 pins y {pin_y:.2f}, body back {body_back:.2f}, J23 row y {hdr_y}, pins end y {tip:.2f}")


def route_rear_usb(r, fps):
    """Short straight tracks from each USB-A pin to the header pin right behind it."""
    F = pcbnew.F_Cu
    for n, w in (("1", 0.8), ("2", 0.3), ("3", 0.3), ("4", 0.8)):
        a, b = pad_xy(fps["J22"], n), pad_xy(fps["J23"], n)
        r.track([a, (a[0], a[1] + 1.2), (b[0], b[1] - 1.2), b], w, F, D.REAR_USB_NETS[n])


def place_panel(fps):
    """J24 2x6: pairs side by side along x, odd pins on the north row. Standing resistors in 2 rows
    of 3 north of it (buttons, then LEDs), pads side by side, pad 1 (3V3) west."""
    e = (D.panel_col_x(5), D.PANEL_ROW_Y)
    for rot in (0, 90, 180, 270):
        if place_rel(fps["J24"], rot, e, {"2": (0, D.PITCH), "3": (-D.PITCH, 0)}):
            break
    else:
        raise SystemExit("J24 orientation")
    for i, ref in enumerate(sorted(D.PANEL_R, key=lambda s: int(s[1:]))):
        p1 = (D.PANEL_R_CX[i % 3] - D.PITCH / 2, D.PANEL_R_ROWS[i // 3])
        assert place_rel(fps[ref], 0, p1, {"2": (D.PITCH, 0)}), ref


def route_panel(r, fps, spread):
    """Tap the six front panel signals off the spread GPIO_1 lanes, down to In2, under the bus and
    between the resistors, straight into the J24 north pads (through-hole, so no via there).
    3V3 comes from the J12 3V3 lane: via, In2 down, via, rail on F.Cu."""
    F, B, I2 = pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu
    j24 = lambda n: pad_xy(fps["J24"], n)  # noqa: E731
    y33 = D.Y0 + D.j12_de(29)[0] + 1.27
    r.via(D.PANEL_3V3_X, y33, "3V3")
    r.track([(D.PANEL_3V3_X, y33), (D.PANEL_3V3_X, D.PANEL_RAIL_Y)], 0.4, I2, "3V3")
    r.via(D.PANEL_3V3_X, D.PANEL_RAIL_Y, "3V3")
    west = D.PANEL_R_CX[0] - D.PITCH / 2
    r.track([(D.PANEL_3V3_X, D.PANEL_RAIL_Y), (west, D.PANEL_RAIL_Y)], 0.3, F, "3V3")
    for cx in D.PANEL_R_CX:                       # rail -> north row pad 1 -> south row pad 1
        x1 = cx - D.PITCH / 2
        r.track([(x1, D.PANEL_RAIL_Y), (x1, D.PANEL_R_ROWS[1])], 0.3, F, "3V3")
    btn_lane = {0: 115.6, 1: 113.4, 2: 114.6}     # button F lanes (planar order)
    led_lane = {3: 114.4, 4: 113.3, 5: 113.3}     # LED anode B lanes
    for i, (name, pin, kind) in enumerate(D.PANEL):
        net = D.J10_NETS[pin]
        xt, xc = D.PANEL_TAP_X[i], D.PANEL_CROSS_X[i]
        ys = spread[net]
        q = 5 - i
        north, south = j24(str(2 * q + 1)), j24(str(2 * q + 2))
        r.via(xt, ys, net, size=0.56, drill=0.3)
        r.track([(xt, ys), (xt, 104.0), (xc, 106.6), (xc, 113.0), (north[0], 115.4), north], 0.25, I2, net)
        p2 = pad_xy(fps[f"R{i + 1}"], "2")
        if kind == "btn":
            # down through the gap between the pads of the LED resistor below, then to the header
            xg = D.PANEL_R_CX[i]
            y = btn_lane[i]
            r.track([p2, (xg, p2[1] + abs(p2[0] - xg)), (xg, y), (north[0], y), north], 0.25, F, net)
        else:
            anode = D.PANEL_R[f"R{i + 1}"][1]
            xa = north[0] + D.PITCH / 2
            y = led_lane[i]
            r.track([p2, (p2[0], y), (xa, y), (xa, south[1] - 1.27), south], 0.25, B, anode)


def route_eth(r, fps):
    """Pin N to pin N. The two jacks face away from each other, so their pin order is mirrored.
    The lines go down the east side of J21 and come back west under its body, which reverses the
    order with no via. Odd pins on F.Cu, even pins on B.Cu (even lines pass between the odd pads)."""
    F, B = pcbnew.F_Cu, pcbnew.B_Cu
    w = 0.36            # ~50 ohm single ended over GND, ~100 ohm per pair (lines are not coupled)
    j21_1 = pad_xy(fps["J21"], "1")
    east = j21_1[0] + 13.24          # just east of the J21 body
    lane_x = {k: east + 0.6 * i for i, k in enumerate((7, 5, 3, 1))}
    lane_x.update({k: east + 0.6 * i for i, k in enumerate((8, 6, 4, 2))})
    lane_y = {k: j21_1[1] + 1.57 + 0.6 * i for i, k in enumerate((7, 5, 3, 1))}
    lane_y.update({k: j21_1[1] + 1.57 + 0.6 * i for i, k in enumerate((8, 6, 4, 2))})
    for n in range(1, 9):
        a = pad_xy(fps["J20"], str(n))
        b = pad_xy(fps["J21"], str(n))
        x, y = lane_x[n], lane_y[n]
        y0 = 38.6
        pts = [a, (a[0], y0), (x, y0 + abs(x - a[0])), (x, y), (b[0], y), b]
        r.track(pts, w, F if n % 2 else B, D.ETH_NETS[n], cham=0.4)


def hub_vbus(U):
    out = {}
    for p in U.Pads():
        if p.GetNumber() == "VBUS":
            x, y = pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
            if abs(y - (D.HUB_C[1] - 8.89)) < 0.01 and x < D.HUB_C[0]:
                out["P1"] = (x, y)
            if abs(y - (D.HUB_C[1] + 1.27)) < 0.01 and x > D.HUB_C[0]:
                out["P4"] = (x, y)
    return out


# --------------------------------------------------------------------------
# Zones, keepouts, stitching, drawings
# --------------------------------------------------------------------------
def zone(board, net, layer, pts, priority=0, clearance=0.3):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    if net is not None:
        z.SetNet(net)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in pts:
        ol.Append(MM(x), MM(y))
    z.SetAssignedPriority(priority)
    z.SetLocalClearance(MM(clearance))
    z.SetMinThickness(MM(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(MM(0.3))
    z.SetThermalReliefSpokeWidth(MM(0.4))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    board.Add(z)
    return z


def add_zones(board, nets):
    gnd = nets["GND"]
    for layer in (pcbnew.In1_Cu, pcbnew.In2_Cu):
        zone(board, gnd, layer, D.OUTLINE, clearance=0.3)
    # No outer pours: between the 2.54 mm connector rows they only leave slivers and starved
    # thermals. Both inner layers are solid GND, which is the reference for every signal layer.


def circle_pts(x, y, r, n=24):
    return [(x + r * math.cos(2 * math.pi * i / n), y + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def add_keepouts(board):
    """Standoffs and screw heads: no copper on the outer layers around the M3 holes."""
    for ref, (x, y, _) in D.HOLES.items():
        z = pcbnew.ZONE(board)
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowZoneFills(True)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        ls = pcbnew.LSET()
        ls.AddLayer(pcbnew.F_Cu)
        ls.AddLayer(pcbnew.B_Cu)
        z.SetLayerSet(ls)
        ol = z.Outline()
        ol.NewOutline()
        for px, py in circle_pts(x, y, 3.3):
            ol.Append(MM(px), MM(py))
        z.SetZoneName(f"KEEPOUT_{ref}")
        board.Add(z)


def seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0 if l2 == 0 else max(0, min(1, ((p[0] - ax) * dx + (p[1] - ay) * dy) / l2))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def inside_poly(p, poly):
    x, y = p
    c = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def stitch(r, board, fps):
    """GND stitching vias on a grid, only where nothing else is close."""
    pads = []
    for fp in fps.values():
        for p in fp.Pads():
            pos = p.GetPosition()
            size = max(pcbnew.ToMM(p.GetSize(pcbnew.F_Cu).x), pcbnew.ToMM(p.GetSize(pcbnew.F_Cu).y),
                       pcbnew.ToMM(p.GetDrillSize().x))
            pads.append(((pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)), size / 2))
    w = D.WINDOW
    added = 0
    y = 22.5
    while y < D.Y_FRONT - 1:
        x = min(p[0] for p in D.OUTLINE) + 2.5
        while x < D.X_RIGHT - 1:
            p = (x, y)
            ok = inside_poly(p, D.OUTLINE)
            ok = ok and all(seg_dist(p, a, b) > 1.2 for a, b in zip(D.OUTLINE, D.OUTLINE[1:] + D.OUTLINE[:1]))
            ok = ok and not (w[0] - 1.5 < x < w[2] + 1.5 and w[1] - 1.5 < y < w[3] + 1.5)
            ok = ok and all(math.hypot(x - hx, y - hy) > 4.0 for hx, hy, _ in D.HOLES.values())
            ok = ok and all(math.hypot(x - c[0], y - c[1]) > rr + 0.3 + 0.5 for c, rr in pads)
            ok = ok and all(seg_dist(p, a, b) > wd / 2 + 0.3 + 0.35 for a, b, wd, _ in r.segments)
            ok = ok and not (155 < x < 191 and 24 < y < 58)          # under the hub module
            if ok:
                r.via(x, y, "GND")
                added += 1
            x += 5.0
        y += 5.0
    print("stitching vias", added)


def add_drawings(board, yp, fps):
    L = pcbnew.Dwgs_User
    add_rect(board, L, D.X0_IO, D.Y0, D.X0_IO + D.BASE_W, D.Y_FRONT, 0.2)
    add_rect(board, L, D.X0_CY, D.Y0, D.X0_CY + D.BASE_W, D.Y_FRONT, 0.2)
    fx, fy = D.FPGA_C
    h = D.FPGA_BODY / 2
    add_rect(board, L, fx - h, fy - h, fx + h, fy + h, 0.15)
    for (dd, ee), name in [((D.RJ45_D, D.RJ45_E), "RJ45 P1 (~13.5 mm)"), ((D.JP7_D, D.JP7_E), "POWER 5V jack (~11 mm)"),
                           ((D.KEY2_D, D.KEY2_E), "KEY2"), ((D.J13_D, D.J13_E), "J13 USB-A (~7 mm)")]:
        a, b = D.cy(dd[0], ee[0]), D.cy(dd[1], ee[1])
        add_rect(board, L, min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]), 0.15)
        add_text(board, pcbnew.Cmts_User, name, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2, 0.8, 0.12)
    C = pcbnew.Cmts_User
    add_text(board, C, "I/O board outline (same as the base, to verify)", D.X0_IO + D.BASE_W / 2, 110, 0.9, 0.12)
    add_text(board, C, "FAN / HEATSINK WINDOW 38.5 x 38.5 (FPGA 23 + 2 x 7.75)", fx, D.WINDOW[1] - 2.2, 0.9, 0.12)
    S = pcbnew.F_SilkS
    add_text(board, S, "MisterFlat backplane Rev A5 - PROTOTYPE, NOT VALIDATED", 54, 106, 1.2, 0.18)
    add_text(board, S, "REAR: VGA / AUDIO", 54, 21.6, 1.2, 0.18)
    add_text(board, S, "REAR: HDMI / POWER 5V", D.sx(135.5), 21.6, 1.2, 0.18)
    add_text(board, S, "FRONT", 54, 125.2, 1.2, 0.18)
    add_text(board, S, "FRONT", D.sx(148.0), 125.2, 1.2, 0.18)
    add_text(board, S, "QMTECH I/O BOARD V2.1", 54, 64, 2.5, 0.35)
    add_text(board, S, "mounts here upright, components up", 54, 68.5, 1.5, 0.22)
    add_text(board, S, "on J1 + J3 (male) and 4 M3 standoffs", 54, 71.5, 1.5, 0.22)
    add_text(board, S, "QMTECH CYCLONE V SoC", D.sx(130.5), 92.0, 1.8, 0.27)
    add_text(board, S, "mounts here FLIPPED, FPGA down", D.sx(130.5), 95.2, 1.2, 0.18)
    add_text(board, S, "on J2 + J4 + J5 (female), 4 M3 standoffs", D.sx(130.5), 97.6, 1.2, 0.18)
    add_text(board, S, "I/O J12 (male)", 85.8, 33.5, 0.9, 0.15, 90)
    add_text(board, S, "CYC J12 (female)", D.sx(96.4), 34.0, 0.9, 0.15, 90)
    add_text(board, S, "I/O J10 GPIO_1", 22.8, 33.0, 0.9, 0.15, 90)
    add_text(board, S, "CYC J10 GPIO_1", D.sx(159.4), 33.0, 0.9, 0.15, 90)
    add_text(board, S, "JP6 USB", D.sx(96.4), 109.8, 0.9, 0.15)
    add_text(board, S, "I/O USB", 85.8, 109.8, 0.9, 0.15)
    for name, (x0, y0) in (("J7 AUX", D.AUX_PIN1), ("J8 DISPLAY", D.DISP_PIN1)):
        add_text(board, S, name, D.sx(177.5), y0 - 2.2, 0.9, 0.15)
        for i, lab in enumerate(["5V", "D-", "D+", "GND"]):
            add_text(board, S, lab, x0 - 2.3, y0 + 2.54 * i, 0.6, 0.1)
        # mated Dupont housing, to show it stays inside the board
        add_rect(board, L, x0 + 4.04, y0 - 1.27, x0 + 4.04 + D.DUPONT_LEN, y0 + 3 * 2.54 + 1.27, 0.15)
    add_text(board, pcbnew.Cmts_User, "mated Dupont housings", D.sx(181.5), 81.6, 0.7, 0.1)
    add_text(board, S, "WIFI/BT", D.USBA_PIN1_X + 3.5, yp - 4.4, 0.9, 0.15)
    add_text(board, S, "NET OUT (rear)", 5.0, 40.6, 1.0, 0.15)
    cx = (D.panel_col_x(0) + D.panel_col_x(5)) / 2
    add_text(board, S, "J24: 12-wire IDC ribbon", cx, 104.7, 0.7, 0.12)
    add_text(board, S, "to the front panel board", cx, 105.9, 0.7, 0.12)
    e, w = pad_xy(fps["J23"], "1"), pad_xy(fps["J23"], "4")
    add_text(board, S, "VIN", e[0] + 3.0, e[1], 1.3, 0.22)
    add_text(board, S, "GND", w[0] - 3.2, w[1], 1.3, 0.22)
    # mated Dupont housing in front of the pins, to show where the cable goes
    add_rect(board, L, w[0] - 1.27, e[1] + 4.04, e[0] + 1.27, e[1] + 4.04 + D.DUPONT_LEN, 0.15)
    add_text(board, pcbnew.Cmts_User, "cable to the front", (e[0] + w[0]) / 2, e[1] + 4.04 + D.DUPONT_LEN + 1.2, 0.7, 0.1)
    add_text(board, S, "NET IN", 4.5, 81.4, 1.0, 0.15)
    add_text(board, S, "patch cable from", 4.5, 83.0, 0.8, 0.12)
    add_text(board, S, "Cyclone RJ45", 4.5, 84.4, 0.8, 0.12)
    add_text(board, pcbnew.Cmts_User, "patch cable plugs in here (front)", 5.0, 108.5, 0.8, 0.12)


if __name__ == "__main__":
    build()
