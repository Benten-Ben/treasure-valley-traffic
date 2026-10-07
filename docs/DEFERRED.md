# Deferred work

Things the UI v2 plan ([ch. 14](14-ui-v2.md)) designed or noted but left
for a later round (owner, Oct 6, 2026), plus earlier map and site ideas
that were marked "later", to review and check off. Data sources not yet
used are tracked separately in [SOURCES.md](SOURCES.md); decisions are in
[DECISIONS.md](DECISIONS.md).

Tick an item when it's built, with the date, or strike it if we drop it.

## Next round (owner, Oct 6)

- [ ] **Lanes** (designed in ch. 14 §14.7): lane counts, turn lanes and where
  they start, from OpenStreetMap (`lanes`, `turn:lanes`), drawn at real
  width from about zoom 16. Comes after the 3D cameras. Needs a regular
  copy of Geofabrik's Idaho extract on the server (owner OK, Oct 6).
  Geofabrik's robots.txt disallows scripted downloads (Oct 6), so hand
  downloads load it until Geofabrik answers. **The first copy was loaded
  by hand on Oct 7** (13,917 ways, 10,614 of them with lanes); weekly hand
  downloads continue until Geofabrik answers.
- [ ] **Full replay:** a time bar, playback at 60x and 600x, scrubbing to any
  moment. Builds on the tracks API this round adds. This round has the
  1–5 minute playback delay and Pause.
- [ ] **Camera wall** (key C): every live camera in a grid.
- [ ] **Valley Feed:** a stream of events (new lane closure, camera frozen,
  bus detoured), click to fly there.
- [ ] **Search:** places, roads, cameras, routes.
- [ ] **Coach marks:** a short first-visit tour.
- [ ] **Intersections layer** (data built Oct 6, [DECISIONS](DECISIONS.md)):
  one badge per signalized intersection with its operator, coordination
  group and confidence; the review list of candidates; approaches with
  right-turn lanes and phasing; cameras, counts and rail crossings attached.
  The review list grew with the Oct 7 OpenStreetMap load: **43
  candidates**, 42 of them OSM signal nodes with no COMPASS match, where
  the Oct 6 review had six (one left after it). Counts are in
  [ingest/README](../ingest/README.md).
- [ ] **Rail crossings layer:** FRA crossings, gates and preemption where
  known, the nearest signal and its distance, trains per day.
- [ ] **Lanes from every source:** draw the lanes the lanes rule picks
  (ch. 9 §9.3), each number labeled with its source, with disagreements
  (e.g. Chinden's) flagged; builds on the lanes design above.
- [ ] **Crashes and the high-injury network** (COMPASS, 2008–2025), and
  **congestion measures** by year (internal until COMPASS answers).
- [ ] **Growth context:** building permits, plats and traffic-zone forecasts
  near corridors; Boise's development pipeline (after the core pieces).

## Later, once their prerequisites exist

| | Item | Why later | Needs |
|---|---|---|---|
| [ ] | Faster VRT polling (every 10 s with `If-None-Match`) for smooth 1-minute playback delays | More requests to VRT's feed | Owner OK |
| [ ] | Lane lines drawn into camera windows, as a calibration check | After lanes | Lanes |
| [ ] | Detecting when a camera has been moved or re-aimed | After the archive work | Archive in place (done) |
| [ ] | Reading the time in 511's timestamp bar (and ITD's caption on road-weather views) | Image work | — |
| [ ] | Syncing buses to a camera picture's moment while looking through | Needs the bar time | Reading the bar time |
| [ ] | Bus shelters only where OSM or VRT says one exists | Data | OSM or VRT stop amenities |
| [ ] | See-through bus silhouettes behind buildings; antialiasing | Measure first | — |
| [ ] | Lower rendering resolution while the map moves; a live server-sent-events channel | Measure first (HTTP/2 is now on) | — |
| [ ] | Serving tiles as plain z/x/y files (a Caddy build with the PMTiles module), so browsers cache them | Mainly helps Chrome and Edge on Windows; the owner uses Chrome on a Mac | Server change |
| [ ] | A night look for the map | Polish | — |
| [ ] | Hand-made glTF models (instead of generated ones) | Polish | — |
| [ ] | 3D road decks (bridges and overpasses with height) | Polish | Road levels (in ACHD's data) |
| [ ] | deck.gl for heavy analysis layers (crash hexbins and similar) | deck.gl doesn't run on MapLibre 6 yet | A deck.gl release that supports MapLibre 6 |
| [ ] | Buses offset into their actual lane | After lanes | Lanes |
| [ ] | An hour-long playback check on a recorded weekday hour | Runs after deploy, on the server's data | Deploy |
| [ ] | Load the road-weather stations (WP16) from the 511 API's camera list and `core.weather_station` instead of the one-off private list, and show their readings on the layer | The API collector arrived while UI v2 was being built (Oct 6) | UI v2 finished |
| [ ] | Lanes for Canyon County: a `segment_lanes` keyed on COMPASS pieces or OpenStreetMap ways, since Canyon has no ACHD segments | Was waiting for the first OpenStreetMap load | OSM extract on the server: **met Oct 7** (first hand load: 13,917 ways, 10,614 with lanes), so this can be built |
| [ ] | Link COMPASS's high-injury junctions to `core.intersection` (nearest within 40 m; they carry no `int_id`) | Both are built now; small | — |
| [ ] | One ArcGIS reader: fold COMPASS's pager (`ingest/compass_layer.py`, core since the plugin split because the safety, flow and development plugins share it) into the shared `ingest/arcgis.py` | Works today; two code paths to maintain | — |
| [ ] | Make `restricted` a real permission boundary (a separate database role the app can't read) | Policy only today: the app and ingestors share one role | Server change |
| [ ] | A "bus speeds" view of the Traffic lens ([ch. 13](13-visual-design.md); a layer in UI v2): travel speeds on the map, derived from VRT's bus GPS by the method in [ch. 15](15-plugins.md#speeds-from-buses-planned-for-flow) (pilot, Oct 5) | It's new map data, so it's the owner's call, and only once there's enough data: roughly two weeks after recording began (2:00 PM MDT, Oct 5). Time-of-day profiles need 2–4 weeks | Steps 2–4 of the bus-speed method (crossing times per segment, removing stop dwell, aggregation; only step 1 is built); owner OK |
| [ ] | Video library: several cameras played side by side on one shared clock, e.g. every camera along a corridor at 5:30 PM | Proposed with the `/videos/` library ([ch. 11 §11.5](11-camera-validation-layer.md#115-storage)) and approved with it as a package (Oct 6), but this part was marked "later" | — (the library is built) |
| [ ] | A "watch this day" button in UI v2's camera windows that opens the video library at that camera, day and moment | Marked "later" with the library (Oct 6) | UI v2 camera windows. Library links already carry the camera, day, speed and position in the address (`#cam=…&day=…&fps=…&t=…`, where `t` is seconds into the video), so the button only has to build that link. The library is LAN and tailnet only |
