# trails

The valley's trails and paths, and their status. OpenStreetMap draws the
network: about 22,200 paths, footways, cycleways, tracks, bridleways and steps
in the valley box, with walking, cycling and riding routes. Foothills trail
conditions and Greenbelt closures, as the City of Boise publishes them
([docs/17 §17.4](../../docs/17-sources-for-new-plugins.md#174-proposed-order-with-rough-effort),
Wave A: "start the clocks"), are linked onto those ways, so the status shows
on the trail itself (landscape sprint, Oct 2026, package P6-data). Both City
layers keep only their current state, so history exists only if we poll.
Ridge to Rivers' per-trail status, recorded through a wet season, is the label
set for the mud model (ch. 17 Q32). Readings go to `raw.record` and lifecycles
to core's `evt.event`; the plugin's own tables are in schema `trails`
(migration 0001). The map layer (P6-app) reads the views below.

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `r2r_trails` | every 30 min: a layer check; the trails only when the layer changed (or daily) | none stated (City disclaimer only) | City of Boise Parks & Recreation (Ridge to Rivers) | aggregates; rows internal until the City answers a courtesy note |
| `boise_greenbelt_closures` | every hour, both layers whole | none stated (City disclaimer only) | City of Boise Parks and Recreation | aggregates; rows internal until the City answers a courtesy note |
| `osm_paths` | by hand, with each extract (`osm-load`) | ODbL | © OpenStreetMap contributors | yes |
| `trails_match` | after a poll that changed a line; the `trails-match` build by hand | derived: ODbL with the City's lines | both | aggregates (the links carry the City's ids) |

The license rule is ch. 17 Q17's: a state or local agency service with no
stated license is used, kept internal or published only as aggregates, and
gets a courtesy note. The note to the City of Boise is due (it's listed in
[§17.7](../../docs/17-sources-for-new-plugins.md#177-owner-actions-consolidated)).

## `r2r_trails`: Ridge to Rivers trails and conditions

Catalog: [trails.md, "Ridge to Rivers trails and live conditions"](../../docs/sources/trails.md#ridge-to-rivers-trails-and-live-conditions).

- **Endpoint:** `services1.arcgis.com/WHM6qC35aMtyAAlN/ArcGIS/rest/services/Ridge_to_Rivers_Trails_Assessment_Map_WFL1/FeatureServer/2`,
  the layer behind Ridge to Rivers' official map. No key. Query only.
- **robots.txt:** `services1.arcgis.com/robots.txt` answers 403, so there are no
  rules (RFC 9309). Re-checked through `ingest/http.py` on Oct 7, 2026.
  Requests to the host are at least 2 s apart (`http.PACE_S`).
- **Cadence:** every 30 minutes the layer's description is read (`?f=json`,
  about 36 KB). If its edit dates, field list and `Condition` values match the
  last full read, and that read is less than a day old, nothing else is
  fetched and the current versions are marked as seen. Otherwise every trail
  is read: an ID list and one batch, about 1 MB with lines, gzipped on the
  wire. The gate's state is one row in core's `ops.layer_signature`, the table
  the COMPASS reader uses for the same purpose. A missing `GlobalID`,
  `TrailName`, `Condition` or `ConditionDate` field fails the fetch, so a
  renamed field never reads as blanks.
- **What we keep:**
  - `raw.record`: one version per changed trail, keyed by `GlobalID`.
    `TrailID` can't be the key: on Oct 7 it had 177 distinct values over
    271 rows, with repeats and blanks. Every field is kept except the staff
    names (`Editor`, `created_user`, `last_edited_user`), `OBJECTID` and the
    derived `Shape__Length`. A fingerprint of the line is added, so a moved
    line makes a new version. Lines are kept at 6 decimals.
  - `evt.event`, kind `trail_condition`: one row per status that staff set
    on a trail, keyed `<GlobalID>/<ConditionDate>/<state>`. When a new status
    is set, the old row ends (its `observed` closes) and a new one starts. So
    each trail has a complete run of conditions: the muddy and closed
    intervals, and every label, including a status set again on a new date.
    `declared` starts when staff set the status. `description` is R2R's own
    label, and `attributes` hold the trail, the state, the staff note and
    the raw date.
- **States:** R2R's seven labels map to `dry`, `frozen`, `muddy_further_out`
  ("dry at start but could be muddy further out"), `frozen_then_muddy`,
  `muddy`, `closed` and `not_evaluated`, with `unset` and `other` for a blank
  or a new label. `severity` restates R2R's own advice: `open` (dry, frozen),
  `caution` (the two mixed states), `do_not_use` (muddy) and `closed`.
- **ConditionDate is Boise wall-clock time stored as if it were UTC.** On
  Oct 7, 227 of the 271 rows had `last_edited_date` (ArcGIS editor tracking,
  true UTC) exactly 6.00 h after `ConditionDate`, as MDT predicts. The "UTC"
  hours of `ConditionDate` cluster at 7 and 15–16, which are office hours in
  Boise, not at night. So the event's `declared` start is the true time
  (America/Boise), and `attributes` keep both the raw value and the
  wall-clock reading. `raw.record` keeps the value as published.
- **On Oct 7:** 271 trails: 238 "Dry / Tacky", 26 "Not Evaluated" and
  7 "CLOSED", matching the catalog's count. The layer was last edited at
  14:06 UTC on Oct 7.
- **Care:** R2R's `Condition` is advice, not a closure order, so label it as
  R2R's. Staff set statuses in batches, so labels are coarse. The schema
  changed on Oct 6, and a schema change now forces a read and a field check.
  If the City overwrites the layer, new GlobalIDs would end every condition
  run and start new ones. The history stays continuous by trail name and
  line in `raw.record`.

## `boise_greenbelt_closures`: Greenbelt closures and detours

Catalogs: [trails.md, "Greenbelt closures, detours and mile markers"](../../docs/sources/trails.md#greenbelt-closures-detours-and-mile-markers)
and [cycling.md, "City of Boise Greenbelt closures"](../../docs/sources/cycling.md#city-of-boise-greenbelt-closures).

- **Endpoint:** `services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Greenbelt_Closures_View/FeatureServer`.
  Layer 0 is `Greenbelt_Construction` (closed stretches) and layer 1 is
  `Greenbelt_Detour` (detour routes). Both are lines. No key. Query only.
- **robots.txt:** the same host, so no rules, and requests are 2 s apart.
- **Cadence:** every hour, both layers are read whole: an ID list and the
  rows, four small requests. The catalogs suggest gating on `lastEditDate`,
  but here a layer's description (about 10 KB) costs more than its rows
  (2–6 KB on Oct 7). Reading is the cheaper check, and a `STATUS` flip shows
  up within the hour whatever the view reports.
- **What we keep:**
  - `raw.record`: every row's version, keyed `construction:<OBJECTID>` or
    `detour:<OBJECTID>` (the view has no GlobalID), as one complete snapshot
    of both layers. Every field is kept except `OBJECTID` (it's in the key),
    `SHAPE__Length` and any staff names from editor tracking (`Creator`,
    `Editor`, `created_user`, `last_edited_user`, should the City turn it
    on), plus a line fingerprint.
  - `evt.event`, kind `closure` (layer 0) or `detour` (layer 1): every row
    in effect. A row is in effect unless its `STATUS`, or a detour's
    `Project_Status`, reads "Inactive" or another ended word (completed,
    cancelled, open, ...). A blank or unknown status counts as in effect,
    since the row is still on the City's map. The City flips `STATUS` by hand
    and may leave the row in the layer. The layer has no dates (only a
    `CONSTRUCTION_SEASON` text), so `observed`, our first and last seen, is
    the lifecycle.
- **Guard:** a layer this small may empty legitimately. The snapshot guard
  (refuse an empty snapshot, or one under half of what's current) applies
  only once we hold 5 rows or more. `fetch_layer` already fails a read that
  doesn't come back whole. A wrongly empty answer heals on the next poll,
  because rows and events that come back keep their first-seen times.
- **On Oct 7:** 2 closures and 1 detour, all "Active". The layers were last
  edited Sep 10, 2026.
- **Care:** the City's staff account owns the view, so it may move. A move
  fails the fetch; it doesn't empty the snapshot.

## `osm_paths`: OpenStreetMap's paths, tracks and routes

A consumer of core's OpenStreetMap loader
([ingest/osm_extract.py](../../ingest/osm_extract.py)): the extract the owner
downloads by hand (Geofabrik's robots.txt disallows scripts), cut to the
valley box once per load, read by each plugin's consumers with its own MD5
gate. Approved by the owner on Oct 8 (the landscape row's classes, and
decision 2c for the route relations). No download code and no schedule.

- **Ways** (`trails.osm_path`): the highway ways core's partition gives
  `osm_paths`, by tags alone: path, track, cycleway, bridleway, steps,
  pedestrian, and footways but sidewalks, crossings, access aisles and traffic
  islands (those are roads' `osm_paving`). Lines, each kept whole if a node is
  in the box. The 12 lane-tagged cycleways, tracks and pedestrian ways
  osm_valley keeps stay in `core.osm_way` (the partition's named exception),
  and `trails.exception_way` reads them with the same rules.
- **Areas** (`trails.osm_area`): pedestrian and footway areas (a closed way
  tagged `area=yes`, or a multipolygon): plazas, for the paved-path base. A
  closed way without `area=yes` is a loop, so a line.
- **Routes** (`trails.osm_route`): hiking, mtb, bicycle, foot and horse route
  relations, with every member in order and their ways' ids. Their ways can be
  any partition owner's (bike routes run on streets and sidewalks);
  `trails-match` draws each route's line from them.

Each way gets, by tags alone (the same rules as trails 0001's SQL functions,
which the exception's view uses; a test runs both over 1,000-odd tag sets):

- **Surface**, one of four, from the `surface` tag: paved (asphalt, concrete*,
  paved, paving_stones, bricks, sett, wood, metal, chipseal), gravel (gravel,
  fine_gravel, compacted, pebblestone), dirt (dirt, ground, earth, sand, grass,
  mud, rock, unpaved), or unknown (another value: the raw tag is kept).
  Untagged: a cycleway is paved and a track dirt (`surface_from` default),
  anything else unknown (`none`). A path most of which an R2R trail runs along
  reads dirt by default on its card (`trails.way_agency`): OpenStreetMap says
  unpaved for 94% of that length. The tiles keep OpenStreetMap's own reading,
  since the R2R default comes from the City's lines (54 ways on scratch).
- **Width**: the `width` tag where it reads as metres or feet (1.3% of path
  length has one), otherwise an estimate by kind ⚠️, as for lanes: dirt or
  unknown path 0.8 m, gravel path or bridleway 1.5 m, footway 1.8 m, paved path
  or cycleway 3.0 m, track 3.0 m; steps 1.5 m and pedestrian ways 4.0 m are
  ours, not the design's.
- **Access** (plan C18): `no_access` when `access=private` or `no`, unless a
  trail mode is opened (`foot`, `bicycle` or `horse` = yes, permissive,
  designated or official). Such a way is never drawn as a trail; the card on a
  nearby way can say "private, no public access". Only the access tag counts:
  `foot=private` alone doesn't close a way, and `access=agricultural`,
  `forestry`, `customers` or `permit` doesn't either. The trail-mode exception
  is our reading of C18, for the owner to confirm: on scratch it keeps 49
  ways tagged private or no drawn (10 km): 35 cycleways, 7 footways and 3
  paths (3 km in all), and 4 tracks (7 km) that the canal rule hides anyway.
  `informal=yes` is kept as `informal`.

Stored versioned in place (plan C2): no `raw.record` copies; `osm_version` and
`osm_timestamp` are OpenStreetMap's, `first_seen` and `last_seen` the loads
that first and last brought each object, and one missing from a load goes
inactive. A load marks the `trails-match` build and gives the Trails layer's
tiles a new version (`core.layer_version` `trails.paths`).

On scratch, Oct 11 (the Oct 5 extract, on the cut already made: 21 s, light):
22,200 ways (9,428 tracks, 8,642 km; 6,822 paths, 1,538 km; 4,623 footways,
415 km; 1,107 cycleways, 157 km; 205 steps, 23 pedestrian ways, 4
bridleways), 82 areas and the 147 route relations. 3,144 ways are closed to
the public (2,922 tracks, 1,736 km), and 128 are informal.

## The access rules (plan C18)

- **Private or no access:** never drawn as a trail (`trails.path.drawn`
  false, `not_drawn` 'private, no public access'), and never a target for an
  agency's line: an R2R trail on such a way draws itself.
- **Informal** (`informal=yes`): drawn only from z16 (`minzoom` 16), worded
  "informal, not an official trail". Never a target for an agency's line, so
  no line makes one official or keeps it from being hidden: an R2R trail on
  one draws itself. Hidden near closures: `trails.hidden_informal(near_m)`
  lists the informal ways within `near_m` (the status endpoint asks for
  100 m ⚠️) of an R2R trail that's CLOSED or a Greenbelt closure in effect.
  R2R closes trails, not areas, and we hold no land manager's area closures
  yet, so "inside a closure" is "near a closed line" for now (none of the 128
  informal ways on scratch is near one today).
- **Canal-bank tracks** (cut-first): a track at least 60% of which lies
  within 15 m of canal, lateral, ditch or drain reaches of water's build
  (`water.reach`, not piped) that match it (core's matcher: the bearing within
  20°), and not tagged `access=yes` or `permissive`, is irrigation access, not
  a trail (`trails.canal_track`, written by `trails-match`, with the water
  build its reaches came from). It needs water's build: until `water.reach`
  exists the rule is skipped, the build says so, and any earlier result is
  cleared. A new water build should be followed by `trails-match` (water's
  build marking it is for P4 to add: `then=("trails-match",)`); until then it
  goes in the deploy order. On scratch, with water's draft reaches (P4-data,
  water build 9, Oct 11): 333 of 9,428 tracks (279 km of 8,642), 92% along
  their canal on average; none named or under an agency's trail. The count
  follows water's build, which is still a draft.

## `trails-match`: the agencies' lines on OpenStreetMap's ways

```bash
python3 -m ingest trails-match            # the build (logs its run in ops.build_run)
python3 -m ingest trails-match --dry-run  # the same, reported, then rolled back
```

Each agency line (an R2R trail from `raw.record`, a Greenbelt closure or
detour) is linked to the ways it lies along with core's line matcher
([ingest/linematch.py](../../ingest/linematch.py)), **in pieces**: the line is
cut into pieces of at most 150 m, each piece is matched to the public,
official ways around it (buffer 15 m, bearing within 20°, 60% of the way
within the piece's buffer or of the piece within the way's), and:

- a way is **fully linked** when 60% of it lies within 15 m of pieces that
  matched it (method `pieces150_buffer15_bearing20`), **partly**
  (`way_in_pieces150_buffer15_bearing20`) when only 20 m or more of it does;
- a way **paints** (`trails.link.paints`: it takes the line's state, as
  feature-state on the whole way) only when it's fully linked and less than
  20 m of it lies farther than 15 m from the line (`off_m`);
- of every other way it's linked to (one longer than the line, or running on
  past it: a 120 m Greenbelt closure on a 1 km way), the stretch that lies
  along the line is drawn in the line's state (the line's `along`:
  OpenStreetMap's geometry, cut to the line);
- wherever neither shows it, the line draws itself (its `gap`: stretches of
  20 m or more).

So every metre of the line shows its state, mostly on OpenStreetMap's
geometry, and no way shows it more than 20 m beyond the line. Painting whole
ways alone (the first version) showed R2R's states on 22 km of ways beyond
their trails, up to 1.4 km past Chukar Butte.

Why pieces: matched whole, a long winding trail fails the bearing check
against a long winding OSM way that lies right along it, because the check
compares end-to-end chords. On scratch (Oct 11), Freddys Stack Rock Trail
(4.8 km, an OSM path within 15 m for 4.6 km) had no link; matched in pieces,
R2R's multi-use trails lie along their linked ways for 320 of 353 km, against
308 km matched whole. A test pins the case.

On scratch (Oct 11, the Oct 5 extract, 24 s as `tvt_build`): 261 of R2R's 270
lines linked; 474 links paint (436 ways) and 164 don't. 87% of R2R's 481 km
shows on OpenStreetMap's geometry: on the ways it paints, and on 183 km of
stretches of the others. 60 km (12.5%) draws itself, 48 km of that R2R's
"Access Road" (OSM maps them as roads, which aren't targets). Two of the
Greenbelt's three lines paint their ways; the detour runs on streets, so it
draws itself.

It runs two ways (docs/15, "Builds and their marks"):

- **After a poll.** `r2r_trails` and `boise_greenbelt_closures` call
  `match.after_poll` once their data is committed, when the poll stored a new
  or removed version. It relinks the lines whose geometry changed (the
  version's line fingerprint), lines never linked first, at most 40 of them
  (one line 0.4 s on scratch, 40 lines 4 s, the 40 longest 13 s); more are
  left for the build, which is marked. It runs in its own try block with its
  own `ops.fetch` row (source `trails_match`): a relink that fails never
  fails the poll (even on a lost connection), is logged there, and marks the
  build. It runs inside `ingest serve`, a second exception to plan item 27
  beside the intersections source's daily rebuild, because P6-data's row asks
  for it: a closure the City posts shows on the map within the hour, the
  Greenbelt's layer having emptied or not. So that it can never hold up the
  sources after it, each statement stops after 20 s and the relink after
  60 s; the work is then left for the build (marked). The build running at
  the time leaves it to the build too.
- **The build**, `trails-match`, by hand: after a new extract (`osm_paths`'
  load marks it), a new water build (canal tracks), or when marked. It logs
  its run (`builds.Run`), and does, in one transaction: the canal-bank rule,
  every line relinked against the extract `osm_paths` holds, each route's line
  (`trails.route_line`, from its member ways in `core.osm_way`,
  `roads.osm_street`, `roads.osm_paving` and `trails.osm_path`: load every
  consumer first), and the valley-zoom network (`trails.path_lo`). Light:
  about 25 s on scratch, as `tvt_build`.

A relink after a poll gives only the `trails.agency` tiles a new version; the
build gives all three a new one (`core.layer_version`).

## What the map reads

Plan C3: each relation, and each tile set, records the strictest of its
inputs. The Trails layer's ways and its valley-zoom network are OpenStreetMap's
alone (with water's reaches for the canal rule), so republish yes: what the
City's lines say of a way reaches the map only as feature-state, from
`/api/trails/status`. What the lines draw themselves is the `trails.agency`
tile set, republish aggregates. The views over the City's rows (`agency_line`,
`agency_state`, `way_agency`) run with their reader's privileges, and the tile
login is refused them ([deploy/tvt_tiles.sql](../../deploy/tvt_tiles.sql)'s
`never_tables`).

| Relation | What | Tile set | License, republish |
|---|---|---|---|
| `trails.path` | the Trails layer's ways: kind, name, surface and where it came from, width (tagged or estimated), `drawn` and `not_drawn`, `informal`, `canal_track`, `greenbelt` (on a route named for the Greenbelt), `minzoom` (16 informal; 13 tracks; 10 the Greenbelt's route, cycleways and named paths; 13 the rest), tags, geometry. Feature id `osm_id` | `trails.paths`, z13 up | ODbL, yes |
| `trails.path_lo` | the network at z10–12: the drawn ways with minzoom 10, simplified (5 m), by `network` (greenbelt, cycleway, named). On scratch 2,006 ways, 799 km | `trails.paths`, z10–12 | ODbL, yes |
| `trails.route_line` | each route relation's line, from its member ways | `trails.routes` | ODbL, yes |
| `trails.osm_area` | pedestrian and footway areas | (the paved-path base) | ODbL, yes |
| `trails.agency_drawn` | what the agencies' lines draw themselves: `part` 'way' (stretches of ways a line lies along without painting them) or 'line' (its own line where nothing else shows it), `kind`, `name`, `length_m`; feature id `fid` = `-line_id` | `trails.agency`, z13 up | the City's with ODbL, aggregates |
| `trails.agency_lo` | every agency line, whole and simplified (5 m), same `fid`. On scratch 273 lines, 475 km | `trails.agency`, z10–12 | the City's, aggregates |
| `trails.agency_state` | each agency line's state now (R2R's `state` and `severity`: open, caution, do_not_use, closed; a closure `closed`, a detour `detour`, a row the City set inactive `ended`), its label in the agency's words, `ways` (the ways it paints), `partial` (the others it's linked to), `line_id`, `gap_m`, `along_m` | (status) | the City's, aggregates; never tiled |
| `trails.way_agency` | per linked way, for the card: `r2r` (an R2R trail paints it), `greenbelt` (a Greenbelt closure or detour does), its surface with R2R's default | (card) | the City's with ODbL, aggregates; never tiled |
| `trails.hidden_informal(near_m)` | informal ways near a closed line | (status) | aggregates |

`GET /api/trails/status` (`app/src/lib/server/trails/status.ts`) serves the
status for feature-state: every agency line (with `drawn`, `gap_m` and
`along_m`), each painted way's worst state (closed, do_not_use, caution,
detour, open, then not_evaluated), the hidden informal ways, R2R's counts and
each source's last poll. Empty before this migration; `no-cache` with an
ETag. On scratch its queries take about 10 ms and 45 ms. The City's rows are
internal, like the tailnet map that shows them: a public build must leave the
status and the `trails.agency` tiles out, or show aggregates only.

## Not built here

- R2R's weekly condition reports (title and link only, internal;
  [trails.md](../../docs/sources/trails.md#ridge-to-rivers-weekly-condition-reports)).
- R2R's amenities layer (trailhead parking, restroom and alert status). It's
  also current-state only, and is a cheap next poller on the same service.
- The Greenbelt mile markers and the rest of Boise Parks GIS: reference
  layers for Wave B.

- The `trails.tread` "seen in the photo" scores (design; cut-first): they
  wait for the ground build's classes.
- The City's `Boise_Parks_Trails_Open_Data` (surface and width; approved Oct 8,
  decision 13): the next trail source, internal, aggregates in public.

## Commands

```bash
python3 -m ingest run r2r_trails boise_greenbelt_closures
python3 -m ingest osm-load --only osm_paths      # the extract we hold, into this consumer (light, on the cut)
python3 -m ingest trails-match [--dry-run]       # the build
python3 -m unittest discover -s plugins/trails/tests -t .   # database tests need TVT_TEST_DATABASE_URL
```

The test fixtures are synthetic: real field names and structure with
made-up values, since the City's data isn't ours to copy into a public
repository. OpenStreetMap's are invented too
([ingest/tests/fixtures/osm_landscape.osm](../../ingest/tests/fixtures/osm_landscape.osm)).
The tests that need osmium run in the ingest image.
