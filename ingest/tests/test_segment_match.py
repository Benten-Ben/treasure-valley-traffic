"""Tests for matching source lines to ACHD road segments (ingest/segment_match.py).

The rule tests are offline. The geometry tests run only against a scratch
database named by TVT_TEST_DATABASE_URL (a clone migrated through 0011):
they draw made-up lines in UTM 11N far from the valley, work inside one
transaction and roll it back, so nothing is left behind.

Run: python3 -m unittest discover -s ingest/tests -t .
"""

import contextlib
import io
import os
import unittest
from unittest import mock

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
        c = {"share": 1.0, "line_len": 300.0, "line_share": None, "chord_m": 100.0, "projected_m": 100.0,
             "chord_bearing": 0.0, "projected_bearing": 180.0, "seg_name": "Sample Rd", "src_name": "SAMPLE RD"}
        c.update(kw)
        return c

    def test_bearing_rule(self):
        self.assertEqual(sm.decide(self.measures(), "buffer15_bearing20"), (0.0, 1.0, "buffer15_bearing20"))
        self.assertIsNone(sm.decide(self.measures(projected_bearing=30), "buffer15_bearing20"))  # 30 degrees off
        self.assertIsNone(sm.decide(self.measures(share=0.59), "buffer15_bearing20"))
        self.assertIsNone(sm.decide(self.measures(projected_m=20), "buffer15_bearing20"))      # crosses the line
        diff, conf, _ = sm.decide(self.measures(src_name="Other Rd"), "buffer15_bearing20")    # names disagree
        self.assertEqual(conf, 0.5)
        diff, conf, _ = sm.decide(self.measures(src_name=None, share=0.8, projected_bearing=9), "buffer15_bearing20")
        self.assertEqual((diff, conf), (9.0, 0.79))                                          # 0.8 x cos 9

    def test_the_lines_share(self):
        # A short line lying along a long segment matches on its own share; its confidence uses that share.
        bay = self.measures(share=0.25, line_len=60.0, line_share=1.0)
        self.assertEqual(sm.decide(bay, "buffer15_bearing20"), (0.0, 1.0, "way_in_buffer15_bearing20"))
        self.assertIsNone(sm.decide({**bay, "line_len": 19.0}, "buffer15_bearing20"))         # under 20 m
        self.assertIsNone(sm.decide({**bay, "line_share": 0.5}, "buffer15_bearing20"))
        self.assertIsNone(sm.decide({**bay, "projected_bearing": 45}, "buffer15_bearing20"))
        # Under the name rule the line's share needs the bearing too.
        self.assertEqual(sm.decide(bay, "buffer10_name"), (0.0, 1.0, "way_in_buffer10_name"))
        self.assertEqual(sm.decide({**bay, "src_name": "SH-99"}, "buffer10_name"),
                         (0.0, 1.0, "way_in_buffer10_bearing20"))
        self.assertIsNone(sm.decide({**bay, "projected_m": 0}, "buffer10_name"))
        self.assertIsNone(sm.decide({**bay, "src_name": "Other Rd"}, "buffer10_name"))

    def test_name_rule(self):
        self.assertEqual(sm.decide(self.measures(), "buffer10_name"), (0.0, 1.0, "buffer10_name"))
        self.assertIsNone(sm.decide(self.measures(src_name="Other Rd"), "buffer10_name"))      # a name mismatch rejects
        # Names that can't be compared fall back to the bearing rule, and say so.
        self.assertEqual(sm.decide(self.measures(src_name="SH-99", projected_bearing=5), "buffer10_name"),
                         (5.0, 0.996, "buffer10_bearing20"))
        self.assertIsNone(sm.decide(self.measures(src_name=None, projected_bearing=40), "buffer10_name"))
        # A loop (zero-length chord) has no bearing, but agreeing names don't need one.
        self.assertEqual(sm.decide(self.measures(chord_m=0, projected_m=0), "buffer10_name"),
                         (None, 1.0, "buffer10_name"))

    def test_summary_adds_up_sources(self):
        total = sm.summary({"a": {"lines": 3, "matched lines": 2, "matches": 5, "ACHD segments": 4},
                            "b": {"lines": 1, "matched lines": 0, "unmatched away from ACHD": 1}})
        self.assertEqual((total["lines"], total["matched lines"], total["matches"]), (4, 2, 5))
        self.assertEqual(total["match rate"], "50.0%")

    def test_every_lane_source_and_osm_can_be_rematched(self):
        self.assertEqual(sorted(sm.matchers()), ["achd_msm", "compass_centerline", "itd_hpms", "osm_valley"])
        with self.assertRaises(ValueError):
            sm.rematch_all(None, ["nonesuch"])

    def test_a_failing_matcher_is_rolled_back_and_the_rest_still_run(self):
        class Conn:
            commits = rollbacks = 0

            def commit(self):
                Conn.commits += 1

            def rollback(self):
                Conn.rollbacks += 1

        def boom(conn):
            raise RuntimeError("boom")

        fake = {"a": (lambda conn: {"matched lines": 1}, ["a"], ["a"]), "b": (boom, ["b"], ["b"]),
                "c": (lambda conn: {"matched lines": 2}, ["c"], ["c"])}
        with mock.patch.object(sm, "matchers", return_value=fake), contextlib.redirect_stdout(io.StringIO()):
            out = sm.rematch_all(Conn())
        self.assertEqual(out, {"a": {"matched lines": 1}, "b": {"failed": "RuntimeError: boom"},
                               "c": {"matched lines": 2}})
        self.assertEqual((Conn.commits, Conn.rollbacks), (2, 1))
        # Only the out-of-date ones, when asked.
        with mock.patch.object(sm, "matchers", return_value=fake), \
                mock.patch.object(sm, "stale", side_effect=lambda conn, s, r: s == ["c"]):
            self.assertEqual(sm.rematch_all(Conn(), only_stale=True), {"c": {"matched lines": 2}})


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
    4: ("N Long Rd", line((1000, 0), (1000, 500))),             # 500 m; R covers 100 m of it
    5: ("W Example Ave", line((2000, 0), (2300, 0))),           # for the name rule
    6: ("N Bend Rd", line((3000, 0), (3000, 500))),             # 500 m; T runs along 100 m of it, then turns away
}
LINES = {        # source_id: (name, line)
    "A": ("Sample Rd", line((7, -100), (7, 400))),               # ascending carriageway, 7 m east
    "D": ("Sample Rd", line((-7, 400), (-7, -100))),             # descending carriageway, 7 m west, drawn the other way
    "R": ("Long Rd", line((1000, 200), (1000, 300))),            # wholly along segment 4, a fifth of its length
    "M1": ("EXAMPLE AVE", line((1990, 5), (2310, 5))),          # 5 m off, same name
    "M2": ("BRIDGE ST", line((1990, -5), (2310, -5))),          # 5 m off, another name
    "T": ("Bend Rd", line((3000, 200), (3000, 300), (3200, 300))),   # 100 m along segment 6, then 200 m east
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

    def found(self, near_m=15):
        return {(c["road_segment_id"], c["source_id"]): c
                for c in sm.candidates(self.conn, self.LINES_SQL, near_m=near_m, segments_sql=self.SEG_SQL)}

    def decided(self, method):
        return {k: sm.decide(c, method) for k, c in self.found(sm.METHODS[method]["near_m"]).items()}

    def test_both_carriageways_7_m_away_match_the_one_centerline(self):
        got = self.decided("buffer15_bearing20")
        self.assertEqual(got[(1, "A")], (0.0, 1.0, "buffer15_bearing20"))
        self.assertEqual(got[(1, "D")], (0.0, 1.0, "buffer15_bearing20"))

    def test_a_cross_street_does_not_match(self):
        got = self.decided("buffer15_bearing20")
        self.assertNotIn((2, "A"), got)                     # only 30 of its 80 m lie within 15 m: no candidate
        self.assertIsNone(got[(3, "A")])                    # wholly within 15 m, but it crosses the line

    def test_a_20_percent_overlap_matches_only_on_the_lines_share(self):
        found = self.found()
        r = found[(4, "R")]
        # 130 of segment 4's 500 m lie within 15 m of R (round ends): too little on the segment's share...
        self.assertAlmostEqual(r["share"], 0.26, places=2)
        self.assertAlmostEqual(r["line_share"], 1.0, places=3)
        # ...but R lies wholly along the segment, so it matches on its own share; the share stays the segment's.
        self.assertEqual(sm.decide(r, "buffer15_bearing20"), (0.0, 1.0, "way_in_buffer15_bearing20"))
        # T runs along 100 m of segment 6, then turns away: neither share reaches 60%.
        self.assertNotIn((6, "T"), found)

    def test_the_name_rule_rejects_another_street(self):
        got = self.decided("buffer10_name")
        self.assertIsNotNone(got[(5, "M1")])
        self.assertIsNone(got[(5, "M2")])

    def test_stale(self):
        c = self.conn
        c.execute("""insert into ops.source (name, title, url, access) values
                     ('test_stale', 'test', 'https://example.invalid', 'open')""")
        self.assertFalse(sm.stale(c, ["test_stale"]))                     # no records: nothing to match
        c.execute("""insert into raw.record (source, source_id, version_hash, payload, first_seen, last_seen)
                     values ('test_stale', 'x', '\\x01', '{}', now() - interval '2 hours', now())""")
        self.assertTrue(sm.stale(c, ["test_stale"]))                      # records, no matches
        seg = c.execute("""insert into core.road_segment (achd_perm_id, name, geom)
                           values (-990199, 'Test', ST_Multi(ST_Transform(ST_GeomFromText(%s, 26911), 4326)))
                           returning id""", (line((5000, 0), (5000, 100)),)).fetchone()[0]
        c.execute("""insert into core.segment_match (road_segment_id, source, source_id, method, matched_at)
                     values (%s, 'test_stale', 'x', 'buffer15_bearing20', now())""", (seg,))
        self.assertFalse(sm.stale(c, ["test_stale"]))                     # matched since
        c.execute("""insert into raw.record (source, source_id, version_hash, payload, first_seen, last_seen)
                     values ('test_stale', 'x', '\\x02', '{}', now() + interval '1 minute', now())""")
        self.assertTrue(sm.stale(c, ["test_stale"]))                      # a newer version of its own

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
        self.assertEqual((stats["lines"], stats["matched lines"], stats["matches"], stats["matches on the line's share"]),
                         (6, 5, 5, 1))
        self.assertEqual(stats["unmatched near ACHD"], 1)               # T
        rows = c.execute("""select road_segment_id, source_id, method, round(share::numeric, 2)
                            from core.segment_match where source = 'test_segment_match' order by 2""").fetchall()
        self.assertEqual([r[:3] for r in rows],
                         [(ids[1], "A", "buffer15_bearing20"), (ids[1], "D", "buffer15_bearing20"),
                          (ids[5], "M1", "buffer15_bearing20"), (ids[5], "M2", "buffer15_bearing20"),
                          (ids[4], "R", "way_in_buffer15_bearing20")])
        self.assertEqual(float(rows[-1][3]), 0.26)                      # R's row measures the ACHD segment
        # Rerun with only the A line: the old matches go, in the same transaction.
        only_a = lines.replace(values_sql(LINES, source=True), values_sql({"A": LINES["A"]}, source=True))
        sm.rematch(c, ["test_segment_match"], only_a, segments_sql=seg_sql)
        self.assertEqual(c.execute("select count(*) from core.segment_match where source = 'test_segment_match'")
                         .fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
