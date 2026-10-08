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

The prototype got **453 intersections** by clustering ACHD's 2022 signal
points and OSM signal nodes within 60 m. That radius over-merges, so the
build below seeds from COMPASS instead and clusters leftovers at 45 m.
ACHD's 2022 `Traffic_Signals` layer (`services2.arcgis.com/9rTo9NcUHIKASKwi`,
layer 15; frozen Aug 2, 2022, "Official Bike Map 2022") holds 2,469 signal
**poles**, not intersections, with only `OBJECTID` and `Purpose` (Eagle &
Fairview has 12). Grouping the poles at different radii:

| Radius | Groups | Note |
|---|---|---|
| 30 m | 799 | Far more groups than intersections |
| 45 m | 464 | Matches COMPASS's 464 ACHD signals |
| 60 m | 453 | The prototype's figure; the widest group spans 209 m, merging neighbours |
| 80 m | 418 | |

Its companion layers are `Pedestrian_Signals` (layer 13; 182: 96 hybrid
beacons, 76 RRFBs, 4 conventional signals, 3 warning beacons and 3 with a
blank purpose, which the build counts as conventional, 7 in all),
`School_Flasher_Signal` (layer 40; 33) and `Fire_Signals` (layer 14; 68).
Nothing newer is public on `gis.achdidaho.org`; ten of its folders need a
token. ACHD turn-movement names ("Eagle & Fairview") and camera locations
link to intersections through `source_link`.

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

Since Oct 6, `core.camera.provider` (`ACHD`, `ITD RWIS` or `ODOT`; the
cameras plugin's migration `cameras/0001`, the number 0008 that ch. 14
reserved) lets ITD's road-weather stations and Oregon DOT's cameras live
beside ACHD's traffic cameras: one `core.camera` per station and one
`core.camera_view` per direction, labeled in `direction`. The Cameras layer
shows `ACHD` only; the Road weather layer shows the rest
([ch. 14 §14.6](14-ui-v2.md#road-weather)).

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
  - **`core.transit_route.color_pinned`** (migration 0006, owner OK Oct 6,
    [ch. 14](14-ui-v2.md) Q4): locks a route's color, so the palette
    assignment never changes it.
- **`core.transit_ribbon`** (migration 0006, built Oct 6): routes that
  share a street, for drawing them side by side
  ([ch. 14 §14.4](14-ui-v2.md#side-by-side-ribbons)). One row per atomic
  piece of shared centreline (`segment_id`, `geom`), with the routes on it
  left to right looking along `geom` (`routes text[]`; dormant routes take
  no slot), `length_m`, a `hub` flag (within 300 m of a stop served by 6 or
  more routes) and the `build` hash. `ingest/transit_ribbons.py` builds it
  from VRT's own shapes, and VRT's daily GTFS run rebuilds it only when the
  shapes, the dormant set or the parameters change, inside a savepoint, so a
  failed build keeps the previous ribbons. Until a first build exists,
  `/api/transit/network` serves plain route shapes.

**Intersections** are built, not fetched: `python3 -m ingest match-intersections`
(and the daily `intersections` source) makes one `core.intersection` per
COMPASS signal, snapped to the junction of its named streets in ACHD's
centerlines. ACHD's 2022 poles (60 m), COMPASS's Regional_Signals (40 m) and
OpenStreetMap's signal nodes (60 m) confirm it, and leftovers cluster at 45 m
into candidates. Confidence follows how many sources agree (three 1.0, two
0.85, COMPASS alone 0.7); below 0.6 a row is a candidate. Reviewed decisions
(`plugins/intersections/ingest/intersection_reviews.json`) retire or hold candidates until new
evidence reopens them. IDs carry over by Synchro ID, then by the nearest row
within 30 m; rows are retired, never deleted. COMPASS's per-approach fields
fill `core.approach`. Cameras link within 80 m when they share a street,
freeway cameras to their interchange's signal within 150 m, and rail
crossings to the nearest active signal within 300 m, with the distance. Once
OpenStreetMap nodes confirm or create intersections, `core.intersection`
holds positions, evidence and some names derived from OpenStreetMap, so it is
an ODbL derivative database: credit "© OpenStreetMap contributors", and
anything published from it stays ODbL. Until COMPASS answers, it is also
internal only.

Scoring rules the builder added, accepted Oct 6 ([DECISIONS](DECISIONS.md)):

- Regional_Signals alone scores 0.5. ACHD's 2022 poles plus Regional_Signals
  with nothing current scores 0.55, which catches removed signals such as
  Chinden & Hwy 16.
- A named junction found 40–150 m from the point costs 0.1.
- At COMPASS's single-point urban interchanges, poles attach within 120 m;
  otherwise each SPUI showed up as duplicate candidates.
- A junction counts only where the centerlines share a vertex, so bridges
  don't.
- State routes match their local names (SH 44 = State St, SH 69 = Meridian
  Rd, US 20/26 = Chinden), and single-letter misspellings are tolerated.
- An ingest or build that would drop below half of what's held is refused.

Data conventions: Regional_Signals devices are stored by their own device
type, and only traffic signals feed the build. That layer adds essentially
no signals (584 of its 586 traffic signals lie within 10 m of a COMPASS
point) but is newer than ACHD's 2022 layer for pedestrian devices ([ch. 8
§8.9](08-data-inventory.md#89-second-source-review-oct-6-2026)). COMPASS's
Synchro IDs 215, 256 and 428 each appear on two points (two of the pairs
are kilometres apart), so those records key on Synchro ID plus location.
COMPASS's "northbound approach" is the south leg when it fills
`core.approach`. Rail crossings link within 300 m, not 200 m, because no
open Union Pacific crossing is within 200 m of a signal: the nearest is
Karcher Rd, Nampa, at 238 m, and Caldwell's are 279–307 m from the Blaine
St signals. The 14 open at-grade crossings within 200 m are all Boise Valley
Railroad, from Cole Rd at 37 m (list in [ch. 8
§8.9](08-data-inventory.md#89-second-source-review-oct-6-2026)).

**The first run** (Oct 6, into a trial database, before OpenStreetMap)
made 8 requests (FRA 1, ACHD 5, COMPASS 1, `swidrdc.org` 1); responses were
cached, so reruns made none.

- **591 intersections:** 585 active, 6 candidates. A rerun gave 0 new and 0
  retired, so the IDs hold.
- **Snapping:** 442 of the 465 Ada points snapped to their named junction.
  Confidence 0.85 for 442, 0.70 for 142 (mostly Canyon, which has no ACHD
  poles).
- **Poles:** 2,429 attached, 12 unattached. 23 active Ada signals have no
  2022 pole, mostly newer ones such as Hwy 16 & Beacon Light and Ustick &
  McDermott.
- **Examples:** Eagle & Fairview is active at 0.85, Synchro 213, 12 poles,
  camera linked at 35 m. Chinden & Cloverdale is active at 0.85, 6 poles,
  camera at 23 m.
- **Cameras:** 196 of 228 linked before the freeway rule. The 32 unlinked
  were freeway cameras (the I-84 SPUI cameras are 120–133 m from their
  signal), 3 at roundabouts and a few with no signal nearby. The freeway
  rule brought it to 199 ([ingest README](../ingest/README.md)).
- **The six candidates:** Chinden & Hwy 16 at 0.55 (2022 poles at the old
  at-grade junction; COMPASS's two points are 130 m away); Capitol & Island
  (4 poles plus a hybrid beacon); Franklin & Wayfinder (8 poles, not in
  COMPASS); Lake Hazel & Maple Grove and Victory & Locust Grove (poles plus
  4 RRFBs each); and one Regional point with a blank type near 43.6478,
  −116.4864. Their outcomes are in [DECISIONS](DECISIONS.md), Oct 6.

After the Oct 7 OpenStreetMap load the table held 633 rows, with 43
candidates (counts in the [ingest README](../ingest/README.md)).

**OpenStreetMap (`osm_valley`, Oct 6, 2026).** Geofabrik's robots.txt, read
Oct 6, 2026, disallows its extracts for every robot (`Disallow: *.osm.pbf`,
`*.md5`, `*updates*` and more). So the owner downloads the Idaho extract by
hand each week and loads it with `python3 -m ingest osm-load --inbox`; there
is no download code and no schedule, and the owner has asked Geofabrik for
one scripted download a week. osmium cuts the extract to the valley box. It
keeps every major way, every other road tagged with lanes or turn lanes, and
the intersection-signal, crossing-signal and level-crossing nodes;
fire-station, ramp-meter, blinker and level-crossing signals are skipped, and
a signal also tagged as a crossing counts as an intersection signal only at a
junction. Lanes are stored one row per lane per direction, numbered from the
left in the direction of travel. Ways match ACHD's centerlines when, with
bearings within 20°, at least 60% of a segment lies within 15 m of the way
(both carriageways of a divided road match), or at least 60% of a way of
20 m or more lies within 15 m of a segment (turn-bay ways). OpenStreetMap
stays in its own tables (ODbL, "© OpenStreetMap contributors"); only the
road network's major and laned ways are kept, so residential street names
come from ACHD, not OpenStreetMap.

The builder's tagging choices, which the lead let stand (Oct 6):

- **Signals:** `crossing:signals=yes` (the newer tagging) counts alongside
  `crossing=traffic_signals`. A `highway=traffic_signals` node tagged
  `traffic_signals=crossing` is a crossing signal. One tagged
  `crossing=traffic_signals` was at first kept as an intersection signal,
  with its tags; the junction rule added later that day replaced that.
- **Junction rule:** a node is at a junction when three or more road ways
  pass through it, or road ways with different names (from osmium's
  way-node lists). Footways don't count, and neither does a road split at
  the signal (two ways, one name). If it can't be told, the node counts as
  a crossing signal.
- **Skipped kinds** (`traffic_signals=emergency`, `ramp_meter`, `blinker`,
  `level_crossing`) are counted in the load's statistics, not stored.
- **Ways:** the keep filter drops proposed, construction, abandoned and
  similar ways, and `area=yes`. `oneway` stores the effective value (yes is
  implied on motorways and roundabouts); `bridge` is false when absent.
- **Lanes:** a two-way road with an even lane count and no direction split
  is split evenly. An odd count with no split (e.g. `lanes=5` alone) gets
  no lane rows. When the turn-lane slots disagree with the lane count, it's
  logged and the lanes get no turns. Odd values such as `2;3` or `2.5`
  become null, with the raw tag kept.
- **History:** the `raw.record` payload is `{tags, geom_hash}`, without
  version or timestamp, so an OSM version bump that changes neither adds no
  row.
- **Matching:** confidence is share × cos(bearing difference). The 15 m
  buffer has round ends, so a way "covers" up to 13.7 m past its own ends (a
  test turn bay of 25% shows share 0.28). When both rules pass, the
  segment rule wins. In the Eagle Rd sample, turn-bay ways were 16 of 43
  approaches.

**Guards.** A load with fewer than half the active ways (when 1,000 or more
are active) won't retire the rest without `--allow-shrink`. An extract with
the same MD5 as the last load is skipped unless `--force`. The last two
extracts are kept, and pruning never removes the file just loaded.

**Sizes and timings** (the builder's figures; the image size is an
estimate):

| What | Figure |
|---|---|
| Matching at server scale | About 47 s with the turn-bay rule, 21 s without |
| A whole load | 1.5–2 min |
| `osmium-tool` in the ingest image | About 4 MB more |
| Disk | About 250 MB of archived extracts, plus about 150 MB temporary |
| `raw.record` growth | Roughly 150–500 new versions (60–200 KB) a week |

**What OpenStreetMap holds in the valley box** (counted through the
`overpass.private.coffee` mirror, data of May 31, 2026 ⚠️):

| Feature | Count |
|---|---|
| `highway=traffic_signals` nodes | 752 |
| `crossing=traffic_signals` nodes | 1,709 |
| `railway=level_crossing` nodes | 342 |
| Major ways (motorway to tertiary) | 7,823: `lanes` on 5,632 (72%), `lanes:forward`/`backward` on 1,177 (15%), any `turn:lanes` on 1,460 (19%), `width` on 6 |
| Residential, unclassified and service ways | 79,611: `lanes` on 5,176 (6.5%) |

**COMPASS (built Oct 6, 2026, migration 0012).** Crashes are `obs.crash`,
one row per ITD serial number. `crashed_at` is the reported local time, so
the key is serial number plus time; with TimescaleDB it's a hypertable in
1-year chunks. The people in them are `restricted.crash_unit`: the
`restricted` schema of §12.8 (foreseen for Assessor data) now also holds
these crash people. Only coded fields are kept, and nothing is copied to
`raw.record`:

- **Age** only in bands: 0–15, 16–20, 21–24, then 10-year bands up to 75 and
  over.
- **Residence** reduced to Idaho resident or not.
- **Citations:** coded types only; case and ticket numbers are dropped.
- **Sex** isn't collected: the lead dropped it as not needed for
  road-network work.

`obs.crash.unit_types` is the one crash-level aggregate taken
from it, and it may be published. Counts are `obs.traffic_count`, shaped as
in §12.6 but keyed by source, the source's location key and `counted_on`;
it adds `period` (what `counted_on` stands for), a nullable `direction`
('both' or 'one_direction') and `count_type`. Growth is `core.taz` with
`obs.taz_demographic` (zone, year, measure, kind: census, estimate or
forecast), `obs.building_permit` and `core.plat`. The high-injury network is
`core.hin_junction` and `core.hin_segment`. COMPASS's building permits do
include 2025 (9,150 permits that year), although the layer's statistics
queries stop at 2023
([ch. 8 §8.9](08-data-inventory.md#89-second-source-review-oct-6-2026)).
The congestion measures and commute travel times are internal until COMPASS
answers; their segment numbers also look like INRIX's network ⚠️. `ops.layer_signature` records each layer's
count and highest object ID at its last full read, so monthly runs skip
layers that haven't changed. That check matters because a full crash pull
downloads about 350 MB for data that changes about once a year, and takes
about 15–20 minutes at our pace; a redeploy that cuts it off resumes after
the 6-hour back-off.

**Lane inventories and segment matching (Oct 6, 2026; 0011, re-keyed in
0016).** Three sources keep their own lane values, each in its own table:
`core.hpms_section` (ITD HPMS: one row per layer and piece, keyed
`<EventID>@<RouteID>:<FromMeasure>`, since one EventID can cover several
pieces of a route), `core.msm_arterial` (ACHD's Master Street Map arterials:
existing, funded and planned lanes, counting the whole cross-section) and
`core.compass_segment` (COMPASS's RegionalCenterline, Ada and Canyon, keyed
by globalid; `pm_id` names a travel-model link of several pieces and stays as
the join to COMPASS's other data). `core.segment_match` records which ACHD
segments each of their lines, and each OpenStreetMap way, lies along, by one
shared matcher (`plugins/roads/ingest/segment_match.py`, in UTM 11N): at least 60% of the
segment within the line's buffer (15 m; 10 m with a street-name check for
the Master Street Map), or else at least 60% of a line of 20 m or more within
the segment's buffer (methods `way_in_…`), with bearings within 20°. `share`
and `overlap_m` always measure the ACHD segment. One line can match many
segments, and one segment several lines (both carriageways of a divided
road). A source's matches are rewritten in one transaction after each run
that changes it, and every source's after `achd_roads` changes ACHD's
segments; by hand, `python3 -m ingest segment-match`. Canyon County has no
ACHD segments, so its lines stay unmatched and keep their own geometry.

Guards added in the same Oct 7 fix as migration 0018:

- **Snapshots:** HPMS (each layer, and the road names), the Master Street
  Map and COMPASS refuse an empty snapshot, or one under half the active
  rows, before writing anything (the same check as the signal sources).
- **Matching** runs inside the fetch's transaction, so a failed match rolls
  the store back too. Rematching every source logs and rolls back a
  matcher that fails and lets the rest run.
- **ArcGIS paging:** a cut-off answer shrinks the batch to the server's page
  size (a synthetic 12,150-row case takes 13 range requests). A by-ID
  request that returns nothing fails the fetch. Truncated reads and
  unparseable JSON are retried. COMPASS is read 1,000 IDs a request.

**`core.segment_lanes` (0017, corrected in 0018)** applies the lanes rule of
[ch. 9 §9.3](09-base-map-data.md#93-streets-network-and-lanes), one row per
active ACHD segment: `lanes_total` (through lanes both ways),
`lanes_forward`/`lanes_backward` (along and against the segment's drawn
direction, when known), `centre_turn_lane`, the winning `source`,
`split_from`/`split_estimated` (where the direction split came from),
`confidence` (the winning match's), every source's own reading in
`candidates` (jsonb), `conflict` when the sources trusted for the road class
differ by more than one lane, and `flags` (`single_lane`,
`carriageway_split`, `ad_conflict`). State routes take HPMS first: an A route
carrying one direction pairs with its D route as a divided road (ITD codes a
divided highway's inventory direction as a two-way roadway, so facility type
can't tell divided from undivided), and on a one-way ACHD segment only the
carriageway running its way counts. ACHD arterials take the Master Street Map
(a whole cross-section: an odd count from 3 is read as a centre turn lane ⚠️;
on one carriageway of a divided road, half of it), with OpenStreetMap's split
when its total agrees. Collectors and local streets take OpenStreetMap, else
an assumed 1+1. One lane on a two-way road is one lane, flagged, at half
confidence. COMPASS's 2 is unknown unless a trusted source agrees. Each
source's best match (by share) is its own view (`core.segment_lanes_hpms`,
`_msm`, `_compass`, `_osm`). It is a plain view: reading all 38,727 rows took
about 4 s, and about 5 s after 0018's fixes. Since it uses OpenStreetMap, it
is an ODbL derivative database if published.

What 0018 fixed (found in review, Oct 7; 0017 was already merged, and the
runner refuses edited migrations):

- **Divided highways.** The evidence for the facility-type rule above:
  I-84's A route carries 2–6 lanes one way and 0 the other, coded facility
  type 2 (two-way), for 281 miles. 0017 let facility type override
  the A/D reading, so it read divided state routes as undivided and halved
  them: 147 segments (51 km) under "two-way" had `ad_conflict` set. Now only
  a one-way roadway or a ramp means "no other direction", and an A route
  with lanes one way and no D route alongside leaves the other direction
  unknown. Three readings still carry `ad_conflict`: one-way facilities
  whose A row claims both directions.
- **Concurrent routes.** Westbound I-84 read 1 lane for 28.8 km: US-26 runs
  with it, its D route is a 1-lane placeholder, and it tied with I-84's own
  D route on share. Ties now go to the interstate, then the US route, then
  the state route. Westbound I-84 now reads 2–5 lanes; 3.1 km of interstate
  (I-184 branches and ramps) still read 1.
- **Carriageway split.** 76 one-way segments that are one carriageway of a
  divided road get half the Master Street Map count, flagged
  `carriageway_split`. "One carriageway" means the Master Street Map line
  has one-way segments running both ways along it; a one-way street keeps
  all its lanes.

**Which source won, after the first OpenStreetMap load** (Oct 7; Ada only,
since Canyon has no ACHD segments):

| Winning source | Segments |
|---|---|
| OpenStreetMap | 7,636 |
| Master Street Map | 3,776 |
| ITD HPMS | 1,116 |
| COMPASS centerline | 206 |
| Assumed 1+1 | 25,699 (33,023 before OpenStreetMap) |

Conflict flags rose from 207 to 651: OpenStreetMap adds a second opinion
where HPMS or the Master Street Map had already decided.

## 12.6 `obs`: time series (TimescaleDB)

| Table | One row per | Key columns | Chunk | Compress after | Rows per year (est.) |
|---|---|---|---|---|---|
| `obs.vehicle_position` | Bus GPS ping | `ts`, `vehicle_id`, `trip_id`, `route_id`, `geom`, `bearing`, `speed` | 1 day | 7 days | ~30 M |
| `obs.vehicle_progress` (built Oct 6, migration 0007; owner OK, [ch. 14](14-ui-v2.md) Q4) | Where a bus fix lies along its route, for playback ([ch. 14 §14.4](14-ui-v2.md#playback)) | `vehicle_id`, `ts` (the fix's key), `shape_id`, `m` and `off_m` (metres along and off the shape), `route_id` and `route_source` (feed, trip, matched or path), `step` to the next fix (along, still, straight or gap) and `step_speed_ms`, `method`, `seen_at` (about its arrival), `backfill` | 1 day | 7 days | ~33 M (about 90k a day) |
| `obs.weather` | Station report | `ts`, `station`, `visibility_m`, `temp_c`, `wind_ms`, `precip_mm`, `present_weather` | 30 days | 30 days | small |
| `obs.weather_reading` (built Oct 6, migration 0010) | ITD road-weather station reading (511 API) | `station_id`, `ts`, air, surface and dew-point °F, humidity, wind, precipitation, visibility, surface status and friction, `status` | 7 days | 14 days | ~4.4 M (127 stations, every 15 min; measured Oct 6) |
| `obs.camera_frame` | Kept frame | `taken_at` (from the 511 bar), `fetched_at`, `view_id`, `archive_file`, `frame_index`, `quality` flags, `scene_hash` | 1 day | 7 days | ~110 M (all cameras) |
| `obs.camera_measurement` | Frame × zone | `taken_at`, `view_id`, `zone_id`, `pipeline_version`, `vehicles`, `occupancy`, `queue_back_m`, `signal_color` | 1 day | 7 days | ~600 M (all cameras, ~6 zones) |
| `obs.traffic_count` | Count × direction | `counted_on`, `station_id`, `direction`, `count_24h`, `am_peak`, `pm_peak`, `count_type` | (plain table) | — | small |
| `obs.turn_count` | Count × period × approach × movement | `counted_on`, `intersection_id`, `period` (AM/NOON/PM/WKND), `leg`, `movement` (L/T/R/U), `volume` | (plain table) | — | small |
| `obs.atr_volume` | ITD counter × month | `month`, `station_id`, `volume` | (plain table) | — | small |

**Road-weather volume, measured.** Before any data arrived we estimated
about 18,000 readings a day (about 6.5 M a year). Measured on the server on
Oct 6: all 127 stations report every 15 minutes (two full batches, at 16:15
and 16:30 UTC), so about 12,000 readings a day statewide and about 4.4 M a
year. The same check of the 511 ingest found 46 API calls in its first ~25
minutes, none failed; 180 events marked as seen on every poll; 15 signs
showing messages; and the API key absent from every log and error record.

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
- **Restricted data:** a separate `restricted` schema, excluded from exports
  and published tiles; only aggregates leave it. It holds the people in
  COMPASS's crash records (`restricted.crash_unit`, coded and coarsened,
  since migration 0012) and, if we ever load it, Ada County Assessor data
  ("do not re-distribute"). It's policy, not a permission boundary yet: the
  app and ingestors connect as the same role.
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
  `ops.schema_migration`. No ORM, so the schema stays readable. The runner
  stores each file's checksum and refuses one that changed after it was
  applied, so a fix goes in a new migration (0018 corrects 0017).
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
