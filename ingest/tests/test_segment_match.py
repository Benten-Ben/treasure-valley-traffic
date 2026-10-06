"""Tests for matching source lines to ACHD road segments (ingest/segment_match.py).

The rule tests are offline. The geometry tests run only against a scratch
database named by TVT_TEST_DATABASE_URL (a clone migrated through 0011):
they draw made-up lines in UTM 11N far from the valley, work inside one
transaction and roll it back, so nothing is left behind.

Run: python3 -m unittest discover -s ingest/tests -t .
"""

import os
import unittest

from ingest import segment_match as sm


class RulesTest(unittest.TestCase):
    def test_bearing_difference_ignores_direction_of_travel(self):
        self.assertEqual(sm.bearing_diff(0, 180), 0)
        self.assertEqual(sm.bearing_diff(10, 350), 20)
        self.assertEqual(sm.bearing_diff(0, 90), 90)
        self.assertEqual(sm.bearing_diff(45, 200), 25)
        self.assertIsNone(sm.bearing_diff(None, 10))

    def test_names_normalize_directions_suffixes_and_case(self):
        self.assertEqual(sm.normalize_name("W Sample Avenue."), "SAMPLE AVE")
        self.assertEqual(sm.normalize_name("N 9th St"), "9TH ST")
        self.assertEqual(sm.normalize_name("WB Sample Pkwy"), "SAMPLE PKWY")
        self.assertIsNone(sm.normalize_name("SH 99 Main"))           # a route designation, not a street name
        self.assertIsNone(sm.normalize_name("N Hwy 99"))
        self.assertIsNone(sm.normalize_name("  "))

    def test_names_agree_across_spelling_variants(self):
        self.assertTrue(sm.names_agree("N SAMPLE RD", "Sample Road"))
        self.assertTrue(sm.names_agree("Sample", "S Sample Rd"))
        self.assertTrue(sm.names_agree("N Six Mile Rd", "SIXMILE RD"))              # spacing
        self.assertTrue(sm.names_agree("W Sample Ave", "SAMPLE RD"))                # suffix differs between sources
        self.assertTrue(sm.names_agree("W Brookside Ln", "BROOKESIDE LN"))          # misspelt
        self.assertTrue(sm.names_agree("W Sample Road Pkwy", "SAMPLE RD"))
        self.assertTrue(sm.names_agree("N Hwy 99", "SH-99"))                        # route numbers
        self.assertTrue(sm.names_agree("WB Interstate 99", "I-99/I-199"))
        self.assertFalse(sm.names_agree("N Hwy 98", "SH-99"))
        self.assertFalse(sm.names_agree("Sample Rd", "Example Rd"))
        self.assertFalse(sm.names_agree("N Five Mile Rd", "TENMILE RD"))
        self.assertFalse(sm.names_agree("Elm St", "Elk St"))                        # too short to call a typo
        self.assertIsNone(sm.names_agree("SH-99", "W Sample St"))                   # a route along a street
        self.assertIsNone(sm.names_agree(None, "Sample Rd"))

    def measures(self, **kw):
        c = {"share": 1.0, "chord_m": 100.0, "projected_m": 100.0, "seg_bearing": 0.0, "src_bearing": 180.0,
             "seg_name": "Sample Rd", "src_name": "SAMPLE RD"}
        c.update(kw)
        return c

    def test_bearing_rule(self):
        self.assertEqual(sm.decide(self.measures(), "buffer15_bearing20"), (0.0, 1.0, "buffer15_bearing20"))
        self.assertIsNone(sm.decide(self.measures(src_bearing=30), "buffer15_bearing20"))      # 30 degrees off
        self.assertIsNone(sm.decide(self.measures(share=0.59), "buffer15_bearing20"))
        self.assertIsNone(sm.decide(self.measures(projected_m=20), "buffer15_bearing20"))      # crosses the line
        diff, conf, _ = sm.decide(self.measures(src_name="Other Rd"), "buffer15_bearing20")    # names disagree
        self.assertEqual(conf, 0.5)
        diff, conf, _ = sm.decide(self.measures(src_name=None, share=0.8, src_bearing=9), "buffer15_bearing20")
        self.assertEqual((diff, conf), (9.0, 0.72))

    def test_name_rule(self):
        self.assertEqual(sm.decide(self.measures(), "buffer10_name"), (0.0, 1.0, "buffer10_name"))
        self.assertIsNone(sm.decide(self.measures(src_name="Other Rd"), "buffer10_name"))      # a name mismatch rejects
        # Names that can't be compared fall back to the bearing rule, and say so.
        self.assertEqual(sm.decide(self.measures(src_name="SH-99", src_bearing=5), "buffer10_name"),
                         (5.0, 0.944, "buffer10_bearing20"))
        self.assertIsNone(sm.decide(self.measures(src_name=None, src_bearing=40), "buffer10_name"))
        # A loop (zero-length chord) has no bearing, but agreeing names don't need one.
        self.assertEqual(sm.decide(self.measures(chord_m=0, projected_m=0), "buffer10_name"),
                         (None, 1.0, "buffer10_name"))

    def test_summary_adds_up_sources(self):
        total = sm.summary({"a": {"lines": 3, "matched lines": 2, "matches": 5, "ACHD segments": 4},
                            "b": {"lines": 1, "matched lines": 0, "unmatched away from ACHD": 1}})
        self.assertEqual((total["lines"], total["matched lines"], total["matches"]), (4, 2, 5))
        self.assertEqual(total["match rate"], "50.0%")


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")

# Made-up geometry in UTM 11N (metres), well away from the valley: x 300,000 is
# about 119.5 W. Each case sits 1 km from the others.
X0, Y0 = 300000, 4800000


def line(*pts):
    return "LINESTRING(" + ", ".join(f"{X0 + x} {Y0 + y}" for x, y in pts) + ")"


SEGMENTS = {     # id: (name, line) -- stand-ins for ACHD segments
    1: ("N Sample Rd", line((0, 0), (0, 300))),                 # a carriageway runs 7 m to each side
    2: ("W Cross St", line((-40, 150), (40, 150))),             # a cross street, 80 m
    3: ("W Stub St", line((-3, 150), (17, 150))),               # a 20 m cross stub, wholly within 15 m of the line
    4: ("N Long Rd", line((1000, 0), (1000, 500))),             # 500 m, a source line covers 100 m of it
    5: ("W Example Ave", line((2000, 0), (2300, 0))),           # for the name rule
}
LINES = {        # source_id: (name, line)
    "A": ("Sample Rd", line((7, -100), (7, 400))),               # ascending carriageway, 7 m east
    "D": ("Sample Rd", line((-7, 400), (-7, -100))),             # descending carriageway, 7 m west, drawn the other way
    "R": ("Long Rd", line((1000, 200), (1000, 300))),            # covers 20% of segment 4
    "M1": ("EXAMPLE AVE", line((1990, 5), (2310, 5))),          # 5 m off, same name
    "M2": ("BRIDGE ST", line((1990, -5), (2310, -5))),          # 5 m off, another name
}


def values_sql(rows, source=None):
    parts = []
    for key, (name, wkt) in rows.items():
        parts.append(f"({key if source is None else repr(key)}, '{name}', "
                     f"ST_Transform(ST_GeomFromText('{wkt}', 26911), 4326))")
    return ",\n".join(parts)


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database migrated through 0011")
class GeometryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.conn = psycopg.connect(DB_URL)
        if not cls.conn.execute("select to_regclass('core.segment_match') is not null").fetchone()[0]:
            cls.conn.close()
            raise unittest.SkipTest("core.segment_match is missing: apply migration 0011")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def tearDown(self):
        self.conn.rollback()

    SEG_SQL = f"select * from (values {values_sql(SEGMENTS)}) s(id, name, geom)"
    LINES_SQL = f"select 'test' as source, * from (values {values_sql(LINES, source=True)}) l(source_id, name, geom)"

    def decided(self, method):
        found = sm.candidates(self.conn, self.LINES_SQL, near_m=sm.METHODS[method]["near_m"], segments_sql=self.SEG_SQL)
        return {(c["road_segment_id"], c["source_id"]): sm.decide(c, method) for c in found}

    def test_both_carriageways_7_m_away_match_the_one_centerline(self):
        got = self.decided("buffer15_bearing20")
        self.assertEqual(got[(1, "A")], (0.0, 1.0, "buffer15_bearing20"))
        self.assertEqual(got[(1, "D")], (0.0, 1.0, "buffer15_bearing20"))

    def test_a_cross_street_does_not_match(self):
        got = self.decided("buffer15_bearing20")
        self.assertNotIn((2, "A"), got)                     # only 30 of its 80 m lie within 15 m: no candidate
        self.assertIsNone(got[(3, "A")])                    # wholly within 15 m, but it crosses the line

    def test_a_20_percent_overlap_is_rejected(self):
        found = sm.candidates(self.conn, self.LINES_SQL, near_m=15, segments_sql=self.SEG_SQL)
        self.assertFalse([c for c in found if c["road_segment_id"] == 4])
        share = self.conn.execute(
            f"""select ST_Length(ST_Intersection(s.g, ST_Buffer(l.g, 15, 'endcap=flat'))) / ST_Length(s.g)
                from (select ST_GeomFromText('{SEGMENTS[4][1]}', 26911) g) s,
                     (select ST_GeomFromText('{LINES["R"][1]}', 26911) g) l""").fetchone()[0]
        self.assertAlmostEqual(share, 0.2, places=3)

    def test_the_name_rule_rejects_another_street(self):
        got = self.decided("buffer10_name")
        self.assertIsNotNone(got[(5, "M1")])
        self.assertIsNone(got[(5, "M2")])

    def test_rematch_rewrites_a_sources_matches_in_place(self):
        c = self.conn
        c.execute("""insert into ops.source (name, title, url, access) values
                     ('test_segment_match', 'test', 'https://example.invalid', 'open')""")
        ids = {}
        for key, (name, wkt) in SEGMENTS.items():
            ids[key] = c.execute(
                """insert into core.road_segment (achd_perm_id, name, geom)
                   values (%s, %s, ST_Multi(ST_Transform(ST_GeomFromText(%s, 26911), 4326))) returning id""",
                (-990000 - key, name, wkt)).fetchone()[0]
        seg_sql = "select id, name, geom from core.road_segment where achd_perm_id between -990099 and -990000"
        lines = self.LINES_SQL.replace("'test' as source", "'test_segment_match' as source")
        stats = sm.rematch(c, ["test_segment_match"], lines, segments_sql=seg_sql)["test_segment_match"]
        self.assertEqual((stats["lines"], stats["matched lines"], stats["matches"]), (5, 4, 4))
        self.assertEqual(stats["unmatched near ACHD"], 1)               # R: along segment 4, too short
        rows = c.execute("""select road_segment_id, source_id, method from core.segment_match
                            where source = 'test_segment_match' order by 2""").fetchall()
        self.assertEqual(rows, [(ids[1], "A", "buffer15_bearing20"), (ids[1], "D", "buffer15_bearing20"),
                                (ids[5], "M1", "buffer15_bearing20"), (ids[5], "M2", "buffer15_bearing20")])
        # Rerun with only the A line: the old matches go, in the same transaction.
        only_a = lines.replace(values_sql(LINES, source=True), values_sql({"A": LINES["A"]}, source=True))
        sm.rematch(c, ["test_segment_match"], only_a, segments_sql=seg_sql)
        self.assertEqual(c.execute("select count(*) from core.segment_match where source = 'test_segment_match'")
                         .fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
