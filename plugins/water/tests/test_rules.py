"""The water network's drawing rules (plugins/water/ingest/rules.py) and the build's pure steps (canal heads, canal
kinds, gauge names). Standard library only.

Run: python3 -m unittest discover -s plugins -t .
"""

import unittest

from plugins.water.ingest import build, rules


class KindTest(unittest.TestCase):
    def test_canal_kinds_by_name(self):
        self.assertEqual(rules.canal_kind_by_name("11.5 Lateral"), "lateral")
        self.assertEqual(rules.canal_kind_by_name("South Slough"), "drain")
        self.assertEqual(rules.canal_kind_by_name("Mason Drain"), "drain")
        self.assertEqual(rules.canal_kind_by_name("Ridenbaugh Canal"), "canal")
        self.assertEqual(rules.canal_kind_by_name("Middleton Mill Ditch"), "ditch")
        self.assertEqual(rules.canal_kind_by_name(None), "ditch")
        self.assertEqual(rules.canal_kind_by_name("Something", default=None), None)

    def test_osm_and_nhd_kinds(self):
        self.assertEqual(rules.osm_kind("canal", "Phyllis Canal"), "canal")
        self.assertEqual(rules.osm_kind("canal", "Wilson Lateral"), "lateral")
        self.assertEqual(rules.osm_kind("canal", None, "Field Supply"), "ditch")
        self.assertEqual(rules.osm_kind("canal", None, "Drain"), "drain")
        self.assertEqual(rules.osm_kind("canal", "Phyllis Canal", "Drain"), "canal")     # a name wins
        self.assertEqual(rules.osm_kind("stream", "New York Canal"), "canal")             # the name says canal
        self.assertEqual(rules.osm_kind("stream", "Fivemile Creek"), "stream")
        self.assertEqual(rules.osm_kind("river", "Boise River"), "river")
        self.assertEqual(rules.nhd_kind("stream_river", "Boise River", 7), "river")
        self.assertEqual(rules.nhd_kind("stream_river", None, 8), "river")
        self.assertEqual(rules.nhd_kind("stream_river", "Fivemile Creek", 3), "stream")
        self.assertEqual(rules.nhd_kind("canal_ditch", "A Lateral", None), "lateral")
        self.assertEqual(rules.nhd_kind("pipeline", None, None), "ditch")

    def test_name_key(self):
        self.assertEqual(rules.name_key("A line Canal"), rules.name_key("A Line  Canal"))
        self.assertEqual(rules.name_key("MIddleton Mill Ditch"), "middleton mill ditch")
        self.assertEqual(rules.name_key("300 \"Bolton\" Lateral"), "300 bolton lateral")
        self.assertIsNone(rules.name_key("  "))
        self.assertIsNone(rules.name_key(None))

    def test_placeholders_are_no_name(self):
        for name in ("Unnamed Drain", "Unnamed Supply", "UNNAMED LATERAL", " Unnamed Creek ", "Unnamed", "Field Supply",
                     "Pump Lifter", "Private Drain", "Drain", "", "  ", None):
            self.assertIsNone(rules.real_name(name), name)
        for name in ("LATERAL 34", "Unnamedville Canal", "Supply Ditch", "Field Supply Lateral", "Drain 5"):
            self.assertEqual(rules.real_name(name), name)

    def test_flow(self):
        self.assertEqual(rules.flow(True, "Perennial"), "intermittent")      # OSM's tag first
        self.assertEqual(rules.flow(False, "Intermittent"), "perennial")
        self.assertEqual(rules.flow(None, "Intermittent"), "intermittent")
        self.assertEqual(rules.flow(None, "Ephemeral"), "ephemeral")
        self.assertEqual(rules.flow(None, None), "unknown")


class WidthTest(unittest.TestCase):
    def test_streams_by_order(self):
        self.assertEqual(rules.width("stream", order=1), (1.0, "order"))
        self.assertEqual(rules.width("stream", order=5), (6.0, "order"))
        self.assertEqual(rules.width("river", order=9), (14.0, "order"))
        self.assertEqual(rules.width("stream", order=3, intermittent=True), (1.25, "order"))
        self.assertEqual(rules.width("stream", order=1, intermittent=True), (0.75, "order"))   # the floor
        self.assertEqual(rules.width("stream"), (1.5, "kind"))
        self.assertEqual(rules.width("river"), (14.0, "kind"))

    def test_canals_by_kind(self):
        self.assertEqual(rules.width("canal", main=True), (8.0, "kind"))
        self.assertEqual(rules.width("canal"), (5.0, "kind"))
        self.assertEqual(rules.width("canal", named=False), (1.5, "kind"))
        self.assertEqual(rules.width("lateral"), (2.5, "kind"))
        self.assertEqual(rules.width("ditch"), (1.5, "kind"))
        self.assertEqual(rules.width("drain", named=False), (3.0, "kind"))

    def test_osm_width_tag_overrides_within_its_range(self):
        self.assertEqual(rules.width("canal", osm_width=12.0), (12.0, "osm_tag"))
        self.assertEqual(rules.width("stream", order=2, osm_width=0.5), (0.5, "osm_tag"))
        self.assertEqual(rules.width("canal", osm_width=120.0), (5.0, "kind"))           # out of range: ignored
        self.assertEqual(rules.width("ditch", osm_width=0.2), (1.5, "kind"))


class ZoomTest(unittest.TestCase):
    def test_streams(self):
        z = rules.reach_minzoom
        self.assertEqual(z("stream", visibility=1000000, has_nhd=True), 8)
        self.assertEqual(z("stream", visibility=500000, has_nhd=True), 9)
        self.assertEqual(z("stream", visibility=100000, has_nhd=True), 11)
        self.assertEqual(z("stream", visibility=24000, has_nhd=True), 13)
        self.assertEqual(z("stream", visibility=0, has_nhd=True), 13)
        self.assertEqual(z("stream", named=True), 12)                          # OSM only
        self.assertEqual(z("stream", named=False), 13)
        self.assertEqual(z("stream", intermittent=True, order=3, visibility=5000000, has_nhd=True), 12)
        self.assertEqual(z("stream", intermittent=True, order=2), 13)

    def test_rivers_by_z9(self):
        self.assertEqual(rules.reach_minzoom("river", visibility=5000000, has_nhd=True), 8)
        self.assertEqual(rules.reach_minzoom("river", visibility=24000, has_nhd=True), 9)
        self.assertEqual(rules.reach_minzoom("river"), 9)

    def test_canals(self):
        z = rules.reach_minzoom
        self.assertEqual(z("canal", main=True, named=True), 10)
        self.assertEqual(z("canal", named=True), 11)
        self.assertEqual(z("lateral", named=True), 12)
        self.assertEqual(z("drain"), 12)
        self.assertEqual(z("ditch", named=True), 13)
        self.assertEqual(z("canal", named=False), 13)
        self.assertEqual(z("lateral", named=True, nhd_only=True), 13)           # NHD-only: one zoom later
        self.assertEqual(z("ditch", nhd_only=True), 14)
        self.assertEqual(z("canal", main=True, named=True, piped=True), 16)      # piped: z16 only

    def test_bodies_and_structures(self):
        self.assertEqual(rules.body_minzoom("reservoir", 28e6), 8)
        self.assertEqual(rules.body_minzoom("pond", 2e5), 10)
        self.assertEqual(rules.body_minzoom("pond", 1.5e4), 11)
        self.assertEqual(rules.body_minzoom("pond", 900), 13)
        self.assertEqual(rules.body_minzoom("pool", 1e5), 15)
        self.assertEqual(rules.body_minzoom("wetland", 1e6), 14)
        self.assertEqual(rules.body_minzoom("river", 10), 8)
        self.assertEqual(rules.structure_minzoom("dam", named=True, on_river=True), 11)
        self.assertEqual(rules.structure_minzoom("dam", named=True), 14)
        self.assertEqual(rules.structure_minzoom("spring"), 15)
        self.assertEqual(rules.structure_minzoom("gauge"), 10)

    def test_never_past_the_bake(self):
        for kind in ("river", "stream", "canal", "lateral", "ditch", "drain"):
            self.assertLessEqual(rules.reach_minzoom(kind, nhd_only=True, piped=True), rules.MAX_Z)
            self.assertLessEqual(rules.reach_minzoom(kind, nhd_only=True), rules.MAX_Z)


class ReachRulesTest(unittest.TestCase):
    def row(self, **kw):
        base = {"geometry_from": "osm", "src_kind": "canal", "name": "Test Canal", "osm_intermittent": None,
                "piped": False, "osm_width": None, "nhd_class": None, "nhd_category": None, "streamorder": None,
                "visibilityfilter": None, "hs_type": None, "canal_id": 7}
        base.update(kw)
        return base

    def test_main_canal(self):
        r = build.reach_rules(self.row(), {7})
        self.assertEqual((r["kind"], r["width_m"], r["minzoom"], r["name_key"]), ("canal", 8.0, 10, "test canal"))
        r = build.reach_rules(self.row(), set())
        self.assertEqual((r["width_m"], r["minzoom"]), (5.0, 11))

    def test_nhd_only_lateral_named_by_hydroshare_type(self):
        r = build.reach_rules(self.row(geometry_from="nhd", src_kind=None, name=None, nhd_class="canal_ditch",
                                       hs_type="Lateral", canal_id=None), set())
        self.assertEqual((r["kind"], r["width_m"], r["minzoom"]), ("lateral", 2.5, 13))

    def test_a_placeholder_neither_names_nor_kinds(self):
        # OSM's unnamed canal with HydroShare's 'Unnamed Supply' (a field supply): an unnamed ditch, kind from its type.
        r = build.reach_rules(self.row(name="Unnamed Supply", hs_type="Field Supply", canal_id=None), set())
        self.assertEqual((r["kind"], r["width_m"], r["minzoom"], r["name_key"], r["kind_from_hydroshare"]),
                         ("ditch", 1.5, 13, None, True))
        r = build.reach_rules(self.row(src_kind="stream", name="Unnamed Drain", hs_type="Drain", canal_id=None), set())
        self.assertEqual((r["kind"], r["kind_from_hydroshare"]), ("stream", False))
        r = build.reach_rules(self.row(), set())
        self.assertFalse(r["kind_from_hydroshare"])

    def test_intermittent_wash(self):
        r = build.reach_rules(self.row(geometry_from="nhd", src_kind=None, name=None, nhd_class="stream_river",
                                       nhd_category="Intermittent", streamorder=1, visibilityfilter=5000000,
                                       canal_id=None), set())
        self.assertEqual((r["kind"], r["flow"], r["intermittent"], r["width_m"], r["minzoom"]),
                         ("stream", "intermittent", True, 0.75, 13))

    def test_canals_never_take_nhd_stream_categories(self):
        r = build.reach_rules(self.row(nhd_class="stream_river", nhd_category="Intermittent", streamorder=4), set())
        self.assertEqual((r["flow"], r["intermittent"], r["width_from"]), ("unknown", False, "kind"))


class CanalTest(unittest.TestCase):
    def test_canal_kinds(self):
        rows = [(1, "canal", 15000.0, 3, "Big Canal", "Big Canal"), (1, "canal", 6000.0, 2, None, "Big Canal"),
                (2, "lateral", 900.0, 1, None, "Small Lateral"), (2, "canal", 100.0, 1, None, "Small Lateral"),
                (3, "canal", 3000.0, 1, None, "Short Canal")]
        out = build.canal_kinds(rows)
        self.assertEqual(out[1][:2], ("main_canal", "Big Canal"))
        self.assertEqual(out[2][:2], ("lateral", "Small Lateral"))
        self.assertEqual(out[3][0], "canal")

    def test_head_is_the_upstream_most_and_distances_follow_the_links(self):
        # 1 -> 2 -> 3 (end links), 4 branches off 2 at 50 m; 5 starts on its own and reaches only 6.
        lengths = {1: 100.0, 2: 200.0, 3: 300.0, 4: 80.0, 5: 10.0, 6: 10.0}
        edges = [(1, 2, 100.0), (2, 3, 200.0), (2, 4, 50.0), (5, 6, 10.0)]
        head, dist = build.heads_and_distances([1, 2, 3, 4, 5, 6], edges, lengths)
        self.assertEqual(head, 1)
        self.assertEqual(dist, {1: 0.0, 2: 100.0, 3: 300.0, 4: 150.0})

    def test_a_loop_starts_at_its_lowest_id(self):
        head, dist = build.heads_and_distances([3, 4], [(3, 4, 5.0), (4, 3, 7.0)], {3: 5.0, 4: 7.0})
        self.assertEqual((head, dist), (3, {3: 0.0, 4: 5.0}))

    def test_gauge_names(self):
        self.assertEqual(build.gauge_names("New York Canal Diversion at Boise"), [("new york canal", "reach")])
        self.assertEqual(build.gauge_names("Southwest Idaho Reservoirs at Lake Lowell"), [("lake lowell", "body")])
        self.assertEqual(build.gauge_names("Boise River above Lucky Peak Dam"),
                         [("lucky peak", "body"), ("boise river", "reach")])
        self.assertEqual(build.gauge_names("Boise River at Boise (Glenwood Bridge)"), [("boise river", "reach")])
        self.assertEqual(build.gauge_names("Succor Creek near Homedale"), [("succor creek", "reach")])
        self.assertEqual(build.gauge_names(None), [])


if __name__ == "__main__":
    unittest.main()
