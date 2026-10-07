"""Tests for the shared ArcGIS reader (ingest/arcgis.py) against a fake layer.

The pager's tests on box-cut layers are with the roads plugin
(plugins/roads/tests/test_lane_sources.py, PagerTest), which uses ITD's box.

Run: python3 -m unittest discover -s ingest/tests -t .
"""

import json
import re
import unittest
import urllib.parse
from unittest import mock

from ingest import arcgis


class FakeLayer:
    """An ArcGIS layer as a server serves it: IDs on request, features in its own order
    (not ours), at most `cap` per answer. ignore_query answers every feature query with
    the same first page (as if it ignored where and resultOffset); lose drops features."""

    def __init__(self, order, cap=3, oid_field="OBJECTID", ignore_query=False, lose=()):
        self.order, self.cap, self.oid_field = order, cap, oid_field
        self.ignore_query, self.lose, self.calls = ignore_query, set(lose), 0

    def get(self, url, timeout=90, compressed=False):
        self.calls += 1
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        if q.get("returnIdsOnly") == ["true"]:
            body = {"objectIdFieldName": self.oid_field, "objectIds": self.order}
        else:
            sel = [i for i in self.order if i not in self.lose]
            if self.ignore_query:
                pass
            elif "objectIds" in q:                                # by ID (the pager's second chance)
                listed = {int(i) for i in q["objectIds"][0].split(",")}
                sel = [i for i in sel if i in listed]
            else:
                lo, hi = (int(t) for t in re.findall(r"(?:>=|<=) (\d+)", q["where"][0]))
                sel = [i for i in sel if lo <= i <= hi]
            body = {"objectIdFieldName": self.oid_field, "exceededTransferLimit": len(sel) > self.cap,
                    "features": [{"attributes": {self.oid_field: i, "Purpose": "TS"}, "geometry": {"x": -116.3, "y": 43.6}}
                                 for i in sel[:self.cap]]}
        return 200, json.dumps(body).encode(), "no_rules"


class FetchLayerTest(unittest.TestCase):
    def fetch(self, fake, **kw):
        with mock.patch.object(arcgis.http, "get", fake.get):
            return arcgis.fetch_layer("https://x/FeatureServer/15", "test", pause_s=0, **kw)

    def ids(self, features, field="OBJECTID"):
        return [f["attributes"][field] for f in features]

    def test_an_unordered_server_with_small_pages_gives_every_feature_once(self):
        features, nbytes, status, robots = self.fetch(FakeLayer([4, 1, 5, 2, 3], cap=3))
        self.assertEqual(self.ids(features), [1, 2, 3, 4, 5])
        self.assertEqual((status, robots), (200, "no_rules"))
        fake = FakeLayer(list(range(2469, 0, -1)), cap=2000, oid_field="objectid")
        self.assertEqual(self.ids(self.fetch(fake)[0], "objectid"), list(range(1, 2470)))
        self.assertEqual(fake.calls, 1 + 5)                      # the IDs, then 500 at a time

    def test_a_server_that_ignores_the_query_fails_instead_of_looping(self):
        fake = FakeLayer([4, 1, 5, 2, 3], cap=3, ignore_query=True)
        with self.assertRaises(RuntimeError):
            self.fetch(fake, batch=2)
        self.assertLessEqual(fake.calls, 4)

    def test_a_listed_feature_that_never_comes_back_fails_the_fetch(self):
        with self.assertRaises(RuntimeError):
            self.fetch(FakeLayer([1, 2, 3, 4, 5], cap=10, lose=[5]))

    def test_an_empty_layer_is_empty(self):
        self.assertEqual(self.fetch(FakeLayer([]))[0], [])


if __name__ == "__main__":
    unittest.main()
