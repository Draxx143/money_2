import sys
import unittest
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))
from pcb_analyzer.easyeda_parser import parse_easyeda_json  # noqa: E402

FIXTURE = HERE / "fixtures" / "PCB_PCB_test_pcb_2_2026-10-20.json"


class TestEasyEDAJsonParser(unittest.TestCase):
    def setUp(self):
        self.board = parse_easyeda_json(str(FIXTURE))

    def test_parses_native_board_primitives(self):
        self.assertEqual(self.board.version, "easyeda-json")
        self.assertEqual(len(self.board.components), 8)
        self.assertEqual(len(self.board.zones), 2)
        self.assertEqual(len(self.board.outline.segments), 4)
        self.assertGreaterEqual(len(self.board.tracks), 80)

    def test_component_vertical_orientation_matches_native_view(self):
        u5 = self.board.find_component("U5")
        u4 = self.board.find_component("U4")
        c1 = self.board.find_component("C1")
        self.assertLess(u5.y, u4.y)
        self.assertLess(c1.y, u4.y)
        self.assertEqual(u5.layer, "F.Cu")
        self.assertEqual(c1.layer, "B.Cu")

    def test_pad_and_net_data(self):
        h1 = self.board.find_component("H1")
        self.assertEqual(len(h1.pads), 2)
        self.assertEqual(h1.pads[0].net, "GND")
        self.assertGreater(h1.pads[0].hole_diameter, 0)
        self.assertAlmostEqual(self.board.bounds()[0], 0.0)


if __name__ == "__main__":
    unittest.main()
