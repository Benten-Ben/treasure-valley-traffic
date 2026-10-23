"""OpenStreetMap's mapped fences, walls, guard rails and hedges, and its gates: fences.fence and fences.gate
(landscape sprint, plan C1, C2, C3, C10, C14; package P10).

A consumer of core's OpenStreetMap loader (ingest/osm_extract.py): no download and no schedule. The owner
downloads the Idaho extract by hand (Geofabrik's robots.txt disallows scripts), and

    python3 -m ingest osm-load --inbox                      # a new extract: every consumer
    python3 -m ingest osm-load --only fences.osm_barriers   # this one, on the extract we hold

loads it, with its own MD5 gate in ops.osm_consumer. It is not one of the partition's owners (barriers are
not highways), so it loads whatever extract it is given.

What it keeps, by tags alone (barrier=*):
- lines (ways): fence, wall, retaining_wall, guard_rail, jersey_barrier and hedge, and a few others
  (city_wall, cable_barrier, handrail, wire_fence) as type 'other': fences.fence. Other barrier values on
  lines (kerbs, ditches, ...) are not fences and are left out, counted. Closed ways are lines too.
- gates: barrier=gate, lift_gate, bollard, block and cattle_grid, on nodes, or on ways (stored at the way's
  middle vertex): fences.gate.

Each fence gets, by tags alone:
- a type: the barrier tag's class (hedge stays 'hedge' so the shrubs' hedge check can read it);
- a look, solid or open ⚠️: walls, retaining walls, jersey barriers and hedges are solid; guard rails and
  cables are open; a fence is solid when its fence_type or material says boards, panels, brick, stone or
  concrete, else open;
- a height in metres: the height tag when it reads as metres or feet (height_source 'tagged'), else an
  estimate by type and fence_type ⚠️ (height_source 'default').

Mapped fences only: most backyard fences are not in OpenStreetMap, and a mapped fence never says where a lot
ends. Stored versioned in place (plan C2): no raw.record copies. After each load the layer
'fences.lines' gets a new core.layer_version row for the app's versioned GeoJSON (OpenStreetMap's alone, so
ODbL, republish yes).

License ODbL: credit "© OpenStreetMap contributors". Its own tables, so other sources' tables aren't pulled
under the ODbL.
"""

import json
import re
from collections import Counter

from ingest import layer_version, osm_extract

SOURCE = {
    "name": "osm_barriers",
    "title": "OpenStreetMap: the valley's mapped fences, walls, guard rails, hedges and gates",
    "url": osm_extract.PAGE,
    "access": "open",
    "schedule": None,   # loaded by hand: Geofabrik's robots.txt disallows scripted downloads (Oct 6, 2026)
    "license": "ODbL",
    "credit": "© OpenStreetMap contributors",
    "notes": "A consumer of the OpenStreetMap loader (python3 -m ingest osm-load): barrier lines (fences, walls, "
             "retaining walls, guard rails, jersey barriers, hedges) and gates, lift gates, bollards, blocks and "
             "cattle grids, cut to the valley box. fences.fence and fences.gate, its own tables (ODbL), versioned "
             "in place. Mapped ones only.",
}

FENCE_TABLE, GATE_TABLE = "fences.fence", "fences.gate"
LAYER = "fences.lines"                      # the fences layer's versioned GeoJSON (core.layer_version)

NAMED_TYPES = ("fence", "wall", "retaining_wall", "guard_rail", "jersey_barrier", "hedge")
OTHER_LINES = ("city_wall", "cable_barrier", "handrail", "wire_fence")   # type 'other'
LINE_KINDS = NAMED_TYPES + OTHER_LINES
GATE_KINDS = ("gate", "lift_gate", "bollard", "block", "cattle_grid")

SOLID_TYPES = {"wall", "retaining_wall", "jersey_barrier", "hedge", "city_wall"}
SOLID_FENCES = {"wood", "board", "boards", "panel", "panels", "solid", "privacy", "paling", "stockade", "wood_panel",
                "brick", "stone", "concrete", "masonry", "block", "vinyl", "glass"}
# Height estimates in metres by type ⚠️ (used without a height tag); a few fence_types differ.
DEFAULT_HEIGHT = {"fence": 1.5, "wall": 1.8, "retaining_wall": 1.0, "guard_rail": 0.8, "jersey_barrier": 0.8,
                  "hedge": 1.5, "other": 1.0}
FENCE_TYPE_HEIGHT = {"wire": 1.2, "barbed_wire": 1.2, "electric": 1.2, "split_rail": 1.2, "rail": 1.2,
                     "wood": 1.8, "privacy": 1.8, "solid": 1.8, "panel": 1.8, "chain_link": 1.5}

FENCE_COLUMNS = [
    ("fence_id", "text"), ("kind", "text"), ("type", "text"), ("look", "text"), ("height_m", "real"),
    ("height_source", "text"), ("material", "text"), ("fence_type", "text"), ("name", "text"), ("tags", "jsonb"),
    ("osm_id", "bigint"), ("osm_version", "int"), ("osm_timestamp", "timestamptz")]
GATE_COLUMNS = [
    ("gate_id", "text"), ("kind", "text"), ("access", "text"), ("name", "text"), ("tags", "jsonb"),
    ("osm_type", "char(1)"), ("osm_id", "bigint"), ("osm_version", "int"), ("osm_timestamp", "timestamptz")]


# ---- the rules ---------------------------------------------------------------------------------

def _norm(v):
    return str(v).strip().lower() if v is not None else ""


def _text(v):
    v = " ".join(str(v).split()) if v is not None else ""
    return v or None


def fence_type_of(kind):
    """The stored type for a barrier value on a line, or None when it isn't a fence we keep."""
    if kind in NAMED_TYPES:
        return kind
    return "other" if kind in OTHER_LINES else None


_HEIGHT = re.compile(r"(\d+(?:\.\d+)?)\s*(m|meters?|metres?|ft|feet|foot|')?")
_FEET_INCHES = re.compile(r"(\d+)\s*'\s*(\d+(?:\.\d+)?)\s*\"")


def parse_height(v):
    """Height in metres: '1.8', '1.8 m', '6 ft', "6'", '6\\'6"'. Anything else ('tall', '1,8', lists) is None; the
    tag stays in tags. Zero and over 30 m are not heights of a fence."""
    s = _norm(v)
    m = _FEET_INCHES.fullmatch(s)
    if m:
        metres = (int(m.group(1)) * 12 + float(m.group(2))) * 0.0254
    else:
        m = _HEIGHT.fullmatch(s)
        if not m:
            return None
        metres = float(m.group(1)) * (0.3048 if m.group(2) in ("ft", "feet", "foot", "'") else 1)
    return round(metres, 2) if 0 < metres <= 30 else None


def height(type_, tags):
    """(height in metres, 'tagged' or 'default'): the height tag when it reads, else an estimate ⚠️."""
    tagged = parse_height(tags.get("height"))
    if tagged is not None:
        return tagged, "tagged"
    if type_ == "fence":
        return FENCE_TYPE_HEIGHT.get(_norm(tags.get("fence_type")), DEFAULT_HEIGHT["fence"]), "default"
    return DEFAULT_HEIGHT[type_], "default"


def look(type_, tags):
    """'solid' or 'open' ⚠️: by type or barrier value (a city_wall is type 'other'), and for a fence by its
    fence_type or material."""
    if type_ in SOLID_TYPES or tags.get("barrier") in SOLID_TYPES:
        return "solid"
    if type_ == "fence" and (_norm(tags.get("fence_type")) in SOLID_FENCES or _norm(tags.get("material")) in SOLID_FENCES):
        return "solid"
    return "open"


# ---- rows --------------------------------------------------------------------------------------

def fence_row(f):
    """One barrier way (osm_extract's dict) as a row: FENCE_COLUMNS' values, then the geometry as GeoJSON."""
    tags = f["tags"]
    kind = tags["barrier"]
    type_ = fence_type_of(kind)
    h, source = height(type_, tags)
    return (f"osm:w{f['osm_id']}", kind, type_, look(type_, tags), h, source, _text(tags.get("material")),
            _text(tags.get("fence_type")), _text(tags.get("name")), json.dumps(tags, ensure_ascii=False),
            f["osm_id"], f["osm_version"], f["osm_timestamp"], json.dumps(f["geom"]))


def gate_point(f):
    """A gate's point: the node itself, or a way's middle vertex."""
    if f["geom"]["type"] == "Point":
        return f["geom"]
    coords = f["geom"]["coordinates"]
    return {"type": "Point", "coordinates": coords[len(coords) // 2]}


def gate_row(f):
    tags = f["tags"]
    return (f"osm:{f['type']}{f['osm_id']}", tags["barrier"], _text(tags.get("access")), _text(tags.get("name")),
            json.dumps(tags, ensure_ascii=False), f["type"], f["osm_id"], f["osm_version"], f["osm_timestamp"],
            json.dumps(gate_point(f)))


def sort_features(features, counts):
    """Split the loader's features into (fence rows, gate rows)."""
    fences, gates = [], []
    for f in features:
        kind = f["tags"].get("barrier")
        if kind in GATE_KINDS and f["geometry"] in ("point", "linestring"):
            gates.append(gate_row(f))
        elif f["geometry"] == "linestring" and f["type"] == "w" and kind in LINE_KINDS:
            fences.append(fence_row(f))
        else:
            counts[f"left out: {f['geometry']} barrier={kind}"] += 1
    return fences, gates


def consume(conn, run):
    """Store this consumer's objects from the loader's cut (run.features(): its tags and the box already
    applied) and give the fences layer a new version. Doesn't commit: the loader does, with its gate."""
    counts = Counter()
    fences, gates = sort_features(run.features(), counts)
    fe = osm_extract.store_objects(conn, FENCE_TABLE, FENCE_COLUMNS, fences, run.seen_at, key=("fence_id",),
                                   allow_shrink=run.allow_shrink)
    ga = osm_extract.store_objects(conn, GATE_TABLE, GATE_COLUMNS, gates, run.seen_at, key=("gate_id",),
                                   allow_shrink=run.allow_shrink)
    md5 = (getattr(run, "md5", None) or "")[:8]
    version = layer_version.record(conn, LAYER, license="ODbL", republish="yes", credit=SOURCE["credit"],
                                   build=f"osm_barriers {md5}".strip(), features=fe["objects"],
                                   note="the OpenStreetMap barrier lines (hedges included, not drawn as fences)")
    stats = {"objects": fe["objects"] + ga["objects"], "fences": fe["objects"], "gates": ga["objects"]}
    for name, s in (("fences", fe), ("gates", ga)):
        stats.update({f"{name} {k}": v for k, v in s.items() if k != "objects" and v})
    stats["hedges"] = sum(1 for row in fences if row[2] == "hedge")
    stats["version"] = version
    stats.update(counts)
    return stats
