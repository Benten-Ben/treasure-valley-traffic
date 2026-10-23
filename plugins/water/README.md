# water

The valley's water network (hydrography: rivers, creeks, canals, ponds and
their gauges; [below](#hydrography-the-water-network)), and the pollers for
rivers, floods, snow, swimming water and drought around the valley: part
of "Wave A: start the clocks"
([docs/17 §17.4](../../docs/17-sources-for-new-plugins.md#174-proposed-order-with-rough-effort)).
Each of these sources keeps only its current state or a short window
(NWPS: 30 days of observations and the latest forecast; the E. coli layer:
the latest sampling round; the hazards layer: each point's current
status), so history exists only if we poll. Ingest only, standard library,
no keys, no UI yet. The owner approved starting these on Oct 7, 2026.

These pollers write only core's tables: readings into `raw.record` (until
a core readings table lands, docs/17 Q8) and lifecycles into `evt.event`
(through `ingest/events.py`); the hydrography has the `water` schema.
They're cut to the ring (W −117.30, S 42.90, E −115.60, N 44.30), the
regional ring adopted for the new plugins (docs/17 Q19); the hydrography
and the IDWR layers to the map box.

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `nwps_gauges` | every 30 min: 1 list call + at most 4 per-gauge calls | US government work | NOAA NWS (NWPS, NWRFC); observations courtesy of USGS where NWPS names a USGS site | yes |
| `nrcs_snotel` | hourly, 1 call | US government work; public domain assumed ⚠️ | USDA NRCS (SNOTEL) | yes |
| `boise_ecoli` | every 12 h, 2 small calls | none stated (City disclaimer only) | City of Boise Parks and Recreation | internal: courtesy note due |
| `boise_river_hazards` | hourly, 2 small calls | none stated | Boise Fire Department and City of Boise (Float the Boise) | internal: courtesy note due |
| `usdm_drought` | every 12 h, 1 call | free to reproduce with the required credit | NDMC (UNL), USDA, NOAA and NASA; map courtesy of NDMC | aggregates, with the credit line |
| `canal_season` | hourly, no request: derived ([below](#the-canal-season)) | derived (NWPS, the water network, HydroShare's canal names (CC BY 4.0), the districts' dates, IDWR) | each lifecycle names its own | each lifecycle says; IDWR's are internal |

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
  Arrowrock, Lake Lowell and C.J. Strike. Observations are USGS's where
  NWPS names a USGS site: 24 of the 37 gauges. The other 13, the New York
  Canal's BSEI1 among them, name no USGS site (`usgsId` is empty) and no
  `dataAttribution` in the metadata we keep (checked Oct 11, 2026);
  Reclamation's at the dams ⚠️. Forecasts are NWRFC's.
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
  Nebraska-Lincoln, the United States Department of Agriculture, the
  National Oceanic and Atmospheric Administration and the National
  Aeronautics and Space Administration. Map courtesy of NDMC."

## Not built here

- **Barber Park floater information** (Ada County; parking, floaters and
  a river sensor): its service advertises public edit capabilities and is
  in season only (June to Labor Day); not part of this wave. Query only,
  when it comes.
- **Float the Boise season facts:** entered by hand each season.

## Commands

```bash
python3 -m ingest run nwps_gauges nrcs_snotel boise_ecoli boise_river_hazards usdm_drought canal_season
python3 -m ingest serve                  # with every other scheduled source
python3 -m unittest discover -s plugins/water/tests -t .
```

**Ethics:** rivers, snow and drought, not people. The City of Boise layers
state no license: used internally with credit until the City answers a
courtesy note (docs/17 Q17). Hazards and water quality are shown in the
agencies' own words ("never deemed completely safe to float"); we never
say "safe".

## Hydrography: the water network

One water network for the map (landscape sprint package P4-data, Oct 11,
2026; the owner's decisions 17 and 19, Oct 8): **OpenStreetMap's geometry
carrying NHD's facts**, NHD-only pieces kept and drawn lighter, canals with
their topology, the gauges that measure them, and the base layers and the
ground's water mask exported for the base bake and the ground. The Water
layer and its cards are P4-app's; the canal season's data side is
[below](#the-canal-season) (P5), its drawing P5-app's.

| Source | Kind | What | Licence | Republish |
|---|---|---|---|---|
| `nhd_hr` | by hand | USGS NHD High Resolution, HU4 1705 (product of 2023-12-09), cut to the map box, with NHDFlow | public domain; credit "USGS National Hydrography Dataset" | yes |
| `hydroshare_canals` | by hand | The Treasure Valley Irrigation System (HydroShare, 2022): 2,743 named canal, lateral, drain and field-supply lines in the box | CC BY 4.0: Tatum, Bittmann, Stone, Kaiser (2022), doi:10.4211/hs.24a5f761bf4f41fb9b872b130d9d1a3f, "modified" | yes |
| `osm_waterways` | OpenStreetMap consumer | waterways, water areas, wetlands, springs, reservoirs and basins, swimming pools (decision 2b) | ODbL; "© OpenStreetMap contributors" | yes |
| `idwr_irrigation_orgs` | every 30 days | IDWR's irrigation organizations: 59 service areas touching the box, without the `Owner` field | none stated (IDWR's disclaimer); credit IDWR | **internal** |
| `idwr_season_of_use` | every 90 days | IDWR's season of use: the legal irrigation season's 4 zones touching the box | none stated (IDWR's disclaimer); credit IDWR | **internal** |
| `nwi` | by hand | FWS National Wetlands Inventory: the 13,753 vegetated palustrine wetlands of the eight HU8 watersheds touching the box (October 2026 release, cut to the box) | public domain; credit "U.S. Fish and Wildlife Service, National Wetlands Inventory" | yes |
| `canal_dates` | by hand | the districts' canal dates, in the versioned [`ingest/canal_dates.json`](ingest/canal_dates.json) (empty until the owner asks for the lookups) | facts, each cited to the district's page | yes, unless an entry says otherwise |

- **NHD**: the HU4 zip was downloaded once more on Oct 11 with the owner's
  OK (19c), from the same S3 URL (same ETag and sha256 as Oct 8), to keep
  NHDFlow. robots.txt: 404 (no rules). It's kept whole on the server for a
  later cut to the regional ring. Its geometry is mostly 1:24,000 topo-era,
  with Lower Boise canal updates in 2013–15. NAD83 is read as WGS 84, the
  ground's datum policy ([basemap/ground](../../basemap/ground/README.md)).
- **HydroShare**: downloaded once by hand on Oct 8 (its download path is
  closed to robots, behind a licence click; [farm.md](../../docs/sources/farm.md#treasure-valley-irrigation-system-hydroshare-canal-network)).
  A static 2022 snapshot, with no scripted refresh. Untrusted: the worker
  unpacks the bag and its 7z into new empty folders, checks the bag's MD5
  manifest, and parses none of its XML. It names canals, its type sets an
  unnamed canal's kind, and it's evidence; it's never geometry. About 2,070
  of its lines carry a placeholder for a name ("Unnamed Drain", "Unnamed
  Supply", "Unnamed Lateral", "Unnamed Creek") or their type's words
  ("Field Supply", "Pump Lifter", "Private Drain"): the build reads those as
  no name.
- **OpenStreetMap**: core's loader ([ingest/osm_extract.py](../../ingest/osm_extract.py))
  reads the held extract's valley cut. 14,087 objects (Oct 5 extract): 7,406
  lines, 6,443 areas (4,795 of them pools, which decision 2b counted) and 238
  nodes. Water isn't part of the highway partition, so it loads whichever
  extract it's given; the build records the MD5 it read. The box's Oregon
  slice has no OpenStreetMap data, so NHD alone draws it.
- **IDWR**: both layers checked Oct 11 through `ingest/http.py` with our
  User-Agent ([`ingest/idwr.py`](ingest/idwr.py)): robots.txt answers with a
  redirect to an HTML "Not Found" page (no rules); each item's licence field
  is IDWR's disclaimer, with no licence granted; Query and Extract only.
  Internal: they're read only into `water.idwr_*` and the side tables a
  canal card reads, never an export or the base map (the bake refuses any
  input from an `idwr_*` source). The `Owner` field is never requested.
  Polygons are stored made valid: 14 of the 59 organizations come with
  self-intersecting rings or a hole outside its shell. A courtesy note to
  IDWR covering both is drafted with the private files for the owner to
  send.

### Tables (migrations 0001, 0002 and 0003)

| Table | What | Licence |
|---|---|---|
| `water.load` | each NHD and HydroShare load: file, sha256, prepare.json, counts | |
| `water.nhd_flowline`, `nhd_polygon`, `nhd_line`, `nhd_point`, `nhd_flow` | NHD as prepared: flowlines with Strahler order, flags and visibility filter; waterbodies and areas; dam and flume lines; springs, waterfalls, gauging stations and point events; NHDFlow | public domain |
| `water.hydroshare_canal` | HydroShare's lines in the box | CC BY 4.0 |
| `water.osm_feature` | OpenStreetMap's water, keyed by type, id and shape, versioned in place (plan C2) | ODbL |
| `water.idwr_org`, `water.idwr_season` | IDWR's layers, replaced whole each run (a snapshot under half of what's held is refused) | **internal** |
| `water.build` | each build: its inputs (sha256s, the extract's MD5, IDWR's fetch times), settings and counts | |
| `water.reach` | every drawn line: kind (river, stream, canal, lateral, ditch, drain), name and where it came from, flow (perennial, intermittent, ephemeral, unknown), piped, width and how we know it, Strahler order, first zoom, geometry_from (osm, nhd), confirmed, the canal and the distance from its head, length | ODbL |
| `water.reach_link` | which reach flows into which: `end`, `branch` (a lateral leaving its canal), `joins` (a drain joining a canal), `nhdflow`; `at_m` along the upstream reach | ODbL |
| `water.reach_evidence` | how we know each reach: its geometry's source, NHD's facts it carries, and every other source that agrees, with the share of its length and the median distance | ODbL |
| `water.body` | every drawn area: kind (lake, reservoir, pond, river, canal, basin, wastewater, wetland, pool, water, dock), intermittent, area, first zoom, geometry_from, confirmed, gauge | ODbL |
| `water.structure` | dams, weirs, lock and sluice gates, waterfalls, springs and gauges, with the reach each sits on | ODbL |
| `water.canal` | one row per named canal (its connected reaches of one name): kind (main canal, canal, lateral, ditch, drain), length, piped length, head reach and structure, source (river, reservoir, canal, unknown), gauge, sources | ODbL |
| `water.gauge` | each NWPS gauge in the box and the reach, body or canal it measures (OSM-derived ids, matched by OSM's and NHD's names: the strictest input's licence, C3) | ODbL |
| `water.canal_org`, `water.canal_season` | the IDWR service areas each canal runs through (share of its length; whether its head is in it), and the legal season at its head | **internal** |
| `water.nwi_project`, `nwi_wetland`, `nwi_presence` | 0003: NWI's mapping projects (image year and source), its vegetated wetlands with their mapping era, and the presence check's shares for the old-mapped ones | public domain |
| `water.wetland_check` | 0003: every NWI polygon's outcome in each build (kept, flagged, retired or unchecked, the reason, the shares, what stood for a wetland), the retired ones included | ODbL |
| `water.canal_date` | 0002: the districts' dates as `canal-dates-load` last loaded them from canal_dates.json, one row per entry, with its page and the day it was read | as each entry says |

Evidence lives in `water.reach_evidence`, not `core.source_link`: that
table's key allows one entity per source record, and one NHD flowline runs
along several OpenStreetMap ways.

### The build

`python3 -m ingest water-build` ([`ingest/build.py`](ingest/build.py)), by
hand, never inside `ingest serve` (a run of the build `water-build`; the
loads mark it, and it marks `water-export`). In PostGIS, in UTM 11N metres:

1. NHD's flowlines, clipped to the map box, are cut into equal pieces of
   25 m or less. A piece is matched when its middle lies within 20 m of an
   OpenStreetMap waterway line, or of an OSM water area.
2. Every OSM waterway way is a reach with OSM's geometry. It takes NHD's
   facts (the GNIS name when OSM has none, perennial or intermittent when
   OSM doesn't say, Strahler order, reach code, visibility filter) from the
   NHD flowline of a like class that is 70% or more matched (the design's
   rule) and covers half the way or more. A way half of whose length or
   more lies within 20 m of NHD is `confirmed`.
3. An unmatched NHD run 100 m or longer is an NHD-only reach. Where it
   leaves or rejoins the OSM way it was matched to, its end is carried onto
   that way, so a lateral OSM lacks starts on the canal OSM draws.
   Artificial paths through lakes and rivers, and connectors, aren't drawn.
4. HydroShare names the canal reaches OSM and NHD leave unnamed, where one
   of its lines runs along half the reach within 20 m. Its placeholders
   ("Unnamed Drain", "Field Supply") are no name, from any source
   (`rules.real_name`), so they never label a line, group a canal or make
   one "named"; its type still sets an unnamed canal's kind (a lateral, a
   drain, a field supply's ditch).
5. Kinds, flow, widths and first zooms come from [`ingest/rules.py`](ingest/rules.py).
   Named canal reaches within 500 m of each other form one canal; one 20 km
   or longer in the box is a main canal ⚠️ (our threshold). An OSM stream
   named "... Canal" is a canal.
6. Topology: links from endpoints and NHDFlow. Two OSM ways meet within
   0.5 m (a shared node), so a lateral leaving a canal a few metres from
   the end of one of its ways (OSM splits canals at every culvert and road)
   still branches from it; anything with an NHD-only run meets within 25 m.
   OSM draws waterways downstream, and NHD's flowdir 1 says the same. Each canal's head is the
   reach from which most of the canal is reached; each reach gets its
   distance from the head. A canal's source is the river, reservoir or
   canal its head leaves (a link, or within 50 m), and its head structure
   the dam, weir or gate within 150 m.
7. Bodies: OSM's water areas, wetlands and pools; NHD's lakes, ponds,
   reservoirs, marshes and river and canal polygons where OSM water covers
   less than half of them. Structures: OSM's and NHD's, and the NWPS
   gauges. NHD's whose shape lies within 50 m of OSM's of the same family
   (a dam and a weir are one) is dropped, and OSM's takes its name when it
   has none: shapes, not points, as a dam drawn as a long area has its
   middle far from NHD's line (Barber Dam: 208 m apart, 1 m between the
   shapes).
8. Gauges: the water a gauge's name says, within 1.5 km (a body for
   "Reservoirs at ..." and "above ... Dam", a river or creek for a river
   name, the canal for "... Canal Diversion"), else the nearest reach within
   300 m.
9. When IDWR's tables hold rows: `canal_org` and `canal_season` (internal),
   from IDWR's polygons made valid again before they're intersected.

**Widths are estimates ⚠️** until measured from NAIP 2025's near-infrared:
perennial streams by Strahler order (1: 1 m, 2: 1.5, 3: 2.5, 4: 4, 5: 6,
6: 9, 7+: 14 m), intermittent ones half that (at least 0.75 m); canals by
kind (main canal 8 m, named canal 5, lateral 2.5, ditch or unnamed 1.5,
drain 3); an OSM width tag of 0.5–40 m over either. **First zooms**:
perennial streams by NHD's visibility filter (1:1M z8, 500k z9, 250k z10,
100k z11, 75k z12, finer z13), rivers by z9, intermittent streams z12
(order 3+) or z13; main canals z10, named canals z11, laterals and drains
z12, ditches and unnamed canals z13, NHD-only canals a zoom later; piped
water z16 only; bodies by size (1 km² z8, 10 ha z10, 1 ha z11, else z13),
river polygons z8, wetlands z14, pools z15.

On scratch (Oct 11, build 10 after the review fixes, about 2.5 minutes as a
light job): 14,604 reaches (7,286 OSM ways, 3,929 km, 6,520 of them
confirmed by NHD; 7,318 NHD-only runs, 8,351 km, of which 2,092 km canals
and laterals and the rest mostly intermittent desert washes), 8,391 named
(1,102 by HydroShare; 495 reaches take their kind from its type), 559
canals (22 main), 14,626 links, 7,736 bodies (4,795 pools; 1,311 NHD-only),
853 structures (the seven NHD-only dams are each over a kilometre from any
of OSM's), and all 13 gauges in the box linked: BSEI1 to the New York
Canal, whose head is the Boise Diversion Dam on the Boise River; LOWI1 to
Lake Lowell; LUCI1 to Lucky Peak Reservoir; the Boise, Snake, Mores Creek
and Succor Creek gauges to their rivers. The New York Canal is two canals
here, as it is on the ground: its lower part leaves Indian Creek.

The schema is about 74 MB with its indexes on scratch; each export about
21 MB in the archive.

### Exports and the base bake

`python3 -m ingest water-export` ([`ingest/export.py`](ingest/export.py))
writes `$TVT_ARCHIVE/water/export/<build>/` through the ground's export
contract, from the newest build (a run of `water-export`, which marks
`landscape-bake`):

| Layer | Base | Fields | What |
|---|---|---|---|
| `reaches` | yes | `id` (stable across builds: an OSM way's id, an NHD run's 2^51 + a hash), `kind`, `name` ('' for none), `width_m`, `intermittent`, `piped`, `nhd_only`, `canal` (0 for none), `minzoom` | every drawn line, the source-layer `water.reaches` |
| `bodies` | yes | `id`, `kind`, `name`, `intermittent`, `nhd_only`, `minzoom` | every drawn area, `water.bodies` |
| `mask` | no | `kind` | the ground's confident water: every body but wetlands, and the reaches OSM draws or both sources agree on, buffered to their widths, with piped water and intermittent channels left out |

All three are ODbL, republish yes, credited to OpenStreetMap, NHD and (when
its names or types are used) HydroShare: the mask too, since it buffers the
reaches to widths that follow their names and kinds. IDWR is never an
input. Each input's sha256 is the download's, the file at its url (the NHD
zip, the HydroShare bag); the prepared GeoPackage loaded from it is named,
with its own hash, in the input's note. Exported columns
are never NULL: PostGIS 3.6.4's `ST_AsFlatGeobuf` writes the value after a
NULL under the NULL column's index, so a reader gets the wrong field or
fails on the feature; names export as '' and canals as 0.

A trial bake on scratch (Oct 11, `--threads 1`, about a minute): 17.5 MB,
z8–16, the largest tile 21 KB at z10 and under 2 KB at z16.

### Wetlands

Vegetated wetlands are bodies of kind `wetland` ([`ingest/wetlands.py`](ingest/wetlands.py); the owner's answer 2 of
Oct 22, issue #309). The National Wetlands Inventory is the only source that maps wetlands as wetlands across the
box, but over the valley floor it dates from July 1981, so those polygons are checked against today's land first.
It is **not a legal (regulatory) wetland boundary**; every card says so.

- **Loading** (`nwi-load --from nwi_mapbox.gpkg`, standard library): the vegetated palustrine polygons only (Cowardin
  class EM, SS or FO first: 13,753 of 23,797), each with the mapping project that holds its point. Its `era` is
  `recent` (imagery of 1999 or later: 12,178), `old` (July 1981 or 1983 photos: 1,572), `interim` (the "Scalable"
  product: 3) or `unknown` (none). NWI's ponds, lakes and riverine polygons are not kept: the bodies and reaches already
  draw that water. Hydric soils stay a row on the soils card.
- **The presence check** applies to `old` and `interim` polygons. A worker step (rasterio, on the ground's grid, from
  mask v0's exact roofs, roads and paving, the held CDL clips and CSB's eight yearly codes) writes five shares per
  polygon to a JSON file, which `nwi-presence --from` loads (the file's format is in the module's docstring). The
  rules are `wetlands.presence()`: retired as `built` (built half or more, or a quarter with CDL developed at half and
  no support); retired as `farmed` (cultivated half or more, no support), or flagged `farmed_supported` with support;
  flagged `hay_pasture` (half or more); otherwise kept. Support is CDL wetland classes over a quarter of the
  polygon; an OSM wetland or NHD marsh overlapping it is listed on the card as evidence but does not rescue it. CDL class 121 counts for nothing. The thresholds are the
  review's first guesses, to be tuned on the ten boxes (the Greenbelt strip's roof share first). **An old polygon with
  no shares yet is `unchecked` and not drawn.**
- **Conflation** (water-build, [`ingest/build.py`](ingest/build.py) `WETLANDS`): where OSM and NWI outline one wetland
  (they overlap half or more of the smaller and a quarter of the larger) OSM's outline is drawn with NWI's class and regime
  (`geometry_from` `osm`, confirmed); NWI alone is drawn from its own outline (`geometry_from` `nwi`), minus every OSM
  wetland (a paired polygon still draws what OSM's outline leaves, if that is a quarter of it); NHD's marshes are evidence where an NWI polygon (retired or unchecked too) or OSM wetland covers half of them; NWI wetlands never hide an NHD lake, pond, river or canal, and
  draw alone otherwise. `thin` marks the older mapping (the 1981-83 and interim polygons that passed, and NHD's marsh
  alone): thinned tufts from z15, where the rest are tufts from z14.
- **Generalisation, per zoom, for the bake's byte budget:** NWI outlines are simplified to 1 m, NWI-only polygons under
  60 m² are dropped, and a wetland draws from the first zoom at which it covers about 20 pixels (z14 or z15 at the
  earliest, z16 at the latest). Measured on the Oct 23 cut: the 12,178 recent polygons, simplified, are about 6 MB as
  FlatGeobuf (22.5 MB unsimplified), and 6,825 of the drawn ones start at z14, 4,391 at z15 and 934 at z16. The bake's
  budget binds per z16 tile of the downtown box (basemap/landscape/spec.json), where wetlands are sparse.
- **Checks and the QA sheet:** `wetland-qa [--build N] [--boxes] [--out DIR]` prints the outcome counts of the old
  polygons (per test box with `--boxes`) and writes `qa-old-mapped.csv`, the retired first, for the owner's QA sheet;
  `--out` is a folder in the private files, never the repository. Retired polygons stay in `water.wetland_check` with
  the reason and the shares.
- **Credit:** "Wetlands: U.S. Fish and Wildlife Service, National Wetlands Inventory" wherever NWI's classes or outlines
  show; the bodies layer's manifest lists `nwi` as an input beside OSM and NHD.

### The canal season

Whether each canal has water: on, off or unknown (landscape sprint
package P5, data side, Oct 11, 2026; the owner's decision 18). The app
draws a canal filled when on, hollow when off and neither when unknown,
through feature-state on the baked reaches (their `canal` field): that's
P5-app's. Here, each canal's season becomes lifecycles in `evt.event`
([`ingest/season.py`](ingest/season.py)), from core's rules-by-date
evaluator ([`ingest/seasons.py`](../../ingest/seasons.py)) over one rule
set per canal. Strongest first:

1. **Its gauge.** The New York Canal (the upper canal, from the Boise
   Diversion Dam) follows BSEI1, "New York Canal Diversion at Boise", from
   the readings `nwps_gauges` keeps (stage in ft, flow in kcfs):
   - a flow of 10 cfs or more is **on**, any lower flow **off**;
   - with no flow (BSEI1 reports none once the canal is off), a stage of
     7.3 ft or more is on, and 3.7 ft or less (plus 0.2 ft, as the empty
     canal's level drifts) off;
   - in between, the canal is filling or draining, and the state before
     holds.

   The levels are the two seen at the head ⚠️ (one season's shut-off):
   7.33–8.34 ft at 1,660–2,090 cfs from Sep 7 to Sep 27, 2026, then a
   3.5-hour ramp down on the morning of Sep 28 (the last flow 126 cfs at
   3.85 ft) to 3.69–3.73 ft with no flow. **48 hours without a reading,
   the canal is "unknown"**, not on or off: from 48 hours after the last
   reading, and between two readings more than 48 hours apart. The gauge's
   claim starts at its first on or off reading; before it, the rules below
   apply.
2. **The district's dates**, from [`ingest/canal_dates.json`](ingest/canal_dates.json),
   a versioned file that `canal-dates-load` loads into `water.canal_date`
   ([`ingest/sources/canal_dates.py`](ingest/sources/canal_dates.py)). It
   is empty until the owner asks for the lookups; each entry is one
   district's season as its own page states it, looked up by hand (never
   scraped), with the page and the day it was read. Within its year an
   entry is off before its `on`, on from `on` to `off`, and off from
   `off`; while no shut-off is announced, the water runs to the end of
   the canal's legal season. That end is IDWR's date, so the span says
   so (`end_from` `legal`), credits IDWR and is **internal** until the
   shut-off is entered. Canals are named as the district names them
   (`water.canal` names, matched without case or punctuation), and
   `"branches": true` adds the canals fed from them. A name selects every
   canal of that name in the valley, and in build 10, 58 names (as
   matched) belong to more than one canal, 126 in all: the heads of
   three Stevens Laterals lie up to 35 km apart. So `canal-dates-load`
   and its dry run list every name that selects several canals, with
   each one's id, length and the IDWR service areas at its head, and two
   optional keys narrow a name: `head_in` (service-area names: only the
   canals whose head lies in one, from `water.canal_org`) and
   `canal_ids` (`water.canal` ids, which follow the builds: prefer
   `head_in`). The load also says how many canals each entry selects. A
   later entry wins over an earlier one, and the gauge over both, its
   "unknown" included.
3. **IDWR's legal season of use** at the canal's head
   (`water.canal_season`): on within it, off outside it, always labelled
   as the legal window, not delivery dates.
4. Nothing: no lifecycle, which reads as unknown.

**Never off:** drains, and canal-class lines named for a creek, river,
slough or gulch without a canal word (Fivemile Creek, Mason Creek, Purdam
Gulch; but Mason Creek Feeder and Dry Creek Canal are canals): one
lifecycle each, on, basis `always`. Unnamed reaches belong to no canal
and get none.

**Where it runs.** `canal_season` is a source, every hour inside `ingest
serve` (after `nwps_gauges`), and by hand (`canal-season`;
`canal-dates-load` runs it after a load). It fetches nothing and builds
nothing: it turns readings and dates into lifecycles, as `nwps_gauges`
turns its readings into flood episodes, and the 48-hour rule needs a
clock, or a gauge that fell silent would leave its canal "on". Each
statement is limited to 30 s. It writes only when a lifecycle changed: a
state change at the gauge, the 48-hour rule, a new water build, a new
dates file, the new year. `ops.source_status` (M1) shows it like any
scheduled source, and its run notes when `canal_dates.json` differs from
what was last loaded.

**Lifecycles** (`evt.event`, source and kind `canal_season`), from Jan 1,
2026 to the end of next year:

| Column | What |
|---|---|
| `source_id` | `<canal id>@<start, UTC ISO>` (`water.canal.id`, which follows the build) |
| `declared` | [start, end): end null for the gauge's current span (it holds until a reading changes it, or 48 hours pass without one) and for `always` |
| `severity` | the state: `on`, `off` or `unknown` |
| `description` | the card's words: "New York Canal: off (gauge BSEI1, New York Canal Diversion at Boise)", "...: in IDWR's legal irrigation season (3/1 - 11/15), not delivery dates" |
| `geom` | the canal's head (its head reach's start) |
| `attributes` | `canal_id`, `canal`, `canal_kind`, `state`, `basis` (`gauge`, `district`, `legal`, `always`), `why`, `credit` (a list), `republish`; for a gauge `gauge`, `gauge_name`; for a district `entry`, `district`, `words`, `source`, `read`, `off_announced`, and `end_from` (`legal`), `season`, `objectid` when IDWR's window ends the span; for the legal window `season`, `objectid` |
| `active` | false once a lifecycle leaves the derivation (a build renumbers a canal, late readings fill a silence): read active rows |

**Licences.** Every lifecycle names a canal of the water network: it
credits OpenStreetMap (ODbL) and NHD, and HydroShare's canal network (CC
BY 4.0, with its creators, DOI and "modified") whenever the canal's
`sources` include it, since HydroShare named or typed the canal or
matched it (522 of build 10's 559 canals; 131 have no other name). A
gauge's lifecycles are NWPS's (public domain): republish yes. BSEI1's NWPS
record names no USGS site and no other source, so its credit is NWPS's
alone. A district's are facts with their page cited: republish yes unless
the entry says otherwise, and internal for an "on" that ends on IDWR's
date. The legal window's are IDWR's: **internal**, like the window
itself; the source's own row says internal, the strictest. The canal
season is never in the base bake (`basemap/landscape/plan.py` refuses
`water/canal_season`): it's drawn as feature-state.

On scratch (Oct 11, water build 10, the readings the copy holds up to
07:15 UTC that morning), a run took 4 s: 559 canals gave 2,017
lifecycles (about 1.4 MB). 188 canals never switch off, 365 follow IDWR's
window (on at the time: 3/1 to 11/15 at their heads), 5 have neither, and
the New York Canal reads on from BSEI1's first reading (Sep 7) and **off
since Sep 28, 07:45 Boise time**, its first reading with no flow (3.79
ft). The next run wrote nothing. As of Oct 13, 07:15 UTC, 48 hours after
the copy's last reading, the off span closes and "unknown" begins; a
minute earlier nothing changes. 1,885 lifecycles, on the 518 canals
with rows whose sources include HydroShare, credit it. A trial dates
file (never committed; loaded, then the empty file again): "Stevens
Lateral" was reported as three canals, with their lengths and the
service areas at their heads, and `head_in` narrowed it to one; the
Ridenbaugh Canal with `branches` and no shut-off selected 41 canals that
switch off, whose "on" ended on Nov 16 with IDWR's window, internal.

### Commands

```bash
# the worker image (GDAL), no network: files to files
python plugins/water/build/prepare.py nhd --zip $TVT_SOURCES/nhd/download/NHD_H_1705_HU4_GDB.zip --out DIR
python plugins/water/build/prepare.py hydroshare --zip $TVT_SOURCES/hydroshare/<id>.zip --out DIR
# the ingest image (standard library; it carries basemap/ground and basemap/landscape's plan for the export)
python3 -m ingest nhd-load --from DIR/nhd.gpkg              # replaces water.nhd_*; skips a file already loaded
python3 -m ingest hydroshare-load --from DIR/hydroshare.gpkg
python3 -m ingest nwi-load --from nwi_mapbox.gpkg [--dry-run]   # the NWI cut kept on the server (water 0003)
python3 -m ingest nwi-presence --from shares.json [--dry-run]   # the worker step's presence shares
python3 -m ingest wetland-qa [--build N] [--boxes] [--out DIR]  # after water-build; DIR in the private files
python3 -m ingest osm-load --only water.osm_waterways        # on the valley cut we hold (light)
python3 -m ingest run idwr_irrigation_orgs idwr_season_of_use
python3 -m ingest water-build [--dry-run]
python3 -m ingest water-export
python3 -m ingest canal-season [--dry-run [--as-of TIME]] [--canal NAME]   # the canal season now (hourly in serve)
python3 -m ingest canal-dates-load [--dry-run] [--file PATH]   # after editing canal_dates.json; then the season
python3 -m unittest discover -s plugins/water -t .           # with TVT_TEST_DATABASE_URL for the database tests
/srv/tvt/work/bin/worker-test -C <checkout> plugins.water.tests.test_prepare
```

**Deploying** (the runbook's loads, as `tvt_build`, after migration water
0001): copy the two prepared GeoPackages (or prepare them again from
`/srv/tvt/work/sources/`) into `$TVT_ARCHIVE/water/prepared/`, with the
NHD zip and its PROVENANCE moving to `$TVT_ARCHIVE/water/nhd/`; then
nhd-load, hydroshare-load, `osm-load --only water.osm_waterways` (light on
the cut production holds), the two IDWR sources once, water-build,
water-export, and the base bake. Migration water 0002 adds the canal
season's dates table; `canal_season` then runs by itself every hour (it
waits for a water build), and `canal-dates-load` once the dates file has
entries. After a new extract, `osm-load` reloads the water consumer with
the rest, and water-build follows (the refresh cascade); the canal season
follows the new build within the hour.

**Limits ⚠️**: widths are estimates; NHD-only canals are topo-era and some
are piped or gone (they draw lighter, and the card says so); 1,139 of OSM's
canal ways are culverts or pipes; OSM's names vary ("A line Canal");
`canal_org` lists the service areas a canal runs through, not who runs it,
and service areas overlap; the main-canal threshold is ours. The canal
season: one gauge (BSEI1) for one canal, its thresholds from one season's
shut-off; other canals have IDWR's legal window (not delivery dates) until
district dates are entered; laterals fed by the New York Canal don't
follow its gauge.
