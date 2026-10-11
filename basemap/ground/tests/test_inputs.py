"""The ground's inputs (inputs.py): every one is republish yes, and the flat fallback. Standard library only.

The republish test (§5, C17): the ground's raw inputs, and every export layer it reads, read no internal source.
"""

import os
import shutil
import tempfile
import unittest

from basemap.ground import inputs as I, manifest as M
from basemap.ground.tests.test_manifest import FIXTURES, OSM, SSURGO, export

CSB = {"name": "csb", "licence": "public-domain", "republish": "yes", "credit": "USDA NASS Crop Sequence Boundaries"}
NHD = {"name": "nhd", "licence": "public-domain", "republish": "yes",
       "credit": "U.S. Geological Survey, National Hydrography Dataset"}


def fgb_layer(name, inputs, **kw):
    lay = {"name": name, "file": f"{name}.fgb", "format": "FlatGeobuf", "inputs": inputs, "base": False}
    lay.update(kw)
    return lay


def write_export(archive, plugin, layers, inputs, build="20261012T031500Z", extra_files=()):
    """An export whose FlatGeobuf layers are copies of squares.fgb (fields id, ground_type, misc)."""
    folder = export(archive, plugin, build, files=())
    for lay in layers:
        if lay["format"] == "FlatGeobuf":
            shutil.copy(os.path.join(FIXTURES, "squares.fgb"), os.path.join(folder, lay["file"]))
    for name, data in extra_files:
        with open(os.path.join(folder, name), "wb") as f:
            f.write(data)
    return M.write(folder, plugin, inputs, layers)


class RawInputsTest(unittest.TestCase):
    def test_every_raw_input_is_public(self):
        for r in I.RAW:
            self.assertEqual(r.republish, "yes", r.name)
            self.assertIn(r.licence, M.LICENCES, r.name)
            self.assertEqual(M.LICENCES[r.licence].loosest, "yes", r.name)
            self.assertTrue(r.credit.strip(), r.name)

    def test_credits_named_in_the_plan(self):
        names = {r.name for r in I.RAW}
        self.assertEqual(names, {"osm", "overture-buildings", "nhd", "cdl", "csb", "naip", "3dep", "sentinel-2"})
        credits = " ".join(r.credit for r in I.RAW)
        for word in ("OpenStreetMap", "Overture", "National Hydrography", "Cropland Data Layer",
                     "Crop Sequence Boundaries", "NAIP", "3D Elevation Program", "Copernicus Sentinel"):
            self.assertIn(word, credits)

    def test_roads_is_never_an_input(self):
        self.assertIn("roads", I.NEVER)
        for u in I.USES:
            self.assertNotIn(u.plugin, I.NEVER, u.ref)
        self.assertEqual(I.GROUND_LICENCE, "ODbL-1.0")

    def test_only_soils_ground_has_no_fallback(self):
        self.assertEqual([u.ref for u in I.USES if u.fallback is None], ["soils/ground"])


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.archive = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.archive)

    def plan(self):
        return I.resolve(M.find(self.archive))

    def test_nothing_exported_is_flat_and_says_so(self):
        plan = self.plan()
        self.assertEqual(plan.status, "flat")
        self.assertIn("the soil survey's ground types", plan.reason)
        self.assertTrue(plan.reason.startswith("Flat ground"))
        self.assertTrue(all(c.fallback for c in plan.choices))
        self.assertEqual(plan.choice("soils/ground").reason, "no soils export yet (P1-data)")

    def test_soils_ground_alone_paints_with_fallbacks(self):
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo"])], [SSURGO])
        plan = self.plan()
        self.assertEqual(plan.status, "painted")
        self.assertFalse(plan.choice("soils/ground").fallback)
        for ref in ("soils/palette", "farm/crop_cover", "farm/fields", "water/mask"):
            self.assertTrue(plan.choice(ref).fallback, ref)
        self.assertEqual(plan.choice("soils/palette").reason,
                         "soils@20261012T031500Z has no 'palette' layer (P2)")
        self.assertEqual(plan.republish, "yes")
        self.assertEqual(plan.licence, "ODbL-1.0")
        self.assertIn(SSURGO["credit"], plan.credits)
        self.assertEqual(plan.credits[0], "© OpenStreetMap contributors")
        self.assertEqual(plan.refs, ["soils/ground@20261012T031500Z"])

    def test_an_internal_input_is_refused(self):
        # A soils layer built with an ACHD table would make the ground internal: refused, not quietly used.
        achd = {"name": "achd", "licence": "none-stated", "republish": "internal", "credit": "ACHD"}
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo", "achd"], licence="ODbL-1.0")],
                     [SSURGO, achd])
        with self.assertRaises(I.InputError) as ctx:
            self.plan()
        self.assertIn("public inputs only", str(ctx.exception))

    def test_aggregates_are_not_enough(self):
        r2r = {"name": "r2r", "licence": "none-stated", "republish": "aggregates", "credit": "Ridge to Rivers"}
        write_export(self.archive, "soils", [fgb_layer("ground", ["r2r"])], [r2r])
        with self.assertRaises(I.InputError):
            self.plan()

    def test_a_stricter_layer_over_public_inputs_is_refused(self):
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo"], republish="internal")], [SSURGO])
        with self.assertRaises(I.InputError):
            self.plan()

    def test_shapes_are_checked(self):
        # squares.fgb has no 'bearing' field, so it can't be farm's fields layer
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo"])], [SSURGO])
        write_export(self.archive, "farm", [fgb_layer("fields", ["csb"])], [CSB])
        with self.assertRaises(I.InputError) as ctx:
            self.plan()
        self.assertIn("'bearing'", str(ctx.exception))

    def test_crop_cover_must_be_on_the_10m_grid(self):
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo"])], [SSURGO])
        cover = {"name": "crop_cover", "file": "crop_cover.tif", "format": "GeoTIFF", "crs": "EPSG:32611",
                 "grid": {"res": 2, "west": 495920, "north": 4855750, "width": 4, "height": 4},
                 "bands": [{"name": "group", "type": "uint8"}], "inputs": ["csb"], "base": False}
        write_export(self.archive, "farm", [cover], [CSB], extra_files=[("crop_cover.tif", b"not really a tiff")])
        with self.assertRaises(I.InputError) as ctx:
            self.plan()
        self.assertIn("10 m", str(ctx.exception))

    def test_crop_cover_bands(self):
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo"])], [SSURGO])
        cover = {"name": "crop_cover", "file": "crop_cover.tif", "format": "GeoTIFF", "crs": "EPSG:32611",
                 "grid": {"res": 10, "west": 495920, "north": 4855750, "width": 4, "height": 4},
                 "bands": [{"name": "group", "type": "uint8"}, {"name": "confidence", "type": "uint8"}],
                 "inputs": ["csb"], "base": False}
        write_export(self.archive, "farm", [cover], [CSB], extra_files=[("crop_cover.tif", b"II*\x00")])
        with self.assertRaises(I.InputError) as ctx:
            self.plan()
        self.assertIn("bands", str(ctx.exception))

    def test_palette_schema(self):
        palette = {"name": "palette", "file": "palette.json", "format": "JSON", "schema": "soils.palette/2",
                   "inputs": ["ssurgo"], "base": False}
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo"]), palette], [SSURGO],
                     extra_files=[("palette.json", b"{}")])
        with self.assertRaises(I.InputError) as ctx:
            self.plan()
        self.assertIn("soils.palette/1", str(ctx.exception))

    def test_every_use_read_from_exports(self):
        palette = {"name": "palette", "file": "palette.json", "format": "JSON", "schema": "soils.palette/1",
                   "inputs": ["ssurgo", "naip"], "licence": "public-domain", "base": False}
        naip = {"name": "naip", "licence": "public-domain", "republish": "yes", "credit": "USDA NAIP"}
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo", "osm"]), palette], [SSURGO, OSM, naip],
                     extra_files=[("palette.json", b"{}")])
        cover = {"name": "crop_cover", "file": "crop_cover.tif", "format": "GeoTIFF", "crs": "EPSG:32611",
                 "grid": {"res": 10, "west": 495920, "north": 4855750, "width": 8967, "height": 9494},
                 "bands": [{"name": "group", "type": "uint8"}, {"name": "state", "type": "uint8"},
                           {"name": "confidence", "type": "uint8"}], "inputs": ["csb"], "base": False}
        folder = export(self.archive, "farm", files=())
        shutil.copy(os.path.join(FIXTURES, "squares.fgb"), os.path.join(folder, "fields.fgb"))
        with open(os.path.join(folder, "crop_cover.tif"), "wb") as f:
            f.write(b"II*\x00")
        fields = fgb_layer("fields", ["csb"], fields={"id": "int", "ground_type": "int", "misc": "string"})
        m = M.write(folder, "farm", [CSB], [fields, cover])
        # the ground reads fields' 'bearing': make the test's copy say it has one (headers aren't re-read here)
        m.data["layers"][0]["fields"] = {"id": "int", "bearing": "double"}
        write_export(self.archive, "water", [fgb_layer("mask", ["nhd", "osm"])], [NHD, OSM])
        found = M.find(self.archive)
        found["farm"] = m
        plan = I.resolve(found)
        self.assertEqual(plan.status, "painted")
        self.assertFalse(any(c.fallback for c in plan.choices))
        self.assertEqual(plan.republish, "yes")
        for credit in ("USDA NAIP", "U.S. Geological Survey, National Hydrography Dataset", SSURGO["credit"]):
            self.assertIn(credit, plan.credits)
        self.assertEqual(len(plan.credits), len(set(plan.credits)))


if __name__ == "__main__":
    unittest.main()
