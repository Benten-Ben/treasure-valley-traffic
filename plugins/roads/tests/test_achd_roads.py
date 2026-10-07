"""Offline tests for ACHD's road segments (plugins/roads/ingest/sources/achd_roads.py).

Run: python3 -m unittest discover -s plugins -t .
"""

import unittest

from plugins.roads.ingest.sources import achd_roads


class RoadsTest(unittest.TestCase):
    def test_segment_maps_achd_fields(self):
        row = achd_roads.segment({"PermID": "12345", "StrtConcat": "W  Front St ", "FuncClass": "LOCAL",
                                  "PostSpeed": 35, "EmergSpeed": 35, "OneWay": "F", "Private": "N",
                                  "FromElev": 10, "ToElev": 20, "L_CommName": "Boise"})
        self.assertEqual(row["perm_id"], 12345)
        self.assertEqual(row["name"], "W Front St")                  # spaces tidied
        self.assertEqual(row["functional_class"], "Local")           # "LOCAL" normalized
        self.assertEqual((row["posted_speed_mph"], row["one_way"], row["private"]), (35, "forward", False))
        self.assertEqual((row["from_level"], row["to_level"], row["community"]), (10, 20, "Boise"))

    def test_one_way_codes(self):
        seg = lambda code: achd_roads.segment({"PermID": 1, "OneWay": code})["one_way"]
        self.assertEqual([seg("B"), seg("F"), seg("T"), seg(None)], ["both", "forward", "backward", "both"])


if __name__ == "__main__":
    unittest.main()
