# Tools

Small Python scripts for collecting and analyzing traffic data you're allowed
to collect yourself. They use only the Python 3 standard library and need no
API keys. Background and legal notes are in
[docs/07-diy-data-collection.md](../docs/07-diy-data-collection.md).

Collected data goes in `data/`, which git ignores. Licensing varies by
source, so check before publishing anything derived from it.

| Script | What it does |
|---|---|
| `collect_static.py` | Downloads OpenStreetMap signal locations, the ACHD camera inventory (228 cameras, duplicates removed), ITD AADT (latest year), and ITD monthly automatic-counter volumes for Ada and Canyon counties. Writes `data/static/` plus a `manifest.json` with fetch times and license notes. |
| `compression_bench.py` | Encodes a camera's 1-per-minute frames as H.264, H.265 and AV1 at several quality levels and reports size vs the JPEGs and SSIM. Results are in docs/11. |
| `gps_runs.py` | Analyzes GPX tracks from floating-car runs: travel time and stops per run, then per signal the share of runs stopped and the mean stop. `--estimate-cycle` infers cycle length from departure times (experimental). |
| `test_gps_runs.py` | Tests `gps_runs.py` on simulated runs through a synthetic coordinated corridor. |

Tools for one-off checks of hosts whose robots.txt asks crawlers to stay
away (ACHD's count tables and camera images) are kept with the project's
private files, not here. They need an explicit flag and are only run by
hand.

## Quick start

```bash
# 1. Public reference data (~1 minute)
python3 tools/collect_static.py

# 2. After driving the corridor with a GPS logger (1-second GPX)
python3 tools/gps_runs.py runs/*.gpx \
    --signals data/static/osm_traffic_signals.geojson --estimate-cycle

# Tests
python3 -m unittest discover tools
```

`--signals` also accepts a hand-made CSV (`name,lat,lon`), which is often
cleaner for one corridor than the full OSM list. Nodes within 60 m of each
other are merged into one intersection either way.

## Notes

- **Overpass (OSM) can be slow.** `collect_static.py` tries three public
  Overpass servers in turn. Use `--only cameras,aadt,atr` to skip OSM if all
  three are down.
- **ACHD cameras:** the image host's `robots.txt` (more.achdidaho.org)
  disallows automated access, so sampling ACHD's images needs ACHD's OK
  first. 511 Idaho's republished images (`/map/Cctv/<id>`) are allowed.
- **There's deliberately no Google, TomTom, HERE or Mapbox travel-time
  logger.** Their terms prohibit storing results to build a dataset. See
  docs/07 §7.2 for paths that do allow it.
- **GPS privacy:** if volunteers contribute tracks, trim the start and end
  of each track, use pseudonymous file names, and share only aggregate
  outputs.
