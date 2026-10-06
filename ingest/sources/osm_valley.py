"""OpenStreetMap in the valley: major roads and every way with lanes, plus signal and crossing nodes.

License ODbL: credit "© OpenStreetMap contributors". OpenStreetMap stays in
its own tables (core.osm_way, core.osm_lane, core.osm_node, and its rows in
raw.record and core.segment_match), so the other sources' tables aren't
pulled under the ODbL (db/migrations/0011, docs/09 §9.3).

Where the data comes from. The owner approved Geofabrik's weekly Idaho
extract (Oct 6, 2026), but Geofabrik's robots.txt, read that day, disallows
the files for every robot: `Disallow: *.osm.pbf`, `*.md5`, `*updates*` (and
.osm.bz2, .osc.gz, .shp.zip, state.txt). We respect it, so `run` (the
download) refuses cleanly and logs the refusal in ops.fetch, and the source has
no schedule until the owner decides. Meanwhile an extract the owner downloads
by hand is loaded with

    python3 -m ingest.osm_load --inbox          # newest file in $TVT_ARCHIVE/osm/inbox/
    python3 -m ingest.osm_load --file PATH      # a .osm.pbf or OSM XML file

and archived in $TVT_ARCHIVE/osm/ (the last two are kept). A file that is
the one loaded last time (same MD5) is skipped.

Processing (osmium-tool, installed in the ingest image):
  1. osmium extract: cut the valley box (-117.05,43.00,-115.95,43.85),
     keeping ways that cross its edge whole;
  2. osmium tags-filter: highway ways, and nodes tagged
     highway=traffic_signals, crossing=traffic_signals,
     crossing:signals=yes or railway=level_crossing;
  3. osmium export to GeoJSON lines, with each object's id, version and timestamp.

What we keep: every major way (motorway to tertiary and their _link roads)
and any other highway way tagged lanes, lanes:forward, lanes:backward or
turn:lanes*, but not proposed or unbuilt roads or areas; and every signal,
crossing-signal and level-crossing node. raw.record (keys 'w<id>' and 'n<id>')
holds the tags and a hash of the geometry, so versions stay small; the
geometry goes to the typed tables. Ways and nodes missing from a load become
inactive.

Lanes (core.osm_lane): one row per lane per direction, numbered from 1 at
the left in the direction of travel, as OSM's turn:lanes and WZDx do. The
direction split comes from lanes:forward/backward/both_ways, else from the
turn:lanes:* slot counts, else, on a two-way road with an even count and no
centre lane, an even split (OSM's convention); an odd count with no split
gets no lane rows. When a turn:lanes value's slot count disagrees with the
lane count, it's logged and the lanes get no turns; the tags are kept as tagged.

Matching (core.segment_match, method 'buffer15_bearing20'): an OSM way
matches an ACHD road segment when at least 60% of the segment lies within
15 m of the way and their bearings there differ by 20° or less, measured in
UTM 11N. Both carriageways of a divided road (5-7 m either side of ACHD's
single centerline) can match one segment. This lives here until the shared
matcher (ingest/segment_match.py) lands; match_achd_segments() is the seam.
"""

import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from collections import Counter
from datetime import datetime, timezone

from .. import USER_AGENT, db, http

URL = "https://download.geofabrik.de/north-america/us/idaho-latest.osm.pbf"
MD5_URL = URL + ".md5"
BOX = (-117.05, 43.00, -115.95, 43.85)          # left, bottom, right, top

SOURCE = {
    "name": "osm_valley",
    "title": "OpenStreetMap: valley roads, lanes, signal and crossing nodes",
    "url": URL,
    "access": "open",
    # No schedule until the owner decides how to get the extract: Geofabrik's
    # robots.txt disallows *.osm.pbf and *.md5 (read Oct 6, 2026).
    "schedule": None,
    "license": "ODbL",
    "credit": "© OpenStreetMap contributors",
    "notes": "Geofabrik's Idaho extract cut to the valley box; major ways and ways with lanes, lanes "
             "per direction, signal and crossing nodes. Its own tables (ODbL). Loaded by hand "
             "(python3 -m ingest.osm_load) while Geofabrik's robots.txt disallows the download.",
}

TAG_FILTERS = ["w/highway", "n/highway=traffic_signals", "n/crossing=traffic_signals",
               "n/crossing:signals=yes", "n/railway=level_crossing"]
OSM_SUFFIXES = (".osm.pbf", ".osm.bz2", ".osm.gz", ".osm")
PAUSE_S = 2.0                 # between the .md5 request and the download
OSMIUM_TIMEOUT_S = 1800
SHRINK_GUARD = 0.5            # refuse to retire ways when a load brings fewer than half the active ones

MAJOR = {"motorway", "trunk", "primary", "secondary", "tertiary"}
MAJOR |= {f"{c}_link" for c in MAJOR}
NOT_ROADS = {"proposed", "planned", "construction", "abandoned", "disused", "razed", "demolished",
             "platform", "bus_stop", "rest_area", "services"}
LANE_KEYS = ("lanes", "lanes:forward", "lanes:backward")

MATCH_SOURCE = SOURCE["name"]
MATCH_METHOD = "buffer15_bearing20"
MATCH_BUFFER_M = 15
MATCH_SHARE = 0.6
MATCH_BEARING_DEG = 20


# ---- tag values ------------------------------------------------------------

def parse_count(v):
    """A lane count: a whole number from 1 to 30, else None ('2;3', '2.5', 'none', '0')."""
    s = str(v).strip() if v is not None else ""
    if not re.fullmatch(r"[0-9]{1,2}", s):
        return None
    n = int(s)
    return n if 1 <= n <= 30 else None


_WIDTH = re.compile(r"(\d+(?:\.\d+)?)\s*(m|meters?|metres?|ft|feet|foot|')?")
_FEET_INCHES = re.compile(r"(\d+)\s*'\s*(\d+(?:\.\d+)?)\s*\"")


def parse_width(v):
    """Width in metres: '7.5', '7.5 m', '24 ft', "24'", '12\\'6"'. Anything else (lists,
    '7,5', 'narrow') is None; the tag stays in tags."""
    s = str(v).strip().lower() if v is not None else ""
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


def parse_bridge(v):
    """bridge=yes, viaduct, boardwalk, ... is a bridge; absent or 'no' isn't."""
    s = str(v).strip().lower() if v is not None else ""
    return bool(s) and s != "no"


def effective_oneway(tags):
    """'yes', '-1' or 'no' (implied yes on motorways and roundabouts); other values
    ('reversible', 'alternating') are kept as tagged and their lanes aren't expanded."""
    v = str(tags.get("oneway") or "").strip().lower()
    if v in ("yes", "true", "1"):
        return "yes"
    if v in ("-1", "reverse"):
        return "-1"
    if v in ("no", "false", "0"):
        return "no"
    if v:
        return v
    if tags.get("highway") == "motorway" or tags.get("junction") in ("roundabout", "circular"):
        return "yes"
    return "no"


def turn_slots(value):
    """'left|through;right||none' -> [['left'], ['through', 'right'], [], []]; None when untagged."""
    if value is None:
        return None
    slots = []
    for slot in str(value).split("|"):
        turns = [t.strip().lower() for t in slot.split(";")]
        slots.append([t for t in turns if t and t != "none"])
    return slots


def expand_lanes(tags):
    """The lanes of one way: ([(direction, lane, turns)], [(issue kind, text)]).

    Lanes are numbered from 1 at the left in the direction of travel; turn:lanes
    values already list them that way. Issue kinds: 'turn_slots' (a turn:lanes
    value's slot count disagrees with the lane count: logged, no turns for
    that direction), 'lanes_total' (lanes isn't forward + backward + both_ways),
    'turn_two_way' (plain turn:lanes on a two-way road), 'unsplit' (an odd
    two-way count with no split: no rows), 'not_expanded' (oneway=reversible etc.).
    """
    issues = []
    oneway = effective_oneway(tags)
    total = parse_count(tags.get("lanes"))
    if oneway in ("yes", "-1"):
        d = "forward" if oneway == "yes" else "backward"
        slots = turn_slots(tags.get("turn:lanes"))
        if slots is None:
            slots = turn_slots(tags.get(f"turn:lanes:{d}"))
        n = parse_count(tags.get(f"lanes:{d}")) or total or (len(slots) if slots else None)
        plan = [(d, n, slots)]
    elif oneway == "no":
        sf, sb = turn_slots(tags.get("turn:lanes:forward")), turn_slots(tags.get("turn:lanes:backward"))
        sboth = turn_slots(tags.get("turn:lanes:both_ways"))
        fwd = parse_count(tags.get("lanes:forward")) or (len(sf) if sf else None)
        bwd = parse_count(tags.get("lanes:backward")) or (len(sb) if sb else None)
        both = parse_count(tags.get("lanes:both_ways")) or (len(sboth) if sboth else 0)
        if total is not None:
            rest = total - both
            if fwd is None and bwd is None:
                if rest > 0 and rest % 2 == 0:
                    fwd = bwd = rest // 2
                else:
                    issues.append(("unsplit", f"lanes={total} on a two-way road with no split"))
            elif fwd is None:
                fwd = rest - bwd if rest - bwd > 0 else None
            elif bwd is None:
                bwd = rest - fwd if rest - fwd > 0 else None
            if fwd and bwd and fwd + bwd + both != total:
                issues.append(("lanes_total", f"lanes={total} but forward {fwd} + backward {bwd} + both ways {both}"))
        if "turn:lanes" in tags:
            issues.append(("turn_two_way", "turn:lanes on a two-way road (needs :forward or :backward)"))
        plan = [("forward", fwd, sf), ("backward", bwd, sb), ("both", both, sboth)]
    else:
        if total or any(k.startswith("turn:lanes") for k in tags):
            issues.append(("not_expanded", f"oneway={oneway}: lanes not expanded"))
        return [], issues

    rows = []
    for d, n, slots in plan:
        if not n:
            continue
        if slots is not None and len(slots) != n:
            issues.append(("turn_slots", f"turn:lanes {d} has {len(slots)} slots for {n} lanes"))
            slots = None
        rows += [(d, i + 1, slots[i] if slots else []) for i in range(n)]
    return rows, issues


# ---- what we keep ----------------------------------------------------------

def keep_way(tags):
    hw = tags.get("highway")
    if not hw or hw in NOT_ROADS or tags.get("area") == "yes":
        return False
    if hw in MAJOR:
        return True
    return any(k in tags for k in LANE_KEYS) or any(k.startswith("turn:lanes") for k in tags)


def node_kind(tags):
    """traffic_signals, crossing_signals or level_crossing; None for other nodes
    (stop signs and plain crossings come through as members of the ways)."""
    if tags.get("railway") == "level_crossing":
        return "level_crossing"
    if tags.get("highway") == "traffic_signals":
        return "crossing_signals" if tags.get("traffic_signals") == "crossing" else "traffic_signals"
    if tags.get("crossing") == "traffic_signals" or tags.get("crossing:signals") == "yes":
        return "crossing_signals"
    return None


def geometry_hash(geom):
    coords = json.dumps(geom.get("coordinates"), separators=(",", ":"))
    return hashlib.sha256(coords.encode()).hexdigest()[:16]


def parse_timestamp(v):
    """osmium writes epoch seconds (1.16) or ISO text, depending on version."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, timezone.utc)
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def _text(v):
    v = " ".join(str(v).split()) if v is not None else ""
    return v or None


def way_row(osm_id, props, tags, geom):
    lanes, issues = expand_lanes(tags)
    return {
        "osm_id": osm_id, "highway": tags["highway"], "name": _text(tags.get("name")), "ref": _text(tags.get("ref")),
        "oneway": effective_oneway(tags),
        "lanes": parse_count(tags.get("lanes")),
        "lanes_forward": parse_count(tags.get("lanes:forward")),
        "lanes_backward": parse_count(tags.get("lanes:backward")),
        "turn_lanes": tags.get("turn:lanes"),
        "turn_lanes_forward": tags.get("turn:lanes:forward"),
        "turn_lanes_backward": tags.get("turn:lanes:backward"),
        "width_m": parse_width(tags.get("width")),
        "maxspeed": _text(tags.get("maxspeed")),
        "layer": parse_layer(tags.get("layer")),
        "bridge": parse_bridge(tags.get("bridge")),
        "tags": tags, "geom": geom,
        "osm_version": props.get("@version"), "osm_timestamp": parse_timestamp(props.get("@timestamp")),
        "lane_rows": lanes, "issues": issues,
    }


def parse_features(lines):
    """Ways and nodes we keep, from osmium's GeoJSON lines. Returns (ways, nodes, counts)."""
    ways, nodes, counts = {}, {}, Counter()
    for line in lines:
        line = line.strip().lstrip("\x1e")         # RFC 8142 record separators, if osmium wrote them
        if not line:
            continue
        feat = json.loads(line)
        props, geom = feat.get("properties") or {}, feat.get("geometry") or {}
        tags = {k: v for k, v in props.items() if not k.startswith("@")}
        fid = str(feat.get("id") or "")
        kind, num = fid[:1], fid[1:]
        osm_id = int(num) if num.isdigit() else props.get("@id")
        if kind == "w" and geom.get("type") == "LineString" and osm_id is not None:
            if keep_way(tags):
                ways[osm_id] = way_row(osm_id, props, tags, geom)
            else:
                counts["ways skipped"] += 1
        elif kind == "n" and geom.get("type") == "Point" and osm_id is not None:
            k = node_kind(tags)
            if k:
                nodes[osm_id] = {"osm_id": osm_id, "kind": k, "tags": tags, "geom": geom,
                                 "osm_version": props.get("@version"),
                                 "osm_timestamp": parse_timestamp(props.get("@timestamp"))}
            else:
                counts["nodes skipped"] += 1
        else:
            counts["other features skipped"] += 1
    return list(ways.values()), list(nodes.values()), counts


# ---- osmium ----------------------------------------------------------------

def osmium_commands(src, work):
    """The three osmium steps, and the GeoJSON-lines file they leave in work."""
    valley, filtered, out = (os.path.join(work, n) for n in ("valley.osm.pbf", "filtered.osm.pbf", "valley.geojsonseq"))
    return [
        ["osmium", "extract", "--bbox", ",".join(f"{v:.2f}" for v in BOX), "--strategy", "complete_ways",
         "--no-progress", "--overwrite", "--output", valley, src],
        ["osmium", "tags-filter", "--no-progress", "--overwrite", "--output", filtered, valley, *TAG_FILTERS],
        ["osmium", "export", "--output-format", "geojsonseq", "--format-option", "print_record_separator=false",
         "--geometry-types", "point,linestring", "--attributes", "id,version,timestamp",
         "--add-unique-id", "type_id", "--no-progress", "--overwrite", "--output", out, filtered],
    ], out


def _osmium(cmd):
    if not shutil.which(cmd[0]):
        raise RuntimeError("osmium-tool isn't installed (the ingest image has it)")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=OSMIUM_TIMEOUT_S)
    if r.returncode:
        raise RuntimeError(f"{' '.join(cmd[:2])} failed ({r.returncode}): {r.stderr.strip()[-500:]}")
    return r.stdout


def data_timestamp(src):
    """When the extract's data was cut (Geofabrik's header), or None."""
    try:
        out = _osmium(["osmium", "fileinfo", "--get", "header.option.osmosis_replication_timestamp", src]).strip()
    except (RuntimeError, OSError, subprocess.SubprocessError):
        return None
    return out or None


def extract_features(src, work_parent=None):
    """Run osmium over an extract and parse what we keep: (ways, nodes, counts)."""
    with tempfile.TemporaryDirectory(prefix="osm-valley-", dir=work_parent) as work:
        cmds, out = osmium_commands(src, work)
        for cmd in cmds:
            _osmium(cmd)
        with open(out, encoding="utf-8") as f:
            return parse_features(f)


# ---- database --------------------------------------------------------------

WAY_UPSERT = """
insert into core.osm_way (osm_id, highway, name, ref, oneway, lanes, lanes_forward, lanes_backward,
  turn_lanes, turn_lanes_forward, turn_lanes_backward, width_m, maxspeed, layer, bridge, tags, geom,
  osm_version, osm_timestamp, active, first_seen, last_seen)
values (%(osm_id)s, %(highway)s, %(name)s, %(ref)s, %(oneway)s, %(lanes)s, %(lanes_forward)s, %(lanes_backward)s,
  %(turn_lanes)s, %(turn_lanes_forward)s, %(turn_lanes_backward)s, %(width_m)s, %(maxspeed)s, %(layer)s, %(bridge)s,
  %(tags)s::jsonb, ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326), %(osm_version)s, %(osm_timestamp)s,
  true, %(seen)s, %(seen)s)
on conflict (osm_id) do update set highway = excluded.highway, name = excluded.name, ref = excluded.ref,
  oneway = excluded.oneway, lanes = excluded.lanes, lanes_forward = excluded.lanes_forward,
  lanes_backward = excluded.lanes_backward, turn_lanes = excluded.turn_lanes,
  turn_lanes_forward = excluded.turn_lanes_forward, turn_lanes_backward = excluded.turn_lanes_backward,
  width_m = excluded.width_m, maxspeed = excluded.maxspeed, layer = excluded.layer, bridge = excluded.bridge,
  tags = excluded.tags, geom = excluded.geom, osm_version = excluded.osm_version,
  osm_timestamp = excluded.osm_timestamp, active = true, last_seen = excluded.last_seen"""

NODE_UPSERT = """
insert into core.osm_node (osm_id, kind, tags, geom, osm_version, osm_timestamp, active, first_seen, last_seen)
values (%(osm_id)s, %(kind)s, %(tags)s::jsonb, ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326),
  %(osm_version)s, %(osm_timestamp)s, true, %(seen)s, %(seen)s)
on conflict (osm_id) do update set kind = excluded.kind, tags = excluded.tags, geom = excluded.geom,
  osm_version = excluded.osm_version, osm_timestamp = excluded.osm_timestamp, active = true,
  last_seen = excluded.last_seen"""


def store(conn, fetch_id, seen_at, ways, nodes, allow_shrink=False):
    """Write one load: record versions, ways, lanes and nodes; retire what's gone."""
    active = conn.execute("select count(*) from core.osm_way where active").fetchone()[0]
    if not allow_shrink and active >= 1000 and len(ways) < active * SHRINK_GUARD:
        raise RuntimeError(f"only {len(ways)} ways in this extract against {active} active; not retiring "
                           "the rest (check the file, or load it with --allow-shrink)")
    records = [(f"w{w['osm_id']}", {"tags": w["tags"], "geom_hash": geometry_hash(w["geom"])}, None) for w in ways]
    records += [(f"n{n['osm_id']}", {"tags": n["tags"], "geom_hash": geometry_hash(n["geom"])}, None) for n in nodes]
    new, unchanged, removed = db.upsert_records(conn, SOURCE["name"], records, fetch_id, seen_at)

    def row(r):
        return {**{k: v for k, v in r.items() if k not in ("lane_rows", "issues")},
                "tags": json.dumps(r["tags"]), "geom": json.dumps(r["geom"]), "seen": seen_at}

    lanes = [(w["osm_id"], d, i, turns) for w in ways for d, i, turns in w["lane_rows"]]
    with conn.cursor() as cur:
        cur.executemany(WAY_UPSERT, [row(w) for w in ways])
        cur.executemany(NODE_UPSERT, [row(n) for n in nodes])
        if ways:
            cur.execute("delete from core.osm_lane where osm_id = any(%s::bigint[])", ([w["osm_id"] for w in ways],))
        cur.executemany("insert into core.osm_lane (osm_id, direction, lane, turns) values (%s, %s, %s, %s)", lanes)
    retired_ways = conn.execute("update core.osm_way set active = false where active and last_seen < %s",
                                (seen_at,)).rowcount
    retired_nodes = conn.execute("update core.osm_node set active = false where active and last_seen < %s",
                                 (seen_at,)).rowcount

    issues = Counter(kind for w in ways for kind, _ in w["issues"])
    logged = [(w["osm_id"], text) for w in ways for kind, text in w["issues"] if kind in ("turn_slots", "lanes_total")]
    for osm_id, text in logged[:20]:
        print(f"osm_valley: w{osm_id}: {text}", flush=True)
    if len(logged) > 20:
        print(f"osm_valley: ... and {len(logged) - 20} more lane-count disagreements", flush=True)
    kinds = Counter(n["kind"] for n in nodes)
    stats = {"ways": len(ways), "with lanes": sum(1 for w in ways if w["lane_rows"]), "lane rows": len(lanes),
             **{f"nodes {k}": kinds[k] for k in ("traffic_signals", "crossing_signals", "level_crossing")},
             "record versions new": new, "unchanged": unchanged, "removed": removed,
             "ways retired": retired_ways, "nodes retired": retired_nodes}
    stats.update({f"lanes {k}": v for k, v in sorted(issues.items())})
    return stats


MATCH_SQL = """
insert into core.segment_match (road_segment_id, source, source_id, overlap_m, share, bearing_diff, method,
                                confidence, matched_at)
select id, %(source)s, source_id, overlap_m, share, bearing_diff, %(method)s,
       least(1, share) * cos(radians(bearing_diff)), now()
from (
  select *, least(m, 180 - m) as bearing_diff
  from (
    select *, d - 180 * floor(d / 180) as m
    from (
      select id, source_id, overlap_m, share,
             abs(degrees(ST_Azimuth(p1, p2))
                 - degrees(ST_Azimuth(ST_LineInterpolatePoint(wg, least(f1, f2)),
                                      ST_LineInterpolatePoint(wg, greatest(f1, f2))))) as d
      from (
        select *, greatest(0, least(1, ST_LineLocatePoint(wg, p1))) as f1,      -- clamped: never NaN or out of range
                  greatest(0, least(1, ST_LineLocatePoint(wg, p2))) as f2
        from (
          select id, source_id, wg, overlap_m, share,
                 ST_StartPoint(ST_GeometryN(ov, 1)) as p1,
                 ST_EndPoint(ST_GeometryN(ov, ST_NumGeometries(ov))) as p2
          from (
            select s.id, w.source_id, w.g as wg, ov, ST_Length(ov) as overlap_m,
                   ST_Length(ov) / nullif(ST_Length(s.g), 0) as share
            from osm_match_seg s
            join osm_match_way w on ST_Intersects(s.g, w.b)
            cross join lateral (select ST_CollectionExtract(ST_Intersection(s.g, w.b), 2) as ov) x
          ) pair_overlap
          where share >= %(share)s
        ) pair_ends
        where p1 is not null and p2 is not null and not ST_Equals(p1, p2)
      ) pair_located
      where f1 <> f2
    ) pair_bearing
  ) pair_folded
) pair_diff
where bearing_diff <= %(bearing)s"""


def match_achd_segments(conn, source=MATCH_SOURCE):
    """Rebuild this source's rows in core.segment_match against the active ACHD
    road segments (method buffer15_bearing20, in UTM 11N).

    Self-contained until the shared matcher lands (ingest/segment_match.py, being
    written alongside); swap this body for a call to it, keeping the signature.
    """
    conn.execute("drop table if exists pg_temp.osm_match_way")
    conn.execute(
        """create temp table osm_match_way on commit drop as
           select 'w' || osm_id as source_id, g, ST_Buffer(g, %s, 'quad_segs=4') as b
           from (select osm_id, ST_Transform(geom, 26911) as g from core.osm_way where active) w
           where ST_Length(g) > 0""",
        (MATCH_BUFFER_M,))
    conn.execute("create index on osm_match_way using gist (b)")
    conn.execute("analyze osm_match_way")
    conn.execute("drop table if exists pg_temp.osm_match_seg")
    conn.execute("""create temp table osm_match_seg on commit drop as
                    select id, ST_Transform(geom, 26911) as g from core.road_segment where active""")
    conn.execute("create index on osm_match_seg using gist (g)")
    conn.execute("analyze osm_match_seg")
    conn.execute("delete from core.segment_match where source = %s and method = %s", (source, MATCH_METHOD))
    n = conn.execute(MATCH_SQL, {"source": source, "method": MATCH_METHOD, "share": MATCH_SHARE,
                                 "bearing": MATCH_BEARING_DEG}).rowcount
    segs, ways = conn.execute(
        """select count(distinct road_segment_id), count(distinct source_id) from core.segment_match
           where source = %s and method = %s""", (source, MATCH_METHOD)).fetchone()
    conn.execute("drop table if exists pg_temp.osm_match_way")
    conn.execute("drop table if exists pg_temp.osm_match_seg")
    return {"segment matches": n, "ACHD segments matched": segs, "ways matched": ways}


def load(conn, fetch, src, allow_shrink=False, work_parent=None):
    """osmium, parse, store and match one extract inside an open db.Fetch. osmium's
    intermediate files go in work_parent (the archive's disk on the server)."""
    ways, nodes, counts = extract_features(src, work_parent)
    stats = store(conn, fetch.id, fetch.started_at, ways, nodes, allow_shrink)
    stats.update(match_achd_segments(conn))
    stats.update(counts)
    stamp = data_timestamp(src)
    if stamp:
        stats["data as of"] = stamp
    fetch.records = len(ways) + len(nodes)
    return stats


# ---- the archive -----------------------------------------------------------

def archive_dir(required=True):
    base = os.environ.get("TVT_ARCHIVE")
    if not base:
        if required:
            raise RuntimeError("set TVT_ARCHIVE: extracts are kept in $TVT_ARCHIVE/osm/")
        return None
    folder = os.path.join(base, "osm")
    os.makedirs(os.path.join(folder, "inbox"), exist_ok=True)
    return folder


def file_md5(path):
    h = hashlib.md5(usedforsecurity=False)
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def parse_md5(text):
    """Geofabrik's .md5 files read '<hex>  idaho-latest.osm.pbf'."""
    m = re.match(r"\s*([0-9a-fA-F]{32})\b", text)
    if not m:
        raise ValueError(f"not an MD5 file: {text[:80]!r}")
    return m.group(1).lower()


def last_loaded(folder):
    """The last extract loaded ({'md5', 'file', 'loaded_at'}), or {}."""
    try:
        with open(os.path.join(folder, "last-loaded.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def mark_loaded(folder, md5, path):
    state = {"md5": md5, "file": os.path.basename(path), "loaded_at": db.now().isoformat(timespec="seconds")}
    tmp = os.path.join(folder, "last-loaded.json.part")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, os.path.join(folder, "last-loaded.json"))


def _suffix(path):
    name = os.path.basename(path).lower()
    return next((s for s in OSM_SUFFIXES if name.endswith(s)), None)


def archive_name(path, md5, day):
    """idaho-latest.osm.pbf -> idaho-20261006-1a2b3c4d.osm.pbf"""
    suffix = _suffix(path) or ".osm.pbf"
    stem = os.path.basename(path)[:-len(suffix)] or "extract"
    stem = re.sub(r"-latest$", "", stem)
    return f"{stem}-{day:%Y%m%d}-{md5[:8]}{suffix}"


def extracts(folder):
    """Archived extracts in the folder (not the inbox), newest first."""
    paths = [p for p in glob.glob(os.path.join(folder, "*")) if os.path.isfile(p) and _suffix(p)]
    return sorted(paths, key=os.path.getmtime, reverse=True)


def prune(folder, keep=2):
    """Keep the newest `keep` extracts (and their .md5 files)."""
    removed = []
    for p in extracts(folder)[keep:]:
        for q in (p, p + ".md5"):
            if os.path.exists(q):
                os.remove(q)
        removed.append(os.path.basename(p))
    return removed


def inbox_file(folder):
    """The newest extract waiting in $TVT_ARCHIVE/osm/inbox/, or None."""
    files = extracts(os.path.join(folder, "inbox"))
    return files[0] if files else None


def archive_file(path, folder, md5):
    """Move a file from the inbox (or copy one from elsewhere) into the archive."""
    if os.path.dirname(os.path.abspath(path)) == os.path.abspath(folder):
        return path                                           # already archived (a re-load)
    dest = os.path.join(folder, archive_name(path, md5, db.now()))
    inbox = os.path.join(folder, "inbox")
    if os.path.dirname(os.path.abspath(path)) == os.path.abspath(inbox):
        os.replace(path, dest)
        if os.path.exists(path + ".md5"):
            os.replace(path + ".md5", dest + ".md5")
    else:
        shutil.copyfile(path, dest + ".part")
        os.replace(dest + ".part", dest)
    os.utime(dest)                                            # pruning goes by when it was archived
    return dest


# ---- entry points ----------------------------------------------------------

def load_file(conn, path, force=False, allow_shrink=False):
    """Load an extract the owner downloaded by hand, then archive it (when TVT_ARCHIVE is set).
    Skipped when it's the extract loaded last time, unless force."""
    if not _suffix(path):
        raise SystemExit(f"{path}: expected a .osm.pbf, .osm, .osm.bz2 or .osm.gz file")
    folder = archive_dir(required=False)
    md5 = file_md5(path)
    if os.path.exists(path + ".md5"):                         # the published .md5, if it came along
        with open(path + ".md5", encoding="utf-8") as f:
            published = parse_md5(f.read())
        if published != md5:
            raise SystemExit(f"{path}: MD5 {md5} doesn't match its .md5 file ({published})")
    if folder and not force and last_loaded(folder).get("md5") == md5:
        return {"skipped": "same extract as the last load", "md5": md5[:8], "left in place": path}
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:                 # no request made: robots and status stay empty
        f.bytes = os.path.getsize(path)
        stats = load(conn, f, path, allow_shrink, work_parent=folder)
    if folder:
        kept = archive_file(path, folder, md5)
        mark_loaded(folder, md5, kept)
        stats["archived"] = os.path.basename(kept)
        pruned = prune(folder)
        if pruned:
            stats["pruned"] = ", ".join(pruned)
    stats["md5"] = md5[:8]
    return stats


def check_robots(url):
    """(robots decision, crawl delay) for a URL we're about to fetch, or raise like http.get."""
    host, rules, decision = http.robots_for(url)
    if decision == "unavailable":
        raise http.RobotsUnavailable(f"robots.txt at {host} couldn't be read; treating {url} as disallowed for now")
    if rules is not None and not rules.allowed(url):
        raise http.RobotsDisallowed(f"robots.txt at {host} disallows {url}")
    return decision, (rules.crawl_delay() if rules else None) or 0


def download(url, folder, md5, timeout=120):
    """Stream the extract into the archive, checking robots.txt first and the MD5
    after. Reuses an archived copy with the same MD5. Returns (path, http status, bytes)."""
    for p in glob.glob(os.path.join(folder, f"*-{md5[:8]}.osm.pbf")):
        if file_md5(p) == md5:
            return p, None, 0
    _, delay = check_robots(url)
    time.sleep(max(delay, PAUSE_S))
    dest = os.path.join(folder, archive_name(url, md5, db.now()))
    h, size = hashlib.md5(usedforsecurity=False), 0
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r, open(dest + ".part", "wb") as out:
            status = r.status
            while chunk := r.read(1 << 20):
                h.update(chunk)
                out.write(chunk)
                size += len(chunk)
        if h.hexdigest() != md5:
            raise RuntimeError(f"downloaded extract's MD5 {h.hexdigest()} doesn't match the published {md5}")
    except BaseException:
        if os.path.exists(dest + ".part"):
            os.remove(dest + ".part")
        raise
    os.replace(dest + ".part", dest)
    return dest, status, size


def run(conn, allow_shrink=False):
    """The download route: Geofabrik's .md5, then the extract when it changed.
    While Geofabrik's robots.txt disallows both, this stops at the first request,
    logs the refusal in ops.fetch, and returns it."""
    db.ensure_source(conn, SOURCE)
    folder = archive_dir()
    md5 = None
    try:
        with db.Fetch(conn, SOURCE["name"]) as f:
            status, body, f.robots = http.get(MD5_URL, timeout=60)
            f.http_status, f.bytes = status, len(body)
            md5 = parse_md5(body.decode("ascii", "replace"))
            if last_loaded(folder).get("md5") == md5:
                f.records = 0
                return {"skipped": "extract unchanged since the last load", "md5": md5[:8]}
            path, status, size = download(URL, folder, md5)
            f.http_status = status or f.http_status
            f.bytes += size
            stats = load(conn, f, path, allow_shrink, work_parent=folder)
    except http.RobotsDisallowed as err:                    # includes RobotsUnavailable
        return {"refused": str(err)}
    mark_loaded(folder, md5, path)
    pruned = prune(folder)
    stats.update({"md5": md5[:8], "archived": os.path.basename(path)})
    if pruned:
        stats["pruned"] = ", ".join(pruned)
    return stats
