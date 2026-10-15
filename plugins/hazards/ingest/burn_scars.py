"""Burn scars (landscape sprint, Oct 2026: plan C15 and §3.4 K10, package P13; decision 25):
`python3 -m ingest burn-scars`.

Fires that burned after the ground's photo are drawn on the painted ground, in Valley only, in a neutral char
tone with a stipple (never red), fading over three growing seasons. They aren't clickable in v1. This module
keeps hazards.burn_scar (hazards/0001) in step with the WFIGS perimeters the poller stores in raw.record
(source nifc_wfigs_perimeters). It fetches nothing.

It's a build, `burn-scars`, and like every build it never runs inside `ingest serve` (plan §0 item 27, M1):
sources mark it, and it runs by hand. The perimeter poller marks it, in the same transaction as its data
(`mark`), when it stores new perimeter versions, and when a held scar's fade step has come since the last build
(a count on this small table; no GEOS); the backfill's load marks it too. `python3 -m ingest.builds` and the VM's
bin/status show it marked, and `python3 -m ingest burn-scars` runs it inside builds.Run, which logs the run in
ops.build_run (its note says what changed and names any fire left out) and clears the marks it saw. It's light:
about a hundred record versions in, a few dozen rows out, about 2 s when nothing changed and 4 s to rewrite every
scar. Each statement has a limit (STATEMENT_TIMEOUT_S; production's login has none), and the writes stop after
BUDGET_S, the build marking itself again for the rest.

Rules, per fire (one source_id in raw.record):

1. **Which version:** the newest final perimeter if the fire has one, else its newest version (newest: last
   seen, then first seen). A final perimeter outranks a later daily one, as in the poller's own reads. A fire
   with no final perimeter yet is drawn from its newest daily one (C15 says "final perimeters"; a rule for the
   owner to confirm).
2. **Whether it's drawn:** that version still stands (nifc_wfigs_perimeters.is_valid: not withdrawn as
   invalid, deleted or hidden), it's a wildfire (WF) or a prescribed fire (RX), it reaches into the map box, and
   the fire came after the photo. Complexes (CX) are left out, on the assumption that their member fires carry
   their own perimeters, so a complex's outline over them would draw the char twice ⚠️ (not yet checked against
   WFIGS; no complex is held as of Oct 11, 2026).
3. **After the photo:** the ground paints NAIP 2025, flown in the box from May 25 to Jul 24, 2025 (docs/09), so
   a fire counts from Jul 25, 2025 (after PHOTO_LAST_DAY). Its day is its discovery day in Boise
   (attr_FireDiscoveryDateTime), else its perimeter's own day (`dated_by` says which).
4. **The fade:** a scar steps down the day after each of the first three whole growing seasons that begin
   after its fire (growing_season.json, read by core's ingest/seasons.py: April through October, an estimate
   ⚠️). A season the fire burned in doesn't count, even on its first day: a fire on Mar 31 first steps down
   seven months later, one on Apr 1 nineteen months later. Its fade is 1 until then, then 2/3, 1/3, and 0
   (gone). `seasons` (0-3) and `fade` are as of the build's day in Boise, and the three step days are stored with
   them; a step's day marks the build, so a scar steps down when the build next runs.
5. **Geometry:** made valid and cut to the map box, the ground's extent (`clipped` says when it was cut), plus a
   copy simplified at 10 m for low zooms. Acres stay the whole fire's, as published. Each fire's geometry is
   worked in a savepoint of its own: one that PostGIS can't make usable (nothing left once made valid, or GEOS
   throws, or it runs out of time) is left out and named in the run's output and note, and is tried again on the
   next run; the rest of the layer goes on. A fire already drawn keeps its last good scar, still stepping down
   on its stored days.

A refresh rewrites only rows whose content changed (content_hash), deletes fires that no longer qualify, and,
when anything changed or the layer has no version yet, records a new version of the tile layer
'hazards.burn_scars' (core.layer_version), in the same transaction. A fade step changes the content, so the
first build on or after a step's day records it. A gone scar stays in the table (hazards.burn_scar_shown leaves
it out), so fading never deletes. raw.record keeps every version, so a refresh that would delete more than half
of the held scars (and more than MAX_DROP_FLOOR) means something upstream is wrong: it's refused unless
--force.

    python3 -m ingest.builds                                  # is burn-scars marked? (state, marks, age)
    python3 -m ingest burn-scars                              # run the build: logged, clears its marks
    python3 -m ingest burn-scars --dry-run --list             # what would change, each scar; nothing written
    python3 -m ingest burn-scars --dry-run --on 2027-11-01    # the fade on another day (dry runs only)

Standard library plus psycopg.
"""

import argparse
import functools
import hashlib
import json
import os
import sys
import time
from collections import Counter, namedtuple
from datetime import date
from zoneinfo import ZoneInfo

import psycopg

from ingest import arcgis, builds, db, layer_version, seasons
from .sources import nifc_wfigs_perimeters as perimeters

BOISE = ZoneInfo("America/Boise")
PERIMETERS = perimeters.SOURCE["name"]
BUILD = "burn-scars"                             # the build (ops.build_run, ops.build_pending): this command
LAYER = "hazards.burn_scars"                     # the tile layer: /api/hazards/tiles/burn_scars
BOX = (-117.05, 43.00, -115.95, 43.85)           # west, south, east, north: the map box, the ground's extent
PHOTO_LAST_DAY = date(2025, 7, 24)               # NAIP 2025's last flight day in the box (docs/09)
STEPS = 3                                        # growing seasons to fade over
KINDS = {"WF": "wildfire", "RX": "prescribed"}   # attr_IncidentTypeCategory
SIMPLIFY_M = 10                                  # geom_lo's tolerance, in metres (UTM 11N)
UTM = 32611
GROWING_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "growing_season.json")
MAX_DROP_SHARE = 0.5
MAX_DROP_FLOOR = 5
# Bounds, as production's login has no statement_timeout and GEOS can stall on a bad outline:
STATEMENT_TIMEOUT_S = 60     # each statement in a refresh (one fire's geometry is one statement)
BUDGET_S = 300               # the writes stop after this; the rest wait for the next run, and the build stays marked
DEFERRED = "left for the next run (out of time)"     # the stats' key for them
NOTE_MAX = 1000              # a run's note in ops.build_run
# Errors that are one fire's geometry, not the refresh's: GEOS or PostGIS throwing (XX000), or a statement out of
# time. Anything else (a missing column, a lost connection) still fails the refresh.
GEOMETRY_ERRORS = (psycopg.errors.InternalError_, psycopg.errors.QueryCanceled)

# The tile layer's licence (plan C3): the perimeters' own, from the manifest (a test checks they agree).
LICENSE = perimeters.SOURCE["license"]
CREDIT = perimeters.SOURCE["credit"]
REPUBLISH = "yes"

# What the geometry is made with: part of every row's content hash, so a change here rewrites every scar.
GEOMETRY_RULE = f"valid; cut to {BOX}; geom_lo simplified at {SIMPLIFY_M} m in EPSG:{UTM}"

# near: the version's outline has a bounding box that overlaps the map box (no GEOS needed); whether the outline
# itself reaches into the box is settled when it's cut (_WRITE).
Version = namedtuple("Version", "source_id version_hash payload first_seen last_seen near")


# --- rules (offline) ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=None)
def growing(path=GROWING_FILE):
    """The growing season's rules, read when first needed (a broken file fails the build, not the perimeter
    poller, which imports this module to mark the build)."""
    return seasons.load(path)


def boise_day(ms):
    """An Esri date (ms since 1970, UTC) as its day in Boise, or None."""
    t = arcgis.esri_date(ms)
    return t.astimezone(BOISE).date() if t else None


def pick(versions):
    """The version a fire is drawn from: its newest final perimeter, else its newest version."""
    return max(versions, key=lambda v: (perimeters.is_final(v.payload), v.last_seen, v.first_seen,
                                        bytes(v.version_hash)))


def kind_of(p):
    """'wildfire' or 'prescribed', or None for anything else (complexes, false alarms, unknown). Complexes are left
    out on the assumption that their member fires carry their own perimeters ⚠️ (not yet checked against WFIGS)."""
    code = (arcgis.text(p.get("attr_IncidentTypeCategory")) or "").upper()
    if code:
        return KINDS.get(code)
    category = (arcgis.text(p.get("poly_FeatureCategory")) or "").lower()    # e.g. 'Wildfire Final Fire Perimeter'
    if "prescribed" in category:
        return "prescribed"
    if "wildfire" in category:
        return "wildfire"
    return None


def burn_day(p):
    """(day in Boise, 'discovery' or 'perimeter'), or (None, None) for a fire with no date at all."""
    day = boise_day(p.get("attr_FireDiscoveryDateTime"))
    if day:
        return day, "discovery"
    day = boise_day(p.get("poly_PolygonDateTime")) or boise_day(p.get("poly_DateCurrent"))
    return (day, "perimeter") if day else (None, None)


def fade_steps(burned_on, rules=None):
    """The STEPS days a scar burned on `burned_on` steps down: the day after each of the first STEPS whole growing
    seasons that begin after the fire's day."""
    rules = growing() if rules is None else rules
    start, end = date(burned_on.year - 1, 1, 1), date(burned_on.year + STEPS + 2, 1, 1)
    last = seasons.moment(end)
    after = seasons.moment(burned_on, end=True)        # the midnight after the fire's day
    steps = [span.end.astimezone(BOISE).date() for span in seasons.timeline(rules, start, end)
             if span.value is not None and span.start >= after and span.end < last]     # whole seasons only
    if len(steps) < STEPS:
        raise ValueError(f"the growing season rules give {len(steps)} seasons after {burned_on}, not {STEPS}")
    return steps[:STEPS]


def seasons_passed(steps, day):
    """How many of a scar's steps have come by `day` (0 to STEPS)."""
    return sum(1 for s in steps if s <= day)


def fade(n):
    """The fade after n whole growing seasons: 1, 2/3, 1/3, then 0 (as the table's generated column)."""
    return (STEPS - n) / STEPS


def content_hash(row):
    """What a refresh compares: every field it writes but the time, plus the geometry rule."""
    body = {k: v for k, v in row.items() if k != "content_hash"}
    body["record_hash"] = bytes(row["record_hash"]).hex()
    body["_geometry"] = GEOMETRY_RULE
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()).digest()


def scar_of(v, today, rules=None):
    """(row, None) for a fire's chosen version that's drawn, else (None, why it's left out)."""
    p = v.payload
    if not perimeters.is_valid(p):
        return None, "withdrawn"
    kind = kind_of(p)
    if kind is None:
        return None, "not a wildfire or prescribed fire"
    if not v.near:
        return None, "outside the box"
    burned, dated_by = burn_day(p)
    if burned is None:
        return None, "no date"
    if burned <= PHOTO_LAST_DAY:
        return None, "before the photo"
    steps = fade_steps(burned, rules)
    acres = arcgis.number(p.get("poly_GISAcres"))
    if acres is None:
        acres = arcgis.number(p.get("attr_IncidentSize"))
    row = {
        "fire_id": v.source_id,
        "name": arcgis.text(p.get("poly_IncidentName")) or arcgis.text(p.get("attr_IncidentName")),
        "kind": kind,
        "burned_on": burned,
        "dated_by": dated_by,
        "perimeter": "final" if perimeters.is_final(p) else "daily",
        "perimeter_at": arcgis.esri_date(p.get("poly_PolygonDateTime")) or arcgis.esri_date(p.get("poly_DateCurrent")),
        "acres": float(acres) if acres is not None and acres >= 0 else None,
        "map_method": arcgis.text(p.get("poly_MapMethod")),
        "seasons": seasons_passed(steps, today),
        "fade_1_on": steps[0],
        "fade_2_on": steps[1],
        "gone_on": steps[2],
        "record_hash": bytes(v.version_hash),
    }
    row["content_hash"] = content_hash(row)
    return row, None


def plan(held, rows):
    """held: {fire_id: content_hash} in the table; rows: {fire_id: row} drawn now.
    -> (rows to write, fire_ids to delete, unchanged count)."""
    write = [r for fid, r in sorted(rows.items()) if held.get(fid) != r["content_hash"]]
    delete = sorted(fid for fid in held if fid not in rows)
    return write, delete, len(rows) - len(write)


def check_drops(n_delete, n_held, force=False):
    """Refuse a refresh that deletes most of what's held (fading never deletes; raw.record keeps every version)."""
    if not force and n_delete > max(MAX_DROP_FLOOR, MAX_DROP_SHARE * n_held):
        raise RuntimeError(f"burn scars: the refresh would delete {n_delete} of {n_held} scars; refused "
                           "(raw.record keeps every version, so check the perimeters source; --force takes it)")


# --- database ------------------------------------------------------------------------------------

_ENVELOPE = "ST_MakeEnvelope(%(west)s, %(south)s, %(east)s, %(north)s, 4326)"

# A perimeter made valid. MakeValid's default (linework) method gives null for some published perimeters on the
# server's GEOS 3.10 (on Oct 11, 2026 RANGE and WILSON, multipolygons with near-zero-area slivers); the structure
# method (GEOS 3.10+) keeps their shells and holes, and treats a sliver as nothing.
_VALID = "coalesce(ST_MakeValid(geom, 'method=structure'), ST_MakeValid(geom))"

# Every current version, with a bounding-box test only: nothing here calls GEOS, so no one perimeter can fail it.
_VERSIONS = f"""
select source_id, version_hash, payload, first_seen, last_seen, coalesce(geom && {_ENVELOPE}, false)
from raw.record
where source = %(source)s and removed_at is null"""

# One scar from its raw.record version: valid polygons, cut to the box, and the low-zoom copy. It answers
# (fire_id if written, whether anything was left once made valid): a version with nothing left is unusable, and one
# whose cut is empty (it only touches the box, or its box overlaps but the outline doesn't) writes nothing.
_WRITE = f"""
with v as (
  select version_hash, ST_Multi(ST_CollectionExtract({_VALID}, 3)) as valid
  from raw.record
  where source = %(source)s and source_id = %(fire_id)s and version_hash = %(record_hash)s and geom is not null
), usable as (
  select * from v where valid is not null and not ST_IsEmpty(valid)
), cut as (
  select version_hash, not ST_CoveredBy(valid, {_ENVELOPE}) as clipped,
         ST_Multi(ST_CollectionExtract(ST_Intersection(valid, {_ENVELOPE}), 3)) as geom
  from usable
), lo as (
  select *, ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Transform(
              ST_SimplifyPreserveTopology(ST_Transform(geom, %(utm)s), %(tolerance)s), 4326)), 3)) as simple
  from cut
  where geom is not null and not ST_IsEmpty(geom)
), written as (
  insert into hazards.burn_scar (fire_id, name, kind, burned_on, dated_by, perimeter, perimeter_at, acres,
                                 map_method, seasons, fade_1_on, fade_2_on, gone_on, clipped, geom, geom_lo,
                                 record_hash, content_hash, refreshed_at)
  select %(fire_id)s, %(name)s, %(kind)s, %(burned_on)s, %(dated_by)s, %(perimeter)s, %(perimeter_at)s, %(acres)s,
         %(map_method)s, %(seasons)s, %(fade_1_on)s, %(fade_2_on)s, %(gone_on)s, clipped, geom,
         case when simple is null or ST_IsEmpty(simple) then geom else simple end,
         version_hash, %(content_hash)s, %(at)s
  from lo
  on conflict (fire_id) do update set
    name = excluded.name, kind = excluded.kind, burned_on = excluded.burned_on, dated_by = excluded.dated_by,
    perimeter = excluded.perimeter, perimeter_at = excluded.perimeter_at, acres = excluded.acres,
    map_method = excluded.map_method, seasons = excluded.seasons, fade_1_on = excluded.fade_1_on,
    fade_2_on = excluded.fade_2_on, gone_on = excluded.gone_on, clipped = excluded.clipped, geom = excluded.geom,
    geom_lo = excluded.geom_lo, record_hash = excluded.record_hash, content_hash = excluded.content_hash,
    refreshed_at = excluded.refreshed_at
  returning fire_id
)
select (select fire_id from written), exists (select 1 from usable)"""

# A held scar whose new version couldn't be drawn keeps its last good row, stepping down on its own stored days.
# Its content_hash stays the old one, so the next refresh still sees a change and tries the new version again.
_SEASONS_ON = "((fade_1_on <= %(today)s)::int + (fade_2_on <= %(today)s)::int + (gone_on <= %(today)s)::int)"
_STEP = f"""
update hazards.burn_scar set seasons = {_SEASONS_ON}, refreshed_at = %(at)s
where fire_id = %(fire_id)s and seasons <> {_SEASONS_ON}
returning fire_id"""


def _box():
    west, south, east, north = BOX
    return {"west": west, "south": south, "east": east, "north": north}


def read_versions(conn, source=PERIMETERS):
    """{source_id: [Version]} for every current perimeter version of the source."""
    out = {}
    for sid, h, payload, first, last, near in conn.execute(_VERSIONS, {"source": source, **_box()}).fetchall():
        out.setdefault(sid, []).append(Version(sid, bytes(h), payload, first, last, near))
    return out


def write_scar(conn, row, source, now):
    """Write one scar (_WRITE) -> (fire_id or None, usable). Raises a GEOMETRY_ERRORS error for a perimeter PostGIS
    can't work; refresh() runs it in a savepoint."""
    return conn.execute(_WRITE, {**row, "source": source, "at": now, "utm": UTM, "tolerance": SIMPLIFY_M,
                                 **_box()}).fetchone()


def ready(conn, build=False):
    """Why a refresh (with build: a logged run of the build) can't run here yet (a missing migration), or None."""
    needs = [("hazards.burn_scar", "hazards/0001_burn_scar.sql"), ("core.layer_version", "migration 0020")]
    if build:
        needs.append(("ops.build_run", "migration 0021"))
    for table, migration in needs:
        if conn.execute("select to_regclass(%s)", (table,)).fetchone()[0] is None:
            return f"{table} is missing: {migration} isn't applied"
    return None


def _first_line(err):
    return (str(err).strip().splitlines() or [type(err).__name__])[0][:160]


def refresh(conn, today=None, now=None, source=PERIMETERS, layer=LAYER, force=False, rules=None,
            statement_timeout_s=STATEMENT_TIMEOUT_S, budget_s=BUDGET_S):
    """Bring hazards.burn_scar in line with the source's perimeters as of `today` (a Boise day; default: now's).
    Doesn't commit. Returns the run's stats."""
    missing = ready(conn)
    if missing:
        return {"skipped": missing}
    deadline = time.monotonic() + budget_s
    conn.execute(f"set local statement_timeout = {int(statement_timeout_s * 1000)}")    # until commit or rollback
    now = now or db.now()
    today = today or now.astimezone(BOISE).date()
    versions = read_versions(conn, source)
    rows, left_out, problems = {}, Counter(), []
    for fid, vs in versions.items():
        row, why = scar_of(pick(vs), today, rules)
        if row is None:
            left_out[why] += 1
        else:
            rows[fid] = row
    held = {fid: (bytes(c), bytes(r)) for fid, c, r in
            conn.execute("select fire_id, content_hash, record_hash from hazards.burn_scar").fetchall()}
    write, delete, unchanged = plan({fid: c for fid, (c, _) in held.items()}, rows)
    check_drops(len(delete), len(held), force)
    # Scars whose version is unchanged first (fade steps: due on their day, and they cost the least), then new ones.
    write.sort(key=lambda r: (held.get(r["fire_id"], (None, None))[1] != r["record_hash"], r["fire_id"]))
    written, kept, stepped, deferred = set(), 0, 0, 0
    for row in write:
        fid = row["fire_id"]
        if time.monotonic() >= deadline:
            deferred += 1                       # held as it is; the next run carries on
            continue
        why = None
        try:
            with conn.transaction():            # a savepoint: one fire's failure is its own
                got, usable = write_scar(conn, row, source, now)
        except GEOMETRY_ERRORS as err:
            got, why = None, "geometry error"
            problems.append(f"{row['name'] or '-'} ({fid}): {_first_line(err)}")
        if got:
            written.add(got)
            continue
        if why is None and not usable:
            why = "geometry unusable"
            problems.append(f"{row['name'] or '-'} ({fid}): nothing left once made valid")
        if why is None:                         # it only touches the box: as if outside it
            left_out["outside the box"] += 1
            if fid in held:
                delete.append(fid)
            continue
        left_out[why] += 1
        if fid in held:                         # keep its last good scar, stepping down on its stored days
            kept += 1
            stepped += bool(conn.execute(_STEP, {"fire_id": fid, "today": today, "at": now}).fetchone())
    if delete:
        conn.execute("delete from hazards.burn_scar where fire_id = any(%s)", (delete,))
    shown, total = conn.execute(
        "select count(*) filter (where seasons < %s), count(*) from hazards.burn_scar", (STEPS,)).fetchone()
    has_version = conn.execute("select exists (select 1 from core.layer_version where layer = %s)",
                               (layer,)).fetchone()[0]
    version = None
    if written or delete or stepped or not has_version:
        note = f"{len(written)} written, {len(delete)} deleted, {shown} shown of {total}"
        if kept:
            note += f", {kept} kept from an older version ({stepped} stepped)"
        version = layer_version.record(
            conn, layer, license=LICENSE, republish=REPUBLISH, credit=CREDIT, features=shown,
            build=f"burn_scars refresh as of {today.isoformat()}", note=note)
    stats = {"as of": today.isoformat(), "fires": len(versions), "scars": total, "shown": shown,
             "written": len(written), "deleted": len(delete), "unchanged": unchanged,
             "version": version or "unchanged"}
    if kept:
        stats["kept from an older version"] = kept
        stats["stepped"] = stepped
    if deferred:
        stats[DEFERRED] = deferred
    stats.update({f"left out ({why})": n for why, n in sorted(left_out.items())})
    if problems:
        stats["problems"] = "; ".join(problems)
    return stats


def note_of(stats):
    """A run's note in ops.build_run: what it did, and any fire left out for its geometry."""
    keys = ("as of", "scars", "shown", "written", "deleted", "version", "kept from an older version", DEFERRED,
            "left out (geometry unusable)", "left out (geometry error)", "problems")
    return ", ".join(f"{k} {stats[k]}" for k in keys if k in stats)[:NOTE_MAX]


def build(conn, force=False, name=BUILD, **kw):
    """Run the build by hand: refresh inside builds.Run, which refuses inside `ingest serve`, logs the run in
    ops.build_run and, once the refresh commits, clears the marks it saw. A run out of time (BUDGET_S) marks the
    build again for what it left. kw goes to refresh(). Returns the refresh's stats."""
    with builds.Run(conn, name) as run:
        missing = ready(conn)
        if missing:
            raise RuntimeError(f"{name}: {missing}")
        stats = refresh(conn, force=force, **kw)
        left = stats.get(DEFERRED)
        if left:
            builds.mark(conn, name, by=name, reason=f"{left} scar{'' if left == 1 else 's'} left for the next run "
                                                    "(out of time)")
        run.note = note_of(stats)
    return stats


# A held scar whose fade step has come since the build last wrote it. The build stores `seasons` as of its own day.
_DUE = f"select count(*) from hazards.burn_scar where seasons < {STEPS} and seasons <> {_SEASONS_ON}"


def mark(conn, by, new=0, now=None, name=BUILD):
    """Mark the build (builds.mark) for what a source brought or what the date did: `new` perimeter versions
    stored, or a held scar's fade step that has come since the last build. The perimeter poller and the
    backfill's load call it in their store step, so the mark commits with their data. Cheap: a count on
    hazards.burn_scar, no GEOS. Does nothing before migration 0021 (ops.build_pending). A step that has come marks
    once, not again on each poll while the build is still marked by `by`. -> {'<build> marked': reason} or {}."""
    marks, table = conn.execute("select to_regclass('ops.build_pending') is not null, "
                                "to_regclass('hazards.burn_scar') is not null").fetchone()
    if not marks:
        return {}
    today = (now or db.now()).astimezone(BOISE).date()
    due = conn.execute(_DUE, {"today": today}).fetchone()[0] if table else 0
    if due and not new and conn.execute("select 1 from ops.build_pending where build = %s and marked_by = %s",
                                        (name, by)).fetchone():
        due = 0
    reasons = []
    if new:
        reasons.append(f"{new} new perimeter version{'' if new == 1 else 's'}")
    if due:
        reasons.append(f"{due} scar{'' if due == 1 else 's'} due a fade step as of {today}")
    if not reasons:
        return {}
    reason = "; ".join(reasons)
    builds.mark(conn, name, by=by, reason=reason)
    return {f"{name} marked": reason}


def report(conn, stats, listing=False, out=print):
    out("burn scars: " + ", ".join(f"{k} {v}" for k, v in stats.items()))
    if not listing or "skipped" in stats:
        return
    rows = conn.execute(
        """select burned_on, name, kind, perimeter, acres, round((ST_Area(geom::geography) / 4046.8564)::numeric, 1),
                  clipped, seasons, fade, fade_1_on, fade_2_on, gone_on
           from hazards.burn_scar order by burned_on, name""").fetchall()
    out(f"{'burned':10}  {'name':24} {'kind':10} {'perimeter':9} {'acres':>9} {'in box':>9} {'cut':3}  "
        f"{'seasons':7} {'fade':5}  steps")
    for burned, name, kind, perim, acres, in_box, clipped, n, f, s1, s2, gone in rows:
        out(f"{burned}  {(name or '-')[:24]:24} {kind:10} {perim:9} "
            f"{'-' if acres is None else round(acres, 1):>9} {in_box:>9} {'yes' if clipped else '':3}  "
            f"{n:<7} {f:<5.2f}  {s1}, {s2}, {gone}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest burn-scars",
                                 description="Build hazards.burn_scar from the WFIGS perimeters in raw.record, by hand "
                                             "(the perimeter poller marks the build; `python3 -m ingest.builds` "
                                             "shows it). Never inside `ingest serve`.")
    ap.add_argument("--dry-run", action="store_true", help="refresh and report, then roll back (no run logged)")
    ap.add_argument("--on", type=date.fromisoformat, metavar="YYYY-MM-DD",
                    help="the day to work the fade out for (with --dry-run only; default: today in Boise)")
    ap.add_argument("--list", action="store_true", help="print each scar")
    ap.add_argument("--force", action="store_true", help="take a refresh that deletes most of the scars")
    args = ap.parse_args(argv)
    if args.on and not args.dry_run:
        ap.error("--on needs --dry-run: the table holds the fade as of today")
    with db.connect() as conn:
        if args.dry_run:
            stats = refresh(conn, today=args.on, force=args.force)
            report(conn, stats, args.list)
            conn.rollback()
            print("(dry run: nothing written)", flush=True)
            return 0
        missing = ready(conn, build=True)
        if missing:
            print(f"burn scars: {missing}", file=sys.stderr, flush=True)
            return 1
        stats = build(conn, force=args.force)
        report(conn, stats, args.list)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
