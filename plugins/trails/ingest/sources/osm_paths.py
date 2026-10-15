"""OpenStreetMap's paths, tracks and routes: trails.osm_path, trails.osm_area and trails.osm_route
(landscape sprint, plan C1, C2, C10, C18, package P6-data).

A consumer of core's OpenStreetMap loader (ingest/osm_extract.py): no download
and no schedule. The owner downloads the Idaho extract by hand (Geofabrik's
robots.txt disallows scripts), and

    python3 -m ingest osm-load --inbox              # a new extract: every consumer
    python3 -m ingest osm-load --only osm_paths     # this one, on the extract we hold

loads it, with its own MD5 gate in ops.osm_consumer (migration 0019). Like
osm_street, it loads only the extract osm_valley holds (or loads in the same
run), so the partition's owners split one extract's ways between them.

What it keeps (approved by the owner, Oct 8: the landscape row's classes, and
decision 2c for the routes):
- the highway ways core's partition gives it (osm_extract.owner), by tags
  alone: path, track, cycleway, bridleway, steps, pedestrian, and footways but
  sidewalks, crossings, access aisles and traffic islands (roads' osm_paving).
  The 12 lane-tagged ones osm_valley keeps stay in core.osm_way, and trails
  reads them through the view trails.exception_way. Lines, with every way that
  has a node in the valley box kept whole: trails.osm_path;
- pedestrian and footway areas (a closed way tagged area=yes, or a
  multipolygon): plazas, for the paved-path base (plan C9): trails.osm_area;
- hiking, mtb, bicycle, foot and horse route relations, with their members in
  order: trails.osm_route. Their ways may be anyone's (a bike route runs on
  streets); trails-match draws each route's line from them.

Each way gets, by tags alone (the same rules as the SQL functions in trails
0001, which the named exception's view uses; a test holds them together):
- a surface class: paved, gravel, dirt or unknown, from the surface tag
  (surface_from 'osm'); untagged, a cycleway is paved and a track dirt
  (surface_from 'default'), anything else unknown ('none'). A path that
  Ridge to Rivers' trail runs along reads dirt by default on its card (the
  view trails.way_agency, since that needs the City's lines; the tiles keep
  OpenStreetMap's own);
- a width estimate by kind and surface, ⚠️ as for lanes: dirt or unknown path
  0.8 m, gravel path or bridleway 1.5 m, footway 1.8 m, paved path or
  cycleway 3.0 m, track 3.0 m, steps 1.5 m, pedestrian way 4.0 m. The width
  tag wins where it reads as metres or feet (1.3% of path length has one);
- the access rule (plan C18): no_access when access=private or no, unless foot,
  bicycle or horse is opened (yes, permissive, designated, official). Such a
  way is never drawn as a trail. informal=yes is kept as informal.

Stored versioned in place (plan C2): no raw.record copies. A load marks the
trails-match build (the links follow the new ways) and gives the Trails
layer's tiles a new version (core.layer_version 'trails.paths': OpenStreetMap's
alone, so ODbL, republish yes; what the City's lines say of a way is
feature-state).

License ODbL: credit "© OpenStreetMap contributors". Its own tables, so other
sources' tables aren't pulled under the ODbL.
"""

import json
import re
from collections import Counter

from ingest import builds, layer_version, osm_extract

SOURCE = {
    "name": "osm_paths",
    "title": "OpenStreetMap: the valley's paths, tracks and trail routes",
    "url": osm_extract.PAGE,
    "access": "open",
    "schedule": None,   # loaded by hand: Geofabrik's robots.txt disallows scripted downloads (Oct 6, 2026)
    "license": "ODbL",
    "credit": "© OpenStreetMap contributors",
    "notes": "A consumer of the OpenStreetMap loader (python3 -m ingest osm-load): paths, footways (not sidewalks or "
             "crossings), cycleways, tracks, bridleways, steps and pedestrian ways, pedestrian areas, and hiking, "
             "mtb, bicycle, foot and horse route relations, cut to the valley box. trails.osm_path, osm_area and "
             "osm_route, its own tables (ODbL), versioned in place.",
}

PATH_TABLE, AREA_TABLE, ROUTE_TABLE = "trails.osm_path", "trails.osm_area", "trails.osm_route"
BUILD = "trails-match"                     # the build a load marks (plugins/trails/ingest/match.py)
LAYER = "trails.paths"                     # the Trails layer's tiles (core.layer_version)

PATH_KINDS = ("path", "footway", "cycleway", "track", "bridleway", "steps", "pedestrian")
AREA_KINDS = ("pedestrian", "footway")
ROUTES = ("hiking", "mtb", "bicycle", "foot", "horse")

PAVED = {"asphalt", "paved", "paving_stones", "bricks", "sett", "wood", "metal", "chipseal"}   # and concrete*
GRAVEL = {"gravel", "fine_gravel", "compacted", "pebblestone"}
DIRT = {"dirt", "ground", "earth", "sand", "grass", "mud", "rock", "unpaved"}
DEFAULT_SURFACE = {"cycleway": "paved", "track": "dirt"}
NO_ACCESS = {"private", "no"}
OPENS = {"yes", "permissive", "designated", "official"}
TRAIL_MODES = ("foot", "bicycle", "horse")

PATH_COLUMNS = [
    ("osm_id", "bigint"), ("kind", "text"), ("name", "text"), ("ref", "text"), ("surface_tag", "text"),
    ("surface", "text"), ("surface_from", "text"), ("width_m", "real"), ("width_est_m", "real"),
    ("access", "text"), ("foot", "text"), ("bicycle", "text"), ("horse", "text"), ("motor_vehicle", "text"),
    ("no_access", "boolean"), ("informal", "boolean"), ("mtb_scale", "text"), ("sac_scale", "text"),
    ("tracktype", "text"), ("smoothness", "text"), ("oneway", "text"), ("bridge", "boolean"), ("tunnel", "boolean"),
    ("layer", "smallint"), ("conditional", "jsonb"), ("tags", "jsonb"), ("osm_version", "int"),
    ("osm_timestamp", "timestamptz")]
AREA_COLUMNS = [
    ("osm_type", "char(1)"), ("osm_id", "bigint"), ("kind", "text"), ("name", "text"), ("surface_tag", "text"),
    ("surface", "text"), ("access", "text"), ("no_access", "boolean"), ("tags", "jsonb"), ("osm_version", "int"),
    ("osm_timestamp", "timestamptz")]
ROUTE_COLUMNS = [
    ("osm_id", "bigint"), ("route", "text"), ("name", "text"), ("ref", "text"), ("network", "text"),
    ("operator", "text"), ("members", "jsonb"), ("way_ids", "bigint[]"), ("tags", "jsonb"), ("osm_version", "int"),
    ("osm_timestamp", "timestamptz")]
AREA_SQL = "ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON({}), 4326))"


# ---- the rules (the same as trails 0001's SQL functions) ------------------------------------

def _norm(v):
    return str(v).strip().lower() if v is not None else ""


def _text(v):
    v = " ".join(str(v).split()) if v is not None else ""
    return v or None


def surface_class(value):
    """OpenStreetMap's surface tag as paved, gravel, dirt or unknown; None when untagged."""
    if value is None:
        return None
    s = _norm(value)
    if s in PAVED or s.startswith("concrete"):
        return "paved"
    if s in GRAVEL:
        return "gravel"
    if s in DIRT:
        return "dirt"
    return "unknown"


def surface(kind, tags):
    """(surface class, where it came from): 'osm' from the tag (a value we can't place stays
    unknown), 'default' by kind when untagged (cycleway paved, track dirt), else 'none'."""
    if "surface" in tags:
        return surface_class(tags["surface"]), "osm"
    if kind in DEFAULT_SURFACE:
        return DEFAULT_SURFACE[kind], "default"
    return "unknown", "none"


def no_public_access(tags):
    """Plan C18: closed to the public when access=private or no, unless foot, bicycle or horse
    is opened (yes, permissive, designated, official)."""
    if _norm(tags.get("access")) not in NO_ACCESS:
        return False
    return not any(_norm(tags.get(mode)) in OPENS for mode in TRAIL_MODES)


def informal(tags):
    return _norm(tags.get("informal")) == "yes"


def width_estimate(kind, surface_class_):
    """The width estimate in metres by kind and surface class (⚠️ estimates)."""
    if kind == "path":
        return {"paved": 3.0, "gravel": 1.5}.get(surface_class_, 0.8)
    return {"bridleway": 1.5, "footway": 1.8, "cycleway": 3.0, "track": 3.0, "steps": 1.5, "pedestrian": 4.0}[kind]


_WIDTH = re.compile(r"(\d+(?:\.\d+)?)\s*(m|meters?|metres?|ft|feet|foot|')?")
_FEET_INCHES = re.compile(r"(\d+)\s*'\s*(\d+(?:\.\d+)?)\s*\"")


def parse_width(v):
    """Width in metres: '1.5', '1.5 m', '4 ft', "4'", '4\\'6"'. Anything else ('narrow', '1,5',
    lists) is None; the tag stays in tags. As osm_valley reads widths."""
    s = _norm(v)
    m = _FEET_INCHES.fullmatch(s)
    if m:
        metres = (int(m.group(1)) * 12 + float(m.group(2))) * 0.0254
    else:
        m = _WIDTH.fullmatch(s)
        if not m:
            return None
        metres = float(m.group(1)) * (0.3048 if m.group(2) in ("ft", "feet", "foot", "'") else 1)
    return round(metres, 2) if 0 < metres < 100 else None


def parse_layer(v):
    s = str(v).strip() if v is not None else ""
    if not re.fullmatch(r"[+-]?[0-9]{1,2}", s):
        return None
    n = int(s)
    return n if -10 <= n <= 10 else None


def parse_yes(v):
    """bridge=yes, boardwalk, ...; tunnel=yes, culvert, ...: anything but absent or 'no'."""
    s = _norm(v)
    return bool(s) and s != "no"


def conditional(tags):
    """The *:conditional tags (seasonal rules: motor_vehicle:conditional=no @ (Nov-Apr)), or None."""
    out = {k: v for k, v in tags.items() if k.endswith(":conditional")}
    return json.dumps(out, ensure_ascii=False) if out else None


# ---- rows ------------------------------------------------------------------------------------

def path_row(f):
    """One way (osm_extract's dict) as a row: PATH_COLUMNS' values, then the geometry as GeoJSON."""
    tags = f["tags"]
    kind = tags["highway"]
    cls, came_from = surface(kind, tags)
    return (f["osm_id"], kind, _text(tags.get("name")), _text(tags.get("ref")), tags.get("surface"), cls, came_from,
            parse_width(tags.get("width")), width_estimate(kind, cls), _text(tags.get("access")),
            _text(tags.get("foot")), _text(tags.get("bicycle")), _text(tags.get("horse")),
            _text(tags.get("motor_vehicle")), no_public_access(tags), informal(tags), _text(tags.get("mtb:scale")),
            _text(tags.get("sac_scale")), _text(tags.get("tracktype")), _text(tags.get("smoothness")),
            _text(tags.get("oneway")), parse_yes(tags.get("bridge")), parse_yes(tags.get("tunnel")),
            parse_layer(tags.get("layer")), conditional(tags), json.dumps(tags, ensure_ascii=False),
            f["osm_version"], f["osm_timestamp"], json.dumps(f["geom"]))


def area_row(f):
    tags = f["tags"]
    return (f["type"], f["osm_id"], tags["highway"], _text(tags.get("name")), tags.get("surface"),
            surface(tags["highway"], tags)[0], _text(tags.get("access")), no_public_access(tags),
            json.dumps(tags, ensure_ascii=False), f["osm_version"], f["osm_timestamp"], json.dumps(f["geom"]))


def route_row(f):
    tags = f["tags"]
    members = f.get("members") or []
    ways = [m["ref"] for m in members if m["type"] == "w"]
    return (f["osm_id"], tags["route"], _text(tags.get("name")), _text(tags.get("ref")), _text(tags.get("network")),
            _text(tags.get("operator")), json.dumps(members), ways, json.dumps(tags, ensure_ascii=False),
            f["osm_version"], f["osm_timestamp"])


def sort_features(features, counts):
    """Split the loader's features into (paths, areas, routes) rows. A closed way tagged
    area=yes is an area, never a line; a closed way without it is a line (a loop), and the area
    osmium also makes of it is left out."""
    paths, areas, routes = [], [], []
    for f in features:
        tags = f["tags"]
        if f["type"] == "r" and f["geometry"] == "relation":
            if tags.get("route") in ROUTES:
                routes.append(route_row(f))
            continue
        kind = tags.get("highway")
        if f["geometry"] == "linestring" and f["type"] == "w" and kind in PATH_KINDS:
            if tags.get("area") == "yes" and osm_extract.closed(f["geom"]):
                counts["left out: an area drawn as a closed line"] += 1
                continue
            paths.append(path_row(f))
        elif f["geometry"] == "polygon" and kind in AREA_KINDS:
            if f["type"] == "w" and tags.get("area") != "yes":
                counts["left out: a closed way that's a loop, not an area"] += 1
                continue
            areas.append(area_row(f))
        else:
            counts[f"left out: {f['geometry']} highway={kind}"] += 1
    return paths, areas, routes


def consume(conn, run):
    """Store this consumer's objects from the loader's cut (run.features(): its tags, the box and
    the partition already applied), mark trails-match and give the Trails layer a new version.
    Doesn't commit: the loader does, with its gate."""
    counts = Counter()
    paths, areas, routes = sort_features(run.features(), counts)
    p = osm_extract.store_objects(conn, PATH_TABLE, PATH_COLUMNS, paths, run.seen_at, allow_shrink=run.allow_shrink)
    a = osm_extract.store_objects(conn, AREA_TABLE, AREA_COLUMNS, areas, run.seen_at, key=("osm_type", "osm_id"),
                                  geometry_sql=AREA_SQL, allow_shrink=run.allow_shrink)
    r = osm_extract.store_objects(conn, ROUTE_TABLE, ROUTE_COLUMNS, routes, run.seen_at, geometry=None,
                                  allow_shrink=run.allow_shrink)
    extract = getattr(run, "extract_name", None) or "an extract"
    md5 = (getattr(run, "md5", None) or "")[:8]
    builds.mark(conn, BUILD, by=SOURCE["name"], reason=f"{extract} loaded ({md5}): relink the agencies' trails")
    version = layer_version.record(conn, LAYER, license="ODbL", republish="yes", credit=SOURCE["credit"],
                                   build=f"osm_paths {md5}".strip(), features=p["objects"],
                                   note="the OpenStreetMap ways (the agencies' states are feature-state)")
    stats = {"objects": p["objects"] + a["objects"] + r["objects"]}
    for name, s in (("paths", p), ("areas", a), ("routes", r)):
        stats[name] = s["objects"]
        stats.update({f"{name} {k}": v for k, v in s.items() if k != "objects" and v})
    stats["no public access"] = sum(1 for row in paths if row[14])
    stats["informal"] = sum(1 for row in paths if row[15])
    stats["version"] = version
    stats.update(counts)
    return stats
