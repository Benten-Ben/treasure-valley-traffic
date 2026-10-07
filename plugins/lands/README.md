# lands

Public lands around the valley: for now, the orders and closures laid over
them. The Forest Service's Intermountain Region (R4) forest orders and
Idaho Parks and Recreation's (IDPR) road, trail and area closures, cut to
the regional ring. The plugin is proposed in
[docs/15 §15.7](../../docs/15-plugins.md#157-ideas-for-later-plugins), and
its sources are researched in [sources/lands.md](../../docs/sources/lands.md)
and [sources/trails.md](../../docs/sources/trails.md).

**Why now.** These layers hold only what is in force today. When an order
ends or is rescinded, it disappears from the layer, so a closure's history
exists only if we poll. This is part of Wave A, "start the clocks"
([docs/17 §17.4](../../docs/17-sources-for-new-plugins.md#174-proposed-order-with-rough-effort)):
ingest only, keyless, standard library, no UI yet. These are the R4 orders
and IDPR closures from the hiker and camper section's "first thing to build"
([§17.2](../../docs/17-sources-for-new-plugins.md#hiker-camper-and-land-permissions)).

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `usfs_r4_orders` | hourly check; full read after an edit, at least daily | public domain (US federal work); USFS: not legal documents | USDA Forest Service, Intermountain Region | yes |
| `idpr_route_closures` | hourly check; full read after an edit, at least daily | IDPR terms: non-commercial use, attribution required | IDPR (trails.idaho.gov), with the agencies it represents | aggregates (owner to decide) |
| `idpr_area_restrictions` | hourly check; full read after an edit, at least daily | IDPR terms: non-commercial use, attribution required | IDPR (trails.idaho.gov), with the agencies it represents | aggregates (owner to decide) |

**Tables:** none of its own, and no migrations. Each order or closure is a
record in core's `raw.record`, versioned when it changes, and a row in
core's `evt.event` (migration 0009). Both use the same `source_id`, and
`observed` runs from first seen until the order leaves the layer.

## How every source reads

All three sources share [ingest/closures.py](ingest/closures.py):

- **The ring:** W −117.30, S 42.90, E −115.60, N 44.30. This is the
  regional ring the lands and trails catalogs use (proposed in
  [DECISIONS](../../docs/DECISIONS.md)). The layer is queried with that
  envelope through the shared ArcGIS reader, query only. Features that touch
  the ring come back whole: Lowman's camping order reaches east of it.
- **The edit gate:** each run reads the layer's metadata first, one small
  request. It reads the ring in full only when `editingInfo.dataLastEditDate`
  is newer than about our last full read, or when that read is a day old.
  A skipped run is logged in `ops.fetch` with no record count. If a required
  field disappears, the run fails as a schema change.
- **Records:** fields every feature of an order agrees on are stored once.
  Each feature's own fields (acres, `crc`, GlobalID) go under `_parts`, with
  a fingerprint of its geometry. The record doesn't change when the layer
  renumbers its object IDs. Object IDs, derived shape areas and lengths, and
  staff user names are dropped. Geometry is GeoJSON in WGS84 to 6 decimals.
- **Polygons:** Esri lists every ring of a multipart polygon in one array.
  Each one is split into outer rings with their own holes (a MultiPolygon).
  Both layers have parts like that: the Claremont Fire closure has 3 outer
  rings and 4 holes.
- **Dates:** the agencies publish days without times. USFS writes them at
  12:00 UTC; IDPR writes text such as "8/13/2026", "12/31/2026 unless
  rescinded" or "Indefinite". They're read as local days (America/Boise),
  with the end day included. A USFS rescind date that comes before the end
  ends the order on that day. Text that doesn't start with a date leaves
  that end open. `attributes.fixes` lists anything adjusted.
- **Snapshot guard:** a read that would end more than half of the active
  orders is refused, unless the previous read saw the same count. So a real
  drop, such as fire closures lifted at the season's end, is taken an hour
  late. A layer caught half rebuilt is not taken.
- **Pacing:** at least 2 s between requests to `services1.arcgis.com`
  (`http.PACE_S`). A full read is 3 requests, gzip.

## Sources

### `usfs_r4_orders`: R4 forest orders

- **Endpoint:** `services1.arcgis.com/gGHDlz6USftL5Pau/arcgis/rest/services/R04_Forest_Orders_PUBLIC_VIEW/FeatureServer/0`
  ("ForestOrder" polygons). The region rebuilds it daily from each forest's
  own layer, driven by the orders' dates
  ([sources/trails.md, "USFS Region 4 forest orders"](../../docs/sources/trails.md#usfs-region-4-forest-orders)).
- **What's there (Oct 7, 2026):** 233 polygons across the region: Boise 15,
  Payette 23, Sawtooth 5, and the rest in other forests. The ring held 7
  polygons, which are 5 Boise NF orders: 0402-05-101 (designated camping),
  0402-03-134 (Grimes Creek), 0402-01-119 (Claremont Fire), 0402-01-122
  (Deer Point) and 0402-03-140 (Crooked Fire). No Payette or Sawtooth order
  reached the ring. If one ever does, it is kept.
- **Keyed on** the order number, so several polygons make one order. The
  record and the event keep the order's text: name, purpose, statement,
  exemption, CFR, type, signed, start, end and rescind dates. They also keep
  its link (`hyperlink`, the alert page or the signed order's PDF). The PDF
  is never fetched. `kind` is `closure` for closure orders and `restriction`
  for restriction or prohibition orders.
- **robots.txt:** `services1.arcgis.com` answers 403, which means no rules
  (checked Oct 7).
- **License:** federal work, public domain. The Forest Service says the
  data "are not legal documents", so the signed order is the authority.
- **Not in the layer:** forest-wide orders without a polygon, such as Boise
  NF's limit of 14 days in any 30 (0402-00-62). These are rules for the
  "Can I be here?" panel. The
  [Boise NF alerts page](../../docs/sources/lands.md#boise-national-forest-alerts-and-forest-orders)
  stays a by-hand source: it is HTML, not scraped.

### `idpr_route_closures`: IDPR emergency road and trail closures

- **Endpoint:** `services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/Idaho_Recreation_Trails/FeatureServer/127`
  (lines). This is the service behind trails.idaho.gov
  ([sources/trails.md, "IDPR Idaho Recreation Trails"](../../docs/sources/trails.md#idpr-idaho-recreation-trails)).
- **What's there (Oct 7, 2026):** 9 segments in the ring, making 4
  closures. They are Eagle Island State Park's construction closures (6
  segments), the Mores Creek trail's private-land closure, and IDPR's copies
  of Boise NF orders 0402-01-122 and 0402-03-140.
- **Keyed on** IDPR's `ID` field, which names a closure and repeats on each
  of its segments. A segment with no ID is keyed on its GlobalID. USFS order
  numbers in the text are listed in `attributes.orders_mentioned`, so a
  later step can link them to `usfs_r4_orders`. Links (`URL_1`, `URL_2`)
  are kept and never fetched. Office phone numbers belong to agency offices
  and are kept.

### `idpr_area_restrictions`: IDPR area closures and restrictions

- **Endpoint:** the same service, layer 123 (polygons).
- **What's there (Oct 7, 2026):** 6 areas in the ring. One is BLM's Big
  Grass Fire closure, which no other machine-readable source has: BLM Idaho
  publishes its orders only as pages and PDFs
  ([sources/lands.md](../../docs/sources/lands.md#blm-idaho-advisories-and-closures)).
  The others are BLM's Four Rivers OHV prohibition areas, the Mores Creek
  Summit parking restriction, and IDPR's copies of the Grimes Creek, Deer
  Point and Crooked Fire orders.
- **Keyed on** GlobalID. `kind` is `closure` when the type or name says
  closure or closed (or "Public Use Exclusion"), else `restriction`.

**Both IDPR layers.** robots.txt as for R4. The trails.idaho.gov robots
file redirects to an HTML page, and parksandrecreation.idaho.gov allows
everything. **Terms:** "Not for commercial use and may not be used in 3rd
party apps without source attribution". IDPR also calls other agencies'
content "representative": authoritative only at its source, so prefer
`usfs_r4_orders` where both have an order. **Republish:** aggregates, until
the owner decides whether to show the closures with credit. A courtesy note
to IDPR (maps@idpr.idaho.gov) is due
([docs/17 Q17](../../docs/17-sources-for-new-plugins.md#178-open-questions)).

## Not built here

- IDPR's park alert pages and park boundaries. The pages are HTML, and the
  catalogs verified no machine-readable listing. The boundary host,
  `gis2.idaho.gov`, is unreachable, so it counts as disallowed. IDPR's own
  park closures do appear in layer 127.
- The BLM Idaho advisories page and the Boise NF alerts page. Both are HTML
  and PDFs, entered by hand per the catalogs.
- IDL fire-restriction stages, another Wave A clock, outside this brief.

## Commands

```bash
python3 -m ingest run usfs_r4_orders idpr_route_closures idpr_area_restrictions
python3 -m unittest discover -s plugins/lands/tests -t .   # set TVT_TEST_DATABASE_URL for the database tests
```

**Storage:** about 2 MB holds today's 15 orders and closures across
`raw.record` and `evt.event`, mostly the fire closures' polygons. A new
version is written only when an order changes, so growth is well under
1 MB a day. The plugin also adds 72 `ops.fetch` rows a day. Download is
about 1 MB a day of metadata, plus 0.3 to 1.1 MB per full read.

**Ethics:** read-only queries; `ingest/http.py` refuses ArcGIS edit
operations. No PDFs or linked pages are fetched. Staff user names are
dropped. No people are described: the orders are about land.
