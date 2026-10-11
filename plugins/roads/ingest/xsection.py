"""The cross-section rules of the real-width roads (landscape sprint package P7; the roads-real-width design;
decision 10). Standard library: roads-build (build.py) gathers each piece's inputs in PostGIS and calls
cross_section() on them, and the tests call it on synthetic pieces.

A piece is an OpenStreetMap way's stretch between junctions (roads.piece). Left and right are as its line is
drawn (the way's direction), and forward lanes run along it (right-hand traffic: on the right). OpenStreetMap
draws a way down the middle of its carriageway, so the pavement is centred on the line: width_left_m =
width_right_m = total / 2, except where a parallel sidewalk caps one side (below).

**Lanes** (lanes_source), first that applies:
1. the way's own `lanes`, `lanes:forward|backward|both_ways` and `turn:lanes*` ('osm'), as osm_valley expands
   them; an odd two-way count with no split reads as the Master Street Map's (a centre turn lane from 3);
2. in Ada, the ACHD segment the piece lies along: core.segment_lanes' choice (HPMS on state routes, the Master
   Street Map on arterials, OpenStreetMap or COMPASS elsewhere, else 1+1 'default'), turned onto the piece by
   their bearings; a one-way piece (a divided road's carriageway) takes its own direction's count;
3. where no segment gives one (Canyon, the rest of the box), ITD's HPMS through lanes along the piece
   ('itd_hpms');
4. 1+1, or 1 on a one-way piece ('default'; 2 on a motorway).
COMPASS's lanes for Canyon are left out (cut first, plan §0). Where the way's own count and the segment's
rule differ by more than a lane, the piece is flagged 'conflict' and goes on the review list; the segment's
own conflict flag is carried too.

**Widths** (width_tier, width_source):
- 'inventoried': ACHD's bike network's curb-to-curb width (`total_pavement_m`) on a two-way piece along a
  two-way segment, or a one-way carriageway's own side (`roadway_m` plus gutters); the way's `width` tag; or
  HPMS's lane width with HPMS's shoulders or a curb.
- 'counted': lanes from a source, widths from the defaults below.
- 'estimated': default lanes; local streets get a class pavement width (curbed or rural ⚠️, calibrated in the
  test windows: build.py's calibrate()).
- 'measured' is the photo check's, later.
Lane width: HPMS's on its sections, else ACHD's lane next to the bike facility, else the class's (§14.7: 3.66 m
major roads, 3.35 m collectors, 3.05 m local streets). Bike lanes: ACHD's facility where it's in the roadway, else
1.5 m where OpenStreetMap tags one. Parking: ACHD's, else OpenStreetMap's parking tags. Shoulders: HPMS's, else
the class's (motorways 3.0 m outside and 1.2 m inside; other rural roads 1.2 m), and a curbed side's 0.6 m
gutter. Median: HPMS's on a single two-way way. Where an inventoried total and the components disagree, the
lanes are widened or narrowed to fit (2.6-4.6 m), and the rest is unassigned pavement at the edges; components
that don't fit are scaled down, flagged and listed for review.

**Edges:** a side is curbed (edge 'curb') where ACHD's bike network says so, where a sidewalk is mapped beside it
(tagged on the way or a parallel sidewalk way), or on developed land (the CDL's classes 122-124, half the
piece's length or more); motorways and their links never; otherwise 'shoulder' (no curb).

**Sidewalks:** a surface edge stays at least SIDEWALK_CLEAR_M inside a parallel sidewalk way (the sidewalk's
centre line, measured square to the piece). An estimated or counted side is cut to it, from its outer space
(gutter, parking, unassigned pavement), never into its lanes; where it would have to be, the piece is flagged
'sidewalk_close' and listed. An inventoried width isn't cut, but listed when the sidewalk is more than a metre
inside it.

**Markings** only where a source gives the lane count (decision 10): never on 'default' lanes, never with
`lane_markings=no`, and on local streets only from 3 lanes, with a centre turn lane or bike lanes, or with
`lane_markings=yes`. Alleys never.

**Material:** the surface tag (osm_paving's MATERIALS: asphalt, concrete, gravel or dirt), else asphalt
('default'), except that unclassified roads, `highway=road`, alleys and service ways take it only on developed
land, like the paving's service ways (plan C11): otherwise 'unknown'.

Every component records its source in `sources`, and a piece with any ACHD or ITD input is `republish`
'internal' (a public variant rebuilds without them, plan C17).
"""

from .sources.osm_paving import DEVELOPED_SHARE, MATERIALS, PAVED, surface_value
from .sources.osm_valley import effective_oneway, expand_lanes, parse_count, parse_width

FT = 0.3048

# The rules' numbers (metres), recorded in each build's roads.build.params. ⚠️ marks the estimates.
DEFAULTS = {
    "lane_w": {"major": 3.66, "collector": 3.35, "local": 3.05},      # §14.7 ⚠️
    "lane_w_range": [2.6, 4.6],                                       # a fitted lane width stays inside this
    "bike_lane": 1.5,                                                 # ⚠️
    "parking": {"parallel": 2.4, "diagonal": 4.8, "perpendicular": 5.4},   # ⚠️
    "gutter": 0.6,                                                    # a curbed side's gutter ⚠️
    "shoulder": {"motorway_out": 3.0, "motorway_in": 1.2, "rural": 1.2},   # ⚠️
    "local_pavement": {"curbed": 10.4, "rural": 7.3},                 # unmarked local streets ⚠️ (calibrated: README)
    "alley": 5.0,                                                     # ⚠️
    "roundabout_lane": 5.0,                                           # a ring's circulating lane ⚠️
    "service": 5.5,                                                   # as osm_paving's other service ways ⚠️
    "sidewalk_clear": 1.0,                                            # an edge stays this far inside a sidewalk
    "markings_local_min_lanes": 3,
}

MAJOR = {"motorway", "trunk", "primary", "secondary", "motorway_link", "trunk_link", "primary_link",
         "secondary_link"}
COLLECTOR = {"tertiary", "tertiary_link"}
LOCAL = {"residential", "unclassified", "living_street", "road", "busway", "service"}
ROAD_CLASSES = MAJOR | COLLECTOR | LOCAL
FREEWAY = {"motorway", "motorway_link", "trunk_link"}       # never curbed; edge lines always
LAND_RULE = {"unclassified", "road", "service"}             # a default material only on developed land
LANE_SOURCES = ("osm", "itd_hpms", "achd_msm", "osm_valley", "compass_centerline", "default")
INTERNAL_SOURCES = {"itd_hpms", "achd_msm", "achd_bike_network", "achd_roads", "osm_valley"}
IN_ROADWAY_BUFFERS = {"painted", "delineator", "extruded_curb", "jersey_barrier"}
BIKE_LANE_TAGS = {"lane", "opposite_lane", "buffered_lane"}
PARKING_OLD = {"parallel": "parallel", "diagonal": "diagonal", "perpendicular": "perpendicular",
               "marked": "parallel", "inline": "parallel"}
PARKING_NEW = {"lane", "street_side", "half_on_kerb", "on_kerb", "shoulder"}
SIDEWALK_YES = {"yes", "both", "left", "right", "separate"}


def road_class(highway):
    """'major', 'collector' or 'local'."""
    if highway in MAJOR:
        return "major"
    if highway in COLLECTOR:
        return "collector"
    return "local"


def travel(oneway):
    """1: one-way along the line, -1: against it, 0: both ways (oneway=reversible etc. count as two-way)."""
    return {"yes": 1, "-1": -1}.get(oneway, 0)


def turn_text(turns):
    return ";".join(turns) if turns else None


def _r(x):
    return round(float(x), 2)


# ---- lanes ---------------------------------------------------------------------------------------

def osm_lanes(tags):
    """The way's own lanes: {fwd, bwd, centre, turn_fwd, turn_bwd, split_estimated} or None, and issues."""
    rows, issues = expand_lanes(tags)
    if rows:
        f = [r for r in rows if r[0] == "forward"]
        b = [r for r in rows if r[0] == "backward"]
        c = [r for r in rows if r[0] == "both"]
        tf = [turn_text(r[2]) for r in f]
        tb = [turn_text(r[2]) for r in b]
        return {"fwd": len(f), "bwd": len(b), "centre": len(c) > 0,
                "turn_fwd": tf if any(tf) else None, "turn_bwd": tb if any(tb) else None,
                "split_estimated": False}, issues
    total = parse_count(tags.get("lanes"))
    if total and effective_oneway(tags) == "no":       # an odd two-way count with no split
        if total == 1:
            return {"fwd": 1, "bwd": 1, "centre": False, "turn_fwd": None, "turn_bwd": None,
                    "split_estimated": True, "single_lane": True}, issues
        centre = total >= 3 and total % 2 == 1
        half = (total - (1 if centre else 0)) // 2
        return {"fwd": half, "bwd": half, "centre": centre, "turn_fwd": None, "turn_bwd": None,
                "split_estimated": True}, issues
    return None, issues


def segment_lanes(seg, lanes, way):
    """The ACHD segment's lane rule (core.segment_lanes) turned onto the piece. seg: {one_way, same_way}; lanes:
    segment_lanes' row; way: the piece's travel (1, -1, 0). Returns ({fwd, bwd, centre}, flags, reviews)."""
    lf, lb = lanes.get("lanes_forward"), lanes.get("lanes_backward")
    same = bool(seg["same_way"])
    flags, reviews = [], []
    if way == 0:
        fwd, bwd = (lf, lb) if same else (lb, lf)
        if seg["one_way"] != "both" and (not fwd or not bwd):
            # One OpenStreetMap way for a road ACHD draws as two one-way segments: the other direction is
            # assumed to match.
            n = fwd or bwd
            if not n:
                return None, flags, reviews
            fwd = bwd = n
            flags.append("other_direction_assumed")
            reviews.append(("other_direction_assumed", {"segment_one_way": seg["one_way"]}))
        if fwd is None or bwd is None:
            return None, flags, reviews
        return {"fwd": fwd, "bwd": bwd, "centre": bool(lanes.get("centre_turn_lane"))}, flags, reviews
    along = same if way == 1 else not same          # the piece's traffic runs the way the segment is drawn
    n = lf if along else lb
    if not n:
        other = lb if along else lf
        reviews.append(("direction", {"segment_one_way": seg["one_way"], "this_way": n, "other_way": other,
                                      "source": lanes.get("source")}))
        flags.append("direction")
        return None, flags, reviews
    return ({"fwd": n, "bwd": 0} if way == 1 else {"fwd": 0, "bwd": n}) | {"centre": False}, flags, reviews


def hpms_lanes(rows, way):
    """ITD HPMS through lanes along the piece (outside Ada): rows of {direction ('A', 'D' or None),
    through_lanes, lanes_ascending, lanes_descending, same_way, overlap}, best first. Ascending runs the way the
    A route is drawn. Returns {fwd, bwd, centre} or None."""
    a = next((r for r in rows if r.get("direction") != "D"), None)
    d = next((r for r in rows if r.get("direction") == "D"), None)

    def d_lanes():
        if d is None:
            return None
        return d.get("lanes_descending") or d.get("through_lanes") or None

    if a is None and d is None:
        return None
    if a is None:
        n = d_lanes()
        if not n:
            return None
        if way == 0:
            return {"fwd": max(1, n // 2), "bwd": max(1, n // 2), "centre": False}
        return ({"fwd": n, "bwd": 0} if way == 1 else {"fwd": 0, "bwd": n}) | {"centre": False}
    asc, desc = a.get("lanes_ascending"), a.get("lanes_descending")
    if not asc and not desc and a.get("through_lanes"):
        if way != 0:
            asc = a["through_lanes"]
        else:
            asc = desc = max(1, a["through_lanes"] // 2)
    if asc and not desc:
        desc = d_lanes()
    same = bool(a.get("same_way"))
    if way == 0:
        if not asc or not desc:
            return None
        fwd, bwd = (asc, desc) if same else (desc, asc)
        return {"fwd": fwd, "bwd": bwd, "centre": False}
    along_a = same if way == 1 else not same
    n = asc if along_a else desc
    if not n:
        return None
    return ({"fwd": n, "bwd": 0} if way == 1 else {"fwd": 0, "bwd": n}) | {"centre": False}


# ---- sides from OpenStreetMap's tags -------------------------------------------------------------

def _side_values(tags, key, way):
    """{left, right} values of key, key:both, key:left and key:right, as the line is drawn. A bare key applies to
    both sides of a two-way road and to the right of travel on a one-way road (left of the line if it runs
    against it)."""
    out = {"left": None, "right": None}
    bare = tags.get(key)
    if bare is not None:
        if way == 0:
            out["left"] = out["right"] = bare
        else:
            out["right" if way == 1 else "left"] = bare
    both = tags.get(f"{key}:both")
    if both is not None:
        out["left"] = out["right"] = both
    for side in ("left", "right"):
        v = tags.get(f"{key}:{side}")
        if v is not None:
            out[side] = v
    return out


def osm_bike(tags, way):
    """Bike lanes in the roadway per side ({left, right} in metres, 0 for none)."""
    vals = _side_values(tags, "cycleway", way)
    if way != 0 and str(tags.get("cycleway") or "").strip().lower() == "opposite_lane":
        vals["left" if way == 1 else "right"] = "lane"
        vals["right" if way == 1 else "left"] = tags.get(f"cycleway:{'right' if way == 1 else 'left'}")
    out = {}
    for side, v in vals.items():
        if str(v or "").strip().lower() in BIKE_LANE_TAGS:
            w = parse_width(tags.get(f"cycleway:{side}:width")) or parse_width(tags.get("cycleway:both:width")) \
                or parse_width(tags.get("cycleway:width"))
            out[side] = w if w and w < 4 else DEFAULTS["bike_lane"]
        else:
            out[side] = 0.0
    return out


def osm_parking(tags):
    """On-street parking per side ({left, right} in metres, as the line is drawn): the old parking:lane scheme
    (parallel, diagonal, perpendicular) and the new one (parking:<side>=lane, street_side, ... with
    parking:<side>:orientation)."""
    out = {"left": 0.0, "right": 0.0}
    old = _side_values(tags, "parking:lane", 0)
    new = _side_values(tags, "parking", 0)
    for side in ("left", "right"):
        kind = PARKING_OLD.get(str(old[side] or "").strip().lower())
        if str(new[side] or "").strip().lower() in PARKING_NEW:
            ori = str(tags.get(f"parking:{side}:orientation") or tags.get("parking:both:orientation")
                      or "parallel").strip().lower()
            kind = ori if ori in DEFAULTS["parking"] else "parallel"
        if kind:
            out[side] = DEFAULTS["parking"][kind]
    return out


def osm_sidewalk_tag(tags, way):
    """{left, right}: True where the way says a sidewalk runs beside it (on the way or drawn separately)."""
    vals = _side_values(tags, "sidewalk", 0)
    bare = str(tags.get("sidewalk") or "").strip().lower()
    if bare in ("left", "right"):
        vals = {"left": "yes" if bare == "left" else "no", "right": "yes" if bare == "right" else "no"}
    elif bare in ("both", "separate", "yes"):
        vals = {"left": bare, "right": bare} | {k: v for k, v in vals.items() if tags.get(f"sidewalk:{k}")}
    return {side: str(v or "").strip().lower() in SIDEWALK_YES for side, v in vals.items()}


def osm_shoulders(tags):
    """{left, right} shoulder widths the way tags, or None for a side it doesn't."""
    vals = _side_values(tags, "shoulder", 0)
    bare = str(tags.get("shoulder") or "").strip().lower()
    if bare in ("left", "right"):
        vals = {"left": "yes" if bare == "left" else "no", "right": "yes" if bare == "right" else "no"}
    elif bare in ("both", "yes"):
        vals = {"left": "yes", "right": "yes"}
    w = parse_width(tags.get("shoulder:width"))
    out = {}
    for side, v in vals.items():
        v = str(v or "").strip().lower()
        out[side] = None if not v else (0.0 if v == "no" else (w or DEFAULTS["shoulder"]["rural"]))
    return out


# ---- ACHD's bike network --------------------------------------------------------------------------

def _bike_side(row, achd_side):
    """One of ACHD's sides (achd_side 'fwd' or 'bwd' of segment_bike_xsection) in metres, or None when the view
    shows nothing there (another carriageway's side, or a direction conflict)."""
    if row is None or row.get(f"{achd_side}_lanes") is None and row.get(f"{achd_side}_edge") is None:
        return None
    g = lambda k: row.get(f"{achd_side}_{k}")     # noqa: E731
    bike = 0.0
    if g("bike_in_roadway") and (g("bike_w_m") or 0) > 0:
        bike = g("bike_w_m")
        if g("buffer") in IN_ROADWAY_BUFFERS and (g("buffer_w_m") or 0) > 0:
            bike += g("buffer_w_m")
    park = g("parking_w_m") if g("parking") in ("parallel", "angled") and (g("parking_w_m") or 0) > 0 else 0.0
    edge = {"curb_gutter": "curb", "curb": "curb", "shoulder": "shoulder"}.get(g("edge"))
    return {"lanes": g("lanes"), "lane_w": g("lane_w_m"), "bike": bike, "park": park, "edge": edge,
            "roadway": g("roadway_m"), "facility": g("bike")}


def bike_sides(row, seg, way):
    """ACHD's two sides as the piece's {left, right} (either None), and the side that holds the piece's own
    traffic on a one-way piece."""
    if row is None or seg is None:
        return {"left": None, "right": None}
    same = bool(seg["same_way"])
    if way == 0:
        right, left = ("fwd", "bwd") if same else ("bwd", "fwd")
        return {"left": _bike_side(row, left), "right": _bike_side(row, right)}
    along = same if way == 1 else not same
    own = _bike_side(row, "fwd" if along else "bwd")
    # A one-way piece's own traffic is on its right as it travels: the line's right if it runs along the line.
    return {"right": own, "left": None} if way == 1 else {"left": own, "right": None}


# ---- the cross-section --------------------------------------------------------------------------

def cross_section(p, d=DEFAULTS):
    """One piece's cross-section. p: {highway, service, oneway, tags, county, roundabout, seg (None or {id,
    functional_class, one_way, same_way, confidence}), lanes (core.segment_lanes' row or None), bike
    (roads.segment_bike_xsection's row or None), hpms ({through: [...], lane_width_ft, shoulder: {type,
    left_ft, right_ft}, median: {type, width_ft}} or None), sidewalk ({left, right}: the nearest parallel
    sidewalk's distance in metres, or None), developed (0-1 or None)}.

    Returns roads.xsection's columns (without piece_id), plus 'reviews' ([(kind, detail)]), 'outer'
    ({left, right}: each side's outer space beyond its lanes, which a sidewalk may cut) and 'spans' (each
    direction's travel lanes as offsets from the line: {fwd: (a, b), bwd: (a, b)})."""
    tags = p.get("tags") or {}
    hw = p["highway"]
    cls = road_class(hw)
    way = travel(p.get("oneway") or effective_oneway(tags))
    seg, seg_lanes, bike_row, hpms = p.get("seg"), p.get("lanes"), p.get("bike"), p.get("hpms") or {}
    flags, reviews, sources = [], [], {}
    alley = hw == "service" and p.get("service") == "alley"

    # -- lanes
    own, issues = osm_lanes(tags)
    for kind, text in issues:
        if kind == "turn_slots":
            flags.append("turn_slots")
            reviews.append(("turn_slots", {"issue": text}))
    lanes, lanes_source, conf = None, None, None
    seg_lane_view = None
    if seg is not None and seg_lanes is not None and seg_lanes.get("source"):
        seg_lane_view, f2, r2 = segment_lanes(seg, seg_lanes, way)
        flags += f2
        reviews += r2
    if own is not None:
        lanes, lanes_source, conf = own, "osm", 1.0
        if own.get("split_estimated"):
            flags.append("split_estimated")
        if own.get("single_lane"):
            flags.append("single_lane")
        if seg_lane_view is not None and seg_lanes["source"] not in ("default", "osm_valley"):
            ours, theirs = own["fwd"] + own["bwd"], seg_lane_view["fwd"] + seg_lane_view["bwd"]
            if abs(ours - theirs) > 1:
                flags.append("conflict")
                reviews.append(("lanes_conflict", {"osm": [own["fwd"], own["bwd"]],
                                                   seg_lanes["source"]: [seg_lane_view["fwd"], seg_lane_view["bwd"]],
                                                   "road_segment_id": seg.get("id")}))
    elif seg_lane_view is not None:
        lanes, lanes_source = dict(seg_lane_view, turn_fwd=None, turn_bwd=None), seg_lanes["source"]
        conf = seg_lanes.get("confidence")
        if seg_lanes.get("conflict"):
            flags.append("conflict")
            reviews.append(("lanes_conflict", {"segment_rule": seg_lanes.get("source"),
                                               "candidates": seg_lanes.get("candidates"),
                                               "road_segment_id": seg.get("id")}))
        for f in seg_lanes.get("flags") or []:
            if f in ("single_lane", "carriageway_split", "ad_conflict"):
                flags.append(f)
    elif hpms.get("through"):
        h = hpms_lanes(hpms["through"], way)
        if h:
            lanes, lanes_source, conf = dict(h, turn_fwd=None, turn_bwd=None), "itd_hpms", 0.8
    if lanes is None:
        n = 2 if hw == "motorway" else 1
        lanes = {"fwd": n if way >= 0 else 0, "bwd": n if way <= 0 else 0, "centre": False,
                 "turn_fwd": None, "turn_bwd": None}
        lanes_source, conf = "default", 0.2
    if way != 0:
        lanes["centre"] = False
    sources["lanes"] = lanes_source
    fwd, bwd, centre = lanes["fwd"], lanes["bwd"], bool(lanes["centre"])
    n_lanes = fwd + bwd + (1 if centre else 0)

    # -- ACHD's bike network
    achd = bike_sides(bike_row, seg, way)

    # -- lane width
    lane_w, lane_w_source = d["lane_w"][cls], "default"
    if hpms.get("lane_width_ft"):
        lane_w, lane_w_source = hpms["lane_width_ft"] * FT, "itd_hpms"
    else:
        achd_w = [s["lane_w"] for s in achd.values() if s and s.get("lane_w")]
        if achd_w:
            lane_w, lane_w_source = sum(achd_w) / len(achd_w), "achd_bike_network"
    if p.get("roundabout") and lane_w_source == "default":
        lane_w = d["roundabout_lane"]   # a ring's circulating lane is wider than a street's
    sources["lane_w"] = lane_w_source

    # -- bike lanes, parking (line frame: left, right)
    ob, op = osm_bike(tags, way), osm_parking(tags)
    bike, park = {}, {}
    for side in ("left", "right"):
        s = achd[side]
        if s is not None and s.get("facility") is not None:
            bike[side], park[side] = float(s["bike"]), float(s["park"])
            sources[f"bike_{side[0]}"] = sources[f"park_{side[0]}"] = "achd_bike_network"
        else:
            bike[side], park[side] = ob[side], op[side]
            if ob[side]:
                sources[f"bike_{side[0]}"] = "osm"
            if op[side]:
                sources[f"park_{side[0]}"] = "osm"
    # -- edges: curb or shoulder, per side
    walks = osm_sidewalk_tag(tags, way)
    near = p.get("sidewalk") or {}
    developed = p.get("developed")
    edge, edge_source = {}, {}
    for side in ("left", "right"):
        s = achd[side]
        if s is not None and s.get("edge"):
            edge[side], edge_source[side] = s["edge"], "achd_bike_network"
        elif hw in FREEWAY or (hw == "trunk" and way != 0):
            edge[side], edge_source[side] = "shoulder", "class"
        elif walks[side] or near.get(side) is not None:
            edge[side], edge_source[side] = "curb", "sidewalk"
        elif developed is not None and developed >= DEVELOPED_SHARE:
            edge[side], edge_source[side] = "curb", "developed"
        else:
            edge[side], edge_source[side] = "shoulder", "class"
    if way != 0 and achd["left" if way == 1 else "right"] is None:
        # A one-way carriageway's other side (the median's, on a divided road) follows its own side.
        own_side = "right" if way == 1 else "left"
        other = "left" if way == 1 else "right"
        if edge_source[own_side] == "achd_bike_network":
            edge[other], edge_source[other] = edge[own_side], "achd_bike_network"
    sources["edge"] = sorted(set(edge_source.values()))[0] if len(set(edge_source.values())) == 1 \
        else edge_source

    # -- shoulders and gutters
    shoulder, sh_source = {}, None
    hs = hpms.get("shoulder")
    tagged_sh = osm_shoulders(tags)
    for side in ("left", "right"):
        if edge[side] == "curb":
            shoulder[side] = d["gutter"]
            continue
        if tagged_sh[side] is not None:
            shoulder[side], sh_source = tagged_sh[side], "osm"
            continue
        if hs and hs.get("type") is not None:
            if hs["type"] == "none":
                shoulder[side] = 0.0
            else:
                travel_right = (side == "right") == (way >= 0)
                ft = hs.get("right_ft") if (way == 0 or travel_right) else hs.get("left_ft")
                shoulder[side] = (ft or 0) * FT
            sh_source = "itd_hpms"
            continue
        if hw in ("motorway", "trunk") and way != 0:
            travel_right = (side == "right") == (way == 1)
            shoulder[side] = d["shoulder"]["motorway_out" if travel_right else "motorway_in"]
        elif hw in FREEWAY:
            shoulder[side] = d["shoulder"]["motorway_in"]
        elif cls == "local":
            shoulder[side] = 0.0                     # the class pavement width covers it
        else:
            shoulder[side] = d["shoulder"]["rural"]
        sh_source = sh_source or "default"
    sources["shoulder"] = sh_source or "gutter"

    # -- median (one two-way way for a divided road, HPMS)
    median_kind, median_w = None, 0.0
    hm = hpms.get("median")
    if way == 0 and hm and hm.get("type") in ("curbed", "barrier", "unprotected") and (hm.get("width_ft") or 0) > 0:
        median_kind, median_w = hm["type"], hm["width_ft"] * FT
        sources["median"] = "itd_hpms"

    # -- the total, by tier
    nonlane = sum(bike.values()) + sum(park.values()) + sum(shoulder.values()) + median_w
    comp_total = nonlane + n_lanes * lane_w
    tier, width_source, total = None, None, None
    unassigned = 0.0
    inv = None
    tag_w = parse_width(tags.get("width"))
    if bike_row is not None and seg is not None:
        if way == 0 and seg["one_way"] == "both" and bike_row.get("total_pavement_m") and \
                "pavement_exceeds_row" not in (bike_row.get("flags") or []):
            inv = ("achd_bike_network", float(bike_row["total_pavement_m"]))
        elif way != 0:
            own_side = achd["right" if way == 1 else "left"]
            if own_side and own_side.get("roadway"):
                gut = sum(d["gutter"] for s in ("left", "right") if edge[s] == "curb")
                inv = ("achd_bike_network", float(own_side["roadway"]) + gut)
    if inv is None and tag_w and 2.0 <= tag_w <= 60:
        inv = ("osm_width", tag_w)
    if inv is not None:
        width_source, total, tier = inv[0], inv[1], "inventoried"
        if n_lanes:
            fit = (total - nonlane) / n_lanes
            lo, hi = d["lane_w_range"]
            if lo <= fit <= hi:
                lane_w = fit
                sources["lane_w"] = "fitted"
            elif fit > hi:
                unassigned = total - comp_total     # pavement the components don't name: at the edges
                flags.append("unassigned_pavement")
            else:
                # The components don't fit: scale them all down, and list it.
                scale = total / comp_total if comp_total else 1.0
                lane_w *= scale
                bike = {k: v * scale for k, v in bike.items()}
                park = {k: v * scale for k, v in park.items()}
                shoulder = {k: v * scale for k, v in shoulder.items()}
                median_w *= scale
                flags.append("components_exceed")
                reviews.append(("components_exceed", {"total": _r(total), "components": _r(comp_total),
                                                      "source": width_source}))
    elif lane_w_source == "itd_hpms" and lanes_source != "default" and \
            (sh_source == "itd_hpms" or all(edge[s] == "curb" for s in edge)):
        width_source, total, tier = "itd_hpms", comp_total, "inventoried"
    else:
        total = comp_total
        width_source = "lanes"
        tier = "counted" if lanes_source != "default" else "estimated"
        if alley:
            total, width_source, tier = d["alley"], "class_default", "estimated"
            lane_w = total / max(1, n_lanes)
        elif hw == "service" and lanes_source == "default":
            total, width_source, tier = d["service"], "class_default", "estimated"
        elif cls == "local":
            curbs = sum(1 for s in edge.values() if s == "curb")
            pave = d["local_pavement"]
            floor = (pave["curbed"] * curbs + pave["rural"] * (2 - curbs)) / 2
            if floor > total:
                unassigned = floor - total
                total = floor
                width_source = "class_default"
                tier = "estimated"
    total = float(total)

    # -- outer space per side (what a sidewalk may cut), and the sidewalk cap
    half = total / 2
    outer = {s: shoulder[s] + park[s] + unassigned / 2 for s in ("left", "right")}
    width = {"left": half, "right": half}
    clear = d["sidewalk_clear"]
    for side in ("left", "right"):
        dist = near.get(side)
        if dist is None:
            continue
        cap = dist - clear
        if width[side] <= cap:
            continue
        cut = width[side] - cap
        if tier == "inventoried":
            if cut > 1.0:
                reviews.append(("sidewalk_close", {"side": side, "sidewalk_m": _r(dist), "half_width": _r(half),
                                                   "width_source": width_source}))
            continue
        if cut <= outer[side] + 1e-6:
            width[side] = max(cap, 0.5)
            flags.append("sidewalk_cap")
        else:
            flags.append("sidewalk_close")
            reviews.append(("sidewalk_close", {"side": side, "sidewalk_m": _r(dist), "half_width": _r(half),
                                               "outer": _r(outer[side])}))

    # -- markings
    lane_markings = str(tags.get("lane_markings") or "").strip().lower()
    any_bike = any(v > 0 for v in bike.values())
    markings = lanes_source != "default" and lane_markings != "no" and not alley and n_lanes > 0
    if markings and cls == "local" and lane_markings != "yes":
        markings = (fwd + bwd + (1 if centre else 0)) >= d["markings_local_min_lanes"] or centre or any_bike
    if "direction" in flags and lanes_source == "default":
        markings = False

    # -- material
    s = surface_value(tags)
    if s in MATERIALS:
        material, material_source = MATERIALS[s], "surface"
    elif s == PAVED:
        material, material_source = "asphalt", "surface"
    elif (hw in LAND_RULE or alley) and (developed is None or developed < DEVELOPED_SHARE):
        material, material_source = "unknown", None
    else:
        material, material_source = "asphalt", "default"
    sources["width"] = width_source
    sources["material"] = material_source or "unknown"

    used = set()
    for v in sources.values():
        used |= set(v.values()) if isinstance(v, dict) else {v}
    if seg is not None and lanes_source not in ("osm", "itd_hpms", "default"):
        used.add("achd_roads")          # the count came through ACHD's segment
    republish = "internal" if used & INTERNAL_SOURCES else "yes"

    xs = {
        "lanes_fwd": fwd, "lanes_bwd": bwd, "centre_turn": centre,
        "turn_fwd": lanes.get("turn_fwd"), "turn_bwd": lanes.get("turn_bwd"),
        "lanes_source": lanes_source, "lanes_conf": None if conf is None else round(float(conf), 3),
        "lane_w_m": _r(lane_w), "bike_l_m": _r(bike["left"]), "bike_r_m": _r(bike["right"]),
        "park_l_m": _r(park["left"]), "park_r_m": _r(park["right"]),
        "shoulder_l_m": _r(shoulder["left"] + unassigned / 2), "shoulder_r_m": _r(shoulder["right"] + unassigned / 2),
        "edge_l": edge["left"], "edge_r": edge["right"],
        "median_kind": median_kind, "median_w_m": _r(median_w),
        "width_left_m": _r(width["left"]), "width_right_m": _r(width["right"]), "total_w_m": _r(total),
        "width_tier": tier, "width_source": width_source,
        "material": material, "material_source": material_source,
        "markings": bool(markings), "sources": sources, "republish": republish,
        "flags": sorted(set(flags)),
    }
    xs["reviews"] = reviews
    xs["outer"] = {k: _r(v) for k, v in outer.items()}
    xs["spans"] = lane_spans(xs, way)
    return xs


# ---- the layout across the pavement: lines and lanes ----------------------------------------------

def _layout(xs, way):
    """The pavement from the left edge to the right as it travels (a two-way piece: as the line is drawn):
    [(part, width, side)], side 'L' or 'R' for the parts outside the lanes (L: the travel left), else None.
    Parts: shoulder, park, bike, lane_bwd, centre (a centre turn lane), median, centre_line (no width),
    lane_fwd; a one-way piece's lanes are 'lane'. Without the unassigned pavement and a sidewalk's cut."""
    left, right = ("l", "r") if way != -1 else ("r", "l")
    parts = [("shoulder", xs[f"shoulder_{left}_m"], "L"), ("park", xs[f"park_{left}_m"], "L"),
             ("bike", xs[f"bike_{left}_m"], "L")]
    if way == 0:
        parts += [("lane_bwd", xs["lane_w_m"], None)] * xs["lanes_bwd"]
        if xs["centre_turn"]:
            parts.append(("centre", xs["lane_w_m"], None))
        elif xs["median_w_m"]:
            parts.append(("median", xs["median_w_m"], None))
        else:
            parts.append(("centre_line", 0.0, None))
        parts += [("lane_fwd", xs["lane_w_m"], None)] * xs["lanes_fwd"]
    else:
        parts += [("lane", xs["lane_w_m"], None)] * (xs["lanes_fwd"] + xs["lanes_bwd"])
    parts += [("bike", xs[f"bike_{right}_m"], "R"), ("park", xs[f"park_{right}_m"], "R"),
              ("shoulder", xs[f"shoulder_{right}_m"], "R")]
    return [p for p in parts if p[1] > 0 or p[0] == "centre_line"]


def _walk(parts):
    """[(part, width, side, x0)] with x0 the part's left offset, the pavement centred on the line."""
    x = -sum(w for _, w, _ in parts) / 2
    out = []
    for k, w, side in parts:
        out.append((k, w, side, x))
        x += w
    return out


LANE_PARTS = ("lane", "lane_fwd", "lane_bwd")


def _lane_key(part, way):
    return {"lane_fwd": "fwd", "lane_bwd": "bwd"}.get(part, "fwd" if way >= 0 else "bwd")


def lane_spans(xs, way):
    """Each direction's travel lanes as offsets from the line (metres, + right of the line): {'fwd': (a, b),
    'bwd': (a, b)}, without a direction that has no lanes. Stop bars run across them."""
    spans = {}
    for k, w, _, x in _walk(_layout(xs, way)):
        if k in LANE_PARTS:
            key = _lane_key(k, way)
            a, b = spans.get(key, (x, x))
            spans[key] = (min(a, x), x + w)
    if way == -1:                       # the travel frame back to the line's
        spans = {k: (-b, -a) for k, (a, b) in spans.items()}
    return {k: (_r(a), _r(b)) for k, (a, b) in spans.items()}


def marking_lines(xs, way, highway=None):
    """The lines to paint, [(kind, dash, offset)], offset in metres from the line (+ right). Empty unless
    xs['markings']. Kinds: edge (solid: a shoulder's inner side where the edge isn't curbed, a median's sides,
    and both sides of a freeway's or ramp's lanes), lane (dashed, between lanes going the same way),
    centre_double (double, between the two directions), twltl (solid_dashed, either side of a centre turn
    lane), bike (solid: a bike lane's inner side, and its outer side where parking is beyond it)."""
    if not xs["markings"]:
        return []
    walked = _walk(_layout(xs, way))
    curb_l, curb_r = (xs["edge_l"], xs["edge_r"]) if way != -1 else (xs["edge_r"], xs["edge_l"])
    out = []
    for i, (k, w, side, x) in enumerate(walked):
        nxt = walked[i + 1][0] if i + 1 < len(walked) else None
        if k == "centre_line":
            out.append(("centre_double", "double", x))
        elif k == "centre":
            out += [("twltl", "solid_dashed", x), ("twltl", "solid_dashed", x + w)]
        elif k == "median":
            out += [("edge", "solid", x), ("edge", "solid", x + w)]
        elif k == "bike":
            inner, outer = (x + w, x) if side == "L" else (x, x + w)
            out.append(("bike", "solid", inner))
            beyond = walked[i - 1][0] if side == "L" and i > 0 else (nxt if side == "R" else None)
            if beyond == "park":
                out.append(("bike", "solid", outer))
        elif k == "shoulder" and w >= 0.6 and (curb_l if side == "L" else curb_r) == "shoulder":
            out.append(("edge", "solid", x + w if side == "L" else x))
        elif k in LANE_PARTS and nxt == k:
            out.append(("lane", "dashed", x + w))
    if way != 0 and highway in FREEWAY:
        span = [x for k, w, _, x0 in walked if k in LANE_PARTS for x in (x0, x0 + w)]
        if span:
            have = {_r(o) for k, _, o in out if k == "edge"}
            out += [("edge", "solid", o) for o in (min(span), max(span)) if _r(o) not in have]
    if way == -1:
        out = [(k, dash, -o) for k, dash, o in out]
    return sorted({(k, dash, _r(o)) for k, dash, o in out}, key=lambda t: (t[2], t[0]))


def lane_centres(xs, way):
    """The lanes with turns tagged: [(direction, lane, offset, turns)], direction 'forward' (along the line) or
    'backward', lane numbered from 1 at the left as it travels, offset of its centre from the line."""
    centres = {"fwd": [], "bwd": []}
    for k, w, _, x in _walk(_layout(xs, way)):
        if k in LANE_PARTS:
            centres[_lane_key(k, way)].append(x + w / 2)
    if way == -1:
        centres["bwd"] = [-c for c in centres["bwd"]]
    out = []
    # Along the line, its left is the travel left; against it, the line's right is.
    for direction, cs, turns in (("forward", sorted(centres["fwd"]), xs.get("turn_fwd")),
                                 ("backward", sorted(centres["bwd"], reverse=True), xs.get("turn_bwd"))):
        for i, c in enumerate(cs):
            t = turns[i] if turns and i < len(turns) else None
            if t:
                out.append((direction, i + 1, _r(c), t.split(";")))
    return out
