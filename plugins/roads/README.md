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
`roads.segment_bike_xsection` (0004).

**Code:** `ingest/sources/` (the sources and consumers), `ingest/developed.py`
(developed land: loading a build, and measuring shares of it in PostGIS),
`build/developed.py` (the worker step that traces it from the CDL),
`ingest/segment_match.py` (matching to ACHD's segments with core's line
matcher, and `core.segment_match`), `ingest/streets.py` (street names made
comparable; the intersections plugin uses it too).

**Commands:**

```bash
TVT_ARCHIVE=data/archive python3 -m ingest osm-load --inbox            # an OSM extract downloaded by hand (needs osmium-tool)
TVT_ARCHIVE=data/archive python3 -m ingest osm-load --only osm_street  # this consumer, on the extract we hold
TVT_ARCHIVE=data/archive python3 -m ingest osm-load --only osm_paving  # the paving (measured against the current developed land)
python -m plugins.roads.build.developed --cdl $TVT_ARCHIVE/farm/cdl --out $TVT_ARCHIVE/roads/developed/<UTC stamp>   # worker image
python3 -m ingest roads-developed-load --build $TVT_ARCHIVE/roads/developed/<UTC stamp>          # then measures the paving again
python3 -m ingest run achd_bike_network                                # ACHD's bike network (monthly when scheduled)
python3 -m ingest segment-match [itd_hpms achd_msm compass_centerline osm_valley achd_bike_network]
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
