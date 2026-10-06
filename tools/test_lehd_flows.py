"""Tests for lehd_flows.py on tiny synthetic LODES files. Run: python3 -m unittest discover tools"""

import gzip
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import lehd_flows  # noqa: E402

ADA, EMMETT, ONTARIO, UTAH = "160010001001000", "160450001001000", "410450001001000", "490350001001000"


def write(folder, name, header, rows):
    with gzip.open(os.path.join(folder, name), "wt") as f:
        f.write(header + "\n" + "".join(r + "\n" for r in rows))


class FlowsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        xw = "tabblk2020,cty,stplcname"
        write(self.dir, "id_xwalk.csv.gz", xw, [f"{ADA},16001,Boise City city", f"{EMMETT},16045,Emmett city"])
        write(self.dir, "or_xwalk.csv.gz", xw, [f"{ONTARIO},41045,Ontario city"])
        od = "w_geocode,h_geocode,S000"
        write(self.dir, "id_od_main_JT00_2023.csv.gz", od, [f"{ADA},{EMMETT},6", f"{EMMETT},{EMMETT},4", f"{ADA},{ADA},10"])
        write(self.dir, "id_od_aux_JT00_2023.csv.gz", od, [f"{ADA},{ONTARIO},2", f"{ADA},{UTAH},5"])
        write(self.dir, "or_od_main_JT00_2023.csv.gz", od, [f"{ONTARIO},{ONTARIO},8"])
        write(self.dir, "or_od_aux_JT00_2023.csv.gz", od, [f"{ONTARIO},{EMMETT},1"])

    def test_county_and_town_flows(self):
        by_county, by_town = lehd_flows.flows(self.dir, "2023", lehd_flows.read_crosswalks(self.dir))
        self.assertEqual(by_county[("Gem", "Ada")], 6)
        self.assertEqual(by_county[("Malheur OR", "Malheur OR")], 8)      # Oregon's in-state file counts
        self.assertEqual(by_county[("Other states", "Ada")], 5)
        self.assertEqual(by_town[("Emmett", "Gem")], {"Ada": 6, "Gem": 4, "Malheur OR": 1})
        report = lehd_flows.report(by_county, by_town)
        self.assertIn("| Emmett | Gem | 11 | 6 | 0 | 55% |", report)
        self.assertIn("| Ontario | Malheur OR | 10 | 2 | 0 | 20% |", report)


if __name__ == "__main__":
    unittest.main()
