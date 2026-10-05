#!/usr/bin/env python3
"""Download free, public reference data for Treasure Valley signal research.

Sources (no API keys needed):
  - OpenStreetMap traffic signal nodes + crossing street names (Overpass API)
  - ACHD traffic camera inventory with snapshot URLs (ACHD ArcGIS)
  - ITD AADT by segment for the most recent year (ITD ArcGIS)
  - ITD automatic traffic recorder (ATR) monthly volumes, Ada + Canyon (ITD ArcGIS)

Usage:
  python3 tools/collect_static.py [--out data/static] [--only osm,cameras,aadt,atr]

Uses only the Python standard library. Each source is fetched independently;
one failing source does not stop the others. A manifest.json records when and
from where each file was fetched, plus licensing notes.
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# Ada + Canyon counties, roughly: (south, west, north, east)
BBOX = (43.25, -117.05, 43.80, -116.05)
USER_AGENT = "treasure-valley-traffic-research/0.1 (public research; contact via repo)"

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
ACHD_CAMERAS = "https://gis.achdidaho.org/server/rest/services/Traffic/Traffic_Cameras/MapServer/26/query"
ITD_AADT = "https://gisp.itd.idaho.gov/server/rest/services/GDWarehouse/Traffic/MapServer/1/query"
ITD_ATR = "https://gisp.itd.idaho.gov/server/rest/services/GDWarehouse/Traffic/MapServer/0/query"

LICENSES = {
    "osm": "© OpenStreetMap contributors, ODbL 1.0. Attribution required; "
           "derived databases you publish must be shared under ODbL.",
    "cameras": "ACHD public GIS service. Check ACHD terms before redistributing.",
    "aadt": "Idaho Transportation Department public GIS service.",
    "atr": "Idaho Transportation Department public GIS service.",
}


def http_get_json(url, params=None, data=None, timeout=120):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def arcgis_query_all(url, params, page_size=1000):
    """Page through an ArcGIS REST query, returning all features."""
    features, offset = [], 0
    while True:
        page = http_get_json(url, {**params, "resultOffset": offset,
                                   "resultRecordCount": page_size, "f": "json"})
        if "error" in page:
            raise RuntimeError(page["error"])
        batch = page.get("features", [])
        features.extend(batch)
        if not batch or not page.get("exceededTransferLimit"):
            return features
        offset += len(batch)


def bbox_envelope():
    s, w, n, e = BBOX
    return json.dumps({"xmin": w, "ymin": s, "xmax": e, "ymax": n,
                       "spatialReference": {"wkid": 4326}})


def write_geojson(path, features):
    with open(path, "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)


def fetch_osm(out):
    s, w, n, e = BBOX
    query = f"""[out:json][timeout:120];
node["highway"="traffic_signals"]({s},{w},{n},{e})->.sig;
.sig out;
way(bn.sig)["highway"]["name"];
out body;"""
    last_err = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            result = http_get_json(endpoint, data={"data": query}, timeout=180)
            break
        except Exception as err:  # try the next mirror
            last_err = err
            print(f"  overpass {endpoint} failed: {err}", file=sys.stderr)
    else:
        raise RuntimeError(f"all Overpass endpoints failed: {last_err}")

    names = {}  # node id -> set of street names crossing it
    for el in result["elements"]:
        if el["type"] == "way":
            for node_id in el.get("nodes", []):
                names.setdefault(node_id, set()).add(el["tags"]["name"])

    features = []
    for el in result["elements"]:
        if el["type"] != "node":
            continue
        streets = sorted(names.get(el["id"], []))
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [el["lon"], el["lat"]]},
            "properties": {"osm_id": el["id"], "streets": " & ".join(streets),
                           **{k: v for k, v in el.get("tags", {}).items()}},
        })
    path = os.path.join(out, "osm_traffic_signals.geojson")
    write_geojson(path, features)
    return path, len(features)


def achd_cameras():
    """ACHD cameras keyed by camera id.

    The GIS layer lists a few cameras twice (as of Oct 2026, 232 records for
    228 cameras), sometimes once without coordinates; keep the located record.
    """
    cams = {}
    for ft in arcgis_query_all(ACHD_CAMERAS, {"where": "1=1", "outFields": "*",
                                              "outSR": 4326}):
        a = ft["attributes"]
        cid = int(a["camID"])
        if cid not in cams or cams[cid]["Latitude"] is None:
            cams[cid] = a
    return cams


def fetch_cameras(out):
    cams = achd_cameras()
    path = os.path.join(out, "achd_cameras.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cam_id", "label", "lat", "lon", "image_url"])
        for cid, a in sorted(cams.items()):
            w.writerow([cid, a["label"].strip(), a["Latitude"], a["Longitude"], a["hyperlink"]])
    return path, len(cams)


def fetch_aadt(out):
    # Find the most recent year that has data, then pull segments in the bbox.
    years = http_get_json(ITD_AADT, {"where": "AADT IS NOT NULL", "outFields": "Year",
                                     "returnDistinctValues": "true",
                                     "returnGeometry": "false", "f": "json"})
    latest = max(int(f["attributes"]["Year"]) for f in years["features"])
    feats = arcgis_query_all(ITD_AADT, {
        "where": f"Year={latest}", "geometry": bbox_envelope(),
        "geometryType": "esriGeometryEnvelope", "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects", "outSR": 4326,
        "outFields": "Year,RouteID,DescriptionFrom,DescriptionTo,AADT,"
                     "CommercialAADT,DHV",
    })
    geo = []
    for ft in feats:
        paths = ft.get("geometry", {}).get("paths")
        if not paths:
            continue
        geo.append({"type": "Feature",
                    "geometry": {"type": "MultiLineString", "coordinates": paths},
                    "properties": ft["attributes"]})
    path = os.path.join(out, f"itd_aadt_{latest}.geojson")
    write_geojson(path, geo)
    return path, len(geo)


def fetch_atr(out):
    feats = arcgis_query_all(ITD_ATR, {
        "where": "County_NAME IN ('Ada','Canyon') AND Count_ IS NOT NULL",
        "outFields": "StationID,Name,RoadName,County_NAME,City,Year,Month,"
                     "Count_,Annual,link",
        "outSR": 4326, "orderByFields": "StationID,Year,Month",
    })
    path = os.path.join(out, "itd_atr_monthly.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["station_id", "name", "road", "county", "city", "year", "month",
                    "monthly_adt", "aadt", "lat", "lon", "detail_link"])
        for ft in feats:
            a, g = ft["attributes"], ft.get("geometry", {})
            w.writerow([a["StationID"], a["Name"], a["RoadName"], a["County_NAME"],
                        a["City"], a["Year"], a["Month"], a["Count_"], a["Annual"],
                        g.get("y"), g.get("x"), a["link"]])
    return path, len(feats)


SOURCES = {"osm": fetch_osm, "cameras": fetch_cameras, "aadt": fetch_aadt,
           "atr": fetch_atr}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="data/static")
    ap.add_argument("--only", default=",".join(SOURCES),
                    help="comma-separated subset of: " + ",".join(SOURCES))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    manifest_path = os.path.join(args.out, "manifest.json")
    manifest = {}
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            manifest = json.load(f)

    failures = 0
    for name in args.only.split(","):
        print(f"[{name}] fetching...")
        t0 = time.time()
        try:
            path, count = SOURCES[name](args.out)
        except Exception as err:
            failures += 1
            print(f"[{name}] FAILED: {err}", file=sys.stderr)
            continue
        print(f"[{name}] {count} records -> {path} ({time.time() - t0:.0f}s)")
        manifest[name] = {"file": os.path.basename(path), "records": count,
                          "fetched_utc": datetime.now(timezone.utc).isoformat(),
                          "license": LICENSES[name]}

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
