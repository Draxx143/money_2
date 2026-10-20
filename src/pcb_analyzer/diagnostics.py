"""Deterministic diagnostic rules for test points.

These rules are intentionally simple and transparent. They never assert that
a component is faulty; they only report whether a recorded measurement is
consistent with the expected value under the stated tolerance.
"""
from typing import Optional, Tuple

from .model import pad_board_position
from .engineering import (
    expected_range,
    fmt_engineering,
    parse_tolerance,
    parse_value,
    within_tolerance,
)
from .testpoints import (
    STATUS_FAIL, STATUS_NOT_TESTED, STATUS_PASS, STATUS_UNKNOWN, TestPoint,
)


DEFAULT_TOLERANCE_PCT = 5.0


def evaluate_testpoint(tp: TestPoint) -> Tuple[str, str]:
    """Return (status, reason) for a single test point.

    Status is one of STATUS_PASS, STATUS_FAIL, STATUS_UNKNOWN, or
    STATUS_NOT_TESTED. Reason is a short human-readable string.
    """
    if not tp.actual_value.strip():
        return STATUS_NOT_TESTED, "No measurement recorded yet."

    if not tp.expected_value.strip():
        return STATUS_UNKNOWN, "No expected value provided."

    measured = parse_value(tp.actual_value)
    expected = parse_value(tp.expected_value)
    if measured is None:
        return STATUS_UNKNOWN, f"Cannot parse actual value '{tp.actual_value}'."
    if expected is None:
        return STATUS_UNKNOWN, f"Cannot parse expected value '{tp.expected_value}'."

    tol = parse_tolerance(tp.tolerance)
    if tol is None:
        tol = DEFAULT_TOLERANCE_PCT

    unit = tp.unit or ""
    ok = within_tolerance(measured, expected, tol)
    low, high = expected_range(expected, tol)

    zero_note = (f" Zero expected value uses absolute tolerance {tol / 100.0:g} {unit}."
                 if expected == 0 else "")
    if ok:
        return STATUS_PASS, (
            f"Measured {fmt_engineering(measured, unit)} is within "
            f"{fmt_engineering(low, unit)}–{fmt_engineering(high, unit)} "
            f"(expected {fmt_engineering(expected, unit)} ±{tol:g}%).{zero_note}"
        )
    return STATUS_FAIL, (
        f"Measured {fmt_engineering(measured, unit)} is outside "
        f"{fmt_engineering(low, unit)}–{fmt_engineering(high, unit)} "
        f"(expected {fmt_engineering(expected, unit)} ±{tol:g}%).{zero_note}"
    )


def suggest_testpoints_for_component(board, ref: str) -> list:
    """Return skeleton TestPoint objects (one per pad) for the given component.

    All fields except reference, pad_number, net, x and y are left blank so
    that the user must supply expected values. Coordinates are resolved from
    the component position and the pad offset.
    """
    if board is None:
        return []
    comp = board.find_component(ref)
    if comp is None:
        return []

    suggestions = []
    for pad in comp.pads:
        tp = TestPoint()
        tp.reference = comp.reference
        tp.pad_number = pad.number
        tp.net = pad.net or ""
        tp.label = f"{comp.reference}.{pad.number}"
        tp.x, tp.y = pad_board_position(comp, pad)
        tp.source = "suggested"
        suggestions.append(tp)
    return suggestions


def summarize_results(test_points) -> dict:
    """Return counts by status for a list of TestPoint objects."""
    counts = {
        STATUS_NOT_TESTED: 0,
        STATUS_PASS: 0,
        STATUS_FAIL: 0,
        STATUS_UNKNOWN: 0,
    }
    for tp in test_points:
        status, _reason = evaluate_testpoint(tp)
        counts[status] = counts.get(status, 0) + 1
    return counts
