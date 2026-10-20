# PCB Analyzer

A GTK 3 desktop workbench for PCB inspection, component navigation, test-point management, and AI-assisted diagnostics.

## Repository layout

- `src/pcb-analyzer` — application entry point and GTK 3 interface.
- `src/pcb_analyzer/` — parsers, board model, viewer, diagnostics, PDF viewer, and AI client. Includes native EasyEDA Standard PCB JSON, Altium ASCII, and KiCad parsing.
- `packaging/` — desktop launcher metadata.
- `scripts/build-deb.sh` — builds the Debian package.
- `tests/` — unit tests and sample input files in `tests/fixtures/`.
- `pcb-analyzer-gtk.zip` — original uploaded project archive, retained for reference.

## Build a Debian package

Requirements: `dpkg-deb`, Python 3, and the GTK 3 / Poppler GI runtime packages.

```sh
sh scripts/build-deb.sh
```

The package is written to `dist/pcb-analyzer_0.6.18_all.deb`. A built copy is also checked in at `artifacts/pcb-analyzer_0.6.18_all.deb`. It includes the supplied EasyEDA board at `/usr/share/pcb-analyzer/examples/PCB_PCB_test_pcb_2_2026-10-20.json`; open this JSON from the File → Open Board dialog for the exact native layout.
Install it on a Debian/Ubuntu system with:

```sh
sudo apt install ./dist/pcb-analyzer_0.6.18_all.deb
```

The package declares these runtime dependencies: `python3`, `python3-gi`, `gir1.2-gtk-3.0`, and `gir1.2-poppler-0.18`. To launch directly with the bundled EasyEDA board:

```sh
pcb-analyzer /usr/share/pcb-analyzer/examples/PCB_PCB_test_pcb_2_2026-10-20.json
```

## Run from source

```sh
python3 src/pcb-analyzer
```

GTK 3 and Poppler GI bindings must be installed on the host. Altium parsing additionally requires a compatible `altium-monkey` installation; this library is not bundled in the Debian package.

## Tests

```sh
python3 -m unittest discover -s tests -v
```
