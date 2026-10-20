# PCB Analyzer

A Python 3 / GTK 3 desktop workbench for inspecting PCB files, navigating components, recording test-point measurements, and asking a locally hosted Ollama model for troubleshooting hypotheses. The PCB viewer and deterministic measurement checks work without AI.

The product's display name and subtitle can be changed in **Edit → Settings**. The stable application/package identifier remains `io.github.draxx.pcbanalyzer` / `pcb-analyzer` for compatibility.

## Current release and honest capability summary

Release version: **0.6.32** (`VERSION` is the version source of truth).

Implemented: GTK 3 application, Cairo PCB viewer, component search/selection, layer and side controls, KiCad PCB / EasyEDA Standard PCB JSON / Altium ASCII parsing, optional Altium binary parsing, PDF visual viewer, test-point JSON storage and CSV export, scalar tolerance evaluation, Ollama JSON-mode requests, local troubleshooting-case archive, and persistent AI conversation/settings.

Not implemented: KiCad schematic/netlist parser; image OCR; electrical-net reconstruction from PDFs; complete datasheet corpus; verified universal component database; cloud-provider integration; calibrated diagnostic confidence; complete session/project manager; PDF report generation; complete ChatGPT-style sidebar or evidence cards. See [the audit](docs/engineering-audit.md) for details and risks.

## Supported inputs and limitations

| Input | Actual support |
|---|---|
| KiCad `.kicad_pcb` | S-expression PCB parser, coordinates in mm. Not a KiCad schematic parser. |
| EasyEDA Standard PCB JSON | Native board JSON parser. Other EasyEDA formats may not be compatible. |
| Altium ASCII PCB export | Pipe-delimited ASCII board data. |
| Altium binary `.PcbDoc` | Optional `altium-monkey` integration; the base Debian package does not guarantee it. Exporting Altium ASCII is the portable option. |
| PDF | Visual rendering only. No netlist or connectivity is inferred from a PDF. |
| Schematic raster image / OCR | Not implemented. |

The internal board model preserves available components, pads, tracks, vias, outlines, zones and nets. Missing source geometry/connectivity is not synthesized. Not every source-format primitive is implemented; validate important results against the originating CAD tool.

## Install on Debian / Ubuntu

Build a package from source (requires `dpkg-deb`):

```sh
sh scripts/build-deb.sh
```

The output is `dist/pcb-analyzer_$(cat VERSION)_all.deb`. Inspect and install it:

```sh
dpkg-deb --info "dist/pcb-analyzer_$(cat VERSION)_all.deb"
dpkg-deb --contents "dist/pcb-analyzer_$(cat VERSION)_all.deb"
sudo apt install "./dist/pcb-analyzer_$(cat VERSION)_all.deb"
```

Launch from the desktop menu or terminal:

```sh
pcb-analyzer
pcb-analyzer /path/to/board.kicad_pcb
```

Runtime dependencies declared by the package: Python 3, PyGObject, GTK 3, Cairo GI bindings, and Poppler GI. Binary Altium parsing additionally requires `altium-monkey` in the Python environment used by the application. Package build alone does not verify that a desktop session can launch GTK.

## Run from source

On a Debian/Ubuntu machine with the declared GTK and Poppler runtime packages installed:

```sh
python3 src/pcb-analyzer
```

Altium binary support is optional:

```sh
python3 -m pip install altium-monkey
```

## Local AI, privacy and persistence

The AI provider is Ollama at `http://127.0.0.1:11434` by default, model `llama3`. Install and start Ollama separately, download a model supported by your machine, then configure endpoint/model under **AI Settings**. This application currently has no cloud provider implementation and does not upload a board to a cloud service. Board context is sent to the configured Ollama endpoint; if that endpoint is remote, treat its operator as a recipient of the board context.

User configuration: `${XDG_CONFIG_HOME:-~/.config}/pcb-analyzer/settings.json` (created with private file permissions). Conversation history and AI-generated troubleshooting cases are stored in `${XDG_DATA_HOME:-~/.local/share}/pcb-analyzer/knowledge.sqlite3`.

Prior AI cases are retrieved as **unverified** hints. This is persistent retrieval, not model fine-tuning; answers are not automatically converted into verified engineering facts. No comprehensive, validated datasheet library is bundled. Do not use an AI hypothesis as a substitute for component ratings, manufacturer datasheets, safe measurement procedure or engineering review.

## Development and tests

Run the deterministic, offline unit suite:

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests
```

The tests mock AI/network interactions and use local fixtures. GTK GUI smoke tests need a real graphical session and installed GTK/PyGObject packages. Build the Debian package with `sh scripts/build-deb.sh`; the script uses `VERSION` for both package metadata and filename.

## Packaging and release notes

`VERSION` is authoritative for runtime version display, Python project metadata and Debian package output. CI runs the unit suite on Python 3.10/3.12 and builds a `.deb` artifact. The build script writes generated output only to `dist/`.

See [CHANGELOG.md](CHANGELOG.md) for the current changes and [docs/engineering-audit.md](docs/engineering-audit.md) for confirmed limitations and audit findings.
