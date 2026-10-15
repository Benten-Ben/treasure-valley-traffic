# ingest: data collectors

Python ingestors that write to the database (see [db/](../db)). This is a
clean rebuild that keeps the prototype's lessons, not its code (the
prototype is [`tvt/`](../tvt)).

**Core and plugins** ([docs/15](../docs/15-plugins.md)). This folder is the
core every subject shares: the CLI (`__main__.py`), polite HTTP with the
robots.txt parser (`http.py`), sources, fetch logs and record versions
(`db.py`), event lifecycles (`events.py`), the shared readers for ArcGIS
layers (`arcgis.py`) and COMPASS's layers (`compass_layer.py`), the UTM
projection (`utm.py`), the line matcher that places one network's lines on
another (`linematch.py`; roads uses it, trails will), the rules-by-date
evaluator for seasons, closures and other recurring rules (`seasons.py`),
build marks and build runs (`builds.py`, [below](#builds-marked-by-sources-run-by-hand)),
the OpenStreetMap loader that reads one hand-downloaded extract into every
plugin's consumers (`osm_extract.py`, the `osm-load` command; below), and
the plugin loader (`manifest.py` reads and orders the manifests;
`sources/__init__.py` builds `SOURCES`, `STREAMS` and the plugin commands
from them). Each subject's sources live in its plugin,
`plugins/<name>/`, with a `plugin.json` (sources, licenses, whether we may
republish, tables, commands), a README, its migrations and its tests. Source
names didn't change, so `ops.source` and `ops.fetch` carry on:

| Plugin | Sources (in run order) | Commands |
|---|---|---|
| [cameras](../plugins/cameras) | `achd_cameras`, `idaho511_views_oneoff`, `idaho511_rwis_sites_oneoff`; stream `idaho511_frames` | `rollup` |
| [transit](../plugins/transit) | `vrt_gtfs`; stream `vrt_realtime` | `match-routes`, `transit-progress`, `transit-ribbons`, `route-colors` |
| [roads](../plugins/roads) | `achd_roads`, `itd_hpms`, `achd_msm`, `compass_centerline`, `achd_bike_network`; by hand (OpenStreetMap consumers) `osm_valley`, `osm_street`, `osm_paving`; by hand `cdl_developed` | `segment-match`, `roads-developed-load`, `roads-build`, `roads-export` |
| [conditions](../plugins/conditions) | streams `itd_wzdx`, `idaho511_api` | |
| [intersections](../plugins/intersections) | `fra_crossings`, `achd_signal_points`, `compass_signals`, `compass_regional_signals`, `intersections` | `match-intersections` |
| [safety](../plugins/safety) | `compass_crashes` | |
| [flow](../plugins/flow) | `compass_counts`, `compass_congestion` | |
| [development](../plugins/development) | `compass_growth`, `compass_plats` | |
| [hazards](../plugins/hazards) | `idl_fire_restrictions`, `nifc_wfigs_incidents`, `nifc_wfigs_perimeters`, `nasa_firms`, `nws_wwa`, `usgs_quakes` | |
| [air](../plugins/air) | `noaa_hms_smoke` | |
| [water](../plugins/water) | `nwps_gauges`, `nrcs_snotel`, `boise_ecoli`, `boise_river_hazards`, `usdm_drought`, `idwr_irrigation_orgs`, `idwr_season_of_use`, `canal_season` (derived, hourly); by hand `nhd_hr`, `hydroshare_canals`, `canal_dates`, and (OpenStreetMap consumer) `osm_waterways` | `nhd-load`, `hydroshare-load`, `water-build`, `water-export`, `canal-season`, `canal-dates-load` |
| [trails](../plugins/trails) | `r2r_trails`, `boise_greenbelt_closures`; manual `osm_paths` (an `osm-load` consumer), `trails_match` | `trails-match` |
| [lands](../plugins/lands) | `usfs_r4_orders`, `idpr_route_closures`, `idpr_area_restrictions` | |
| [weather](../plugins/weather) | `awc_metar` | |
| [wildlife](../plugins/wildlife) | `idfg_roadkill` | |
| [farm](../plugins/farm) | `agrimet_et` | |
| [sky](../plugins/sky) | `swpc_ovation`, `swpc_kp_1m` | |

Private plugins (ACHD's tables, parcels) live on the server, outside this
repository: `TVT_PLUGIN_PATH` names their parent folders and they load the
same way. The old module entry points (`python3 -m ingest.osm_load`,
`ingest.segment_match`, `ingest.transit_progress`, `ingest.transit_ribbons`)
still work and name the new commands.

**OpenStreetMap** (landscape sprint, Oct 2026; plan C1, C2, C10). Geofabrik's
robots.txt disallows scripted downloads, so the owner downloads the Idaho
extract in a browser into `$TVT_ARCHIVE/osm/inbox/`, and `python3 -m ingest
osm-load` (`osm_extract.py`) reads it into each plugin's **consumers**, listed
in its `plugin.json` (`osm_consumers`: one of its by-hand sources, the osmium
tags-filter expressions it wants, the geometry it gets, the tables it writes).
A load checks the MD5, cuts the valley box **once** with osmium's `smart`
strategy (ways with a node in the box whole, multipolygons with a member in it
whole; kept as `$TVT_ARCHIVE/osm/cut/valley.osm.pbf` with `valley.json`, which
the ground's mask reads), runs each consumer whose own MD5 gate says it hasn't
loaded this extract, each with its own `ops.fetch` row, then archives the file
(the last two are kept). Gates: `ops.osm_consumer` (migration 0019), except
`osm_valley`'s, which stays `$TVT_ARCHIVE/osm/last-loaded.json`. Highway ways
are split between consumers by tags alone (`owner()`): osm_valley's keep rule,
unchanged, then streets and alleys (`osm_street`), sidewalks, crossings and
other service ways (`osm_paving`), then paths (`osm_paths`); the lane-tagged
cycleways, tracks and pedestrian ways osm_valley already keeps are the named
exception. No way has two owners; 1,811 of the Oct 5 extract's 185,358 have
none (unbuilt, indoor, and 17 raceways and odd classes no consumer names:
[docs/12](../docs/12-database-schema.md)). The partition holds only while its
owners hold one extract, so osm_valley loads first and `osm_street`,
`osm_paving` and `osm_paths` load only the extract it holds: one that would
load another is held back, and so is osm_valley when a follower that holds
another extract isn't loading in the same run (`--only osm_valley` on a new
extract). `--allow-mixed` lifts both holds; `--force` doesn't. They can still
differ if a follower fails after osm_valley loaded, so a build that reads
their tables together calls `check_partition(conn, names)` first, which
returns the one extract's MD5 or raises; `--list` and each load say when the
owners differ. The new consumers' tables are
versioned in place (`store_objects`: OpenStreetMap's version and timestamp,
first and last seen, active, and the shrink guard at any size), with no
`raw.record` copies.

A consumer's manifest entry is checked (`manifest.py`): its source is one of
the plugin's by-hand sources, with license ODbL and the credit "©
OpenStreetMap contributors"; each type its tags name has its geometry and
each geometry its type (n/ point, w/ linestring, a/ polygon, r/ relation).
osmium export makes areas only from a/ expressions, so a lot or a lake needs
`a/amenity=parking`, not `nwr/amenity=parking`.

| Consumer | Tags | Writes |
|---|---|---|
| `roads.osm_valley` | highway ways; signal, crossing-signal and level-crossing nodes | as below (unchanged; its own pipeline over the cut) |
| `roads.osm_street` | residential, unclassified, living_street, road, busway and alleys that osm_valley doesn't keep | `roads.osm_street` |
| `roads.osm_paving` | the other service ways, sidewalks, crossings, access aisles and traffic islands; parking lots and stalls drawn as areas (multipolygons too); crossing and kerb nodes. Untagged service ways and lots get a default material only on the Cropland Data Layer's developed land, traced in the worker image and measured in PostGIS ([plugins/roads](../plugins/roads/README.md#paving-service-ways-sidewalks-crossings-and-lots)) | `roads.osm_paving`, `roads.osm_parking`, `roads.osm_walk_node` |
| `water.osm_waterways` | waterways (lines and nodes), water areas, wetlands, springs, reservoirs and basins, swimming pools (not part of the highway partition) | `water.osm_feature` |

```bash
python3 -m ingest osm-load --inbox                  # a new extract: every consumer (a heavy job: see below)
python3 -m ingest osm-load --only roads.osm_street  # one consumer, on the extract we hold
python3 -m ingest osm-load --archived [--force]     # every consumer due, on the extract we hold
python3 -m ingest osm-load --cut-only               # just the valley cut (heavy)
python3 -m ingest osm-load --only osm_paths --make-cut   # make the cut if it's missing, then load (heavy)
python3 -m ingest osm-load --list                   # the consumers, what each loaded last, the partition
```

**Memory** (measured Oct 11 on the Oct 5 extract, 129 MB). osmium keeps a
bitmap over every node id, and Idaho's run to about 13 billion, so the smart
cut and osm_valley's own `complete_ways` cut each peak at about 3.9 GB for
about 15 s; a load that makes a cut, or runs osm_valley, is a heavy job (give
it 5 GB: [deploy/README.md](../deploy/README.md)). The other consumers don't
use osmium's tags-filter, which would need 1.9 GB even on the 32 MB cut: they
export the cut's tagged objects (about 140 MB) and pick theirs in Python, so a
consumer on a cut already made is light (`osm_street`: 16 s, under 0.2 GB).
So a load never makes the cut by surprise: only a run with osm_valley due,
`--make-cut` or `--cut-only` makes it, and any other run stops before loading
when it's missing.

**Status:** camera sources (for the calibrator), Valley Regional Transit (buses), ITD's work zones and the 511 Idaho API.

| Source | Access | Schedule | Writes |
|---|---|---|---|
| `achd_cameras` | open (ACHD GIS, no robots.txt) | daily | `raw.record`, `core.camera` (228), `core.source_link` |
| `idaho511_views_oneoff` | one-off (dated private file `511-camera-views-2026-10-05.csv`, read from `TVT_PRIVATE_DATA`) | never | `core.camera_view` (210 linked within 200 m) |
| `idaho511_rwis_sites_oneoff` | one-off (dated private file `511-camera-sites-statewide-2026-10-05.json`, read from `TVT_PRIVATE_DATA`; no request to 511) | never (by hand: the deploy runbook's step 2) | `raw.record`, `core.camera` (ITD's road-weather stations statewide as provider `ITD RWIS`, about 130, and Oregon DOT's cameras in the regional ring as `ODOT`; [docs/14 §14.6](../docs/14-ui-v2.md#road-weather)), `core.camera_view` (each station's views by 511 image id, about 385), `core.source_link` |
| `achd_roads` | open (ACHD GIS, no robots.txt) | weekly | `raw.record`, `core.road_segment` (38,727 Ada County segments: posted speed, class, one-way, level, community), `core.source_link`; a run that changes the segments rematches every lane source and OpenStreetMap in `core.segment_match` |
| `itd_hpms` | open (ITD GIS, no robots.txt; no license stated, credit ITD) | monthly | `raw.record` (one source per layer, `itd_hpms_<kind>`, keyed `<EventID>@<RouteID>:<FromMeasure>`, plus `itd_hpms_road_names`), `core.hpms_section` (33,770 pieces touching the valley box: through lanes 19,507, turn lanes 637, lane width 558, median 738, shoulders 634, access control 5,376, peak lanes 1,384, facility type 4,936), `core.segment_match` |
| `achd_msm` | open (ACHD GIS, no robots.txt; no license stated) | monthly | `raw.record` (by GlobalID; the bulk-stamped edit dates left out), `core.msm_arterial` (1,049 Master Street Map arterials; existing lanes on 896), `core.segment_match` (`buffer10_name`; `buffer10_bearing20` where a state-route name faces a street name) |
| `compass_centerline` | open (COMPASS on swidrdc.org, no robots.txt rules; disclaimer only, credit COMPASS) | monthly | `raw.record` (by globalid), `core.compass_segment` (62,213 pieces in Ada and Canyon on 26,911 `pm_id`s; lanes on 61,404), `core.segment_match` (Canyon's pieces stay unmatched: no ACHD segments there) |
| `achd_bike_network` | open (ACHD GIS on gis.achdidaho.org, robots.txt 404: no rules; no license stated, a disclaimer only: internal, credit ACHD) | monthly (a content hash of the read: an unchanged layer only confirms its versions) | `raw.record` (by OBJECTID, carried over when a reload renumbers them), `roads.bike_facility` (3,932 records on Oct 11, 2026: curb-to-curb and right-of-way widths, per-direction lanes, bike facilities, buffers and parking, ACHD's LTS), `roads.bike_facility_note` (ACHD's free text: internal, in no view or export), `roads.bike_facility_match` (street records on ACHD segments: `buffer15_bearing20`, names must not disagree); views `roads.bike_facility_side` and `roads.segment_bike_xsection` (per ACHD segment, forward and backward, in metres: the real-width roads build's input; [plugins/roads](../plugins/roads/README.md#achds-bike-network-widths-for-the-real-width-roads)) |
| `vrt_gtfs` | open (VRT, CC BY 3.0) | daily | `core.transit_route`/`_stop`/`_shape`/`_trip`; each zip archived in `$TVT_ARCHIVE/vrt-gtfs/`. Picks each route's map color (routes sharing streets differ). |
| `vrt_realtime` | open (VRT, CC BY 3.0) | stream, every 30 s | each changed feed archived in `$TVT_ARCHIVE/vrt-gtfs-rt/<date>/`; bus positions in `obs.vehicle_position` |
| `itd_wzdx` | open (ITD's WZDx feed on 511 Idaho; may be republished, crediting ITD) | stream, every 5 min | each changed snapshot archived in `$TVT_ARCHIVE/wzdx/<date>/`; every work zone's versions in `raw.record`; cleaned rows in `evt.event` (fixes listed per row; [docs/08 §8.8](../docs/08-data-inventory.md#88-itds-work-zone-feed-checked-against-the-wzdx-spec-oct-6-2026)) |
| `idaho511_api` | API key (`IDAHO511_API_KEY`; 511 Idaho developer terms; not republished) | stream, per endpoint: events and signs 2 min, weather and advisories 5, truck restrictions and winter roads 15, cameras hourly, the rest daily; at most 8 calls a minute | changed responses archived in `$TVT_ARCHIVE/idaho511/<endpoint>/<date>/`; versions in `raw.record` (one source per endpoint, `idaho511_<endpoint>`); `evt.event` (events, advisories, truck restrictions), `core.message_sign` + `evt.sign_message`, `core.weather_station` + `obs.weather_reading`; the regional capture list in `$TVT_ARCHIVE/lists/` |
| `fra_crossings` | open (FRA on data.transportation.gov, public domain; robots allows /resource/, Crawl-delay 1) | weekly | `raw.record` (by crossing number, without Socrata's computed-region columns), `core.rail_crossing` (433 in Ada and Canyon; 197 closed, kept and flagged), `core.source_link` |
| `achd_signal_points` | open (ACHD's 2022 layers on ArcGIS Online, frozen Aug 2, 2022; no robots rules) | monthly | `raw.record` (`<layer>:<OBJECTID>`), `core.signal_device` (2,469 signal poles, 182 pedestrian signals, 33 school flashers, 68 fire signals) |
| `compass_signals` | open (COMPASS on ArcGIS Online; no license, "meant only for reference": internal until COMPASS answers) | weekly | `raw.record` (`synchro:<id>`, else `loc:<operator>:<location>`), `core.signal_device` (585 signalized intersections with operator, coordination and per-approach lanes, phasing and modelled volumes) |
| `compass_regional_signals` | open (COMPASS on swidrdc.org; internal until COMPASS answers) | weekly | `raw.record`, `core.signal_device` (1,076 devices: 586 traffic signals, the rest pedestrian signals, flashers and fire signals) |
| `intersections` | derived (fetches nothing; by hand: `python3 -m ingest match-intersections [--dry-run]`) | daily | `core.intersection` (633 after the Oct 7 OpenStreetMap load: 585 active, 43 candidates, 5 retired by review in `plugins/intersections/ingest/intersection_reviews.json`; 42 of the candidates are new, from OSM signal nodes with no COMPASS match, and need review. Before the load it was 591 with 1 candidate), `core.approach` (2,276), `core.signal_device.intersection_id`, camera and OSM links in `core.source_link` (199 cameras, 3 of them to interchanges; 711 OSM nodes), `core.rail_crossing.intersection_id` (nearest active signal within 300 m; 56 crossings). Since OSM nodes now confirm and create intersections, `core.intersection` is an ODbL derivative database: credit "© OpenStreetMap contributors", and anything published from it stays ODbL ([docs/12 §12.5](../docs/12-database-schema.md#125-core-our-entities)) |
| `osm_valley` | open (OpenStreetMap, ODbL; credit "© OpenStreetMap contributors"); by hand only: Geofabrik's robots.txt disallows scripted downloads (Oct 6), so the owner downloads the Idaho extract in a browser into `$TVT_ARCHIVE/osm/inbox/`. Not a scheduled source; no download code. A consumer of `osm-load` (above), first | by hand, weekly (`python3 -m ingest osm-load --inbox`) | `raw.record` (`w<id>`/`n<id>`: tags and a geometry hash), `core.osm_way` (major ways and every way with lanes), `core.osm_lane`, `core.osm_node` (intersection signals, crossing signals, level crossings), `core.segment_match` (ACHD segments, by the shared matcher: `buffer15_bearing20`, and `way_in_buffer15_bearing20` for turn-bay ways); extracts archived in `$TVT_ARCHIVE/osm/` (last two) |
| `compass_crashes` | open (COMPASS hub, disclaimer only; swidrdc.org has no robots.txt) | monthly (unchanged layers skipped; 6 h back-off) | `raw.record`, `obs.crash` (174,038 crashes 2008-2025: local time, KABCO severity, pm_id/int_id, unit types), `restricted.crash_unit` (345,152 people: age group, Idaho resident or not, coded citations; no sex; never in `raw.record`; aggregates only), `core.hin_junction` (1,924), `core.hin_segment` (14,487) |
| `compass_counts` | open (COMPASS hub) | monthly | `raw.record`, `obs.traffic_count` (latest short count on 4,387 segments from every agency; 115 permanent counters; earlier counts kept) |
| `compass_growth` | open (COMPASS hub) | monthly (unchanged layers skipped) | `raw.record`, `core.taz` (2,498 zones), `obs.taz_demographic` (2020 Census, estimates 2022-26, forecasts 2030-55), `obs.building_permit` (174,244 since 2000; no addresses, parcels or comments) |
| `compass_plats` | open (COMPASS hub) | weekly | `raw.record`, `core.plat` (1,061 development applications: homes planned, permitted and still to build; jobs) |
| `compass_congestion` | open, internal use only (swidrdc.org only; not offered as open data) | monthly (unchanged layers skipped) | `raw.record`, `obs.congestion_measure` (47,293 segment-years 2018-2025), `obs.commute_travel_time` (16 commutes, AM and PM) |

```bash
pip install -r ingest/requirements.txt
export DATABASE_URL=postgres://tvt:<password>@localhost/tvt
python3 -m ingest sources
python3 -m ingest run all           # or: run achd_cameras
TVT_ARCHIVE=data/archive python3 -m ingest stream vrt_realtime            # live buses, every 30 s
python3 -m ingest backfill vrt_realtime data/archive/vrt-gtfs-rt          # reload positions from the archive
TVT_ARCHIVE=data/archive python3 -m ingest stream itd_wzdx                # ITD work zones, every 5 min
TVT_ARCHIVE=data/archive IDAHO511_API_KEY=... python3 -m ingest stream idaho511_api   # the 511 API (key never committed)
python3 -m ingest backfill itd_wzdx data/archive/wzdx                     # load snapshots the database missed
python3 -m ingest match-intersections --dry-run                         # rebuild core.intersection from the signal sources
TVT_ARCHIVE=data/archive python3 -m ingest osm-load --inbox             # OSM extract downloaded by hand (needs osmium-tool)
TVT_ARCHIVE=data/archive python3 -m ingest osm-load --only osm_street   # one consumer, on the extract we hold
TVT_COMPASS_MAX_PAGES=3 python3 -m ingest run compass_crashes          # dev only: at most 3 pages per layer, logged as failed
TVT_COMPASS_FORCE=1 python3 -m ingest run compass_growth               # skip the freshness and change checks
python3 -m ingest segment-match [itd_hpms achd_msm compass_centerline osm_valley achd_bike_network]   # rematch to ACHD segments by hand
python3 -m ingest -h                                                    # every command, the plugins' included
python3 -m unittest discover -s ingest/tests -t .                       # core
python3 -m unittest discover -s plugins -t .                            # the plugins
```

Each run logs to `ops.fetch`. Records are versioned in `raw.record`, so a
re-run that finds nothing new adds nothing.

### Builds: marked by sources, run by hand

Builds (`roads-build`, `water-build`, `trails-match`, the exports, the
base bake) never run inside `ingest serve` (plan §0 item 27): `builds.Run`
refuses there. A source whose new data a build should take in marks the
build in the same transaction as its data, and the build, run by hand
(under the VM's `heavy` when it's heavy), clears the marks it saw when it
started once it succeeds (migration 0021, `builds.py`):

```python
from ingest import builds
builds.mark(conn, "roads-build", by="osm_street", reason="new extract 2026-10-12")   # doesn't commit
with builds.Run(conn, "roads-build", then=["landscape-bake"]) as run:   # one run at a time per database
    ...                                    # the build; run.note = "41,203 pieces"
```

One exception predates the rule: the scheduled `intersections` source
(the intersections plugin) rebuilds `core.intersection` from the signal
sources inside `ingest serve` once a day, in about 10 s. It stays a
source, logged in `ops.fetch`, until the owner decides otherwise. And the
trails pollers relink the few lines a poll changed once its data is
committed (plan P6-data: at most 40 lines, a few seconds), in their own try
block with their own `ops.fetch` row (`trails_match`), so a failure never
fails the poll. Each statement stops after 20 s and the relink after 60 s,
so it can't hold up the sources after it; anything bigger, or out of time,
marks the `trails-match` build ([plugins/trails](../plugins/trails/README.md)).

A build is named by the command that runs it (or, for a worker step, its
job), in lower-case letters, digits, `.`, `_` and `-`. A run that fails
clears nothing and logs its error, and the build reads `failed` until a
run succeeds, even while it's marked. One stopped by SIGTERM (heavy's
deadline) is logged as stopped. One killed outright (SIGKILL, the OOM
killer) can't log anything, but it no longer holds the build's lock, so
`ops.build_status` reads it as failed, and the build's next run closes
its row.

A command logs its run one way, never both. A command that uses
`builds.Run` (its plugin's README says so) is run plainly,
`python3 -m ingest <command>`. `python3 -m ingest.builds run` is for a
command that doesn't log itself; a `builds.Run` of the same build inside
it refuses. When it's stopped, it stops its command (SIGINT, so a Python
command's psycopg cancels its query; then SIGTERM; then SIGKILL; 20 s at
most, well inside heavy's 60 s grace), and when the command fails or is
stopped it ends the database sessions the command left (they carry
`application_name` `tvt-build-<run id>`). Its note is the command's
first words, stopping at anything that could carry a secret; `--note`
says more. A shell command can't be stopped this way: wrap the program
itself, or use `exec`.

```bash
python3 -m ingest.builds                                   # each build: state, marks, age
python3 -m ingest.builds mark roads-build --by 'by hand: lead' --reason 'ACHD widths fixed'
python3 -m ingest.builds run segment-match -- python3 -m ingest segment-match   # a command that doesn't log itself
python3 -m ingest.builds start landscape-bake              # a worker step can't reach the database:
python3 -m ingest.builds finish <id> --ok --note 'landscape-3fa9c1.pmtiles'   # log its run around it
python3 -m ingest.builds done roads-build --note 'built by hand'   # clears what's marked now
```

`ops.build_status` shows each build's state and age, and
`ops.source_status` each scheduled source's last good fetch against its
schedule. `/api/meta`'s `status` and the VM's `bin/status` report both.

Rules carried over from the prototype, which all ingestors must follow:

- Check robots.txt before every request, using the lenient RFC 9309 parser
  ([docs/10 §10.5](../docs/10-architecture.md#105-what-the-prototype-taught-us-kept-as-lessons-not-code)),
  and honor crawl-delay.
- Identify ourselves with a descriptive User-Agent.
- Only collect sources marked allowed in
  [docs/08](../docs/08-data-inventory.md). Never store Google, TomTom, HERE,
  Mapbox or Waze data.
- Log every fetch (status and robots decision) so gaps are visible.

## Verifying a source

When the owner asked to verify the ingestors one at a time (Oct 5, 2026),
the prototype's `achd_cameras` went through six checks. They make a
reusable acceptance test for each new ingestor or plugin source. Checks 5
and 6 were never run: the owner then chose to go over each source in detail
before committing to how it is used.

| Check | What it asks | `achd_cameras` (Oct 5) |
|---|---|---|
| 1. Count against the source | Does what we stored match what the source lists, after deduplication? | 232 source records, 228 unique cameras, 228 stored |
| 2. Duplicates | Which copy wins when the source lists a thing twice? | The 4 double-listed cameras each kept the copy with coordinates (2 had a second copy with none) |
| 3. Field sanity | Are positions, labels and links plausible? | Everything inside the valley box, labels clean, image links match camera IDs |
| 4. Re-run safety | Does a second run add nothing and keep history? | No duplicates added; the original first-seen dates kept |
| 5. Cross-check against a second source | Does an independent copy agree? | Not run (planned against 511 Idaho's copy of the cameras) |
| 6. Liveness from the source's own metadata | Can we flag dead items without fetching them? | Not run (planned from the GIS timestamp field, without fetching images). It can't work per camera: the layer has one timestamp for the whole layer ([docs/10 §10.5](../docs/10-architecture.md#105-what-the-prototype-taught-us-kept-as-lessons-not-code)). Camera health now comes from reading 511's timestamp bar ([docs/11](../docs/11-camera-validation-layer.md)) |
