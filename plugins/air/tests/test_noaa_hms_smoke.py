"""Tests for the NOAA HMS smoke poller: listing, KML parsing, the ring, record ids, snapshot refusal,
the archive and the schedule. Offline, except DatabaseTest (needs TVT_TEST_DATABASE_URL).

Run: python3 -m unittest discover -s plugins/air/tests -t .

Fixtures (NOAA, public domain): hms_smoke20261006_trimmed.kml is the real Oct 6, 2026 file cut
to its overlays and four of its 221 polygons (none of them near Idaho); hms_smoke20261007_early.kml
is the real same-day file as it stood at 13:43 UTC, before the first analysis; listing_2026_10.html
is the folder's index at 14:35 UTC on Oct 7. The polygons over the ring below are made up.
"""

import gzip
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

from ingest import db, http, manifest
from plugins.air.ingest.sources import noaa_hms_smoke as hms

UTC = timezone.utc
HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
OCT5, OCT6, OCT7 = date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)


def fixture(name):
    with open(os.path.join(HERE, "fixtures", name), "rb") as f:
        return f.read()


def square(cx, cy, r):
    return [(cx - r, cy - r), (cx + r, cy - r), (cx + r, cy + r), (cx - r, cy + r), (cx - r, cy - r)]


def placemark(coords, density="Light", sat="GOES-WEST", start="2026278 1800UTC", end="2026278 2100UTC", holes=()):
    def ring(cs):
        return ("<LinearRing><coordinates>" + " ".join(f"{x:.6f},{y:.6f},0" for x, y in cs)
                + "</coordinates></LinearRing>")
    inner = "".join(f"<innerBoundaryIs>{ring(h)}</innerBoundaryIs>" for h in holes)
    return (f'<Placemark><description><![CDATA[<div style="width:170px;">Start Time: {start}<br>End Time: {end}'
            f'<br>Density: {density}<br>Satellite: {sat}</div>]]></description>'
            f"<styleUrl>#Smoke_{density}_style</styleUrl><Polygon><tessellate>1</tessellate>"
            f"<outerBoundaryIs>{ring(coords)}</outerBoundaryIs>{inner}</Polygon></Placemark>")


def kml(day="20261005", placemarks=(), generated="1830GMT 20261005"):
    """A KML shaped like NOAA's (overlays, one folder per density), with made-up polygons."""
    folders = {}
    for p in placemarks:
        density = p.split("Density: ", 1)[1].split("<", 1)[0]
        folders.setdefault(density, []).append(p)
    body = "".join(f"<Folder><name>Smoke ({d})</name><open>0</open>{''.join(ps)}</Folder>" for d, ps in folders.items())
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2" '
            f'xmlns:gx="http://www.google.com/kml/ext/2.2"><Document><name>HMS Smoke Mapping-{day}</name>'
            f"<Folder><name>Overlay</name>"
            f"<ScreenOverlay><name>Analysis Date</name><Icon><href><![CDATA[http://chart.example/c?chld=b|"
            f"Analysis%20for:%20{day}]]></href></Icon></ScreenOverlay>"
            f"<ScreenOverlay><name>Generated DateTime</name><Icon><href><![CDATA[http://chart.example/c?chld=b|"
            f"Generated:%20{generated.replace(' ', '%20')}]]></href></Icon></ScreenOverlay></Folder>"
            f"{body}</Document></kml>").encode()


BOISE = square(-116.2, 43.6, 0.2)
NAMPA = square(-116.56, 43.54, 0.1)
FAR = square(-100.0, 40.0, 1.0)


class WhereAndWhenTest(unittest.TestCase):
    def test_urls(self):
        self.assertEqual(hms.file_url(OCT6), "https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/Smoke_Polygons/"
                                             "KML/2026/10/hms_smoke20261006.kml")
        self.assertEqual(hms.month_url(2026, 1), "https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/Smoke_Polygons/"
                                                 "KML/2026/01/")

    def test_watch_today_yesterday_and_the_day_before(self):
        self.assertEqual(hms.watch_days(datetime(2026, 10, 7, 14, 35, tzinfo=UTC)), [OCT5, OCT6, OCT7])
        # Early on the 1st the window spans two months (two listings).
        days = hms.watch_days(datetime(2026, 11, 1, 0, 10, tzinfo=UTC))
        self.assertEqual(days, [date(2026, 10, 30), date(2026, 10, 31), date(2026, 11, 1)])
        # A local time is read in UTC: 6 PM MDT on Oct 7 is Oct 8 in UTC.
        mdt = timezone(timedelta(hours=-6))
        self.assertEqual(hms.watch_days(datetime(2026, 10, 7, 18, 30, tzinfo=mdt))[-1], date(2026, 10, 8))

    def test_the_listing(self):
        listing = hms.parse_listing(fixture("listing_2026_10.html"))
        self.assertEqual(sorted(listing), [f"hms_smoke202610{d:02d}.kml" for d in range(1, 8)])
        self.assertEqual(listing["hms_smoke20261007.kml"], datetime(2026, 10, 7, 13, 43, tzinfo=UTC))
        self.assertEqual(listing["hms_smoke20261006.kml"], datetime(2026, 10, 7, 10, 2, tzinfo=UTC))

    def test_a_listing_without_a_time_still_lists_the_file(self):
        self.assertEqual(hms.parse_listing(b'<tr><td><a href="hms_smoke20261008.kml">x</a></td></tr>'),
                         {"hms_smoke20261008.kml": None})

    def test_download_only_when_the_listing_moved(self):
        listed = datetime(2026, 10, 7, 13, 43, tzinfo=UTC)
        self.assertTrue(hms.needs_download(listed, None))                                  # never seen
        self.assertTrue(hms.needs_download(None, listed))                                  # no time listed
        self.assertFalse(hms.needs_download(listed, listed + timedelta(minutes=25)))       # we looked after it
        self.assertTrue(hms.needs_download(listed, listed + timedelta(minutes=5)))         # too close to call
        self.assertTrue(hms.needs_download(listed, listed - timedelta(hours=1)))           # changed since


class KmlTest(unittest.TestCase):
    def test_the_real_file(self):
        p = hms.parse_kml(fixture("hms_smoke20261006_trimmed.kml"), OCT6)
        self.assertEqual((p["analysis_date"], p["generated"]), ("2026-10-06", "2026-10-07T10:02:00Z"))
        pms = p["placemarks"]
        self.assertEqual([x["density"] for x in pms], ["light", "light", "medium", "heavy"])
        self.assertEqual([x["folder"] for x in pms],
                         ["Smoke (Light)", "Smoke (Light)", "Smoke (Medium)", "Smoke (Heavy)"])
        self.assertEqual({x["satellite"] for x in pms}, {"GOES-EAST"})
        self.assertEqual((pms[0]["start"], pms[0]["end"]), ("2026-10-06T17:00:00Z", "2026-10-06T20:00:00Z"))
        self.assertEqual(pms[1]["end"], "2026-10-06T23:30:00Z")
        self.assertEqual(pms[0]["fields"], {"Start Time": "2026279 1700UTC", "End Time": "2026279 2000UTC",
                                            "Density": "Light", "Satellite": "GOES-EAST"})
        g = pms[3]["geometry"]
        self.assertEqual(g["type"], "Polygon")
        self.assertEqual(g["coordinates"][0][0], [-123.48962, 41.480031])       # altitude dropped
        # A zero-area sliver (A, B, B, A) is kept as published.
        self.assertEqual(len(pms[0]["geometry"]["coordinates"][0]), 4)
        self.assertTrue(all(x["fixes"] == [] for x in pms))
        self.assertEqual(len(p["content_sha256"]), 64)

    def test_the_same_day_file_before_the_first_analysis(self):
        p = hms.parse_kml(fixture("hms_smoke20261007_early.kml"), OCT7)
        self.assertEqual((p["placemarks"], p["generated"]), ([], "2026-10-07T13:43:00Z"))

    def test_a_file_for_another_day_is_refused(self):
        with self.assertRaisesRegex(ValueError, "says it's for 20261006"):
            hms.parse_kml(fixture("hms_smoke20261006_trimmed.kml"), OCT7)

    def test_a_cut_off_file_is_refused(self):
        body = fixture("hms_smoke20261006_trimmed.kml")
        with self.assertRaisesRegex(ValueError, "not a complete KML"):
            hms.parse_kml(body[: len(body) // 2], OCT6)
        with self.assertRaises(ValueError):
            hms.parse_kml(b"<html><body>Not Found</body></html>", OCT6)

    def test_entity_declarations_are_refused(self):
        with self.assertRaisesRegex(ValueError, "entity"):
            hms.parse_kml(b'<?xml version="1.0"?><!DOCTYPE k [<!ENTITY a "aaaa">]><kml/>', OCT6)

    def test_regenerated_without_changes_is_the_same_content(self):
        a = hms.parse_kml(kml(placemarks=[placemark(BOISE)], generated="1830GMT 20261005"), OCT5)
        b = hms.parse_kml(kml(placemarks=[placemark(BOISE)], generated="2310GMT 20261005"), OCT5)
        c = hms.parse_kml(kml(placemarks=[placemark(BOISE, density="Medium")]), OCT5)
        self.assertEqual(a["content_sha256"], b["content_sha256"])
        self.assertNotEqual(a["generated"], b["generated"])
        self.assertNotEqual(a["content_sha256"], c["content_sha256"])

    def test_times(self):
        self.assertEqual(hms.hms_time("2026279 1200UTC"), "2026-10-06T12:00:00Z")
        self.assertEqual(hms.hms_time("2024366 2359UTC"), "2024-12-31T23:59:00Z")   # a leap year
        self.assertIsNone(hms.hms_time("2026366 0000UTC"))                          # not one
        self.assertIsNone(hms.hms_time("2026279 2500UTC"))
        self.assertIsNone(hms.hms_time("soon"))
        self.assertIsNone(hms.hms_time(None))

    def test_densities_before_and_after_july_2022(self):
        for raw, want in (("Light", "light"), ("MEDIUM", "medium"), ("heavy", "heavy"),
                          ("5", "light"), ("16", "medium"), ("27", "heavy"), ("27.000", "heavy")):
            self.assertEqual(hms.density({"Density": raw}, None), want, raw)
        self.assertEqual(hms.density({}, "Smoke (Medium)"), "medium")
        self.assertIsNone(hms.density({"Density": "thick"}, "Overlay"))

    def test_rings_are_closed_and_holes_and_multigeometry_kept(self):
        open_ring = BOISE[:-1]
        p = hms.parse_kml(kml(placemarks=[placemark(open_ring, holes=[square(-116.2, 43.6, 0.05)])]), OCT5)
        pm = p["placemarks"][0]
        self.assertEqual(pm["fixes"], ["ring_closed"])
        self.assertEqual(len(pm["geometry"]["coordinates"]), 2)                    # outer ring and a hole
        two = placemark(BOISE).replace("<Polygon>", "<MultiGeometry><Polygon>", 1).replace(
            "</Polygon>", "</Polygon><Polygon><outerBoundaryIs><LinearRing><coordinates>"
            + " ".join(f"{x},{y},0" for x, y in FAR) + "</coordinates></LinearRing></outerBoundaryIs></Polygon>"
            "</MultiGeometry>", 1)
        g = hms.parse_kml(kml(placemarks=[two]), OCT5)["placemarks"][0]["geometry"]
        self.assertEqual((g["type"], len(g["coordinates"])), ("MultiPolygon", 2))

    def test_bad_coordinates_leave_the_placemark_without_geometry(self):
        for junk in ("-116.4;43.4", "nan,43.4,0", "-116.4,95,0", "west,43.4,0"):
            bad = placemark(BOISE).replace("-116.400000,43.400000,0", junk, 1)
            pm = hms.parse_kml(kml(placemarks=[bad]), OCT5)["placemarks"][0]
            self.assertIsNone(pm["geometry"], junk)
            self.assertEqual(pm["fixes"], ["bad_coordinates"], junk)


class RingTest(unittest.TestCase):
    def poly(self, coords, holes=()):
        return {"type": "Polygon", "coordinates": [[list(c) for c in coords]] + [[list(c) for c in h] for h in holes]}

    def test_inside_outside_and_around(self):
        self.assertTrue(hms.touches_box(self.poly(BOISE)))
        self.assertFalse(hms.touches_box(self.poly(FAR)))
        self.assertTrue(hms.touches_box(self.poly(square(-116.45, 43.6, 5))))       # covers the whole ring
        self.assertFalse(hms.touches_box(None))

    def test_crossing_without_a_vertex_inside(self):
        band = [(-118, 43.5), (-115, 43.5), (-115, 43.6), (-118, 43.6), (-118, 43.5)]   # a band across the ring
        self.assertTrue(hms.touches_box(self.poly(band)))

    def test_bounding_box_overlap_alone_is_not_enough(self):
        # An L whose arms pass west and south of the ring: its bounding box covers the ring, it doesn't.
        ell = [(-118, 42), (-114, 42), (-114, 42.5), (-117.5, 42.5), (-117.5, 45), (-118, 45), (-118, 42)]
        self.assertFalse(hms.touches_box(self.poly(ell)))

    def test_a_ring_inside_a_hole_has_no_smoke(self):
        outer = square(-116.45, 43.6, 5)
        hole = square(-116.45, 43.6, 2)
        self.assertFalse(hms.touches_box(self.poly(outer, holes=[hole])))

    def test_one_part_of_a_multipolygon(self):
        g = {"type": "MultiPolygon", "coordinates": [[[list(c) for c in FAR]], [[list(c) for c in NAMPA]]]}
        self.assertTrue(hms.touches_box(g))

    def test_the_ring(self):
        self.assertEqual(hms.RING, (-117.30, 42.90, -115.60, 44.30))


class RecordsTest(unittest.TestCase):
    def test_the_real_file_has_nothing_over_the_ring(self):
        p = hms.parse_kml(fixture("hms_smoke20261006_trimmed.kml"), OCT6)
        (fid, payload, geom), ring = hms.records(OCT6, p)
        self.assertEqual((fid, geom, ring), ("20261006", None, []))
        self.assertEqual(payload["polygons"], 4)
        self.assertEqual(payload["by_density"], {"light": 2, "medium": 1, "heavy": 1})
        self.assertEqual(payload["by_satellite"], {"GOES-EAST": 4})
        self.assertEqual((payload["in_ring"], payload["generated"]), (0, "2026-10-07T10:02:00Z"))
        self.assertEqual(payload["url"], hms.file_url(OCT6))

    def test_ids_and_ordinals(self):
        p = hms.parse_kml(kml(placemarks=[placemark(BOISE), placemark(FAR), placemark(NAMPA),
                                          placemark(NAMPA, density="Heavy", sat="GOES-EAST")]), OCT5)
        _, ring = hms.records(OCT5, p)
        self.assertEqual([r[0] for r in ring], [
            "20261005/GOES-WEST/20261005T1800Z-20261005T2100Z/light/1",
            "20261005/GOES-WEST/20261005T1800Z-20261005T2100Z/light/2",
            "20261005/GOES-EAST/20261005T1800Z-20261005T2100Z/heavy/1"])
        sid, payload, geom = ring[0]
        self.assertEqual(geom, payload["geometry"])
        self.assertEqual((payload["analysis_date"], payload["file"], payload["density"]),
                         ("2026-10-05", "hms_smoke20261005.kml", "light"))
        self.assertNotIn("generated", payload)          # a regenerated file doesn't version its polygons

    def test_a_later_analysis_does_not_renumber_earlier_polygons(self):
        first = hms.parse_kml(kml(placemarks=[placemark(BOISE), placemark(NAMPA)]), OCT5)
        later = hms.parse_kml(kml(placemarks=[placemark(NAMPA, start="2026278 2300UTC", end="2026279 0100UTC"),
                                              placemark(BOISE), placemark(NAMPA)]), OCT5)
        ids_first = {sid: pl for sid, pl, _ in hms.records(OCT5, first)[1]}
        ids_later = {sid: pl for sid, pl, _ in hms.records(OCT5, later)[1]}
        for sid, payload in ids_first.items():
            self.assertEqual(ids_later[sid], payload)
        self.assertIn("20261005/GOES-WEST/20261005T2300Z-20261006T0100Z/light/1", ids_later)

    def test_unparsed_times_still_give_an_id(self):
        p = hms.parse_kml(kml(placemarks=[placemark(BOISE, start="??", end="")]), OCT5)
        self.assertEqual(hms.records(OCT5, p)[1][0][0], "20261005/GOES-WEST/unknown-unknown/light/1")


class SnapshotTest(unittest.TestCase):
    def test_a_file_that_lost_most_of_its_polygons_is_refused(self):
        with self.assertRaises(RuntimeError):
            hms.check_file_snapshot(50, 10, "test")
        with self.assertRaises(RuntimeError):
            hms.check_file_snapshot(5, 0, "test")
        hms.check_file_snapshot(50, 30, "test")         # some loss: taken
        hms.check_file_snapshot(4, 0, "test")           # small counts: taken
        hms.check_file_snapshot(None, 0, "test")        # the first, empty, version of a day
        hms.check_file_snapshot(0, 120, "test")         # a day's file grows


class ArchiveTest(unittest.TestCase):
    def test_kept_once_per_content(self):
        body = kml(placemarks=[placemark(BOISE)])
        p = hms.parse_kml(body, OCT5)
        with tempfile.TemporaryDirectory() as root:
            path = hms.archive(root, OCT5, p, body)
            self.assertEqual(os.path.relpath(path, root), os.path.join(
                "air", "hms", "2026", "10", f"hms_smoke20261005-20261005T1830Z-{p['content_sha256'][:12]}.kml.gz"))
            with gzip.open(path) as f:
                self.assertEqual(f.read(), body)
            regenerated = kml(placemarks=[placemark(BOISE)], generated="2310GMT 20261005")
            self.assertIsNone(hms.archive(root, OCT5, hms.parse_kml(regenerated, OCT5), regenerated))
            changed = kml(placemarks=[placemark(BOISE), placemark(NAMPA)], generated="2310GMT 20261005")
            self.assertTrue(hms.archive(root, OCT5, hms.parse_kml(changed, OCT5), changed))
            self.assertEqual(len(os.listdir(os.path.dirname(path))), 2)
        self.assertIsNone(hms.archive(None, OCT5, p, body))


class FakeHttp:
    def __init__(self, files):
        self.files, self.urls = files, []

    def get(self, url, timeout=90, compressed=False):
        self.urls.append(url)
        if url.endswith("/"):
            return 200, fixture("listing_2026_10.html"), "no_rules"
        return 200, self.files[url.rsplit("/", 1)[1]], "no_rules"


class PollTest(unittest.TestCase):
    """The run's decisions, with the database calls stubbed."""

    SEEN = datetime(2026, 10, 7, 14, 35, tzinfo=UTC)

    def setUp(self):
        self.files = {"hms_smoke20261005.kml": kml(placemarks=[placemark(BOISE), placemark(FAR)]),
                      "hms_smoke20261006.kml": fixture("hms_smoke20261006_trimmed.kml"),
                      "hms_smoke20261007.kml": fixture("hms_smoke20261007_early.kml")}
        self.http = FakeHttp(self.files)
        self.fetch = SimpleNamespace(id=1, http_status=None, robots=None, bytes=None, records=None)
        self.stored = []

    def poll(self, held, root=None):
        def store(conn, fetch_id, seen_at, day, parsed):
            self.stored.append(day)
            return {"new": 1, "unchanged": 0, "removed": 0, "in_ring": len(hms.records(day, parsed)[1])}
        with mock.patch.object(hms.http, "get", self.http.get), \
                mock.patch.object(hms, "current", lambda conn, day: held.get(day)), \
                mock.patch.object(hms, "heartbeat", lambda conn, day, seen: 1), \
                mock.patch.object(hms, "store", store):
            return hms.poll(None, self.fetch, self.SEEN, root)

    def held(self, day, last_seen, **payload):
        parsed = hms.parse_kml(self.files[hms.file_name(day)], day)
        return ({**hms.records(day, parsed)[0][1], **payload}, last_seen)

    def test_first_run_downloads_the_watched_days(self):
        with tempfile.TemporaryDirectory() as root:
            stats = self.poll({}, root)
            self.assertEqual(len(os.listdir(os.path.join(root, "air", "hms", "2026", "10"))), 3)
        self.assertEqual(self.http.urls, [hms.month_url(2026, 10)] + [hms.file_url(d) for d in (OCT5, OCT6, OCT7)])
        self.assertEqual(self.stored, [OCT5, OCT6, OCT7])
        self.assertEqual((stats["downloaded"], stats["changed"], stats["archived"], stats["polygons in ring"]),
                         (3, 3, 3, 1))
        self.assertEqual((self.fetch.http_status, self.fetch.robots), (200, "no_rules"))

    def test_nothing_listed_as_changed_means_one_request(self):
        later = datetime(2026, 10, 7, 14, 5, tzinfo=UTC)          # the last run, after every listed time
        stats = self.poll({d: self.held(d, later) for d in (OCT5, OCT6, OCT7)})
        self.assertEqual(self.http.urls, [hms.month_url(2026, 10)])
        self.assertEqual((stats["unchanged per listing"], stats["downloaded"], self.stored), (3, 0, []))
        self.assertEqual(stats["archived"], "off (TVT_ARCHIVE not set)")

    def test_downloaded_but_unchanged_is_only_seen_again(self):
        later = datetime(2026, 10, 7, 14, 5, tzinfo=UTC)
        held = {d: self.held(d, later) for d in (OCT5, OCT6)}
        held[OCT7] = self.held(OCT7, datetime(2026, 10, 7, 13, 50, tzinfo=UTC))   # within the margin of 13:43
        with tempfile.TemporaryDirectory() as root:
            stats = self.poll(held, root)
            self.assertFalse(os.path.exists(os.path.join(root, "air")))
        self.assertEqual((stats["downloaded"], stats["unchanged"], stats["changed"], self.stored), (1, 1, 0, []))

    def test_a_day_that_lost_most_of_its_polygons_is_archived_then_refused(self):
        earlier = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
        held = {OCT5: self.held(OCT5, datetime(2026, 10, 7, 14, 5, tzinfo=UTC)),
                OCT6: self.held(OCT6, earlier, polygons=200, content_sha256="0" * 64)}
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(RuntimeError, "only 4 polygons against 200"):
                self.poll(held, root)
            self.assertEqual(len(os.listdir(os.path.join(root, "air", "hms", "2026", "10"))), 1)
        self.assertEqual(self.stored, [])

    def test_a_day_not_listed_yet_is_skipped(self):
        del self.files["hms_smoke20261007.kml"]
        with mock.patch.object(hms, "parse_listing", lambda body: {"hms_smoke20261005.kml": None,
                                                                   "hms_smoke20261006.kml": None}):
            stats = self.poll({})
        self.assertEqual((stats["not listed yet"], stats["downloaded"]), (1, 2))


class ManifestTest(unittest.TestCase):
    def test_the_manifest_and_the_module_agree(self):
        plugin = manifest.load(PLUGIN)
        self.assertEqual((plugin.name, plugin.visibility, plugin.order, plugin.depends), ("air", "public", 61, []))
        (entry,) = plugin.entries("source")
        self.assertEqual(entry["name"], hms.SOURCE["name"])
        self.assertEqual((entry["license"], entry["credit"]), (hms.SOURCE["license"], hms.SOURCE["credit"]))
        self.assertEqual(entry["republish"], "yes")

    def test_registered(self):
        from ingest import sources as registry
        self.assertIs(registry.SOURCES["noaa_hms_smoke"], hms)
        self.assertEqual(registry.PLUGIN_OF["noaa_hms_smoke"], "air")

    def test_the_schedule_and_pace(self):
        s = hms.SOURCE
        self.assertEqual((s["access"], s["schedule"]), ("open", "30 minutes"))
        n, unit = s["schedule"].split()
        self.assertGreaterEqual(int(n) * {"minutes": 1, "hour": 60, "hours": 60}[unit], 10)
        self.assertGreaterEqual(http.PACE_S[hms.HOST], 2)


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database migrated through db/migrations")
class DatabaseTest(unittest.TestCase):
    """store, heartbeat and current against a real (scratch) database, rolled back afterwards."""

    def setUp(self):
        import psycopg
        self.conn = psycopg.connect(DB_URL)
        db.ensure_source(self.conn, hms.SOURCE)
        self.conn.execute("delete from raw.record where source = %s and source_id like '20261005%%'",
                          (hms.SOURCE["name"],))

    def tearDown(self):
        if not self.conn.closed:
            self.conn.rollback()
            self.conn.close()

    def fetch(self, at):
        return self.conn.execute("insert into ops.fetch (source, started_at, ok) values (%s, %s, true) returning id",
                                 (hms.SOURCE["name"], at)).fetchone()[0]

    def live(self):
        return sorted(r[0] for r in self.conn.execute(
            """select source_id from raw.record where source = %s and removed_at is null
               and source_id like '20261005%%'""", (hms.SOURCE["name"],)).fetchall())

    def test_a_day_versioned_through_its_analyses(self):
        c = self.conn
        t0, t1, t2 = (datetime(2026, 10, 5, h, 30, tzinfo=UTC) for h in (17, 18, 23))
        v1 = hms.parse_kml(kml(placemarks=[placemark(BOISE), placemark(NAMPA), placemark(FAR)]), OCT5)
        self.assertEqual(hms.store(c, self.fetch(t0), t0, OCT5, v1),
                         {"new": 3, "unchanged": 0, "removed": 0, "in_ring": 2})
        self.assertEqual(len(self.live()), 3)
        geom_type = c.execute("""select ST_GeometryType(geom) from raw.record where source = %s
                                 and source_id like '20261005/%%' limit 1""", (hms.SOURCE["name"],)).fetchone()[0]
        self.assertEqual(geom_type, "ST_Polygon")
        self.assertEqual(hms.heartbeat(c, OCT5, t1), 3)
        payload, last_seen = hms.current(c, OCT5)
        self.assertEqual((payload["polygons"], payload["in_ring"], last_seen), (3, 2, t1))
        # The evening analysis drops Nampa's polygon and adds a heavy one over Boise.
        v2 = hms.parse_kml(kml(placemarks=[placemark(BOISE), placemark(FAR), placemark(FAR),
                                           placemark(BOISE, density="Heavy", start="2026278 2300UTC",
                                                     end="2026279 0000UTC")]), OCT5)
        self.assertEqual(hms.store(c, self.fetch(t2), t2, OCT5, v2),
                         {"new": 2, "unchanged": 1, "removed": 2, "in_ring": 2})
        self.assertEqual(self.live(), ["20261005", "20261005/GOES-WEST/20261005T1800Z-20261005T2100Z/light/1",
                                       "20261005/GOES-WEST/20261005T2300Z-20261006T0000Z/heavy/1"])
        self.assertEqual(hms.current(c, OCT5)[0]["polygons"], 4)
        versions = c.execute("select count(*) from raw.record where source = %s and source_id = '20261005'",
                             (hms.SOURCE["name"],)).fetchone()[0]
        self.assertEqual(versions, 2)

    def test_poll_end_to_end_with_a_fake_server(self):
        c = self.conn
        seen = datetime(2026, 10, 7, 14, 35, tzinfo=UTC)
        files = {"hms_smoke20261005.kml": kml(placemarks=[placemark(BOISE)]),
                 "hms_smoke20261006.kml": fixture("hms_smoke20261006_trimmed.kml"),
                 "hms_smoke20261007.kml": fixture("hms_smoke20261007_early.kml")}
        c.execute("delete from raw.record where source = %s and source_id similar to '2026100(6|7)%%'",
                  (hms.SOURCE["name"],))
        fake = FakeHttp(files)
        fetch = SimpleNamespace(id=self.fetch(seen), http_status=None, robots=None, bytes=None, records=None)
        with mock.patch.object(hms.http, "get", fake.get):
            stats = hms.poll(c, fetch, seen, None)
            self.assertEqual((stats["changed"], stats["polygons in ring"], fetch.records), (3, 1, 4))
            later = seen + timedelta(minutes=30)
            fetch2 = SimpleNamespace(id=self.fetch(later), http_status=None, robots=None, bytes=None, records=None)
            stats = hms.poll(c, fetch2, later, None)
        self.assertEqual((stats["unchanged per listing"], stats["downloaded"], fetch2.records), (3, 0, 4))
        self.assertEqual(len(fake.urls), 5)          # two listings, three files once


if __name__ == "__main__":
    unittest.main()
