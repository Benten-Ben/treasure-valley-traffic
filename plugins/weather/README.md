# weather

Weather for the valley and the regional ring
([docs/17 §17.2, Weather](../../docs/17-sources-for-new-plugins.md#weather)).
It starts with Wave A's airport observations
([§17.4](../../docs/17-sources-for-new-plugins.md#174-proposed-order-with-rough-effort)).
The Aviation Weather Center (AWC) keeps only 30 days of METARs, so a
morning's fog or a storm's gusts are lost unless we record them as they
come. These reports feed the fog study
([ch. 2](../../docs/02-treasure-valley-signal-system.md)) and later the fog
chip, feed cards and cloud bases for 3D weather. There's no UI yet.

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `awc_metar` | every 10 min, one request | US Government work; none stated, public domain assumed ⚠️ | NOAA NWS Aviation Weather Center | yes |

**`awc_metar`:** METARs and SPECIs from the ring's airports.

- **Endpoint:** `https://aviationweather.gov/api/data/metar?bbox=42.90,-117.30,44.30,-115.60&format=json&hours=N`,
  keyless ([API page](https://aviationweather.gov/data/api/)). The box is
  the regional ring (west −117.30, south 42.90, east −115.60, north 44.30;
  proposed in [DECISIONS](../../docs/DECISIONS.md), "How far the study area
  reaches"). AWC's bbox order is lat, lon, lat, lon.
- **Stations** (Oct 7, 2026): Boise (KBOI), Nampa (KMAN, an AWOS, every 20
  min), Caldwell (KEUL), Mountain Home AFB (KMUO) and Ontario, Oregon
  (KONO). AWC's station list for the box also has KU35 (Caldwell), which
  doesn't report. Any airport AWC adds inside the box is picked up.
- **Cadence:** routine reports hourly (KMAN every 20 min), specials at any
  time. On the morning of Oct 7, haze at Caldwell brought six specials in
  90 minutes, with visibility down to ¾ mile. Every 10 minutes we ask for
  everything since the last good fetch plus 6 hours (6 to 24 hours). The
  overlap catches reports that reach AWC late: Mountain Home AFB's 11:55Z
  report arrived at 14:18Z. A normal poll returns about 60 reports
  (25 KB). AWC allows 100 requests a minute, caps an answer at 400 entries
  and asks for limited, infrequent requests and a custom User-Agent.
- **robots.txt:** 404, so no rules (re-read Oct 7, 2026).
- **What we keep:** each report is a record in `raw.record`, keyed by
  station and observation time (`KBOI 2026-10-07T13:53Z`). These are
  readings, not snapshots, so nothing is ever marked removed. The payload
  is AWC's decoded JSON as returned: the raw METAR text (`rawOb`),
  temperature, dew point, wind and gusts, visibility (`visib` is a number
  or text such as `10+`), altimeter and sea-level pressure, present weather,
  cloud layers and cover, flight category, the 6- and 24-hour extremes and
  precipitation, QC flags, and AWC's receipt and report times. The only
  field dropped is the station's display name. The airport's point goes in
  `geom` (WGS84). A corrected report (COR) adds a version. An unchanged
  report only moves `last_seen`.
- **Failures:** an empty answer (HTTP 204) fails the fetch, since Boise
  reports every hour, and the next run asks for the whole gap. After an
  outage of more than 18 hours the oldest reports are left to IEM's archive
  (catalog: IEM). If an answer hits AWC's 400-entry cap, the run says so in
  its stats; a day is about 200 reports.
- **Catalogs:** [weather.md, "Aviation Weather Center Data
  API"](../../docs/sources/weather.md#aviation-weather-center-data-api) and
  [weather-3d.md, "Aviation Weather Center Data API
  (METAR)"](../../docs/sources/weather-3d.md#aviation-weather-center-data-api-metar).

**Tables:** none of its own. Readings go to core's `raw.record` until core
has a station and readings table (ch. 17 Q8). TAFs, PIREPs, NWS warnings
and IEM history are later sources (§17.2).

**Commands:**

```bash
python3 -m ingest run awc_metar          # one poll (needs DATABASE_URL)
python3 -m unittest discover -s plugins/weather/tests -t .
```

**Ethics:** weather at airports, nothing about people. api.weather.gov
stays off-limits (its robots.txt disallows everything; ch. 17 Q13), and
the public fog layer will come from NOAA inputs only, not 511's internal
road-weather stations (§17.2, watch-outs).
