# wildlife

Animals on our roads
([docs/17 §17.2](../../docs/17-sources-for-new-plugins.md#wildlife)). For now
this is one Wave A poller
([§17.4](../../docs/17-sources-for-new-plugins.md#174-proposed-order-with-rough-effort)):
Idaho Fish and Game's roadkill reports in the ring, kept as versions in
core's `raw.record`. It adds no tables, no migrations and no map layer yet.

**Why now:** IDFG rebuilds its roadkill layer in full (on Oct 7, 2026 the
OBJECTIDs were renumbered across the whole table), so it holds only its
current state. Corrections and removals of duplicate reports leave no
trace unless we keep the versions. Matching carcasses to road segments
("Animals on the road") comes later, in Wave C.

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `idfg_roadkill` | daily (retried after 1 hour if refused or failed) | none stated (disclaimer only) | Idaho Department of Fish and Game | aggregates only; a courtesy note to IDFG is due (docs/17 Q17) |

## `idfg_roadkill`

- **Endpoint:** `https://gisportal-idfg.idaho.gov/hosting/rest/services/Roadkill/Roadkill_Observations/MapServer/1`
  (ArcGIS Server 11.5; capabilities Map, Query and Data; 100,000 records a
  query; no key). Catalog:
  [docs/sources/wildlife.md, "IDFG roadkill observations"](../../docs/sources/wildlife.md#idfg-roadkill-observations).
- **robots.txt:** `gisportal-idfg.idaho.gov/robots.txt` returns 404, so
  there are no rules (re-checked through `ingest/http.py` on Oct 7, 2026).
  The host is still paced at 5 s between requests (`http.PACE_S`), plus
  the reader's own 2 s pause.
- **What a run does:** reads every report in the ring (117.30° W to
  115.60° W, 42.90° N to 44.30° N) with the shared ArcGIS reader: the IDs,
  then one range query, gzipped. That's three requests with robots.txt,
  about 5 MB before gzip. The data covers the ring's Idaho side only; IDFG
  has nothing in Oregon.
- **Size:** 9,268 reports in the ring on Oct 7, 2026, observed from 1970
  on, with new ones almost daily. By channel: IDFG Roadkill & Salvage
  Reports 8,911, IDFG Survey 123 317, ITD Survey 123 31, Big Game Mortality
  Reports 9.
- **What we keep:** one `raw.record` row per report and per changed
  version (`complete=False`). Reports are occurrences, so one that IDFG
  drops just stops being seen: its `last_seen` stays behind and nothing is
  marked removed. The payload has the fields on an allow-list: species,
  channel, observed and reported times, salvaged, sex, life stage and
  state, disposition, decomposition, latitude and longitude, highway,
  milepost, county, region and GMU. The geometry is the WGS84 point.
- **Our own IDs:** OBJECTIDs change at every rebuild, and GlobalIDs
  probably do too. A report's ID is a hash of its channel, its observed and
  reported times and its reported point (to 6 decimals). Reports alike in
  all of those (two animals in one report) get `#2`, `#3`. Any other
  edit is a new version of the same report.
- **Dates:** kept as served, in epoch milliseconds. The service works in
  Mountain Standard Time without daylight saving: date-only reports arrive
  at 07:00 UTC (midnight MST). The two Survey 123 channels carry a time of
  day (348 reports in the ring), unlike the catalog's "dates only".
  Pre-1977 dates are suspect, and each run counts them.
- **Refusals:** a run fails, stores nothing and retries after an hour if
  the answer is empty, has under 90% of the reports the last run saw (read
  during IDFG's rebuild, or a cut layer), or has mostly new IDs while most
  of the last run's are gone (dates or points served differently). If IDFG
  really did cut the layer, a person checks it and lowers `MIN_SHARE` for
  one run.

## Commands

```bash
python3 -m ingest run idfg_roadkill
python3 -m unittest discover -s plugins/wildlife -t .
```

## Ethics

- **Road network, not people** (docs/17 Q21). Dropped at ingest:
  - IDFG's free-text `note`, which may hold personal details;
  - `path`, undocumented, which may point to a photo (never fetched);
  - any field the layer adds later. Each run names such fields, and one
    is kept only after a person reviews it and adds it to `KEEP`.

  The layer has no reporter name, email or phone field.
- **No licence is stated** (a disclaimer only), so under the rule extended
  to state agency GIS (docs/17 Q17) the reports are used with credit to
  IDFG, stay internal or are published only as aggregates, and a courtesy
  note goes to IDFG. Its draft is the owner's to send. Republishing the
  reports themselves waits for a licence or a yes.
- **Sensitive taxa:** any public aggregate passes the core sensitivity rules
  (Q21): no points, and cells of 0.2° or coarser.
- **Bias:** most reports come from salvage permits (since the 2012 salvage
  law), so deer and elk are over-represented, and IDFG warns of duplicate
  reports. Compared with police-reported animal crashes, this is a
  "reporting-channel ratio", not under-reporting.
- **Never** query IDFG's `Wildlife_Conflicts_public` service: it's a
  write-only intake whose schema holds reporters' contact details.
