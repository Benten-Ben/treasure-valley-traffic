"""Tests for core's line matcher (ingest/linematch.py).

roads' own matcher tests (plugins/roads/tests/test_segment_match.py) cover
the rules as roads uses them against ACHD's segments. These cover what core
adds: rules with their own buffer and thresholds, method names made from
them, generic target and line names, any network as the targets, and the
coverage stats.

The rule tests are offline. The geometry tests run only against a scratch
database named by TVT_TEST_DATABASE_URL with PostGIS (no migrations needed):
they draw made-up lines in UTM 11N far from the valley, work inside one
transaction and roll it back, so nothing is left behind.

Run: python3 -m unittest discover -s ingest/tests -t .
"""

import os
import unittest

from ingest import linematch as lm


class RuleTest(unittest.TestCase):
    def test_method_names_come_from_the_rule(self):
        # The names stored in core.segment_match since Oct 6 stay as they were.
        self.assertEqual(lm.Rule().method, "buffer15_bearing20")
        self.assertEqual(lm.Rule(15, "bearing").method, "buffer15_bearing20")
        self.assertEqual(lm.Rule(10, "name").method, "buffer10_name")
        self.assertEqual(lm.Rule(10, "name").fallback, "buffer10_bearing20")
        self.assertEqual(lm.Rule(7.5, max_bearing=30).method, "buffer7.5_bearing30")
        self.assertEqual(lm.Rule(near_m=8.0).method, "buffer8_bearing20")

    def test_a_rule_must_make_sense(self):
        with self.assertRaises(ValueError):
            lm.Rule(15, "shape")
        with self.assertRaises(ValueError):
            lm.Rule(0)
        with self.assertRaises(ValueError):
            lm.Rule(loops="no")
        self.assertEqual(lm.Rule(loops=False).method, lm.Rule().method)          # not part of the name

    def measures(self, **kw):
        c = {"share": 1.0, "line_len": 300.0, "line_share": None, "chord_m": 100.0, "projected_m": 100.0,
             "chord_bearing": 0.0, "projected_bearing": 180.0, "target_name": "Sample Gulch Trail",
             "line_name": "SAMPLE GULCH"}
        c.update(kw)
        return c

    def test_decide_reads_the_target_and_line_names(self):
        self.assertEqual(lm.decide(self.measures()), (0.0, 1.0, "buffer15_bearing20"))
        self.assertEqual(lm.decide(self.measures(), lm.Rule(10, "name")), (0.0, 1.0, "buffer10_name"))
        # Names that disagree halve the bearing rule's confidence and reject the name rule.
        other = self.measures(line_name="Other Ridge Trail")
        self.assertEqual(lm.decide(other)[1], 0.5)
        self.assertIsNone(lm.decide(other, lm.Rule(10, "name")))
        # Names that can't be compared fall back to the bearing, and say so.
        self.assertEqual(lm.decide(self.measures(line_name=None), lm.Rule(10, "name")),
                         (0.0, 1.0, "buffer10_bearing20"))

    def test_a_rules_own_thresholds(self):
        c = self.measures(share=0.7, projected_bearing=25)
        self.assertIsNone(lm.decide(c))                                          # 25 degrees off
        self.assertEqual(lm.decide(c, lm.Rule(max_bearing=30)), (25.0, 0.634, "buffer15_bearing30"))  # 0.7 x cos 25
        self.assertIsNone(lm.decide(c, lm.Rule(max_bearing=30, min_share=0.8)))
        bay = self.measures(share=0.2, line_len=15.0, line_share=0.9)
        self.assertIsNone(lm.decide(bay))                                        # a line under 20 m
        self.assertEqual(lm.decide(bay, lm.Rule(min_line_m=10)), (0.0, 0.9, "way_in_buffer15_bearing20"))
        crossing = self.measures(projected_m=40)
        self.assertIsNone(lm.decide(crossing))                                   # the lines cross
        self.assertEqual(lm.decide(crossing, lm.Rule(min_projected=0.4))[2], "buffer15_bearing20")

    def test_names_beyond_streets(self):
        self.assertTrue(lm.names_agree("Sample Gulch Trail", "SAMPLE GULCH"))    # a trail's suffix
        self.assertTrue(lm.names_agree("Sample Canal", "SAMPLE CANAL"))
        self.assertFalse(lm.names_agree("Sample Canal", "Other Canal"))
        self.assertIsNone(lm.names_agree("", "Sample Canal"))
        # Only street suffixes are dropped, so a long generic word they share looks like a
        # misspelling to the name check: a network named that way should take the bearing check,
        # or drop the word from both names first.
        self.assertTrue(lm.names_agree("Sample Canal", "Example Canal"))
        self.assertFalse(lm.names_agree("Sample", "Example"))


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")

# Made-up geometry in UTM 11N (metres), well away from the valley: x 300,000 is
# about 119.5 W. Each case sits 1 km from the others.
X0, Y0 = 300000, 4810000


def line(*pts):
    return "LINESTRING(" + ", ".join(f"{X0 + x} {Y0 + y}" for x, y in pts) + ")"


# The network: a path mapped as short pieces, as OpenStreetMap splits a trail.
TARGETS = {      # id: (name, kind, line)
    "p1": ("Sample Ridge Trail", "path", line((0, 0), (0, 120))),
    "p2": ("Sample Ridge Trail", "path", line((0, 120), (0, 260))),
    "p3": ("Sample Ridge Trail", "path", line((0, 260), (0, 400))),
    "p4": ("Spur", "path", line((-60, 200), (60, 200))),                  # crosses the ridge trail
    "p6": ("Stub", "path", line((-10, 50), (6, 50))),                     # a 16 m stub across it
    "p5": ("Long Bench Trail", "path", line((1000, 0), (1000, 900))),      # 900 m; L lies along 100 m of it
    "r1": ("Sample Ridge Trail", "road", line((3, 0), (3, 400))),          # left out by the targets' query
}
LINES = {        # source_id: (name, line)
    "T": ("SAMPLE RIDGE", line((4, -20), (4, 410))),                       # the agency's line, 4 m east
    "L": ("Long Bench", line((1006, 300), (1006, 400))),                  # short, along p5
    "N": ("Sample Ridge", line((30, 0), (30, 400))),                       # 30 m off: a miss near the network
    "A": ("Far Away", line((5000, 0), (5000, 300))),                       # nowhere near
}


def values(rows, cols):
    return ",\n".join("(" + ", ".join(f"'{v}'" for v in vals[:-1]) +
                      f", ST_Transform(ST_GeomFromText('{vals[-1]}', 26911), 4326))" for vals in rows)


TARGETS_SQL = (f"select * from (values {values([(k, *v) for k, v in TARGETS.items()], 4)}) "
               "t(id, name, kind, geom) where kind = %(kind)s")
LINES_SQL = f"select 'test' as source, * from (values {values([(k, *v) for k, v in LINES.items()], 3)}) l(source_id, name, geom)"


def ring(cx, cy, r, start_deg=0, n=8):
    """A closed n-gon of radius r around (cx, cy), starting at start_deg (0 is east)."""
    import math
    pts = [(cx + r * math.cos(math.radians(start_deg + 360 * i / n)),
            cy + r * math.sin(math.radians(start_deg + 360 * i / n))) for i in range(n)]
    return line(*pts, pts[0])


# Closed lines, 10 km and more from the cases above.
POND = line((10000, 0), (10100, 0), (10100, 60), (10000, 60), (10000, 0))          # a 320 m pond loop
LOOP_TARGETS = {
    "pond": ("Pond Loop", POND),
    "rb": (None, ring(12000, 0, 10, start_deg=90)),      # a small roundabout as one closed way...
    "rb2": (None, ring(13000, 0, 10)),                   # ...and one whose halfway chord lies along the road
    "path": ("Bench Path", line((14000, 0), (14000, 900))),
}
LOOP_LINES = {
    "same": ("Pond Loop", POND),                                                       # the loop drawn twice
    "round": ("Pond Loop", line((9997, -3), (10103, -3), (10103, 63), (9997, 63), (9997, 10))),  # open, 3 m out
    "road": ("Main St", line((11900, 0), (12100, 0))),                                 # straight through rb
    "road2": ("Main St", line((12900, 0), (13100, 0))),                                # straight through rb2
    "thin": ("Bench Path", line((14003, 300), (14003, 400), (14006, 400), (14006, 300), (14003, 300))),
}
LOOP_TARGETS_SQL = f"select * from (values {values([(k, *v) for k, v in LOOP_TARGETS.items()], 3)}) t(id, name, geom)"
LOOP_LINES_SQL = (f"select 'loops' as source, * from (values {values([(k, *v) for k, v in LOOP_LINES.items()], 3)}) "
                  "l(source_id, name, geom)")


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database with PostGIS")
class GeometryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.conn = psycopg.connect(DB_URL)
        if not cls.conn.execute("select exists (select 1 from pg_extension where extname = 'postgis')").fetchone()[0]:
            cls.conn.close()
            raise unittest.SkipTest("PostGIS is missing")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def tearDown(self):
        self.conn.rollback()

    def matched(self, rule=lm.Rule()):
        found = lm.match(self.conn, LINES_SQL, TARGETS_SQL, rule, {"kind": "path"})
        return found, {(m["target_id"], m["source_id"]): m for m in found}

    def test_a_line_matches_every_piece_it_runs_along(self):
        found, got = self.matched()
        self.assertEqual(sorted(got), [("p1", "T"), ("p2", "T"), ("p3", "T"), ("p5", "L")])
        for key in ("p1", "T"), ("p2", "T"), ("p3", "T"):
            self.assertEqual((got[key]["method"], got[key]["confidence"]), ("buffer15_bearing20", 1.0))
            self.assertAlmostEqual(got[key]["share"], 1.0, places=3)
        self.assertNotIn(("r1", "T"), got)                                 # the query's params reach the targets
        # L covers a ninth of p5, so it matches on its own share; share still measures the target.
        self.assertEqual(got[("p5", "L")]["method"], "way_in_buffer15_bearing20")
        self.assertLess(got[("p5", "L")]["share"], 0.15)                    # about 128 of its 900 m
        self.assertAlmostEqual(got[("p5", "L")]["line_share"], 1.0, places=3)

    def test_crossing_paths_do_not_match(self):
        found = {(c["target_id"], c["source_id"]): c
                 for c in lm.candidates(self.conn, LINES_SQL, TARGETS_SQL, {"kind": "path"})}
        self.assertNotIn(("p4", "T"), found)                               # 30 of its 120 m: no candidate
        self.assertAlmostEqual(found[("p6", "T")]["share"], 1.0, places=3)  # wholly within 15 m...
        self.assertIsNone(lm.decide(found[("p6", "T")]))                   # ...but it crosses the line
        self.assertEqual((found[("p1", "T")]["target_name"], found[("p1", "T")]["line_name"]),
                         ("Sample Ridge Trail", "SAMPLE RIDGE"))

    def test_a_wider_rule_reaches_the_line_30_m_off(self):
        found, got = self.matched(lm.Rule(35))
        self.assertEqual(got[("p2", "N")]["method"], "buffer35_bearing20")
        self.assertEqual(got[("p2", "N")]["confidence"], 1.0)

    def test_closed_lines_are_measured_by_their_quarters(self):
        found = {(m["target_id"], m["source_id"]): m for m in lm.match(self.conn, LOOP_LINES_SQL, LOOP_TARGETS_SQL)}
        self.assertEqual(sorted(found), [("path", "thin"), ("pond", "round"), ("pond", "same")])
        for key in ("pond", "same"), ("pond", "round"):
            self.assertEqual(found[key]["method"], "buffer15_bearing20")             # on the closed target's share
            self.assertGreater(found[key]["chord_m"], 50)                           # a quarter of it, not 0
            self.assertGreater(found[key]["confidence"], 0.9)
        self.assertEqual(found[("pond", "same")]["bearing_diff"], 0.0)
        # A thin closed line along a path matches on its own share; every quarter runs along the path.
        self.assertEqual(found[("path", "thin")]["method"], "way_in_buffer15_bearing20")
        # A straight road through a small roundabout never matches it, wherever the loop starts: at
        # most two quarters can run along the road. (rb2's start-to-halfway chord lies along road2, so
        # measuring a loop by its halves would have matched it.)
        cands = {(c["target_id"], c["source_id"]): c for c in lm.candidates(self.conn, LOOP_LINES_SQL, LOOP_TARGETS_SQL)}
        for key in ("rb", "road"), ("rb2", "road2"):
            self.assertAlmostEqual(cands[key]["share"], 1.0, places=3)
            self.assertIsNone(lm.decide(cands[key]))

    def test_without_loops_a_closed_line_has_no_chord(self):
        # Roads' rule (loops=False), as on Oct 6: the closed lines fail the bearing check; the open one
        # doesn't help either, since the chord measured is the closed target's.
        rule = lm.Rule(loops=False)
        cands = lm.candidates(self.conn, LOOP_LINES_SQL, LOOP_TARGETS_SQL, rule=rule)
        pond = [c for c in cands if c["target_id"] == "pond"]
        self.assertEqual(sorted(c["source_id"] for c in pond), ["round", "same"])
        self.assertEqual({c["chord_m"] for c in pond}, {0.0})
        self.assertEqual(lm.match(self.conn, LOOP_LINES_SQL, LOOP_TARGETS_SQL, rule), [])
        # Under the name check the names decide, loops or not.
        names = lm.match(self.conn, LOOP_LINES_SQL, LOOP_TARGETS_SQL, lm.Rule(10, "name", loops=False))
        self.assertEqual(sorted((m["target_id"], m["source_id"], m["method"]) for m in names),
                         [("pond", "round", "buffer10_name"), ("pond", "same", "buffer10_name")])

    def test_coverage(self):
        found, _ = self.matched()
        stats = lm.coverage(self.conn, found)
        self.assertEqual(stats, {"test": {"lines": 4, "matched lines": 2, "matches": 4, "targets": 4,
                                          "matches on the line's share": 1, "unmatched near": 1,
                                          "unmatched away": 1}})
        # With nothing matched, every line is a miss or away. N crosses the spur.
        stats = lm.coverage(self.conn, [], near_m=20)
        self.assertEqual((stats["test"]["matched lines"], stats["test"]["unmatched near"],
                          stats["test"]["unmatched away"]), (0, 3, 1))


if __name__ == "__main__":
    unittest.main()
