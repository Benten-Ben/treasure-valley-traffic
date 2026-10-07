# ingest: data collectors

Python ingestors that write to the database (see [db/](../db)). This is a
clean rebuild that keeps the prototype's lessons, not its code (the
prototype is [`tvt/`](../tvt)).

**Core and plugins** ([docs/15](../docs/15-plugins.md)). This folder is the
core every subject shares: the CLI (`__main__.py`), polite HTTP with the
robots.txt parser (`http.py`), sources, fetch logs and record versions
(`db.py`), event lifecycles (`events.py`), the shared readers for ArcGIS
layers (`arcgis.py`) and COMPASS's layers (`compass_layer.py`), the UTM
projection (`utm.py`), and the plugin loader (`manifest.py` reads and orders
the manifests; `sources/__init__.py` builds `SOURCES`, `STREAMS` and the
plugin commands from them). Each subject's sources live in its plugin,
`plugins/<name>/`, with a `plugin.json` (sources, licenses, whether we may
republish, tables, commands), a README, its migrations and its tests. Source
names didn't change, so `ops.source` and `ops.fetch` carry on:

| Plugin | Sources (in run order) | Commands |
|---|---|---|
| [cameras](../plugins/cameras) | `achd_cameras`, `idaho511_views_oneoff`; stream `idaho511_frames` | `rollup` |
| [transit](../plugins/transit) | `vrt_gtfs`; stream `vrt_realtime` | `match-routes`, `transit-progress`, `transit-ribbons`, `route-colors` |
| [roads](../plugins/roads) | `achd_roads`, `itd_hpms`, `achd_msm`, `compass_centerline`; by hand `osm_valley` | `osm-load`, `segment-match` |
| [conditions](../plugins/conditions) | streams `itd_wzdx`, `idaho511_api` | |
| [intersections](../plugins/intersections) | `fra_crossings`, `achd_signal_points`, `compass_signals`, `compass_regional_signals`, `intersections` | `match-intersections` |
| [safety](../plugins/safety) | `compass_crashes` | |
| [flow](../plugins/flow) | `compass_counts`, `compass_congestion` | |
| [development](../plugins/development) | `compass_growth`, `compass_plats` | |
| [hazards](../plugins/hazards) | `idl_fire_restrictions`, `nifc_wfigs_incidents`, `nifc_wfigs_perimeters`, `nasa_firms`, `nws_wwa`, `usgs_quakes` | |
| [air](../plugins/air) | `noaa_hms_smoke` | |
| [water](../plugins/water) | `nwps_gauges`, `nrcs_snotel`, `boise_ecoli`, `boise_river_hazards`, `usdm_drought` | |
| [trails](../plugins/trails) | `r2r_trails`, `boise_greenbelt_closures` | |
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

**Status:** camera sources (for the calibrator), Valley Regional Transit (buses), ITD's work zones and the 511 Idaho API.

| Source | Access | Schedule | Writes |
|---|---|---|---|
| `achd_cameras` | open (ACHD GIS, no robots.txt) | daily | `raw.record`, `core.camera` (228), `core.source_link` |
| `idaho511_views_oneoff` | one-off (dated private file `511-camera-views-2026-10-05.csv`, read from `TVT_PRIVATE_DATA`) | never | `core.camera_view` (210 linked within 200 m) |
| `achd_roads` | open (ACHD GIS, no robots.txt) | weekly | `raw.record`, `core.road_segment` (38,727 Ada County segments: posted speed, class, one-way, level, community), `core.source_link`; a run that changes the segments rematches every lane source and OpenStreetMap in `core.segment_match` |
| `itd_hpms` | open (ITD GIS, no robots.txt; no license stated, credit ITD) | monthly | `raw.record` (one source per layer, `itd_hpms_<kind>`, keyed `<EventID>@<RouteID>:<FromMeasure>`, plus `itd_hpms_road_names`), `core.hpms_section` (33,770 pieces touching the valley box: through lanes 19,507, turn lanes 637, lane width 558, median 738, shoulders 634, access control 5,376, peak lanes 1,384, facility type 4,936), `core.segment_match` |
| `achd_msm` | open (ACHD GIS, no robots.txt; no license stated) | monthly | `raw.record` (by GlobalID; the bulk-stamped edit dates left out), `core.msm_arterial` (1,049 Master Street Map arterials; existing lanes on 896), `core.segment_match` (`buffer10_name`; `buffer10_bearing20` where a state-route name faces a street name) |
| `compass_centerline` | open (COMPASS on swidrdc.org, no robots.txt rules; disclaimer only, credit COMPASS) | monthly | `raw.record` (by globalid), `core.compass_segment` (62,213 pieces in Ada and Canyon on 26,911 `pm_id`s; lanes on 61,404), `core.segment_match` (Canyon's pieces stay unmatched: no ACHD segments there) |
| `vrt_gtfs` | open (VRT, CC BY 3.0) | daily | `core.transit_route`/`_stop`/`_shape`/`_trip`; each zip archived in `$TVT_ARCHIVE/vrt-gtfs/`. Picks each route's map color (routes sharing streets differ). |
| `vrt_realtime` | open (VRT, CC BY 3.0) | stream, every 30 s | each changed feed archived in `$TVT_ARCHIVE/vrt-gtfs-rt/<date>/`; bus positions in `obs.vehicle_position` |
| `itd_wzdx` | open (ITD's WZDx feed on 511 Idaho; may be republished, crediting ITD) | stream, every 5 min | each changed snapshot archived in `$TVT_ARCHIVE/wzdx/<date>/`; every work zone's versions in `raw.record`; cleaned rows in `evt.event` (fixes listed per row; [docs/08 §8.8](../docs/08-data-inventory.md#88-itds-work-zone-feed-checked-against-the-wzdx-spec-oct-6-2026)) |
| `idaho511_api` | API key (`IDAHO511_API_KEY`; 511 Idaho developer terms; not republished) | stream, per endpoint: events and signs 2 min, weather and advisories 5, truck restrictions and winter roads 15, cameras hourly, the rest daily; at most 8 calls a minute | changed responses archived in `$TVT_ARCHIVE/idaho511/<endpoint>/<date>/`; versions in `raw.record` (one source per endpoint, `idaho511_<endpoint>`); `evt.event` (events, advisories, truck restrictions), `core.message_sign` + `evt.sign_message`, `core.weather_station` + `obs.weather_reading`; the regional capture list in `$TVT_ARCHIVE/lists/` |
| `fra_crossings` | open (FRA on data.transportation.gov, public domain; robots allows /resource/, Crawl-delay 1) | weekly | `raw.record` (by crossing number, without Socrata's computed-region columns), `core.rail_crossing` (433 in Ada and Canyon; 197 closed, kept and flagged), `core.source_link` |
| `achd_signal_points` | open (ACHD's 2022 layers on ArcGIS Online, frozen Aug 2, 2022; no robots rules) | monthly | `raw.record` (`<layer>:<OBJECTID>`), `core.signal_device` (2,469 signal poles, 182 pedestrian signals, 33 school flashers, 68 fire signals) |
| `compass_signals` | open (COMPASS on ArcGIS Online; no license, "meant only for reference": internal until COMPASS answers) | weekly | `raw.record` (`synchro:<id>`, else `loc:<operator>:<location>`), `core.signal_device` (585 signalized intersections with operator, coordination and per-approach lanes, phasing and modelled volumes) |
| `compass_regional_signals` | open (COMPASS on swidrdc.org; internal until COMPASS answers) | weekly | `raw.record`, `core.signal_device` (1,076 devices: 586 traffic signals, the rest pedestrian signals, flashers and fire signals) |
| `intersections` | derived (fetches nothing; by hand: `python3 -m ingest match-intersections [--dry-run]`) | daily | `core.intersection` (633 after the Oct 7 OpenStreetMap load: 585 active, 43 candidates, 5 retired by review in `plugins/intersections/ingest/intersection_reviews.json`; 42 of the candidates are new, from OSM signal nodes with no COMPASS match, and need review. Before the load it was 591 with 1 candidate), `core.approach` (2,276), `core.signal_device.intersection_id`, camera and OSM links in `core.source_link` (199 cameras, 3 of them to interchanges; 711 OSM nodes), `core.rail_crossing.intersection_id` (nearest active signal within 300 m; 56 crossings). Since OSM nodes now confirm and create intersections, `core.intersection` is an ODbL derivative database: credit "© OpenStreetMap contributors", and anything published from it stays ODbL ([docs/12 §12.5](../docs/12-database-schema.md#125-core-our-entities)) |
| `osm_valley` | open (OpenStreetMap, ODbL; credit "© OpenStreetMap contributors"); by hand only: Geofabrik's robots.txt disallows scripted downloads (Oct 6), so the owner downloads the Idaho extract in a browser into `$TVT_ARCHIVE/osm/inbox/`. Not a scheduled source; no download code | by hand, weekly (`python3 -m ingest osm-load --inbox`) | `raw.record` (`w<id>`/`n<id>`: tags and a geometry hash), `core.osm_way` (major ways and every way with lanes), `core.osm_lane`, `core.osm_node` (intersection signals, crossing signals, level crossings), `core.segment_match` (ACHD segments, by the shared matcher: `buffer15_bearing20`, and `way_in_buffer15_bearing20` for turn-bay ways); extracts archived in `$TVT_ARCHIVE/osm/` (last two) |
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
TVT_COMPASS_MAX_PAGES=3 python3 -m ingest run compass_crashes          # dev only: at most 3 pages per layer, logged as failed
TVT_COMPASS_FORCE=1 python3 -m ingest run compass_growth               # skip the freshness and change checks
python3 -m ingest segment-match [itd_hpms achd_msm compass_centerline osm_valley]   # rematch to ACHD segments by hand
python3 -m ingest -h                                                    # every command, the plugins' included
python3 -m unittest discover -s ingest/tests -t .                       # core
python3 -m unittest discover -s plugins -t .                            # the plugins
```

Each run logs to `ops.fetch`. Records are versioned in `raw.record`, so a
re-run that finds nothing new adds nothing.

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
