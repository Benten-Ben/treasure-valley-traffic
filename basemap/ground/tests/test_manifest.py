"""Export manifests (manifest.py) and the FlatGeobuf header reader (fgb.py): standard library only.

The fixtures are synthetic, written by PostGIS 3.6's ST_AsFlatGeobuf (the exports' writer), base64 out of psql:
- squares.fgb, three 80 m squares with their spatial index:
    SELECT ST_AsFlatGeobuf(q, true, 'geom') FROM (SELECT i::int AS id, (10 + i)::int AS ground_type,
      CASE WHEN i = 3 THEN 'rock' ELSE '' END AS misc, ST_Multi(ST_MakeEnvelope(500000 + i*100, 4800000,
      500080 + i*100, 4800080, 32611))::geometry(MultiPolygon, 32611) AS geom FROM generate_series(1, 3) i) q
- lines-no-index.fgb, two lines with no index and no SRID:
    SELECT ST_AsFlatGeobuf(q, false, 'geom') FROM (SELECT i::int AS id, ('way ' || i)::text AS name,
      ST_MakeLine(ST_MakePoint(500000 + i*10, 4800000), ST_MakePoint(500100 + i*10, 4800100)) AS geom
      FROM generate_series(1, 2) i) q
"""

import copy
import json
import os
import shutil
import tempfile
import unittest

from basemap.ground import fgb, manifest as M
from basemap.ground.tests.tiffs import grid_tiff

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SSURGO = {"name": "ssurgo", "licence": "public-domain", "republish": "yes",
          "credit": "USDA NRCS Soil Survey Geographic Database (SSURGO)", "version": "FY2027"}
OSM = {"name": "osm", "licence": "ODbL-1.0", "republish": "yes", "credit": "© OpenStreetMap contributors"}
ACHD = {"name": "achd-roads", "licence": "none-stated", "republish": "internal", "credit": "ACHD",
        "source": "roads/achd_roads"}
# What plugin.json says of a few sources (plugin_sources() reads the real ones).
REGISTRY = {"roads/achd_roads": {"republish": "internal"}, "trails/r2r_trails": {"republish": "aggregates"},
            "hazards/nifc_wfigs_perimeters": {"republish": "yes"}}
BUILD = "20261012T031500Z"


def export(archive, plugin="soils", build=BUILD, files=("squares.fgb",)):
    """An export folder with fixture files in it (no manifest yet)."""
    folder = M.export_dir(archive, plugin, build)
    os.makedirs(folder)
    for f in files:
        shutil.copy(os.path.join(FIXTURES, f), folder)
    return folder


def ground_layer(**kw):
    lay = {"name": "ground", "file": "squares.fgb", "format": "FlatGeobuf", "inputs": ["ssurgo"], "base": False}
    lay.update(kw)
    return lay


def valid_manifest():
    """A full, valid manifest dict (not tied to files)."""
    return {
        "contract": 1, "plugin": "farm", "build": BUILD, "created": "2026-10-12T03:15:00Z",
        "inputs": [{"name": "csb", "licence": "public-domain", "republish": "yes",
                    "credit": "USDA NASS Crop Sequence Boundaries"},
                   dict(OSM)],
        "layers": [
            {"name": "fields", "file": "fields.fgb", "format": "FlatGeobuf", "crs": "EPSG:32611",
             "geometry": "MultiPolygon", "features": 3, "fields": {"id": "int", "bearing": "double"},
             "bytes": 10, "sha256": "0" * 64, "inputs": ["csb", "osm"], "licence": "ODbL-1.0", "republish": "yes",
             "credit": ["USDA NASS Crop Sequence Boundaries", "© OpenStreetMap contributors"], "base": True},
            {"name": "crop_cover", "file": "crop_cover.tif", "format": "GeoTIFF", "crs": "EPSG:32611",
             "grid": {"res": 10, "west": 495920, "north": 4855750, "width": 8967, "height": 9494},
             "bands": [{"name": "group", "type": "uint8", "nodata": 0, "values": {"1": "corn", "2": "hay"}},
                       {"name": "state", "type": "uint8"}, {"name": "confidence", "type": "uint8"}],
             "bytes": 10, "sha256": "1" * 64, "inputs": ["csb"], "licence": "public-domain", "republish": "yes",
             "credit": ["USDA NASS Crop Sequence Boundaries"], "base": False},
            {"name": "palette", "file": "palette.json", "format": "JSON", "schema": "farm.palette/1",
             "bytes": 10, "sha256": "2" * 64, "inputs": ["csb"], "licence": "public-domain", "republish": "yes",
             "credit": ["USDA NASS Crop Sequence Boundaries"], "base": False},
        ],
    }


class HeaderTest(unittest.TestCase):
    def test_postgis_squares(self):
        h = fgb.read_header(os.path.join(FIXTURES, "squares.fgb"))
        self.assertEqual(h.geometry_type, "MultiPolygon")
        self.assertEqual(h.columns, {"id": "int", "ground_type": "int", "misc": "string"})
        self.assertEqual(list(h.columns), ["id", "ground_type", "misc"])
        self.assertEqual(h.features_count, 3)
        self.assertEqual(h.index_node_size, 16)
        self.assertEqual(h.crs, "EPSG:32611")
        self.assertEqual(h.envelope, (500100.0, 4800000.0, 500380.0, 4800080.0))
        self.assertFalse(h.has_z)

    def test_no_index_states_less(self):
        h = fgb.read_header(os.path.join(FIXTURES, "lines-no-index.fgb"))
        self.assertEqual(h.geometry_type, "LineString")
        self.assertEqual(h.columns, {"id": "int", "name": "string"})
        self.assertEqual(h.features_count, 0)        # unknown without the index
        self.assertEqual(h.index_node_size, 0)
        self.assertEqual(h.crs, "")

    def test_not_flatgeobuf(self):
        with tempfile.NamedTemporaryFile(suffix=".fgb") as f:
            f.write(b'{"type": "FeatureCollection"}')
            f.flush()
            with self.assertRaises(fgb.FgbError):
                fgb.read_header(f.name)
        with open(os.path.join(FIXTURES, "squares.fgb"), "rb") as f:
            data = f.read()
        with self.assertRaises(fgb.FgbError):
            fgb.parse_header(data[:3] + b"\x02" + data[4:])     # another major version
        with self.assertRaises(fgb.FgbError):
            fgb.parse_header(data[:40])                          # cut short


class CheckTest(unittest.TestCase):
    def bad(self, m, words):
        with self.assertRaises(M.ManifestError) as ctx:
            M.check(m)
        self.assertIn(words, str(ctx.exception))

    def test_valid(self):
        M.check(valid_manifest())

    def test_top_level(self):
        m = valid_manifest()
        m["extra"] = 1
        self.bad(m, "unknown field")
        for key in ("contract", "plugin", "build", "created", "inputs", "layers"):
            m = valid_manifest()
            del m[key]
            self.bad(m, f"missing {key}")
        m = valid_manifest()
        m["contract"] = 2
        self.bad(m, "contract 2")
        m = valid_manifest()
        m["contract"] = True
        self.bad(m, "contract")
        m = valid_manifest()
        m["build"] = "latest"
        self.bad(m, "build 'latest'")
        m = valid_manifest()
        m["created"] = "2026-10-12 03:15"
        self.bad(m, "created")

    def test_build_is_the_folder(self):
        with self.assertRaises(M.ManifestError):
            M.check(valid_manifest(), folder="/x/farm/export/20261013T000000Z")
        M.check(valid_manifest(), folder=f"/x/farm/export/{BUILD}/")
        m = valid_manifest()
        m["build"] = BUILD + "-p3data"
        M.check(m, folder=f"/x/farm/export/{BUILD}-p3data")

    def test_input_licences(self):
        m = valid_manifest()
        m["inputs"][0]["licence"] = "MIT"
        self.bad(m, "licence 'MIT'")
        m = valid_manifest()
        m["inputs"][0] = dict(ACHD, name="csb")
        del m["inputs"][0]["source"]
        self.bad(m, "names its plugin source")
        m = valid_manifest()
        m["inputs"][0] = dict(ACHD, name="csb", source="ACHD roads")
        self.bad(m, "source must name a plugin source")
        m = valid_manifest()
        m["inputs"][0] = dict(ACHD, name="csb", licence="restricted", republish="internal")
        self.bad(m, "looser than restricted allows")
        m = valid_manifest()
        m["inputs"][0]["republish"] = "sometimes"
        self.bad(m, "republish must be one of")
        m = valid_manifest()
        m["inputs"].append(dict(m["inputs"][0]))
        self.bad(m, "listed twice")
        m = valid_manifest()
        m["inputs"].append({"name": "nhd", "licence": "public-domain", "republish": "yes", "credit": "USGS NHD"})
        self.bad(m, "no layer uses: nhd")
        m = valid_manifest()
        m["inputs"][0]["sha256"] = "abc"
        self.bad(m, "sha256")

    def test_strictest_input_wins(self):
        m = valid_manifest()
        m["inputs"][0]["republish"] = "internal"            # csb as if internal
        self.bad(m, "is looser than input 'csb'")
        for lay in m["layers"]:
            lay["republish"] = "internal"
        M.check(m)                                          # stricter is fine

    def test_share_alike(self):
        m = valid_manifest()
        m["layers"][0]["licence"] = "public-domain"
        self.bad(m, "share-alike")

    def test_a_layer_carries_its_inputs_licence(self):
        m = valid_manifest()
        m["layers"][1]["licence"] = "CC0-1.0"                    # crop_cover is made from csb (public domain) only
        self.bad(m, "isn't one of its inputs'")
        # a restricted input can't hide behind a looser label, even with republish no
        m = valid_manifest()
        m["inputs"].append({"name": "private", "licence": "restricted", "republish": "no", "credit": "Private"})
        m["layers"][1].update(inputs=["csb", "private"], republish="no",
                              credit=["USDA NASS Crop Sequence Boundaries", "Private"])
        self.bad(m, "looser than its input's restricted")
        m["layers"][1]["licence"] = "restricted"
        M.check(m)
        # nor a none-stated one behind public-domain: its republish rests on the owner's decision, not a grant
        m = valid_manifest()
        m["inputs"].append(dict(ACHD))
        m["layers"][1].update(inputs=["csb", "achd-roads"], republish="internal",
                              credit=["USDA NASS Crop Sequence Boundaries", "ACHD"])
        self.bad(m, "looser than its input's none-stated")
        m["layers"][1]["licence"] = "none-stated"
        M.check(m)
        # with a share-alike input the layer is ODbL, and republish carries any restriction
        m = valid_manifest()
        m["inputs"].append({"name": "private", "licence": "restricted", "republish": "no", "credit": "Private"})
        m["layers"][0].update(inputs=["csb", "osm", "private"], republish="no",
                              credit=m["layers"][0]["credit"] + ["Private"])
        M.check(m)

    def test_credit_carries_every_input(self):
        m = valid_manifest()
        m["layers"][0]["credit"] = ["USDA NASS Crop Sequence Boundaries"]
        self.bad(m, "lacks input 'osm'")
        m = valid_manifest()
        m["layers"][0]["credit"] = "USDA"
        self.bad(m, "credit must be a non-empty list")

    def test_layer_shape(self):
        m = valid_manifest()
        m["layers"][0]["format"] = "Shapefile"
        self.bad(m, "format must be one of")
        m = valid_manifest()
        m["layers"][0]["file"] = "../fields.fgb"
        self.bad(m, "plain file name")
        m = valid_manifest()
        m["layers"][0]["file"] = "fields.geojson"
        self.bad(m, "ends in .fgb")
        m = valid_manifest()
        m["layers"][1]["name"] = "fields"
        self.bad(m, "listed twice")
        m = valid_manifest()
        m["layers"][0]["crs"] = "EPSG:4326"
        self.bad(m, "crs must be EPSG:32611")
        m = valid_manifest()
        m["layers"][0]["fields"]["bearing"] = "numeric"
        self.bad(m, "type 'numeric'")
        m = valid_manifest()
        m["layers"][0]["geometry"] = "GeometryCollection"
        self.bad(m, "geometry must be one of")
        m = valid_manifest()
        m["layers"][0]["schema"] = "farm.fields/1"
        self.bad(m, "unknown field(s) for a FlatGeobuf layer: schema")
        m = valid_manifest()
        m["layers"][0]["minzoom"], m["layers"][0]["maxzoom"] = 14, 12
        self.bad(m, "minzoom is above maxzoom")
        m = valid_manifest()
        m["layers"][0]["minzoom"], m["layers"][0]["maxzoom"] = 8, 16
        M.check(m)
        m = valid_manifest()
        m["layers"][0]["inputs"] = ["csb", "nope"]
        self.bad(m, "input 'nope' isn't in the manifest's inputs")

    def test_base_layers(self):
        m = valid_manifest()
        del m["layers"][0]["fields"]["id"]
        self.bad(m, "integer 'id'")
        m = valid_manifest()
        m["layers"][0]["fields"]["id"] = "string"
        self.bad(m, "integer 'id'")
        m = valid_manifest()
        m["layers"][1]["base"] = True
        self.bad(m, "only FlatGeobuf layers")
        m = valid_manifest()
        m["layers"][0]["base"] = "yes"
        self.bad(m, "base must be true or false")

    def test_rasters_sit_on_the_grid(self):
        m = valid_manifest()
        m["layers"][1]["grid"]["west"] = 495925
        self.bad(m, "isn't on the ground grid")
        m = valid_manifest()
        m["layers"][1]["grid"].update(res=0.6, west=495920.0)
        self.bad(m, "isn't on the ground grid")
        m = valid_manifest()
        m["layers"][1]["grid"].update(res=2, west=495922, north=4855748, width=10, height=10)
        M.check(m)
        m = valid_manifest()
        m["layers"][1]["bands"][0]["type"] = "byte"
        self.bad(m, "type must be one of")
        m = valid_manifest()
        m["layers"][1]["bands"][1]["name"] = "group"
        self.bad(m, "unique lower-case name")
        m = valid_manifest()
        m["layers"][1]["bands"][0]["values"] = {"corn": 1}
        self.bad(m, "whole-number codes")

    def test_odd_types_are_manifest_errors(self):
        for path, value in ((("inputs", 0, "licence"), ["public-domain"]), (("layers", 0, "format"), {"x": 1}),
                            (("layers", 0, "republish"), ["yes"]), (("layers", 0, "geometry"), ["Polygon"]),
                            (("layers", 0, "inputs"), [["csb"]]), (("layers", 0, "fields"), {"id": ["int"]}),
                            (("layers", 1, "bands"), [{"name": "group", "type": ["uint8"]}])):
            m = valid_manifest()
            node = m
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = value
            with self.assertRaises(M.ManifestError, msg=str(path)):
                M.check(m)

    def test_json_schema_names_the_plugin(self):
        m = valid_manifest()
        m["layers"][2]["schema"] = "soils.palette/1"
        self.bad(m, "farm.<name>/<version>")

    def test_strictest(self):
        self.assertEqual(M.strictest(["yes", "internal", "aggregates"]), "internal")
        self.assertEqual(M.strictest([]), "yes")
        self.assertEqual([M.rank(v) for v in M.REPUBLISH], [0, 1, 2, 3])

    def test_licence_registry(self):
        for name, lic in M.LICENCES.items():
            self.assertIn(lic.loosest, M.REPUBLISH, name)
        self.assertTrue(M.LICENCES["ODbL-1.0"].share_alike)
        self.assertTrue(M.LICENCES["none-stated"].per_source)
        self.assertEqual(M.LICENCES["restricted"].loosest, "no")
        # Overture: places is CDLA-Permissive-2.0; buildings, transportation and divisions are ODbL (from OSM)
        self.assertIn("places", M.LICENCES["CDLA-Permissive-2.0"].about)
        for theme in ("buildings", "transportation", "divisions"):
            self.assertIn(theme, M.LICENCES["ODbL-1.0"].about)
            self.assertNotIn(theme, M.LICENCES["CDLA-Permissive-2.0"].about)


class SourcesTest(unittest.TestCase):
    """Inputs that name a plugin source are no looser than its plugin.json (the owner's decision for it)."""

    def manifest(self, entry):
        m = valid_manifest()
        m["inputs"][0] = dict(entry, name="csb")
        for lay in m["layers"]:
            lay["republish"] = M.strictest([lay["republish"], entry["republish"]])
            if lay["licence"] != "ODbL-1.0":
                lay["licence"] = entry["licence"]
            lay["credit"] = [entry["credit"] if c == "USDA NASS Crop Sequence Boundaries" else c
                             for c in lay["credit"]]
        M.check(m)
        return m

    def test_against_a_registry(self):
        M.check_sources(self.manifest(ACHD), REGISTRY)
        with self.assertRaises(M.ManifestError) as ctx:
            M.check_sources(self.manifest(dict(ACHD, republish="aggregates")), REGISTRY)
        self.assertIn("looser than its source roads/achd_roads ('internal' in plugin.json)", str(ctx.exception))
        wfigs = {"licence": "none-stated", "republish": "yes", "source": "hazards/nifc_wfigs_perimeters",
                 "credit": "NIFC"}
        M.check_sources(self.manifest(wfigs), REGISTRY)
        with self.assertRaises(M.ManifestError) as ctx:
            M.check_sources(self.manifest(dict(wfigs, source="hazards/nope")), REGISTRY)
        self.assertIn("which no plugin.json lists", str(ctx.exception))
        M.check_sources(valid_manifest(), {})                     # nothing named: nothing to look up

    def test_the_real_plugin_manifests(self):
        reg = M.plugin_sources()
        for key, entry in REGISTRY.items():
            self.assertEqual(reg[key]["republish"], entry["republish"], key)
        self.assertEqual(reg["roads/compass_centerline"]["republish"], "yes")
        M.check_sources(self.manifest(ACHD))
        with self.assertRaises(M.ManifestError):
            M.check_sources(self.manifest(dict(ACHD, republish="yes")))


class WriteReadTest(unittest.TestCase):
    def setUp(self):
        self.archive = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.archive)

    def test_write_fills_from_the_files_and_reads_back(self):
        folder = export(self.archive)
        m = M.write(folder, "soils", [SSURGO, OSM], [ground_layer(inputs=["ssurgo", "osm"])],
                    command="python3 -m ingest soils-export")
        lay = m.layer("ground")
        self.assertEqual(lay["geometry"], "MultiPolygon")
        self.assertEqual(lay["fields"], {"id": "int", "ground_type": "int", "misc": "string"})
        self.assertEqual(lay["features"], 3)
        self.assertEqual(lay["crs"], "EPSG:32611")
        self.assertEqual(lay["licence"], "ODbL-1.0")             # OSM is share-alike
        self.assertEqual(lay["republish"], "yes")
        self.assertEqual(lay["credit"], [SSURGO["credit"], OSM["credit"]])
        self.assertEqual(lay["bytes"], os.path.getsize(os.path.join(FIXTURES, "squares.fgb")))
        self.assertEqual(lay.ref, f"soils/ground@{BUILD}")
        again = M.read(folder)
        self.assertEqual(again.data, m.data)
        self.assertEqual(again.republish, "yes")
        self.assertEqual(again.credits, [SSURGO["credit"], OSM["credit"]])
        with open(os.path.join(folder, M.FILE), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["build"], BUILD)
        self.assertEqual([n for n in os.listdir(folder) if n.startswith(".")], [])   # no temp file left

    def test_write_derives_the_strictest(self):
        folder = export(self.archive, "roads")
        m = M.write(folder, "roads", [ACHD, OSM], [ground_layer(name="surface", inputs=["achd-roads", "osm"])])
        self.assertEqual(m.layer("surface")["republish"], "internal")
        self.assertEqual(m.layer("surface")["licence"], "ODbL-1.0")

    def test_write_needs_a_licence_when_inputs_differ(self):
        folder = export(self.archive)
        nhd = {"name": "nhd", "licence": "public-domain", "republish": "yes", "credit": "USGS NHD"}
        cop = {"name": "s2", "licence": "Copernicus", "republish": "yes", "credit": "Copernicus"}
        with self.assertRaises(M.ManifestError):
            M.write(folder, "soils", [nhd, cop], [ground_layer(inputs=["nhd", "s2"])])
        M.write(folder, "soils", [nhd, cop], [ground_layer(inputs=["nhd", "s2"], licence="public-domain")])
        m = M.write(folder, "soils", [nhd, ACHD], [ground_layer(inputs=["nhd", "achd-roads"])], registry=REGISTRY)
        self.assertEqual((m.layer("ground")["licence"], m.layer("ground")["republish"]), ("none-stated", "internal"))

    def test_write_checks_sources(self):
        folder = export(self.archive, "roads")
        with self.assertRaises(M.ManifestError):
            M.write(folder, "roads", [dict(ACHD, republish="aggregates")],
                    [ground_layer(name="surface", inputs=["achd-roads"])], registry=REGISTRY)
        self.assertFalse(os.path.exists(os.path.join(folder, M.FILE)))
        M.write(folder, "roads", [ACHD], [ground_layer(name="surface", inputs=["achd-roads"])], registry=REGISTRY)
        with self.assertRaises(M.ManifestError):                       # read() checks too
            M.read(folder, registry={"roads/achd_roads": {"republish": "no"}})

    def test_plugin_is_the_folders(self):
        folder = export(self.archive, "soils")
        with self.assertRaises(M.ManifestError) as ctx:
            M.write(folder, "farm", [SSURGO], [ground_layer()])
        self.assertIn("isn't the folder's", str(ctx.exception))
        M.write(folder, "soils", [SSURGO], [ground_layer()])
        mpath = os.path.join(folder, M.FILE)
        with open(mpath, encoding="utf-8") as f:
            data = json.load(f)
        data["plugin"] = "farm"
        with open(mpath, "w", encoding="utf-8") as f:
            json.dump(data, f)
        for call in (lambda: M.read(folder), lambda: M.latest(self.archive, "soils"), lambda: M.find(self.archive)):
            with self.assertRaises(M.ManifestError):
                call()

    def test_geotiff_and_json_files_are_verified(self):
        folder = export(self.archive, "farm", files=())
        g = {"res": 10, "west": 495920, "north": 4855750, "width": 6, "height": 4}
        bands = [{"name": "group", "type": "uint8"}, {"name": "state", "type": "uint8"}]
        lay = {"name": "crop_cover", "file": "crop_cover.tif", "format": "GeoTIFF", "crs": "EPSG:32611",
               "grid": g, "bands": bands, "inputs": ["ssurgo"], "base": False}
        pal = {"name": "palette", "file": "palette.json", "format": "JSON", "schema": "farm.palette/1",
               "inputs": ["ssurgo"], "base": False}
        tif_path, json_path = os.path.join(folder, "crop_cover.tif"), os.path.join(folder, "palette.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"schema": "farm.palette/1", "types": {}}, f)
        for wrong, words in ((dict(g, width=7), "7 x 4"), (dict(g, north=4855755), "corner"),
                             (dict(g, res=5), "cells are 5 x 5 m")):
            grid_tiff(tif_path, wrong, bands)
            with self.assertRaises(M.ManifestError, msg=words) as ctx:
                M.write(folder, "farm", [SSURGO], [lay, pal])
            self.assertIn(words, str(ctx.exception))
        grid_tiff(tif_path, g, bands[:1])
        with self.assertRaises(M.ManifestError) as ctx:
            M.write(folder, "farm", [SSURGO], [lay, pal])
        self.assertIn("bands", str(ctx.exception))
        grid_tiff(tif_path, g, [{"type": "uint8"}, {"type": "float32"}])
        with self.assertRaises(M.ManifestError):
            M.write(folder, "farm", [SSURGO], [lay, pal])
        from basemap.ground.tests.tiffs import write_geotiff
        write_geotiff(tif_path, 6, 4, (495920, 10, 0, 4855750, 0, -10), epsg=26911, types=("uint8", "uint8"))
        with self.assertRaises(M.ManifestError) as ctx:
            M.write(folder, "farm", [SSURGO], [lay, pal])
        self.assertIn("EPSG:26911", str(ctx.exception))
        grid_tiff(tif_path, g, bands, point=True)                       # PixelIsPoint, the same corners
        m = M.write(folder, "farm", [SSURGO], [lay, pal])
        M.read(folder)
        with open(json_path, "w", encoding="utf-8") as f:
            f.write('{"schema": "farm.palette/2", "types": {}}')
        m.data["layers"][1].update(bytes=os.path.getsize(json_path), sha256=M.sha256_of(json_path))
        with open(os.path.join(folder, M.FILE), "w", encoding="utf-8") as f:
            json.dump(m.data, f)
        with self.assertRaises(M.ManifestError) as ctx:
            M.read(folder)
        self.assertIn("schema", str(ctx.exception))
        with open(json_path, "w", encoding="utf-8") as f:
            f.write("{not json")
        m.data["layers"][1].update(bytes=os.path.getsize(json_path), sha256=M.sha256_of(json_path))
        with open(os.path.join(folder, M.FILE), "w", encoding="utf-8") as f:
            json.dump(m.data, f)
        with self.assertRaises(M.ManifestError) as ctx:
            M.read(folder)
        self.assertIn("not JSON", str(ctx.exception))

    def test_write_refuses_what_the_file_contradicts(self):
        folder = export(self.archive)
        with self.assertRaises(M.ManifestError):
            M.write(folder, "soils", [SSURGO], [ground_layer(fields={"ground_type": "int"})])
        with self.assertRaises(M.ManifestError):
            M.write(folder, "soils", [SSURGO], [ground_layer(features=4)])
        with self.assertRaises(M.ManifestError):
            M.write(folder, "soils", [SSURGO], [ground_layer(geometry="Polygon")])
        self.assertFalse(os.path.exists(os.path.join(folder, M.FILE)))

    def test_feature_count_needed_without_an_index(self):
        folder = export(self.archive, files=("lines-no-index.fgb",))
        lay = ground_layer(name="lines", file="lines-no-index.fgb")
        with self.assertRaises(M.ManifestError) as ctx:
            M.write(folder, "soils", [SSURGO], [lay])
        self.assertIn("spatial index", str(ctx.exception))
        m = M.write(folder, "soils", [SSURGO], [dict(lay, features=2)])
        self.assertEqual(m.layer("lines")["geometry"], "LineString")
        M.read(folder)                                        # no CRS or count in the header: nothing to contradict

    def test_read_catches_changed_files(self):
        folder = export(self.archive)
        M.write(folder, "soils", [SSURGO], [ground_layer()])
        path = os.path.join(folder, "squares.fgb")
        with open(path, "r+b") as f:                          # same size, different bytes (in a coordinate)
            f.seek(-9, os.SEEK_END)
            b = f.read(1)
            f.seek(-9, os.SEEK_END)
            f.write(bytes([b[0] ^ 1]))
        with self.assertRaises(M.ManifestError) as ctx:
            M.read(folder)
        self.assertIn("sha256", str(ctx.exception))
        M.read(folder, hashes=False)
        with open(path, "ab") as f:
            f.write(b"x")
        with self.assertRaises(M.ManifestError) as ctx:
            M.read(folder, hashes=False)
        self.assertIn("bytes", str(ctx.exception))
        M.read(folder, verify=False)

    def test_read_catches_a_manifest_that_disagrees_with_the_header(self):
        folder = export(self.archive)
        M.write(folder, "soils", [SSURGO], [ground_layer()])
        mpath = os.path.join(folder, M.FILE)
        with open(mpath, encoding="utf-8") as f:
            data = json.load(f)
        for key, value, words in (("fields", {"id": "int", "ground_type": "long", "misc": "string"}, "fields"),
                                  ("features", 5, "features"), ("geometry", "Polygon", "holds MultiPolygon")):
            d = copy.deepcopy(data)
            d["layers"][0][key] = value
            with open(mpath, "w", encoding="utf-8") as f:
                json.dump(d, f)
            with self.assertRaises(M.ManifestError) as ctx:
                M.read(folder, hashes=False)
            self.assertIn(words, str(ctx.exception))

    def test_write_without_the_file(self):
        folder = export(self.archive, files=())
        with self.assertRaises(M.ManifestError):
            M.write(folder, "soils", [SSURGO], [ground_layer()])

    def test_missing_file(self):
        folder = export(self.archive)
        M.write(folder, "soils", [SSURGO], [ground_layer()])
        os.remove(os.path.join(folder, "squares.fgb"))
        with self.assertRaises(M.ManifestError):
            M.read(folder)

    def test_latest_and_find(self):
        self.assertIsNone(M.latest(self.archive, "soils"))
        self.assertEqual(M.find(self.archive), {})
        old = export(self.archive, build="20261011T000000Z")
        M.write(old, "soils", [SSURGO], [ground_layer()])
        new = export(self.archive, build="20261012T000000Z")
        M.write(new, "soils", [SSURGO], [ground_layer()])
        export(self.archive, build="20261013T000000Z")          # unfinished: no manifest
        os.makedirs(os.path.join(self.archive, "soils", "export", "scratch"))   # not a build
        self.assertEqual(M.builds(self.archive, "soils"), ["20261011T000000Z", "20261012T000000Z"])
        self.assertEqual(M.latest(self.archive, "soils").build, "20261012T000000Z")
        farm = export(self.archive, "farm")
        M.write(farm, "farm", [SSURGO], [ground_layer(name="fields")])
        os.makedirs(os.path.join(self.archive, "trees", "20261001T000000Z"))    # a plugin without exports
        self.assertEqual(sorted(M.find(self.archive)), ["farm", "soils"])

    def test_newest_broken_export_raises(self):
        old = export(self.archive, build="20261011T000000Z")
        M.write(old, "soils", [SSURGO], [ground_layer()])
        new = export(self.archive, build="20261012T000000Z")
        M.write(new, "soils", [SSURGO], [ground_layer()])
        os.remove(os.path.join(new, "squares.fgb"))
        with self.assertRaises(M.ManifestError):
            M.latest(self.archive, "soils")

    def test_build_id(self):
        import datetime as dt
        t = dt.datetime(2026, 10, 12, 3, 15, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(M.build_id(t), "20261012T031500Z")
        self.assertEqual(M.build_id(t, "p1data"), "20261012T031500Z-p1data")
        self.assertTrue(M.BUILD_RE.match(M.build_id()))


if __name__ == "__main__":
    unittest.main()
