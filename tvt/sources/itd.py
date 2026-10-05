"""Idaho Transportation Department GIS: AADT, automatic counters, crashes."""

import json
from datetime import datetime, timezone

from .. import BBOX
from ..geo import esri_to_geojson
from ..http import arcgis_query, get_json
from ..store import point

TRAFFIC = "https://gisp.itd.idaho.gov/server/rest/services/GDWarehouse/Traffic/MapServer"
CRASHES = "https://gis.itd.idaho.gov/arcgisprod/rest/services/ArcGISOnline/CrashLayers/MapServer/11"
CRASH_YEARS = 5  # most recent years to keep


def _envelope():
    s, w, n, e = BBOX
    return {"geometry": json.dumps({"xmin": w, "ymin": s, "xmax": e, "ymax": n,
                                    "spatialReference": {"wkid": 4326}}),
            "geometryType": "esriGeometryEnvelope", "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects", "outSR": 4326}


def aadt(store):
    years = get_json(f"{TRAFFIC}/1/query", {
        "where": "AADT IS NOT NULL", "outFields": "Year", "returnDistinctValues": "true",
        "returnGeometry": "false", "f": "json"})
    latest = max(int(f["attributes"]["Year"]) for f in years["features"])
    feats = arcgis_query(f"{TRAFFIC}/1", {
        "where": f"Year={latest}", "outFields": "OBJECTID,Year,RouteID,DescriptionFrom,"
        "DescriptionTo,AADT,CommercialAADT,DHV", **_envelope()})
    items = []
    for ft in feats:
        a, geom = ft["attributes"], esri_to_geojson(ft.get("geometry"))
        if geom:
            items.append((f"{a['Year']}:{a['OBJECTID']}", geom, {
                "year": a["Year"], "route_id": a["RouteID"], "from": a["DescriptionFrom"],
                "to": a["DescriptionTo"], "aadt": a["AADT"], "truck_aadt": a["CommercialAADT"],
                "design_hour_volume": a["DHV"]}))
    return store.upsert_features("itd_aadt", "aadt_segment", items)


def atr_monthly(store):
    feats = arcgis_query(f"{TRAFFIC}/0", {
        "where": "County_NAME IN ('Ada','Canyon') AND Count_ IS NOT NULL",
        "outFields": "StationID,Name,RoadName,County_NAME,Year,Month,Count_,Annual",
        "outSR": 4326})
    stations, obs = {}, []
    for ft in feats:
        a, g = ft["attributes"], ft.get("geometry") or {}
        sid = a["StationID"]
        if g.get("x") is not None:
            stations[sid] = (point(g["x"], g["y"]),
                             {"name": a["Name"], "road": a["RoadName"], "county": a["County_NAME"]})
        obs.append((sid, f"{a['Year']}-{int(a['Month']):02d}", "monthly_adt", a["Count_"]))
        if a.get("Annual"):
            obs.append((sid, f"{a['Year']}", "aadt", a["Annual"]))
    store.upsert_features("itd_atr", "counter_station",
                          [(sid, g, p) for sid, (g, p) in stations.items()])
    return store.add_observations("itd_atr", obs)


def crashes(store):
    first_year = datetime.now(timezone.utc).year - CRASH_YEARS
    feats = arcgis_query(CRASHES, {
        "where": f"Accident_Year >= '{first_year}'",
        "outFields": "Serial_Number,Severity,Accident_Year,Accident_Date_Time,"
                     "Number_Of_Fatalities,Number_Of_Injuries,IntersectionRelated,County",
        **_envelope()}, page_size=10000)
    items = []
    for ft in feats:
        a, g = ft["attributes"], ft.get("geometry") or {}
        if g.get("x") is None:
            continue
        ts = a.get("Accident_Date_Time")
        items.append((a["Serial_Number"], point(g["x"], g["y"]), {
            "severity": a["Severity"], "year": a["Accident_Year"],
            "time": datetime.fromtimestamp(ts / 1000, timezone.utc).isoformat() if ts else None,
            "fatalities": a["Number_Of_Fatalities"], "injuries": a["Number_Of_Injuries"],
            "intersection": a["IntersectionRelated"] == "Y", "county": a["County"]}))
    return store.upsert_features("itd_crashes", "crash", items)
