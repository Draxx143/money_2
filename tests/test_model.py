"""Board-model lookup tests for exact AI-to-PCB reference mapping."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from pcb_analyzer.model import Board, Component, Pad, Track, Via  # noqa: E402


class TestBoardComponentLookup(unittest.TestCase):
    def setUp(self):
        self.board = Board(components=[
            Component("U1", "regulator", "SOT-23", 0, 0),
            Component("U10", "controller", "QFN", 1, 1),
        ])

    def test_case_insensitive_exact_resolution(self):
        self.assertIs(self.board.resolve_component_reference("u1"), self.board.components[0])
        self.assertIs(self.board.resolve_component_reference("U10"), self.board.components[1])

    def test_never_resolves_prefix_or_unknown_reference(self):
        for ref in ("U", "U100", "R1", ""):
            with self.subTest(ref=ref):
                self.assertIsNone(self.board.resolve_component_reference(ref))

    def test_net_inventory_contains_only_parsed_geometry(self):
        self.board.components[0].pads.append(Pad("1", 0, 0, 1, 1, net="GND"))
        self.board.tracks.append(Track(0, 0, 1, 1, 0.2, "F.Cu", net="GND"))
        self.board.vias.append(Via(1, 1, 0.6, 0.3, ["F.Cu", "B.Cu"], net="VCC"))
        self.assertEqual(self.board.net_inventory(), {
            "GND": {"pads": 1, "tracks": 1, "vias": 0},
            "VCC": {"pads": 0, "tracks": 0, "vias": 1},
        })


if __name__ == "__main__":
    unittest.main()
