"""Deterministic engineering calculations and unit handling.

All functions are pure; they raise ValueError on invalid input so that the
caller can decide how to surface the error (usually as 'Unknown' status).
"""
import math
import re
from typing import Optional


SI_PREFIXES = {
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "µ": 1e-6,
    "m": 1e-3,
    "": 1.0,
    "k": 1e3,
    "K": 1e3,
    "M": 1e6,
    "G": 1e9,
}

_VALUE_RE = re.compile(r"^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*([pnuµmkKMG]?)\s*([A-Za-zΩ]*)\s*$")


def parse_value(text: str) -> Optional[float]:
    """Parse a value with an SI prefix.

    Examples:
        "4.7k"  -> 4700.0
        "10M"   -> 1e7
        "100nF" -> 1e-7
        "3.3 V" -> 3.3
    Returns None if the text cannot be parsed.
    """
    if text is None:
        return None
    text = str(text).strip()
    if not text:
        return None
    m = _VALUE_RE.match(text)
    if not m:
        return None
    number = float(m.group(1))
    prefix = m.group(2) or ""
    factor = SI_PREFIXES.get(prefix)
    if factor is None:
        return None
    return number * factor


def parse_tolerance(text: str) -> Optional[float]:
    """Parse a tolerance like '5%', '±5%', '2' (percent) -> float percent."""
    if text is None:
        return None
    s = str(text).strip().replace("±", "").replace("%", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ---- Basic electronics ----
def ohms_law_voltage(current_a: float, resistance_ohm: float) -> float:
    if resistance_ohm < 0:
        raise ValueError("resistance must be >= 0")
    return current_a * resistance_ohm


def ohms_law_current(voltage_v: float, resistance_ohm: float) -> float:
    if resistance_ohm <= 0:
        raise ValueError("resistance must be > 0")
    return voltage_v / resistance_ohm


def ohms_law_resistance(voltage_v: float, current_a: float) -> float:
    if current_a == 0:
        raise ValueError("current must be non-zero")
    return voltage_v / current_a


def power(voltage_v: float, current_a: float) -> float:
    return voltage_v * current_a


def power_from_resistance(voltage_v: float, resistance_ohm: float) -> float:
    if resistance_ohm <= 0:
        raise ValueError("resistance must be > 0")
    return voltage_v * voltage_v / resistance_ohm


def voltage_divider(vin_v: float, r1_ohm: float, r2_ohm: float) -> float:
    if r1_ohm < 0 or r2_ohm < 0:
        raise ValueError("resistances must be >= 0")
    denom = r1_ohm + r2_ohm
    if denom <= 0:
        raise ValueError("R1 + R2 must be > 0")
    return vin_v * r2_ohm / denom


def within_tolerance(measured: float, expected: float, tol_pct: float) -> bool:
    """Return True if measured is within expected ± tol_pct/100."""
    if tol_pct < 0:
        raise ValueError("tolerance must be >= 0")
    if expected == 0:
        return abs(measured) <= tol_pct / 100.0
    allowed = abs(expected) * (tol_pct / 100.0)
    return abs(measured - expected) <= allowed


def expected_range(expected: float, tol_pct: float):
    """Return (low, high) inclusive bounds."""
    if tol_pct < 0:
        raise ValueError("tolerance must be >= 0")
    delta = abs(expected) * (tol_pct / 100.0)
    return (expected - delta, expected + delta)


def fmt_engineering(value: float, unit: str = "") -> str:
    """Return a short human-readable form with SI prefix.

    Examples:
        4700.0  -> '4.7 kΩ' (if unit='Ω')
        0.0001  -> '100 µ'  (if unit='')
    """
    if value is None:
        return "—"
    if value == 0:
        return f"0 {unit}".rstrip()
    abs_v = abs(value)
    for prefix, factor in (("G", 1e9), ("M", 1e6), ("k", 1e3),
                           ("", 1.0), ("m", 1e-3), ("µ", 1e-6),
                           ("n", 1e-9), ("p", 1e-12)):
        if abs_v >= factor or prefix == "p":
            scaled = value / factor
            if abs(scaled) >= 100:
                return f"{scaled:.0f} {prefix}{unit}".rstrip()
            if abs(scaled) >= 10:
                return f"{scaled:.1f} {prefix}{unit}".rstrip()
            return f"{scaled:.2f} {prefix}{unit}".rstrip()
    return f"{value:g} {unit}".rstrip()


def is_finite(x) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False
