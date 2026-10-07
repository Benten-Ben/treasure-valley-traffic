"""Tests for the street-name helpers (plugins/roads/ingest/streets.py), on made-up names.

Run: python3 -m unittest discover -s plugins -t .
"""

import unittest

from plugins.roads.ingest import streets


class StreetsTest(unittest.TestCase):
    def test_core_names(self):
        cases = {"W Alpha Ave": "ALPHA", "ALPHA": "ALPHA", "11TH AVENUE S.": "11", "N 11th Ave": "11",
                 "WB Interstate 99 Off Exit 50B": "I 99 OFF EXIT 50B", "Hwy 99": "SH 99", "SH-99": "SH 99",
                 "US HWY 98/99": "US 98/99", "US 98-99": "US 98/99", "Ave (b)": "AVENUE B", 'AVE. "A"': "AVENUE A",
                 "N Avenue B Ave": "AVENUE B", "5 Mile Rd": "FIVE MILE", "GAMMA ST (OLD NAME)": "GAMMA"}
        for name, want in cases.items():
            self.assertEqual(streets.core(name), want, name)

    def test_same_street(self):
        same = [("I 84", "I 84 OFF EXIT 50B"), ("I 84 N RAMP", "I 84 ON EXIT 46"), ("BROADWAY", "BROADWAY RAMP"),
                ("PARK CENTER", "PARKCENTER"), ("KOOTENIA", "KOOTENAI"), ("STATE", "SH 44"), ("VMP", "VETERANS MEMORIAL")]
        differ = [("I 84", "I 84B"), ("I 84", "I 184"), ("STATE", "STATESBORO"), ("EAGLE", "KARCHER"),
                  ("COLUMBIA", "COLUMBUS"), ("FIVE MILE", "TEN MILE"), ("23", "25")]
        for a, b in same:
            self.assertTrue(streets.same_street(a, b), (a, b))
        for a, b in differ:
            self.assertFalse(streets.same_street(a, b), (a, b))

    def test_display(self):
        self.assertEqual(streets.display_location("ALPHA-BETA BLVD & 11TH AVENUE S."), "Alpha-Beta Blvd & 11th Ave S")
        self.assertEqual(streets.display("W ParkCenter Blvd"), "ParkCenter Blvd")
        self.assertEqual(streets.display("I-99B"), "I-99B")
        self.assertEqual(streets.display("Avenue B"), "Avenue B")


if __name__ == "__main__":
    unittest.main()
