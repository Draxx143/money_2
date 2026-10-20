import sys
import unittest
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))
from pcb_analyzer.altium_parser import parse_pcbdoc  # noqa: E402

FIXTURE = HERE / "fixtures" / "PCB_test_pcb_2_2026-10-20.pcbdoc"


class TestAltiumAsciiParser(unittest.TestCase):
    def test_loads_ascii_board_without_optional_library(self):
        board = parse_pcbdoc(str(FIXTURE))
        self.assertEqual(board.version, "altium-ascii")
        self.assertEqual(len(board.components), 8)
        self.assertEqual(len(board.tracks), 89)
        self.assertEqual(len(board.outline.segments), 4)
        self.assertEqual(len(board.zones), 2)
        self.assertEqual(board.zones[0].net, "GND")
        self.assertGreaterEqual(len(board.zones[0].points), 8)
        self.assertIsNotNone(board.bounds())

    def test_decodes_component_metadata_and_pads(self):
        board = parse_pcbdoc(str(FIXTURE))
        capacitor = board.find_component("C1")
        self.assertIsNotNone(capacitor)
        self.assertEqual(capacitor.value, "100nF")
        self.assertEqual(capacitor.layer, "B.Cu")
        self.assertEqual(capacitor.footprint, "CAP-SMD_L2.2-W1.3-RD")
        self.assertIsNotNone(capacitor.reference_x)
        self.assertIsNotNone(capacitor.value_x)
        self.assertEqual(len(capacitor.pads), 2)
        self.assertEqual(capacitor.pads[0].net, "GND")
        self.assertAlmostEqual(capacitor.x, 53.0700, places=2)


if __name__ == "__main__":
    unittest.main()
