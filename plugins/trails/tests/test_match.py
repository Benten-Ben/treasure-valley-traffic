"""Tests for trails-match (plugins/trails/ingest/match.py): the agencies' lines linked onto
OpenStreetMap's paths, the relink after a poll, the build, the canal-bank rule, routes and the
valley-zoom network, and the status the map reads (trails.agency_state, trails.hidden_informal).

Offline: the rule's settings, the tile sets' licences, and that the pollers relink only after
their data is committed and only when they stored a change. Synthetic lines only (invented ids,
names and coordinates near an invented point): the City's layers aren't ours to copy.

Database tests run only against a scratch database named by TVT_TEST_DATABASE_URL (with trails
0001 and migrations 0019-0021), inside one transaction that is rolled back; code that commits
gets savepoints instead (tests.Nested).

Run: python3 -m unittest discover -s plugins -t .
"""

import json
import math
import os
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest import mock

from ingest import db, events, linematch, osm_extract
from plugins.trails.ingest import match
from plugins.trails.ingest.sources import boise_greenbelt_closures as gb
from plugins.trails.ingest.sources import osm_paths
from plugins.trails.ingest.sources import r2r_trails as r2r
from plugins.trails.tests import FakeFetch, FakeLayers, Nested, fixture

DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
T0 = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)
LON0, LAT0 = -116.20, 43.70                      # an invented spot in the foothills
M_LON = 111_320 * math.cos(math.radians(LAT0))
M_LAT = 111_132


def pt(dx, dy):
    """A position dx metres east and dy north of the invented spot."""
    return [round(LON0 + dx / M_LON, 7), round(LAT0 + dy / M_LAT, 7)]


def line(*points):
    return {"type": "LineString", "coordinates": [pt(*p) for p in points]}


def square(x, y, side):
    return line((x, y), (x + side, y), (x + side, y + side), (x, y + side), (x, y))


class SettingsTest(unittest.TestCase):
    def test_the_rule_is_roads_buffer_and_bearing_in_pieces(self):
        self.assertEqual((match.RULE.near_m, match.RULE.check, match.RULE.max_bearing, match.RULE.min_share),
                         (15, "bearing", 20.0, 0.6))
        self.assertTrue(match.RULE.loops)                    # S4's advice for trails (a piece is rarely closed)
        self.assertEqual(match.RULE.method, "buffer15_bearing20")
        self.assertEqual((match.PIECE_M, match.METHOD), (150.0, "pieces150_buffer15_bearing20"))

    def test_the_tile_sets_licences(self):
        self.assertEqual(match.LAYERS["trails.paths"]["republish"], "yes")
        self.assertEqual(match.LAYERS["trails.routes"]["license"], "ODbL")
        self.assertEqual(match.LAYERS["trails.agency"]["republish"], "aggregates")      # the City's own lines
        self.assertEqual(match.SOURCE["schedule"], None)
        self.assertEqual(match.SOURCE["name"], "trails_match")

    def test_a_poll_that_stored_nothing_new_does_nothing(self):
        self.assertFalse(match.changed({"unchanged since": "x", "versions confirmed": 6}))
        self.assertFalse(match.changed({"trails": 271, "versions new": 0, "removed": 0}))
        self.assertTrue(match.changed({"versions new": 3}))
        self.assertTrue(match.changed({"removed": 1}))
        self.assertEqual(match.after_poll(None, "r2r_trails", False), {})        # never touches the database


class PollerTest(unittest.TestCase):
    """The pollers relink after their data is committed, and only after a change."""

    def run_poll(self, module, server, store_stats):
        order = []

        class Fetch(FakeFetch):
            def __exit__(self, *exc):
                order.append("poll committed")
                return False

        def after(conn, source, changed):
            order.append(("relink", source, changed))
            return {"links": "relinked"}

        with mock.patch.object(db, "ensure_source"), mock.patch.object(db, "Fetch", Fetch), \
                mock.patch.object(module, "store", return_value=store_stats), \
                mock.patch.object(match, "after_poll", side_effect=after):
            if module is r2r:
                from plugins.trails.ingest import layers
                with mock.patch.object(layers, "stored_signature", return_value=None), \
                        mock.patch.object(layers, "save_signature"):
                    stats = module.run(None, get=server, sleep=lambda s: None)
            else:
                stats = module.run(None, get=server, sleep=lambda s: None)
        return stats, order

    def test_r2r(self):
        server = FakeLayers({r2r.LAYER: fixture("r2r_trails.json")}, {r2r.LAYER: fixture("r2r_layer.json")})
        stats, order = self.run_poll(r2r, server, {"trails": 6, "versions new": 2, "removed": 0})
        self.assertEqual(order, ["poll committed", ("relink", "r2r_trails", True)])
        self.assertEqual(stats["links"], "relinked")
        stats, order = self.run_poll(r2r, server, {"trails": 6, "versions new": 0, "removed": 0})
        self.assertEqual(order[-1], ("relink", "r2r_trails", False))

    def test_greenbelt(self):
        data = fixture("greenbelt_closures.json")
        server = FakeLayers({gb.layer_url(0): data["0"], gb.layer_url(1): data["1"]})
        stats, order = self.run_poll(gb, server, {"rows": 3, "versions new": 0, "removed": 1})
        self.assertEqual(order, ["poll committed", ("relink", "boise_greenbelt_closures", True)])


# ---- the database -------------------------------------------------------------------------

B = 9_500_000_000           # invented OSM ids
GID = {n: f"0000test-0000-4000-8000-00000000000{n}" for n in range(1, 7)}
CLOSURE = "construction:9001"


def r2r_attrs(name, condition="Dry / Tacky - Enjoy", when=1791230400000):
    return {"TrailName": name, "Name": f"#0 {name}", "SystemName": "Ridge to Rivers", "Condition": condition,
            "ConditionDate": when, "R2R_Use": "Multi-use non-motorized"}


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (with trails 0001 and 0019-0021)")
class DatabaseTest(unittest.TestCase):
    """Everything here runs in one transaction that is rolled back."""

    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg = psycopg
        with psycopg.connect(DB_URL) as c:
            if not c.execute("select to_regclass('trails.matched_line') is not null "
                             "and to_regclass('ops.build_pending') is not null").fetchone()[0]:
                raise unittest.SkipTest("apply trails 0001 and migrations 0019-0021")

    def setUp(self):
        self.conn = self.psycopg.connect(DB_URL)
        c = self.conn
        for s in (r2r.SOURCE, gb.SOURCE, osm_paths.SOURCE, match.SOURCE):
            db.ensure_source(c, s)
        # A clean slate inside the transaction (rolled back): no other trails, lines or marks.
        for sql in ("delete from trails.link", "delete from trails.matched_line", "delete from trails.canal_track",
                    "delete from trails.route_line", "delete from trails.path_lo",
                    "update trails.osm_path set active = false where active",
                    "update trails.osm_route set active = false where active",
                    "update core.osm_way set active = false where active and highway in "
                    "('track', 'path', 'footway', 'cycleway', 'bridleway', 'steps', 'pedestrian')",
                    "delete from evt.event where source in ('r2r_trails', 'boise_greenbelt_closures')",
                    "delete from ops.layer_signature where source in ('r2r_trails', 'boise_greenbelt_closures')",
                    "delete from raw.record where source in ('r2r_trails', 'boise_greenbelt_closures')",
                    "delete from ops.osm_consumer where consumer = 'trails.osm_paths'",
                    "delete from ops.build_pending where build = 'trails-match'"):
            c.execute(sql)
        self.fetch0 = c.execute("select coalesce(max(id), 0) from ops.fetch").fetchone()[0]

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    # -- the world ----------------------------------------------------------------------

    def ways(self):
        """OSM's paths around the invented spot (each case's comment says what it's for)."""
        w = osm_paths
        f = lambda osm_id, geom, **tags: {"type": "w", "osm_id": osm_id, "geometry": "linestring", "tags": tags,
                                          "osm_version": 1, "osm_timestamp": T0, "geom": geom}
        return [
            f(B + 1, line((5, 0), (5, 300)), highway="path"),                   # along trail 1 (south half)
            f(B + 2, line((5, 300), (5, 600)), highway="path"),                 # along trail 1 (north half)
            f(B + 3, line((5, 600), (5, 900)), highway="path"),                 # carries on past it: no
            f(B + 4, line((-200, 300), (200, 300)), highway="footway"),         # crosses it: no
            f(B + 5, line((1000, 0), (2000, 0)), highway="cycleway", name="Fixture Greenbelt"),  # the closure's way
            f(B + 6, line((3000, 0), (3000, 400)), highway="path", access="private"),           # trail 3's, private
            f(B + 7, square(4003, 3, 100), highway="path", name="Fixture Loop"),               # trail 4's loop
            f(B + 9, line((7000, 0), (7000, 300)), highway="path", informal="yes"),             # informal, by trail 6
        ]

    def world(self, load=True, extra=()):
        """Load the ways (and extra ones), the agencies' lines and their states; osm_paths' gate."""
        c = self.conn
        if load:
            osm_paths.consume(c, FakeRunLike(self.ways() + list(extra) + [
                {"type": "r", "osm_id": B + 20, "geometry": "relation", "geom": None, "osm_version": 1,
                 "osm_timestamp": T0, "tags": {"type": "route", "route": "bicycle", "name": "Fixture Greenbelt Ride"},
                 "members": [{"type": "w", "ref": B + 5, "role": ""}, {"type": "w", "ref": B + 8, "role": ""},
                             {"type": "w", "ref": 999_999_999, "role": ""}]}]))
            c.execute("""insert into core.osm_way (osm_id, highway, name, tags, geom)
                         values (%s, 'cycleway', 'Fixture Lanes', '{"highway": "cycleway", "lanes": "1"}',
                                 ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))""",
                      (B + 8, json.dumps(line((6000, 0), (6000, 300)))))          # the named exception
            consumer = next(x for x in osm_extract.consumers() if x.id == "trails.osm_paths")
            osm_extract.set_db_state(c, consumer, "a" * 32, "fixture.osm.pbf", None, None, 9, {})
        self.lines = {
            GID[1]: ("Fixture Ridge", line((0, 0), (0, 600))),
            GID[2]: ("Faraway Trail", line((9000, 9000), (9000, 9400))),
            GID[3]: ("Private Way Trail", line((3002, 0), (3002, 400))),
            GID[4]: ("Fixture Loop", square(4000, 0, 100)),
            GID[5]: ("Lanes Trail", line((6004, 0), (6004, 300))),
            GID[6]: ("Closed Gulch", line((7040, 0), (7040, 300))),
        }
        self.store_r2r(self.lines, T0)
        self.store_closure(line((1050, 2), (1170, 2)), T0)

    def store_r2r(self, lines, seen, conditions=None):
        conditions = conditions or {GID[6]: "CLOSED"}
        records, rows = [], []
        for gid, (name, geom) in lines.items():
            attrs = {**r2r_attrs(name, conditions.get(gid, "Dry / Tacky - Enjoy")), "GlobalID": gid}
            records.append((gid, r2r.payload(attrs, geom), geom))
            rows.append(r2r.condition_row(gid, attrs, geom))
        db.upsert_records(self.conn, "r2r_trails", records, None, seen, complete=True)
        events.upsert(self.conn, "r2r_trails", rows, seen)

    def store_closure(self, geom, seen):
        attrs = {"OBJECTID": 9001, "PROJECT": "Fixture repair", "STATUS": "Active"}
        db.upsert_records(self.conn, gb.SOURCE["name"], [(CLOSURE, gb.payload("construction", attrs, geom), geom)],
                          None, seen, complete=True)
        events.upsert(self.conn, gb.SOURCE["name"], [gb.event_row(CLOSURE, "construction", "closure", attrs, geom)],
                      seen)

    def links(self, source_id):
        return {r[0] - B: r[1] for r in self.conn.execute(
            "select osm_id, method from trails.link where source_id = %s", (source_id,)).fetchall()}

    def build(self):
        lines = []
        stats, note = match.build(self.conn, T0, out=lines.append)
        return stats, note, lines

    # -- the build -----------------------------------------------------------------------

    def test_the_build_links_each_kind_of_case(self):
        self.world()
        stats, note, lines = self.build()
        full, part = match.METHOD, "way_in_" + match.METHOD
        self.assertEqual(self.links(GID[1]), {1: full, 2: full})                  # not 3 (beyond it) or 4 (across)
        self.assertEqual(self.links(CLOSURE), {5: part})                          # 120 m of a 1 km way: partial
        self.assertEqual(self.links(GID[2]), {})                                  # far from every way
        self.assertEqual(self.links(GID[3]), {})                                  # its way is private: not a target
        self.assertEqual(self.links(GID[4]), {7: full})                           # a loop on a loop
        self.assertEqual(self.links(GID[5]), {8: full})                           # the named exception's way
        self.assertEqual(self.links(GID[6]), {})                                  # 40 m from the informal way: too far
        self.assertEqual((stats["lines"], stats["matched lines"], stats["links"], stats["full links"],
                          stats["unmatched lines"]), (7, 4, 5, 4, 3))
        if not self.has_water():
            self.assertIn("canal-bank rule: skipped", lines[0])
        self.assertIn("5 links for 4 of 7 lines", note)
        line_m, covered, links, by = self.conn.execute(
            "select line_m, covered_m, links, matched_by from trails.matched_line where source_id = %s",
            (GID[1],)).fetchone()
        self.assertAlmostEqual(line_m, 600, delta=1)
        self.assertAlmostEqual(covered, 600, delta=1)
        self.assertEqual((links, by), (2, "trails-match"))
        self.assertEqual(self.conn.execute("select links, covered_m from trails.matched_line where source_id = %s",
                                           (GID[2],)).fetchone(), (0, None))
        # Where each line draws itself: nowhere on its ways, all of it without one, and all of the
        # closure, whose way is longer than it (a partial link paints nothing).
        gaps = {k: (round(v) if v else 0) for k, v in self.conn.execute(
            "select source_id, gap_m from trails.matched_line").fetchall()}
        self.assertEqual({k: gaps[k] for k in (GID[1], GID[4], GID[5])}, {GID[1]: 0, GID[4]: 0, GID[5]: 0})
        for k, want in ((GID[2], 400), (GID[3], 400), (GID[6], 300), (CLOSURE, 120)):
            self.assertAlmostEqual(gaps[k], want, delta=2, msg=k)
        drawn = dict(self.conn.execute("select source_id, fid from trails.agency_gap").fetchall())
        self.assertEqual(set(drawn), {GID[2], GID[3], GID[6], CLOSURE})
        self.assertTrue(all(fid < 0 for fid in drawn.values()))
        self.assertEqual(stats["lines drawing a gap"], 4)
        # Each tile set got a version, with its licence.
        got = dict(self.conn.execute(
            "select layer, republish from core.layer_version_current where layer like 'trails.%'").fetchall())
        self.assertEqual(got, {"trails.paths": "yes", "trails.routes": "yes", "trails.agency": "aggregates"})

    def test_a_winding_trail_on_a_way_that_runs_on_past_it(self):
        """Why pieces: a switchback trail, and an OSM way along all of it that runs on 335 m past its
        end. Matched whole, the way's end-to-end chord points off the trail and the bearing check
        fails; in pieces, 73% of the way lies along the trail: a full link."""
        zigzag = [(0, 0), (200, 100), (0, 200), (200, 300), (0, 400)]
        self.world(extra=[
            {"type": "w", "osm_id": B + 40, "geometry": "linestring", "osm_version": 1, "osm_timestamp": T0,
             "tags": {"highway": "path"}, "geom": line(*[(x + 10000 + 4, y) for x, y in zigzag], (10000 - 300, 250))}])
        self.store_r2r({**self.lines, GID[2]: ("Switchback Trail", line(*[(x + 10000, y) for x, y in zigzag]))},
                       T0 + timedelta(hours=1))
        whole = linematch.match(
            self.conn, "select source, source_id, name, geom from trails.agency_line where source_id = %(id)s",
            f"select osm_id as id, name, geom from trails.osm_path where osm_id = {B + 40}", match.RULE,
            params={"id": GID[2]})
        self.assertEqual(whole, [])                                            # the whole-line check misses it
        self.build()
        self.assertEqual(self.links(GID[2]), {40: match.METHOD})
        share, gap = self.conn.execute(
            """select k.share, m.gap_m from trails.link k join trails.matched_line m using (source, source_id)
               where k.source_id = %s""", (GID[2],)).fetchone()
        self.assertAlmostEqual(share, 0.73, delta=0.02)
        self.assertEqual(gap, 0)

    def test_a_way_is_fully_linked_when_most_of_it_lies_along_the_line(self):
        f = lambda osm_id, geom: {"type": "w", "osm_id": osm_id, "geometry": "linestring", "osm_version": 1,
                                  "osm_timestamp": T0, "tags": {"highway": "path"}, "geom": geom}
        self.world(extra=[f(B + 41, line((12000, 0), (12000, 1000))),          # 700 m of it along trail 2: full
                          f(B + 42, line((13000, 0), (13000, 1000)))])         # 500 m along trail 3: partial
        self.store_r2r({**self.lines, GID[2]: ("Seven Hundred", line((12003, 0), (12003, 700))),
                        GID[3]: ("Five Hundred", line((13003, 0), (13003, 500)))}, T0 + timedelta(hours=1))
        self.build()
        self.assertEqual(self.links(GID[2]), {41: match.METHOD})
        self.assertEqual(self.links(GID[3]), {42: "way_in_" + match.METHOD})
        gaps = dict(self.conn.execute("select source_id, round(gap_m) from trails.matched_line where source_id in (%s, %s)",
                                      (GID[2], GID[3])).fetchall())
        self.assertEqual(gaps[GID[2]], 0)                                      # it paints its way
        self.assertAlmostEqual(gaps[GID[3]], 500, delta=2)                     # it draws itself over the longer way

    def test_the_layer_s_view_after_the_build(self):
        self.world()
        self.build()
        rows = {r[0] - B: r[1:] for r in self.conn.execute(
            """select osm_id, r2r, greenbelt, minzoom, surface, surface_from, surface_default, informal, drawn, on_r2r
               from trails.path where osm_id > %s""", (B,)).fetchall()}
        self.assertEqual(rows[1], (True, False, 10, "dirt", "default", "Ridge to Rivers trail", False, True, True))
        self.assertEqual(rows[3], (False, False, 13, "unknown", "none", None, False, True, False))
        self.assertEqual(rows[5][:3], (False, True, 10))                       # the closure's way, and its route
        self.assertEqual(rows[6][-1], False)                                   # private: never drawn
        self.assertEqual(rows[9][2], 16)                                       # informal: close in only
        lo = dict(self.conn.execute("select fid - %s, network from trails.path_lo where fid > %s", (B, B)).fetchall())
        self.assertEqual(lo, {1: "r2r", 2: "r2r", 5: "greenbelt", 7: "r2r", 8: "r2r"})

    def test_route_lines_from_every_owner_s_table(self):
        self.world()
        self.build()
        ways, found, kind, length = self.conn.execute(
            "select ways, ways_found, ST_GeometryType(geom), length_m from trails.route_line where osm_id = %s",
            (B + 20,)).fetchone()
        self.assertEqual((ways, found, kind), (3, 2, "ST_MultiLineString"))   # the third member is outside our box
        self.assertAlmostEqual(length, 1300, delta=2)                         # trails.osm_path's 1 km, core's 300 m

    def test_the_status_the_map_reads(self):
        self.world()
        self.build()
        rows = {r[1]: r for r in self.conn.execute(
            """select source, source_id, kind, name, state, severity, ways, partial, links, line_id, round(gap_m)
               from trails.agency_state""").fetchall()}
        ridge = rows[GID[1]]
        self.assertEqual(ridge[2:9], ("trail", "Fixture Ridge", "dry", "open", [B + 1, B + 2], [], 2))
        self.assertEqual(rows[GID[6]][4:6], ("closed", "closed"))
        closure = rows[CLOSURE]
        self.assertEqual(closure[2:8], ("closure", "Fixture repair", "closure", "closed", [], [B + 5]))
        self.assertIsNotNone(rows[GID[2]][9])                                   # a line drawn as itself has an id
        self.assertEqual((rows[GID[1]][10], rows[CLOSURE][10]), (0, 120))
        # An informal way 40 m from a closed trail is hidden; at 30 m it wouldn't be near enough.
        hidden = self.conn.execute("select osm_id, source_id from trails.hidden_informal(100)").fetchall()
        self.assertEqual(hidden, [(B + 9, GID[6])])
        self.assertEqual(self.conn.execute("select count(*) from trails.hidden_informal(30)").fetchone()[0], 0)
        # The City sets the closure inactive: it ends.
        attrs = {"OBJECTID": 9001, "PROJECT": "Fixture repair", "STATUS": "Inactive"}
        geom = line((1050, 2), (1170, 2))
        db.upsert_records(self.conn, gb.SOURCE["name"], [(CLOSURE, gb.payload("construction", attrs, geom), geom)],
                          None, T0 + timedelta(hours=1), complete=True)
        events.upsert(self.conn, gb.SOURCE["name"], [], T0 + timedelta(hours=1))
        self.assertEqual(self.conn.execute("select state, severity from trails.agency_state where source_id = %s",
                                           (CLOSURE,)).fetchone(), ("ended", None))

    def has_water(self):
        return self.conn.execute("select to_regclass('water.reach') is not null").fetchone()[0]

    def test_the_canal_bank_rule(self):
        """Tracks along a canal are irrigation access (plan C18), unless they're open to all."""
        if not self.has_water():
            self.assertIsNone(match.canal_reaches_sql(self.conn))
        run = FakeRunLike([
            {"type": "w", "osm_id": B + 30, "geometry": "linestring", "osm_version": 1, "osm_timestamp": T0,
             "tags": {"highway": "track"}, "geom": line((8000, 0), (8000, 400))},              # along the canal
            {"type": "w", "osm_id": B + 31, "geometry": "linestring", "osm_version": 1, "osm_timestamp": T0,
             "tags": {"highway": "track", "access": "permissive"}, "geom": line((8016, 0), (8016, 400))},
            {"type": "w", "osm_id": B + 32, "geometry": "linestring", "osm_version": 1, "osm_timestamp": T0,
             "tags": {"highway": "track"}, "geom": line((7800, 200), (8200, 200))},            # crosses it
            {"type": "w", "osm_id": B + 33, "geometry": "linestring", "osm_version": 1, "osm_timestamp": T0,
             "tags": {"highway": "path"}, "geom": line((7996, 0), (7996, 400))},               # a path, not a track
        ] + self.ways())
        osm_paths.consume(self.conn, run)
        self.conn.execute("create temp table reach_fixture (id bigint, name text, geom geometry) on commit drop")
        self.conn.execute("insert into reach_fixture values (77, 'Fixture Canal', ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))",
                          (json.dumps(line((8008, -50), (8008, 450))),))
        n = match.canal_tracks(self.conn, T0, "select id::text as id, name, geom from pg_temp.reach_fixture")
        self.assertEqual(n, 1)
        self.assertEqual(self.conn.execute("select osm_id - %s, reach_id from trails.canal_track", (B,)).fetchall(),
                         [(30, "77")])
        drawn = dict(self.conn.execute("select osm_id - %s, not_drawn from trails.path where osm_id between %s and %s",
                                       (B, B + 30, B + 33)).fetchall())
        self.assertEqual(drawn, {30: "irrigation access along a canal", 31: None, 32: None, 33: None})
        self.assertEqual(self.conn.execute("select count(*) from trails.target_way where osm_id = %s",
                                           (B + 30,)).fetchone()[0], 0)

    def test_the_build_needs_the_paths(self):
        self.world(load=False)
        with self.assertRaisesRegex(RuntimeError, "hasn't loaded an extract"):
            self.build()

    # -- after a poll --------------------------------------------------------------------------

    def fetches(self):
        return self.conn.execute(
            "select ok, records, error from ops.fetch where source = 'trails_match' and id > %s order by id",
            (self.fetch0,)).fetchall()

    def marks(self):
        return self.conn.execute(
            "select marked_by, reason from ops.build_pending where build = 'trails-match' order by marked_by").fetchall()

    def test_after_a_poll_before_the_paths_load_nothing_happens(self):
        self.world(load=False)
        self.assertEqual(match.after_poll(Nested(self.conn), "r2r_trails", True), {})
        self.assertEqual((self.fetches(), self.marks()), ([], []))

    def test_a_source_never_linked_is_left_for_the_build(self):
        self.world()
        self.conn.execute("delete from ops.build_pending where build = 'trails-match'")       # the load's mark
        got = match.after_poll(Nested(self.conn), "r2r_trails", True)
        self.assertEqual(got, {"links": "6 lines left for trails-match (marked)"})
        self.assertEqual(self.fetches(), [])
        self.assertEqual([m[0] for m in self.marks()], ["r2r_trails"])

    def test_a_moved_line_is_relinked_alone(self):
        self.world()
        self.build()
        before = dict(self.conn.execute("select source_id, matched_at from trails.matched_line").fetchall())
        moved = dict(self.lines)
        moved[GID[2]] = ("Faraway Trail", line((5, 600), (5, 900)))          # now along way 3
        self.store_r2r(moved, T0 + timedelta(hours=1))
        conn = Nested(self.conn)
        got = match.after_poll(conn, "r2r_trails", True)
        self.assertEqual(got["links"], "1 for 1 changed lines (0 gone)")
        self.assertEqual(self.links(GID[2]), {3: match.METHOD})
        self.assertEqual(self.fetches(), [(True, 1, None)])
        by, fetch_id = self.conn.execute("select matched_by, fetch_id from trails.matched_line where source_id = %s",
                                         (GID[2],)).fetchone()
        self.assertEqual(by, "poll")
        self.assertIsNotNone(fetch_id)
        after = dict(self.conn.execute("select source_id, matched_at from trails.matched_line").fetchall())
        self.assertEqual({k for k in before if before[k] != after[k]}, {GID[2]})       # the others untouched
        self.assertEqual(self.links(GID[1]), {1: match.METHOD, 2: match.METHOD})
        self.assertGreaterEqual(conn.commits, 2)                                       # the fetch row, then the links
        # Nothing changed since: nothing to do, and no fetch row.
        self.assertEqual(match.after_poll(Nested(self.conn), "r2r_trails", True), {})
        self.assertEqual(len(self.fetches()), 1)

    def test_a_line_gone_from_the_layer_loses_its_links(self):
        self.world()
        self.build()
        db.upsert_records(self.conn, gb.SOURCE["name"], [], None, T0 + timedelta(hours=1), complete=True)
        got = match.after_poll(Nested(self.conn), gb.SOURCE["name"], True)
        self.assertEqual(got["links"], "0 for 0 changed lines (1 gone)")
        self.assertEqual(self.links(CLOSURE), {})
        self.assertEqual(self.conn.execute("select count(*) from trails.matched_line where source_id = %s",
                                           (CLOSURE,)).fetchone()[0], 0)

    def test_a_failed_relink_never_fails_the_poll(self):
        self.world()
        self.build()
        moved = dict(self.lines)
        moved[GID[2]] = ("Faraway Trail", line((5, 600), (5, 900)))
        self.store_r2r(moved, T0 + timedelta(hours=1))
        before = self.conn.execute("select count(*) from raw.record where source = 'r2r_trails'").fetchone()[0]
        with mock.patch.object(match, "relink", side_effect=RuntimeError("the matcher broke")):
            got = match.after_poll(Nested(self.conn), "r2r_trails", True)
        self.assertIn("failed (RuntimeError)", got["links"])
        self.assertEqual(self.fetches(), [(False, None, "RuntimeError: the matcher broke")])
        self.assertIn("r2r_trails", [m[0] for m in self.marks()])
        self.assertEqual(self.conn.execute("select count(*) from raw.record where source = 'r2r_trails'").fetchone()[0],
                         before)                                                        # the poll's data stays
        self.assertEqual(self.conn.execute("select pg_try_advisory_lock(%s)", (self.lock_key(),)).fetchone()[0], True)
        self.conn.execute("select pg_advisory_unlock(%s)", (self.lock_key(),))         # the lock was let go

    def lock_key(self):
        return self.conn.execute(match.LINKS_LOCK).fetchone()[0]

    def test_a_poll_while_links_are_being_written_leaves_it_to_the_build(self):
        self.world()
        # As after a build, but this transaction mustn't hold the links' lock (a build's run holds it
        # until it commits, and this test never commits): its lines are matched, but for one.
        self.conn.execute(
            """insert into trails.matched_line (source, source_id, line_fp, osm_md5, links, matched_at, matched_by)
               select source, source_id, case when source_id = %s then 'old' else line_fp end, %s, 0, %s,
                      'trails-match'
               from trails.agency_line""", (GID[2], "a" * 32, T0))
        with self.psycopg.connect(DB_URL, autocommit=True) as other:
            other.execute("select pg_advisory_lock(%s)", (self.lock_key(),))
            try:
                got = match.after_poll(Nested(self.conn), "r2r_trails", True)
            finally:
                other.execute("select pg_advisory_unlock(%s)", (self.lock_key(),))
        self.assertIn("is running", got["links"])
        self.assertEqual(self.fetches(), [])
        self.assertIn("r2r_trails", [m[0] for m in self.marks()])

    def test_the_poll_and_its_relink_end_to_end(self):
        """r2r_trails.run against a fake server: the poll stores, commits, then relinks; a relink that
        fails leaves the poll's own result as it was."""
        self.world()
        self.build()
        server = FakeLayers({r2r.LAYER: fixture("r2r_trails.json")}, {r2r.LAYER: fixture("r2r_layer.json")})
        conn = Nested(self.conn)
        with mock.patch.object(match, "relink", side_effect=RuntimeError("the matcher broke")):
            stats = r2r.run(conn, get=server, sleep=lambda s: None)
        self.assertEqual(stats["trails"], 6)                                   # the fixture's trails, stored
        self.assertIn("failed", stats["links"])
        ok = self.conn.execute("select ok from ops.fetch where source = 'r2r_trails' and id > %s",
                               (self.fetch0,)).fetchall()
        self.assertEqual(ok, [(True,)])
        self.assertEqual(self.fetches()[0][0], False)


class FakeRunLike:
    """What osm_paths.consume reads of the loader's Run."""

    def __init__(self, features, seen_at=T0):
        self._features, self.seen_at, self.allow_shrink = features, seen_at, True
        self.extract_name, self.md5 = "fixture.osm.pbf", "a" * 32

    def features(self):
        return iter(self._features)


if __name__ == "__main__":
    unittest.main()
