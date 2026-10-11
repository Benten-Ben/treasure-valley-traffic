"""The window-rasterising helper (rasterize.py) on synthetic vectors. Needs the worker image (GDAL, NumPy, SciPy): the
tests skip elsewhere, and in the worker image a skip counts as a failure.

    docker run --rm --memory 1g --cpus 1 --network none -v "$PWD":/repo -w /repo tvt-worker \\
      python -m unittest discover -s basemap/ground -t . -v
"""

import math
import os
import shutil
import tempfile
import unittest

try:
    import numpy as np
    from osgeo import gdal, ogr, osr
    from basemap.ground import rasterize as R
except ImportError:                                  # outside the worker image
    np = None

from basemap.ground import fgb, grid as G, manifest as M
from basemap.ground.tests.test_manifest import SSURGO

X0, Y0 = 500000.0, 4800000.0                         # a corner well inside the grid, on every level


def srs(code):
    s = osr.SpatialReference()
    s.ImportFromEPSG(code)
    s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return s


def write_layer(path, epsg, features, geom_type=None, fields=(("id", "int"), ("ground_type", "int"))):
    """A FlatGeobuf (with its spatial index) of (wkt, {field: value}) features."""
    types = {"int": ogr.OFTInteger, "long": ogr.OFTInteger64, "double": ogr.OFTReal, "string": ogr.OFTString}
    ds = ogr.GetDriverByName("FlatGeobuf").CreateDataSource(path)
    lyr = ds.CreateLayer("layer", srs(epsg), geom_type or ogr.wkbMultiPolygon, options=["SPATIAL_INDEX=YES"])
    for name, t in fields:
        lyr.CreateField(ogr.FieldDefn(name, types[t]))
    for wkt, attrs in features:
        f = ogr.Feature(lyr.GetLayerDefn())
        g = ogr.CreateGeometryFromWkt(wkt)
        if geom_type in (None, ogr.wkbMultiPolygon) and g.GetGeometryType() == ogr.wkbPolygon:
            g = ogr.ForceToMultiPolygon(g)
        f.SetGeometry(g)
        for k, v in attrs.items():
            f.SetField(k, v)
        lyr.CreateFeature(f)
    ds = None
    return path


def square(x, y, size):
    return f"POLYGON(({x} {y},{x + size} {y},{x + size} {y + size},{x} {y + size},{x} {y}))"


def target(res, width, height, x0=X0, y0=Y0 + 400):
    """A grid window with its upper-left corner at (x0, y0)."""
    return G.window((x0, y0 - height * res, x0 + width * res, y0), res, snap="exact")


@unittest.skipIf(np is None, "needs the worker image (GDAL, NumPy, SciPy)")
class RasterizeTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def path(self, name):
        return os.path.join(self.dir, name)

    def test_proj_never_goes_online(self):
        self.assertFalse(osr.GetPROJEnableNetwork())

    def test_cell_centres_inside(self):
        # A 40 m square on 2 m cell edges burns exactly 20 x 20 cells; shifted by a quarter cell, still 400.
        p = write_layer(self.path("a.fgb"), 32611, [(square(X0 + 20, Y0 + 100, 40), {"id": 1, "ground_type": 7}),
                                                     (square(X0 + 100.5, Y0 + 100.5, 40), {"id": 2, "ground_type": 9})])
        t = target(2.0, 100, 200)
        a = R.rasterize(t, p)
        self.assertEqual(a.shape, (200, 100))
        self.assertEqual(a.dtype, np.uint8)
        self.assertEqual(int(a.sum()), 800)
        b = R.rasterize(t, p, attribute="ground_type", dtype="uint16")
        self.assertEqual(sorted(np.unique(b).tolist()), [0, 7, 9])
        self.assertEqual(int((b == 7).sum()), 400)
        self.assertEqual(int((b == 9).sum()), 400)
        c = R.rasterize(t, p, where="ground_type = 9", burn=3)
        self.assertEqual(int((c == 3).sum()), 400)
        touched = R.rasterize(t, p, where="ground_type = 9", all_touched=True)
        self.assertEqual(int(touched.sum()), 21 * 21)             # its edges cut cells: one more row and column

    def test_holes_and_the_array_orientation(self):
        ring = (f"POLYGON(({X0} {Y0},{X0 + 100} {Y0},{X0 + 100} {Y0 + 100},{X0} {Y0 + 100},{X0} {Y0}),"
                f"({X0 + 40} {Y0 + 40},{X0 + 60} {Y0 + 40},{X0 + 60} {Y0 + 60},{X0 + 40} {Y0 + 60},"
                f"{X0 + 40} {Y0 + 40}))")
        p = write_layer(self.path("ring.fgb"), 32611, [(ring, {"id": 1, "ground_type": 1}),
                                                        (square(X0, Y0 + 300, 10), {"id": 2, "ground_type": 2})])
        t = target(10.0, 10, 40)                                # rows run north to south from Y0 + 400
        a = R.rasterize(t, p, attribute="ground_type")
        self.assertEqual(int((a == 1).sum()), 100 - 4)
        self.assertEqual(a[30:40, 0:10][4, 4], 0)               # the hole
        self.assertEqual(a[9, 0], 2)                            # the small square, 300-310 m up: row 9 from the top
        self.assertEqual(int((a == 2).sum()), 1)

    def test_windows_match_the_whole(self):
        # Buffers and feathers computed per padded window and cut back to the core equal those on the whole area.
        rng = np.random.default_rng(7)
        feats = [(square(X0 + float(x), Y0 + float(y), float(s)), {"id": i, "ground_type": i % 5 + 1})
                 for i, (x, y, s) in enumerate(zip(rng.uniform(0, 900, 60), rng.uniform(0, 900, 60),
                                                   rng.uniform(4, 60, 60)))]
        p = write_layer(self.path("many.fgb"), 32611, feats)
        bounds = (X0, Y0, X0 + 960, Y0 + 960)
        halo = 21.0
        whole = G.window(bounds, 2.0).pad_m(halo + 40)
        m_whole = R.rasterize(whole, p, attribute="ground_type")
        grown_whole = R.grow(m_whole > 0, 5.0, 2.0)
        soft_whole = R.feather(m_whole == 3, 20.0, 2.0)
        n = 0
        for core, padded in G.windows(2.0, 100, bounds=bounds, halo_m=halo):
            m = R.rasterize(padded, p, attribute="ground_type")
            rows, cols = core.inner(padded)
            wr, wc = core.inner(whole)
            np.testing.assert_array_equal(m[rows, cols], m_whole[wr, wc])
            np.testing.assert_array_equal(R.grow(m > 0, 5.0, 2.0)[rows, cols], grown_whole[wr, wc])
            np.testing.assert_allclose(R.feather(m == 3, 20.0, 2.0)[rows, cols], soft_whole[wr, wc], atol=1e-6)
            n += 1
        self.assertEqual(n, 25)

    def test_grow_by_centre_distance(self):
        m = np.zeros((21, 21), bool)
        m[10, 10] = True
        g = R.grow(m, 2.0, 0.5)                                 # 4 cells: lattice points within radius 4
        self.assertEqual(int(g.sum()), sum(1 for i in range(-4, 5) for j in range(-4, 5) if i * i + j * j <= 16))
        self.assertTrue(np.array_equal(R.grow(m, 0, 0.5), m))
        d = R.distance(m, 0.5)
        self.assertAlmostEqual(float(d[10, 14]), 2.0)
        self.assertAlmostEqual(float(d[13, 14]), 2.5)
        self.assertTrue(np.isinf(R.distance(np.zeros((3, 3), bool), 1.0)).all())

    def test_feather(self):
        m = np.zeros((1, 40), bool)
        m[:, :20] = True                                        # edge between columns 19 and 20
        w = R.feather(m, 20.0, 2.0)                             # 20 m ramp: 5 cells each side
        self.assertAlmostEqual(float(w[0, 19]), 0.55, places=6)
        self.assertAlmostEqual(float(w[0, 20]), 0.45, places=6)
        self.assertEqual(float(w[0, 0]), 1.0)
        self.assertEqual(float(w[0, 39]), 0.0)
        self.assertTrue(np.all(np.diff(w[0]) <= 0))
        np.testing.assert_allclose(w + R.feather(~m, 20.0, 2.0), 1.0, atol=1e-6)   # two regions sum to 1
        self.assertEqual(float(R.feather(np.ones((2, 2), bool), 20, 2).min()), 1.0)
        self.assertEqual(float(R.feather(np.zeros((2, 2), bool), 20, 2).max()), 0.0)

    def test_datum_policy(self):
        # The same coordinates labelled NAD83 / UTM 11N burn the same cells: the null shift, no grid, no network.
        feats = [(square(X0 + 20, Y0 + 100, 40), {"id": 1, "ground_type": 7})]
        a = R.rasterize(target(2.0, 100, 200), write_layer(self.path("wgs.fgb"), 32611, feats))
        for code in (26911, 6340):
            b = R.rasterize(target(2.0, 100, 200), write_layer(self.path(f"{code}.fgb"), code, feats))
            np.testing.assert_array_equal(a, b)
        # lon/lat (WGS 84 and NAD83) project onto the grid: the square's corners, as lon/lat, land in the same cells
        from ingest.utm import from_utm
        x, y, s = X0 + 20.4, Y0 + 100.4, 38.2                    # edges between cell centres: no ties
        ll = [from_utm(px, py) for px, py in ((x, y), (x + s, y), (x + s, y + s), (x, y + s), (x, y))]
        wkt = "POLYGON((" + ",".join(f"{lon!r} {lat!r}" for lon, lat in ll) + "))"
        for code in (4326, 4269):
            c = R.rasterize(target(2.0, 100, 200), write_layer(self.path(f"ll{code}.fgb"), code,
                                                               [(wkt, {"id": 1, "ground_type": 7})]))
            self.assertEqual(int(c.sum()), 19 * 19, code)
        # NAD83 rasters: warp_srs gives the null shift for gdal.Warp
        ct = osr.CoordinateTransformation(srs_from_wkt(R.warp_srs("EPSG:26911")), srs(32611))
        px, py = ct.TransformPoint(550000.0, 4820000.0)[:2]
        self.assertAlmostEqual(px, 550000.0, places=6)
        self.assertAlmostEqual(py, 4820000.0, places=6)
        ct = osr.CoordinateTransformation(srs_from_wkt(R.warp_srs("EPSG:5070")), srs(32611))
        self.assertTrue(all(math.isfinite(v) for v in ct.TransformPoint(-1500000.0, 2500000.0)[:2]))

    def test_raster_targets(self):
        # target_of: a raster's own grid, e.g. a NAIP window at 0.6 m in EPSG:26911, burned from grid-CRS vectors.
        path = self.path("naip.tif")
        ds = gdal.GetDriverByName("GTiff").Create(path, 300, 200, 1, gdal.GDT_Byte)
        ds.SetGeoTransform((X0 - 0.3, 0.6, 0.0, Y0 + 150.3, 0.0, -0.6))
        ds.SetProjection(srs(26911).ExportToWkt())
        ds = None
        t = R.target_of(path, window=(10, 20, 100, 100))
        self.assertEqual(t.shape, (100, 100))
        self.assertAlmostEqual(t.transform[0], X0 - 0.3 + 6.0)
        self.assertAlmostEqual(t.transform[3], Y0 + 150.3 - 12.0)
        p = write_layer(self.path("sq.fgb"), 32611, [(square(X0 + 5.7, Y0 + 80.1, 30.0), {"id": 1, "ground_type": 1})])
        a = R.rasterize(t, p)
        self.assertEqual(int(a.sum()), 50 * 50)                   # 30 m of 0.6 m cells, centres strictly inside

    def test_reads_a_manifest_layer(self):
        folder = M.export_dir(self.dir, "soils", "20261012T031500Z")
        os.makedirs(folder)
        write_layer(os.path.join(folder, "ground.fgb"), 32611,
                    [(square(X0 + 20, Y0 + 100, 40), {"id": 1, "ground_type": 7})])
        m = M.write(folder, "soils", [SSURGO],
                    [{"name": "ground", "file": "ground.fgb", "format": "FlatGeobuf", "inputs": ["ssurgo"],
                      "base": False}])
        lay = M.read(folder).layer("ground")
        self.assertEqual(lay["fields"], {"id": "int", "ground_type": "int"})
        self.assertEqual(lay["features"], 1)
        a = R.rasterize(target(2.0, 100, 200), lay, attribute="ground_type")
        self.assertEqual(int((a == 7).sum()), 400)
        self.assertEqual(m.layer("ground")["sha256"], M.sha256_of(lay.path))


@unittest.skipIf(np is None, "needs the worker image (GDAL)")
class HeaderAgreesWithGdalTest(unittest.TestCase):
    """fgb.py reads GDAL's FlatGeobuf as GDAL does (and PostGIS's: test_manifest.py's fixtures)."""

    def test_columns_types_count_crs(self):
        d = tempfile.mkdtemp()
        try:
            path = os.path.join(d, "t.fgb")
            ds = ogr.GetDriverByName("FlatGeobuf").CreateDataSource(path)
            lyr = ds.CreateLayer("t", srs(32611), ogr.wkbLineString, options=["SPATIAL_INDEX=YES"])
            for name, t in (("id", ogr.OFTInteger), ("big", ogr.OFTInteger64), ("width", ogr.OFTReal),
                            ("name", ogr.OFTString), ("when", ogr.OFTDateTime)):
                lyr.CreateField(ogr.FieldDefn(name, t))
            for i in range(5):
                f = ogr.Feature(lyr.GetLayerDefn())
                f.SetGeometry(ogr.CreateGeometryFromWkt(f"LINESTRING({X0 + i} {Y0},{X0 + i + 10} {Y0 + 10})"))
                f.SetField("id", i)
                lyr.CreateFeature(f)
            ds = None
            h = fgb.read_header(path)
            self.assertEqual(h.geometry_type, "LineString")
            self.assertEqual(h.columns, {"id": "int", "big": "long", "width": "double", "name": "string",
                                         "when": "datetime"})
            self.assertEqual(h.features_count, 5)
            self.assertEqual(h.crs, "EPSG:32611")
            src = ogr.Open(path)
            back = src.GetLayer(0)
            self.assertEqual(back.GetFeatureCount(), h.features_count)
            self.assertEqual([back.GetLayerDefn().GetFieldDefn(i).GetName()
                              for i in range(back.GetLayerDefn().GetFieldCount())], list(h.columns))
        finally:
            shutil.rmtree(d)

    def test_postgis_fixture(self):
        from basemap.ground.tests.test_manifest import FIXTURES
        path = os.path.join(FIXTURES, "squares.fgb")
        h = fgb.read_header(path)
        src = ogr.Open(path)
        lyr = src.GetLayer(0)
        defn = lyr.GetLayerDefn()
        self.assertEqual(lyr.GetFeatureCount(), h.features_count)
        self.assertEqual([defn.GetFieldDefn(i).GetName() for i in range(defn.GetFieldCount())], list(h.columns))
        self.assertEqual(ogr.GeometryTypeToName(lyr.GetGeomType()).replace(" ", "").lower(), h.geometry_type.lower())
        self.assertEqual(lyr.GetSpatialRef().GetAuthorityCode(None), "32611")
        self.assertEqual(tuple(lyr.GetExtent()), (h.envelope[0], h.envelope[2], h.envelope[1], h.envelope[3]))


def srs_from_wkt(wkt):
    s = osr.SpatialReference()
    s.ImportFromWkt(wkt)
    s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return s


if __name__ == "__main__":
    unittest.main()
