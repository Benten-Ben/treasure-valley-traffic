"""Tests for USGS earthquakes (ingest/sources/usgs_quakes.py). Offline.

The fixture is the week feed trimmed to two real Alaska events (Oct 7, 2026; public
domain) and two made-up events in the ring (network "zz").

Run: python3 -m unittest discover -s plugins/hazards/tests -t .
"""

import json
import os
import unittest

from plugins.hazards.ingest.sources import usgs_quakes as quakes

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def feed():
    with open(os.path.join(FIXTURES, "usgs_quakes.geojson"), encoding="utf-8") as f:
        return json.load(f)


class ParseTest(unittest.TestCase):
    def test_only_the_ring_edges_included(self):
        self.assertEqual(sorted(quakes.parse(feed())), ["zz9000test1", "zz9000test2"])

    def test_payload_without_links_and_empties_point_in_2d(self):
        payload, point, ids = quakes.parse(feed())["zz9000test1"]
        for gone in ("url", "detail", "title", "tz", "mmi", "alert"):
            self.assertNotIn(gone, payload)
        self.assertEqual((payload["id"], payload["mag"], payload["depth_km"], payload["felt"]), ("zz9000test1", 2.7, 7.1, 3))
        self.assertEqual(point, {"type": "Point", "coordinates": [-116.5, 43.6]})
        self.assertEqual(ids, ["zz9000test1", "yy1234test"])

    def test_an_event_keeps_the_id_we_first_stored(self):
        parsed = quakes.parse(feed())
        resolved = quakes.resolve(parsed, known={"yy1234test"})
        self.assertEqual(sorted(resolved), ["yy1234test", "zz9000test2"])
        self.assertEqual(resolved["yy1234test"][0]["id"], "zz9000test1")
        self.assertEqual(sorted(quakes.resolve(parsed, known=set())), ["zz9000test1", "zz9000test2"])

    def test_the_feed(self):
        self.assertTrue(quakes.URL.endswith("/summary/all_week.geojson"))
        self.assertEqual(quakes.SOURCE["schedule"], "1 hour")


if __name__ == "__main__":
    unittest.main()
