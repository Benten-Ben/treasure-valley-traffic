"""COMPASS's Regional_Signals: signal devices across the valley's operators, on swidrdc.org.

Layer 3 of COMPASSData/I_84DetourRoutesRegional (1,078 points: ACHD 833,
Nampa 166, Caldwell 28, ITD 23, Nampa and Canyon highway districts 18). No
date ⚠️ and no catalog entry: "meant only for reference". Used internally
until COMPASS answers (owner, Oct 6); credit COMPASS. The host has no
robots.txt rules but sometimes resets connections, so a failed request is
retried once.

Besides traffic signals, the layer lists pedestrian signals (HAWK, RRFB,
conventional), flashing beacons, school flashers and fire signals in its
its_device field; each becomes the matching core.signal_device kind, and only
traffic signals feed the intersection build. There's no Synchro ID, so records
are keyed 'loc:<operator>:<kind>:<normalized location>' (several devices often
share a location, and school flashers are listed by street alone, so repeats
get '#2', '#3', ... west to east); objectid is left out of the stored record.

Checked Oct 6, 2026: 586 of the 1,078 points are traffic signals, and 584 of
those lie within 10 m of a Signalized_Intersections point; the rest are 166
school flashers, 126 RRFBs, 118 HAWKs, 35 flashing beacons, 23 fire signals and
22 conventional pedestrian signals. So the layer confirms COMPASS's 585 rather
than adding signals.
"""

from .. import arcgis, db, signal_devices, streets
from . import compass_signals

LAYER = "https://swidrdc.org/arcgis/rest/services/COMPASSData/I_84DetourRoutesRegional/MapServer/3"

SOURCE = {
    "name": "compass_regional_signals",
    "title": "COMPASS regional signal devices (Regional_Signals)",
    "url": LAYER,
    "access": "open",
    "schedule": "7 days",
    "license": "none stated",
    "credit": "COMPASS (Community Planning Association of Southwest Idaho) and its member agencies",
    "notes": "INTERNAL ONLY until COMPASS answers (owner, Oct 6): on swidrdc.org only, no catalog entry, "
             "'meant only for reference', no date. Keyed by operator + location.",
}

DEVICE_KIND = [  # (words in its_device, kind), first match wins
    ("RRFB", "rrfb"), ("RECTANGULAR RAPID", "rrfb"),
    ("HAWK", "ped_hybrid"), ("HYBRID", "ped_hybrid"),
    ("PEDX WITH", "warning_beacon"),
    ("PEDX", "ped_conventional"),
    ("SCHOOL", "school_flasher"),
    ("FIRE", "fire_signal"), ("EMERGENCY", "fire_signal"),
    ("BEACON", "warning_beacon"), ("FLASH", "warning_beacon"),
    ("TRAFFIC SIGNAL", "signal_intersection"),
]


def kind(device):
    """its_device to a core.signal_device kind; blanks count as traffic signals (the layer's subject)."""
    d = (arcgis.text(device) or "").upper()
    for words, k in DEVICE_KIND:
        if words in d:
            return k
    return "signal_intersection"


def attributes(attrs):
    return {
        "operator": arcgis.text(attrs.get("jurisdicti")),
        "owner": arcgis.text(attrs.get("owner")),
        "city": compass_signals.title(attrs.get("city")),
        "county": compass_signals.title(attrs.get("county")),
        "location": arcgis.text(attrs.get("location")),
        "device": arcgis.text(attrs.get("its_device")),
        "i84_detour": arcgis.yes_no(attrs.get("i84detourr")),
        "coordinated": arcgis.yes_no(attrs.get("coordinated")),
        "coord_group": arcgis.text(attrs.get("coor_group")),
    }


def parse(features):
    """-> (records, devices)."""
    records, devices = [], []
    kind_of = lambda attrs: kind(attrs.get("its_device"))
    for source_id, attrs, geom in compass_signals.keyed(features, synchro_field=None, kind_of=kind_of):
        records.append((source_id, {k: v for k, v in attrs.items() if k.lower() != "objectid"}, geom))
        a = attributes(attrs)
        devices.append({"source_id": source_id, "kind": kind(a["device"]),
                        "name": streets.display_location(a["location"]) if a["location"] else None,
                        "geom": geom, "attributes": a})
    return records, devices


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        features, f.bytes, f.http_status, f.robots = arcgis.fetch_layer(LAYER, SOURCE["name"], order_by="objectid")
        records, devices = parse(features)
        f.records = len(records)
        signal_devices.check(conn, SOURCE["name"], len(devices))
        new, unchanged, removed = db.upsert_records(conn, SOURCE["name"], records, f.id, f.started_at)
        stats = {"record versions new": new, "unchanged": unchanged, "removed": removed,
                 "without a point": len(features) - len(records)}
        stats.update(signal_devices.store(conn, SOURCE["name"], devices, f.started_at))
    return stats
