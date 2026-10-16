"""The ground's inputs (inputs.py): every one is republish yes, and the flat fallback. Standard library only.

The republish test (§5, C17): the ground's raw inputs, every export layer it reads, and its own products (mask v0,
the box classes) read no internal source.
"""

import json
import os
import shutil
import tempfile
import unittest

from basemap.ground import grid as G, inputs as I, manifest as M, maskrules as MR
from basemap.ground.tests.test_manifest import ACHD, FIXTURES, OSM, SSURGO, export
from basemap.ground.tests.tiffs import grid_tiff

CSB = {"name": "csb", "licence": "public-domain", "republish": "yes", "credit": "USDA NASS Crop Sequence Boundaries"}
NHD = {"name": "nhd", "licence": "public-domain", "republish": "yes",
       "credit": "U.S. Geological Survey, National Hydrography Dataset"}
R2R = {"name": "r2r", "licence": "none-stated", "republish": "aggregates", "credit": "Ridge to Rivers",
       "source": "trails/r2r_trails"}


MASK_LAYERS = tuple(MR.LAYERS)


def fgb_layer(name, inputs, **kw):
    lay = {"name": name, "file": f"{name}.fgb", "format": "FlatGeobuf", "inputs": inputs, "base": False}
    lay.update(kw)
    return lay


def tif_layer(name, inputs, g, bands=("group", "state", "confidence"), **kw):
    lay = {"name": name, "file": f"{name}.tif", "format": "GeoTIFF", "crs": "EPSG:32611", "grid": dict(g),
           "bands": [{"name": b, "type": "uint8"} for b in bands], "inputs": inputs, "base": False}
    lay.update(kw)
    return lay


def write_export(archive, plugin, layers, inputs, build="20261012T031500Z", extra_files=()):
    """An export whose FlatGeobuf layers are copies of squares.fgb (fields id, ground_type, misc), whose GeoTIFF
    layers are header-only GeoTIFFs on their declared grid, and whose JSON layers name their schema."""
    folder = export(archive, plugin, build, files=())
    given = {name for name, _ in extra_files}
    for name, data in extra_files:
        with open(os.path.join(folder, name), "wb") as f:
            f.write(data)
    for lay in layers:
        path = os.path.join(folder, lay["file"])
        if lay["file"] in given:
            continue
        if lay["format"] == "FlatGeobuf":
            shutil.copy(os.path.join(FIXTURES, "squares.fgb"), path)
        elif lay["format"] == "GeoTIFF":
            grid_tiff(path, lay["grid"], lay["bands"], data=False)
        else:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"schema": lay["schema"]}, f)
    return M.write(folder, plugin, inputs, layers)


def write_mask(archive, inputs=None, build="20261011T040000Z", layers=MASK_LAYERS):
    """Mask v0 (S5a-2's product) with its layers (copies of squares.fgb), from raw inputs."""
    inputs = inputs or [I.RAW_BY_NAME["osm"].entry("md5:0123"), I.RAW_BY_NAME["overture-buildings"].entry("2025-09")]
    return write_export(archive, "ground_mask", [fgb_layer(n, [e["name"] for e in inputs]) for n in layers], inputs,
                        build)


def write_farm(archive, build="20261012T031500Z"):
    """Farm's export (P3-data): fields.fgb (the fields fixture, written by PostGIS like farm's own, with crop_group and
    bearing) and a header-only crop_cover on the 10 m grid, from CSB."""
    with open(os.path.join(FIXTURES, "fields.fgb"), "rb") as f:
        fields = f.read()
    g = {"res": 10, "west": 495920, "north": 4855750, "width": 4, "height": 4}
    return write_export(archive, "farm", [fgb_layer("fields", ["csb"]), tif_layer("crop_cover", ["csb"], g)], [CSB],
                        build, extra_files=(("fields.fgb", fields),))


def box_grid(box_id):
    w = G.box(box_id).window()
    return {"res": w.res, "west": w.west, "north": w.north, "width": w.width, "height": w.height}


def write_classes(archive, boxes=("a", "d"), inputs=None, build="20261013T040000Z"):
    inputs = inputs or [I.RAW_BY_NAME[n].entry() for n in ("naip", "3dep", "sentinel-2", "rcmap", "osm")]
    names = [e["name"] for e in inputs]
    layers = [tif_layer(b, names, box_grid(b), bands=("class",)) for b in boxes]
    return write_export(archive, "ground_classes", layers, inputs, build)


class RawInputsTest(unittest.TestCase):
    def test_every_raw_input_is_public(self):
        for r in I.RAW:
            self.assertEqual(r.republish, "yes", r.name)
            self.assertIn(r.licence, M.LICENCES, r.name)
            self.assertEqual(M.LICENCES[r.licence].loosest, "yes", r.name)
            self.assertFalse(M.LICENCES[r.licence].per_source, r.name)
            self.assertTrue(r.credit.strip(), r.name)

    def test_credits_named_in_the_plan(self):
        names = {r.name for r in I.RAW}
        self.assertEqual(names, {"osm", "overture-buildings", "nhd", "cdl", "csb", "naip", "naip-2m", "3dep",
                                 "sentinel-2", "rcmap"})
        credits = " ".join(r.credit for r in I.RAW)
        for word in ("OpenStreetMap", "Overture", "National Hydrography", "Cropland Data Layer",
                     "Crop Sequence Boundaries", "NAIP", "3D Elevation Program", "Copernicus Sentinel", "RCMAP"):
            self.assertIn(word, credits)

    def test_roads_is_never_an_input(self):
        self.assertIn("roads", I.NEVER)
        for u in I.USES:
            self.assertNotIn(u.plugin, I.NEVER, u.ref)
        self.assertEqual(I.GROUND_LICENCE, "ODbL-1.0")

    def test_what_has_no_fallback(self):
        self.assertEqual([u.ref for u in I.USES if u.fallback is None],
                         ["soils/ground", "farm/crop_cover", "farm/fields", "ground_mask"])

    def test_products_are_not_plugins(self):
        self.assertEqual(I.PRODUCTS, ("ground_mask", "ground_classes"))
        plugins = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))), "plugins")
        for p in I.PRODUCTS:
            self.assertFalse(os.path.exists(os.path.join(plugins, p)), p)

    def test_fallbacks_read_raw_inputs(self):
        for u in I.USES:
            for name in u.fallback_reads:
                self.assertIn(name, I.RAW_BY_NAME, u.ref)


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.archive = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.archive)

    def plan(self, versions=None):
        return I.resolve(I.exports(self.archive), versions)

    def test_nothing_exported_is_flat_and_says_so(self):
        plan = self.plan()
        self.assertEqual(plan.status, "flat")
        self.assertEqual(plan.reason, "Flat ground: the painted ground needs the soil survey's ground types, the crop "
                                      "cover, the crop fields and mask v0, which aren't built yet.")
        self.assertTrue(all(c.fallback for c in plan.choices))
        self.assertEqual(plan.choice("soils/ground").reason, "no soils export yet (P1-data)")
        write_mask(self.archive)
        write_farm(self.archive)
        self.assertEqual(self.plan().reason, "Flat ground: the painted ground needs the soil survey's ground types, "
                                             "which isn't built yet.")

    def test_no_crops_is_flat(self):
        # C7's CSB and CDL fallback was retired when farm's crop cover landed: a Valley without crops isn't painted.
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo"])], [SSURGO])
        write_mask(self.archive)
        plan = self.plan()
        self.assertEqual(plan.status, "flat")
        self.assertEqual(plan.reason, "Flat ground: the painted ground needs the crop cover and the crop fields, which "
                                      "aren't built yet.")
        self.assertEqual(plan.choice("farm/crop_cover").reason, "no farm export yet (P3-data)")
        write_farm(self.archive)
        self.assertEqual(self.plan().status, "painted")

    def test_soils_ground_farm_and_mask_paint_with_fallbacks(self):
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo"])], [SSURGO])
        mask = write_mask(self.archive)
        farm = write_farm(self.archive)
        plan = self.plan()
        self.assertEqual(plan.status, "painted")
        self.assertFalse(plan.choice("soils/ground").fallback)
        self.assertEqual(plan.choice("ground_mask").layers[0].ref, f"ground_mask/roofs@{mask.build}")
        self.assertEqual(plan.choice("farm/fields").layer.ref, f"farm/fields@{farm.build}")
        for ref in ("soils/palette", "water/mask", "ground_classes"):
            self.assertTrue(plan.choice(ref).fallback, ref)
        self.assertEqual(plan.choice("soils/palette").reason,
                         "soils@20261012T031500Z has no 'palette' layer (P2)")
        self.assertEqual(plan.republish, "yes")
        self.assertEqual(plan.licence, "ODbL-1.0")
        self.assertEqual(plan.raw_names, [])                          # the fallbacks left read no raw input
        self.assertEqual(plan.missing_versions, [])
        self.assertIn(SSURGO["credit"], plan.credits)
        self.assertIn("© OpenStreetMap contributors", plan.credits)  # through mask v0
        self.assertIn(CSB["credit"], plan.credits)                   # through farm's export
        self.assertEqual(plan.refs, ["soils/ground@20261012T031500Z", f"farm/crop_cover@{farm.build}",
                                     f"farm/fields@{farm.build}"] +
                         [f"ground_mask/{n}@{mask.build}" for n in MASK_LAYERS])
        plan = self.plan({"cdl": "2025", "naip": "2025 county mosaics"})
        self.assertEqual(plan.missing_versions, [])
        self.assertEqual(plan.raw_names, ["cdl", "naip"])
        self.assertIn("USDA NAIP", plan.credits)

    def test_a_fallbacks_raw_inputs_need_versions(self):
        # A fallback that reads raw files names them, so their versions go into the tiles' digest (tiles.digest).
        use = I.Use("farm", "fields", "FlatGeobuf", "the crop fields", "fields", "P3-data", fallback="CSB polygons",
                    fallback_reads=("csb",))
        plan = I.Plan("painted", "", [I.Choice(use, reason="no farm export yet")], {"naip": "2025"})
        self.assertEqual(plan.raw_names, ["csb", "naip"])
        self.assertEqual(plan.missing_versions, ["csb"])
        self.assertEqual(I.Plan("painted", "", plan.choices, {"naip": "2025", "csb": "2025"}).missing_versions, [])

    def test_versions_name_raw_inputs(self):
        with self.assertRaises(I.InputError):
            self.plan({"achd": "2026"})
        with self.assertRaises(I.InputError):
            self.plan({"naip": " "})

    def test_an_internal_input_is_refused(self):
        # A soils layer built with an ACHD table would make the ground internal: refused, not quietly used.
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo", "achd-roads"])], [SSURGO, ACHD])
        with self.assertRaises(I.InputError) as ctx:
            self.plan()
        self.assertIn("public inputs only", str(ctx.exception))

    def test_aggregates_are_not_enough(self):
        write_export(self.archive, "soils", [fgb_layer("ground", ["r2r"])], [R2R])
        with self.assertRaises(I.InputError):
            self.plan()

    def test_a_none_stated_source_approved_for_yes_is_public(self):
        # NIFC's WFIGS perimeters have no licence, and the owner set them republish yes (hazards' plugin.json).
        wfigs = {"name": "wfigs", "licence": "none-stated", "republish": "yes",
                 "source": "hazards/nifc_wfigs_perimeters", "credit": "National Interagency Fire Center (WFIGS)"}
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo", "wfigs"])], [SSURGO, wfigs])
        write_mask(self.archive)
        write_farm(self.archive)
        plan = self.plan()
        self.assertEqual(plan.status, "painted")
        self.assertEqual(plan.choice("soils/ground").layer["licence"], "none-stated")

    def test_a_stricter_layer_over_public_inputs_is_refused(self):
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo"], republish="internal")], [SSURGO])
        with self.assertRaises(I.InputError):
            self.plan()

    def test_mask_v0_needs_its_layers(self):
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo"])], [SSURGO])
        write_mask(self.archive, layers=("roofs", "roads", "covered"))
        with self.assertRaises(I.InputError) as ctx:
            self.plan()
        self.assertIn("ground_mask@20261011T040000Z lacks the layer(s) paving, water (S5a-2)", str(ctx.exception))
        self.assertEqual(I.USES[[u.ref for u in I.USES].index("ground_mask")].required,
                         ("roofs", "roads", "paving", "water", "covered"))

    def test_a_partial_mask_is_never_read(self):
        # A box's quick look is skipped as the newest, and refused if it's handed in.
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo"])], [SSURGO])
        whole = write_mask(self.archive)
        write_farm(self.archive)
        part = write_mask(self.archive, build="20261011T050000Z-box-d-part")
        self.assertEqual(I.exports(self.archive)["ground_mask"].build, whole.build)
        self.assertEqual(self.plan().status, "painted")
        with self.assertRaises(I.InputError) as ctx:
            I.resolve(dict(I.exports(self.archive), ground_mask=part))
        self.assertIn("ground_mask@20261011T050000Z-box-d-part is a partial build", str(ctx.exception))

    def test_mask_v0_layers_are_areas(self):
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo"])], [SSURGO])
        inputs = [I.RAW_BY_NAME["osm"].entry("md5:0123")]
        folder = export(self.archive, "ground_mask", "20261011T040000Z", files=())
        layers = []
        for n in MASK_LAYERS:
            src = "lines-no-index.fgb" if n == "roads" else "squares.fgb"
            shutil.copy(os.path.join(FIXTURES, src), os.path.join(folder, f"{n}.fgb"))
            layers.append(fgb_layer(n, ["osm"], **({"features": 2} if n == "roads" else {})))
        M.write(folder, "ground_mask", inputs, layers)
        with self.assertRaises(I.InputError) as ctx:
            self.plan()
        self.assertIn("ground_mask/roads@20261011T040000Z holds LineString", str(ctx.exception))

    def test_shapes_are_checked(self):
        # squares.fgb has no 'bearing' field, so it can't be farm's fields layer
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo"])], [SSURGO])
        write_export(self.archive, "farm", [fgb_layer("fields", ["csb"])], [CSB])
        with self.assertRaises(I.InputError) as ctx:
            self.plan()
        self.assertIn("'bearing'", str(ctx.exception))

    def test_crop_cover_must_be_on_the_10m_grid(self):
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo"])], [SSURGO])
        g = {"res": 2, "west": 495920, "north": 4855750, "width": 4, "height": 4}
        write_export(self.archive, "farm", [tif_layer("crop_cover", ["csb"], g)], [CSB])
        with self.assertRaises(I.InputError) as ctx:
            self.plan()
        self.assertIn("10 m", str(ctx.exception))

    def test_crop_cover_bands(self):
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo"])], [SSURGO])
        g = {"res": 10, "west": 495920, "north": 4855750, "width": 4, "height": 4}
        write_export(self.archive, "farm", [tif_layer("crop_cover", ["csb"], g, bands=("group", "confidence"))],
                     [CSB])
        with self.assertRaises(I.InputError) as ctx:
            self.plan()
        self.assertIn("bands", str(ctx.exception))

    def test_crop_cover_half_a_cell_off_is_refused(self):
        g = {"res": 10, "west": 495920, "north": 4855750, "width": 4, "height": 4}
        layer = tif_layer("crop_cover", ["csb"], g)
        folder = export(self.archive, "farm", files=())
        grid_tiff(os.path.join(folder, "crop_cover.tif"), dict(g, west=495925), layer["bands"])
        with self.assertRaises(M.ManifestError) as ctx:                 # write() reads the file's header
            M.write(folder, "farm", [CSB], [layer])
        self.assertIn("corner", str(ctx.exception))

    def test_palette_schema(self):
        palette = {"name": "palette", "file": "palette.json", "format": "JSON", "schema": "soils.palette/2",
                   "inputs": ["ssurgo"], "base": False}
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo"]), palette], [SSURGO],
                     extra_files=[("palette.json", b"{}")])
        with self.assertRaises(I.InputError) as ctx:
            self.plan()
        self.assertIn("soils.palette/1", str(ctx.exception))

    def test_classes_read_raw_inputs_only(self):
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo"])], [SSURGO])
        write_mask(self.archive)
        m = write_classes(self.archive)
        plan = self.plan()
        self.assertEqual([lay.ref for lay in plan.choice("ground_classes").layers],
                         [f"ground_classes/a@{m.build}", f"ground_classes/d@{m.build}"])
        self.assertIn(I.RAW_BY_NAME["rcmap"].credit, plan.credits)
        # The spike's classes took their road reference from ACHD's segments: that would be refused...
        achd = dict(ACHD, name="achd_segments")
        write_classes(self.archive, inputs=[I.RAW_BY_NAME["naip"].entry(), achd], build="20261014T000000Z")
        with self.assertRaises(I.InputError) as ctx:
            self.plan()
        self.assertIn("public inputs only", str(ctx.exception))
        # ...and so would any source outside RAW, however it's labelled
        fake = {"name": "achd_segments", "licence": "public-domain", "republish": "yes", "credit": "ACHD"}
        write_classes(self.archive, inputs=[I.RAW_BY_NAME["naip"].entry(), fake], build="20261015T000000Z")
        with self.assertRaises(I.InputError) as ctx:
            self.plan()
        self.assertIn("isn't one of the ground's raw inputs", str(ctx.exception))
        # a raw input under another licence than RAW's
        cdl = dict(I.RAW_BY_NAME["cdl"].entry(), licence="CC0-1.0")
        write_classes(self.archive, inputs=[cdl], build="20261016T000000Z")
        with self.assertRaises(I.InputError) as ctx:
            self.plan()
        self.assertIn("is public-domain", str(ctx.exception))

    def test_classes_sit_on_their_boxes(self):
        g = box_grid("a")
        inputs = [I.RAW_BY_NAME["naip"].entry()]
        write_export(self.archive, "ground_classes", [tif_layer("nampa", ["naip"], g, bands=("class",))], inputs)
        with self.assertRaises(I.InputError) as ctx:
            self.plan()
        self.assertIn("named by its box", str(ctx.exception))
        g = dict(g, west=g["west"] + 0.5)
        write_export(self.archive, "ground_classes", [tif_layer("a", ["naip"], g, bands=("class",))], inputs,
                     build="20261014T000000Z")
        with self.assertRaises(I.InputError) as ctx:
            self.plan()
        self.assertIn("box a is", str(ctx.exception))

    def test_a_product_in_the_wrong_folder(self):
        folder = export(self.archive, "ground_classes", files=())
        g = box_grid("a")
        grid_tiff(os.path.join(folder, "a.tif"), g, [{"type": "uint8"}], data=False)
        with self.assertRaises(M.ManifestError) as ctx:
            M.write(folder, "farm", [I.RAW_BY_NAME["naip"].entry()],
                    [tif_layer("a", ["naip"], g, bands=("class",))])
        self.assertIn("isn't the folder's", str(ctx.exception))

    def test_only_the_grounds_exports_are_read(self):
        # A broken export of a plugin the ground doesn't read (roads, here) can't hold it up.
        roads = write_export(self.archive, "roads", [fgb_layer("surface", ["osm"])], [OSM])
        with open(os.path.join(roads.folder, "surface.fgb"), "ab") as f:
            f.write(b"x")
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo"])], [SSURGO])
        write_mask(self.archive)
        write_farm(self.archive)
        self.assertEqual(sorted(I.exports(self.archive)), ["farm", "ground_mask", "soils"])
        self.assertEqual(self.plan().status, "painted")
        with self.assertRaises(M.ManifestError):
            M.find(self.archive)                                        # the bake's view: every export

    def test_a_missing_archive_is_an_error(self):
        with self.assertRaises(I.InputError):
            I.exports(os.path.join(self.archive, "not-mounted"))
        with self.assertRaises(I.InputError):
            I.exports("")

    def test_every_use_read_from_exports(self):
        palette = {"name": "palette", "file": "palette.json", "format": "JSON", "schema": "soils.palette/1",
                   "inputs": ["ssurgo", "naip"], "licence": "public-domain", "base": False}
        naip = {"name": "naip", "licence": "public-domain", "republish": "yes", "credit": "USDA NAIP"}
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo", "osm"]), palette], [SSURGO, OSM, naip])
        g = {"res": 10, "west": 495920, "north": 4855750, "width": 8967, "height": 9494}
        cover = tif_layer("crop_cover", ["csb"], g)
        folder = export(self.archive, "farm", files=())
        shutil.copy(os.path.join(FIXTURES, "squares.fgb"), os.path.join(folder, "fields.fgb"))
        grid_tiff(os.path.join(folder, "crop_cover.tif"), g, cover["bands"], data=False)
        fields = fgb_layer("fields", ["csb"], fields={"id": "int", "ground_type": "int", "misc": "string"})
        m = M.write(folder, "farm", [CSB], [fields, cover])
        # the ground reads fields' 'bearing': make the test's copy say it has one (headers aren't re-read here)
        m.data["layers"][0]["fields"] = {"id": "int", "bearing": "double"}
        write_export(self.archive, "water", [fgb_layer("mask", ["nhd", "osm"])], [NHD, OSM])
        write_mask(self.archive)
        write_classes(self.archive)
        found = I.exports(self.archive)
        found["farm"] = m
        plan = I.resolve(found)
        self.assertEqual(plan.status, "painted")
        self.assertFalse(any(c.fallback for c in plan.choices))
        self.assertEqual(plan.raw_names, [])
        self.assertEqual(plan.republish, "yes")
        for credit in ("USDA NAIP", "U.S. Geological Survey, National Hydrography Dataset", SSURGO["credit"]):
            self.assertIn(credit, plan.credits)
        self.assertEqual(len(plan.credits), len(set(plan.credits)))


if __name__ == "__main__":
    unittest.main()
