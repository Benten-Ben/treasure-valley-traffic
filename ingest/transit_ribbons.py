"""Side-by-side transit ribbons: the corridor graph, slot order and route colors
(docs/14 §14.4, "Route colors" and "Side-by-side ribbons").

Routes that share a street are drawn side by side. This builds, from VRT's own
shapes, the atomic pieces of shared street ("segments") with the routes on
each, left to right, ordered so routes cross as little as possible; then
picks route colors so routes drawn beside each other never clash
(route_colors.py). Standard library only; the database is touched only by
load_inputs, dormant_routes, store and run.

A build runs in this fixed order:

1. corridors and a crossing-optimal slot order, without colors (deterministic);
2. neighbors from that order (adjacent slots for 100 m or more) plus the
   proximity rule (sharing 300 m or more outside the hubs);
3. colors against those neighbors, in the owner's mode (Q3: rebalance);
4. a color pass that swaps routes only where the crossing cost is unchanged
   and the swap creates no clash.

It's skipped when the build hash (shapes, dormant set, parameters, and the
current colors) is unchanged, and stored inside a savepoint, so a failed
build keeps the previous ribbons. vrt_gtfs's daily run calls run().

By hand:
  python3 -m ingest.transit_ribbons [--force] [--mode rebalance|minimal] [--dry-run]
"""

import argparse
import hashlib
import itertools
import json
import math
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from . import route_colors

ALGO = "corridors_v1"

# Parameters (all part of the build hash). Distances in metres, in UTM 11N.
STEP_M = 5.0             # densify every shape every 5 m
MATCH_M = 40.0           # a shape point joins a piece within 40 m...
MATCH_DEG = 35.0         # ...whose tangent is parallel or antiparallel within 35 degrees
SWITCH_M = 10.0          # extra cost for leaving the previous point's piece
MIN_RUN_M = 80.0         # matched runs shorter than this become unmatched
BRIDGE_M = 40.0          # unmatched gaps shorter than this between runs on one piece are bridged
SELF_GAP_M = 150.0       # a shape can run back over its own street once it's this far along
MIN_PIECE_M = 30.0       # shorter unmatched runs make no piece of their own
CLUSTER_M = 20.0         # cuts on a piece within 20 m are one cut
SNAP_M = 40.0            # where a route changes piece, the cut snaps to the pieces' closest approach within this
JOIN_MAX_M = 60.0        # cuts further apart than this are never joined into one node
LOOP_M = 50.0            # a shape whose ends are this close is a loop
SIMPLIFY_M = 1.5         # Douglas-Peucker tolerance
HUB_ROUTES = 6           # a stop served by this many routes is a hub
HUB_SEGMENT_M = 300.0    # a segment whose midpoint is this close to a hub stop is a hub segment
HUB_RADIUS_M = 900.0     # the proximity rule ignores sharing this close to a hub (today's rule)
W_CROSS, W_CROSS_HUB, W_SEP = 4, 1, 1
TURN_DEG = 10.0          # turns closer than this impose no side
HEADING_M = 30.0         # headings at a segment end are measured over this distance
SWEEPS = 30
EXACT_MAX = 6            # try every permutation up to this many routes on a segment
ADJACENT_M = 100.0       # adjacent slots for this long make neighbors
SHARED_M = 300.0         # sharing this much outside the hubs makes neighbors (today's rule)
DORMANT_DAYS = 7

PARAMS = {k: v for k, v in globals().items() if k.isupper() and isinstance(v, (int, float)) and not k.startswith("_")}

# -- UTM zone 11N (WGS84), Krueger series to n^6: sub-millimetre in the zone ------------------------------------

_A, _F = 6378137.0, 1 / 298.257223563
_N = _F / (2 - _F)
_E = math.sqrt(_F * (2 - _F))
_K0, _LON0, _E0 = 0.9996, math.radians(-117.0), 500000.0
_AA = _A / (1 + _N) * (1 + _N ** 2 / 4 + _N ** 4 / 64 + _N ** 6 / 256)
_n = _N
_ALPHA = (
    _n / 2 - 2 * _n ** 2 / 3 + 5 * _n ** 3 / 16 + 41 * _n ** 4 / 180 - 127 * _n ** 5 / 288 + 7891 * _n ** 6 / 37800,
    13 * _n ** 2 / 48 - 3 * _n ** 3 / 5 + 557 * _n ** 4 / 1440 + 281 * _n ** 5 / 630 - 1983433 * _n ** 6 / 1935360,
    61 * _n ** 3 / 240 - 103 * _n ** 4 / 140 + 15061 * _n ** 5 / 26880 + 167603 * _n ** 6 / 181440,
    49561 * _n ** 4 / 161280 - 179 * _n ** 5 / 168 + 6601661 * _n ** 6 / 7257600,
    34729 * _n ** 5 / 80640 - 3418889 * _n ** 6 / 1995840,
    212378941 * _n ** 6 / 319334400)
_BETA = (
    _n / 2 - 2 * _n ** 2 / 3 + 37 * _n ** 3 / 96 - _n ** 4 / 360 - 81 * _n ** 5 / 512 + 96199 * _n ** 6 / 604800,
    _n ** 2 / 48 + _n ** 3 / 15 - 437 * _n ** 4 / 1440 + 46 * _n ** 5 / 105 - 1118711 * _n ** 6 / 3870720,
    17 * _n ** 3 / 480 - 37 * _n ** 4 / 840 - 209 * _n ** 5 / 4480 + 5569 * _n ** 6 / 90720,
    4397 * _n ** 4 / 161280 - 11 * _n ** 5 / 504 - 830251 * _n ** 6 / 7257600,
    4583 * _n ** 5 / 161280 - 108847 * _n ** 6 / 3991680,
    20648693 * _n ** 6 / 638668800)


def to_utm(lon, lat):
    """WGS84 lon/lat to UTM 11N metres (EPSG:26911/32611 agree to centimetres here)."""
    phi, lam = math.radians(lat), math.radians(lon) - _LON0
    s = math.sin(phi)
    t = math.sinh(math.atanh(s) - _E * math.atanh(_E * s))
    xi_, eta_ = math.atan2(t, math.cos(lam)), math.atanh(math.sin(lam) / math.sqrt(1 + t * t))
    xi, eta = xi_, eta_
    for j, a in enumerate(_ALPHA, 1):
        xi += a * math.sin(2 * j * xi_) * math.cosh(2 * j * eta_)
        eta += a * math.cos(2 * j * xi_) * math.sinh(2 * j * eta_)
    return _E0 + _K0 * _AA * eta, _K0 * _AA * xi


def from_utm(x, y):
    """UTM 11N metres to WGS84 lon/lat."""
    xi, eta = y / (_K0 * _AA), (x - _E0) / (_K0 * _AA)
    xi_, eta_ = xi, eta
    for j, b in enumerate(_BETA, 1):
        xi_ -= b * math.sin(2 * j * xi) * math.cosh(2 * j * eta)
        eta_ -= b * math.cos(2 * j * xi) * math.sinh(2 * j * eta)
    tau_ = math.sin(xi_) / math.sqrt(math.sinh(eta_) ** 2 + math.cos(xi_) ** 2)
    lam = math.atan2(math.sinh(eta_), math.cos(xi_))
    tau = tau_
    for _ in range(10):
        sig = math.sinh(_E * math.atanh(_E * tau / math.sqrt(1 + tau * tau)))
        ti = tau * math.sqrt(1 + sig * sig) - sig * math.sqrt(1 + tau * tau)
        d = (tau_ - ti) / math.sqrt(1 + ti * ti) * (1 + (1 - _E * _E) * tau * tau) / (
            (1 - _E * _E) * math.sqrt(1 + tau * tau))
        tau += d
        if abs(d) < 1e-14:
            break
    return math.degrees(lam + _LON0), math.degrees(math.atan(tau))


# -- geometry ------------------------------------------------------------------------------------------------------

def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def densify(coords, step=STEP_M):
    """Points every `step` metres along a polyline (metres), ends included: [(x, y)]."""
    pts = [tuple(coords[0])]
    run, next_at = 0.0, step
    for a, b in zip(coords, coords[1:]):
        d = _dist(a, b)
        if d == 0:
            continue
        while next_at <= run + d + 1e-9:
            t = (next_at - run) / d
            pts.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            next_at += step
        run += d
    if len(pts) > 1 and _dist(pts[-1], coords[-1]) <= 0.5:
        pts[-1] = tuple(coords[-1])
    elif _dist(pts[-1], coords[-1]) > 0:
        pts.append(tuple(coords[-1]))
    return pts


def tangents(pts, span=2):
    """Unit tangents by central differences over +-span points."""
    out = []
    n = len(pts)
    for i in range(n):
        a, b = pts[max(0, i - span)], pts[min(n - 1, i + span)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy)
        if d == 0:
            out.append(out[-1] if out else (1.0, 0.0))
        else:
            out.append((dx / d, dy / d))
    return out


def length(pts):
    return sum(_dist(a, b) for a, b in zip(pts, pts[1:]))


def simplify(pts, tol=SIMPLIFY_M):
    """Douglas-Peucker, keeping both ends."""
    if len(pts) < 3:
        return list(pts)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        a, b = pts[i], pts[j]
        dx, dy = b[0] - a[0], b[1] - a[1]
        dd = dx * dx + dy * dy
        worst, at = -1.0, -1
        for k in range(i + 1, j):
            p = pts[k]
            if dd == 0:
                d = _dist(p, a)
            else:
                t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / dd))
                d = math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)
            if d > worst:
                worst, at = d, k
        if worst > tol:
            keep[at] = True
            stack.append((i, at))
            stack.append((at, j))
    return [p for p, k in zip(pts, keep) if k]


def point_at(pts, frac):
    """The point a fraction of the way along a polyline."""
    total = length(pts)
    goal, run = total * frac, 0.0
    for a, b in zip(pts, pts[1:]):
        d = _dist(a, b)
        if run + d >= goal and d > 0:
            t = (goal - run) / d
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        run += d
    return pts[-1]


def _heading_into(pts, from_end):
    """Unit vector from a segment end into the segment, over HEADING_M."""
    seq = pts if not from_end else pts[::-1]
    origin = seq[0]
    run = 0.0
    target = seq[-1]
    for a, b in zip(seq, seq[1:]):
        run += _dist(a, b)
        if run >= HEADING_M:
            target = b
            break
    dx, dy = target[0] - origin[0], target[1] - origin[1]
    d = math.hypot(dx, dy) or 1.0
    return dx / d, dy / d


def _turn(arrive, depart):
    """Signed turn in degrees from an arrival heading to a departure heading; left is positive."""
    cross = arrive[0] * depart[1] - arrive[1] * depart[0]
    dot = arrive[0] * depart[0] + arrive[1] * depart[1]
    return math.degrees(math.atan2(cross, dot))


class _Grid:
    def __init__(self, cell):
        self.cell, self.cells = cell, defaultdict(list)

    def add(self, x, y, item):
        self.cells[(int(x // self.cell), int(y // self.cell))].append(item)

    def near(self, x, y):
        cx, cy = int(x // self.cell), int(y // self.cell)
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                yield from self.cells.get((cx + i, cy + j), ())


# -- corridors -----------------------------------------------------------------------------------------------------

SELF = -1


class _UF:
    def __init__(self):
        self.parent = {}

    def find(self, k):
        self.parent.setdefault(k, k)
        root = k
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[k] != root:
            self.parent[k], k = root, self.parent[k]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            if rb < ra:
                ra, rb = rb, ra
            self.parent[rb] = ra


def _runs(labels):
    """Maximal runs of equal piece ids: [pid or None, i0, i1]."""
    runs = []
    for i, lab in enumerate(labels):
        pid = lab[0] if lab else None
        if runs and runs[-1][0] == pid:
            runs[-1][2] = i
        else:
            runs.append([pid, i, i])
    return runs


def _bridge(labels):
    step_pts = BRIDGE_M / STEP_M
    runs = _runs(labels)
    for k in range(1, len(runs) - 1):
        pid, i0, i1 = runs[k]
        prev, nxt = runs[k - 1], runs[k + 1]
        if pid is not None or prev[0] is None or prev[0] != nxt[0]:
            continue
        gap = i1 - i0 + 1
        if gap >= step_pts:
            continue
        a, b = labels[i0 - 1][1], labels[i1 + 1][1]
        if abs(b - a) > gap + 1 + step_pts:
            continue   # the same piece, but somewhere else along it
        for i in range(i0, i1 + 1):
            labels[i] = (prev[0], round(a + (b - a) * (i - i0 + 1) / (gap + 1)))


def _split(pid, seq):
    """Entries [pid, a, b] for a run of piece indices: a new one wherever the
    route turns back along the piece (by more than 20 m) or jumps (over 40 m)."""
    back, jump = int(CLUSTER_M / STEP_M), int(BRIDGE_M / STEP_M)
    out = [[pid, seq[0], seq[0]]]
    sign = 0                     # the direction along the piece so far; e[2] is the furthest point reached
    for v in seq[1:]:
        e = out[-1]
        step = v - e[2]
        if sign == 0:
            if abs(step) > jump:
                out.append([pid, v, v])
            elif step:
                e[2], sign = v, (1 if step > 0 else -1)
        elif step * sign >= 0:
            if step * sign > 2 * jump:
                out.append([pid, v, v])
                sign = 0
            else:
                e[2] = v
        elif -step * sign > jump:
            out.append([pid, v, v])
            sign = 0
        elif -step * sign > back:
            out.append([pid, e[2], v])
            sign = -sign
    return out


def _drop_short(labels):
    min_pts = MIN_RUN_M / STEP_M
    for pid, i0, i1 in _runs(labels):
        if pid is not None and i1 - i0 + 1 < min_pts:
            for i in range(i0, i1 + 1):
                labels[i] = None


class Corridors:
    """The corridor graph of a set of shapes (in metres): pieces, cut into segments."""

    def __init__(self, shapes):
        """shapes: [{'shape_id', 'route_id', 'xy': [(x, y), ...]}]."""
        self.pieces = []          # {'owner', 'pts', 'tans'}
        self.grid = _Grid(MATCH_M)
        self.paths = {}           # shape_id -> entries [pid, a, b]
        self.unions = []          # ((pid, cut), (pid, cut))
        self.extra_cuts = defaultdict(set)
        self.shapes = sorted(shapes, key=lambda s: (-length(s["xy"]), s["shape_id"]))
        self.cos_match = math.cos(math.radians(MATCH_DEG))
        for s in self.shapes:
            self._add_shape(s)
        self._cut()

    # -- step 2-4: match each shape against the pieces so far ------------------------------------------------------

    def _match(self, pts, tans):
        n = len(pts)
        labels = [None] * n
        own = _Grid(MATCH_M)
        gap = int(SELF_GAP_M / STEP_M)
        r2 = MATCH_M * MATCH_M
        prev = None
        for i in range(n):
            j = i - gap
            if j >= 0 and labels[j] is None:
                own.add(pts[j][0], pts[j][1], j)
            x, y = pts[i]
            tx, ty = tans[i]
            best = {}
            for pid, idx in self.grid.near(x, y):
                piece = self.pieces[pid]
                px, py = piece["pts"][idx]
                d2 = (px - x) ** 2 + (py - y) ** 2
                if d2 > r2:
                    continue
                qx, qy = piece["tans"][idx]
                if abs(tx * qx + ty * qy) < self.cos_match:
                    continue
                if abs((x - px) * qx + (y - py) * qy) > STEP_M:
                    continue   # beside the piece, not beyond its end
                cur = best.get(pid)
                if cur is None or (d2, idx) < cur:
                    best[pid] = (d2, idx)
            for jj in own.near(x, y):
                px, py = pts[jj]
                d2 = (px - x) ** 2 + (py - y) ** 2
                if d2 > r2:
                    continue
                qx, qy = tans[jj]
                if abs(tx * qx + ty * qy) < self.cos_match or abs((x - px) * qx + (y - py) * qy) > STEP_M:
                    continue
                cur = best.get(SELF)
                if cur is None or (d2, jj) < cur:
                    best[SELF] = (d2, jj)
            choice = None
            for pid, (d2, idx) in best.items():
                cost = math.sqrt(d2) + (0 if pid == prev else SWITCH_M)
                key = (cost, pid)
                if choice is None or key < choice[0]:
                    choice = (key, pid, idx)
            labels[i] = (choice[1], choice[2]) if choice else None
            prev = choice[1] if choice else None
        _bridge(labels)
        _drop_short(labels)
        _bridge(labels)
        return labels

    def _new_piece(self, owner, pts):
        pid = len(self.pieces)
        self.pieces.append({"owner": owner, "pts": pts, "tans": None})
        return pid

    def _index_piece(self, pid):
        piece = self.pieces[pid]
        piece["tans"] = tangents(piece["pts"])
        for idx, (x, y) in enumerate(piece["pts"]):
            self.grid.add(x, y, (pid, idx))

    def _pt(self, ref):
        return self.pieces[ref[0]]["pts"][ref[1]]

    def _add_shape(self, shape):
        pts = densify(shape["xy"])
        tans = tangents(pts)
        labels = self._match(pts, tans)
        n = len(pts)
        res = [None] * n
        entries = []          # [pid, a, b, anchored_start, anchored_end]
        new = []
        min_pts = MIN_PIECE_M / STEP_M
        runs = _runs(labels)
        for pid, i0, i1 in runs:
            if pid is not None and pid >= 0:
                for i in range(i0, i1 + 1):
                    res[i] = labels[i]
                entries.extend(e + [False, False] for e in _split(pid, [labels[i][1] for i in range(i0, i1 + 1)]))
            elif pid == SELF:
                # The route runs back over its own street: follow what those earlier points became.
                groups = []
                for i in range(i0, i1 + 1):
                    t = res[labels[i][1]]
                    res[i] = t
                    if t is None:
                        continue
                    if i > i0 and res[i - 1] is not None and res[i - 1][0] == t[0]:
                        groups[-1][1].append(t[1])
                    else:
                        groups.append((t[0], [t[1]]))
                for gpid, seq in groups:
                    entries.extend(e + [False, False] for e in _split(gpid, seq))
            else:
                if i1 - i0 + 1 < min_pts:
                    continue
                start = res[i0 - 1] if i0 > 0 else None
                if start and entries and entries[-1][0] == start[0]:
                    entries[-1][2] = start[1]      # the route leaves its piece exactly where the new one starts
                own_pts = ([self._pt(start)] if start else []) + pts[i0:i1 + 1]
                new_pid = self._new_piece(shape["shape_id"], own_pts)
                off = 1 if start else 0
                for i in range(i0, i1 + 1):
                    res[i] = (new_pid, off + i - i0)
                end = None
                if i1 + 1 < n and labels[i1 + 1] is not None:
                    lab = labels[i1 + 1]
                    end = res[lab[1]] if lab[0] == SELF else lab
                if end is not None:
                    own_pts.append(self._pt(end))
                last = len(own_pts) - 1
                if start:
                    self.unions.append(((new_pid, 0), start))
                    self.extra_cuts[start[0]].add(start[1])
                if end is not None:
                    self.unions.append(((new_pid, last), end))
                    self.extra_cuts[end[0]].add(end[1])
                entries.append([new_pid, 0, last, bool(start), end is not None])
                new.append(new_pid)
        # Where the route moves from one piece to the next without an anchor, snap both cuts to
        # the pieces' closest approach and join them.
        for e1, e2 in zip(entries, entries[1:]):
            if e1[4] or e2[3]:
                continue
            if (e1[0], e1[2]) != (e2[0], e2[1]):
                e1[2], e2[1] = self._snap(e1[0], e1[2], e2[0], e2[1])
            self.unions.append(((e1[0], e1[2]), (e2[0], e2[1])))
        if entries and _dist(pts[0], pts[-1]) < LOOP_M:
            first, last = entries[0], entries[-1]
            if (last[0], last[2]) != (first[0], first[1]):
                last[2], first[1] = self._snap(last[0], last[2], first[0], first[1])
            self.unions.append(((last[0], last[2]), (first[0], first[1])))
        for pid in new:
            self._index_piece(pid)
        self.paths[shape["shape_id"]] = [e[:3] for e in entries]

    def _snap(self, p, a, q, b):
        w = int(SNAP_M / STEP_M)
        P, Q = self.pieces[p]["pts"], self.pieces[q]["pts"]
        best = None
        for i in range(max(0, a - w), min(len(P), a + w + 1)):
            for j in range(max(0, b - w), min(len(Q), b + w + 1)):
                key = (round(_dist(P[i], Q[j]), 6), abs(i - a) + abs(j - b), i, j)
                if best is None or key < best:
                    best = key
        return best[2], best[3]

    # -- steps 5-6: cut pieces into segments, join cuts into nodes ------------------------------------------------

    def _cut(self):
        cuts = defaultdict(set)
        for pid, piece in enumerate(self.pieces):
            cuts[pid].update((0, len(piece["pts"]) - 1))
        for path in self.paths.values():
            for pid, a, b in path:
                cuts[pid].update((a, b))
        for pid, extra in self.extra_cuts.items():
            cuts[pid].update(extra)
        for (p1, c1), (p2, c2) in self.unions:
            cuts[p1].add(c1)
            cuts[p2].add(c2)
        span = int(CLUSTER_M / STEP_M)
        self.rep = {}
        self.reps = {}
        for pid in range(len(self.pieces)):
            last = len(self.pieces[pid]["pts"]) - 1
            cs = sorted(cuts[pid])
            # The piece's ends absorb cuts within 20 m (a short piece's cuts go to the nearer
            # end); the rest cluster greedily, each cluster spanning at most 20 m.
            if last <= 2 * span:
                head = [c for c in cs if c <= last - c]
                tail = [c for c in cs if c > last - c]
            else:
                head = [c for c in cs if c <= span]
                tail = [c for c in cs if c >= last - span]
            clusters = [head]
            for c in cs:
                if c in head or c in tail:
                    continue
                if len(clusters) > 1 and c - clusters[-1][0] <= span:
                    clusters[-1].append(c)
                else:
                    clusters.append([c])
            clusters.append(tail)
            reps = []
            for k, cl in enumerate(clusters):
                r = 0 if k == 0 else last if k == len(clusters) - 1 else cl[(len(cl) - 1) // 2]
                reps.append(r)
                for c in cl:
                    self.rep[(pid, c)] = r
            self.reps[pid] = reps
        uf = _UF()
        self.gaps = 0
        for k1, k2 in self.unions:
            r1, r2 = (k1[0], self.rep[k1]), (k2[0], self.rep[k2])
            if _dist(self._pt(r1), self._pt(r2)) > JOIN_MAX_M:
                self.gaps += 1
                continue
            uf.union(r1, r2)
        self.node = {}
        for pid, reps in self.reps.items():
            for r in reps:
                self.node[(pid, r)] = uf.find((pid, r))
        # Segments, in piece order.
        self.segments = []
        self.seg_of = {}
        for pid in range(len(self.pieces)):
            reps = self.reps[pid]
            for r0, r1 in zip(reps, reps[1:]):
                pts = list(self.pieces[pid]["pts"][r0:r1 + 1])
                n0, n1 = self.node[(pid, r0)], self.node[(pid, r1)]
                pts[0], pts[-1] = self._pt(n0), self._pt(n1)
                seg = {"piece": pid, "r0": r0, "r1": r1, "pts": pts, "nodes": (n0, n1), "routes": set(),
                       "index": len(self.segments)}
                self.seg_of[(pid, r0)] = seg["index"]
                self.segments.append(seg)
        # Each shape's path as segments in travel order.
        self.seg_paths = {}
        for sid, path in self.paths.items():
            out = []
            for pid, a, b in path:
                ra, rb = self.rep[(pid, a)], self.rep[(pid, b)]
                if ra == rb:
                    continue
                reps = self.reps[pid]
                ia, ib = reps.index(ra), reps.index(rb)
                if ia < ib:
                    seq = [(self.seg_of[(pid, reps[k])], 1) for k in range(ia, ib)]
                else:
                    seq = [(self.seg_of[(pid, reps[k])], -1) for k in range(ia - 1, ib - 1, -1)]
                for item in seq:
                    if not out or out[-1] != item:
                        out.append(item)
            self.seg_paths[sid] = out


# -- slot order ----------------------------------------------------------------------------------------------------

class Network:
    """Segments with their routes, nodes, continuations and slot orders."""

    def __init__(self, corridors, shapes, route_rank, hub_points):
        self.c = corridors
        self.route_of = {s["shape_id"]: s["route_id"] for s in shapes}
        self.rank = route_rank
        segs = corridors.segments
        for sid, path in corridors.seg_paths.items():
            for si, _ in path:
                segs[si]["routes"].add(self.route_of[sid])
        # Drop segments no route uses (possible only for degenerate input).
        self.segs = [s for s in segs if s["routes"]]
        remap = {s["index"]: k for k, s in enumerate(self.segs)}
        self.paths = {sid: [(remap[si], d) for si, d in path if si in remap] for sid, path in corridors.seg_paths.items()}
        for k, s in enumerate(self.segs):
            s["id"] = k
            s["length"] = length(s["pts"])
            mid = point_at(s["pts"], 0.5)
            s["hub"] = any(_dist(mid, h) <= HUB_SEGMENT_M for h in hub_points)
            s["outside_hubs"] = self._outside(s["pts"], hub_points)
            s["into"] = (_heading_into(s["pts"], False), _heading_into(s["pts"], True))
        self.hub_nodes = {n for s in self.segs if s["hub"] for n in s["nodes"]}
        self._continuations()
        self._groups()

    @staticmethod
    def _outside(pts, hubs):
        total = 0.0
        for a, b in zip(pts, pts[1:]):
            m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            if not any(_dist(m, h) <= HUB_RADIUS_M for h in hubs):
                total += _dist(a, b)
        return total

    def _continuations(self):
        cont = defaultdict(lambda: defaultdict(Counter))
        for sid, path in self.paths.items():
            r = self.route_of[sid]
            for (s1, d1), (s2, d2) in zip(path, path[1:]):
                e1 = 1 if d1 == 1 else 0
                e2 = 0 if d2 == 1 else 1
                if s1 == s2 or self.segs[s1]["nodes"][e1] != self.segs[s2]["nodes"][e2]:
                    continue
                cont[(s1, e1)][r][(s2, e2)] += 1
                cont[(s2, e2)][r][(s1, e1)] += 1
        self.cont = cont

    def _groups(self):
        """Cost terms: pair groups between two segment ends through a node, and turn groups at one end."""
        self.pair_groups = []
        self.turn_groups = []
        self.by_seg = defaultdict(list)
        seen = set()
        for (s1, e1), routes in sorted(self.cont.items()):
            node = self.segs[s1]["nodes"][e1]
            w = W_CROSS_HUB if node in self.hub_nodes else W_CROSS
            others = defaultdict(list)
            for r in sorted(routes):
                for (s2, e2) in sorted(routes[r]):
                    others[(s2, e2)].append(r)
            for (s2, e2), rs in sorted(others.items()):
                key = tuple(sorted(((s1, e1), (s2, e2))))
                if key in seen or len(rs) < 2:
                    continue
                seen.add(key)
                f = (1 if e1 == 1 else -1) * (1 if e2 == 0 else -1)
                g = {"kind": "pair", "s1": s1, "s2": s2, "f": f, "w": w,
                     "pairs": list(itertools.combinations(sorted(rs, key=self._rk), 2))}
                self.pair_groups.append(g)
                self.by_seg[s1].append(g)
                if s2 != s1:
                    self.by_seg[s2].append(g)
            # Turns: routes leaving this end for different segments must sit on the side they turn to.
            arrive = tuple(-v for v in self.segs[s1]["into"][e1])
            main = {}
            for r in sorted(routes):
                (s2, e2), _count = min(routes[r].items(), key=lambda kv: (-kv[1], kv[0]))
                main[r] = ((s2, e2), _turn(arrive, self.segs[s2]["into"][e2]))
            left_of = []
            for a, b in itertools.combinations(sorted(main, key=self._rk), 2):
                (ta, tha), (tb, thb) = main[a], main[b]
                if ta == tb or abs(tha - thb) <= TURN_DEG:
                    continue
                left_of.append((a, b) if tha > thb else (b, a))
            if left_of:
                g = {"kind": "turn", "s": s1, "sign": 1 if e1 == 1 else -1, "w": w, "left_of": left_of}
                self.turn_groups.append(g)
                self.by_seg[s1].append(g)

    def _rk(self, r):
        return (self.rank.get(r, 10 ** 6), r)

    # Cost of one group given slot maps.
    @staticmethod
    def _gcost(g, slots):
        cost = 0
        if g["kind"] == "pair":
            S1, S2, f, w = slots[g["s1"]], slots[g["s2"]], g["f"], g["w"]
            for a, b in g["pairs"]:
                x, y = S1[a] - S1[b], S2[a] - S2[b]
                if x * y * f < 0:
                    cost += w
                if (abs(x) == 1) != (abs(y) == 1):
                    cost += W_SEP
        else:
            S, sg, w = slots[g["s"]], g["sign"], g["w"]
            for a, b in g["left_of"]:
                if (S[a] - S[b]) * sg > 0:
                    cost += w
        return cost

    def total_cost(self, slots):
        return sum(self._gcost(g, slots) for g in self.pair_groups) + sum(self._gcost(g, slots) for g in self.turn_groups)

    def seg_cost(self, s, slots):
        return sum(self._gcost(g, slots) for g in self.by_seg[s])

    def start_orders(self, kind):
        orders = []
        for s in self.segs:
            rs = sorted(s["routes"], key=self._rk)
            if kind == 1:
                rs = rs[::-1]
            elif kind == 2:
                # Left turners (at the segment's far end) to the left.
                turn = {}
                cont = self.cont.get((s["id"], 1), {})
                arrive = tuple(-v for v in s["into"][1])
                for r in rs:
                    if r in cont:
                        (s2, e2), _ = min(cont[r].items(), key=lambda kv: (-kv[1], kv[0]))
                        turn[r] = _turn(arrive, self.segs[s2]["into"][e2])
                    else:
                        turn[r] = 0.0
                rs = sorted(rs, key=lambda r: (-round(turn[r], 6), self._rk(r)))
            orders.append(rs)
        return orders

    @staticmethod
    def slots_of(orders):
        return [{r: i for i, r in enumerate(o)} for o in orders]

    def _improve(self, s, orders, slots):
        cur = orders[s]
        n = len(cur)
        if n < 2 or not self.by_seg[s]:
            return False
        base = self.seg_cost(s, slots)
        if base == 0:
            return False
        best, best_cost = None, base
        if n <= EXACT_MAX:
            for perm in itertools.permutations(cur):
                slots[s] = {r: i for i, r in enumerate(perm)}
                c = self.seg_cost(s, slots)
                if c < best_cost:
                    best, best_cost = list(perm), c
                    if c == 0:
                        break
            if best is None:
                slots[s] = {r: i for i, r in enumerate(cur)}
                return False
            orders[s] = best
            slots[s] = {r: i for i, r in enumerate(best)}
            return True
        improved = False
        for _ in range(200):
            move = None
            for i in range(n):
                for j in range(n):
                    if i == j:
                        continue
                    trial = cur[:i] + cur[i + 1:]
                    trial.insert(j, cur[i])
                    slots[s] = {r: k for k, r in enumerate(trial)}
                    c = self.seg_cost(s, slots)
                    if c < best_cost:
                        move, best_cost = trial, c
            if move is None:
                break
            cur, improved = move, True
            slots[s] = {r: k for k, r in enumerate(cur)}
        orders[s] = cur
        slots[s] = {r: k for k, r in enumerate(cur)}
        return improved

    def order(self):
        """Crossing-optimal slot orders by local search from three deterministic starts."""
        results = []
        for kind in range(3):
            orders = self.start_orders(kind)
            slots = self.slots_of(orders)
            start_cost = self.total_cost(slots)
            sweeps = 0
            for sweeps in range(1, SWEEPS + 1):
                if not any([self._improve(s["id"], orders, slots) for s in self.segs]):
                    break
            results.append((self.total_cost(slots), kind, orders, start_cost, sweeps))
        best = min(results, key=lambda r: (r[0], r[1]))
        self.orders = best[2]
        return {"cost": best[0], "start": best[1], "start_cost": results[0][3], "sweeps": best[4],
                "costs": [r[0] for r in results]}

    # -- neighbors and the color pass -------------------------------------------------------------------------------

    def neighbors(self, orders=None):
        orders = orders or self.orders
        adj, shared = Counter(), Counter()
        for s, o in zip(self.segs, orders):
            for a, b in zip(o, o[1:]):
                adj[tuple(sorted((a, b)))] += s["length"]
            for a, b in itertools.combinations(sorted(o), 2):
                shared[(a, b)] += s["outside_hubs"]
        out = defaultdict(set)
        for (a, b), m in adj.items():
            if m >= ADJACENT_M:
                out[a].add(b)
                out[b].add(a)
        for (a, b), m in shared.items():
            if m >= SHARED_M:
                out[a].add(b)
                out[b].add(a)
        return {r: out[r] for r in sorted(out)}

    def color_pass(self, colors):
        """Swap routes on a segment where it leaves the crossing cost unchanged,
        creates no clash between adjacent slots, and separates adjacent colors
        better (the worst adjacent pair first)."""
        orders = [list(o) for o in self.orders]
        slots = self.slots_of(orders)
        sep = {}

        def s_of(a, b):
            k = (colors[a], colors[b])
            if k not in sep:
                sep[k] = 0.0 if k[0] == k[1] else route_colors.separation(*k)
            return sep[k]

        def quality(o):
            return sorted(round(s_of(a, b), 9) for a, b in zip(o, o[1:]))

        def clashing(o):
            return {frozenset((a, b)) for a, b in zip(o, o[1:]) if s_of(a, b) < 1.0}

        swaps = 0
        for s in self.segs:
            k = s["id"]
            o = orders[k]
            if len(o) < 2:
                continue
            for _ in range(len(o) * len(o)):
                base = self.seg_cost(k, slots)
                q0 = quality(o)
                had = clashing(o)
                best = None
                for i, j in itertools.combinations(range(len(o)), 2):
                    t = list(o)
                    t[i], t[j] = t[j], t[i]
                    if not clashing(t) <= had:
                        continue
                    slots[k] = {r: n for n, r in enumerate(t)}
                    if self.seg_cost(k, slots) != base:
                        continue
                    q = quality(t)
                    if q > q0 and (best is None or q > best[0]):
                        best = (q, t)
                slots[k] = {r: n for n, r in enumerate(o)}
                if best is None:
                    break
                o = best[1]
                orders[k] = o
                slots[k] = {r: n for n, r in enumerate(o)}
                swaps += 1
        return orders, swaps


# -- the build (pure) ----------------------------------------------------------------------------------------------

def input_hash(shapes, dormant, route_order, hub_stops):
    """sha256 of everything the ribbons depend on: active shapes, the dormant set,
    the display order, the hub stops and the parameters."""
    doc = {
        "algo": ALGO, "params": PARAMS, "dormant": sorted(dormant), "routes": list(route_order),
        "shapes": sorted([s["shape_id"], s["route_id"], [[round(x, 7), round(y, 7)] for x, y in s["coords"]]]
                         for s in shapes),
        "hubs": sorted([h["stop_id"], round(h["lon"], 7), round(h["lat"], 7)] for h in hub_stops),
    }
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def colors_hash(colors):
    doc = sorted((r, c) for r, c in colors.items() if c)
    return hashlib.sha256(json.dumps(doc, separators=(",", ":")).encode()).hexdigest()


def build_id(ihash, colors):
    return f"{ihash[:16]}-{colors_hash(colors)[:8]}"


def build(shapes, route_order, stored, hub_stops=(), dormant=(), pinned=(), mode=route_colors.DEFAULT_MODE,
          all_routes=None):
    """The whole build, without the database.

    shapes: [{'shape_id', 'route_id', 'coords': [(lon, lat), ...]}] (active ones).
    route_order: route ids in display order. stored: route -> current color.
    hub_stops: [{'stop_id', 'lon', 'lat'}] served by HUB_ROUTES or more routes.
    dormant: routes with no bus in DORMANT_DAYS days: no slot, color kept.
    all_routes: every active route (default: route_order), for the per-color cap.

    Returns a dict: segments (lon/lat, routes left to right), colors, build id,
    neighbors, cost and stats.
    """
    t0 = time.monotonic()
    dormant = set(dormant)
    all_routes = list(all_routes or route_order)
    live = [s for s in shapes if s["route_id"] not in dormant and len(s["coords"]) >= 2]
    xy = [{"shape_id": s["shape_id"], "route_id": s["route_id"], "xy": [to_utm(*c) for c in s["coords"]]}
          for s in live]
    hubs = [to_utm(h["lon"], h["lat"]) for h in hub_stops]
    rank = {r: i for i, r in enumerate(route_order)}
    corridors = Corridors(xy)
    net = Network(corridors, xy, rank, hubs)
    order_stats = net.order()
    t_order = time.monotonic()

    nb = net.neighbors()
    # Dormant routes keep their color (and count toward the cap); every other route takes part.
    fixed = {r: stored[r] for r in all_routes if r in dormant and stored.get(r)}
    variables = [r for r in route_order if r not in fixed]
    colors, info = route_colors.assign(variables, nb, stored, mode=mode, pinned=set(pinned), fixed=fixed,
                                       n_routes=len(set(all_routes) | set(route_order)))
    final_orders, swaps = net.color_pass(colors)
    cost = net.total_cost(net.slots_of(final_orders))
    final_nb = net.neighbors(final_orders)
    colors = {r: colors.get(r) or stored.get(r) for r in all_routes}

    segments = []
    for s, o in zip(net.segs, final_orders):
        pts = simplify(s["pts"])
        segments.append({"id": s["id"] + 1, "coords": [[round(v, 7) for v in from_utm(*p)] for p in pts],
                         "routes": list(o), "length_m": round(s["length"], 1), "hub": s["hub"]})
    ih = input_hash(shapes, dormant, route_order, hub_stops)
    return {
        "build": build_id(ih, colors), "input_hash": ih, "segments": segments, "colors": colors,
        "neighbors": {r: sorted(v) for r, v in final_nb.items()},
        "assignment": info, "clashes": route_colors.clashes({r: c for r, c in colors.items() if c}, final_nb),
        "paths": {sid: [(net.segs[si]["id"] + 1, d) for si, d in p] for sid, p in net.paths.items()},
        "stats": {"segments": len(segments), "cost": cost, "cost_before_colors": order_stats["cost"],
                  "start_cost": order_stats["start_cost"], "start": order_stats["start"],
                  "start_costs": order_stats["costs"], "sweeps": order_stats["sweeps"], "swaps": swaps,
                  "max_routes": max((len(s["routes"]) for s in segments), default=0),
                  "pieces": len(corridors.pieces), "node_gaps": corridors.gaps,
                  "seconds": round(time.monotonic() - t0, 2), "order_seconds": round(t_order - t0, 2)},
    }


def ribbons_json(result):
    """The stored part of a build, canonically serialized (for byte-identical checks)."""
    return json.dumps({"build": result["build"], "segments": result["segments"]}, separators=(",", ":"))


# -- the database --------------------------------------------------------------------------------------------------

def load_inputs(conn):
    from .sources import vrt_gtfs
    has_pin = conn.execute(
        """select exists (select 1 from information_schema.columns
                          where table_schema = 'core' and table_name = 'transit_route' and column_name = 'color_pinned')"""
    ).fetchone()[0]
    rows = conn.execute(
        f"""select route_id, short_name, sort_order, color, {'color_pinned' if has_pin else 'false'}
            from core.transit_route where active""").fetchall()
    routes = [{"route_id": r[0], "short_name": r[1], "sort_order": r[2]} for r in rows]
    shapes = [{"shape_id": sid, "route_id": rid, "coords": [tuple(c) for c in json.loads(g)["coordinates"]]}
              for sid, rid, g in conn.execute(
                  """select s.shape_id, s.route_id, ST_AsGeoJSON(s.geom, 9)
                     from core.transit_shape s join core.transit_route r on r.route_id = s.route_id and r.active
                     where s.active order by s.shape_id""").fetchall()]
    hubs = [{"stop_id": sid, "lon": lon, "lat": lat} for sid, lon, lat in conn.execute(
        """select stop_id, ST_X(geom), ST_Y(geom) from core.transit_stop
           where active and cardinality(route_ids) >= %s order by stop_id""", (HUB_ROUTES,)).fetchall()]
    return {"routes": routes, "order": vrt_gtfs.route_order(routes), "names": {r[0]: r[1] for r in rows},
            "stored": {r[0]: r[3] for r in rows}, "pinned": {r[0] for r in rows if r[4]},
            "shapes": shapes, "hubs": hubs}


def dormant_routes(conn, now=None):
    """Active routes with no fix attributed to them in DORMANT_DAYS days, once the
    positions table spans that long (a fresh database marks nothing dormant)."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=DORMANT_DAYS)
    first = conn.execute("select min(ts) from obs.vehicle_position").fetchone()[0]
    if first is None or first > since:
        return set()
    rows = conn.execute(
        """select r.route_id from core.transit_route r
           where r.active
             and not exists (select 1 from obs.vehicle_position p
                             where p.route_id = r.route_id and p.ts > %(since)s and p.ts <= %(now)s)
             and not exists (select 1 from obs.trip_route_match m
                             where m.route_id = r.route_id
                               and m.service_date >= (%(since)s at time zone 'America/Boise')::date)""",
        {"since": since, "now": now}).fetchall()
    return {r[0] for r in rows}


def stored_build(conn):
    rows = conn.execute("select distinct build from core.transit_ribbon").fetchall()
    return rows[0][0] if len(rows) == 1 else None


def store(conn, result):
    """Replace the ribbons and update route colors, inside a savepoint."""
    with conn.transaction():
        conn.execute("delete from core.transit_ribbon")
        with conn.cursor() as cur:
            cur.executemany(
                """insert into core.transit_ribbon (segment_id, geom, routes, length_m, hub, build)
                   values (%s, ST_GeomFromText(%s, 4326), %s, %s, %s, %s)""",
                [(s["id"], "LINESTRING(" + ",".join(f"{x:.7f} {y:.7f}" for x, y in s["coords"]) + ")",
                  s["routes"], s["length_m"], s["hub"], result["build"]) for s in result["segments"]])
        for route_id, color in sorted(result["colors"].items()):
            if color:
                conn.execute(
                    """update core.transit_route set color = %s, text_color = %s
                       where route_id = %s and (color is distinct from %s or text_color is distinct from %s)""",
                    (color, route_colors.badge_text_color(color), route_id, color,
                     route_colors.badge_text_color(color)))


def run(conn, force=False, mode=route_colors.DEFAULT_MODE, dry_run=False, now=None, log=print):
    """Rebuild the ribbons and colors if their inputs changed. Never raises for a
    failed build: it logs, keeps the previous ribbons and says so."""
    if conn.execute("select to_regclass('core.transit_ribbon')").fetchone()[0] is None:
        return {"ribbons": "skipped (no core.transit_ribbon: migration 0006)"}
    inputs = load_inputs(conn)
    dormant = dormant_routes(conn, now)
    ih = input_hash([s for s in inputs["shapes"]], dormant, inputs["order"], inputs["hubs"])
    current = stored_build(conn)
    if not force and current == build_id(ih, inputs["stored"]):
        return {"ribbons": "unchanged", "build": current}
    try:
        result = build(inputs["shapes"], inputs["order"], inputs["stored"], inputs["hubs"], dormant,
                       inputs["pinned"], mode)
    except Exception as e:   # keep the previous ribbons; never lose the feed load over this
        log(f"transit_ribbons: build failed, previous ribbons kept: {type(e).__name__}: {e}")
        return {"ribbons": "failed", "error": f"{type(e).__name__}: {e}"}
    changes = route_colors.report(inputs["stored"], result["colors"], inputs["names"])
    st = result["stats"]
    stats = {"ribbons": "dry run" if dry_run else "built", "build": result["build"], "mode": mode,
             "segments": st["segments"], "cost": st["cost"], "max routes": st["max_routes"],
             "dormant": ",".join(sorted(dormant)) or "none", "colors changed": len(changes),
             "clashes": len(result["clashes"]), "seconds": st["seconds"]}
    if changes:
        log(f"transit_ribbons ({mode}{', dry run' if dry_run else ''}): colors old -> new\n" + "\n".join(changes))
    if dry_run:
        return stats
    try:
        store(conn, result)
    except Exception as e:
        log(f"transit_ribbons: storing failed, previous ribbons kept: {type(e).__name__}: {e}")
        return {"ribbons": "failed", "error": f"{type(e).__name__}: {e}"}
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest.transit_ribbons", description=__doc__.split("\n")[0])
    ap.add_argument("--force", action="store_true", help="rebuild even if the inputs are unchanged")
    ap.add_argument("--mode", choices=route_colors.MODES, default=route_colors.DEFAULT_MODE,
                    help=f"color assignment (default {route_colors.DEFAULT_MODE}, the owner's Q3 answer)")
    ap.add_argument("--dry-run", action="store_true", help="print what would change; write nothing")
    args = ap.parse_args(argv)
    from . import db
    with db.connect() as conn:
        stats = run(conn, force=args.force or args.dry_run, mode=args.mode, dry_run=args.dry_run)
        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
    print("transit_ribbons: " + ", ".join(f"{k} {v}" for k, v in stats.items()), flush=True)
    return 0 if stats.get("ribbons") != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
