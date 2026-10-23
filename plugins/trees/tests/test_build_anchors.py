"""The trees build end to end (build.py) with anchors, on a synthetic area: a DSM and DTM in EPSG:6340 with one lone
crown, and an anchors CSV with a trunk point at the crown, one on bare ground and one planted after the flight.

What the lidar finds goes in the public files; the link from the crown to its anchor and the tree the lidar doesn't show
go in anchors.jsonl; nothing of the inventory (its source, ids, genus, trunk diameters, offsets) reaches the public
files, and the public loader accepts them. Needs NumPy, SciPy, rasterio and pyproj: run it in the worker image, where a
skip counts as a failure."""
import csv
import json
import os
import sys
import tempfile
import unittest

try:
    import numpy as np
    import rasterio
    from pyproj import Transformer
    from rasterio.transform import from_origin
    from scipy import ndimage  # noqa: F401
except ImportError:  # pragma: no cover
    np = None

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "build"))
SOURCE = "zz-inventory"                                  # invented names: nothing here is a real record
CROWN_ID, BARE_ID, LATE_ID = "zz-111-crown", "zz-222-bare", "zz-333-late"
X0, Y1, PX, N = 500000.0, 4800060.0, 0.5, 120            # a 60 m square
GROUND = 100.0
CROWN_E, CROWN_S = 30.0, 30.0                             # metres east and south of the NW corner
BARE_E, BARE_S = 10.0, 10.0


def dome(cx, cy, H, R, a=0.77, n=1.64):
    yy, xx = np.mgrid[0:N, 0:N]
    d = np.hypot((xx + 0.5) * PX - cx, (yy + 0.5) * PX - cy) / R
    return np.where(d <= 1, H * (1 - a * np.minimum(d, 1) ** n), 0.0)


def lonlat(east, south):
    return Transformer.from_crs(6340, 4326, always_xy=True).transform(X0 + east, Y1 - south)


@unittest.skipIf(np is None, "NumPy/SciPy/rasterio/pyproj not installed")
class BuildWithAnchorsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = cls.tmp.name
        tf = from_origin(X0, Y1, PX, PX)
        prof = dict(driver="GTiff", height=N, width=N, count=1, dtype="float32", crs="EPSG:6340", transform=tf, nodata=-9999)
        for name, arr in (("dsm.tif", GROUND + dome(CROWN_E, CROWN_S, 15, 4.5)), ("dtm.tif", np.full((N, N), GROUND))):
            with rasterio.open(os.path.join(d, name), "w", **prof) as ds:
                ds.write(arr.astype("float32"), 1)
        cls.csv = os.path.join(d, "anchors.csv")
        late_ms = 1.9e12                                    # 2030: after the flight
        with open(cls.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["source", "source_id", "lon", "lat", "genus", "trunk_in", "installed_ms"])
            for sid, (e, s), genus, trunk, ms in ((CROWN_ID, (CROWN_E + 0.5, CROWN_S - 0.4), "acer", 14, ""),
                                                 (BARE_ID, (BARE_E, BARE_S), "pinus", 9, ""),
                                                 (LATE_ID, (50.0, 50.0), "ulmus", 3, late_ms)):
                lon, lat = lonlat(e, s)
                w.writerow([SOURCE, sid, lon, lat, genus, trunk, ms])
        cls.out = os.path.join(d, "c-test")
        cls.build_it(["--area", "c", "--dsm", os.path.join(d, "dsm.tif"), "--dtm", os.path.join(d, "dtm.tif"),
                 "--anchors", cls.csv, "--lidar-date", "2023-10-24", "--out", cls.out])
        cls.plain = os.path.join(d, "c-plain")
        cls.build_it(["--area", "c", "--dsm", os.path.join(d, "dsm.tif"), "--dtm", os.path.join(d, "dtm.tif"),
                 "--lidar-date", "2023-10-24", "--out", cls.plain])

    @classmethod
    def build_it(cls, argv):
        import build
        build.main(argv)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def public_text(self):
        return "".join(open(os.path.join(self.out, n)).read() for n in ("trees.geojson", "log.jsonl", "build.json"))

    def test_the_public_files_hold_the_crown_as_a_placed_tree_and_nothing_of_the_inventory(self):
        fc = json.load(open(os.path.join(self.out, "trees.geojson")))
        trees = [f["properties"] for f in fc["features"]]
        self.assertEqual(len(trees), 1)
        self.assertEqual(trees[0]["kind"], "placed")
        self.assertTrue(trees[0]["id"].startswith("c-"))
        self.assertAlmostEqual(trees[0]["height_m"], 15, delta=1.5)
        text = self.public_text()
        for word in (SOURCE, CROWN_ID, BARE_ID, LATE_ID, "trunk_in", "dbh_in", "catalogue", "trunk_to_crown", "acer", "pinus",
                     "Urban Tree Database"):
            self.assertNotIn(word, text, word)
        events = [json.loads(line) for line in open(os.path.join(self.out, "log.jsonl"))]
        self.assertEqual([e["event"] for e in events], ["placed"])
        self.assertEqual(events[0]["tree_id"], trees[0]["id"])
        counts = json.load(open(os.path.join(self.out, "build.json")))["counts"]
        self.assertEqual(counts["trees"], 1)
        self.assertFalse({"catalogued", "estimated"} & set(counts))

    def test_the_public_loader_accepts_the_public_files(self):
        from plugins.trees.ingest import load
        build, trees, log = load.read_build(self.out)
        self.assertEqual((len(trees), len(log)), (1, 1))

    def test_the_link_and_the_estimated_tree_are_in_the_anchors_file(self):
        import anchors
        recs = anchors.read(self.out)
        self.assertEqual(sorted(r["kind"] for r in recs), ["estimated", "matched"])
        by = {r["kind"]: r for r in recs}
        public = json.load(open(os.path.join(self.out, "trees.geojson")))["features"][0]["properties"]["id"]
        self.assertEqual((by["matched"]["tree_id"], by["matched"]["source"], by["matched"]["source_id"]),
                         (public, SOURCE, CROWN_ID))
        self.assertLess(by["matched"]["fit"]["trunk_to_crown_m"], 2.5)
        self.assertEqual(by["matched"]["events"][0]["event"], "measured")
        e = by["estimated"]
        self.assertEqual((e["source_id"], e["tree_id"]), (BARE_ID, f"{SOURCE}-{BARE_ID}"))
        self.assertEqual(e["fit"]["trunk_in"], 9)
        self.assertEqual(e["events"][0]["event"], "estimated")
        self.assertGreater(e["height_m"], 0)
        # the tree planted after the flight is in neither file
        self.assertNotIn(LATE_ID, open(os.path.join(self.out, "anchors.jsonl")).read())

    def test_the_sources_say_anchors_were_used_and_name_nothing(self):
        sources = json.load(open(os.path.join(self.out, "build.json")))["params"]["sources"]
        self.assertIn("anchors", [s["source"] for s in sources])
        self.assertNotIn("anchors", [s["source"] for s in json.load(open(os.path.join(self.plain, "build.json")))["params"]["sources"]])

    def test_without_anchors_there_is_no_anchors_file(self):
        self.assertFalse(os.path.exists(os.path.join(self.plain, "anchors.jsonl")))
        self.assertEqual(len(json.load(open(os.path.join(self.plain, "trees.geojson")))["features"]), 1)


if __name__ == "__main__":
    unittest.main()
