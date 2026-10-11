"""The water network's drawing rules: kinds, widths and first zooms (the water design's "look"; plan §3.5). Pure
Python, so the rules are tested apart from the database; water-build applies them to every reach and body.

Widths are estimates ⚠️ until they're measured from NAIP 2025's near-infrared (water reads dark): Strahler order for
perennial streams, a table by kind for canals, and an OpenStreetMap width tag (0.5-40 m) over either. They're metres,
drawn at max(min px, metres / m per px), so a ribbon reaches its true width only close in.
"""

import re

# Perennial streams by Strahler order (m); 7 and up where no polygon draws the river.
ORDER_WIDTH_M = {1: 1.0, 2: 1.5, 3: 2.5, 4: 4.0, 5: 6.0, 6: 9.0, 7: 14.0}
RIVER_WIDTH_M = 14.0              # a river without an order
STREAM_WIDTH_M = 1.5              # a stream without an order
INTERMITTENT_FACTOR, INTERMITTENT_MIN_M = 0.5, 0.75
# Canals by kind (m): main canal 8, other named canal 5, lateral 2.5, ditch or unnamed 1.5, drain or slough 3.
CANAL_WIDTH_M = {"main_canal": 8.0, "canal": 5.0, "lateral": 2.5, "ditch": 1.5, "drain": 3.0, "unnamed": 1.5}
OSM_WIDTH_RANGE_M = (0.5, 40.0)
MAIN_CANAL_M = 20000.0            # a named canal this long in the box is a main canal ⚠️ (our threshold)

# NHD's visibility filter (the smallest scale a flowline is kept at) to a first zoom, for perennial streams.
VISIBILITY_ZOOM = ((1000000, 8), (500000, 9), (250000, 10), (100000, 11), (75000, 12))
PERENNIAL_DEFAULT_Z = 13          # 1:50k, 1:24k, or no filter
OSM_STREAM_Z = {True: 12, False: 13}    # an OSM-only perennial stream, named or not
OSM_RIVER_Z = 9                   # a river with no NHD visibility, and the latest any perennial river starts
INTERMITTENT_Z = {True: 12, False: 13}  # order 3 and up, or less
CANAL_Z = {"main_canal": 10, "canal": 11, "lateral": 12, "drain": 12, "ditch": 13, "unnamed": 13}
NHD_ONLY_EXTRA_Z = 1              # NHD-only canals draw one zoom later
PIPED_Z = 16                      # piped water: a faint dotted line, from z16 only
MAX_Z = 16                        # the bake's last zoom: past it is the style's business

# Bodies: a few kinds by kind, the rest by area.
BODY_KIND_Z = {"river": 8, "pool": 15, "wetland": 14, "basin": 13, "wastewater": 13, "dock": 13}
BODY_AREA_Z = ((1e6, 8), (1e5, 10), (1e4, 11))     # >= 1 km2 z8, >= 10 ha z10, >= 1 ha z11
BODY_DEFAULT_Z = 13

STRUCTURE_Z = {"spring": 15, "gauge": 10}
STRUCTURE_DEFAULT_Z = 14
RIVER_DAM_Z = 11                  # a named dam on a river (Boise Diversion, Barber, Lucky Peak)

CANAL_KINDS = ("canal", "lateral", "ditch", "drain")

_LATERAL = re.compile(r"\blateral\b", re.IGNORECASE)
_DRAIN = re.compile(r"\b(drain|slough|wasteway|waste)\b", re.IGNORECASE)
_CANAL = re.compile(r"\bcanal\b", re.IGNORECASE)
_DITCH = re.compile(r"\bditch\b", re.IGNORECASE)
_RIVER = re.compile(r"\briver\b", re.IGNORECASE)
HYDROSHARE_KIND = {"Canal": "canal", "Lateral": "lateral", "Drain": "drain", "Field Supply": "ditch",
                   "Pump Lifter": "ditch", "Creek": "stream", "River": "river"}


def name_key(name):
    """A name for grouping: lower case, letters and digits only ('A line Canal' and 'A Line Canal' are one)."""
    if not name:
        return None
    key = " ".join(re.sub(r"[^a-z0-9]+", " ", name.lower()).split())
    return key or None


def canal_kind_by_name(name, default="ditch"):
    """A canal-class line's kind from its name: lateral, drain (drains, sloughs, wasteways), canal, ditch."""
    if not name:
        return default
    if _LATERAL.search(name):
        return "lateral"
    if _DRAIN.search(name):
        return "drain"
    if _CANAL.search(name):
        return "canal"
    if _DITCH.search(name):
        return "ditch"
    return default


def nhd_kind(nhd_class, name, order):
    """An NHD-only run's kind."""
    if nhd_class == "stream_river":
        return "river" if (order or 0) >= 7 or (name and _RIVER.search(name)) else "stream"
    return canal_kind_by_name(name)


def osm_kind(kind, name, hydroshare_type=None):
    """An OpenStreetMap way's kind: its waterway class, a canal refined by its name (or HydroShare's type), and a
    stream whose name says it's a canal, lateral, ditch or drain taken at its word ('New York Canal' tagged as a
    stream in a few places)."""
    if kind == "stream":
        return canal_kind_by_name(name, default=None) or kind
    if kind != "canal":
        return kind
    by_name = canal_kind_by_name(name, default=None)
    if by_name in ("lateral", "drain"):
        return by_name
    hs = HYDROSHARE_KIND.get(hydroshare_type)
    if not name and hs in ("lateral", "drain", "ditch"):
        return hs
    return "canal"


def width(kind, *, intermittent=False, order=None, osm_width=None, named=True, main=False):
    """(metres, how we know it): 'osm_tag', 'order' or 'kind'."""
    lo, hi = OSM_WIDTH_RANGE_M
    if osm_width is not None and lo <= osm_width <= hi:
        return float(osm_width), "osm_tag"
    if kind in ("river", "stream"):
        if order:
            w, how = ORDER_WIDTH_M[min(int(order), 7)], "order"
        else:
            w, how = (RIVER_WIDTH_M if kind == "river" else STREAM_WIDTH_M), "kind"
        if intermittent:
            w = max(w * INTERMITTENT_FACTOR, INTERMITTENT_MIN_M)
        return w, how
    if kind == "canal":
        return CANAL_WIDTH_M["main_canal" if main else ("canal" if named else "unnamed")], "kind"
    return CANAL_WIDTH_M.get(kind, CANAL_WIDTH_M["unnamed"]), "kind"


def visibility_zoom(vis):
    for scale, z in VISIBILITY_ZOOM:
        if vis and vis >= scale:
            return z
    return PERENNIAL_DEFAULT_Z


def reach_minzoom(kind, *, intermittent=False, order=None, visibility=None, named=False, main=False, nhd_only=False,
                  piped=False, has_nhd=False):
    """A reach's first zoom (the design's zoom table)."""
    if piped:
        return PIPED_Z
    if kind == "river":
        if intermittent:
            z = INTERMITTENT_Z[(order or 0) >= 3]
        else:                                     # rivers draw by z9 at the latest
            z = min(visibility_zoom(visibility), OSM_RIVER_Z) if has_nhd else OSM_RIVER_Z
    elif kind == "stream":
        if intermittent:
            z = INTERMITTENT_Z[(order or 0) >= 3]
        elif has_nhd:
            z = visibility_zoom(visibility)
        else:
            z = OSM_STREAM_Z[bool(named)]
    else:
        key = "main_canal" if main else kind
        if kind in ("canal", "ditch") and not named:
            key = "unnamed"
        z = CANAL_Z[key] + (NHD_ONLY_EXTRA_Z if nhd_only else 0)
    return min(z, MAX_Z)


def body_minzoom(kind, area_m2):
    if kind in BODY_KIND_Z:
        return BODY_KIND_Z[kind]
    for least, z in BODY_AREA_Z:
        if area_m2 >= least:
            return z
    return BODY_DEFAULT_Z


def structure_minzoom(kind, *, named=False, on_river=False):
    if kind == "dam" and named and on_river:
        return RIVER_DAM_Z
    return STRUCTURE_Z.get(kind, STRUCTURE_DEFAULT_Z)


def flow(osm_intermittent, nhd_category):
    """'perennial', 'intermittent', 'ephemeral' or 'unknown': OpenStreetMap's tag first, then NHD's category."""
    if osm_intermittent is True:
        return "intermittent"
    if osm_intermittent is False:
        return "perennial"
    return {"Perennial": "perennial", "Intermittent": "intermittent", "Ephemeral": "ephemeral"}.get(nhd_category,
                                                                                                   "unknown")


def settings():
    """The rules as water.build records them."""
    return {"order_width_m": ORDER_WIDTH_M, "river_width_m": RIVER_WIDTH_M, "stream_width_m": STREAM_WIDTH_M,
            "intermittent": [INTERMITTENT_FACTOR, INTERMITTENT_MIN_M], "canal_width_m": CANAL_WIDTH_M,
            "osm_width_range_m": OSM_WIDTH_RANGE_M, "main_canal_m": MAIN_CANAL_M,
            "visibility_zoom": VISIBILITY_ZOOM, "canal_z": CANAL_Z, "piped_z": PIPED_Z,
            "body_kind_z": BODY_KIND_Z, "body_area_z": BODY_AREA_Z}
