# 13. Visual design: the valley as a city-builder

How the app should look and feel. The owner asked for something closer to
SimCity, Cities: Skylines and Civilization than to a corporate dashboard,
with the usefulness of a traffic management center. The owner left the
final call to the pilot (Oct 5, 2026). How that choice was made, the
directions set aside and the owner's own words are in
[§13.11](#1311-how-the-direction-was-chosen-oct-5). Chapter 12 is reserved
for the database schema.

---

## 13.1 The idea

**A friendly command center built like a city-builder game.**

- The valley appears as a warm, softly lit 3D model: terrain, cream
  buildings, turquoise river.
- You look at it the way you look at your city in Cities: Skylines:
  tilted, zoomable, alive.
- Every data source is a **lens** that turns the model into a clean
  backdrop and paints one story onto it: traffic, signals, buses, roadwork,
  crashes, cameras.
- Time has game-speed controls, so you can replay last Tuesday's evening
  peak at 60x and watch it build up.
- Panels feel like game cards: rounded, tactile, quick to read.
- The numbers inside them are precise and honest. **It's playful in form
  and serious in content.**

City-builders spent decades making dense simulation data pleasant to
explore, and traffic data has the same problem.

## 13.2 What we borrow from games

| Game idea | Where it comes from | What it becomes here |
|---|---|---|
| **Info views / lenses**: one key turns the map into a data mode | Cities: Skylines info views, Civilization VI lenses | Number keys 1–7 switch lenses; the base fades to "clay" and one layer takes color |
| **Clay model** look in data modes | Cities: Skylines, SimCity (2013) data maps | Buildings, terrain and roads go cream and gray so data colors pop |
| **City stats bar** across the top | Cities: Skylines (population, money, happiness) | Live chips: buses running, active work zones, cameras live, weather at the airport |
| **Game speed** controls | Every city-builder | ⏸ ▶ ▶▶ ▶▶▶ with a LIVE pill: replay any stored day at 1x, 60x or 600x |
| **Notification stack** | Civilization's right-side notifications; Cities: Skylines' Chirper feed | The **Valley Feed**: new lane closure, camera frozen, bus route detoured. Click to fly there. |
| **Query tool / info panel** | SimCity's query tool; Cities: Skylines building panels | Click an intersection to get a card with a grade badge, camera thumbnail, stats bars and history |
| **Letter grades** | Game ratings, and traffic engineering's own Level of Service (LOS) A–F | Intersection badges A–F once we can measure delay; it's both a game idiom and an engineering standard |
| **Hex map** | Civilization | Crash density as extruded hexagon columns |
| **Units moving on the map** | Strategy games | Buses glide along their routes (positions interpolated between 30 s GPS updates) and leave fading trails |
| **Advisors** | SimCity and Civilization advisors | Later, a **Findings** panel: automated observations, each linked to its evidence. No cartoon people. |
| **Strategic view** | Civilization VI's flat parchment map | Later, a **Print view**: flat, paper-and-ink style for reports and screenshots |

## 13.3 A walk through the screen

This section is written as a walk-through on purpose: the owner liked
hearing the design described as it would look and behave in the actual UI,
and asked for more of that (§13.11).

**Opening the app.**

- A short "Building the valley…" card fades away and the camera settles
  above Meridian, pitched about 50° and turned slightly off north. The
  valley reads as a landscape, not a flat web map:
  - the Boise Foothills rise as soft shaded relief in the northeast;
  - the Boise River is a turquoise thread;
  - downtown's buildings stand up as cream blocks;
  - the sky fades from warm haze at the horizon to blue.
- **Top-left:** a nameplate reads *Treasure Valley*, with the live clock
  and day: *5:42 PM · Tue*.
- **Top, beside it:** the stats bar: 🚌 *38 buses running* · 🚧 *22 work
  zones* · 📷 *205/210 cameras live* · 🌫 *Fog at BOI*.

**Lenses (left edge).** A column of big round two-tone icon buttons:
Normal, Traffic, Signals, Transit, Roadwork, Safety, Cameras. Hovering one
shows its name and hotkey. Choosing **Traffic** (key 2):

- the map drains to clay in about a third of a second;
- roads repaint by volume: wider and warmer means busier, so Eagle Road
  and I-84 swell into thick orange-to-magenta bands;
- a small legend card slides out under the lens bar.

**The Valley Feed (right edge).** A short stack of cards, newest on top:

- 🚧 *New lane closure · Eagle Rd at Pine · 3 min ago*
- 📷 *Camera "Chinden & Cloverdale" frozen for 20 min*
- 🚌 *Route 9 running 6 min late on Fairview*

Each card enters with a small bounce. Clicking one flies the map there
and opens its card. The feed collapses to a single badge with a count
when you want the space.

**Inspecting an intersection.** Click *Eagle & Fairview* and a card slides
in from the right, like a building panel in Cities: Skylines:

- **Header:** the name, with chips for *Signal · ACHD · Camera*.
- **A large grade badge** once we measure delay or queues. Until then it
  shows a dashed outline that reads *Not measured yet*, never a made-up
  grade.
- **A live camera thumbnail** that refreshes each minute, with the time it
  was taken.
- **Stats as chunky bars:**
  - highest adjacent volume (AADT), for example *61,000/day*;
  - crashes within 60 m over 5 years, with injury and fatal counts
    marked;
  - distance to the nearest rail crossing;
  - work zones nearby;
  - bus stops.
- **Tabs:** *Overview · Camera · History.* History shows a week of queue
  measurements as a heat strip (days by time of day) once cameras are
  measured.

**Replaying time (bottom center).**

- The time bar shows a sparkline of region-wide activity for the selected
  day.
- Press Space to pause, press ▶▶ to run at 60x, and drag the handle back to
  4:30 PM.
- As the clock runs:
  - buses glide along their routes, leaving trails that fade over five
    minutes;
  - work zones appear and disappear at their real times;
  - in the Cameras lens, queue bars at each camera rise and fall.
- A LIVE pill jumps back to now.

**Camera wall (key C).** The traffic-center video wall, made friendly:

- a grid of live thumbnails for the cameras in the current view;
- each card has a status dot (live, stale, offline, each with a distinct
  shape as well as color) and a small queue gauge;
- clicking a card flies the map to that camera, with its view cone drawn
  on the ground.

**Calibrating a camera (Calibrate on a camera's card).** The screen splits
in two:

- **Left:** the camera's current frame, zoomable.
- **Right:** the map in survey mode, looking straight down at the
  intersection:
  - aerial imagery draped on the terrain: NAIP 0.6 m everywhere, or ACHD's
    3-inch imagery fetched live and never cached, where its terms allow;
  - the camera's corner pole marked as a starting guess.

How it works:

1. **Pair points.** Click a point in the frame, such as the near end of a
   left-turn stop bar, then the same spot on the map. An amber numbered pin
   pair appears; ground height comes from the 1 m elevation model.
2. **Live fit.** From the fourth pair on, the solver runs live. A small card
   shows the camera's height, compass heading, tilt and field of view, plus
   each pair's error in pixels. A pair that doesn't fit gets a warning icon.
3. **Check by eye.**
   - The map's road edges and lane lines are drawn onto the camera frame,
     and the camera's view cone appears on the map.
   - A slider fades in a **camera's-eye view**: our 3D map rendered from
     exactly where the camera sits, laid over the photo. A good fit lines
     up; a bad one is obvious at a glance.
4. **Save.** The calibration is stored with a reference frame for that
   view, and versioned.
5. **Draw zones on the map, not the image.** Lane and approach zones are
   drawn on the map in real-world coordinates and projected into the camera
   image automatically. If the camera shifts slightly, the zones follow.
   If an operator moves it to an unknown view, the Valley Feed says
   *"Camera X has a new view and needs calibration"*.

**Tips for a good fit** (the pilot's how-to for the owner, Oct 5):

- Opening Calibrate pulls a fresh frame from 511's allowed image route
  (`/map/Cctv/<id>`), so the frame is current.
- Click sharp ground features: the end of a stop bar, a lane-line corner,
  a crosswalk corner. Then click the same spot on the map.
- Position, heading and tilt are solved from 4 pairs and update live with
  each new pair. Aim for **6 or more, spread out**: near and far, left and
  right in the frame.
- Saving turns the camera's node teal and draws its view cone on the main
  map.
- The first camera opened to try it was Park & Parkcenter, picked as an
  easy one.

**Foggy mornings.** When the Boise airport reports fog, the stats-bar chip
says so. In the Normal lens a light haze settles over the map, and a feed
card notes reduced visibility. Context like this explains odd data.

## 13.4 The map's look

| Element | Normal lens | Clay (any data lens) |
|---|---|---|
| Ground | Warm sand `#EEE7DA` with soft hillshade | Same, slightly paler |
| Terrain | 3DEP terrain, exaggeration about 1.3 so the Foothills read | Same |
| Buildings | Cream extrusions `#F8F4EC`, sides shading darker; buildings with no measured height a lighter tone (§13.8) | Light gray-cream, 60% opacity; estimates lighter |
| Water | Turquoise `#7CC4E4` | Pale blue-gray |
| Parks | Soft green `#B9D88F` | Very pale green |
| Roads | White with a warm gray casing; major roads a little wider | Thin, pale; the lens paints over them |
| Sky | Warm haze at the horizon, blue above | Same |
| Labels | Clear, few, warm dark gray | Fewer: only what the lens needs |

**Camera defaults:**
- Pitch about 50° and bearing about −12°: the slightly turned, tilted
  angle that makes city-builders feel three-dimensional.
- One key returns to the **god's-eye overview**: the whole valley, looking
  straight down.

**Later:** lighting that follows the real sun over Boise, with a night look
after dark.

## 13.5 The lenses

| # | Lens | What it shows | How it looks |
|---|---|---|---|
| 1 | **Normal** | The valley itself | Full color; a few icons for the selected item only |
| 2 | **Traffic** | Volumes (AADT now; camera-measured queues later) | Road width and color by volume, on the shared ramp. **Built first as "Streets" (Oct 5, 2026):** posted speed (ACHD) on a one-hue blue ramp, width by road class, chevrons on one-way streets, speed numbers along the bigger roads |
| 3 | **Signals** | 453 signalized intersections | Round pins with a tiny three-light signal glyph; later the A–F grade badge |
| 4 | **Transit** | VRT routes, stops, live buses | Routes in their own GTFS colors; buses as rounded bus icons with route badges, gliding, with fading trails |
| 5 | **Roadwork** | Work zones and incidents (WZDx, ACHD) | Orange-and-white **barricade stripes** along affected segments; cone icons; incidents as pulsing rings that fade with age |
| 6 | **Safety** | Crashes (ITD, 5 years) | Extruded **hexagon columns**: height for count, color for share involving injury |
| 7 | **Cameras** | Camera health and queue measurements | Camera icons with **view cones** on the ground; status shown by shape and color; queue bars beside each |

## 13.6 Panels and controls

**Game-card panels:**
- Cream background `#FFFBF4`, a 2 px warm edge `#E3D7C4`, 16 px rounded
  corners.
- A **solid offset shadow** (a few pixels straight down) gives the toy-like
  depth of game UIs.
- Each card has a slim header strip in its lens color, with an icon chip.

**Buttons:**
- Chunky pills that **press down** when clicked: they move 2 px and the
  shadow shrinks.
- The active lens button sits pressed in, with an amber ring.

**Layout:**

| Area | Desktop | Phone |
|---|---|---|
| Lenses | Vertical bar, left edge | Bottom tab bar |
| Feed | Right edge, collapsible | Pull-up sheet |
| Inspect card | Slides in over the feed | Full-height sheet |
| Time bar | Bottom center | Above the tab bar |
| Stats bar | Top, next to the nameplate | Chips under the nameplate, horizontally scrollable |

**Keyboard:**

| Keys | Action |
|---|---|
| 1–7 | Lenses |
| Space | Pause / play |
| `[` `]` | Slower / faster |
| C | Camera wall |
| F | Feed |
| O | God's-eye overview |
| / | Go to (intersection, road, camera) |
| Esc | Close |

## 13.7 Type, color, icons, motion

**Type** (all open source, self-hosted in the app; no font CDNs):

| Font | Use | Why |
|---|---|---|
| **Fredoka** (rounded) | Headings, the nameplate, grade letters, lens names | Warm and game-like without being childish |
| **Overpass** | Body text and, later, map labels | An open-source version of the Highway Gothic road-sign lettering; very much at home on a traffic map |
| **Overpass Mono** | Every number: clock, counts, times, percentages | Tabular digits that line up and don't jiggle as they update |

Map labels start in Noto Sans, from the basemap assets. Overpass map labels
need glyph files we'd generate later.

**Color tokens:**

| Token | Value | Use |
|---|---|---|
| `--ink` | `#2B2A33` | Text |
| `--ink-soft` | `#5D5A66` | Secondary text |
| `--panel` | `#FFFBF4` | Card backgrounds |
| `--panel-edge` | `#E3D7C4` | Card edges and casings |
| `--accent` | `#F2A20C` | Signal amber: active state, primary actions |
| `--accent-2` | `#2C8C99` | Boise River teal: links, secondary |
| `--alert` | `#D9467A` | Problems, always paired with an icon |

**Data ramp:** low to high, or free-flowing to jammed. Five steps:

1. Blue-teal `#3A9AB2`
2. Yellow `#F2D16B`
3. Orange `#F29A3A`
4. Magenta `#D9467A`
5. Purple `#7A2E8C`

No red-to-green: about 8% of men can't tell those apart. Wherever it
matters, a second channel backs up the color: width for roads, height for
hexagons, letters for grades. We'll check the ramp in a color-blindness
simulator when we build it.

**Icons:**
- [Phosphor](https://phosphoricons.com) (MIT license), **duotone** weight.
  Two-tone icons echo Cities: Skylines' info-view icons.
- Installed from npm and bundled with the app.

**Motion:**

| Movement | Timing |
|---|---|
| Lens switch | About 350 ms color crossfade |
| Fly-to | About 1.2 s, eased |
| Feed cards | 250 ms slide with a slight bounce |
| Buses | Glide continuously between GPS updates |

Motion is for moving through place and time (fly-to, replay, scrubbing),
not decoration: there's no staggered page-load reveal, because this is a
tool people open every day (§13.11).

When the system asks for reduced motion, lenses switch instantly, fly-to
becomes a jump, and nothing bounces.

## 13.8 Usability rules

- **Honest data first.**
  - Every number shows its source and age on hover.
  - Missing data says "not measured yet" or "not built yet"; it's never
    filled in with a guess.
  - An estimate that is drawn looks like one. A building with no height in
    the data (or 0 m) stands at an estimated height (its floors × 3.2 m,
    else 4 m) in a lighter tone, so it's never mistaken for a measured one
    (owner, Oct 7; [ch. 14 §14.5](14-ui-v2.md#145-streets-and-the-base-look)).
  - No made-up grades.
- **Play without gamification.** No points, achievements or streaks. The
  game influence is about legibility and enjoyment, not engagement tricks.
- **Readable at a glance.**
  - At most one data story in color at a time (the lens).
  - Labels thinned out in data lenses.
  - Large hit targets.
- **Never red-versus-green alone** (see the data ramp).
- **Fast:** heavy layers (bus trails, hexagons, replay) use deck.gl on the
  GPU; panels stay light.

## 13.9 What we're avoiding

- The dark "security operations" or corporate BI look: gray cards, tiny
  type, neon on black.
- Glassmorphism and frosted panels, and purple gradients on white.
- Default fonts (Inter, Roboto, system UI). The app's first header was
  exactly that, system fonts on white.
- Cartoonish styling inside the data: numbers stay crisp and monospaced.
- Staggered page-load reveals and other motion for its own sake.
- Fonts or other assets from third-party CDNs, even where general
  front-end advice recommends them (§13.7).

The other directions considered on Oct 5, and why they were set aside, are
in §13.11.

## 13.10 Build order

1. Design tokens (CSS variables), self-hosted fonts and icons; restyle the
   page shell: nameplate and stats bar.
2. Clay and normal base styles. These need the basemap build: github.com
   access for the `pmtiles` CLI and assets.
3. Lens bar with the first data lenses, fed from the database once the
   first ingestor lands: Roadwork (work zones), then Signals and Cameras.
4. Inspect card; then the Valley Feed.
5. Time bar and replay, once time series exist; buses first.
6. Calibration workbench (needs the basemap, terrain and NAIP imagery),
   then the camera wall and queue gauges once camera measurements exist
   ([chapter 11](11-camera-validation-layer.md)).
7. Later: Findings, Print view, real-sun lighting.

## 13.11 How the direction was chosen (Oct 5)

The look in §13.1 came out of one short exchange on Oct 5, 2026. The
directions set aside are kept here so they aren't proposed again as new,
and so the reasons are on record.

### The owner's aesthetics guide

The owner first shared a general front-end aesthetics guide and asked
whether it still applied. Its main point is that without a stated direction
a UI drifts to generic defaults. The pilot's reading:

| The guide's advice | Here | Why |
|---|---|---|
| Give the UI a direction, or it falls back to generic choices | **Applies** | Our first header was system fonts on white, exactly the default the guide names (§13.9) |
| Load fonts from Google Fonts | **Doesn't apply** | It breaks the self-hosted, no-third-party rule; fonts are bundled with the app (§13.7) |
| Backgrounds and atmosphere; dominant colors with sharp accents | **Applies, moved to the basemap** | On a map app the map *is* the background, so color work belongs in the basemap style. A muted basemap lets the data layers be the sharp accents (the clay look, §13.4) |
| Motion: a staggered page-load reveal | **Doesn't apply** | It adds little to a tool opened every day. The motion that matters is fly-to transitions and scrubbing through time: bus trails, before and after (§13.7) |
| Stack advice (plain HTML, Tailwind, Motion for React) | **Doesn't apply** | The app is Svelte, which has its own transitions |
| (Not covered) | **Matters more here** | Colorblind-safe color (red/green fails for about 8% of men) and readable numbers in dense panels. The guide itself says dashboards are where the generic look shows most, and this app is a dashboard |

The guide stays outside the repo, as its own note intends.

### The first three directions

| Direction | Look |
|---|---|
| Signal cabinet | Dark map, amber and green accents like signal heads, monospace numbers |
| USGS topo print | Paper-cream map, serif labels, contour-brown and survey-red accents |
| High desert | Sagebrush green, basalt gray, sunset amber |

The owner's reply:

> "my first suggestion was like gods eye view (idk what that looks
> like/means exactly though) but maybe also like a command center or
> something, maybe more techno aesthetic"

### What "god's-eye view" means

The pilot described it as a viewpoint as much as a style: looking down at
a slight tilt over the whole valley, with everything live at once on a
dark, quiet map. Roads glow by how busy they are, buses leave light
trails, incidents pulse, and labels and screen furniture are kept to a
minimum. Think spy-thriller satellite shots, Google Earth flyovers and
SimCity's info views.

### The 17 directions

| # | Family | Direction | Look |
|---|---|---|---|
| 1 | Command and operations | Traffic management center | Dark navy, tiled panels, a strip of camera thumbnails, status lights, monospace numbers |
| 2 | Command and operations | NASA mission control, 1960s–70s | Black, phosphor green and amber, big numerals, grid lines, a faint monitor glow |
| 3 | Command and operations | Military ops / HUD | Near-black, thin cyan-white lines, bracketed symbols, crosshairs, coordinates everywhere |
| 4 | Command and operations | Spy-thriller satellite | Washed-out teal-tinted imagery, scanlines, zoom-to-target reticles, time stamps |
| 5 | Command and operations | Bloomberg Terminal | Black, amber text, extremely dense, all monospace |
| 6 | Techno | Neon Tron / Blade Runner | Roads as glowing cyan and magenta traces |
| 7 | Techno | Arcade wireframe vector | Terrain as a green line mesh |
| 8 | Techno | Data art (deck.gl / kepler.gl demo style) | Bus trails as particle streams, crashes as 3D hexagon columns |
| 9 | Techno | NASA Black Marble city lights | Black base, roads glowing sodium-orange by volume; "the most literal god's-eye view" |
| 10 | Techno | Weather radar ("traffic weather") | Congestion as radar-style color blobs, looped through time |
| 11 | Engineering and maps | Engineering blueprint | Prussian blue, white linework, drafting lettering, dimension callouts |
| 12 | Engineering and maps | Highway signage (MUTCD) | Asphalt gray, sign green, warning orange, the open-source Overpass font |
| 13 | Engineering and maps | USGS topo print | As above |
| 14 | Engineering and maps | Swiss transit map | White, a strict grid, bold primary-colored route lines |
| 15 | Place and play | High desert | As above, plus foothills gold and sunset amber over the Owyhees |
| 16 | Place and play | SimCity / Cities: Skylines | Toy-like 3D, each layer a colored info view |
| 17 | Place and play | Civilization-style strategy | Territories, unit-like markers, a "turn" timeline |

The pilot's own pick was a dark city-lights base (9) with control-room
panels (1), plus a light blueprint (11) or topo (13) mode for reports. It
offered to render three to five of these as side-by-side mock screens;
those were never made.

### The owner's decision

> "those are all great inspirations. I think you can decide which would
> both look best and be nicest to actually use. i do like the way you were
> describing things as you were imagining them in the actual UI so maybe
> do that more to flesh everything out. I'm drawn most to the simcity,
> city skylines, civilization ... because obviously a lot was put into
> making those aesthetic and enjoyable. I think the traffic management
> center look but maybe that more friendly vibe than like 'corporate
> app'."

So the pilot went with the city-builder look (16, with ideas from 17) and
the traffic management center's usefulness (1), made friendly. The
owner's pull toward friendly over "corporate app" is why the pilot's dark
city-lights pick gave way to the warm, light model in §13.1, and why
§13.9 avoids dark, neon-on-black screens. The request for UI walk-throughs
is why §13.3 is written as one.

**What survived from the other directions:**

| Kept | From | Where it is now |
|---|---|---|
| Overpass type | 12, highway signage | §13.7 |
| Hexagon columns for crashes | 8, data art, and Civilization's hex map | Safety lens, §13.5 |
| A flat paper-and-ink view for reports | An echo of 11 (blueprint) and 13 (topo) | Print view, later (§13.2) |
| The camera wall | 1, traffic management center, made friendly | §13.3 |
| The god's-eye name | The owner's first wish | The overview key (O), §13.4 |
