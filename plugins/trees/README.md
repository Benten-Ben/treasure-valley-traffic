# trees

Every tree we can find in the lidar, catalogued trees first ([docs/19](../../docs/19-trees.md)).

- `model/crown_model.json`: how wide a crown is for its height and type, and the shape of its top, fitted on the 137 lone
  trees the owner kept on Oct 8, 2026. `model/utd_boise.json`: height and crown width from trunk diameter for 16 genera,
  fitted here on the Boise trees in the US Forest Service's Urban Tree Database (McPherson, van Doorn & Peper 2016,
  RDS-2016-0005; "can be used without additional permissions or fees", with that citation).
- `build/place.py`: the crown placer. `build/build.py`: builds one area in the worker image (NumPy, SciPy, rasterio):
  catalogued trees first (from a catalogue's trunk points, when given), then the placer, then a repair pass. It writes
  `trees.geojson`, `log.jsonl` and `build.json` to a build folder.
- `python3 -m ingest trees-load --build DIR` loads a build: the area's trees are replaced, its log events added.
- Tables: `trees.build`, `trees.tree`, `trees.tree_log` (migrations/0001_trees.sql).

The settings were calibrated on the North End's city street trees on Oct 8 (overlap limit 0.2: 76% of 941 street trees
found within 3 m, the fewest extra trees, and a closer rebuild of the lidar than any height-only rule).

Tests: `python3 -m unittest plugins.trees.tests.test_load`; the placer's tests need NumPy and SciPy (the worker image):
`python -m unittest test_place` from `plugins/trees/tests`.
