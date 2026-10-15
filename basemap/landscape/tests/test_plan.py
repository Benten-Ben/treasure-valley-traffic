"""What the bake reads and promises (plan.py): standard library only.

Exports are synthetic: copies of the ground's squares.fgb fixture (fields id, ground_type and misc, written by
PostGIS's ST_AsFlatGeobuf) with real manifests. The sources named are checked against the repository's real
plugin.json files, as in the ground's tests.
"""

import json
import os
import re
import shutil
import tempfile
import unittest

from basemap.ground import grid as G, manifest as M
from basemap.ground.tests.test_inputs import R2R, fgb_layer, write_export, write_mask
from basemap.ground.tests.test_manifest import ACHD, OSM
from basemap.landscape import plan as P

NHD = {"name": "nhd", "licence": "public-domain", "republish": "yes",
       "credit": "U.S. Geological Survey, National Hydrography Dataset"}
PUBLIC = {"water": "public", "roads": "public", "trails": "public", "trees": "public", "secret": "private"}


def base_layer(name, inputs, **kw):
    return fgb_layer(name, inputs, base=True, **kw)


def write_water(archive, build="20261012T031500Z", **kw):
    return write_export(archive, "water", [base_layer("reaches", ["osm", "nhd"], **kw),
                                           fgb_layer("mask", ["nhd"])], [OSM, NHD], build)


def write_roads(archive, build="20261013T031500Z"):
    return write_export(archive, "roads", [base_layer("surfaces", ["osm", "achd-roads"], minzoom=14)],
                        [OSM, ACHD], build)


def baked(plan, sizes=None):
    """A valid entry for a plan, as if baked (no file)."""
    b = P.measure_budget(sizes or {}, plan.roads)
    return P.baked_entry(plan, P.digest(plan, "GDAL 3.13.3"), b, "GDAL 3.13.3")


class SpecTest(unittest.TestCase):
    def test_the_contract(self):
        self.assertEqual((P.MINZOOM, P.MAXZOOM), (8, 16))
        self.assertEqual(P.ENTRY, "landscape")
        self.assertEqual(P.PROMOTE_ID, "id")
        self.assertEqual(P.KEEP, 2)
        self.assertEqual((P.BUDGET["zoom"], P.BUDGET["box"], P.BUDGET["maxBytes"]), (16, "downtown", 60000))
        self.assertEqual(P.file_name("0123456789abcdef" * 4), "landscape-0123456789ab.pmtiles")
        self.assertTrue(P.FILE_RE.match("landscape-0123456789ab.pmtiles"))
        self.assertFalse(P.FILE_RE.match("landscape-0123456789ab.pmtiles.part"))

    def test_budget_tiles_cover_downtown(self):
        t = P.budget_tiles()
        self.assertEqual(len(t), 30)
        self.assertTrue(all(z == 16 for z, _, _ in t))
        w, s, e, n = G.lonlat_of(G.box("downtown").utm)
        xs = {x for _, x, _ in t}
        ys = {y for _, _, y in t}
        n16 = 2 ** 16
        self.assertLessEqual(min(xs), (w + 180) / 360 * n16)
        self.assertGreaterEqual(max(xs) + 1, (e + 180) / 360 * n16)
        self.assertEqual(len(xs) * len(ys), 30)

    def test_measure_budget(self):
        sizes = {(16, 11613, 23923): 1000, (16, 11614, 23923): 70000, (16, 11615, 23924): 61000}
        b = P.measure_budget(sizes, roads=True)
        self.assertEqual(b, {"zoom": 16, "box": "downtown", "maxBytes": 60000, "tiles": 3, "largest": 70000,
                             "at": "16/11614/23923", "roads": True})
        self.assertEqual(P.over_budget(sizes), [((16, 11614, 23923), 70000), ((16, 11615, 23924), 61000)])
        self.assertEqual(P.measure_budget({}, roads=False)["largest"], 0)
        self.assertEqual(P.over_budget({(16, 1, 1): 60000}), [])


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.archive = os.path.join(self.dir, "archive")
        os.makedirs(self.archive)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def plan(self, visibility=PUBLIC, **kw):
        return P.resolve(P.exports(self.archive), visibility=visibility, **kw)

    def test_missing_archive(self):
        with self.assertRaisesRegex(P.BakeError, "no archive folder"):
            P.exports(os.path.join(self.dir, "nowhere"))
        with self.assertRaisesRegex(P.BakeError, "no archive folder"):
            P.exports(None)

    def test_nothing_exported(self):
        p = self.plan()
        self.assertEqual((p.status, p.reason), ("empty", "no plugin exports a base layer yet"))
        write_export(self.archive, "trees", [fgb_layer("crowns", ["osm"])], [OSM])
        p = self.plan()
        self.assertEqual(p.status, "empty")
        self.assertEqual(p.skipped, [("trees", "trees@20261012T031500Z has no base layer")])

    def test_base_layers_become_source_layers(self):
        write_water(self.archive)
        write_roads(self.archive)
        p = self.plan()
        self.assertEqual(p.status, "baked")
        self.assertEqual([b.id for b in p.bases], ["roads.surfaces", "water.reaches"])
        self.assertEqual(p.refs, ["roads/surfaces@20261013T031500Z", "water/reaches@20261012T031500Z"])
        self.assertTrue(p.roads)
        roads, water = p.bases
        self.assertEqual((roads.minzoom, roads.maxzoom), (14, 16))
        self.assertEqual((water.minzoom, water.maxzoom), (8, 16))
        self.assertEqual(water.fields, {"id": "int", "ground_type": "int", "misc": "string"})

    def test_internal_input_makes_it_tailnet_only(self):
        write_water(self.archive)
        p = self.plan()
        self.assertEqual((p.republish, p.access, p.internal), ("yes", "public", []))
        self.assertEqual(p.licences, ["ODbL-1.0"])
        write_roads(self.archive)
        p = self.plan()
        self.assertEqual((p.republish, p.access), ("internal", "tailnet"))
        self.assertEqual(p.internal, [("roads.surfaces", ["© OpenStreetMap contributors", "ACHD"])])
        self.assertEqual(p.licences, ["ODbL-1.0"])
        self.assertEqual(p.credits, ["© OpenStreetMap contributors", "ACHD",
                                     "U.S. Geological Survey, National Hydrography Dataset"])

    def test_licences_strictest_first(self):
        write_export(self.archive, "water", [base_layer("reaches", ["nhd"]), base_layer("ditches", ["achd-roads"])],
                     [NHD, ACHD])
        self.assertEqual(self.plan().licences, ["none-stated", "public-domain"])

    def test_aggregates_and_private_and_unknown_are_refused(self):
        write_export(self.archive, "trails", [base_layer("paths", ["osm", "r2r"])], [OSM, R2R])
        with self.assertRaisesRegex(P.BakeError, "aggregates.*side tables"):
            self.plan()
        shutil.rmtree(os.path.join(self.archive, "trails"))
        write_export(self.archive, "secret", [base_layer("things", ["osm"])], [OSM])
        with self.assertRaisesRegex(P.BakeError, "private plugin"):
            self.plan()
        with self.assertRaisesRegex(P.BakeError, "no plugin.json names"):
            self.plan(visibility={})

    def test_a_never_source_is_refused_with_the_real_plugin_json(self):
        ecoli = {"name": "ecoli", "licence": "none-stated", "republish": "internal",
                 "credit": "City of Boise Parks and Recreation", "source": "water/boise_ecoli"}
        write_export(self.archive, "water", [base_layer("reaches", ["osm", "ecoli"])], [OSM, ecoli])
        with self.assertRaisesRegex(P.BakeError, "water/boise_ecoli, a City of Boise layer.*never in the base"):
            self.plan(visibility=None)

    def test_real_plugin_visibility(self):
        vis = P.plugin_visibility()
        self.assertEqual(vis["water"], "public")
        self.assertEqual(vis["roads"], "public")
        write_water(self.archive)
        self.assertEqual([b.id for b in self.plan(visibility=None).bases], ["water.reaches"])

    def test_products_are_never_read(self):
        write_mask(self.archive)                                  # the ground's mask v0
        os.makedirs(os.path.join(self.archive, "ground_classes", "export", "20261013T040000Z"))
        with open(os.path.join(self.archive, "ground_classes", "export", "20261013T040000Z", "manifest.json"),
                  "w") as f:
            f.write("{broken")                                    # the bake doesn't even open it
        self.assertEqual(P.exports(self.archive), {})

    def test_exports_without_a_base_layer_are_not_the_bakes(self):
        write_water(self.archive)
        # trees' export names a source no plugin.json here lists (a private plugin's, say): not read, so no matter.
        folder = os.path.join(self.archive, "trees", "export", "20261012T031500Z")
        write_export(self.archive, "trees", [fgb_layer("crowns", ["osm"])], [OSM])
        with open(os.path.join(folder, "manifest.json"), encoding="utf-8") as f:
            m = json.load(f)
        m["inputs"][0]["source"] = "city_trees/inventory"
        with open(os.path.join(folder, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(m, f)
        with self.assertRaises(M.ManifestError):
            M.read(folder)
        p = self.plan()
        self.assertEqual([b.id for b in p.bases], ["water.reaches"])
        self.assertEqual(p.skipped, [("trees", "trees@20261012T031500Z has no base layer")])
        # ... but a manifest that isn't plain is read in full, and refuses the bake.
        for broken in ("{not json", json.dumps(dict(m, layers=[dict(m["layers"][0], base="no")]))):
            with open(os.path.join(folder, "manifest.json"), "w", encoding="utf-8") as f:
                f.write(broken)
            with self.assertRaises(M.ManifestError):
                self.plan()

    def test_files_checked_only_for_base_layers(self):
        m = write_water(self.archive)
        with open(m.layer("mask").path, "ab") as f:               # a broken non-base file: not the bake's
            f.write(b"x")
        self.assertEqual([b.id for b in self.plan().bases], ["water.reaches"])
        with open(m.layer("reaches").path, "ab") as f:
            f.write(b"x")
        with self.assertRaisesRegex(M.ManifestError, "bytes"):
            self.plan()
        self.assertEqual(len(self.plan(verify=False).bases), 1)

    def test_a_broken_newest_manifest_refuses(self):
        write_water(self.archive)
        later = M.export_dir(self.archive, "water", "20261020T000000Z")
        os.makedirs(later)
        with open(os.path.join(later, "manifest.json"), "w") as f:
            json.dump({"contract": 1}, f)
        with self.assertRaises(M.ManifestError):
            self.plan()

    def test_zooms_clamp_to_the_bake(self):
        write_water(self.archive, minzoom=5, maxzoom=18)
        b = self.plan().bases[0]
        self.assertEqual((b.minzoom, b.maxzoom), (8, 16))
        shutil.rmtree(os.path.join(self.archive, "water"))
        write_water(self.archive, minzoom=17)
        b = self.plan().bases[0]
        self.assertEqual((b.minzoom, b.maxzoom), (16, 16))
        shutil.rmtree(os.path.join(self.archive, "water"))
        write_water(self.archive, maxzoom=6)
        with self.assertRaisesRegex(P.BakeError, "below the bake's first zoom"):
            self.plan()


class CheckBaseTest(unittest.TestCase):
    INPUTS = {"osm": OSM, "achd": dict(ACHD, name="achd"),
              "orgs": {"name": "orgs", "licence": "none-stated", "republish": "internal",
                       "credit": "Idaho Department of Water Resources", "source": "water/idwr_organizations"},
              "hazards": {"name": "hazards", "licence": "none-stated", "republish": "internal",
                          "credit": "Boise Fire Department and City of Boise", "source": "water/boise_river_hazards"},
              "things": {"name": "things", "licence": "none-stated", "republish": "internal", "credit": "Secret",
                         "source": "secret/things"},
              "elsewhere": {"name": "elsewhere", "licence": "none-stated", "republish": "internal",
                            "credit": "Someone", "source": "nowhere/things"}}

    def layer(self, **kw):
        spec = {"name": "reaches", "file": "r.fgb", "format": "FlatGeobuf", "crs": "EPSG:32611",
                "geometry": "LineString", "features": 1, "fields": {"id": "long", "kind": "string"}, "bytes": 1,
                "sha256": "0" * 64, "inputs": ["osm"], "licence": "ODbL-1.0", "republish": "yes",
                "credit": ["© OpenStreetMap contributors"], "base": True}
        spec.update(kw)
        return M.Layer("water", "20261012T031500Z", "/nowhere/r.fgb", spec)

    def test_fields(self):
        P.check_base(self.layer(), PUBLIC)
        P.check_base(self.layer(fields={"id": "int", "minzoom": "short", "w": "float", "ok": "bool"}), PUBLIC)
        with self.assertRaisesRegex(P.BakeError, "integer 'id'"):
            P.check_base(self.layer(fields={"id": "string"}), PUBLIC)
        with self.assertRaisesRegex(P.BakeError, "datetime"):
            P.check_base(self.layer(fields={"id": "int", "seen": "datetime"}), PUBLIC)
        with self.assertRaisesRegex(P.BakeError, "json"):
            P.check_base(self.layer(fields={"id": "int", "tags": "json"}), PUBLIC)
        with self.assertRaisesRegex(P.BakeError, "first zoom, so it must be an integer"):
            P.check_base(self.layer(fields={"id": "int", "minzoom": "double"}), PUBLIC)

    def test_republish(self):
        P.check_base(self.layer(republish="internal"), PUBLIC)
        for r in ("aggregates", "no"):
            with self.assertRaisesRegex(P.BakeError, "never in the base"):
                P.check_base(self.layer(republish=r), PUBLIC)

    def test_plugin_visibility(self):
        with self.assertRaisesRegex(P.BakeError, "water is a private plugin"):
            P.check_base(self.layer(), dict(PUBLIC, water="private"))
        with self.assertRaisesRegex(P.BakeError, "no plugin.json names plugin 'water'"):
            P.check_base(self.layer(), {})

    def test_inputs_sources(self):
        """C17's named sources never go in, whatever their republish; nor does a private plugin's source."""
        P.check_base(self.layer(inputs=["osm", "achd"], republish="internal"), PUBLIC, self.INPUTS)
        for name, msg in (("orgs", "water/idwr_organizations, IDWR's data .*never in the base \\(C17\\)"),
                          ("hazards", "water/boise_river_hazards, a City of Boise layer"),
                          ("things", "secret/things, a source of a private plugin"),
                          ("elsewhere", "nowhere/things, a source of 'nowhere', which no plugin.json names")):
            with self.subTest(name):
                with self.assertRaisesRegex(P.BakeError, msg):
                    P.check_base(self.layer(inputs=["osm", name], republish="internal"), PUBLIC, self.INPUTS)

    def test_never_covers_every_city_and_idwr_source(self):
        """Every plugin.json source credited to the City of Boise or IDWR matches a NEVER pattern, so a source added
        under another name can't slip into the base."""
        credited = re.compile(r"City of Boise|Boise Fire|Ridge to Rivers|IDWR|Idaho Department of Water Resources")
        sources = M.plugin_sources()
        named = sorted(k for k, e in sources.items() if credited.search(str(e.get("credit", ""))))
        self.assertIn("water/boise_ecoli", named)
        self.assertIn("trails/r2r_trails", named)
        self.assertEqual([k for k in named if not P.never(k)], [])
        self.assertIsNone(P.never("roads/achd_roads"))
        self.assertIsNone(P.never("roads/osm_valley"))
        self.assertEqual(P.never("water/idwr_season_of_use"), P.NEVER["*/idwr*"])


class PlanTest(unittest.TestCase):
    """Built and empty base layers, from layers made by hand."""

    def base(self, plugin, name, features, republish="yes", credit="© OpenStreetMap contributors", build=None):
        spec = {"name": name, "file": f"{name}.fgb", "format": "FlatGeobuf", "crs": "EPSG:32611",
                "geometry": "LineString", "features": features, "fields": {"id": "long"}, "bytes": 1,
                "sha256": "0" * 64, "inputs": ["osm"], "licence": "ODbL-1.0", "republish": republish,
                "credit": [credit], "base": True}
        b = build or "20261012T031500Z"
        return P.Base(M.Layer(plugin, b, f"/nowhere/{name}.fgb", spec))

    def test_empty_layers_are_read_but_not_built(self):
        plan = P.Plan(bases=[self.base("roads", "surfaces", 2), self.base("water", "reaches", 0, "internal", "IDWR")],
                      skipped=[("trails", "trails@20261012T031500Z has no base layer")])
        self.assertEqual(([b.id for b in plan.built], plan.empty, plan.ids), (["roads.surfaces"], ["water.reaches"],
                                                                              ["roads.surfaces"]))
        self.assertEqual(plan.refs, ["roads/surfaces@20261012T031500Z", "water/reaches@20261012T031500Z"])
        # Only built layers count towards who may see the file and its credits.
        self.assertEqual((plan.republish, plan.access, plan.credits), ("yes", "public",
                                                                      ["© OpenStreetMap contributors"]))
        e = baked(plan)
        P.check_entry(e, in_manifest=False)
        self.assertEqual((sorted(e["layers"]), e["empty"]), (["roads.surfaces"], ["water.reaches"]))
        self.assertEqual(e["inputs"], plan.refs)
        self.assertEqual(plan.why_not_built("water.reaches"), "water/reaches@20261012T031500Z is empty")
        self.assertEqual(plan.why_not_built("trails.paved"), "trails@20261012T031500Z has no base layer")
        self.assertEqual(plan.why_not_built("roads.markings"), "roads@20261012T031500Z has no base layer 'markings'")
        self.assertEqual(plan.why_not_built("farm.fields"), "there's no export of farm")

        none = P.Plan(bases=[self.base("water", "reaches", 0)])
        self.assertEqual((none.status, none.reason), ("empty", "every base layer is empty: water.reaches"))
        with self.assertRaises(ValueError):
            P.baked_entry(none, "0" * 64, P.measure_budget({}, False), "GDAL")
        # An entry may not list an empty layer, nor the same layer in both.
        with self.assertRaisesRegex(ValueError, "has no features"):
            P.check_entry(dict(e, layers={"roads.surfaces": dict(e["layers"]["roads.surfaces"], features=0)}),
                          in_manifest=False)
        for bad in (["roads.surfaces"], ["water.reaches", "water.reaches"], ["b.x", "a.x"], "water.reaches",
                    ["Water"]):
            with self.assertRaisesRegex(ValueError, "empty must list"):
                P.check_entry(dict(e, empty=bad), in_manifest=False)


class EntryTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.archive = os.path.join(self.dir, "archive")
        self.tiles = os.path.join(self.dir, "tiles")
        os.makedirs(self.archive)
        os.makedirs(self.tiles)
        with open(os.path.join(self.tiles, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"zoom": 10, "ground": {"status": "flat"}}, f)
        write_water(self.archive)
        write_roads(self.archive)
        self.p = P.resolve(P.exports(self.archive), visibility=PUBLIC)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_digest(self):
        a = P.digest(self.p, "GDAL 3.13.3")
        self.assertEqual(a, P.digest(self.p, "GDAL 3.13.3"))
        self.assertNotEqual(a, P.digest(self.p, "GDAL 3.14.0"))
        write_water(self.archive, build="20261014T000000Z")
        p2 = P.resolve(P.exports(self.archive), visibility=PUBLIC)
        self.assertNotEqual(a, P.digest(p2, "GDAL 3.13.3"))
        with self.assertRaises(ValueError):
            P.digest(P.Plan(), "GDAL 3.13.3")

    def test_baked_entry_checks(self):
        e = baked(self.p)
        P.check_entry(e, in_manifest=False)
        P.check_entry(dict(e, previous=None))
        P.check_entry(dict(e, previous="landscape-000000000000.pmtiles"))
        P.check_entry(dict(e, minzoom=14, maxzoom=16), in_manifest=False)   # a file whose first tiles are at z14
        self.assertEqual(e["access"], "tailnet")
        self.assertEqual(e["republish"], "internal")
        self.assertEqual(e["layers"]["roads.surfaces"]["minzoom"], 14)
        self.assertEqual(e["attribution"], "© OpenStreetMap contributors; ACHD; "
                                           "U.S. Geological Survey, National Hydrography Dataset")
        self.assertEqual(e["inputs"], self.p.refs)
        with self.assertRaisesRegex(ValueError, "exactly"):
            P.check_entry(e)                                     # a manifest entry names its previous file
        bad = [
            (dict(e, access="public"), "access must be 'tailnet'"),
            (dict(e, republish="yes"), "strictest"),
            (dict(e, file="landscape-ffffffffffff.pmtiles"), "digest"),
            (dict(e, attribution="© OpenStreetMap contributors"), "attribution lacks"),
            (dict(e, licences=["ODbL-1.0", "public-domain"]), "licences"),
            (dict(e, maxzoom=17), "zooms must lie"),
            (dict(e, minzoom=12, maxzoom=11), "zooms must lie"),
            (dict(e, promoteId="fid"), "spec"),
            (dict(e, budget=dict(e["budget"], largest=60001)), "budget"),
            (dict(e, layers={}), "at least one layer"),
            (dict(e, layers={"water.other": e["layers"]["water.reaches"]}), "isn't named"),
            (dict(e, layers=dict(e["layers"], **{"water.reaches": dict(e["layers"]["water.reaches"],
                                                                       republish="aggregates")})), "never baked"),
            (dict(e, layers="nope"), "at least one layer"),
            (dict(e, layers={"water.reaches": {"plugin": "water"}}), "exactly"),
        ]
        for entry, msg in bad:
            with self.assertRaisesRegex(ValueError, msg):
                P.check_entry(entry, in_manifest=False)
        with self.assertRaisesRegex(ValueError, "another landscape file"):
            P.check_entry(dict(e, previous=e["file"]))

    def test_empty_entry(self):
        e = P.empty_entry("no plugin exports a base layer yet")
        P.check_entry(e)
        P.check_entry(P.empty_entry("x", previous="landscape-000000000000.pmtiles"))
        with self.assertRaises(ValueError):
            P.empty_entry(" ")
        with self.assertRaisesRegex(ValueError, "previous"):
            P.check_entry(dict(e, previous="valley.pmtiles"))
        with self.assertRaisesRegex(ValueError, "status"):
            P.check_entry({"status": "flat"})

    def test_update_manifest_keeps_the_rest(self):
        e = dict(baked(self.p), previous=None)
        P.update_manifest(self.tiles, e)
        with open(os.path.join(self.tiles, "manifest.json"), encoding="utf-8") as f:
            m = json.load(f)
        self.assertEqual(m["zoom"], 10)
        self.assertEqual(m["ground"], {"status": "flat"})
        self.assertEqual(m["landscape"], e)
        self.assertEqual(P.current(self.tiles), e)
        self.assertEqual(sorted(f for f in os.listdir(self.tiles) if f.startswith(".manifest-")), [])
        with self.assertRaises(ValueError):
            P.update_manifest(self.tiles, dict(e, access="public"))
        self.assertEqual(P.current(self.tiles), e)
        with self.assertRaisesRegex(P.BakeError, "build the basemap first"):
            P.current(self.dir)

    def test_prune_keeps_the_last_two(self):
        names = [f"landscape-{i:012x}.pmtiles" for i in range(4)]
        for n in names + [".landscape-000000000009.pmtiles.12.part", "valley.pmtiles", "ground-0123.pmtiles"]:
            open(os.path.join(self.tiles, n), "w").close()
        gone = P.prune(self.tiles, {"file": names[3], "previous": names[1]})
        self.assertEqual(gone, sorted([names[0], names[2], ".landscape-000000000009.pmtiles.12.part"]))
        self.assertEqual(P.files(self.tiles), [names[1], names[3]])
        self.assertTrue(os.path.exists(os.path.join(self.tiles, "valley.pmtiles")))
        P.prune(self.tiles, {"status": "empty", "previous": None})
        self.assertEqual(P.files(self.tiles), [])


if __name__ == "__main__":
    unittest.main()
