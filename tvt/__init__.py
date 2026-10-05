"""Treasure Valley traffic data platform: ingestors, store, and aggregator.

Collects public, permitted data about the Ada/Canyon County road network into
a local SQLite database and builds a combined map view. See tvt/README.md.
"""

import os

# Ada + Canyon counties, roughly: (south, west, north, east)
BBOX = (43.25, -117.05, 43.80, -116.05)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("TVT_DATA", os.path.join(ROOT, "data"))
DB_PATH = os.path.join(DATA_DIR, "tvt.sqlite")
SITE_DIR = os.path.join(ROOT, "site")


def in_bbox(lat, lon, bbox=BBOX):
    s, w, n, e = bbox
    return lat is not None and lon is not None and s <= lat <= n and w <= lon <= e
