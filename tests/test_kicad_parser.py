"""Basic parser tests using a synthetic sample board."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from pcb_analyzer.kicad_parser import parse_pcb, parse_pcb_text  # noqa: E402


class TestParser(unittest.TestCase):
    def setUp(self):
        path = os.path.join(HERE, "fixtures", "sample_board.kicad_pcb")
        self.board = parse_pcb(path)

    def test_components_parsed(self):
        refs = [c.reference for c in self.board.components]
        self.assertIn("R1", refs)
        self.assertIn("C1", refs)
        self.assertIn("U1", refs)

    def test_component_positions(self):
        r1 = self.board.find_component("R1")
        self.assertAlmostEqual(r1.x, 100.0)
        self.assertAlmostEqual(r1.y, 100.0)
        self.assertEqual(r1.value, "10k")

    def test_ic_pads(self):
        u1 = self.board.find_component("U1")
        self.assertEqual(len(u1.pads), 8)
        self.assertEqual(u1.pads[0].number, "1")

    def test_tracks(self):
        self.assertGreaterEqual(len(self.board.tracks), 2)

    def test_outline(self):
        self.assertGreaterEqual(len(self.board.outline.segments), 4)

    def test_bounds(self):
        b = self.board.bounds()
        self.assertIsNotNone(b)
        min_x, min_y, max_x, max_y = b
        self.assertLess(min_x, max_x)
        self.assertLess(min_y, max_y)


if __name__ == "__main__":
    unittest.main()
