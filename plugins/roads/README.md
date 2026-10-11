# roads

The road network as data ([docs/15 §15.4](../../docs/15-plugins.md#154-the-plugins-we-already-have)):
ACHD's road segments (the Streets layer's data), the lane inventories, and
OpenStreetMap's ways, lanes and signal nodes, all matched to ACHD's segments
by core's line matcher ([ingest/linematch.py](../../ingest/linematch.py)). The
base map's streets (for drawing) stay in core (`basemap/`).

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `achd_roads` | weekly | none stated | Ada County Highway District | internal |
| `itd_hpms` | monthly | none stated | Idaho Transportation Department | internal |
| `achd_msm` | monthly | none stated | Ada County Highway District | internal |
| `compass_centerline` | monthly | none stated (disclaimer only) | COMPASS and its member agencies | yes (open-data hub) |
| `osm_valley` | by hand | ODbL | © OpenStreetMap contributors | yes, as ODbL |
| `osm_street` | by hand | ODbL | © OpenStreetMap contributors | yes, as ODbL |

"Internal" for ACHD's and ITD's layers means no license is stated and the
owner hasn't decided on republishing; they're shown only on the owner's own
map. Details of each source: [ingest/README.md](../../ingest/README.md).

**OpenStreetMap.** Both OpenStreetMap sources are consumers of core's loader
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
- Later in the sprint: `osm_paving` (P8: other service ways, sidewalks,
  crossings, lots), in `roads.osm_paving`.

The lane-tagged cycleways, tracks and pedestrian ways that `osm_valley`
already keeps (12 in the Oct 5 extract) stay in `core.osm_way`; trails reads
them through a view.

**Tables:** `core.road_segment`, `core.segment_match`, `core.hpms_section`,
`core.msm_arterial`, `core.compass_segment`, `core.osm_way`, `core.osm_lane`,
`core.osm_node`, and the `core.segment_lanes` view with its four per-source
views (migrations 0004, 0011, 0016–0018 in `db/migrations/`); in schema
`roads`: `roads.osm_street` (`migrations/0001`).

**Code:** `ingest/sources/` (the sources and consumers), `ingest/segment_match.py`
(matching to ACHD's segments with core's line matcher, and
`core.segment_match`), `ingest/streets.py` (street names made comparable; the
intersections plugin uses it too).

**Commands:**

```bash
TVT_ARCHIVE=data/archive python3 -m ingest osm-load --inbox            # an OSM extract downloaded by hand (needs osmium-tool)
TVT_ARCHIVE=data/archive python3 -m ingest osm-load --only osm_street  # this consumer, on the extract we hold
python3 -m ingest segment-match [itd_hpms achd_msm compass_centerline osm_valley]
python3 -m unittest discover -s plugins/roads -t .
```

**Ethics:** Geofabrik's robots.txt disallows scripted downloads of its
extracts (Oct 6, 2026), so the owner downloads the Idaho extract in a
browser; neither OpenStreetMap source has download code or a schedule.
Loading the remaining street classes was approved by the owner on Oct 8
(decision 2a). Anything we publish that's derived from OpenStreetMap stays
ODbL.
