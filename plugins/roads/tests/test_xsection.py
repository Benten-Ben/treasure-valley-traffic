"""The real-width roads' cross-section rules (plugins/roads/ingest/xsection.py) on synthetic pieces.

python3 -m unittest plugins.roads.tests.test_xsection
"""

import unittest

from plugins.roads.ingest import xsection as X

D = X.DEFAULTS


def piece(highway="residential", oneway="no", tags=None, **kw):
    t = {"highway": highway, **(tags or {})}
    if oneway != "no":
        t.setdefault("oneway", oneway)
    return {"highway": highway, "oneway": oneway, "tags": t, "county": "Ada", **kw}


def seg(one_way="both", same_way=True, sid=7):
    return {"id": sid, "functional_class": "Minor Arterial", "one_way": one_way, "same_way": same_way,
            "confidence": 0.9}


def seg_lanes(source="achd_msm", fwd=2, bwd=2, centre=False, conflict=False, flags=()):
    return {"source": source, "lanes_total": fwd + bwd, "lanes_forward": fwd, "lanes_backward": bwd,
            "centre_turn_lane": centre, "conflict": conflict, "flags": list(flags), "confidence": 0.8}


def bike_row(total=None, flags=(), **sides):
    row = {"total_pavement_m": total, "flags": list(flags)}
    for side in ("fwd", "bwd"):
        row.update({f"{side}_lanes": None, f"{side}_edge": None, f"{side}_lane_w_m": None, f"{side}_bike": None,
                    f"{side}_bike_w_m": None, f"{side}_bike_in_roadway": None, f"{side}_buffer": None,
                    f"{side}_buffer_w_m": None, f"{side}_parking": None, f"{side}_parking_w_m": None,
                    f"{side}_roadway_m": None})
    row.update(sides)
    return row


def side(prefix, lanes=1, edge="curb_gutter", bike="no_facility", bike_w=0.0, in_roadway=False, lane_w=None,
         parking="none", parking_w=0.0, roadway=None, buffer="none", buffer_w=0.0):
    return {f"{prefix}_lanes": lanes, f"{prefix}_edge": edge, f"{prefix}_bike": bike, f"{prefix}_bike_w_m": bike_w,
            f"{prefix}_bike_in_roadway": in_roadway, f"{prefix}_lane_w_m": lane_w, f"{prefix}_parking": parking,
            f"{prefix}_parking_w_m": parking_w, f"{prefix}_roadway_m": roadway, f"{prefix}_buffer": buffer,
            f"{prefix}_buffer_w_m": buffer_w}


class LocalStreets(unittest.TestCase):
    def test_an_untagged_street_in_town_is_the_curbed_class_width(self):
        xs = X.cross_section(piece(seg=seg(), lanes=seg_lanes("default", 1, 1), developed=0.9))
        self.assertEqual((xs["lanes_fwd"], xs["lanes_bwd"], xs["lanes_source"]), (1, 1, "default"))
        self.assertEqual((xs["total_w_m"], xs["width_tier"], xs["width_source"]),
                         (D["local_pavement"]["curbed"], "estimated", "class_default"))
        self.assertEqual((xs["edge_l"], xs["edge_r"]), ("curb", "curb"))
        self.assertEqual(xs["width_left_m"], xs["width_right_m"])
        self.assertFalse(xs["markings"])
        self.assertEqual((xs["material"], xs["material_source"]), ("asphalt", "default"))
        # The 1+1 is our rule, not ACHD's data: nothing internal went in.
        self.assertEqual(xs["republish"], "yes")
        self.assertEqual(X.marking_lines(xs, 0), [])

    def test_a_rural_road_is_the_rural_width_and_its_material_unknown(self):
        xs = X.cross_section(piece("unclassified", developed=0.1, county="Canyon"))
        self.assertEqual(xs["total_w_m"], D["local_pavement"]["rural"])
        self.assertEqual((xs["edge_l"], xs["edge_r"]), ("shoulder", "shoulder"))
        self.assertEqual((xs["material"], xs["material_source"]), ("unknown", None))
        xs = X.cross_section(piece("unclassified", tags={"surface": "gravel"}, developed=0.1))
        self.assertEqual((xs["material"], xs["material_source"]), ("gravel", "surface"))

    def test_a_mapped_sidewalk_makes_a_curb_even_off_developed_land(self):
        xs = X.cross_section(piece(sidewalk={"left": 6.5, "right": None}, developed=0.0))
        self.assertEqual((xs["edge_l"], xs["edge_r"]), ("curb", "shoulder"))
        mixed = (D["local_pavement"]["curbed"] + D["local_pavement"]["rural"]) / 2
        self.assertAlmostEqual(xs["total_w_m"], mixed, places=2)
        xs = X.cross_section(piece(tags={"sidewalk": "both"}, developed=0.0))
        self.assertEqual((xs["edge_l"], xs["edge_r"]), ("curb", "curb"))

    def test_two_tagged_lanes_on_a_residential_street_draw_no_lines(self):
        xs = X.cross_section(piece(tags={"lanes": "2"}, developed=1.0))
        self.assertEqual((xs["lanes_source"], xs["markings"]), ("osm", False))
        self.assertEqual(xs["total_w_m"], D["local_pavement"]["curbed"])     # the class width is a floor
        xs = X.cross_section(piece(tags={"lanes": "2", "lane_markings": "yes"}, developed=1.0))
        self.assertTrue(xs["markings"])
        self.assertEqual([k for k, _, _ in X.marking_lines(xs, 0)], ["centre_double"])

    def test_an_alley(self):
        xs = X.cross_section(piece("service", service="alley", tags={"service": "alley"}, developed=0.2))
        self.assertEqual((xs["total_w_m"], xs["width_tier"], xs["markings"]), (D["alley"], "estimated", False))
        self.assertEqual(xs["material"], "unknown")


class SidewalkCap(unittest.TestCase):
    def test_a_sidewalk_cuts_the_outer_space(self):
        xs = X.cross_section(piece(sidewalk={"left": 4.5, "right": 4.5}, developed=1.0))
        self.assertEqual((xs["width_left_m"], xs["width_right_m"]), (3.5, 3.5))
        self.assertIn("sidewalk_cap", xs["flags"])
        self.assertEqual(xs["reviews"], [])

    def test_never_into_the_lanes(self):
        xs = X.cross_section(piece(sidewalk={"left": 2.5, "right": None}, developed=1.0))
        self.assertEqual(xs["width_left_m"], xs["total_w_m"] / 2)
        self.assertIn("sidewalk_close", xs["flags"])
        self.assertEqual(xs["reviews"][0][0], "sidewalk_close")

    def test_an_inventoried_width_is_listed_not_cut(self):
        p = piece("tertiary", seg=seg(), lanes=seg_lanes("achd_msm", 1, 1), bike=bike_row(12.0),
                  sidewalk={"left": 4.0, "right": None}, developed=1.0)
        xs = X.cross_section(p)
        self.assertEqual((xs["width_tier"], xs["width_left_m"]), ("inventoried", 6.0))
        self.assertEqual([r[0] for r in xs["reviews"]], ["sidewalk_close"])


class Lanes(unittest.TestCase):
    def test_osm_lanes_with_a_centre_turn_lane(self):
        xs = X.cross_section(piece("primary", tags={"lanes": "5", "lanes:forward": "2", "lanes:backward": "2",
                                                    "lanes:both_ways": "1"}, developed=1.0))
        self.assertEqual((xs["lanes_fwd"], xs["lanes_bwd"], xs["centre_turn"]), (2, 2, True))
        self.assertEqual((xs["lanes_source"], xs["width_tier"], xs["markings"]), ("osm", "counted", True))
        self.assertAlmostEqual(xs["total_w_m"], 5 * 3.66 + 2 * D["gutter"], places=2)
        kinds = [k for k, _, _ in X.marking_lines(xs, 0)]
        self.assertEqual(kinds, ["lane", "twltl", "twltl", "lane"])
        lines = X.marking_lines(xs, 0)
        self.assertEqual([o for _, _, o in lines], [-5.49, -1.83, 1.83, 5.49])
        self.assertEqual(xs["spans"], {"bwd": (-9.15, -1.83), "fwd": (1.83, 9.15)})

    def test_an_odd_count_without_a_split_reads_as_the_master_street_maps(self):
        xs = X.cross_section(piece("secondary", tags={"lanes": "3"}, developed=1.0))
        self.assertEqual((xs["lanes_fwd"], xs["lanes_bwd"], xs["centre_turn"]), (1, 1, True))
        self.assertIn("split_estimated", xs["flags"])

    def test_achd_lanes_split_onto_a_divided_roads_carriageways(self):
        # ACHD draws one two-way line; OpenStreetMap two one-way ways. The northbound one is drawn against
        # the segment, so it takes the segment's backward lanes.
        p = piece("primary", oneway="yes", seg=seg("both", same_way=False),
                  lanes=seg_lanes("achd_msm", 2, 3), developed=1.0)
        xs = X.cross_section(p)
        self.assertEqual((xs["lanes_fwd"], xs["lanes_bwd"], xs["lanes_source"]), (3, 0, "achd_msm"))
        self.assertEqual(xs["republish"], "internal")
        self.assertEqual((xs["width_tier"], xs["markings"]), ("counted", True))
        self.assertEqual([k for k, _, _ in X.marking_lines(xs, 1)], ["lane", "lane"])

    def test_a_one_way_piece_against_its_one_way_segment_is_listed(self):
        p = piece("primary", oneway="yes", seg=seg("forward", same_way=False), lanes=seg_lanes("achd_msm", 3, 0))
        xs = X.cross_section(p)
        self.assertEqual((xs["lanes_source"], xs["lanes_fwd"]), ("default", 1))
        self.assertIn("direction", xs["flags"])
        self.assertEqual(xs["reviews"][0][0], "direction")
        self.assertFalse(xs["markings"])

    def test_a_two_way_way_on_one_way_segments_assumes_the_other_direction(self):
        p = piece("secondary", seg=seg("forward"), lanes=seg_lanes("achd_msm", 2, 0), developed=1.0)
        xs = X.cross_section(p)
        self.assertEqual((xs["lanes_fwd"], xs["lanes_bwd"]), (2, 2))
        self.assertIn("other_direction_assumed", xs["flags"])

    def test_osm_against_the_segments_rule_by_more_than_a_lane_is_a_conflict(self):
        p = piece("primary", tags={"lanes": "4"}, seg=seg(), lanes=seg_lanes("achd_msm", 3, 3), developed=1.0)
        xs = X.cross_section(p)
        self.assertEqual((xs["lanes_source"], xs["lanes_fwd"]), ("osm", 2))
        self.assertIn("conflict", xs["flags"])
        self.assertEqual(xs["reviews"][0][0], "lanes_conflict")
        p["lanes"] = seg_lanes("achd_msm", 2, 3)
        self.assertNotIn("conflict", X.cross_section(p)["flags"])

    def test_canyon_falls_back_on_hpms_then_the_default(self):
        hp = {"through": [{"direction": "A", "lanes_ascending": 2, "lanes_descending": 2, "through_lanes": 4,
                           "same_way": False, "route_id": "01990ASH055"}]}
        xs = X.cross_section(piece("trunk", county="Canyon", hpms=hp))
        self.assertEqual((xs["lanes_fwd"], xs["lanes_bwd"], xs["lanes_source"]), (2, 2, "itd_hpms"))
        self.assertEqual(xs["republish"], "internal")
        # A divided highway's A row runs one way; the D row is the other carriageway.
        hp = {"through": [{"direction": "A", "lanes_ascending": 2, "lanes_descending": 0, "same_way": True,
                           "route_id": "00010AIN084"},
                          {"direction": "D", "lanes_descending": 3, "same_way": False, "route_id": "00010DIN084"}]}
        self.assertEqual(X.cross_section(piece("motorway", oneway="yes", county="Canyon", hpms=hp))["lanes_fwd"], 2)
        hp["through"][0]["same_way"] = False
        self.assertEqual(X.cross_section(piece("motorway", oneway="yes", county="Canyon", hpms=hp))["lanes_fwd"], 3)
        xs = X.cross_section(piece("trunk", county="Canyon"))
        self.assertEqual((xs["lanes_source"], xs["lanes_fwd"], xs["markings"]), ("default", 1, False))
        # Off the state routes HPMS's counts are defaults: not taken.
        hp = {"through": [{"direction": "A", "lanes_ascending": 1, "lanes_descending": 1, "same_way": True,
                           "route_id": "27000ALOCAL1"}]}
        self.assertEqual(X.cross_section(piece("residential", county="Canyon", hpms=hp))["lanes_source"], "default")

    def test_turn_lanes_and_arrows(self):
        tags = {"lanes": "3", "oneway": "yes", "turn:lanes": "left|through|through;right"}
        xs = X.cross_section(piece("primary", oneway="yes", tags=tags, developed=1.0))
        self.assertEqual(xs["turn_fwd"], ["left", "through", "through;right"])
        arrows = X.lane_centres(xs, 1)
        self.assertEqual([(d, n, t) for d, n, _, t in arrows],
                         [("forward", 1, ["left"]), ("forward", 2, ["through"]), ("forward", 3, ["through", "right"])])
        self.assertLess(arrows[0][2], arrows[2][2])          # lane 1 on the left
        # Against the line: the travel left is the line's right.
        tags = {"lanes": "2", "oneway": "-1", "turn:lanes": "left|right"}
        xs = X.cross_section(piece("primary", oneway="-1", tags=tags, developed=1.0))
        (d1, n1, o1, t1), (d2, n2, o2, t2) = X.lane_centres(xs, -1)
        self.assertEqual((d1, n1, t1, d2, n2, t2), ("backward", 1, ["left"], "backward", 2, ["right"]))
        self.assertGreater(o1, o2)
        self.assertEqual(set(xs["spans"]), {"bwd"})

    def test_a_turn_lanes_slot_count_off_is_listed(self):
        tags = {"lanes": "2", "oneway": "yes", "turn:lanes": "left|through|right"}
        xs = X.cross_section(piece("primary", oneway="yes", tags=tags))
        self.assertIsNone(xs["turn_fwd"])
        self.assertEqual(xs["reviews"][0][0], "turn_slots")


class Widths(unittest.TestCase):
    def test_achds_curb_to_curb_width_fits_the_lanes(self):
        row = bike_row(18.9, **side("fwd", 2, bike="bike_lane", bike_w=1.5, in_roadway=True),
                       **side("bwd", 2, bike="bike_lane", bike_w=1.5, in_roadway=True))
        p = piece("primary", seg=seg(same_way=False), lanes=seg_lanes("achd_msm", 2, 2, centre=True), bike=row,
                  developed=1.0)
        xs = X.cross_section(p)
        self.assertEqual((xs["width_tier"], xs["width_source"], xs["total_w_m"]),
                         ("inventoried", "achd_bike_network", 18.9))
        self.assertEqual(xs["lane_w_m"], round((18.9 - 3.0 - 2 * D["gutter"]) / 5, 2))
        self.assertEqual((xs["bike_l_m"], xs["bike_r_m"]), (1.5, 1.5))
        self.assertEqual(xs["sources"]["lane_w"], "fitted")
        kinds = [k for k, _, _ in X.marking_lines(xs, 0)]
        self.assertEqual(kinds, ["bike", "lane", "twltl", "twltl", "lane", "bike"])

    def test_components_that_dont_fit_are_scaled_and_listed(self):
        row = bike_row(9.0, **side("fwd", 2, parking="parallel", parking_w=2.4),
                       **side("bwd", 2, parking="parallel", parking_w=2.4))
        p = piece("secondary", seg=seg(), lanes=seg_lanes("achd_msm", 2, 2), bike=row, developed=1.0)
        xs = X.cross_section(p)
        self.assertEqual(xs["total_w_m"], 9.0)
        self.assertIn("components_exceed", xs["flags"])
        self.assertEqual(xs["reviews"][0][0], "components_exceed")
        parts = sum(xs[k] for k in ("park_l_m", "park_r_m", "shoulder_l_m", "shoulder_r_m")) + 4 * xs["lane_w_m"]
        self.assertAlmostEqual(parts, 9.0, delta=0.05)

    def test_wide_pavement_goes_to_the_edges(self):
        row = bike_row(16.0)
        p = piece("tertiary", seg=seg(), lanes=seg_lanes("achd_msm", 1, 1), bike=row, developed=1.0)
        xs = X.cross_section(p)
        self.assertIn("unassigned_pavement", xs["flags"])
        self.assertEqual(xs["lane_w_m"], 3.35)
        self.assertAlmostEqual(xs["shoulder_l_m"] + xs["shoulder_r_m"] + 2 * 3.35, 16.0, places=1)

    def test_a_divided_roads_carriageway_takes_its_own_sides_roadway(self):
        row = bike_row(30.0, **side("fwd", 2, bike="bike_lane", bike_w=1.8, in_roadway=True, roadway=9.4),
                       **side("bwd", 3, roadway=11.0))
        p = piece("primary", oneway="yes", seg=seg(same_way=True), lanes=seg_lanes("achd_msm", 2, 3), bike=row)
        xs = X.cross_section(p)
        self.assertEqual((xs["width_source"], xs["total_w_m"]), ("achd_bike_network", 9.4 + 2 * D["gutter"]))
        self.assertEqual((xs["bike_r_m"], xs["bike_l_m"]), (1.8, 0.0))

    def test_the_osm_width_tag(self):
        xs = X.cross_section(piece("tertiary", tags={"width": "9"}, developed=1.0))
        self.assertEqual((xs["width_tier"], xs["width_source"], xs["total_w_m"]), ("inventoried", "osm_width", 9.0))
        self.assertEqual(xs["republish"], "yes")

    def test_hpms_lane_width_and_shoulders_are_inventoried(self):
        hp = {"lane_width_ft": 12, "shoulder": {"type": "surfaced_asphalt", "right_ft": 8, "left_ft": 4}}
        xs = X.cross_section(piece("motorway", oneway="yes", tags={"lanes": "2"}, county="Canyon", hpms=hp))
        self.assertEqual((xs["width_tier"], xs["width_source"]), ("inventoried", "itd_hpms"))
        self.assertAlmostEqual(xs["total_w_m"], 2 * 12 * X.FT + 12 * X.FT, places=1)
        self.assertEqual((xs["shoulder_r_m"], xs["shoulder_l_m"]), (round(8 * X.FT, 2), round(4 * X.FT, 2)))
        lines = X.marking_lines(xs, 1, "motorway")
        self.assertEqual([k for k, _, _ in lines], ["edge", "lane", "edge"])

    def test_a_one_way_against_its_line_mirrors(self):
        hp = {"shoulder": {"type": "surfaced_asphalt", "right_ft": 10, "left_ft": 4}}
        xs = X.cross_section(piece("motorway", oneway="-1", tags={"lanes": "2"}, hpms=hp))
        # The travel right (outside shoulder) is the line's left.
        self.assertEqual((xs["shoulder_l_m"], xs["shoulder_r_m"]), (round(10 * X.FT, 2), round(4 * X.FT, 2)))
        a, b = xs["spans"]["bwd"]
        self.assertLess(a, 0)
        self.assertAlmostEqual(b - a, 2 * 3.66, delta=0.02)

    def test_a_motorway_without_hpms(self):
        xs = X.cross_section(piece("motorway", oneway="yes", tags={"lanes": "3"}))
        self.assertEqual((xs["shoulder_r_m"], xs["shoulder_l_m"]),
                         (D["shoulder"]["motorway_out"], D["shoulder"]["motorway_in"]))
        self.assertEqual((xs["edge_l"], xs["edge_r"]), ("shoulder", "shoulder"))

    def test_an_hpms_median_on_one_way(self):
        hp = {"median": {"type": "curbed", "width_ft": 14}}
        xs = X.cross_section(piece("primary", tags={"lanes": "4"}, hpms=hp, developed=1.0))
        self.assertEqual((xs["median_kind"], xs["median_w_m"]), ("curbed", round(14 * X.FT, 2)))
        lines = X.marking_lines(xs, 0)
        self.assertEqual([k for k, _, _ in lines], ["lane", "edge", "edge", "lane"])
        self.assertAlmostEqual(lines[2][2] - lines[1][2], 14 * X.FT, delta=0.02)

    def test_a_roundabouts_ring(self):
        xs = X.cross_section(piece("secondary", oneway="yes", roundabout=True, tags={"junction": "roundabout"},
                                   developed=1.0))
        self.assertEqual(xs["lane_w_m"], D["roundabout_lane"])

    def test_osm_bike_lanes_and_parking(self):
        tags = {"lanes": "2", "cycleway:right": "lane", "parking:lane:left": "parallel"}
        xs = X.cross_section(piece("tertiary", tags=tags, developed=1.0))
        self.assertEqual((xs["bike_l_m"], xs["bike_r_m"], xs["park_l_m"], xs["park_r_m"]),
                         (0.0, D["bike_lane"], D["parking"]["parallel"], 0.0))
        self.assertEqual(xs["sources"]["bike_r"], "osm")
        self.assertEqual([k for k, _, _ in X.marking_lines(xs, 0)], ["centre_double", "bike"])
        # On a one-way road, a bare cycleway=lane is on the right of travel.
        xs = X.cross_section(piece("tertiary", oneway="-1", tags={"lanes": "2", "cycleway": "lane"}, developed=1.0))
        self.assertEqual((xs["bike_l_m"], xs["bike_r_m"]), (D["bike_lane"], 0.0))


if __name__ == "__main__":
    unittest.main()
