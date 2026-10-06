"""Offline tests for the ITD WZDx stream's cleaning and change detection.

Run: python3 -m unittest discover -s ingest/tests -t .
The features below copy the shapes seen in Idaho's feed on Oct 6, 2026 (docs/08 §8.8).
"""

import copy
import json
import os
import unittest
from datetime import datetime, timezone

from ingest.sources import itd_wzdx as wz

UTC = timezone.utc


def feature(fid="5260-1", **props):
    p = {
        "core_details": {"event_type": "work-zone", "data_source_id": "ERS", "road_names": ["W Chinden Blvd"],
                         "direction": "eastbound", "description": " Road construction on W Chinden Blvd. ",
                         "update_date": "2026-09-29T03:27:14Z",
                         "related_road_events": [{"type": "next-occurrence", "id": "abc="}]},
        "road_event_id": "5260",
        "start_date": "2026-10-06T14:00:00Z", "end_date": "2026-10-06T22:59:59Z",
        "is_start_date_verified": False, "is_end_date_verified": False,
        "is_start_position_verified": False, "is_end_position_verified": False,
        "location_method": "unknown", "vehicle_impact": "some-lanes-closed",
        "lanes": [{"order": 1, "type": "general", "status": "open"}, {"order": 2, "type": "general", "status": "closed"}],
        "reduced_speed_limit_kph": 72.42, "work_zone_type": "static",
        "worker_presence": {"are_workers_present": True, "definition": ["workers-in-work-zone-working"]},
        "beginning_cross_street": "N McDermott Rd", "ending_cross_street": "",
        "types_of_work": [], "impacted_cds_curb_zones": [],
    }
    p.update(props)
    return {"type": "Feature", "id": fid, "properties": p,
            "geometry": {"type": "LineString", "coordinates": [[-116.5, 43.66], [-116.49, 43.66]]}}


class CleanTest(unittest.TestCase):
    def test_a_normal_work_zone(self):
        r = wz.clean(feature())
        self.assertEqual((r["source_id"], r["kind"]), ("5260-1", "work_zone"))
        self.assertEqual((r["start"], r["end"]), (datetime(2026, 10, 6, 14, 0, tzinfo=UTC),
                                                  datetime(2026, 10, 6, 22, 59, 59, tzinfo=UTC)))
        a = r["attributes"]
        self.assertEqual(a["reduced_speed_mph"], 45)                              # 72.42 km/h
        self.assertEqual(a["parent_event"], "5260")
        self.assertEqual(a["related"], {"next-occurrence": ["abc="]})
        self.assertEqual([lane["status"] for lane in a["lanes"]], ["open", "closed"])
        self.assertEqual((a["location_verified"], a["times_verified"], a["fixes"]), (False, False, []))
        self.assertEqual(r["description"], "Road construction on W Chinden Blvd.")
        self.assertIsNone(a["ending_cross_street"])

    def test_overnight_end_a_day_early_is_moved_forward(self):
        r = wz.clean(feature(start_date="2026-10-08T04:00:00Z", end_date="2026-10-07T11:59:59Z"))
        self.assertEqual(r["end"], datetime(2026, 10, 8, 11, 59, 59, tzinfo=UTC))   # 10 PM to 6 AM local
        self.assertEqual(r["attributes"]["fixes"], ["end_date_moved_a_day"])

    def test_end_far_before_start_is_left_open(self):
        r = wz.clean(feature(start_date="2026-10-08T04:00:00Z", end_date="2026-10-01T00:00:00Z"))
        self.assertIsNone(r["end"])
        self.assertEqual(r["attributes"]["fixes"], ["end_before_start"])

    def test_bad_values_are_dropped(self):
        r = wz.clean(feature(reduced_speed_limit_kph="NaN", work_zone_type=""))
        self.assertIsNone(r["attributes"]["reduced_speed_mph"])
        self.assertIsNone(r["attributes"]["work_zone_type"])
        self.assertEqual(r["attributes"]["fixes"], ["speed_not_a_number", "work_zone_type_empty"])
        self.assertIsNone(wz.clean(feature(reduced_speed_limit_kph=float("nan")))["attributes"]["reduced_speed_mph"])

    def test_every_speed_seen_is_a_round_mph(self):
        speeds = {24.14: 15, 40.234: 25, 56.327: 35, 72.42: 45, 88.514: 55, 104.607: 65, 112.654: 70}
        for kph, mph in speeds.items():
            self.assertEqual(wz.clean(feature(reduced_speed_limit_kph=kph))["attributes"]["reduced_speed_mph"], mph)

    def test_single_points_and_their_own_ids(self):
        f = feature("IWj0hpLhUI7aapYJy4XZVJkdNnc=", road_event_id="IWj0hpLhUI7aapYJy4XZVJkdNnc=")
        f["geometry"] = {"type": "MultiPoint", "coordinates": [[-116.2, 43.6]]}
        r = wz.clean(f)
        self.assertEqual(r["geom"]["type"], "MultiPoint")                        # kept as published
        self.assertIsNone(r["attributes"]["parent_event"])

    def test_content_hash_follows_content(self):
        a, b = wz.clean(feature()), wz.clean(feature())
        self.assertEqual(a["content_hash"], b["content_hash"])
        self.assertNotEqual(a["content_hash"], wz.clean(feature(vehicle_impact="all-lanes-open"))["content_hash"])


class SnapshotTest(unittest.TestCase):
    def test_header_times_dont_count_as_a_change(self):
        feed = {"type": "FeatureCollection", "feed_info": {"update_date": "2026-10-06T15:39:15.0282324+00:00"},
                "features": [feature()]}
        later = copy.deepcopy(feed)
        later["feed_info"]["update_date"] = "2026-10-06T15:43:55.4538608+00:00"
        self.assertEqual(wz.content_digest(feed), wz.content_digest(later))
        later["features"][0]["properties"]["vehicle_impact"] = "all-lanes-closed"
        self.assertNotEqual(wz.content_digest(feed), wz.content_digest(later))

    def test_restart_knows_the_last_archived_snapshot(self):
        import shutil, tempfile
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        self.assertIsNone(wz.latest_archived_digest(root))
        old = {"features": [feature("1")]}
        new = {"feed_info": {"update_date": "x"}, "features": [feature("2")]}
        wz.write_archive(root, json.dumps(old).encode(), datetime(2026, 10, 6, 23, 59, tzinfo=UTC))
        wz.write_archive(root, json.dumps(new).encode(), datetime(2026, 10, 7, 0, 4, tzinfo=UTC))
        self.assertEqual(wz.latest_archived_digest(root), wz.content_digest(new))

    def test_archive_paths_round_trip(self):
        when = datetime(2026, 10, 6, 15, 39, 15, tzinfo=UTC)
        path = wz.archive_path("/a", when)
        self.assertEqual(path, os.path.join("/a", "wzdx", "2026-10-06", "wzdx-153915Z.json.gz"))
        self.assertEqual(wz.archive_time(path), when)


if __name__ == "__main__":
    unittest.main()
