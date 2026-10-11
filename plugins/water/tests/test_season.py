"""The canal season (plugins/water/ingest/season.py) and the districts' dates file (sources/canal_dates.py).

Offline: readings to gauge spans (the shut-off, filling and draining, the 48-hour rule), the rules' precedence over
a timeline (gauge over district over IDWR's legal window), the dates file's checks, and the rows. The database case
runs only against a scratch database named by TVT_TEST_DATABASE_URL (with water 0001 and 0002), inside a
transaction that is rolled back. Everything is invented; the gauge's levels follow the shape of BSEI1's readings
around its Sep 28, 2026 shut-off.

Run: python3 -m unittest discover -s plugins -t .
"""

import json
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone

from ingest import events, seasons
from plugins.water.ingest import season as S
from plugins.water.ingest.sources import canal_dates as D
from plugins.water.tests import synthetic as syn

DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
UTC = timezone.utc
G = S.GAUGES["BSEI1"]
T0 = datetime(2026, 9, 27, 0, 0, tzinfo=UTC)
Q = timedelta(minutes=15)
H = timedelta(hours=1)


def utc(*a):
    return datetime(*a, tzinfo=UTC)


def boise(*a):
    return seasons.moment(datetime(*a))


def series(start, values, every=Q):
    """Readings every `every` from start: (stage ft, flow cfs or None)."""
    return [S.Reading(start + i * every, st, fl) for i, (st, fl) in enumerate(values)]


def shut_off():
    """A day on at the full level, the 3.5-hour ramp down (flow to 126 cfs), then the empty canal's level."""
    on = [(7.34, 1670.0)] * 96
    ramp = [(6.91, 1490.0), (6.43, 1300.0), (6.08, 1170.0), (5.5, 967.0), (4.36, 605.0), (3.94, 354.0),
            (3.85, 126.0)]
    off = [(3.79, None), (3.76, None)] + [(3.73, None)] * 40
    return series(T0, on + ramp + off)


def spec(**kw):
    base = {"id": "test-district-2026", "district": "Test Irrigation District", "canals": ["Test Canal"],
            "on": "2026-04-06", "off": "2026-10-15", "text": "Water will be turned in on April 6.",
            "source": "https://example.org/notices", "read": "2026-03-20"}
    base.update(kw)
    return {k: v for k, v in base.items() if v is not None}


LEGAL = ((3, 1), (11, 15), "3/1 - 11/15", 2)
SINCE, UNTIL = S.window(utc(2026, 10, 11, 12))


def timeline(rule_list):
    return [(s, e, v["state"], v["basis"]) for s, e, v, _ in S.spans(rule_list, SINCE, UNTIL)]


class ReadingTest(unittest.TestCase):
    def test_stage_and_flow_as_nwps_gives_them(self):
        r = S.reading({"lid": "BSEI1", "pe": "HGIRG", "t": "2026-09-27T06:00:00Z", "primary": 7.35,
                       "secondary": 1.67, "units": ["ft", "kcfs"]})
        self.assertEqual(r.t, utc(2026, 9, 27, 6))
        self.assertEqual(r.stage_ft, 7.35)
        self.assertAlmostEqual(r.flow_cfs, 1670.0)
        off = S.reading({"lid": "BSEI1", "pe": "HGIRG", "t": "2026-09-29T00:00:00Z", "primary": 3.73,
                         "secondary": None, "units": ["ft", None]})
        self.assertEqual((off.stage_ft, off.flow_cfs), (3.73, None))

    def test_units_and_what_isnt_a_reading(self):
        self.assertEqual(S.reading({"pe": "QRIRZ", "t": "2026-09-27T06:00:00Z", "primary": 250, "secondary": None,
                                    "units": ["cfs", None]}).flow_cfs, 250.0)
        # A pool elevation in ft is not a canal's stage.
        self.assertIsNone(S.reading({"pe": "HPIRG", "t": "2026-09-27T06:00:00Z", "primary": 2475.2,
                                     "units": ["ft", None]}))
        self.assertIsNone(S.reading({"pe": "HGIRG", "t": "2026-09-27T06:00:00Z", "primary": None,
                                     "secondary": None, "units": ["ft", "kcfs"]}))
        self.assertIsNone(S.reading({"pe": "HGIRG", "t": "", "primary": 3.7, "units": ["ft", None]}))
        self.assertIsNone(S.reading({"pe": "HGIRG", "t": "2026-09-27T06:00:00Z", "primary": True,
                                     "units": ["ft", None]}))


class ClassifyTest(unittest.TestCase):
    def test_flow_first_then_stage_with_a_dead_band(self):
        c = (lambda stage, flow=None: S.classify(G, S.Reading(T0, stage, flow)))
        self.assertEqual(c(3.85, 126.0), "on")          # the last trickle of the ramp down
        self.assertEqual(c(7.34, 5.0), "off")           # a flow reported under 10 cfs
        self.assertEqual(c(7.35), "on")
        self.assertEqual(c(7.30), "on")
        self.assertEqual(c(3.73), "off")                # the empty canal's level drifts above 3.7 ft
        self.assertEqual(c(3.90), "off")
        self.assertIsNone(c(3.95))                      # filling or draining: the state before holds
        self.assertIsNone(c(5.5))
        self.assertIsNone(c(None))


class GaugeSpansTest(unittest.TestCase):
    def test_the_shut_off(self):
        rs = shut_off()
        first_off = next(r.t for r in rs if r.flow_cfs is None)
        got = S.gauge_spans(G, rs, rs[-1].t + H)
        self.assertEqual([(s.start, s.end, s.state) for s in got],
                         [(T0, first_off, "on"), (first_off, None, "off")])
        self.assertEqual(got[0].why, "flow 1,670 cfs, stage 7.34 ft")
        self.assertEqual(got[1].why, "stage 3.79 ft, no flow reported")

    def test_filling_and_draining_keep_the_state_before(self):
        rs = series(T0, [(7.4, None), (5.5, None), (4.2, None), (3.8, None), (4.5, None), (6.0, None),
                         (7.3, None)], every=H)
        got = S.gauge_spans(G, rs, rs[-1].t + H)
        self.assertEqual([(s.start, s.state) for s in got],
                         [(T0, "on"), (T0 + 3 * H, "off"), (T0 + 6 * H, "on")])
        self.assertIsNone(got[-1].end)

    def test_no_claim_before_the_first_on_or_off_reading(self):
        rs = series(T0, [(5.0, None), (5.2, None), (3.7, None)], every=H)
        self.assertEqual([(s.start, s.end, s.state) for s in S.gauge_spans(G, rs, T0 + 3 * H)],
                         [(T0 + 2 * H, None, "off")])
        self.assertEqual(S.gauge_spans(G, series(T0, [(5.0, None)]), T0 + H), [])
        self.assertEqual(S.gauge_spans(G, [], T0), [])

    def test_unknown_48_hours_after_the_last_reading(self):
        """The staleness case: the state holds for 48 hours after the last reading, then it's unknown."""
        rs = series(T0, [(3.73, None)] * 8, every=H)
        last = rs[-1].t
        fresh = S.gauge_spans(G, rs, last + timedelta(hours=47, minutes=59))
        self.assertEqual([(s.start, s.end, s.state) for s in fresh], [(T0, None, "off")])
        stale = S.gauge_spans(G, rs, last + timedelta(hours=48))
        self.assertEqual([(s.start, s.end, s.state) for s in stale],
                         [(T0, last + S.STALE, "off"), (last + S.STALE, None, "unknown")])
        self.assertEqual(stale[-1].why, "no reading for 48 hours")
        # Three days on, still unknown from the same moment: the rows don't move.
        self.assertEqual(S.gauge_spans(G, rs, last + timedelta(days=5)), stale)

    def test_a_silence_between_readings(self):
        before = series(T0, [(7.34, 1670.0)] * 4, every=H)
        last = before[-1].t
        after = series(last + timedelta(hours=50), [(3.73, None)] * 3, every=H)
        got = S.gauge_spans(G, before + after, after[-1].t + H)
        self.assertEqual([(s.start, s.end, s.state) for s in got],
                         [(T0, last + S.STALE, "on"), (last + S.STALE, after[0].t, "unknown"),
                          (after[0].t, None, "off")])
        # Readings in between after a silence leave it unknown until an on or off reading.
        mid = series(last + timedelta(hours=50), [(5.0, None), (5.5, None), (7.4, None)], every=H)
        got = S.gauge_spans(G, before + mid, mid[-1].t + H)
        self.assertEqual([(s.start, s.state) for s in got],
                         [(T0, "on"), (last + S.STALE, "unknown"), (mid[2].t, "on")])

    def test_exactly_48_hours_apart_is_not_a_silence(self):
        rs = [S.Reading(T0, 3.73, None), S.Reading(T0 + S.STALE, 3.72, None)]
        self.assertEqual([(s.start, s.end, s.state) for s in S.gauge_spans(G, rs, T0 + S.STALE + H)],
                         [(T0, None, "off")])

    def test_readings_after_now_are_left_out(self):
        rs = shut_off()
        first_off = next(r.t for r in rs if r.flow_cfs is None)
        got = S.gauge_spans(G, rs, first_off - Q)
        self.assertEqual([(s.start, s.end, s.state) for s in got], [(T0, None, "on")])

    def test_order_of_readings_doesnt_matter(self):
        rs = shut_off()
        self.assertEqual(S.gauge_spans(G, list(reversed(rs)), rs[-1].t + H), S.gauge_spans(G, rs, rs[-1].t + H))


class SeasonalTest(unittest.TestCase):
    def test_drains_and_creeks_never_switch_off(self):
        self.assertFalse(S.seasonal("drain", "Mill Slough"))
        self.assertFalse(S.seasonal("drain", "Test Drain"))
        self.assertFalse(S.seasonal("canal", "Fivemile Creek"))
        self.assertFalse(S.seasonal("canal", "Purdam Gulch"))
        self.assertFalse(S.seasonal("ditch", "Boise River"))
        self.assertTrue(S.seasonal("canal", "Mason Creek Feeder"))
        self.assertTrue(S.seasonal("canal", "Dry Creek Canal"))
        self.assertTrue(S.seasonal("lateral", "Gulch Lateral"))
        self.assertTrue(S.seasonal("ditch", "River Flat Ditch"))
        self.assertTrue(S.seasonal("main_canal", "New York Canal"))


class RulesTest(unittest.TestCase):
    """The timeline from Jan 1, 2026 to Jan 1, 2028 (the window as of Oct 2026)."""

    def test_legal_end(self):
        self.assertEqual(S.legal_end(LEGAL, 2026), boise(2026, 11, 16))
        self.assertIsNone(S.legal_end(None, 2026))
        self.assertIsNone(S.legal_end(((11, 16), (4, 30), "11/16 - 4/30", 9), 2026))      # across New Year
        feb29 = ((1, 1), (2, 29), "1/1 - 2/29", 9)
        self.assertEqual((S.legal_end(feb29, 2027), S.legal_end(feb29, 2028)), (boise(2027, 3, 1), boise(2028, 3, 1)))

    def test_window(self):
        self.assertEqual((SINCE, UNTIL), (boise(2026, 1, 1), boise(2028, 1, 1)))
        self.assertEqual(S.window(utc(2027, 1, 1, 7))[1], boise(2029, 1, 1))

    def test_legal_window_alone(self):
        self.assertEqual(timeline(S.canal_rules(LEGAL, [])), [
            (boise(2026, 1, 1), boise(2026, 3, 1), "off", "legal"),
            (boise(2026, 3, 1), boise(2026, 11, 16), "on", "legal"),
            (boise(2026, 11, 16), boise(2027, 3, 1), "off", "legal"),
            (boise(2027, 3, 1), boise(2027, 11, 16), "on", "legal"),
            (boise(2027, 11, 16), UNTIL, "off", "legal")])
        self.assertEqual(timeline(S.canal_rules(None, [])), [])

    def test_the_gauge_wins_and_its_current_span_stays_open(self):
        rs = shut_off()
        first_off = next(r.t for r in rs if r.flow_cfs is None)
        got = timeline(S.canal_rules(LEGAL, [], G, S.gauge_spans(G, rs, rs[-1].t + H)))
        self.assertEqual(got, [
            (boise(2026, 1, 1), boise(2026, 3, 1), "off", "legal"),
            (boise(2026, 3, 1), T0, "on", "legal"),          # before the gauge's first reading
            (T0, first_off, "on", "gauge"),
            (first_off, None, "off", "gauge")])              # holds until a reading changes it

    def test_the_district_over_the_legal_window(self):
        entry = D.entry(spec(), 0)
        self.assertEqual(timeline(S.canal_rules(LEGAL, [entry])), [
            (boise(2026, 1, 1), boise(2026, 4, 6), "off", "district"),
            (boise(2026, 4, 6), boise(2026, 10, 15), "on", "district"),
            (boise(2026, 10, 15), boise(2027, 1, 1), "off", "district"),
            (boise(2027, 1, 1), boise(2027, 3, 1), "off", "legal"),
            (boise(2027, 3, 1), boise(2027, 11, 16), "on", "legal"),
            (boise(2027, 11, 16), UNTIL, "off", "legal")])

    def test_a_shut_off_not_yet_announced_ends_with_the_legal_season(self):
        entry = D.entry(spec(off=None), 0)
        got = timeline(S.canal_rules(LEGAL, [entry]))
        self.assertEqual(got[:3], [(boise(2026, 1, 1), boise(2026, 4, 6), "off", "district"),
                                   (boise(2026, 4, 6), boise(2026, 11, 16), "on", "district"),
                                   (boise(2026, 11, 16), boise(2027, 3, 1), "off", "legal")])
        _, _, value, _ = S.spans(S.canal_rules(LEGAL, [entry]), SINCE, UNTIL)[1]
        self.assertFalse(value["off_announced"])
        # Without a legal window, to the end of the year; then nothing.
        self.assertEqual(timeline(S.canal_rules(None, [entry])),
                         [(boise(2026, 1, 1), boise(2026, 4, 6), "off", "district"),
                          (boise(2026, 4, 6), boise(2027, 1, 1), "on", "district")])
        # Only a shut-off: nothing claimed before it.
        only_off = D.entry(spec(on=None, off="2026-09-24"), 0)
        self.assertEqual(timeline(S.canal_rules(LEGAL, [only_off]))[:4],
                         [(boise(2026, 1, 1), boise(2026, 3, 1), "off", "legal"),
                          (boise(2026, 3, 1), boise(2026, 9, 24), "on", "legal"),
                          (boise(2026, 9, 24), boise(2027, 1, 1), "off", "district"),
                          (boise(2027, 1, 1), boise(2027, 3, 1), "off", "legal")])

    def test_a_later_entry_wins(self):
        first = D.entry(spec(), 0)
        revised = D.entry(spec(id="test-district-2026-revised", on=None, off="2026-09-24T08:00"), 1)
        got = timeline(S.canal_rules(LEGAL, [first, revised]))
        self.assertEqual(got[1:3], [(boise(2026, 4, 6), boise(2026, 9, 24, 8), "on", "district"),
                                    (boise(2026, 9, 24, 8), boise(2027, 1, 1), "off", "district")])

    def test_unknown_from_the_gauge_wins_over_the_districts_dates(self):
        """Decision 18: with no reading for 48 hours the gauged canal shows unknown, not on or off."""
        entry = D.entry(spec(on="2026-04-06", off="2026-10-31"), 0)
        rs = series(T0, [(7.34, 1670.0)] * 4, every=H)
        now = utc(2026, 10, 11, 12)
        got = timeline(S.canal_rules(LEGAL, [entry], G, S.gauge_spans(G, rs, now)))
        self.assertEqual(got[-2:], [(T0, rs[-1].t + S.STALE, "on", "gauge"),
                                    (rs[-1].t + S.STALE, None, "unknown", "gauge")])


class SelectionTest(unittest.TestCase):
    CANALS = [S.Canal(1, "Test Canal", "canal", None, None, None),
              S.Canal(2, "Test Lateral", "lateral", None, 1, None),
              S.Canal(3, "Small Lateral", "lateral", None, 2, None),
              S.Canal(4, "Test Drain", "drain", None, 1, None),
              S.Canal(5, "Test Canal", "canal", None, None, None),       # two canals of one name
              S.Canal(6, "Other Canal", "canal", None, None, None)]

    def test_names_and_branches(self):
        plain = D.entry(spec(canals=["TEST canal"]), 0)
        chosen, missing = S.selections([plain], self.CANALS)
        self.assertEqual(sorted(chosen), [1, 5])
        self.assertEqual(missing, [])
        branches = D.entry(spec(id="b", canals=["Test Canal", "Gone Canal"], branches=True), 1)
        chosen, missing = S.selections([plain, branches], self.CANALS)
        self.assertEqual(sorted(chosen), [1, 2, 3, 5])                    # not the drain
        self.assertEqual([e.id for e in chosen[1]], ["test-district-2026", "b"])
        self.assertEqual(missing, [("b", "Gone Canal")])


class RowTest(unittest.TestCase):
    CANAL = S.Canal(77, "Test Canal", "main_canal", "BSEI1", None, {"type": "Point", "coordinates": [-116.5, 43.4]})

    def rows(self, rule_list):
        return [S.row(self.CANAL, s, e, v, r) for s, e, v, r in S.spans(rule_list, SINCE, UNTIL)]

    def test_rows(self):
        rs = shut_off()
        rows = self.rows(S.canal_rules(LEGAL, [], G, S.gauge_spans(G, rs, rs[-1].t + H)))
        legal, gauge_off = rows[1], rows[-1]
        self.assertEqual(legal["source_id"], "77@2026-03-01T07:00:00Z")
        self.assertEqual((legal["kind"], legal["severity"]), ("canal_season", "on"))
        self.assertEqual(legal["description"],
                         "Test Canal: in IDWR's legal irrigation season (3/1 - 11/15), not delivery dates")
        self.assertEqual(legal["attributes"]["republish"], "internal")
        self.assertIn("Idaho Department of Water Resources (Season of Use)", legal["attributes"]["credit"])
        self.assertIsNone(gauge_off["end"])
        self.assertEqual(gauge_off["description"], "Test Canal: off (gauge BSEI1, New York Canal Diversion at Boise)")
        a = gauge_off["attributes"]
        self.assertEqual((a["canal_id"], a["state"], a["basis"], a["gauge"], a["republish"]),
                         (77, "off", "gauge", "BSEI1", "yes"))
        self.assertEqual(a["credit"][0], "NOAA National Weather Service (NWPS), gauge BSEI1")
        self.assertNotIn("Geological Survey", " ".join(a["credit"]))   # BSEI1's NWPS record names no USGS site
        self.assertEqual(gauge_off["geom"], self.CANAL.head)
        json.dumps(rows, default=str)                                 # the rows serialize as events.upsert does
        stale = self.rows(S.canal_rules(LEGAL, [], G, S.gauge_spans(G, rs, rs[-1].t + 3 * S.STALE)))[-1]
        self.assertEqual((stale["severity"], stale["start"], stale["end"]), ("unknown", rs[-1].t + S.STALE, None))
        self.assertEqual(stale["description"], "Test Canal: unknown (gauge BSEI1: no reading for 48 hours)")

    def test_district_and_always_rows(self):
        entry = D.entry(spec(republish="internal"), 0)
        on = self.rows(S.canal_rules(None, [entry]))[1]
        self.assertEqual(on["description"], "Test Canal: water on (Test Irrigation District's dates)")
        self.assertEqual((on["attributes"]["source"], on["attributes"]["read"], on["attributes"]["republish"]),
                         ("https://example.org/notices", "2026-03-20", "internal"))
        drain = S.always_row(S.Canal(9, "Test Drain", "drain", None, None, None), SINCE)
        self.assertEqual((drain["severity"], drain["end"], drain["attributes"]["basis"]), ("on", None, "always"))
        self.assertEqual(drain["description"],
                         "Test Drain: water all year (a drain; drains and creeks never switch off)")

    def test_unchanged(self):
        rows = self.rows(S.canal_rules(LEGAL, []))
        stored = {r["source_id"]: (True, events.content_hash(r)) for r in rows}
        self.assertTrue(S.unchanged(stored, rows))
        self.assertFalse(S.unchanged({**stored, "1@2026-01-01T07:00:00Z": (True, b"x")}, rows))   # one to close
        self.assertTrue(S.unchanged({**stored, "1@2026-01-01T07:00:00Z": (False, b"x")}, rows))   # closed already
        first = rows[0]["source_id"]
        self.assertFalse(S.unchanged({**stored, first: (False, stored[first][1])}, rows))         # to reopen
        self.assertFalse(S.unchanged({**stored, first: (True, b"x")}, rows))                       # changed
        self.assertFalse(S.unchanged({}, rows))


class DatesFileTest(unittest.TestCase):
    def test_the_file_starts_empty_and_parses(self):
        entries, digest = D.read_file()
        self.assertEqual(entries, [])
        self.assertEqual(len(digest), 64)

    def test_an_entry(self):
        e = D.entry(spec(on="2026-04-06", off="2026-10-15T08:30"), 3)
        self.assertEqual((e.id, e.position, e.season, e.canals, e.branches, e.republish),
                         ("test-district-2026", 3, 2026, ("Test Canal",), False, "yes"))
        self.assertEqual(e.on_at, boise(2026, 4, 6))
        self.assertEqual(e.off_at, boise(2026, 10, 15, 8, 30))
        self.assertEqual((e.on_given, e.read_on), ("2026-04-06", date(2026, 3, 20)))

    def test_refused(self):
        for bad, msg in (
                (spec(colour="blue"), "unknown key"),
                (spec(id="Test 2026"), "id is lower-case"),
                (spec(district=" "), "district"),
                (spec(canals=[]), "canals is a list"),
                (spec(canals=["--"]), "canals is a list"),
                (spec(branches="yes"), "branches"),
                (spec(on=None, off=None), "give on, off or both"),
                (spec(on="20260406"), "on: not a date"),
                (spec(off="2026-10-15T24:00"), "off: not a date"),
                (spec(on=20260406), "on is a date as text"),
                (spec(on="2026-10-15", off="2026-04-06"), "isn't after"),
                (spec(on="2026-04-06", off="2027-04-06"), "different years"),
                (spec(source=None), "source is the page's URL"),
                (spec(source="example.org"), "source is the page's URL"),
                (spec(read="Mar 20"), "read is the day"),
                (spec(read="2026-02-30"), "read is not a date"),
                (spec(text="x" * 501), "text is the district's words"),
                (spec(republish="maybe"), "republish is one of")):
            with self.subTest(msg=msg), self.assertRaisesRegex(ValueError, msg):
                D.entry(bad, 0)
        with self.assertRaisesRegex(ValueError, "used twice"):
            D.parse({"seasons": [spec(), spec()]})
        with self.assertRaisesRegex(ValueError, "unknown key\\(s\\) at the top"):
            D.parse({"seasons": [], "notes": "x"})
        with self.assertRaisesRegex(ValueError, '"seasons" list'):
            D.parse({"rules": []})

    def test_read_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "dates.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"about": "test", "seasons": [spec()]}, f)
            entries, digest = D.read_file(path)
            self.assertEqual([e.id for e in entries], ["test-district-2026"])
            with open(path, "w", encoding="utf-8") as f:
                f.write("{not json")
            with self.assertRaisesRegex(ValueError, "not JSON"):
                D.read_file(path)


def _line(*points):
    return json.dumps({"type": "LineString", "coordinates": [list(syn.at(*p)) for p in points]})


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (with water 0001 and 0002)")
class DatabaseTest(unittest.TestCase):
    """Derive and store on a synthetic build: a gauged main canal, a district's lateral, a drain."""

    @classmethod
    def setUpClass(cls):
        import psycopg
        from ingest import db
        from plugins.water.ingest.sources import nwps_gauges
        cls.conn = c = psycopg.connect(DB_URL)
        for t in ("water.canal_season", "water.canal_org", "water.gauge", "water.reach_evidence", "water.reach_link",
                  "water.structure", "water.body", "water.canal", "water.reach", "water.canal_date"):
            c.execute(f"delete from {t}")
        c.execute("delete from evt.event where source = 'canal_season'")
        c.execute("delete from raw.record where source = 'nwps_gauges' and source_id like 'BSEI1@%'")
        db.ensure_source(c, nwps_gauges.SOURCE)
        db.ensure_source(c, S.SOURCE)
        build = c.execute("insert into water.build default values returning id").fetchone()[0]
        for rid, kind, name, geom in ((101, "canal", "Test Main Canal", _line((0, 0), (5000, 0))),
                                      (102, "lateral", "Test Lateral", _line((2000, 0), (2000, 1500))),
                                      (103, "drain", "Test Drain", _line((0, 500), (3000, 500)))):
            c.execute("""insert into water.reach (id, kind, name, width_m, width_from, minzoom, geometry_from, length_m,
                                                  geom, build_id)
                         values (%s, %s, %s, 5, 'kind', 11, 'osm', 1000, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
                                 %s)""", (rid, kind, name, geom, build))
        for cid, name, kind, lid, src in ((101, "Test Main Canal", "main_canal", "BSEI1", None),
                                          (102, "Test Lateral", "lateral", None, 101),
                                          (103, "Test Drain", "drain", None, None)):
            c.execute("""insert into water.canal (id, name, kind, length_m, reaches, head_reach_id, source_kind,
                                                  source_canal_id, gauge_lid, sources, build_id)
                         values (%s, %s, %s, 1000, 1, %s, 'canal', %s, %s, '{osm_waterways}', %s)""",
                      (cid, name, kind, cid, src, lid, build))
        for cid in (101, 102):
            c.execute("""insert into water.canal_season (canal_id, objectid, season, start_month, start_day,
                                                         end_month, end_day, build_id)
                         values (%s, 2, '3/1 - 11/15', 3, 1, 11, 15, %s)""", (cid, build))
        entry = D.entry(spec(id="test-lateral-2026", canals=["test lateral"]), 0)
        cls.counts, cls.missing = D.store(c, [entry], "canal_dates.json", "0" * 64)
        rs = shut_off()
        cls.last = rs[-1].t
        cls.first_off = next(r.t for r in rs if r.flow_cfs is None)
        records = [(f"BSEI1@{S.iso(r.t)}", {"lid": "BSEI1", "pe": "HGIRG", "t": S.iso(r.t), "primary": r.stage_ft,
                                            "secondary": None if r.flow_cfs is None else r.flow_cfs / 1000,
                                            "units": ["ft", None if r.flow_cfs is None else "kcfs"]}, None)
                   for r in rs]
        db.upsert_records(c, "nwps_gauges", records, None, cls.last, complete=False)
        # A revised version of one observation: the newest is read.
        revised = dict(records[0][1], primary=7.36)
        db.upsert_records(c, "nwps_gauges", [(records[0][0], revised, None)], None, cls.last + H, complete=False)

    @classmethod
    def tearDownClass(cls):
        cls.conn.rollback()
        cls.conn.close()

    def lifecycles(self):
        return self.conn.execute(
            """select source_id, severity, lower(declared), upper(declared), attributes->>'basis', active
               from evt.event where source = 'canal_season' order by source_id""").fetchall()

    def test_derive_store_and_go_stale(self):
        c = self.conn
        self.assertEqual((self.counts["entries"], self.missing), (1, []))
        rows, stats = S.derive(c, self.last + H)
        self.assertEqual(stats["canals"], 3)
        self.assertEqual(stats["gauge BSEI1"], f"off since {S.iso(self.first_off)}")
        self.assertEqual(stats["always"], 1)
        self.assertEqual(S.write(c, rows, self.last + H), {"new": len(rows), "changed": 0, "gone": 0})
        got = self.lifecycles()
        main = [r for r in got if r[0].startswith("101@")]
        self.assertEqual([(r[1], r[4]) for r in main][-3:], [("on", "legal"), ("on", "gauge"), ("off", "gauge")])
        self.assertEqual((main[-1][2], main[-1][3]), (self.first_off, None))
        lateral = [r for r in got if r[0].startswith("102@")]
        self.assertEqual([(r[1], r[4]) for r in lateral][:3], [("off", "district"), ("on", "district"),
                                                               ("off", "district")])
        self.assertEqual([(r[1], r[4], r[3]) for r in got if r[0].startswith("103@")], [("on", "always", None)])
        head = c.execute("""select ST_AsText(geom) from evt.event where source = 'canal_season'
                            and source_id = %s""", (main[-1][0],)).fetchone()[0]
        self.assertEqual(head, c.execute("select ST_AsText(ST_StartPoint(geom)) from water.reach where id = 101"
                                         ).fetchone()[0])

        # The next hour: nothing changed, nothing written.
        rows, _ = S.derive(c, self.last + 2 * H)
        self.assertEqual(S.write(c, rows, self.last + 2 * H), {"new": 0, "changed": 0, "gone": 0})

        # Three days without a reading: the off span closes 48 hours after the last reading, and unknown begins.
        later = self.last + timedelta(days=3)
        rows, stats = S.derive(c, later)
        self.assertEqual(stats["gauge BSEI1"], f"unknown since {S.iso(self.last + S.STALE)}")
        self.assertEqual(S.write(c, rows, later), {"new": 1, "changed": 1, "gone": 0})
        main = [r for r in self.lifecycles() if r[0].startswith("101@")]
        self.assertEqual([(r[1], r[2], r[3]) for r in main][-2:],
                         [("off", self.first_off, self.last + S.STALE), ("unknown", self.last + S.STALE, None)])

    def test_the_dates_table_and_the_load(self):
        c = self.conn
        row = c.execute("""select d.entry_id, d.district, d.canals, d.season, d.on_at, d.off_at, d.on_given, l.source,
                                  l.sha256
                           from water.canal_date d join water.load l on l.id = d.load_id""").fetchone()
        self.assertEqual(row, ("test-lateral-2026", "Test Irrigation District", ["test lateral"], 2026,
                               boise(2026, 4, 6), boise(2026, 10, 15), "2026-04-06", "canal_dates", "0" * 64))
        self.assertEqual([e.id for e in D.loaded(c)], ["test-lateral-2026"])
        self.assertEqual(D.loaded(c)[0], D.entry(spec(id="test-lateral-2026", canals=["test lateral"]), 0))
