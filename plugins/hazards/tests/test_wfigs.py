"""Tests for the NIFC WFIGS incident and perimeter sources. Offline.

The fixtures are trimmed real records from NIFC's services (federal, disclaimer only),
read Oct 7, 2026: three incidents and two perimeters on federal land in the ring.
Variants (contained but not out, withdrawn, duplicates) are made in the tests.

Run: python3 -m unittest discover -s plugins/hazards/tests -t .
"""

import copy
import json
import os
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone

from ingest import arcgis
from ingest.db import version_hash
from plugins.hazards.ingest import common
from plugins.hazards.ingest.sources import nifc_wfigs_incidents as inc
from plugins.hazards.ingest.sources import nifc_wfigs_perimeters as per

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
UTC = timezone.utc


def load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)["features"]


def ms(t):
    return int(t.timestamp() * 1000)


def by_name(parsed, field):
    return {p[field]: (sid, p, g) for sid, (p, g) in parsed.items()}


class WindowTest(unittest.TestCase):
    NOW = datetime(2026, 10, 7, 15, 22, 30, tzinfo=UTC)

    def test_first_run_reads_the_year(self):
        self.assertEqual(inc.since(None, self.NOW), datetime(2026, 1, 1, tzinfo=UTC))

    def test_later_runs_overlap_two_hours_floored_to_the_hour(self):
        self.assertEqual(inc.since(datetime(2026, 10, 7, 15, 10, tzinfo=UTC), self.NOW),
                         datetime(2026, 10, 7, 13, tzinfo=UTC))
        future = self.NOW + timedelta(days=3)                      # a clock that runs ahead can't skip records
        self.assertEqual(inc.since(future, self.NOW), datetime(2026, 10, 7, 13, tzinfo=UTC))

    def test_filters_are_absolute(self):
        start = datetime(2026, 10, 7, 13, tzinfo=UTC)
        self.assertEqual(inc.where(start), "ModifiedOnDateTime_dt >= TIMESTAMP '2026-10-07 13:00:00'")
        self.assertEqual(per.where(start), "attr_ModifiedOnDateTime_dt >= TIMESTAMP '2026-10-07 13:00:00' OR "
                                           "poly_DateCurrent >= TIMESTAMP '2026-10-07 13:00:00'")
        for clause in (inc.where(start), per.where(start)):
            for relative in ("CURRENT_TIMESTAMP", "CURRENT_DATE", "INTERVAL", "NOW("):
                self.assertNotIn(relative, clause.upper())
        url = common.query_url(inc.LAYER, inc.where(start))
        self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["where"], [inc.where(start)])

    def test_the_services_are_the_all_years_ones(self):
        self.assertTrue(inc.LAYER.endswith("/WFIGS_Incident_Locations/FeatureServer/0"))
        self.assertTrue(per.LAYER.endswith("/WFIGS_Interagency_Perimeters/FeatureServer/0"))
        self.assertEqual((inc.SOURCE["schedule"], per.SOURCE["schedule"]), ("10 minutes", "15 minutes"))


class IncidentTest(unittest.TestCase):
    def setUp(self):
        self.parsed = inc.parse(load("wfigs_incidents.json"))
        self.fires = by_name(self.parsed, "IncidentName")

    def test_keyed_by_irwin_id_without_hosting_artefacts_or_empty_fields(self):
        self.assertEqual(sorted(self.fires), ["BULLDOG", "RX HIGH VALLEY", "WOODRIDGE"])
        sid, payload, geom = self.fires["WOODRIDGE"]
        self.assertEqual(sid, payload["IrwinID"].upper())
        for gone in ("OBJECTID", "GlobalID", "SourceOID"):
            self.assertNotIn(gone, payload)
        self.assertFalse(any(v is None for v in payload.values()))
        self.assertEqual(geom["type"], "Point")
        self.assertTrue(common.in_ring(*geom["coordinates"]))

    def test_a_fire_read_twice_keeps_the_newer_record(self):
        fs = load("wfigs_incidents.json")
        older = copy.deepcopy(fs[0])
        older["attributes"]["ModifiedOnDateTime_dt"] -= 3600000
        older["attributes"]["IncidentSize"] = 1
        newer = inc.parse(fs)
        self.assertEqual(inc.parse(fs + [older]), newer)
        self.assertEqual(inc.parse([older] + fs), newer)

    def test_an_out_fire_is_closed_with_its_out_time(self):
        sid, p, g = self.fires["BULLDOG"]
        row, is_open = inc.row_of(sid, p, g, datetime(2026, 10, 1, tzinfo=UTC))
        self.assertFalse(is_open)
        self.assertEqual((row["kind"], row["severity"], row["description"]), ("wildfire", "A", "BULLDOG"))
        self.assertEqual(row["end"], arcgis.esri_date(p["FireOutDateTime"]))
        self.assertEqual(row["start"], arcgis.esri_date(p["FireDiscoveryDateTime"]))
        self.assertEqual(row["attributes"]["out"], common.iso(row["end"]))

    def test_a_prescribed_fire_goes_quiet_after_three_days(self):
        sid, p, g = self.fires["RX HIGH VALLEY"]
        modified = arcgis.esri_date(p["ModifiedOnDateTime_dt"])
        row, is_open = inc.row_of(sid, p, g, modified + timedelta(days=1))
        self.assertEqual((row["kind"], row["end"], is_open), ("prescribed_fire", None, True))
        self.assertFalse(inc.row_of(sid, p, g, modified + timedelta(days=4))[1])

    def test_contained_is_still_open_withdrawn_is_not(self):
        sid, p, g = self.fires["WOODRIDGE"]
        p = {k: v for k, v in p.items() if k != "FireOutDateTime"}
        p.update({"IncidentSize": 400, "PercentContained": 100})
        modified = arcgis.esri_date(p["ModifiedOnDateTime_dt"])
        self.assertTrue(inc.row_of(sid, p, g, modified + timedelta(days=10))[1])     # 14-day window
        self.assertFalse(inc.row_of(sid, p, g, modified + timedelta(days=15))[1])
        self.assertFalse(inc.row_of(sid, {**p, "IsValid": 0}, g, modified)[1])

    def test_the_event_hash_follows_the_record(self):
        sid, p, g = self.fires["WOODRIDGE"]
        at = datetime(2026, 10, 7, tzinfo=UTC)
        a = inc.row_of(sid, p, g, at)[0]["content_hash"]
        self.assertEqual(a, inc.row_of(sid, dict(p), dict(g), at + timedelta(hours=1))[0]["content_hash"])
        self.assertNotEqual(a, inc.row_of(sid, {**p, "IncidentSize": 36}, g, at)[0]["content_hash"])


class PerimeterTest(unittest.TestCase):
    def setUp(self):
        self.features = load("wfigs_perimeters.json")
        self.parsed, self.duplicates = per.parse(self.features)
        self.fires = by_name(self.parsed, "poly_IncidentName")

    def test_keyed_by_the_polygons_irwin_id(self):
        self.assertEqual(sorted(self.fires), ["GOODSON", "HARTLEY"])
        sid, payload, geom = self.fires["GOODSON"]
        self.assertNotIn("attr_IrwinID", payload)                 # a final perimeter leaves it empty
        self.assertEqual(sid, payload["poly_IRWINID"].upper())
        for gone in ("OBJECTID", "GlobalID", "Shape__Area", "Shape__Length", "poly_SourceOID"):
            self.assertNotIn(gone, payload)
        self.assertEqual(payload["_geom"], arcgis.geom_digest(geom))
        self.assertEqual(geom["type"], "Polygon")
        ring = geom["coordinates"][0]
        self.assertEqual(ring[0], ring[-1])
        self.assertEqual(self.duplicates, 0)

    def test_key_fallbacks(self):
        self.assertEqual(per.key({"attr_IrwinID": "{ab}"}), "{AB}")
        self.assertEqual(per.key({"poly_SourceGlobalID": "{cd}"}), "sg:{CD}")
        self.assertIsNone(per.key({}))

    def test_a_final_perimeter_wins_over_a_daily_one(self):
        goodson = next(f for f in self.features if f["attributes"]["poly_IncidentName"] == "GOODSON")
        daily = copy.deepcopy(goodson)
        daily["attributes"].update({"poly_FeatureCategory": "Wildfire Daily Fire Perimeter",
                                    "poly_DateCurrent": goodson["attributes"]["poly_DateCurrent"] + 86400000})
        daily["geometry"]["rings"][0] = daily["geometry"]["rings"][0][:-4] + [daily["geometry"]["rings"][0][0]]
        for order in ([goodson, daily], [daily, goodson]):
            parsed, dups = per.parse(order)
            (payload, _), = parsed.values()
            self.assertEqual((payload["poly_FeatureCategory"], dups), ("Wildfire Final Fire Perimeter", 1))

    def test_a_changed_line_is_a_new_version_float_noise_is_not(self):
        sid, p, _ = self.fires["HARTLEY"]
        moved = copy.deepcopy(self.features)
        noisy = copy.deepcopy(self.features)
        for fs, dx in ((moved, 0.001), (noisy, 0.0000001)):
            f = next(f for f in fs if f["attributes"]["poly_IncidentName"] == "HARTLEY")
            f["geometry"]["rings"][0][3][0] += dx
        self.assertNotEqual(version_hash(per.parse(moved)[0][sid][0]), version_hash(p))
        self.assertEqual(version_hash(per.parse(noisy)[0][sid][0]), version_hash(p))

    def test_rows_use_the_newer_of_the_two_modified_stamps(self):
        sid, p, g = self.fires["HARTLEY"]
        row, _ = per.row_of(sid, p, g, datetime(2026, 10, 7, tzinfo=UTC))
        newest = max(arcgis.esri_date(p["attr_ModifiedOnDateTime_dt"]), arcgis.esri_date(p["poly_DateCurrent"]))
        self.assertEqual(row["attributes"]["modified"], common.iso(newest))
        self.assertEqual((row["kind"], row["description"]), ("fire_perimeter", "HARTLEY"))
        open_p = {k: v for k, v in p.items() if k != "attr_FireOutDateTime"}
        self.assertTrue(per.row_of(sid, open_p, g, newest + timedelta(days=1))[1])
        self.assertFalse(per.row_of(sid, {**open_p, "poly_DeleteThis": "Yes"}, g, newest)[1])


if __name__ == "__main__":
    unittest.main()
