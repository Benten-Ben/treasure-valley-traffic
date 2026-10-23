# fences

The valley's **mapped** fences, walls, retaining walls, guard rails, jersey barriers and hedges, and its gates,
bollards and cattle grids, from OpenStreetMap's held Idaho extract (landscape sprint, Oct 2026, package P10). The
map's fences layer reads `fences.fence`, and the shrubs' hedge check reads its hedges
([docs/19 §19.8](../../docs/19-trees.md#198-shrubs)). Readings are versioned in place in schema `fences`
(migration 0001); no `raw.record` copies.

**What this is not.** Most backyard fences aren't mapped, so the layer is never a count of fences or a picture of
what is fenced. And a fence is never a property line, a lot boundary or a statement of who owns what is behind it
(owner's decision, Oct 8, 2026): the layer only says where a contributor drew a barrier.

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `osm_barriers` | by hand, with each extract (`osm-load`) | ODbL | © OpenStreetMap contributors | yes |

## `osm_barriers`: the barrier lines and gates

A consumer of core's OpenStreetMap loader ([`ingest/osm_extract.py`](../../ingest/osm_extract.py)). No download, no
schedule, no request: the owner downloads the extract in a browser (Geofabrik's `robots.txt` disallows scripts),
and

```bash
python3 -m ingest osm-load --inbox                      # a new extract: every consumer
python3 -m ingest osm-load --only fences.osm_barriers   # this one, on the extract we hold
```

loads it, with its own MD5 gate in `ops.osm_consumer`.

- **`fences.fence`** (`fence_id` `osm:w<id>`): ways tagged `barrier=` fence, wall, retaining_wall, guard_rail,
  jersey_barrier or hedge, and a few others (city_wall, cable_barrier, handrail, wire_fence) as type `other`.
  Other barrier values on lines (kerbs, ditches) are left out. `type` is the class, `kind` the tag as mapped,
  `look` is `solid` or `open` ⚠️ from the tags (walls, retaining walls, jersey barriers and hedges solid; a fence
  solid when its `fence_type` or `material` says boards, panels, brick, stone or concrete), and `height_m` is the
  `height` tag when it reads as metres or feet (`height_source` `tagged`), else an estimate by type ⚠️
  (`default`). Hedges are stored here for the hedge check (`fence_id`, `type`, `geom` and `active`) and are not
  drawn as fences.
- **`fences.gate`** (`gate_id` `osm:n<id>` or `osm:w<id>`): gates, lift gates, bollards, blocks and cattle
  grids, with their `access` tag. A gate mapped as a way sits at its middle vertex.
- **Versions.** An object seen again is updated; one missing from a load becomes inactive and is never deleted;
  a load refuses to retire when it brings fewer than half the active objects (`--allow-shrink` overrides).
  Each load adds a `core.layer_version` row for `fences.lines` (ODbL, republish yes) for the app's versioned
  GeoJSON.
- **Credit.** "© OpenStreetMap contributors"; anything published from these tables stays ODbL.

## Tests

```bash
python3 -m unittest discover -s plugins/fences -t .      # with TVT_TEST_DATABASE_URL for the database tests
```

Synthetic OSM only (invented ids and coordinates). The pipeline test needs `osmium-tool` (the ingest image).
