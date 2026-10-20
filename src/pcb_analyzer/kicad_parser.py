"""Parser for KiCad .kicad_pcb files (S-expression format, KiCad 6/7/8)."""
import re
import math
from typing import List, Union

from .model import Board, Component, Pad, Track, Via


class SexpError(ValueError):
    pass


def parse_sexpr(text: str) -> list:
    """Parse an S-expression into nested Python lists of strings."""
    tokens = re.findall(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()]+', text)
    pos = 0

    def parse():
        nonlocal pos
        if pos >= len(tokens):
            raise SexpError("unexpected end of input")
        tok = tokens[pos]
        if tok == "(":
            pos += 1
            items = []
            while pos < len(tokens) and tokens[pos] != ")":
                items.append(parse())
            if pos >= len(tokens):
                raise SexpError("unbalanced parentheses")
            pos += 1  # skip ')'
            return items
        if tok == ")":
            raise SexpError("unexpected ')'")
        pos += 1
        if tok.startswith('"') and tok.endswith('"'):
            return tok[1:-1]
        return tok

    result = parse()
    return result


def _children(node: list, name: str) -> List[list]:
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


def _child(node: list, name: str):
    for c in node:
        if isinstance(c, list) and c and c[0] == name:
            return c
    return None


def _atom(node: list, idx: int, default=None):
    if len(node) > idx:
        return node[idx]
    return default


def _floats(node: list, start: int, count: int) -> List[float]:
    out = []
    for i in range(count):
        v = _atom(node, start + i)
        if v is None:
            raise SexpError(f"expected {count} numbers in {node[0]}")
        out.append(float(v))
    return out


def parse_pcb(path: str) -> Board:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return parse_pcb_text(text)


def parse_pcb_text(text: str) -> Board:
    root = parse_sexpr(text)
    if not root or root[0] != "kicad_pcb":
        raise SexpError("not a kicad_pcb file")

    board = Board()

    ver = _child(root, "version")
    if ver and len(ver) > 1:
        board.version = str(ver[1])

    # Layers
    layers = _child(root, "layers")
    if layers:
        for entry in layers[1:]:
            if isinstance(entry, list) and len(entry) >= 2:
                board.layers.append(entry[1])

    net_names = {}
    for net in _children(root, "net"):
        if len(net) > 2:
            net_names[str(net[1])] = str(net[2])

    # Footprints (modern and legacy KiCad 5 nodes).
    for fp in _children(root, "footprint") + _children(root, "module"):
        try:
            comp = _parse_footprint(fp)
            if comp:
                board.components.append(comp)
        except (ValueError, TypeError, IndexError):
            continue

    # Segments (tracks)
    for seg in _children(root, "segment"):
        try:
            start = _child(seg, "start")
            end = _child(seg, "end")
            width = _child(seg, "width")
            layer = _child(seg, "layer")
            if not (start and end and width and layer):
                continue
            sx, sy = _floats(start, 1, 2)
            ex, ey = _floats(end, 1, 2)
            w = float(width[1])
            net_node = _child(seg, "net")
            net = net_names.get(str(net_node[1]), str(net_node[1])) if net_node and len(net_node) > 1 else None
            board.tracks.append(Track(sx, sy, ex, ey, w, str(layer[1]), net=net))
        except (SexpError, ValueError, IndexError):
            continue

    for via in _children(root, "via"):
        try:
            at, size, drill, layers, net_node = (_child(via, key) for key in
                                                  ("at", "size", "drill", "layers", "net"))
            if not (at and size and drill):
                continue
            x, y = _floats(at, 1, 2)
            net = net_names.get(str(net_node[1]), str(net_node[1])) if net_node and len(net_node) > 1 else None
            board.vias.append(Via(x, y, float(size[1]), float(drill[1]),
                                  [str(v) for v in layers[1:]] if layers else [], net))
        except (ValueError, TypeError, IndexError, SexpError):
            continue

    # Board outline from Edge.Cuts gr_line / gr_rect
    for gr in _children(root, "gr_line"):
        layer = _child(gr, "layer")
        if not layer or layer[1] != "Edge.Cuts":
            continue
        start = _child(gr, "start")
        end = _child(gr, "end")
        if start and end:
            x1, y1 = _floats(start, 1, 2)
            x2, y2 = _floats(end, 1, 2)
            board.outline.segments.append((x1, y1, x2, y2))

    for gr in _children(root, "gr_circle"):
        layer = _child(gr, "layer")
        center, end = _child(gr, "center"), _child(gr, "end")
        if not layer or len(layer) < 2 or layer[1] != "Edge.Cuts" or not (center and end):
            continue
        try:
            cx, cy = _floats(center, 1, 2); ex, ey = _floats(end, 1, 2)
            radius = math.hypot(ex - cx, ey - cy)
            points = [(cx + radius * math.cos(i * math.pi / 36),
                       cy + radius * math.sin(i * math.pi / 36)) for i in range(73)]
            board.outline.segments.extend((a[0], a[1], b[0], b[1]) for a, b in zip(points, points[1:]))
        except (ValueError, IndexError, SexpError):
            continue

    for gr in _children(root, "gr_poly"):
        layer, pts = _child(gr, "layer"), _child(gr, "pts")
        if not layer or len(layer) < 2 or layer[1] != "Edge.Cuts" or not pts:
            continue
        try:
            points = [_floats(xy, 1, 2) for xy in _children(pts, "xy")]
            board.outline.segments.extend((a[0],a[1],b[0],b[1]) for a,b in zip(points, points[1:] + points[:1]))
        except (ValueError, IndexError, SexpError):
            continue

    for gr in _children(root, "gr_arc") + _children(root, "gr_curve"):
        layer = _child(gr, "layer")
        if not layer or len(layer) < 2 or layer[1] != "Edge.Cuts":
            continue
        try:
            pts = [_child(gr, key) for key in ("start", "mid", "end")]
            pts = [_floats(point, 1, 2) for point in pts if point]
            board.outline.segments.extend((a[0],a[1],b[0],b[1]) for a,b in zip(pts, pts[1:]))
        except (ValueError, IndexError, SexpError):
            continue

    for gr in _children(root, "gr_rect"):
        layer = _child(gr, "layer")
        if not layer or layer[1] != "Edge.Cuts":
            continue
        start = _child(gr, "start")
        end = _child(gr, "end")
        if start and end:
            x1, y1 = _floats(start, 1, 2)
            x2, y2 = _floats(end, 1, 2)
            board.outline.segments.extend([
                (x1, y1, x2, y1),
                (x2, y1, x2, y2),
                (x2, y2, x1, y2),
                (x1, y2, x1, y1),
            ])

    return board


def _parse_footprint(fp: list):
    at = _child(fp, "at")
    if not at:
        return None
    try:
        x, y = _floats(at, 1, 2)
        rot = float(at[3]) if len(at) > 3 else 0.0
    except (SexpError, ValueError, IndexError):
        return None

    layer_node = _child(fp, "layer")
    layer = str(layer_node[1]) if layer_node and len(layer_node) > 1 else "F.Cu"

    reference = ""
    value = ""
    for t in _children(fp, "fp_text"):
        if len(t) < 3:
            continue
        kind = t[1]
        content = t[2]
        if kind == "reference":
            reference = content
        elif kind == "value":
            value = content

    if not reference:
        # Fallback: search property "Reference"
        for p in _children(fp, "property"):
            if len(p) >= 3 and p[1] == "Reference":
                reference = p[2]
                break
    if not value:
        for p in _children(fp, "property"):
            if len(p) >= 3 and p[1] == "Value":
                value = p[2]
                break

    comp = Component(
        reference=reference or "(unnamed)",
        value=value,
        footprint=str(_atom(fp, 1, "")),
        x=x, y=y, rotation=rot, layer=layer,
    )

    for pad in _children(fp, "pad"):
        parsed = _parse_pad(pad)
        if parsed:
            comp.pads.append(parsed)

    return comp


def _parse_pad(pad: list):
    try:
        number = str(pad[1])
        shape = str(pad[2])
    except IndexError:
        return None
    at = _child(pad, "at")
    size = _child(pad, "size")
    if not at or not size:
        return None
    try:
        px, py = _floats(at, 1, 2)
        rotation = float(at[3]) if len(at) > 3 else 0.0
        w, h = _floats(size, 1, 2)
    except (SexpError, ValueError, IndexError):
        return None

    layers_node = _child(pad, "layers")
    layers = [str(x) for x in layers_node[1:]] if layers_node else []

    net_node = _child(pad, "net")
    net = str(net_node[1]) if net_node and len(net_node) > 1 else None
    drill_node = _child(pad, "drill")
    try:
        drill = float(drill_node[1]) if drill_node and len(drill_node) > 1 else 0.0
    except (ValueError, TypeError):
        drill = 0.0

    return Pad(number=number, x=px, y=py, width=w, height=h,
               shape=shape, layers=layers, net=net, hole_diameter=drill, rotation=rotation)
