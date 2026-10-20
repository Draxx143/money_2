import csv
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from pcb_analyzer.report import export_csv  # noqa: E402
from pcb_analyzer.testpoints import TestPoint, TestPointStore  # noqa: E402


class TestReport(unittest.TestCase):
    def test_csv_bom_columns_and_unicode_measurement_result(self):
        store = TestPointStore()
        store.add(TestPoint(label="تست", reference="R1", pad_number="2", net="زمین",
                            expected_value="5", actual_value="4", unit="V", notes="بررسی"))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.csv")
            export_csv(store, path)
            raw = Path(path).read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            with open(path, encoding="utf-8-sig", newline="") as f:
                row = next(csv.DictReader(f))
            self.assertEqual(row["label"], "تست")
            self.assertEqual(row["net"], "زمین")
            self.assertEqual(row["status"], "Fail")
            self.assertIn("outside", row["reason"])

if __name__ == "__main__":
    unittest.main()
