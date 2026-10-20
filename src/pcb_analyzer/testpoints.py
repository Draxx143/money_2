"""Test-point records and persistent JSON storage."""
import json
import math
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

    __test__ = False  # unittest/pytest should not collect this data class.

    @classmethod
    def from_dict(cls, d):
        """Build a point from legacy or partially malformed JSON."""
        if not isinstance(d, dict):
            raise ValueError("test point entry must be an object")
        defaults = cls()
        fields = ("id", "label", "reference", "pad_number", "net", "expected_value",
                  "actual_value", "unit", "tolerance", "instrument", "notes", "source",
                  "timestamp")
        values = {}
        for name in fields:
            value = d.get(name)
            if value is None:
                value = getattr(defaults, name)
            values[name] = value if isinstance(value, str) else str(value)
        for name in ("x", "y"):
            try:
                value = float(d[name]) if d.get(name) is not None else None
                values[name] = value if value is None or math.isfinite(value) else None
            except (TypeError, ValueError, OverflowError):
                values[name] = None
        category = d.get("category")
        values["category"] = category if category in ALL_CATEGORIES else defaults.category
        status = d.get("status")
        values["status"] = status if status in ALL_STATUSES else defaults.status
        return cls(**values)



class TestPointStore:
    __test__ = False
    """In-memory store with JSON persistence.

    Each board file may have a companion file named
    ``<board-basename>.testpoints.json``. Callers may also save explicitly.
    """

    def __init__(self):
        self._points: List[TestPoint] = []
        self._path: Optional[str] = None
        self.skipped = 0

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
        self.skipped = 0

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
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            os.replace(tmp, path)
            self._path = path
        finally:
            try:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            except OSError:
                pass

    def load(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid test point file: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("Invalid test point file: expected a JSON object")
        points = payload.get("points")
        if not isinstance(points, list):
            raise ValueError("Invalid test point file: 'points' must be a list")
        valid, self.skipped = [], 0
        for entry in points:
            if not isinstance(entry, dict):
                self.skipped += 1
                continue
            valid.append(TestPoint.from_dict(entry))
        self._points, self._path = valid, path

    def load_if_exists(self, board_path: str) -> bool:
        path = self.companion_path_for_board(board_path)
        if os.path.isfile(path):
            try:
                self.load(path)
            except ValueError:
                self.clear()
                self._path = path
                raise
            return True
        self.clear()
        self._path = path
        return False
