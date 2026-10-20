"""Test-point records and persistent JSON storage."""
import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


STATUS_NOT_TESTED = "Not Tested"
STATUS_PASS = "Pass"
STATUS_FAIL = "Fail"
STATUS_UNKNOWN = "Unknown"

ALL_STATUSES = (STATUS_NOT_TESTED, STATUS_PASS, STATUS_FAIL, STATUS_UNKNOWN)

CATEGORY_GENERIC = "Generic"
CATEGORY_VOLTAGE = "Voltage"
CATEGORY_RESISTANCE = "Resistance"
CATEGORY_CONTINUITY = "Continuity"
CATEGORY_DIODE = "Diode"
CATEGORY_CURRENT = "Current"
CATEGORY_OTHER = "Other"

ALL_CATEGORIES = (
    CATEGORY_GENERIC, CATEGORY_VOLTAGE, CATEGORY_RESISTANCE,
    CATEGORY_CONTINUITY, CATEGORY_DIODE, CATEGORY_CURRENT, CATEGORY_OTHER,
)


@dataclass
class TestPoint:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    label: str = ""
    reference: str = ""            # component reference, e.g. "U1"
    pad_number: str = ""           # pad identifier, e.g. "3"
    net: str = ""                  # net name, if known
    x: Optional[float] = None      # board coordinates in mm, if known
    y: Optional[float] = None
    category: str = CATEGORY_GENERIC
    expected_value: str = ""
    actual_value: str = ""
    unit: str = ""
    tolerance: str = ""
    status: str = STATUS_NOT_TESTED
    instrument: str = ""
    notes: str = ""
    source: str = "manual"         # manual | imported | measured
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        known = {f: d.get(f) for f in (
            "id", "label", "reference", "pad_number", "net", "x", "y",
            "category", "expected_value", "actual_value", "unit", "tolerance",
            "status", "instrument", "notes", "source", "timestamp",
        )}
        if not known["id"]:
            known["id"] = str(uuid.uuid4())
        return cls(**known)


class TestPointStore:
    """In-memory store with JSON persistence.

    Each board file may have a companion file named
    ``<board-basename>.testpoints.json``. Callers may also save explicitly.
    """

    def __init__(self):
        self._points: List[TestPoint] = []
        self._path: Optional[str] = None

    # ---- Iteration / lookup ----
    def __len__(self):
        return len(self._points)

    def __iter__(self):
        return iter(self._points)

    def all(self) -> List[TestPoint]:
        return list(self._points)

    def get(self, tp_id: str) -> Optional[TestPoint]:
        for p in self._points:
            if p.id == tp_id:
                return p
        return None

    def find_by_reference(self, reference: str) -> List[TestPoint]:
        return [p for p in self._points if p.reference == reference]

    # ---- Mutation ----
    def add(self, tp: TestPoint):
        if not tp.id:
            tp.id = str(uuid.uuid4())
        self._points.append(tp)

    def update(self, tp: TestPoint):
        for i, p in enumerate(self._points):
            if p.id == tp.id:
                self._points[i] = tp
                return
        # If not found, treat as add.
        self._points.append(tp)

    def delete(self, tp_id: str) -> bool:
        before = len(self._points)
        self._points = [p for p in self._points if p.id != tp_id]
        return len(self._points) < before

    def clear(self):
        self._points = []

    # ---- Persistence ----
    @property
    def path(self) -> Optional[str]:
        return self._path

    @staticmethod
    def companion_path_for_board(board_path: str) -> str:
        base, _ext = os.path.splitext(board_path)
        return base + ".testpoints.json"

    def save(self, path: str):
        payload = {
            "version": 1,
            "points": [p.to_dict() for p in self._points],
        }
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
        self._path = path

    def load(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        points = payload.get("points", [])
        self._points = [TestPoint.from_dict(d) for d in points]
        self._path = path

    def load_if_exists(self, board_path: str) -> bool:
        path = self.companion_path_for_board(board_path)
        if os.path.isfile(path):
            self.load(path)
            return True
        self.clear()
        self._path = path
        return False
