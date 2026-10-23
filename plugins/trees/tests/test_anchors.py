"""The anchors file a trees build writes beside its public files (standard library only)."""
import csv
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "build"))
import anchors  # noqa: E402

AN = {"source": "boise", "source_id": "abc-1"}


class AnchorsFileTest(unittest.TestCase):
    def test_reads_the_csv_and_names_a_missing_column(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.csv")
            with open(p, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(anchors.CSV_FIELDS)
                w.writerow(["boise", "abc-1", -116.2, 43.6, "acer", 14, ""])
            self.assertEqual(anchors.read_rows(p)[0]["source_id"], "abc-1")
            with open(p, "w", newline="") as f:
                csv.writer(f).writerow(["source", "source_id", "lon", "lat", "genus"])
            with self.assertRaisesRegex(ValueError, "trunk_in, installed_ms"):
                anchors.read_rows(p)

    def test_writes_nothing_when_there_are_no_anchors(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(anchors.write(d, []), 0)
            self.assertEqual(os.listdir(d), [])
            self.assertEqual(anchors.read(d), [])

    def test_a_matched_and_an_estimated_record_round_trip(self):
        m = anchors.matched("c-1-2", AN, "c", "c-test", 0.8, 12.3, "2023-10-24T12:00:00Z", {"height_m": 12.0})
        e = anchors.estimated(AN | {"source_id": "abc-2"}, "c", "c-test",
                              {"type": "broadleaf", "lon": -116.2, "lat": 43.6, "height_m": 6.0, "crown_radius_m": 2.0,
                               "fit": {"trunk_in": 7}}, "2026-10-22T00:00:00Z", {"why": "none"})
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(anchors.write(d, [m, e]), 2)
            got = anchors.read(d)
        self.assertEqual([r["kind"] for r in got], ["matched", "estimated"])
        self.assertEqual(got[0]["tree_id"], "c-1-2")
        self.assertEqual(got[1]["tree_id"], "boise-abc-2")          # private: <source>-<source_id>
        self.assertEqual(got[1]["fit"], {"trunk_in": 7})
        self.assertEqual(got[0]["events"][0]["event"], "measured")

    def test_refuses_a_line_without_a_known_kind_or_a_key(self):
        for bad in ({"kind": "placed", "tree_id": "x", "source": "s", "source_id": "1"},
                    {"kind": "matched", "tree_id": "x", "source": "s"},
                    {"kind": "matched", "source": "s", "source_id": "1"}):
            with tempfile.TemporaryDirectory() as d:
                with open(os.path.join(d, anchors.ANCHOR_FILE), "w") as f:
                    f.write(json.dumps(bad) + "\n")
                with self.assertRaises(ValueError):
                    anchors.read(d)


if __name__ == "__main__":
    unittest.main()
