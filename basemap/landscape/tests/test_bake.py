"""The base bake end to end (bake.py): synthetic exports, baked, read back. Needs the worker image (GDAL): the tests
skip elsewhere, and in the worker image a skip counts as a failure.

    /srv/tvt/work/bin/worker-test -C <checkout> discover -s basemap/landscape -t .

The exports are synthetic FlatGeobuf files around downtown Boise written with GDAL, with real manifests
(basemap/ground/manifest.py) whose sources are checked against the repository's plugin.json files.
"""

import contextlib
import io
import json
import os
import random
import shutil
import tempfile
import unittest

try:
    from osgeo import gdal, ogr, osr
    gdal.UseExceptions()
    ogr.UseExceptions()
    osr.UseExceptions()
except ImportError:                                  # outside the worker image
    gdal = None

from basemap.ground import manifest as M, tiles as ground_tiles
from basemap.ground.tests.test_manifest import ACHD, FIXTURES, OSM
from basemap.landscape import bake, plan as P, pmtiles
from basemap.landscape.tests.test_plan import NHD

CX, CY = 565000.0, 4830000.0                          # downtown Boise, in the grid's metres (EPSG:32611)
TYPES = {"int": "OFTInteger", "long": "OFTInteger64", "short": "OFTInteger", "double": "OFTReal",
         "float": "OFTReal", "string": "OFTString", "bool": "OFTInteger"}


def utm():
    s = osr.SpatialReference()
    s.ImportFromEPSG(32611)
    s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return s


def write_fgb(path, geom, fields, features):
    """A FlatGeobuf, with its spatial index unless a feature has no geometry (GDAL can't index one): fields
    [(name, type)], features [(wkt or None, {field: value})]."""
    ds = ogr.GetDriverByName("FlatGeobuf").CreateDataSource(path)
    index = "YES" if all(wkt for wkt, _ in features) else "NO"
    lyr = ds.CreateLayer("layer", utm(), getattr(ogr, "wkb" + geom), options=[f"SPATIAL_INDEX={index}"])
    for name, t in fields:
        fd = ogr.FieldDefn(name, getattr(ogr, TYPES[t]))
        if t == "short":
            fd.SetSubType(ogr.OFSTInt16)
        if t == "bool":
            fd.SetSubType(ogr.OFSTBoolean)
        if t == "float":
            fd.SetSubType(ogr.OFSTFloat32)
        lyr.CreateField(fd)
    for wkt, attrs in features:
        f = ogr.Feature(lyr.GetLayerDefn())
        if wkt:
            f.SetGeometry(ogr.CreateGeometryFromWkt(wkt))
        for k, v in attrs.items():
            if v is None:
                f.SetFieldNull(k)
            else:
                f.SetField(k, v)
        lyr.CreateFeature(f)
    ds = None
    return path


def line(x0, y0, x1, y1):
    return f"LINESTRING({x0} {y0},{x1} {y1})"


def square(x, y, size):
    return f"POLYGON(({x} {y},{x + size} {y},{x + size} {y + size},{x} {y + size},{x} {y}))"


REACH_FIELDS = [("id", "long"), ("kind", "string"), ("minzoom", "short"), ("width", "float")]
REACHES = [
    (line(CX - 900, CY - 900, CX + 900, CY + 900), {"id": 1, "kind": "main canal", "minzoom": 10, "width": 12.5}),
    (line(CX - 900, CY + 900, CX + 900, CY - 900), {"id": 2, "kind": "ditch", "minzoom": 13, "width": 1.5}),
    (line(CX - 950, CY, CX + 950, CY + 10), {"id": 9007199254740991, "kind": "river", "minzoom": None,
                                             "width": None}),
]
SURFACE_FIELDS = [("id", "int"), ("surface", "string"), ("curbed", "bool")]
SURFACES = [(square(CX - 50, CY - 50, 100), {"id": 7, "surface": "asphalt", "curbed": 1}),
            (square(CX + 200, CY + 200, 40), {"id": 8, "surface": "concrete", "curbed": 0})]


def export(archive, plugin, build, layers, inputs):
    """layers: [(name, geometry, fields, features, manifest extras)]."""
    folder = M.export_dir(archive, plugin, build)
    os.makedirs(folder)
    specs = []
    for name, geom, fields, feats, extra in layers:
        write_fgb(os.path.join(folder, f"{name}.fgb"), geom, fields, feats)
        spec = {"name": name, "file": f"{name}.fgb", "format": "FlatGeobuf", "base": True,
                "inputs": [e["name"] for e in inputs], "features": len(feats)}
        spec.update(extra)
        specs.append(spec)
    return M.write(folder, plugin, inputs, specs)


def water(archive, build="20261012T031500Z", features=REACHES):
    return export(archive, "water", build, [("reaches", "LineString", REACH_FIELDS, features, {})], [OSM, NHD])


def roads(archive, build="20261013T031500Z", features=SURFACES):
    return export(archive, "roads", build, [("surfaces", "Polygon", SURFACE_FIELDS, features, {"minzoom": 14})],
                  [OSM, ACHD])


def at_zoom(path, z):
    """{source layer: {id: {field: value}}} of every feature GDAL reads at zoom z (mvt_id included)."""
    ds = gdal.OpenEx(path, open_options=[f"ZOOM_LEVEL={z}"])
    out = {}
    for i in range(ds.GetLayerCount()):
        lyr = ds.GetLayer(i)
        feats = {}
        for f in lyr:
            feats[f["id"]] = f.items()
        out[lyr.GetName()] = feats
    return out


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = bake.main(list(argv))
    return code, out.getvalue(), err.getvalue()


@unittest.skipIf(gdal is None, "needs the worker image (GDAL)")
class BakeTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.archive = os.path.join(self.dir, "archive")
        self.tiles = os.path.join(self.dir, "tiles")
        os.makedirs(self.archive)
        os.makedirs(self.tiles)
        with open(os.path.join(self.tiles, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"zoom": 10, "basemap": {"file": "valley.pmtiles"}}, f)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def bake(self, *extra):
        return run("bake", "--archive", self.archive, "--tiles", self.tiles, *extra)

    def entry(self):
        return P.current(self.tiles)

    def test_bake_and_read_back(self):
        water(self.archive)
        roads(self.archive)
        code, out, err = self.bake()
        self.assertEqual(code, 0, err)
        e = self.entry()
        path = os.path.join(self.tiles, e["file"])
        self.assertTrue(P.FILE_RE.match(e["file"]))
        self.assertEqual(sorted(e["layers"]), ["roads.surfaces", "water.reaches"])
        self.assertEqual(e["empty"], [])
        self.assertEqual(e["layers"]["water.reaches"]["features"], 3)
        self.assertEqual(e["layers"]["water.reaches"]["fields"],
                         {"id": "long", "kind": "string", "width": "float"})
        self.assertEqual((e["republish"], e["access"], e["previous"]), ("internal", "tailnet", None))
        self.assertEqual(e["attribution"], "© OpenStreetMap contributors; ACHD; "
                                           "U.S. Geological Survey, National Hydrography Dataset")
        self.assertEqual(e["promoteId"], "id")
        self.assertTrue(e["budget"]["roads"])
        self.assertGreater(e["budget"]["tiles"], 0)
        self.assertIn("served to the tailnet only", out)
        with open(os.path.join(self.tiles, "manifest.json"), encoding="utf-8") as f:
            m = json.load(f)
        self.assertEqual(m["basemap"], {"file": "valley.pmtiles"})        # the other entries are kept

        # The file: gzipped MVT, z8-16, with the entry and credits in its metadata.
        h = pmtiles.read_header(path)
        self.assertEqual((h.tile_type_name, h.tile_compression_name, h.min_zoom, h.max_zoom), ("mvt", "gzip", 8, 16))
        meta = pmtiles.read_metadata(path)
        self.assertEqual(meta["attribution"], e["attribution"])
        self.assertEqual(meta["tvt"]["landscape"], {k: v for k, v in e.items() if k != "previous"})
        self.assertEqual({v["id"] for v in meta["vector_layers"]}, {"roads.surfaces", "water.reaches"})

        # The features: per-feature first zooms, the id as both feature id and property, minzoom left out.
        self.assertEqual(set(at_zoom(path, 8)["water.reaches"]), {9007199254740991})
        self.assertEqual(set(at_zoom(path, 10)["water.reaches"]), {1, 9007199254740991})
        self.assertEqual(set(at_zoom(path, 12)["water.reaches"]), {1, 9007199254740991})
        z13 = at_zoom(path, 13)
        self.assertEqual(set(z13["water.reaches"]), {1, 2, 9007199254740991})
        self.assertEqual(z13.get("roads.surfaces", {}), {})
        z16 = at_zoom(path, 16)
        self.assertEqual(set(z16["roads.surfaces"]), {7, 8})
        r = z16["water.reaches"][1]
        self.assertEqual((r["mvt_id"], r["kind"]), (1, "main canal"))
        self.assertAlmostEqual(r["width"], 12.5)
        self.assertNotIn("minzoom", r)
        self.assertIsNone(z16["water.reaches"][9007199254740991]["width"])
        s = z16["roads.surfaces"][7]
        self.assertEqual((s["mvt_id"], s["surface"], bool(s["curbed"])), (7, "asphalt", True))

        # check: the entry agrees with the file; --public refuses a tailnet-only bake.
        self.assertEqual(bake.check(self.tiles), [])
        problems = bake.check(self.tiles, public=True)
        self.assertEqual(len(problems), 2)
        self.assertTrue(all("tailnet only" in p for p in problems))
        code, _, err = run("check", "--tiles", self.tiles, "--public")
        self.assertEqual(code, 1)
        self.assertIn("republish internal", err)

    def test_public_bake(self):
        water(self.archive)
        self.assertEqual(self.bake()[0], 0)
        e = self.entry()
        self.assertEqual((e["republish"], e["access"]), ("yes", "public"))
        self.assertFalse(e["budget"]["roads"])
        self.assertEqual(bake.check(self.tiles, public=True), [])
        self.assertEqual(run("check", "--tiles", self.tiles, "--public")[0], 0)

    def test_same_exports_same_file(self):
        water(self.archive)
        self.assertEqual(self.bake()[0], 0)
        first = self.entry()
        before = os.path.getmtime(os.path.join(self.tiles, first["file"]))
        code, out, _ = self.bake()
        self.assertEqual(code, 0)
        self.assertIn("already switched in; nothing changed", out)
        self.assertEqual(self.entry(), first)
        self.assertEqual(os.path.getmtime(os.path.join(self.tiles, first["file"])), before)

    def test_swap_keeps_the_last_two_and_rolls_back(self):
        water(self.archive)
        self.assertEqual(self.bake()[0], 0)
        a = self.entry()["file"]
        roads(self.archive)
        self.assertEqual(self.bake()[0], 0)
        b = self.entry()
        self.assertEqual(b["previous"], a)
        self.assertEqual(P.files(self.tiles), sorted([a, b["file"]]))
        water(self.archive, build="20261014T031500Z")
        code, out, _ = self.bake()
        self.assertEqual(code, 0)
        c = self.entry()
        self.assertEqual(c["previous"], b["file"])
        self.assertEqual(P.files(self.tiles), sorted([b["file"], c["file"]]))
        self.assertIn(f"removed {a}", out)
        self.assertEqual(bake.check(self.tiles), [])

        code, out, _ = run("rollback", "--tiles", self.tiles)
        self.assertEqual(code, 0)
        back = self.entry()
        self.assertEqual((back["file"], back["previous"]), (b["file"], c["file"]))
        self.assertEqual(back["inputs"], b["inputs"])
        self.assertEqual(bake.check(self.tiles), [])
        self.assertEqual(P.files(self.tiles), sorted([b["file"], c["file"]]))

    def test_over_budget_switches_nothing(self):
        water(self.archive)
        self.assertEqual(self.bake()[0], 0)
        before = self.entry()
        # One z16 tile downtown, crowded: 3,000 small lots with incompressible names.
        z, x, y = (16,) + tuple(int(v) for v in (ground_tiles._tx(-116.195, 16), ground_tiles._ty(43.62, 16)))
        w, s, e, n = ground_tiles.tile_lonlat(z, x, y)
        src = osr.SpatialReference()
        src.ImportFromEPSG(4326)
        src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        ct = osr.CoordinateTransformation(src, utm())
        mx, my, _ = ct.TransformPoint((w + e) / 2, (s + n) / 2)
        rnd = random.Random(3)
        lots = [(square(mx - 100 + rnd.uniform(0, 195), my - 100 + rnd.uniform(0, 195), rnd.uniform(1, 5)),
                 {"id": i, "surface": "%032x" % rnd.getrandbits(128), "curbed": i % 2}) for i in range(1, 3001)]
        roads(self.archive, features=lots)
        code, out, err = self.bake()
        self.assertEqual(code, 4, out + err)
        self.assertIn("over budget, so nothing is switched in", err)
        self.assertIn(f"{z}/{x}/{y}", err)
        self.assertEqual(self.entry(), before)
        self.assertEqual(P.files(self.tiles), [before["file"]])
        self.assertEqual([f for f in os.listdir(self.tiles) if f.startswith(P.PART_PREFIX)], [])

    def test_features_the_bake_refuses(self):
        cases = [
            ("repeated", [(line(CX, CY, CX + 10, CY), {"id": 4}), (line(CX, CY, CX + 20, CY), {"id": 4})]),
            ("no geometry", [(None, {"id": 5})]),
            ("outside 0..2", [(line(CX, CY, CX + 10, CY), {"id": -1})]),
            ("no id", [(line(CX, CY, CX + 10, CY), {"id": None})]),
        ]
        for i, (msg, feats) in enumerate(cases):
            water(self.archive, build=f"2026101{i}T000000Z",
                  features=[(wkt, dict({"kind": "x", "minzoom": None, "width": None}, **a)) for wkt, a in feats])
            code, _, err = self.bake()
            self.assertEqual(code, 2, msg)
            self.assertIn(msg, err)
            self.assertIsNone(self.entry())
            self.assertEqual(P.files(self.tiles), [])

    def test_minzoom_past_the_layers_maxzoom(self):
        export(self.archive, "water", "20261012T031500Z",
               [("reaches", "LineString", REACH_FIELDS,
                 [(line(CX, CY, CX + 10, CY), {"id": 1, "kind": "x", "minzoom": 15, "width": 1.0})],
                 {"maxzoom": 14})], [OSM, NHD])
        code, _, err = self.bake()
        self.assertEqual(code, 2)
        self.assertIn("past the layer's maxzoom 14", err)

    def test_empty_layer_and_empty_bake(self):
        code, out, _ = self.bake()
        self.assertEqual(code, 0)
        self.assertEqual(self.entry()["status"], "empty")
        self.assertEqual(self.entry()["reason"], "no plugin exports a base layer yet")
        code, out, _ = self.bake()
        self.assertIn("the entry already says so", out)
        water(self.archive, features=[])                          # GDAL writes no file without features
        self.assertEqual(self.bake()[0], 0)
        self.assertEqual(self.entry()["reason"], "every base layer is empty: water.reaches")
        roads(self.archive)
        code, out, err = self.bake()
        self.assertEqual(code, 0, err)
        self.assertIn("empty, so not built: water.reaches", out)
        e = self.entry()
        # An empty layer isn't built: it's not in the file or the entry's layers (the app treats it as not built,
        # so water's suppresses don't apply), only in `empty`. The credits and access are the built layers'.
        self.assertEqual((list(e["layers"]), e["empty"]), (["roads.surfaces"], ["water.reaches"]))
        self.assertEqual(e["layers"]["roads.surfaces"]["features"], 2)
        self.assertNotIn("National Hydrography", e["attribution"])
        self.assertIn("water/reaches@20261012T031500Z", e["inputs"])
        meta = pmtiles.read_metadata(os.path.join(self.tiles, e["file"]))
        self.assertEqual(bake.source_layers(meta), {"roads.surfaces"})
        # The file's zooms are those holding tiles (roads' surfaces from z14), in its header and its entry.
        h = pmtiles.read_header(os.path.join(self.tiles, e["file"]))
        self.assertEqual((e["minzoom"], e["maxzoom"], h.min_zoom, h.max_zoom), (14, 16, 14, 16))
        self.assertLessEqual(14, h.center_zoom)
        meta = pmtiles.read_metadata(os.path.join(self.tiles, e["file"]))
        self.assertEqual((meta["minzoom"], meta["maxzoom"], meta["center"].split(",")[2]), ("14", "16", "14"))
        self.assertEqual(bake.check(self.tiles), [])
        shutil.rmtree(os.path.join(self.archive, "water"))
        shutil.rmtree(os.path.join(self.archive, "roads"))
        code, _, err = self.bake()                                # baked to empty: only when asked
        self.assertEqual(code, 2)
        self.assertIn("roads.surfaces (there's no export of roads). It would switch the landscape to empty", err)
        self.assertEqual(self.entry(), e)
        code, out, err = self.bake("--allow-drop")
        self.assertEqual(code, 0, err)
        gone = self.entry()
        self.assertEqual((gone["status"], gone["previous"]), ("empty", e["file"]))
        self.assertEqual(P.files(self.tiles), [e["file"]])
        self.assertEqual(bake.check(self.tiles), [])
        code, out, _ = run("rollback", "--tiles", self.tiles)     # back from empty to the last bake
        self.assertEqual(code, 0)
        self.assertEqual((self.entry()["file"], self.entry()["previous"]), (e["file"], None))

    def test_geometry_must_be_the_layers_type(self):
        lines = [(line(CX, CY, CX + 10, CY), {"id": 1}),
                 ("MULTILINESTRING((%s %s,%s %s),(%s %s,%s %s))" % (CX, CY, CX + 5, CY, CX, CY + 5, CX + 5, CY + 5),
                  {"id": 2})]
        cases = [("POINT(%s %s)" % (CX, CY), "Point"), (square(CX, CY, 10), "Polygon"),
                 ("GEOMETRYCOLLECTION(LINESTRING(%s %s,%s %s))" % (CX, CY, CX + 1, CY), "Geometry Collection")]
        for i, (wkt, kind) in enumerate(cases):
            # A PostGIS export's header says Unknown, so only the features can tell.
            export(self.archive, "water", f"2026101{i}T000000Z",
                   [("reaches", "Unknown", [("id", "long")], lines + [(wkt, {"id": 3})],
                     {"geometry": "LineString"})], [OSM, NHD])
            code, _, err = self.bake()
            self.assertEqual(code, 2, err)
            self.assertIn(f"id 3 is a {kind}, not a LineString or its multi form", err)
            self.assertIsNone(self.entry())
        export(self.archive, "water", "20261019T000000Z",
               [("reaches", "Unknown", [("id", "long")], lines, {"geometry": "LineString"})], [OSM, NHD])
        code, _, err = self.bake()
        self.assertEqual(code, 0, err)                                # LineString and MultiLineString both go in
        self.assertEqual(set(at_zoom(os.path.join(self.tiles, self.entry()["file"]), 16)["water.reaches"]), {1, 2})

    def test_a_bake_that_drops_a_served_layer_is_refused(self):
        water(self.archive)
        roads(self.archive)
        self.assertEqual(self.bake()[0], 0)
        before = self.entry()
        # roads' newest export holds no base layer (a re-export of something else, say): its surfaces would vanish.
        export(self.archive, "roads", "20261020T000000Z",
               [("surfaces", "Polygon", SURFACE_FIELDS, SURFACES, {"base": False})], [OSM, ACHD])
        code, out, _ = run("status", "--archive", self.archive, "--tiles", self.tiles)
        self.assertIn("refused without --allow-drop: roads.surfaces (roads@20261020T000000Z has no base layer)", out)
        code, _, err = self.bake()
        self.assertEqual(code, 2)
        self.assertIn(f"refused: {before['file']} is served with source-layer(s) this bake wouldn't build: "
                      "roads.surfaces (roads@20261020T000000Z has no base layer). They would vanish", err)
        self.assertEqual(self.entry(), before)
        self.assertEqual(P.files(self.tiles), [before["file"]])
        code, out, err = self.bake("--allow-drop")
        self.assertEqual(code, 0, err)
        self.assertIn("dropped roads.surfaces (--allow-drop)", out)
        e = self.entry()
        self.assertEqual((list(e["layers"]), e["previous"]), (["water.reaches"], before["file"]))
        # A layer whose export is now empty is a drop too.
        water(self.archive, build="20261021T000000Z", features=[])
        code, _, err = self.bake()
        self.assertEqual(code, 2)
        self.assertIn("water.reaches (water/reaches@20261021T000000Z is empty). It would switch the landscape to "
                      "empty", err)

    def test_feature_count_must_match_the_manifest(self):
        # PostGIS's ST_AsFlatGeobuf without its index states no count (and here no CRS): the bake counts.
        for build, claimed, code in (("20261012T031500Z", 5, 2), ("20261013T031500Z", 2, 0)):
            folder = M.export_dir(self.archive, "water", build)
            os.makedirs(folder)
            shutil.copy(os.path.join(FIXTURES, "lines-no-index.fgb"), os.path.join(folder, "lines.fgb"))
            M.write(folder, "water", [OSM], [{"name": "lines", "file": "lines.fgb", "format": "FlatGeobuf",
                                              "base": True, "inputs": ["osm"], "features": claimed}])
            got, _, err = self.bake()
            self.assertEqual(got, code, err)
            if code:
                self.assertIn("the file holds 2 features, the manifest says 5", err)
                self.assertIsNone(self.entry())
        e = self.entry()
        self.assertEqual(e["layers"]["water.lines"]["features"], 2)
        z16 = at_zoom(os.path.join(self.tiles, e["file"]), 16)["water.lines"]
        self.assertEqual({k: v["name"] for k, v in z16.items()}, {1: "way 1", 2: "way 2"})

    def test_an_unrelated_file_with_the_name_is_never_overwritten(self):
        water(self.archive)
        plan = P.resolve(P.exports(self.archive))
        name = P.file_name(P.digest(plan, bake.writer_version()))
        with open(os.path.join(self.tiles, name), "wb") as f:
            f.write(b"something else")
        code, _, err = self.bake()
        self.assertEqual(code, 2)
        self.assertIn("never overwritten", err)
        with open(os.path.join(self.tiles, name), "rb") as f:
            self.assertEqual(f.read(), b"something else")

    def test_a_broken_entry_is_replaced(self):
        with open(os.path.join(self.tiles, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"zoom": 10, "landscape": {"status": "baked", "file": "x"}}, f)
        water(self.archive)
        code, _, err = self.bake()
        self.assertEqual(code, 0, err)
        self.assertIn("landscape entry is broken", err)
        self.assertIsNone(self.entry()["previous"])
        self.assertEqual(bake.check(self.tiles), [])

    def test_a_broken_entry_keeps_the_file_it_serves(self):
        water(self.archive)
        self.assertEqual(self.bake()[0], 0)
        a = self.entry()
        with open(os.path.join(self.tiles, "manifest.json"), encoding="utf-8") as f:
            m = json.load(f)
        m["landscape"]["spec"] = 2                                    # a newer contract, say: not this bake's
        with open(os.path.join(self.tiles, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(m, f)
        # The file it serves still says what it holds, so dropping water is refused all the same.
        shutil.rmtree(os.path.join(self.archive, "water"))
        roads(self.archive)
        code, _, err = self.bake()
        self.assertEqual(code, 2)
        self.assertIn("water.reaches (there's no export of water)", err)
        water(self.archive, build="20261014T031500Z")
        code, _, err = self.bake()
        self.assertEqual(code, 0, err)
        self.assertIn("landscape entry is broken", err)
        e = self.entry()
        self.assertEqual(e["previous"], a["file"])                    # kept: clients may still be reading it
        self.assertEqual(P.files(self.tiles), sorted([a["file"], e["file"]]))
        self.assertEqual(bake.check(self.tiles), [])

    def test_status(self):
        code, out, _ = run("status", "--archive", self.archive, "--tiles", self.tiles)
        self.assertEqual(code, 3)
        self.assertIn("no landscape entry yet", out)
        water(self.archive)
        roads(self.archive)
        code, out, _ = run("status", "--archive", self.archive, "--tiles", self.tiles)
        self.assertEqual(code, 0)
        self.assertIn("water.reaches", out)
        self.assertIn("z8-16, per feature", out)
        self.assertIn("served to the tailnet only, while these carry internal data: roads.surfaces", out)
        self.assertEqual(self.bake()[0], 0)
        code, out, _ = run("status", "--archive", self.archive, "--tiles", self.tiles)
        self.assertIn("(up to date)", out)
        water(self.archive, build="20261020T000000Z")
        code, out, _ = run("status", "--archive", self.archive, "--tiles", self.tiles)
        self.assertIn("a bake would read water/reaches@20261020T000000Z and no longer "
                      "water/reaches@20261012T031500Z", out)
        self.assertNotIn("--allow-drop", out)                     # a newer export of a layer drops nothing

    def test_check_finds_a_tampered_file(self):
        water(self.archive)
        roads(self.archive)
        self.assertEqual(self.bake()[0], 0)
        e = self.entry()
        path = os.path.join(self.tiles, e["file"])
        meta = pmtiles.read_metadata(path)
        meta["tvt"]["landscape"]["republish"] = "yes"         # a file that claims to be public
        meta["tvt"]["landscape"]["access"] = "public"
        tmp = path + ".tmp"
        pmtiles.write_with_metadata(path, tmp, meta)
        os.replace(tmp, path)
        problems = bake.check(self.tiles)
        self.assertTrue(any("metadata's entry isn't the manifest's" in p for p in problems), problems)
        # --public still refuses: the manifest's entry says tailnet.
        self.assertTrue(any("(the manifest serves it)" in p for p in bake.check(self.tiles, public=True)))


if __name__ == "__main__":
    unittest.main()
