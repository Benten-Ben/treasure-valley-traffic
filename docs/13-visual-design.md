# 13. Visual design: the valley as a city-builder

How the app should look and feel. The owner asked for something closer to
SimCity, Cities: Skylines and Civilization than to a corporate dashboard,
with the usefulness of a traffic management center. The owner left the
final call to the pilot (Oct 5, 2026). How that choice was made, the
directions set aside and the owner's own words are in
[§13.11](#1311-how-the-direction-was-chosen-oct-5). Chapter 12 is reserved
for the database schema.

**Since UI v2 (Oct 6–7, 2026),** the built app follows
[chapter 14](14-ui-v2.md), and this chapter has been brought in line with it
(§14.12, with the owner's OK): the lenses became **layers that combine**,
switched from a bottom toolbar instead of a left lens bar; "one data story
in color" became a **color budget**; heavy 3D drawing uses our own small
**scene engine** instead of deck.gl. The tokens, fonts and game-card look
below are unchanged. What's designed here but left for a later round (the
Valley Feed, the time bar and replay, the camera wall, search, lanes) is
tracked in [DEFERRED.md](DEFERRED.md).

---

## 13.1 The idea

**A friendly command center built like a city-builder game.**

- The valley appears as a warm, softly lit 3D model: terrain, cream
  buildings, turquoise river.
- You look at it the way you look at your city in Cities: Skylines:
  tilted, zoomable, alive.
- Every data source is a **layer**: traffic, signals, buses, roadwork,
  crashes, cameras. Layers switch on and off together, and with any of them
  on the model turns into a clean clay backdrop for them to paint on, within
  one color budget (§13.8). (The Oct 5 design had one-at-a-time *lenses*;
  UI v2 made them layers, §13.5.)
- Time has game-speed controls, so you can replay last Tuesday's evening
  peak at 60x and watch it build up. (UI v2 replays the buses a minute or
  two behind live, with Pause; the time bar and 60x replay are next round.)
- Panels feel like game cards: rounded, tactile, quick to read.
- The numbers inside them are precise and honest. **It's playful in form
  and serious in content.**

City-builders spent decades making dense simulation data pleasant to
explore, and traffic data has the same problem.

## 13.2 What we borrow from games

| Game idea | Where it comes from | What it becomes here |
|---|---|---|
| **Info views / lenses**: one key turns the map into a data mode | Cities: Skylines info views, Civilization VI lenses | **Layers that combine** (UI v2): round buttons in a bottom toolbar, and number keys that toggle them (2 Streets, 4 Transit, 7 Cameras, 9 Road weather; Shift solos one). With any data layer on, the base turns to "clay" (Base on Auto). The Oct 5 lenses showed one layer at a time |
| **Clay model** look in data modes | Cities: Skylines, SimCity (2013) data maps | Buildings, terrain and roads go cream and gray so data colors pop (the Clay flavor, §13.4) |
| **City stats bar** across the top | Cities: Skylines (population, money, happiness) | Live chips: buses, routes running, cameras recording and calibrated (UI v2); work zones and weather at the airport once those layers exist |
| **Game speed** controls | Every city-builder | A LIVE pill with the playback delay (1–5 min behind live) and Pause (UI v2); later ⏸ ▶ ▶▶ ▶▶▶ and a time bar to replay any stored day at 1x, 60x or 600x ([DEFERRED](DEFERRED.md)) |
| **Notification stack** | Civilization's right-side notifications; Cities: Skylines' Chirper feed | The **Valley Feed** (next round; key N): new lane closure, camera frozen, bus route detoured. Click to fly there. |
| **Query tool / info panel** | SimCity's query tool; Cities: Skylines building panels | Click an intersection to get a card with a grade badge, camera thumbnail, stats bars and history |
| **Letter grades** | Game ratings, and traffic engineering's own Level of Service (LOS) A–F | Intersection badges A–F once we can measure delay; it's both a game idiom and an engineering standard |
| **Hex map** | Civilization | Crash density as extruded hexagon columns |
| **Units moving on the map** | Strategy games | Buses glide along their own GPS paths, replayed about 90 s behind live so the next position is always known (never extrapolated); far out they're discs with route plates, close in toy-like 3D buses; optional fading trails (ch. 14 §14.4) |
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
- **Top-left:** a nameplate reads *Treasure Valley*.
- **Beside it:** the stat chips: *38 buses* · *14/20 routes running* ·
  *34 recording · 11 calibrated*. Later, *22 work zones* and *Fog at BOI*
  join as those layers arrive. Hovering a chip shows its source and age.
- **Top-right:** the clock shows the moment the buses on the map are at,
  *5:41:20 PM · Tue*, beside a *LIVE −1:30* pill (the playback delay), then
  Help (?).

**Layers (bottom toolbar).** A row of big round two-tone icon buttons
along the bottom: Base at the left end, then Streets, Transit, Cameras and
Road weather (Signals, Roadwork, Safety and Lanes join as they're built).
Hovering one shows its name, key, what it shows, and its source and age.
Any combination can be on. Turning on **Streets** (key 2):

- the map drains to clay in about a third of a second (Base on Auto);
- roads repaint by posted speed in 11 shades of one blue, wider for bigger
  roads; with Transit on too, they turn pale slate so the route colors stay
  readable. (Later, volumes: Eagle Road and I-84 swell into thick bands.)
- its legend joins the stack in the left column, expanded, and the others
  fold to one-line rows.

**The Valley Feed** (next round, key N). A short stack of cards, newest on
top, each with its Phosphor icon:

- *New lane closure · Eagle Rd at Pine · 3 min ago* (barricade)
- *Camera "Chinden & Cloverdale" frozen for 20 min* (camera)
- *Route 9 running 6 min late on Fairview* (bus)

Each card enters with a small bounce. Clicking one flies the map there
and opens its card. The feed collapses to a single badge with a count
when you want the space.

**Inspecting an intersection** (the intersections layer is next round). Click
*Eagle & Fairview* and the docked inspect card on the right fills in, like a
building panel in Cities: Skylines:

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

**Replaying time (bottom center; next round).** UI v2 already plays the
buses back a minute or two behind live (1, 1.5, 2, 3 or 5 minutes), with
Space to pause and L to go live. The full version:

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

**Camera wall (key C; next round).** The traffic-center video wall, made
friendly:

- a grid of live thumbnails for the cameras in the current view;
- each card has a status dot (live, stale, offline, each with a distinct
  shape as well as color) and a small queue gauge;
- clicking a card flies the map to that camera, with its view cone drawn
  on the ground.

**Calibrating a camera (Calibrate or Configure in its window).** The same
map goes into Calibrate mode (UI v2; [ch. 14 §14.6](14-ui-v2.md#calibrating-on-the-map)),
and the screen splits in two:

- **Left (45% of the width):** the panel, with the camera's frame frozen
  as the reference so every pair refers to one picture, zoomable, plus a
  small Live inset and a blink compare.
- **Right:** the map in survey mode, looking straight down at the
  intersection along the camera's heading:
  - aerial imagery draped on the terrain at true scale: NAIP 2025 at
    0.3 m across Ada and Canyon, sharper still around the cameras and
    signals ([ch. 9 §9.5](09-base-map-data.md#95-imagery)); ACHD's 3-inch
    imagery only viewed live and never cached, where its terms allow;
  - the camera's corner pole marked as a starting guess.

How it works:

1. **Pair points.** Click a point in the frame, such as the near end of a
   left-turn stop bar, then the same spot on the map. An amber numbered pin
   pair appears; ground height comes from the 1 m elevation model.
2. **Live fit.** From the fourth pair on, the solver runs live. A small card
   shows the camera's height, compass heading, tilt and field of view, plus
   each pair's error in pixels. A pair that doesn't fit gets a warning icon.
3. **Check by eye.**
   - The camera's view cone appears on the map, and the frame can be
     draped on the ground as a check.
   - **Check alignment** looks through the unsaved pose: our 3D map
     rendered from exactly where the camera sits, with the photo over it
     and a slider to fade it. A good fit lines up; a bad one is obvious at
     a glance.
   - Later, the map's lane lines drawn onto the camera frame (after lanes).
4. **Save.** The calibration is stored with its reference frame for that
   view, and versioned. *Use this frame* swaps the reference for the live
   picture shown, and the server keeps exactly those bytes. Saving reopens
   the camera's window and offers *Look through to check*.
5. **Draw zones on the map, not the image.** Lane and approach zones are
   drawn on the map in real-world coordinates and projected into the camera
   image automatically. If the camera shifts slightly, the zones follow.
   If an operator moves it to an unknown view, the Valley Feed says
   *"Camera X has a new view and needs calibration"*.

**Tips for a good fit** (the pilot's how-to for the owner, Oct 5):

- Opening Calibrate shows the newest frame: from our own archive for the
  recorded cameras, otherwise fetched on demand from 511's allowed image
  route (`/map/Cctv/<id>`). *Use this frame* swaps in the live picture.
- Click sharp ground features: the end of a stop bar, a lane-line corner,
  a crosswalk corner. Then click the same spot on the map.
- Position, heading and tilt are solved from 4 pairs and update live with
  each new pair. Aim for **6 or more, spread out**: near and far, left and
  right in the frame.
- Saving turns the camera's icon teal. From z14 its view footprint is
  drawn on the ground, and from z15 it stands on a pole with its head and
  view cone in 3D.
- The first camera opened to try it was Park & Parkcenter, picked as an
  easy one.

**Foggy mornings** (later). When the Boise airport reports fog, a stat chip
says so. In the Valley look (no data layer on) a light haze settles over the
map, and a feed card notes reduced visibility. Context like this explains odd data.

## 13.4 The map's look

Two base **flavors**, switched by the Base button (Auto · Map · Clay; Auto
means Clay whenever a data layer is on) with a 350 ms crossfade. The exact
values are in [ch. 14 §14.5](14-ui-v2.md#145-streets-and-the-base-look)
(`#lib/map/flavors.ts`).

| Element | Valley (the normal look) | Clay (any data layer on) |
|---|---|---|
| Ground | Warm sand `#EEE7DA` with soft hillshade | Paler sand `#F3EDE2`, softer hillshade |
| Terrain | 3DEP terrain, exaggeration about 1.3 so the Foothills read; true scale while looking through a camera or calibrating | Same |
| Buildings | Cream extrusions `#F8F4EC`, sides shading darker; buildings with no measured height a lighter tone (§13.8) | Light gray-cream, 55% opacity; estimates lighter |
| Water | Turquoise `#7CC4E4` | Pale blue-gray `#C9DCE3` |
| Parks | Soft green `#B9D88F` | Very pale green `#E4E8D6` |
| Roads | White with a warm gray casing; major roads a little wider | Pale; the data layers paint over them |
| Sky | Warm haze at the horizon, blue above | Same |
| Labels | Clear, few, warm dark gray | Fewer: addresses, points of interest, minor road labels, shields and one-way arrows hidden |
| Aerial photos (Base) | NAIP | Muted (saturation −0.7) |

**Camera defaults:**
- Pitch about 50° and bearing about −12°: the slightly turned, tilted
  angle that makes city-builders feel three-dimensional.
- **O** goes to the **god's-eye overview**: the whole valley, looking
  straight down. **H** goes home, over Meridian.

**Later:** lighting that follows the real sun over Boise, with a night look
after dark.

## 13.5 The layers

The Oct 5 lenses showed one data story at a time. Since UI v2 (owner, Oct 6;
[ch. 14 §14.3](14-ui-v2.md#layers-and-the-toolbar)) they're **layers that
combine**: each has a round button in the bottom toolbar and a number key
that toggles it (the lens numbers, kept). Shift with a number solos that
layer, and 1 turns every data layer off (press again to restore). A button
appears only once its layer exists. A layer's data loads the first time it's
switched on (or once the map is idle) and then stays loaded; turning it off
only hides it.

| Key | Layer | What it shows | How it looks | Built |
|---|---|---|---|---|
| 1 | (all off) | The valley itself | The Valley look; a few icons for the selected item only | UI v2 |
| 2 | **Streets** (planned as Traffic) | Posted speed (ACHD); later volumes (AADT, then camera-measured queues) | **11 shades of one blue** (every 5 mph from 20 to 65, plus 75), changing crisply where the posted speed changes; a pale slate version while Transit is on; width by road class; chevrons on one-way streets; speed numbers along the bigger roads | UI v2 (Streets since Oct 5) |
| 3 | Signals | Signalized intersections (one per COMPASS signal) | Round pins with a tiny three-light signal glyph; later the A–F grade badge | Next round ([DEFERRED](DEFERRED.md)) |
| 4 | **Transit** | VRT routes, stops, buses | Routes in **our own 13-color palette** with the route number everywhere, not VRT's GTFS colors (which give only 4 tier colors and were rejected Oct 5; [ch. 14 §14.4](14-ui-v2.md#route-colors)); routes that share a street drawn side by side; routes with no bus in 15 minutes in a pale ghost color; buses as discs with route plates far out and toy-like 3D buses close in, replayed along their GPS paths about 90 s behind live; stop capsules, then 3D sign posts | UI v2 |
| 5 | Roadwork | Work zones and incidents (WZDx, ACHD) | Orange-and-white **barricade stripes** along affected segments; cone icons; incidents as pulsing rings that fade with age | Later (work zones recorded since Oct 6) |
| 6 | Safety | Crashes (ITD and COMPASS) | Extruded **hexagon columns**: height for count, color for share involving injury | Later |
| 7 | **Cameras** | Cameras, their calibration and live pictures | Teal discs with a check (calibrated), hollow amber rings with "?" (not), small gray dots (not on 511); from z14 calibrated footprints on the ground, and from z15 poles, heads and **view cones** in 3D with each open window's picture hanging in its cone; floating windows with the live picture; later, queue bars | UI v2 |
| 8 | Lanes | Lane counts and turn lanes (OpenStreetMap) | Real-width road surfaces and markings from about z16 | Next round ([ch. 14 §14.7](14-ui-v2.md#147-lanes-designed-built-next-round)) |
| 9 | **Road weather** | ITD's road-weather station cameras and Oregon DOT's nearby | Cream rounded-square badges with a thermometer-and-road icon (no data hue), hollow where every view shows 511's placeholder; a window per station with a tab per direction | UI v2 (WP16) |

## 13.6 Panels and controls

**Game-card panels:**
- Cream background `#FFFBF4`, a 2 px warm edge `#E3D7C4`, 16 px rounded
  corners.
- A **solid offset shadow** (a few pixels straight down) gives the toy-like
  depth of game UIs.
- Each card has a slim header with its layer's icon chip.
- Only camera windows float (at most 4); bus, stop, road and route cards
  share one docked inspect card, and calibration is a docked mode.

**Buttons:**
- Chunky pills that **press down** when clicked: they move 2 px and the
  shadow shrinks.
- **Layer buttons** are 52 px round, with Phosphor duotone icons and the
  label under them on hover or focus (always at 1280 px or wider):

| State | Look |
|---|---|
| Off | Panel background |
| On | Pressed in (2 px down), ink background, cream icon |
| Keyboard focus | A 2 px ink ring inside a 3 px amber ring (amber alone on cream is 2.05:1, below the 3:1 minimum) |
| Loading | A rotating ring segment; a static dashed ring under reduced motion |
| Error | A ▲ badge; the tooltip gives the reason, and the legend row offers Retry |

**Layout** (UI v2, [ch. 14 §14.3](14-ui-v2.md#regions)):

| Area | Desktop (1024 px and wider) | Phone (under 600 px) |
|---|---|---|
| Top bar | Nameplate and stat chips on the left; clock, time pill and Help on the right | A compact nameplate pill (name and clock), with one scrollable row of chips under it |
| Layers | Bottom-centre toolbar, Base at its left end; a mode banner replaces it while looking through or calibrating | A scrollable tab bar with labels, Base at its end |
| Legends | Left column, the newest layer's expanded | In the bottom sheet |
| Inspect card | Docked in the right column, under the camera widget | In the bottom sheet |
| Camera windows | Float in the safe area between the bars, at most 4 | Up to 3 tabs in the sheet |
| Camera widget | Right column: compass and reset north, zoom, 2D/3D, Home, Overview | — |
| Scale, credits | Bottom corners, outside the toolbar | No scale; the (i) credits move to the top left, under the chips |
| Feed (next round) | Right edge, collapsible | Pull-up sheet |
| Time bar (next round) | Bottom center | Above the tab bar |

On a tablet (600–1023 px), toolbar labels are hidden, legends fold to
one-line rows, the inspect card is 320 px, at most 2 windows open, and
calibrating needs 900 px or more. A phone gets one bottom sheet (25%, 55%
or 90% high), look-through full screen with a bottom strip, "Calibration
needs a larger screen", touch targets of at least 44 px and no horizontal
scroll.

**Keyboard** (one registry drives the keys and the help overlay; keys are
ignored while typing):

| Keys | Action |
|---|---|
| 2 / 4 / 7 / 9 | Toggle Streets / Transit / Cameras / Road weather (8 Lanes and 3, 5, 6 kept for Signals, Roadwork and Safety) |
| Shift+2/4/7/9 | Solo that layer; again to restore |
| 1 | All data layers off; again to restore |
| W A S D | Pan |
| Q / E | Rotate 15° left / right |
| R / F | Tilt up / down 10° |
| H | Home: over Meridian, pitch 50, bearing −12 |
| O | God's-eye overview: the whole valley, looking straight down |
| Backspace | Previous view |
| Space | Pause / play |
| L | Back to live |
| ? | Help |
| ← / → | In look-through: the next or previous calibrated camera |
| Esc | Close, in order: help or a popover, the focused window, look-through, calibrate (the draft is kept), follow, the inspect card, the selection |

Reserved for later: `[` `]` (slower / faster), C (camera wall), **N** (the
Valley Feed, moved from F, which now tilts) and / (go to an intersection,
road or camera).

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
| `--accent` | `#F2A20C` | Signal amber: UI interaction (focus rings, primary actions) and the "needs calibration" state |
| `--accent-2` | `#2C8C99` | Boise River teal: on the map, **cameras only** (view footprints, cones, calibrated heads); in panels, secondary accents |
| `--alert` | `#D9467A` | Problems, always paired with an icon |

**Reserved colors and selection** (UI v2, the color budget in §13.8):

- **Teal** belongs to cameras on the map, and **amber** to the interface and
  to "needs calibration". Route yellow is ΔE 1 from amber, so selection on
  the map never relies on amber.
- **Selection on the map is ink and cream:** a 2 px ink line with a 3 px
  cream halo (1.3× width for routes); a 3D object lifts 2 m, grows 1.2× and
  gets an ink-and-cream ring on the ground.
- **Magenta** marks problems and always comes with an icon.
- **Status text** is set in ink with a colored shape beside it, since teal
  and magenta text fall below 4.5:1 at 13 px.

**The badge rule** (bus plates, route shields, legend and card badges):
numerals at least 14 px bold in the slot's badge text color, reaching 4.5:1
on the plate. Where a slot can't (blue, orange and red route colors, and
the unknown-route gray), the numerals get a 2 px halo in the opposite tone,
ink around white or cream around ink, and the measured pair is numeral
against halo (about 14:1). Contrast is never fixed by changing a palette
color: the 13 route slots are fixed and append-only
([ch. 14 §14.3](14-ui-v2.md#motion-and-accessibility), §14.4).

**Data ramp** (for volumes and other "low to high" layers, later): low to
high, or free-flowing to jammed. Five steps:

1. Blue-teal `#3A9AB2`
2. Yellow `#F2D16B`
3. Orange `#F29A3A`
4. Magenta `#D9467A`
5. Purple `#7A2E8C`

No red-to-green: about 8% of men can't tell those apart. Wherever it
matters, a second channel backs up the color: width for roads, height for
hexagons, letters for grades. We'll check the ramp in a color-blindness
simulator when we build it.

The layers built so far use their own validated colors: Streets a one-hue
blue speed ramp (11 steps, and a slate version under Transit), and Transit a
13-slot route palette checked in OKLab with colorblind simulation
([ch. 14 §14.4–14.5](14-ui-v2.md#144-transit)).

**Icons:**
- [Phosphor](https://phosphoricons.com) (MIT license), **duotone** weight.
  Two-tone icons echo Cities: Skylines' info-view icons.
- Installed from npm and bundled with the app.

**Motion:**

| Movement | Timing |
|---|---|
| Map and Clay switch | 350 ms paint crossfade |
| Fly-to | About 1.2 s, eased |
| Feed cards (next round) | 250 ms slide with a slight bounce |
| Buses | Glide continuously along their GPS paths |
| Selection | One 1.2 s pulse |

Motion is for moving through place and time (fly-to, replay, scrubbing),
not decoration: there's no staggered page-load reveal, because this is a
tool people open every day (§13.11).

When the system asks for reduced motion, Clay switches instantly, fly-to
becomes a jump, nothing pulses or bounces, and loading rings are static.
Buses still move: that's data.

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
- **Readable at a glance: the color budget.** "At most one data story in
  color at a time" held while lenses showed one layer at a time. Now that
  layers combine ([ch. 14 §14.3](14-ui-v2.md#the-color-budget)):
  - categorical hue belongs to Transit (route colors);
  - Streets use the blue speed ramp when Transit is off, and a pale slate
    version of it (same order, low chroma, 70% width) when Transit is on;
  - teal is for cameras, amber for the interface and "needs calibration",
    and magenta for problems, always with an icon (§13.7);
  - lanes, road weather and selection use form, icons and ink and cream
    only;
  - labels are thinned out in Clay;
  - large hit targets.
- **Never color alone.** Never red-versus-green (see the data ramp), and
  every status has a shape and a word, the same everywhere: ● live, ▲ late
  or stale, ■ offline, ◌ not calibrated. Running and not-running routes,
  calibrated and not, stale and one-way each have a shape or a word too.
- **Fast:** the 3D buses, stops and cameras are drawn by our own small
  WebGL scene engine, loaded only when needed, and far-zoom buses and badges
  by an always-loaded 2D overlay; moving things never rebuild map data each
  frame; panels stay light. deck.gl (the Oct 5 pick) doesn't run on
  MapLibre 6, so it waits for heavy analysis layers such as crash hexagons
  ([ch. 14 §14.8](14-ui-v2.md#the-3d-engine-instead-of-deckgl);
  [ch. 10 §10.2](10-architecture.md#102-proposed-stack)).

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

**Where this stands (Oct 7, 2026):** UI v2 ([ch. 14](14-ui-v2.md)) built
the tokens, fonts and icons; the Valley and Clay looks; the Streets,
Transit, Cameras and Road weather layers in a bottom toolbar; the inspect
card; bus playback a minute or two behind live; camera windows with live
pictures; 3D buses, stops and cameras; and calibration on the map. Roadwork,
Signals and Safety come as layers once designed; the Valley Feed, the time
bar with replay, the camera wall and search are next round
([DEFERRED.md](DEFERRED.md)).

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
| Hexagon columns for crashes | 8, data art, and Civilization's hex map | Safety layer (later), §13.5 |
| A flat paper-and-ink view for reports | An echo of 11 (blueprint) and 13 (topo) | Print view, later (§13.2) |
| The camera wall | 1, traffic management center, made friendly | §13.3 |
| The god's-eye name | The owner's first wish | The overview key (O), §13.4 |
