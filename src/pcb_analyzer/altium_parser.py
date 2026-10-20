"""Parser for Altium .PcbDoc files using altium-monkey.

Tries to load the .PcbDoc directly first. Falls back to loading via a
project file (.PrjPcb) if direct loading is not supported by the
installed version of altium-monkey.
"""
import os
from typing import Optional

try:
    from altium_monkey import AltiumDesign, AltiumPcbDoc
    HAS_ALTIUM = True
except ImportError:
    HAS_ALTIUM = False
    AltiumDesign = None
    AltiumPcbDoc = None

from .model import Board, Component, Pad, Track


class AltiumParserError(Exception):
    pass


def parse_pcbdoc(path: str) -> Board:
    """Parse an Altium .PcbDoc (or .PrjPcb) and return a Board."""
    if not HAS_ALTIUM:
        raise AltiumParserError(
            "altium-monkey is not installed. Run: pip install altium-monkey --break-system-packages"
        )
    if not os.path.isfile(path):
        raise AltiumParserError(f"File not found: {path}")

    lower = path.lower()

    # AltiumPcbDoc.from_file is the public API. Its constructor only creates
    # an empty document; it does not load a file.
    if lower.endswith(".pcbdoc") and AltiumPcbDoc is not None:
        try:
            loader = getattr(AltiumPcbDoc, "from_file", None)
            if callable(loader):
                pcbdoc = loader(path)
            else:
                # Compatibility with older releases that provided instance.load.
                pcbdoc = AltiumPcbDoc()
                load = getattr(pcbdoc, "load", None)
                if not callable(load):
                    raise AttributeError("altium-monkey provides no PcbDoc file loader")
                load(path)
            return _convert_pcbdoc_object(pcbdoc)
        except Exception as direct_exc:
            direct_error = f"{type(direct_exc).__name__}: {direct_exc}"
    else:
        direct_error = "Direct .PcbDoc loading is unavailable in the installed altium-monkey."

    # 2) Fall back to project-based loading
    if lower.endswith(".pcbdoc"):
        prj = _find_sibling_project(path)
        if prj is None:
            raise AltiumParserError(
                f"Could not load .PcbDoc directly ({direct_error}) and no matching "
                f".PrjPcb was found in the same folder. "
                f"Either place a .PrjPcb next to the .PcbDoc, or ensure your "
                f"altium-monkey version supports direct .PcbDoc loading."
            )
        design = AltiumDesign.from_prjpcb(prj)
        board_obj = design.load_pcbdoc()
        return _convert_board(board_obj)

    elif lower.endswith(".prjpcb"):
        design = AltiumDesign.from_prjpcb(path)
        board_obj = design.load_pcbdoc()
        return _convert_board(board_obj)

    else:
        raise AltiumParserError("Unsupported Altium file. Expected .PcbDoc or .PrjPcb")


def _find_sibling_project(pcbdoc_path: str) -> Optional[str]:
    base = os.path.splitext(pcbdoc_path)[0]
    for candidate in (base + ".PrjPcb", base + ".prjpcb"):
        if os.path.isfile(candidate):
            return candidate
    folder = os.path.dirname(pcbdoc_path)
    try:
        for f in os.listdir(folder):
            if f.lower().endswith(".prjpcb"):
                return os.path.join(folder, f)
    except OSError:
        pass
    return None


def _to_mm(value) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _convert_pcbdoc_object(pcbdoc) -> Board:
    """Convert a directly-loaded AltiumPcbDoc object to our Board model."""
    board = Board()
    board.version = "altium-direct"

    # Components
    for comp in getattr(pcbdoc, "components", []) or []:
        try:
            ref = getattr(comp, "designator", "") or getattr(comp, "reference", "")
            value = getattr(comp, "comment", "") or getattr(comp, "value", "")
            footprint = getattr(comp, "footprint", "") or getattr(comp, "pattern", "")
            x = _to_mm(getattr(comp, "x", 0))
            y = _to_mm(getattr(comp, "y", 0))
            rotation = _to_mm(getattr(comp, "rotation", 0))
            layer = getattr(comp, "layer", "F.Cu")

            c = Component(
                reference=str(ref), value=str(value), footprint=str(footprint),
                x=x, y=y, rotation=rotation, layer=str(layer),
            )
            for pad in getattr(comp, "pads", []) or []:
                try:
                    c.pads.append(Pad(
                        number=str(getattr(pad, "number", "")),
                        x=_to_mm(getattr(pad, "x", 0)),
                        y=_to_mm(getattr(pad, "y", 0)),
                        width=_to_mm(getattr(pad, "width", 0)),
                        height=_to_mm(getattr(pad, "height", 0)),
                        shape=str(getattr(pad, "shape", "rect")),
                        layers=getattr(pad, "layers", []) or [],
                        net=getattr(pad, "net", None),
                    ))
                except Exception:
                    continue
            board.components.append(c)
        except Exception:
            continue

    # Tracks
    for t in getattr(pcbdoc, "tracks", []) or []:
        try:
            board.tracks.append(Track(
                start_x=_to_mm(getattr(t, "x1", 0)),
                start_y=_to_mm(getattr(t, "y1", 0)),
                end_x=_to_mm(getattr(t, "x2", 0)),
                end_y=_to_mm(getattr(t, "y2", 0)),
                width=_to_mm(getattr(t, "width", 0)),
                layer=str(getattr(t, "layer", "F.Cu")),
            ))
        except Exception:
            continue

    return board


def _convert_board(board_obj) -> Board:
    """Convert a board object obtained via project loading."""
    board = Board()
    board.version = "altium"

    for comp in getattr(board_obj, "components", []) or []:
        try:
            ref = getattr(comp, "designator", "") or getattr(comp, "reference", "")
            value = getattr(comp, "comment", "") or getattr(comp, "value", "")
            footprint = getattr(comp, "footprint", "") or getattr(comp, "pattern", "")
            x = _to_mm(getattr(comp, "x", 0))
            y = _to_mm(getattr(comp, "y", 0))
            rotation = _to_mm(getattr(comp, "rotation", 0))
            layer = getattr(comp, "layer", "F.Cu")

            c = Component(
                reference=str(ref), value=str(value), footprint=str(footprint),
                x=x, y=y, rotation=rotation, layer=str(layer),
            )
            for pad in getattr(comp, "pads", []) or []:
                try:
                    c.pads.append(Pad(
                        number=str(getattr(pad, "number", "")),
                        x=_to_mm(getattr(pad, "x", 0)),
                        y=_to_mm(getattr(pad, "y", 0)),
                        width=_to_mm(getattr(pad, "width", 0)),
                        height=_to_mm(getattr(pad, "height", 0)),
                        shape=str(getattr(pad, "shape", "rect")),
                        layers=getattr(pad, "layers", []) or [],
                        net=getattr(pad, "net", None),
                    ))
                except Exception:
                    continue
            board.components.append(c)
        except Exception:
            continue

    for t in getattr(board_obj, "tracks", []) or []:
        try:
            board.tracks.append(Track(
                start_x=_to_mm(getattr(t, "x1", 0)),
                start_y=_to_mm(getattr(t, "y1", 0)),
                end_x=_to_mm(getattr(t, "x2", 0)),
                end_y=_to_mm(getattr(t, "y2", 0)),
                width=_to_mm(getattr(t, "width", 0)),
                layer=str(getattr(t, "layer", "F.Cu")),
            ))
        except Exception:
            continue

    return board
