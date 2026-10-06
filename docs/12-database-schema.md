# 12. Database schema v1 (draft for review)

**Status:** proposal. Nothing is built until the owner has reviewed the
decisions in [§12.9](#129-decisions-for-the-owner). The database is
PostgreSQL + PostGIS + TimescaleDB ([DECISIONS](DECISIONS.md)).

The schema has to serve four things:

1. **The map and its lenses**
   ([ch. 13](13-visual-design.md)): signals, traffic, transit, roadwork,
   safety, cameras.
2. **Time replay:** any stored day, at game speed.
3. **The camera pipeline**
   ([ch. 11 §11.7](11-camera-validation-layer.md#117-processing-pipeline-collect-everything-measure-every-frame)):
   calibration, zones, measurements, and reprocessing as methods improve.
4. **Analysis:** joins across sources at the intersection, approach and
   corridor level; before/after comparisons.

---

## 12.1 Lessons carried from the prototype

The prototype (`tvt/`) used five generic SQLite tables: fetches,
features, events, observations and vehicle positions, with JSON
properties. That was quick, but:

- **Every query had to dig into JSON**, and nothing was type-checked or
  indexed.
- **Sources disagree about identity.** ACHD's signal points, OSM nodes,
  camera locations and count-location names all describe the same
  intersections differently. We need **our own IDs**, plus a record of how
  each source record links to them.
- **The three kinds of data behave differently:**
  - inventories need a current version and a history;
  - events need lifecycles;
  - time series need volume handling.

## 12.2 Overall shape

Six PostgreSQL schemas (namespaces), so the layers stay obvious:

| Schema | Holds | Written by |
|---|---|---|
| `ops` | Source registry, fetch log, migration history | Ingestors, migration runner |
| `raw` | Every version of every source record, as fetched (jsonb) | Ingestors |
| `core` | Our entities: intersections, approaches, cameras, count stations, transit stops and routes, road segments, and the links from source records to them | Ingest plus matching jobs; calibration by hand |
| `obs` | Time series (TimescaleDB hypertables): bus positions, weather, camera frames and measurements, traffic counts | Ingestors, camera pipeline |
| `evt` | Things with lifecycles: work zones, incidents, message-sign texts | Ingestors |
| `ana` | Derived results: continuous aggregates, per-intersection summaries | Database jobs, analysis |

**Data flow:**

1. An ingestor fetches a source and logs the fetch in `ops.fetch`.
2. It stores each record version in `raw.record`.
3. It updates the typed tables in `core`, `obs` or `evt`.
4. Matching jobs link source records to our entities.
5. The app reads `core`, `obs`, `evt` and `ana`.

**Conventions:**

- **Time:** every time is `timestamptz`, stored in UTC. Daily bins use
  `America/Boise` local time.
- **Geometry:** stored as `geometry(…, 4326)` for the web map. Distances
  and buffers use `ST_Transform` to NAD83 / UTM zone 11N (EPSG:26911),
  which is in meters ([decision 3](#129-decisions-for-the-owner)).
- **IDs:** our IDs are `bigint` identity columns. Source IDs are kept as
  text alongside them.
- **Provenance:** every typed row carries its `source` and the
  `fetch_id` it came from.

## 12.3 `ops`: sources and fetches

```sql
create table ops.source (
  name          text primary key,          -- 'wzdx', 'vrt_positions', 'achd_cameras', ...
  title         text not null,
  url           text not null,
  access        text not null check (access in
                  ('open', 'api_key', 'one_off', 'request')),  -- how we're allowed to get it
  schedule      interval,                  -- null = not scheduled (one-off, request)
  license       text,                      -- e.g. 'ODbL', 'public domain', 'none stated'
  credit        text,                      -- attribution to show
  notes         text,
  check (access not in ('one_off', 'request') or schedule is null)  -- never schedule these
);

create table ops.fetch (
  id            bigint generated always as identity primary key,
  source        text not null references ops.source,
  started_at    timestamptz not null,
  finished_at   timestamptz,
  http_status   int,
  robots        text check (robots in ('allowed', 'no_rules', 'one_off')),
  ok            boolean not null,
  records       int,
  bytes         bigint,
  error         text
);
```

- `access = 'one_off'` sources, such as the ACHD tables, can never get a
  `schedule`. A check constraint enforces the project rule in the
  database itself.
- `ops.schema_migration` records which migration files have run.

## 12.4 `raw`: every version of every record

```sql
create table raw.record (
  source        text not null references ops.source,
  source_id     text not null,             -- the source's own ID
  version_hash  bytea not null,            -- hash of the normalized payload
  payload       jsonb not null,            -- attributes as fetched
  geom          geometry(Geometry, 4326),
  first_seen    timestamptz not null,
  last_seen     timestamptz not null,
  removed_at    timestamptz,               -- gone from a full snapshot
  first_fetch   bigint references ops.fetch,
  primary key (source, source_id, version_hash)
);
```

- **New version:** when a record's content changes, a new row is added.
- **Unchanged:** an unchanged record only moves `last_seen` forward.
- **Removed:** a record missing from a complete snapshot gets
  `removed_at`.

This gives inventory history, such as "camera moved" or "count updated",
for free. It also lets us rebuild every typed table from scratch.

**Not stored here:** high-volume streams. Bus positions every 30 s and
camera images skip `raw`; they go straight to `obs`, and images go to the
video archive.

## 12.5 `core`: our entities

**Intersections and approaches**: the hub most things join to.

```sql
create table core.intersection (
  id            bigint generated always as identity primary key,
  name          text not null,             -- 'Eagle Rd & Fairview Ave'
  geom          geometry(Point, 4326) not null,
  signalized    boolean not null default false,
  operator      text,                      -- 'ACHD', 'ITD'
  city          text
);

create table core.approach (                -- one leg of an intersection
  id            bigint generated always as identity primary key,
  intersection_id bigint not null references core.intersection,
  leg           text not null check (leg in ('N','NE','E','SE','S','SW','W','NW')),
  road_name     text,
  bearing_deg   real,                      -- direction of travel *toward* the intersection
  geom          geometry(LineString, 4326),-- ~300 m back from the stop bar
  unique (intersection_id, leg)
);

create table core.source_link (             -- how source records map to our entities
  source        text not null,
  source_id     text not null,
  entity        text not null check (entity in
                  ('intersection','approach','camera','count_station','road_segment','stop')),
  entity_id     bigint not null,
  method        text not null,             -- 'cluster_60m', 'name_match', 'manual', ...
  distance_m    real,
  confidence    real check (confidence between 0 and 1),
  linked_at     timestamptz not null default now(),
  primary key (source, source_id, entity)
);
```

The **453 intersections** come from clustering ACHD's 2022 signal points
and OSM signal nodes within 60 m (prototype lesson). ACHD turn-movement
names ("Eagle & Fairview") and camera locations link to them through
`source_link`.

**Cameras:**

```sql
create table core.camera (
  id            bigint generated always as identity primary key,
  name          text not null,
  pole_geom     geometry(Point, 4326),     -- ACHD GIS point; refined by calibration
  achd_cam_id   int unique,
  intersection_id bigint references core.intersection
);

create table core.camera_view (            -- one image stream; a PTZ preset is a separate view
  id            bigint generated always as identity primary key,
  camera_id     bigint not null references core.camera,
  image_id      int unique,                -- 511 /map/Cctv/<image_id>
  status        text,                      -- 511 Views[].Status
  direction     text,                      -- 511 Direction (coarse)
  width         int, height int
);

create table core.camera_calibration (     -- versioned; a view can be re-calibrated
  id            bigint generated always as identity primary key,
  view_id       bigint not null references core.camera_view,
  valid         tstzrange not null,        -- when this pose applies
  position      geometry(PointZ, 4326) not null,   -- solved camera position and height
  heading_deg   real not null, tilt_deg real not null, roll_deg real not null default 0,
  vfov_deg      real not null,
  k1            real,                      -- radial distortion, if solved
  point_pairs   jsonb not null,            -- [{pixel:[x,y], ground:[lon,lat,z]}, ...]
  rms_error_px  real not null,
  reference_frame text,                    -- archive path of the frame used
  created_by    text not null              -- 'manual' or a pipeline version
);

create table core.camera_zone (            -- drawn on the map, in world coordinates
  id            bigint generated always as identity primary key,
  approach_id   bigint not null references core.approach,
  lane          smallint,                  -- null = whole approach
  kind          text not null check (kind in ('queue','stop_bar','count_line')),
  geom          geometry(Geometry, 4326) not null
);
```

Zones live in world coordinates. Each frame's calibration projects them
into the image, so a slightly moved camera keeps its zones.

**Counts, network, transit:**

- **`core.count_station`:** ACHD and ITD count locations.
  - Fields: `street`, `location_text` (e.g. "NORTH OF FAIRVIEW AVE"),
    `count_type`, and `geom` once geocoded, with the geocoding `method`.
  - ACHD's table gives text locations only, so geocoding is a matching
    job: the street plus the cross street gives a point near that
    intersection.
- **`core.road_segment`:** the reference road network, with lanes, speed
  limit, functional class and AADT links. Which network is the reference
  is an open question ([decision 5](#129-decisions-for-the-owner)).
- **`core.transit_route`, `core.transit_stop`, `core.transit_shape`:**
  from VRT's GTFS, versioned by feed date.

## 12.6 `obs`: time series (TimescaleDB)

| Table | One row per | Key columns | Chunk | Compress after | Rows per year (est.) |
|---|---|---|---|---|---|
| `obs.vehicle_position` | Bus GPS ping | `ts`, `vehicle_id`, `trip_id`, `route_id`, `geom`, `bearing`, `speed` | 1 day | 7 days | ~30 M |
| `obs.weather` | Station report | `ts`, `station`, `visibility_m`, `temp_c`, `wind_ms`, `precip_mm`, `present_weather` | 30 days | 30 days | small |
| `obs.weather_reading` (built Oct 6, migration 0010) | ITD road-weather station reading (511 API) | `station_id`, `ts`, air, surface and dew-point °F, humidity, wind, precipitation, visibility, surface status and friction, `status` | 7 days | 14 days | ~6.5 M (127 stations, every ~15 min) |
| `obs.camera_frame` | Kept frame | `taken_at` (from the 511 bar), `fetched_at`, `view_id`, `archive_file`, `frame_index`, `quality` flags, `scene_hash` | 1 day | 7 days | ~110 M (all cameras) |
| `obs.camera_measurement` | Frame × zone | `taken_at`, `view_id`, `zone_id`, `pipeline_version`, `vehicles`, `occupancy`, `queue_back_m`, `signal_color` | 1 day | 7 days | ~600 M (all cameras, ~6 zones) |
| `obs.traffic_count` | Count × direction | `counted_on`, `station_id`, `direction`, `count_24h`, `am_peak`, `pm_peak`, `count_type` | (plain table) | — | small |
| `obs.turn_count` | Count × period × approach × movement | `counted_on`, `intersection_id`, `period` (AM/NOON/PM/WKND), `leg`, `movement` (L/T/R/U), `volume` | (plain table) | — | small |
| `obs.atr_volume` | ITD counter × month | `month`, `station_id`, `volume` | (plain table) | — | small |

**Camera notes:**

- **Measurements are wide:** one row per zone per frame, with named
  columns. That's easier to query, and compresses better than a key/value
  layout.
- `pipeline_version` lets reprocessed results sit beside the old ones
  until we switch over.
- **Nothing in these tables identifies vehicles or people,** by design.

**Size:**

- At full camera coverage, measurements dominate: roughly 10–20 GB a year
  after TimescaleDB compression. ⚠️ This is an estimate; we'll measure it
  in step 1 of the camera rollout.
- Everything else is small next to the video archive.

**Continuous aggregates** (pre-computed rollups the app reads directly):

- `ana.queue_15min` per zone: presence share and median and 90th-percentile
  queue length.
- `ana.bus_speed_segment_15min`.
- `ana.region_activity_5min`, which feeds the time bar's sparkline.

## 12.7 `evt`: lifecycles

```sql
create table evt.event (
  id            bigint generated always as identity primary key,
  source        text not null references ops.source,
  source_id     text not null,
  kind          text not null,             -- 'work_zone', 'incident', 'closure', ...
  geom          geometry(Geometry, 4326),  -- WZDx mixes points, lines, multipoints
  declared      tstzrange,                 -- start/end as published
  observed      tstzrange not null,        -- first seen .. last seen (open while active)
  active        boolean not null,
  severity      text,
  description   text,
  attributes    jsonb,
  unique (source, source_id)
);

create table evt.sign_message (            -- message boards: one row per distinct text shown
  sign_id       bigint not null,           -- core sign inventory
  observed      tstzrange not null,
  message       text not null
);
```

Replay simply asks what was active at time *t*:
`observed @> t`.

Built Oct 6, 2026 in `db/migrations/0009_events.sql` for ITD's work zones
(`itd_wzdx`), with two more columns: `content_hash` (of the cleaned row,
so an unchanged poll writes nothing) and `updated_at` (when the row's
content last changed). `declared` holds the published start and end after
the fixes listed in `attributes.fixes`. A work zone that leaves the feed
and later returns keeps its first-seen time.

The 511 API's events, advisories and truck restrictions use the same
table (sources `idaho511_event`, `idaho511_alerts`,
`idaho511_truckrestrictions`; kinds `roadwork`, `closure`, `incident`,
`info`, `advisory`, `truck_restriction`). Their `attributes.ers_id` is the
number WZDx uses for the same event. Migration 0010 built
`evt.sign_message` with `sign_id text` (511's sign ID, in a new
`core.message_sign`) and `messages text[]` (the rotating messages, in
order); blank periods have no row. Road-weather stations are in
`core.weather_station`.

## 12.8 What this schema deliberately leaves out

- **No vehicle or person identities:** no plates, faces or cross-camera
  tracks.
- **No commercial traffic data:** Google, Waze, TomTom, HERE and Mapbox
  results are never stored.
- **Ada County Assessor data:** "do not re-distribute". If we ever load it,
  it goes in a separate `restricted` schema that's excluded from exports
  and published tiles.
- **No basemap tiles:** those are static PMTiles files built by
  `basemap/`.

## 12.9 Decisions for the owner

| # | Question | Options | Recommendation |
|---|---|---|---|
| 1 | Table style | (a) typed tables per kind of thing, plus `raw` versions; (b) the prototype's generic features, events and observations | **(a)**. Clearer queries, constraints and indexes; `raw` keeps everything regardless. |
| 2 | Identity | (a) our own IDs, with `source_link` records; (b) use each source's IDs directly | **(a)**. Sources disagree; links stay inspectable and fixable. |
| 3 | Coordinate system for meters | UTM 11N (EPSG:26911), Idaho Transverse Mercator (EPSG:8826), or geography casts | **UTM 11N**. Standard, well supported, and the valley sits well inside zone 11. ✅ Approved Oct 5. |
| 4 | Turn-count layout | (a) long, one row per movement; (b) wide, 16 columns like ACHD's table | **(a)** with a pivot view for display. Easier sums by leg or movement. |
| 5 | Reference road network | Overture (stable IDs across releases), OSM, ITD's linear-reference system | **Overture** segments with ITD HPMS lanes attached. This can wait for v1.1; v1 needs only intersections and approaches. |
| 6 | Raw payload storage | Database (`raw.record`, jsonb) for inventories and events; none for high-volume streams | As proposed. ✅ Approved Oct 5: high-volume feeds (e.g. GTFS-realtime) are archived as files on disk instead. |
| 7 | Retention | Keep everything (per the camera decision); compress after 7 days | As proposed. ✅ Approved Oct 5. |

## 12.10 Migrations and testing

- **Migrations:** plain SQL files in `db/migrations/NNNN_name.sql`,
  applied in order by a small Python runner that records them in
  `ops.schema_migration`. No ORM, so the schema stays readable.
- **Testing:**
  - The PostGIS parts can be tested in the cloud sandbox now (PostgreSQL
    16 + PostGIS 3 install from apt).
  - TimescaleDB needs `packagecloud.io` on the network allowlist, or
    testing in the server VM.
- **Order of work after review:**
  1. `ops` and `raw`.
  2. `core` intersections and cameras.
  3. `evt` (work zones), which feeds the first ingestor and the Roadwork
     lens.
  4. `obs` tables as their ingestors arrive.
