import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from pcb_analyzer.diagnostics import (  # noqa: E402
    evaluate_testpoint, suggest_testpoints_for_component, summarize_results,
)
from pcb_analyzer.kicad_parser import parse_pcb  # noqa: E402
from pcb_analyzer.model import Component, Pad, pad_board_position  # noqa: E402
from pcb_analyzer.testpoints import (  # noqa: E402
    STATUS_FAIL, STATUS_NOT_TESTED, STATUS_PASS, STATUS_UNKNOWN, TestPoint,
)


def make_tp(expected="5", actual="5", unit="V", tolerance="5"):
    return TestPoint(label="T", reference="U1", pad_number="1",
                     expected_value=expected, actual_value=actual,
                     unit=unit, tolerance=tolerance)


class TestEvaluate(unittest.TestCase):
    def test_not_tested(self):
        tp = make_tp(actual="")
        s, _r = evaluate_testpoint(tp)
        self.assertEqual(s, STATUS_NOT_TESTED)

    def test_no_expected(self):
        tp = make_tp(expected="", actual="5")
        s, _r = evaluate_testpoint(tp)
        self.assertEqual(s, STATUS_UNKNOWN)

    def test_pass(self):
        tp = make_tp(expected="5", actual="5.02")
        s, _r = evaluate_testpoint(tp)
        self.assertEqual(s, STATUS_PASS)

    def test_fail(self):
        tp = make_tp(expected="5", actual="3.3")
        s, _r = evaluate_testpoint(tp)
        self.assertEqual(s, STATUS_FAIL)

    def test_unparseable(self):
        tp = make_tp(expected="5", actual="oops")
        s, _r = evaluate_testpoint(tp)
        self.assertEqual(s, STATUS_UNKNOWN)

    def test_default_tolerance_when_missing(self):
        tp = make_tp(expected="5", actual="5.02", tolerance="")
        s, _r = evaluate_testpoint(tp)
        self.assertEqual(s, STATUS_PASS)

    def test_boundary_pass(self):
        tp = make_tp(expected="5", actual="5.25", tolerance="5")
        s, _r = evaluate_testpoint(tp)
        self.assertEqual(s, STATUS_PASS)

    def test_boundary_fail(self):
        tp = make_tp(expected="5", actual="5.26", tolerance="5")
        s, _r = evaluate_testpoint(tp)
        self.assertEqual(s, STATUS_FAIL)


class TestPadBoardPosition(unittest.TestCase):
    def test_cardinal_rotations_and_bottom_mirror(self):
        pad = Pad("1", 2, 3, 1, 1)
        expected = {0: (12, 23), 90: (7, 22), 180: (8, 17), 270: (13, 18)}
        for angle, point in expected.items():
            with self.subTest(angle=angle):
                self.assertAlmostEqual(pad_board_position(
                    Component("U1", "", "", 10, 20, rotation=angle), pad)[0], point[0])
                self.assertAlmostEqual(pad_board_position(
                    Component("U1", "", "", 10, 20, rotation=angle), pad)[1], point[1])
        self.assertEqual(pad_board_position(Component("U1", "", "", 10, 20, layer="B.Cu"), pad), (8, 23))
        self.assertAlmostEqual(pad_board_position(Component("U1", "", "", 10, 20, rotation=90, layer="B.Cu"), pad)[0], 7)


class TestSuggestions(unittest.TestCase):
    def test_suggest_for_u1(self):
        path = os.path.join(HERE, "fixtures", "sample_board.kicad_pcb")
        board = parse_pcb(path)
        suggestions = suggest_testpoints_for_component(board, "U1")
        self.assertEqual(len(suggestions), 8)
        for tp in suggestions:
            self.assertEqual(tp.reference, "U1")
            self.assertTrue(tp.pad_number)
            self.assertIsNotNone(tp.x)
            self.assertIsNotNone(tp.y)

    def test_missing_component(self):
        path = os.path.join(HERE, "fixtures", "sample_board.kicad_pcb")
        board = parse_pcb(path)
        self.assertEqual(suggest_testpoints_for_component(board, "ZZZ"), [])


class TestSummary(unittest.TestCase):
    def test_counts(self):
        tps = [
            make_tp(actual="5.0"),
            make_tp(actual="3.3"),
            make_tp(actual=""),
            make_tp(expected="", actual="1"),
        ]
        counts = summarize_results(tps)
        self.assertEqual(counts[STATUS_PASS], 1)
        self.assertEqual(counts[STATUS_FAIL], 1)
        self.assertEqual(counts[STATUS_NOT_TESTED], 1)
        self.assertEqual(counts[STATUS_UNKNOWN], 1)


if __name__ == "__main__":
    unittest.main()
