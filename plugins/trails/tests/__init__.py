"""Tests for the trails plugin. Shared here: the fixtures (synthetic: the City's layers are
not ours to copy) and a fake ArcGIS server that answers the requests arcgis.fetch_layer makes."""

import json
import os
import re
import urllib.parse
from datetime import datetime, timezone

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


class FakeLayers:
    """Answers layer descriptions (?f=json), ID lists, OBJECTID-range queries and by-ID queries
    from {layer URL: Esri JSON answer}, like ArcGIS Online. Records every URL asked for."""

    def __init__(self, answers, descriptions=None):
        self.answers, self.descriptions, self.urls = answers, descriptions or {}, []

    def __call__(self, url):
        self.urls.append(url)
        base, _, query = url.partition("?")
        q = dict(urllib.parse.parse_qsl(query))
        if base in self.descriptions and q.get("f") == "json" and len(q) == 1:
            return 200, json.dumps(self.descriptions[base]).encode(), "no_rules"
        layer = base[:-len("/query")]
        answer = self.answers[layer]
        feats = answer["features"]
        oid = answer.get("objectIdFieldName", "OBJECTID")
        if q.get("returnIdsOnly") == "true":
            body = {"objectIdFieldName": oid, "objectIds": [f["attributes"][oid] for f in feats]}
        elif "objectIds" in q:
            wanted = {int(i) for i in q["objectIds"].split(",")}
            body = {**answer, "features": [f for f in feats if f["attributes"][oid] in wanted]}
        else:
            lo, hi = (int(x) for x in re.search(rf"{oid} >= (\d+) AND {oid} <= (\d+)", q["where"]).groups())
            body = {**answer, "features": sorted((f for f in feats if lo <= f["attributes"][oid] <= hi),
                                                 key=lambda f: f["attributes"][oid])}
        return 200, json.dumps(body).encode(), "no_rules"


class FakeFetch:
    """Stands in for db.Fetch (no database)."""

    def __init__(self, conn, source):
        self.http_status = self.robots = self.records = self.bytes = None
        self.started_at, self.id = datetime(2026, 10, 7, 12, tzinfo=timezone.utc), 1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def interval_s(text):
    """A Postgres interval like '30 minutes' or '1 hour' in seconds (the forms the sources use)."""
    n, unit = re.fullmatch(r"(\d+) (minute|hour|day)s?", text).groups()
    return int(n) * {"minute": 60, "hour": 3600, "day": 86400}[unit]
