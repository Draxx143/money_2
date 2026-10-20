"""Unit tests for TestPointStore."""
import os
import sys
import tempfile
import unittest
import json
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from pcb_analyzer.testpoints import (  # noqa: E402
    STATUS_NOT_TESTED, STATUS_PASS, TestPoint, TestPointStore,
)


class TestStore(unittest.TestCase):
    def test_add_and_get(self):
        store = TestPointStore()
        tp = TestPoint(label="VCC", reference="U1", pad_number="8", net="VCC")
        store.add(tp)
        self.assertEqual(len(store), 1)
        self.assertIs(store.get(tp.id), tp)

    def test_update(self):
        store = TestPointStore()
        tp = TestPoint(label="X", reference="R1")
        store.add(tp)
        tp.status = STATUS_PASS
        tp.actual_value = "5.0"
        store.update(tp)
        self.assertEqual(store.get(tp.id).status, STATUS_PASS)
        self.assertEqual(store.get(tp.id).actual_value, "5.0")

    def test_delete(self):
        store = TestPointStore()
        tp = TestPoint(label="X")
        store.add(tp)
        self.assertTrue(store.delete(tp.id))
        self.assertFalse(store.delete(tp.id))
        self.assertEqual(len(store), 0)

    def test_find_by_reference(self):
        store = TestPointStore()
        store.add(TestPoint(reference="U1", label="a"))
        store.add(TestPoint(reference="U1", label="b"))
        store.add(TestPoint(reference="R1", label="c"))
        self.assertEqual(len(store.find_by_reference("U1")), 2)
        self.assertEqual(len(store.find_by_reference("R1")), 1)

    def test_save_and_load_roundtrip(self):
        store = TestPointStore()
        store.add(TestPoint(label="V1", reference="U1", pad_number="1",
                            net="VCC", expected_value="5", unit="V",
                            status=STATUS_NOT_TESTED))
        store.add(TestPoint(label="V2", reference="C1", pad_number="1",
                            expected_value="3.3", unit="V",
                            status=STATUS_PASS, actual_value="3.28"))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tp.json")
            store.save(path)
            self.assertTrue(os.path.isfile(path))

            store2 = TestPointStore()
            store2.load(path)
            self.assertEqual(len(store2), 2)
            refs = sorted(p.reference for p in store2)
            self.assertEqual(refs, ["C1", "U1"])
            for p in store2:
                self.assertTrue(p.id)

    def test_from_dict_repairs_missing_none_and_wrong_types(self):
        tp = TestPoint.from_dict({"label": None, "actual_value": 12, "x": "bad",
                                  "y": "2.5", "status": "broken", "extra": 1})
        self.assertEqual(tp.label, "")
        self.assertEqual(tp.actual_value, "12")
        self.assertIsNone(tp.x)
        self.assertEqual(tp.y, 2.5)
        self.assertEqual(tp.status, STATUS_NOT_TESTED)
        from pcb_analyzer.diagnostics import evaluate_testpoint
        self.assertEqual(evaluate_testpoint(TestPoint.from_dict({}))[0], STATUS_NOT_TESTED)

    def test_load_validates_payload_skips_bad_entries_and_corrupt_file_clears(self):
        with tempfile.TemporaryDirectory() as tmp:
            board = os.path.join(tmp, "board.kicad_pcb")
            path = TestPointStore.companion_path_for_board(board)
            store = TestPointStore()
            for payload in ([], {"points": "x"}):
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(payload, f)
                with self.assertRaisesRegex(ValueError, "Invalid test point file"):
                    store.load(path)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"points": [1, {"label": "legacy"}]}, f)
            store.load(path)
            self.assertEqual(len(store), 1)
            self.assertEqual(store.skipped, 1)
            with open(path, "w", encoding="utf-8") as f:
                f.write("{")
            store.add(TestPoint(label="stale"))
            with self.assertRaises(ValueError):
                store.load_if_exists(board)
            self.assertEqual(len(store), 0)
            self.assertEqual(store.path, path)

    def test_save_removes_temp_after_dump_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tp.json")
            with mock.patch("pcb_analyzer.testpoints.json.dump", side_effect=OSError("full")):
                with self.assertRaises(OSError):
                    TestPointStore().save(path)
            self.assertEqual(os.listdir(tmp), [])

    def test_companion_path(self):
        p = TestPointStore.companion_path_for_board("/tmp/board.kicad_pcb")
        self.assertEqual(p, "/tmp/board.testpoints.json")

    def test_load_if_exists_returns_false_when_missing(self):
        store = TestPointStore()
        with tempfile.TemporaryDirectory() as tmp:
            board = os.path.join(tmp, "board.kicad_pcb")
            self.assertFalse(store.load_if_exists(board))
            self.assertEqual(len(store), 0)


if __name__ == "__main__":
    unittest.main()
