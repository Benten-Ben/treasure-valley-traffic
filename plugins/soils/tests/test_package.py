"""Reading a prepared soil survey and deriving the soils rows (standard library only), on the synthetic survey.

Run: python3 -m unittest plugins.soils.tests.test_package
"""

import contextlib
import copy
import io
import json
import os
import tempfile
import unittest

from plugins.soils.ingest import load, package
from plugins.soils.tests import synthetic


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f)


class Prepared(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        synthetic.write_prepared(self.dir)

    def tearDown(self):
        self.tmp.cleanup()


class ReadTest(Prepared):
    def test_reads_areas_tables_and_polygons(self):
        pkg = package.read(self.dir)
        self.assertEqual(sorted(pkg.areas), ["ZZ001", "ZZ002"])
        self.assertEqual(pkg.areas["ZZ001"]["saverest"], "2026-08-31T21:54:36")
        self.assertEqual([r["mukey"] for r in pkg.table("mapunit")], ["1001", "1002", "1003", "2001", "2002", "2003"])
        polys = list(pkg.polygons())
        self.assertEqual([p[0] for p in polys], ["ZZ001:0", "ZZ001:1", "ZZ001:2", "ZZ002:0", "ZZ002:1", "ZZ002:2"])
        self.assertEqual(json.loads(polys[2][3])["type"], "MultiPolygon")
        self.assertEqual([p[0] for p in pkg.polygons({"ZZ002"})], ["ZZ002:0", "ZZ002:1", "ZZ002:2"])
        bounds = list(pkg.survey_areas())
        self.assertEqual([b[0] for b in bounds], ["ZZ001", "ZZ002", "ZZ002"])           # ZZ002 in two pieces
        self.assertEqual(json.loads(bounds[0][1])["type"], "MultiPolygon")
        self.assertEqual([b[0] for b in pkg.survey_areas({"ZZ001"})], ["ZZ001"])

    def test_refuses_a_changed_file(self):
        with open(os.path.join(self.dir, "tabular", "component.csv"), "a", encoding="utf-8") as f:
            f.write("ZZ001,x\n")
        with self.assertRaisesRegex(package.PackageError, "component.csv: sha256"):
            package.read(self.dir)
        package.read(self.dir, check=False)          # unchecked, it opens

    def test_refuses_a_missing_column_another_box_or_format(self):
        meta_path = os.path.join(self.dir, package.MANIFEST)
        meta = read_json(meta_path)
        for change, message in (({"format": "tvt-soils-prepared/1"}, "format.*prepare.py again"),
                                ({"box": [-117, 43, -116, 44]}, "box"), ({"areas": []}, "no survey areas")):
            with self.subTest(message):
                write_json(meta_path, dict(meta, **change))
                with self.assertRaisesRegex(package.PackageError, message):
                    package.read(self.dir)
        path = os.path.join(self.dir, "tabular", "chorizon.csv")
        with open(path, encoding="utf-8") as f:
            text = f.read().replace("ph1to1h2o_r", "ph_other", 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        meta["files"]["tabular/chorizon.csv"]["sha256"] = package.sha256(path)
        write_json(meta_path, meta)
        with self.assertRaisesRegex(package.PackageError, "chorizon.csv: no column.*ph1to1h2o_r"):
            package.read(self.dir)

    def test_needs_the_survey_areas(self):
        meta_path = os.path.join(self.dir, package.MANIFEST)
        meta = read_json(meta_path)
        del meta["files"][package.SURVEY_AREAS]
        write_json(meta_path, meta)
        with self.assertRaisesRegex(package.PackageError, "lists no survey_areas.geojsonl"):
            package.read(self.dir)

    def test_no_manifest(self):
        os.remove(os.path.join(self.dir, package.MANIFEST))
        with self.assertRaisesRegex(package.PackageError, "prepare.py first"):
            package.read(self.dir)


class DeriveTest(Prepared):
    def setUp(self):
        super().setUp()
        d = package.derive(package.read(self.dir), ["ZZ001", "ZZ002"])
        self.d = d
        self.mu = {m["mukey"]: m for m in d.map_units}
        self.co = {c["cokey"]: c for c in d.components}
        self.hz = {h["chkey"]: h for h in d.horizons}

    def test_a_consociation_with_a_deep_duripan(self):
        m = self.mu["1001"]
        self.assertEqual((m["dom_cokey"], m["ground_type"]), ("1001-1", "purdam:silt-loam"))
        self.assertEqual((m["restr_kind"], m["restr_top_cm"], m["restr_hard"]), ("Duripan", 61, "Indurated"))
        self.assertEqual((m["c_restr"], m["pat"]), (2, "none"))           # 50-100 cm, below the pattern's 50 cm
        self.assertEqual((m["c_drain"], m["c_aws"], m["c_farm"], m["farm_cond"], m["c_hsg"], m["hsg_dual"]),
                         (1, 2, 2, "irrigated", 2, False))
        self.assertEqual((m["aws0100wta"], m["iccdcd"], m["pondfreqprs"]), (11.8, "3", 0))

    def test_ties_go_to_the_major_component_and_o_horizons_are_skipped(self):
        m = self.mu["1002"]
        self.assertEqual(m["dom_cokey"], "1002-2")                       # Chilcott, major, beats Elijah's lower key
        self.assertEqual(m["ground_type"], "chilcott:gravelly-silt-loam")
        g = self.d.ground_types["chilcott:gravelly-silt-loam"]
        self.assertEqual((g["series"], g["texture"], g["texcl"], g["modifier"], g["misc"]),
                         ("Chilcott", "Gravelly silt loam", "Silt loam", "Gravelly", None))
        # The shallowest restriction of any kind, but the depth code and pattern from the bedrock.
        self.assertEqual((m["restr_kind"], m["restr_top_cm"]), ("Abrupt textural change", 8))
        self.assertEqual((m["c_restr"], m["pat"]), (4, "bedrock"))
        self.assertEqual((m["c_drain"], m["c_aws"], m["c_farm"], m["farm_cond"], m["c_hsg"], m["hsg_dual"]),
                         (3, 0, 1, "reclaimed", 2, True))
        self.assertEqual(self.co["1002-2"]["surf_frag_cover_pct"], 3.5)

    def test_a_miscellaneous_area_is_unrated(self):
        m = self.mu["1003"]
        self.assertEqual(m["ground_type"], "water")
        self.assertEqual(self.d.ground_types["water"]["misc"], "water")
        self.assertIsNone(self.d.ground_types["water"]["texture"])
        for k in ("c_restr", "pat", "c_drain", "c_aws", "c_hsg", "hsg_dual", "farm_cond", "restr_kind"):
            self.assertIsNone(m[k], k)
        self.assertEqual(m["c_farm"], 0)

    def test_the_same_type_across_areas_and_no_restriction(self):
        m = self.mu["2001"]
        self.assertEqual(m["ground_type"], "purdam:silt-loam")
        self.assertEqual((m["c_restr"], m["pat"], m["c_drain"], m["c_aws"], m["c_farm"], m["c_hsg"]),
                         (0, "none", 0, 4, None, 0))
        self.assertEqual(sorted(self.d.ground_types),
                         ["chilcott:gravelly-silt-loam", "notcom", "purdam:silt-loam", "rock-outcrop", "water"])

    def test_notcom_is_no_survey_not_a_soil(self):
        m = self.mu["2002"]
        self.assertEqual((m["ground_type"], m["dom_cokey"]), ("notcom", "2002-1"))
        self.assertEqual(self.d.ground_types["notcom"], {"id": "notcom", "series": "NOTCOM", "texture": None,
                                                         "texcl": None, "modifier": None, "misc": "nodata"})
        for k in ("c_restr", "pat", "c_drain", "c_aws", "c_farm", "farm_cond", "c_hsg", "hsg_dual", "restr_kind"):
            self.assertIsNone(m[k], k)

    def test_notcom_by_its_symbol_alone(self):
        tables = copy.deepcopy(synthetic.TABLES)
        tables["component"] = [c for c in tables["component"] if c["mukey"] != "2002"]
        tables["mapunit"] = [dict(r, farmlndcl="Not prime farmland") if r["mukey"] == "2002" else r
                             for r in tables["mapunit"]]
        with tempfile.TemporaryDirectory() as d:
            synthetic.write_prepared(d, tables=tables)
            mu = {m["mukey"]: m for m in package.derive(package.read(d), ["ZZ002"]).map_units}
        self.assertEqual((mu["2002"]["ground_type"], mu["2002"]["dom_cokey"], mu["2002"]["c_farm"]),
                         ("notcom", None, None))

    def test_a_miscellaneous_area_is_one_type_whatever_its_texture(self):
        m = self.mu["2003"]
        self.assertEqual(m["ground_type"], "rock-outcrop")                 # not 'rock-outcrop:bedrock'
        g = self.d.ground_types["rock-outcrop"]
        self.assertEqual((g["misc"], g["texture"], g["texcl"], g["modifier"]), ("rock", None, None, None))
        self.assertEqual((m["c_restr"], m["pat"], m["c_hsg"]), (4, "bedrock", 3))   # rated: bedrock at 0 cm
        self.assertEqual(self.hz["h10"]["texture"], "Bedrock")                # the horizon keeps its texture

    def test_component_card_fields(self):
        c = self.co["1001-1"]
        self.assertEqual(c["landform"], "Stream terrace")                # the representative landform
        self.assertEqual(c["pm_kind"], "Loess; Alluvium")                  # by pmorder, from the rv group
        self.assertEqual((c["eco_id"], c["eco_name"]), ("R011XY001ID", "Loamy 8-12 PZ"))   # NRCS's site first
        self.assertEqual(c["crop_yields"], [{"crop": "Alfalfa hay", "units": "Tons", "irr": 6.0, "nonirr": None},
                                            {"crop": "Wheat", "units": "Bu", "irr": 100.0, "nonirr": None}])
        self.assertEqual(c["restrictions"], [{"kind": "Duripan", "top_cm": 61, "bottom_cm": 150, "hard": "Indurated"}])
        self.assertEqual((c["majcomp"], c["comppct_r"], c["irrcapcl"], c["ffd_r"], c["albedodry_r"]),
                         (True, 90, 3, 140, 0.23))
        self.assertIs(self.co["1001-2"]["majcomp"], False)
        self.assertIsNone(self.co["1003-1"]["surf_frag_cover_pct"])        # no rows: unknown, not zero

    def test_horizons(self):
        self.assertEqual((self.hz["h5"]["texture"], self.hz["h5"]["texcl"]), ("Gravelly silt loam", "Silt loam"))
        self.assertEqual((self.hz["h3"]["texture"], self.hz["h3"]["texcl"]), ("Cemented material", "Cemented material"))
        self.assertEqual((self.hz["h1"]["top_cm"], self.hz["h1"]["bottom_cm"], self.hz["h1"]["kwfact"]), (0, 25, 0.49))
        self.assertNotIn("h7", self.hz)                                   # map unit 1004 was left out
        self.assertEqual(len(self.d.horizons), 9)

    def test_one_area_only(self):
        d = package.derive(package.read(self.dir), ["ZZ002"])
        self.assertEqual([m["mukey"] for m in d.map_units], ["2001", "2002", "2003"])
        self.assertEqual(sorted(c["cokey"] for c in d.components), ["2001-1", "2001-2", "2002-1", "2003-1"])


class RulesTest(unittest.TestCase):
    def test_depth_codes(self):
        self.assertEqual([package.depth_code(x) for x in (None, 0, 24, 25, 49, 50, 99, 100, 149)],
                         [0, 4, 4, 3, 3, 2, 2, 1, 1])

    def test_aws_and_drainage(self):
        self.assertEqual([package.aws_code(x) for x in (None, 0, 4.99, 5, 11.8, 15, 19.9, 20, 31)],
                         [None, 0, 0, 1, 2, 3, 3, 4, 4])
        self.assertEqual([package.drainage_code(x) for x in ("Excessively drained", "Well drained",
                                                             "Moderately well drained", "Somewhat poorly drained",
                                                             "Very poorly drained", "", None)],
                         [0, 1, 2, 3, 4, None, None])

    def test_farmland(self):
        cases = {
            "Not prime farmland": (0, None),
            "All areas are prime farmland": (2, None),
            "Prime farmland if irrigated": (2, "irrigated"),
            "Prime farmland if irrigated and drained": (2, "drained"),
            "Prime farmland if irrigated and reclaimed of excess salts and sodium": (2, "reclaimed"),
            "Prime farmland if drained and either protected from flooding or not frequently flooded during the "
            "growing season": (2, "drained"),
            "Prime farmland if protected from flooding or not frequently flooded during the growing season":
                (2, "protected"),
            "Prime farmland if subsoiled, completely removing the root inhibiting soil layer": (2, "other"),
            "Farmland of statewide importance": (1, None),
            "Farmland of statewide importance, if irrigated": (1, "irrigated"),
            "Farmland of local importance": (1, None),
            "Farmland of unique importance": (1, None),
            "": (None, None),
        }
        for value, expected in cases.items():
            with self.subTest(value):
                self.assertEqual(package.farm_code(value), expected)

    def test_hydrologic_groups(self):
        self.assertEqual([package.hsg_code(x) for x in ("A", "B", "C", "D", "A/D", "C/D", "", "X")],
                         [(0, False), (1, False), (2, False), (3, False), (0, True), (2, True), (None, None),
                          (None, None)])

    def test_ground_type_ids_and_misc(self):
        self.assertEqual(package.ground_type_id("Purdam", "Silt loam"), "purdam:silt-loam")
        self.assertEqual(package.ground_type_id("Xeric Torriorthents", "Very gravelly loam"),
                         "xeric-torriorthents:very-gravelly-loam")
        self.assertEqual(package.ground_type_id("Urban land", None), "urban-land")
        self.assertIsNone(package.ground_type_id("", "Loam"))
        self.assertEqual([package.misc_kind(n, "Miscellaneous area") for n in
                          ("Water", "Urban land", "Rock outcrop", "Badland", "Rubble land", "Pits, gravel", "Dumps",
                           "Pits and Dumps", "Riverwash")],
                         ["water", "urban", "rock", "badland", "rubble", "pits", "other", "pits", "other"])
        self.assertIsNone(package.misc_kind("Purdam", "Series"))
        self.assertIsNone(package.misc_kind("Xeric Torriorthents", "Taxon above family"))
        self.assertEqual([package.misc_kind("NOTCOM", k) for k in ("", None, "Miscellaneous area")], ["nodata"] * 3)
        self.assertTrue(package.is_notcom("Purdam", " notcom "))
        self.assertFalse(package.is_notcom(None, "", "Notcomish"))

    def test_saverest(self):
        self.assertEqual(package.saverest("08/31/2026 21:54:36"), "2026-08-31T21:54:36")


class PlanAndCommandTest(Prepared):
    def test_plan_skips_what_is_loaded(self):
        pkg = package.read(self.dir)
        self.assertEqual(load.plan(pkg, {}), (["ZZ001", "ZZ002"], []))
        loaded = {"ZZ001": "2026-08-31T21:54:36", "ZZ002": "2025-09-01T00:00:00"}
        self.assertEqual(load.plan(pkg, loaded), (["ZZ002"], ["ZZ001"]))
        self.assertEqual(load.plan(pkg, loaded, force=True), (["ZZ001", "ZZ002"], []))
        self.assertEqual(load.plan(pkg, {}, areas=["ZZ002"]), (["ZZ002"], []))
        with self.assertRaisesRegex(package.PackageError, "no survey area ZZ009"):
            load.plan(pkg, {}, areas=["ZZ009"])

    def test_dry_run(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(load.main(["--from", self.dir, "--dry-run"]), 0)
        self.assertIn("ZZ001, ZZ002: 6 map units, 9 components, 9 horizons, 6 polygons, 5 ground types", out.getvalue())

    def test_a_bad_package_is_an_error_not_a_traceback(self):
        os.remove(os.path.join(self.dir, package.MANIFEST))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(load.main(["--from", self.dir, "--dry-run"]), 1)
        self.assertIn("soils-load:", err.getvalue())


if __name__ == "__main__":
    unittest.main()
