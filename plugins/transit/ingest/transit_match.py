"""Put unlabeled live bus trips on their routes (docs/08, VRT row).

Since VRT's Oct 1, 2026 service changes, about a quarter of live trips carry a
numeric trip ID that names no route and isn't in the static schedule. Two
fixes, run every few minutes by the transit stream:

1. **Re-resolve:** fixes stored with no route but a trip ID that does name one
   (e.g. stored before the schedule was loaded) get it, by the same rule as live
   fixes (vrt_realtime.resolve_route).
2. **Match by path:** a numeric trip with at least MIN_FIXES fixes is matched to
   the route whose shapes most of its fixes lie within NEAR_M of. It's labeled
   only if that share is at least MIN_SHARE and leads the runner-up by
   MIN_MARGIN; ambiguous trips (routes sharing most of their streets) stay
   unlabeled. Matches go to obs.trip_route_match, not into the fixes.

By hand: python3 -m ingest match-routes [--hours 24]
"""

import argparse

from ingest import db

from .sources import vrt_realtime

NEAR_M = 40
MIN_FIXES = 10
MIN_SHARE = 0.55
MIN_MARGIN = 0.15
METHOD = f"shape_{NEAR_M}m"


def decide(fixes, hits):
    """(route_id, share, runner_up, runner_up_share) for a trip, or None if it's
    too short or ambiguous. hits maps route_id to the number of the trip's fixes
    near that route."""
    if fixes < MIN_FIXES or not hits:
        return None
    ranked = sorted(hits.items(), key=lambda kv: (-kv[1], kv[0]))
    best, best_hits = ranked[0]
    share = best_hits / fixes
    runner_up, runner_hits = ranked[1] if len(ranked) > 1 else (None, 0)
    runner_share = runner_hits / fixes
    if share < MIN_SHARE or share - runner_share < MIN_MARGIN:
        return None
    return best, round(share, 3), runner_up, (round(runner_share, 3) if runner_up else None)


def reresolve(conn, hours):
    lookup = vrt_realtime.load_lookup(conn)
    trips = [t for (t,) in conn.execute(
        """select distinct trip_id from obs.vehicle_position
           where ts > now() - make_interval(hours => %s) and route_id is null
             and trip_id <> '' and trip_id !~ '^[0-9]+$'""", (hours,)).fetchall()]
    fixed = 0
    for trip in trips:
        route = vrt_realtime.resolve_route(trip, "", lookup)
        if route:
            fixed += conn.execute(
                """update obs.vehicle_position set route_id = %s
                   where ts > now() - make_interval(hours => %s) and trip_id = %s and route_id is null""",
                (route, hours, trip)).rowcount
    return fixed


# Fixes of numeric trips, each trip dated by its first fix; then, per trip and
# route, how many of those fixes lie within NEAR_M of one of the route's shapes.
# Shapes are compared in UTM 11N (meters); the bounding-box test uses the index.
_HITS = """
with u as (
  select trip_id, ts, geom,
         (min(ts) over (partition by trip_id) at time zone 'America/Boise')::date as service_date
  from obs.vehicle_position
  where ts > now() - make_interval(hours => %(hours)s) and route_id is null and trip_id ~ '^[0-9]+$'
),
tot as (select trip_id, service_date, count(*) as fixes from u group by 1, 2),
hits as (
  select u.trip_id, u.service_date, s.route_id, count(distinct u.ts) as h
  from u join core.transit_shape s
    on s.geom && ST_Expand(u.geom, 0.0006)
   and ST_DWithin(ST_Transform(s.geom, 26911), ST_Transform(u.geom, 26911), %(near)s)
  group by 1, 2, 3
)
select t.trip_id, t.service_date, t.fixes, h.route_id, h.h
from tot t left join hits h using (trip_id, service_date)
"""


def match(conn, hours):
    trips = {}
    for trip_id, day, fixes, route_id, h in conn.execute(_HITS, {"hours": hours, "near": NEAR_M}).fetchall():
        t = trips.setdefault((trip_id, day), {"fixes": fixes, "hits": {}})
        if route_id:
            t["hits"][route_id] = h
    matched = 0
    for (trip_id, day), t in trips.items():
        result = decide(t["fixes"], t["hits"])
        if not result:
            continue
        route, share, runner_up, runner_share = result
        conn.execute(
            """insert into obs.trip_route_match (trip_id, service_date, route_id, share, runner_up, runner_up_share,
                 fixes, method, matched_at)
               values (%s, %s, %s, %s, %s, %s, %s, %s, now())
               on conflict (trip_id, service_date) do update set route_id = excluded.route_id,
                 share = excluded.share, runner_up = excluded.runner_up, runner_up_share = excluded.runner_up_share,
                 fixes = excluded.fixes, method = excluded.method, matched_at = excluded.matched_at""",
            (trip_id, day, route, share, runner_up, runner_share, t["fixes"], METHOD))
        matched += 1
    return {"trips": len(trips), "matched": matched}


def run(conn, hours=3):
    stats = {"re-resolved fixes": reresolve(conn, hours)}
    stats.update(match(conn, hours))
    conn.commit()
    return stats


def main(argv=None):
    """`python3 -m ingest match-routes` (registered in ../plugin.json)."""
    ap = argparse.ArgumentParser(prog="python3 -m ingest match-routes",
                                 description="Put unlabeled bus trips on routes by their path (the transit stream does this).")
    ap.add_argument("--hours", type=int, default=24, help="how far back to look (default 24)")
    args = ap.parse_args(argv)
    with db.connect() as conn:
        stats = run(conn, args.hours)
    print("match-routes: " + ", ".join(f"{k} {v}" for k, v in stats.items()), flush=True)
