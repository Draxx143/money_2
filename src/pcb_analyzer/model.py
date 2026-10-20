"""Data model for PCB boards.

All coordinates are in millimetres, matching KiCad's internal units.
"""
from dataclasses import dataclass, field
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


@dataclass
class Track:
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    width: float
    layer: str


@dataclass
class BoardOutline:
    """Simple polyline outline; edges may be non-closed."""
    segments: List[tuple] = field(default_factory=list)  # [(x1,y1,x2,y2), ...]


@dataclass
class Board:
    version: str = ""
    components: List[Component] = field(default_factory=list)
    tracks: List[Track] = field(default_factory=list)
    outline: BoardOutline = field(default_factory=BoardOutline)
    layers: List[str] = field(default_factory=list)

    def bounds(self):
        """Return (min_x, min_y, max_x, max_y) covering all geometry, or None."""
        xs, ys = [], []
        for c in self.components:
            xs.append(c.x); ys.append(c.y)
        for t in self.tracks:
            xs.extend([t.start_x, t.end_x]); ys.extend([t.start_y, t.end_y])
        for x1, y1, x2, y2 in self.outline.segments:
            xs.extend([x1, x2]); ys.extend([y1, y2])
        if not xs:
            return None
        return (min(xs), min(ys), max(xs), max(ys))

    def find_component(self, reference: str) -> Optional[Component]:
        for c in self.components:
            if c.reference == reference:
                return c
        return None
