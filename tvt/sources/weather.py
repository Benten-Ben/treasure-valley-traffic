"""Boise airport (BOI) hourly weather from the Iowa Environmental Mesonet.

Visibility and fog codes let us test whether fog days line up with the
video-detection failures that put signals on max recall (docs chapter 2).
"""

import csv
import io
from datetime import datetime, timedelta, timezone

from ..http import get

URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"


def parse(text):
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        ts = r["valid"].replace(" ", "T") + ":00+00:00"
        codes = r.get("wxcodes") or ""

        def num(key):
            try:
                return float(r[key])
            except (KeyError, ValueError):
                return None

        rows += [("BOI", ts, "visibility_mi", num("vsby")),
                 ("BOI", ts, "temp_f", num("tmpf")),
                 ("BOI", ts, "wind_kt", num("sknt")),
                 ("BOI", ts, "fog", 1.0 if "FG" in codes else 0.0),
                 ("BOI", ts, "mist", 1.0 if "BR" in codes else 0.0),
                 ("BOI", ts, "precip", 1.0 if any(c in codes for c in ("RA", "SN", "DZ")) else 0.0)]
    return rows


def boise_airport(store, days=2):
    end = datetime.now(timezone.utc) + timedelta(days=1)
    start = end - timedelta(days=days + 1)
    text = get(URL, {
        "station": "BOI", "data": ["vsby", "tmpf", "sknt", "wxcodes"],
        "year1": start.year, "month1": start.month, "day1": start.day,
        "year2": end.year, "month2": end.month, "day2": end.day,
        "tz": "Etc/UTC", "format": "onlycomma", "latlon": "no", "missing": "M",
        "trace": "T", "direct": "no", "report_type": "3"}).decode("utf-8", "replace")
    return store.add_observations("weather_boi", parse(text))
