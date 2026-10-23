"""Tests for trails-match (plugins/trails/ingest/match.py): the agencies' lines linked onto
OpenStreetMap's paths, the relink after a poll, the build, the canal-bank rule, routes and the
valley-zoom network, and the status the map reads (trails.agency_state, trails.hidden_informal).

Offline: the rule's settings, the tile sets' licences (and that the Trails layer's ways read
nothing of the City's), that the pollers relink only after their data is committed and only when
they stored a change, and that a relink on a lost connection still never fails the poll.
Synthetic lines only (invented ids, names and coordinates near an invented point): the City's
layers aren't ours to copy.

Database tests run only against a scratch database named by TVT_TEST_DATABASE_URL (with trails
0001 and migrations 0019-0021), inside one transaction that is rolled back; code that commits
gets savepoints instead (tests.Nested).

Run: python3 -m unittest discover -s plugins -t .
"""

import json
import math
import os
import re
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
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
MIGRATION = os.path.join(REPO, "plugins", "trails", "migrations", "0001_paths.sql")
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
        self.assertEqual(match.LAYERS["trails.paths"], {"license": "ODbL", "republish": "yes",
                                                         "credit": "© OpenStreetMap contributors"})
        self.assertEqual(match.LAYERS["trails.routes"]["license"], "ODbL")
        agency = match.LAYERS["trails.agency"]                       # the City's lines, with OSM's ways cut to them
        self.assertEqual(agency["republish"], "aggregates")
        self.assertIn("ODbL", agency["license"])
        self.assertIn("City of Boise", agency["credit"])
        self.assertIn("OpenStreetMap", agency["credit"])
        self.assertEqual(match.SOURCE["schedule"], None)
        self.assertEqual(match.SOURCE["name"], "trails_match")

    def test_the_trails_layer_s_ways_read_nothing_of_the_city_s(self):
        """Plan C3: trails.path and trails.path_lo are recorded ODbL, republish yes, so neither may
        read the City's lines or anything made from them."""
        with open(MIGRATION, encoding="utf-8") as f:
            sql = f.read()
        view = re.search(r"create view trails\.path as(.*?);", sql, re.S).group(1)
        for city in ("trails.link", "matched_line", "agency", "raw.", "evt.", "way_agency"):
            self.assertNotIn(city, view)
        import inspect
        network = inspect.getsource(match.network)
        self.assertIn("from trails.path p", network)
        for city in ("trails.link", "matched_line", "agency_", "raw."):
            self.assertNotIn(city, network.split('"""')[2])          # the code, not the docstring

    def test_every_table_and_view_records_its_licence(self):
        with open(MIGRATION, encoding="utf-8") as f:
            sql = f.read()
        made = re.findall(r"create (table|view) (trails\.\w+)", sql)
        self.assertGreater(len(made), 15)
        for kind, name in made:
            comment = re.search(rf"comment on {kind} {re.escape(name)} is\s+'(.*?)';", sql, re.S)
            self.assertIsNotNone(comment, name)
            self.assertRegex(comment.group(1), r"republish: (yes|aggregates)", name)
        # The views over the City's rows run as their reader, and the tile login is refused them.
        for name in ("agency_line", "agency_state", "way_agency"):
            self.assertRegex(sql, rf"create view trails\.{name} with \(security_invoker = true\) as", name)
        with open(os.path.join(REPO, "deploy", "tvt_tiles.sql"), encoding="utf-8") as f:
            never = re.search(r"never_tables text\[\] := ARRAY\[(.*?)\];", f.read(), re.S).group(1)
        for name in ("agency_line", "agency_state", "way_agency"):
            self.assertIn(f"'trails.{name}'", never)

    def test_a_poll_that_stored_nothing_new_does_nothing(self):
        self.assertFalse(match.changed({"unchanged since": "x", "versions confirmed": 6}))
        self.assertFalse(match.changed({"trails": 271, "versions new": 0, "removed": 0}))
        self.assertTrue(match.changed({"versions new": 3}))
        self.assertTrue(match.changed({"removed": 1}))
        self.assertEqual(match.after_poll(None, "r2r_trails", False), {})        # never touches the database

    def test_a_relink_on_a_lost_connection_never_fails_the_poll(self):
        """The poll's data is committed; if the connection then drops, the relink's failure (and
        its rollback's) stays in the poll's stats instead of failing the poll."""
        class Lost:
            def execute(self, *a, **k):
                raise ConnectionError("the server closed the connection")
            rollback = commit = execute
        got = match.after_poll(Lost(), "r2r_trails", True)
        self.assertEqual(got, {"links": "failed (ConnectionError), logged in ops.fetch as trails_match; "
                                        "trails-match couldn't be marked"})


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
GID = {n: f"0000test-0000-4000-8000-00000000000{n}" for n in range(1, 10)}
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
            # The setUp deletes raw.record rows for these sources, which the scratch build role may not do.
            if not c.execute("select has_table_privilege(current_user, 'raw.record', 'DELETE')").fetchone()[0]:
                raise unittest.SkipTest("the database role can't delete from raw.record (scratch build role); "
                                        "run these as the owner on a test database")

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
            f(B + 10, line((15000, 0), (15000, 500)), highway="track", name="Fixture Track"),  # named, but a track
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

    def paints(self, source_id):
        return {r[0] - B: r[1] for r in self.conn.execute(
            "select osm_id, paints from trails.link where source_id = %s", (source_id,)).fetchall()}

    def drawn(self):
        """What each line draws itself: {source_id: (gap_m, along_m)}, rounded."""
        return {k: (round(g), round(a)) for k, g, a in self.conn.execute(
            "select source_id, gap_m, along_m from trails.matched_line").fetchall()}

    def build(self):
        lines = []
        stats, note = match.build(self.conn, T0, out=lines.append)
        return stats, note, lines

    def versions(self, layer):
        return self.conn.execute("select build from core.layer_version where layer = %s order by built_at, version",
                                 (layer,)).fetchall()

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
        self.assertEqual(self.paints(GID[1]), {1: True, 2: True})
        self.assertEqual(self.paints(CLOSURE), {5: False})                        # it would show 880 m past the closure
        self.assertEqual((stats["lines"], stats["matched lines"], stats["links"], stats["painting"],
                          stats["unmatched lines"]), (7, 4, 5, 4, 3))
        if not self.has_water():
            self.assertIn("canal-bank rule: skipped", lines[0])
        self.assertIn("5 links for 4 of 7 lines", note)
        line_m, covered, links, by, kind, name = self.conn.execute(
            "select line_m, covered_m, links, matched_by, kind, name from trails.matched_line where source_id = %s",
            (GID[1],)).fetchone()
        self.assertAlmostEqual(line_m, 600, delta=1)
        self.assertAlmostEqual(covered, 600, delta=1)
        self.assertEqual((links, by, kind, name), (2, "trails-match", "trail", "Fixture Ridge"))
        self.assertEqual(self.conn.execute("select links, covered_m from trails.matched_line where source_id = %s",
                                           (GID[2],)).fetchone(), (0, None))
        # What each line draws itself: nothing where its ways show it; all of it without one; and of the
        # closure, which paints no way, the stretch of its way that lies along it (with the buffer's ends).
        drawn = self.drawn()
        self.assertEqual({k: drawn[k] for k in (GID[1], GID[4], GID[5])}, {GID[1]: (0, 0), GID[4]: (0, 0), GID[5]: (0, 0)})
        for k, want in ((GID[2], 400), (GID[3], 400), (GID[6], 300)):
            self.assertAlmostEqual(drawn[k][0], want, delta=2, msg=k)
            self.assertEqual(drawn[k][1], 0, k)
        self.assertEqual(drawn[CLOSURE][0], 0)
        self.assertAlmostEqual(drawn[CLOSURE][1], 150, delta=2)
        parts = {(k, part) for k, part in self.conn.execute("select source_id, part from trails.agency_drawn").fetchall()}
        self.assertEqual(parts, {(GID[2], "line"), (GID[3], "line"), (GID[6], "line"), (CLOSURE, "way")})
        self.assertTrue(all(fid < 0 for (fid,) in self.conn.execute("select fid from trails.agency_drawn").fetchall()))
        lo = dict(self.conn.execute("select source_id, fid from trails.agency_lo").fetchall())
        self.assertEqual(set(lo), set(GID[n] for n in range(1, 7)) | {CLOSURE})   # every line, whole, at z10-12
        self.assertEqual(stats["agency features"], 4 + 7)
        # Each tile set got a version, with its licence.
        got = dict(self.conn.execute(
            "select layer, republish from core.layer_version_current where layer like 'trails.%'").fetchall())
        self.assertEqual(got, {"trails.paths": "yes", "trails.routes": "yes", "trails.agency": "aggregates"})

    def test_a_winding_trail_on_a_way_that_runs_on_past_it(self):
        """Why pieces, and why a way that runs on past its line doesn't paint: a switchback trail, and
        an OSM way along all of it that runs on 339 m past its end. Matched whole, the way's end-to-end
        chord points off the trail and the bearing check fails; in pieces, 73% of the way lies along
        the trail: a full link. But the way would show the trail's state 339 m past it, so it doesn't
        paint; the stretch of it along the trail is drawn in the trail's state instead."""
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
        share, off, paints = self.conn.execute(
            "select share, off_m, paints from trails.link where source_id = %s", (GID[2],)).fetchone()
        self.assertAlmostEqual(share, 0.73, delta=0.02)
        self.assertGreater(off, 300)
        self.assertFalse(paints)
        gap, along = self.drawn()[GID[2]]
        self.assertEqual(gap, 0)                                               # all of it shown, on the way's geometry
        self.assertAlmostEqual(along, 900, delta=15)                           # the 894 m along it, not the tail
        self.assertEqual(self.conn.execute("select ways, partial from trails.agency_state where source_id = %s",
                                           (GID[2],)).fetchone(), ([], [B + 40]))

    def test_a_way_paints_only_when_it_lies_along_the_line(self):
        f = lambda osm_id, geom: {"type": "w", "osm_id": osm_id, "geometry": "linestring", "osm_version": 1,
                                  "osm_timestamp": T0, "tags": {"highway": "path"}, "geom": geom}
        self.world(extra=[f(B + 41, line((12000, 0), (12000, 1000))),          # 700 m of it along trail 2: full
                          f(B + 42, line((13000, 0), (13000, 1000))),          # 500 m along trail 3: partial
                          f(B + 43, line((14000, 0), (14000, 1000)))])         # 990 m along trail 7
        self.store_r2r({**self.lines, GID[2]: ("Seven Hundred", line((12003, 0), (12003, 700))),
                        GID[3]: ("Five Hundred", line((13003, 0), (13003, 500))),
                        GID[7]: ("Nearly All", line((14003, 0), (14003, 990)))}, T0 + timedelta(hours=1))
        self.build()
        self.assertEqual(self.links(GID[2]), {41: match.METHOD})
        self.assertEqual(self.links(GID[3]), {42: "way_in_" + match.METHOD})
        self.assertEqual(self.links(GID[7]), {43: match.METHOD})
        # Only the way that lies along its line takes the line's state; the others would show it
        # 300 m and 500 m past the line, so the line draws itself on their stretch along it.
        self.assertEqual({**self.paints(GID[2]), **self.paints(GID[3]), **self.paints(GID[7])},
                         {41: False, 42: False, 43: True})
        drawn = self.drawn()
        self.assertEqual((drawn[GID[2]][0], drawn[GID[3]][0], drawn[GID[7]]), (0, 0, (0, 0)))
        self.assertAlmostEqual(drawn[GID[2]][1], 715, delta=3)
        self.assertAlmostEqual(drawn[GID[3]][1], 515, delta=3)
        status = {k: (w, p) for k, w, p in self.conn.execute(
            "select source_id, ways, partial from trails.agency_state where source_id in (%s, %s, %s)",
            (GID[2], GID[3], GID[7])).fetchall()}
        self.assertEqual(status, {GID[2]: ([], [B + 41]), GID[3]: ([], [B + 42]), GID[7]: ([B + 43], [])})

    def test_the_layer_s_view_is_openstreetmap_s_alone(self):
        """trails.path (the 'trails.paths' tiles, republish yes) reads nothing of the City's: the build's
        links change none of its rows. What they add is in trails.way_agency, internal."""
        self.world()
        cols = ("osm_id, kind, name, surface, surface_from, surface_default, width_m, informal, canal_track, drawn, "
                "not_drawn, greenbelt, minzoom")
        before = self.conn.execute(f"select {cols} from trails.path where osm_id > %s order by 1", (B,)).fetchall()
        self.build()
        after = self.conn.execute(f"select {cols} from trails.path where osm_id > %s order by 1", (B,)).fetchall()
        self.assertEqual(before, after)
        rows = {r[0] - B: r[1:] for r in self.conn.execute(
            """select osm_id, greenbelt, minzoom, surface, surface_from, surface_default, informal, drawn
               from trails.path where osm_id > %s""", (B,)).fetchall()}
        self.assertEqual(rows[1], (False, 13, "unknown", "none", None, False, True))     # R2R's, but unnamed in OSM
        self.assertEqual(rows[5][:2], (True, 10))                              # on the Greenbelt's route
        self.assertEqual(rows[6][-1], False)                                   # private: never drawn
        self.assertEqual(rows[7][1], 10)                                       # a named path
        self.assertEqual(rows[9][1], 16)                                       # informal: close in only
        self.assertEqual(rows[10][1], 13)                                      # a named track: from z13 only
        agency = {r[0] - B: r[1:] for r in self.conn.execute(
            "select osm_id, r2r, greenbelt, lines, surface, surface_from, surface_default from trails.way_agency "
            "where osm_id > %s", (B,)).fetchall()}
        self.assertEqual(agency[1], (True, False, 1, "dirt", "default", "Ridge to Rivers trail"))
        self.assertEqual(agency[5], (False, False, 1, "paved", "default", "cycleway"))   # the closure doesn't paint it
        self.assertEqual(set(agency), {1, 2, 5, 7, 8})
        lo = dict(self.conn.execute("select fid - %s, network from trails.path_lo where fid > %s", (B, B)).fetchall())
        self.assertEqual(lo, {5: "greenbelt", 7: "named", 8: "greenbelt"})

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
            """select source, source_id, kind, name, state, severity, ways, partial, links, line_id, round(gap_m),
                      round(along_m)
               from trails.agency_state""").fetchall()}
        ridge = rows[GID[1]]
        self.assertEqual(ridge[2:9], ("trail", "Fixture Ridge", "dry", "open", [B + 1, B + 2], [], 2))
        self.assertEqual(rows[GID[6]][4:6], ("closed", "closed"))
        closure = rows[CLOSURE]
        self.assertEqual(closure[2:8], ("closure", "Fixture repair", "closure", "closed", [], [B + 5]))
        self.assertIsNotNone(rows[GID[2]][9])                                   # a line drawn as itself has an id
        self.assertEqual((ridge[10], ridge[11]), (0, 0))
        self.assertEqual(closure[10], 0)
        self.assertAlmostEqual(closure[11], 150, delta=2)
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

    def test_an_informal_way_is_never_a_target(self):
        """An agency's line on an informal way doesn't make it official, or keep it from being hidden
        near a closure: the line draws itself, and the way stays informal (plan C18)."""
        self.world()
        self.store_r2r({**self.lines, GID[6]: ("Closed Gulch", line((7004, 0), (7004, 300)))},   # 4 m from way 9
                       T0 + timedelta(hours=1))
        self.build()
        self.assertEqual(self.links(GID[6]), {})
        self.assertAlmostEqual(self.drawn()[GID[6]][0], 300, delta=2)
        self.assertEqual(self.conn.execute("select count(*) from trails.target_way where osm_id = %s",
                                           (B + 9,)).fetchone()[0], 0)
        self.assertEqual(self.conn.execute("select informal, minzoom from trails.path where osm_id = %s",
                                           (B + 9,)).fetchone(), (True, 16))
        self.assertEqual(self.conn.execute("select osm_id from trails.hidden_informal(100)").fetchall(), [(B + 9,)])

    def has_water(self):
        return self.conn.execute("select to_regclass('water.reach') is not null").fetchone()[0]

    def test_the_canal_bank_rule(self):
        """Tracks along a canal are irrigation access (plan C18), unless they're open to all."""
        if not self.has_water():
            self.assertIsNone(match.canal_reaches_sql(self.conn))
            self.assertIsNone(match.water_build(self.conn))
        run = FakeRunLike([
            {"type": "w", "osm_id": B + 30, "geometry": "linestring", "osm_version": 1, "osm_timestamp": T0,
             "tags": {"highway": "track"}, "geom": line((8000, 0), (8000, 400))},              # along the canal
            {"type": "w", "osm_id": B + 31, "geometry": "linestring", "osm_version": 1, "osm_timestamp": T0,
             "tags": {"highway": "track", "access": "permissive"}, "geom": line((8016, 0), (8016, 400))},
            {"type": "w", "osm_id": B + 32, "geometry": "linestring", "osm_version": 1, "osm_timestamp": T0,
             "tags": {"highway": "track"}, "geom": line((7800, 200), (8200, 200))},            # crosses it
            {"type": "w", "osm_id": B + 33, "geometry": "linestring", "osm_version": 1, "osm_timestamp": T0,
             "tags": {"highway": "path"}, "geom": line((7996, 0), (7996, 400))},               # a path, not a track
            {"type": "w", "osm_id": B + 34, "geometry": "linestring", "osm_version": 1, "osm_timestamp": T0,
             "tags": {"highway": "track"}, "geom": line((9000, 0), (9000, 1000))},             # 30% along a canal
            {"type": "w", "osm_id": B + 35, "geometry": "linestring", "osm_version": 1, "osm_timestamp": T0,
             "tags": {"highway": "track"}, "geom": line((9500, 0), (9500, 800))},              # 75%, along two reaches
        ] + self.ways())
        osm_paths.consume(self.conn, run)
        self.conn.execute("create temp table reach_fixture (id bigint, name text, geom geometry) on commit drop")
        for reach_id, geom in ((77, line((8008, -50), (8008, 450))), (78, line((9008, 0), (9008, 300))),
                               (79, line((9508, 0), (9508, 300))), (80, line((9508, 300), (9508, 650)))):
            self.conn.execute("insert into reach_fixture values (%s, 'Fixture Canal', "
                              "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))", (reach_id, json.dumps(geom)))
        n = match.canal_tracks(self.conn, T0, "select id::text as id, name, geom from pg_temp.reach_fixture", 7)
        self.assertEqual(n, 2)
        got = self.conn.execute("select osm_id - %s, reach_id, line_share, water_build from trails.canal_track "
                                "order by 1", (B,)).fetchall()
        self.assertEqual([(r[0], r[1], r[3]) for r in got], [(30, "77", 7), (35, "80", 7)])   # 80 runs along more
        self.assertAlmostEqual(got[1][2], 0.81, delta=0.02)          # 650 m of 800, with the buffer's round end
        drawn = dict(self.conn.execute("select osm_id - %s, not_drawn from trails.path where osm_id between %s and %s",
                                       (B, B + 30, B + 35)).fetchall())
        self.assertEqual(drawn, {30: "irrigation access along a canal", 31: None, 32: None, 33: None, 34: None,
                                 35: "irrigation access along a canal"})
        self.assertEqual(self.conn.execute("select count(*) from trails.target_way where osm_id = %s",
                                           (B + 30,)).fetchone()[0], 0)
        # Without water's reaches the rule is skipped, and its last result doesn't linger.
        with mock.patch.object(match, "canal_reaches_sql", return_value=None):
            self.assertIsNone(match.canal_tracks(self.conn, T0))
        self.assertEqual(self.conn.execute("select count(*) from trails.canal_track").fetchone()[0], 0)

    def test_the_build_needs_the_paths(self):
        self.world(load=False)
        with self.assertRaisesRegex(RuntimeError, "hasn't loaded an extract"):
            self.build()

    def test_the_tile_login_can_t_read_the_city_s_rows(self):
        """Views run with their owner's privileges unless they say otherwise: the ones over raw.record
        and evt.event run as their reader, so a login that may read trails and core, but not raw or evt
        (the tile login), reads the tiles' relations and is refused the City's rows."""
        c = self.conn
        if not c.execute("select rolsuper or rolcreaterole from pg_roles where rolname = current_user").fetchone()[0]:
            self.skipTest("needs a login that can create roles (a laptop test cluster)")
        self.world()
        self.build()
        c.execute("create role tvt_test_tiles_probe nologin")
        c.execute("grant usage on schema trails, core to tvt_test_tiles_probe")
        c.execute("grant select on all tables in schema trails, core to tvt_test_tiles_probe")
        c.execute("set local role tvt_test_tiles_probe")
        try:
            for readable in ("trails.path", "trails.path_lo", "trails.route_line", "trails.agency_drawn",
                             "trails.agency_lo"):
                self.assertGreater(c.execute(f"select count(*) from {readable}").fetchone()[0], 0, readable)
            for refused in ("select count(*) from trails.agency_line", "select count(*) from trails.agency_state",
                            "select count(*) from trails.hidden_informal(100)"):
                c.execute("savepoint probe")
                with self.assertRaises(self.psycopg.errors.InsufficientPrivilege, msg=refused):
                    c.execute(refused)
                c.execute("rollback to savepoint probe")
        finally:
            c.execute("reset role")

    # -- after a poll --------------------------------------------------------------------------

    def fetches(self):
        return self.conn.execute(
            "select ok, records, error from ops.fetch where source = 'trails_match' and id > %s order by id",
            (self.fetch0,)).fetchall()

    def marks(self):
        return self.conn.execute(
            "select marked_by, reason from ops.build_pending where build = 'trails-match' order by marked_by").fetchall()

    def moved(self, **more):
        """The R2R lines with trail 2 moved onto way 3, stored an hour later."""
        lines = {**self.lines, GID[2]: ("Faraway Trail", line((5, 600), (5, 900))), **more}
        self.store_r2r(lines, T0 + timedelta(hours=1))
        return lines

    def test_after_a_poll_before_the_paths_load_nothing_happens(self):
        self.world(load=False)
        self.assertEqual(match.after_poll(Nested(self.conn), "r2r_trails", True), {})
        self.assertEqual((self.fetches(), self.marks()), ([], []))

    def test_a_source_never_linked_is_linked_by_its_poll(self):
        """A closure the City posts shows on the map within its poll, even when the Greenbelt's
        layer had emptied (no line of the source linked): no build needed."""
        self.world()
        self.conn.execute("delete from ops.build_pending where build = 'trails-match'")       # the load's mark
        paths = self.versions("trails.paths")
        got = match.after_poll(Nested(self.conn), gb.SOURCE["name"], True)
        self.assertEqual(got["links"], "1 for 1 changed lines (0 gone)")
        self.assertEqual(self.fetches(), [(True, 1, None)])
        self.assertEqual(self.marks(), [])
        part, length = self.conn.execute("select part, length_m from trails.agency_drawn where source_id = %s",
                                         (CLOSURE,)).fetchone()
        self.assertEqual(part, "way")
        self.assertAlmostEqual(length, 150, delta=2)
        # Only the agencies' tiles change: the ways' tiles are OpenStreetMap's alone.
        self.assertEqual(self.conn.execute("select version from core.layer_version_current where layer = 'trails.agency'")
                         .fetchone()[0], got["tiles"])
        self.assertEqual(self.versions("trails.paths"), paths)

    def test_more_changed_lines_than_a_poll_relinks(self):
        """Lines never linked go first; the rest are left for the build, which is marked."""
        self.world()
        self.build()
        self.conn.execute("delete from ops.build_pending where build = 'trails-match'")
        self.store_r2r({**self.lines, GID[2]: ("Faraway Trail", line((9000, 9000), (9000, 9500))),     # changed
                        GID[7]: ("New Trail", line((5, 600), (5, 900)))}, T0 + timedelta(hours=1))   # never linked
        with mock.patch.object(match, "POLL_MAX_LINES", 1):
            got = match.after_poll(Nested(self.conn), "r2r_trails", True)
        self.assertEqual(got["links"], "1 for 1 changed lines (0 gone); 1 more left for trails-match (marked)")
        self.assertEqual(self.links(GID[7]), {3: match.METHOD})
        self.assertEqual(self.conn.execute(
            """select m.line_fp is distinct from l.line_fp from trails.matched_line m
               join trails.agency_line l using (source, source_id) where source_id = %s""", (GID[2],)).fetchone()[0],
            True)                                                                   # left for the build
        self.assertEqual([m[0] for m in self.marks()], ["r2r_trails"])
        self.assertIn("1 more than a poll relinks", self.marks()[0][1])
        self.assertEqual(self.fetches(), [(True, 1, None)])

    def test_a_moved_line_is_relinked_alone(self):
        self.world()
        self.build()
        before = dict(self.conn.execute("select source_id, matched_at from trails.matched_line").fetchall())
        paths = self.versions("trails.paths")
        self.moved()
        conn = Nested(self.conn)
        got = match.after_poll(conn, "r2r_trails", True)
        self.assertEqual(got["links"], "1 for 1 changed lines (0 gone)")
        self.assertEqual(self.links(GID[2]), {3: match.METHOD})
        self.assertEqual(self.paints(GID[2]), {3: True})
        self.assertEqual(self.fetches(), [(True, 1, None)])
        by, fetch_id = self.conn.execute("select matched_by, fetch_id from trails.matched_line where source_id = %s",
                                         (GID[2],)).fetchone()
        self.assertEqual(by, "poll")
        self.assertIsNotNone(fetch_id)
        after = dict(self.conn.execute("select source_id, matched_at from trails.matched_line").fetchall())
        self.assertEqual({k for k in before if before[k] != after[k]}, {GID[2]})       # the others untouched
        self.assertEqual(self.links(GID[1]), {1: match.METHOD, 2: match.METHOD})
        self.assertGreaterEqual(conn.commits, 2)                                       # the fetch row, then the links
        self.assertEqual(self.versions("trails.paths"), paths)                         # the ways' tiles unchanged
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

    def lock_held(self):
        """Whether any session holds the links' lock, asked from a connection of its own (a session's
        advisory locks are re-entrant, so asking on the session that may hold it would always succeed)."""
        with self.psycopg.connect(DB_URL, autocommit=True) as other:
            if other.execute("select pg_try_advisory_lock(%s)", (self.lock_key(),)).fetchone()[0]:
                other.execute("select pg_advisory_unlock(%s)", (self.lock_key(),))
                return False
            return True

    def test_a_failed_relink_never_fails_the_poll(self):
        self.world()            # no build here: its run's lock lasts until the test's transaction ends
        before = self.conn.execute("select count(*) from raw.record where source = 'r2r_trails'").fetchone()[0]
        with mock.patch.object(match, "relink", side_effect=RuntimeError("the matcher broke")):
            got = match.after_poll(Nested(self.conn), "r2r_trails", True)
        self.assertIn("failed (RuntimeError)", got["links"])
        self.assertEqual(self.fetches(), [(False, None, "RuntimeError: the matcher broke")])
        self.assertIn("r2r_trails", [m[0] for m in self.marks()])
        self.assertEqual(self.conn.execute("select count(*) from raw.record where source = 'r2r_trails'").fetchone()[0],
                         before)                                                        # the poll's data stays
        self.assertFalse(self.lock_held())                                             # the lock was let go
        # And the check can tell: held by this session, another one can't take it.
        self.conn.execute("select pg_advisory_lock(%s)", (self.lock_key(),))
        try:
            self.assertTrue(self.lock_held())
        finally:
            self.conn.execute("select pg_advisory_unlock(%s)", (self.lock_key(),))

    def test_a_relink_out_of_time_is_left_for_the_build(self):
        self.world()            # no build: see test_a_failed_relink_never_fails_the_poll
        with mock.patch.object(match, "BUDGET_S", -1):
            got = match.after_poll(Nested(self.conn), "r2r_trails", True)
        self.assertIn("failed (OutOfTime)", got["links"])
        (ok, records, error), = self.fetches()
        self.assertFalse(ok)
        self.assertTrue(error.startswith("OutOfTime"), error)
        self.assertIn("r2r_trails", [m[0] for m in self.marks()])
        self.assertFalse(self.lock_held())

    def test_each_statement_of_a_relink_is_limited(self):
        """Production's login has no statement_timeout, and serve runs every source in turn."""
        self.world()
        self.build()
        self.moved()
        seen, real = [], match.relink

        def spy(conn, *a, **k):
            seen.append(conn.execute("show statement_timeout").fetchone()[0])
            return real(conn, *a, **k)
        with mock.patch.object(match, "relink", side_effect=spy):
            got = match.after_poll(Nested(self.conn), "r2r_trails", True)
        self.assertEqual(got["links"], "1 for 1 changed lines (0 gone)")
        self.assertEqual(seen, [f"{match.STATEMENT_TIMEOUT_S}s"])

    def lock_key(self):
        return self.conn.execute(match.LINKS_LOCK).fetchone()[0]

    def test_a_poll_while_links_are_being_written_leaves_it_to_the_build(self):
        self.world()
        # As after a build, but this transaction mustn't hold the links' lock (a build's run holds it
        # until it commits, and this test never commits): its lines are matched, but for one.
        self.conn.execute(
            """insert into trails.matched_line (source, source_id, kind, line_fp, osm_md5, links, matched_at, matched_by)
               select source, source_id, kind, case when source_id = %s then 'old' else line_fp end, %s, 0, %s,
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
