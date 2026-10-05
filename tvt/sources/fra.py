"""FRA highway-rail crossing inventory (data.transportation.gov, open data)."""

from ..http import get_json
from ..store import point

URL = "https://data.transportation.gov/resource/m2f8-22s6.json"


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def crossings(store):
    rows = get_json(URL, {
        "$where": "statename='IDAHO' AND countyname in ('ADA','CANYON') AND crossingclosed='No'",
        "$limit": 5000})
    items = []
    for r in rows:
        try:
            lat, lon = float(r["latitude"]), float(r["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        trains = sum(_int(r.get(k)) for k in (
            "totaldaylightthrutrains", "totalnighttimethrutrains", "totalswitchingtrains"))
        items.append((r["crossingid"], point(lon, lat), {
            "street": r.get("street"), "city": r.get("cityname"),
            "railroad": r.get("railroadname"), "position": r.get("crossingposition"),
            "traffic_signal_nearby": r.get("highwaytrafficsignal") == "Yes",
            "gate_arms": _int(r.get("countroadwaygatearms")), "trains_per_day": trains}))
    return store.upsert_features("fra_crossings", "rail_crossing", items)
