#!/bin/sh
# Regenerate both boards and every output (reports, fab packages, print PDFs, case files).
# Run from the repository root.
set -e
KPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
K=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
ROOT=$(pwd)
TMP=$(mktemp -d)
LAYERS2=F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts
LAYERS4=F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts

python3 tools/build_sch.py
$KPY tools/build_pcb.py
$KPY tools/build_panel.py
$KPY tools/verify.py

fab() {   # $1 dir, $2 project, $3 layers, $4 print title
  cd "$ROOT/$1"
  P=$2.kicad_pcb
  mkdir -p reports fab mech
  $K sch erc -o reports/ERC.rpt --severity-all $2.kicad_sch
  $K pcb drc --schematic-parity --refill-zones --severity-all -o reports/DRC.rpt $P
  rm -rf fab/gerbers && mkdir -p fab/gerbers
  $K pcb export gerbers -o fab/gerbers/ --layers $3 --subtract-soldermask --check-zones $P
  $K pcb export drill -o fab/gerbers/ --format excellon --excellon-units mm --excellon-separate-th \
     --generate-map --map-format gerberx2 $P
  rm -f fab/$2_gerbers.zip
  (cd fab/gerbers && zip -q ../$2_gerbers.zip $(ls | grep -v -e drl_map -e job))
  $K sch export pdf -o reports/$2_schematic.pdf $2.kicad_sch
  $K sch export bom -o reports/$2_BOM.csv $2.kicad_sch
  $K pcb export svg --layers Edge.Cuts,F.Mask,F.SilkS,Dwgs.User --mode-single --page-size-mode 2 \
     --exclude-drawing-sheet --black-and-white -o $TMP/board.svg $P
  python3 "$ROOT/tools/make_print.py" $TMP/board.svg $TMP/print.svg "$4"
  rsvg-convert -f pdf -o reports/PRINT_1to1_A4_landscape.pdf $TMP/print.svg
  $K pcb export step -o mech/$2.step --subst-models --drill-origin --force $P
}

fab RevA5 MisterFlat_RevA5 $LAYERS4 "MisterFlat backplane Rev A5"
cd "$ROOT/RevA5"
$K pcb export pos -o fab/positions_raw.csv --side front --format csv --units mm MisterFlat_RevA5.kicad_pcb
python3 ../tools/build_fab.py
rm -f reports/pcb_layers_pdf/*.pdf
$K pcb export pdf --mode-separate --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.SilkS,Edge.Cuts,Dwgs.User \
   -o reports/pcb_layers_pdf/ MisterFlat_RevA5.kicad_pcb
mkdir -p $TMP/mech && $KPY ../tools/make_mech.py $TMP/mech
rsvg-convert -f pdf -o mech/MisterFlat_RevA5_mechanical.pdf $TMP/mech/p*.svg
rm -f fab/MisterFlat_RevA5_fab_package.zip
zip -qr fab/MisterFlat_RevA5_fab_package.zip fab/README_fab.md fab/BOM_JLCPCB.csv fab/CPL_JLCPCB.csv \
   fab/MisterFlat_RevA5_gerbers.zip fab/gerbers

fab PanelRevA MisterFlat_Panel_RevA $LAYERS2 "MisterFlat front panel Rev A"

cd "$ROOT"
grep -h "Found\|^\*\* Found" RevA5/reports/DRC.rpt PanelRevA/reports/DRC.rpt
rm -rf $TMP
echo done
