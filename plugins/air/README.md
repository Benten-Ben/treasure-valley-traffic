# air

Smoke and air quality over the valley
([docs/17 §17.2, "Fire and hazards"](../../docs/17-sources-for-new-plugins.md#fire-and-hazards)).
For now, one source: NOAA's Hazard Mapping System (HMS) smoke polygons for
the days around today, kept for the ones that touch the regional ring.

**Why now:** this is Wave A, "start the clocks"
([§17.4](../../docs/17-sources-for-new-plugins.md#174-proposed-order-with-rough-effort)).
NOAA rewrites each day's smoke file as the analyses land and keeps only the
final one, so the same-day versions (what had been drawn by noon, by
evening) exist only if we poll. Ingest only: no new tables, no migrations,
no map layer yet.

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `noaa_hms_smoke` | every 30 min (a ~2 KB listing; a file only when it changed) | public domain (U.S. Government work, NOAA) | NOAA NESDIS OSPO Hazard Mapping System | yes, with NOAA's caveats (below) |

## noaa_hms_smoke

- **What:** analyst-drawn smoke polygons rated light, medium or heavy, each
  with its satellite (GOES-East, GOES-West, ...) and the start and end of
  the imagery it was drawn on. Catalogs:
  [hazards.md, "NOAA Hazard Mapping System"](../../docs/sources/hazards.md#noaa-hazard-mapping-system-hms-fire-points-and-smoke-polygons)
  and [gardening.md, "Heat, smoke, air and alerts"](../../docs/sources/gardening.md#noaa-hazard-mapping-system-hms-smoke-polygons).
- **Endpoint:** one national KML a day,
  `https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/Smoke_Polygons/KML/YYYY/MM/hms_smokeYYYYMMDD.kml`
  (62–454 KB in early October 2026), and the month folder's directory
  listing, whose times are UTC (they match each file's "Generated" stamp).
- **Cadence:** the day's file is listed, empty, before the first analysis
  (we saw it at 13:43 UTC on Oct 7), is rewritten after each analysis (the
  first 11 AM–12 PM ET, the second 7–8 PM ET) and is finalised about
  10:00 UTC the next morning. We read the listing every 30 minutes and
  download today's, yesterday's and the day before's file (UTC) only when
  the listing shows it changed since our last look (with a 10-minute
  margin for the listing's minute resolution), 3 s apart. A typical day is
  48 listings and a handful of file downloads.
- **robots.txt:** no rules on `satepsanone.nesdis.noaa.gov` (the catalog
  saw a 404; `ingest/http.py` read it as "no rules" again on Oct 7).
  `www.ospo.noaa.gov`, which we don't request, has a `*` group with no
  Disallow lines (per the catalog).
- **What we keep:**
  - a changed file, as published and gzipped, in
    `$TVT_ARCHIVE/air/hms/YYYY/MM/hms_smokeYYYYMMDD-<generated>-<digest>.kml.gz`,
    once per distinct content (a file NOAA regenerates without changes
    isn't kept again). Without `TVT_ARCHIVE` nothing is archived;
  - in `raw.record`, per changed file: one record for the file
    (`20261006`: analysis date, generation time, a digest of its smoke,
    national counts by density and satellite, how many touch the ring), and
    one per polygon that touches the ring, whole and unclipped, with its
    published fields, normalised density, satellite, start and end
    (`20261006/GOES-WEST/20261006T1200Z-20261006T1500Z/light/1`: day,
    satellite, imagery window, density, then an ordinal, so a later
    analysis doesn't renumber earlier ones). Presentation-only parts
    (styles, draw order, the overlays' chart images) are dropped.
  - Each day's file is a full snapshot of its own day: when it changes,
    that day's records missing from the new version (and the file's old
    version) get `removed_at`, so a day's current records are the ones
    with `removed_at` null. An unchanged file only moves `last_seen`.
  - A changed file with less than half the polygons of its last version
    (once that had 5 or more) is refused: nothing of that day is written,
    though the file is already archived. A day's analysis only grows, so
    that looks like a cut-off file.
  - Each day is stored on its own: a day whose file is refused, cut off or
    missing doesn't hold back the others. They're stored, then the run
    fails naming the file, so `ops.fetch` logs it, and the file is tried
    again on the next run.
  - A new month's folder may not exist yet in the first hours of the 1st
    (UTC), so until then its listing (404) counts as empty. A listing that
    names no smoke files at all fails the run.
- **The ring:** west −117.30, south 42.90, east −115.60, north 44.30, the
  regional ring in [DECISIONS](../../docs/DECISIONS.md), adopted for the new
  plugins' regional data on Oct 7 and used by the 511 sources. A polygon
  counts if it meets the ring (a real intersection test, not just bounding
  boxes).

**Caveats to carry into any use** (hazards.md): HMS shows smoke anywhere in
the column, not at the ground, so it isn't air quality; analyses are daytime
only and clouds hide smoke; NOAA says positions "may be slightly offset"
and the product is for strategic, not tactical, use. Densities were numbers
(5, 16, 27) before July 19, 2022; the poller maps those to light, medium and
heavy too, for a later backfill. Polygons are stored as drawn: some are
zero-area slivers or self-touching, so use `ST_MakeValid` before area maths.

**Not here (yet):** AirNow waits for the owner to return its Data Exchange
Guidelines form and notify Idaho DEQ ([§17.7](../../docs/17-sources-for-new-plugins.md#177-owner-actions-consolidated)).
PurpleAir and DEQ's crop-burn decisions are off-limits (robots.txt;
[§17.6](../../docs/17-sources-for-new-plugins.md#176-refuted-and-risky-sources)).
HMS fire points, GOES smoke masks, HRRR-Smoke and EPA AirData come later.
Smoke polygons could also become lifecycles in `evt.event` once replay
needs them; their start and end are already in each record.

**Tables:** none of its own; versions in core's `raw.record`.

**Commands:**

```bash
TVT_ARCHIVE=data/archive python3 -m ingest run noaa_hms_smoke
python3 -m unittest discover -s plugins/air/tests -t .
```
