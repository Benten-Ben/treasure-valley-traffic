"""trails-match: Ridge to Rivers' trails and the Greenbelt's closures and detours, linked onto
OpenStreetMap's paths (landscape sprint, plan C18, package P6-data).

    python3 -m ingest trails-match              # the build: every agency line, routes, the network
    python3 -m ingest trails-match --dry-run    # the same, reported, then rolled back

OpenStreetMap draws the network (trails.osm_path, and the named exception's
ways in core.osm_way); the City of Boise's lines carry the status. Each agency
line (an R2R trail from raw.record, a Greenbelt closure or detour) is matched
to the ways it lies along with core's line matcher (ingest/linematch.py):
buffer 15 m, bearing within 20°, at least 60% of the way within the line's
buffer, or of the line (20 m or more) within the way's. Closed lines (park
loops) are measured by their quarters (the matcher's `loops`, on). Only public
ways are targets: a way closed to the public, or a track taken as canal
access, is never a trail, and an R2R trail on one draws from its own line. A
line no way matches draws from its own line too. Measured before the build
(Oct 8, design): 88.5% of R2R's length lies within 15 m of an OSM path or
track, and most of the rest is R2R's "Access Road", which OSM maps as roads.

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
RULE = linematch.Rule(near_m=15, check="bearing")          # loops on: park and pond loops match
CANAL_RULE = linematch.Rule(near_m=15, check="bearing")
CANAL_KINDS = ("canal", "lateral", "ditch", "drain")
NEAR_DEG = 0.0005             # a way within this many degrees (40-55 m here) of a line is a candidate
POLL_MAX_LINES = 40           # more changed lines than this in one poll: left for the build
LO_TOLERANCE_M = 5.0          # the valley-zoom network's simplification (UTM metres)
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
LINES_SQL = """select l.source, l.source_id, l.name, l.geom from trails.agency_line l
               join pg_temp.tm_key k on k.source = l.source and k.source_id = l.source_id"""
TARGETS_SQL = """select t.osm_id as id, t.name, t.geom from trails.target_way t
                 where exists (select 1 from pg_temp.tm_box b where t.geom && b.box)"""


def _stage_keys(conn, keys):
    conn.execute(_KEYS)
    with conn.cursor() as cur:
        with cur.copy("copy tm_key (source, source_id) from stdin") as cp:
            for k in keys:
                cp.write_row(k)
    conn.execute("drop table if exists pg_temp.tm_box")
    conn.execute(
        """create temp table tm_box on commit drop as
           select ST_Expand(ST_Envelope(l.geom), %s) as box from trails.agency_line l
           join tm_key k on k.source = l.source and k.source_id = l.source_id where l.geom is not null""",
        (NEAR_DEG,))


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
    matches = linematch.match(conn, LINES_SQL, TARGETS_SQL, RULE)
    cover = linematch.coverage(conn, matches)
    conn.execute("""delete from trails.link k using tm_key t
                    where k.source = t.source and k.source_id = t.source_id""")
    with conn.cursor() as cur:
        cur.executemany(
            """insert into trails.link (source, source_id, osm_id, overlap_m, share, line_share, bearing_diff,
                                        confidence, method, matched_at)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [(m["source"], m["source_id"], m["target_id"], round(m["overlap_m"], 1), round(m["share"], 3),
              None if m["line_share"] is None else round(m["line_share"], 3), m["bearing_diff"], m["confidence"],
              m["method"], now) for m in matches])
    # Each line's match: how much of it lies within 15 m of the ways it linked to.
    conn.execute(
        f"""insert into trails.matched_line (source, source_id, line_fp, osm_md5, line_m, covered_m, links,
                                             matched_at, matched_by, fetch_id)
            select t.source, t.source_id, l.line_fp, %(md5)s,
                   ST_Length(l.geom::geography),
                   (select ST_Length(ST_Intersection(ST_Transform(l.geom, {UTM}),
                                                     ST_Buffer(ST_Collect(ST_Transform(w.geom, {UTM})), %(near)s)))
                    from trails.link k join trails.any_way w on w.osm_id = k.osm_id
                    where k.source = t.source and k.source_id = t.source_id),
                   (select count(*) from trails.link k where k.source = t.source and k.source_id = t.source_id),
                   %(now)s, %(by)s, %(fetch)s
            from tm_key t join trails.agency_line l on l.source = t.source and l.source_id = t.source_id
            on conflict (source, source_id) do update set
              line_fp = excluded.line_fp, osm_md5 = excluded.osm_md5, line_m = excluded.line_m,
              covered_m = excluded.covered_m, links = excluded.links, matched_at = excluded.matched_at,
              matched_by = excluded.matched_by, fetch_id = excluded.fetch_id""",
        {"md5": md5, "near": RULE.near_m, "now": now, "by": matched_by, "fetch": fetch_id})
    stats["links"] = len(matches)
    stats["matched lines"] = len({(m["source"], m["source_id"]) for m in matches})
    for source, c in cover.items():
        stats[f"{source}: unmatched near the paths"] = c["unmatched near"]
        stats[f"{source}: unmatched away from them"] = c["unmatched away"]
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
    """Rewrite trails.canal_track: the tracks along a canal bank. Returns its count, or None when
    water's reaches don't exist yet (the rule is skipped). Doesn't commit."""
    reaches_sql = reaches_sql or canal_reaches_sql(conn)
    if reaches_sql is None:
        return None
    matches = linematch.match(conn, TRACKS_SQL.format(reaches=reaches_sql, near=NEAR_DEG), reaches_sql, CANAL_RULE)
    best = {}
    for m in matches:                                      # each track's best reach: the most of it along one
        share = m["line_share"] if m["line_share"] is not None else 1.0
        if share >= best.get(m["source_id"], (-1,))[0]:
            best[m["source_id"]] = (share, m)
    conn.execute("delete from trails.canal_track")
    with conn.cursor() as cur:
        cur.executemany(
            "insert into trails.canal_track (osm_id, reach_id, line_share, bearing_diff, built_at) "
            "values (%s, %s, %s, %s, %s)",
            [(int(k), str(m["target_id"]), round(share, 3), m["bearing_diff"], now)
             for k, (share, m) in best.items()])
    return len(best)


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
    agency = conn.execute("select count(*) from trails.agency_state where coalesce(links, 0) = 0").fetchone()[0]
    versions = record_versions(conn, LAYERS, BUILD, {"trails.paths": paths, "trails.routes": drawn,
                                                     "trails.agency": agency})
    stats.update({"canal tracks": "skipped" if canal is None else canal, "routes": routes, "routes drawn": drawn,
                  "valley-zoom ways": lo, "ways drawn": paths, "lines drawn as themselves": agency,
                  "extract": md5[:8], **{f"version {k}": v for k, v in versions.items()}})
    note = (f"{stats['links']} links for {stats['matched lines']} of {stats['lines']} lines; {routes} routes; "
            f"extract {md5[:8]}")
    return stats, note


def summary(conn, out=print):
    """Each source's lines, linked or not, and their coverage, after a build."""
    for source, lines, linked, covered, length in conn.execute(
            """select source, count(*), count(*) filter (where links > 0),
                      sum(coalesce(covered_m, 0)), sum(coalesce(line_m, 0))
               from trails.matched_line group by 1 order by 1""").fetchall():
        share = f"{covered / length:.1%}" if length else "-"
        out(f"  {source}: {linked} of {lines} lines linked; {share} of their length within 15 m of a linked way")


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
