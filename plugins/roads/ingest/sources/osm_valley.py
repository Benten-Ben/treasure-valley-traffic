"""OpenStreetMap in the valley: major roads and every way with lanes, plus signal and crossing nodes.

License ODbL: credit "© OpenStreetMap contributors". OpenStreetMap stays in
its own tables (core.osm_way, core.osm_lane, core.osm_node, and its rows in
raw.record and core.segment_match), so the other sources' tables aren't
pulled under the ODbL (db/migrations/0011, docs/09 §9.3).

Where the data comes from: by hand only. Geofabrik's robots.txt, read Oct 6,
2026, disallows its extracts for every robot (`Disallow: *.osm.pbf`,
`*.md5`, `*updates*`, ...), so this module makes no network requests and the
source has no schedule; it isn't in the registry's SOURCES, so `run all` and
`serve` never touch it. The owner downloads the Idaho extract in a browser
(download.geofabrik.de/north-america/us/idaho.html), copies it (and its .md5)
to the server, and loads it with core's OpenStreetMap loader
(ingest/osm_extract.py), which reads one extract into every plugin's
consumers, this one first:

    python3 -m ingest osm-load --inbox          # newest file in $TVT_ARCHIVE/osm/inbox/
    python3 -m ingest osm-load --file PATH      # a .osm.pbf or OSM XML file

It registers the source, logs the load in ops.fetch, and archives the file
in $TVT_ARCHIVE/osm/ (the last two are kept). The extract this source loaded
last (same MD5, in $TVT_ARCHIVE/osm/last-loaded.json, its own gate) is
skipped. If Geofabrik agrees to a weekly scripted download, it gets added
through ingest/http.py. The inbox, MD5 and archive helpers and the keep rule
live in core now (the landscape sprint's loader, Oct 2026); they're imported
back here unchanged. load_file() still loads this source on its own.

Processing (osmium-tool, installed in the ingest image), over the core
loader's smart cut of the box (or a whole extract, with load_file):
  1. osmium extract: cut the valley box (-117.05,43.00,-115.95,43.85),
     keeping ways that cross its edge whole (complete_ways: on the smart cut,
     the same ways and nodes as on the whole extract);
  2. osmium tags-filter: highway ways, and nodes tagged
     highway=traffic_signals, crossing=traffic_signals,
     crossing:signals=yes or railway=level_crossing;
  3. osmium export to GeoJSON lines, with each object's id, version and
     timestamp, and each way's node IDs.

What we keep: every major way (motorway to tertiary and their _link roads)
and any other highway way tagged lanes, lanes:forward, lanes:backward or
turn:lanes*, but not proposed or unbuilt roads or areas. (Residential
streets without lanes tags aren't kept, so their names aren't here either.)
Nodes, as core.osm_node kinds:
  - traffic_signals: highway=traffic_signals, an intersection signal;
  - crossing_signals: a pedestrian signal: crossing=traffic_signals or
    crossing:signals=yes, traffic_signals=crossing, or highway=traffic_signals
    tagged as a crossing (crossing=traffic_signals) away from a junction;
  - level_crossing: railway=level_crossing.
Fire-station (traffic_signals=emergency), ramp-meter, blinker and
level-crossing signals aren't intersection signals and 0011's kinds have no
place for them, so they're skipped (and counted). A node is at a junction
when it lies on three or more road ways, or on road ways with different
names; osmium exports nodes before ways, so the ways' node IDs settle it.

raw.record (keys 'w<id>' and 'n<id>') holds the tags and a hash of the
geometry, so versions stay small; the geometry goes to the typed tables.
Ways and nodes missing from a load become inactive.

Lanes (core.osm_lane): one row per lane per direction, numbered from 1 at
the left in the direction of travel, as OSM's turn:lanes and WZDx do. The
direction split comes from lanes:forward/backward/both_ways, else from the
turn:lanes:* slot counts, else, on a two-way road with an even count and no
centre lane, an even split (OSM's convention); an odd count with no split
gets no lane rows (the lanes tag stays on the way). When a turn:lanes value's
slot count disagrees with the lane count, it's logged and the lanes get no
turns; the tags are kept as tagged.

Matching (core.segment_match) uses the shared matcher (segment_match.py),
in UTM 11N, with bearings within 20° along the shared stretch:
  - 'buffer15_bearing20': at least 60% of the ACHD segment lies within 15 m
    of the way. Both carriageways of a divided road (5-7 m either side of
    ACHD's single centerline) can match one segment.
  - 'way_in_buffer15_bearing20': otherwise, at least 60% of a way of 20 m or
    more lies within 15 m of the segment, which catches turn-bay ways split
    off a block (owner, Oct 6).
share and overlap_m always measure the ACHD segment (0011); confidence is
the matched rule's share × cos(bearing difference), halved when the way and
the segment are both named and the names disagree.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone

from ingest import db
from ingest.osm_extract import (BOX, LANE_KEYS, MAJOR, NOT_ROADS, OSM_SUFFIXES, PAGE, ROADS,  # noqa: F401
                                _suffix, archive_dir, archive_file, archive_name, extracts, file_md5, inbox_file,
                                keep_way, parse_md5, prune)
from .. import segment_match

SOURCE = {
    "name": "osm_valley",
    "title": "OpenStreetMap: valley roads, lanes, signal and crossing nodes",
    "url": PAGE,
    "access": "open",
    "schedule": None,   # loaded by hand: Geofabrik's robots.txt disallows scripted downloads (Oct 6, 2026)
    "license": "ODbL",
    "credit": "© OpenStreetMap contributors",
    "notes": "Geofabrik's Idaho extract, downloaded by hand and loaded with python3 -m ingest osm-load, cut to "
             "the valley box: major ways and ways with lanes, lanes per direction, signal and crossing nodes. "
             "Its own tables (ODbL).",
}

TAG_FILTERS = ["w/highway", "n/highway=traffic_signals", "n/crossing=traffic_signals",
               "n/crossing:signals=yes", "n/railway=level_crossing"]
OSMIUM_TIMEOUT_S = 1800
SHRINK_GUARD = 0.5            # refuse to retire ways when a load brings fewer than half the active ones

# MAJOR, ROADS, NOT_ROADS, LANE_KEYS and keep_way() come from ingest/osm_extract.py: the keep rule
# is the first rule of core's partition (plan C10), so it lives there, unchanged.
NOT_INTERSECTION_SIGNALS = {"emergency", "ramp_meter", "blinker", "level_crossing"}   # traffic_signals=*

MATCH_SOURCE = SOURCE["name"]
MATCH_METHOD = "buffer15_bearing20"
MATCH_METHOD_WAY = segment_match.WAY_IN + MATCH_METHOD      # "way_in_buffer15_bearing20"


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


# ---- what we keep (keep_way: ingest/osm_extract.py) ------------------------

def special_signal(tags):
    """A fire-station, ramp-meter, blinker or level-crossing signal: not an intersection signal."""
    return (tags.get("highway") == "traffic_signals"
            and str(tags.get("traffic_signals") or "").strip().lower() in NOT_INTERSECTION_SIGNALS)


def node_kind(tags, at_junction=None):
    """traffic_signals, crossing_signals or level_crossing; None for other nodes (stop signs
    and plain crossings come through as members of the ways, and special signals are skipped).

    highway=traffic_signals tagged as a crossing (crossing=traffic_signals or
    crossing:signals=yes) is an intersection signal only at a junction; when
    at_junction is unknown (None), it counts as a crossing signal."""
    if tags.get("railway") == "level_crossing":
        return "level_crossing"
    crossing = tags.get("crossing") == "traffic_signals" or tags.get("crossing:signals") == "yes"
    if tags.get("highway") == "traffic_signals":
        if special_signal(tags):
            return None
        if str(tags.get("traffic_signals") or "").strip().lower() == "crossing":
            return "crossing_signals"
        if crossing and not at_junction:
            return "crossing_signals"
        return "traffic_signals"
    return "crossing_signals" if crossing else None


def needs_junction(tags):
    """Whether node_kind's answer depends on the node being at a junction."""
    return node_kind(tags, True) != node_kind(tags, False)


def at_junction(members):
    """members: [(way id, name or ref or None)] of the road ways through a node. A junction
    has three or more of them, or road ways with different names (a road split at a
    mid-block signal gives two ways with one name)."""
    return len({w for w, _ in members}) >= 3 or len({n for _, n in members}) >= 2


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
    """Ways and nodes we keep, from osmium's GeoJSON lines. Returns (ways, nodes, counts).

    Nodes whose kind depends on being at a junction wait until the road ways
    have been read (osmium writes nodes first; each way carries @way_nodes)."""
    ways, nodes, counts = {}, {}, Counter()
    waiting, members = {}, defaultdict(list)          # node id -> node; node id -> [(way id, name)]
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
            if waiting and tags.get("highway") in ROADS:
                name = _text(tags.get("name")) or _text(tags.get("ref"))
                for nid in set(props.get("@way_nodes") or ()) & waiting.keys():
                    members[nid].append((osm_id, name))
            if keep_way(tags):
                ways[osm_id] = way_row(osm_id, props, tags, geom)
            else:
                counts["ways skipped"] += 1
        elif kind == "n" and geom.get("type") == "Point" and osm_id is not None:
            node = {"osm_id": osm_id, "tags": tags, "geom": geom, "osm_version": props.get("@version"),
                    "osm_timestamp": parse_timestamp(props.get("@timestamp"))}
            if needs_junction(tags):
                waiting[osm_id] = node
            elif node_kind(tags):
                nodes[osm_id] = {**node, "kind": node_kind(tags)}
            elif special_signal(tags):
                counts["special signals skipped"] += 1
            else:
                counts["nodes skipped"] += 1
        else:
            counts["other features skipped"] += 1
    for osm_id, node in waiting.items():
        junction = at_junction(members.get(osm_id, []))
        nodes[osm_id] = {**node, "kind": node_kind(node["tags"], junction)}
        counts["signal-and-crossing nodes at junctions" if junction else "signal-and-crossing nodes mid-block"] += 1
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
         "--geometry-types", "point,linestring", "--attributes", "id,version,timestamp,way_nodes",
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


LINES_SQL = """select %(source)s::text as source, 'w' || osm_id as source_id, geom, name
               from core.osm_way where active"""


def match_achd_segments(conn, source=MATCH_SOURCE):
    """Rebuild this source's rows in core.segment_match against the active ACHD road
    segments with the shared matcher (segment_match.py): methods
    buffer15_bearing20 and way_in_buffer15_bearing20, in UTM 11N. Doesn't commit."""
    segment_match.rematch(conn, [source], LINES_SQL, {"source": source})
    by_method = dict(conn.execute(
        """select method, count(*) from core.segment_match where source = %s and method in (%s, %s) group by 1""",
        (source, MATCH_METHOD, MATCH_METHOD_WAY)).fetchall())
    segs, ways = conn.execute(
        """select count(distinct road_segment_id), count(distinct source_id) from core.segment_match
           where source = %s and method in (%s, %s)""", (source, MATCH_METHOD, MATCH_METHOD_WAY)).fetchone()
    return {"segment matches": by_method.get(MATCH_METHOD, 0), "turn-bay matches": by_method.get(MATCH_METHOD_WAY, 0),
            "ACHD segments matched": segs, "ways matched": ways}


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


# ---- this source's gate (the rest of the archive: ingest/osm_extract.py) ---

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


def loaded_md5(folder):
    """This source's gate for core's loader: the MD5 in last-loaded.json, as before (core's other
    consumers keep theirs in ops.osm_consumer)."""
    return last_loaded(folder).get("md5")


def consume(conn, run):
    """This source as a consumer of core's loader (ingest/osm_extract.py): its own unchanged
    pipeline over the loader's smart cut (run.cut), store, match, inside the loader's db.Fetch."""
    stats = load(conn, run.fetch, run.cut, run.allow_shrink, work_parent=run.work_parent)
    if run.data_as_of:
        stats["data as of"] = run.data_as_of       # the extract's own header, which the cut may not carry
    return stats


# ---- this source on its own ------------------------------------------------

def load_file(conn, path, force=False, allow_shrink=False):
    """Load an extract the owner downloaded by hand into this source alone (its own cut of the
    whole file), then archive it (when TVT_ARCHIVE is set). Registers the source and logs the
    load in ops.fetch. Skipped when it's the extract loaded last time, unless force. The way in
    is core's loader (`python3 -m ingest osm-load`), which loads every consumer, this one first."""
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
        pruned = prune(folder, protect=(kept,))
        if pruned:
            stats["pruned"] = ", ".join(pruned)
    stats["md5"] = md5[:8]
    return stats
