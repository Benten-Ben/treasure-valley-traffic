"""OpenStreetMap traffic-signal nodes via the Overpass API (ODbL)."""

from .. import BBOX
from ..http import get_json
from ..store import point

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def signals(store):
    s, w, n, e = BBOX
    query = (f'[out:json][timeout:120];node["highway"="traffic_signals"]({s},{w},{n},{e})->.sig;'
             '.sig out;way(bn.sig)["highway"]["name"];out body;')
    last = None
    for url in ENDPOINTS:
        try:
            result = get_json(url, data={"data": query}, timeout=180)
            break
        except Exception as err:  # try the next mirror
            last = err
    else:
        raise RuntimeError(f"all Overpass endpoints failed: {last}")
    names = {}
    for el in result["elements"]:
        if el["type"] == "way":
            for nid in el.get("nodes", []):
                names.setdefault(nid, set()).add(el["tags"]["name"])
    items = [(el["id"], point(el["lon"], el["lat"]),
              {"streets": sorted(names.get(el["id"], []))})
             for el in result["elements"] if el["type"] == "node"]
    return store.upsert_features("osm_signals", "signal_node", items)
