"""The hazards sources' store steps against a real (scratch) database: raw.record versions,
snapshot refusals and evt.event lifecycles.

Runs only with TVT_TEST_DATABASE_URL set to a scratch database with core's migrations
(0001 and 0009 are the ones used), inside a transaction that is rolled back. Each test
stores under a test-only source name, so real rows of these sources are never touched.

Run: TVT_TEST_DATABASE_URL=... python3 -m unittest discover -s plugins/hazards/tests -t .
"""

import copy
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from ingest import db
from plugins.hazards.ingest.sources import idl_fire_restrictions as idl
from plugins.hazards.ingest.sources import nasa_firms as firms
from plugins.hazards.ingest.sources import nifc_wfigs_incidents as inc
from plugins.hazards.ingest.sources import nifc_wfigs_perimeters as per
from plugins.hazards.ingest.sources import nws_wwa as nws
from plugins.hazards.ingest.sources import usgs_quakes as quakes

DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
UTC = timezone.utc
T0 = datetime(2026, 8, 10, 20, tzinfo=UTC)


def load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read() if name.endswith(".csv") else json.load(f)


def ms(t):
    return int(t.timestamp() * 1000)


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (core migrations 0001 and 0009)")
class DatabaseTest(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.conn = psycopg.connect(DB_URL)
        if not self.conn.execute("select to_regclass('evt.event') is not null").fetchone()[0]:
            self.conn.close()
            self.skipTest("evt.event is missing: apply migration 0009")

    def tearDown(self):
        if not self.conn.closed:
            self.conn.rollback()
            self.conn.close()

    def as_test(self, module):
        """Store under a test-only source name."""
        name = "test_" + module.SOURCE["name"]
        patch = mock.patch.dict(module.SOURCE, {"name": name})
        patch.start()
        self.addCleanup(patch.stop)
        db.ensure_source(self.conn, module.SOURCE)
        return name

    def events(self, source):
        return {r[0]: r[1:] for r in self.conn.execute(
            """select source_id, active, upper(observed), upper(declared), kind from evt.event where source = %s""",
            (source,)).fetchall()}

    def current(self, source):
        return self.conn.execute("""select count(*) from raw.record where source = %s and removed_at is null""",
                                 (source,)).fetchone()[0]

    def test_idl_stages_open_and_close_and_a_small_snapshot_is_refused(self):
        name = self.as_test(idl)
        fs = load("idl_zones.json")["features"]
        stats = idl.store(self.conn, None, T0, idl.parse(fs))
        self.assertEqual((stats["zones"], stats["record versions new"], stats["in force"], stats["events new"]), (3, 3, 1, 2))
        self.assertEqual({k: v[0] for k, v in self.events(name).items()},
                         {"{00000000-0000-4000-8000-00000000000A}|Stage I|2026-07-15T14:00:00Z": True,
                          "{00000000-0000-4000-8000-00000000000A}|upcoming|Stage II": True})
        geom = self.conn.execute("""select ST_GeometryType(geom), ST_IsValid(geom) from raw.record
                                    where source = %s and source_id like '%%0B}'""", (name,)).fetchone()
        self.assertEqual(geom, ("ST_MultiPolygon", True))
        # Back to None: both lifecycles close; the zone gets a new version.
        t1 = T0 + timedelta(days=30)
        fs[0]["attributes"].update({"Stage": "None", "UpcomingStage": None, "last_edited_date": ms(t1)})
        stats = idl.store(self.conn, None, t1, idl.parse(fs))
        self.assertEqual((stats["record versions new"], stats["removed"], stats["events gone"]), (1, 1, 2))
        self.assertTrue(all(not active and upper == t1 for active, upper, _, _ in self.events(name).values()))
        self.assertEqual(self.current(name), 3)
        with self.assertRaises(RuntimeError):
            idl.store(self.conn, None, t1 + timedelta(hours=1), idl.parse(fs[:1]))

    def incident(self, name, **attrs):
        f = copy.deepcopy(next(f for f in load("wfigs_incidents.json")["features"]
                               if f["attributes"]["IncidentName"] == name))
        f["attributes"].update(attrs)
        return f

    def test_wfigs_fire_lifecycles(self):
        name = self.as_test(inc)
        discovered = ms(T0 - timedelta(days=2))
        woodridge = self.incident("WOODRIDGE", FireOutDateTime=None, IncidentSize=400, FireDiscoveryDateTime=discovered,
                                  ModifiedOnDateTime_dt=ms(T0 - timedelta(hours=1)))
        rx = self.incident("RX HIGH VALLEY", ModifiedOnDateTime_dt=ms(T0 - timedelta(hours=2)))
        bulldog = self.incident("BULLDOG")                                     # already out when first seen
        parsed = inc.parse([woodridge, rx, bulldog])
        stats = inc.store(self.conn, None, T0, parsed)
        self.assertEqual((stats["record versions new"], stats["events new"], stats["active fires"]), (3, 2, 2))
        bulldog_id = bulldog["attributes"]["IrwinID"].upper()
        self.assertNotIn(bulldog_id, self.events(name))
        # The same read again changes nothing.
        stats = inc.store(self.conn, None, T0 + timedelta(minutes=10), parsed)
        self.assertEqual((stats["record versions new"], stats["unchanged"], stats["events changed"]), (0, 3, 0))
        # Nothing read for a day: rebuilt from raw.record (geometry round trip), still the same.
        stats = inc.store(self.conn, None, T0 + timedelta(days=1), {})
        self.assertEqual((stats["events new"], stats["events changed"], stats["events closed"]), (0, 0, 0))
        # Five days on, the prescribed fire has gone quiet (3-day window); Woodridge (400 acres) hasn't.
        t5 = T0 + timedelta(days=5)
        stats = inc.store(self.conn, None, t5, {})
        rx_id = rx["attributes"]["IrwinID"].upper()
        wood_id = woodridge["attributes"]["IrwinID"].upper()
        events = self.events(name)
        self.assertEqual((stats["events closed"], events[rx_id][:2], events[wood_id][0]), (1, (False, t5), True))
        # Woodridge is declared out: closed, with the out time as declared's end.
        out = T0 + timedelta(days=6)
        t6 = out + timedelta(minutes=5)
        done = inc.parse([self.incident("WOODRIDGE", FireOutDateTime=ms(out), IncidentSize=410,
                                        FireDiscoveryDateTime=discovered, ModifiedOnDateTime_dt=ms(out))])
        stats = inc.store(self.conn, None, t6, done)
        self.assertEqual((stats["record versions new"], stats["events closed"], stats["active fires"]), (1, 1, 0))
        self.assertEqual(self.events(name)[wood_id][:3], (False, t6, out))
        self.assertEqual(self.conn.execute("select count(*) from raw.record where source = %s and source_id = %s",
                                           (name, wood_id)).fetchone()[0], 2)

    def test_wfigs_perimeters_keep_every_version(self):
        name = self.as_test(per)
        f = copy.deepcopy(next(f for f in load("wfigs_perimeters.json")["features"]
                               if f["attributes"]["poly_IncidentName"] == "HARTLEY"))
        f["attributes"].update({"attr_FireOutDateTime": None, "poly_DateCurrent": ms(T0 - timedelta(hours=1))})
        parsed, _ = per.parse([f])
        stats = per.store(self.conn, None, T0, parsed)
        self.assertEqual((stats["record versions new"], stats["events new"]), (1, 1))
        stats = per.store(self.conn, None, T0 + timedelta(hours=1), {})       # rebuilt from the database
        self.assertEqual((stats["events changed"], stats["events closed"]), (0, 0))
        moved = copy.deepcopy(f)                                               # remapped 40 m east
        moved["geometry"]["rings"] = [[[x + 0.0005, y] for x, y in ring] for ring in f["geometry"]["rings"]]
        moved["attributes"]["poly_DateCurrent"] = ms(T0 + timedelta(hours=2))
        stats = per.store(self.conn, None, T0 + timedelta(hours=2), per.parse([moved])[0])
        self.assertEqual((stats["record versions new"], stats["events changed"]), (1, 1))
        self.assertEqual(self.conn.execute("""select count(*), min(ST_GeometryType(geom)) from raw.record
                                              where source = %s""", (name,)).fetchone(), (2, "ST_Polygon"))

    def test_nws_snapshots(self):
        name = self.as_test(nws)
        parsed, dropped = nws.parse(load("nws_wwa.json")["features"])
        stats = nws.store(self.conn, None, T0, parsed)
        self.assertEqual((stats["alerts"], stats["events new"], dropped), (3, 3, 1))
        self.assertEqual(self.conn.execute("""select count(*) from raw.record where source = %s
                                              and payload::text ilike '%%abduction%%'""", (name,)).fetchone()[0], 0)
        self.assertEqual(nws.active_events(self.conn)["KBOI.FW.W.0012.2026"], datetime(2026, 8, 11, 3, tzinfo=UTC))
        t1 = T0 + timedelta(hours=8)
        stats = nws.store(self.conn, None, t1, {})                            # all expired: an empty snapshot
        self.assertEqual((stats["removed"], stats["events gone"]), (3, 3))
        self.assertEqual(self.current(name), 0)

    def test_firms_and_quakes_are_occurrences(self):
        name = self.as_test(firms)
        parsed = firms.parse("viirs_noaa20", load("firms_viirs_24h.csv"))
        self.assertEqual(firms.store(self.conn, None, T0, parsed), {"detections in the ring": 2, "new": 2, "seen again": 0})
        self.assertEqual(firms.store(self.conn, None, T0 + timedelta(hours=1), {})["new"], 0)
        self.assertEqual(firms.store(self.conn, None, T0 + timedelta(hours=1), parsed)["seen again"], 2)
        self.assertEqual(self.current(name), 2)                               # never retired

        qname = self.as_test(quakes)
        feed = load("usgs_quakes.geojson")
        quakes.store(self.conn, None, T0, quakes.parse(feed))
        moved = copy.deepcopy(feed)
        event = next(f for f in moved["features"] if f["id"] == "zz9000test1")
        event["id"] = "yy1234test"                                            # USGS changed its preferred ID
        stats = quakes.store(self.conn, None, T0 + timedelta(hours=1), quakes.parse(moved))
        self.assertEqual(stats["versions new"], 1)
        ids = [r[0] for r in self.conn.execute("select distinct source_id from raw.record where source = %s order by 1",
                                               (qname,)).fetchall()]
        self.assertEqual(ids, ["zz9000test1", "zz9000test2"])
        self.assertEqual(self.conn.execute("select ST_NDims(geom) from raw.record where source = %s limit 1",
                                           (qname,)).fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
