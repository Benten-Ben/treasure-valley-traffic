"""Tests for the shared UTM 11N projection (ingest/utm.py).

Run: python3 -m unittest discover -s ingest/tests -t .
"""

import unittest

from ingest import utm


class ProjectionTest(unittest.TestCase):
    def test_utm_matches_postgis(self):
        # ST_Transform(..., 32611) on PostGIS 3 / PROJ, Oct 6 2026.
        for lon, lat, x, y in [(-116.2023, 43.6150, 564367.0951, 4829422.2816),
                               (-116.6873, 43.6629, 525211.9591, 4834480.4951),
                               (-117.0, 44.0, 500000.0, 4871872.8408)]:
            px, py = utm.to_utm(lon, lat)
            self.assertAlmostEqual(px, x, delta=0.001)
            self.assertAlmostEqual(py, y, delta=0.001)
            blon, blat = utm.from_utm(px, py)
            self.assertAlmostEqual(blon, lon, places=9)
            self.assertAlmostEqual(blat, lat, places=9)


if __name__ == "__main__":
    unittest.main()
