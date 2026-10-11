"""Tests for the burn scars (burn_scars.py, hazards/0001): which perimeter version a fire is drawn from, which fires
are drawn, the fade over three growing seasons, and the refresh against a database.

Every record here is synthetic: made-up fires with WFIGS's field names, no real perimeter. The database tests run
only with TVT_TEST_DATABASE_URL set to a scratch database with core's migrations (0001, 0020; 0021 for the build's
marks and runs) and hazards/0001, inside a transaction that's rolled back (the build's commits become savepoints),
under a test-only source, layer and build name.

Run: python3 -m unittest discover -s plugins/hazards/tests -t .
"""

import json
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

from ingest import builds, manifest, seasons
from ingest.db import version_hash
from plugins.hazards.ingest import burn_scars as bs
from plugins.hazards.ingest.sources import nifc_wfigs_perimeters as per

DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
UTC = timezone.utc
TODAY = date(2026, 10, 11)
T0 = datetime(2026, 10, 11, 18, tzinfo=UTC)


def ms(t):
    return int(t.timestamp() * 1000)


def payload(irwin="{00000000-0000-4000-8000-0000000000A1}", name="SYNTH ONE", final=True, type_="WF",
            discovered=datetime(2026, 7, 6, 20, tzinfo=UTC), acres=120.5, **kw):
    """A made-up perimeter payload, as the poller stores it (empty values left out)."""
    p = {"poly_IRWINID": irwin, "poly_IncidentName": name,
         "poly_FeatureCategory": "Wildfire Final Fire Perimeter" if final else "Wildfire Daily Fire Perimeter",
         "attr_IncidentTypeCategory": type_, "attr_FireDiscoveryDateTime": ms(discovered) if discovered else None,
         "poly_GISAcres": acres, "poly_MapMethod": "Infrared Image",
         "poly_PolygonDateTime": ms(datetime(2026, 7, 9, 3, tzinfo=UTC)),
         "poly_DateCurrent": ms(datetime(2026, 7, 9, 4, tzinfo=UTC)), "_geom": "synthetic"}
    p.update(kw)
    return {k: v for k, v in p.items() if v is not None}


def version(p, seen=T0, first=None, near=True, sid=None):
    return bs.Version(sid or p.get("poly_IRWINID", "X").upper(), version_hash(p), p, first or seen, seen, near)


class ManifestTest(unittest.TestCase):
    def test_the_layer_carries_the_perimeters_licence(self):
        hazards = next(p for p in manifest.find() if p.name == "hazards")
        entries = {e["name"]: e for e in hazards.manifest["sources"]}
        self.assertEqual(bs.REPUBLISH, entries["nifc_wfigs_perimeters"]["republish"])
        self.assertEqual((bs.LICENSE, bs.CREDIT), (per.SOURCE["license"], per.SOURCE["credit"]))

    def test_it_is_a_build_run_by_hand_never_a_scheduled_source(self):
        # Plan §0 item 27 (M1): builds never run inside `ingest serve`; the poller marks this one.
        hazards = next(p for p in manifest.find() if p.name == "hazards")
        self.assertNotIn("burn_scars", [e["name"] for e in hazards.manifest["sources"]])
        self.assertFalse(hasattr(bs, "SOURCE") or hasattr(bs, "run"))
        commands = {c["name"]: c["module"] for c in hazards.manifest["commands"]}
        self.assertEqual((bs.BUILD, commands[bs.BUILD]), ("burn-scars", "ingest.burn_scars"))
        builds.check_name(bs.BUILD)
        with mock.patch.dict(os.environ, {builds.SERVE_ENV: "1"}):
            with self.assertRaisesRegex(RuntimeError, "never run inside `ingest serve`"):
                bs.build(object())                     # refused before it touches a database

    def test_a_runs_note_says_what_it_did_and_what_it_left_out(self):
        stats = {"as of": "2026-10-11", "fires": 3, "scars": 2, "shown": 2, "written": 1, "deleted": 0,
                 "unchanged": 1, "version": "v1", "left out (geometry error)": 1, "problems": "X ({0-X}): boom"}
        self.assertEqual(bs.note_of(stats), "as of 2026-10-11, scars 2, shown 2, written 1, deleted 0, version v1, "
                                            "left out (geometry error) 1, problems X ({0-X}): boom")
        self.assertEqual(len(bs.note_of({**stats, "problems": "x" * 5000})), bs.NOTE_MAX)

    def test_box_is_the_grounds(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "..", "..", "basemap", "ground", "spec.json")) as f:
            self.assertEqual(list(bs.BOX), json.load(f)["grid"]["lonlat"])


class PickTest(unittest.TestCase):
    def test_a_final_perimeter_beats_a_newer_daily_one(self):
        final = version(payload(final=True), seen=T0)
        daily = version(payload(final=False, poly_GISAcres=99), seen=T0 + timedelta(days=3))
        self.assertIs(bs.pick([daily, final]), final)

    def test_the_newest_final_wins_then_the_newest_daily(self):
        old = version(payload(poly_GISAcres=100), seen=T0)
        new = version(payload(poly_GISAcres=110), seen=T0 + timedelta(hours=1))
        self.assertIs(bs.pick([new, old]), new)
        d1 = version(payload(final=False, poly_GISAcres=5), seen=T0)
        d2 = version(payload(final=False, poly_GISAcres=6), seen=T0 + timedelta(hours=1))
        self.assertIs(bs.pick([d2, d1]), d2)

    def test_a_tie_on_last_seen_goes_to_the_later_first_seen(self):
        a = version(payload(poly_GISAcres=1), seen=T0, first=T0 - timedelta(days=2))
        b = version(payload(poly_GISAcres=2), seen=T0, first=T0 - timedelta(days=1))
        self.assertIs(bs.pick([a, b]), b)


class RulesTest(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(bs.kind_of(payload(type_="WF")), "wildfire")
        self.assertEqual(bs.kind_of(payload(type_="rx")), "prescribed")
        self.assertIsNone(bs.kind_of(payload(type_="CX")))           # a complex: its fires carry their own
        self.assertIsNone(bs.kind_of(payload(type_="FA")))
        self.assertEqual(bs.kind_of(payload(type_=None)), "wildfire")  # from the feature category
        self.assertEqual(bs.kind_of(payload(type_=None, poly_FeatureCategory="Prescribed Fire")), "prescribed")
        self.assertIsNone(bs.kind_of(payload(type_=None, poly_FeatureCategory="Other")))

    def test_the_burn_day_is_the_discovery_day_in_boise(self):
        late = payload(discovered=datetime(2025, 8, 1, 3, 30, tzinfo=UTC))    # Jul 31, 21:30 MDT
        self.assertEqual(bs.burn_day(late), (date(2025, 7, 31), "discovery"))
        undiscovered = payload(discovered=None)
        self.assertEqual(bs.burn_day(undiscovered), (date(2026, 7, 8), "perimeter"))   # Jul 9 03:00 UTC
        self.assertEqual(bs.burn_day(payload(discovered=None, poly_PolygonDateTime=None, poly_DateCurrent=None)),
                         (None, None))

    def test_a_fire_counts_from_the_day_after_the_photos_last_flight(self):
        self.assertEqual(bs.PHOTO_LAST_DAY, date(2025, 7, 24))
        on_the_day = version(payload(discovered=datetime(2025, 7, 25, 5, 59, tzinfo=UTC)))   # Jul 24 MDT
        after = version(payload(discovered=datetime(2025, 7, 25, 6, 0, tzinfo=UTC)))         # Jul 25 MDT
        self.assertEqual(bs.scar_of(on_the_day, TODAY), (None, "before the photo"))
        row, why = bs.scar_of(after, TODAY)
        self.assertIsNone(why)
        self.assertEqual(row["burned_on"], date(2025, 7, 25))

    def test_what_is_left_out(self):
        cases = {
            "withdrawn": [payload(attr_IsValid=0), payload(poly_DeleteThis="Yes"), payload(poly_IsVisible="No")],
            "not a wildfire or prescribed fire": [payload(type_="CX")],
            "no date": [payload(discovered=None, poly_PolygonDateTime=None, poly_DateCurrent=None)],
        }
        for why, ps in cases.items():
            for p in ps:
                self.assertEqual(bs.scar_of(version(p), TODAY), (None, why))
        self.assertEqual(bs.scar_of(version(payload(), near=False), TODAY), (None, "outside the box"))

    def test_a_scars_row(self):
        row, _ = bs.scar_of(version(payload(acres=None, attr_IncidentSize=42)), TODAY)
        self.assertEqual({k: row[k] for k in ("fire_id", "name", "kind", "burned_on", "dated_by", "perimeter",
                                               "acres", "map_method", "seasons", "fade_1_on", "fade_2_on", "gone_on")},
                         {"fire_id": "{00000000-0000-4000-8000-0000000000A1}", "name": "SYNTH ONE", "kind": "wildfire",
                          "burned_on": date(2026, 7, 6), "dated_by": "discovery", "perimeter": "final", "acres": 42.0,
                          "map_method": "Infrared Image", "seasons": 0, "fade_1_on": date(2027, 11, 1),
                          "fade_2_on": date(2028, 11, 1), "gone_on": date(2029, 11, 1)})
        self.assertEqual(row["perimeter_at"], datetime(2026, 7, 9, 3, tzinfo=UTC))
        daily, _ = bs.scar_of(version(payload(final=False)), TODAY)
        self.assertEqual(daily["perimeter"], "daily")             # a fire with no final perimeter yet is drawn


class FadeTest(unittest.TestCase):
    def test_three_whole_growing_seasons_after_the_fire(self):
        for burned, first in [(date(2025, 7, 31), 2026),    # mid-season: next year's is the first whole one
                              (date(2025, 12, 31), 2026),
                              (date(2026, 3, 31), 2026),    # before the season: this year's counts (7 months)
                              (date(2026, 4, 1), 2027),     # on its first day: it doesn't (19 months)
                              (date(2026, 10, 31), 2027),
                              (date(2026, 11, 1), 2027)]:
            with self.subTest(burned):
                self.assertEqual(bs.fade_steps(burned), [date(first + k, 11, 1) for k in range(3)])

    def test_seasons_and_fade_by_day(self):
        steps = bs.fade_steps(date(2025, 7, 31))
        for day, n in [(date(2026, 10, 31), 0), (date(2026, 11, 1), 1), (date(2027, 10, 31), 1),
                       (date(2027, 11, 1), 2), (date(2028, 11, 1), 3), (date(2031, 1, 1), 3)]:
            self.assertEqual(bs.seasons_passed(steps, day), n, day)
        self.assertEqual([bs.fade(n) for n in range(4)], [1.0, 2 / 3, 1 / 3, 0.0])

    def test_the_season_is_data(self):
        with open(bs.GROWING_FILE, encoding="utf-8") as f:
            self.assertIn("⚠️", f.read())                     # an estimate, marked as one
        self.assertEqual(seasons.state_at(bs.growing(), datetime(2026, 7, 4, 12)).value, "growing")
        self.assertIsNone(seasons.state_at(bs.growing(), datetime(2026, 12, 4, 12)).value)
        shorter = seasons.parse([{"level": "seasonal", "value": "growing", "yearly": {"start": "05-01", "end": "09-30"}}])
        self.assertEqual(bs.fade_steps(date(2026, 4, 15), shorter), [date(2026 + k, 10, 1) for k in range(3)])
        ended = seasons.parse([{"level": "seasonal", "value": "growing", "yearly": {"start": "04-01", "end": "10-31"},
                                "dates": {"end": "2027-12-31"}}])
        with self.assertRaises(ValueError):
            bs.fade_steps(date(2026, 7, 1), ended)

    def test_a_step_changes_the_content_and_nothing_else_does(self):
        v = version(payload())
        a, _ = bs.scar_of(v, date(2027, 10, 31))
        b, _ = bs.scar_of(v, date(2027, 10, 31))
        c, _ = bs.scar_of(v, date(2027, 11, 1))
        self.assertEqual(a["content_hash"], b["content_hash"])
        self.assertNotEqual(a["content_hash"], c["content_hash"])
        moved, _ = bs.scar_of(version(payload(_geom="moved")), date(2027, 10, 31))   # a new record version
        self.assertNotEqual(a["content_hash"], moved["content_hash"])


class PlanTest(unittest.TestCase):
    def rows(self, *ids):
        return {i: {"fire_id": i, "content_hash": i.encode()} for i in ids}

    def test_only_changes_are_written(self):
        held = {"A": b"A", "B": b"old", "C": b"C"}
        write, delete, unchanged = bs.plan(held, self.rows("A", "B", "D"))
        self.assertEqual([r["fire_id"] for r in write], ["B", "D"])
        self.assertEqual((delete, unchanged), (["C"], 1))

    def test_mass_deletes_are_refused(self):
        bs.check_drops(5, 6)                       # under the floor
        bs.check_drops(10, 20)                     # half
        with self.assertRaises(RuntimeError):
            bs.check_drops(11, 20)
        bs.check_drops(11, 20, force=True)


# --- against a database ------------------------------------------------------------------------------

def square(lon, lat, d=0.01):
    return {"type": "Polygon", "coordinates": [[[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d],
                                                 [lon, lat]]]}


BOWTIE = {"type": "Polygon", "coordinates": [[[-116.30, 43.50], [-116.28, 43.52], [-116.28, 43.50],
                                              [-116.30, 43.52], [-116.30, 43.50]]]}   # self-intersecting
# A fire with a zero-area sliver beside its main part, as some published perimeters have (MakeValid's default method
# gave null for two such on the server's GEOS 3.10, Oct 11, 2026).
SLIVER = {"type": "MultiPolygon", "coordinates": [
    square(-116.10, 43.40)["coordinates"],
    [[[-116.05, 43.40], [-116.04, 43.40], [-116.03, 43.40], [-116.04, 43.40], [-116.05, 43.40]]]]}


class Tx:
    """A connection whose commit() and rollback() stay inside the test's transaction, as savepoints (as in
    ingest/tests/test_builds.py), so a build run, which commits, leaves nothing behind."""

    def __init__(self, conn):
        self.conn = conn
        conn.execute("savepoint tvt_test")

    def execute(self, sql, params=None):
        return self.conn.execute(sql, params)

    def transaction(self):
        return self.conn.transaction()

    def commit(self):
        self.conn.execute("release savepoint tvt_test")
        self.conn.execute("savepoint tvt_test")

    def rollback(self):
        self.conn.execute("rollback to savepoint tvt_test")


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (core 0001, 0020 and hazards/0001)")
class RefreshDatabaseTest(unittest.TestCase):
    SOURCE = "test_nifc_wfigs_perimeters"
    LAYER = "hazards.test_burn_scars"
    BUILD = "test-burn-scars"

    def setUp(self):
        import psycopg
        from ingest import db
        self.conn = psycopg.connect(DB_URL)
        missing = bs.ready(self.conn)
        if missing:
            self.conn.close()
            self.skipTest(missing)
        db.ensure_source(self.conn, {**per.SOURCE, "name": self.SOURCE, "schedule": None})
        self.conn.execute("delete from hazards.burn_scar")         # rolled back with the rest
        self.n = 0

    def tearDown(self):
        if not self.conn.closed:
            self.conn.rollback()
            self.conn.close()

    def add(self, p, geom, seen=T0):
        self.n += 1
        sid = p["poly_IRWINID"].upper()
        self.conn.execute(
            """insert into raw.record (source, source_id, version_hash, payload, geom, first_seen, last_seen)
               values (%s, %s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s, %s)""",
            (self.SOURCE, sid, version_hash(p), json.dumps(p), json.dumps(geom), seen, seen))
        return sid

    def refresh(self, today=TODAY, **kw):
        return bs.refresh(self.conn, today=today, now=T0, source=self.SOURCE, layer=self.LAYER, **kw)

    def scars(self):
        return {r[0]: r[1:] for r in self.conn.execute(
            """select fire_id, seasons, fade, clipped, ST_GeometryType(geom), ST_IsValid(geom), ST_IsValid(geom_lo),
                      perimeter
               from hazards.burn_scar""").fetchall()}

    def versions(self):
        return self.conn.execute("select version, features from core.layer_version where layer = %s order by id",
                                 (self.LAYER,)).fetchall()

    def tx(self):
        """The connection for a build run (its commits as savepoints); skips without migration 0021."""
        if bs.ready(self.conn, build=True):
            self.skipTest("ops.build_run is missing: apply migration 0021")
        return Tx(self.conn)

    def pending(self):
        return {r[0]: r[1:] for r in self.conn.execute(
            "select marked_by, marks, reason from ops.build_pending where build = %s", (self.BUILD,)).fetchall()}

    def runs(self):
        return self.conn.execute("select ok, note, error from ops.build_run where build = %s order by id",
                                 (self.BUILD,)).fetchall()

    def build(self, conn, today=TODAY, **kw):
        return bs.build(conn, name=self.BUILD, today=today, now=T0, source=self.SOURCE, layer=self.LAYER, **kw)

    def test_new_versions_and_a_step_that_has_come_mark_the_build(self):
        self.tx()
        self.add(payload(irwin="{0-A}"), square(-116.40, 43.60))
        self.refresh()                                                     # seasons 0, as of TODAY
        self.assertEqual(bs.mark(self.conn, "test_poller", now=T0, name=self.BUILD), {})
        key = f"{self.BUILD} marked"
        self.assertEqual(bs.mark(self.conn, "test_poller", new=2, now=T0, name=self.BUILD),
                         {key: "2 new perimeter versions"})
        self.assertEqual(self.pending(), {"test_poller": (1, "2 new perimeter versions")})
        self.conn.execute("delete from ops.build_pending where build = %s", (self.BUILD,))
        step = datetime(2027, 11, 1, 18, tzinfo=UTC)                       # the scar's first step has come
        self.assertEqual(bs.mark(self.conn, "test_poller", now=step, name=self.BUILD),
                         {key: "1 scar due a fade step as of 2027-11-01"})
        self.assertEqual(bs.mark(self.conn, "test_poller", now=step, name=self.BUILD), {})   # once, while marked
        self.assertEqual(bs.mark(self.conn, "test_poller", new=1, now=step, name=self.BUILD),
                         {key: "1 new perimeter version; 1 scar due a fade step as of 2027-11-01"})
        self.assertEqual(self.pending()["test_poller"][0], 2)               # new data still counts

    def test_the_build_runs_by_hand_logs_its_run_and_clears_its_marks(self):
        tx = self.tx()
        self.add(payload(irwin="{0-A}"), square(-116.40, 43.60))
        builds.mark(tx, self.BUILD, by="test_poller", reason="1 new perimeter version")
        stats = self.build(tx)
        self.assertEqual((stats["written"], stats["scars"]), (1, 1))
        self.assertEqual(self.pending(), {})
        (ok, note, error), = self.runs()
        self.assertEqual((ok, error), (True, None))
        self.assertTrue(note.startswith(f"as of {TODAY}, scars 1, shown 1, written 1, deleted 0, version "), note)

    def test_a_build_out_of_time_marks_itself_for_the_rest(self):
        tx = self.tx()
        self.add(payload(irwin="{0-A}"), square(-116.40, 43.60))
        builds.mark(tx, self.BUILD, by="test_poller", reason="1 new perimeter version")
        stats = self.build(tx, budget_s=0)
        self.assertEqual((stats["written"], stats[bs.DEFERRED]), (0, 1))
        self.assertEqual(self.pending(), {self.BUILD: (1, "1 scar left for the next run (out of time)")})
        self.assertIn(f"{bs.DEFERRED} 1", self.runs()[-1][1])
        self.assertEqual(self.build(tx)["written"], 1)                     # the next run takes the rest
        self.assertEqual(self.pending(), {})

    def test_a_failed_build_keeps_its_marks_and_its_scars(self):
        tx = self.tx()
        for i in range(12):
            self.add(payload(irwin=f"{{0-{i:02d}}}"), square(-116.6 + i * 0.02, 43.6))
        self.build(tx)
        self.conn.execute("update raw.record set removed_at = %s where source = %s and source_id <> %s",
                          (T0, self.SOURCE, "{0-00}"))
        builds.mark(tx, self.BUILD, by="test_poller", reason="11 fires removed")
        with self.assertRaises(RuntimeError):
            self.build(tx)                                                 # most scars would go: refused
        self.assertEqual(self.pending(), {"test_poller": (1, "11 fires removed")})
        self.assertEqual(self.runs()[-1][0], False)
        self.assertIn("refused", self.runs()[-1][2])
        self.assertEqual(len(self.scars()), 12)

    def test_a_refresh_draws_the_box_s_fires_after_the_photo_and_records_a_version(self):
        inside = self.add(payload(irwin="{0-A}"), square(-116.40, 43.60))
        edge = self.add(payload(irwin="{0-B}", name="EDGE"), square(-115.96, 43.60, 0.05))     # crosses the east edge
        self.add(payload(irwin="{0-C}", name="AWAY"), square(-115.80, 43.60))                  # in the ring, not the box
        self.add(payload(irwin="{0-D}", name="OLD", discovered=datetime(2025, 7, 1, tzinfo=UTC)), square(-116.5, 43.5))
        bowtie = self.add(payload(irwin="{0-E}", name="BOWTIE"), BOWTIE)
        sliver = self.add(payload(irwin="{0-F}", name="SLIVER"), SLIVER)
        stats = self.refresh()
        self.assertEqual((stats["fires"], stats["scars"], stats["shown"], stats["written"], stats["deleted"]),
                         (6, 4, 4, 4, 0))
        self.assertEqual((stats["left out (outside the box)"], stats["left out (before the photo)"]), (1, 1))
        scars = self.scars()
        self.assertEqual(set(scars), {inside, edge, bowtie, sliver})
        parts = self.conn.execute("select ST_NumGeometries(geom) from hazards.burn_scar where fire_id = %s",
                                  (sliver,)).fetchone()[0]
        self.assertEqual(parts, 1)                                  # the sliver is nothing
        for fid, (n, f, clipped, kind, valid, valid_lo, perimeter) in scars.items():
            self.assertEqual((n, f, kind, valid, valid_lo, perimeter), (0, 1.0, "ST_MultiPolygon", True, True, "final"))
            self.assertEqual(clipped, fid == edge)
        east = self.conn.execute("select ST_XMax(geom) from hazards.burn_scar where fire_id = %s", (edge,)).fetchone()[0]
        self.assertAlmostEqual(east, bs.BOX[2], places=9)
        self.assertEqual(self.versions()[-1][1], 4)
        self.assertEqual(stats["version"], self.versions()[-1][0])

    def test_an_unchanged_refresh_writes_nothing_and_a_step_writes_a_new_version(self):
        self.add(payload(irwin="{0-A}"), square(-116.40, 43.60))
        self.refresh()
        again = self.refresh()
        self.assertEqual((again["written"], again["unchanged"], again["version"]), (0, 1, "unchanged"))
        self.assertEqual(len(self.versions()), 1)
        stepped = self.refresh(today=date(2027, 11, 1))
        self.assertEqual(stepped["written"], 1)
        self.assertEqual(len(self.versions()), 2)
        (n, f, *_), = self.scars().values()
        self.assertEqual(n, 1)
        self.assertAlmostEqual(f, 2 / 3, places=6)
        gone = self.refresh(today=date(2029, 11, 1))
        self.assertEqual((gone["scars"], gone["shown"]), (1, 0))                  # kept, but not shown
        self.assertEqual(self.conn.execute("select count(*) from hazards.burn_scar_shown").fetchone()[0], 0)
        self.assertEqual(self.versions()[-1][1], 0)

    def test_an_empty_first_refresh_still_versions_the_layer(self):
        stats = self.refresh()
        self.assertEqual((stats["scars"], stats["written"]), (0, 0))
        self.assertEqual(len(self.versions()), 1)
        self.assertEqual(self.refresh()["version"], "unchanged")

    def test_a_new_perimeter_redraws_and_a_withdrawn_fire_goes(self):
        fid = self.add(payload(irwin="{0-A}", final=False), square(-116.40, 43.60))
        self.add(payload(irwin="{0-B}"), square(-116.20, 43.60))
        self.refresh()
        self.add(payload(irwin="{0-A}", final=True, poly_GISAcres=200, _geom="bigger"),
                 square(-116.40, 43.60, 0.02), seen=T0 + timedelta(hours=1))
        self.add(payload(irwin="{0-B}", attr_IsValid=0, _geom="gone"), square(-116.20, 43.60),
                 seen=T0 + timedelta(hours=1))
        stats = self.refresh()
        self.assertEqual((stats["written"], stats["deleted"], stats["left out (withdrawn)"]), (1, 1, 1))
        self.assertEqual(set(self.scars()), {fid})
        self.assertEqual(self.scars()[fid][-1], "final")
        self.assertEqual(len(self.versions()), 2)

    def test_a_box_that_overlaps_is_not_enough(self):
        # An L around the box's north-east corner: its bounding box overlaps the map box, its outline doesn't.
        west, south, east, north = bs.BOX
        ell = {"type": "Polygon", "coordinates": [[[east + 0.01, north - 0.05], [east + 0.02, north - 0.05],
                                                   [east + 0.02, north + 0.02], [east - 0.05, north + 0.02],
                                                   [east - 0.05, north + 0.01], [east + 0.01, north + 0.01],
                                                   [east + 0.01, north - 0.05]]]}
        self.add(payload(irwin="{0-L}", name="ELL"), ell)
        self.add(payload(irwin="{0-A}"), square(-116.40, 43.60))
        stats = self.refresh()
        self.assertEqual((stats["written"], stats["scars"], stats["left out (outside the box)"]), (1, 1, 1))
        self.assertNotIn("problems", stats)

    def test_the_refresh_sets_its_own_statement_limit(self):
        self.refresh(statement_timeout_s=42)
        self.assertEqual(self.conn.execute("show statement_timeout").fetchone()[0], "42s")

    def test_one_fire_s_geometry_failing_leaves_out_that_fire_only(self):
        good = self.add(payload(irwin="{0-A}"), square(-116.40, 43.60))
        throws = self.add(payload(irwin="{0-B}", name="THROWS"), square(-116.30, 43.60))
        slow = self.add(payload(irwin="{0-C}", name="SLOW"), square(-116.20, 43.60))
        real = bs.write_scar

        def write(conn, row, *a):
            if row["fire_id"] == throws:     # a real PostGIS error (XX000), as GEOS throwing would give
                conn.execute("select ST_GeomFromText('POLYGON((0 0, 1 1))')")
            if row["fire_id"] == slow:       # a real statement timeout
                conn.execute("select pg_sleep(2)")
            return real(conn, row, *a)

        with mock.patch.object(bs, "write_scar", side_effect=write):
            stats = self.refresh(statement_timeout_s=0.2)
        self.assertEqual((stats["written"], stats["scars"], stats["left out (geometry error)"]), (1, 1, 2))
        self.assertEqual(set(self.scars()), {good})
        self.assertIn("THROWS ({0-B}): geometry requires more points", stats["problems"])
        self.assertIn("SLOW ({0-C}): canceling statement due to statement timeout", stats["problems"])
        self.assertEqual(len(self.versions()), 1)
        again = self.refresh()                       # tried again on the next run
        self.assertEqual((again["written"], again["scars"]), (2, 3))

    def test_a_drawn_scar_whose_new_version_cant_be_drawn_keeps_its_last_good_one(self):
        fid = self.add(payload(irwin="{0-A}", final=False), square(-116.40, 43.60))
        self.refresh()
        old = self.conn.execute("select record_hash from hazards.burn_scar").fetchone()[0]
        flat = {"type": "Polygon", "coordinates": [[[-116.40, 43.60], [-116.39, 43.60], [-116.38, 43.60],
                                                    [-116.39, 43.60], [-116.40, 43.60]]]}   # zero area only
        self.add(payload(irwin="{0-A}", _geom="flat"), flat, seen=T0 + timedelta(hours=1))
        stats = self.refresh()
        self.assertEqual((stats["written"], stats["deleted"], stats["left out (geometry unusable)"],
                          stats["kept from an older version"], stats["stepped"], stats["version"]),
                         (0, 0, 1, 1, 0, "unchanged"))
        self.assertIn("SYNTH ONE ({0-A}): nothing left once made valid", stats["problems"])
        self.assertEqual(self.conn.execute("select record_hash from hazards.burn_scar").fetchone()[0], old)
        stepped = self.refresh(today=date(2027, 11, 1))          # its step still comes on its day
        self.assertEqual((stepped["stepped"], stepped["written"]), (1, 0))
        (n, f, *_), = self.scars().values()
        self.assertEqual(n, 1)
        self.assertAlmostEqual(f, 2 / 3, places=6)
        self.assertEqual(len(self.versions()), 2)
        self.assertEqual(self.refresh(today=date(2027, 11, 1))["version"], "unchanged")   # stepped once
        self.assertEqual(set(self.scars()), {fid})

    def test_out_of_time_the_rest_wait_for_the_next_run(self):
        a = self.add(payload(irwin="{0-A}"), square(-116.40, 43.60))
        self.refresh()
        self.add(payload(irwin="{0-B}"), square(-116.30, 43.60))
        late = self.refresh(today=date(2027, 11, 1), budget_s=0)
        self.assertEqual((late["written"], late["left for the next run (out of time)"], late["version"]),
                         (0, 2, "unchanged"))
        self.assertEqual(set(self.scars()), {a})
        stats = self.refresh(today=date(2027, 11, 1))
        self.assertEqual((stats["written"], stats["scars"]), (2, 2))

    def test_most_scars_vanishing_is_refused(self):
        for i in range(12):
            self.add(payload(irwin=f"{{0-{i:02d}}}"), square(-116.6 + i * 0.02, 43.6))
        self.refresh()
        self.conn.execute("update raw.record set removed_at = %s where source = %s and source_id <> %s",
                          (T0, self.SOURCE, "{0-00}"))
        with self.assertRaises(RuntimeError):
            self.refresh()
        self.assertEqual(self.refresh(force=True)["deleted"], 11)


if __name__ == "__main__":
    unittest.main()
