"""Tests for the playback matcher (ingest/transit_progress.py; docs/14 §14.4 "Playback").

The matcher tests are offline, on synthetic shapes in metres. The database tests
(stream isolation, backfill racing the stream) run only against a scratch
database, never the server's, named by TVT_TEST_DATABASE_URL (a package clone
with migration 0007, e.g. tvt_wp7). They add rows for vehicles named wp7-test-*
and remove them afterwards.

Run: python3 -m unittest discover -s ingest/tests -t .
     TVT_TEST_DATABASE_URL=postgres://tvt:...@localhost/tvt_wp7 python3 -m unittest ingest.tests.test_transit_progress
"""

import contextlib
import io
import os
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone

from ingest import transit_progress as tp
from ingest.sources import vrt_realtime

T0 = datetime(2026, 10, 5, 20, 17, tzinfo=timezone.utc)


def network(*shapes):
    """shapes: (shape_id, route_id, [(x, y), ...]) in metres."""
    return tp.Network([tp.Shape(sid, rid, coords) for sid, rid, coords in shapes])


def fix(t, x, y, bearing=None, *, vid="v1", route=None, trip=None, matched=None):
    return tp.Fix(vid, T0 + timedelta(seconds=t), x, y, bearing, trip, route, "trip" if route else None, matched)


def run(net, fixes, history=()):
    chain = tp.Chain(net, history)
    return [chain.add(f) for f in fixes]


def steps(rows):
    return [r.step for r in rows[:-1]]


class MatcherTest(unittest.TestCase):
    def test_out_and_back_shape_keeps_the_right_pass(self):
        # One shape up a street and back down its other side, 6 m over (ends 200 m apart: not a loop).
        net = network(("ob", "R", [(0, 0), (0, 1000), (6, 1000), (6, 200)]))
        # Without a bearing, a fix drifting 4 m east lies closer to the return pass, 1,000 m ahead:
        # only the window keeps it on the way out (and, on the way back, off the way out).
        north = [fix(0, 0, 100, 0), fix(30, 0, 300, 0), fix(60, 4, 500), fix(90, 0, 700, 0), fix(120, 0, 900, 0),
                 fix(150, 0, 980, 0)]
        south = [fix(180, 6, 900, 180), fix(210, 6, 700, 180), fix(240, 2, 500), fix(270, 6, 300, 180)]
        rows = run(net, north + south)
        self.assertEqual([round(r.m) for r in rows], [100, 300, 500, 700, 900, 980, 1106, 1306, 1506, 1706])
        self.assertEqual({r.shape_id for r in rows}, {"ob"})
        self.assertEqual(set(steps(rows)), {"along"})

    def test_overlapping_opposite_shapes_follow_the_bearing_and_progress_is_monotonic(self):
        net = network(("up", "R", [(0, 0), (0, 2000)]), ("down", "R", [(3, 2000), (3, 0)]))
        south = [fix(0, 1.5, 1800, 180), fix(30, 1.5, 1600, 182), fix(60, 1.4, 1595, 0),   # stopped, bogus bearing
                 fix(90, 1.6, 1590, 10), fix(120, 1.5, 1400, 178), fix(150, 1.5, 1150, 181)]
        rows = run(net, south)
        self.assertEqual({r.shape_id for r in rows}, {"down"})
        ms = [r.m for r in rows]
        self.assertEqual(ms, sorted(ms))
        self.assertEqual(steps(rows), ["along", "still", "still", "along", "along"])
        north = run(net, [fix(0, 1.5, 200, 0), fix(30, 1.5, 450, 3), fix(60, 1.5, 700, 359)])
        self.assertEqual({r.shape_id for r in north}, {"up"})
        self.assertEqual([round(r.m) for r in north], [200, 450, 700])

    def test_a_loop_seam_gives_one_along_step(self):
        # A 400 m square whose ends are 10 m apart: a loop of 1590 m.
        net = network(("loop", "T", [(0, 0), (400, 0), (400, 400), (0, 400), (0, 10)]))
        shape = net.shapes["loop"]
        self.assertTrue(shape.loop)
        rows = run(net, [fix(0, 0, 200, 180), fix(30, 0, 60, 180), fix(60, 60, 0, 90), fix(90, 200, 0, 90)])
        self.assertEqual([round(r.m) for r in rows], [1400, 1540, 60, 200])
        self.assertEqual(steps(rows), ["along", "along", "along"])
        self.assertAlmostEqual(rows[1].step_speed_ms, 110 / 30)      # 50 m to the seam and 60 m past it
        self.assertAlmostEqual(shape.dm(1540, 60), 110)
        self.assertAlmostEqual(shape.dm(60, 1540), -110)

    def test_step_kinds(self):
        net = network(("s", "R", [(0, 0), (0, 3000)]))
        off = run(net, [fix(0, 0, 100, 0), fix(30, 200, 400, 30)])          # 200 m off every shape
        self.assertIsNone(off[1].shape_id)
        self.assertEqual(off[0].step, "straight")
        self.assertAlmostEqual(off[0].step_speed_ms, 360.555 / 30, places=2)
        gap = run(net, [fix(0, 0, 100, 0), fix(200, 0, 600, 0)])
        self.assertEqual((gap[0].step, gap[0].step_speed_ms), ("gap", None))
        jitter = run(net, [fix(0, 0, 100, 0), fix(30, 8, 100, 0)])            # 8 m of GPS jitter
        self.assertEqual((jitter[0].step, jitter[0].step_speed_ms), ("still", 0.0))
        back = run(net, [fix(0, 0, 500, 0), fix(30, 0, 485, 0)])              # slid back 15 m along the shape
        self.assertEqual(back[0].step, "still")
        fast = run(net, [fix(0, 0, 100, 0), fix(30, 0, 1300, 0)])             # 40 m/s
        self.assertEqual(fast[0].step, "straight")
        # The speed rule on its own, with both fixes on the shape:
        a = tp.Row("v", T0, 0, 100, shape_id="s", m=100.0)
        b = tp.Row("v", T0 + timedelta(seconds=30), 0, 1300, shape_id="s", m=1300.0)
        self.assertEqual(tp.classify(net, a, b), ("straight", 40.0))
        b.y, b.m = 900, 900.0                                                 # 26.7 m/s
        kind, speed = tp.classify(net, a, b)
        self.assertEqual(kind, "along")
        self.assertAlmostEqual(speed, 800 / 30)

    def test_a_route_restricts_the_candidates(self):
        net = network(("a", "A", [(0, 0), (0, 1000)]), ("b", "B", [(30, 0), (30, 1000)]))
        on_b = run(net, [fix(0, 2, 100, 0, matched="B")])
        self.assertEqual((on_b[0].shape_id, on_b[0].route_id, on_b[0].route_source), ("b", "B", "matched"))
        self.assertAlmostEqual(on_b[0].off_m, 28)
        labeled = run(net, [fix(0, 28, 100, 0, route="A")])
        self.assertEqual((labeled[0].shape_id, labeled[0].route_source), ("a", "trip"))
        free = run(net, [fix(0, 2, 100, 0)])
        self.assertEqual((free[0].shape_id, free[0].route_id), ("a", None))

    def test_a_bus_with_no_route_gets_a_provisional_one_from_its_path(self):
        net = network(("r1", "R1", [(0, 0), (0, 3000)]), ("r2", "R2", [(1000, 0), (1000, 3000)]))
        rows = run(net, [fix(30 * i, 0, 100 + 200 * i, 0, trip="182273") for i in range(7)])
        self.assertEqual([r.route_id for r in rows], [None, None, None, None, "R1", "R1", "R1"])
        self.assertEqual(rows[4].route_source, "path")
        # A new trip starts over.
        more = tp.Chain(net)
        for r in [fix(30 * i, 0, 100 + 200 * i, 0, trip="182273") for i in range(6)]:
            more.add(r)
        self.assertIsNone(more.add(fix(210, 0, 1400, 0, trip="182999")).route_id)

    def test_shared_streets_give_no_provisional_route(self):
        net = network(("r1", "R1", [(0, 0), (0, 3000)]), ("r2", "R2", [(5, 0), (5, 3000)]))
        rows = run(net, [fix(30 * i, 2, 100 + 200 * i, 0, trip="182273") for i in range(8)])
        self.assertEqual({r.route_id for r in rows}, {None})

    def test_a_provisional_route_survives_between_calls(self):
        net = network(("r1", "R1", [(0, 0), (0, 3000)]), ("r2", "R2", [(1000, 0), (1000, 3000)]))
        first = run(net, [fix(30 * i, 0, 100 + 200 * i, 0, trip="182273") for i in range(3)])
        later = run(net, [fix(30 * i, 0, 100 + 200 * i, 0, trip="182273") for i in range(3, 6)], history=first)
        self.assertEqual([r.route_id for r in later], [None, "R1", "R1"])


class ThreadTest(unittest.TestCase):
    """How pending fixes join the rows already stored."""

    def setUp(self):
        self.net = network(("s", "R", [(0, 0), (0, 5000)]))
        stored = run(self.net, [fix(0, 0, 1000, 0), fix(60, 0, 1300, 0)])
        stored[-1].step = None                         # as loaded: the newest row has no step yet
        self.history = stored
        self.first = stored[0]

    def test_newer_fixes_continue_the_chain_and_set_the_stored_rows_step(self):
        rows, updated = tp.thread(self.net, [fix(90, 0, 1450, 0), fix(120, 0, 1600, 0)], self.history, self.first)
        self.assertEqual([r.method for r in rows], ["window_v1", "window_v1"])
        self.assertEqual(updated, [self.history[-1]])
        self.assertEqual(updated[0].step, "along")
        self.assertEqual(rows[0].step, "along")
        self.assertIsNone(rows[1].step)

    def test_a_fix_older_than_the_newest_row_is_late(self):
        rows, updated = tp.thread(self.net, [fix(30, 0, 1150, 0)], self.history, self.first)
        self.assertEqual([(r.method, r.step) for r in rows], [("late", None)])
        self.assertEqual(rows[0].shape_id, "s")
        self.assertEqual(updated, [])

    def test_fixes_older_than_every_row_become_their_own_chain_ending_at_the_oldest(self):
        rows, updated = tp.thread(self.net, [fix(-90, 0, 550, 0), fix(-60, 0, 700, 0), fix(-30, 0, 850, 0)],
                                  self.history, self.first)
        self.assertEqual([r.method for r in rows], ["window_v1"] * 3)
        self.assertEqual([r.step for r in rows], ["along", "along", "along"])   # the last one steps to the first row
        self.assertAlmostEqual(rows[-1].step_speed_ms, 150 / 30)
        self.assertEqual(updated, [])

    def test_a_vehicle_with_no_rows_starts_fresh(self):
        rows, updated = tp.thread(self.net, [fix(0, 0, 100, 0), fix(30, 0, 250, 0)])
        self.assertEqual([r.step for r in rows], ["along", None])
        self.assertEqual(updated, [])


class FakeConn:
    def __init__(self):
        self.calls = []

    def commit(self):
        self.calls.append("commit")

    def rollback(self):
        self.calls.append("rollback")


class IsolationTest(unittest.TestCase):
    """The stream's call can't raise, and rolls back whatever a failing matcher left."""

    ROWS = [{"vehicle_id": "706", "ts": T0}]

    def test_a_matcher_that_raises_is_rolled_back_and_the_stream_carries_on(self):
        conn = FakeConn()

        def boom(c, fresh):
            self.assertEqual(fresh, {("706", T0)})
            raise RuntimeError("matcher bug")

        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertIsNone(vrt_realtime.match_progress(conn, self.ROWS, boom))
        self.assertEqual(conn.calls, ["rollback"])
        self.assertIn("positions are stored", out.getvalue())

    def test_a_working_matcher_returns_its_stats(self):
        self.assertEqual(vrt_realtime.match_progress(FakeConn(), self.ROWS, lambda c, fresh: {"rows": 1}), {"rows": 1})


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
VEHICLES = [f"wp7-test-{i}" for i in range(6)]
TRIP = "1_-_Regular_Service-Weekday-9-A-TO-0000-wp7test"


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (a package clone with migration 0007)")
class DatabaseTest(unittest.TestCase):
    """Against a real (scratch) database: positions are never lost, and the backfill and
    the stream's matcher, run at the same time, write each row once and in order."""

    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg = psycopg
        with psycopg.connect(DB_URL) as c:
            ok = c.execute("select to_regclass('obs.vehicle_progress') is not null").fetchone()[0]
            if not ok:
                raise unittest.SkipTest("obs.vehicle_progress is missing: apply migration 0007")
            shape = c.execute("""select shape_id from core.transit_shape where active and route_id = '9'
                                 order by ST_Length(geom::geography) desc limit 1""").fetchone()
            if not shape:
                raise unittest.SkipTest("no route 9 shape in this database")
            cls.shape = shape[0]
            vrt_realtime.db.ensure_source(c, vrt_realtime.SOURCE)

    def setUp(self):
        self.conn = self.psycopg.connect(DB_URL)
        self.cleanup()
        self.fetch_id = self.conn.execute("select coalesce(max(id), 0) from ops.fetch").fetchone()[0]
        self.base = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=2)

    def tearDown(self):
        self.cleanup()
        self.conn.execute("delete from ops.fetch where source = 'vrt_realtime' and id > %s", (self.fetch_id,))
        self.conn.commit()
        self.conn.close()

    def cleanup(self):
        self.conn.rollback()
        self.conn.execute("delete from obs.vehicle_progress where vehicle_id like 'wp7-test-%'")
        self.conn.execute("delete from obs.vehicle_position where vehicle_id like 'wp7-test-%'")
        self.conn.commit()

    def track(self, n, k):
        """Fix k of vehicle n: along route 9's shape at 3 m/s, stopped every 5th fix, a 200 s gap at fix 40."""
        moved = sum(1 for j in range(1, k + 1) if j % 5)
        secs = 30 * k + (170 if k >= 40 else 0)
        f = min(0.04 * n + moved * 90 / 10500, 0.999)
        lon, lat, az = self.conn.execute(
            """select ST_X(p), ST_Y(p),
                      degrees(ST_Azimuth(p::geography, ST_LineInterpolatePoint(g, least(%s + 0.0005, 1))::geography))
               from (select geom g, ST_LineInterpolatePoint(geom, %s) p from core.transit_shape where shape_id = %s) s""",
            (f, f, self.shape)).fetchone()
        return {"ts": self.base + timedelta(seconds=secs), "vehicle_id": VEHICLES[n], "vehicle_label": VEHICLES[n],
                "trip_id": TRIP, "route_id": "9", "lon": lon, "lat": lat, "bearing": az, "speed_ms": None,
                "stop_id": None, "stop_sequence": None, "status": None, "feed_ts": self.base + timedelta(seconds=secs)}

    def feed(self, rows):
        """A GTFS-realtime VehiclePositions snapshot carrying these fixes."""
        from google.transit import gtfs_realtime_pb2 as pb
        msg = pb.FeedMessage()
        msg.header.gtfs_realtime_version = "1.0"
        msg.header.timestamp = int(max(r["ts"] for r in rows).timestamp())
        for i, r in enumerate(rows):
            v = msg.entity.add(id=str(i)).vehicle
            v.vehicle.id, v.vehicle.label = r["vehicle_id"], r["vehicle_label"]
            v.trip.trip_id = r["trip_id"]
            v.position.latitude, v.position.longitude, v.position.bearing = r["lat"], r["lon"], r["bearing"]
            v.timestamp = int(r["ts"].timestamp())
        return msg.SerializeToString()

    def stored(self, table="obs.vehicle_position"):
        with self.psycopg.connect(DB_URL) as other:          # a separate session: sees only what's committed
            return other.execute(f"select count(*) from {table} where vehicle_id like 'wp7-test-%%'").fetchone()[0]

    LOOKUP = {"trips": {}, "short": {"9": "9"}}

    def test_a_matcher_that_raises_leaves_the_batch_stored_and_nothing_else(self):
        batch = [self.track(n, 0) for n in range(len(VEHICLES))]

        def boom(conn, fresh):
            conn.execute("insert into obs.vehicle_progress (vehicle_id, ts) values (%s, %s)",
                         (VEHICLES[0], batch[0]["ts"]))
            raise RuntimeError("matcher bug")

        with contextlib.redirect_stdout(io.StringIO()):
            n, stats = vrt_realtime.record_positions(self.conn, self.feed(batch), self.LOOKUP, matcher=boom)
        self.assertEqual((n, stats), (len(VEHICLES), None))
        self.assertEqual(self.stored(), len(VEHICLES))
        self.assertEqual(self.stored("obs.vehicle_progress"), 0)              # the matcher's write was rolled back
        n, stats = vrt_realtime.record_positions(self.conn, self.feed([self.track(n, 1) for n in range(6)]),
                                                 self.LOOKUP)                # the next batch matches both
        self.assertEqual(self.stored("obs.vehicle_progress"), 2 * len(VEHICLES))

    def test_a_matcher_that_sleeps_past_its_budget_leaves_the_batch_stored(self):
        batch = [self.track(n, 0) for n in range(len(VEHICLES))]
        seen = []

        def sleepy(conn, fresh):
            seen.append(self.stored())                       # committed before the matcher started
            time.sleep(tp.BUDGET_S + 0.5)
            return {"rows": 0}

        n, stats = vrt_realtime.record_positions(self.conn, self.feed(batch), self.LOOKUP, matcher=sleepy)
        self.assertEqual(seen, [len(VEHICLES)])
        self.assertEqual(self.stored(), len(VEHICLES))
        # The real matcher with no budget left defers everything; positions stay, and a later call catches up.
        self.assertGreaterEqual(tp.after_batch(self.conn, budget_s=0).get("deferred", 0), len(VEHICLES))
        self.assertEqual(self.stored("obs.vehicle_progress"), 0)
        tp.after_batch(self.conn)
        self.assertEqual(self.stored("obs.vehicle_progress"), len(VEHICLES))

    def test_the_stream_marks_its_own_batch_as_arrivals(self):
        old = [self.track(n, 0) for n in range(len(VEHICLES))]
        vrt_realtime.store_positions(self.conn, old)          # stored while matching was skipped
        self.conn.commit()
        batch = [self.track(n, 1) for n in range(len(VEHICLES))]
        n, stats = vrt_realtime.record_positions(self.conn, self.feed(batch), self.LOOKUP)
        rows = self.conn.execute("""select ts, backfill, method, route_source from obs.vehicle_progress
                                    where vehicle_id = %s order by ts""", (VEHICLES[0],)).fetchall()
        self.assertEqual([(r[1], r[2], r[3]) for r in rows], [(True, "window_v1", "trip"), (False, "window_v1", "trip")])

    def test_backfill_racing_the_stream_writes_each_row_once_and_in_order(self):
        total, backlog = 100, 60
        for k in range(backlog):
            vrt_realtime.store_positions(self.conn, [self.track(n, k) for n in range(len(VEHICLES))])
        self.conn.commit()
        later = [[self.track(n, k) for n in range(len(VEHICLES))] for k in range(backlog, total)]
        results, errors = [], []
        holding = threading.Event()
        logged = []

        def pause(msg):
            # Called once before the lock is taken, then after each commit while it's held.
            logged.append(msg)
            if len(logged) >= 2:
                holding.set()
            time.sleep(0.05)

        def stream():
            holding.wait(30)
            try:
                with self.psycopg.connect(DB_URL) as c:
                    for batch in later:
                        _, stats = vrt_realtime.record_positions(c, self.feed(batch), self.LOOKUP)
                        results.append(stats)
                        time.sleep(0.02)
            except Exception as e:                            # pragma: no cover - reported below
                errors.append(e)

        def backfill():
            try:
                with self.psycopg.connect(DB_URL) as c:
                    # Small chunks with a pause after each commit: the lock is held for a while.
                    tp.backfill(c, self.base - timedelta(minutes=1), log=pause, commit_every=40)
            except Exception as e:                            # pragma: no cover
                errors.append(e)
            finally:
                holding.set()

        threads = [threading.Thread(target=backfill), threading.Thread(target=stream)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(120)
        self.assertEqual(errors, [])
        tp.after_batch(self.conn)                             # whatever the last skipped batch left
        self.assertTrue(any(r and r.get("skipped (locked)") for r in results), "the two never overlapped")

        n_pos = self.stored()
        rows = self.conn.execute("""select vehicle_id, ts, shape_id, step, method from obs.vehicle_progress
                                    where vehicle_id like 'wp7-test-%' order by vehicle_id, ts""").fetchall()
        self.assertEqual(n_pos, len(VEHICLES) * total)
        self.assertEqual(len(rows), n_pos)                                   # one row per fix, none twice
        self.assertEqual(len({(r[0], r[1]) for r in rows}), n_pos)
        self.assertEqual({r[4] for r in rows}, {"window_v1"})                # nothing arrived out of order
        # The same fixes threaded in one pass give exactly the same steps.
        net = tp.network(self.conn)
        expected = {}
        for vid, fixes in tp.pending(self.conn, self.base - timedelta(days=1)).items():
            if vid.startswith("wp7-test-"):
                self.fail(f"{vid} still has {len(fixes)} unmatched fixes")
        for vid in VEHICLES:
            fixes = [tp.Fix(v, ts, x, y, b, trip, route, "trip", None, None) for v, ts, x, y, b, trip, route in
                     self.conn.execute(f"""select vehicle_id, ts, ST_X(ST_Transform(geom, {tp.UTM})),
                                             ST_Y(ST_Transform(geom, {tp.UTM})), bearing, trip_id, route_id
                                           from obs.vehicle_position where vehicle_id = %s order by ts""", (vid,))]
            for r in run(net, fixes):
                expected[(r.vehicle_id, r.ts)] = (r.shape_id, r.step)
        got = {(r[0], r[1]): (r[2], r[3]) for r in rows}
        self.assertEqual(got, expected)
        kinds = {s for _, s in got.values()}
        self.assertTrue({"along", "still", "gap"} <= kinds, kinds)


if __name__ == "__main__":
    unittest.main()
