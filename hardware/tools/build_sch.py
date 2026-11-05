"""Generate RevA5/MisterFlat_RevA5.kicad_sch and the project symbol library from design.py."""
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design as D  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "RevA5")
NS = uuid.UUID("7d0c6a52-4d0b-4b8e-9a43-6f1b2b0a5a05")
ROOT_UUID = str(uuid.uuid5(NS, "root-sheet"))


def uid(*parts):
    return str(uuid.uuid5(NS, "/".join(parts)))


def lib_block(lib, name):
    s = open(os.path.join(D.KICAD_SYM, lib + ".kicad_sym")).read()
    i = s.find(f'(symbol "{name}"')
    assert i >= 0, (lib, name)
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "(":
            depth += 1
        elif s[j] == ")":
            depth -= 1
            if depth == 0:
                break
    blk = s[i:j + 1]
    assert "(extends" not in blk, name
    return blk.replace(f'(symbol "{name}"', f'(symbol "{lib}:{name}"', 1)


ADAFRUIT_LEFT = ["UP_D+", "UP_D-", None, "VBUS", "GND"]
ADAFRUIT_RIGHT = ["P1_D+", "P1_D-", "P2_D+", "P2_D-", "P3_D+", "P3_D-", "P4_D+", "P4_D-"]


def adafruit_symbol(prefixed):
    name = "MisterFlat:Adafruit_5997" if prefixed else "Adafruit_5997"
    pins = []
    top = 8.89
    for i, p in enumerate(ADAFRUIT_LEFT):
        if p:
            typ = "passive" if p in ("VBUS", "GND") else "bidirectional"
            label = "5V (VBUS)" if p == "VBUS" else p
            pins.append(f'(pin {typ} line (at -12.7 {top - 2.54 * i:.2f} 0) (length 2.54) '
                        f'(name "{label}" (effects (font (size 1.27 1.27)))) '
                        f'(number "{p}" (effects (font (size 1.27 1.27)))))')
    for i, p in enumerate(ADAFRUIT_RIGHT):
        pins.append(f'(pin bidirectional line (at 12.7 {top - 2.54 * i:.2f} 180) (length 2.54) '
                    f'(name "{p}" (effects (font (size 1.27 1.27)))) '
                    f'(number "{p}" (effects (font (size 1.27 1.27)))))')
    return f'''(symbol "{name}" (pin_names (offset 1.016)) (exclude_from_sim no) (in_bom yes) (on_board yes)
  (property "Reference" "U" (at 0 11.43 0) (effects (font (size 1.27 1.27))))
  (property "Value" "Adafruit_5997" (at 0 -13.97 0) (effects (font (size 1.27 1.27))))
  (property "Footprint" "MisterFlat:Adafruit_5997_CH334F_Socketed" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
  (property "Datasheet" "https://learn.adafruit.com/adafruit-ch334f-mini-4-port-usb-hub-breakout" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
  (property "Description" "Adafruit CH334F Mini 4-Port USB Hub Breakout #5997. All 5V pads and all GND pads are tied on the module." (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
  (symbol "Adafruit_5997_0_1" (rectangle (start -10.16 10.16) (end 10.16 -12.7) (stroke (width 0.254) (type default)) (fill (type background))))
  (symbol "Adafruit_5997_1_1" {" ".join(pins)})
)'''


def write_symbol_lib():
    os.makedirs(os.path.join(OUT, "lib"), exist_ok=True)
    with open(os.path.join(OUT, "lib", "MisterFlat.kicad_sym"), "w") as f:
        f.write('(kicad_symbol_lib (version 20251024) (generator "misterflat_build_sch") (generator_version "10.0")\n')
        f.write(adafruit_symbol(False) + "\n)\n")


def pin_points(lib_blk):
    """number -> (x, y, angle) in library coordinates (y up)."""
    pts = {}
    for m in re.finditer(r'\(pin \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+) (\d+)\)(.*?)\(number "([^"]*)"', lib_blk, re.S):
        pts[m.group(5)] = (float(m.group(1)), float(m.group(2)), int(m.group(3)))
    return pts


def fmt(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


class Sheet:
    def __init__(self, project=None, root=ROOT_UUID):
        self.items = []
        self.libs = {}
        self.project = project or D.PROJECT
        self.root = root

    def lib(self, lib_id):
        if lib_id not in self.libs:
            if lib_id == "MisterFlat:Adafruit_5997":
                self.libs[lib_id] = adafruit_symbol(True)
            else:
                lib, name = lib_id.split(":")
                self.libs[lib_id] = lib_block(lib, name)
        return self.libs[lib_id]

    def label(self, net, x, y, side):
        # Global labels: net names without the sheet prefix, identical to the PCB net names.
        ang, just = (180, "right") if side == "left" else (0, "left")
        self.items.append(
            f'(global_label "{net}" (shape passive) (at {fmt(x)} {fmt(y)} {ang}) (fields_autoplaced yes) '
            f'(effects (font (size 1.27 1.27)) (justify {just})) (uuid "{uid("label", net, fmt(x), fmt(y))}") '
            f'(property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {fmt(x)} {fmt(y)} 0) '
            f'(effects (font (size 1.27 1.27)) (hide yes))))')

    def text(self, txt, x, y, size=1.27):
        txt = txt.replace('"', "'").replace("\n", "\\n")
        self.items.append(f'(text "{txt}" (exclude_from_sim no) (at {fmt(x)} {fmt(y)} 0) '
                          f'(effects (font (size {size} {size})) (justify left top)) (uuid "{uid("text", txt[:40], fmt(x))}"))')

    def symbol(self, ref, lib_id, x, y, value, footprint, nets, fields=None, in_bom=True, on_board=True):
        blk = self.lib(lib_id)
        pts = pin_points(blk)
        su = uid("sym", ref)
        props = [
            f'(property "Reference" "{ref}" (at {fmt(x)} {fmt(y - 2.54 - max([0] + [p[1] for p in pts.values()]))} 0) (effects (font (size 1.27 1.27))))',
            f'(property "Value" "{value}" (at {fmt(x)} {fmt(y + 2.54 - min([0] + [p[1] for p in pts.values()]))} 0) (effects (font (size 1.27 1.27))))',
            f'(property "Footprint" "{footprint}" (at {fmt(x)} {fmt(y)} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
            f'(property "Datasheet" "~" (at {fmt(x)} {fmt(y)} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        ]
        for k, v in (fields or {}).items():
            props.append(f'(property "{k}" "{v}" (at {fmt(x)} {fmt(y)} 0) (effects (font (size 1.27 1.27)) (hide yes)))')
        pins = " ".join(f'(pin "{n}" (uuid "{uid("pin", ref, n)}"))' for n in pts)
        self.items.append(
            f'(symbol (lib_id "{lib_id}") (at {fmt(x)} {fmt(y)} 0) (unit 1) (exclude_from_sim no) '
            f'(in_bom {"yes" if in_bom else "no"}) (on_board {"yes" if on_board else "no"}) (dnp no) (uuid "{su}") '
            + " ".join(props) + " " + pins +
            f' (instances (project "{self.project}" (path "/{self.root}" (reference "{ref}") (unit 1)))))')
        for n, (px, py, ang) in pts.items():
            if n in nets:
                ax, ay = x + px, y - py
                self.label(nets[n], ax, ay, "left" if ang == 0 else "right")
        missing = set(nets) - set(pts)
        assert not missing, (ref, missing)
        return su

    def pwr_flag(self, net, x, y, idx):
        self.lib("power:PWR_FLAG")
        self.items.append(
            f'(symbol (lib_id "power:PWR_FLAG") (at {fmt(x)} {fmt(y)} 0) (unit 1) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no) '
            f'(uuid "{uid("flag", net)}") '
            f'(property "Reference" "#FLG0{idx}" (at {fmt(x)} {fmt(y - 1.9)} 0) (effects (font (size 1.27 1.27)) (hide yes))) '
            f'(property "Value" "PWR_FLAG" (at {fmt(x)} {fmt(y - 3.8)} 0) (effects (font (size 1.27 1.27)))) '
            f'(property "Footprint" "" (at {fmt(x)} {fmt(y)} 0) (effects (font (size 1.27 1.27)) (hide yes))) '
            f'(property "Datasheet" "~" (at {fmt(x)} {fmt(y)} 0) (effects (font (size 1.27 1.27)) (hide yes))) '
            f'(pin "1" (uuid "{uid("flagpin", net)}")) '
            f'(instances (project "{self.project}" (path "/{self.root}" (reference "#FLG0{idx}") (unit 1)))))')
        self.label(net, x, y, "right")

    TITLE = ('(title_block (title "QMTECH MiSTer flat backplane") (date "2026-10-09") (rev "A5") '
             '(company "PROTOTYPE - NOT VALIDATED - DO NOT FABRICATE") '
             '(comment 1 "I/O Board V2.1 left (upright), Cyclone V SoC right (flipped), Adafruit 5997 hub") '
             '(comment 2 "Generated by tools/build_sch.py from tools/design.py"))')

    def write(self, path, paper="A2", title=None):
        with open(path, "w") as f:
            f.write(f'(kicad_sch (version 20251024) (generator "eeschema") (generator_version "10.0") (uuid "{self.root}") (paper "{paper}")\n')
            f.write((title or self.TITLE) + "\n")
            f.write("(lib_symbols\n" + "\n".join(self.libs.values()) + "\n)\n")
            f.write("\n".join(self.items) + "\n")
            f.write('(sheet_instances (path "/" (page "1")))\n)\n')


def main():
    write_symbol_lib()
    sh = Sheet()
    P = D.PARTS
    g = 2.54
    row1 = 30 * g
    cols = [20 * g, 50 * g, 80 * g, 110 * g]
    for ref, x in zip(["J1", "J2", "J3", "J4"], cols):
        v, sym, fp, nets, fields = P[ref]
        sh.symbol(ref, sym, x, row1, v, fp, nets, fields)
    row2 = 76 * g
    for ref, x, y in [("J5", 20 * g, row2), ("J6", 20 * g, row2 + 14 * g), ("U1", 54 * g, row2 + 4 * g),
                      ("J7", 86 * g, row2), ("J8", 86 * g, row2 + 12 * g), ("J9", 108 * g, row2 + 4 * g),
                      ("C1", 128 * g, row2 + 2 * g), ("C2", 136 * g, row2 + 2 * g)]:
        v, sym, fp, nets, fields = P[ref]
        sh.symbol(ref, sym, x, y, v, fp, nets, fields)
    for ref, y in (("J20", 22 * g), ("J21", 44 * g), ("J22", 70 * g), ("J23", 86 * g)):
        v, sym, fp, nets, fields = P[ref]
        sh.symbol(ref, sym, 146 * g, y, v, fp, nets, fields)
    sh.text("Network extension: J21 gets a short patch cable from the\nCyclone RJ45 (P1, front). J20 is the rear panel jack.\n"
            "Pin N to pin N, no magnetics (the Cyclone RJ45 has them).", 134 * g, 56 * g, 1.27)
    v, sym, fp, nets, fields = P["J24"]
    sh.symbol("J24", sym, 180 * g, 30 * g, v, fp, nets, fields)
    for i, ref in enumerate(sorted(D.PANEL_R, key=lambda s: int(s[1:]))):
        v, sym, fp, nets, fields = P[ref]
        sh.symbol(ref, sym, (172 + 8 * i) * g, 62 * g, v, fp, nets, fields)
    sh.text("Front panel (J24, pairs from the west): RESET (J10.17), OSD (J10.13), USER (J10.15): signal + GND,\n"
            "10k pull-up to 3V3, button to GND. LED USER (J10.1), LED DISK (J10.3), LED POWER (J10.5):\n"
            "3V3 - 1k - LED - FPGA pin. The I/O Board may already have pull-ups/LEDs on these pins (in parallel).",
            168 * g, 76 * g, 1.27)
    sh.pwr_flag("USB_5V", 128 * g, row2 + 18 * g, 1)
    sh.pwr_flag("GND", 136 * g, row2 + 18 * g, 2)
    sh.pwr_flag("USB_REAR_VBUS", 120 * g, row2 + 18 * g, 3)   # supplied through the J23 cable
    for i, ref in enumerate(sorted(D.HOLES)):
        v, sym, fp, nets, fields = P[ref]
        sh.symbol(ref, sym, (56 + 6 * (i % 7)) * g, (103 + 6 * (i // 7)) * g, v, fp, nets, fields,
                  in_bom=False)

    sh.text("J12 and J10 (GPIO_1) are passed through pin for pin. Net names are the base board names. J10 pins 11/29 are named J10_VIN/J10_3V3: same supply as VIN/3V3, tied on both QMTECH boards, not linked on the backplane. "
            "(QMTECH schematic 2024-06-07, page 5).\nJ12 pins 12 and 30 are GND, pin 32 is LED5 (the A4 table was wrong).",
            10 * g, 8 * g, 1.6)
    sh.text("USB: Cyclone JP6 (USB3300 host) -> Adafruit 5997 USBHOST. JP6 shares D+/D- with the Cyclone J13 USB-A: leave J13 empty.\n"
            "Hub power = JP6 pin 2 (USB_5V, current limited by the Cyclone U13 TPS2553/TPS25221). It also feeds the I/O USB 5V,\n"
            "the AUX and DISPLAY headers and the Wi-Fi USB-A. On the module all 5V pads and all GND pads are one net.\n"
            "Hub ports: P1 = I/O Board, P2 = DISPLAY, P3 = Wi-Fi USB-A, P4 = AUX (P3/P4 swapped against the brief to avoid vias).",
            10 * g, 66 * g, 1.6)
    sh.text("J6 is PROVISIONAL: it assumes the I/O Board V2.1 has a 2x2 socket over the base JP6.\n"
            "Check on the real board before ordering.", 10 * g, 97 * g, 1.6)
    sh.write(os.path.join(OUT, f"{D.PROJECT}.kicad_sch"))
    print("ok", len(sh.items), "items")


if __name__ == "__main__":
    main()
