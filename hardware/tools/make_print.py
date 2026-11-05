"""Centre the 1:1 board SVG on an A4 landscape page, with a 100 mm scale bar.

Usage: python3 make_print.py board.svg out.svg [title]   (then: rsvg-convert -f pdf -o out.pdf out.svg)
The board SVG comes from: kicad-cli pcb export svg --layers Edge.Cuts,F.Mask,F.SilkS,Dwgs.User
  --mode-single --page-size-mode 2 --exclude-drawing-sheet --black-and-white
"""
import re
import sys

s = open(sys.argv[1]).read()
w = float(re.search(r'width="([\d.]+)mm"', s).group(1))
h = float(re.search(r'height="([\d.]+)mm"', s).group(1))
inner = s[s.find("<svg"):]
inner = re.sub(r'width="[\d.]+mm" height="[\d.]+mm"',
               f'x="{(297 - w) / 2:.3f}" y="{(210 - h) / 2:.3f}" width="{w}" height="{h}"', inner, 1)
y_bar = (210 + h) / 2 + 12
title = sys.argv[3] if len(sys.argv) > 3 else "MisterFlat backplane Rev A5"
out = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="297mm" height="210mm" viewBox="0 0 297 210">
<rect x="0" y="0" width="297" height="210" fill="white"/>
<text x="148.5" y="{(210 - h) / 2 - 8:.2f}" font-family="Helvetica" font-size="4" text-anchor="middle">{title} - 1:1 - print at 100 % (actual size), A4 landscape</text>
{inner}
<g stroke="black" stroke-width="0.3" fill="none">
<line x1="98.5" y1="{y_bar}" x2="198.5" y2="{y_bar}"/>
<line x1="98.5" y1="{y_bar - 2}" x2="98.5" y2="{y_bar + 2}"/>
<line x1="198.5" y1="{y_bar - 2}" x2="198.5" y2="{y_bar + 2}"/>
</g>
<text x="148.5" y="{y_bar + 6:.2f}" font-family="Helvetica" font-size="3.5" text-anchor="middle">this line must measure 100 mm (board width {w:.0f} mm)</text>
</svg>'''
open(sys.argv[2], "w").write(out)
