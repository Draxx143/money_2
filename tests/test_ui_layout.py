import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from pcb_analyzer.ui_layout import clamp_workspace_divider, component_label_font_sizes  # noqa: E402


class TestLayoutHelpers(unittest.TestCase):
    def test_divider_keeps_canvas_and_right_panel_in_bounds(self):
        self.assertEqual(clamp_workspace_divider(1400, 1300), 1060)
        self.assertEqual(clamp_workspace_divider(1400, 100), 880)
        self.assertEqual(clamp_workspace_divider(900, 900), 560)

    def test_component_labels_scale_up_and_have_readable_limits(self):
        small = component_label_font_sizes(2)
        large = component_label_font_sizes(10)
        maxed = component_label_font_sizes(1000)
        self.assertLess(small[0], large[0])
        self.assertLessEqual(large[0], maxed[0])
        self.assertEqual(maxed[0], 36)
        self.assertGreaterEqual(small[1], 7)


if __name__ == "__main__":
    unittest.main()
