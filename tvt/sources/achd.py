"""Ada County Highway District GIS services (gis.achdidaho.org, ArcGIS Online)."""

from .. import in_bbox
from ..geo import esri_to_geojson
from ..http import arcgis_query
from ..store import point

TRAFFIC = "https://gis.achdidaho.org/server/rest/services/Traffic/Traffic_Cameras/MapServer"
AGOL = "https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services"
SIGNAL_LAYERS = {  # service/layer -> signal type (2022 bike-map data)
    "Traffic_Signals/FeatureServer/15": "traffic",
    "Pedestrian_Signals/FeatureServer/13": "pedestrian",
    "School_Flasher_Signal/FeatureServer/40": "school_flasher",
    "Fire_Signals/FeatureServer/14": "fire",
}


def cameras(store):
    """Camera inventory. The GIS layer lists some cameras twice; keep the located copy."""
    cams = {}
    for ft in arcgis_query(f"{TRAFFIC}/26", {"where": "1=1", "outFields": "*", "outSR": 4326}):
        a = ft["attributes"]
        cid = int(a["camID"])
        if cid not in cams or cams[cid]["Latitude"] is None:
            cams[cid] = a
    items = [(cid, point(a["Longitude"], a["Latitude"]),
              {"label": " ".join(a["label"].split()), "image_url": a["hyperlink"],
               "camera_timestamp": a.get("camtimestamp")})
             for cid, a in cams.items() if a["Latitude"] is not None]
    return store.upsert_features("achd_cameras", "camera", items)


def _text(*parts):
    return " / ".join(p.strip() for p in parts if p and p.strip())


def live(store):
    """Roadwork (layer 22), incidents (21) and message-board text (28)."""
    n = 0
    road = arcgis_query(f"{TRAFFIC}/22", {"where": "1=1", "outFields": "*", "outSR": 4326})
    n += store.sync_events("achd_live", "roadwork", [
        (a["ConstructionID"], point(a["Lon"], a["Lat"]),
         {"location": a.get("Location"), "description": a.get("Description"),
          "lane_pattern_url": a.get("hyperlink")})
        for a in (f["attributes"] for f in road) if a.get("Lat")])
    inc = arcgis_query(f"{TRAFFIC}/21", {"where": "1=1", "outFields": "*", "outSR": 4326})
    n += store.sync_events("achd_live", "incident", [
        (a["IncidId"], point(a["Lon"], a["Lat"]),
         {"location": a.get("Location"), "description": a.get("Description")})
        for a in (f["attributes"] for f in inc) if a.get("Lat")])
    signs = arcgis_query(f"{TRAFFIC}/28", {"where": "1=1", "outFields": "*", "outSR": 4326})
    msgs = []
    for a in (f["attributes"] for f in signs):
        lines = [a.get(f"P{p}L{l}") for p in (1, 2) for l in (1, 2, 3, 4)]
        text = _text(*lines)
        if text and a.get("Lat"):
            # One event per distinct message, so message changes show up as new events.
            msgs.append((f"{a['SignID']}:{text}", point(a["Lon"], a["Lat"]),
                         {"sign_id": a["SignID"], "location": a.get("Location"), "text": text}))
    n += store.sync_events("achd_live", "message_sign", msgs)
    return n


def signal_assets(store):
    """Signal points from ACHD's 2022 layers (poles/heads, not intersections)."""
    items = []
    for layer, sig_type in SIGNAL_LAYERS.items():
        for ft in arcgis_query(f"{AGOL}/{layer}", {"where": "1=1", "outFields": "*",
                                                  "outSR": 4326}):
            geom = esri_to_geojson(ft.get("geometry"))
            if not geom:
                continue
            lon, lat = geom["coordinates"]
            if in_bbox(lat, lon):
                items.append((f"{sig_type}:{ft['attributes']['OBJECTID']}", geom,
                              {"signal_type": sig_type}))
    return store.upsert_features("achd_signal_assets", "signal_asset", items)
