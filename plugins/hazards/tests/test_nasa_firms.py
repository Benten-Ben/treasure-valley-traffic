"""Tests for NASA FIRMS detections (ingest/sources/nasa_firms.py). Offline.

The fixtures carry the files' real headers. Rows outside the ring are real (Oct 6-7,
2026, Cuba, Quebec, Mississippi); the rows inside the ring are made up.

Run: python3 -m unittest discover -s plugins/hazards/tests -t .
"""

import os
import unittest
import urllib.error

from ingest import http
from ingest.db import version_hash
from plugins.hazards.ingest.sources import nasa_firms as firms

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def text(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


class ParseTest(unittest.TestCase):
    def test_only_rows_in_the_ring_edges_included(self):
        parsed = firms.parse("viirs_noaa20", text("firms_viirs_24h.csv"))
        self.assertEqual(sorted(parsed), ["viirs_noaa20:N20:2026-10-06:2041:43.51234:-116.41234",
                                          "viirs_noaa20:N20:2026-10-07:0918:44.29000:-115.61000"])

    def test_every_column_kept_and_typed(self):
        payload, geom = firms.parse("viirs_noaa20", text("firms_viirs_24h.csv"))[
            "viirs_noaa20:N20:2026-10-06:2041:43.51234:-116.41234"]
        self.assertEqual(payload, {"sensor": "viirs_noaa20", "latitude": 43.51234, "longitude": -116.41234,
                                   "bright_ti4": 330.5, "scan": 0.45, "track": 0.39, "acq_date": "2026-10-06",
                                   "acq_time": "2041", "satellite": "N20", "confidence": "high", "version": "2.0NRT",
                                   "bright_ti5": 296.4, "frp": 7.25, "daynight": "D",
                                   "acquired": "2026-10-06T20:41:00Z"})
        self.assertEqual(geom, {"type": "Point", "coordinates": [-116.41234, 43.51234]})

    def test_modis_columns_and_numeric_confidence(self):
        (sid, (payload, _)), = firms.parse("modis", text("firms_modis_24h.csv")).items()
        self.assertEqual(sid, "modis:A:2026-10-06:1805:43.40000:-116.70000")
        self.assertEqual((payload["confidence"], payload["brightness"], payload["bright_t31"]), (81, 318.4, 295.1))

    def test_an_hourly_rewrite_changes_nothing(self):
        a = firms.parse("viirs_noaa20", text("firms_viirs_24h.csv"))
        b = firms.parse("viirs_noaa20", text("firms_viirs_24h.csv").replace("\n", "\r\n"))
        self.assertEqual(sorted(a), sorted(b))
        self.assertEqual({k: version_hash(p) for k, (p, _) in a.items()},
                         {k: version_hash(p) for k, (p, _) in b.items()})

    def test_acquired(self):
        self.assertEqual(firms.acquired({"acq_date": "2026-10-06", "acq_time": "5"}), "2026-10-06T00:05:00Z")
        self.assertIsNone(firms.acquired({"acq_date": "2026-10-06", "acq_time": "late"}))


class FetchTest(unittest.TestCase):
    def files(self, fail=()):
        bodies = {"viirs": text("firms_viirs_24h.csv").encode(), "modis": text("firms_modis_24h.csv").encode()}
        calls = []

        def get(url):
            calls.append(url)
            sensor = next(s for s, p in firms.FILES if url.endswith(p))
            if sensor in fail:
                raise fail[sensor]
            return 200, bodies["modis" if sensor == "modis" else "viirs"], "allowed"
        return get, calls

    def test_four_files_paced(self):
        get, calls = self.files()
        pauses = []
        parsed, failed, nbytes, status, decision = firms.fetch(get, sleep=pauses.append)
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(u.startswith("https://firms.modaps.eosdis.nasa.gov/data/active_fire/") for u in calls))
        self.assertEqual(pauses, [2.0, 2.0, 2.0])
        self.assertEqual((len(parsed), failed, status, decision), (7, {}, 200, "allowed"))

    def test_a_failed_file_is_reported_the_rest_kept(self):
        gone = urllib.error.HTTPError("u", 404, "Not Found", None, None)
        self.addCleanup(gone.close)
        get, _ =self.files({"viirs_snpp": gone, "modis": http.RobotsDisallowed("no")})
        parsed, failed, *_ = firms.fetch(get, sleep=lambda s: None)
        self.assertEqual(sorted(failed), ["modis", "viirs_snpp"])
        self.assertEqual({k.split(":")[0] for k in parsed}, {"viirs_noaa20", "viirs_noaa21"})

    def test_all_failing_fails_the_fetch(self):
        err = OSError("network down")
        get, _ = self.files({s: err for s, _ in firms.FILES})
        with self.assertRaises(RuntimeError):
            firms.fetch(get, sleep=lambda s: None)


if __name__ == "__main__":
    unittest.main()
