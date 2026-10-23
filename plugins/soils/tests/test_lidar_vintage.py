"""The calibration report's lidar vintage column (pure; runs without GDAL)."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(os.path.dirname(HERE), "build")
if BUILD not in sys.path:
    sys.path.insert(0, BUILD)

import lidar_vintage as LV  # noqa: E402

BOXES = ("a", "b", "c", "d", "downtown", "e", "f", "h", "i", "j")


class LidarVintageTests(unittest.TestCase):
    def test_every_box_has_a_vintage(self):
        for b in BOXES:
            self.assertIn(LV.lidar_vintage(b), (LV.VINTAGE_2019, LV.VINTAGE_2023), b)

    def test_held_out_boxes_keep_2019_lidar(self):
        self.assertEqual(sorted(LV.HELD_OUT), ["a", "e", "i", "j"])
        for b in LV.HELD_OUT:
            self.assertEqual(LV.lidar_vintage(b), LV.VINTAGE_2019)

    def test_fit_boxes_use_2023_lidar(self):
        fit = [b for b in BOXES if b not in LV.HELD_OUT]
        self.assertEqual(sorted(fit), ["b", "c", "d", "downtown", "f", "h"])
        for b in fit:
            self.assertEqual(LV.lidar_vintage(b), LV.VINTAGE_2023)

    def test_table_prints_a_vintage_column(self):
        text = LV.vintage_table([("a", 1.5), ("b", None)]).splitlines()
        self.assertTrue(text[0].startswith("box") and "lidar" in text[0])
        self.assertIn(LV.VINTAGE_2019, text[1])
        self.assertIn(LV.VINTAGE_2023, text[2])
        self.assertTrue(text[2].endswith("-"))


if __name__ == "__main__":
    unittest.main()
