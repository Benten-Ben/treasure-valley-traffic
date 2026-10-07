"""Where each bus fix lies along its route, and how the bus got to its next fix
(docs/14 §14.4, "Playback").

For every fix in obs.vehicle_position this writes one row to
obs.vehicle_progress (migration 0007): the shape the fix was matched to, its
measure m along that shape (metres in UTM 11N), how far off the shape it was,
the route and how that route is known, and the step to the vehicle's next fix:

  kind      rule (dt seconds, c chord metres, dm metres along the shape)   speed
  gap       dt > 150 s                                                     -
  still     c < 12 m, or -20 <= dm < 0 on the same shape                   0
  along     same shape, 0 <= dm <= 3c + 100, dm/dt <= 30 m/s               dm/dt
  straight  anything else, including off every shape                      c/dt

The tracks API (app/src/lib/server/transit-tracks.ts) replays buses from these
rows; fixes with no row yet still play there, as straight steps.

**Matching.** Candidates are the shapes of the bus's route (the feed's own
route or its trip ID's, else obs.trip_route_match); with no route, every shape
within 40 m. On the shape of the previous fix, projections are limited to the
window [m_prev - 60, m_prev + 30 m/s * dt + 60] (loops, whose ends are under
50 m apart, wrap), which keeps an out-and-back shape on the right pass. Among
the projections within 40 m the cost is the distance, plus 50 if the bus is
moving (12 m or more since its last fix) and the feed bearing is more than 60
degrees off the shape, plus 25 for switching shape, plus any backward motion
beyond 20 m. After a gap the chain starts afresh.

**Provisional routes.** A bus with no route whose last 4 "along" fixes each lie
within 40 m of exactly one route's shapes, the same route, is put on that route
for the rest of its trip (route_source 'path'). A trip_route_match wins once it
exists (the tracks API checks it at read time).

**It can never cost us bus positions.** The transit stream commits each batch of
positions first and only then calls after_batch(), inside try/except with a
rollback (sources/vrt_realtime.py). Each call has a 5 s budget: fixes it doesn't
reach wait for the next batch. Runs are serialised with a session advisory
lock: the stream tries it and skips matching for that batch if it's held; the
backfill waits for it. Rows are written with `on conflict do nothing`. A fix
older than its vehicle's newest row is stored with no step (method 'late')
rather than re-threading the chain; fixes older than a vehicle's oldest row
(a backfill behind the running stream) are threaded as their own chain, ending
with a step to that row.

By hand (idempotent: it only processes fixes with no row, per vehicle in time
order):

  python3 -m ingest transit-progress --hours 24
  python3 -m ingest transit-progress --from 2026-10-06T11:00Z --to 2026-10-06T15:00Z
  python3 -m ingest transit-progress --report --hours 24     # step shares, speeds, backward motion
"""

import argparse
import bisect
import math
import sys
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ingest import db
from .sources.vrt_realtime import TRIP_ROUTE

NEAR_M = 40.0             # a fix this close to a shape can be on it
BACK_M = 60.0             # projection window on the previous shape: this far behind the previous measure,
AHEAD_MS = 30.0           # ... and up to this speed ahead,
AHEAD_M = 60.0            # ... plus this
LOOP_M = 50.0             # a shape whose ends are closer than this is a loop: measures wrap
MOVING_M = 12.0           # "moving": at least this far from the last fix
BEARING_DEG = 60.0        # feed bearing this far off the shape's direction costs BEARING_COST
BEARING_COST = 50.0
SWITCH_COST = 25.0
BACKWARD_FREE_M = 20.0    # backward motion beyond this costs a metre per metre
GAP_S = 150.0
STILL_M = 12.0
STILL_BACK_M = 20.0
ALONG_MAX_MS = 30.0
PATH_FIXES = 4
BUDGET_S = 5.0            # per call from the stream
ONLINE_HOURS = 3          # the stream's matcher looks this far back for fixes with no row
HORIZON = timedelta(hours=1)   # earlier rows can't share a non-gap step with a pending fix
METHOD = "window_v1"
LATE = "late"
LOCK_KEY = 0x7476_7470_7207    # pg advisory lock: one matcher at a time (stream or backfill)
UTM = 26911                    # NAD83 / UTM zone 11N, metres


# -- geometry (metres) ------------------------------------------------------------------------------

def angle_between(a, b):
    """Smallest difference between two bearings, degrees."""
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


class Shape:
    """A shape as a polyline in metres, with the cumulative measure at each vertex."""

    def __init__(self, shape_id, route_id, coords):
        pts = [tuple(coords[0])]
        for p in coords[1:]:
            if tuple(p) != pts[-1]:
                pts.append(tuple(p))
        self.id, self.route_id = shape_id, route_id
        self.x = [p[0] for p in pts]
        self.y = [p[1] for p in pts]
        cum = [0.0]
        for i in range(1, len(pts)):
            cum.append(cum[-1] + math.hypot(self.x[i] - self.x[i - 1], self.y[i] - self.y[i - 1]))
        self.cum = cum
        self.length = cum[-1]
        self.loop = len(pts) > 2 and math.hypot(self.x[0] - self.x[-1], self.y[0] - self.y[-1]) < LOOP_M

    def bearing(self, i):
        """Direction of segment i, degrees clockwise from (grid) north."""
        return math.degrees(math.atan2(self.x[i + 1] - self.x[i], self.y[i + 1] - self.y[i])) % 360.0

    def at(self, m):
        """(x, y) at measure m, clamped to the shape."""
        m = min(max(m, 0.0), self.length)
        i = min(max(bisect.bisect_right(self.cum, m) - 1, 0), len(self.cum) - 2)
        seg = self.cum[i + 1] - self.cum[i]
        f = 0.0 if seg <= 0 else (m - self.cum[i]) / seg
        return self.x[i] + f * (self.x[i + 1] - self.x[i]), self.y[i] + f * (self.y[i + 1] - self.y[i])

    def dm(self, m0, m1):
        """m1 - m0, the short way round when the shape is a loop."""
        d = m1 - m0
        if self.loop and self.length > 0:
            d = (d + self.length / 2.0) % self.length - self.length / 2.0
        return d

    def ranges(self, lo, hi):
        """The parts of [0, length] inside the measure window [lo, hi]; loops wrap."""
        n = self.length
        if not self.loop:
            a, b = max(lo, 0.0), min(hi, n)
            return [(a, b)] if a <= b else []
        if hi - lo >= n:
            return [(0.0, n)]
        a, b = lo % n, hi % n
        return [(a, b)] if a <= b else [(a, n), (0.0, b)]


class Network:
    """Every shape, with a grid of segments for finding the ones near a point."""

    CELL = 100.0

    def __init__(self, shapes):
        self.shapes, self.by_route = {}, defaultdict(list)
        self.grid = defaultdict(list)
        c = self.CELL
        for s in shapes:
            if len(s.x) < 2 or s.length <= 0:
                continue
            self.shapes[s.id] = s
            self.by_route[s.route_id].append(s.id)
            for i in range(len(s.x) - 1):
                x0, x1 = sorted((s.x[i], s.x[i + 1]))
                y0, y1 = sorted((s.y[i], s.y[i + 1]))
                for cx in range(math.floor((x0 - NEAR_M) / c), math.floor((x1 + NEAR_M) / c) + 1):
                    for cy in range(math.floor((y0 - NEAR_M) / c), math.floor((y1 + NEAR_M) / c) + 1):
                        self.grid[(cx, cy)].append((s.id, i))

    def route_shapes(self, route_id):
        """The shape ids a bus on this route can be matched to; None (every shape) if the route has none."""
        ids = self.by_route.get(route_id) if route_id else None
        return set(ids) if ids else None

    def projections(self, x, y, shape_ids=None, windows=None):
        """[(shape_id, m, off, segment)]: each nearby segment's closest point within NEAR_M.
        windows ({shape_id: [(a, b)]}) limits the measures allowed on those shapes."""
        out = []
        for sid, i in self.grid.get((math.floor(x / self.CELL), math.floor(y / self.CELL)), ()):
            if shape_ids is not None and sid not in shape_ids:
                continue
            s = self.shapes[sid]
            ax, ay = s.x[i], s.y[i]
            dx, dy = s.x[i + 1] - ax, s.y[i + 1] - ay
            m0, m1 = s.cum[i], s.cum[i + 1]
            seg2 = dx * dx + dy * dy
            t = 0.0 if seg2 <= 0 else min(1.0, max(0.0, ((x - ax) * dx + (y - ay) * dy) / seg2))
            m = m0 + t * (m1 - m0)
            rng = windows.get(sid) if windows else None
            if rng is None:
                off = math.hypot(x - (ax + t * dx), y - (ay + t * dy))
            else:
                best = None
                for a, b in rng:
                    lo, hi = max(a, m0), min(b, m1)
                    if lo > hi:
                        continue
                    mm = min(max(m, lo), hi)
                    f = 0.0 if m1 <= m0 else (mm - m0) / (m1 - m0)
                    d = math.hypot(x - (ax + f * dx), y - (ay + f * dy))
                    if best is None or d < best[1]:
                        best = (mm, d)
                if best is None:
                    continue
                m, off = best
            if off <= NEAR_M:
                out.append((sid, m, off, i))
        return out

    def routes_near(self, x, y):
        """Routes with a shape within NEAR_M of the point."""
        return {self.shapes[sid].route_id for sid, _, _, _ in self.projections(x, y)}


# -- matching (pure) ----------------------------------------------------------------------------------

@dataclass
class Fix:
    """One GPS fix to place, with what's known about its route."""
    vehicle_id: str
    ts: datetime
    x: float
    y: float
    bearing: float | None = None
    trip_id: str | None = None
    route_id: str | None = None        # the recorder's route: the feed's own or the trip ID's
    route_source: str | None = None    # 'feed' or 'trip' when route_id is set
    matched_route: str | None = None   # obs.trip_route_match
    trip_shape: str | None = None      # the scheduled trip's shape: a tie-break hint at most

    @property
    def t(self):
        return self.ts.timestamp()


@dataclass
class Row:
    """One obs.vehicle_progress row (x, y and trip_id ride along for the next step)."""
    vehicle_id: str
    ts: datetime
    x: float
    y: float
    trip_id: str | None = None
    shape_id: str | None = None
    m: float | None = None
    off_m: float | None = None
    route_id: str | None = None
    route_source: str | None = None
    step: str | None = None
    step_speed_ms: float | None = None
    method: str = METHOD
    step_in: str | None = None         # the step that led here (not stored: it's the previous row's step)

    @property
    def t(self):
        return self.ts.timestamp()


def classify(net, prev, cur):
    """(kind, speed m/s) of the step from one placed fix to the next."""
    dt = cur.t - prev.t
    if dt > GAP_S:
        return "gap", None
    c = math.hypot(cur.x - prev.x, cur.y - prev.y)
    shape = net.shapes.get(prev.shape_id) if prev.shape_id is not None and prev.shape_id == cur.shape_id else None
    dm = shape.dm(prev.m, cur.m) if shape else None
    if c < STILL_M or (dm is not None and -STILL_BACK_M <= dm < 0):
        return "still", 0.0
    if dm is not None and dt > 0 and 0 <= dm <= 3 * c + 100 and dm / dt <= ALONG_MAX_MS:
        return "along", dm / dt
    return "straight", (c / dt if dt > 0 else None)


def place(net, fix, prev, route_id):
    """(shape_id, m, off) for a fix, or (None, None, None) when it's off every candidate shape.
    prev: the chain's previous row, or None for a fresh start."""
    dt = fix.t - prev.t if prev is not None else None
    chain = prev is not None and prev.shape_id in net.shapes and dt <= GAP_S
    windows = None
    if chain:
        s = net.shapes[prev.shape_id]
        windows = {s.id: s.ranges(prev.m - BACK_M, prev.m + AHEAD_MS * dt + AHEAD_M)}
    moving = prev is None or math.hypot(fix.x - prev.x, fix.y - prev.y) >= MOVING_M
    best = None
    for sid, m, off, i in net.projections(fix.x, fix.y, net.route_shapes(route_id), windows):
        s = net.shapes[sid]
        cost = off
        if moving and fix.bearing is not None and angle_between(fix.bearing, s.bearing(i)) > BEARING_DEG:
            cost += BEARING_COST
        if chain:
            if sid != prev.shape_id:
                cost += SWITCH_COST
            else:
                back = -s.dm(prev.m, m)
                if back > BACKWARD_FREE_M:
                    cost += back - BACKWARD_FREE_M
        key = (round(cost, 6), sid != fix.trip_shape, sid, m)
        if best is None or key < best[0]:
            best = (key, sid, m, off)
    if best is None:
        return None, None, None
    return best[1], best[2], best[3]


def known_route(fix):
    """(route_id, route_source) from the feed, the trip ID, or trip_route_match; (None, None) if unknown."""
    if fix.route_id:
        return fix.route_id, fix.route_source or "feed"
    if fix.matched_route:
        return fix.matched_route, "matched"
    return None, None


class Chain:
    """One vehicle's fixes, placed and stepped in time order. history: the vehicle's
    newest stored rows (oldest first), so a chain picks up where the last call stopped."""

    def __init__(self, net, history=()):
        self.net = net
        self.last = None
        self.near = deque(maxlen=PATH_FIXES)
        self.path_trip, self.path_route = None, None
        prev = None
        for r in history:
            r.step_in = prev.step if prev is not None else None
            if r.route_source == "path":
                # A stored provisional route stands for the rest of its trip.
                if r.trip_id != self.path_trip:
                    self.near.clear()
                self.path_trip, self.path_route = r.trip_id, r.route_id
            elif r.route_source is None:
                self._path(r)
            prev = r
        self.last = prev

    def _path(self, row):
        """The provisional route of a bus no source labels (route_source 'path')."""
        if row.trip_id != self.path_trip or row.step_in == "gap":
            self.path_trip, self.path_route = row.trip_id, None
            self.near.clear()
        if self.path_route is None and row.step_in == "along":
            self.near.append(frozenset(self.net.routes_near(row.x, row.y)))
            if len(self.near) == PATH_FIXES and all(len(r) == 1 for r in self.near) \
                    and len(frozenset().union(*self.near)) == 1:
                self.path_route = next(iter(self.near[0]))
        if self.path_route is not None:
            row.route_id, row.route_source = self.path_route, "path"

    def add(self, fix):
        """Place the next fix, set the previous row's step, and return the new row."""
        route_id, source = known_route(fix)
        shape_id, m, off = place(self.net, fix, self.last, route_id)
        row = Row(fix.vehicle_id, fix.ts, fix.x, fix.y, fix.trip_id, shape_id, m, off, route_id, source)
        if self.last is not None:
            kind, speed = classify(self.net, self.last, row)
            self.last.step, self.last.step_speed_ms = kind, speed
            row.step_in = kind
        if route_id is None:
            self._path(row)
        self.last = row
        return row


def late_row(net, fix):
    """A fix older than its vehicle's newest row: placed on its own, with no step."""
    row = Chain(net).add(fix)
    row.method = LATE
    return row


def thread(net, fixes, history=(), first=None):
    """Place one vehicle's pending fixes (in time order) around its stored rows.

    history: the vehicle's newest stored rows, oldest first; first: its oldest
    stored row (within the horizon). Returns (new rows, stored rows whose step
    was set). Fixes newer than the newest row continue its chain; fixes older
    than the oldest row form their own chain, ending in a step to that row;
    anything in between is late.
    """
    newest = history[-1] if history else None
    before = [f for f in fixes if first is not None and f.ts < first.ts]
    after = [f for f in fixes if newest is None or f.ts > newest.ts]
    taken = {id(f) for f in before} | {id(f) for f in after}
    rows, updated = [], []
    if before:
        chain = Chain(net)
        part = [chain.add(f) for f in before]
        part[-1].step, part[-1].step_speed_ms = classify(net, part[-1], first)
        rows += part
    for f in fixes:
        if id(f) not in taken:
            rows.append(late_row(net, f))
    if after:
        chain = Chain(net, history)
        stored = chain.last
        rows += [chain.add(f) for f in after]
        if stored is not None and stored.step is not None:
            updated.append(stored)
    rows.sort(key=lambda r: r.ts)
    return rows, updated


# -- database -----------------------------------------------------------------------------------------

_SHAPES = f"""
select shape_id, route_id, ST_AsGeoJSON(ST_Transform(geom, {UTM}))::json -> 'coordinates'
from core.transit_shape where active and route_id is not null order by shape_id
"""

_net_cache = {"key": None, "net": None}


def network(conn):
    """Active shapes in metres, reloaded only when they change."""
    key = conn.execute("select count(*), max(updated_at) from core.transit_shape where active").fetchone()
    if _net_cache["key"] != key:
        rows = conn.execute(_SHAPES).fetchall()
        _net_cache["net"] = Network([Shape(sid, rid, coords) for sid, rid, coords in rows])
        _net_cache["key"] = key
    return _net_cache["net"]


# Fixes with no progress row, with what's known of their route. The trip match
# is looked up the way the tracks API does: the trip's own date or the day before.
_PENDING = f"""
select p.vehicle_id, p.ts, ST_X(ST_Transform(p.geom, {UTM})), ST_Y(ST_Transform(p.geom, {UTM})), p.bearing,
       p.trip_id, p.route_id, t.trip_id is not null, t.shape_id, m.route_id
from obs.vehicle_position p
left join core.transit_trip t on t.trip_id = p.trip_id
left join lateral (
  select x.route_id from obs.trip_route_match x
  where p.route_id is null and x.trip_id = p.trip_id
    and x.service_date between (p.ts at time zone 'America/Boise')::date - 1 and (p.ts at time zone 'America/Boise')::date
  order by x.service_date desc limit 1) m on true
where p.ts >= %(start)s and (%(end)s::timestamptz is null or p.ts <= %(end)s)
  and not exists (select 1 from obs.vehicle_progress g where g.vehicle_id = p.vehicle_id and g.ts = p.ts)
order by p.vehicle_id, p.ts
"""

_ROW_COLUMNS = f"""g.vehicle_id, g.ts, ST_X(ST_Transform(p.geom, {UTM})), ST_Y(ST_Transform(p.geom, {UTM})), p.trip_id,
       g.shape_id, g.m, g.off_m, g.route_id, g.route_source, g.step, g.step_speed_ms"""

# Each vehicle's newest stored rows since the horizon (enough to rebuild a provisional route).
_HISTORY = f"""
select * from (
  select {_ROW_COLUMNS}, row_number() over (partition by g.vehicle_id order by g.ts desc) as rn
  from obs.vehicle_progress g join obs.vehicle_position p on p.vehicle_id = g.vehicle_id and p.ts = g.ts
  where g.vehicle_id = any(%(vids)s) and g.ts >= %(since)s and g.method <> 'late') h
where rn <= {2 * PATH_FIXES} order by 1, 2
"""

_OLDEST = f"""
select distinct on (g.vehicle_id) {_ROW_COLUMNS}
from obs.vehicle_progress g join obs.vehicle_position p on p.vehicle_id = g.vehicle_id and p.ts = g.ts
where g.vehicle_id = any(%(vids)s) and g.ts >= %(since)s and g.method <> 'late'
order by g.vehicle_id, g.ts
"""

_INSERT = """
insert into obs.vehicle_progress (vehicle_id, ts, shape_id, m, off_m, route_id, route_source, step, step_speed_ms,
                                  method, backfill)
values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
on conflict (vehicle_id, ts) do nothing
"""

_UPDATE = """
update obs.vehicle_progress set step = %s, step_speed_ms = %s
where vehicle_id = %s and ts = %s and step is null
"""


def _r(v, nd):
    return None if v is None else round(v, nd)


def _stored(rec):
    vid, ts, x, y, trip, shape, m, off, route, source, step, speed = rec[:12]
    return Row(vid, ts, x, y, trip, shape, m, off, route, source, step, speed)


def pending(conn, start, end=None):
    """{vehicle_id: [Fix]} for fixes with no progress row in [start, end], in time order."""
    out = defaultdict(list)
    for vid, ts, x, y, bearing, trip, route, scheduled, trip_shape, matched in conn.execute(
            _PENDING, {"start": start, "end": end}):
        source = None
        if route:
            source = "trip" if scheduled or TRIP_ROUTE.search(trip or "") else "feed"
        out[vid].append(Fix(vid, ts, x, y, bearing, trip, route, source, matched, trip_shape))
    return out


def process(conn, start, end=None, *, deadline=None, backfill=False, fresh=None, commit_every=None, log=None):
    """Match every fix with no progress row in [start, end]. Doesn't commit (unless
    commit_every rows, for the backfill). deadline: time.monotonic() value after which
    vehicles not yet reached are left for the next call. fresh: (vehicle_id, ts) keys of
    the batch just stored; rows for other fixes are marked as caught up (backfill)."""
    stats = Counter()
    net = network(conn)
    fixes = pending(conn, start, end)
    if not fixes:
        return dict(stats)
    vids = sorted(fixes, key=lambda v: (fixes[v][0].ts, v))
    since = min(f[0].ts for f in fixes.values()) - HORIZON
    history = defaultdict(list)
    for rec in conn.execute(_HISTORY, {"vids": vids, "since": since}):
        history[rec[0]].append(_stored(rec))
    oldest = {rec[0]: _stored(rec) for rec in conn.execute(_OLDEST, {"vids": vids, "since": since})}

    inserts, updates = [], []
    done = 0
    for n, vid in enumerate(vids):
        if deadline is not None and time.monotonic() > deadline:
            stats["deferred"] += sum(len(fixes[v]) for v in vids[n:])
            break
        rows, updated = thread(net, fixes[vid], history.get(vid, []), oldest.get(vid))
        for r in rows:
            caught_up = backfill or (fresh is not None and (r.vehicle_id, r.ts) not in fresh)
            inserts.append((r.vehicle_id, r.ts, r.shape_id, _r(r.m, 2), _r(r.off_m, 2), r.route_id, r.route_source,
                            r.step, _r(r.step_speed_ms, 2), r.method, caught_up))
            stats["late" if r.method == LATE else (r.step or "newest")] += 1
            if r.route_source == "path":
                stats["path"] += 1
        for r in updated:
            updates.append((r.step, _r(r.step_speed_ms, 2), r.vehicle_id, r.ts))
            stats[r.step] += 1
        stats["fixes"] += len(fixes[vid])
        if commit_every and len(inserts) >= commit_every:
            done += _write(conn, inserts, updates)
            conn.commit()
            inserts, updates = [], []
            if log:
                log(f"  {n + 1}/{len(vids)} vehicles, {done} rows")
    done += _write(conn, inserts, updates)
    stats["rows"] = done
    stats["vehicles"] = len(vids)
    return dict(stats)


def _write(conn, inserts, updates):
    with conn.cursor() as cur:
        if inserts:
            cur.executemany(_INSERT, inserts)
        if updates:
            cur.executemany(_UPDATE, updates)
    return len(inserts)


def after_batch(conn, fresh=None, budget_s=BUDGET_S, hours=ONLINE_HOURS):
    """The stream's call, after each committed batch of positions: match what's
    pending, within budget_s. If the backfill (or another matcher) holds the lock,
    skip this batch; its fixes are matched by a later call."""
    started = time.monotonic()
    if not conn.execute("select pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0]:
        conn.rollback()
        return {"skipped (locked)": 1}
    try:
        # A guard against a hung query; the budget itself is checked between vehicles.
        conn.execute(f"set local statement_timeout = {int(max(budget_s, 1.0) * 1000)}")
        start = db.now() - timedelta(hours=hours)
        stats = process(conn, start, deadline=started + budget_s, fresh=fresh)
        conn.commit()
        return stats
    except BaseException:
        conn.rollback()
        raise
    finally:
        try:
            conn.execute("select pg_advisory_unlock(%s)", (LOCK_KEY,))
            conn.commit()
        except Exception:
            pass


def backfill(conn, start, end=None, log=print, commit_every=5000):
    """Match every pending fix in [start, end], waiting for the stream's matcher
    to finish first; the stream skips matching until this is done. Rows are
    committed every commit_every (log is called after each commit)."""
    if log:
        log("transit_progress: waiting for the matcher lock")
    conn.execute("select pg_advisory_lock(%s)", (LOCK_KEY,))
    conn.commit()
    try:
        stats = process(conn, start, end, backfill=True, commit_every=commit_every, log=log)
        conn.commit()
        return stats
    except BaseException:
        conn.rollback()
        raise
    finally:
        try:
            conn.execute("select pg_advisory_unlock(%s)", (LOCK_KEY,))
            conn.commit()
        except Exception:
            pass


# -- report -------------------------------------------------------------------------------------------

_REPORT = """
select g.vehicle_id, g.shape_id, g.m, g.off_m, g.route_source, g.step, g.step_speed_ms, g.method,
       lead(g.shape_id) over w, lead(g.m) over w
from obs.vehicle_progress g
where g.ts >= %(start)s and (%(end)s::timestamptz is null or g.ts <= %(end)s) and g.method <> 'late'
window w as (partition by g.vehicle_id order by g.ts)
"""

# The prototype's shares on 432 fixes of Oct 5 (docs/14 §14.4), for labeled buses.
PROTOTYPE = {"along": 232, "still": 71, "gap": 14, "straight": 6}


def report(conn, start, end=None):
    """Step shares and the playback checks for a window (docs/14 §14.4, "Acceptance")."""
    net = network(conn)
    labeled, every = Counter(), Counter()
    offs, along_fast, along_back, straight_back = [], 0, 0, 0
    max_along = 0.0
    for vid, shape, m, off, source, step, speed, method, shape1, m1 in conn.execute(
            _REPORT, {"start": start, "end": end}):
        if off is not None:
            offs.append(off)
        if step is None:
            continue
        every[step] += 1
        if source in ("feed", "trip"):
            labeled[step] += 1
        s = net.shapes.get(shape) if shape is not None and shape == shape1 and m1 is not None else None
        dm = s.dm(m, m1) if s else None
        if step == "along":
            max_along = max(max_along, speed or 0.0)
            along_fast += (speed or 0.0) > ALONG_MAX_MS
            along_back += dm is not None and dm < 0
        if step == "straight" and dm is not None and dm < -STILL_BACK_M:
            straight_back += 1
    late = conn.execute("""select count(*) from obs.vehicle_progress where method = 'late' and ts >= %(start)s
                             and (%(end)s::timestamptz is null or ts <= %(end)s)""",
                        {"start": start, "end": end}).fetchone()[0]
    n = sum(labeled.values())
    proto_n = sum(PROTOTYPE.values())
    offs.sort()
    return {
        "steps (labeled buses)": dict(labeled),
        "steps (every bus)": dict(every),
        "shares (labeled)": {k: round(labeled[k] / n, 3) if n else None for k in PROTOTYPE},
        "prototype shares": {k: round(v / proto_n, 3) for k, v in PROTOTYPE.items()},
        "along or still (labeled)": round((labeled["along"] + labeled["still"]) / n, 3) if n else None,
        "fastest along m/s": round(max_along, 2),
        "along over 30 m/s": along_fast,
        "along going backward": along_back,
        "straight steps going back over 20 m": straight_back,
        "p99 matched distance m": round(offs[min(len(offs) - 1, int(0.99 * len(offs)))], 1) if offs else None,
        "late fixes": late,
    }


def _when(text):
    t = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest transit-progress",
                                 description="Match bus fixes to their routes for playback (docs/14 §14.4).")
    ap.add_argument("--hours", type=float, default=24, help="how far back to look (default 24)")
    ap.add_argument("--from", dest="start", type=_when, help="window start, ISO time (instead of --hours)")
    ap.add_argument("--to", dest="end", type=_when, help="window end, ISO time (default: now)")
    ap.add_argument("--report", action="store_true", help="print the window's step shares and checks; match nothing")
    args = ap.parse_args(argv)
    start = args.start or db.now() - timedelta(hours=args.hours)
    with db.connect() as conn:
        if args.report:
            for k, v in report(conn, start, args.end).items():
                print(f"{k}: {v}")
            return
        t0 = time.monotonic()
        stats = backfill(conn, start, args.end)
    print(f"transit_progress: {time.monotonic() - t0:.1f} s; " + ", ".join(f"{k} {v}" for k, v in sorted(stats.items())),
          flush=True)


if __name__ == "__main__":
    sys.exit(main())
