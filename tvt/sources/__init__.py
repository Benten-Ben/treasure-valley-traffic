"""Source registry. Each source fetches one dataset and writes it to the store.

Only sources we're allowed to use automatically are registered here: public
APIs and GIS services with no terms or robots.txt rule against this use.
See docs/08-data-inventory.md for everything we found and why some sources
are excluded (e.g., ACHD's counts table and camera images on
more.achdidaho.org, whose robots.txt disallows automated access).
"""

from dataclasses import dataclass
from typing import Callable

from . import achd, fra, itd, osm, vrt, weather, wzdx

HOUR = 3600
DAY = 24 * HOUR


@dataclass
class Source:
    name: str
    interval_s: int
    run: Callable
    description: str
    license: str


SOURCES = {s.name: s for s in [
    Source("vrt_positions", 30, vrt.positions,
           "Valley Regional Transit bus GPS positions (GTFS-realtime)",
           "VRT: GTFS files provided for public use"),
    Source("achd_live", 300, achd.live,
           "ACHD roadwork, incidents and message-sign text",
           "ACHD public GIS; as-is disclaimer"),
    Source("wzdx", 900, wzdx.work_zones,
           "ITD/511 work zones (WZDx feed)", "511 Idaho public WZDx feed"),
    Source("weather_boi", HOUR, weather.boise_airport,
           "Boise airport hourly weather: visibility, fog, temperature",
           "Iowa Environmental Mesonet (NWS ASOS data, public domain)"),
    Source("achd_cameras", DAY, achd.cameras,
           "ACHD traffic camera inventory (locations, image links)",
           "ACHD public GIS; images themselves not fetched (robots.txt)"),
    Source("achd_signal_assets", 7 * DAY, achd.signal_assets,
           "ACHD signal points from its 2022 bike-map layers",
           "ACHD ArcGIS Online public layer"),
    Source("osm_signals", 7 * DAY, osm.signals,
           "OpenStreetMap traffic-signal nodes with street names",
           "(c) OpenStreetMap contributors, ODbL 1.0"),
    Source("vrt_static", 7 * DAY, vrt.static,
           "VRT GTFS: stops and route shapes", "VRT: provided for public use"),
    Source("itd_aadt", 7 * DAY, itd.aadt,
           "ITD AADT by segment (latest year)", "ITD public GIS"),
    Source("itd_atr", 7 * DAY, itd.atr_monthly,
           "ITD automatic counter monthly volumes (Ada/Canyon)", "ITD public GIS"),
    Source("itd_crashes", 30 * DAY, itd.crashes,
           "ITD crash points, recent years (Ada/Canyon box)", "ITD public GIS"),
    Source("fra_crossings", 30 * DAY, fra.crossings,
           "FRA highway-rail crossing inventory (Ada/Canyon, open crossings)",
           "USDOT open data"),
]}
