"""Data model for PCB boards.

All coordinates are in millimetres, matching KiCad's internal units.
"""
from dataclasses import dataclass, field
import math
from typing import List, Optional


@dataclass
class Pad:
    number: str
    x: float
    y: float
    width: float
    height: float
    shape: str = "rect"
    layers: List[str] = field(default_factory=list)
    net: Optional[str] = None
    hole_diameter: float = 0.0
    rotation: float = 0.0


@dataclass
class Component:
    reference: str          # e.g. "R1"
    value: str              # e.g. "10k"
    footprint: str          # e.g. "Resistor_SMD:R_0805_2012Metric"
    x: float
    y: float
    rotation: float = 0.0
    layer: str = "F.Cu"
    pads: List[Pad] = field(default_factory=list)
    reference_x: Optional[float] = None
    reference_y: Optional[float] = None
    value_x: Optional[float] = None
    value_y: Optional[float] = None


def pad_board_position(comp: Component, pad: Pad) -> tuple:
    """Return physical pad coordinates in board mm.

    Pad offsets are local footprint coordinates. Apply component rotation in
    screen coordinates (positive angle rotates toward +Y), reflect local X for
    bottom-side footprints, then translate by the component origin. The viewer
    uses this same helper before its independent whole-board bottom-view flip.
    """
    x = -pad.x if str(comp.layer).startswith("B.") else pad.x
    y = pad.y
    angle = math.radians(comp.rotation or 0.0)
    return (comp.x + x * math.cos(angle) - y * math.sin(angle),
            comp.y + x * math.sin(angle) + y * math.cos(angle))


@dataclass
class Track:
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    width: float
    layer: str
    component_ref: Optional[str] = None
    net: Optional[str] = None


@dataclass
class Via:
    x: float
    y: float
    size: float
    drill: float
    layers: List[str] = field(default_factory=list)
    net: Optional[str] = None


@dataclass
class BoardOutline:
    """Simple polyline outline; edges may be non-closed."""
    segments: List[tuple] = field(default_factory=list)  # [(x1,y1,x2,y2), ...]


@dataclass
class BoardZone:
    """Filled copper polygon in board coordinates."""
    points: List[tuple] = field(default_factory=list)
    layer: str = "B.Cu"
    net: Optional[str] = None


@dataclass
class Board:
    version: str = ""
    components: List[Component] = field(default_factory=list)
    tracks: List[Track] = field(default_factory=list)
    outline: BoardOutline = field(default_factory=BoardOutline)
    zones: List[BoardZone] = field(default_factory=list)
    layers: List[str] = field(default_factory=list)
    vias: List[Via] = field(default_factory=list)

    def bounds(self):
        """Return (min_x, min_y, max_x, max_y) covering all geometry, or None."""
        xs, ys = [], []
        for c in self.components:
            xs.append(c.x); ys.append(c.y)
        for t in self.tracks:
            xs.extend([t.start_x, t.end_x]); ys.extend([t.start_y, t.end_y])
        for x1, y1, x2, y2 in self.outline.segments:
            xs.extend([x1, x2]); ys.extend([y1, y2])
        for zone in self.zones:
            for x, y in zone.points:
                xs.append(x); ys.append(y)
        if not xs:
            return None
        return (min(xs), min(ys), max(xs), max(ys))

    def find_component(self, reference: str) -> Optional[Component]:
        for c in self.components:
            if c.reference == reference:
                return c
        return None
