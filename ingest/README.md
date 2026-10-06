# ingest: data collectors

Python ingestors that write to the database (see [db/](../db)). This is a
clean rebuild that keeps the prototype's lessons, not its code (the
prototype is [`tvt/`](../tvt)).

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
| `intersections` | derived (fetches nothing; by hand: `python3 -m ingest match-intersections [--dry-run]`) | daily | `core.intersection` (591: 585 active, 1 candidate, 5 retired by review in `ingest/intersection_reviews.json`), `core.approach`, `core.signal_device.intersection_id`, camera and OSM links in `core.source_link` (199 cameras), `core.rail_crossing.intersection_id` (nearest active signal within 300 m) |
| `osm_valley` | open (OpenStreetMap, ODbL; credit "© OpenStreetMap contributors"); by hand only: Geofabrik's robots.txt disallows scripted downloads (Oct 6), so the owner downloads the Idaho extract in a browser into `$TVT_ARCHIVE/osm/inbox/`. Not a scheduled source; no download code | by hand, weekly (`python3 -m ingest.osm_load --inbox`) | `raw.record` (`w<id>`/`n<id>`: tags and a geometry hash), `core.osm_way` (major ways and every way with lanes), `core.osm_lane`, `core.osm_node` (intersection signals, crossing signals, level crossings), `core.segment_match` (ACHD segments, by the shared matcher: `buffer15_bearing20`, and `way_in_buffer15_bearing20` for turn-bay ways); extracts archived in `$TVT_ARCHIVE/osm/` (last two) |

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
TVT_ARCHIVE=data/archive python3 -m ingest.osm_load --inbox             # OSM extract downloaded by hand (needs osmium-tool)
python3 -m ingest.segment_match [itd_hpms achd_msm compass_centerline osm_valley]   # rematch to ACHD segments by hand
python3 -m unittest discover -s ingest/tests -t .
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
