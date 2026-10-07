# water

Rivers, floods, snow, swimming water and drought around the valley: part
of "Wave A: start the clocks"
([docs/17 §17.4](../../docs/17-sources-for-new-plugins.md#174-proposed-order-with-rough-effort)).
Each of these sources keeps only its current state or a short window
(NWPS: 30 days of observations and the latest forecast; the E. coli layer:
the latest sampling round; the hazards layer: each point's current
status), so history exists only if we poll. Ingest only, standard library,
no keys, no UI yet. The owner approved starting these on Oct 7, 2026.

Everything goes into core's tables: readings into `raw.record` (until a
core readings table lands, docs/17 Q8) and lifecycles into `evt.event`
(through `ingest/events.py`). No migrations of its own. Cut to the ring
(W −117.30, S 42.90, E −115.60, N 44.30), the proposed regional ring the
catalogs use.

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `nwps_gauges` | every 30 min: 1 list call + at most 4 per-gauge calls | US government work | NOAA NWS (NWPS, NWRFC); observations courtesy of USGS | yes |
| `nrcs_snotel` | hourly, 1 call | US government work; public domain assumed ⚠️ | USDA NRCS (SNOTEL) | yes |
| `boise_ecoli` | every 12 h, 2 small calls | none stated (City disclaimer only) | City of Boise Parks and Recreation | internal: courtesy note due |
| `boise_river_hazards` | hourly, 2 small calls | none stated | Boise Fire Department and City of Boise (Float the Boise) | internal: courtesy note due |
| `usdm_drought` | every 12 h, 1 call | free to reproduce with the required credit | NDMC (UNL), USDA and NOAA; map courtesy of NDMC | aggregates, with the credit line |

Every request goes through `ingest/http.py` (robots.txt checked, our
User-Agent) with at least 2 s between requests to one host. Each run is
logged in `ops.fetch`.

## The sources

### `nwps_gauges`: NOAA National Water Prediction Service gauges

- **Endpoint:** `api.water.noaa.gov/nwps/v1`: `/gauges?bbox...` (the ring),
  `/gauges/{LID}`, `/gauges/{LID}/stageflow`, `.../stageflow/forecast`.
  robots.txt: 404, no rules. Catalogs:
  [trails.md, "NOAA NWPS"](../../docs/sources/trails.md#noaa-nwps-boise-river-at-glenwood-bridge),
  [hazards.md, "NWPS"](../../docs/sources/hazards.md#national-water-prediction-service-nwps-river-forecasts-and-flood-categories).
- **What:** 37 gauges in the ring on Oct 7, 2026: the Boise (Twin Springs
  to Parma, Glenwood Bridge BIGI1 among them), Payette, Snake, Malheur,
  Owyhee and Weiser rivers, creeks, the New York Canal, and pool levels at
  Arrowrock, Lake Lowell and C.J. Strike. Observations are USGS's
  (Reclamation's at the dams); forecasts are NWRFC's.
- **Cadence:** each run lists every gauge's latest observation and flood
  category (37 KB). Per-gauge calls, most urgent first: a flooding gauge's
  forecast every 3 h; each gauge's metadata and 30-day series weekly
  (about 460 KB for a 15-minute gauge: it fills in the 15-minute values
  between list calls, since observations arrive in batches 2–3 h late);
  otherwise each forecast daily. About 4–5 MB a day in all.
- **Kept:** `<LID>@<time>` one observation ({lid, pe, t, primary,
  secondary, units}: the PEDTS code says which is stage, flow or pool
  elevation; −999/−9999 become null); `<LID>/forecast` a version per
  issuance; `<LID>` the gauge's metadata (flood categories in stage and
  flow, crests, impact statements), without the live status and image
  links. Each gauge's first sweep also loads the 30 days NWPS holds
  (about 100,000 rows for all 37, over the first day). Flood episodes
  (action stage or above, as NWPS categorizes the latest observation) go
  into `evt.event` as `river_flood`, one per gauge and episode; a gauge
  whose category can't be read keeps its episode open.
- **Not used:** the USGS Water Data API, whose robots.txt disallows its
  data paths (docs/17 Q14). NWPS carries USGS's values at forecast points.

### `nrcs_snotel`: NRCS SNOTEL hourly

- **Endpoint:** the AWDB REST API,
  `wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data` (all elements,
  hourly, the last 48 hours). robots.txt: 404, no rules. Catalog:
  [trails.md, "NRCS SNOTEL"](../../docs/sources/trails.md#nrcs-snotel).
- **What:** the ring's four SNOTEL stations: Bogus Basin (978), Cozy Cove
  (423), Mores Creek Summit (637) and Reynolds Creek (2029). None of
  Oregon's 82 stations is in the ring (checked Oct 7). Snow water, snow
  depth, precipitation, temperature, and at Mores Creek humidity, wind and
  radiation; battery voltage everywhere.
- **Kept:** one record per station and hour, `<triplet>@<UTC time>`, with
  every element's value, unit and flags; the time as published (station
  standard time, UTC−8) and in UTC. Re-reading 48 hours catches late
  values and NRCS's revisions; only new or changed versions are written.
  AWDB keeps the history itself; our copy keeps values as first published.

### `boise_ecoli`: Boise's E. coli results

- **Endpoint:** `services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/BPR_EColi_Testing/FeatureServer/0`,
  read whole through the shared ArcGIS reader (query only). robots.txt:
  403, no rules. Catalog:
  [trails.md, "Boise River E. coli results"](../../docs/sources/trails.md#boise-river-e-coli-results).
- **What:** the latest sampling round only (7 samples on Oct 7, 2026, at
  the City's swimming ponds by the river: Quinn's, Esther Simplot and
  Veterans); each round overwrites the last.
- **Kept:** each sample for good, `<SampleName>|<SampleDatetime>|<LabNumber>`,
  every field but OBJECTID. Shown later with the City's or DEQ's
  thresholds and wording; we make no swim or no-swim call.

### `boise_river_hazards`: Boise River hazards and access (Float the Boise)

- **Endpoint:** `services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Boise_River_Hazards_and_Access_-_VIEW/FeatureServer/10`,
  read whole (query only). robots.txt: 403, no rules. Catalog:
  [trails.md, "Boise River hazards and access"](../../docs/sources/trails.md#boise-river-hazards-and-access-float-the-boise).
- **What:** 119 points from Barber Park to Ann Morrison Park (Oct 7,
  2026): temporary, permanent and extreme hazards, rapids, put-ins and
  take-outs, each with a status (active, remediated, inactive, potential).
  Codes are mixed with words and blanks; normalized for the events, kept
  as published in the records.
- **Kept:** a full snapshot in `raw.record` by OBJECTID (a snapshot with
  less than half the points we hold is refused), without the editors'
  user names and the "Internal Comments" field, which names people; a
  point fingerprint makes a moved point a new version. Active and
  potential hazards are `river_hazard` lifecycles in `evt.event`, from
  first seen until remediated, made inactive or deleted; `declared`
  starts at the point's creation date.

### `usdm_drought`: U.S. Drought Monitor county statistics

- **Endpoint:** `usdmdataservices.unl.edu/api/CountyStatistics/GetDroughtSeverityStatisticsByAreaPercent`
  (`statisticsType=2`, categorical; CSV). robots.txt: 404, no rules.
  Catalogs: [farm.md, "U.S. Drought Monitor"](../../docs/sources/farm.md#us-drought-monitor-usdm),
  [hazards.md](../../docs/sources/hazards.md#us-drought-monitor).
- **What:** weekly percent of area in None and D0–D4 for the ring's ten
  counties: Ada, Boise, Canyon, Elmore, Gem, Owyhee, Payette, Valley and
  Washington, and Malheur (Oregon). Whether Baker County, Oregon, touches
  the ring's north edge wasn't checked.
- **Kept:** each county and map, `<FIPS>:<MapDate>`. Each run reads from
  four weeks before the latest map held; the first run reads the archive
  since 2000 in one call (about 14,000 rows). Drought episodes in
  `evt.event` as `drought`: one per county and "Dn or worse" while any of
  the county is in that category or worse, from the first map's valid
  start to the latest map's valid end.
- **Not used:** the polygons. The official files sit under
  `droughtmonitor.unl.edu/data/`, which robots.txt disallows; NDMC's own
  ArcGIS archive service is an alternative for later (its time extent
  ends in 2020 ⚠️).
- **Credit line** (required): "The U.S. Drought Monitor is jointly
  produced by the National Drought Mitigation Center at the University of
  Nebraska-Lincoln, the United States Department of Agriculture, and the
  National Oceanic and Atmospheric Administration. Map courtesy of NDMC."

## Not built here

- **Barber Park floater information** (Ada County; parking, floaters and
  a river sensor): its service advertises public edit capabilities and is
  in season only (June to Labor Day); not part of this wave. Query only,
  when it comes.
- **Float the Boise season facts:** entered by hand each season.

## Commands

```bash
python3 -m ingest run nwps_gauges nrcs_snotel boise_ecoli boise_river_hazards usdm_drought
python3 -m ingest serve                  # with every other scheduled source
python3 -m unittest discover -s plugins/water/tests -t .
```

**Ethics:** rivers, snow and drought, not people. The City of Boise layers
state no license: used internally with credit until the City answers a
courtesy note (docs/17 Q17). Hazards and water quality are shown in the
agencies' own words ("never deemed completely safe to float"); we never
say "safe".
