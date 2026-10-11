# roads

The road network as data ([docs/15 §15.4](../../docs/15-plugins.md#154-the-plugins-we-already-have)):
ACHD's road segments (the Streets layer's data), the lane inventories,
ACHD's bike network with its curb-to-curb widths, and OpenStreetMap's ways,
lanes and signal nodes, all matched to ACHD's segments by core's line
matcher ([ingest/linematch.py](../../ingest/linematch.py)). The base map's
streets (for drawing) stay in core (`basemap/`).

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `achd_roads` | weekly | none stated | Ada County Highway District | internal |
| `itd_hpms` | monthly | none stated | Idaho Transportation Department | internal |
| `achd_msm` | monthly | none stated | Ada County Highway District | internal |
| `compass_centerline` | monthly | none stated (disclaimer only) | COMPASS and its member agencies | yes (open-data hub) |
| `achd_bike_network` | monthly (skipped when unchanged) | none stated (disclaimer: not for planning determinations) | Ada County Highway District | internal |
| `osm_valley` | by hand | ODbL | © OpenStreetMap contributors | yes, as ODbL |
| `osm_street` | by hand | ODbL | © OpenStreetMap contributors | yes, as ODbL |
| `osm_paving` | by hand | ODbL | © OpenStreetMap contributors | yes, as ODbL |
| `cdl_developed` | by hand, after a new CDL year | public domain | USDA NASS Cropland Data Layer | yes |

"Internal" for ACHD's and ITD's layers means no license is stated and the
owner hasn't decided on republishing; they're shown only on the owner's own
map. Details of each source: [ingest/README.md](../../ingest/README.md).

**OpenStreetMap.** The OpenStreetMap sources are consumers of core's loader
([ingest/osm_extract.py](../../ingest/osm_extract.py), `python3 -m ingest
osm-load`), declared in `plugin.json`'s `osm_consumers`. The loader cuts the
valley box out of the hand-downloaded extract once, and gives each highway way
to one consumer by its tags (plan C10):

- `osm_valley` (first, unchanged): every major way and every way tagged with
  lanes, into `core.osm_way` and friends, with `raw.record` versions and the
  ACHD matching, as before. It runs its own pipeline over the loader's cut
  and keeps its own gate (`$TVT_ARCHIVE/osm/last-loaded.json`).
- `osm_street` (landscape sprint, Oct 2026): the other streets, so the
  real-width roads build has every carriageway. That's residential,
  unclassified, living_street, road and busway ways, and alleys
  (`highway=service` + `service=alley`), that `osm_valley` doesn't keep, into
  `roads.osm_street`. It's versioned in place (OpenStreetMap's version and
  timestamp, first and last seen, active) with no `raw.record` copies. Its
  gate is its row in `ops.osm_consumer`.
- `osm_paving` (landscape sprint, Oct 2026): the paving that meets the
  carriageways ([below](#paving-service-ways-sidewalks-crossings-and-lots)):
  every other service way, sidewalks, crossings, access aisles and traffic
  islands into `roads.osm_paving`; parking lots and stalls into
  `roads.osm_parking`; crossing and kerb nodes into `roads.osm_walk_node`.
  Versioned in place, gated in `ops.osm_consumer`, like `osm_street`.

The lane-tagged cycleways, tracks and pedestrian ways that `osm_valley`
already keeps (12 in the Oct 5 extract) stay in `core.osm_way`; trails reads
them through a view.

`osm_street` and `osm_paving` load only the extract `osm_valley` holds, so
`core.osm_way`, `roads.osm_street` and `roads.osm_paving` always split one
extract's ways between them: a new extract goes through `osm_valley` first
(as the database owner), and `--only osm_street` or `--only osm_paving` then
follows it. A build that reads them together (the real-width build, P7)
calls `osm_extract.check_partition(conn, names)` first, naming each owner it
reads (`("osm_valley", "osm_street", "osm_paving")` with the paving).

### Paving: service ways, sidewalks, crossings and lots

`osm_paving` ([`ingest/sources/osm_paving.py`](ingest/sources/osm_paving.py),
migration `0002`; landscape sprint package P8-data, plan C10 and C11) keeps
what the partition gives it and what its tags name:

| Table | What | Oct 5 extract (scratch, Oct 11) |
|---|---|---|
| `roads.osm_paving` | every service way but alleys (`kind` driveway, parking_aisle, drive_through, emergency_access, or service for untagged and other values), and `footway=sidewalk`, `crossing`, `access_aisle` or `traffic_island` on a footway, path or cycleway; lines, whole across the box's edge (a closed way tagged `area=yes` keeps its outline, `area` true). An alley is `osm_street`'s unless it's tagged `area=yes`, closed or not; the table checks the partition's own test on the raw tags, so an alley the partition gives the paving never fails the load | 124,582: sidewalks 43,162, crossings 27,976, service 26,573, driveways 14,812, parking aisles 10,397, drive-throughs 800, access aisles 659, traffic islands 139, emergency access 64 |
| `roads.osm_parking` | lots (`amenity=parking`) and mapped stalls (`amenity=parking_space`) drawn as areas, closed ways and multipolygons; the smart cut keeps a multipolygon whole when any member is in the box. Lots mapped only as points aren't kept | 2,198 lots (29 of them multipolygons), 2,189 stalls (1 a multipolygon); 828 ha |
| `roads.osm_walk_node` | crossing nodes (`highway=crossing` or any `crossing=*`) and kerb nodes (`kerb=*`), with the `roads.osm_paving` ways through each (`ways`) | 35,806 crossings, 29,811 kerbs |

**Material** (plan C11): `material` is asphalt, concrete, gravel, dirt or
unknown. It comes from the surface tag where it reads as one of them
(`material_source` 'surface'; pavers, brick, wood and metal count as
concrete, `surface=paved` takes the kind's paved material). Otherwise the
kind's default (`material_source` 'default': the card says "surface
estimated"): concrete for driveways, sidewalks, traffic islands and parking
garages, asphalt for the other service ways, crossings, access aisles, lots
and stalls. **Service ways and lots take theirs only on developed land:**
at least half of the way's length or of the lot's area on the Cropland Data
Layer's developed classes 122-124 (`developed` holds the share, measured
exactly in PostGIS on NASS's equal-area grid). Off it they're `unknown`:
farm lanes, private roads and trailhead lots are often gravel, and we don't
guess. Class 121 (developed open space) doesn't count: it's lawns and parks,
and NLCD paints rural roads into it. Walkways and garages take their default
anywhere; underground lots get none. On the Oct 5 extract, against the 2025
CDL, 4,511 service ways (1,029 km; 2,405 of kind service and 2,021
driveways among them) and 81 lots and stalls (one underground) are unknown.
Driveways sit on the line more than the rest: 1,642 have between 0.4 and 0.6
of their length on developed land.

**Developed land** is a vector input, so the raster is never decoded in the
ingest image (docs/17 §17.8 Q9: rasters are decoded in the worker):

1. A worker step, [`build/developed.py`](build/developed.py) (GDAL, NumPy),
   traces the CDL's classes 122-124 into polygons on NASS's own grid
   (EPSG:5070), window by window (512 cells), from **farm's archived copy**
   (`$TVT_ARCHIVE/farm/cdl/`, which `farm-cdl-load` fills and indexes in
   `farm.cdl_year`; the newest year there is read), so the paving and the
   crop fields read the same file. It writes `developed.jsonl.gz` and
   `build.json` to `$TVT_ARCHIVE/roads/developed/<UTC stamp>/`. For the 2025
   CDL: 191,222 pieces (3.1 million vertices) and 861.4 km² of developed
   land, 7.7 MB, in about 45 s at 0.15 GB (a light job).
2. `roads-developed-load` ([`ingest/developed.py`](ingest/developed.py),
   standard library) checks the build, records it in
   `roads.developed_build` (the CDL's file, year, sha256, licence and
   credit; one build is current), replaces `roads.developed_land` with its
   polygons cut to at most 256 vertices (203,546 parts; the stored area
   must match the build's cell count), and measures the stored paving
   again, marking `roads-build` when any material changed. About 45-55 s.
3. Every `osm_paving` load measures what it loads against the current
   build. With none loaded it still loads, and says so: untagged service
   ways and lots are unknown until a build is loaded, which measures them.
   So a missing CDL never fails an OpenStreetMap load or leaves the
   partition's tables on two extracts.

**After a new CDL year** (late February, the owner's OK for each download):
`farm-cdl-load` takes it into farm's folder, then run the worker step and
`roads-developed-load` again; the paving follows, and `roads-build` is marked
if anything changed.

**Widths** (⚠️ estimates until measured in the test windows): the width tag
where it reads as metres (57 ways), else a kind's default in `width_est_m`
(`width_source` 'default'): sidewalk 1.5 m, crossing 3.0, access aisle 1.5,
traffic island 1.5, driveway 4.0, parking aisle 7.0 (4.5 one-way),
drive-through 3.5, emergency access 6.0, other service 5.5.

**Crossings:** `marked` is true for `crossing:markings` other than `no`,
`crossing=marked`, `zebra` or `uncontrolled` (OpenStreetMap's older word for
a painted crossing without signals ⚠️; 1,700 nodes), or
`crossing_ref=zebra`; false for `crossing:markings=no` or
`crossing=unmarked`/`no`; otherwise null, not known
(`crossing=traffic_signals` alone says nothing about paint). A crossing way
with nothing on it takes its crossing nodes' (`marked_from` 'node'). Rail
crossings (`railway=crossing`, `level_crossing`, `tram_crossing` or
`tram_level_crossing`) are never crosswalks: `marked` stays null, and a rail
crossing way doesn't take its nodes'. Another railway value (`abandoned`,
`disused`: a rail trail) doesn't make a crossing a rail crossing; the three
crossing ways on rail trails are marked on the way itself. Crosswalks are
drawn only where `marked` is true (decision 10; the roads build, P7, makes
them from `roads.osm_walk_node` where `kind = 'crossing' and marked`). On
the Oct 5 extract: 5,912 crossing nodes and 5,183 crossing ways are marked;
1,741 crossing nodes are at signals (`signals`), and 856 of those have no
`crossing:markings` and stay null.

Kerbs are stored for routing, not drawn. A load that changed anything
marks `roads-build` (`ops.build_pending`). Loading takes about 60 s and
0.3 GB on a cut already made (a light job).

**Size** on scratch, freshly loaded, with indexes: `roads.osm_paving` 53 MB,
`roads.osm_parking` 2 MB, `roads.osm_walk_node` 20 MB, `roads.developed_land`
62 MB. A reload rewrites every row it brings (and a developed load every
polygon), so a table holds up to about twice that until it's vacuumed.

**Licences:** the three paving tables are ODbL (© OpenStreetMap
contributors). `developed`, and the materials resting on it, also read the
CDL (USDA NASS, public domain, "free to redistribute"; credit "USDA NASS
Cropland Data Layer <year>"), which changes neither. An export of them lists
the CDL as an input, with `roads.developed_build`'s current year and sha256;
the tables' comments say so.

**Tables:** `core.road_segment`, `core.segment_match`, `core.hpms_section`,
`core.msm_arterial`, `core.compass_segment`, `core.osm_way`, `core.osm_lane`,
`core.osm_node`, and the `core.segment_lanes` view with its four per-source
views (migrations 0004, 0011, 0016–0018 in `db/migrations/`). In the plugin's
own schema `roads` ([migrations/](migrations/)): `roads.osm_street` (0001),
`roads.osm_paving`, `roads.osm_parking`, `roads.osm_walk_node`,
`roads.developed_build` and `roads.developed_land` (0002),
`roads.bike_facility`, `roads.bike_facility_note` (internal),
`roads.bike_facility_match` and the views `roads.bike_facility_side` and
`roads.segment_bike_xsection` (0004); the real-width build's `roads.build`,
`roads.piece`, `roads.xsection`, `roads.junction`, `roads.surface`,
`roads.edge`, `roads.marking`, `roads.arrow` and `roads.review` (0003,
[below](#real-width-roads-the-build)).

**Code:** `ingest/sources/` (the sources and consumers), `ingest/developed.py`
(developed land: loading a build, and measuring shares of it in PostGIS),
`build/developed.py` (the worker step that traces it from the CDL),
`ingest/segment_match.py` (matching to ACHD's segments with core's line
matcher, and `core.segment_match`), `ingest/streets.py` (street names made
comparable; the intersections plugin uses it too), `ingest/build.py`,
`ingest/xsection.py`, `ingest/calibrate.py` and `ingest/export.py` (the
real-width roads), `ingest/marks.py` (the sources' marks on `roads-build`).

**Commands:**

```bash
TVT_ARCHIVE=data/archive python3 -m ingest osm-load --inbox            # an OSM extract downloaded by hand (needs osmium-tool)
TVT_ARCHIVE=data/archive python3 -m ingest osm-load --only osm_street  # this consumer, on the extract we hold
TVT_ARCHIVE=data/archive python3 -m ingest osm-load --only osm_paving  # the paving (measured against the current developed land)
python -m plugins.roads.build.developed --cdl $TVT_ARCHIVE/farm/cdl --out $TVT_ARCHIVE/roads/developed/<UTC stamp>   # worker image
python3 -m ingest roads-developed-load --build $TVT_ARCHIVE/roads/developed/<UTC stamp>          # then measures the paving again
python3 -m ingest run achd_bike_network                                # ACHD's bike network (monthly when scheduled)
python3 -m ingest segment-match [itd_hpms achd_msm compass_centerline osm_valley achd_bike_network]
python3 -m ingest roads-build                                          # the real-width roads (below), then roads-export
python3 -m unittest discover -s plugins/roads -t .
data/dev/worker-test-remote.sh <worktree> <name> plugins.roads.tests.test_developed_build    # the worker step, worker image
```

**Ethics:** Geofabrik's robots.txt disallows scripted downloads of its
extracts (Oct 6, 2026), so the owner downloads the Idaho extract in a
browser; no OpenStreetMap source has download code or a schedule.
Loading the remaining street classes was approved by the owner on Oct 8
(decision 2a), and the paving's tags (service and driveway ways, sidewalks
and crossings, parking) the same day. The CDL is USDA NASS's, public domain:
farm's archived copy of the owner's hand download (each yearly download
needs the owner's OK), traced in the worker image, never served as tiles.
Anything we publish that's derived from OpenStreetMap stays ODbL.

## ACHD's bike network: widths for the real-width roads

`achd_bike_network` reads ACHD's Official Bicycle Facility Network
(landscape sprint package P7b; the owner brought it forward on Oct 8, 2026,
decision 11) from `gis.achdidaho.org` (robots.txt: 404, no rules; never
`more.achdidaho.org`) through the shared ArcGIS reader: the ID list, then two
pages of 2,000, our User-Agent and a pause between requests. Catalog:
[docs/sources/cycling.md](../../docs/sources/cycling.md#achd-official-bicycle-facility-network).
On Oct 11, 2026 it held 3,932 records over 1,080 miles: 3,401 on streets,
183 pathways and 348 roads not built yet; 2,503 with a curb-to-curb width,
2,652 field-checked.

- **Licence:** none stated; the hub's licence field holds a disclaimer
  ("general reference purposes only and should not be used for planning
  determinations"). Internal use, credited to the Ada County Highway District;
  anything built from it (P7's cross-sections, the base bake) is internal
  too. ACHD's LTS is ACHD's assessment, never ours.
- **Versions and change check:** every record's versions in `raw.record` by
  OBJECTID. The layer has no GlobalID and no edit dates, and a reload
  renumbers its OBJECTIDs, so rows are carried over to new IDs (by LocationID
  and street, then the line), and each run compares a content hash of the
  whole read with the last one (`ops.layer_signature`): an unchanged layer
  only confirms its versions. The hub's DCAT feed isn't read: it lists the
  whole hub on another host, while the layer itself is three requests.
- **Free text:** ACHD's `Comments` and `FieldNotes` stay in
  `roads.bike_facility_note` (and `raw.record`). No view, export, tile set or
  card reads them.
- **Matching:** each street record is matched to ACHD's road segments by
  core's line matcher under roads' rule (15 m, bearings within 20°, closed
  lines failing), into `roads.bike_facility_match`. A match whose street
  names disagree is dropped (150 of 8,478 on Oct 11: mostly another street's
  segments beside or across the record), after ACHD's zero-padded numbers
  ('08th St') are unpadded. Pathways and roads not built yet aren't matched.
  On Oct 11: 3,312 of 3,401 street records matched, 8,328 matches on 8,105
  ACHD segments (1,300 km). It reruns after a run that changes the records,
  and after ACHD's segments change (`achd_roads`' rematch).

**The interface for P7** (the real-width roads build). Read
`roads.segment_bike_xsection`: one row per ACHD road segment the network lies
along (`road_segment_id`), from its best record (share, then field-checked,
then confidence). Metres, rounded to the centimetre; ACHD records feet.

| Column | Meaning |
|---|---|
| `object_id`, `location_id`, `street`, `existing_type`, `lts`, `field_verified`, `year_updated` | The record: ACHD's OBJECTID (changes on a reload: key cards on `road_segment_id`), LocationID, street, what's there in ACHD's words, ACHD's LTS (1–4), whether ACHD checked it in the field, and when |
| `share`, `confidence`, `method` | The match (`share` measures the ACHD segment) |
| `seg_one_way` | The ACHD segment's one-way (`both`, `forward`, `backward`) |
| `total_pavement_m`, `total_row_m` | Curb to curb, and the right of way: the whole road's (both carriageways where ACHD draws a divided road as two one-way segments) |
| `total_lanes`, `centre_lanes` | Every lane; and what's left after both directions' lanes (a centre turn lane on most rows that have one); null when they disagree |
| `unassigned_m` | Pavement left after both of the record's sides' `roadway_m` (both, even where the row shows one): the centre turn lane, a median, gutters. Null where either side's `roadway_m` is: on most streets without a bike facility ([coverage](#coverage)). On Oct 11 its median was 3.8 m with a centre lane and 0.3 m without |
| `forward_side` | `ebnb` or `wbsb`: which of ACHD's sides runs the way the segment is drawn. The record names its sides on one axis (north/south or east/west) and the segment's end-to-end bearing decides, within 75° of that axis; null otherwise |
| `fwd_lanes`, `fwd_lane_w_m` | Travel lanes the forward way, and the width of the one next to the bike facility (ACHD's adjacent lane width, recorded almost only beside a facility) |
| `fwd_bike`, `fwd_bike_w_m`, `fwd_bike_in_roadway` | The bike facility (`mixed_traffic`, `no_facility`, `bike_lane`, `buffered_bike_lane`, `protected_bike_lane`, `raised_bike_lane`, `cycle_track`, `multi_use_path`, `other`), its width (0 for mixed traffic or none), and whether it lies between the curbs (bike lanes, buffered and protected ones ⚠️; not raised lanes, cycle tracks or paths) |
| `fwd_buffer`, `fwd_buffer_w_m`, `fwd_buffer_varies` | The buffer (`none`, `painted`, `landscaping`, `extruded_curb`, `jersey_barrier`, `delineator`, `parking`, `other`), its width (0 for none; null where it varies) |
| `fwd_parking`, `fwd_parking_w_m` | Parking (`none`, `parallel`, `angled`) and its width (0 for none) |
| `fwd_edge`, `fwd_right_turn` | The pavement edge (`curb_gutter`, `curb`, `shoulder`); right-turn lanes (`turn_lane`, `through_right_outside`, `through_right_shared`) |
| `fwd_roadway_m` | This side's share of the pavement: lanes × lane width + parking + the facility and buffer when they're in the roadway; null when a part is unknown, which is most sides in mixed traffic ([coverage](#coverage)) |
| `bwd_*` | The same for the backward way. On a one-way street the side against the traffic has 0 lanes but keeps its edge and parking. On a one-way ACHD segment, a side that isn't the segment's carriageway is null ([below](#one-way-segments)) |
| `flags` | `direction_unclear`; `direction_conflicts_one_way` and `other_carriageway` ([below](#one-way-segments)); `lanes_disagree`; `components_exceed_pavement` (`unassigned_m` under −0.5 m); `pavement_exceeds_row`; `one_way_segment` (`seg_one_way` isn't `both`) |

### One-way segments

Where ACHD's segment is one-way (`seg_one_way` `forward` or `backward`; 312
rows on Oct 11, 2026, flag `one_way_segment`), the row shows only the sides
that belong to that carriageway. Don't draw lanes from a null side.

- **A one-way record** (ACHD's side against the traffic has 0 lanes): both
  sides are shown. The other side holds only its edge and any parking or
  bike lane.
- **Lanes on both sides** (89 rows): a two-way record over one carriageway
  of a divided road, or over a couplet or slip piece. The side against the
  segment's traffic belongs to another carriageway, so its `bwd_*` (or
  `fwd_*`) are null; flag `other_carriageway`.
- **No lanes where the segment's traffic runs** (9 rows): 0 lanes there, or
  none known while the other side has some. The match or ACHD's directions
  are wrong, so neither side is shown; flag `direction_conflicts_one_way`.

The totals, `centre_lanes` and `unassigned_m` are always the record's, for
the whole road. `roads.bike_facility_side` keeps every side.

### Coverage

ACHD records the adjacent lane width almost only beside a bike facility. Of
its field-checked street sides on Oct 11, 2026, 2,514 of 2,760 in mixed
traffic and 154 of 301 with no facility have lanes but no lane width. So
`roadway_m`, and `unassigned_m` with it, are mostly null on streets without
a bike facility.

| Of 8,105 rows (Oct 11, 2026) | Rows |
|---|---|
| Both sides' `roadway_m` | 1,973 in all: 1,913 of the 2,292 rows with a facility on a side, but only 60 of the 3,170 without |
| `unassigned_m` | 1,961 |
| `total_pavement_m` | 5,375 |
| `total_lanes` | 7,721 |
| The lane counts (`fwd_lanes` or `bwd_lanes`) | 5,268 |
| Sides known (`forward_side`) | 5,462 |

On mixed-traffic streets, only `total_pavement_m`, `total_lanes` and the
lane counts are reliable. Splitting the pavement between the lanes there is
P7's own estimate.

Width tier for the card: "inventoried (ACHD bike network, field-checked)"
where `field_verified`; credit "Ada County Highway District". Records ACHD
hasn't checked in the field have no sides (`forward_side` null, no flag) and
mostly no widths. `roads.bike_facility_side` has each record's two sides in
metres, unturned (`side` `ebnb` or `wbsb`), for anything that works on ACHD's
lines rather than its segments. Neither view has free text.

## Real-width roads: the build

`roads-build` ([`ingest/build.py`](ingest/build.py), migration `0003`;
landscape sprint package P7, the roads-real-width design, decision 10)
draws every road at its width: OpenStreetMap's geometry everywhere, the lane
counts and widths from the sources below, and how each is known shown by
form (the app half is P9). It's a light job: standard-library Python running
PostGIS SQL, as `tvt_build`, rebuilt whole each time in one transaction.
Never inside `ingest serve`: a source that changes its inputs marks
`roads-build` (M1; [`ingest/marks.py`](ingest/marks.py)), and it runs by
hand. When it succeeds it marks `roads-export`.

**Inputs.** The carriageways are `core.osm_way`'s road classes and
`roads.osm_street`: motorway to tertiary and their links, residential,
unclassified, living_street, road, busway, alleys, and the few lane-tagged
service ways osm_valley keeps (not its 12 cycleways, tracks and pedestrian
ways, which are trails'). The build first calls
`osm_extract.check_partition(conn, ("osm_valley", "osm_street",
"osm_paving"))`, so they and the paving it reads (sidewalks, crossings) hold
one extract. Then ACHD's segments and their lanes rule (`core.segment_lanes`),
ACHD's bike network (`roads.segment_bike_xsection`), ITD's HPMS sections,
signals (`core.intersection`), COMPASS's traffic zones (`core.taz`: which
county a piece is in) and developed land (the CDL, `roads.developed_land`).

**Steps** (the module's docstring has each rule):

1. **Pieces:** each way split at every node it shares with another road way
   (OpenStreetMap shares one only where roads meet, so a bridge over a road
   never splits it). The pieces' ids are the build's own: cards key on the
   way (`osm_id`) and ACHD's segment, never on a piece.
2. **Matching:** the ACHD segment each Ada piece lies along (core's line
   matcher, roads' rule: 15 m, bearings within 20°), HPMS's sections along
   each piece, the parallel sidewalks either side (two of three samples,
   within 15 m and 25°), and the piece's share of developed land.
3. **Cross-sections** ([`ingest/xsection.py`](ingest/xsection.py)), below.
4. **Junctions:** nodes where three or more piece ends meet, joined into one
   junction along pieces shorter than 30 m (a major road at either node),
   22 m (a collector) or 15 m, and all round a roundabout. Kinds: `signal`
   (a `core.intersection` signal within 30 m), `roundabout`, `interchange`
   (a motorway meets it: no curb returns, so gores stay open) and `plain`.
5. **Surfaces:** each piece's carriageway, one-sided buffers either side with
   flat ends and mitred joins, plus a disc where two pieces meet end to end
   at an angle; a curbed or barrier median strip where HPMS has one on a
   single way; **bridges are decks** (`kind` 'deck', with their `layer`),
   drawn flat with a dark edge in v1: no 3D decks. Tunnels get none.
   **Tapers:** where two pieces meet end to end and their lane counts differ
   (both from a source: a lane added or dropped is mapped there), the wider
   narrows to the other over its first 30 m (at most half its length)
   instead of stepping. A bay is never given a length of our own.
6. **Islands:** the road graph's enclosed faces (its at-grade centrelines
   polygonized) that are small (under 2,000 m²: channelizing islands, tiny
   blocks), thin (twice the area over the perimeter under 15 m: medians,
   frontage-road separators) or a roundabout's centre, less the carriageways
   over them. Small ones (and the medians between a divided road's crossings,
   when they're that small) and roundabout centres near a junction are stored
   (`kind` 'island', material `unknown`: grass, concrete or planted, the map
   doesn't know); thin longer ones only keep the closings out. `area:highway`
   islands aren't loaded by any consumer (it would be a new tag set: an
   owner item), so islands come from the graph.
7. **Closings (curb returns):** for each pair of arms side by side around a
   junction, their carriageways and its inner pieces', cut to the junction's
   disc, closed by its radius (buffered out, then back in). Arms leaving
   within 25° of each other (a divided road's two carriageways) aren't
   paired, so its median stays open, and nor are arms 170° or more apart. The
   radius by the two highest classes that meet ⚠️: 10.5 m major/major, 9 m
   major/collector, 7.5 m collector/collector, 6 m with a local street, 4.5 m
   local/local, 3 m where an alley or service way meets a street, at most
   6 m at roundabouts. What the closings add, less the junction's
   carriageways and the islands, is its fill (`kind` 'junction').
8. **Edges:** every surface's outline less the surfaces it meets (so no seam
   where two meet is an edge): `curb`, `shoulder` (no curb) or `deck`, each
   with its width's tier, so a crisp curb is drawn only where the width is
   known and a soft edge where it's estimated (decision 10).
9. **Crosswalks** at marked crossing nodes only (`roads.osm_walk_node` where
   `kind = 'crossing' and marked`; rail crossings are never marked, P8): 3 m
   deep ⚠️, across the road along the crossing way where it crosses (if
   that's within 35° of square to the road; else square), as long as the
   road is wide that way and 2 m more, clipped to the surfaces.
10. **Markings**, where the cross-section says so (below): lane, centre,
    edge, two-way turn lane and bike-lane lines offset from the centreline;
    cut back from each junction by the length of the piece inside the other
    pieces' carriageways plus the curb-return radius and 1 m, and 1 m from
    crosswalks; **stop bars** across the lanes coming into a signal, where
    the lines stop (1.2 m before a crosswalk there); **turn arrows**
    (`turn:lanes`) 8 m before where a lane's lines stop.
11. **Generalised** surfaces for z15 (0.5 m; under 4 m² left out), and the
    **review list** (`roads.review`).

**On scratch** (Oct 11, 2026, the Oct 5 extract; build `20261011T175252Z`):

| | |
|---|---|
| Ways, pieces | 36,689 ways (13,904 in `core.osm_way`: its 13,917 less the 7 cycleways, 4 tracks, 1 pedestrian way and 1 raceway; 22,785 in `roads.osm_street`), 69,893 pieces: Ada 44,884, Canyon 22,310, elsewhere 2,699; 38,097 of Ada's on an ACHD segment |
| Lanes | from OpenStreetMap 22,111 pieces, the Master Street Map 1,043, HPMS 326, COMPASS (in Ada, by the lanes rule) 143, OpenStreetMap through ACHD's segment 101, the default 46,169; lines on 13,303 |
| Widths | inventoried 8,916, counted 4,767, estimated 56,210 |
| Junctions | 31,087 (signal 588, roundabout 139, interchange 126); 79,950 corner pairs closed, 30,324 fills; 1,852 islands; 928 tapers |
| Edges, markings | 204,351 edges (curb, shoulder, deck); 30,150 lines and stop bars (1,651 stop bars); 4,295 crosswalks; 1,738 arrows |
| Review list | lanes_conflict 801, sidewalk_close 1,444, components_exceed 724, unmatched 196, direction 42, other_direction_assumed 16, deck_mismatch 12, turn_slots 10, bike_other_carriageway 8 |
| Time | 456-528 s, as a light job (2 GB, 2 CPUs, `tvt_build`): matching 90 s, cross-sections 35-90 s, closings 140 s, edges 85 s; a rebuild over the last build takes no longer. The build's container peaked at 0.56 GB; the database's at 1 GB (its cap is 2) |
| Size | 192 MB with indexes, freshly built: `roads.surface` 74 MB, `roads.edge` 53, `roads.xsection` 25, `roads.piece` 25, `roads.marking` 9, `roads.junction` 6, the rest under 2. A rebuild deletes and writes every row, so up to about twice that until vacuumed |
| Export | 164 MB of FlatGeobuf, about 15 s |
| Bake | the export alone baked to 30.6 MB (21,475 tiles, z14-16) in 346 s at one CPU and under 1 GB (a light worker job); the largest z16 tile downtown is 20 KB, a third of the 60 KB budget |

### Cross-sections

Left and right are as the line is drawn; forward lanes run along it.
OpenStreetMap draws a way down the middle of its carriageway, so the
pavement is centred on it, except where a sidewalk cuts one side.

| Part | Rule, first that applies |
|---|---|
| Lanes (`lanes_source`) | The way's own `lanes`, `lanes:forward/backward/both_ways`, `turn:lanes*` (`osm`; an odd two-way count without a split reads as the Master Street Map's, a centre turn lane from 3). In Ada, the ACHD segment's lanes rule (`core.segment_lanes`: HPMS on state routes, the Master Street Map on arterials, OpenStreetMap or COMPASS elsewhere, else 1+1), turned onto the piece by bearing: a one-way piece (a divided road's carriageway) takes its own direction's count. Elsewhere HPMS's through lanes on interstate, US and state routes (`itd_hpms`; off them HPMS's counts are defaults). Else 1+1, or 1 one-way (`default`). COMPASS for Canyon is left out (cut first) |
| Lane width | HPMS's on its sections; else ACHD's lane beside the bike facility; else 3.66 m on major roads, 3.35 m collectors, 3.05 m local streets (§14.7 ⚠️), 5.0 m round a roundabout ⚠️ |
| Bike lanes, parking | ACHD's bike network where it covers the side (in the roadway: bike lanes, buffered and protected ones, with a painted, delineator, curb or barrier buffer); else OpenStreetMap's `cycleway*=lane` (1.5 m ⚠️) and parking tags (parallel 2.4 m, diagonal 4.8, perpendicular 5.4 ⚠️) |
| Edges | Curbed where ACHD's bike network says so, where a sidewalk is mapped beside it (tagged on the way, or a parallel sidewalk way), or on developed land (the CDL's 122-124, half the piece or more); never on motorways and their links; else a shoulder (no curb) |
| Shoulders, gutters | HPMS's; else motorways 3.0 m outside and 1.2 m inside, other rural roads 1.2 m ⚠️; a curbed side's 0.6 m gutter ⚠️, inside a parking or bike lane where there is one |
| Median | HPMS's on a single two-way way (curbed, barrier or unprotected) |
| Total (`width_tier`) | **inventoried:** ACHD's measured curb to curb (`total_pavement_m`) on a two-way piece along a two-way segment, or a one-way carriageway's own side (`roadway_m` plus gutters); the way's `width`; HPMS's lane width with HPMS's shoulders or curbs. **counted:** lanes from a source, widths from the defaults. **estimated:** default lanes, or a class pavement wider than the lanes: local streets 9.75 m curbed and 7.3 m rural ⚠️ (calibrated, below), curbed two-way collectors 11.3 m ⚠️. **measured** is the photo check's (later) |
| Fitting | An inventoried total fits its lanes to it (2.6-4.6 m a lane; an unmarked local street's down to 2 m, shared between parked cars). Wider pavement goes to the edges; components that don't fit are scaled down, flagged `components_exceed` and listed |
| Sidewalks | A surface edge stays 1 m inside a parallel sidewalk: an estimated or counted side is cut to it from its gutter, parking and unassigned pavement, never into lanes with lines (an estimated street's notional lanes may go, down to 2.75 m a side); otherwise `sidewalk_close`, listed. An inventoried width isn't cut, but listed when a sidewalk is more than a metre inside it |
| Markings | Only where a source gives the lane count: never on `default` lanes or `lane_markings=no`; on local streets only from 3 lanes, with a centre turn lane or bike lanes, or with `lane_markings=yes`; alleys never. A two-way road's directions part at a double line (`centre_double`), or either side of a centre turn lane (`twltl`); lanes going the same way at dashed lines; a shoulder at an edge line; a bike lane at solid lines; freeways and ramps always carry both edge lines |
| Material | The surface tag (the paving's mapping: asphalt, concrete, gravel, dirt); else asphalt, but unclassified roads, `highway=road`, alleys and service ways only on developed land (plan C11), otherwise `unknown` |

Each piece's `sources` names every part's source, and `republish` is
`internal` where any is ACHD's or ITD's (or the lane count came through
ACHD's segment). A public variant (decision 4) is a rebuild without them.

**Calibration** (`roads-build --calibrate`, read only;
[`ingest/calibrate.py`](ingest/calibrate.py)). The design's 10.4 m curbed and
7.3 m rural were checked against ACHD's measured curb-to-curb widths, by the
build's own reading of each street's edges, in the ten test windows first,
then valley-wide (Oct 11, 2026; p25 / p50 / p75 in metres):

| Where | Curbed local streets | Rural local streets | Curbed collectors |
|---|---|---|---|
| Box c, North End (86 / 30 segments) | 8.99 / 10.67 / 11.43 | none measured | 10.06 / 10.52 / 14.63 |
| Box d, South Meridian (10) | 9.30 / 9.30 / 9.30 | none | none |
| Downtown (49 / 57) | 10.36 / 10.82 / 10.97 | none | 10.52 / 11.73 / 14.41 |
| Valley-wide (1,899 / 244 / 894) | 9.66 / 9.75 / 10.67 | 7.32 / 8.75 / 9.75 | 10.52 / 11.28 / 11.73 |

So curbed local streets default to **9.75 m** (32 ft: the valley's median,
which the windows' medians bracket), rural ones stay at 7.3 m (no measured
rural street lies in the windows; ACHD's rural local streets are wider, but
they're its bike routes), and curbed two-way collectors get 11.3 m. ACHD's
widths are internal, and these defaults are aggregates of them: a public
variant may want them recalibrated from public data (the photo check). A
second, public measure, the spacing of the sidewalks either side of
residential pieces less 2 × 0.9 m, runs 10.35 / 10.81 / 14.16 valley-wide
(14,539 pieces): an upper bound, since planter strips widen it.

### The review list

`roads.review` (`roads-build --review [KIND]` lists it): where the sources
disagree or a rule couldn't be applied cleanly, never silently.

| Kind | What |
|---|---|
| `lanes_conflict` | The way's own lane count and the ACHD segment's rule differ by more than a lane, or the rule's own sources conflict (`core.segment_lanes.conflict`) |
| `direction` | A one-way piece against its ACHD segment's direction of travel, or the segment's count for its direction is 0: lanes from the default instead |
| `other_direction_assumed` | One OpenStreetMap way for a road ACHD draws as two one-way segments: the other direction is taken to match |
| `components_exceed` | An inventoried width narrower than its lanes, parking and bike lanes: scaled down |
| `sidewalk_close` | A sidewalk closer than the lanes allow (or more than a metre inside an inventoried width) |
| `unmatched` | A major or collector piece in Ada, 50 m or more, along no ACHD segment |
| `deck_mismatch` | A piece along an elevated ACHD segment (an overpass) that OpenStreetMap doesn't draw as a bridge |
| `turn_slots` | `turn:lanes` with more or fewer slots than lanes |
| `bike_other_carriageway` | ACHD's bike network row conflicts with its one-way segment's direction |
| `junction_large` | A junction of more than 12 nodes or spreading over 100 m |
| `geometry` | A surface the geometry steps left invalid |

### The export

`roads-export` ([`ingest/export.py`](ingest/export.py)) writes the current
build to `$TVT_ARCHIVE/roads/export/<build>/` through the export contract,
every layer a base layer for the landscape bake (`basemap/landscape/`),
source-layers `roads.<layer>`:

| Layer | Zooms | Geometry | Fields |
|---|---|---|---|
| `lines` | 14-16 (alleys and service ways from 15) | LineString | `class`, `w` (the pavement's width, m), `material`, `tier`, `lanes`, `marked`, `conflict` (▲), `deck`, `tunnel`, `layer` |
| `surfaces_z15` | 15 | MultiPolygon | `kind` (carriageway, junction, deck, median, island), `material`, `tier`, `layer`: generalised |
| `surfaces` | 16 | MultiPolygon | the same, full detail |
| `edges` | 16 | MultiLineString | `kind` (curb, shoulder, deck), `tier`, `layer` |
| `markings` | 16 | MultiLineString | `kind` (edge, lane, centre_double, twltl, bike, stop_bar), `dash` (solid, dashed, double, solid_dashed) |
| `crosswalks` | 16 | MultiPolygon | marked crossings only |
| `arrows` | 16 | Point | `turns` ('left;through'), `bearing` (degrees from grid north) |

Every layer has an integer `id` (the build's own) and is **internal**
(republish `internal`, licence ODbL-1.0 with ACHD's and ITD's inputs): the
bake that holds it is tailnet-only until a public variant exists (C17,
decision 4). The ground never reads it. The inputs and their versions come
from `roads.build.inputs`. Paving's base layers (P8-app) join this export:
add them to `LAYERS`, since the bake reads each plugin's newest export whole.

```bash
python3 -m ingest roads-build                 # the build (as tvt_build; a light job)
python3 -m ingest roads-build --dry-run       # the same, rolled back
python3 -m ingest roads-build --calibrate     # local streets' widths against ACHD's, in the windows and valley-wide
python3 -m ingest roads-build --review [KIND] # the review list
python3 -m ingest roads-export                # the base layers, to $TVT_ARCHIVE/roads/export/<build>/
```
