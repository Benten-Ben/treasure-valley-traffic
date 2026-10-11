"""trails-match: Ridge to Rivers' trails and the Greenbelt's closures and detours, linked onto
OpenStreetMap's paths (landscape sprint, plan C18, package P6-data).

    python3 -m ingest trails-match              # the build: every agency line, routes, the network
    python3 -m ingest trails-match --dry-run    # the same, reported, then rolled back

OpenStreetMap draws the network (trails.osm_path, and the named exception's
ways in core.osm_way); the City of Boise's lines carry the status. Each agency
line (an R2R trail from raw.record, a Greenbelt closure or detour) is linked to
the ways it lies along with core's line matcher (ingest/linematch.py), in
pieces: the line is cut into pieces of at most PIECE_M (150 m), each piece is
matched to the ways around it (buffer 15 m, bearing within 20°, 60% of the way
within the piece's buffer or of the piece within the way's), and a way is
**fully linked** to the line when 60% of it lies within 15 m of pieces that
matched it; **partly** (method way_in_...) when only 20 m or more does: the
way is longer than the line, or runs on past it. Only full links paint the
line's state on a way. Wherever else the line runs (its **gap**: stretches of
20 m or more farther than 15 m from its fully linked ways, or all of it), it
draws itself. So every metre of the line shows its state, and no way shows a
state beyond the line.

Why pieces (measured on scratch, Oct 11, the Oct 5 extract): matched whole, a
long winding trail fails the bearing check against a long winding OSM way that
lies right along it, since the check compares end-to-end chords (Freddys Stack
Rock Trail, 4.8 km, with an OSM path within 15 m for 4.6 km, had no link).
Whole, R2R's multi-use trails were linked along 308 of their 353 km; in pieces
of 150 m, 320 km. Most of the rest is R2R's "Access Road" (50 km), which OSM
maps as roads, so it draws itself. Only public ways are targets: a way closed
to the public, or a track taken as canal access, is never a trail, so an R2R
trail on one draws itself too.

Two ways it runs (plan P6-data; docs/15 "Builds and their marks"):

* **After a poll** (`after_poll`, called by r2r_trails and
  boise_greenbelt_closures once their data is committed): when the poll
  stored new or removed versions, the lines whose geometry changed (their
  fingerprint) are relinked, at most POLL_MAX_LINES of them. It runs in its
  own try block with its own ops.fetch row (source trails_match), so a match
  that fails never fails the poll: the failure is logged there, and the build
  is marked. More lines than that (the City reloading its layer), or a source
  never matched, are left for the build, which is marked.
* **The build** (`trails-match`, by hand, logged in ops.build_run): after a
  new extract (osm_paths' load marks it) or when marked. Every current line is
  relinked against the extract osm_paths holds; then the canal-bank rule (once
  water's reaches exist), each route's line, and the network at valley zoom.

Every run that changes links gives the Trails layer's tiles a new version
(core.layer_version 'trails.paths', and 'trails.agency' for the lines that
draw themselves; 'trails.routes' from the build). The links carry the City's
ids, so they're internal: republish aggregates, like their sources.

The canal-bank rule (plan C18, cut-first): a track lying along a canal,
lateral, ditch or drain of water's build (water.reach, not piped) for at least
60% of its length, within 15 m and within 20°, and not tagged access=yes or
permissive, is irrigation access, not a trail (trails.canal_track). It needs
water's build, so until water.reach exists it's skipped, and said so.
"""

import argparse
import sys

from ingest import builds, db, layer_version, linematch

SOURCE = {
    "name": "trails_match",
    "title": "Trail links: Ridge to Rivers' trails and Greenbelt closures on OpenStreetMap's paths",
    "url": "https://github.com/Benten-Ben/treasure-valley-traffic/blob/main/plugins/trails/ingest/match.py",
    "access": "open",
    "schedule": None,   # after the trails pollers commit, and by hand (trails-match); fetches nothing
    "license": "derived: ODbL (OpenStreetMap) with the City of Boise's lines (none stated)",
    "credit": "© OpenStreetMap contributors; City of Boise Parks & Recreation (Ridge to Rivers)",
    "notes": "Derived, fetches nothing: links the City of Boise's trail and Greenbelt closure lines (raw.record) to "
             "OpenStreetMap's paths (trails.osm_path) with core's line matcher. A row per poll that relinked "
             "changed lines; the trails-match build logs in ops.build_run. Internal: the City's ids.",
}
BUILD = "trails-match"
SOURCES = ("r2r_trails", "boise_greenbelt_closures")
OSM_CONSUMER = "trails.osm_paths"
RULE = linematch.Rule(near_m=15, check="bearing")          # each piece of a line against each way
PIECE_M = 150.0               # agency lines are matched in pieces this long at most
METHOD = f"pieces{PIECE_M:g}_{RULE.method}"                 # 'pieces150_buffer15_bearing20'
CANAL_RULE = linematch.Rule(near_m=15, check="bearing")
CANAL_KINDS = ("canal", "lateral", "ditch", "drain")
NEAR_DEG = 0.0005             # a way within this many degrees (40-55 m here) of a line is a candidate
POLL_MAX_LINES = 40           # more changed lines than this in one poll: left for the build
LO_TOLERANCE_M = 5.0          # the valley-zoom network's simplification (UTM metres)
MIN_GAP_M = 20.0              # an agency line's stretch off its ways shorter than this isn't drawn as itself
UTM = linematch.SRID

CITY_CREDIT = "City of Boise Parks & Recreation (Ridge to Rivers); City of Boise Parks and Recreation"
CITY_LICENSE = "none stated (City of Boise disclaimer only)"
OSM_CREDIT = "© OpenStreetMap contributors"
# The Trails layer's tile sets (core.layer_version), as the trails layer's tile definitions name them.
LAYERS = {
    "trails.paths": {"license": "ODbL", "republish": "yes", "credit": OSM_CREDIT},
    "trails.routes": {"license": "ODbL", "republish": "yes", "credit": OSM_CREDIT},
    "trails.agency": {"license": CITY_LICENSE, "republish": "aggregates", "credit": CITY_CREDIT},
}


# ---- state ------------------------------------------------------------------------------------

def ready(conn):
    """Whether trails 0001 is applied (production before the deploy runbook isn't)."""
    return conn.execute("select to_regclass('trails.matched_line') is not null").fetchone()[0]


def osm_md5(conn):
    """The extract osm_paths holds (its gate in ops.osm_consumer), or None before its first load."""
    if not conn.execute("select to_regclass('ops.osm_consumer') is not null").fetchone()[0]:
        return None
    row = conn.execute("select md5 from ops.osm_consumer where consumer = %s", (OSM_CONSUMER,)).fetchone()
    return row[0] if row else None


def pending(conn, sources=SOURCES):
    """The agency lines a poll should relink: (current lines never matched or whose line changed
    since, as [(source, source_id)]; matched lines no longer current)."""
    todo = conn.execute(
        """select l.source, l.source_id from trails.agency_line l
           left join trails.matched_line m on m.source = l.source and m.source_id = l.source_id
           where l.source = any(%s) and (m.source is null or m.line_fp is distinct from l.line_fp)
           order by 1, 2""", (list(sources),)).fetchall()
    gone = conn.execute(
        """select m.source, m.source_id from trails.matched_line m
           where m.source = any(%s) and not exists (
             select 1 from trails.agency_line l where l.source = m.source and l.source_id = m.source_id)
           order by 1, 2""", (list(sources),)).fetchall()
    return [tuple(k) for k in todo], [tuple(k) for k in gone]


def current_lines(conn, sources=SOURCES):
    return [tuple(k) for k in conn.execute(
        "select source, source_id from trails.agency_line where source = any(%s) order by 1, 2",
        (list(sources),)).fetchall()]


def matched_sources(conn, source):
    return conn.execute("select count(*) from trails.matched_line where source = %s", (source,)).fetchone()[0]


# ---- relinking ----------------------------------------------------------------------------------

_KEYS = """create temp table if not exists tm_key (source text, source_id text) on commit drop;
           truncate tm_key"""
# Each line in pieces of at most PIECE_M (each part cut into equal pieces), in UTM.
_PIECES = f"""create temp table tm_piece on commit drop as
  select l.source, l.source_id, l.source_id || '#' || coalesce(d.path[1], 1) || '.' || i as piece_id, l.name,
         ST_LineSubstring(d.geom, i::float8 / kk.k, (i + 1)::float8 / kk.k) as g
  from trails.agency_line l
  join tm_key t on t.source = l.source and t.source_id = l.source_id
  cross join lateral ST_Dump(ST_Transform(l.geom, {UTM})) d
  cross join lateral (select greatest(1, ceil(ST_Length(d.geom) / %(piece)s))::int as k) kk
  cross join lateral generate_series(0, kk.k - 1) i
  where l.geom is not null and ST_Length(d.geom) > 0"""
LINES_SQL = "select source, piece_id as source_id, name, ST_Transform(g, 4326) as geom from pg_temp.tm_piece"
TARGETS_SQL = """select t.osm_id as id, t.name, t.geom from trails.target_way t
                 where exists (select 1 from pg_temp.tm_box b where t.geom && b.box)"""
# Each (line, way): how much of the way lies along the line's pieces that matched it (within 15 m
# of them), and how much of the line those pieces are.
_LINKS = f"""create temp table tm_link on commit drop as
  with pm as (
    select p.source, p.source_id, m.osm_id, p.g, ST_Length(p.g) as piece_m, m.bearing_diff, m.confidence
    from tm_pm m join tm_piece p on p.piece_id = m.piece_id),
  agg as (
    select source, source_id, osm_id, ST_Union(ST_Buffer(g, %(near)s, 'quad_segs=4')) as buf, sum(piece_m) as pieces_m,
           sum(coalesce(bearing_diff, 0) * piece_m) / sum(piece_m) as bearing_diff,
           sum(confidence * piece_m) / sum(piece_m) as confidence
    from pm group by 1, 2, 3)
  select a.source, a.source_id, a.osm_id, a.pieces_m, a.bearing_diff, a.confidence,
         ST_Length(ST_Intersection(w.g, a.buf)) as overlap_m, ST_Length(w.g) as way_m,
         (select sum(ST_Length(p.g)) from tm_piece p where p.source = a.source and p.source_id = a.source_id) as line_m
  from agg a
  join (select osm_id, ST_Transform(geom, {UTM}) as g from trails.any_way) w on w.osm_id = a.osm_id"""


def _stage_keys(conn, keys):
    conn.execute(_KEYS)
    with conn.cursor() as cur:
        with cur.copy("copy tm_key (source, source_id) from stdin") as cp:
            for k in keys:
                cp.write_row(k)
    for table in ("tm_box", "tm_piece", "tm_pm", "tm_link"):
        conn.execute(f"drop table if exists pg_temp.{table}")
    conn.execute(_PIECES, {"piece": PIECE_M})
    conn.execute(
        """create temp table tm_box on commit drop as
           select ST_Expand(ST_Envelope(l.geom), %s) as box from trails.agency_line l
           join tm_key k on k.source = l.source and k.source_id = l.source_id where l.geom is not null""",
        (NEAR_DEG,))


def link_rows(conn, matches):
    """The links from the pieces' matches: [(source, source_id, osm_id, overlap_m, share, line_share,
    bearing_diff, confidence, method)]. A way is fully linked when RULE.min_share of it lies along
    pieces that matched it; otherwise partly (way_in_...), when 20 m or more of it does."""
    conn.execute("create temp table tm_pm (piece_id text, osm_id bigint, bearing_diff real, confidence real) "
                 "on commit drop")
    with conn.cursor() as cur:
        with cur.copy("copy tm_pm (piece_id, osm_id, bearing_diff, confidence) from stdin") as cp:
            for m in matches:
                cp.write_row((m["source_id"], m["target_id"], m["bearing_diff"], m["confidence"]))
    conn.execute(_LINKS, {"near": RULE.near_m})
    out = []
    for source, source_id, osm_id, pieces_m, bearing, confidence, overlap, way_m, line_m in conn.execute(
            "select source, source_id, osm_id, pieces_m, bearing_diff, confidence, overlap_m, way_m, line_m "
            "from tm_link order by 1, 2, 3").fetchall():
        share = overlap / way_m if way_m else 0.0
        line_share = min(pieces_m / line_m, 1.0) if line_m else None
        if share >= RULE.min_share:
            method, scale = METHOD, min(share, 1.0)
        elif overlap >= RULE.min_line_m:
            method, scale = linematch.WAY_IN + METHOD, (line_share or 0.0)
        else:
            continue
        out.append((source, source_id, osm_id, round(overlap, 1), round(share, 3),
                    None if line_share is None else round(line_share, 3), round(bearing, 1),
                    round(max(0.0, min(1.0, confidence * scale)), 3), method))
    return out


def relink(conn, keys, gone, md5, now, matched_by, fetch_id=None):
    """Replace the links of the lines in keys ([(source, source_id)]) with fresh matches against the
    ways osm_paths holds now, and forget the lines in gone. Doesn't commit. Returns stats."""
    keys, gone = list(keys), list(gone)
    for source, source_id in gone:
        conn.execute("delete from trails.link where source = %s and source_id = %s", (source, source_id))
        conn.execute("delete from trails.matched_line where source = %s and source_id = %s", (source, source_id))
    stats = {"lines": len(keys), "gone": len(gone), "links": 0, "matched lines": 0}
    if not keys:
        return stats
    _stage_keys(conn, keys)
    rows = link_rows(conn, linematch.match(conn, LINES_SQL, TARGETS_SQL, RULE))
    conn.execute("""delete from trails.link k using tm_key t
                    where k.source = t.source and k.source_id = t.source_id""")
    with conn.cursor() as cur:
        cur.executemany(
            """insert into trails.link (source, source_id, osm_id, overlap_m, share, line_share, bearing_diff,
                                        confidence, method, matched_at)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", [(*r, now) for r in rows])
    # Each line's match: how much of it lies within 15 m of the ways it's fully linked to (they lie
    # along it), and its gap, where it draws itself: the rest, in stretches of MIN_GAP_M or more.
    # Partial links (way_in_: a longer way) take no state, so they leave a gap.
    conn.execute(
        f"""insert into trails.matched_line (source, source_id, line_fp, osm_md5, line_m, covered_m, gap, gap_m, links,
                                             matched_at, matched_by, fetch_id)
            select t.source, t.source_id, l.line_fp, %(md5)s, ST_Length(l.geom::geography), c.covered_m, g.gap,
                   coalesce(ST_Length(g.gap::geography), 0), n.links, %(now)s, %(by)s, %(fetch)s
            from tm_key t join trails.agency_line l on l.source = t.source and l.source_id = t.source_id
            cross join lateral (select ST_Transform(l.geom, {UTM}) as lg) u
            cross join lateral (
              select ST_Buffer(ST_Collect(ST_Transform(w.geom, {UTM})), %(near)s) as buf
              from trails.link k join trails.any_way w on w.osm_id = k.osm_id
              where k.source = t.source and k.source_id = t.source_id and not starts_with(k.method, 'way_in_')) b
            cross join lateral (
              select case when b.buf is not null then ST_Length(ST_Intersection(u.lg, b.buf)) end as covered_m) c
            cross join lateral (
              select ST_Transform(ST_Multi(ST_Collect(d.geom order by d.path)), 4326) as gap
              from ST_Dump(ST_LineMerge(ST_CollectionExtract(
                     case when b.buf is null then u.lg else ST_Difference(u.lg, b.buf) end, 2))) d
              where ST_Length(d.geom) >= %(min_gap)s) g
            cross join lateral (
              select count(*) as links from trails.link k where k.source = t.source and k.source_id = t.source_id) n
            on conflict (source, source_id) do update set
              line_fp = excluded.line_fp, osm_md5 = excluded.osm_md5, line_m = excluded.line_m,
              covered_m = excluded.covered_m, gap = excluded.gap, gap_m = excluded.gap_m, links = excluded.links,
              matched_at = excluded.matched_at, matched_by = excluded.matched_by, fetch_id = excluded.fetch_id""",
        {"md5": md5, "near": RULE.near_m, "min_gap": MIN_GAP_M, "now": now, "by": matched_by, "fetch": fetch_id})
    full = [r for r in rows if not r[8].startswith(linematch.WAY_IN)]
    stats.update({"links": len(rows), "full links": len(full), "partial links": len(rows) - len(full),
                  "matched lines": len({(r[0], r[1]) for r in rows}),
                  "unmatched lines": len(keys) - len({(r[0], r[1]) for r in rows})})
    return stats


def record_versions(conn, layers, build, features=None):
    """A new tile version for each of layers (keys of LAYERS), in the transaction of the data."""
    return {layer: layer_version.record(conn, layer, build=build, features=(features or {}).get(layer),
                                        **LAYERS[layer]) for layer in layers}


# ---- after a poll -------------------------------------------------------------------------------

LINKS_LOCK = "select hashtextextended('tvt trails links', 0)"   # one writer of trails.link at a time


def changed(stats):
    """Whether a poll's stats say it stored a new or removed version (a line may have moved)."""
    return bool(stats.get("versions new") or stats.get("removed"))


def after_poll(conn, source, changed):
    """Relink the lines a poll changed, once its data is committed (plan P6-data). changed: whether
    the poll stored new or removed versions; nothing happens otherwise. A failure is logged in
    ops.fetch (source trails_match), marks the build, and is reported in the poll's stats: it
    never fails the poll. Returns stats for the poll's line ({} when there was nothing to do)."""
    if not changed:
        return {}
    try:
        return _after_poll(conn, source)
    except Exception as err:
        conn.rollback()
        try:
            builds.mark(conn, BUILD, by=source, reason=f"relinking after {source}'s poll failed: "
                                                       f"{type(err).__name__}: {err}")
            conn.commit()
        except Exception:
            conn.rollback()
        return {"links": f"failed ({type(err).__name__}), logged in ops.fetch as {SOURCE['name']}; "
                         f"{BUILD} is marked"}


def _after_poll(conn, source):
    if not ready(conn):
        conn.rollback()
        return {}
    md5 = osm_md5(conn)
    if md5 is None:                           # osm_paths hasn't loaded: nothing to link to yet
        conn.rollback()
        return {}
    todo, gone = pending(conn, [source])
    if not todo and not gone:
        conn.rollback()
        return {}
    if len(todo) > POLL_MAX_LINES or not matched_sources(conn, source):
        builds.mark(conn, BUILD, by=source, reason=f"{len(todo)} of {source}'s lines changed or were never linked")
        conn.commit()
        return {"links": f"{len(todo)} lines left for {BUILD} (marked)"}
    key = conn.execute(LINKS_LOCK).fetchone()[0]
    if not conn.execute("select pg_try_advisory_lock(%s)", (key,)).fetchone()[0]:
        builds.mark(conn, BUILD, by=source, reason=f"{len(todo)} of {source}'s lines changed while it ran")
        conn.commit()
        return {"links": f"{BUILD} is running: {len(todo)} lines left for its next run (marked)"}
    try:                                      # a session lock: Fetch's commits don't end it
        conn.commit()
        db.ensure_source(conn, SOURCE)
        with db.Fetch(conn, SOURCE["name"]) as f:
            todo, gone = pending(conn, [source])          # again, now that nothing else relinks
            stats = relink(conn, todo, gone, md5, f.started_at, "poll", f.id)
            f.records = stats["links"]
            versions = record_versions(conn, ("trails.paths", "trails.agency"), f"{SOURCE['name']} after {source}")
    finally:
        try:
            conn.rollback()
            conn.execute("select pg_advisory_unlock(%s)", (key,))
            conn.commit()
        except Exception:
            pass                              # the lock goes with the connection
    return {"links": f"{stats['links']} for {stats['lines']} changed lines ({stats['gone']} gone)",
            "tiles": versions["trails.paths"]}


# ---- the canal-bank rule (cut-first) --------------------------------------------------------------

def canal_reaches_sql(conn):
    """The SQL of water's canal reaches, or None until water's build (water.reach) exists."""
    if not conn.execute("select to_regclass('water.reach') is not null").fetchone()[0]:
        return None
    cols = {r[0] for r in conn.execute(
        """select column_name from information_schema.columns
           where table_schema = 'water' and table_name = 'reach'""").fetchall()}
    if not {"id", "kind", "geom"} <= cols:
        return None
    piped = " and not piped" if "piped" in cols else ""
    return (f"select id::text as id, name, geom from water.reach "
            f"where kind in ({', '.join(repr(k) for k in CANAL_KINDS)}){piped}")


TRACKS_SQL = """select 'osm_paths' as source, w.osm_id::text as source_id, w.name, w.geom
                from trails.any_way w
                where w.kind = 'track' and not w.no_access
                  and coalesce(lower(btrim(w.tags->>'access')), '') not in ('yes', 'permissive')
                  and exists (select 1 from ({reaches}) r where ST_DWithin(w.geom, r.geom, {near}))"""


def canal_tracks(conn, now, reaches_sql=None):
    """Rewrite trails.canal_track: the tracks along a canal bank, where 60% or more of the track
    lies within 15 m of canal reaches that match it (core's matcher: either one's share, and the
    bearing). The reach recorded is the one most of the track lies along. Returns the count, or
    None when water's reaches don't exist yet (the rule is skipped). Doesn't commit."""
    reaches_sql = reaches_sql or canal_reaches_sql(conn)
    if reaches_sql is None:
        return None
    matches = linematch.match(conn, TRACKS_SQL.format(reaches=reaches_sql, near=NEAR_DEG), reaches_sql, CANAL_RULE)
    conn.execute("drop table if exists pg_temp.tm_cm")
    conn.execute("create temp table tm_cm (osm_id bigint, reach_id text, bearing_diff real) on commit drop")
    with conn.cursor() as cur:
        with cur.copy("copy tm_cm (osm_id, reach_id, bearing_diff) from stdin") as cp:
            for m in matches:
                cp.write_row((int(m["source_id"]), str(m["target_id"]), m["bearing_diff"]))
    conn.execute("delete from trails.canal_track")
    return conn.execute(
        f"""insert into trails.canal_track (osm_id, reach_id, line_share, bearing_diff, built_at)
            with pair as (
              select c.osm_id, c.reach_id, c.bearing_diff, ST_Buffer(ST_Transform(r.geom, {UTM}), %(near)s) as rb
              from tm_cm c join ({reaches_sql}) r on r.id = c.reach_id),
            track as (
              select p.osm_id, avg(p.bearing_diff) as bearing_diff,
                     ST_Length(ST_Intersection(w.g, ST_Union(p.rb))) / nullif(ST_Length(w.g), 0) as share,
                     (array_agg(p.reach_id order by ST_Length(ST_Intersection(w.g, p.rb)) desc))[1] as reach_id
              from pair p
              join (select osm_id, ST_Transform(geom, {UTM}) as g from trails.any_way) w on w.osm_id = p.osm_id
              group by p.osm_id, w.g)
            select osm_id, reach_id, round(share::numeric, 3), round(bearing_diff::numeric, 1), %(now)s
            from track where share >= %(share)s""",
        {"near": CANAL_RULE.near_m, "now": now, "share": CANAL_RULE.min_share}).rowcount


# ---- routes and the valley-zoom network --------------------------------------------------------

# Where a route's member ways can be: the partition's owners' tables (and the named exception's).
WAY_TABLES = ("core.osm_way", "roads.osm_street", "roads.osm_paving", "trails.osm_path")


def way_tables_sql(conn):
    """A union of (osm_id, geom) over the partition owners' line tables that exist here."""
    parts = []
    for table in WAY_TABLES:
        schema, name = table.split(".")
        cols = {r[0] for r in conn.execute(
            "select column_name from information_schema.columns where table_schema = %s and table_name = %s",
            (schema, name)).fetchall()}
        if {"osm_id", "geom", "active"} <= cols:
            parts.append(f"select osm_id, geom from {table} where active "
                         "and ST_GeometryType(geom) in ('ST_LineString', 'ST_MultiLineString')")
    return " union all ".join(parts)


def route_lines(conn, now):
    """Rewrite trails.route_line from each active route's member ways. Doesn't commit."""
    ways = way_tables_sql(conn)
    conn.execute("delete from trails.route_line")
    conn.execute(
        f"""insert into trails.route_line (osm_id, ways, ways_found, geom, length_m, built_at)
            select r.osm_id, cardinality(r.way_ids), count(w.osm_id),
                   ST_Multi(ST_LineMerge(ST_Collect(w.geom order by m.n))),
                   sum(ST_Length(w.geom::geography)), %s
            from trails.osm_route r
            cross join lateral unnest(r.way_ids) with ordinality as m(osm_id, n)
            left join (select distinct on (osm_id) osm_id, geom from ({ways}) u order by osm_id) w
              on w.osm_id = m.osm_id
            where r.active
            group by r.osm_id, r.way_ids""", (now,))
    return conn.execute("select count(*), count(geom) from trails.route_line").fetchone()


def network(conn, now):
    """Rewrite trails.path_lo, the valley-zoom network (z10-12): the drawn ways with minzoom 10,
    simplified. Agency lines that draw themselves are in trails.agency_line, not here. Doesn't
    commit."""
    conn.execute("delete from trails.path_lo")
    conn.execute(
        f"""insert into trails.path_lo (fid, network, kind, name, surface, geom, built_at)
            select p.osm_id,
                   case when p.r2r then 'r2r' when p.greenbelt then 'greenbelt'
                        when p.kind = 'cycleway' then 'cycleway' else 'named' end,
                   p.kind, p.name, p.surface,
                   ST_Transform(ST_SimplifyPreserveTopology(ST_Transform(p.geom, {UTM}), %s), 4326), %s
            from trails.path p
            where p.drawn and p.minzoom <= 12""", (LO_TOLERANCE_M, now))
    return conn.execute("select count(*) from trails.path_lo").fetchone()[0]


# ---- the build ----------------------------------------------------------------------------------

def build(conn, now, out=print):
    """Everything the build does, in one transaction, without committing: the canal-bank rule,
    every line relinked, the route lines, the valley-zoom network and the tiles' versions.
    Returns (stats, a note for its run)."""
    md5 = osm_md5(conn)
    if md5 is None:
        raise RuntimeError(f"{OSM_CONSUMER} hasn't loaded an extract: load it first "
                           "(python3 -m ingest osm-load --only osm_paths)")
    key = conn.execute(LINKS_LOCK).fetchone()[0]
    conn.execute("select pg_advisory_xact_lock(%s)", (key,))     # waits for a poll's relink (seconds)
    canal = canal_tracks(conn, now)
    if canal is None:
        out("canal-bank rule: skipped (water's reaches, water.reach, aren't built yet)")
    keys = current_lines(conn)
    _, gone = pending(conn)
    stats = relink(conn, keys, gone, md5, now, BUILD)
    routes, drawn = route_lines(conn, now)
    lo = network(conn, now)
    paths = conn.execute("select count(*) from trails.path where drawn").fetchone()[0]
    agency = conn.execute("select count(*) from trails.agency_gap").fetchone()[0]
    versions = record_versions(conn, LAYERS, BUILD, {"trails.paths": paths, "trails.routes": drawn,
                                                     "trails.agency": agency})
    stats.update({"canal tracks": "skipped" if canal is None else canal, "routes": routes, "routes drawn": drawn,
                  "valley-zoom ways": lo, "ways drawn": paths, "lines drawing a gap": agency,
                  "extract": md5[:8], **{f"version {k}": v for k, v in versions.items()}})
    note = (f"{stats['links']} links for {stats['matched lines']} of {stats['lines']} lines; {routes} routes; "
            f"extract {md5[:8]}")
    return stats, note


def summary(conn, out=print):
    """Each source's lines, linked or not, how much lies along the ways they're on, and how much
    draws itself, after a build."""
    for source, lines, linked, covered, gap, length in conn.execute(
            """select source, count(*), count(*) filter (where links > 0), sum(coalesce(covered_m, 0)),
                      sum(gap_m), sum(coalesce(line_m, 0))
               from trails.matched_line group by 1 order by 1""").fetchall():
        share = (lambda v: f"{v / length:.1%}" if length else "-")
        out(f"  {source}: {linked} of {lines} lines linked; {share(covered)} of their length along the ways they're "
            f"on, {share(gap)} drawn as themselves ({length / 1000:.0f} km)")


def main(argv=None):
    """`python3 -m ingest trails-match` (registered in ../plugin.json)."""
    ap = argparse.ArgumentParser(prog="python3 -m ingest trails-match", description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="build and report, then roll back")
    args = ap.parse_args(argv)
    with db.connect() as conn:
        if not ready(conn):
            sys.exit("trails 0001 isn't applied (python3 db/migrate.py)")
        if args.dry_run:
            stats, _ = build(conn, db.now())
            print("trails-match: " + ", ".join(f"{k} {v}" for k, v in stats.items()), flush=True)
            summary(conn)
            conn.rollback()
            print("(dry run: nothing written)", flush=True)
            return 0
        with builds.Run(conn, BUILD) as run:
            stats, run.note = build(conn, db.now())
        print("trails-match: " + ", ".join(f"{k} {v}" for k, v in stats.items()), flush=True)
        summary(conn)
    return 0
