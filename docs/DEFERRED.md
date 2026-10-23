# Deferred work

Things the UI v2 plan ([ch. 14](14-ui-v2.md)) designed or noted but left
for a later round (owner, Oct 6, 2026), plus earlier map and site ideas
that were marked "later". Data sources not yet used are in
[SOURCES.md](SOURCES.md); decisions are in [DECISIONS.md](DECISIONS.md).

**The open items are on the project's GitHub board, not in this file.**
Each item below is a pointer to its issue. The tracking issue for this
list is [#5](https://github.com/Benten-Ben/treasure-valley-traffic/issues/5).
Done items are dated history in the issue, not here.

## Next round (owner, Oct 6)

| Item | Why it's deferred | Issue |
|---|---|---|
| Lanes (ch. 14 §14.7): lane counts and turn lanes from OpenStreetMap, at real width from about zoom 16 | Comes after the 3D cameras; the first OSM copy is loaded (Oct 7) | [#201](https://github.com/Benten-Ben/treasure-valley-traffic/issues/201) |
| Full replay: a time bar, playback at 60x and 600x | Builds on the tracks API; this round has the 1–5 minute delay and Pause | [#178](https://github.com/Benten-Ben/treasure-valley-traffic/issues/178) |
| Camera wall (key C) | Every live camera in a grid | [#179](https://github.com/Benten-Ben/treasure-valley-traffic/issues/179) |
| Valley Feed: a stream of events, click to fly there | Next round | [#180](https://github.com/Benten-Ben/treasure-valley-traffic/issues/180) |
| Search: places, roads, cameras, routes | Next round | [#181](https://github.com/Benten-Ben/treasure-valley-traffic/issues/181) |
| Coach marks: a short first-visit tour | Next round | [#182](https://github.com/Benten-Ben/treasure-valley-traffic/issues/182) |
| Intersections layer (data built Oct 6; 43 candidates after the Oct 7 OSM load) | Review list and badges | [#183](https://github.com/Benten-Ben/treasure-valley-traffic/issues/183), [#256](https://github.com/Benten-Ben/treasure-valley-traffic/issues/256) |
| Rail crossings layer | FRA crossings, gates and preemption | [#184](https://github.com/Benten-Ben/treasure-valley-traffic/issues/184) |
| Lanes from every source, each number labelled, disagreements flagged | Builds on the lanes design | [#201](https://github.com/Benten-Ben/treasure-valley-traffic/issues/201) |
| Crashes and the high-injury network; congestion measures by year | COMPASS, 2008–2025; internal until COMPASS answers | [#185](https://github.com/Benten-Ben/treasure-valley-traffic/issues/185) |
| Growth context: permits, plats, traffic-zone forecasts | After the core pieces | [#186](https://github.com/Benten-Ben/treasure-valley-traffic/issues/186) |

## Later, once their prerequisites exist

| Item | Why later | Issue |
|---|---|---|
| Faster VRT polling (every 10 s with `If-None-Match`) | More requests to VRT's feed; owner OK | [#252](https://github.com/Benten-Ben/treasure-valley-traffic/issues/252) |
| Lane lines drawn into camera windows, as a calibration check | After lanes | [#188](https://github.com/Benten-Ben/treasure-valley-traffic/issues/188) |
| Detecting when a camera has been moved or re-aimed | After the archive work | [#189](https://github.com/Benten-Ben/treasure-valley-traffic/issues/189) |
| Reading the time in 511's timestamp bar (and ITD's caption) | Image work | [#190](https://github.com/Benten-Ben/treasure-valley-traffic/issues/190) |
| Syncing buses to a camera picture's moment while looking through | Needs the bar time | [#191](https://github.com/Benten-Ben/treasure-valley-traffic/issues/191) |
| Bus shelters only where OSM or VRT says one exists | Data | [#192](https://github.com/Benten-Ben/treasure-valley-traffic/issues/192) |
| See-through bus silhouettes; antialiasing | Measure first | [#193](https://github.com/Benten-Ben/treasure-valley-traffic/issues/193) |
| Lower rendering resolution while moving; a live SSE channel | Measure first (HTTP/2 is on) | [#194](https://github.com/Benten-Ben/treasure-valley-traffic/issues/194) |
| Serving tiles as plain z/x/y files (Caddy with the PMTiles module) | Mainly helps Chrome and Edge on Windows; server change | [#71](https://github.com/Benten-Ben/treasure-valley-traffic/issues/71) |
| A night look for the map | Polish | [#195](https://github.com/Benten-Ben/treasure-valley-traffic/issues/195) |
| Trees across the whole valley, beyond the North End pilot ([ch. 19](19-trees.md)) | Needs lidar height products everywhere | [#196](https://github.com/Benten-Ben/treasure-valley-traffic/issues/196) |
| Hand-made glTF models | Polish | [#197](https://github.com/Benten-Ben/treasure-valley-traffic/issues/197) |
| 3D road decks (bridges and overpasses with height) | Road levels in ACHD's data | [#198](https://github.com/Benten-Ben/treasure-valley-traffic/issues/198) |
| deck.gl for heavy analysis layers | Needs a deck.gl release that supports MapLibre 6 | [#199](https://github.com/Benten-Ben/treasure-valley-traffic/issues/199) |
| Buses offset into their actual lane | After lanes | [#200](https://github.com/Benten-Ben/treasure-valley-traffic/issues/200) |
| An hour-long playback check on a recorded weekday hour, and the bus-seconds-waiting query | Runs after deploy, on the server's data | [#55](https://github.com/Benten-Ben/treasure-valley-traffic/issues/55) |
| Road-weather stations (WP16) from the 511 API's camera list and `core.weather_station` | UI v2 cutover | [#202](https://github.com/Benten-Ben/treasure-valley-traffic/issues/202), [#53](https://github.com/Benten-Ben/treasure-valley-traffic/issues/53) |
| Lanes for Canyon County: a `segment_lanes` keyed on COMPASS pieces or OSM ways | OSM extract is on the server (met Oct 7) | [#5](https://github.com/Benten-Ben/treasure-valley-traffic/issues/5) |
| Link COMPASS's high-injury junctions to `core.intersection` | Both built; small | [#203](https://github.com/Benten-Ben/treasure-valley-traffic/issues/203) |
| One ArcGIS reader: fold COMPASS's pager into `ingest/arcgis.py` | Works today; two code paths | [#204](https://github.com/Benten-Ben/treasure-valley-traffic/issues/204) |
| Make `restricted` a real permission boundary | Policy only today; server change | [#72](https://github.com/Benten-Ben/treasure-valley-traffic/issues/72) |
| A "bus speeds" view of the Streets layer (bus-speed method steps 2–4) | Owner's call; needs enough data | [#205](https://github.com/Benten-Ben/treasure-valley-traffic/issues/205) |
| Video library: several cameras on one shared clock | Part of the library, marked later (Oct 6) | [#206](https://github.com/Benten-Ben/treasure-valley-traffic/issues/206) |
| A "watch this day" button in UI v2's camera windows | Marked later with the library | [#207](https://github.com/Benten-Ben/treasure-valley-traffic/issues/207) |

## History

- **Oct 7, 2026:** the first OpenStreetMap copy of the Idaho extract was
  loaded by hand (13,917 ways, 10,614 with lanes), so the lanes items above
  can be built. Weekly hand downloads continue until Geofabrik answers
  ([#78](https://github.com/Benten-Ben/treasure-valley-traffic/issues/78)).
  That also met the wait on Canyon County lanes (a `segment_lanes` keyed on
  COMPASS pieces or OpenStreetMap ways, since Canyon has no ACHD segments;
  [#5](https://github.com/Benten-Ben/treasure-valley-traffic/issues/5)),
  which can now be built.
