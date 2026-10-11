# trees

Every tree we can find in the lidar, catalogued trees first ([docs/19](../../docs/19-trees.md)).

- `model/crown_model.json`: how wide a crown is for its height and type, and the shape of its top, fitted on the 137 lone
  trees the owner kept on Oct 8, 2026. `model/utd_boise.json`: height and crown width from trunk diameter for 16 genera,
  fitted here on the Boise trees in the US Forest Service's Urban Tree Database (McPherson, van Doorn & Peper 2016,
  RDS-2016-0005; "can be used without additional permissions or fees", with that citation).
- `build/place.py`: the crown placer. `build/build.py`: builds one area in the worker image (NumPy, SciPy, rasterio):
  catalogued trees first (from a catalogue's trunk points, when given), then the placer, then a repair pass. A placed
  tree is narrow by the narrow rule, not by the width curve that sized it: its crown falls 45-95% of its height within
  3 m of an even top that is its own (under 2 m above its height) and 8.3 m or higher (docs/19 §19.3). Otherwise it is
  a conifer when the spring cue sees an evergreen crown: with `--spring` and `--summer` (the early-April and July 2025
  Sentinel-2 NDVI on the ground's 10 m grid), a crown of 50 m² or more whose April NDVI is 0.2 or more where at least
  half the April views around it were snow. In the valley the April lawns are as green as an evergreen at 10 m, so the
  cue only tells in the mountains, and it types trees only in areas where its calls were checked against the owner's
  labels (`SPRING_CHECKED_AREAS`: Bogus Basin, `h`, so far); elsewhere it is kept in the fit but types nothing. Otherwise
  it is broadleaf, or conifer where the conifer curve sized it
  (`KEEP_WIDTH_CONIFER`, pending the owner). The fit keeps the curve, the crown's profile and its spring cue. It writes
  `trees.geojson`, `log.jsonl` and `build.json` (with the Sentinel-2 files' sha256 and the sources it read) to a build
  folder.
- `python3 -m ingest trees-load --build DIR` loads a build: the area's trees are replaced, its log events added.
- Tables: `trees.build`, `trees.tree`, `trees.tree_log` (migrations/0001_trees.sql).
- Sources (`plugin.json`, each a manual source with a module stating its licence and credit, in `ingest/sources/`):
  the USGS 3DEP lidar (public domain), Sentinel-2 (Copernicus: "Contains modified Copernicus Sentinel data 2025") and
  OpenStreetMap's hedges (ODbL; the shrubs' hedge check, docs/19 §19.8). The build never reads a catalogue unless
  `--anchors` names one.

The settings were calibrated on the North End's city street trees on Oct 8 (overlap limit 0.2: 76% of 941 street trees
found within 3 m, the fewest extra trees, and a closer rebuild of the lidar than any height-only rule).

Tests: `python3 -m unittest plugins.trees.tests.test_load`; the placer's, the narrow rule's and the spring cue's tests
need NumPy, SciPy, rasterio and pyproj (the worker image, where a skip counts as a failure). On the VM:
`worker-test -C <checkout> plugins.trees.tests.test_place plugins.trees.tests.test_narrow plugins.trees.tests.test_spring`.
