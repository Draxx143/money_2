#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=$(cat "$ROOT/VERSION")
OUTPUT="$ROOT/dist"
STAGING=$(mktemp -d)
trap 'rm -rf "$STAGING"' EXIT HUP INT TERM
chmod 755 "$STAGING"

mkdir -p "$OUTPUT" \
         "$STAGING/DEBIAN" \
         "$STAGING/usr/bin" \
         "$STAGING/usr/share/applications" \
         "$STAGING/usr/share/pcb-analyzer/src/pcb_analyzer" \
         "$STAGING/usr/share/pcb-analyzer/examples"

cat > "$STAGING/DEBIAN/control" <<CONTROL
Package: pcb-analyzer
Version: $VERSION
Section: electronics
Priority: optional
Architecture: all
Maintainer: Draxx <draxx@localhost>
Depends: python3, python3-gi, gir1.2-gtk-3.0, gir1.2-poppler-0.18
Description: Professional PCB Analysis & AI Diagnostics Workbench
 A GTK 3 desktop application for PCB analysis, component navigation,
 test-point management, and AI-assisted diagnostics.
CONTROL

install -m 755 "$ROOT/src/pcb-analyzer" "$STAGING/usr/bin/pcb-analyzer"
install -m 644 "$ROOT/packaging/pcb-analyzer.desktop" \
    "$STAGING/usr/share/applications/pcb-analyzer.desktop"

# install package (sources)
for f in "$ROOT"/src/pcb_analyzer/*.py; do
    install -m 644 "$f" "$STAGING/usr/share/pcb-analyzer/src/pcb_analyzer/"
done
install -m 644 "$ROOT/tests/fixtures/PCB_PCB_test_pcb_2_2026-10-20.json" \
    "$STAGING/usr/share/pcb-analyzer/examples/PCB_PCB_test_pcb_2_2026-10-20.json"

dpkg-deb --root-owner-group --build "$STAGING" \
    "$OUTPUT/pcb-analyzer_${VERSION}_all.deb"
echo "Built: $OUTPUT/pcb-analyzer_${VERSION}_all.deb"
