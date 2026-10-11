"""Burn scars (landscape sprint, Oct 2026: plan C15 and §3.4 K10, package P13; decision 25):
`python3 -m ingest burn-scars`.

Fires that burned after the ground's photo are drawn on the painted ground, in Valley only, in a neutral char
tone with a stipple (never red), fading over three growing seasons. They aren't clickable in v1. This module
keeps hazards.burn_scar (hazards/0001) in step with the WFIGS perimeters the poller stores in raw.record
(source nifc_wfigs_perimeters). It fetches nothing. It runs as the derived source `burn_scars`, hourly in
`ingest serve` and logged in ops.fetch like any source (as the daily intersections build does), and by hand. It's
light: about a hundred record versions in, a few dozen rows out. It runs on a schedule because the scars follow
the poller (plan C4: they change with it, so they aren't baked) and the fade's steps fall on dates.

Rules, per fire (one source_id in raw.record):

1. **Which version:** the newest final perimeter if the fire has one, else its newest version (newest: last
   seen, then first seen). A final perimeter outranks a later daily one, as in the poller's own reads.
2. **Whether it's drawn:** that version still stands (nifc_wfigs_perimeters.is_valid: not withdrawn as
   invalid, deleted or hidden), it's a wildfire (WF) or a prescribed fire (RX), it touches the map box, and the
   fire came after the photo. Complexes (CX) are left out: their member fires carry their own perimeters, and
   a complex's outline over them would draw the char twice.
3. **After the photo:** the ground paints NAIP 2025, flown in the box from May 25 to Jul 24, 2025 (docs/09), so
   a fire counts from Jul 25, 2025 (after PHOTO_LAST_DAY). Its day is its discovery day in Boise
   (attr_FireDiscoveryDateTime), else its perimeter's own day (`dated_by` says which).
4. **The fade:** a scar steps down the day after each of the first three whole growing seasons that begin
   after its fire (growing_season.json, read by core's ingest/seasons.py: April through October, an estimate
   ⚠️). Its fade is 1 until then, then 2/3, 1/3, and 0 (gone). `seasons` (0-3) and `fade` are as of the
   refresh's day in Boise; the three step days are stored with them.
5. **Geometry:** made valid and cut to the map box, the ground's extent (`clipped` says when it was cut), plus a
   copy simplified at 10 m for low zooms. Acres stay the whole fire's, as published.

A refresh rewrites only rows whose content changed (content_hash), deletes fires that no longer qualify, and,
when anything changed or the layer has no version yet, records a new version of the tile layer
'hazards.burn_scars' (core.layer_version), in the same transaction. A fade step changes the content, so the
hourly run records each step as its day comes. A gone scar stays in the table (hazards.burn_scar_shown leaves
it out), so fading never deletes. raw.record keeps every version, so a refresh that would delete more than half
of the held scars (and more than MAX_DROP_FLOOR) means something upstream is wrong: it's refused unless
--force.

    python3 -m ingest burn-scars                              # refresh now
    python3 -m ingest burn-scars --dry-run --list             # what would change, each scar; nothing written
    python3 -m ingest burn-scars --dry-run --on 2027-11-01    # the fade on another day (dry runs only)

Standard library plus psycopg.
"""

import argparse
import functools
import hashlib
import json
import os
from collections import Counter, namedtuple
from datetime import date
from zoneinfo import ZoneInfo

from ingest import arcgis, db, layer_version, seasons
from .sources import nifc_wfigs_perimeters as perimeters

BOISE = ZoneInfo("America/Boise")
PERIMETERS = perimeters.SOURCE["name"]
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

# The tile layer's licence (plan C3): the perimeters' own, from the manifest (a test checks they agree).
LICENSE = perimeters.SOURCE["license"]
CREDIT = perimeters.SOURCE["credit"]
REPUBLISH = "yes"

# What the geometry is made with: part of every row's content hash, so a change here rewrites every scar.
GEOMETRY_RULE = f"valid; cut to {BOX}; geom_lo simplified at {SIMPLIFY_M} m in EPSG:{UTM}"

SOURCE = {
    "name": "burn_scars",
    "title": "Burn scars (derived from the WFIGS perimeters)",
    "url": "https://github.com/Benten-Ben/treasure-valley-traffic/blob/main/plugins/hazards/ingest/burn_scars.py",
    "access": "open",
    "schedule": "1 hour",
    "license": "derived",
    "credit": CREDIT,
    "notes": "Derived, fetches nothing: hazards.burn_scar refreshed from raw.record's nifc_wfigs_perimeters versions "
             "(fires in the map box after the ground's photo, Jul 24, 2025), with their fade over three growing "
             "seasons; a new version of the tile layer hazards.burn_scars when anything changed.",
}

Version = namedtuple("Version", "source_id version_hash payload first_seen last_seen in_box")


# --- rules (offline) ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=None)
def growing(path=GROWING_FILE):
    """The growing season's rules, read when first needed (a broken file fails the refresh, not the import that
    `ingest serve` makes of every source at start)."""
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
    """'wildfire' or 'prescribed', or None for anything else (complexes, false alarms, unknown)."""
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
    if not v.in_box:
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

_VERSIONS = f"""
select source_id, version_hash, payload, first_seen, last_seen,
       coalesce(geom && {_ENVELOPE} and ST_Intersects(ST_MakeValid(geom), {_ENVELOPE}), false)
from raw.record
where source = %(source)s and removed_at is null"""

# One scar from its raw.record version: valid polygons, cut to the box, and the low-zoom copy. A version whose cut
# is empty (it only touches the box) writes nothing.
_WRITE = f"""
with v as (
  select version_hash, ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3)) as valid
  from raw.record
  where source = %(source)s and source_id = %(fire_id)s and version_hash = %(record_hash)s and geom is not null
), cut as (
  select version_hash, not ST_CoveredBy(valid, {_ENVELOPE}) as clipped,
         ST_Multi(ST_CollectionExtract(ST_Intersection(valid, {_ENVELOPE}), 3)) as geom
  from v
), lo as (
  select *, ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Transform(
              ST_SimplifyPreserveTopology(ST_Transform(geom, %(utm)s), %(tolerance)s), 4326)), 3)) as simple
  from cut
  where not ST_IsEmpty(geom)
)
insert into hazards.burn_scar (fire_id, name, kind, burned_on, dated_by, perimeter, perimeter_at, acres, map_method,
                               seasons, fade_1_on, fade_2_on, gone_on, clipped, geom, geom_lo, record_hash,
                               content_hash, refreshed_at)
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
returning fire_id"""


def _box():
    west, south, east, north = BOX
    return {"west": west, "south": south, "east": east, "north": north}


def read_versions(conn, source=PERIMETERS):
    """{source_id: [Version]} for every current perimeter version of the source."""
    out = {}
    for sid, h, payload, first, last, in_box in conn.execute(_VERSIONS, {"source": source, **_box()}).fetchall():
        out.setdefault(sid, []).append(Version(sid, bytes(h), payload, first, last, in_box))
    return out


def ready(conn):
    """Why a refresh can't run here yet (a missing migration), or None."""
    if conn.execute("select to_regclass('hazards.burn_scar')").fetchone()[0] is None:
        return "hazards/0001_burn_scar.sql isn't applied"
    if conn.execute("select to_regclass('core.layer_version')").fetchone()[0] is None:
        return "core.layer_version (migration 0020) isn't applied"
    return None


def refresh(conn, today=None, now=None, source=PERIMETERS, layer=LAYER, force=False, rules=None):
    """Bring hazards.burn_scar in line with the source's perimeters as of `today` (a Boise day; default: now's).
    Doesn't commit. Returns the run's stats."""
    missing = ready(conn)
    if missing:
        return {"skipped": missing}
    now = now or db.now()
    today = today or now.astimezone(BOISE).date()
    versions = read_versions(conn, source)
    rows, left_out = {}, Counter()
    for fid, vs in versions.items():
        row, why = scar_of(pick(vs), today, rules)
        if row is None:
            left_out[why] += 1
        else:
            rows[fid] = row
    held = {fid: bytes(h) for fid, h in conn.execute("select fire_id, content_hash from hazards.burn_scar").fetchall()}
    write, delete, unchanged = plan(held, rows)
    check_drops(len(delete), len(held), force)
    written = set()
    for row in write:
        got = conn.execute(_WRITE, {**row, "source": source, "at": now, "utm": UTM, "tolerance": SIMPLIFY_M,
                                    **_box()}).fetchone()
        if got:
            written.add(got[0])
        else:                                   # it only touches the box: as if outside it
            left_out["outside the box"] += 1
            if row["fire_id"] in held:
                delete.append(row["fire_id"])
    if delete:
        conn.execute("delete from hazards.burn_scar where fire_id = any(%s)", (delete,))
    shown, total = conn.execute(
        "select count(*) filter (where seasons < %s), count(*) from hazards.burn_scar", (STEPS,)).fetchone()
    has_version = conn.execute("select exists (select 1 from core.layer_version where layer = %s)",
                               (layer,)).fetchone()[0]
    version = None
    if written or delete or not has_version:
        version = layer_version.record(
            conn, layer, license=LICENSE, republish=REPUBLISH, credit=CREDIT, features=shown,
            build=f"burn_scars refresh as of {today.isoformat()}",
            note=f"{len(written)} written, {len(delete)} deleted, {shown} shown of {total}")
    stats = {"as of": today.isoformat(), "fires": len(versions), "scars": total, "shown": shown,
             "written": len(written), "deleted": len(delete), "unchanged": unchanged,
             "version": version or "unchanged"}
    stats.update({f"left out ({why})": n for why, n in sorted(left_out.items())})
    return stats


def run(conn):
    """The scheduled derived source: refresh, logged in ops.fetch like any other source."""
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        stats = refresh(conn, now=f.started_at)
        f.records = stats.get("scars")
    return stats


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
                                 description="Refresh hazards.burn_scar from the WFIGS perimeters in raw.record "
                                             "(the 'burn_scars' source does this hourly).")
    ap.add_argument("--dry-run", action="store_true", help="refresh and report, then roll back")
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
        db.ensure_source(conn, SOURCE)
        with db.Fetch(conn, SOURCE["name"]) as f:
            stats = refresh(conn, now=f.started_at, force=args.force)
            f.records = stats.get("scars")
        report(conn, stats, args.list)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
