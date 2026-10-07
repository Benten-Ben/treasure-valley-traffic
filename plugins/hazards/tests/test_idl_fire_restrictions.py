"""Tests for IDL's fire-restriction stages (ingest/sources/idl_fire_restrictions.py). Offline.

The fixture is synthetic (IDL states no license): the layer's real field names with
made-up zones, stages, dates and outlines.

Run: python3 -m unittest discover -s plugins/hazards/tests -t .
"""

import copy
import json
import os
import unittest
from unittest import mock

from ingest.db import version_hash
from plugins.hazards.ingest.sources import idl_fire_restrictions as idl

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
A = "{00000000-0000-4000-8000-00000000000A}"
B = "{00000000-0000-4000-8000-00000000000B}"


def features():
    with open(os.path.join(FIXTURES, "idl_zones.json"), encoding="utf-8") as f:
        return json.load(f)["features"]


class ParseTest(unittest.TestCase):
    def test_zones_keyed_by_globalid_without_people_or_shape_statistics(self):
        parsed = idl.parse(features())
        self.assertEqual(sorted(parsed), [A, B, "{00000000-0000-4000-8000-00000000000C}"])
        payload, geom = parsed[A]
        for gone in ("OBJECTID", "Shape.STArea()", "Shape.STLength()", "last_edited_user", "DateRescinded"):
            self.assertNotIn(gone, payload)
        self.assertEqual((payload["Name"], payload["Stage"], payload["UpcomingStage"]),
                         ("Example North Zone", "Stage I", "Stage II"))
        self.assertTrue(payload["_geom"])
        self.assertEqual(geom["type"], "Polygon")

    def test_a_zone_in_two_parts_with_a_hole(self):
        _, geom = idl.parse(features())[B]
        self.assertEqual(geom["type"], "MultiPolygon")
        self.assertEqual([len(p) for p in geom["coordinates"]], [2, 1])

    def test_a_moved_outline_is_a_new_version(self):
        moved = features()
        moved[0]["geometry"]["rings"][0][1][1] += 0.01
        self.assertNotEqual(version_hash(idl.parse(features())[A][0]), version_hash(idl.parse(moved)[A][0]))


class EventsTest(unittest.TestCase):
    def test_stages_in_force_and_announced(self):
        rows = {r["source_id"]: r for r in idl.rows(idl.parse(features()))}
        self.assertEqual(sorted(rows), [f"{A}|Stage I|2026-07-15T14:00:00Z", f"{A}|upcoming|Stage II"])
        now = rows[f"{A}|Stage I|2026-07-15T14:00:00Z"]
        self.assertEqual((now["kind"], now["severity"], now["end"]), ("fire_restriction", "Stage I", None))
        self.assertEqual(now["start"].isoformat(), "2026-07-15T14:00:00+00:00")
        self.assertEqual(now["attributes"]["area"], "Example Fire Restriction Area")
        self.assertEqual(rows[f"{A}|upcoming|Stage II"]["kind"], "fire_restriction_announced")
        self.assertTrue(all(r["content_hash"] for r in rows.values()))

    def test_stage_ii_is_a_new_lifecycle_and_none_closes_it(self):
        fs = features()
        fs[0]["attributes"].update({"Stage": "Stage II", "UpcomingStage": None, "DateEnacted": 1785000000000})
        self.assertEqual([r["source_id"] for r in idl.rows(idl.parse(fs))], [f"{A}|Stage II|2026-07-25T17:20:00Z"])
        fs[0]["attributes"]["Stage"] = "None"
        self.assertEqual(idl.rows(idl.parse(fs)), [])

    def test_no_restriction_words(self):
        for stage in (None, "", " ", "None", "NONE", "No Restrictions"):
            self.assertFalse(idl.in_force(stage), stage)
        self.assertTrue(idl.in_force("Stage I"))


class ChangeCheckTest(unittest.TestCase):
    def test_the_attributes_only_read_against_what_we_hold(self):
        stored = idl.parse(features())
        current = idl.attributes_by_zone([{"attributes": f["attributes"]} for f in features()])
        self.assertTrue(idl.unchanged(current, stored))
        self.assertFalse(idl.unchanged(current, {}))                               # nothing held yet
        edited = copy.deepcopy(current)
        edited[A]["last_edited_date"] += 1000                                      # any edit, outline included
        self.assertFalse(idl.unchanged(edited, stored))
        fewer = {k: v for k, v in current.items() if k != B}
        self.assertFalse(idl.unchanged(fewer, stored))

    def test_an_unchanged_layer_reads_no_outlines(self):
        conn = mock.MagicMock()
        attrs_only = [{"attributes": f["attributes"]} for f in features()]
        with mock.patch.object(idl.db, "ensure_source"), mock.patch.object(idl.db, "Fetch") as fetch, \
                mock.patch.object(idl.common, "query_layer", return_value=(attrs_only, 5000, 200, "no_rules")) as q, \
                mock.patch.object(idl.common, "latest", return_value=idl.parse(features())), \
                mock.patch.object(idl.common, "heartbeat", return_value=3) as beat:
            fetch.return_value.__enter__.return_value = mock.MagicMock(started_at="t")
            stats = idl.run(conn, sleep=lambda s: None)
        self.assertEqual(q.call_count, 1)
        self.assertEqual(q.call_args.kwargs["geometry"], False)
        beat.assert_called_once()
        self.assertEqual(stats, {"zones": 3, "unchanged": 3, "outlines read": False})

    def test_a_changed_layer_reads_outlines_and_stores(self):
        conn = mock.MagicMock()
        attrs_only = [{"attributes": f["attributes"]} for f in features()]
        answers = [(attrs_only, 5000, 200, "no_rules"), (features(), 850000, 200, "no_rules")]
        with mock.patch.object(idl.db, "ensure_source"), mock.patch.object(idl.db, "Fetch") as fetch, \
                mock.patch.object(idl.common, "query_layer", side_effect=answers) as q, \
                mock.patch.object(idl.common, "latest", return_value={}), \
                mock.patch.object(idl, "store", return_value={"zones": 3}) as store:
            fetch.return_value.__enter__.return_value = mock.MagicMock(started_at="t")
            stats = idl.run(conn, sleep=lambda s: None)
        self.assertEqual([c.kwargs["geometry"] for c in q.call_args_list], [False, True])
        self.assertEqual(q.call_args_list[1].kwargs["precision"], 5)
        self.assertEqual(sorted(store.call_args.args[3]), sorted(idl.parse(features())))
        self.assertEqual(stats, {"zones": 3, "outlines read": True})


if __name__ == "__main__":
    unittest.main()
