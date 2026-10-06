# Deferred work

Things the UI v2 plan ([ch. 14](14-ui-v2.md)) designed or noted but left
for a later round (owner, Oct 6, 2026), to review and check off. Data
sources not yet used are tracked separately in [SOURCES.md](SOURCES.md);
decisions are in [DECISIONS.md](DECISIONS.md).

Tick an item when it's built, with the date, or strike it if we drop it.

## Next round (owner, Oct 6)

- [ ] **Lanes** (designed in ch. 14 §14.7): lane counts, turn lanes and where
  they start, from OpenStreetMap (`lanes`, `turn:lanes`), drawn at real
  width from about zoom 16. Needs a regular copy of Geofabrik's Idaho
  extract on the server (owner OK, Oct 6), and comes after the 3D cameras. Geofabrik's robots.txt disallows scripted downloads (Oct 6), so a hand download loads it until Geofabrik answers.
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
