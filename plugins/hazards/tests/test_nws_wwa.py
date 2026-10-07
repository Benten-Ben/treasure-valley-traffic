"""Tests for NWS watches, warnings and advisories (ingest/sources/nws_wwa.py). Offline.

The fixture has the WWA layer's real field names and formats (Oct 7, 2026 sample) with
made-up alerts in the ring.

Run: python3 -m unittest discover -s plugins/hazards/tests -t .
"""

import copy
import json
import os
import unittest
from datetime import datetime, timezone
from unittest import mock

from ingest.db import version_hash
from plugins.hazards.ingest.sources import nws_wwa as nws

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
UTC = timezone.utc
RFW = "KBOI.FW.W.0012.2026"
FLOOD = "KBOI.FA.A.0003.2026"
SPS = "Special Weather Statement|urn:oid:2.49.0.1.840.0.0000000000000000000000000000000000000002.001.1"


def features():
    with open(os.path.join(FIXTURES, "nws_wwa.json"), encoding="utf-8") as f:
        return json.load(f)["features"]


class GroupTest(unittest.TestCase):
    def test_events_by_vtec_and_people_dropped(self):
        parsed, dropped = nws.parse(features())
        self.assertEqual(sorted(parsed), sorted([RFW, FLOOD, SPS]))
        self.assertEqual(dropped, 1)                                     # the Child Abduction Emergency
        self.assertNotIn("Child Abduction", json.dumps(parsed))

    def test_people_alerts_dropped_by_name_or_code(self):
        for attrs in ({"prod_type": "Missing and Endangered Persons", "msg_type": " "},
                      {"prod_type": "Blue Alert"}, {"prod_type": "Renamed Product", "msg_type": "lew"}):
            self.assertTrue(nws.person_related(attrs), attrs)
        self.assertFalse(nws.person_related({"prod_type": "Red Flag Warning", "msg_type": "NEW"}))

    def test_one_event_over_two_zones(self):
        payload, geom = nws.parse(features())[0][RFW]
        self.assertEqual((payload["parts"], len(payload["products"])), (2, 1))
        self.assertEqual(geom["type"], "MultiPolygon")
        self.assertEqual(len(geom["coordinates"]), 2)
        for gone in ("objectid", "idp_filedate", "idp_ingestdate", "url"):
            self.assertNotIn(gone, json.dumps(payload))
        self.assertEqual(payload["products"][0]["cap_id"],
                         "urn:oid:2.49.0.1.840.0.0000000000000000000000000000000000000001.001.1")

    def test_a_reload_changes_nothing(self):
        reloaded = copy.deepcopy(features())[::-1]
        for i, f in enumerate(reloaded):
            f["attributes"].update({"objectid": 100 + i, "idp_filedate": 1, "idp_ingestdate": 2})
        a, _ = nws.parse(features())
        b, _ = nws.parse(reloaded)
        self.assertEqual({k: version_hash(p) for k, (p, _) in a.items()}, {k: version_hash(p) for k, (p, _) in b.items()})

    def test_an_active_event_keeps_its_year_across_january(self):
        attrs = {"wfo": "KBOI", "phenom": "WS", "sig": "W", "event": "0040", "issuance": "2027-01-01T03:00:00-07:00"}
        self.assertEqual(nws.event_key(attrs), "KBOI.WS.W.0040.2027")
        self.assertEqual(nws.event_key(attrs, active={"KBOI.WS.W.0040.2026", "KBOI.WS.W.0041.2026"}),
                         "KBOI.WS.W.0040.2026")
        self.assertIsNone(nws.vtec({"wfo": " ", "phenom": " ", "sig": " ", "event": " "}))


class RowTest(unittest.TestCase):
    def setUp(self):
        self.parsed, _ = nws.parse(features())

    def test_declared_from_onset_to_end(self):
        row = nws.row_of(RFW, *self.parsed[RFW])
        self.assertEqual((row["kind"], row["severity"], row["description"]),
                         ("weather_alert", "warning", "Red Flag Warning"))
        self.assertEqual((row["start"], row["end"]), (datetime(2026, 8, 10, 18, tzinfo=UTC),
                                                      datetime(2026, 8, 11, 3, tzinfo=UTC)))
        self.assertEqual(row["attributes"]["expires"], "2026-08-11T03:00:00Z")
        self.assertEqual(row["attributes"]["etn"], "0012")

    def test_until_further_notice_has_no_end(self):
        row = nws.row_of(FLOOD, *self.parsed[FLOOD])
        self.assertEqual((row["severity"], row["end"]), ("watch", None))
        self.assertEqual(nws.row_of(SPS, *self.parsed[SPS])["severity"], None)


class RereadTest(unittest.TestCase):
    NOW = datetime(2026, 8, 10, 20, tzinfo=UTC)

    def test_vanished_before_expiry(self):
        active = {"a": datetime(2026, 8, 11, tzinfo=UTC), "b": datetime(2026, 8, 10, 19, tzinfo=UTC), "c": None,
                  "d": datetime(2026, 8, 11, tzinfo=UTC)}
        self.assertEqual(nws.vanished_early(active, {"d"}, self.NOW), ["a"])

    def run_with(self, answers, active):
        conn, pauses = mock.MagicMock(), []
        with mock.patch.object(nws.db, "ensure_source"), mock.patch.object(nws.db, "Fetch") as fetch, \
                mock.patch.object(nws.common, "query_layer", side_effect=answers) as q, \
                mock.patch.object(nws, "active_events", return_value=active), \
                mock.patch.object(nws, "store", side_effect=lambda c, i, t, parsed: {"alerts": len(parsed)}):
            f = mock.MagicMock(started_at=self.NOW, bytes=0)
            fetch.return_value.__enter__.return_value = f
            stats = nws.run(conn, sleep=pauses.append)
        return stats, q.call_count, pauses

    def test_read_again_when_an_unexpired_alert_vanishes(self):
        answers = [([], 100, 200, "no_rules"), (features(), 9000, 200, "no_rules")]
        stats, calls, pauses = self.run_with(answers, {RFW: datetime(2026, 8, 11, 3, tzinfo=UTC)})
        self.assertEqual((calls, pauses, stats["alerts"], stats["read twice"]), (2, [30], 3, True))

    def test_one_read_when_nothing_vanished(self):
        stats, calls, pauses = self.run_with([(features(), 9000, 200, "no_rules")], {RFW: None})
        self.assertEqual((calls, pauses, stats["read twice"], stats["person-related dropped"]), (1, [], False, 1))


if __name__ == "__main__":
    unittest.main()
