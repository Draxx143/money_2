"""GTK-free test-point report exporters."""
import csv

from .diagnostics import evaluate_testpoint

CSV_COLUMNS = ("label", "reference", "pad", "net", "category", "expected", "actual",
               "unit", "tolerance", "status", "reason", "instrument", "notes", "timestamp")


def export_csv(store, path):
    """Export test points and deterministic evaluation results as Excel-friendly CSV."""
    with open(path, "w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for point in store:
            status, reason = evaluate_testpoint(point)
            writer.writerow({
                "label": point.label, "reference": point.reference, "pad": point.pad_number,
                "net": point.net, "category": point.category,
                "expected": point.expected_value, "actual": point.actual_value,
                "unit": point.unit, "tolerance": point.tolerance, "status": status,
                "reason": reason, "instrument": point.instrument, "notes": point.notes,
                "timestamp": point.timestamp,
            })
