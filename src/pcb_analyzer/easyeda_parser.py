"""Reader for EasyEDA Standard PCB JSON exports (docType 3)."""
import json
import re
from pathlib import Path
from typing import Optional

from .model import Board, BoardZone, Component, Pad, Track

# EasyEDA PCB coordinate units are 0.254 mm (10 mil) each.
UNIT_MM = 0.254
LAYER_NAMES = {
    "1": "F.Cu",
    "2": "B.Cu",
    "3": "F.SilkS",
    "4": "B.SilkS",
    "5": "F.Paste",
    "6": "B.Paste",
    "7": "F.Mask",
    "8": "B.Mask",
    "10": "Edge.Cuts",
    "11": "Multi-Layer",
    "99": "ComponentShapeLayer",
    "100": "LeadShapeLayer",
}


def parse_easyeda_json(path: str) -> Board:
    """Load a native EasyEDA Standard PCB JSON file into the common model."""
    try:
        with open(path, "r", encoding="utf-8") as source:
            document = json.load(source)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read EasyEDA PCB JSON: {exc}") from exc

    if not isinstance(document, dict) or document.get("head", {}).get("docType") != "3":
        raise ValueError("Unsupported JSON file: expected an EasyEDA Standard PCB export")

    board = Board(version="easyeda-json")
    raw_tracks = []
    raw_zones = []
    for shape in document.get("shape", []):
        if not isinstance(shape, str):
            continue
        record = shape.split("~", 1)[0]
        if record == "TRACK":
            fields = shape.split("~")
            if len(fields) < 6:
                continue
            width, layer_id, net = fields[1], fields[2], fields[3]
            points = _number_pairs(fields[4])
            if len(points) < 2:
                continue
            if layer_id == "10":
                for a, b in zip(points, points[1:]):
                    board.outline.segments.append((*_point(a), *_point(b)))
            else:
                for a, b in zip(points, points[1:]):
                    raw_tracks.append((a, b, _float(width), _layer(layer_id), None, net))
        elif record == "SOLIDREGION":
            fields = shape.split("~", 5)
            if len(fields) < 4:
                continue
            layer_id, net, path_data = fields[1], fields[2], fields[3]
            if layer_id in ("1", "2") and net and "cutout" not in shape.lower():
                points = _path_points(path_data)
                if len(points) >= 3:
                    raw_zones.append((points, _layer(layer_id), net))
        elif record == "LIB":
            component, component_tracks = _parse_lib(shape)
            if component is None:
                continue
            board.components.append(component)
            raw_tracks.extend(component_tracks)

    for points, layer, net in raw_zones:
        board.zones.append(BoardZone(
            points=[_point(point) for point in points], layer=layer, net=net
        ))

    board.tracks.extend(Track(
        start_x=_point(start)[0], start_y=_point(start)[1],
        end_x=_point(end)[0], end_y=_point(end)[1],
        width=width * UNIT_MM, layer=layer, component_ref=owner,
    ) for start, end, width, layer, owner, _net in raw_tracks)

    # EasyEDA stores a large canvas origin. Shift the board to a local origin
    # so the component inspector and measurement readouts remain useful.
    all_x, all_y = [], []
    for component in board.components:
        all_x.append(component.x); all_y.append(component.y)
        if component.reference_x is not None:
            all_x.append(component.reference_x); all_y.append(component.reference_y)
        if component.value_x is not None:
            all_x.append(component.value_x); all_y.append(component.value_y)
    for track in board.tracks:
        all_x.extend((track.start_x, track.end_x))
        all_y.extend((track.start_y, track.end_y))
    for x1, y1, x2, y2 in board.outline.segments:
        all_x.extend((x1, x2)); all_y.extend((y1, y2))
    for zone in board.zones:
        for x, y in zone.points:
            all_x.append(x); all_y.append(y)
    if all_x and all_y:
        x_origin, y_origin = min(all_x), min(all_y)
        for component in board.components:
            component.x -= x_origin
            component.y -= y_origin
            if component.reference_x is not None:
                component.reference_x -= x_origin
                component.reference_y -= y_origin
            if component.value_x is not None:
                component.value_x -= x_origin
                component.value_y -= y_origin
        for track in board.tracks:
            track.start_x -= x_origin; track.end_x -= x_origin
            track.start_y -= y_origin; track.end_y -= y_origin
        board.outline.segments = [
            (x1-x_origin, y1-y_origin, x2-x_origin, y2-y_origin)
            for x1, y1, x2, y2 in board.outline.segments
        ]
        for zone in board.zones:
            zone.points = [(x-x_origin, y-y_origin) for x, y in zone.points]

    board.layers = sorted({t.layer for t in board.tracks} |
                          {p.layers[0] for c in board.components for p in c.pads if p.layers})
    return board


def _parse_lib(shape: str):
    parts = shape.split("#@$")
    header = parts[0].split("~")
    if len(header) < 8:
        return None, []
    x, y = _float(header[1]) * UNIT_MM, -_float(header[2]) * UNIT_MM
    package = ""
    package_match = re.search(r"package`([^`]*)`", header[3])
    if package_match:
        package = package_match.group(1)
    layer_id = header[7]
    component = Component(
        reference="", value="", footprint=package, x=x, y=y,
        rotation=_float(header[4]), layer=_layer(layer_id),
    )
    raw_tracks = []
    label_values = []

    for item in parts[1:]:
        fields = item.split("~")
        kind = fields[0] if fields else ""
        if kind == "TEXT" and len(fields) > 10:
            label_kind = fields[1]
            label_x = _float(fields[2]) * UNIT_MM
            label_y = -_float(fields[3]) * UNIT_MM
            text = fields[10]
            if label_kind == "P":
                component.reference = text
                component.reference_x, component.reference_y = label_x, label_y
            elif label_kind == "N":
                component.value = text
                component.value_x, component.value_y = label_x, label_y
        elif kind == "PAD" and len(fields) > 9:
            pad_type = fields[1].upper()
            pad_x, pad_y = _float(fields[2]), _float(fields[3])
            layer = _layer(fields[6])
            hole = _float(fields[9]) * UNIT_MM
            component.pads.append(Pad(
                number=fields[8],
                x=(pad_x * UNIT_MM - component.x),
                y=(-pad_y * UNIT_MM - component.y),
                width=_float(fields[4]) * UNIT_MM,
                height=_float(fields[5]) * UNIT_MM,
                shape="circle" if pad_type == "ELLIPSE" else "rect",
                layers=[layer],
                net=fields[7] or None,
                hole_diameter=hole,
            ))
        elif kind == "TRACK" and len(fields) > 5:
            width, layer_id = _float(fields[1]), fields[2]
            coords = _number_pairs(fields[4])
            layer = _layer(layer_id)
            if len(coords) >= 2:
                raw_tracks.extend((a, b, width, layer, component.reference, "")
                                  for a, b in zip(coords, coords[1:]))

    # LIB subrecords put the designator text after the header. Resolve the
    # placeholder owner now, once the component reference has been read.
    raw_tracks = [(*track[:4], component.reference, track[5]) for track in raw_tracks]
    return component, raw_tracks


def _number_pairs(value: str):
    try:
        numbers = [float(item) for item in value.replace(",", " ").split()]
    except ValueError:
        return []
    return list(zip(numbers[::2], numbers[1::2]))


def _path_points(path_data: str):
    # EasyEDA paths are a compact sequence of M/L commands; curve commands are
    # ignored rather than inventing geometry where unsupported.
    return [(float(x), float(y)) for x, y in re.findall(
        r"[ML]\s*([-+]?\d*\.?\d+)\s*[, ]\s*([-+]?\d*\.?\d+)", path_data
    )]


def _point(point):
    # EasyEDA JSON coordinates use a bottom-up board Y axis; Cairo's canvas is
    # top-down, so reflect Y here before translating the board origin.
    return point[0] * UNIT_MM, -point[1] * UNIT_MM


def _layer(layer_id: str) -> str:
    return LAYER_NAMES.get(str(layer_id), f"EasyEDA:{layer_id}")


def _float(value: Optional[str]) -> float:
    try:
        return float(value or 0)
    except (ValueError, TypeError):
        return 0.0
