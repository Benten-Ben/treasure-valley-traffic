"""OpenStreetMap's paving: service ways and driveways, sidewalks and crossings, parking lots, and
crossing and kerb nodes (landscape sprint, plan C1, C2, C10, C11; package P8-data).

A consumer of core's OpenStreetMap loader (ingest/osm_extract.py): no download
and no schedule. The owner downloads the Idaho extract by hand (Geofabrik's
robots.txt disallows scripts), and

    python3 -m ingest osm-load --inbox              # a new extract: every consumer
    python3 -m ingest osm-load --only osm_paving    # this one, on the extract we hold

loads it, with its own MD5 gate in ops.osm_consumer (migration 0019). Like
osm_street, it loads only the extract osm_valley holds (or loads in the same
run), so the partition's tables always split one extract's ways between them.

What it keeps (plugins/roads/migrations/0002), from the loader's smart cut of
the valley box:
  - roads.osm_paving: the highway ways core's partition gives it
    (osm_extract.owner), by tags alone: every service way but alleys (those are
    osm_street's), so driveways, parking aisles, drive-throughs, emergency
    access and untagged and other service ways; and footway=sidewalk, crossing,
    access_aisle or traffic_island on a footway, path or cycleway. osm_valley
    keeps any of them tagged with lanes. Lines, kept whole across the box's
    edge. A way drawn as an area (area=yes) keeps its outline, with area true.
  - roads.osm_parking: parking lots (amenity=parking) and mapped stalls
    (amenity=parking_space) drawn as areas: closed ways and multipolygons. The
    smart cut keeps a multipolygon whole when any member is in the box, so a
    lot across the edge comes whole. A lot mapped only as a point isn't kept:
    there's nothing to draw.
  - roads.osm_walk_node: crossing nodes (highway=crossing, or any crossing=*)
    and kerb nodes (kerb=*), with the paving ways through each (`ways`).

Material (plan C11): from the surface tag, read into asphalt, concrete, gravel
or dirt (MATERIALS; surface=paved takes the kind's paved material). Untagged,
or tagged with a value we don't read, an object takes its kind's default
(KIND_DEFAULTS), marked 'default' (the card says "surface estimated"). Service
ways and lots take theirs only on developed land: at least half of the way's
length, or of the lot's area, on the Cropland Data Layer 2025's developed
classes (cdl.py; `developed` holds the share). Off it, they're 'unknown': farm
lanes, private roads and trailhead lots are often gravel, and we don't guess.
Walkways take their kind's default anywhere. Underground lots get no material.

Where the CDL comes from: $TVT_CDL (a path, or 'none' to load without it, every
untagged service way and lot then 'unknown'), else
$TVT_ARCHIVE/roads/cdl/cdl_2025_10m.tif (production's copy), else
$TVT_SOURCES/cdl/out/cdl_2025_10m.tif (the downloaded sources, mounted on the
scratch database's jobs). Without any, the load fails rather than mark every
untagged service way unknown by surprise.

Widths (⚠️ estimates until measured): the width tag where it reads as metres,
else a kind's default (WIDTHS, the landscape design's; a one-way parking aisle
4.5 m).

Crossings. `marked` is true for crossing:markings other than 'no', crossing=
marked, zebra or uncontrolled, or crossing_ref=zebra; false for
crossing:markings=no or crossing=unmarked|no; otherwise null (not known; at
signals, crossing=traffic_signals alone says nothing about paint). A crossing
way with nothing on it takes its crossing nodes' (marked_from 'node'). Rail
crossings (a railway tag) are never crosswalks: marked stays null. Crosswalks
are drawn only where marked is true (decision 10; P7 builds them).

Versioned in place (plan C2): no raw.record copies; osm_version and
osm_timestamp, first_seen and last_seen, and objects missing from a load
become inactive. A load that changed anything marks roads-build (M1).

License ODbL: credit "© OpenStreetMap contributors". Its own tables, so other
sources' tables aren't pulled under the ODbL. `developed` also reads the CDL
(USDA NASS, public domain), which changes neither.
"""

import json
import os
from collections import Counter

from ingest import builds, osm_extract
from .. import cdl
from .osm_valley import _text, effective_oneway, parse_bridge, parse_layer, parse_width

SOURCE = {
    "name": "osm_paving",
    "title": "OpenStreetMap: the valley's service ways, sidewalks, crossings and parking lots",
    "url": osm_extract.PAGE,
    "access": "open",
    "schedule": None,   # loaded by hand: Geofabrik's robots.txt disallows scripted downloads (Oct 6, 2026)
    "license": "ODbL",
    "credit": "© OpenStreetMap contributors",
    "notes": "A consumer of the OpenStreetMap loader (python3 -m ingest osm-load): service ways but alleys, "
             "sidewalks, crossings, access aisles and traffic islands; parking lots and stalls drawn as areas; "
             "crossing and kerb nodes, cut to the valley box. roads.osm_paving, roads.osm_parking and "
             "roads.osm_walk_node, its own tables (ODbL), versioned in place. Untagged service ways and lots "
             "take a default material only on the Cropland Data Layer 2025's developed land (USDA NASS).",
}

WAYS, LOTS, NODES = "roads.osm_paving", "roads.osm_parking", "roads.osm_walk_node"

# ---- kinds -----------------------------------------------------------------

SERVICE_KINDS = {"driveway": "driveway", "parking_aisle": "parking_aisle", "drive-through": "drive_through",
                 "emergency_access": "emergency_access"}           # service=* -> kind; any other value: 'service'
WALKWAY_KINDS = tuple(sorted(osm_extract.PAVING_FOOTWAYS))         # footway=* on a footway, path or cycleway


def way_kind(tags):
    """A paving way's kind: from service=* on a service way, else its footway=* value."""
    if tags.get("highway") == "service":
        return SERVICE_KINDS.get(tags.get("service"), "service")
    return tags["footway"]


def lot_kind(tags):
    return {"parking": "lot", "parking_space": "space"}.get(tags.get("amenity"))


def node_kind(tags):
    """'crossing' (highway=crossing, or any crossing=*), else 'kerb' (kerb=*), else None."""
    if tags.get("highway") == "crossing" or "crossing" in tags:
        return "crossing"
    if "kerb" in tags:
        return "kerb"
    return None


# ---- material (plan C11) ---------------------------------------------------

# surface=* -> material. Other hard surfaces (pavers, brick, wood, metal) draw as concrete.
MATERIALS = {
    **dict.fromkeys(("asphalt", "chipseal"), "asphalt"),
    **dict.fromkeys(("concrete", "concrete:plates", "concrete:lanes", "paving_stones", "paving_stones:lanes",
                     "sett", "cobblestone", "unhewn_cobblestone", "bricks", "brick", "stone", "metal", "wood",
                     "rubber", "tartan"), "concrete"),
    **dict.fromkeys(("gravel", "fine_gravel", "compacted", "pebblestone", "rock", "shells", "unpaved"), "gravel"),
    **dict.fromkeys(("dirt", "earth", "ground", "mud", "sand", "soil", "grass", "grass_paver", "woodchips"), "dirt"),
}
PAVED = "paved"            # surface=paved: paved, but not which; the kind's paved material

# kind -> (default material, only on developed land). Service ways and lots: plan C11.
KIND_DEFAULTS = {
    "service": ("asphalt", True), "driveway": ("concrete", True), "parking_aisle": ("asphalt", True),
    "drive_through": ("asphalt", True), "emergency_access": ("asphalt", True),
    "sidewalk": ("concrete", False), "crossing": ("asphalt", False),       # a crossing is the carriageway's
    "access_aisle": ("asphalt", False), "traffic_island": ("concrete", False),
    "lot": ("asphalt", True), "space": ("asphalt", True),
}
STRUCTURES = {"multi-storey": "concrete", "rooftop": "concrete", "underground": None}   # parking=*: no land rule
DEVELOPED_SHARE = 0.5      # on developed land: at least half of it (cdl.py)


def surface_value(tags):
    """The surface tag's first value, lower case, or None."""
    v = tags.get("surface")
    v = str(v).split(";")[0].strip().lower() if v is not None else ""
    return v or None


def kind_default(kind, parking=None):
    """(default material or None, whether it needs developed land). Service ways and lots that need
    it have `developed` measured, tagged or not."""
    if kind in ("lot", "space") and parking in STRUCTURES:
        return STRUCTURES[parking], False
    return KIND_DEFAULTS[kind]


def material(kind, tags, developed=None):
    """(material, material_source): from the surface tag ('surface'), else the kind's default
    ('default'; service ways and lots only when developed >= DEVELOPED_SHARE), else ('unknown', None)."""
    s = surface_value(tags)
    if s in MATERIALS:
        return MATERIALS[s], "surface"
    default, land = kind_default(kind, tags.get("parking"))
    if s == PAVED:
        return default or "concrete", "surface"
    if default is None or (land and (developed is None or developed < DEVELOPED_SHARE)):
        return "unknown", None
    return default, "default"


# ---- widths (⚠️ estimates) -------------------------------------------------

# The landscape design's defaults, in metres, until measured in the test windows.
WIDTHS = {"service": 5.5, "driveway": 4.0, "parking_aisle": 7.0, "drive_through": 3.5, "emergency_access": 6.0,
          "sidewalk": 1.5, "crossing": 3.0, "access_aisle": 1.5, "traffic_island": 1.5}
ONE_WAY_AISLE = 4.5


def width(kind, tags):
    """(width_m as tagged or None, width_est_m, width_source)."""
    tagged = parse_width(tags.get("width"))
    if tagged:
        return tagged, tagged, "tagged"
    est = ONE_WAY_AISLE if kind == "parking_aisle" and effective_oneway(tags) in ("yes", "-1") else WIDTHS[kind]
    return None, est, "default"


# ---- crossings -------------------------------------------------------------

MARKED = {"marked", "zebra", "uncontrolled"}       # crossing=*: painted (uncontrolled: marked, no signals)
UNMARKED = {"unmarked", "no"}
SIGNALS = {"traffic_signals"}


def marked(tags):
    """Whether a crossing (node or way) is painted: True, False or None (not known, or a rail crossing)."""
    if tags.get("railway"):
        return None
    m = _text(tags.get("crossing:markings"))
    if m:
        return m.lower() != "no"
    c = str(tags.get("crossing") or "").strip().lower()
    if c in MARKED:
        return True
    if c in UNMARKED:
        return False
    if str(tags.get("crossing_ref") or "").strip().lower() == "zebra":
        return True
    return None


def at_signals(tags):
    return (str(tags.get("crossing") or "").strip().lower() in SIGNALS or tags.get("highway") == "traffic_signals"
            or tags.get("crossing:signals") == "yes")


def from_nodes(values):
    """A crossing way's marking from its crossing nodes' (marked values, None left out): any True, else False."""
    values = [v for v in values if v is not None]
    if not values:
        return None
    return any(values)


# ---- rows ------------------------------------------------------------------

WAY_COLUMNS = [("osm_id", "bigint"), ("kind", "text"), ("highway", "text"), ("service", "text"),
               ("footway", "text"), ("name", "text"), ("area", "boolean"), ("surface", "text"),
               ("material", "text"), ("material_source", "text"), ("developed", "real"), ("width_m", "real"),
               ("width_est_m", "real"), ("width_source", "text"), ("oneway", "text"), ("access", "text"),
               ("crossing", "text"), ("crossing_markings", "text"), ("marked", "boolean"),
               ("marked_from", "text"), ("layer", "smallint"), ("bridge", "boolean"), ("tunnel", "boolean"),
               ("tags", "jsonb"), ("osm_version", "int"), ("osm_timestamp", "timestamptz")]
LOT_COLUMNS = [("osm_type", "char(1)"), ("osm_id", "bigint"), ("kind", "text"), ("parking", "text"),
               ("name", "text"), ("operator", "text"), ("access", "text"), ("fee", "text"), ("capacity", "int"),
               ("surface", "text"), ("material", "text"), ("material_source", "text"), ("developed", "real"),
               ("layer", "smallint"), ("building", "text"), ("area_m2", "real"), ("tags", "jsonb"),
               ("osm_version", "int"), ("osm_timestamp", "timestamptz")]
NODE_COLUMNS = [("osm_id", "bigint"), ("kind", "text"), ("crossing", "text"), ("crossing_markings", "text"),
                ("marked", "boolean"), ("signals", "boolean"), ("kerb", "text"), ("tactile_paving", "text"),
                ("railway", "text"), ("ways", "bigint[]"), ("tags", "jsonb"), ("osm_version", "int"),
                ("osm_timestamp", "timestamptz")]


def _col(columns, name):
    return [c for c, _ in columns].index(name)


def capacity(v):
    s = str(v).strip() if v is not None else ""
    return int(s) if s.isdigit() and len(s) <= 6 else None


def outline(geom):
    """A polygon feature's outer ring as a LineString (a way drawn as an area)."""
    coords = geom["coordinates"]
    ring = coords[0][0] if geom["type"] == "MultiPolygon" else coords[0]
    return {"type": "LineString", "coordinates": ring}


def way_row(f, land=None, area=False):
    """One paving way (osm_extract's feature dict) as a list: WAY_COLUMNS' values, then the geometry
    as GeoJSON. area: f is a polygon feature (its outline is kept); a closed line tagged area=yes is
    an area too. land: a cdl.Developed, or None (no measurement: untagged service ways are unknown)."""
    tags = f["tags"]
    kind = way_kind(tags)
    geom = outline(f["geom"]) if area else f["geom"]
    area = area or (tags.get("area") == "yes" and osm_extract.closed(geom))
    developed = land.line_share(geom["coordinates"]) if land is not None and kind_default(kind)[1] else None
    mat, source = material(kind, tags, developed)
    width_m, est, width_source = width(kind, tags)
    crossing = kind == "crossing"
    m = marked(tags) if crossing else None
    return [f["osm_id"], kind, tags["highway"], _text(tags.get("service")), _text(tags.get("footway")),
            _text(tags.get("name")), area, _text(tags.get("surface")), mat, source, developed, width_m, est,
            width_source, effective_oneway(tags), _text(tags.get("access")),
            _text(tags.get("crossing")) if crossing else None,
            _text(tags.get("crossing:markings")) if crossing else None, m, "way" if m is not None else None,
            parse_layer(tags.get("layer")), parse_bridge(tags.get("bridge")), parse_bridge(tags.get("tunnel")),
            json.dumps(tags, ensure_ascii=False), f["osm_version"], f["osm_timestamp"], json.dumps(geom)]


def lot_row(f, land=None):
    """One lot or stall (an area feature) as a list: LOT_COLUMNS' values, then the geometry."""
    tags, polygons = f["tags"], f["geom"]["coordinates"]
    if f["geom"]["type"] == "Polygon":
        polygons = [polygons]
    kind = lot_kind(tags)
    parking = _text(tags.get("parking"))
    developed = land.area_share(polygons) if land is not None else None
    mat, source = material(kind, tags, developed)
    return [f["type"], f["osm_id"], kind, parking, _text(tags.get("name")), _text(tags.get("operator")),
            _text(tags.get("access")), _text(tags.get("fee")), capacity(tags.get("capacity")),
            _text(tags.get("surface")), mat, source, developed, parse_layer(tags.get("layer")),
            _text(tags.get("building")), round(cdl.area_m2(polygons), 1), json.dumps(tags, ensure_ascii=False),
            f["osm_version"], f["osm_timestamp"], json.dumps({"type": "MultiPolygon", "coordinates": polygons})]


def node_row(f):
    """One crossing or kerb node as a list: NODE_COLUMNS' values (ways empty), then the geometry."""
    tags = f["tags"]
    kind = node_kind(tags)
    crossing = kind == "crossing"
    return [f["osm_id"], kind, _text(tags.get("crossing")), _text(tags.get("crossing:markings")),
            marked(tags) if crossing else None, crossing and at_signals(tags), _text(tags.get("kerb")),
            _text(tags.get("tactile_paving")), _text(tags.get("railway")), [], json.dumps(tags, ensure_ascii=False),
            f["osm_version"], f["osm_timestamp"], json.dumps(f["geom"])]


# ---- the CDL ---------------------------------------------------------------

CDL_ENV = "TVT_CDL"
CDL_NAME = "cdl_2025_10m.tif"
CDL_PLACES = (("TVT_ARCHIVE", ("roads", "cdl", CDL_NAME)), ("TVT_SOURCES", ("cdl", "out", CDL_NAME)))


def cdl_path(environ=None):
    """The CDL raster's path, or None when $TVT_CDL is 'none'. Raises RuntimeError when there's none."""
    environ = os.environ if environ is None else environ
    v = environ.get(CDL_ENV)
    if v:
        if v.strip().lower() == "none":
            return None
        if not os.path.isfile(v):
            raise RuntimeError(f"{CDL_ENV}={v}: no such file")
        return v
    for var, parts in CDL_PLACES:
        if environ.get(var) and os.path.isfile(p := os.path.join(environ[var], *parts)):
            return p
    raise RuntimeError(f"no Cropland Data Layer for the material defaults (plan C11): put {CDL_NAME} in "
                       f"$TVT_ARCHIVE/roads/cdl/ or $TVT_SOURCES/cdl/out/, set {CDL_ENV} to it, or set "
                       f"{CDL_ENV}=none to leave every untagged service way and lot 'unknown'")


# ---- the load --------------------------------------------------------------

def rows_from(features, land=None, counts=None):
    """Sort a consumer's features into (way rows, lot rows, node rows), as lists, and link them:
    each node's paving ways, and each unmarked-unknown crossing way's marking from its nodes."""
    counts = Counter() if counts is None else counts
    ways, lots, nodes, way_nodes = {}, {}, {}, {}
    for f in features:
        tags = f["tags"]
        if f["geometry"] == "point":
            if f["type"] == "n" and node_kind(tags):
                nodes[f["osm_id"]] = node_row(f)
            else:
                counts["skipped: points that aren't crossings or kerbs"] += 1
        elif f["geometry"] == "linestring" and f["type"] == "w" and "highway" in tags:
            ways[f["osm_id"]] = way_row(f, land)
            way_nodes[f["osm_id"]] = f.get("way_nodes") or ()
        elif f["geometry"] == "polygon" and lot_kind(tags):
            lots[(f["type"], f["osm_id"])] = lot_row(f, land)
        elif f["geometry"] == "polygon" and f["type"] == "w" and "highway" in tags:
            if f["osm_id"] not in ways:                        # the line, when osmium gave both
                ways[f["osm_id"]] = way_row(f, land, area=True)
                way_nodes.setdefault(f["osm_id"], ())
        else:
            counts[f"skipped: {f['geometry']}s of type {f['type']} with no paving tags"] += 1
    ways_at = {}
    for wid, refs in way_nodes.items():
        for nid in refs:
            if nid in nodes:
                ways_at.setdefault(nid, []).append(wid)
    i_ways = _col(NODE_COLUMNS, "ways")
    for nid, wids in ways_at.items():
        nodes[nid][i_ways] = sorted(set(wids))
    i_kind, i_marked, i_from = (_col(WAY_COLUMNS, c) for c in ("kind", "marked", "marked_from"))
    n_kind, n_marked = _col(NODE_COLUMNS, "kind"), _col(NODE_COLUMNS, "marked")
    for wid, row in ways.items():
        if row[i_kind] == "crossing" and row[i_marked] is None:
            m = from_nodes(nodes[n][n_marked] for n in way_nodes[wid] if n in nodes and nodes[n][n_kind] == "crossing")
            if m is not None:
                row[i_marked], row[i_from] = m, "node"
    return list(ways.values()), list(lots.values()), list(nodes.values())


def _tally(rows, columns, *names, where=None):
    """'a 3 / b 1' counts of rows by the named columns' values (joined with ':'), largest first."""
    idx = [_col(columns, n) for n in names]
    c = Counter(":".join(str(r[i]) for i in idx) for r in rows if where is None or where(r))
    return " / ".join(f"{k} {v}" for k, v in c.most_common())


def summary(ways, lots, nodes):
    """What a load holds, for its counts (and the loader's line): kinds, materials, markings."""
    crossing_way = lambda r: r[_col(WAY_COLUMNS, "kind")] == "crossing"      # noqa: E731
    crossing_node = lambda r: r[_col(NODE_COLUMNS, "kind")] == "crossing"    # noqa: E731
    return {"ways by kind": _tally(ways, WAY_COLUMNS, "kind"),
            "ways by material": _tally(ways, WAY_COLUMNS, "material", "material_source"),
            "crossing ways marked": _tally(ways, WAY_COLUMNS, "marked", "marked_from", where=crossing_way),
            "lots by kind": _tally(lots, LOT_COLUMNS, "kind"),
            "lots by material": _tally(lots, LOT_COLUMNS, "material", "material_source"),
            "nodes by kind": _tally(nodes, NODE_COLUMNS, "kind"),
            "crossing nodes marked": _tally(nodes, NODE_COLUMNS, "marked", where=crossing_node)}


def consume(conn, run):
    """Store this consumer's ways, lots and nodes from the loader's cut (run.features(): its tags,
    the box and the partition already applied). Doesn't commit: the loader does, with its gate."""
    path = cdl_path()
    raster = cdl.Raster(path) if path else None
    try:
        land = cdl.Developed(raster) if raster else None
        counts = getattr(run, "counts", Counter())
        ways, lots, nodes = rows_from(run.features(), land, counts)
    finally:
        if raster:
            raster.close()
    stats = {"objects": len(ways) + len(lots) + len(nodes)}
    for table, columns, rows, key in ((WAYS, WAY_COLUMNS, ways, ("osm_id",)),
                                      (LOTS, LOT_COLUMNS, lots, ("osm_type", "osm_id")),
                                      (NODES, NODE_COLUMNS, nodes, ("osm_id",))):
        geometry_sql = ("ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON({}), 4326))" if table == LOTS
                        else "ST_SetSRID(ST_GeomFromGeoJSON({}), 4326)")
        got = osm_extract.store_objects(conn, table, columns, (tuple(r) for r in rows), run.seen_at, key=key,
                                        geometry_sql=geometry_sql, allow_shrink=run.allow_shrink)
        name = table.split(".")[1]
        for k, v in got.items():
            stats[f"{name} {k}"] = v
        for k in ("new", "changed", "retired", "reactivated"):
            stats[k] = stats.get(k, 0) + got[k]
    stats.update(summary(ways, lots, nodes))
    stats["developed land"] = (f"{cdl.CREDIT} ({os.path.basename(path)}, sha256 {osm_extract.sha256_file(path)[:12]})"
                               if path else f"none ({CDL_ENV}=none): untagged service ways and lots unknown")
    if any(stats[k] for k in ("new", "changed", "retired", "reactivated")) and _builds_ready(conn):
        builds.mark(conn, "roads-build", by=SOURCE["name"],
                    reason=f"extract {getattr(run, 'md5', '?')[:8]}: {stats['new']} new, {stats['changed']} changed, "
                           f"{stats['retired']} retired")
    return stats


def _builds_ready(conn):
    return conn.execute("select to_regclass('ops.build_pending') is not null").fetchone()[0]
