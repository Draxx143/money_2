"""Parser for Altium .PcbDoc files using altium-monkey.

Tries to load the .PcbDoc directly first. Falls back to loading via a
project file (.PrjPcb) if direct loading is not supported by the
installed version of altium-monkey.
"""
import os
import logging
from typing import Optional

try:
    from altium_monkey import AltiumDesign, AltiumPcbDoc
    HAS_ALTIUM = True
except ImportError:
    HAS_ALTIUM = False
    AltiumDesign = None
    AltiumPcbDoc = None

from .model import Board, BoardZone, Component, Pad, Track

logger = logging.getLogger(__name__)


class AltiumParserError(Exception):
    pass


def parse_pcbdoc(path: str) -> Board:
    """Parse an Altium .PcbDoc (or .PrjPcb) and return a Board."""
    if not os.path.isfile(path):
        raise AltiumParserError(f"File not found: {path}")

    # Altium ASCII exports are often given a .PcbDoc suffix. They can be read
    # without altium-monkey; binary OLE PcbDoc files still use the library.
    with open(path, "rb") as source:
        header = source.read(128)
    if header.lstrip().startswith(b"|RECORD="):
        return _parse_ascii_pcbdoc(path)

    if not HAS_ALTIUM:
        raise AltiumParserError(
            "altium-monkey is required for binary Altium PcbDoc files. "
            "Install altium-monkey or export the board as Altium ASCII."
        )

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
        except Exception as direct_exc:  # Try the documented project-loader fallback.
            logger.warning("Direct Altium loading failed; trying fallback: %s", direct_exc)
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


def _parse_ascii_pcbdoc(path: str) -> Board:
    """Parse Altium's pipe-delimited ASCII board export."""
    board = Board(version="altium-ascii")
    components_by_id = {}
    net_names = {}
    tracks = []
    pads = []
    regions = []
    text_values = {}
    label_positions = {}

    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as source:
            lines = source
            for line in lines:
                if not line.startswith("|RECORD="):
                    continue
                fields = {}
                for field in line.rstrip("\r\n").split("|")[1:]:
                    key, separator, value = field.partition("=")
                    if separator:
                        fields[key.upper()] = value
                record = fields.get("RECORD", "").lower()

                if record == "net":
                    net_names[fields.get("ID", "")] = fields.get("NAME", "")
                elif record == "component":
                    cid = fields.get("ID", "")
                    if not cid:
                        continue
                    component = Component(
                        reference=fields.get("SOURCEDESIGNATOR", cid),
                        value="",
                        footprint=fields.get("PATTERN", ""),
                        x=_ascii_mm(fields.get("X")),
                        y=_ascii_mm(fields.get("Y")),
                        rotation=_ascii_float(fields.get("ROTATION")),
                        layer=_ascii_layer(fields.get("LAYER", "TOP")),
                    )
                    components_by_id[cid] = component
                    board.components.append(component)
                elif record == "text" and fields.get("COMPONENT") is not None:
                    cid = fields["COMPONENT"]
                    if fields.get("COMMENT", "").upper() == "TRUE":
                        text_values[cid] = _decode_widestring(fields.get("WIDESTRING", ""))
                        label_positions[(cid, "value")] = (
                            _ascii_mm(fields.get("X")), _ascii_mm(fields.get("Y"))
                        )
                    elif fields.get("DESIGNATOR", "").upper() == "TRUE":
                        if cid in components_by_id:
                            components_by_id[cid].reference = _decode_widestring(
                                fields.get("WIDESTRING", "")
                            ) or components_by_id[cid].reference
                            label_positions[(cid, "reference")] = (
                                _ascii_mm(fields.get("X")), _ascii_mm(fields.get("Y"))
                            )
                elif record == "pad":
                    pads.append(fields)
                elif record == "track":
                    if fields.get("POLYGONOUTLINE", "FALSE").upper() == "TRUE":
                        board.outline.segments.append((
                            _ascii_mm(fields.get("X1")), _ascii_mm(fields.get("Y1")),
                            _ascii_mm(fields.get("X2")), _ascii_mm(fields.get("Y2")),
                        ))
                    elif all(key in fields for key in ("X1", "Y1", "X2", "Y2")):
                        tracks.append(fields)
                elif record == "region":
                    regions.append(fields)
    except OSError as exc:
        raise AltiumParserError(f"Could not read Altium ASCII board: {exc}") from exc

    if not board.components and not tracks and not pads:
        raise AltiumParserError("File is not a supported Altium ASCII PCB export")

    for cid, component in components_by_id.items():
        if cid in text_values:
            component.value = text_values[cid]
        if (cid, "reference") in label_positions:
            component.reference_x, component.reference_y = label_positions[(cid, "reference")]
        if (cid, "value") in label_positions:
            component.value_x, component.value_y = label_positions[(cid, "value")]

    for fields in pads:
        component = components_by_id.get(fields.get("COMPONENT", ""))
        if component is None:
            continue
        width = _ascii_mm(fields.get("XSIZE"))
        height = _ascii_mm(fields.get("YSIZE"))
        component.pads.append(Pad(
            number=fields.get("NAME", ""),
            x=_ascii_mm(fields.get("X")) - component.x,
            y=_ascii_mm(fields.get("Y")) - component.y,
            width=width,
            height=height,
            shape=_ascii_pad_shape(fields.get("SHAPE", "")),
            layers=[_ascii_layer(fields.get("LAYER", "TOP"))],
            net=net_names.get(fields.get("NET", "")),
            hole_diameter=_ascii_mm(fields.get("HOLESIZE")),
        ))

    # Filled copper is stored in shape-based Region records. Without these,
    # a board with copper pours looks like bare traces and does not match the
    # rendered PCB in Altium/KiCad.
    for fields in regions:
        layer = _ascii_layer(fields.get("LAYER", ""))
        if layer not in ("F.Cu", "B.Cu") or "NET" not in fields:
            continue
        try:
            count = int(fields.get("MAINCONTOURVERTEXCOUNT", "0"))
        except ValueError:
            continue
        points = []
        for index in range(count):
            x_key, y_key = f"VX{index}", f"VY{index}"
            if x_key not in fields or y_key not in fields:
                points = []
                break
            points.append((_ascii_mm(fields[x_key]), _ascii_mm(fields[y_key])))
        if len(points) >= 3:
            board.zones.append(BoardZone(
                points=points,
                layer=layer,
                net=net_names.get(fields.get("NET", "")),
            ))

    board.tracks.extend(Track(
        start_x=_ascii_mm(item.get("X1")),
        start_y=_ascii_mm(item.get("Y1")),
        end_x=_ascii_mm(item.get("X2")),
        end_y=_ascii_mm(item.get("Y2")),
        width=_ascii_mm(item.get("WIDTH")),
        layer=_ascii_layer(item.get("LAYER", "TOP")),
        component_ref=(components_by_id.get(item.get("COMPONENT", "")).reference
                       if item.get("COMPONENT", "") in components_by_id else None),
    ) for item in tracks)
    board.layers = sorted({item.layer for item in board.tracks} | {
        pad.layers[0] for component in board.components for pad in component.pads
    })
    return board



def _ascii_mm(value: Optional[str]) -> float:
    """Convert an Altium ASCII dimension (normally mils) to millimetres."""
    if not value:
        return 0.0
    text = value.strip()
    try:
        if text.lower().endswith("mil"):
            return float(text[:-3]) * 0.0254
        if text.lower().endswith("mm"):
            return float(text[:-2])
        return float(text) * 0.0254
    except ValueError:
        return 0.0


def _ascii_float(value: Optional[str]) -> float:
    try:
        return float(value or 0)
    except ValueError:
        return 0.0


def _ascii_layer(name: str) -> str:
    return {
        "TOP": "F.Cu", "BOTTOM": "B.Cu",
        "TOPOVERLAY": "F.SilkS", "BOTTOMOVERLAY": "B.SilkS",
        "MULTILAYER": "Multi-Layer", "MULTI-LAYER": "Multi-Layer",
    }.get(name.upper(), name)


def _ascii_pad_shape(shape: str) -> str:
    normalized = shape.upper()
    if "ROUND" in normalized or "CIRCLE" in normalized:
        return "circle"
    if "OVAL" in normalized:
        return "oval"
    return "rect"


def _decode_widestring(value: str) -> str:
    try:
        return "".join(chr(int(code)) for code in value.split(",") if code)
    except (ValueError, OverflowError):
        return ""


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
                except Exception as exc:  # Third-party object may have incomplete attributes.
                    logger.warning("Skipping malformed Altium pad: %s", exc)
                    continue
            board.components.append(c)
        except Exception as exc:  # Skip malformed third-party geometry records.
            logger.warning("Skipping malformed Altium component/track: %s", exc)
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
        except Exception as exc:  # Skip malformed third-party geometry records.
            logger.warning("Skipping malformed Altium component/track: %s", exc)
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
                except Exception as exc:  # Third-party object may have incomplete attributes.
                    logger.warning("Skipping malformed Altium pad: %s", exc)
                    continue
            board.components.append(c)
        except Exception as exc:  # Skip malformed third-party geometry records.
            logger.warning("Skipping malformed Altium component/track: %s", exc)
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
        except Exception as exc:  # Skip malformed third-party geometry records.
            logger.warning("Skipping malformed Altium component/track: %s", exc)
            continue

    return board
