# tvt: Treasure Valley traffic data platform (prototype)

> **Status: throwaway prototype.** It proved that 12 sources work and taught
> us a lot (see [docs/10 §10.5](../docs/10-architecture.md#105-what-the-prototype-taught-us-kept-as-lessons-not-code)),
> but it isn't the platform's foundation. The real design is decided with
> the owner step by step ([docs/DECISIONS.md](../docs/DECISIONS.md)).

Ingestors for every source we're allowed to collect automatically (see
[docs/08](../docs/08-data-inventory.md)), a local SQLite store that keeps
history, and an aggregator that combines everything per signalized
intersection.

```bash
pip install -r requirements.txt        # only needed for live bus positions
python3 -m tvt sources                 # list sources and last fetch result
python3 -m tvt ingest                  # fetch everything once (~1 minute)
python3 -m tvt run                     # keep fetching, each on its own schedule
python3 -m tvt build                   # aggregate -> site/data/*.geojson
python3 -m tvt status                  # what's in the database
python3 -m unittest discover tests     # offline tests
```

Data lives in `data/tvt.sqlite`; set `TVT_DATA` to put it elsewhere. Both
`data/` and `site/data/` are git-ignored.

## Sources

| Name | Every | What |
|---|---|---|
| `vrt_positions` | 30 s | Valley Regional Transit bus GPS (GTFS-realtime) |
| `achd_live` | 5 min | ACHD roadwork, incidents, message-sign text |
| `wzdx` | 15 min | 511 Idaho work zones |
| `weather_boi` | 1 h | Boise airport visibility, fog, temperature |
| `achd_cameras` | 1 day | ACHD camera inventory (not the images) |
| `achd_signal_assets` | 7 days | ACHD signal points (2022) |
| `osm_signals` | 7 days | OpenStreetMap signal nodes with street names |
| `vrt_static` | 7 days | VRT stops and route shapes |
| `itd_aadt` | 7 days | ITD AADT by segment |
| `itd_atr` | 7 days | ITD automatic counter monthly volumes |
| `itd_crashes` | 30 days | ITD crash points, last 5 years available |
| `fra_crossings` | 30 days | FRA rail crossings |

## Rules the code enforces

- **robots.txt is checked before every request** (`tvt/http.py`), following
  RFC 9309: groups, `*` and `$` wildcards, longest match wins, and 4xx means
  "no rules". It also handles real-world quirks: BOMs, blank lines, and rules
  with no User-agent line. Paths are matched case-insensitively, which is
  stricter than the RFC.
- **Crawl-delay is honored** per host. IEM asks for 120 s.
- **Excluded on purpose:**
  - ACHD's counts table and camera images on `more.achdidaho.org`
    (robots.txt disallows them);
  - 511's website list endpoints (use the official API instead);
  - Google, TomTom, HERE, Mapbox and Waze traffic data (their terms forbid
    storing it).

## Aggregated output (`python3 -m tvt build`)

- **`intersections.geojson`**: signalized intersections, built by merging
  ACHD signal points and OSM nodes within 60 m. Each one carries:
  - nearest camera;
  - highest adjacent non-interstate AADT;
  - crash counts within 60 m (total, injury, fatal);
  - distance to the nearest rail crossing;
  - active work zones nearby;
  - bus stops.
- **Other layers:** `cameras`, `aadt`, `rail_crossings`, `transit_routes`,
  `work`, `message_signs`, `buses` (positions from the last 5 minutes).
- **`summary.json`**: layer counts, latest weather, and the last successful
  fetch per source.
