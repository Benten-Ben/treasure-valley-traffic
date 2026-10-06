"""ACHD's 2022 signal points: traffic-signal poles, pedestrian signals, school flashers, fire signals.

Four hosted layers on ArcGIS Online, made for ACHD's "Official Bike Map 2022"
and frozen since Aug 2, 2022 (docs/08 §8.9). Each holds only OBJECTID and a
Purpose. The traffic-signal layer lists poles, not intersections (Eagle &
Fairview has 12); the intersection build groups them. No license stated.

Each record is versioned in raw.record as '<layer>:<OBJECTID>' (the layers are
frozen, so OBJECTIDs hold), and becomes a core.signal_device.
"""

import time

from .. import arcgis, db, signal_devices

BASE = "https://services2.arcgis.com/9rTo9NcUHIKASKwi/ArcGIS/rest/services"
LAYERS = [  # (service, layer id, default kind)
    ("Traffic_Signals", 15, "signal_pole"),
    ("Pedestrian_Signals", 13, "ped_conventional"),
    ("School_Flasher_Signal", 40, "school_flasher"),
    ("Fire_Signals", 14, "fire_signal"),
]

SOURCE = {
    "name": "achd_signal_points",
    "title": "ACHD signal points, 2022 (poles, pedestrian signals, school flashers, fire signals)",
    "url": f"{BASE}/Traffic_Signals/FeatureServer/15",
    "access": "open",
    "schedule": "30 days",
    "license": "none stated",
    "credit": "Ada County Highway District",
    "notes": "Frozen 2022-08-02 (Official Bike Map 2022): Traffic_Signals/15, Pedestrian_Signals/13, "
             "School_Flasher_Signal/40, Fire_Signals/14. Signal poles, not intersections.",
}


def layer_url(service, layer_id):
    return f"{BASE}/{service}/FeatureServer/{layer_id}"


def kind(service, purpose):
    """A device kind from the layer and ACHD's Purpose text."""
    p = (arcgis.text(purpose) or "").lower()
    if service == "Traffic_Signals":
        return "signal_pole"
    if service == "School_Flasher_Signal" or "school" in p:
        return "school_flasher"
    if service == "Fire_Signals" or "fire" in p or "emergency" in p:
        return "fire_signal"
    if "hybrid" in p or "hawk" in p or "phb" in p:
        return "ped_hybrid"
    if "rrfb" in p or "rapid" in p or "rectangular" in p:
        return "rrfb"
    if "warning" in p or "beacon" in p or "flash" in p:
        return "warning_beacon"
    return "ped_conventional"           # conventional pedestrian signals, and blanks in that layer


def parse(service, features):
    """-> (records, devices) for one layer's Esri JSON features. Features without a point are skipped."""
    records, devices = [], []
    for f in features:
        attrs = f.get("attributes") or {}
        oid = attrs.get("OBJECTID")
        geom = arcgis.point_geojson(f.get("geometry"))
        if oid is None or geom is None:
            continue
        source_id = f"{service}:{int(oid)}"
        payload = {"layer": service, **attrs}
        records.append((source_id, payload, geom))
        purpose = arcgis.text(attrs.get("Purpose"))
        devices.append({"source_id": source_id, "kind": kind(service, purpose), "name": purpose, "geom": geom,
                        "attributes": {"layer": service, "purpose": purpose}})
    return records, devices


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        records, devices, nbytes, skipped = [], [], 0, 0
        for i, (service, layer_id, _) in enumerate(LAYERS):
            if i:
                time.sleep(arcgis.PAUSE_S)
            features, n, f.http_status, f.robots = arcgis.fetch_layer(layer_url(service, layer_id), SOURCE["name"])
            r, d = parse(service, features)
            skipped += len(features) - len(r)
            records += r
            devices += d
            nbytes += n
        f.bytes, f.records = nbytes, len(records)
        signal_devices.check(conn, SOURCE["name"], len(devices))
        new, unchanged, removed = db.upsert_records(conn, SOURCE["name"], records, f.id, f.started_at)
        stats = {"record versions new": new, "unchanged": unchanged, "removed": removed,
                 "without a point": skipped}
        stats.update(signal_devices.store(conn, SOURCE["name"], devices, f.started_at))
    return stats
