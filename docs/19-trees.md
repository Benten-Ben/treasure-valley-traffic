# 19. Trees

A layer of individual trees: every tree we can find in the lidar, plus the
trees the City of Boise has catalogued, drawn as low-poly 3D trees (crown
discs from farther out). Click one to see what we know about it and how we
know it. Agreed with the owner on Oct 8, 2026 ([DECISIONS](DECISIONS.md));
the pilot is the North End.

The experiments behind it are in the land-cover spike's work on the
project's server (crown separation, the owner's lone-tree picks, the crown
model and the placement tests, Oct 8).

## 19.1 Three kinds of tree

Like buildings, whose measured heights draw solid and estimated ones
lighter (§13.8), each tree says how much of it is measured.

| Kind | What it is | Drawn |
|---|---|---|
| **Catalogued** | A tree in a catalogue (today the City of Boise's park and street trees) that we found in the lidar: the catalogue's trunk point, species, trunk diameter and planting date; the lidar's height and crown | Solid |
| **Placed** | A tree we found in the lidar that no catalogue lists: yard trees, farm windbreaks, river cottonwoods, foothill brush, mountain forest. Height measured; crown and position estimated by placement (§19.3) | Lighter |
| **Estimated** | A catalogued tree the lidar doesn't show (planted after the flight, or still under 3 m): sized from its species and trunk diameter (§19.2) | Lightest, labelled "estimated" |

Where we have no lidar there are no trees, and the layer says so; it never
fills in from another source (the front-end rule in CLAUDE.md).

## 19.2 The crown model

How wide a crown can be for its height and type, and the shape of its top.

- **Width for height**, fitted on 137 lone trees the owner kept out of 154
  candidates in nine areas (Oct 8): valley broadleaf
  width ≈ 0.69 × H^1.01 (n = 58), narrow trees 0.58 × H^0.88 in the valley
  and 0.50 × H^0.89 in the mountains, a spread of about ±25% (one standard
  deviation). The valley broadleaf curve matches the US Forest Service's
  2005 measurements of 706 large broadleaf Boise street trees
  (0.67 × H^1.03) within about 3%. That is from the Urban Tree Database
  (McPherson, van Doorn & Peper 2016, RDS-2016-0005), where Boise is the
  reference city for its climate zone; the data "can be used without
  additional permissions or fees", with that citation.
- **Top shape:** a dome, z = H × (1 − a × (d/R)^n). For lone broadleaf trees
  a = 0.77 and n = 1.64 (the edge at about 23% of the height); for narrow
  trees a = 0.95 and n = 2.09. In a cluster, crowns meet high, so each type
  also has a crowded shape whose edge stays at about 55% (broadleaf) or 30%
  (narrow) of the height. The shape doesn't change with height (checked by
  height class).
- **Type:** width for height is the one cue that separates narrow from wide
  crowns here; the photo's near-infrared and the top's shape didn't (Oct 8).
  In the mountains, narrow means conifer. In the valley it is its own type
  ("narrow": spruce, young street trees, poplars) unless a catalogue says
  otherwise. Only about 1% of the North End's street trees are conifers.
- **Catalogued trees** also get their species' Urban Tree Database curves
  for Boise (crown diameter and height from trunk diameter), which size the
  estimated kind and guide the measured one.

The model is a small JSON file in the plugin (`plugins/trees/model/`),
rebuilt by hand when the owner picks more trees.

## 19.3 How trees are made

1. **Catalogued trees first.** Each catalogue tree planted before the
   lidar flight is looked for in the lidar: the highest point within 3 m of
   its trunk point. If that point is 3 m or taller, the tree is
   *catalogued*: its crown centre may sit up to 2.5 m off the trunk point
   (crowns lean and grow away from neighbours), its height is the lidar's,
   and its width comes from its species curve, checked against the lidar.
   If not, it is *estimated*.
2. **Then the placer fills the rest** (the owner's method, Oct 8): seeds
   are local peaks of the smoothed height, tallest first; a seed becomes a
   tree only where the height is well above what the trees placed so far
   explain (by at least 1 m or 15% of the height). Its crown is sized from
   the model for its height and type and placed where it best explains the
   height left over, keeping overlap with every neighbour within a share
   of the smaller crown (θ). Each tree must earn its place (a per-tree
   cost), and a crown wider or narrower than usual for its height pays a
   size cost. Leftover patches larger than the smallest crown are seeded
   again. A repair pass then tries deleting, moving, resizing, reshaping,
   splitting and merging trees, keeping any change that improves the fit.
   Catalogued trees stay: the repair may nudge them by up to 1 m, never
   delete them.
3. **The fit is the score** (the owner's idea): the trees rebuild a lidar
   surface (their crowns' upper envelope), and every choice is judged by
   how close it comes to the real one. The North End's city street trees
   are a second, independent check: how many the placer finds within 3 m,
   and how many extra trees it puts next to the street.

θ is the main count setting. It is calibrated on the North End's street
trees (§19.7).

## 19.4 Data

**Public plugin `trees`** (schema `trees`), holding only our own
lidar-derived data:

- `trees.tree`: one row per tree: area, kind, type, point (the crown
  centre), ground elevation, height, crown radius, crown shape, the lidar
  it came from, the catalogue and catalogue id if any, the fit (how well it
  explains the surface, or how far it sits from its trunk point), and the
  build it came from.
- `trees.tree_log`: what we know about each tree over time, one entry per
  event: measured by the 2023 lidar, matched to the catalogue, placed with
  a fit, and later a 2005 Forest Service measurement or a removal seen in
  newer lidar.
- `trees.build`: each build's area, settings, model and counts.

**Private plugin `city_trees`** (the private repository; schema
`city_trees`): the City of Boise's park and street trees, all of them,
read once a month from the city's Forestry map service (it adds a
last-verified date and condition to what the public layer has; its
robots.txt sets no rules). No licence is stated, only a disclaimer, so the
records stay private: never committed, published or tiled. The plugin
exposes the catalogue to the build (trunk points, species, diameter,
planting date) and its attributes to the app's tree panel on the owner's
own site. It is the first private plugin with code a service runs: the
`compose.private.yml` override mounts the private repository into the ingest
service (§15.3).

## 19.5 Building

`trees build` runs in the worker image (NumPy, SciPy, rasterio): it reads an
area's lidar height products and building mask, the crown model and, when
the private plugin is present, the catalogue. It writes the trees and their
log to the archive, and the ingest service loads them into PostGIS,
replacing the area's trees and keeping the build history. An area is
rebuilt when its catalogue changes (monthly) or new lidar arrives.

## 19.6 On the map

- **Close up (zoom 15 and in):** low-poly 3D trees in the scene engine
  (`#lib/scene`, §14.8), built in code like the buses: a round crown for
  broadleaf trees, stacked cones for conifers, a tall rounded column for
  narrow trees, each on a short trunk, scaled to the tree's crown and
  height, with a soft shadow. Kinds are told apart by tone, as with
  buildings (catalogued in full green, placed lighter, estimated lightest),
  and by name in the tree panel and the legend, never by color alone.
- **Farther out:** crown discs, in the same tones.
- **Click a tree:** its kind and how we know it; height and crown width;
  type; for catalogued trees the species, trunk diameter, planting date,
  last verified and condition; and its log.
- **Only where built:** elsewhere the layer says where trees exist so far.

**As built (Oct 8, `app/src/lib/layers/trees/`):**

- **API:** `GET /api/trees?bbox=w,s,e,n&limit=N` gives the trees whose point
  is in the box, tallest first (`limit` 4,000 by default, 8,000 at most),
  with `truncated` when there were more. `GET /api/trees/areas` gives where
  trees are built. `GET /api/trees/<id>` gives one tree with its log, newest
  first, and its catalogue entry when the private `city_trees.tree` is
  there (`catalogue: null` elsewhere). Before the plugin's migration every
  list is empty, never a 500.
- **Models:** `tree-broad`, `tree-cone` and `tree-column` in
  `#lib/scene/meshes.ts` (100, 68 and 100 triangles), after the concept
  models the owner saw. They have a unit crown radius and height, scaled
  [r, r, h], with a brown trunk and the crown in the tree's green. The
  greens are olive, three per type, at least ΔE 10 from every route color
  ([ch. 14's color budget](14-ui-v2.md#the-color-budget)).
- **Kinds by tone** (Oct 8, after the review): every tree draws solid.
  Placed trees mix a quarter of cream into their green (OKLab), estimated
  ones half, on the models, the discs, the legend and the panel. The first
  build dithered placed trees at 80% and estimated ones at 50%, which made
  most of the map's trees grey, speckled and see-through; the dither is now
  only for the disc-to-model crossfade. The discs keep a thin dark edge, so
  an estimated disc's swatch keeps 3:1 against the legend card.
- **Zooms:** crown discs from z13; the scene engine is asked for at z14.5;
  models dither in over 14.7–15 as the discs fade out. The discs' fade
  depends on the zoom alone: MapLibre evaluates an expression of zoom and a
  feature's value only at whole zooms and blends between them, so a fade
  that also read each kind's opacity started at z14. The view's trees are
  asked for 250 ms after the map stops, in a box a quarter bigger than the
  view and kept within a screen diagonal of the centre. Only the newest
  request lands: one the view no longer wants is called off. Nothing is
  asked for where no area is built.
- **Credit:** the map's attribution credits the trees (USGS 3DEP lidar,
  City of Boise, US Forest Service) at every zoom they're drawn, through a
  layer that matches no tree (MapLibre credits a source only while one of
  its layers is shown, and the discs stop at z15).
- **Picking:** trees rank just under streets, so a click on a road under a
  crown still opens the road. A model's hit area is a capsule from its
  trunk to its top, as wide as its crown, not its bounding sphere (the
  scene engine's opt-in `pickRadius`), so a tall tree is picked anywhere
  along it with the map tilted. Where trees overlap on screen, the one
  nearest the camera wins. A selected tree stays on the ground at its size
  (the engine's `grounded`): the ground ring marks it.
- **Measured (Oct 8, owner's laptop, headless Chromium on the M1 GPU):**
  15,000 synthetic trees around the North End box, viewed at z16 with
  pitch 50 while rotating. With 1,000, 2,000, 3,000 and 4,000 trees handed
  to the scene (613 to 2,552 drawn), frames held 16.7 ms (60 fps), and the
  scene's JS took a median 0.9, 1.5, 2.3 and 3.1 ms a frame. With Transit,
  Cameras and Streets on as well, 4,000 trees still held 16.7 ms, at 4.0 ms
  of scene JS. So the cap is the API's close-up limit: the tallest 4,000
  trees in view, and the legend says so when it applies. Under SwiftShader
  (the test browser) a frame takes hundreds of ms at any count. Measured
  again with the hit capsules (two more projections per tree): still
  16.7 ms at every count, at a median 1.1, 2.2, 3.0 and 4.1 ms of scene JS
  (95th percentile 7.4 ms at 4,000).

## 19.7 The pilot: North End

The North End box on the preview site first, with θ set from the street
tree scores, then the other test areas. Trees across the whole valley wait
for lidar height products beyond the test areas ([DEFERRED](DEFERRED.md)).
