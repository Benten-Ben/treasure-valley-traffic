"""Mask v0's build (mask.py) on synthetic inputs made here: an OpenStreetMap file read through GDAL's OSM driver, an NHD
GeoPackage in NAD83, roofs in Web Mercator (also as a PMTiles file), and a CDL raster in NAD83 Albers. Every id, tag
and coordinate is invented. Needs the worker image (GDAL, NumPy, SciPy): the tests skip elsewhere, and in the worker
image a skip counts as a failure.

    /srv/tvt/work/bin/worker-test -C <checkout> discover -s basemap/ground -t .
"""

import json
import math
import os
import shutil
import signal
import tempfile
import time
import unittest
from unittest import mock
from xml.sax.saxutils import quoteattr

try:
    import numpy as np
    from osgeo import gdal, ogr, osr
    from basemap.ground import mask as K, rasterize as R
except ImportError:                                  # outside the worker image
    np = None

from basemap.ground import grid as G, inputs as I, manifest as M, maskrules as MR
from basemap.ground.tests.test_inputs import fgb_layer, write_export, write_farm
from basemap.ground.tests.test_manifest import SSURGO
from ingest.utm import from_utm

X0, Y0 = 551000.0, 4822000.0                         # in box d, on every level of the grid
BOUNDS = (X0 - 100, Y0 - 100, X0 + 700, Y0 + 900)
MERC_R = 6378137.0


def lonlat(x, y):
    return from_utm(X0 + x, Y0 + y)


def mercator(x, y):
    lon, lat = lonlat(x, y)
    return MERC_R * math.radians(lon), MERC_R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def square(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


class OsmFile:
    """A small OSM XML file, in metres from (X0, Y0)."""

    def __init__(self):
        self.nodes, self.ways, self.rels = [], [], []

    def _node(self, x, y):
        lon, lat = lonlat(x, y)
        self.nodes.append((1000 + len(self.nodes), lon, lat))
        return self.nodes[-1][0]

    def way(self, pts, closed=False, **tags):
        ids = [self._node(x, y) for x, y in pts]
        if closed:
            ids.append(ids[0])
        wid = 100 + len(self.ways)
        self.ways.append((wid, ids, {k.replace("__", ":"): v for k, v in tags.items()}))
        return wid

    def relation(self, members, **tags):
        rid = 900 + len(self.rels)
        self.rels.append((rid, members, tags))
        return rid

    def write(self, path):
        out = ['<?xml version="1.0" encoding="UTF-8"?>', '<osm version="0.6" generator="test_mask">']
        for nid, lon, lat in self.nodes:
            out.append(f'  <node id="{nid}" version="1" lat="{lat:.9f}" lon="{lon:.9f}"/>')
        for wid, ids, tags in self.ways:
            out.append(f'  <way id="{wid}" version="1">')
            out += [f'    <nd ref="{n}"/>' for n in ids]
            out += [f'    <tag k={quoteattr(k)} v={quoteattr(v)}/>' for k, v in tags.items()]
            out.append("  </way>")
        for rid, members, tags in self.rels:
            out.append(f'  <relation id="{rid}" version="1">')
            out += [f'    <member type="way" ref="{w}" role="{role}"/>' for w, role in members]
            out += [f'    <tag k={quoteattr(k)} v={quoteattr(v)}/>' for k, v in tags.items()]
            out.append("  </relation>")
        out.append("</osm>")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")


def osm_fixture(path):
    o = OsmFile()
    o.way([(0, 0), (200, 0)], highway="residential", name="Test Street")
    o.way([(0, 20), (200, 20)], highway="footway", footway="sidewalk")
    o.way([(0, 60), (200, 60)], highway="path", surface="dirt")                          # trodden soil: ground
    o.way([(0, 80), (200, 80)], highway="primary", tunnel="yes")                         # out of sight
    o.way([(0, 100), (200, 100)], highway="footway", surface="concrete")                # a paved path
    o.way(square(300, 0, 340, 40), closed=True, amenity="parking")
    o.way(square(300, 100, 360, 160), closed=True, natural="water")
    o.way([(0, 200), (200, 200)], waterway="canal")
    o.way([(0, 260), (200, 260)], waterway="stream", intermittent="yes")
    o.way([(0, 320), (200, 320)], railway="rail")                                        # a line: a 5 m bed
    o.way([(0, 800), (200, 800)], aeroway="runway")                                      # a line: 45 m
    o.way([(300, 800), (500, 800)], aeroway="taxiway")                                   # a line: 23 m
    o.way(square(400, 300, 440, 340), closed=True, aeroway="apron")
    o.way(square(500, 300, 540, 340), closed=True, landuse="railway")
    o.way(square(400, 0, 420, 20), closed=True, building="yes")                         # OSM buildings: unused
    o.way(square(450, 0, 480, 30), closed=True, highway="pedestrian", area="yes")
    outer = o.way(square(300, 400, 400, 500), closed=True)
    inner = o.way(square(330, 430, 370, 470), closed=True)
    o.relation([(outer, "outer"), (inner, "inner")], type="multipolygon", natural="water", water="pond")
    o.way(square(500, 100, 510, 110), closed=True, leisure="swimming_pool")
    plaza = o.way(square(620, 600, 680, 640), closed=True)
    o.relation([(plaza, "outer")], type="multipolygon", highway="pedestrian", name="Test Plaza")   # no area=yes
    o.way([(0, 550), (200, 550)], highway="residential", bridge="yes", layer="1")
    o.write(path)
    return path


def srs(code):
    s = osr.SpatialReference()
    s.ImportFromEPSG(code)
    s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return s


def ring_wkt(pts, fn):
    pts = list(pts) + [pts[0]]
    return "(" + ",".join(f"{a!r} {b!r}" for a, b in (fn(x, y) for x, y in pts)) + ")"


def line_wkt(pts, fn):
    return "LINESTRING(" + ",".join(f"{a!r} {b!r}" for a, b in (fn(x, y) for x, y in pts)) + ")"


NHD_FIELDS = (("permanent_identifier", ogr.OFTString), ("ftype_name", ogr.OFTString),
              ("hydrographiccategory", ogr.OFTString), ("class", ogr.OFTString),
              ("relationshiptosurface", ogr.OFTString), ("streamorder", ogr.OFTInteger)) if np is not None else ()


def nhd_fixture(path):
    """NHD's three layers, in NAD83 lon/lat. The coordinates are WGS 84's numbers (from_utm), so under the null
    datum shift they land exactly on the metres they were made from."""
    ds = ogr.GetDriverByName("GPKG").CreateDataSource(path)
    layers = {
        "waterbody": (ogr.wkbMultiPolygon, [
            (f"MULTIPOLYGON(({ring_wkt(square(0, 400, 50, 450), lonlat)}))",
             {"permanent_identifier": "wb-1", "ftype_name": "Lake/Pond", "hydrographiccategory": "Perennial"}),
            (f"MULTIPOLYGON(({ring_wkt(square(100, 400, 150, 450), lonlat)}))",
             {"permanent_identifier": "wb-2", "ftype_name": "Swamp/Marsh"})]),
        "area": (ogr.wkbMultiPolygon, [
            (f"MULTIPOLYGON(({ring_wkt(square(0, 600, 200, 612), lonlat)}))",
             {"permanent_identifier": "ar-1", "ftype_name": "Canal/Ditch"}),
            (f"MULTIPOLYGON(({ring_wkt(square(300, 600, 400, 640), lonlat)}))",
             {"permanent_identifier": "ar-2", "ftype_name": "Inundation Area"})]),
        "flowline": (ogr.wkbMultiLineString, [
            ("MULTI" + line_wkt([(0, 650), (200, 650)], lonlat).replace("LINESTRING(", "LINESTRING((") + ")",
             {"permanent_identifier": "fl-1", "class": "stream_river", "hydrographiccategory": "Intermittent",
              "streamorder": 1}),
            ("MULTI" + line_wkt([(0, 700), (200, 700)], lonlat).replace("LINESTRING(", "LINESTRING((") + ")",
             {"permanent_identifier": "fl-2", "class": "canal_ditch"}),
            ("MULTI" + line_wkt([(0, 750), (200, 750)], lonlat).replace("LINESTRING(", "LINESTRING((") + ")",
             {"permanent_identifier": "fl-3", "class": "pipeline", "relationshiptosurface": "Underground"})]),
    }
    for name, (gtype, feats) in layers.items():
        lyr = ds.CreateLayer(name, srs(4269), gtype)
        for fname, ftype in NHD_FIELDS:
            lyr.CreateField(ogr.FieldDefn(fname, ftype))
        for wkt, attrs in feats:
            f = ogr.Feature(lyr.GetLayerDefn())
            f.SetGeometry(ogr.CreateGeometryFromWkt(wkt))
            for k, v in attrs.items():
                f.SetField(k, v)
            lyr.CreateFeature(f)
    ds = None
    return path


ROOFS = (square(400, 0, 420, 20), square(600, 400, 615, 412))


def roofs_fixture(path, release="2026-09-23.1"):
    """Two roofs in Web Mercator (EPSG:3857, as buildings.pmtiles holds them), and the tiles manifest's entry."""
    ds = ogr.GetDriverByName("GPKG").CreateDataSource(path)
    lyr = ds.CreateLayer("buildings", srs(3857), ogr.wkbPolygon)
    for pts in ROOFS:
        f = ogr.Feature(lyr.GetLayerDefn())
        f.SetGeometry(ogr.CreateGeometryFromWkt(f"POLYGON({ring_wkt(pts, mercator)})"))
        lyr.CreateFeature(f)
    ds = None
    if release:
        with open(os.path.join(os.path.dirname(path), "buildings.json"), "w") as f:
            json.dump({"buildings": {"source": f"Overture Maps {release}, theme=buildings/type=building",
                                     "built": "2026-10-05"}}, f)
    return path


ALBERS_CELL = 10.0


def cdl_fixture(path):
    """A CDL raster on its own 10 m Albers grid (EPSG:5070): a 4 x 4 block of class 124 (developed, high), a 3 x 3
    block of 123 and a 4 x 4 block of 82 (cropland), around points given in grid metres."""
    to_albers = osr.CoordinateTransformation(R.srs_of(G.CRS), R.srs_of("EPSG:5070"))
    pts = [to_albers.TransformPoint(X0 + x, Y0 + y)[:2] for x, y in ((0, 0), (700, 0), (0, 900), (700, 900))]
    x0 = math.floor(min(p[0] for p in pts) / 10) * 10 - 100        # Albers turns about 13 degrees from UTM here
    y0 = math.ceil(max(p[1] for p in pts) / 10) * 10 + 100
    size = int(math.ceil((max(max(p[0] for p in pts) - x0, y0 - min(p[1] for p in pts)) + 100) / 10))
    a = np.zeros((size, size), np.uint8)

    def cell(x, y):
        px, py = to_albers.TransformPoint(X0 + x, Y0 + y)[:2]
        return int((y0 - py) // 10), int((px - x0) // 10)

    r, c = cell(560, 760)
    a[r - 2:r + 2, c - 2:c + 2] = 124
    r, c = cell(560, 600)
    a[r - 1:r + 2, c - 1:c + 2] = 123
    r, c = cell(560, 200)
    a[r - 2:r + 2, c - 2:c + 2] = 82
    ds = gdal.GetDriverByName("GTiff").Create(path, size, size, 1, gdal.GDT_Byte)
    ds.SetGeoTransform((x0, ALBERS_CELL, 0, y0, 0, -ALBERS_CELL))
    ds.SetSpatialRef(srs(5070))
    ds.GetRasterBand(1).WriteArray(a)
    ds.GetRasterBand(1).SetNoDataValue(0)
    ds = None
    return path


def features(path):
    ds = ogr.Open(path)
    lyr = ds.GetLayer(0)
    out = []
    for f in lyr:
        d = f.items()
        d["geom"] = f.GetGeometryRef().Clone()
        out.append(d)
    return out


@unittest.skipIf(np is None, "needs the worker image (GDAL, NumPy, SciPy)")
class MaskTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        cls.src = os.path.join(cls.dir, "src")
        os.makedirs(os.path.join(cls.src, "cut"))
        cls.osm = osm_fixture(os.path.join(cls.src, "cut", "valley.osm"))
        with open(os.path.join(cls.src, "cut", "valley.json"), "w") as f:
            json.dump({"extract": "idaho-test.osm.pbf", "md5": "0123456789abcdef0123456789abcdef",
                       "data_as_of": "2026-10-05T20:21:35Z", "sha256": M.sha256_of(cls.osm)}, f)
        cls.nhd = nhd_fixture(os.path.join(cls.src, "nhd.gpkg"))
        os.makedirs(os.path.join(cls.src, "roofs"))
        cls.roofs = roofs_fixture(os.path.join(cls.src, "roofs", "buildings.gpkg"))
        cls.cdl = cdl_fixture(os.path.join(cls.src, "cdl_2025_10m.tif"))
        cls.archive = os.path.join(cls.dir, "archive")
        cls.m = K.build(cls.archive, cls.osm, cls.nhd, cls.roofs, cls.cdl, build_id="20261011T120000Z",
                        command="test", log=lambda *a: None)      # the whole grid (the fixtures are all in BOUNDS)
        cls.layers = {n: features(os.path.join(cls.m.folder, f"{n}.fgb")) for n in MR.LAYERS}
        cls.win = G.window(BOUNDS, G.LEVELS["classes"], snap="exact")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir)

    def build(self, **kw):
        args = dict(archive=os.path.join(self.dir, "other"), osm=self.osm, nhd=self.nhd, roofs=self.roofs,
                    cdl=self.cdl, log=lambda *a: None)
        args.update(kw)
        return K.build(**args)

    def at(self, arr, x, y):
        """The cell of a window-sized array holding the point (X0 + x, Y0 + y)."""
        w = self.win
        return bool(arr[int((w.north - (Y0 + y)) / w.res), int((X0 + x - w.west) / w.res)])

    # -- the export ----------------------------------------------------------------------------------------------

    def test_the_manifest(self):
        m = M.read(self.m.folder)                                   # every file, header and sha256 checked
        self.assertEqual(m.plugin, "ground_mask")
        self.assertEqual([lay.name for lay in m.layers], list(MR.LAYERS))
        for lay in m.layers:
            self.assertEqual((lay["format"], lay["geometry"], lay["crs"]), ("FlatGeobuf", "MultiPolygon", G.CRS))
            self.assertEqual(lay["fields"], dict(MR.LAYERS[lay.name][2]))
            self.assertEqual(lay["republish"], "yes")
            self.assertEqual(lay["licence"], "public-domain" if lay["inputs"] == ["cdl"] else "ODbL-1.0", lay.name)
            self.assertEqual(lay["features"], len(self.layers[lay.name]))
        self.assertEqual(m.layer("water")["inputs"], ["nhd", "osm"])
        self.assertEqual(m.layer("covered")["inputs"], ["osm", "overture-buildings", "nhd", "cdl"])
        inp = m.inputs
        self.assertEqual(sorted(inp), ["cdl", "nhd", "osm", "overture-buildings"])
        self.assertEqual(inp["osm"]["version"], "0123456789abcdef0123456789abcdef")
        self.assertEqual(inp["osm"]["sha256"], M.sha256_of(self.osm))
        self.assertIn("idaho-test.osm.pbf", inp["osm"]["note"])
        self.assertIn("Malheur", inp["osm"]["note"])
        self.assertEqual(inp["overture-buildings"]["version"], "2026-09-23.1")
        self.assertEqual(inp["nhd"]["version"], K.NHD_VERSION)
        self.assertEqual(inp["cdl"]["version"], "2025")
        for name, e in inp.items():
            raw = I.RAW_BY_NAME[name]
            self.assertEqual((e["licence"], e["republish"], e["credit"]), (raw.licence, "yes", raw.credit))
        self.assertEqual(m.data["command"], "test")
        self.assertIn("over the whole grid", m.data["note"])
        self.assertFalse(os.path.exists(os.path.join(m.folder, K.Out.RAW)))   # the buffers one by one: gone
        self.assertEqual(os.listdir(os.path.join(self.archive, "ground_mask", K.STAGING)), [])

    def test_the_ground_reads_it(self):
        archive = os.path.join(self.dir, "with-soils")
        shutil.copytree(self.archive, archive)
        write_export(archive, "soils", [fgb_layer("ground", ["ssurgo"])], [SSURGO])
        write_farm(archive)
        plan = I.resolve(I.exports(archive))
        self.assertEqual(plan.status, "painted")
        self.assertEqual([lay.name for lay in plan.choice("ground_mask").layers], list(MR.LAYERS))
        self.assertEqual(plan.republish, "yes")
        self.assertIn("Overture Maps Foundation, © OpenStreetMap contributors", plan.credits)
        self.assertIn("U.S. Geological Survey, National Hydrography Dataset", plan.credits)
        self.assertEqual(K.latest(archive).build, "20261011T120000Z")

    # -- what's in it --------------------------------------------------------------------------------------------

    def test_roads(self):
        roads = self.layers["roads"]
        got = sorted((r["highway"], r["kind"], r["width"], r["bridge"]) for r in roads)
        self.assertEqual(got, [("footway", "path", 2.0, False), ("footway", "walkway", 1.5, False),
                               ("residential", "street", 10.4, False), ("residential", "street", 10.4, True)])
        street = next(r for r in roads if r["highway"] == "residential" and not r["bridge"])
        self.assertEqual((street["surface"], street["width_from"]), ("unknown", "class"))
        self.assertRegex(street["ref"], r"^w\d+$")
        # 200 m at 10.4 m, with round ends (a 12-gon of radius 5.2 m: 3 r^2)
        self.assertAlmostEqual(street["geom"].GetArea(), 200 * 10.4 + 3 * 5.2 ** 2, delta=1.0)

    def test_paving_and_water(self):
        self.assertEqual(sorted((p["kind"], p["surface"], p["ref"][0]) for p in self.layers["paving"]),
                         [("highway_area", "unknown", "r"), ("highway_area", "unknown", "w"),
                          ("parking", "unknown", "w")])                 # the plaza is a relation
        water = sorted((w["source"], w["kind"], bool(w["intermittent"]), w["width"] or 0.0)
                       for w in self.layers["water"])                # width: None for areas
        self.assertEqual(water, [("nhd", "canal", False, 0.0),
                                 ("nhd", "lake", False, 0.0), ("nhd", "stream", True, 2.0),
                                 ("osm", "canal", False, 6.0), ("osm", "lake", False, 0.0),
                                 ("osm", "lake", False, 0.0), ("osm", "pool", False, 0.0),
                                 ("osm", "stream", True, 2.5)])
        self.assertEqual([w["width"] for w in self.layers["water"] if w["source"] == "osm" and w["kind"] == "pool"],
                         [None])
        holed = next(w for w in self.layers["water"] if w["ref"].startswith("r"))   # the pond with an island
        # OpenStreetMap's coordinates are whole 1e-7 degrees (about 1 cm), so a 100 m square is within a few m2
        self.assertAlmostEqual(holed["geom"].GetArea(), 100 ** 2 - 40 ** 2, delta=4.0)
        self.assertEqual(sorted(w["ref"] for w in self.layers["water"] if w["source"] == "nhd"),
                         ["nhd:ar-1", "nhd:fl-1", "nhd:wb-1"])          # fl-2, a canal line, isn't painted

    def test_nad83_is_read_with_the_null_shift(self):
        lake = next(w for w in self.layers["water"] if w["ref"] == "nhd:wb-1")
        x0, x1, y0, y1 = lake["geom"].GetEnvelope()
        for got, want in zip((x0, y0, x1, y1), (X0, Y0 + 400, X0 + 50, Y0 + 450)):
            self.assertAlmostEqual(got, want, delta=0.001)          # a NAD83-to-WGS 84 grid would move it ~1 m

    def test_roofs(self):
        roofs = self.layers["roofs"]
        self.assertEqual(len(roofs), 2)
        areas = sorted(r["geom"].GetArea() for r in roofs)
        self.assertAlmostEqual(areas[0], 15 * 12, delta=0.5)
        self.assertAlmostEqual(areas[1], 20 * 20, delta=0.5)

    def test_covered_what(self):
        whats = {c["what"] for c in self.layers["covered"]}
        self.assertEqual(whats, {"road", "paving", "water", "rail", "aeroway", "roof", "developed"})
        for c in self.layers["covered"]:
            self.assertEqual(c["buffer"], MR.SAMPLE_BUFFER[c["what"]])

    def test_covered_is_dissolved_by_block(self):
        cov = self.layers["covered"]
        keys = []
        for c in cov:
            x0, x1, y0, y1 = c["geom"].GetEnvelope()
            bx, by = math.floor((x0 + 1e-6 - G.WEST) / 1000), math.floor((G.NORTH - y1 + 1e-6) / 1000)
            self.assertLessEqual(x1, G.WEST + (bx + 1) * 1000 + 1e-6)
            self.assertGreaterEqual(y0, G.NORTH - (by + 1) * 1000 - 1e-6)
            keys.append((bx, by, c["what"]))
        self.assertEqual(len(keys), len(set(keys)))                 # one piece per block and what
        self.assertEqual(sorted(c["id"] for c in cov), list(range(1, len(cov) + 1)))

    # -- through the rasterising helper --------------------------------------------------------------------------

    def test_sampling_and_painting_cells(self):
        cov = K.covered(self.win, self.m)
        roads = K.exact(self.win, self.m, "roads")
        roofs = K.exact(self.win, self.m, "roofs")
        water = K.exact(self.win, self.m, "water")
        paving = K.exact(self.win, self.m, "paving")
        # The street: 5.2 m each side exact, 7.2 m for sampling.
        self.assertTrue(self.at(roads, 100, 4.9))
        self.assertFalse(self.at(roads, 100, 5.6))
        self.assertTrue(self.at(cov, 100, 6.9))
        self.assertFalse(self.at(cov, 100, 7.6))
        # The dirt path is ground; the tunnel isn't seen.
        self.assertFalse(self.at(cov, 100, 60.1) or self.at(roads, 100, 60.1))
        self.assertFalse(self.at(cov, 100, 80.1))
        # A roof, and 1 m around it for sampling (Overture's, not OSM's building, which is the same square).
        self.assertTrue(self.at(roofs, 410, 10))
        self.assertFalse(self.at(roofs, 420.6, 10))
        self.assertTrue(self.at(cov, 420.6, 10))
        self.assertFalse(self.at(cov, 421.4, 10))
        # The lake: 5 m around it; not in its island.
        self.assertTrue(self.at(water, 330, 130))
        self.assertTrue(self.at(cov, 364.6, 130))
        self.assertFalse(self.at(cov, 365.6, 130))
        self.assertFalse(self.at(water, 350.1, 450.1) or self.at(cov, 350.1, 450.1))
        self.assertTrue(self.at(water, 310, 450))
        # The intermittent stream is water (painters filter on intermittent), and kept out of sampling like any
        # water (C6): 1.25 m and 5 m.
        self.assertTrue(self.at(water, 100, 260.1))
        self.assertFalse(self.at(K.exact(self.win, self.m, "water", where="intermittent = 0"), 100, 260.1))
        self.assertTrue(self.at(cov, 100, 266.0))
        self.assertFalse(self.at(cov, 100, 266.6))
        # Apron and rail yard: sampling only, 2 m around.
        self.assertTrue(self.at(cov, 420, 320) and not self.at(paving, 420, 320))
        self.assertTrue(self.at(cov, 541.6, 320))
        self.assertFalse(self.at(cov, 542.4, 320) or self.at(paving, 520, 320))
        # The railway line: a 5 m bed and 2 m around (4.5 m from the line); runway 45 m, taxiway 23 m, likewise.
        # None of them is painted.
        self.assertTrue(self.at(cov, 100, 320) and self.at(cov, 100, 324.4))
        self.assertFalse(self.at(cov, 100, 325.1) or self.at(paving, 100, 320))
        self.assertTrue(self.at(cov, 100, 800) and self.at(cov, 100, 824.0))
        self.assertFalse(self.at(cov, 100, 825.0) or self.at(paving, 100, 800) or self.at(water, 100, 800))
        self.assertTrue(self.at(cov, 400, 800) and self.at(cov, 400, 812.9))
        self.assertFalse(self.at(cov, 400, 814.1) or self.at(paving, 400, 800))
        # Parking: paint and sample. The plaza (a relation): paint, and 2 m for sampling.
        self.assertTrue(self.at(paving, 320, 20) and self.at(cov, 341.9, 20))
        self.assertTrue(self.at(paving, 650, 620) and self.at(cov, 681.6, 620))
        self.assertFalse(self.at(paving, 680.6, 620) or self.at(cov, 682.4, 620))
        # NHD: the canal area is painted; the canal line only sampled (2 m and 5 m); the swamp and the inundation
        # area aren't water; the pipeline is gone.
        self.assertTrue(self.at(water, 100, 606))
        self.assertFalse(self.at(water, 100, 700))
        self.assertTrue(self.at(cov, 100, 706.6))
        self.assertFalse(self.at(cov, 100, 707.4))
        self.assertFalse(self.at(water, 125, 425) or self.at(water, 350, 620) or self.at(water, 100, 750))

    def test_developed_land(self):
        dev = K.covered(self.win, self.m, what=("developed",))
        self.assertTrue(self.at(dev, 560, 760))                     # class 124
        self.assertTrue(self.at(dev, 560, 600))                     # class 123
        self.assertFalse(self.at(dev, 560, 200))                    # cropland
        self.assertFalse(self.at(dev, 100, 0))
        roofs_only = K.covered(self.win, self.m, what=("roof",))
        self.assertFalse(self.at(roofs_only, 100, 0))

    def test_api_refusals(self):
        with self.assertRaises(K.MaskError):
            K.exact(self.win, self.m, "covered")
        with self.assertRaises(K.MaskError):
            K.covered(self.win, self.m, what=("trees",))
        m = M.Manifest(self.m.folder, dict(self.m.data, layers=self.m.data["layers"][:-1]))
        with self.assertRaisesRegex(K.MaskError, "no covered layer"):
            K.check(m)
        m = M.Manifest(self.m.folder, dict(self.m.data, build="20261011T120000Z-box-d-part"))
        with self.assertRaisesRegex(K.MaskError, "part of the grid only"):
            K.check(m)
        self.assertIs(K.check(m, partial=True), m)

    # -- builds that stop ----------------------------------------------------------------------------------------

    def test_bounds(self):
        archive = os.path.join(self.dir, "bounds")
        small = (X0 - 20, Y0 - 20, X0 + 250, Y0 + 30)
        m = self.build(archive=archive, bounds=small)
        self.assertRegex(m.build, r"^\d{8}T\d{6}Z-part$")                  # a partial build says so
        self.assertIn("part of the grid (a partial build)", m.data["note"])
        self.assertEqual(sorted(f["kind"] for f in features(os.path.join(m.folder, "roads.fgb"))),
                         ["street", "walkway"])
        self.assertEqual(m.layer("water")["features"], 0)
        self.assertEqual(m.layer("roofs")["features"], 0)
        with self.assertRaisesRegex(K.MaskError, "ends in -part"):
            self.build(archive=archive, bounds=small, build_id="20261011T120000Z")
        with self.assertRaisesRegex(K.MaskError, "ends in -part"):
            self.build(archive=archive, build_id="20261011T120000Z-part")
        self.assertEqual(M.builds(archive, "ground_mask", partial=True), [m.build])

    def test_partial_builds_are_never_the_newest(self):
        # A box's quick look, newer than the whole mask, doesn't become the mask the ground reads.
        archive = os.path.join(self.dir, "partial")
        whole = self.build(archive=archive, build_id="20261011T120000Z")
        part = self.build(archive=archive, bounds=G.box("d").utm, build_id="20261011T130000Z-box-d-part")
        self.assertEqual(M.builds(archive, "ground_mask"), [whole.build])
        self.assertEqual(K.latest(archive).build, whole.build)
        self.assertEqual(K.latest(archive, partial=True).build, part.build)
        self.assertEqual(I.exports(archive)["ground_mask"].build, whole.build)
        shutil.rmtree(whole.folder)
        self.assertIsNone(K.latest(archive))
        self.assertEqual(K.latest(archive, partial=True).build, part.build)

    def test_a_failed_build_leaves_nothing(self):
        archive = os.path.join(self.dir, "failed")
        with mock.patch.object(K, "read_cdl", side_effect=RuntimeError("boom")):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                self.build(archive=archive, build_id="20261011T120000Z")
        self.assertEqual(os.listdir(os.path.join(archive, "ground_mask", K.STAGING)), [])
        self.assertFalse(os.path.exists(os.path.join(archive, "ground_mask", "export")))
        self.assertIsNone(K.latest(archive))

    def test_a_stopped_build_cleans_up(self):
        # docker stop sends SIGTERM: the command line turns it into SystemExit, and the build removes its folder.
        archive = os.path.join(self.dir, "stopped")
        before = signal.getsignal(signal.SIGTERM)

        def stopped(*_a, **_k):
            os.kill(os.getpid(), signal.SIGTERM)
            time.sleep(5)                                       # the handler raises before this ends
            raise AssertionError("SIGTERM didn't stop the build")

        with mock.patch.object(K, "read_cdl", side_effect=stopped):
            with self.assertRaises(SystemExit) as ctx:
                K.main(["build", "--archive", archive, "--osm", self.osm, "--nhd", self.nhd, "--cdl", self.cdl,
                        "--roofs", self.roofs])
        self.assertEqual(ctx.exception.code, 128 + signal.SIGTERM)
        self.assertEqual(signal.getsignal(signal.SIGTERM), before)
        self.assertEqual(os.listdir(os.path.join(archive, "ground_mask", K.STAGING)), [])
        self.assertIsNone(K.latest(archive, partial=True))

    def test_a_killed_build_is_swept(self):
        # SIGKILL (out of memory) skips every cleanup: the next build sweeps what it left.
        archive = os.path.join(self.dir, "killed")
        left = os.path.join(archive, "ground_mask", K.STAGING, "20261011T110000Z")
        os.makedirs(left)
        with open(os.path.join(left, "roofs.fgb"), "wb") as f:
            f.write(b"half")
        logged = []
        m = self.build(archive=archive, build_id="20261011T120000Z", log=logged.append)
        self.assertEqual(os.listdir(os.path.join(archive, "ground_mask", K.STAGING)), [])
        self.assertTrue(any("20261011T110000Z" in line and "swept" in line for line in logged))
        self.assertEqual(M.builds(archive, "ground_mask"), [m.build])

    def test_one_build_at_a_time(self):
        archive = os.path.join(self.dir, "locked")
        with K._Lock(archive):
            with self.assertRaisesRegex(K.MaskError, "another mask build is running"):
                self.build(archive=archive, build_id="20261011T120000Z")
        self.assertEqual(self.build(archive=archive, build_id="20261011T120000Z").build, "20261011T120000Z")

    def test_old_builds_are_pruned(self):
        archive = os.path.join(self.dir, "prune")
        for t in ("100000", "110000", "120000"):
            self.build(archive=archive, build_id=f"20261011T{t}Z")
        self.assertEqual(M.builds(archive, "ground_mask"), ["20261011T110000Z", "20261011T120000Z"])
        # A partial build is left alone; the build the ground tiles name is kept; one written with an older id
        # than the newest is kept too.
        part = self.build(archive=archive, bounds=BOUNDS, build_id="20261011T121000Z-part")
        tiles_dir = os.path.join(self.dir, "prune-tiles")
        os.makedirs(tiles_dir)
        with open(os.path.join(tiles_dir, "manifest.json"), "w") as f:
            json.dump({"ground": {"status": "painted", "inputs": [
                "soils/ground@20261012T031500Z", "ground_mask/roofs@20261011T110000Z",
                "ground_mask/covered@20261011T110000Z", "raw/osm@0123"]}, "buildings": {"file": "b.pmtiles"}}, f)
        self.assertEqual(K.tiles_builds(tiles_dir), {"20261011T110000Z"})
        self.assertEqual(K.tiles_builds(os.path.join(self.dir, "nowhere")), set())
        self.build(archive=archive, build_id="20261011T130000Z", protect=K.tiles_builds(tiles_dir))
        self.assertEqual(M.builds(archive, "ground_mask"),
                         ["20261011T110000Z", "20261011T120000Z", "20261011T130000Z"])
        self.build(archive=archive, build_id="20261011T090000Z", keep=1)
        self.assertEqual(M.builds(archive, "ground_mask"), ["20261011T090000Z", "20261011T130000Z"])
        self.assertEqual(M.builds(archive, "ground_mask", partial=True),
                         ["20261011T090000Z", "20261011T121000Z-part", "20261011T130000Z"])
        self.assertTrue(os.path.isdir(part.folder))
        with self.assertRaisesRegex(K.MaskError, "keep at least one"):
            self.build(archive=archive, build_id="20261011T140000Z", keep=0)

    def test_versions_must_be_known(self):
        other = os.path.join(self.dir, "versions")
        os.makedirs(other, exist_ok=True)
        archive = os.path.join(self.dir, "versions-archive")

        def build(**kw):
            return self.build(archive=archive, **kw)

        osm = shutil.copy(self.osm, os.path.join(other, "valley.osm"))
        with open(os.path.join(other, "valley.json"), "w") as f:
            json.dump({"md5": "f" * 32, "sha256": "0" * 64}, f)
        with self.assertRaisesRegex(K.MaskError, "sha256 differs"):
            build(osm=osm)
        os.remove(os.path.join(other, "valley.json"))
        with self.assertRaisesRegex(K.MaskError, "--osm-version"):
            build(osm=osm)
        self.assertEqual(build(osm=osm, osm_version="f" * 32, build_id="20261011T140000Z").inputs["osm"]["version"],
                         "f" * 32)
        roofs = roofs_fixture(os.path.join(other, "roofs.gpkg"), release=None)
        with self.assertRaisesRegex(K.MaskError, "release"):
            build(roofs=roofs)
        cdl = shutil.copy(self.cdl, os.path.join(other, "cdl.tif"))
        with self.assertRaisesRegex(K.MaskError, "--cdl-version"):
            build(cdl=cdl)
        with self.assertRaisesRegex(K.MaskError, "no nhd file"):
            build(nhd=os.path.join(other, "missing.gpkg"))
        self.assertEqual(M.builds(archive, "ground_mask"), ["20261011T140000Z"])     # the refused left nothing

    def test_the_command_line(self):
        archive = os.path.join(self.dir, "cli")
        look = os.path.join(self.dir, "cli-look")
        files = ["--osm", self.osm, "--nhd", self.nhd, "--cdl", self.cdl, "--roofs", self.roofs]
        with mock.patch.dict(os.environ, {"TVT_ARCHIVE": archive}):
            self.assertEqual(K.main(["build", "--build", "20261011T130000Z"] + files), 0)
            self.assertEqual(K.latest(archive).build, "20261011T130000Z")
            # A box or bounds build is a quick look: never into $TVT_ARCHIVE.
            bounds = ["--bounds", ",".join(f"{v:g}" for v in BOUNDS)]
            self.assertEqual(K.main(["build", "--box", "d"] + files), 2)
            self.assertEqual(K.main(["build", "--archive", archive + "/"] + bounds + files), 2)
            self.assertEqual(M.builds(archive, "ground_mask", partial=True), ["20261011T130000Z"])
            self.assertEqual(K.main(["build", "--archive", look, "--box", "d"] + files), 0)
            self.assertEqual(K.main(["build", "--archive", look, "--build", "20261011T130000Z"] + bounds + files),
                             2)                                 # a partial build's id ends in -part
        self.assertRegex(K.latest(look, partial=True).build, r"^\d{8}T\d{6}Z-box-d-part$")
        self.assertIsNone(K.latest(look))
        rc = K.main(["build", "--archive", archive, "--osm", self.osm, "--nhd", self.nhd, "--cdl", self.cdl,
                     "--roofs", os.path.join(self.dir, "nowhere.pmtiles")])
        self.assertEqual(rc, 2)
        bad = os.path.join(self.dir, "cli-tiles")
        os.makedirs(bad)
        with open(os.path.join(bad, "manifest.json"), "w") as f:
            f.write("{not json")
        self.assertEqual(K.main(["build", "--archive", archive, "--tiles", bad] + files), 2)
        self.assertEqual(M.builds(archive, "ground_mask"), ["20261011T130000Z"])


@unittest.skipIf(np is None, "needs the worker image (GDAL, NumPy, SciPy)")
class PmtilesRoofsTest(unittest.TestCase):
    """Roofs read from a PMTiles file at z15, as the map's buildings.pmtiles holds them: one crossing a z15 tile's
    edge comes back in two pieces that cover the same cells."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_a_roof_across_a_tile_edge(self):
        tile = 2 * math.pi * MERC_R / 2 ** 15
        mx, my = mercator(300, 300)
        edge = math.floor((mx + math.pi * MERC_R) / tile) * tile - math.pi * MERC_R     # a z15 column's west edge
        top = math.pi * MERC_R - math.floor((math.pi * MERC_R - my) / tile) * tile       # its row's north edge
        roof = [(edge - 30, top - 340), (edge + 30, top - 340), (edge + 30, top - 300), (edge - 30, top - 300)]
        src = os.path.join(self.dir, "roofs.gpkg")
        ds = ogr.GetDriverByName("GPKG").CreateDataSource(src)
        lyr = ds.CreateLayer("buildings", srs(3857), ogr.wkbPolygon)
        f = ogr.Feature(lyr.GetLayerDefn())
        f.SetGeometry(ogr.CreateGeometryFromWkt(f"POLYGON({ring_wkt(roof, lambda x, y: (x, y))})"))
        lyr.CreateFeature(f)
        ds = None
        pm = os.path.join(self.dir, "buildings.pmtiles")
        gdal.VectorTranslate(pm, src, format="PMTiles", datasetCreationOptions=["MINZOOM=15", "MAXZOOM=15"])
        whole = ogr.CreateGeometryFromWkt(f"POLYGON({ring_wkt(roof, lambda x, y: (x, y))})")
        whole.Transform(K.transformer(srs(3857)))

        class Out:
            def __init__(self):
                self.got, self.covers = [], []
                self.roofs = self

            def add(self, g):
                self.got.append(g.Clone())

            def cover(self, g, what, kind, extra=0.0):
                self.covers.append(what)

        out = Out()
        K.read_roofs(pm, G.EXTENT, out, log=lambda *a: None)
        self.assertEqual(len(out.got), 2)
        self.assertEqual(out.covers, ["roof", "roof"])
        union = out.got[0].Union(out.got[1])
        # z15 tiles of 4,096 units: 0.3 m in Web Mercator, about 0.22 m on the ground
        self.assertAlmostEqual(union.GetArea(), whole.GetArea(), delta=whole.GetArea() * 0.02)
        self.assertLess(union.SymmetricDifference(whole).GetArea(), whole.GetArea() * 0.03)


if __name__ == "__main__":
    unittest.main()
