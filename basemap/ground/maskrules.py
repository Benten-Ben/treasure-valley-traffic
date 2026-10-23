"""Mask v0's rules (C6): which mapped things cover the ground, what kind they are, and how wide. Standard library only.

Mask v0 is the ground's own product (inputs.PRODUCTS: `ground_mask`), built on the server by mask.py (worker image)
from raw inputs only (inputs.RAW): S1's valley cut of the OpenStreetMap extract, read through GDAL's OSM driver; NHD
HU4 1705; Overture's roofs, as the map's buildings.pmtiles holds them at z15; and CDL 2025. This module holds every
rule mask.py applies, as plain functions of a feature's tags or fields, so they're tested without GDAL:

- road(tags): an OSM highway way's kind, surface class and width, when it covers the ground;
- paving_area(tags, relation), water_area(tags), other_area(tags): an OSM area (a closed way or a multipolygon);
- waterway(tags), other_line(tags): OSM waterways, and the railway, runway and taxiway lines;
- nhd_waterbody(), nhd_area(), nhd_flowline(): NHD's features, from their fields;
- CDL_DEVELOPED: the CDL classes counted as developed (123 and 124, medium and high intensity);
- SAMPLE_BUFFER: how far each kind is grown for sampling (C6: roads and paving +2 m, roofs +1 m, water +5 m).

The OSM tags read are decision 2's (highways, parking, water), the soils design's (rail and aeroway areas, kept out
of sampling) and the owner's of Oct 22 (answer 4: railway tracks, runways and taxiways drawn as lines, so ballast and
runway lines aren't sampled as soil). Their widths below are estimates ⚠️ that wait for calibration in the ten windows.

Widths are OpenStreetMap's own: a `width` tag, else `lanes` x 3.6 m + 2 m, else the class's default below. They are
estimates ⚠️ until the ten windows calibrate them. The roads build's measured widths come from ACHD and ITD
(internal), which the ground never reads (C6, C17), so mask v0 keeps OSM's. A road layer here isn't the map's
roads: it's what covers the ground, for the soil sampler and the painter.

The layers mask.py writes (FlatGeobuf, EPSG:32611, MultiPolygon), named in LAYERS:
- exact, for painting: `roofs`, `roads` (centrelines grown to half their width), `paving` (lots and highway areas),
  `water` (bodies, and waterways grown to half their width; `intermittent` says which may be dry, and a painter
  filters on it);
- buffered, for sampling: `covered`, everything that isn't uncovered ground, each grown by its SAMPLE_BUFFER:
  roofs, roads, paving, water (intermittent too, as C6 says), aeroway and railway areas and lines, and CDL's
  developed land,
  dissolved by `what` in 1 km blocks of the grid (COVER_BLOCK_M).
"""

import re

# ---- the layers ----------------------------------------------------------------------------------------------------

# name -> (use, about, fields as (name, FlatGeobuf type)). Every layer is MultiPolygon in EPSG:32611 with an integer
# id, unique in its layer.
LAYERS = {
    "roofs": ("paint", "Overture's roof footprints (the map's buildings, z15; split where they cross a z15 tile edge)",
              (("id", "int"),)),
    "roads": ("paint", "OSM highway ways that cover the ground (roads, streets, service ways, sidewalks and "
                       "crossings, paved paths and tracks), each centreline grown to half its width",
              (("id", "int"), ("ref", "string"), ("highway", "string"), ("kind", "string"), ("surface", "string"),
               ("width", "double"), ("width_from", "string"), ("bridge", "bool"))),
    "paving": ("paint", "OSM parking lots and highway areas (plazas, service areas)",
               (("id", "int"), ("ref", "string"), ("kind", "string"), ("surface", "string"))),
    "water": ("paint", "NHD and OSM water: bodies, and rivers, streams, canals and ditches grown to half their width "
                       "(NHD's canal and ditch lines aren't painted). intermittent marks water that may be dry: "
                       "painters filter on it (intermittent = 0)",
              (("id", "int"), ("source", "string"), ("ref", "string"), ("kind", "string"), ("intermittent", "bool"),
               ("width", "double"))),
    "covered": ("sample", "everything that isn't uncovered ground, grown for sampling (roofs +1 m, roads and paving "
                          "+2 m, water +5 m, intermittent too, aeroway and railway areas +2 m, CDL developed land as "
                          "it is), dissolved by what in 1 km blocks of the grid",
                (("id", "int"), ("what", "string"), ("buffer", "double"))),
}
PAINT_LAYERS = tuple(n for n, (use, _, _) in LAYERS.items() if use == "paint")
SAMPLE_LAYER = "covered"

# `covered`'s `what` -> metres each is grown for sampling (C6). A line's buffer is added to half its width. Water
# is every water, intermittent too: C6 and the soils design put no condition on it, and a pond that holds water in
# the June photo mustn't be sampled as soil (over-covering only costs samples).
SAMPLE_BUFFER = {"roof": 1.0, "road": 2.0, "paving": 2.0, "water": 5.0, "aeroway": 2.0, "rail": 2.0,
                 "developed": 0.0}

COVER_BLOCK_M = 1000.0    # `covered` is dissolved by what within blocks of this size, on the grid's 10 m edges

# CDL 2025 classes counted as developed land for sampling (the soils design: medium and high intensity).
CDL_DEVELOPED = {123: "developed_medium", 124: "developed_high"}

# ---- surfaces and widths -------------------------------------------------------------------------------------------

PAVED = {"paved", "asphalt", "concrete", "concrete:plates", "concrete:lanes", "paving_stones", "sett", "cobblestone",
         "unhewn_cobblestone", "bricks", "brick", "metal", "metal_grid", "wood", "chipseal", "rubber", "tartan",
         "acrylic", "plastic"}
UNPAVED = {"unpaved", "gravel", "fine_gravel", "compacted", "dirt", "earth", "ground", "grass", "sand", "mud",
           "pebblestone", "rock", "stone", "woodchips", "grass_paver", "soil", "clay", "salt", "snow", "ice"}


def surface_class(tags):
    """'paved', 'unpaved' or 'unknown', from `surface` (and a track's `tracktype=grade1`, which is paved)."""
    s = (tags.get("surface") or "").strip().lower()
    if s in PAVED:
        return "paved"
    if s in UNPAVED:
        return "unpaved"
    if tags.get("highway") == "track" and tags.get("tracktype") == "grade1":
        return "paved"
    return "unknown"


_NUMBER = r"(\d+(?:\.\d+)?)"


def metres(value):
    """A width tag in metres, or None: '12', '12.5', '12 m', '12m', '40 ft', "40'", "12'6\"" (OSM's default unit is
    metres; feet and inches as the wiki writes them). A list, a range or anything else is None."""
    if value is None:
        return None
    v = str(value).strip().lower().replace(",", ".")
    m = re.fullmatch(_NUMBER + r"\s*(m|meters?|metres?)?", v)
    if m:
        return float(m.group(1))
    m = re.fullmatch(_NUMBER + r"\s*(ft|feet|')", v)
    if m:
        return float(m.group(1)) * 0.3048
    m = re.fullmatch(r"(\d+)\s*'\s*(\d+(?:\.\d+)?)\s*(\"|in)?", v)
    if m:
        return int(m.group(1)) * 0.3048 + float(m.group(2)) * 0.0254
    return None


def _width_tag(tags, low, high):
    w = metres(tags.get("width"))
    return w if w is not None and low <= w <= high else None


def lanes(tags):
    """A way's `lanes` as a whole number from 1 to 12, or None (missing, a list or out of range)."""
    v = (tags.get("lanes") or "").strip()
    if not v.isdigit():
        return None
    n = int(v)
    return n if 1 <= n <= 12 else None


LANE_M = 3.6              # a lane ⚠️
EDGE_M = 1.0              # gutter or shoulder, each side of a carriageway ⚠️

MAJOR = {"motorway", "trunk", "primary", "secondary", "tertiary"}
MAJOR_LINKS = {f"{c}_link" for c in MAJOR}
STREETS = {"residential", "unclassified", "living_street", "road", "busway"}
SIDEWALKS = {"sidewalk", "crossing", "access_aisle", "traffic_island"}   # footway=*, on a footway, path or cycleway
WALK_CLASSES = {"footway", "path", "cycleway"}

# Class widths in metres, (two-way, one-way) ⚠️: estimates until the ten windows calibrate them. Local streets use the
# roads design's default (10.4 m curbed; 7.3 m rural for unclassified and road; DECISIONS Oct 8, decision 10).
CLASS_WIDTH = {
    "motorway": (24.0, 12.0), "trunk": (20.0, 11.0), "primary": (18.0, 10.0), "secondary": (15.0, 9.0),
    "tertiary": (12.0, 7.5),
    "residential": (10.4, 7.0), "unclassified": (7.3, 5.0), "road": (7.3, 5.0), "living_street": (7.0, 5.0),
    "busway": (7.0, 4.0), "service": (5.5, 4.0), "track": (3.5, 3.5), "pedestrian": (6.0, 6.0),
    "cycleway": (2.5, 2.5), "footway": (2.0, 2.0), "path": (2.0, 2.0), "bridleway": (2.5, 2.5), "steps": (2.0, 2.0),
}
for _link in MAJOR_LINKS:
    CLASS_WIDTH[_link] = (8.0, 6.0)
SERVICE_WIDTH = {"alley": 5.0, "driveway": 4.0, "parking_aisle": 6.5, "drive-through": 4.0, "emergency_access": 4.0}
FOOTWAY_WIDTH = {"sidewalk": 1.5, "crossing": 3.0, "access_aisle": 1.5, "traffic_island": 2.0}

MOTOR = MAJOR | MAJOR_LINKS | STREETS | {"service"}


def oneway(tags):
    """True for a one-way carriageway: oneway=yes|true|1|-1|reversible, a roundabout, or a motorway (implied)."""
    v = tags.get("oneway")
    if v == "no":
        return False
    if v in ("yes", "true", "1", "-1", "reversible"):
        return True
    return tags.get("junction") in ("roundabout", "circular") or tags.get("highway") in ("motorway", "motorway_link")


def below_ground(tags):
    """True for a way under the ground or indoors, where the photo can't see it: a tunnel or culvert, an underground
    or indoor location. (A building passage is at ground level, under a roof that covers it anyway.)"""
    return (tags.get("tunnel") in ("yes", "culvert", "flooded") or tags.get("location") in ("underground", "indoor")
            or tags.get("indoor") == "yes")


def road_width(tags):
    """(metres, 'width' | 'lanes' | 'class') for a highway way: its width tag (1-80 m), else lanes x 3.6 m + 2 m for
    a road with lanes tagged, else its class's default."""
    hw = tags.get("highway")
    w = _width_tag(tags, 1.0, 80.0)
    if w is not None:
        return w, "width"
    n = lanes(tags)
    if n is not None and hw in MOTOR:
        return n * LANE_M + 2 * EDGE_M, "lanes"
    if hw == "service" and tags.get("service") in SERVICE_WIDTH:
        return SERVICE_WIDTH[tags["service"]], "class"
    if hw in WALK_CLASSES and tags.get("footway") in FOOTWAY_WIDTH:
        return FOOTWAY_WIDTH[tags["footway"]], "class"
    two, one = CLASS_WIDTH[hw]
    return (one if oneway(tags) else two), "class"


def road(tags):
    """For an OSM highway way (a line), (kind, surface class, width m, width_from) when it covers the ground, else
    None. Kinds:
      major    motorway to tertiary, and their links
      street   residential, unclassified, living_street, road, busway
      service  every service way (alleys, driveways, parking aisles, ...)
      walkway  sidewalks, crossings, access aisles and traffic islands (footway=* on a footway, path or cycleway),
               and pedestrian streets unless tagged unpaved
      path     cycleways and steps unless tagged unpaved; footways, paths and bridleways only when tagged paved
      track    tracks tagged paved (or tracktype=grade1)
    Roads, streets, service ways and sidewalks count whatever their surface (a gravel road isn't the soil either:
    these are the ways the roads plugin draws). An unpaved path or track is trodden soil, so it stays ground. Ways
    drawn as areas
    (area=yes) are areas (paving_area), and ways under the ground or indoors don't count. Every way of these classes
    that osm_extract's partition gives osm_valley, osm_street or osm_paving counts (test_maskrules checks it);
    osm_valley also keeps other classes when they carry lanes (one raceway on Oct 11), which don't."""
    hw = tags.get("highway")
    if not hw or hw not in CLASS_WIDTH or tags.get("area") == "yes" or below_ground(tags):
        return None
    surf = surface_class(tags)
    if hw in MAJOR or hw in MAJOR_LINKS:
        kind = "major"
    elif hw in STREETS:
        kind = "street"
    elif hw == "service":
        kind = "service"
    elif hw in WALK_CLASSES and tags.get("footway") in SIDEWALKS:
        kind = "walkway"
    elif hw == "pedestrian":
        kind = "walkway" if surf != "unpaved" else None
    elif hw in ("cycleway", "steps"):
        kind = "path" if surf != "unpaved" else None
    elif hw in ("footway", "path", "bridleway"):
        kind = "path" if surf == "paved" else None
    elif hw == "track":
        kind = "track" if surf == "paved" else None
    else:
        kind = None
    if kind is None:
        return None
    w, src = road_width(tags)
    return kind, surf, w, src


def bridge(tags):
    """True for a way on a bridge (the photo shows its deck; the map drapes it, decision 10)."""
    v = tags.get("bridge")
    return bool(v) and v != "no"


# ---- areas ---------------------------------------------------------------------------------------------------------

HIGHWAY_AREAS = {"pedestrian", "footway", "service", "residential", "unclassified", "living_street", "cycleway",
                 "path", "track", "road", "busway"}
NOT_SURFACE_PARKING = {"underground", "multi-storey", "rooftop", "carports"}


def paving_area(tags, relation=False):
    """For an OSM area, (kind, surface class) when it's mapped paving, else None. relation: it's a multipolygon
    relation (an area by definition, which seldom says area=yes); otherwise a closed way.
      parking       amenity=parking at ground level (not underground, multi-storey, rooftop or carports, which
                    roofs or the ground hide), whatever its surface
      highway_area  a highway drawn as an area (a closed way with area=yes, or a multipolygon relation such as a
                    pedestrian plaza) or area:highway=*, unless tagged unpaved"""
    if tags.get("building") not in (None, "no") or below_ground(tags):
        return None
    surf = surface_class(tags)
    if tags.get("amenity") == "parking" and tags.get("parking") not in NOT_SURFACE_PARKING:
        return "parking", surf
    is_area = relation or tags.get("type") == "multipolygon" or tags.get("area") == "yes"
    if tags.get("area:highway") not in (None, "no") or (tags.get("highway") in HIGHWAY_AREAS and is_area
                                                         and tags.get("area") != "no"):
        return ("highway_area", surf) if surf != "unpaved" else None
    return None


WATER_KIND = {"river": "river", "riverbank": "river", "oxbow": "lake", "stream": "stream", "stream_pool": "stream",
              "canal": "canal", "ditch": "ditch", "drain": "ditch", "lake": "lake", "pond": "lake",
              "lagoon": "lake", "reservoir": "reservoir", "basin": "basin", "wastewater": "reservoir",
              "fish_pass": "canal", "moat": "lake", "reflecting_pool": "pool", "pool": "pool",
              "swimming_pool": "pool"}
DRY_BASINS = {"detention", "infiltration", "evaporation"}


def intermittent(tags):
    """True when the water may be dry: intermittent=yes, seasonal=* (not no), or water=intermittent."""
    return (tags.get("intermittent") == "yes" or tags.get("seasonal") not in (None, "no")
            or tags.get("water") == "intermittent")


def water_area(tags):
    """For an OSM area, (kind, intermittent) when it's water, else None: natural=water (kind from water=*, default
    lake), waterway=riverbank, landuse=reservoir|basin (a detention, infiltration or evaporation basin without
    natural=water is intermittent), leisure=swimming_pool outdoors, or a bare water=*. Wetlands aren't water
    (they're vegetation, P14)."""
    if below_ground(tags) or tags.get("covered") == "yes" or tags.get("building") not in (None, "no"):
        return None
    water = tags.get("water")
    if tags.get("natural") == "water":
        return WATER_KIND.get(water, "lake"), intermittent(tags)
    if tags.get("waterway") == "riverbank":
        return "river", intermittent(tags)
    if tags.get("landuse") == "reservoir":
        return WATER_KIND.get(water, "reservoir"), intermittent(tags)
    if tags.get("landuse") == "basin":
        return "basin", intermittent(tags) or tags.get("basin") in DRY_BASINS
    if tags.get("leisure") == "swimming_pool":
        return "pool", intermittent(tags)
    if water and water in WATER_KIND:
        return WATER_KIND[water], intermittent(tags)
    return None


AEROWAY_AREAS = {"apron", "runway", "taxiway", "helipad"}


def other_area(tags):
    """For an OSM area, (what, kind) when it covers the ground for sampling only: an aeroway apron, runway, taxiway or
    helipad ('aeroway'), or a railway yard, landuse=railway ('rail'); the soils design's "rail and aeroway areas".
    Not painted: the map doesn't draw them as surfaces, so the photo shows them."""
    if below_ground(tags):
        return None
    if tags.get("aeroway") in AEROWAY_AREAS:
        return "aeroway", tags["aeroway"]
    if tags.get("landuse") == "railway":
        return "rail", "rail_yard"
    return None


# ---- lines ---------------------------------------------------------------------------------------------------------

WATERWAY_WIDTH = {"river": 15.0, "canal": 6.0, "stream": 2.5, "drain": 3.0, "ditch": 2.0}   # ⚠️ estimates


def waterway(tags):
    """For an OSM line, (kind, intermittent, width m) when it's a waterway at the surface (river, canal, stream, drain
    or ditch; not in a culvert or tunnel, underground or covered), else None. Width: its width tag (0.3-500 m), else
    WATERWAY_WIDTH."""
    ww = tags.get("waterway")
    if ww not in WATERWAY_WIDTH or below_ground(tags) or tags.get("covered") == "yes":
        return None
    w = _width_tag(tags, 0.3, 500.0)
    return WATER_KIND[ww], intermittent(tags), (w if w is not None else WATERWAY_WIDTH[ww])


RAILWAYS = {"rail", "light_rail", "narrow_gauge", "preserved"}
RAIL_BED_M = 5.0          # one track's bed, ballast included ⚠️ (waits for calibration in the ten windows)
AEROWAY_WIDTH = {"runway": 45.0, "taxiway": 23.0}    # ⚠️ (150 and 75 ft, common sizes; wait for calibration)


def other_line(tags):
    """For an OSM line, (what, kind, width m) when it covers the ground for sampling only: a railway track's bed
    ('rail', 5 m per track by its `tracks` tag, one if missing; sidings and yards too, not trams, which run in streets), or a runway or taxiway drawn as a line
    ('aeroway', its width tag else AEROWAY_WIDTH). Else None. Not painted: the map doesn't draw them as surfaces."""
    if below_ground(tags) or tags.get("area") == "yes":
        return None
    if tags.get("railway") in RAILWAYS:
        t = (tags.get("tracks") or "").strip()
        n = int(t) if t.isdigit() and 1 <= int(t) <= 6 else 1      # a line drawn once for several tracks
        return "rail", tags["railway"], RAIL_BED_M * n
    a = tags.get("aeroway")
    if a in AEROWAY_WIDTH:
        w = _width_tag(tags, 5.0, 100.0)
        return "aeroway", a, (w if w is not None else AEROWAY_WIDTH[a])
    return None


# ---- NHD -----------------------------------------------------------------------------------------------------------

NHD_STREAM_WIDTH = ((5, 8.0), (3, 4.0), (0, 2.0))   # (from stream order, metres) ⚠️; wide rivers are NHD areas
NHD_CANAL_WIDTH = 4.0                                # ⚠️ most are laterals; the main canals are in OSM too


def _nhd_intermittent(f):
    return (f.get("hydrographiccategory") or "").lower() in ("intermittent", "ephemeral")


def nhd_waterbody(f):
    """For an NHD waterbody's fields, (kind, intermittent) when it's open water (Lake/Pond, Reservoir), else None.
    Swamp/Marsh and Playa aren't open water."""
    t = f.get("ftype_name")
    if t == "Lake/Pond":
        return "lake", _nhd_intermittent(f)
    if t == "Reservoir":
        return "reservoir", _nhd_intermittent(f)
    return None


def nhd_area(f):
    """For an NHD area's fields, (kind, intermittent) for Stream/River and Canal/Ditch polygons, else None.
    Inundation areas, washes, dams and spillways aren't water most of the year."""
    t = f.get("ftype_name")
    if t == "Stream/River":
        return "river", _nhd_intermittent(f)
    if t == "Canal/Ditch":
        return "canal", _nhd_intermittent(f)
    return None


def nhd_flowline(f):
    """For an NHD flowline's fields, (kind, intermittent, width m, painted) for streams, rivers, canals and ditches
    at the surface, else None. Pipelines, connectors and artificial paths (the centre lines through NHD's own water
    polygons, which are read as areas) are left out.

    painted is False for canal and ditch lines: they're kept out of sampling but not painted. Much of NHD's canal
    geometry is 1:24,000-era and some has since been piped or built over (on Oct 11, 46% of the painted NHD canal
    area lay over 20 m from any OSM water, and 6.8 ha under roofs). OSM's canals are painted, and water's conflated
    mask (P4-data) decides the rest."""
    c = f.get("class")
    if (f.get("relationshiptosurface") or "").lower() == "underground":
        return None
    if c == "stream_river":
        order = f.get("streamorder") or 0
        width = next(w for o, w in NHD_STREAM_WIDTH if order >= o)
        return "stream", _nhd_intermittent(f), width, True
    if c == "canal_ditch":
        return "canal", _nhd_intermittent(f), NHD_CANAL_WIDTH, False
    return None
