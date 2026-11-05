"""Write the JLCPCB BOM and CPL files from design.py and the KiCad position export.

Run after `kicad-cli pcb export pos ... -o RevA5/fab/positions_raw.csv`.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design as D  # noqa: E402

FAB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "RevA5", "fab")

# LCSC codes only where we are sure of the part. Empty = choose in the JLC BOM tool.
LCSC = {
}
MPN = {
    "PinHeader_2x20_P2.54mm_Vertical": "Wurth 61304021121 (2x20 male, straight)",
    "PinSocket_2x20_P2.54mm_Vertical": "Wurth 61304021821 (2x20 female, 8.5 mm)",
    "PinSocket_2x02_P2.54mm_Vertical": "Wurth 61300421821 (2x2 female, 8.5 mm)",
    "PinHeader_2x02_P2.54mm_Vertical": "Wurth 61300421121 (2x2 male)",
    "PinHeader_1x04_P2.54mm_Horizontal": "Wurth 61300411021 (1x4 male, right angle)",
    "IDC-Header_2x06_P2.54mm_Vertical": "2x6 boxed IDC header, 2.54 mm, straight (e.g. Wurth 61201221621)",
    "USB_A_Molex_67643_Horizontal": "Molex 67643-0910",
    "RJ45_Amphenol_54602-x08_Horizontal": "Amphenol 54602-908 (no magnetics)",
    "CP_Radial_D5.0mm_P2.00mm": "47uF 16V electrolytic, 5 mm diameter, 2.0 mm pitch",
    "C_Disc_D3.0mm_W1.6mm_P2.50mm": "100nF ceramic, 2.5 mm pitch",
    "R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical": "1/4 W metal film, mounted standing",
    "Adafruit_5997_CH334F_Socketed": "2x 1x8 + 1x4 female 2.54 mm sockets (module bought from Adafruit)",
}


def main():
    rows = list(csv.DictReader(open(os.path.join(FAB, "positions_raw.csv"))))
    groups = {}
    for r in rows:
        ref = r["Ref"]
        if ref.startswith("H"):
            continue                       # mounting holes, nothing to place
        fp = D.PARTS[ref][2].split(":")[1]
        key = (r["Val"], fp)
        groups.setdefault(key, []).append(ref)

    with open(os.path.join(FAB, "BOM_JLCPCB.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #", "Suggested part / note"])
        for (val, fp), refs in sorted(groups.items(), key=lambda kv: kv[1][0]):
            refs.sort(key=lambda s: (s.rstrip("0123456789"), int("".join(c for c in s if c.isdigit()))))
            w.writerow([val, ",".join(refs), fp, LCSC.get((fp, val), ""), MPN.get(fp, "")])

    with open(os.path.join(FAB, "CPL_JLCPCB.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for r in rows:
            if r["Ref"].startswith("H"):
                continue
            w.writerow([r["Ref"], f'{float(r["PosX"]):.4f}mm', f'{float(r["PosY"]):.4f}mm',
                        "Top" if r["Side"] == "top" else "Bottom", f'{float(r["Rot"]):.1f}'])
    print("BOM groups", len(groups), "CPL rows", sum(len(v) for v in groups.values()))


if __name__ == "__main__":
    main()
