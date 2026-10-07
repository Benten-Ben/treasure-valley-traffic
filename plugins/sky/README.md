# sky

The sky over the valley
([docs/15 §15.7](../../docs/15-plugins.md#157-ideas-for-later-plugins)).
So far, aurora and space weather: NOAA SWPC's OVATION aurora nowcast,
cut to the sky north of the valley, and SWPC's 1-minute estimate of the
planetary Kp index. Both keep only their current state, so history exists
only if we poll. They're Wave A's "start the clocks" pollers
([docs/17 §17.4](../../docs/17-sources-for-new-plugins.md#174-proposed-order-with-rough-effort)):
ingest only, no map layers yet. Later the plugin will own the night sky's
other data: satellites, light pollution, meteors, dark-sky places and the
astronomy forecast. The sun and moon ephemeris and lighting belong to core
([§17.8](../../docs/17-sources-for-new-plugins.md#178-decisions-on-the-open-questions-oct-7),
Q3).

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `swpc_ovation` | every 30 min (retry after 10) | public domain (US government work) ⚠️ | NOAA Space Weather Prediction Center (OVATION Prime) | yes |
| `swpc_kp_1m` | hourly | public domain (US government work) ⚠️ | NOAA Space Weather Prediction Center | yes |

⚠️ SWPC's product and data-access pages state no license. These are US
government works, so they're presumed public domain, with credit to SWPC
([catalog](../../docs/sources/sky.md#noaa-swpc-data-service-ovation-aurora-kp)).

Both read `services.swpc.noaa.gov`. Its robots.txt returns 404, so there are
no rules (checked again Oct 7 through `ingest/http.py`). Each source makes
one request per run, at least 2 s after the other's (`http.PACE_S`), with
gzip.

### `swpc_ovation`: the OVATION aurora nowcast

- **Endpoint:** `https://services.swpc.noaa.gov/json/ovation_aurora_latest.json`.
  OVATION Prime 2020, the JHU/APL empirical model, run from the solar wind
  measured at L1, so it leads by 30–90 minutes. When solar-wind data are
  missing it falls back to Kp, with no lead. The file is the whole globe on a
  1° grid: 65,160 points of `[longitude 0–359 east, latitude, aurora 0–100]`,
  plus an observation time and a forecast time. It's about 900 KB, or about
  145 KB gzipped, and SWPC remakes it every few minutes. On Oct 7 the
  observation time was 14:45 UTC, the forecast time 16:00, and the file was
  last modified at 14:54.
- **What we keep:** the slice 125°W–105°W, 35°N–65°N: 21 × 31 = 651
  values, as the catalog sizes it. Bright aurora can be seen from as far as
  1000 km away (SWPC), so the slice reaches well past the ring. Cut to the
  ring, it would keep two or three rows that are nearly always zero. Each
  snapshot is **one** `raw.record` row, never one row per value
  ([sky.md design note 8 and correction 6](../../docs/sources/sky.md#design-corrections-from-verification)):
  - `source_id`: the forecast time;
  - `payload`: `observation_time`, `forecast_time`, `grid` (west −125,
    south 35, a 1° step, 21 columns, 31 rows) and `aurora`, 31 rows from
    35°N north to 65°N, each with 21 values from 125°W east to 105°W;
  - `geom`: the slice's outline.

  The cell at longitude `lon` (negative west) and latitude `lat` is
  `aurora[lat - 35][lon + 125]`. The records go in with `complete=False`, so
  every forecast time stays and none is retired. A grid with a missing,
  repeated-but-different or out-of-range cell, a changed `Data Format` or an
  unreadable time fails the fetch, and nothing is stored.
- **Why every 30 minutes:** it's the cadence the catalog and §17.4 size.
  Each run downloads the whole global file (there's no smaller one), about
  7 MB a day.
- **Care:** OVATION gives the chance of aurora overhead, not of seeing it
  from Boise. Anything built on it needs a viewline offset and an
  "approximate" label (catalog, Risks).

### `swpc_kp_1m`: the estimated planetary Kp, every minute

- **Endpoint:** `https://services.swpc.noaa.gov/json/planetary_k_index_1m.json`.
  It holds about the last six hours, one entry a minute:
  `{time_tag, kp_index, estimated_kp, kp}`. On Oct 7 it had 358 entries,
  08:57–14:54 UTC, about 28 KB (1.3 KB gzipped). `kp` is the value in thirds
  (`2P` is 2+, `3M` is 3−) and `kp_index` the nearest integer.
- **What we keep:** one `raw.record` row per complete UTC hour, so 24 rows a
  day rather than 1,440:
  - `source_id`: the hour's start;
  - `payload`: `start`, `step_s` (60) and `estimated_kp`, 60 values, with
    null for a minute the file lacks. `kp_index` and `kp` are dropped where
    they're exactly what `estimated_kp` gives (as on every minute of the
    Oct 7 sample). Any minute where they differ keeps them under `labels`.
  - no geometry: Kp is planetary.

  An hour is stored only once the file holds its first and last minutes, so
  no record gets a partial version. The hour in progress waits for the next
  run. With a six-hour window, about five hourly runs in a row can fail
  before a minute is lost. `complete=False`.
- **Not here:** the definitive 3-hourly Kp since 1932 is
  [GFZ's](../../docs/sources/sky.md#gfz-kp-index-since-1932) (CC BY), and
  it can be read at any time, so it needs no clock started now. SWPC's
  estimate as it stood in real time is what would otherwise be lost.

**Tables:** none of its own, and no migrations. Readings stay in core's
`raw.record` until core's readings and fields contracts take them
([§17.8](../../docs/17-sources-for-new-plugins.md#178-decisions-on-the-open-questions-oct-7),
Q8 and Q1). The OVATION slice is a 2D field frame in all but name, and
each record carries its grid, so moving it is mechanical.

**Storage:** measured in a scratch Postgres 17 on Oct 7. An OVATION payload
is about 0.5 KB after compression on a quiet day and about 1.5 KB with a
busy oval. A Kp hour is about 0.8 KB. With the rows and their indexes, that's
roughly 70–120 KB a day.

```bash
python3 -m ingest run swpc_ovation swpc_kp_1m
python3 -m unittest discover -s plugins/sky/tests -t .
```

**Ethics:** this is nature, not people: no personal data. The test
fixtures are real SWPC files (public domain), trimmed: the slice plus a
1° border, and 81 minutes of Kp.
