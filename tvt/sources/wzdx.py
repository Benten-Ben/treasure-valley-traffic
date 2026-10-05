"""Work zones from the 511 Idaho WZDx feed (no API key needed)."""

from .. import in_bbox
from ..geo import line_vertices, representative_point
from ..http import get_json

URL = "https://511.idaho.gov/api/wzdx"


def _in_valley(geom):
    pts = line_vertices(geom) or ([representative_point(geom)] if geom else [])
    return any(p and in_bbox(*p) for p in pts)


def work_zones(store):
    feed = get_json(URL)
    items = []
    for ft in feed.get("features", []):
        geom = ft.get("geometry")
        if not _in_valley(geom):
            continue
        p = ft.get("properties", {})
        core = p.get("core_details", {})
        items.append((ft.get("id"), geom, {
            "roads": core.get("road_names"), "direction": core.get("direction"),
            "description": core.get("description"), "event_type": core.get("event_type"),
            "start": p.get("start_date"), "end": p.get("end_date"),
            "vehicle_impact": p.get("vehicle_impact")}))
    return store.sync_events("wzdx", "work_zone", items)
