# trails

Foothills trail conditions and Greenbelt closures, as the City of Boise
publishes them
([docs/17 §17.4](../../docs/17-sources-for-new-plugins.md#174-proposed-order-with-rough-effort),
Wave A: "start the clocks"). Both layers keep only their current state, so
history exists only if we poll. Ridge to Rivers' per-trail status, recorded
through a wet season, is the label set for the mud model (ch. 17 Q32). Ingest
only for now: no tables of its own, no migrations and no map layers. Readings
go to `raw.record` and lifecycles to core's `evt.event`.

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `r2r_trails` | every 30 min: a layer check; the trails only when the layer changed (or daily) | none stated (City disclaimer only) | City of Boise Parks & Recreation (Ridge to Rivers) | aggregates; rows internal until the City answers a courtesy note |
| `boise_greenbelt_closures` | every hour, both layers whole | none stated (City disclaimer only) | City of Boise Parks and Recreation | aggregates; rows internal until the City answers a courtesy note |

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
    of both layers. Every field is kept except `OBJECTID` (it's in the key)
    and `SHAPE__Length`, plus a line fingerprint.
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

## Not built here

- R2R's weekly condition reports (title and link only, internal;
  [trails.md](../../docs/sources/trails.md#ridge-to-rivers-weekly-condition-reports)).
- R2R's amenities layer (trailhead parking, restroom and alert status). It's
  also current-state only, and is a cheap next poller on the same service.
- The Greenbelt mile markers and the rest of Boise Parks GIS: reference
  layers for Wave B.

## Commands

```bash
python3 -m ingest run r2r_trails boise_greenbelt_closures
python3 -m unittest discover -s plugins/trails/tests -t .   # database tests need TVT_TEST_DATABASE_URL
```

The test fixtures are synthetic: real field names and structure with
made-up values, since the City's data isn't ours to copy into a public
repository.
