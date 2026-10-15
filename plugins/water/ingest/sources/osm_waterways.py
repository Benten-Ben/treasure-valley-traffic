"""OpenStreetMap's water: water.osm_feature (landscape sprint, package P4-data; plan C1, C2).

A consumer of core's OpenStreetMap loader (ingest/osm_extract.py): no download and no schedule. The owner downloads
the Idaho extract by hand (Geofabrik's robots.txt disallows scripts), and

    python3 -m ingest osm-load --inbox                  # a new extract: every consumer
    python3 -m ingest osm-load --only osm_waterways     # this one, on the extract we hold (light, on the valley cut)

loads it, with its own MD5 gate in ops.osm_consumer (migration 0019). Water isn't part of the highway partition, so
it loads whichever extract it's given; water-build records the MD5 it read.

What it keeps (the owner's OK of Oct 8, decision 2b: "waterways, natural=water, wetland and spring, water=*,
reservoirs and basins, including about 4,800 swimming pools, drawn only from z15"):
- lines: every way tagged waterway=* (rivers, streams, canals, ditches, drains; dams and weirs drawn as lines);
- areas: natural=water, wetland and spring; water=*; landuse=reservoir and basin; waterway=riverbank, dock,
  boatyard, dam and weir drawn as areas; leisure=swimming_pool (the pools of decision 2b: OSM tags them so);
- points: nodes tagged waterway=* (weirs, dams, lock gates, waterfalls, sluice gates) and natural=spring.
Every object with a node in the valley box, whole; multipolygons with a member in it, whole.

Each object gets a `kind` (KINDS, by kind_of()), its name, intermittent (intermittent=yes or seasonal=yes; null when
untagged), piped (any tunnel=*, covered=yes, location=underground, waterway=pressurised), width in metres, layer, and
every tag. A closed way that's both a waterway line and an area (a riverbank) comes as both, keyed by shape.

Stored in water.osm_feature (plugins/water/migrations/0001), versioned in place (plan C2): no raw.record copies;
osm_version and osm_timestamp, first_seen and last_seen, and objects missing from a load become inactive. A load marks
water-build out of date, in the same transaction.

License ODbL: credit "© OpenStreetMap contributors". Its own table, so other sources' tables aren't pulled under the
ODbL; the drawn network, which carries OSM's geometry, is ODbL.
"""

import json
import re

from ingest import osm_extract

SOURCE = {
    "name": "osm_waterways",
    "title": "OpenStreetMap: the valley's waterways, water areas, wetlands, pools and water structures",
    "url": osm_extract.PAGE,
    "access": "open",
    "schedule": None,   # loaded by hand: Geofabrik's robots.txt disallows scripted downloads (Oct 6, 2026)
    "license": "ODbL",
    "credit": "© OpenStreetMap contributors",
    "notes": "A consumer of the OpenStreetMap loader (python3 -m ingest osm-load): waterway=*, natural=water, wetland "
             "and spring, water=*, landuse=reservoir and basin, and leisure=swimming_pool, cut to the valley box. "
             "water.osm_feature, its own table (ODbL), versioned in place.",
}

TABLE = "water.osm_feature"
BUILD = "water-build"
COLUMNS = [("osm_type", "text"), ("osm_id", "bigint"), ("shape", "text"), ("kind", "text"), ("name", "text"),
           ("intermittent", "boolean"), ("piped", "boolean"), ("width_m", "real"), ("layer", "smallint"),
           ("tags", "jsonb"), ("osm_version", "int"), ("osm_timestamp", "timestamptz")]
KEY = ("osm_type", "osm_id", "shape")

# Kinds by shape. Lines: the waterway classes water-build draws, then structures drawn as lines, then the rest.
LINE_KINDS = {"river": "river", "stream": "stream", "brook": "stream", "canal": "canal", "ditch": "ditch",
              "drain": "drain", "pressurised": "canal", "dam": "dam", "weir": "weir", "lock_gate": "lock_gate",
              "waterfall": "waterfall", "spillway": "waterway", "fish_pass": "waterway", "tidal_channel": "waterway",
              "wadi": "stream", "canoe_pass": "waterway", "rapids": "waterway"}
AREA_ONLY_WATERWAYS = {"riverbank", "dock", "boatyard"}          # as lines they're the outline of an area
WATER_KINDS = {"lake": "lake", "oxbow": "lake", "lagoon": "lake", "reservoir": "reservoir", "pond": "pond",
               "stream_pool": "pond", "river": "river", "canal": "canal", "ditch": "canal", "drain": "canal",
               "stream": "river", "basin": "basin", "wastewater": "wastewater", "swimming_pool": "pool",
               "fountain": "fountain", "reflecting_pool": "fountain", "moat": "pond", "lock": "canal",
               "fish_pass": "canal"}
POINT_KINDS = {"dam": "dam", "weir": "weir", "lock_gate": "lock_gate", "waterfall": "waterfall",
               "sluice_gate": "sluice_gate"}
KINDS = sorted(set(LINE_KINDS.values()) | set(WATER_KINDS.values()) | set(POINT_KINDS.values())
               | {"water", "wetland", "spring", "pool", "dock", "dam", "weir", "other"})
PIPED_TUNNELS_NOT = {"no"}
_WIDTH = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(m|meters?|metres?|ft|feet|')?\s*$", re.IGNORECASE)


def _text(v):
    if v is None:
        return None
    v = " ".join(str(v).split())
    return v or None


def kind_of(shape, tags):
    """Our kind for one object, or None when it isn't water we keep (a riverbank's outline as a line)."""
    ww, nat, water = tags.get("waterway"), tags.get("natural"), tags.get("water")
    if shape == "line":
        if ww in AREA_ONLY_WATERWAYS:
            return None
        return LINE_KINDS.get(ww, "other") if ww else None
    if shape == "point":
        if nat == "spring":
            return "spring"
        return POINT_KINDS.get(ww, "other") if ww else None
    # areas
    if tags.get("leisure") == "swimming_pool" or water == "swimming_pool":
        return "pool"
    if nat == "wetland":
        return "wetland"
    if nat == "spring":
        return "spring"
    if ww in ("dam", "weir"):
        return ww
    if ww in ("dock", "boatyard"):
        return "dock"
    if ww == "riverbank":
        return "river"
    if water:
        return WATER_KINDS.get(water, "water")
    if tags.get("landuse") == "reservoir":
        return "reservoir"
    if tags.get("landuse") == "basin":
        return "basin"
    if nat == "water":
        return "water"
    return "other"


def intermittent(tags):
    """True for intermittent=yes or seasonal=yes (any season), False for intermittent=no, else None."""
    i, s = tags.get("intermittent"), tags.get("seasonal")
    if i == "yes" or (s and s != "no"):
        return True
    if i == "no":
        return False
    return None


def piped(tags):
    t = tags.get("tunnel")
    return bool((t and t not in PIPED_TUNNELS_NOT) or tags.get("covered") == "yes"
                or tags.get("location") == "underground" or tags.get("waterway") == "pressurised")


def width_m(v):
    """A width tag in metres (feet converted), when it reads as one and is between 0.1 and 500 m; else None."""
    m = _WIDTH.match(str(v)) if v is not None else None
    if not m:
        return None
    w = float(m.group(1))
    if (m.group(2) or "m").lower() in ("ft", "feet", "'"):
        w *= 0.3048
    return round(w, 2) if 0.1 <= w <= 500 else None


def layer(v):
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        return None
    return n if -10 <= n <= 10 else None


SHAPES = {"point": "point", "linestring": "line", "polygon": "area"}


def feature_row(f):
    """One feature (osm_extract's dict) as a row: COLUMNS' values, then the geometry as GeoJSON; None to skip."""
    shape = SHAPES.get(f["geometry"])
    if shape is None:
        return None
    tags = f["tags"]
    kind = kind_of(shape, tags)
    if kind is None:
        return None
    return (f["type"], f["osm_id"], shape, kind, _text(tags.get("name")), intermittent(tags), piped(tags),
            width_m(tags.get("width")), layer(tags.get("layer")), json.dumps(tags, ensure_ascii=False),
            f["osm_version"], f["osm_timestamp"], json.dumps(f["geom"]))


def consume(conn, run):
    """Store this consumer's objects from the loader's cut (run.features(): its tags and the box already applied).
    Doesn't commit: the loader does, with its gate."""
    rows, skipped = [], 0
    for f in run.features():
        r = feature_row(f)
        if r is None:
            skipped += 1
        else:
            rows.append(r)
    stats = osm_extract.store_objects(conn, TABLE, COLUMNS, rows, run.seen_at, key=KEY,
                                      geometry_sql="ST_SetSRID(ST_GeomFromGeoJSON({}), 4326)",
                                      allow_shrink=run.allow_shrink)
    by_shape = {}
    for r in rows:
        by_shape[r[2]] = by_shape.get(r[2], 0) + 1
    stats.update({f"{k}s": v for k, v in sorted(by_shape.items())})
    stats["pools"] = sum(1 for r in rows if r[3] == "pool")
    stats["skipped (riverbank outlines, untyped)"] = skipped
    if conn.execute("select to_regclass('ops.build_pending') is not null").fetchone()[0]:
        from ingest import builds
        builds.mark(conn, BUILD, by=SOURCE["name"], reason=f"OpenStreetMap water loaded from {run.extract_name} "
                                                           f"(md5 {run.md5[:8]})")
    return stats
