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
    edge. A closed way tagged area=yes keeps its outline, with area true. An
    alley tagged area=yes is the paving's too, closed or not, and so is one
    whose service value isn't exactly 'alley' (osm_street takes the others):
    the table checks the partition's own test, on the raw tags.
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
length, or of the lot's area, on the Cropland Data Layer's developed classes
(`developed` holds the share). Off it, they're 'unknown': farm lanes, private
roads and trailhead lots are often gravel, and we don't guess. Walkways take
their kind's default anywhere. Underground lots get no material.

Developed land is a vector input: the CDL's developed classes traced into
polygons in the worker image (plugins/roads/build/developed.py, from farm's
archived copy of the CDL) and loaded into roads.developed_land by
`python3 -m ingest roads-developed-load` (../developed.py). The raster is
never read here (rasters are decoded in the worker: docs/17 §17.8 Q9). Each
load measures its service ways and lots against the current build in PostGIS
(measure()), and loading a new build measures the stored ones again
(remeasure()). With no build loaded, the load still runs: untagged service
ways and lots are 'unknown' until one is, and the counts say so.

Widths (⚠️ estimates until measured): the width tag where it reads as metres,
else a kind's default (WIDTHS, the landscape design's; a one-way parking aisle
4.5 m).

Crossings. `marked` is true for crossing:markings other than 'no', crossing=
marked, zebra or uncontrolled, or crossing_ref=zebra; false for
crossing:markings=no or crossing=unmarked|no; otherwise null (not known; at
signals, crossing=traffic_signals alone says nothing about paint). A crossing
way with nothing on it takes its crossing nodes' (marked_from 'node'). Rail
crossings (railway=crossing, level_crossing, tram_crossing or
tram_level_crossing) are never crosswalks: marked stays null, and a rail
crossing way doesn't take its nodes'. Another railway value (abandoned,
disused: a rail trail) doesn't make a crossing a rail crossing. Crosswalks are
drawn only where marked is true (decision 10; P7 builds them).

Versioned in place (plan C2): no raw.record copies; osm_version and
osm_timestamp, first_seen and last_seen, and objects missing from a load
become inactive. A load that changed anything marks roads-build (M1).

License ODbL: credit "© OpenStreetMap contributors". Its own tables, so other
sources' tables aren't pulled under the ODbL. `developed`, and the materials
resting on it, also read the CDL (USDA NASS, public domain; credit "USDA NASS
Cropland Data Layer <year>"), which changes neither: an export of them lists
the CDL as an input, with the current build's year and sha256
(roads.developed_build).

A build that reads core.osm_way with roads.osm_street and roads.osm_paving
together calls osm_extract.check_partition(conn, ("osm_valley", "osm_street",
"osm_paving")) first: its default names only the first two.
"""

import json
from collections import Counter

from ingest import builds, osm_extract
from .. import developed
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
             "take a default material only on the Cropland Data Layer's developed land (USDA NASS, public domain: "
             "roads.developed_land, loaded by roads-developed-load).",
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
DEVELOPED_SHARE = 0.5      # on developed land: at least half of it (developed.py measures it)
LAND_WAY_KINDS = tuple(k for k, (_, land) in KIND_DEFAULTS.items() if land and k not in ("lot", "space"))


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


def material(kind, tags, share=None):
    """(material, material_source): from the surface tag ('surface'), else the kind's default
    ('default'; service ways and lots only when their share of developed land, `developed`, is at
    least DEVELOPED_SHARE), else ('unknown', None). share None: not measured."""
    s = surface_value(tags)
    if s in MATERIALS:
        return MATERIALS[s], "surface"
    default, land = kind_default(kind, tags.get("parking"))
    if s == PAVED:
        return default or "concrete", "surface"
    if default is None or (land and (share is None or share < DEVELOPED_SHARE)):
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
RAIL_CROSSINGS = {"crossing", "level_crossing", "tram_crossing", "tram_level_crossing"}   # railway=*


def rail_crossing(tags):
    """A crossing of a railway or tramway (railway=crossing, level_crossing, ...); not a rail trail's
    railway=abandoned or disused."""
    return str(tags.get("railway") or "").strip().lower() in RAIL_CROSSINGS


def marked(tags):
    """Whether a crossing (node or way) is painted: True, False or None (not known, or a rail crossing)."""
    if rail_crossing(tags):
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
    if at_signals(tags):      # a stated exception (owner, Oct 22): a signalized crossing is painted unless tagged otherwise
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


def way_row(f, area=False):
    """One paving way (osm_extract's feature dict) as a list: WAY_COLUMNS' values, then the geometry
    as GeoJSON. area: f is a polygon feature (its outline is kept); a closed line tagged area=yes is
    an area too. `developed` is left for with_land(): until then a service way's default needs land
    it hasn't been measured on, so untagged it's 'unknown'."""
    tags = f["tags"]
    kind = way_kind(tags)
    geom = outline(f["geom"]) if area else f["geom"]
    area = area or (tags.get("area") == "yes" and osm_extract.closed(geom))
    mat, source = material(kind, tags)
    width_m, est, width_source = width(kind, tags)
    crossing = kind == "crossing"
    m = marked(tags) if crossing else None
    return [f["osm_id"], kind, tags["highway"], _text(tags.get("service")), _text(tags.get("footway")),
            _text(tags.get("name")), area, _text(tags.get("surface")), mat, source, None, width_m, est,
            width_source, effective_oneway(tags), _text(tags.get("access")),
            _text(tags.get("crossing")) if crossing else None,
            _text(tags.get("crossing:markings")) if crossing else None, m, "way" if m is not None else None,
            parse_layer(tags.get("layer")), parse_bridge(tags.get("bridge")), parse_bridge(tags.get("tunnel")),
            json.dumps(tags, ensure_ascii=False), f["osm_version"], f["osm_timestamp"], json.dumps(geom)]


def lot_row(f):
    """One lot or stall (an area feature) as a list: LOT_COLUMNS' values, then the geometry.
    `developed` and area_m2 are left for with_land()."""
    tags, polygons = f["tags"], f["geom"]["coordinates"]
    if f["geom"]["type"] == "Polygon":
        polygons = [polygons]
    kind = lot_kind(tags)
    mat, source = material(kind, tags)
    return [f["type"], f["osm_id"], kind, _text(tags.get("parking")), _text(tags.get("name")),
            _text(tags.get("operator")), _text(tags.get("access")), _text(tags.get("fee")),
            capacity(tags.get("capacity")), _text(tags.get("surface")), mat, source, None,
            parse_layer(tags.get("layer")), _text(tags.get("building")), None, json.dumps(tags, ensure_ascii=False),
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


# ---- the load --------------------------------------------------------------

def rows_from(features, counts=None):
    """Sort a consumer's features into (way rows, lot rows, node rows), as lists, and link them:
    each node's paving ways, and each unmarked-unknown crossing way's marking from its nodes (not a
    rail crossing's). Land isn't measured here (with_land, measure)."""
    counts = Counter() if counts is None else counts
    ways, lots, nodes, way_nodes, rail = {}, {}, {}, {}, set()
    for f in features:
        tags = f["tags"]
        if f["geometry"] == "point":
            if f["type"] == "n" and node_kind(tags):
                nodes[f["osm_id"]] = node_row(f)
            else:
                counts["skipped: points that aren't crossings or kerbs"] += 1
        elif f["geometry"] == "linestring" and f["type"] == "w" and "highway" in tags:
            ways[f["osm_id"]] = way_row(f)
            way_nodes[f["osm_id"]] = f.get("way_nodes") or ()
        elif f["geometry"] == "polygon" and lot_kind(tags):
            lots[(f["type"], f["osm_id"])] = lot_row(f)
            continue
        elif f["geometry"] == "polygon" and f["type"] == "w" and "highway" in tags:
            if f["osm_id"] not in ways:                        # the line, when osmium gave both
                ways[f["osm_id"]] = way_row(f, area=True)
                way_nodes.setdefault(f["osm_id"], ())
        else:
            counts[f"skipped: {f['geometry']}s of type {f['type']} with no paving tags"] += 1
            continue
        if f["type"] == "w" and rail_crossing(tags):
            rail.add(f["osm_id"])
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
        if row[i_kind] == "crossing" and row[i_marked] is None and wid not in rail:
            m = from_nodes(nodes[n][n_marked] for n in way_nodes[wid] if n in nodes and nodes[n][n_kind] == "crossing")
            if m is not None:
                row[i_marked], row[i_from] = m, "node"
    return list(ways.values()), list(lots.values()), list(nodes.values())


def needs_land(row):
    """A way row whose kind takes its default only on developed land (it's measured)."""
    return row[_col(WAY_COLUMNS, "kind")] in LAND_WAY_KINDS


def with_land(ways, lots, way_shares=None, lot_measures=None):
    """Set `developed`, and the material resting on it, from measured shares (in place):
    way_shares {osm_id: share} for the ways that need land; lot_measures {(osm_type, osm_id):
    (share, area_m2)} for every lot (area_m2 is set from it too). A share of None: not measured."""
    way_shares, lot_measures = way_shares or {}, lot_measures or {}
    for rows, columns, key, get in (
            (ways, WAY_COLUMNS, lambda r: r[0], lambda k: (way_shares.get(k), None)),
            (lots, LOT_COLUMNS, lambda r: (r[0], r[1]), lambda k: lot_measures.get(k, (None, None)))):
        i_kind, i_tags, i_dev, i_mat, i_src = (_col(columns, c) for c in
                                               ("kind", "tags", "developed", "material", "material_source"))
        i_area = _col(columns, "area_m2") if columns is LOT_COLUMNS else None
        for r in rows:
            if columns is WAY_COLUMNS and not needs_land(r):
                continue
            share, m2 = get(key(r))
            r[i_dev] = share
            r[i_mat], r[i_src] = material(r[i_kind], json.loads(r[i_tags]), share)
            if i_area is not None:
                r[i_area] = m2


def measure(conn, ways, lots):
    """Measure the rows' land in PostGIS (developed.measure) and set it (with_land): the ways that
    need it and every lot (whose area_m2 comes from here too). Returns the current developed land's
    build (a dict), or None when none is loaded (then nothing is measured, and lots get only their area)."""
    land = developed.current(conn)
    shares = {}
    if land is not None:
        need = [("w", r[0], r[-1]) for r in ways if needs_land(r)]
        shares = {i: v for (_, i), v in developed.measure(conn, need).items()} if need else {}
    lot_measures = {}
    if lots:
        lot_measures = developed.measure(conn, [(r[0], r[1], r[-1]) for r in lots], area=True, land=land is not None)
    with_land(ways, lots, shares, lot_measures)
    return land


def remeasure(conn, by=SOURCE["name"], reason=None):
    """Measure every active service way and lot against the current developed land again (after
    roads-developed-load), and update `developed` and the material resting on it where they changed.
    Marks roads-build when any did. Doesn't commit. Returns stats."""
    land = developed.current(conn)
    stats = {}
    for table, columns, query, area, key in (
            (WAYS, WAY_COLUMNS, f"select 'w'::char(1) as t, osm_id as id, geom from {WAYS} "
                                "where active and kind = any(%s)", False, ("osm_id",)),
            (LOTS, LOT_COLUMNS, f"select osm_type as t, osm_id as id, geom from {LOTS} where active", True,
             ("osm_type", "osm_id"))):
        params = (list(LAND_WAY_KINDS),) if table == WAYS else ()
        got = developed.measure(conn, query=query, params=params, area=area, land=land is not None)
        cols = ", ".join(key)
        where = "active and kind = any(%s)" if table == WAYS else "active"
        changed = []
        for row in conn.execute(f"select {cols}, kind, tags, developed, material, material_source from {table} "
                                f"where {where}", params).fetchall():
            k, (kind, tags, dev, mat, src) = row[:len(key)], row[len(key):]
            m = got[("w", k[0]) if table == WAYS else tuple(k)]
            share = m[0] if area else m
            new = (share, *material(kind, tags, share))
            old = (round(dev, developed.DIGITS) if dev is not None else None, mat, src)
            if new != old:
                changed.append((*k, *new))
        if changed:
            conn.execute("drop table if exists pg_temp.roads_remeasure")
            types = ", ".join(f"{c} {t}" for c, t in columns if c in key)
            conn.execute(f"create temp table roads_remeasure ({types}, developed real, material text, "
                         "material_source text) on commit drop")
            with conn.cursor() as cur:
                with cur.copy(f"copy roads_remeasure ({cols}, developed, material, material_source) from stdin") as cp:
                    for r in changed:
                        cp.write_row(r)
            join = " and ".join(f"t.{c} = c.{c}" for c in key)
            conn.execute(f"""update {table} t set developed = c.developed, material = c.material,
                                    material_source = c.material_source
                               from roads_remeasure c where {join}""")
            conn.execute("drop table pg_temp.roads_remeasure")
        stats[f"{table.split('.')[1]} remeasured"] = len(changed)
    stats["developed land"] = developed.describe(land)
    if any(v for k, v in stats.items() if k.endswith("remeasured")) and _builds_ready(conn):
        builds.mark(conn, "roads-build", by=by,
                    reason=f"{reason or 'developed land'}: {stats['osm_paving remeasured']} service ways and "
                           f"{stats['osm_parking remeasured']} lots remeasured")
    return stats


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
    the box and the partition already applied), measured against the current developed land.
    Doesn't commit: the loader does, with its gate."""
    counts = getattr(run, "counts", Counter())
    ways, lots, nodes = rows_from(run.features(), counts)
    land = measure(conn, ways, lots)
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
    stats["developed land"] = developed.describe(land)
    if any(stats[k] for k in ("new", "changed", "retired", "reactivated")) and _builds_ready(conn):
        builds.mark(conn, "roads-build", by=SOURCE["name"],
                    reason=f"extract {getattr(run, 'md5', '?')[:8]}: {stats['new']} new, {stats['changed']} changed, "
                           f"{stats['retired']} retired")
    return stats


def _builds_ready(conn):
    return conn.execute("select to_regclass('ops.build_pending') is not null").fetchone()[0]
