"""The intersection build: one core.intersection per signalized intersection (owner, Oct 6, 2026).

Rebuilt daily by the ingest service (source 'intersections') and by hand with
`python3 -m ingest match-intersections`. It reads what the signal ingestors
stored and writes our own rows; it fetches nothing.

1. **Seeds:** one intersection per COMPASS Signalized_Intersections point
   (compass_signals), its control from COMPASS's type. Each is snapped to the
   junction of its two named streets in ACHD's centerlines (Ada) when that
   junction is within SNAP_M; a point whose named junction lies farther away
   stays put and loses SNAP_PENALTY confidence (point and names disagree).
   Junctions are where centerlines meet at a vertex (bridges don't count);
   names are matched by streets.same_street (local names for state routes,
   COMPASS's abbreviations and misspellings). A Synchro ID COMPASS lists on two
   points is kept off both.
2. **ACHD's 2022 poles** (achd_signal_points, kind signal_pole) attach to the
   nearest seed within POLE_ATTACH_M (SPUI_ATTACH_M for COMPASS's single-point
   urban interchanges, whose poles spread wider).
3. **COMPASS's Regional_Signals** traffic signals (compass_regional_signals)
   attach to the nearest seed within REGIONAL_MATCH_M. On Oct 6, 2026, 584 of
   its 586 traffic signals did, within 10 m: the layer confirms the 585 rather
   than adding to them.
4. **Leftovers become candidates:** leftover poles and Regional signals are
   clustered together at CLUSTER_M; a group with 3+ poles or a Regional signal
   becomes a candidate intersection, snapped to the nearest junction of two
   named streets within SNAP_M.
5. **OpenStreetMap** signal nodes (core.osm_node, kind traffic_signals) attach
   to the nearest intersection within OSM_ATTACH_M; leftovers are clustered at
   CLUSTER_M into further candidates.
6. **Confidence:** sources agreeing (COMPASS, ACHD, OSM): three 1.0, two 0.85;
   COMPASS alone 0.7, Regional_Signals alone 0.5, ACHD alone 0.5, OSM alone
   0.4; minus SNAP_PENALTY as above. ACHD's 2022 poles with Regional_Signals
   and nothing current score only CONFIDENCE_OLD_PAIR (a signal since removed
   looks like that). Below ACTIVE_MIN an intersection is a 'candidate' (the
   review list).
7. **Reviews:** decisions on candidates (owner's lead, Oct 6) live in
   ingest/intersection_reviews.json. Each sets the status of the built
   intersection nearest its point within REVIEW_M ('retired' with a reason,
   or 'candidate'), until that intersection gains a source the review lists in
   reopen_on; then the review stops applying and the report says so. Devices
   aren't linked to an intersection a review retired.
8. **Stable IDs:** built intersections take the ID of an existing row with the
   same ACHD Synchro ID, else of the nearest existing row within STABLE_M. Rows
   are never deleted; one whose sources are all gone is 'retired'. A build
   with less than MIN_SHARE of the intersections held is refused (an emptied
   source shouldn't retire the network).

Then: COMPASS's per-approach fields go to core.approach (its northbound
approach is the south leg); pedestrian signals, flashers and fire signals are
linked to the nearest intersection within OTHER_ATTACH_M (not counted as
evidence); each ACHD camera links to the nearest intersection within CAMERA_M
whose name shares a street with the camera's, and a freeway camera (an
interstate in its name) otherwise to the nearest interchange signal within
INTERCHANGE_CAMERA_M (core.source_link); each rail crossing gets the nearest
active signalized intersection within CROSSING_M, with the distance, so an
analysis can pick its own cut (e.g. 61 m, the MUTCD's 200 ft for preemption).

Licensing: once OpenStreetMap signal nodes confirm or create intersections,
core.intersection holds positions, evidence and (for OSM-only candidates)
names derived from OpenStreetMap, so the table is an ODbL derivative
database: credit "© OpenStreetMap contributors", and anything published from
it stays ODbL. Until COMPASS answers, it's also internal only.

Distances are in UTM 11N metres (EPSG:26911), as in transit_match.py.
"""

import json
import math
import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from plugins.roads.ingest import streets

from . import db
from .utm import to_utm

UTM = 26911
SNAP_M = 40
JUNCTION_SEARCH_M = 150
JUNCTION_GROUP_M = 50          # junction points of divided roads within this form one junction
TOUCH_M = 1.0                  # centerlines this close count as meeting
NODE_M = 1.5                   # ... if one of them has a vertex this close (not a bridge)
POLE_ATTACH_M = 60
SPUI_ATTACH_M = 120            # a single-point urban interchange spreads its poles wider
REGIONAL_MATCH_M = 40
CLUSTER_M = 45
POLE_CANDIDATE_MIN = 3
OSM_ATTACH_M = 60
OTHER_ATTACH_M = 60
STABLE_M = 30
CAMERA_M = 80
INTERCHANGE_CAMERA_M = 150     # a freeway camera to its interchange's signal (the SPUI reach)
CROSSING_M = 300
REVIEW_M = 50
REVIEWS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "intersection_reviews.json")
ACTIVE_MIN = 0.6
SNAP_PENALTY = 0.1
MIN_SHARE = 0.5                # a build with less than half the intersections held is refused
CONFIDENCE_AGREE = {3: 1.0, 2: 0.85}
CONFIDENCE_ALONE = {"compass": 0.7, "compass_regional": 0.5, "achd_2022": 0.5, "osm": 0.4}
CONFIDENCE_OLD_PAIR = 0.55     # ACHD 2022 + Regional_Signals only: both old snapshots
NO_NAME_CLASSES = {"Driveway", "Alley", "Parks"}
UNNAMED = "Signal near"        # a candidate no two named streets meet at: 'Signal near 43.64782, -116.48638'

SEED_SOURCE = "compass_signals"
REGIONAL_SOURCE = "compass_regional_signals"
ACHD_SOURCE = "achd_signal_points"
OSM_SOURCE = "osm_valley"          # builder of core.osm_node; its links are written only if it's registered
CAMERA_SOURCE = "achd_cameras"
DEVICE_SOURCES = [SEED_SOURCE, REGIONAL_SOURCE, ACHD_SOURCE]

SOURCE = {
    "name": "intersections",
    "title": "Intersection build (COMPASS signals, ACHD 2022 signal poles, OpenStreetMap signal nodes)",
    "url": "https://github.com/Benten-Ben/treasure-valley-traffic/blob/main/ingest/intersections.py",
    "access": "open",
    "schedule": "1 day",
    "license": "derived",
    "credit": "COMPASS; Ada County Highway District; © OpenStreetMap contributors",
    "notes": "Derived, fetches nothing: rebuilt from core.signal_device and core.osm_node, with the reviews in "
             "ingest/intersection_reviews.json. Internal until COMPASS answers; once OpenStreetMap nodes confirm "
             "or create intersections, an ODbL derivative database (credit OpenStreetMap contributors).",
}


# --- inputs ----------------------------------------------------------------------------------

@dataclass
class Device:
    id: int
    source: str
    source_id: str
    kind: str
    name: str | None
    x: float
    y: float
    lon: float
    lat: float
    attrs: dict = field(default_factory=dict)


@dataclass
class OsmNode:
    osm_id: int
    x: float
    y: float
    lon: float
    lat: float


@dataclass
class Segment:
    id: int
    name: str
    cls: str | None
    parts: list              # [[(x, y), ...], ...]: a MultiLineString's lines, kept apart
    core: str = ""

    def __post_init__(self):
        self.core = streets.core(self.name)


@dataclass
class Existing:
    id: int
    synchro: int | None
    x: float
    y: float
    status: str


@dataclass
class Review:
    """A reviewed decision (ingest/intersection_reviews.json), its point in metres."""
    key: str
    name: str
    status: str
    reason: str
    x: float
    y: float
    reopen_on: set = field(default_factory=lambda: {"compass"})
    evidence: list = field(default_factory=list)
    decided: str | None = None


def load_reviews(path=REVIEWS_FILE):
    """The reviews file as Review objects (points from 'lat,lon' keys to UTM 11N)."""
    with open(path) as f:
        data = json.load(f)
    out = []
    for r in data.get("reviews", []):
        if r["status"] not in ("retired", "candidate", "active"):
            raise ValueError(f"review {r['key']}: unknown status {r['status']!r}")
        lat, lon = (float(v) for v in r["key"].split(","))
        x, y = to_utm(lon, lat)
        out.append(Review(r["key"], r.get("name", ""), r["status"], r.get("reason", ""), x, y,
                          set(r.get("reopen_on", ["compass"])), list(r.get("evidence", [])), r.get("decided")))
    return out


@dataclass
class Junction:
    x: float
    y: float
    dist: float              # from the point it was looked up for
    name_a: str
    name_b: str


@dataclass
class Built:
    x: float
    y: float
    lon: float
    lat: float
    name: str = ""
    control: str = "signal"
    operator: str | None = None
    owner: str | None = None
    county: str | None = None
    city: str | None = None
    synchro: int | None = None
    coord_group: str | None = None
    evidence: set = field(default_factory=set)
    seed: Device | None = None
    spui: bool = False                   # a single-point urban interchange (COMPASS names them '... SPUI')
    snapped: bool = False
    snap_m: float | None = None          # from the source point to its named junction, when one was found
    devices: list = field(default_factory=list)      # [(Device, distance)]: evidence and other devices
    osm: list = field(default_factory=list)          # [(OsmNode, distance)]
    streets: set = field(default_factory=set)        # core street names, for camera matching
    approaches: dict = field(default_factory=dict)
    confidence: float = 0.0
    status: str = "candidate"
    review: Review | None = None                     # a reviewed decision that applies to it
    id: int | None = None

    @property
    def penalized(self):
        return self.snap_m is not None and self.snap_m > SNAP_M

    @property
    def reviewed_out(self):
        """Retired by a review: kept as a row, but nothing links to it."""
        return self.review is not None and self.review.status == "retired"


# --- geometry --------------------------------------------------------------------------------

def dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def _clamp(v):
    return 0.0 if v < 0 else 1.0 if v > 1 else v


def closest_between(p1, p2, q1, q2):
    """Closest points of segments p1-p2 and q1-q2: (distance, midpoint of the two)."""
    d1x, d1y = p2[0] - p1[0], p2[1] - p1[1]
    d2x, d2y = q2[0] - q1[0], q2[1] - q1[1]
    rx, ry = p1[0] - q1[0], p1[1] - q1[1]
    a, e, f = d1x * d1x + d1y * d1y, d2x * d2x + d2y * d2y, d2x * rx + d2y * ry
    eps = 1e-9
    if a <= eps and e <= eps:
        s = t = 0.0
    elif a <= eps:
        s, t = 0.0, _clamp(f / e)
    else:
        c = d1x * rx + d1y * ry
        if e <= eps:
            s, t = _clamp(-c / a), 0.0
        else:
            b = d1x * d2x + d1y * d2y
            denom = a * e - b * b
            s = _clamp((b * f - c * e) / denom) if denom > eps else 0.0
            t = (b * s + f) / e
            if t < 0:
                s, t = _clamp(-c / a), 0.0
            elif t > 1:
                s, t = _clamp((b - c) / a), 1.0
    c1 = (p1[0] + d1x * s, p1[1] + d1y * s)
    c2 = (q1[0] + d2x * t, q1[1] + d2y * t)
    return dist(*c1, *c2), ((c1[0] + c2[0]) / 2, (c1[1] + c2[1]) / 2)


def point_segment(px, py, a, b):
    d, _ = closest_between((px, py), (px, py), a, b)
    return d


class Grid:
    """Points or boxes in square cells, for "what's near here" lookups."""

    def __init__(self, cell=100.0):
        self.cell, self.cells = cell, defaultdict(list)

    def _range(self, x0, y0, x1, y1):
        c = self.cell
        for i in range(math.floor(x0 / c), math.floor(x1 / c) + 1):
            for j in range(math.floor(y0 / c), math.floor(y1 / c) + 1):
                yield i, j

    def add(self, item, x0, y0, x1=None, y1=None):
        for k in self._range(x0, y0, x0 if x1 is None else x1, y0 if y1 is None else y1):
            self.cells[k].append(item)

    def near(self, x, y, r):
        seen = set()
        for k in self._range(x - r, y - r, x + r, y + r):
            for item in self.cells.get(k, ()):
                if id(item) not in seen:
                    seen.add(id(item))
                    yield item


class Roads:
    """Named road centerlines (in metres), to find where two named streets meet."""

    def __init__(self, segments):
        self.grid = Grid(100.0)
        for s in segments:
            for part in s.parts:
                for a, b in zip(part, part[1:]):
                    self.grid.add((s, a, b), min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))

    def pieces_near(self, x, y, r, exclude=()):
        return [p for p in self.grid.near(x, y, r)
                if p[0].cls not in exclude and point_segment(x, y, p[1], p[2]) <= r]

    @staticmethod
    def meets(a1, a2, b1, b2):
        """Where two centerline pieces meet at grade, or None. ACHD's centerlines are split
        where streets join, so a real junction has a vertex of one line or the other there;
        a bridge crosses mid-piece and doesn't count."""
        d, (mx, my) = closest_between(a1, a2, b1, b2)
        if d > TOUCH_M:
            return None
        if min(dist(mx, my, *p) for p in (a1, a2, b1, b2)) > NODE_M:
            return None
        return mx, my

    @classmethod
    def _meetings(cls, pieces_a, pieces_b):
        out = []
        for sa, a1, a2 in pieces_a:
            for sb, b1, b2 in pieces_b:
                if sa is sb:
                    continue
                m = cls.meets(a1, a2, b1, b2)
                if m:
                    out.append((m[0], m[1], sa, sb))
        return out

    @staticmethod
    def _centre(x, y, meetings):
        """The junction nearest (x, y), as the centre of the meeting points near it (a divided
        road meets a cross street twice)."""
        if not meetings:
            return None
        mx, my, sa, sb = min(meetings, key=lambda m: dist(x, y, m[0], m[1]))
        group = [m for m in meetings if dist(mx, my, m[0], m[1]) <= JUNCTION_GROUP_M]
        cx = sum(m[0] for m in group) / len(group)
        cy = sum(m[1] for m in group) / len(group)
        return Junction(cx, cy, dist(x, y, cx, cy), sa.name, sb.name)

    def named_junction(self, x, y, parts, r=JUNCTION_SEARCH_M):
        """Where two of the named streets meet nearest (x, y), within r: a Junction or None."""
        cores = []
        for p in parts:
            c = streets.core(p)
            if c and c not in cores:
                cores.append(c)
        if len(cores) < 2:
            return None
        pieces = self.pieces_near(x, y, r)
        best = None
        for i in range(len(cores)):
            for j in range(i + 1, len(cores)):
                if streets.same_street(cores[i], cores[j]):
                    continue
                pa = [p for p in pieces if streets.same_street(p[0].core, cores[i])]
                pb = [p for p in pieces if streets.same_street(p[0].core, cores[j])]
                jn = self._centre(x, y, self._meetings(pa, pb))
                if jn and (best is None or jn.dist < best.dist):
                    best = jn
        return best

    def nearest_junction(self, x, y, r=SNAP_M):
        """The nearest place two differently named streets meet, within r: a Junction or None."""
        pieces = self.pieces_near(x, y, r, exclude=NO_NAME_CLASSES)
        meetings = []
        for i, (sa, a1, a2) in enumerate(pieces):
            for sb, b1, b2 in pieces[i + 1:]:
                if sa is sb or streets.same_street(sa.core, sb.core):
                    continue
                m = self.meets(a1, a2, b1, b2)
                if m:
                    meetings.append((m[0], m[1], sa, sb))
        if not meetings:
            return None
        mx, my, sa, sb = min(meetings, key=lambda m: dist(x, y, m[0], m[1]))
        same_pair = [m for m in meetings if {m[2].core, m[3].core} == {sa.core, sb.core}]
        return self._centre(x, y, same_pair)


class Index:
    """Built intersections by position, for nearest-within lookups."""

    def __init__(self, items=()):
        self.grid = Grid(100.0)
        for b in items:
            self.add(b)

    def add(self, b):
        self.grid.add(b, b.x, b.y)

    def nearest(self, x, y, r, accept=None):
        """The nearest item within r (that accept(item, distance) allows): (item, distance) or (None, None)."""
        found = sorted(((dist(x, y, b.x, b.y), i, b) for i, b in enumerate(self.grid.near(x, y, r))),
                       key=lambda t: (t[0], t[1]))
        for d, _, b in found:
            if d <= r and (accept is None or accept(b, d)):
                return b, d
        return None, None


def cluster(points, r):
    """Single-linkage groups of points (objects with .x, .y) closer than r, as lists."""
    parent = list(range(len(points)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    grid = Grid(r)
    for i, p in enumerate(points):
        grid.add(i, p.x, p.y)
    for i, p in enumerate(points):
        for j in grid.near(p.x, p.y, r):
            if j > i and dist(p.x, p.y, points[j].x, points[j].y) <= r:
                parent[find(i)] = find(j)
    groups = defaultdict(list)
    for i, p in enumerate(points):
        groups[find(i)].append(p)
    return sorted(groups.values(), key=lambda g: (min(p.x for p in g), min(p.y for p in g)))


# --- the build -------------------------------------------------------------------------------

def _mean(items, attr):
    return sum(getattr(i, attr) for i in items) / len(items)


def _name_parts(name):
    return [streets.core(p) for p in streets.split_location(name or "") if streets.core(p)]


def _street_name(part, achd_name):
    """ACHD's full name for a street ('Fairview' -> 'Fairview Ave'), except for ramps and
    numbered routes, where the source's own words read better ('I-184 E Ramp')."""
    return streets.display(part if streets.route(streets.core(achd_name)) else achd_name)


def _snap_named(b, location, roads):
    """Snap b to the junction of its location's named streets. Returns the junction or None."""
    parts = streets.split_location(location or "")
    jn = roads.named_junction(b.x, b.y, parts) if roads else None
    if jn:
        b.snap_m = round(jn.dist, 1)
        if jn.dist <= SNAP_M:
            b.x, b.y, b.snapped = jn.x, jn.y, True
            b.streets |= {streets.core(jn.name_a), streets.core(jn.name_b)}
            if len(parts) == 2 and streets.same_street(streets.core(parts[0]), streets.core(jn.name_a)):
                b.name = f"{_street_name(parts[0], jn.name_a)} & {_street_name(parts[1], jn.name_b)}"
    return jn


def _snap_nearest(b, roads_list):
    """Name and place a nameless candidate by the nearest junction of two named streets."""
    for roads in roads_list:
        jn = roads.nearest_junction(b.x, b.y) if roads else None
        if jn:
            b.x, b.y, b.snapped = jn.x, jn.y, True
            b.name = f"{streets.display(jn.name_a)} & {streets.display(jn.name_b)}"
            b.streets |= {streets.core(jn.name_a), streets.core(jn.name_b)}
            return jn
    b.name = f"{UNNAMED} {b.lat:.5f}, {b.lon:.5f}"
    return None


def seed(d, roads):
    a = d.attrs or {}
    b = Built(d.x, d.y, d.lon, d.lat, name=streets.display_location(a.get("location")) or d.name or "",
              control=a.get("control") or "signal", operator=a.get("operator"), owner=a.get("owner"),
              county=a.get("county"), city=a.get("city"), synchro=a.get("synchro_id"),
              coord_group=a.get("coord_group"), evidence={"compass"}, seed=d,
              spui="SPUI" in streets.tokens(a.get("location")), approaches=a.get("approaches") or {})
    b.streets |= set(_name_parts(a.get("location")))
    _snap_named(b, a.get("location"), roads)
    if not b.name:
        b.name = f"{UNNAMED} {d.lat:.5f}, {d.lon:.5f}"
    b.devices.append((d, round(dist(d.x, d.y, b.x, b.y), 1)))
    return b


def score(b):
    """(confidence, status). COMPASS's two layers count as one source. Two sources agree at
    0.85, but if both are old snapshots (ACHD's 2022 poles and the undated Regional_Signals,
    with neither COMPASS's current layer nor OpenStreetMap), only OLD_PAIR: that's how a
    signal since removed looks."""
    families = set()
    if b.evidence & {"compass", "compass_regional"}:
        families.add("compass")
    if "achd_2022" in b.evidence:
        families.add("achd")
    if "osm" in b.evidence:
        families.add("osm")
    if len(families) >= 2 and not b.evidence & {"compass", "osm"}:
        c = CONFIDENCE_OLD_PAIR
    elif len(families) >= 2:
        c = CONFIDENCE_AGREE[min(len(families), 3)]
    elif "compass" in b.evidence:
        c = CONFIDENCE_ALONE["compass"]
    else:
        c = max((CONFIDENCE_ALONE[e] for e in b.evidence if e in CONFIDENCE_ALONE), default=0.0)
    if b.penalized:
        c -= SNAP_PENALTY
    c = round(max(0.0, min(1.0, c)), 2)
    return c, ("active" if c >= ACTIVE_MIN else "candidate")


def plan(seeds, poles, regional, others, osm_nodes, roads, osm_roads=None, reviews=()):
    """Build the intersections from the inputs (pure: no database). Returns (built, stats).

    seeds: COMPASS Signalized_Intersections devices; poles: ACHD signal poles; regional:
    Regional_Signals traffic signals; others: pedestrian signals, flashers, fire signals
    (linked, not evidence); osm_nodes: OpenStreetMap traffic-signal nodes; roads: Roads of
    ACHD centerlines (or None); osm_roads: Roads of OSM ways, used only to name candidates;
    reviews: Review decisions (load_reviews())."""
    stats = Counter()
    built = [seed(d, roads) for d in seeds]

    # A Synchro ID COMPASS lists twice can't identify either intersection.
    counts = Counter(b.synchro for b in built if b.synchro is not None)
    shared = sorted(s for s, n in counts.items() if n > 1)
    for b in built:
        if b.synchro in shared:
            b.synchro = None
    stats["snapped"] = sum(b.snapped for b in built)
    stats["far from named junction"] = sum(b.penalized for b in built)

    def pole_reach(b, d):
        return d <= (SPUI_ATTACH_M if b.spui else POLE_ATTACH_M)

    index = Index(built)
    leftovers = []
    for p in poles:
        b, d = index.nearest(p.x, p.y, max(POLE_ATTACH_M, SPUI_ATTACH_M), pole_reach)
        if b:
            b.devices.append((p, round(d, 1)))
            b.evidence.add("achd_2022")
            stats["poles attached"] += 1
        else:
            leftovers.append(p)

    regional_by_operator = defaultdict(lambda: [0, 0])
    regional_unmatched = []
    for r in regional:
        op = (r.attrs or {}).get("operator") or "(blank)"
        regional_by_operator[op][1] += 1
        b, d = index.nearest(r.x, r.y, REGIONAL_MATCH_M)
        if b and b.seed is not None:
            b.devices.append((r, round(d, 1)))
            b.evidence.add("compass_regional")
            regional_by_operator[op][0] += 1
        else:
            leftovers.append(r)
            regional_unmatched.append(r)

    for group in cluster(leftovers, CLUSTER_M):
        group_poles = [p for p in group if p.source == ACHD_SOURCE]
        group_regional = [p for p in group if p.source == REGIONAL_SOURCE]
        if len(group_poles) < POLE_CANDIDATE_MIN and not group_regional:
            stats["poles unattached"] += len(group_poles)
            continue
        if group_regional:
            r = group_regional[0]
            a = r.attrs or {}
            b = Built(r.x, r.y, r.lon, r.lat, name=streets.display_location(a.get("location")) or "",
                      operator=a.get("operator"), owner=a.get("owner"), county=a.get("county"), city=a.get("city"),
                      coord_group=a.get("coord_group"), evidence={"compass_regional"})
            b.streets |= set(_name_parts(a.get("location")))
            jn = _snap_named(b, a.get("location"), roads)
            if not b.name or (jn is None and not b.streets):
                _snap_nearest(b, [roads, osm_roads])
        else:
            b = Built(_mean(group_poles, "x"), _mean(group_poles, "y"), _mean(group_poles, "lon"),
                      _mean(group_poles, "lat"), evidence={"achd_2022"})
            _snap_nearest(b, [roads, osm_roads])
        if group_poles:
            b.evidence.add("achd_2022")
        for p in group:
            b.devices.append((p, round(dist(p.x, p.y, b.x, b.y), 1)))
        built.append(b)
        index.add(b)
        stats["candidates from ACHD and Regional leftovers"] += 1

    osm_left = []
    for n in osm_nodes:
        b, d = index.nearest(n.x, n.y, OSM_ATTACH_M)
        if b:
            b.osm.append((n, round(d, 1)))
            b.evidence.add("osm")
            stats["OSM nodes attached"] += 1
        else:
            osm_left.append(n)
    for group in cluster(osm_left, CLUSTER_M):
        b = Built(_mean(group, "x"), _mean(group, "y"), _mean(group, "lon"), _mean(group, "lat"), evidence={"osm"})
        _snap_nearest(b, [roads, osm_roads])
        b.osm = [(n, round(dist(n.x, n.y, b.x, b.y), 1)) for n in group]
        built.append(b)
        index.add(b)
        stats["candidates from OSM leftovers"] += 1

    for b in built:
        b.confidence, b.status = score(b)
        if not b.name.startswith(UNNAMED):
            b.streets |= set(_name_parts(b.name))
        b.streets.discard("")
    reviews_done = apply_reviews(built, reviews)
    stats["retired by review"] = sum(b.reviewed_out for b in built)

    live = Index(b for b in built if not b.reviewed_out)
    for o in others:
        b, d = live.nearest(o.x, o.y, OTHER_ATTACH_M)
        if b:
            b.devices.append((o, round(d, 1)))
            stats["other devices linked"] += 1

    stats["shared synchro ids"] = len(shared)
    return built, {"counts": dict(stats), "shared_synchro": shared, "reviews": reviews_done,
                   "regional_by_operator": {k: tuple(v) for k, v in sorted(regional_by_operator.items())},
                   "regional_unmatched": [(r.attrs.get("operator"), r.name, r.source_id) for r in regional_unmatched]}


def apply_reviews(built, reviews):
    """Set the status of each reviewed intersection (the nearest within REVIEW_M), unless it has
    gained one of the review's reopen_on sources since the review. Returns
    {'applied': [(Review, Built)], 'reopened': [(Review, Built, gained)], 'unmatched': [Review]}."""
    index = Index(built)
    done = {"applied": [], "reopened": [], "unmatched": []}
    for r in reviews:
        b, _ = index.nearest(r.x, r.y, REVIEW_M, lambda b, d: b.review is None)
        if b is None:
            done["unmatched"].append(r)
            continue
        gained = sorted((b.evidence - set(r.evidence)) & r.reopen_on)
        if gained:
            done["reopened"].append((r, b, gained))
            continue
        b.review, b.status = r, r.status
        done["applied"].append((r, b))
    return done


def assign_ids(built, existing):
    """Give built intersections the IDs of existing rows: same Synchro ID first, then the
    nearest unclaimed row within STABLE_M. Returns the existing rows left over (to retire)."""
    by_synchro = {e.synchro: e for e in existing if e.synchro is not None}
    used = set()
    for b in built:
        e = by_synchro.get(b.synchro) if b.synchro is not None else None
        if e and e.id not in used:
            b.id = e.id
            used.add(e.id)
    grid = Grid(100.0)
    for e in existing:
        if e.id not in used:
            grid.add(e, e.x, e.y)
    pairs = []
    for i, b in enumerate(built):
        if b.id is None:
            for e in grid.near(b.x, b.y, STABLE_M):
                d = dist(b.x, b.y, e.x, e.y)
                if d <= STABLE_M:
                    pairs.append((d, i, e))
    pairs.sort(key=lambda p: (p[0], p[1], p[2].id))
    for d, i, e in pairs:
        if built[i].id is None and e.id not in used:
            built[i].id = e.id
            used.add(e.id)
    return [e for e in existing if e.id not in used]


def _interstate(core):
    return (streets.route(core) or "").startswith("I ")


def interchange(b):
    """An interchange's signal: a SPUI, a ramp terminal, or a signal on an interstate's ramps."""
    return b.spui or bool(set(streets.tokens(b.name)) & {"RAMP", "EXIT", "TERMINAL", "IC", "SPUI"}) \
        or any(_interstate(s) for s in b.streets)


def link_cameras(built, cameras):
    """cameras: [(camera_id, name, x, y)]. -> {camera_id: (Built, distance, confidence, method)}: the
    nearest intersection within CAMERA_M whose name shares a street with the camera's; failing
    that, for a freeway camera (an interstate in its name), the nearest interchange signal within
    INTERCHANGE_CAMERA_M that shares a street with it."""
    index = Grid(100.0)
    for b in built:
        if b.status != "retired":
            index.add(b, b.x, b.y)
    out = {}
    for cam_id, name, x, y in cameras:
        cam_streets = _name_parts(name)
        freeway = any(_interstate(c) for c in cam_streets)
        best = None
        for b in index.near(x, y, INTERCHANGE_CAMERA_M if freeway else CAMERA_M):
            d = dist(x, y, b.x, b.y)
            if not streets.shares_street(cam_streets, b.streets):
                continue
            if d <= CAMERA_M:
                method = f"nearest_{CAMERA_M}m_street"
                shared = sum(1 for c in cam_streets if any(streets.same_street(c, s) for s in b.streets))
                conf = 1.0 if shared >= 2 else 0.8
            elif freeway and d <= INTERCHANGE_CAMERA_M and interchange(b):
                method, conf = f"interchange_{INTERCHANGE_CAMERA_M}m", 0.7
            else:
                continue
            rank = (method != f"nearest_{CAMERA_M}m_street", d)      # a street match within 80 m first
            if best is None or rank < best[0]:
                best = (rank, (b, round(d, 1), conf, method))
        if best:
            out[cam_id] = best[1]
    return out


def link_crossings(built, crossings):
    """crossings: [(crossing_row_id, x, y)]. -> {row_id: (Built, distance)} for the nearest active
    intersection within CROSSING_M."""
    index = Index(b for b in built if b.status == "active")
    out = {}
    for cid, x, y in crossings:
        b, d = index.nearest(x, y, CROSSING_M)
        if b:
            out[cid] = (b, round(d, 1))
    return out


# --- the database side -----------------------------------------------------------------------

def _area(area, col="geom"):
    """A bounding-box filter (lon/lat) on col, or 'true'. Tests build in a small synthetic area."""
    if not area:
        return "true", {}
    return (f"{col} && ST_MakeEnvelope(%(ax0)s, %(ay0)s, %(ax1)s, %(ay1)s, 4326)",
            {"ax0": area[0], "ay0": area[1], "ax1": area[2], "ay1": area[3]})


def _xy(col):
    return (f"ST_X(ST_Transform({col}, {UTM})), ST_Y(ST_Transform({col}, {UTM})), "
            f"ST_X({col}), ST_Y({col})")


def load(conn, area=None):
    where, params = _area(area)
    devices = [Device(*r[:9], attrs=r[9] or {}) for r in conn.execute(
        f"""select id, source, source_id, kind, name, {_xy('geom')}, attributes
            from core.signal_device where active and source = any(%(sources)s) and {where}
            order by source, source_id""",
        {**params, "sources": DEVICE_SOURCES}).fetchall()]
    seeds = [d for d in devices if d.source == SEED_SOURCE]
    poles = [d for d in devices if d.source == ACHD_SOURCE and d.kind == "signal_pole"]
    regional = [d for d in devices if d.source == REGIONAL_SOURCE and d.kind == "signal_intersection"]
    others = [d for d in devices if d.kind not in ("signal_pole", "signal_intersection")]
    osm_nodes = [OsmNode(*r) for r in conn.execute(
        f"""select osm_id, {_xy('geom')} from core.osm_node
            where active and kind = 'traffic_signals' and {where} order by osm_id""", params).fetchall()]
    segs = [Segment(i, n, c, [[tuple(p) for p in line] for line in json.loads(g)["coordinates"]])
            for i, n, c, g in conn.execute(
                f"""with pts as (select geom from core.signal_device where active and source = any(%(sources)s) and {where}
                                 union all select geom from core.osm_node where active and kind = 'traffic_signals' and {where})
                    select distinct on (s.id) s.id, s.name, s.functional_class, ST_AsGeoJSON(ST_Transform(s.geom, {UTM}), 2)
                    from pts p join core.road_segment s on s.geom && ST_Expand(p.geom, 0.0025)
                    where s.active and s.name is not null""",
                {**params, "sources": DEVICE_SOURCES}).fetchall()]
    roads = Roads(segs) if segs else None
    osm_roads = None
    if conn.execute("select exists (select 1 from core.osm_way)").fetchone()[0]:
        ways = [Segment(i, n, h, [[tuple(p) for p in json.loads(g)["coordinates"]]]) for i, n, h, g in conn.execute(
            f"""with pts as (select geom from core.signal_device where active and source = any(%(sources)s) and {where}
                             union all select geom from core.osm_node where active and kind = 'traffic_signals' and {where})
                select distinct on (w.osm_id) w.osm_id, w.name, w.highway, ST_AsGeoJSON(ST_Transform(w.geom, {UTM}), 2)
                from pts p join core.osm_way w on w.geom && ST_Expand(p.geom, 0.0025)
                where w.active and w.name is not null
                  and w.highway in ('motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified',
                                    'residential', 'motorway_link', 'trunk_link', 'primary_link', 'secondary_link',
                                    'tertiary_link')""",
            {**params, "sources": DEVICE_SOURCES}).fetchall()]
        osm_roads = Roads(ways) if ways else None
    existing = [Existing(*r) for r in conn.execute(
        f"""select id, achd_synchro_id, ST_X(ST_Transform(geom, {UTM})), ST_Y(ST_Transform(geom, {UTM})), status
            from core.intersection where {where} order by id""", params).fetchall()]
    return seeds, poles, regional, others, osm_nodes, roads, osm_roads, existing


def write(conn, built, retire, seen_at, area=None):
    """Write intersections, device links, approaches, OSM links. Returns {'new': n, 'retired': n}."""
    # Rows changing their Synchro ID give it up first, so the unique constraint holds throughout.
    conn.execute("update core.intersection set achd_synchro_id = null where id = any(%s)",
                 ([b.id for b in built if b.id is not None],))
    new = 0
    for b in built:
        row = {"name": b.name[:200], "x": b.x, "y": b.y, "control": b.control, "operator": b.operator,
               "owner": b.owner, "county": b.county, "city": b.city, "synchro": b.synchro,
               "coord_group": b.coord_group, "evidence": sorted(b.evidence), "confidence": b.confidence,
               "status": b.status, "seen": seen_at, "id": b.id}
        point = f"ST_Transform(ST_SetSRID(ST_MakePoint(%(x)s, %(y)s), {UTM}), 4326)"
        if b.id is None:
            b.id = conn.execute(
                f"""insert into core.intersection (name, geom, control, operator, owner, county, city, achd_synchro_id,
                      coord_group, evidence, confidence, status, first_seen, last_seen)
                    values (%(name)s, {point}, %(control)s, %(operator)s, %(owner)s, %(county)s, %(city)s, %(synchro)s,
                      %(coord_group)s, %(evidence)s, %(confidence)s, %(status)s, %(seen)s, %(seen)s)
                    returning id""", row).fetchone()[0]
            new += 1
        else:
            conn.execute(
                f"""update core.intersection set name = %(name)s, geom = {point}, control = %(control)s,
                      operator = %(operator)s, owner = %(owner)s, county = %(county)s, city = %(city)s,
                      achd_synchro_id = %(synchro)s, coord_group = %(coord_group)s, evidence = %(evidence)s,
                      confidence = %(confidence)s, status = %(status)s, last_seen = %(seen)s
                    where id = %(id)s""", row)
    retired = conn.execute("update core.intersection set status = 'retired' where id = any(%s) and status <> 'retired'",
                           ([e.id for e in retire],)).rowcount

    where, params = _area(area)
    conn.execute(f"""update core.signal_device set intersection_id = null, distance_m = null
                     where intersection_id is not null and source = any(%(sources)s) and {where}""",
                 {**params, "sources": DEVICE_SOURCES})
    links = [(d.id, b.id, dd) for b in built if not b.reviewed_out for d, dd in b.devices]
    if links:
        conn.execute("""update core.signal_device s set intersection_id = v.iid, distance_m = v.dist
                        from unnest(%s::bigint[], %s::bigint[], %s::real[]) as v(did, iid, dist) where s.id = v.did""",
                     ([l[0] for l in links], [l[1] for l in links], [l[2] for l in links]))

    # COMPASS's approaches, by leg.
    ids = [b.id for b in built] + [e.id for e in retire]
    rows = [(b.id, a["leg"], a.get("right_turn_lanes"), a.get("left_turn_phasing"), a.get("right_turn_phasing"),
             json.dumps(a["volumes"]) if a.get("volumes") else None)
            for b in built if b.seed is not None and not b.reviewed_out for a in b.approaches.values()]
    keep = {(r[0], r[1]) for r in rows}
    stale = [(i, leg) for i, leg in conn.execute(
        "select intersection_id, leg from core.approach where source = %s and intersection_id = any(%s)",
        (SEED_SOURCE, ids)).fetchall() if (i, leg) not in keep]
    for i, leg in stale:
        conn.execute("delete from core.approach where intersection_id = %s and leg = %s and source = %s",
                     (i, leg, SEED_SOURCE))
    for r in rows:
        conn.execute(
            """insert into core.approach (intersection_id, leg, source, right_turn_lanes, left_turn_phasing,
                 right_turn_phasing, peak_volumes, updated_at)
               values (%s, %s, %s, %s, %s, %s, %s, now())
               on conflict (intersection_id, leg, source) do update set right_turn_lanes = excluded.right_turn_lanes,
                 left_turn_phasing = excluded.left_turn_phasing, right_turn_phasing = excluded.right_turn_phasing,
                 peak_volumes = excluded.peak_volumes, updated_at = excluded.updated_at""",
            (r[0], r[1], SEED_SOURCE, r[2], r[3], r[4], r[5]))

    # OpenStreetMap nodes have no column for their intersection: they're linked in core.source_link.
    osm_links = 0
    if conn.execute("select exists (select 1 from ops.source where name = %s)", (OSM_SOURCE,)).fetchone()[0]:
        conn.execute(f"""delete from core.source_link l using core.osm_node n
                         where l.source = %(src)s and l.entity = 'intersection' and l.source_id = 'n' || n.osm_id
                           and {where.replace('geom', 'n.geom')}""", {**params, "src": OSM_SOURCE})
        for b in built:
            for n, d in ([] if b.reviewed_out else b.osm):
                conn.execute(
                    """insert into core.source_link (source, source_id, entity, entity_id, method, distance_m, confidence)
                       values (%s, %s, 'intersection', %s, %s, %s, %s)
                       on conflict (source, source_id, entity) do update set entity_id = excluded.entity_id,
                         method = excluded.method, distance_m = excluded.distance_m, confidence = excluded.confidence,
                         linked_at = now()""",
                    (OSM_SOURCE, f"n{n.osm_id}", b.id, f"nearest_{OSM_ATTACH_M}m", d, b.confidence))
                osm_links += 1
    return {"new": new, "retired": retired, "approaches": len(rows), "OSM links": osm_links}


def write_cameras(conn, built, area=None):
    """Link each active ACHD camera (each of its GIS records) to its intersection; links of
    cameras since gone or moved away are dropped."""
    where, params = _area(area, "c.pole_geom")
    rows = conn.execute(
        f"""select c.id, c.name, ST_X(ST_Transform(c.pole_geom, {UTM})), ST_Y(ST_Transform(c.pole_geom, {UTM})), c.active
            from core.camera c where c.pole_geom is not null and {where}""", params).fetchall()
    cams = [r[:4] for r in rows if r[4]]
    links = link_cameras(built, cams)
    source_ids = defaultdict(list)
    for sid, cam_id in conn.execute(
            "select source_id, entity_id from core.source_link where source = %s and entity = 'camera' and entity_id = any(%s)",
            (CAMERA_SOURCE, [r[0] for r in rows])).fetchall():
        source_ids[cam_id].append(sid)
    all_sids = [s for v in source_ids.values() for s in v]
    conn.execute("delete from core.source_link where source = %s and entity = 'intersection' and source_id = any(%s)",
                 (CAMERA_SOURCE, all_sids))
    for cam_id, (b, d, conf, method) in links.items():
        for sid in source_ids.get(cam_id, ()):
            conn.execute(
                """insert into core.source_link (source, source_id, entity, entity_id, method, distance_m, confidence)
                   values (%s, %s, 'intersection', %s, %s, %s, %s)""",
                (CAMERA_SOURCE, sid, b.id, method, d, conf))
    by_method = Counter(m for _, _, _, m in links.values())
    return {"cameras": len(cams), "cameras linked": len(links),
            "cameras linked to interchanges": by_method[f"interchange_{INTERCHANGE_CAMERA_M}m"]}, links


def write_crossings(conn, built, area=None):
    where, params = _area(area)
    rows = conn.execute(
        f"""select id, ST_X(ST_Transform(geom, {UTM})), ST_Y(ST_Transform(geom, {UTM}))
            from core.rail_crossing where geom is not null and {where}""", params).fetchall()
    links = link_crossings(built, rows)
    conn.execute(f"update core.rail_crossing set intersection_id = null, signal_distance_m = null where {where}", params)
    if links:
        conn.execute("""update core.rail_crossing r set intersection_id = v.iid, signal_distance_m = v.dist
                        from unnest(%s::bigint[], %s::bigint[], %s::real[]) as v(cid, iid, dist) where r.id = v.cid""",
                     (list(links), [b.id for b, _ in links.values()], [d for _, d in links.values()]))
    return {"crossings near signals": len(links)}


def build(conn, seen_at, area=None, reviews=None):
    """The whole build in the caller's transaction (no commit). Returns (stats, details).
    reviews: Review list; by default the reviews file."""
    seeds, poles, regional, others, osm_nodes, roads, osm_roads, existing = load(conn, area)
    if reviews is None:
        reviews = load_reviews()
    built, details = plan(seeds, poles, regional, others, osm_nodes, roads, osm_roads, reviews)
    alive = sum(e.status != "retired" for e in existing)
    if alive and len(built) < MIN_SHARE * alive:
        raise RuntimeError(f"only {len(built)} intersections built against {alive} held; refusing to retire the rest "
                           "(is a signal source empty?)")
    retire = assign_ids(built, existing)
    w = write(conn, built, retire, seen_at, area)
    cams, cam_links = write_cameras(conn, built, area)
    crossings = write_crossings(conn, built, area)
    status = Counter(b.status for b in built)
    stats = {"intersections": len(built), "active": status["active"], "candidate": status["candidate"],
             "new": w["new"], "retired": w["retired"], **{k: v for k, v in sorted(details["counts"].items())},
             "approaches": w["approaches"], **cams, **crossings}
    if w["OSM links"]:
        stats["OSM links"] = w["OSM links"]
    details.update({"built": built, "camera_links": cam_links})
    return stats, details


def report(conn, stats, details, out=print):
    """A readable summary of a build (for `python3 -m ingest match-intersections`)."""
    built = details["built"]
    out("match-intersections: " + ", ".join(f"{k} {v}" for k, v in stats.items()))
    by = Counter((b.status, "+".join(sorted(b.evidence))) for b in built)
    out("\nIntersections by status and evidence:")
    for (status, ev), n in sorted(by.items(), key=lambda kv: (kv[0][0], -kv[1])):
        out(f"  {status:9} {ev:40} {n:5}")
    retired = conn.execute("select count(*) from core.intersection where status = 'retired'").fetchone()[0]
    out(f"  retired (all time) {retired}")
    conf = Counter(b.confidence for b in built)
    out("Confidence: " + ", ".join(f"{c:.2f}: {n}" for c, n in sorted(conf.items(), reverse=True)))
    far = [b for b in built if b.penalized]
    if far:
        out(f"\nCOMPASS points more than {SNAP_M} m from their named junction (kept in place, -{SNAP_PENALTY}):")
        for b in sorted(far, key=lambda b: -b.snap_m):
            out(f"  {b.name} ({b.operator}): {b.snap_m:.0f} m")
    def describe(b):
        kinds = Counter(d.kind for d, _ in b.devices)
        return (f"{b.confidence:.2f} {b.name} [{'+'.join(sorted(b.evidence))}] at {b.lat:.5f}, {b.lon:.5f}: "
                + ", ".join(f"{k} {n}" for k, n in sorted(kinds.items())) + (f", OSM nodes {len(b.osm)}" if b.osm else ""))

    cands = sorted((b for b in built if b.status == "candidate" and b.review is None), key=lambda b: (-b.confidence, b.name))
    out(f"\nCandidates to review: {len(cands)}")
    for b in cands:
        out(f"  {describe(b)}")
    rv = details["reviews"]
    out(f"\nReviews applied ({os.path.basename(REVIEWS_FILE)}): {len(rv['applied'])}")
    for r, b in rv["applied"]:
        out(f"  {r.status:9} {describe(b)}\n            {r.reason} ({r.decided})")
    for r, b, gained in rv["reopened"]:
        out(f"  NO LONGER APPLIES (gained {', '.join(gained)}): {r.key} {r.name!r}: {describe(b)}")
    for r in rv["unmatched"]:
        out(f"  NO INTERSECTION within {REVIEW_M} m: {r.key} {r.name!r}")
    if details["shared_synchro"]:
        out(f"\nSynchro IDs COMPASS lists on two points (left off both): {details['shared_synchro']}")
    out("\nRegional_Signals traffic signals within "
        f"{REGIONAL_MATCH_M} m of a COMPASS seed, by operator (matched / listed):")
    for op, (m, n) in details["regional_by_operator"].items():
        out(f"  {op:28} {m:4} / {n}")
    for op, name, sid in details["regional_unmatched"]:
        out(f"  unmatched: {op} {name!r} ({sid})")
    links = details["camera_links"]
    methods = Counter(m for _, _, _, m in links.values())
    out(f"\nCameras linked: {len(links)} of {stats.get('cameras', 0)} ("
        + ", ".join(f"{m} {n}" for m, n in sorted(methods.items())) + ")")
    for b, d, _, m in sorted(links.values(), key=lambda v: v[0].name):
        if m.startswith("interchange"):
            out(f"  {m}: {b.name}, {d:.0f} m")
    rows = conn.execute(
        """select r.crossing_id, r.street, r.railroad_code, r.warning, r.closed, r.position,
                  round(r.signal_distance_m::numeric), i.name
           from core.rail_crossing r join core.intersection i on i.id = r.intersection_id
           order by r.closed, r.signal_distance_m""").fetchall()
    out(f"\nRail crossings within {CROSSING_M} m of an active signalized intersection: {len(rows)}")
    for cid, street, rr, warning, closed, position, d, name in rows:
        flag = " (closed)" if closed else "" if position == "At Grade" else f" ({position})"
        out(f"  {cid} {street} [{rr}, {warning}]{flag}: {d} m from {name}")


def run(conn):
    """The scheduled derived source: rebuild and log it in ops.fetch like any other source."""
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        stats, _ = build(conn, f.started_at)
        f.records = stats["intersections"]
    return stats
