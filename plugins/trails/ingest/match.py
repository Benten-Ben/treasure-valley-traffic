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
matched it; **partly** (method way_in_...) when only 20 m or more does.

A way **paints** (takes the line's state, as feature-state on the whole way)
only on a full link with less than MIN_GAP_M (20 m) of it farther than 15 m
from the line. Of every other way it's linked to (one longer than the line, or
running on past it), the stretch along the line is drawn in the line's state
(its `along`: OpenStreetMap's geometry, cut to the line). Wherever neither
shows it, the line draws itself (its `gap`: stretches of 20 m or more). So
every metre of the line shows its state, and no way shows it more than 20 m
beyond the line. Only public, official ways are targets: a way closed to the
public, an informal one, or a track taken as canal access is never a trail, so
an agency's line on one draws itself.

Why pieces (measured on scratch, Oct 11, the Oct 5 extract): matched whole, a
long winding trail fails the bearing check against a long winding OSM way that
lies right along it, since the check compares end-to-end chords (Freddys Stack
Rock Trail, 4.8 km, with an OSM path within 15 m for 4.6 km, had no link).
Whole, R2R's multi-use trails were linked along 308 of their 353 km; in pieces
of 150 m, 320 km. Most of the rest is R2R's "Access Road" (50 km), which OSM
maps as roads, so it draws itself.

Two ways it runs (plan P6-data; docs/15 "Builds and their marks"):

* **After a poll** (`after_poll`, called by r2r_trails and
  boise_greenbelt_closures once their data is committed): when the poll
  stored new or removed versions, the lines whose geometry changed (their
  fingerprint) are relinked, lines never linked first, at most POLL_MAX_LINES
  of them; the build is marked for any more. It runs in its own try block with
  its own ops.fetch row (source trails_match), so a match that fails never
  fails the poll: the failure is logged there, and the build is marked. It
  runs inside `ingest serve`, an exception to plan item 27 that P6-data's row
  asks for (a closure the City posts shows within the hour); so that it can
  never hold up the sources after it, each statement stops after
  STATEMENT_TIMEOUT_S and the relink after BUDGET_S, the work then left for the
  build (marked). The build running at the time also leaves it to the build.
* **The build** (`trails-match`, by hand, logged in ops.build_run): after a
  new extract (osm_paths' load marks it), a new water build (canal tracks), or
  when marked. Every current line is relinked against the extract osm_paths
  holds; then the canal-bank rule (once water's reaches exist), each route's
  line, and the network at valley zoom.

Licences (plan C3). The Trails layer's ways (trails.path, the 'trails.paths'
tiles) and the valley-zoom network (trails.path_lo) are OpenStreetMap's alone,
so republish yes: what the City's lines say of a way reaches the map only as
feature-state (/api/trails/status), and nothing here changes those tiles but
the build (canal tracks, routes). What the lines draw themselves (their along
and gap from z13, their whole lines at z10-12) is the 'trails.agency' tile set:
the City's lines with OpenStreetMap's ways cut to them, republish aggregates.
A relink after a poll gives only that set a new version.

The canal-bank rule (plan C18, cut-first): a track lying along a canal,
lateral, ditch or drain of water's build (water.reach, not piped) for at least
60% of its length, within 15 m and within 20°, and not tagged access=yes or
permissive, is irrigation access, not a trail (trails.canal_track, with the
water build it came from). It needs water's build, so until water.reach exists
it's skipped, said so, and any earlier result cleared.
"""

import argparse
import sys
import time

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
POLL_MAX_LINES = 40           # a poll relinks this many changed lines at most; the build the rest (marked)
STATEMENT_TIMEOUT_S = 20      # each statement of a relink after a poll (serve runs every source in turn)
BUDGET_S = 60                 # a relink after a poll stops after this; the build is marked instead
LO_TOLERANCE_M = 5.0          # the valley-zoom network's simplification (UTM metres)
MIN_GAP_M = 20.0              # a stretch shorter than this isn't drawn on its own, nor a way's part off its line
UTM = linematch.SRID

CITY_CREDIT = "City of Boise Parks & Recreation (Ridge to Rivers); City of Boise Parks and Recreation"
CITY_LICENSE = "none stated (City of Boise disclaimer only)"
OSM_CREDIT = "© OpenStreetMap contributors"
# The Trails layer's tile sets (core.layer_version), as the trails layer's tile definitions name them
# (plan C3: each takes the strictest of its inputs). 'trails.paths' (trails.path) and the network at
# valley zoom (trails.path_lo) are OpenStreetMap's alone; 'trails.agency' (trails.agency_drawn and
# trails.agency_lo) is the City's lines, with OpenStreetMap's ways cut to them.
LAYERS = {
    "trails.paths": {"license": "ODbL", "republish": "yes", "credit": OSM_CREDIT},
    "trails.routes": {"license": "ODbL", "republish": "yes", "credit": OSM_CREDIT},
    "trails.agency": {"license": f"{CITY_LICENSE} + ODbL", "republish": "aggregates",
                      "credit": f"{CITY_CREDIT}; {OSM_CREDIT}"},
}


class OutOfTime(RuntimeError):
    """A relink after a poll went past its budget (BUDGET_S); the build is marked instead."""


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
    since, as [(source, source_id)], those never matched first; matched lines no longer current)."""
    todo = conn.execute(
        """select l.source, l.source_id from trails.agency_line l
           left join trails.matched_line m on m.source = l.source and m.source_id = l.source_id
           where l.source = any(%s) and (m.source is null or m.line_fp is distinct from l.line_fp)
           order by m.source is not null, 1, 2""", (list(sources),)).fetchall()
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


# ---- relinking ----------------------------------------------------------------------------------

_KEYS = """create temp table if not exists tm_key (source text, source_id text) on commit drop;
           truncate tm_key"""
# The lines to relink, read once (one snapshot of the City's rows for the whole relink): what
# matched_line keeps of each, and the line and its 15 m buffer in UTM.
_LINE = f"""create temp table tm_line on commit drop as
  select l.source, l.source_id, l.kind, l.name, l.line_fp, l.geom, u.lg,
         ST_Buffer(u.lg, %(near)s, 'quad_segs=4') as buf
  from trails.agency_line l
  join tm_key t on t.source = l.source and t.source_id = l.source_id
  cross join lateral (select ST_Transform(l.geom, {UTM}) as lg) u"""
# Each line in pieces of at most PIECE_M (each part cut into equal pieces), in UTM.
_PIECES = """create temp table tm_piece on commit drop as
  select l.source, l.source_id, l.source_id || '#' || coalesce(d.path[1], 1) || '.' || i as piece_id, l.name,
         ST_LineSubstring(d.geom, i::float8 / kk.k, (i + 1)::float8 / kk.k) as g
  from tm_line l
  cross join lateral ST_Dump(l.lg) d
  cross join lateral (select greatest(1, ceil(ST_Length(d.geom) / %(piece)s))::int as k) kk
  cross join lateral generate_series(0, kk.k - 1) i
  where l.lg is not null and ST_Length(d.geom) > 0"""
LINES_SQL = "select source, piece_id as source_id, name, ST_Transform(g, 4326) as geom from pg_temp.tm_piece"
TARGETS_SQL = """select t.osm_id as id, t.name, t.geom from trails.target_way t
                 where exists (select 1 from pg_temp.tm_box b where t.geom && b.box)"""
# Each (line, way): the stretch of the way within 15 m of the line's pieces that matched it (along),
# how much of the way lies farther than 15 m from the whole line (off_m), and how much of the line
# those pieces are.
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
         ST_Intersection(w.g, a.buf) as along_g, ST_Length(w.g) as way_m,
         ST_Length(ST_Difference(w.g, l.buf)) as off_m,
         (select sum(ST_Length(p.g)) from tm_piece p where p.source = a.source and p.source_id = a.source_id) as line_m
  from agg a
  join tm_line l on l.source = a.source and l.source_id = a.source_id
  join (select osm_id, ST_Transform(geom, {UTM}) as g from trails.any_way) w on w.osm_id = a.osm_id"""
# The stretches of the ways a line is linked to but doesn't paint that lie along it: 20 m or more.
_ALONG = """create temp table tm_along on commit drop as
  select x.source, x.source_id, x.osm_id, d.geom
  from tm_link x
  join trails.link k on k.source = x.source and k.source_id = x.source_id and k.osm_id = x.osm_id and not k.paints
  cross join lateral ST_Dump(ST_LineMerge(ST_CollectionExtract(x.along_g, 2))) d
  where ST_Length(d.geom) >= %(min_gap)s"""
# Each line's match: what shows it (the ways it paints, and its along), how much of it lies within
# 15 m of those, its gap (the rest, in stretches of MIN_GAP_M or more) and its line at valley zoom.
_MATCHED = f"""insert into trails.matched_line (source, source_id, kind, name, line_fp, osm_md5, line_m, covered_m,
                                     along, along_m, gap, gap_m, line_lo, links, matched_at, matched_by, fetch_id)
  select t.source, t.source_id, t.kind, t.name, t.line_fp, %(md5)s, ST_Length(t.geom::geography), c.covered_m,
         a.along, coalesce(ST_Length(a.along::geography), 0), g.gap, coalesce(ST_Length(g.gap::geography), 0),
         ST_Transform(ST_Multi(ST_SimplifyPreserveTopology(t.lg, %(lo)s)), 4326), n.links,
         %(now)s, %(by)s, %(fetch)s
  from tm_line t
  cross join lateral (
    select ST_Buffer(ST_Collect(s.g), %(near)s) as buf from (
      select ST_Transform(w.geom, {UTM}) as g
      from trails.link k join trails.any_way w on w.osm_id = k.osm_id
      where k.source = t.source and k.source_id = t.source_id and k.paints
      union all
      select d.geom from tm_along d where d.source = t.source and d.source_id = t.source_id) s) b
  cross join lateral (
    select ST_Transform(ST_Multi(ST_Collect(d.geom order by d.osm_id)), 4326) as along
    from tm_along d where d.source = t.source and d.source_id = t.source_id) a
  cross join lateral (
    select case when b.buf is not null then ST_Length(ST_Intersection(t.lg, b.buf)) end as covered_m) c
  cross join lateral (
    select ST_Transform(ST_Multi(ST_Collect(d.geom order by d.path)), 4326) as gap
    from ST_Dump(ST_LineMerge(ST_CollectionExtract(
           case when b.buf is null then t.lg else ST_Difference(t.lg, b.buf) end, 2))) d
    where ST_Length(d.geom) >= %(min_gap)s) g
  cross join lateral (
    select count(*) as links from trails.link k where k.source = t.source and k.source_id = t.source_id) n
  on conflict (source, source_id) do update set
    kind = excluded.kind, name = excluded.name, line_fp = excluded.line_fp, osm_md5 = excluded.osm_md5,
    line_m = excluded.line_m, covered_m = excluded.covered_m, along = excluded.along, along_m = excluded.along_m,
    gap = excluded.gap, gap_m = excluded.gap_m, line_lo = excluded.line_lo, links = excluded.links,
    matched_at = excluded.matched_at, matched_by = excluded.matched_by, fetch_id = excluded.fetch_id"""


def _in_time(deadline):
    if deadline is not None and time.monotonic() > deadline:
        raise OutOfTime(f"the relink went past its {BUDGET_S} s budget")


def _stage_keys(conn, keys):
    conn.execute(_KEYS)
    with conn.cursor() as cur:
        with cur.copy("copy tm_key (source, source_id) from stdin") as cp:
            for k in keys:
                cp.write_row(k)
    for table in ("tm_line", "tm_box", "tm_piece", "tm_pm", "tm_link", "tm_along"):
        conn.execute(f"drop table if exists pg_temp.{table}")
    conn.execute(_LINE, {"near": RULE.near_m})
    conn.execute(_PIECES, {"piece": PIECE_M})
    conn.execute("create temp table tm_box on commit drop as "
                 "select ST_Expand(ST_Envelope(geom), %s) as box from tm_line where geom is not null", (NEAR_DEG,))


def link_rows(conn, matches):
    """The links from the pieces' matches: [(source, source_id, osm_id, overlap_m, off_m, share,
    line_share, bearing_diff, confidence, method, paints)]. A way is fully linked when
    RULE.min_share of it lies along pieces that matched it, otherwise partly (way_in_...) when 20 m
    or more of it does; it paints when it's fully linked and less than MIN_GAP_M of it lies
    farther than 15 m from the line."""
    conn.execute("create temp table tm_pm (piece_id text, osm_id bigint, bearing_diff real, confidence real) "
                 "on commit drop")
    with conn.cursor() as cur:
        with cur.copy("copy tm_pm (piece_id, osm_id, bearing_diff, confidence) from stdin") as cp:
            for m in matches:
                cp.write_row((m["source_id"], m["target_id"], m["bearing_diff"], m["confidence"]))
    conn.execute(_LINKS, {"near": RULE.near_m})
    out = []
    for source, source_id, osm_id, pieces_m, bearing, confidence, overlap, off, way_m, line_m in conn.execute(
            "select source, source_id, osm_id, pieces_m, bearing_diff, confidence, ST_Length(along_g), off_m, "
            "way_m, line_m from tm_link order by 1, 2, 3").fetchall():
        share = overlap / way_m if way_m else 0.0
        line_share = min(pieces_m / line_m, 1.0) if line_m else None
        if share >= RULE.min_share:
            method, scale = METHOD, min(share, 1.0)
        elif overlap >= RULE.min_line_m:
            method, scale = linematch.WAY_IN + METHOD, (line_share or 0.0)
        else:
            continue
        paints = method == METHOD and off < MIN_GAP_M
        out.append((source, source_id, osm_id, round(overlap, 1), round(off, 1), round(share, 3),
                    None if line_share is None else round(line_share, 3), round(bearing, 1),
                    round(max(0.0, min(1.0, confidence * scale)), 3), method, paints))
    return out


def relink(conn, keys, gone, md5, now, matched_by, fetch_id=None, deadline=None):
    """Replace the links of the lines in keys ([(source, source_id)]) with fresh matches against the
    ways osm_paths holds now, and forget the lines in gone. Past deadline (time.monotonic()), it
    stops with OutOfTime. Doesn't commit. Returns stats."""
    keys, gone = list(keys), list(gone)
    for source, source_id in gone:
        conn.execute("delete from trails.link where source = %s and source_id = %s", (source, source_id))
        conn.execute("delete from trails.matched_line where source = %s and source_id = %s", (source, source_id))
    stats = {"lines": len(keys), "gone": len(gone), "links": 0, "matched lines": 0}
    if not keys:
        return stats
    _stage_keys(conn, keys)
    _in_time(deadline)
    matches = linematch.match(conn, LINES_SQL, TARGETS_SQL, RULE)
    _in_time(deadline)
    rows = link_rows(conn, matches)
    _in_time(deadline)
    conn.execute("""delete from trails.link k using tm_key t
                    where k.source = t.source and k.source_id = t.source_id""")
    with conn.cursor() as cur:
        cur.executemany(
            """insert into trails.link (source, source_id, osm_id, overlap_m, off_m, share, line_share, bearing_diff,
                                        confidence, method, paints, matched_at)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", [(*r, now) for r in rows])
    conn.execute(_ALONG, {"min_gap": MIN_GAP_M})
    _in_time(deadline)
    conn.execute(_MATCHED, {"md5": md5, "near": RULE.near_m, "min_gap": MIN_GAP_M, "lo": LO_TOLERANCE_M,
                            "now": now, "by": matched_by, "fetch": fetch_id})
    paints = sum(1 for r in rows if r[10])
    stats.update({"links": len(rows), "painting": paints, "not painting": len(rows) - paints,
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
    the poll stored new or removed versions; nothing happens otherwise. A failure (an error, a
    statement past STATEMENT_TIMEOUT_S, the relink past BUDGET_S) is logged in ops.fetch (source
    trails_match), marks the build, and is reported in the poll's stats: it never fails the poll,
    even when the connection is gone. Returns stats for the poll's line ({} when there was nothing
    to do)."""
    if not changed:
        return {}
    try:
        return _after_poll(conn, source)
    except Exception as err:
        marked = False
        try:
            conn.rollback()
            builds.mark(conn, BUILD, by=source, reason=f"relinking after {source}'s poll failed: "
                                                       f"{type(err).__name__}: {err}")
            conn.commit()
            marked = True
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass                          # the connection is gone: serve opens a new one
        return {"links": f"failed ({type(err).__name__}), logged in ops.fetch as {SOURCE['name']}; "
                         + (f"{BUILD} is marked" if marked else f"{BUILD} couldn't be marked")}


def _limit(conn):
    """The statement limit for this transaction (production's login has none)."""
    conn.execute(f"set local statement_timeout = {int(STATEMENT_TIMEOUT_S * 1000)}")


def _after_poll(conn, source):
    deadline = time.monotonic() + BUDGET_S
    _limit(conn)
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
    key = conn.execute(LINKS_LOCK).fetchone()[0]
    if not conn.execute("select pg_try_advisory_lock(%s)", (key,)).fetchone()[0]:
        builds.mark(conn, BUILD, by=source, reason=f"{len(todo)} of {source}'s lines changed while it ran")
        conn.commit()
        return {"links": f"{BUILD} is running: {len(todo)} lines left for its next run (marked)"}
    try:                                      # a session lock: Fetch's commits don't end it
        conn.commit()
        db.ensure_source(conn, SOURCE)
        with db.Fetch(conn, SOURCE["name"]) as f:
            _limit(conn)
            todo, gone = pending(conn, [source])          # again, now that nothing else relinks
            now, later = todo[:POLL_MAX_LINES], todo[POLL_MAX_LINES:]   # lines never linked come first
            stats = relink(conn, now, gone, md5, f.started_at, "poll", f.id, deadline=deadline)
            f.records = stats["links"]
            if later:
                builds.mark(conn, BUILD, by=source, reason=f"{len(todo)} of {source}'s lines changed: "
                                                           f"{len(later)} more than a poll relinks")
            versions = record_versions(conn, ("trails.agency",), f"{SOURCE['name']} after {source}")
    finally:
        try:
            conn.rollback()
            conn.execute("select pg_advisory_unlock(%s)", (key,))
            conn.commit()
        except Exception:
            pass                              # the lock goes with the connection
    out = {"links": f"{stats['links']} for {stats['lines']} changed lines ({stats['gone']} gone)",
           "tiles": versions["trails.agency"]}
    if later:
        out["links"] += f"; {len(later)} more left for {BUILD} (marked)"
    return out


# ---- the canal-bank rule (cut-first) --------------------------------------------------------------

def _reach_columns(conn):
    return {r[0] for r in conn.execute(
        """select column_name from information_schema.columns
           where table_schema = 'water' and table_name = 'reach'""").fetchall()}


def canal_reaches_sql(conn):
    """The SQL of water's canal reaches, or None until water's build (water.reach) exists."""
    if not conn.execute("select to_regclass('water.reach') is not null").fetchone()[0]:
        return None
    cols = _reach_columns(conn)
    if not {"id", "kind", "geom"} <= cols:
        return None
    piped = " and not piped" if "piped" in cols else ""
    return (f"select id::text as id, name, geom from water.reach "
            f"where kind in ({', '.join(repr(k) for k in CANAL_KINDS)}){piped}")


def water_build(conn):
    """The water build whose reaches are in water.reach (its build_id), or None."""
    if not conn.execute("select to_regclass('water.reach') is not null").fetchone()[0] \
            or "build_id" not in _reach_columns(conn):
        return None
    return conn.execute("select max(build_id) from water.reach").fetchone()[0]


TRACKS_SQL = """select 'osm_paths' as source, w.osm_id::text as source_id, w.name, w.geom
                from trails.any_way w
                where w.kind = 'track' and not w.no_access
                  and coalesce(lower(btrim(w.tags->>'access')), '') not in ('yes', 'permissive')
                  and exists (select 1 from ({reaches}) r where ST_DWithin(w.geom, r.geom, {near}))"""


def canal_tracks(conn, now, reaches_sql=None, build_id=None):
    """Rewrite trails.canal_track: the tracks along a canal bank, where 60% or more of the track
    lies within 15 m of canal reaches that match it (core's matcher: either one's share, and the
    bearing). The reach recorded is the one most of the track lies along, with the water build it
    came from (build_id; by default water.reach's). Returns the count, or None when water's reaches
    don't exist (the rule is skipped, and any earlier result cleared). Doesn't commit."""
    if reaches_sql is None:
        reaches_sql, build_id = canal_reaches_sql(conn), water_build(conn)
    conn.execute("delete from trails.canal_track")
    if reaches_sql is None:
        return None
    matches = linematch.match(conn, TRACKS_SQL.format(reaches=reaches_sql, near=NEAR_DEG), reaches_sql, CANAL_RULE)
    conn.execute("drop table if exists pg_temp.tm_cm")
    conn.execute("create temp table tm_cm (osm_id bigint, reach_id text, bearing_diff real) on commit drop")
    with conn.cursor() as cur:
        with cur.copy("copy tm_cm (osm_id, reach_id, bearing_diff) from stdin") as cp:
            for m in matches:
                cp.write_row((int(m["source_id"]), str(m["target_id"]), m["bearing_diff"]))
    return conn.execute(
        f"""insert into trails.canal_track (osm_id, reach_id, line_share, bearing_diff, water_build, built_at)
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
            select osm_id, reach_id, round(share::numeric, 3), round(bearing_diff::numeric, 1), %(build)s, %(now)s
            from track where share >= %(share)s""",
        {"near": CANAL_RULE.near_m, "now": now, "share": CANAL_RULE.min_share, "build": build_id}).rowcount


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
    """Rewrite trails.path_lo, the valley-zoom network (z10-12): the drawn ways with minzoom 10
    (OpenStreetMap's alone: the Greenbelt's route, cycleways, named paths), simplified. The
    agencies' lines at these zooms are trails.agency_lo. Doesn't commit."""
    conn.execute("delete from trails.path_lo")
    conn.execute(
        f"""insert into trails.path_lo (fid, network, kind, name, surface, geom, built_at)
            select p.osm_id,
                   case when p.greenbelt then 'greenbelt' when p.kind = 'cycleway' then 'cycleway' else 'named' end,
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
    water = water_build(conn)
    canal = canal_tracks(conn, now)
    if canal is None:
        out("canal-bank rule: skipped (water's reaches, water.reach, aren't built yet)")
    else:
        out(f"canal-bank rule: {canal} tracks along canals" + (f", from water build {water}" if water else ""))
    keys = current_lines(conn)
    _, gone = pending(conn)
    stats = relink(conn, keys, gone, md5, now, BUILD)
    routes, drawn = route_lines(conn, now)
    lo = network(conn, now)
    paths = conn.execute("select count(*) from trails.path where drawn").fetchone()[0]
    agency = conn.execute("select count(*) from trails.agency_drawn").fetchone()[0] \
        + conn.execute("select count(*) from trails.agency_lo").fetchone()[0]
    versions = record_versions(conn, LAYERS, BUILD, {"trails.paths": paths, "trails.routes": drawn,
                                                     "trails.agency": agency})
    stats.update({"canal tracks": "skipped" if canal is None else canal, "water build": water, "routes": routes,
                  "routes drawn": drawn, "valley-zoom ways": lo, "ways drawn": paths, "agency features": agency,
                  "extract": md5[:8], **{f"version {k}": v for k, v in versions.items()}})
    note = (f"{stats['links']} links for {stats['matched lines']} of {stats['lines']} lines; {routes} routes; "
            f"extract {md5[:8]}" + (f"; canal tracks from water build {water}" if canal is not None and water else ""))
    return stats, note


def summary(conn, out=print):
    """Each source's lines, linked or not, how much of their length the ways they paint show, how
    much the ways they don't paint, and how much draws itself, after a build."""
    for source, lines, linked, covered, along, gap, length in conn.execute(
            """select source, count(*), count(*) filter (where links > 0), sum(coalesce(covered_m, 0)),
                      sum(along_m), sum(gap_m), sum(coalesce(line_m, 0))
               from trails.matched_line group by 1 order by 1""").fetchall():
        share = (lambda v: f"{v / length:.1%}" if length else "-")
        out(f"  {source}: {linked} of {lines} lines linked; {share(covered)} of their length shown on the ways "
            f"(of which {share(along)} on stretches of ways they don't paint), {share(gap)} drawn as themselves "
            f"({length / 1000:.0f} km)")


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
