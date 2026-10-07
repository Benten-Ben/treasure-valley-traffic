# roads

The road network as data ([docs/15 §15.4](../../docs/15-plugins.md#154-the-plugins-we-already-have)):
ACHD's road segments (the Streets layer's data), the lane inventories, and
OpenStreetMap's ways, lanes and signal nodes, all matched to ACHD's segments
by the shared segment matcher. The base map's streets (for drawing) stay in
core (`basemap/`).

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `achd_roads` | weekly | none stated | Ada County Highway District | internal |
| `itd_hpms` | monthly | none stated | Idaho Transportation Department | internal |
| `achd_msm` | monthly | none stated | Ada County Highway District | internal |
| `compass_centerline` | monthly | none stated (disclaimer only) | COMPASS and its member agencies | yes (open-data hub) |
| `osm_valley` | by hand | ODbL | © OpenStreetMap contributors | yes, as ODbL |

"Internal" for ACHD's and ITD's layers means no license is stated and the
owner hasn't decided on republishing; they're shown only on the owner's own
map. Details of each source: [ingest/README.md](../../ingest/README.md).

**Tables:** `core.road_segment`, `core.segment_match`, `core.hpms_section`,
`core.msm_arterial`, `core.compass_segment`, `core.osm_way`, `core.osm_lane`,
`core.osm_node`, and the `core.segment_lanes` view with its four per-source
views (migrations 0004, 0011, 0016–0018 in `db/migrations/`).

**Code:** `ingest/sources/` (the sources), `ingest/segment_match.py` (the
shared matcher), `ingest/streets.py` (street names made comparable; the
intersections plugin uses it too), `ingest/osm_load.py`.

**Commands:**

```bash
TVT_ARCHIVE=data/archive python3 -m ingest osm-load --inbox    # an OSM extract downloaded by hand (needs osmium-tool)
python3 -m ingest segment-match [itd_hpms achd_msm compass_centerline osm_valley]
python3 -m unittest discover -s plugins/roads -t .
```

**Ethics:** Geofabrik's robots.txt disallows scripted downloads of its
extracts (Oct 6, 2026), so the owner downloads the Idaho extract in a
browser; `osm_valley` has no download code and no schedule. Anything we
publish that's derived from OpenStreetMap stays ODbL.
