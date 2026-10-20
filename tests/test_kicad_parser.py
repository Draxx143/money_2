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

    def test_legacy_module_net_via_drill_and_edge_circle(self):
        text = '''(kicad_pcb
          (net 1 "GND")
          (module "Legacy:Part" (layer "B.Cu") (at 10 20 90)
            (fp_text reference "Q1") (fp_text value "FET")
            (pad "1" thru_hole circle (at 1 2 45) (size 2 2) (drill 0.8)
              (layers "*.Cu") (net 1 "GND")))
          (segment (start 0 0) (end 1 1) (width 0.2) (layer "B.Cu") (net 1))
          (via (at 4 5) (size 0.8) (drill 0.4) (layers "F.Cu" "B.Cu") (net 1))
          (gr_circle (center 0 0) (end 2 0) (layer "Edge.Cuts"))
          (zone (net 1) (layer "B.Cu") (filled_polygon (pts (xy 0 0) (xy 1 0) (xy 1 1)))) )'''
        board = parse_pcb_text(text)
        self.assertEqual(board.components[0].reference, "Q1")
        self.assertEqual(board.components[0].pads[0].hole_diameter, 0.8)
        self.assertEqual(board.components[0].pads[0].rotation, 45)
        self.assertEqual(board.components[0].pads[0].net, "GND")
        self.assertEqual(len(board.zones), 1)
        self.assertEqual(board.tracks[0].net, "GND")
        self.assertEqual(board.vias[0].net, "GND")
        self.assertGreater(len(board.outline.segments), 60)

    def test_bounds(self):
        b = self.board.bounds()
        self.assertIsNotNone(b)
        min_x, min_y, max_x, max_y = b
        self.assertLess(min_x, max_x)
        self.assertLess(min_y, max_y)


if __name__ == "__main__":
    unittest.main()
