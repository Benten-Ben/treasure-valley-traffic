"""OpenStreetMap's other streets and alleys: roads.osm_street (landscape sprint, plan C1, C2, C10).

A consumer of core's OpenStreetMap loader (ingest/osm_extract.py): no download
and no schedule. The owner downloads the Idaho extract by hand (Geofabrik's
robots.txt disallows scripts), and

    python3 -m ingest osm-load --inbox              # a new extract: every consumer
    python3 -m ingest osm-load --only osm_street    # this one, on the extract we hold

loads it, with its own MD5 gate in ops.osm_consumer (migration 0019). It
loads only the extract osm_valley holds (or loads in the same run), so
core.osm_way and roads.osm_street always split one extract's ways between
them; a build that reads both calls osm_extract.check_partition() first.

What it keeps: the highway ways core's partition gives it (osm_extract.owner),
by tags alone: residential, unclassified, living_street, road and busway, and
alleys (highway=service + service=alley), unless drawn as an area. osm_valley
keeps any of them tagged with lanes (core.osm_way, unchanged), so each way has
one owner. Lines only, with every way that has a node in the valley box kept
whole. Approved by the owner, Oct 8 (decision 2a), for real-width roads: with
core.osm_way it gives the roads build every carriageway (plan P7).

Stored in roads.osm_street (plugins/roads/migrations/0001), versioned in place
(plan C2): no raw.record copies; osm_version and osm_timestamp, first_seen and
last_seen, and ways missing from a load become inactive.

License ODbL: credit "© OpenStreetMap contributors". Its own table, so other
sources' tables aren't pulled under the ODbL.
"""

import json

from ingest import osm_extract
from .osm_valley import _text, effective_oneway, parse_bridge, parse_layer, parse_width

SOURCE = {
    "name": "osm_street",
    "title": "OpenStreetMap: the valley's other streets and alleys",
    "url": osm_extract.PAGE,
    "access": "open",
    "schedule": None,   # loaded by hand: Geofabrik's robots.txt disallows scripted downloads (Oct 6, 2026)
    "license": "ODbL",
    "credit": "© OpenStreetMap contributors",
    "notes": "A consumer of the OpenStreetMap loader (python3 -m ingest osm-load): residential, unclassified, "
             "living street, road and busway ways and alleys that osm_valley doesn't keep, cut to the valley box. "
             "roads.osm_street, its own table (ODbL), versioned in place.",
}

TABLE = "roads.osm_street"
COLUMNS = [("osm_id", "bigint"), ("highway", "text"), ("service", "text"), ("name", "text"), ("ref", "text"),
           ("oneway", "text"), ("width_m", "real"), ("surface", "text"), ("access", "text"), ("maxspeed", "text"),
           ("layer", "smallint"), ("bridge", "boolean"), ("tunnel", "boolean"), ("tags", "jsonb"),
           ("osm_version", "int"), ("osm_timestamp", "timestamptz")]


def parse_tunnel(v):
    """tunnel=yes, culvert, building_passage, ... is a tunnel; absent or 'no' isn't."""
    return parse_bridge(v)


def street_row(f):
    """One feature (osm_extract's dict) as a row: COLUMNS' values, then the geometry as GeoJSON."""
    tags = f["tags"]
    return (f["osm_id"], tags["highway"], _text(tags.get("service")) if tags["highway"] == "service" else None,
            _text(tags.get("name")), _text(tags.get("ref")), effective_oneway(tags), parse_width(tags.get("width")),
            _text(tags.get("surface")), _text(tags.get("access")), _text(tags.get("maxspeed")),
            parse_layer(tags.get("layer")), parse_bridge(tags.get("bridge")), parse_tunnel(tags.get("tunnel")),
            json.dumps(tags, ensure_ascii=False), f["osm_version"], f["osm_timestamp"], json.dumps(f["geom"]))


def consume(conn, run):
    """Store this consumer's ways from the loader's cut (run.features(): its tags, the box and the
    partition already applied). Doesn't commit: the loader does, with its gate."""
    rows = [street_row(f) for f in run.features() if f["type"] == "w" and f["geometry"] == "linestring"]
    stats = osm_extract.store_objects(conn, TABLE, COLUMNS, rows, run.seen_at, allow_shrink=run.allow_shrink)
    stats["alleys"] = sum(1 for r in rows if r[2] == "alley")
    return stats
