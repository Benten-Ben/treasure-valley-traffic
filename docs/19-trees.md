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
- **Type:** on lone trees, width for height separates narrow from wide
  crowns; the photo's near-infrared and the fitted dome's shape didn't
  (Oct 8). Among other trees it doesn't: neighbours squeeze crowns, and on
  the owner's labelled trees the width fit's narrow and conifer calls were
  mostly wrong. So whether a placed tree is narrow comes from how fast its
  crown falls away from its top (the narrow rule, §19.3), and whether it is
  a conifer from a spring Sentinel-2 image where that can tell and its
  calls have been checked (over Bogus Basin's April snow so far, §19.3);
  the width curve sizes and shapes the crown, and elsewhere for now still
  makes the conifer call (pending, §19.3). In the mountains, narrow means conifer. In the valley it is its
  own type ("narrow": spruce, young street trees, poplars) unless a
  catalogue says otherwise. Only about 1% of the North End's street trees
  are conifers.
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

**One rule everywhere, checked by the owner (Oct 8).** Every tree tries the
three width curves (broadleaf, conifer, narrow) and keeps the best fit;
there is no switch by area. The owner typed 100
larger trees from eight test areas (from 50 m views of the photo, the lidar
heights and a height profile): 46 broadleaf, 20 conifer, 8 narrow, 20 part
of a bigger tree and 6 not a tree. What that showed:
- **Extra trees on big crowns.** The placer puts small trees on the flanks
  of large crowns. A per-tree cost of 40 (was 20) removes about a quarter
  of the fakes while keeping 73 of the 74 real trees and the same share of
  city street trees (78% within 3 m); 80 removes more fakes but a third of
  all trees, mostly small ones no test covers yet.
- **Narrow trees** fall away fast: a crown that drops 45% of its height
  within 3 m of its top caught all 8 (and 12 of 66 others).
- **The narrow rule, tightened (Oct 11).** A placed tree is narrow when its
  crown falls 45% of its height within 3 m of its top but stops short of
  the ground there (under 95%), from an even top (the heights within 1 m of
  it vary by under a fifth of its height; a broken crown edge or a top
  between crowns overstates the fall). The top is the crown's highest lidar
  point, unsmoothed. It must be the tree's own: less than 2 m above the
  tree's height, which comes from the smoothed surface and usually sits
  under 1 m lower (a higher top is a neighbour's crown or a roof). And it
  must be 8.3 m or more, where a typical broadleaf crown with that top
  reaches 3 m out (the width curves were fitted on the lone trees' tops);
  below that, what lies 3 m out is the neighbourhood, not the crown. So a
  narrow tree's height, as the map gives it, can be under 8.3 m (down to
  about 6.3 m). The width curve that fits a crown still sizes and shapes
  it, but its narrow call isn't kept: on the labels, 2 of its 23 narrow
  calls were narrow trees.
- **How well it does.** Rebuilt on the eight labelled areas' central 500 m
  (the placement itself unchanged: the same 10,992 trees), the rule calls 7
  of the 8 narrow trees narrow and 2 of the 65 others (one broadleaf, one
  conifer), where the width fit called 2 and 21; the build types 51 of the
  73 real trees it finds rightly (the width fit: 35, the Oct 8 rule: 46).
  These scores are in-sample: the 95% cap and the even-top limit were
  chosen on the same trees. Choosing the cut-offs on 73 of the real
  labelled trees and typing the one left out, in turn, catches 4 to 6 of
  the 8 narrow trees (depending on which of the equally good cut-offs is
  taken) and calls 2 of the 66 others narrow. With only 8 narrow trees,
  that is a rough guide. In the windows 6% of the trees come out narrow;
  179 of the 649 are under 8.3 m tall (the lowest 6.7 m), all with tops of
  8.3 m or more. The own-top check took out 27 narrow calls whose top stood
  2–10 m above the tree; no labelled tree was among them.
- **Where it can't tell.** Tops under 8.3 m (too few labelled trees are
  that short to set a cue there, so short junipers and young columnar trees
  aren't called narrow; one labelled juniper with a 7 m top is missed),
  tops that aren't the tree's own, and crowns that end within 3 m. By the
  model's curves a lone narrow crown ends within 3 m up to about 14 m tall,
  and a lone mountain conifer up to about 16 m, so a lone yard spruce or an
  open-stand conifer below those heights isn't called narrow either: in the
  windows, 166 of the 3,418 trees with their own top of 8.3 m or more.
  These trees are conifer where the spring image types them (Bogus Basin
  so far) or, for now, where the conifer curve sized them, else broadleaf
  (the next points). Letting the width fit's narrow call stand for crowns that
  end within 3 m was tried: on the labels it typed no more trees rightly
  and called two more conifers narrow, so it isn't used.
- **Conifers from a spring image (Oct 11).** Evergreen crowns are green in
  early April, when broadleaf crowns are still bare (decision 24 of the
  landscape sprint, Oct 8). The image is Sentinel-2's NDVI from April 4
  and 5, 2025 (10 m; "Contains modified Copernicus Sentinel data 2025"),
  set against July 2025's. Each placed crown gets its April and July
  greenness over the 10 m cells it covers (weighted by its area in each).
  In the valley that can't tell: by early April the lawns, pastures and
  cheatgrass under and around the crowns are green too, and a yard tree is
  a fifth of a cell, so a bare broadleaf crown reads about as green as an
  evergreen one. Of the owner's 40 labelled valley broadleaf trees, 9 read
  at least as green in April as the least green of the 4 labelled valley
  conifers (NDVI 0.54), and 16 keep at least as much of their July
  greenness (69%); unmixing each cell's canopy share, from the lidar,
  didn't separate them either. Over snow it can: the ground reads white,
  so only evergreen foliage is green. So a crown reads evergreen when at
  least half the clear April views within 50 m of it were snow, it is at
  least half a 10 m cell (50 m², so the cells' colour is mostly its own),
  and its April NDVI is 0.2 or more. Where the cue's calls have been
  checked (below), that makes it a conifer, after the narrow rule. A crown
  that reads dark over snow may still be a conifer (laden with snow, or a
  few metres off the image's cells: two labelled conifers do), so the cue
  says nothing about it. July's greenness is kept with each tree but
  doesn't enter the call: over snow it added nothing on the labels.
- **How well it does.** On the eight labelled areas (the placement
  unchanged), the cue catches 9 of the 20 labelled conifers, all in Bogus
  Basin; the build types 60 of the 73 real trees it finds rightly with the
  width fit's conifer call dropped (51 before), 59 with it kept. It misses
  the 4 valley conifers (no snow, and crowns of 12–40 m²), 5 small Bogus
  Basin conifers and the 2 that read dark over snow. These scores are in-sample: the
  snow-only rule and the half-cell floor were settled while looking at
  them.
- **Its false calls over snow are untested.** No labelled broadleaf or
  narrow tree over snow has a crown of 50 m² or more: every real tree the
  owner labelled in Bogus Basin is a conifer (from a draw that took the old
  build's broadleaf and conifer calls alike), and Silver City's 5
  broadleaf and 5 narrow trees are 8–36 m². So none of the 53 other real
  trees could have been called conifer, and that none was (nor in a
  leave-one-out over the two floors) says nothing about false calls. What
  the Silver City labels do show is against the NDVI floor: over snow its
  5 broadleaf trees read 0.055, 0.182, 0.199, 0.221 and 0.295, and the two
  over 0.2 are as green as 4 of the 9 conifers caught in Bogus Basin
  (0.201–0.246; the others 0.343–0.55). Only the crown floor kept them
  out, and 47 of the 103 crowns
  (not narrow) the cue sees evergreen in Silver City's window read
  0.20–0.30 (Bogus Basin: 56 of 163). In the Owyhees some evergreen trees
  aren't conifers (curl-leaf mountain mahogany keeps its leaves ⚠️).
- **Where it types trees: Bogus Basin, for now (Oct 11).** The cue types
  trees only in an area where its calls were checked against the owner's
  labels (`SPRING_CHECKED_AREAS` in the build): so far Bogus Basin, where
  its 10 calls among the labelled crowns were 9 conifers and one part of a
  bigger tree. Even there a broadleaf crown green over the snow would be
  called conifer, but none was labelled. In Silver City, and in any area
  not yet checked, the cue is kept with each tree but types nothing, until
  the owner labels a sample of that area's large crowns that read green
  over the snow ([DECISIONS](DECISIONS.md#pending-owner-to-decide)). In the
  windows it types 163 of Bogus Basin's 1,315 trees conifer; it sees 114
  of Silver City's 3,669 evergreen but types none; and none in the valley.
- **Where the spring image can't tell.** Anywhere without April snow,
  which in 2025 means the whole valley and the foothills below about the
  snow line; crowns under 50 m² (a lone tree under about 8 m wide); and
  trees whose cells read dark over snow. Those trees are narrow,
  broadleaf, or conifer where the conifer curve sized them (next points).
- **In the mountains most trees stay broadleaf.** Over snow, a crown the
  cue can't type falls back as a valley tree does. In Bogus Basin's window
  it can tell for 337 of the 1,315 trees and sees 177 evergreen; 1,055
  trees stay broadleaf without the width fit's conifer call and 980 with
  it, though every real tree the owner labelled there is a conifer, and the
  7 labelled conifers the cue misses stay broadleaf either way. A default
  of "over snow, conifer unless the cue reads the crown dark" would catch
  14 of Bogus Basin's 16 labelled conifers and type 1,087 of its window's
  trees conifer, but it would also make all 5 of Silver City's labelled
  broadleaf trees conifers (and 3,313 of that window's 3,669 trees). So it
  would need checked areas too. Whether to have it, or more labels first,
  is the owner's call ([DECISIONS](DECISIONS.md#pending-owner-to-decide)).
- **The width fit's conifer call: pending (Oct 11).** Where the spring
  cue doesn't type a tree, a placed tree the narrow rule doesn't call
  narrow keeps the width fit's conifer call until the owner decides
  ([DECISIONS](DECISIONS.md#pending-owner-to-decide)). That call is weak:
  of the 14 labelled trees the Oct 8 build called conifer, one was (ten
  weren't trees of their own). It puts cones on 7–8% of the North End's
  and downtown's trees 8 m and taller, where about 1% of the North End's
  street trees are conifers. The photo's darkness only looked like a cue
  because the forest area's photo is darker. Proposed: drop it, so that
  the spring cue and a catalogue's genus say conifer.

## 19.4 Data

**Public plugin `trees`** (schema `trees`), holding only our own
lidar-derived data:

- `trees.tree`: one row per tree: area, kind, type, point (the crown
  centre), ground elevation, height, crown radius, crown shape, the lidar
  it came from, the catalogue and catalogue id if any, the fit (how well it
  explains the surface, the width curve that sized it and its width
  against that curve's typical one, how its crown falls from its top, and
  its spring cue: its April and July NDVI, the April snow around it, its
  crown area, whether it read evergreen and whether the cue types trees in
  its area; or how far it sits from its trunk point), and the build it
  came from.
- `trees.tree_log`: what we know about each tree over time, one entry per
  event: measured by the 2023 lidar, matched to the catalogue, placed with
  a fit, and later a 2005 Forest Service measurement or a removal seen in
  newer lidar.
- `trees.build`: each build's area, settings, model, sources (the lidar,
  and Sentinel-2's acquisitions and files' sha256) and counts.

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
area's lidar height products and building mask, the crown model, the
early-April and July Sentinel-2 NDVI on the ground's 10 m grid
(`--spring`, `--summer`; each read once by hand, with its provenance
beside it on the server) and, when the private plugin is present, the
catalogue. The plugin's manifest lists its sources with their licences:
the 3DEP lidar, Sentinel-2 and OpenStreetMap's hedges (the shrubs' check,
§19.8). It writes the trees and their log to the archive, and the ingest
service loads them into PostGIS, replacing the area's trees and keeping
the build history. An area is rebuilt when its catalogue changes
(monthly) or new lidar arrives.

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
  City of Boise, US Forest Service, and "contains modified Copernicus
  Sentinel data 2025" for the conifer cue; a tree the spring image typed
  says so on its card) at every zoom they're drawn, through a
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

## 19.8 Shrubs

Shrubs become plants too: each one a position, height, width and look,
drawn as low-poly shrubs beside the trees. The owner settled the approach
on Oct 8 ("no classification by place ... figure out what combination of
settings gives the best tradeoff across our tests") and left the rest to
the lead ("I'm fine with you thinking through and settling all of this
however you see fit"). The experiments ran on the ten land-cover test
areas' central 500 m on the project's server.

**What counts.** Woody plants 0.3–2.4 m tall; from 2.4 m up a plant belongs
to the trees (§19.3). One rule everywhere: a 0.5 m lidar cell in that band
that isn't a building is a shrub when the summer photo's near-infrared
calls it green (each area's own NDVI cut) **or** the lidar calls it a plant
(at least 3 returns above the ground, with a scatter of 0.25 or more). In
the 1 m ring around buildings only green cells count, since the rest there
are roof slivers. This was the best of 132 settings (lowest band
0.3 or 0.5 m; near-infrared, lidar or either; the lidar cut-offs; a 1 m
vote) on three checks at once: agreement with RCMAP's 2023 shrub cover
per 30 m pixel, shrubs on building edges, and green cells kept.

**Cleaning.** The first images showed four kinds of false shrub, each
dropped by a rule that doesn't depend on where the shrub is:

- **A crown's skirt:** a clump whose top leans on a tree (a cell 2.4 m or
  taller within 1 m of its top stands higher than it). These are the low
  edges of tree crowns.
- **A gap in a crown:** a clump whose surrounding ring is mostly tree.
- **A speck:** one cell, or two under 0.6 m. In Dry Creek's grass the lidar
  is striped with them.
- **A crop:** a 25 m block where at least 15% of the cells are in the shrub
  band, at least 90% of those are green, their heights are even (spread
  under 0.35 m) and nothing but roofs stands over 1.5 m. Neighbouring
  blocks just as green and low join it, and so does green, low ground
  connected to it up to 30 m out. In the ten areas this caught 69 of the
  72 blocks of the NY Canal crop field and nothing anywhere else. Shrubland
  is never all green in July, and almost always has something taller
  nearby.

**Checked against RCMAP** (USGS's rangeland cover maps, 2023, 30 m; shrub
and tree cover per pixel). Where the land is open, our shrubs plus
everything woody above 2.4 m match RCMAP's shrub plus tree cover. In the
mountains RCMAP calls much more of it shrub than we do, but the total is
the same:

| Area | RCMAP shrub + tree | Ours: shrub + woody ≥ 2.4 m |
|---|---|---|
| Dry Creek foothills | 12.1 + 3.8 = 15.8% | 8.9 + 6.6 = 15.5% |
| Bogus Basin | 20.2 + 8.7 = 28.9% | 3.5 + 25.3 = 28.8% |
| Silver City | 31.2 + 18.1 = 49.2% | 1.7 + 39.1 = 40.7% |
| Barber Pool | 8.8 + 6.6 = 15.4% | 2.5 + 19.5 = 22.0% |
| Initial Point desert | 1.5% | 0.2% |
| Owyhee front | 0.7% | 0.2% |

So the mountain difference is where the line between shrub and tree falls
(mountain mahogany and bitterbrush 2.4–6 m tall are trees to us), not
plants we miss. A rule that counted wide, low woody plants up to 6 m as
shrubs closed only a tenth of that gap and added shrubs to valley yards.
Barber Pool's riverside trees are real trees that RCMAP undercounts. So
RCMAP stays a check: no top-up from it, and no second shrub line.

**Shrubs from clumps.** The width a shrub has for its height comes from
277 isolated, compact, single-topped clumps: **bush** width 1.48·H^0.25 m
(225 shrubs) and **sage** width 1.28·H^0.15 m (52), spread ±0.17 in log
width. The slopes are shallow partly because the 0.5 m cells make shrubs
under about 1 m across look wider than they are. In each clump the peaks
are taken tallest first, and a lower peak closer than half the two
shrubs' model widths is dropped (the owner's spacing rule for trees). A
watershed from the kept peaks splits the clump, and a piece much bigger
than a model shrub of its height is split again (k-means) into
model-sized shrubs. Each shrub's height is its piece's top, its width the
piece's equal-area width held within twice the spread, and its look the
piece's majority: **bush** when near-infrared calls it green (yard
plantings, hedges, riparian thickets), **sage** when it isn't (sagebrush,
bitterbrush, rabbitbrush). A hedge becomes a row of bushes.

| Test area (500 m) | Shrubs per hectare | Bush share | Median height |
|---|---|---|---|
| Dry Creek foothills | 575 | 46% | 1.1 m |
| Barber Pool | 291 | 65% | 1.3 m |
| Bogus Basin | 228 | 91% | 0.8 m |
| Silver City | 127 | 50% | 1.6 m |
| North End, Downtown, South Meridian | 42–45 | 69–88% | 1.3–1.7 m |
| Initial Point desert, Owyhee front | 15–17 | 22–82% | 0.6–1.2 m |
| NY Canal farmland | 7 | 46% | 0.8 m |

The domes these shrubs make cover 66–87% of the cleaned shrub cells, with
a mean height error of 0.2–0.6 m there. Low desert shrubs under about
0.4 m mostly don't reach the band in this lidar, so the desert areas look
emptier than their photos.

**Looks.** Two low-poly models in the trees' style, with the same flat
shading and soft shadow: **bush**, a leafy mound of two lumpy lobes sunk a
little into the ground (160 triangles), and **sage**, a low twiggy mound of
six faceted clumps over three short stems, grey-green (144 triangles).
Like trees, each shrub gets its own heading, lump pattern and a small
colour nudge.

**As built (Oct 11, the landscape sprint's P11-data).** The trees plugin
holds the shrubs: `trees.shrub` (one row per shrub: its centre, look,
height, width and ground height), `trees.shrub_build` (each build's
outline, settings and counts) and the view `trees.shrub_area` (where
shrubs are built), in its migration 0002. The build
(`plugins/trees/build/build_shrubs.py`) runs in the worker image, one area
at a time, as a heavy job: it reads the area's lidar products (the trees'
height rasters and building mask), its point cloud for the lidar cue (the
returns above the ground in each cell and their scatter, worked chunk by
chunk so any area fits in memory) and the summer photo, and
`shrubs-load` loads what it writes. Three things the experiments left
open:

- **Crops** come from farm's fields, as the landscape's crop class does
  (decision 15, Oct 8): a clump with half its cells or more in a crop
  field is a crop, not shrubs. Until farm's fields are built, the crop
  fields of USDA's 2025 Crop Sequence Boundaries stand in. The spike's own
  crop rule (the even, all-green, low 25 m blocks) runs beside it as a
  check, and each build says how the two agree.
- **The photo** sits a little off the lidar, by a shift each build
  measures where the photo's green best meets the lidar's trees (up to 6 m
  each way, in whole 0.5 m cells; none where trees are too few to tell).
  The photo's NAD83 and the lidar's NAD83(2011) differ by well under a
  metre here, so the photo is read in the lidar's frame and the measured
  shift takes that up too: doing it properly needs NOAA grids that PROJ
  would download, and a build fetches nothing.
- **Downtown's box overlaps the North End's** (by about 0.7 km²): the
  overlap's shrubs are the North End's, and downtown's build leaves that
  part out of its shrubs and its outline.

**The ten boxes** (whole boxes, about 2.1 km² each, Oct 11, on the
scratch database): 343,700 shrubs in 2,239 ha, built in 53 minutes as ten
heavy jobs (2-12 minutes each, about 2 GB at most). The areas' own green
cuts came out within 0.01 of the spike's (0.04 in the deserts to 0.22 at
Bogus Basin), and the measured photo shifts match the spike's where trees
are plentiful (North End, Barber Pool, downtown, Bogus Basin). The domes
cover 78-83% of the kept shrub cells, with a mean height error of
0.23-0.46 m. Whole boxes differ from the spike's central 500 m, most at
Bogus Basin, where the central square has fewer shrubs than the box:

| Box | Shrubs | Per hectare | Bush share | Median height | Spike, central 500 m |
|---|---|---|---|---|---|
| Dry Creek foothills | 88,291 | 412 | 50% | 0.9 m | 575 |
| Bogus Basin | 122,135 | 571 | 97% | 0.9 m | 228 |
| Barber Pool | 40,014 | 196 | 58% | 1.3 m | 291 |
| Silver City | 34,771 | 163 | 69% | 1.3 m | 127 |
| Downtown (less the North End's part) | 23,079 | 70 | 62% | 1.3 m | 45 |
| South Meridian | 14,005 | 66 | 84% | 1.4 m | 42 |
| North End | 11,951 | 56 | 75% | 1.6 m | 45 |
| NY Canal farmland | 5,177 | 25 | 89% | 0.7 m | 7 |
| Owyhee front | 3,012 | 14 | 55% | 1.0 m | 15-17 |
| Initial Point desert | 1,265 | 6 | 75% | 0.6 m | 15-17 |

**The crop check.** In the NY Canal box the crop fields took 20,020
clumps (21 ha of shrub cells). The spike's rule found 267 field blocks
there, and 97% of its fields lie in CSB's crop fields, as in the spike.
1,393 shrubs still stand in its fields, in clumps that lie mostly outside
CSB's crop fields (whose edges can be 5-15 m off). Over whole boxes the
rule also fires where there are no farm fields: 2 blocks at Barber Pool
(813 shrubs) and 5 at Bogus Basin (3,363 shrubs), even, green and low,
not yet looked at in the photo. They stay shrubs while the rule is only
a check; whether they should go is for the owner's look at the sheets.

**The hedge check** (plan C14). OpenStreetMap maps 28 hedges in Idaho; 8
of them (383 m) are in the ten boxes, all downtown. Five (355 m, 93% of
the length) come out as rows of bushes (188 bushes along them, none
sage), two short ones of about 12 m are half covered, and a 3.4 m piece
isn't found. The check reads the hedges from the held extract until the
fences plugin stores them (`shrubs-hedge-check`; it writes nothing).

Not drawn yet: the shrubs on the map (the low-detail and full meshes, from
z17, at most 1,500 nearest the view's centre). Fences and walls, the
straight, thin raised lines the same lidar shows, come next as their own
layer.
