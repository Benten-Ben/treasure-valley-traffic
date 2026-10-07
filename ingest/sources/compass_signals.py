"""COMPASS's Signalized_Intersections: one point per signalized intersection in Ada and Canyon.

A hosted layer on ArcGIS Online (585 points: Ada 465, Canyon 120), built in
2019 for the regional signal operations plan and edited since (last Aug 2026).
It names each signal's operator, owner, coordination group and ACHD Synchro
ID, and per approach the right-turn lanes, turn phasing and modelled peak-hour
turn volumes (year unknown ⚠️). No license; COMPASS calls it "meant only for
reference". Used internally until COMPASS answers (owner, Oct 6); credit
COMPASS.

Keys: COMPASS overwrites the layer, so OBJECTID isn't stable. Records are keyed
'synchro:<ACHD_Synchro_ID>' (all ACHD signals have one), else
'loc:<operator>:<normalized location>'. Three Synchro IDs are listed on two
points each (two of the pairs kilometres apart: errors), so a shared ID is
keyed 'synchro:<id>:<normalized location>'. OBJECTID and the two Google Maps
link fields are left out of the stored record.

Approaches: COMPASS names them by travel direction, so its northbound (NB)
approach is the intersection's south leg.
"""

from collections import defaultdict

from plugins.roads.ingest import streets

from .. import arcgis, db, signal_devices

LAYER = ("https://services6.arcgis.com/2S9FP4vfcUQQ8G1T/arcgis/rest/services/"
         "Signalized_Intersections/FeatureServer/0")

SOURCE = {
    "name": "compass_signals",
    "title": "COMPASS signalized intersections (Signalized_Intersections)",
    "url": LAYER,
    "access": "open",
    "schedule": "7 days",
    "license": "none stated",
    "credit": "COMPASS (Community Planning Association of Southwest Idaho) and its member agencies",
    "notes": "INTERNAL ONLY until COMPASS answers (owner, Oct 6): 'meant only for reference', no license. "
             "Keyed by ACHD Synchro ID, else operator + location (OBJECTID resets when COMPASS overwrites). "
             "Google link fields not stored.",
}

DROP = {"OBJECTID", "Street_View", "Google_Earth"}       # unstable ID; links to Google Maps

APPROACH_LEG = {"NB": "S", "SB": "N", "EB": "W", "WB": "E"}   # travel direction -> the leg it comes from

# Synchro's phasing codes as COMPASS lists them ('D.' = Dallas phasing, a flashing-yellow variant).
PHASING = {"prot": "protected", "perm": "permitted", "pm+pt": "protected-permitted",
           "pt+pm": "protected-permitted", "d.p+p": "protected-permitted", "d.pm": "permitted",
           "free": "free", "split": "split", "custom": "custom", "ovl": "overlap", "overlap": "overlap",
           "pt+ov": "protected-overlap", "pm+ov": "permitted-overlap"}


def phasing(v):
    t = (arcgis.text(v) or "").lower()
    if not t or t in ("none", "n/a", "na", "-"):
        return None
    return PHASING.get(t, t)


def control(crossing_type):
    """COMPASS's intersection type (field CrossingTy, alias Int_Type: 'Full Signal', 'Half Signal',
    'U-Turn') as core.intersection.control."""
    t = (arcgis.text(crossing_type) or "").lower()
    if "half" in t:
        return "half_signal"
    if "u-turn" in t or "uturn" in t or "u turn" in t:
        return "signal_uturn"
    return "signal"


def title(v):
    t = arcgis.text(v)
    return t.title() if t and t.isupper() else t


def payload(attrs):
    return {k: v for k, v in attrs.items() if k not in DROP}


def synchro_id(attrs, synchro_field="ACHD_Synchro_ID"):
    n = arcgis.number(attrs.get(synchro_field)) if synchro_field else None
    return int(n) if n is not None else None


def location_part(attrs, geom):
    loc = streets.location_key(arcgis.text(attrs.get("location")) or "")
    if not loc:
        lon, lat = geom["coordinates"]
        loc = f"pt {lon:.4f},{lat:.4f}"
    return loc


def base_key(attrs, geom, synchro_field="ACHD_Synchro_ID", shared_synchro=(), kind=None):
    """'synchro:<id>'; for a Synchro ID listed on more than one point (a COMPASS error),
    'synchro:<id>:<location>'; without one, 'loc:<operator>:<location>', or with a device
    kind (Regional_Signals), 'loc:<operator>:<kind>:<location>'."""
    synchro = synchro_id(attrs, synchro_field)
    if synchro is not None:
        if synchro in shared_synchro:
            return f"synchro:{synchro}:{location_part(attrs, geom)}"
        return f"synchro:{synchro}"
    operator = (arcgis.text(attrs.get("jurisdicti")) or "unknown").lower()
    if kind:
        return f"loc:{operator}:{kind}:{location_part(attrs, geom)}"
    return f"loc:{operator}:{location_part(attrs, geom)}"


def keyed(features, synchro_field="ACHD_Synchro_ID", kind_of=None):
    """-> [(source_id, attrs, geom)] for features with a point. Keys that still come out
    twice (the same location listed twice) get '#2', '#3', ... in west-to-east order.
    kind_of(attrs), if given, adds a device kind to location keys."""
    points = []
    for f in features:
        geom = arcgis.point_geojson(f.get("geometry"))
        if geom is not None:
            points.append((f.get("attributes") or {}, geom))
    seen = defaultdict(int)
    for attrs, _ in points:
        s = synchro_id(attrs, synchro_field)
        if s is not None:
            seen[s] += 1
    shared = {s for s, n in seen.items() if n > 1}
    groups = defaultdict(list)
    for attrs, geom in points:
        kind = kind_of(attrs) if kind_of else None
        groups[base_key(attrs, geom, synchro_field, shared, kind)].append((attrs, geom))
    out = []
    for key, items in groups.items():
        items.sort(key=lambda ag: (ag[1]["coordinates"][0], ag[1]["coordinates"][1]))
        for i, (attrs, geom) in enumerate(items):
            out.append((key if i == 0 else f"{key}#{i + 1}", attrs, geom))
    return out


def approaches(attrs):
    """Per-approach fields by travel direction, with the leg each approach comes from."""
    out = {}
    for d, leg in APPROACH_LEG.items():
        vols = {m: arcgis.number(attrs.get(f"{d}{m}_Vol")) for m in ("L", "T", "R")}
        a = {
            "leg": leg,
            "right_turn_lanes": arcgis.number(attrs.get(f"{d}_RT_Lanes")),
            "left_turn_phasing": phasing(attrs.get(f"{d}_LT_Phasing")),
            "right_turn_phasing": phasing(attrs.get(f"{d}_RT_Phasing")),
            "volumes": {m: v for m, v in vols.items() if v is not None} or None,
        }
        if any(v is not None for k, v in a.items() if k != "leg"):
            out[d] = a
    return out


def attributes(attrs):
    """The fields the build and the map use, cleaned."""
    synchro = arcgis.number(attrs.get("ACHD_Synchro_ID"))
    coordinated = arcgis.yes_no(attrs.get("coordinated"))
    if coordinated is None:
        coordinated = arcgis.yes_no(attrs.get("Coordinate"))
    return {
        "operator": arcgis.text(attrs.get("jurisdicti")),
        "owner": arcgis.text(attrs.get("owner")),
        "city": title(attrs.get("city")),
        "county": title(attrs.get("county")),
        "location": arcgis.text(attrs.get("location")),
        "type": arcgis.text(attrs.get("CrossingTy")),
        "control": control(attrs.get("CrossingTy")),
        "coordinated": coordinated,
        "coord_group": arcgis.text(attrs.get("coor_group")),
        "synchro_id": int(synchro) if synchro is not None else None,
        "skew": arcgis.yes_no(attrs.get("Skew")),
        "five_legged": arcgis.yes_no(attrs.get("five_legged")),
        "lpi": arcgis.text(attrs.get("LPI_Status")),
        "aps": arcgis.text(attrs.get("APS")),
        "tev": arcgis.number(attrs.get("TEV")),
        "approaches": approaches(attrs),
    }


def parse(features):
    """-> (records, devices)."""
    records, devices = [], []
    for source_id, attrs, geom in keyed(features):
        records.append((source_id, payload(attrs), geom))
        a = attributes(attrs)
        devices.append({"source_id": source_id, "kind": "signal_intersection",
                        "name": streets.display_location(a["location"]) if a["location"] else None,
                        "geom": geom, "attributes": a})
    return records, devices


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        features, f.bytes, f.http_status, f.robots = arcgis.fetch_layer(LAYER, SOURCE["name"])
        records, devices = parse(features)
        f.records = len(records)
        signal_devices.check(conn, SOURCE["name"], len(devices))
        new, unchanged, removed = db.upsert_records(conn, SOURCE["name"], records, f.id, f.started_at)
        stats = {"record versions new": new, "unchanged": unchanged, "removed": removed,
                 "without a point": len(features) - len(records)}
        stats.update(signal_devices.store(conn, SOURCE["name"], devices, f.started_at))
    return stats
