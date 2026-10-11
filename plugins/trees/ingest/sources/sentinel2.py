"""Sentinel-2 NDVI: the trees' spring cue, evergreen crowns green in early April (docs/19 §19.3).

Copernicus Sentinel data, free, full and open use (ESA's Sentinel Data Legal Notice); credit "Contains modified
Copernicus Sentinel data 2025". Listed in plugin.json as a manual source, for its licence: this module makes no network
requests and has no schedule. Two one-off reads, each approved by the owner and made by hand on the project's server
from Element 84's public copy (earth-search's sentinel-2-c1-l2a collection; robots.txt checked, our User-Agent, at least
2 s between requests), each with a PROVENANCE.md beside its products:

- July 2025: the NDVI median of ten clear passes (Oct 8, 2026, for the land cover's July state);
- early April 2025: the NDVI median of the April 4 and 5 passes, with their clear and snow view counts (Oct 11, 2026;
  decision 24 of the landscape sprint).

Both are on the ground's 10 m grid (basemap/ground/grid.py). plugins/trees/build/build.py reads them (--spring,
--summer)."""

SOURCE = {
    "name": "sentinel2",
    "title": "Sentinel-2 NDVI, early April and July 2025: the trees' spring cue",
    "url": "https://earth-search.aws.element84.com/v1/collections/sentinel-2-c1-l2a",
    "access": "open",
    "schedule": None,   # two one-off reads by hand, each approved by the owner
    "license": "Copernicus Sentinel data (free, full and open use)",
    "credit": "Contains modified Copernicus Sentinel data 2025",
    "notes": "NDVI medians on the ground's 10 m grid: April 4-5, 2025 (with snow counts) and July 2025.",
}
