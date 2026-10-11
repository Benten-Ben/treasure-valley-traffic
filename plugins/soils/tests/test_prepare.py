"""prepare.py on the synthetic survey written as Web Soil Survey packages (needs GDAL: skipped where it's missing, e.g.
the ingest image; on the VM, `worker-test -C <checkout> plugins.soils.tests.test_prepare`, where a skip fails).

What prepare writes must read back (package.read checks every sha256) and derive exactly what the standard-library
fixture's prepared folder derives.
"""

import contextlib
import csv
import io
import json
import os
import sys
import tempfile
import unittest

try:
    from osgeo import ogr  # noqa: F401
except ImportError:  # pragma: no cover
    ogr = None

from plugins.soils.ingest import package
from plugins.soils.tests import synthetic

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "build"))


def rows(folder, table):
    with open(os.path.join(folder, "tabular", f"{table}.csv"), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@unittest.skipIf(ogr is None, "GDAL not installed")
class PrepareTest(unittest.TestCase):
    def setUp(self):
        import prepare
        self.prepare = prepare
        self.tmp = tempfile.TemporaryDirectory()
        self.sources = os.path.join(self.tmp.name, "data")
        self.out = os.path.join(self.tmp.name, "prepared")
        self.expected = os.path.join(self.tmp.name, "expected")
        synthetic.write_raw(self.sources)
        synthetic.write_prepared(self.expected)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(prepare.main(["--sources", self.sources, "--out", self.out]), 0)

    def tearDown(self):
        self.tmp.cleanup()

    def test_keeps_polygons_touching_the_box_whole(self):
        pkg = package.read(self.out)
        polys = {p[0]: (p[2], json.loads(p[3])) for p in pkg.polygons()}
        # ZZ001:3 lies outside; ZZ001:4 only shares the box's edge.
        self.assertEqual(sorted(polys), ["ZZ001:0", "ZZ001:1", "ZZ001:2", "ZZ002:0", "ZZ002:1", "ZZ002:2"])
        mukey, geom = polys["ZZ002:0"]
        self.assertEqual((mukey, geom["type"]), ("2001", "MultiPolygon"))
        xs = [x for x, _ in geom["coordinates"][0][0]]
        self.assertEqual((min(xs), max(xs)), (-117.06, -117.04))          # whole, not clipped at -117.05
        self.assertEqual(len(polys["ZZ001:2"][1]["coordinates"]), 2)

    def test_carries_each_survey_areas_boundary_whole(self):
        pkg = package.read(self.out)
        got = [(a, json.loads(g)) for a, g in pkg.survey_areas()]
        want = [(a, json.loads(g)) for a, g in package.read(self.expected).survey_areas()]

        def corners(geom):                    # the shapefile turns rings clockwise: compare the vertices only
            return sorted({tuple(xy) for poly in geom["coordinates"] for ring in poly for xy in ring})

        self.assertEqual([(a, corners(g)) for a, g in got], [(a, corners(g)) for a, g in want])
        self.assertEqual([a for a, _ in got], ["ZZ001", "ZZ002", "ZZ002"])   # ZZ002's two pieces, as they are
        self.assertEqual({g["type"] for _, g in got}, {"MultiPolygon"})

    def test_tables_follow_the_kept_map_units_and_keep_every_column(self):
        for table in package.TABLES:
            with self.subTest(table):
                got, want = rows(self.out, table), rows(self.expected, table)
                key = lambda r: json.dumps(r, sort_keys=True)              # noqa: E731
                self.assertEqual(sorted(got, key=key), sorted(want, key=key))
        self.assertIn("muacres", rows(self.out, "mapunit")[0])               # a column the loader doesn't read
        self.assertNotIn("1004", {r["mukey"] for r in rows(self.out, "mapunit")})
        self.assertEqual(rows(self.out, "chtexturemod"), [{"areasymbol": "ZZ001", "chtkey": "t5", "texmod": "Gravelly"}])

    def test_manifest(self):
        with open(os.path.join(self.out, package.MANIFEST), encoding="utf-8") as f:
            meta = json.load(f)
        a = {x["areasymbol"]: x for x in meta["areas"]}
        self.assertEqual(sorted(a), ["ZZ001", "ZZ002"])
        self.assertEqual((a["ZZ001"]["saverest"], a["ZZ001"]["scale"], a["ZZ001"]["saversion"], a["ZZ001"]["polygons"]),
                         ("2026-08-31T21:54:36", 24000, 14, 3))
        self.assertEqual(a["ZZ001"]["source_url"],
                         "https://websoilsurvey.sc.egov.usda.gov/DSD/Download/Cache/SSA/wss_SSA_ZZ001_%5B2026-08-31%5D.zip")
        self.assertEqual(a["ZZ002"]["areaname"], "Synthetic Area, Oregon")
        self.assertEqual(meta["files"]["tabular/component.csv"]["rows"], 9)
        self.assertEqual(meta["files"][package.SURVEY_AREAS]["rows"], 3)
        self.assertIn("ZZ001/spatial/soilmu_a_zz001.shp", meta["inputs"])
        self.assertIn("ZZ002/spatial/soilsa_a_zz002.shp", meta["inputs"])
        self.assertIn("ZZ001/tabular/comp.txt", meta["inputs"])
        self.assertEqual(meta["format"], package.FORMAT)

    def test_derives_what_the_fixture_derives(self):
        got = package.derive(package.read(self.out), ["ZZ001", "ZZ002"])
        want = package.derive(package.read(self.expected), ["ZZ001", "ZZ002"])
        by = lambda xs, k: sorted(xs, key=lambda r: r[k])                     # noqa: E731
        self.assertEqual(by(got.map_units, "mukey"), by(want.map_units, "mukey"))
        self.assertEqual(by(got.components, "cokey"), by(want.components, "cokey"))
        self.assertEqual(by(got.horizons, "chkey"), by(want.horizons, "chkey"))
        self.assertEqual(got.ground_types, want.ground_types)

    def test_one_area_and_refusals(self):
        out = os.path.join(self.tmp.name, "one")
        with contextlib.redirect_stdout(io.StringIO()):
            meta = self.prepare.prepare(self.sources, out, only=["ZZ002"], log=lambda *a: None)
        self.assertEqual([x["areasymbol"] for x in meta["areas"]], ["ZZ002"])
        with self.assertRaisesRegex(SystemExit, "isn't empty"):
            self.prepare.prepare(self.sources, out, log=lambda *a: None)
        with self.assertRaisesRegex(SystemExit, "no survey area ZZ009"):
            self.prepare.prepare(self.sources, os.path.join(self.tmp.name, "x"), only=["ZZ009"])
        for ext in (".shp", ".shx", ".dbf", ".prj"):
            os.remove(os.path.join(self.sources, "ZZ002", "spatial", "soilsa_a_zz002" + ext))
        with self.assertRaisesRegex(SystemExit, "ZZ002: no survey area boundary"):
            self.prepare.prepare(self.sources, os.path.join(self.tmp.name, "y"), log=lambda *a: None)


if __name__ == "__main__":
    unittest.main()
