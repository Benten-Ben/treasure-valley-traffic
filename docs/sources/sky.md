# Sky sources (researched Oct 7, 2026)

Data and tools for the sky over the valley: the sun, moon and twilight; sun
glare on roads; real-sun lighting and shadows on the map; satellites such
as the ISS and Starlink; planets, comets and the star catalogs for a
night-sky dome; light pollution and dark-sky places; aurora, meteors and
eclipses; and the cloud, seeing and transparency forecasts that decide
whether any of it is visible. It serves the proposed `sky` plugin
([ch. 15 §15.7](../15-plugins.md#157-ideas-for-later-plugins)) and the sky
watcher and photographer
([ch. 16](../16-ideas-and-personas.md#sky-watcher-and-photographer-sky)),
and part of it (the sun and moon position) may belong in core
([design note 1](#design-notes)). The overview of every theme is in
[chapter 17](../17-sources-for-new-plugins.md); the ideas across all
themes are in [chapter 16](../16-ideas-and-personas.md).

**Status: research only; nothing here is approved.** Sources go to the owner
one at a time ([CLAUDE.md](../../CLAUDE.md)). The research pass ran on
Oct 6; on Oct 7 (UTC) a verifier re-read each entry's official pages,
robots.txt and terms. Of the 43 entries, 27 were confirmed, 14 corrected
and 2 couldn't be verified; none was refuted. Each entry gives its result.
No accounts were created and no datasets downloaded. Small keyless sample
requests, all with our honest User-Agent, went to five hosts: SatNOGS (one
ISS TLE), USNO (one Boise rise and set), SWPC (the directory listing, a
HEAD and two byte-range reads), NASA's ISS ephemeris (a HEAD and one
byte-range read of the header, repeated once by the verifier) and HRRR (one
`.idx`).

How to read this page:
- **Verdicts:** **use** (fits our rules as described), **internal only**
  (use, but publish aggregates only), **needs owner action** (an account,
  a request, a by-hand download or a dependency decision comes first),
  **avoid**.
- **Effort** (S, M, L) is the researcher's rough size of the work.
- **Needs from core** names the core pieces from
  [ch. 15](../15-plugins.md) a source depends on. "Proposed core sky
  ephemeris" is design note 1's proposal, not something that exists.
- **The ring** is the regional ring proposed in
  [DECISIONS](../DECISIONS.md) (about 117.30°W to 115.60°W, 42.90°N to
  44.30°N); "the valley box" is the Ada and Canyon box.

---

## Summary

| Source | Publisher | What it gives | Access | Key or account | License or terms | robots.txt | Verdict | Verified |
|---|---|---|---|---|---|---|---|---|
| [Astronomy Engine](https://github.com/cosinekitty/astronomy) | Don Cross (cosinekitty) | Sun, moon and planet positions, rise and set, twilight, phases, eclipses; ±1 arcminute | npm 2.1.19, lazy-loaded; one-file Python | None | MIT | Not applicable (library) | use | confirmed |
| [SunCalc](https://github.com/mourner/suncalc) | Vladimir Agafonkin | Sun and moon position, light phases, moon illumination | npm 2.1.1 | None | BSD-2-Clause | Not applicable (library) | use | confirmed |
| [NOAA Solar Calculator equations](https://gml.noaa.gov/grad/solcalc/calcdetails.html) | NOAA Global Monitoring Laboratory | Meeus sun equations, about 1 minute accuracy | We port the formulas | None | No statement; US government work, presumed public domain ⚠️ | Not applicable (nothing fetched) | use | confirmed |
| [NREL SPA](https://midcdmz.nrel.gov/spa/) | NREL (apparently renamed ⚠️) | High-precision sun position, C code | Behind a license agreement | Unknown | NREL's own license | Unreadable (no DNS answer); treated as disallow | avoid | unverifiable |
| [USNO API](https://aa.usno.navy.mil/data/api) | US Naval Observatory | Rise, set, twilight, moon phases, solar eclipses, seasons (no lunar eclipses) | JSON GET | None | US Navy work; no statement | 404, no rules | use (checks only) | corrected |
| [JPL Horizons API](https://ssd-api.jpl.nasa.gov/doc/horizons.html) | NASA JPL Solar System Dynamics | Ephemerides for planets, comets, asteroids; az/el and magnitude for any site | JSON GET | None | None stated; credit customary ⚠️ | 404, no rules | use | corrected |
| [satellite.js](https://github.com/shashwatak/satellite-js) | Shashwat Kandadai and contributors | SGP4 from TLE or OMM; look angles | npm 7.1.0 | None | MIT | Not applicable (library) | use | confirmed |
| [Skyfield and sgp4](https://rhodesmill.org/skyfield/earth-satellites.html) | Brandon Rhodes | Satellite passes in Python | PyPI; NumPy and a JPL ephemeris file | None | MIT (sgp4 ⚠️) | Not applicable (libraries) | needs owner action | confirmed |
| [NASA ISS trajectory (OEM)](https://nasa-public-data.s3.amazonaws.com/iss-coords/current/ISS_OEM/ISS.OEM_J2K_EPH.txt) | NASA Johnson Space Center | Predicted ISS state vectors every 4 min for about 15 days | One S3 file | None | Public domain | 404, no rules | use | corrected |
| [SatNOGS DB TLE API](https://db.satnogs.org/api/tle/) | Libre Space Foundation | Latest and historical TLEs (TLE only) | JSON GET | None today; schema declares token auth | CC BY-SA 4.0; cite Space-Track too | Allowed (only `/admin/` disallowed) | use | corrected |
| [CelesTrak GP and SupGP](https://celestrak.org/NORAD/documentation/gp-data-formats.php) | CelesTrak (Dr. T.S. Kelso) | Elements for the whole catalog, incl. Starlink from SpaceX ephemerides | GET under a strict usage policy | None | None found | **Disallows** the GP pages for `*`; `claudebot` disallowed entirely | needs owner action | confirmed |
| [Space-Track.org](https://www.space-track.org/documentation#user_agree) | US Space Command / US Space Force | The authoritative catalog, OMM, history, decay | REST API after login | Individual account | Basic SSA data may be redistributed with citation | API paths allowed | needs owner action | confirmed |
| [HYG v4.4](https://codeberg.org/astronexus/hyg) | David Nash (astronexus) | 119,614 stars with magnitudes, colours and names | Git LFS clone by hand | None | CC BY-SA 4.0 | Downloads disallowed on Codeberg and astronexus.com; clone by hand | use | confirmed |
| [d3-celestial data](https://github.com/ofrohn/d3-celestial) | Olaf Frohn | GeoJSON stars, constellation lines and boundaries, Milky Way outlines | One clone | None | BSD-3-Clause | Not applicable (one clone) | use | corrected |
| [NASA SVS Deep Star Maps 2020](https://svs.gsfc.nasa.gov/4851) | NASA Goddard SVS | Milky Way and starfield textures, 4K to 64K | Download by hand | None | Public domain unless noted; Gaia content CC BY-NC | 404, no rules | use | confirmed |
| [ESA Gaia Archive](https://www.cosmos.esa.int/web/gaia-users/license) | ESA (Gaia DPAC) | DR3, about 1.8 billion sources | TAP, bulk files | None | CC BY-NC 3.0 IGO | Archive disallowed except documentation | avoid | confirmed |
| [EOG VIIRS Nighttime Lights](https://eogdata.mines.edu/products/vnl/) | Earth Observation Group, Colorado School of Mines | Annual and monthly night-light radiance, about 500 m | Download by hand | Free account ⚠️ | "Many" files CC BY 4.0 | Disallows `/nighttime_light` | needs owner action | confirmed |
| [NASA Black Marble](https://www.earthdata.nasa.gov/data/projects/black-marble) | NASA GSFC / LAADS DAAC | Corrected daily, monthly and yearly night lights | HDF-EOS5 tiles | Earthdata Login | NASA open science; credit | Behind the login; treated as disallow | needs owner action | corrected |
| [NASA GIBS](https://nasa-gibs.github.io/gibs-api-docs/access-basics/) | NASA ESDIS | Night-lights imagery tiles | Keyless WMTS | None | No restrictions stated; credit | 404, no rules | use | confirmed |
| [Falchi et al. 2016 atlas](https://doi.org/10.5880/GFZ.1.4.2016.001) | Falchi et al.; GFZ Data Services | Artificial night-sky brightness, 30 arc-seconds | By hand (request form, or now a direct link ⚠️) | Unknown | CC BY-NC 4.0 | `*` allowed; AI agents named and blocked | needs owner action | corrected |
| [Globe at Night](https://globeatnight.org/maps-data/) | NSF NOIRLab | Citizen sky-brightness readings since 2006 | Yearly files | None | CC BY 4.0 | 404, no rules | internal only | corrected |
| [lightpollutionmap.info](https://www.lightpollutionmap.info/) | Jurij Stare (private site) | Overlays of VIIRS, Black Marble and Falchi | `/geoserver/` tiles | None | Not checked | Disallows `/geoserver/` | avoid | confirmed |
| [Idaho dark-sky places](https://parksandrecreation.idaho.gov/state-park/bruneau-dunes-state-park/) | DarkSky International; Idaho Parks and Recreation | Bruneau Dunes observatory and dark-sky parks | Hand entry | None | Facts only, credited | Parks site allows all; darksky.org pages give a bot challenge | use | corrected |
| [NOAA SWPC data service](https://services.swpc.noaa.gov/json/) | NOAA Space Weather Prediction Center | OVATION aurora grid, 1-minute Kp | HTTPS GET | None | US government work, public domain ⚠️; credit | 404, no rules | use | confirmed |
| [GFZ Kp index](https://kp.gfz.de/en/data) | GFZ Helmholtz Centre for Geosciences | Kp since 1932, Hp30 and Hp60, F10.7 | JSON API and files | None | CC BY 4.0 | 404, no rules | use | confirmed |
| [IMO meteor shower calendar](https://www.imo.net/) | International Meteor Organization | Yearly shower table | PDF by hand | None | © IMO; facts only | An HTML page, no valid rules | use (facts only) | confirmed |
| [IAU MDC shower lists](https://www.ta3.sk/IAUC22DB/MDC2022/) | IAU Meteor Data Center | Every known shower, with radiants | Text files, once | None | None stated; cite | Allowed | use | confirmed |
| [Global Meteor Network](https://globalmeteornetwork.org/data/) | Global Meteor Network | Meteor trajectories, every 6 h | Text files | None | CC BY 4.0 | `*` allowed, Crawl-delay 10; AI agents named and blocked | use | confirmed |
| [CNEOS Fireball API](https://ssd-api.jpl.nasa.gov/doc/fireball.html) | NASA JPL CNEOS | Fireballs from US government sensors | JSON GET | None | None stated | 404, no rules | use | confirmed |
| [American Meteor Society](https://www.amsmeteors.org/) | American Meteor Society | Witness fireball reports | Website; members API ⚠️ | Unknown | Not checked | Allows all | avoid | unverifiable |
| [NASA eclipse predictions and EclipseWise](https://eclipse.gsfc.nasa.gov/eclipse.html) | NASA GSFC (Fred Espenak); EclipseWise | Eclipse catalogs, paths, local circumstances | Read for checks | None | Credit lines (they differ by site) | 404 (NASA); EclipseWise read once | use | corrected |
| [NOAA HRRR on AWS](https://registry.opendata.aws/noaa-hrrr-pds/) | NOAA NCEP (NODD) | Hourly 3 km cloud layers, visibility, smoke | S3 byte ranges | None | Open; attribution requested | 404, no rules | use | confirmed |
| [ECCC seeing and transparency](https://weather.gc.ca/astro/index_e.html) | Environment and Climate Change Canada | Cloud, seeing and transparency to 84 h | Datamart GRIB2; AMQPS push for regular use | None | ECCC licence v2.1.1: open, with attribution | Datamart 404; GeoMet map requests disallowed | use | corrected |
| [7Timer! ASTRO](https://www.7timer.info/doc.php) | 7Timer! (Ye Quanzhi) | 3-day astronomy forecast from GFS | JSON API | None | Free for non-commercial use | 404, no rules | avoid | confirmed |
| [Clear Sky Chart](https://www.cleardarksky.com/) | CSC Charts | Charts per observing site | Chart images | None | Display allowed on free, ad-free sites with a legend link | Several paths disallowed; Crawl-delay 50 | avoid (link out) | confirmed |
| [NWS API](https://api.weather.gov/) | NOAA National Weather Service | Gridpoint sky cover | Keyless JSON | None | Public domain | **Disallows everything** | avoid | confirmed |
| [NASA POWER](https://power.larc.nasa.gov/) | NASA Langley | Solar and weather climatology, about 0.5° | `/api/` | None | NASA open data | **Disallows `/api/`** | avoid | confirmed |
| [NSRDB on AWS](https://registry.opendata.aws/nrel-pds-nsrdb/) | NREL (now listed as the National Laboratory of the Rockies) | Satellite irradiance and cloud type, 2 km | S3, HDF5 | None | CC BY 3.0 US | 404, no rules | use | corrected |
| [WRI and Meta canopy height](https://registry.opendata.aws/dataforgood-fb-forests/) | World Resources Institute and Meta | Tree heights, about 1 m | S3, COG | None | CC BY 4.0 | 404, no rules | use | confirmed |
| [USGS 3DEP LiDAR point clouds](https://www.usgs.gov/3d-elevation-program) | USGS 3D Elevation Program | Point clouds for a surface model with trees and buildings | S3 EPT (2018–20); rockyweb LAZ (2023–24) | None | Public domain | S3 hosts 404; rockyweb unreadable, treated as disallow | use | corrected |
| [Bruneton atmospheric scattering](https://github.com/ebruneton/precomputed_atmospheric_scattering) | Eric Bruneton | Physically based sky colours (shaders) | GitHub source | None | BSD-3-Clause | Not applicable (source code) | use | confirmed |
| [MapLibre sky, light and hillshade](https://maplibre.org/maplibre-style-spec/sky/) | MapLibre | Style properties for sky colour, extrusion light, hillshade | Built into GL JS 6 | None | BSD-3-Clause | Not applicable (library) | use | confirmed |
| [Sun-glare and twilight research](https://trid.trb.org/View/1241470) | Various journals and universities | Glare thresholds, crash and deer-collision timing | Papers and abstracts | None | Copyrighted; cite, don't copy | Not applicable (read once) | use (methods) | corrected |

---

## Sun, moon and planets

### Astronomy Engine

[github.com/cosinekitty/astronomy](https://github.com/cosinekitty/astronomy).
Don Cross (cosinekitty), open source. **use**, confirmed.

Positions of the Sun, Moon and planets; rise, set and culmination; civil,
nautical and astronomical twilight; moon phases and libration; lunar and
solar eclipses, including local solar eclipse circumstances; transits;
seasons; magnitudes; conjunctions and oppositions; Jupiter's four large
moons; constellation lookup; coordinate conversions; refraction. It also
has a gravity simulator for user-defined small bodies (asteroids, comets)
started from state vectors, but ships no comet elements. Stated accuracy is
within ±1 arcminute, unit-tested against NOVAS and JPL Horizons. Versions
in C, C#, JavaScript, Python and Kotlin/JVM.

- **Coverage:** global, any date; no data files.
- **Access:** npm `astronomy-engine` 2.1.19 (`astronomy.browser.min.js`
  116,424 bytes; `esm/astronomy.js` 412,025 bytes unminified),
  lazy-loaded. Python: copy the single `astronomy/astronomy.py` (no
  third-party dependencies) or `pip install astronomy-engine`. No key;
  MIT; nothing is fetched at runtime, so robots.txt doesn't apply.
- **Updates and size:** library releases only; about 116 KB minified, and
  one Python file.
- **Use cases:** planets and the Moon (with phase) on the night-sky dome;
  rise, set and twilight times for any spot; local eclipse circumstances
  (the 2017 replay, future eclipses); server-side Valley Feed items
  (moonrise, conjunctions, equinoxes) without a new Python dependency;
  optionally comet tracks from Horizons state vectors via the small-body
  simulator.
- **Personas:** stargazer, photographer, hiker and camper, gardener,
  farmer, commuter.
- **Needs from core:** time and replay clock, 3D engine, proposed core sky
  ephemeris. **Effort** S.
- **Risks:** bundle size if loaded eagerly, so load it lazily. About 1
  arcminute is fine for display and glare, not for occultation timing.
- **Checked:** the README confirms MIT, the ±1 arcminute accuracy and the
  testing against NOVAS and Horizons; unpkg confirms 2.1.19 and the
  116,424-byte browser file; the Python page confirms there are no
  third-party dependencies. The researcher's "no comets" was too strong
  (the simulator can propagate them). Evidence:
  [repository](https://github.com/cosinekitty/astronomy),
  [Python](https://github.com/cosinekitty/astronomy/tree/master/source/python),
  [unpkg metadata](https://unpkg.com/astronomy-engine@2.1.19/?meta).

### SunCalc

[github.com/mourner/suncalc](https://github.com/mourner/suncalc). Vladimir
Agafonkin (mourner), open source. **use**, confirmed.

Sun position (altitude, azimuth); sunlight phases (sunrise, sunset, dusk,
golden hour, twilight); moon position, rise and set, and illumination. v2
is a precision-focused rewrite with breaking changes. Stated typical
errors: sun about 0.08°, moon about 0.09°, rise and set about 15 s,
validated against JPL Horizons and USNO.

- **Coverage:** global.
- **Access:** npm `suncalc` 2.1.1 (`index.js` 22,904 bytes; `suncalc.cjs`
  16,199 bytes). No key; BSD-2-Clause; no runtime fetch.
- **Updates and size:** rare releases; about 16–23 KB unminified.
- **Use cases:** per-frame sun and moon direction in the always-loaded
  bundle, driving MapLibre's light, sky and hillshade and our engine's
  light; twilight phases for the night look.
- **Personas:** everyone (map lighting), cyclist, commuter, gardener.
- **Needs from core:** time and replay clock, proposed core sky ephemeris.
  **Effort** S.
- **Risks:** overlaps with Astronomy Engine; the alternative is porting the
  NOAA/Meeus equations into `#lib/sky` with no dependency. The v2 API
  breaks 1.x, so pin the version.
- **Checked:** the README confirms the license, error figures, validation
  and the breaking v2.0 rewrite; unpkg confirms 2.1.1 and both file sizes.
  Evidence: [repository](https://github.com/mourner/suncalc),
  [unpkg metadata](https://unpkg.com/suncalc@2.1.1/?meta).

### NOAA Solar Calculator equations (Meeus)

[gml.noaa.gov/grad/solcalc/calcdetails.html](https://gml.noaa.gov/grad/solcalc/calcdetails.html).
NOAA Global Monitoring Laboratory. **use**, confirmed.

The equations behind NOAA's solar calculator (after Meeus): declination,
equation of time, hour angle, azimuth and elevation, and refraction that
depends on elevation. Sunrise and sunset use 0.833°, which NOAA calls all
refraction; it is about 0.567° of refraction plus the Sun's 0.267°
semidiameter. NOAA calls it "theoretically accurate to within a minute"
between ±72° latitude; the spreadsheets are valid 1901–2099 and the web
calculator −2000 to +3000.

- **Coverage:** global.
- **Access:** documentation and downloadable spreadsheets; we port the
  formulas and fetch nothing. No key. No license statement on the page; as
  a US government work it's presumed public domain ⚠️. The page says NOAA
  "cannot certify or authenticate" the results and that the calculator is
  no longer actively supported or maintained.
- **Updates and size:** static (unmaintained); about 150 lines of code.
- **Use cases:** a dependency-free sun position in TypeScript and Python
  (it produced the Boise glare windows in [design note 2](#design-notes));
  a reference for tests.
- **Personas:** commuter, traffic researcher, gardener.
- **Needs from core:** proposed core sky ephemeris. **Effort** S.
- **Risks:** none material; refraction near the horizon varies with the
  weather, as in every model.
- **Checked:** accuracy, latitude limit, year ranges, the 0.833° assumption
  and the "no longer actively supported" notice are on the page. The
  researcher's "research and recreational use only" wording wasn't seen;
  the disclaimer seen is that NOAA "cannot certify". The verifier
  re-implemented the equations and reproduced every Boise glare window to
  the minute. Evidence:
  [calculation details](https://gml.noaa.gov/grad/solcalc/calcdetails.html).

### NREL Solar Position Algorithm (SPA)

[midcdmz.nrel.gov/spa](https://midcdmz.nrel.gov/spa/). National Renewable
Energy Laboratory, apparently renamed the National Laboratory of the
Rockies ⚠️. **avoid**, unverifiable.

A very high-precision solar position algorithm (Reda and Andreas), as C
source behind a license agreement. pvlib wraps it but doesn't ship it:
"Due to license restrictions, the C code must be downloaded seperately"
(sic).

- **Coverage:** global.
- **Access:** C source behind NREL's own license agreement; whether a key or
  account is needed is unknown. robots.txt not checked: `midcdmz.nrel.gov`,
  `nrel.gov`, `www.nrel.gov` and `developer.nrel.gov` gave no DNS answer
  from the research environment on Oct 7 (UTC), so we treat it as
  disallowed.
- **Use cases:** none needed; Astronomy Engine and the NOAA equations are
  precise enough.
- **Personas:** traffic researcher. **Effort** S.
- **Risks:** a license that would conflict with an MIT repository if
  vendored; NREL domains may have moved after the renaming.
- **Checked:** the pvlib quote is confirmed on pvlib's official docs. The
  NREL hosts still don't resolve. The AWS registry now names the "National
  Laboratory of the Rockies (NREL)", which suggests a rename rather than an
  outage ⚠️. The SPA license itself couldn't be read. Evidence:
  [SPA page](https://midcdmz.nrel.gov/spa/) (DNS failure),
  [pvlib docs](https://pvlib-python.readthedocs.io/en/v0.10.5/reference/generated/pvlib.solarposition.spa_c.html),
  [AWS registry](https://registry.opendata.aws/nrel-pds-nsrdb/).

### USNO Astronomical Applications API

[aa.usno.navy.mil/data/api](https://aa.usno.navy.mil/data/api). US Naval
Observatory. **use** (for checks only), corrected.

JSON endpoints: `/api/rstt/oneday` (sun and moon rise, set, transit,
twilight, moon phase and illumination), `/api/moon/phases/date` and
`/year`, `/api/eclipses/solar/date` and `/year`, `/api/seasons`,
`/api/siderealtime`, `/api/daylightsaving`, `/api/celnav`,
`/api/juliandate`, `/api/calendardate` and religious observances. There is
**no lunar-eclipse endpoint**; the Lunar Eclipse Computer is a web form
only.

- **Coverage:** global.
- **Access:**
  `https://aa.usno.navy.mil/api/rstt/oneday?date=YYYY-MM-DD&coords=lat,lon&tz=-7&dst=true`.
  `tz` is east-positive, local time minus UT1 (−12 to +14); `dst=true` adds
  the summer hour. An optional ID of up to 8 alphanumerics (not "AA"). All
  services are capped at 9,999 iterations. No key. A US government (Navy)
  work, with no license or terms statement on the API page. robots.txt
  returns 404, so no rules (re-checked Oct 7, UTC).
- **Updates and size:** on demand; about 1 KB per call.
- **Use cases:** test fixtures for our own sun, moon, twilight, moon-phase
  and solar-eclipse code (a handful of calls, stored once); cross-checking
  solar eclipse circumstances. Lunar eclipses are checked against NASA's
  Espenak tables instead.
- **Personas:** traffic researcher, stargazer.
- **Needs from core:** none. **Effort** S.
- **Risks:** not a runtime dependency: we compute locally and use USNO only
  to validate.
- **Checked:** the API page lists only the endpoints above, so
  `eclipses/lunar` was removed from the entry. The ID, `tz` and
  9,999-iteration details are confirmed word for word. The verifier didn't
  repeat the sample call; its NOAA recomputation for Oct 6 (sunrise about
  07:48–07:50, sunset about 19:15–19:17 MDT) agrees with the sample once
  the time-zone mistake is corrected ([design note 2](#design-notes)).
  Evidence: [API page](https://aa.usno.navy.mil/data/api),
  [robots.txt](https://aa.usno.navy.mil/robots.txt).

### JPL Horizons API

[ssd-api.jpl.nasa.gov/doc/horizons.html](https://ssd-api.jpl.nasa.gov/doc/horizons.html).
NASA JPL Solar System Dynamics Group. **use**, corrected.

Ephemerides for planets, moons, comets, asteroids and spacecraft, with
observer tables (az/el, magnitude) for any site.

- **Coverage:** the solar system, from any observer location.
- **Access:** GET `https://ssd.jpl.nasa.gov/api/horizons.api` with
  URL-encoded Horizons settings; JSON (default) or text; optional
  `EMAIL_ADDR`. Output needs `MAKE_EPHEM='YES'` and/or `OBJ_DATA='YES'`.
  The manual describes the API as for "machine-to-machine" use; its 1–2 s
  spacing advice is written for automated e-mail requests. No key. No
  license or citation text in the pages read; crediting the JPL SSD
  Horizons system is customary ⚠️. robots.txt on both `ssd.jpl.nasa.gov`
  and `ssd-api.jpl.nasa.gov` returns 404, so no rules (re-checked).
- **Updates and size:** on demand, with solutions updated continuously; a
  few KB per call.
- **Use cases:** a bright comet when one appears, with one call a day for
  its az/el and magnitude over the valley (Astronomy Engine ships no comet
  elements, though its simulator could propagate Horizons state vectors);
  test fixtures for the planet code.
- **Personas:** stargazer, photographer.
- **Needs from core:** time and replay clock. **Effort** S.
- **Risks:** no stated rate limit, so keep to a few calls a day and check
  the JSON `signature` version, as the docs ask.
- **Checked:** endpoint, formats, the machine-to-machine wording and the
  1–2 s spacing are confirmed. No license or citation statement was found,
  so the researcher's credit line is custom, not a requirement ⚠️.
  Evidence: [API docs](https://ssd-api.jpl.nasa.gov/doc/horizons.html),
  [manual](https://ssd.jpl.nasa.gov/horizons/manual.html),
  [robots.txt](https://ssd.jpl.nasa.gov/robots.txt),
  [API robots.txt](https://ssd-api.jpl.nasa.gov/robots.txt).

## Satellites

### satellite.js (SGP4 in JavaScript)

[github.com/shashwatak/satellite-js](https://github.com/shashwatak/satellite-js).
Shashwat Kandadai and contributors. **use**, confirmed.

SGP4/SDP4 propagation from TLE or OMM JSON (`json2satrec`); `propagate`,
`gstime`, `eciToEcf`, `ecfToLookAngles`, `dopplerFactor`; a WASM bulk
propagator and calculators (look angles, shadow fraction, Doppler). Output
is in the TEME/ECI frame. "Heavily based" on Brandon Rhodes' sgp4 and David
Vallado's C++ code.

- **Coverage:** Earth-orbiting objects.
- **Access:** npm `satellite.js` 7.1.0. No key; MIT; a library, so
  robots.txt doesn't apply.
- **Updates and size:** releases; unpkg lists about 380 KB of files (WASM
  bundles 126–285 KB), and the JS propagation core is about 55 KB
  unminified.
- **Use cases:** propagating the ISS and bright satellites in a Web Worker
  for the dome, 3D orbit ribbons and pass predictions; OMM input for
  objects with 6-digit catalog numbers, which have had no TLE form since
  July 2026.
- **Personas:** stargazer.
- **Needs from core:** 3D engine, time and replay clock, tracks contract.
  **Effort** S.
- **Risks:** elements are good only for days to weeks from their epoch, so
  replay needs archived elements. Don't mix its TEME output with J2000
  data such as NASA's OEM without a frame conversion.
- **Checked:** license, derivation, function list and WASM build confirmed
  on GitHub; unpkg shows 7.1.0. The researcher's 668 KB "unpacked" figure
  isn't reproduced by unpkg's file list (about 380 KB) ⚠️. Evidence:
  [repository](https://github.com/shashwatak/satellite-js),
  [unpkg metadata](https://unpkg.com/satellite.js/?meta).

### Skyfield and sgp4 (Python)

[rhodesmill.org/skyfield/earth-satellites.html](https://rhodesmill.org/skyfield/earth-satellites.html).
Brandon Rhodes. **needs owner action** (a dependency decision), confirmed.

Satellite passes (`find_events`, with greatest altitude "accurate to within
a second or so"), `is_sunlit` (needs an ephemeris for the Sun's position),
loading from OMM JSON or CSV (`from_omm`, which needs a timescale for leap
seconds), and advice to save element files rather than re-download them.

- **Coverage:** global.
- **Access:** PyPI packages `skyfield` and `sgp4`. Skyfield needs NumPy,
  and a JPL ephemeris file (such as `de421.bsp`) for `is_sunlit`, which is
  a data download. No key. Skyfield is MIT; sgp4 is MIT ⚠️ (not re-read).
  Libraries, so robots.txt doesn't apply.
- **Use cases:** server-side pass lists for the Valley Feed ("ISS bright
  pass tonight").
- **Personas:** stargazer.
- **Needs from core:** none. **Effort** S.
- **Risks:** breaks the "Python 3.11, standard library only" rule (NumPy is
  a binary dependency), and the ephemeris file is a dataset download; the
  owner decides. Alternatives: compute passes in the browser with
  satellite.js, or port SGP4 to standard-library Python.
- **Checked:** the page's quotes, Skyfield's MIT license and its NumPy
  dependency are confirmed. Evidence:
  [Skyfield satellites page](https://rhodesmill.org/skyfield/earth-satellites.html),
  [repository](https://github.com/skyfielders/python-skyfield).

### NASA ISS trajectory (CCSDS OEM, J2000)

[ISS.OEM_J2K_EPH.txt](https://nasa-public-data.s3.amazonaws.com/iss-coords/current/ISS_OEM/ISS.OEM_J2K_EPH.txt).
NASA Johnson Space Center, Flight Operations Directorate (TOPO). **use**,
corrected.

CCSDS OEM v2.0: predicted ISS state vectors (position in km, velocity in
km/s) every 4 minutes in EME2000 (mean of J2000), UTC. The file current on
Oct 7 (created 2026-10-05T20:52:43) was usable from 2026-10-05T12:00 to
2026-10-20T12:00. Comments hold mass and drag area, ascending-node epochs
and a trajectory event table (Crew12 undock, NG24 departure, SpX-35 launch
and docking) with apogee and perigee heights. NASA says it includes
maneuver details and predicted post-maneuver vectors. An XML twin sits
alongside.

- **Coverage:** the ISS only, worldwide.
- **Access:** permanent "current" links on S3 (TXT and XML); dated archives
  on data.nasa.gov and catalog.data.gov, which also list ISS
  sighting-opportunity XML files for cities and parks. No key. Public
  domain (catalog.data.gov: `usa.gov/publicdomain/label/1.0`). robots.txt
  on `nasa-public-data.s3.amazonaws.com` returns 404 (S3 NoSuchKey), so no
  rules (re-checked). The verifier made one 2.5 KB byte-range read of the
  header.
- **Updates and size:** daily per data.gov (R/P1D), but irregular: at
  05:43 UTC on Oct 7 the file still showed Last-Modified 2026-10-05 20:43
  UTC, over 33 h old. 718,711 bytes per file: about 260 MB a year if every
  file is kept, or about 17 MB a year keeping only the first day of each.
- **Use cases:** ISS passes over the valley, more accurate than TLEs around
  reboosts; an ISS track in 3D and on the dome; visible passes in the
  Valley Feed.
- **Personas:** stargazer, families and everyone.
- **Needs from core:** tracks contract, time and replay clock, Valley Feed.
  **Effort** S.
- **Risks:** fetch at most once a day, and only when Last-Modified changes.
  The states are inertial J2000: they need precession, nutation and Earth
  rotation to reach Earth-fixed coordinates, and Hermite interpolation
  between the 4-minute points ([correction 4](#design-corrections-from-verification)).
- **Checked:** the header read confirms format, frame, span, interval,
  events and total size (Content-Range /718711). The cadence was softened
  from "about daily" because the file hadn't changed in over 33 hours.
  License, publisher and NASA's description are confirmed. Evidence:
  [current file](https://nasa-public-data.s3.amazonaws.com/iss-coords/current/ISS_OEM/ISS.OEM_J2K_EPH.txt)
  (byte-range header read),
  [robots.txt](https://nasa-public-data.s3.amazonaws.com/robots.txt),
  [catalog.data.gov](https://catalog.data.gov/dataset/iss_coords_2021-11-02),
  [NASA](https://www.nasa.gov/?p=308017).

### SatNOGS DB TLE API

[db.satnogs.org/api/tle](https://db.satnogs.org/api/tle/). Libre Space
Foundation (SatNOGS). **use**, corrected.

The latest TLE per satellite, with `tle_source` and an updated timestamp,
and a paginated `/api/tle/historical/` endpoint filtered by NORAD or
satellite ID. Formats are only `3le` and `json` (TLE lines in JSON); there
is no OMM endpoint. The API root lists artifacts, modes, satellites,
transmitters, telemetry, tle, optical-observations and
transmitter-params-schemas.

- **Coverage:** satellites in the SatNOGS DB (an amateur-radio focus) with
  5-digit catalog numbers. CelesTrak reports the 5-digit numbers ran out
  on 2026-07-11, so objects catalogued since then, including most new
  Starlinks, can't be expressed as TLEs.
- **Access:** `GET https://db.satnogs.org/api/tle/?norad_cat_id=<id>&format=json`.
  The researcher's anonymous GET worked, but the OpenAPI schema lists token
  auth (`Authorization: Token …`) and cookie auth on `/api/tle/` and
  `/api/tle/historical/`. License CC BY-SA 4.0 ("All API data are freely
  distributed under the CC BY-SA license"); the TLEs originate at
  Space-Track, so cite both. robots.txt: `user-agent: *` with
  `Disallow: /admin/` only, so the API is allowed (re-checked).
- **Updates and size:** several times a day as SatNOGS refreshes from its
  sources ⚠️; KB per satellite, a few MB at most for the full list.
- **Use cases:** daily elements for the ISS, Tiangong, Hubble and other
  long-catalogued bright satellites, archived in `raw.record` so replay can
  re-propagate; historical TLEs for past nights (probably with a token).
- **Personas:** stargazer.
- **Needs from core:** tracks contract, time and replay clock. **Effort** S.
- **Risks:** share-alike applies to any element tables we publish. If the
  declared token auth starts being enforced, a free SatNOGS account becomes
  an owner action. TLE-only, so no 6-digit catalog numbers.
- **Checked:** license and robots.txt confirmed. Corrected: the schema
  declares token or cookie auth; there's no OMM option (format is
  `3le|json`); TLE exhaustion has already happened, not "upcoming"; a
  historical endpoint exists. Evidence:
  [API docs](https://docs.satnogs.org/projects/satnogs-db/en/stable/api.html),
  [robots.txt](https://db.satnogs.org/robots.txt),
  [API root](https://db.satnogs.org/api/),
  [schema](https://db.satnogs.org/api/schema/),
  [CelesTrak on formats](https://celestrak.org/NORAD/documentation/gp-data-formats.php).

### CelesTrak GP and Supplemental GP

[celestrak.org GP data formats](https://celestrak.org/NORAD/documentation/gp-data-formats.php).
CelesTrak (Dr. T.S. Kelso). **needs owner action**, confirmed.

GP elements for the whole catalog and for groups (active, Starlink,
stations, visual) in TLE, 3LE, 2LE, OMM XML, KVN, JSON and CSV (`FORMAT`
defaults to CSV since 2026 May 09). Supplemental GP (SupGP) comes from
operator ephemerides, including Starlink; recent Starlink launches use
9-digit 799xxxxxx launch-nominal numbers. Also SATCAT. Since 2026-07-11,
new objects have 6-digit catalog numbers with no TLE form, so any use must
be CSV, JSON or XML.

- **Coverage:** every tracked object.
- **Access:** `https://celestrak.org/NORAD/elements/gp.php?GROUP=...&FORMAT=json`.
  The usage policy (updated 2026 May 22): GP updates every 2 hours; "only
  download data once per update"; machine clients must stop on any
  non-200. The GP-formats FAQ: a 250 MB daily limit; one download per
  update enforced for Active and Starlink since 2026 Mar 26 (repeats get
  HTTP 403); a firewall after 50 HTTP errors (301, 403, 404) in 2 hours,
  and after more than 1,000 403s in a day. No key. No license,
  redistribution or attribution terms found on the usage-policy or GP-format
  pages.
- **robots.txt: disallowed.** For `User-agent: *` it disallows
  `/NORAD/elements/gp*.php`, `/NORAD/elements/supplemental/sup-gp.php`,
  `/*.txt`, `/*.csv`, `/*.zip`, `/SpaceTrack/`, the `/satcat/` table,
  record, search and TLE pages, and more; `User-agent: claudebot` has
  `Disallow: /` (re-checked Oct 7, UTC).
- **Updates and size:** every 2 hours; a few MB per group.
- **Use cases:** Starlink trains after launches (SupGP is the best public
  source); the visual-satellite group.
- **Personas:** stargazer.
- **Needs from core:** tracks contract. **Effort** S.
- **Risks:** automated access contradicts robots.txt. Options: the owner
  asks CelesTrak for a written OK for one daily download of 2–3 groups in
  CSV or JSON with our User-Agent, or downloads by hand
  ([open questions](#open-questions)).
- **Checked:** every figure checks out. The 2-hour cadence, once-per-update
  and stop-on-non-200 rules are on the usage-policy page; the 250 MB limit,
  the 2026-03-26 enforcement and the firewall rules are in the GP-formats
  FAQ. Evidence: [robots.txt](https://celestrak.org/robots.txt),
  [GP data formats](https://celestrak.org/NORAD/documentation/gp-data-formats.php),
  [usage policy](https://celestrak.org/usage-policy.php).

### Space-Track.org

[space-track.org documentation](https://www.space-track.org/documentation#user_agree).
US Space Command / US Space Force (18th and 19th Space Defense Squadrons).
**needs owner action** (an account), confirmed.

The authoritative GP catalog (every object, including Starlink, with OMM
for 6- and 9-digit numbers), GP history, SATCAT, and decay and reentry
(TIP) messages.

- **Coverage:** every tracked object, with history.
- **Access:** REST API after login. Limits: under 30 requests a minute and
  300 an hour; query GP once an hour at a random minute away from the top
  of the hour; fetch GP_History "once per lifetime" and keep it locally.
  Needs an individual account. The user agreement forbids transferring data
  "without prior express approval", but USSPACECOM gives blanket approval
  to redistribute basic SSA data (TLEs, OMMs, SATCAT, decay) "conditioned
  on appropriate citation". robots.txt disallows only `/cgi-bin/`,
  `/tmp/`, `/arrowchat/`, `/assets/` and `/system/` for `*`, so the API
  paths are allowed (re-checked).
- **Updates and size:** continuous, GP hourly; MB a day for a few groups.
- **Use cases:** Starlink and every visible satellite (OMM, so 6-digit
  numbers work); historical elements for replaying past nights; reentry
  predictions.
- **Personas:** stargazer.
- **Needs from core:** tracks contract, time and replay clock, full replay.
  **Effort** M.
- **Risks:** the account must be the owner's own; credentials can't be
  shared and would live only in the server's `.env`. Cite Space-Track on
  anything derived.
- **Checked:** agreement clauses, the blanket approval, rate limits, the GP
  and GP_History guidance and the account requirement are confirmed;
  robots.txt confirmed verbatim. Evidence:
  [robots.txt](https://www.space-track.org/robots.txt),
  [user agreement](https://www.space-track.org/documentation#user_agree).

## Stars and the night-sky dome

### HYG star database v4.4 (and AT-HYG)

[codeberg.org/astronexus/hyg](https://codeberg.org/astronexus/hyg). David
Nash (astronexus). **use**, confirmed.

HYG v4.4: 119,614 stars merged from Hipparcos, the Yale Bright Star
catalog and Gliese, with positions, magnitudes, spectral types, colour
index and IDs. AT-HYG: about 118,971 stars based on Tycho-2 and Gaia, with
Gaia DR3 distances and velocities. Also a miscellaneous list of about 220k
deep-sky objects, mostly galaxies.

- **Coverage:** the whole sky to about magnitude 8–9 (Hipparcos
  completeness).
- **Access:** a Git repository on Codeberg with Git LFS (the GitHub repo was
  archived on Feb 14, 2025 and points to Codeberg); the owner clones it by
  hand once. No key. CC BY-SA 4.0 for v4.x (CC BY-SA 2.5 for v3 and
  earlier).
- **robots.txt:** astronexus.com disallows `/downloads/catalogs` for `*`
  and disallows ClaudeBot, GPTBot, CCBot and others entirely. codeberg.org
  disallows `/*/*/raw/`, `/*/*/src/`, `/*/*/media/` (where LFS files are
  served), `/*/*/archive/`, `/*/*/releases/download` and `/api/` for `*`.
  So no scripted download; the owner clones by hand.
- **Updates and size:** rare; a 123 MiB repository; a magnitude ≤ 6.5
  subset of about 9k stars is under 200 KB as binary.
- **Use cases:** stars for the night-sky dome with B–V colour; star names
  for picking.
- **Personas:** stargazer, camper, photographer.
- **Needs from core:** 3D engine. **Effort** S.
- **Risks:** share-alike: a derived star table we publish must be CC BY-SA.
  Keep it out of the MIT code tree, or in a data folder with its own
  license notice.
- **Checked:** version, star counts, licenses, LFS and the 123 MiB size
  confirmed on Codeberg; the archived GitHub repo confirms the move.
  Evidence: [Codeberg](https://codeberg.org/astronexus/hyg),
  [archived GitHub repo](https://github.com/astronexus/HYG-Database),
  [astronexus robots.txt](https://www.astronexus.com/robots.txt),
  [Codeberg robots.txt](https://codeberg.org/robots.txt).

### d3-celestial data

[github.com/ofrohn/d3-celestial](https://github.com/ofrohn/d3-celestial).
Olaf Frohn. **use**, corrected.

GeoJSON at J2000 (right ascension converted to −180..180 longitude): stars
to magnitude 6, 8.5 and 14; star names in several languages; constellation
lines, boundaries and names (IAU and Traditional Chinese); "Milky Way
outlines in 5 brightness steps"; deep-sky objects to magnitude 6, 14 and
20, showpieces and Messier; asterisms; local-group galaxies; globular
clusters; planetary Keplerian elements. Sources: XHIP, SAC, IAU, Stellarium
sky cultures, JPL and VizieR.

- **Coverage:** the whole sky.
- **Access:** clone the repository (or npm) once. No key. BSD-3-Clause for
  the repository; no separate data license found. A one-time clone of a
  public repository, not a crawl.
- **Updates and size:** static; a few MB of GeoJSON.
- **Use cases:** constellation lines and boundaries, and a vector Milky Way
  fallback, on the dome; a ready star list to magnitude 6.
- **Personas:** stargazer, families and everyone.
- **Needs from core:** 3D engine. **Effort** S.
- **Risks:** some names come from Stellarium sky cultures, whose licenses
  vary ⚠️; if in doubt use only the IAU-based lines and boundaries.
- **Checked:** BSD-3-Clause, J2000 GeoJSON and the cited sources are
  confirmed. Corrected: star files go to magnitude 8.5, not 8; the contents
  list now includes the other files. Evidence:
  [repository](https://github.com/ofrohn/d3-celestial).

### NASA SVS Deep Star Maps 2020

[svs.gsfc.nasa.gov/4851](https://svs.gsfc.nasa.gov/4851). NASA Goddard
Scientific Visualization Studio. **use**, confirmed.

1.7 billion stars rendered as plate carrée maps in celestial (ICRF/J2000)
and galactic coordinates, from 4K up to 64K (65536 × 32768). Star maps are
OpenEXR half-float; constellation figure and boundary overlays are
grayscale TIFF; JPGs too. Built from Hipparcos-2 (brighter than 8.0),
Tycho-2 (8.0–11.5) and Gaia DR2, plus YBSC, UCAC3 and XHIP. Constellation
figures are based on Alan MacRobert's work.

- **Coverage:** the whole sky.
- **Access:** direct downloads from the SVS page (up to 3.8 GB for the 64K
  EXR); the owner downloads one 8K celestial map by hand. No key. The SVS
  help page: "All of our content is in the public domain (unless otherwise
  noted)". Credit "NASA/Goddard Space Flight Center Scientific
  Visualization Studio. Gaia DR2: ESA/Gaia/DPAC." robots.txt returns 404
  (an HTML "Resource not found" page), so no rules.
- **Updates and size:** static (2020); tens to hundreds of MB for one 8K–16K
  map, served as KTX2/Basis tiles of a few MB.
- **Use cases:** the Milky Way and faint-star background on the night dome,
  faded by light pollution, moon and twilight.
- **Personas:** stargazer, camper, photographer.
- **Needs from core:** 3D engine. **Effort** S.
- **Risks:** contains Gaia-derived content (ESA licenses Gaia data CC BY-NC
  3.0 IGO), so credit ESA and keep uses non-commercial. The map already
  holds the bright stars, so it double-counts with HYG sprites unless
  they're masked. A 16K texture is too big for a laptop GPU uncompressed
  ([correction 8](#design-corrections-from-verification)).
- **Checked:** every stated fact confirmed on the SVS page and help page;
  the robots.txt 404 confirmed; the size estimate adjusted for an 8K map.
  Evidence: [SVS 4851](https://svs.gsfc.nasa.gov/4851),
  [SVS help](https://svs.gsfc.nasa.gov/help/),
  [robots.txt](https://svs.gsfc.nasa.gov/robots.txt).

### ESA Gaia Archive

[Gaia license page](https://www.cosmos.esa.int/web/gaia-users/license).
European Space Agency (Gaia DPAC). **avoid**, confirmed.

Gaia DR3 astrometry and photometry for about 1.8 billion sources.

- **Coverage:** the whole sky, very deep.
- **Access:** TAP and archive queries at `gea.esac.esa.int`; bulk files at
  `cdn.gea.esac.esa.int`. No key. "Gaia data are distributed under the
  CC BY-NC 3.0 IGO license"; commercial use falls under ESA's archive
  terms and conditions. robots.txt on `gea.esac.esa.int` allows only
  `/archive/documentation/` for GDR1–GDR4, GEDR3 and FPR, then
  `Disallow: /`; `cdn.gea.esac.esa.int` returns 404 (no rules).
- **Use cases:** not needed: a naked-eye or binocular dome needs magnitude
  6.5–9, which HYG and the SVS texture cover.
- **Personas:** stargazer. **Effort** L.
- **Risks:** robots.txt disallows the archive; a non-commercial license;
  far more data than we need.
- **Checked:** license sentence and both robots.txt results confirmed
  verbatim. Evidence:
  [license](https://www.cosmos.esa.int/web/gaia-users/license),
  [archive robots.txt](https://gea.esac.esa.int/robots.txt),
  [CDN robots.txt](https://cdn.gea.esac.esa.int/robots.txt).

## Light pollution and dark skies

### EOG VIIRS Nighttime Lights (VNL)

[eogdata.mines.edu/products/vnl](https://eogdata.mines.edu/products/vnl/).
Earth Observation Group, Payne Institute, Colorado School of Mines.
**needs owner action**, confirmed.

Cloud-free VIIRS day/night band radiance composites in nW/cm²/sr, at 15
arc-seconds (about 500 m), as GeoTIFF (DEFLATE) in EPSG:4326. Annual
V2, V2.1 and V2.2 (latest v2.2) layers: average, average-masked, median,
median-masked, minimum, maximum, `cf_cvg` (cloud-free coverage) and
coverage; monthly products separately. The product page still describes
V2 as 2012–2020; the 2012–2024 range for V2.2 comes only from secondary
sources ⚠️.

- **Coverage:** global; the ring clips to about 408 × 336 pixels a year.
- **Access:** downloads under `eogdata.mines.edu/nighttime_light/`. A free
  account (approved in 1–2 days) has been required since 2025, according to
  secondary sources only ⚠️; the product page doesn't say. License: "Many
  of the VIIRS Nighttime Lights data are available under Creative Commons
  Attribution 4.0"; cite EOG and the product paper (Elvidge et al. 2021,
  Remote Sensing 13(5):922).
- **robots.txt:** for `*`, `Allow: /`, `Disallow: /wwwdata` and
  `Disallow: /nighttime_light` (EarthEngineBot may fetch everything). So no
  scripted downloads; the owner downloads by hand.
- **Updates and size:** annual and monthly; global files are GBs, under 1
  MB a year for the ring after clipping.
- **Use cases:** a light-pollution layer; the valley's light dome growing
  year by year on the year slider (with the `development` plugin); input to
  the dark-sky finder and the dome's sky brightness.
- **Personas:** stargazer, camper, land and development watcher, wildlife.
- **Needs from core:** layer system, basemap build, time and replay clock
  (the year slider). **Effort** S.
- **Risks:** registration is an owner action; robots.txt forbids
  automation; the license says "many", so check each file's readme.
- **Checked:** robots.txt, license wording, versions, layers, resolution
  and units confirmed on the official pages. The account requirement and
  the 2012–2024 range remain secondary-only (a third-party tool page and
  the Earth Engine catalog). Evidence:
  [product page](https://eogdata.mines.edu/products/vnl/),
  [robots.txt](https://eogdata.mines.edu/robots.txt),
  [Earth Engine catalog](https://developers.google.com/earth-engine/datasets/catalog/NOAA_VIIRS_DNB_ANNUAL_V22)
  (search result ⚠️).

### NASA Black Marble (VNP46A1–A4, VJ146)

[earthdata.nasa.gov Black Marble](https://www.earthdata.nasa.gov/data/projects/black-marble).
NASA GSFC / LAADS DAAC. **needs owner action**, corrected.

Daily, monthly and yearly VIIRS night-light radiance with atmospheric,
terrain, lunar-BRDF and stray-light corrections (snow handled through flags
⚠️). VNP46 (S-NPP) from 2012-01-19, VJ146 (NOAA-20) from 2018-01-05,
VJ246 (NOAA-21) in development. Collection 2 has been current since
2025-08-25 (Collection 1 terminated). Gridded at 15 arc-seconds; the page
quotes the sensor's 750 m resolution ⚠️.

- **Coverage:** global; the ring is one tile.
- **Access:** HDF-EOS5 tiles from LAADS DAAC behind Earthdata Login (an
  account). NASA's open science policy: no restrictions on reuse; credit
  NASA Black Marble.
- **robots.txt:** `ladsweb.modaps.eosdis.nasa.gov/robots.txt` answers 303
  to `/profiles/licenses/robots.txt`, which redirects to the
  `urs.earthdata.nasa.gov` OAuth login page (HTML). Unreadable, so treated
  as disallowed (conservative; RFC 9309 doesn't directly cover a login
  page). The owner downloads by hand.
- **Updates and size:** daily (near real time), monthly, yearly; tens of MB
  per yearly tile, KB after clipping.
- **Use cases:** moon- and snow-corrected change detection: new
  subdivisions lighting up, outages after storms.
- **Personas:** land and development watcher, stargazer.
- **Needs from core:** layer system, time and replay clock. **Effort** M.
- **Risks:** needs an Earthdata account; HDF5 decoding needs h5py or GDAL,
  a dependency decision.
- **Checked:** products, dates and format confirmed. Added NOAA-21,
  Collection 2 and the terrain and stray-light corrections; the robots.txt
  path is a 303 redirect chain ending at the login, not a direct redirect.
  Evidence:
  [Black Marble](https://www.earthdata.nasa.gov/data/projects/black-marble),
  [robots.txt](https://ladsweb.modaps.eosdis.nasa.gov/robots.txt).

### NASA GIBS night-lights imagery

[GIBS access basics](https://nasa-gibs.github.io/gibs-api-docs/access-basics/).
NASA ESDIS (GIBS). **use**, confirmed.

Keyless WMTS (REST and KVP), WMS, TWMS and XYZ in EPSG:4326, 3857, 3413 and
3031. Night layers: `VIIRS_Black_Marble` (2012 and 2016 snapshots) and
`VIIRS_SNPP_DayNightBand_ENCC` (daily since 2016-11-30; 500 m imagery from
the 750 m sensor) ⚠️ (layer facts from Earthdata blog and wiki pages via
search).

- **Coverage:** global.
- **Access:** `https://gibs.earthdata.nasa.gov/wmts/...`; no key or login
  mentioned in the docs. The access page states no restrictions or
  attribution rules; credit NASA GIBS/Worldview. robots.txt returns 404,
  so no rules (re-checked).
- **Updates and size:** daily for the day/night band layer; a few MB to
  cache the ring at zoom 9 and below.
- **Use cases:** a quick pictorial night-lights backdrop, cached into our
  own `/tiles/` (the map never calls GIBS directly).
- **Personas:** stargazer, everyone.
- **Needs from core:** basemap build, layer system. **Effort** S.
- **Risks:** pictures, not radiance values; use EOG or Black Marble for
  numbers.
- **Checked:** keyless access, protocols, projections and the robots.txt
  404 confirmed. Layer names and dates come from search snippets of
  Earthdata pages, not a capabilities document, so they stay ⚠️. Evidence:
  [access basics](https://nasa-gibs.github.io/gibs-api-docs/access-basics/),
  [robots.txt](https://gibs.earthdata.nasa.gov/robots.txt),
  [Earthdata blog](https://www.earthdata.nasa.gov/news/blog/announcing-viirs-nighttime-imagery-day-night-band)
  (search result ⚠️).

### New World Atlas of Artificial Night Sky Brightness (Falchi et al. 2016)

[GFZ Data Services landing page](https://dataservices.gfz.de/10.5880/gfz.1.4.2016.001/supplement-to-the-new-world-atlas-of-artificial).
Falchi et al. (ISTIL); GFZ Data Services. **needs owner action**,
corrected.

Simulated artificial zenith sky radiance (mcd/m²) at 30 arc-seconds, from
VIIRS day/night band data with radiative-transfer modelling, calibrated
with Sky Quality Meters: a 2.9 GB GeoTIFF plus a KMZ. Artificial light
only: natural sky brightness (stars, Milky Way) must be added. The VIIRS
year isn't on the landing page (2014 per secondary sources ⚠️).

- **Coverage:** global; the ring clips to about 204 × 168 cells.
- **Access:** the DOI resolves to `dataservices.gfz.de` (the old
  `dataservices.gfz-potsdam.de` host was renamed). The description says FTP
  access is requested through a data request form; the landing page's own
  config now shows a "Download data and description" link to
  `datapub.gfz.de` with downloads available ⚠️, so the form may no longer
  be needed. The owner downloads by hand either way. Whether an account is
  needed is unknown. License CC BY-NC 4.0, confirmed on the landing page
  (schema.org license CC-BY-NC-4.0; changed 13 November 2019 "after end of
  embargo period").
- **robots.txt:** `dataservices.gfz.de` has an empty `Disallow` for `*`
  (all allowed), but disallows ClaudeBot, Claude-User, GPTBot, CCBot and
  other AI agents from `/10.`, `/datasets/` and `/portal`. Our honest
  project User-Agent falls under `*`. `datapub.gfz.de/robots.txt` returns
  403 (no rules); the old host's returned 404.
- **Updates and size:** static (2016; v1.1); 2.9 GB source, under 1 MB
  after clipping.
- **Use cases:** the sky-brightness class at any spot (Boise's core against
  Bruneau Dunes), which sets the dome's limiting magnitude; the dark-sky
  finder.
- **Personas:** stargazer, camper, photographer.
- **Needs from core:** layer system, basemap build. **Effort** S.
- **Risks:** non-commercial license (fits this project; record republishing
  as non-commercial). Its VIIRS lights predate recent growth, so combine
  with VNL for trends.
- **Checked:** the landing page now renders through the DOI's new host, so
  license, file description and request-form text come from the publisher
  rather than b2find. Corrected the host name, the robots.txt result for
  the new host, that access may now be a direct download, and auth (now
  unknown). Evidence: [DOI](https://doi.org/10.5880/GFZ.1.4.2016.001),
  [landing page](https://dataservices.gfz.de/10.5880/gfz.1.4.2016.001/supplement-to-the-new-world-atlas-of-artificial),
  [robots.txt](https://dataservices.gfz.de/robots.txt),
  [datapub robots.txt](https://datapub.gfz.de/robots.txt),
  [old host robots.txt](https://dataservices.gfz-potsdam.de/robots.txt).

### Globe at Night observations

[globeatnight.org/maps-data](https://globeatnight.org/maps-data/). NSF
NOIRLab. **internal only**, corrected.

Citizen naked-eye limiting-magnitude estimates and Sky Quality Meter
readings since 2006. Recent years come as CSV and JSON (2022 also XLSX);
older years as KMZ, XLS, CSV and SQM KMZ. 13,421 observations in 2025;
14,377 in 2024.

- **Coverage:** global but sparse; the density in the Treasure Valley is
  unknown.
- **Access:** yearly file downloads from the maps-data page (`maps.php` now
  301-redirects there). No key. "Globe at Night data is made available
  under a Creative Commons Attribution 4.0 International License".
  robots.txt returns HTTP 404 (an HTML "Page not found"), so no rules. A
  fetch tool got 403 on the page; a plain request with our project
  User-Agent got 200.
- **Updates and size:** yearly files, MB a year.
- **Use cases:** ground truth for the Falchi and VIIRS sky-brightness layer.
- **Personas:** stargazer.
- **Needs from core:** layer system. **Effort** S.
- **Risks:** points are often observers' homes. Aggregate to about 2 km
  cells, at ingest too (recent files include coordinates); never show raw
  points.
- **Checked:** license quote confirmed. Corrected the URL (moved to
  `/maps-data/`), the formats (recent years CSV and JSON) and the coverage
  (through 2025). Evidence:
  [maps and data](https://globeatnight.org/maps-data/),
  [robots.txt](https://globeatnight.org/robots.txt).

### lightpollutionmap.info

[lightpollutionmap.info](https://www.lightpollutionmap.info/). Jurij Stare
(a private site). **avoid**, confirmed.

Web-map overlays of VIIRS, Black Marble and Falchi data, served as tiles
through `/geoserver/`.

- **Coverage:** global.
- **Terms:** no key; license not checked, since the verdict is avoid.
  robots.txt disallows `/geoserver/` and `/dev/` for `*` (re-checked).
- **Use cases:** link out only; we take the originals from EOG, NASA and
  GFZ.
- **Personas:** stargazer. **Effort** S.
- **Risks:** its tile endpoint is disallowed, and it's a third party's
  derived product.
- **Checked:** robots.txt confirmed verbatim. Evidence:
  [robots.txt](https://www.lightpollutionmap.info/robots.txt).

### Idaho dark-sky places (a hand-entered list)

[Bruneau Dunes State Park](https://parksandrecreation.idaho.gov/state-park/bruneau-dunes-state-park/).
DarkSky International; Idaho Parks and Recreation; Central Idaho Dark Sky
Reserve partners. **use**, corrected.

- **Bruneau Dunes State Park:** a 25-inch Obsession telescope (donated by
  BAS, in use since 1998) and, since 2023, a second observatory with a
  PlaneWave CDK700 for imaging and remote use, whose dome doubles as a
  planetarium. Programs on Friday and Saturday nights, March 13 to
  October 17; $5, families $20, children 5 and under free. At 42.9100,
  −115.70972, just inside the ring's south-east corner. The Idaho Business
  Review says Bruneau "earned its Dark Sky Park designation in June 2024".
- **Elsewhere in Idaho:** Visit Idaho lists Bruneau Dunes, Craters of the
  Moon and City of Rocks as International Dark Sky Parks (the latter two are
  outside the ring). The Central Idaho Dark Sky Reserve covers 906,000 acres
  (about 1,416 sq mi) around Sun Valley, Ketchum and Stanley, the first in
  the US (Visit Idaho). Its Dec 18, 2017 date, Gold tier and county list
  are secondary ⚠️.

Details:
- **Coverage:** Idaho; within the ring, only Bruneau Dunes.
- **Access:** entered by hand from official pages; darksky.org place pages
  return HTTP 403 (a bot challenge), which we won't bypass. Facts only,
  with credit; no copied text or maps. robots.txt: darksky.org disallows
  only `/wp/wp-admin/`, but its place pages answer 403, so nothing is
  automated; `parksandrecreation.idaho.gov` allows everything (empty
  `Disallow`).
- **Updates and size:** rare, plus the yearly observatory season; a handful
  of points.
- **Use cases:** dark-sky destinations on the map and in search;
  observatory open nights in the Valley Feed.
- **Personas:** stargazer, camper, families and everyone.
- **Needs from core:** places and search, areas, lifecycles contract
  (observatory nights). **Effort** S.
- **Risks:** confirm the certification on darksky.org in a browser (the
  owner) before labelling it official.
- **Checked:** the park page does **not** say "not formally certified", as
  first reported; it only says Idaho parks are striving to obtain Dark Sky
  certifications where appropriate, which neither confirms nor denies. The
  Idaho Business Review article (read directly) gives June 2024, and Visit
  Idaho lists Bruneau as a Dark Sky Park, so the earlier conflict largely
  disappears. Telescope, schedule, price and coordinates confirmed; the
  park's canonical URL has changed. Evidence:
  [park page](https://parksandrecreation.idaho.gov/parks/bruneau-dunes/)
  (redirects to the new URL),
  [parks robots.txt](https://parksandrecreation.idaho.gov/robots.txt),
  [darksky.org robots.txt](https://darksky.org/robots.txt),
  [Central Idaho Dark Sky Reserve](https://darksky.org/places/central-idaho-dark-sky-reserve/)
  (403),
  [Idaho Business Review](https://idahobusinessreview.com/2024/08/21/southern-idaho-has-a-new-international-dark-sky-park/),
  [Visit Idaho](https://visitidaho.org/things-to-do/dark-skies/).

## Aurora and space weather

### NOAA SWPC data service (OVATION aurora, Kp)

[services.swpc.noaa.gov/json](https://services.swpc.noaa.gov/json/). NOAA
Space Weather Prediction Center. **use**, confirmed.

`ovation_aurora_latest.json` from OVATION Prime 2020, the JHU/APL empirical
model, with a 30–90 minute lead from solar wind measured at L1; it falls
back to Kp with no lead when solar-wind data are missing. Per the
researcher's byte-range read: Observation and Forecast Time plus a global
1° grid of `[Longitude, Latitude, Aurora]` with values 0–100. Also
`planetary_k_index_1m.json`, `boulder_k_index_1m.json`, `/products`,
`/text` and `/images`; the long-term archive is at NCEI.

- **Coverage:** global; the northern grid includes Idaho's latitudes.
- **Access:** plain HTTPS GET, no key. Directory listing at 05:46 UTC on
  Oct 7: `ovation_aurora_latest.json` 898K, `planetary_k_index_1m.json`
  27K, `boulder_k_index_1m.json` 84K. A US government work, public domain
  ⚠️ (no explicit statement on the product or data-access pages); credit
  NOAA SWPC. robots.txt on `services.swpc.noaa.gov` returns 404 (no
  rules); `www.spaceweather.gov`'s blocks only `/core/`, `/profiles/`,
  admin, search and user paths (re-checked).
- **Updates and size:** OVATION about every 5 minutes ⚠️; Kp every minute.
  A 125–105°W, 35–65°N slice (651 cells) every 30 minutes is about 11.4 M
  values a year, which is under 10 MB only if each snapshot is stored as
  one compressed array ([correction 6](#design-corrections-from-verification)).
- **Use cases:** the aurora chance north of the valley, with a Valley Feed
  alert when Kp reaches 6–7 and skies are clear; an aurora glow on the
  dome's northern horizon; an archive for replaying future storms.
- **Personas:** stargazer, photographer, camper.
- **Needs from core:** readings contract, Valley Feed, time and replay
  clock. **Effort** S.
- **Risks:** OVATION gives overhead intensity or probability, and SWPC
  notes bright aurora "can often be observed from as much as a 1000 km
  away", so use a viewline offset and label it approximate.
- **Checked:** files, sizes, model, lead time, fallback and both robots.txt
  results confirmed. The 1° grid and 0–100 range rest on the researcher's
  byte-range read; the product page doesn't state them. The storage
  estimate was checked and qualified. Evidence:
  [JSON directory](https://services.swpc.noaa.gov/json/),
  [aurora forecast](https://www.spaceweather.gov/products/aurora-30-minute-forecast),
  [data access](https://www.spaceweather.gov/content/data-access),
  [spaceweather.gov robots.txt](https://www.spaceweather.gov/robots.txt),
  [services robots.txt](https://services.swpc.noaa.gov/robots.txt).

### GFZ Kp index (since 1932)

[kp.gfz.de/en/data](https://kp.gfz.de/en/data). GFZ Helmholtz Centre for
Geosciences. **use**, confirmed.

Kp, ap, Ap, Cp, C9, Hp30, Hp60, ap30, ap60, SN and F10.7 (Fobs, Fadj):
definitive since 1932, with a nowcast in near real time.

- **Coverage:** a planetary index: one Kp value per 3 h; Hp30 and Hp60 at
  30 and 60 minutes.
- **Access:** files and a JSON API:
  `https://kp.gfz.de/app/json/?start=...&end=...&index=Kp&status=def`. No
  key. CC BY 4.0; users must refer to GFZ as the data source. Dataset DOI
  10.5880/Kp.0001. robots.txt returns 404 (an HTML TYPO3 page), so no
  rules (re-checked).
- **Updates and size:** nowcast in near real time, definitive monthly; a
  few MB for the full history.
- **Use cases:** replaying historic storms on the dome (such as the G5
  storm of May 10–11, 2024, widely seen in Idaho ⚠️); climatology of how
  often Kp is high enough for aurora at Boise.
- **Personas:** stargazer, photographer.
- **Needs from core:** readings contract, full replay. **Effort** S.
- **Risks:** none.
- **Checked:** license, attribution, API pattern and index list confirmed;
  Hp30 and Hp60 added. The nowcast cadence isn't stated as a number on the
  pages read. Evidence: [data](https://kp.gfz.de/en/data),
  [home](https://kp.gfz.de/en/), [robots.txt](https://kp.gfz.de/robots.txt).

## Meteors and fireballs

### IMO Meteor Shower Calendar

[imo.net](https://www.imo.net/). International Meteor Organization.
**use** (facts only), confirmed.

A yearly PDF with each shower's activity period, peak, ZHR, radiant,
velocity and moon conditions. The site is being rebuilt and moved to new
infrastructure; the 2027 calendar and fireball reporting remain.

- **Coverage:** showers worldwide.
- **Access:** the PDF, by hand. No key. "© 2026 International Meteor
  Organization" with no reuse license, so we hand-enter facts only (shower,
  dates, ZHR) with credit and never copy the PDF. `www.imo.net/robots.txt`
  returns HTTP 200 with an HTML page (meta "noindex, nofollow"), which
  holds no valid rules; nothing is automated anyway.
- **Updates and size:** yearly; a table of about 30 rows.
- **Use cases:** the meteor shower calendar on the dome and in the Valley
  Feed (peak nights, radiant rise times, expected rate given the moon and
  sky brightness).
- **Personas:** stargazer, camper, families and everyone.
- **Needs from core:** lifecycles contract, Valley Feed. **Effort** S.
- **Risks:** copyright: keep only facts, credited.
- **Checked:** the rebuild notice, the 2027 calendar, the copyright line and
  the HTML-instead-of-robots.txt response confirmed. Evidence:
  [imo.net](https://www.imo.net/), [robots.txt](https://www.imo.net/robots.txt).

### IAU Meteor Data Center shower lists

[ta3.sk/IAUC22DB/MDC2022](https://www.ta3.sk/IAUC22DB/MDC2022/). IAU Meteor
Data Center (Astronomical Institute, Slovak Academy of Sciences). **use**,
confirmed.

All, established, working-list, pending and permanently removed showers,
with radiants, solar longitude, velocities and parent bodies, plus
templates for shower mean data and lookup tables. A beta database is at
`ceresiaumdc.ta3.sk`.

- **Coverage:** every known shower.
- **Access:** text file downloads, once. No key. No terms stated; cite the
  IAU MDC. robots.txt disallows only `/wp-admin/` (allowing
  `admin-ajax.php`) for `*` (re-checked).
- **Updates and size:** occasional; under 1 MB.
- **Use cases:** radiant positions for the dome, beyond the IMO's major
  showers.
- **Personas:** stargazer.
- **Needs from core:** 3D engine. **Effort** S.
- **Risks:** no explicit license; a small factual table, credited.
- **Checked:** the five lists, the beta site, the missing terms and
  robots.txt confirmed. Evidence:
  [MDC 2022](https://www.ta3.sk/IAUC22DB/MDC2022/),
  [robots.txt](https://www.ta3.sk/robots.txt).

### Global Meteor Network trajectories

[globalmeteornetwork.org/data](https://globalmeteornetwork.org/data/).
Global Meteor Network (Vida et al.). **use**, confirmed.

Meteor trajectories, orbits, radiants, magnitudes and masses, "updated
every 6 hours": `traj_summary_latest_daily.txt`,
`traj_summary_yesterday.txt`, and monthly and full archives. GMN also
publishes KML fields of view for every station (`/data/kml_fov/`), which
we never use.

- **Coverage:** wherever GMN cameras overlap; coverage over southern Idaho
  is unverified.
- **Access:** plain text files under
  `https://globalmeteornetwork.org/data/traj_summary_data/`. No key. CC BY
  4.0 for high-level products; cite the site and the listed papers.
- **robots.txt:** for `*`, disallows wiki `Special:` pages and `api.php`,
  with Crawl-delay 10. ClaudeBot, GPTBot, Amazonbot, Bytespider and others
  are disallowed entirely. Our honest project User-Agent falls under `*`.
- **Updates and size:** every 6 hours; MB a day worldwide, KB for meteors
  over the ring.
- **Use cases:** real meteors drawn as 3D streaks at their true heights over
  the valley during showers.
- **Personas:** stargazer.
- **Needs from core:** 3D engine, time and replay clock, tracks contract.
  **Effort** S.
- **Risks:** camera stations are volunteers' homes and GMN publishes their
  fields of view, so never mirror or show station locations or FOV KMLs,
  only meteors. Honor Crawl-delay 10.
- **Checked:** license, files, cadence and robots.txt confirmed; added that
  the FOV KMLs are public, so the privacy rule must cover them. Evidence:
  [data](https://globalmeteornetwork.org/data/),
  [robots.txt](https://globalmeteornetwork.org/robots.txt).

### CNEOS Fireball API

[ssd-api.jpl.nasa.gov/doc/fireball.html](https://ssd-api.jpl.nasa.gov/doc/fireball.html).
NASA JPL Center for Near-Earth Object Studies. **use**, confirmed.

Fireballs detected by US government sensors. Date, energy and impact energy
are always present; latitude and longitude (with directions) come as a full
set or not at all; altitude and velocity components are often missing.

- **Coverage:** global; events over Idaho are rare.
- **Access:** `GET https://ssd-api.jpl.nasa.gov/fireball.api` (v1.2, July
  2025) with `date-min`/`date-max`, energy, impact-e and altitude ranges,
  `req-loc`, `req-alt`, `req-vel-comp` and `limit`; JSON. No key. NASA/JPL,
  no terms stated. robots.txt returns 404, so no rules.
- **Updates and size:** as events are released; tiny.
- **Use cases:** bright fireballs in the ring on the replay and in the feed.
- **Personas:** stargazer.
- **Needs from core:** lifecycles contract, Valley Feed. **Effort** S.
- **Risks:** sparse; a weekly check is enough.
- **Checked:** fields, filters, version and robots.txt confirmed. Evidence:
  [API docs](https://ssd-api.jpl.nasa.gov/doc/fireball.html),
  [robots.txt](https://ssd-api.jpl.nasa.gov/robots.txt).

### American Meteor Society fireball reports

[amsmeteors.org](https://www.amsmeteors.org/). American Meteor Society.
**avoid**, unverifiable.

Public witness reports of fireballs and derived event trajectories.

- **Coverage:** the US.
- **Access:** the website; a members API page exists at `/members/api/` (a
  JavaScript app), and whether it needs a key is unconfirmed ⚠️. License not
  checked. robots.txt: `User-agent: *` with `Allow: /` (re-checked).
- **Use cases:** not needed beyond CNEOS and GMN.
- **Personas:** stargazer. **Effort** M.
- **Risks:** reports are individual witnesses with locations (people, not
  nature). Avoid unless only event-level trajectories are used.
- **Checked:** robots.txt confirmed. The API page is a client-side app that
  couldn't be read without running scripts, so the key requirement and
  terms stay unverified. Evidence:
  [robots.txt](https://www.amsmeteors.org/robots.txt),
  [members API](https://www.amsmeteors.org/members/api/).

## Eclipses

### NASA eclipse predictions (Espenak) and EclipseWise

[eclipse.gsfc.nasa.gov](https://eclipse.gsfc.nasa.gov/eclipse.html). NASA
GSFC (Fred Espenak); EclipseWise.com. **use**, corrected.

Eclipse catalogs, paths and local circumstances. EclipseWise's 2017 Idaho
page: Boise saw magnitude 0.994, 24 km (15 mi) outside the southern limit;
the shadow crossed the Oregon–Idaho border at 17:26 UT1; central-line
totality in Idaho ran from 2 min 10 s (west) to 2 min 19 s (east).

- **Coverage:** global, over millennia.
- **Access:** web pages. We compute locally with Astronomy Engine and use
  these for checks (including lunar eclipses, which the USNO API doesn't
  cover) and for credit. No key. Credit lines differ: the NASA site uses
  "Eclipse Predictions by Fred Espenak, NASA/GSFC"; EclipseWise allows free
  reproduction with "Eclipse Predictions by Fred Espenak (EclipseWise.com)".
  `eclipse.gsfc.nasa.gov/robots.txt` returns 404, so no rules; EclipseWise
  was read once, not automated.
- **Updates and size:** static; a reference, nothing stored.
- **Use cases:** validating the 2017 eclipse replay and the lunar-eclipse
  code; credit text.
- **Personas:** everyone, stargazer.
- **Needs from core:** full replay, 3D engine. **Effort** S.
- **Risks:** none.
- **Checked:** the Boise facts confirmed. Corrected: the two sites use
  different acknowledgment strings, and the Idaho central-line duration is
  a range, not just 2:10. Evidence:
  [NASA eclipse site](https://eclipse.gsfc.nasa.gov/eclipse.html),
  [robots.txt](https://eclipse.gsfc.nasa.gov/robots.txt),
  [EclipseWise 2017 Idaho](https://eclipsewise.com/solar/SEnews/TSE2017/TSE2017states/TSE2017stateID.html).

## Clouds, seeing and transparency

### NOAA HRRR on AWS (cloud layers for astronomy)

[registry.opendata.aws/noaa-hrrr-pds](https://registry.opendata.aws/noaa-hrrr-pds/).
NOAA NCEP, through the NOAA Open Data Dissemination (NODD) program.
**use**, confirmed.

`wrfsfc` fields (from NCO's inventory): TCDC (boundary-layer cloud layer;
entire atmosphere), LCDC, MCDC and HCDC (low, middle and high cloud
layers), HGT at cloud ceiling, base and top, VIS (surface), MASSDEN at 8 m
above ground (smoke), COLMD (column smoke), AOTK (aerosol optical
thickness) and DSWRF. Hourly runs at 3 km. True 3D cloud structure
(hydrometeor mixing ratios by level) is in the `wrfprs` and `wrfnat` files
⚠️.

- **Coverage:** the contiguous US, including the ring; archive since 2014.
  Model versions and field lists change over time, and smoke fields exist
  only in recent versions ⚠️.
- **Access:** `s3://noaa-hrrr-bdp-pds` (us-east-1, keyless,
  `--no-sign-request`); byte-range only the needed fields using the `.idx`
  offsets. A Zarr copy is in `s3://hrrrzarr` (us-west-1, run by the
  University of Utah). License: "NOAA data disseminated through NODD are
  open to the public and can be used as desired"; attribution requested, no
  implied endorsement. robots.txt on both buckets returns 404 (NoSuchKey),
  so no rules (re-checked). The researcher fetched one `.idx`; the verifier
  didn't repeat it.
- **Updates and size:** hourly; about 0.3–1 MB per field per hour for the
  whole country before clipping, KB after.
- **Use cases:** tonight's cloud cover for stargazing (low, mid, high), and
  whether there's glare at all (overcast kills it); cloud deck heights for
  3D volumetric clouds (better from the `wrfprs`/`wrfnat` levels); smoke
  and aerosol (COLMD, AOTK) dimming and reddening the sun and stars.
- **Personas:** stargazer, commuter, weather watcher, fire watcher.
- **Needs from core:** readings contract, time and replay clock, 3D engine.
  **Effort** M.
- **Risks:** GRIB2 decoding needs eccodes, cfgrib or wgrib2, which breaks
  the standard-library rule (an owner decision shared with the weather
  theme). Replays before HRRR v4 lack smoke fields ⚠️.
- **Checked:** buckets, regions, keyless access, archive start, license and
  robots.txt confirmed. Every listed field is in NCO's official `wrfsfc`
  inventory, which also has AOTK (added). Evidence:
  [AWS registry](https://registry.opendata.aws/noaa-hrrr-pds/),
  [NCO wrfsfc inventory](https://www.nco.ncep.noaa.gov/pmb/products/hrrr/hrrr.t00z.wrfsfcf02.grib2.shtml),
  [bucket robots.txt](https://noaa-hrrr-bdp-pds.s3.amazonaws.com/robots.txt),
  [Zarr robots.txt](https://hrrrzarr.s3.amazonaws.com/robots.txt).

### ECCC astronomical seeing and sky transparency (RDPS)

[weather.gc.ca/astro](https://weather.gc.ca/astro/index_e.html).
Environment and Climate Change Canada, Meteorological Service of Canada.
**use**, corrected.

Cloud (hourly), seeing (3-hourly) and sky transparency (hourly), plus wind,
temperature and humidity, for North America out to 84 h. On MSC Datamart
the RDPS astronomy variables are SEEI (seeing index) and TRSP (sky
transparency index), for the atmospheric column, from 0 (worst) to 5
(excellent). RDPS is now a component of GDPS at about 10 km (0.09°) on a
rotated lat-lon grid covering Canada, the US, Mexico and the Caribbean,
with 4 runs a day. The researcher's claim that a 35 km grid was retired in
a 2025 update is unverified ⚠️.

- **Coverage:** North America, including Idaho (confirmed by the domain
  description).
- **Access:** MSC Datamart
  `https://dd.weather.gc.ca/today/model_rdps/10km/{HH}/{hhh}/`, files named
  `{YYYYMMDD}T{HH}Z_MSC_RDPS_{VAR}_{LVL}_RLatLon0.09_PT{hhh}H.grib2`. The
  usage policy reserves wget or curl for ad hoc retrieval only; systematic
  or real-time retrieval must use the AMQPS push service; no polling of
  directory listings; bulk WMS tile retrieval is prohibited; contact them
  above about 86,400 requests a day. No key. ECCC Data Servers End-use
  Licence v2.1.1 (Aug 2026): worldwide, royalty-free, commercial use
  allowed, redistribution allowed with "Data Source: Environment and
  Climate Change Canada".
- **robots.txt:** `dd.weather.gc.ca` returns 404 (no rules);
  `geo.weather.gc.ca` disallows `*GetMap*`, `*GetCoverage*` and
  `*GetFeature*`; `weather.gc.ca` disallows only `/cgi-bin/`, `/scripts/`,
  `/build/`, `/template/`, `/search/` and `/html/kiosk/`, so `/astro/` is
  allowed (re-checked).
- **Updates and size:** 4 runs a day, hourly (seeing 3-hourly) to 84 h; KB
  to MB per run after clipping.
- **Use cases:** seeing and transparency for telescope nights at Bruneau
  Dunes or from a backyard; the same model family is behind the Clear Sky
  Charts.
- **Personas:** stargazer, photographer.
- **Needs from core:** readings contract, Valley Feed. **Effort** M.
- **Risks:** daily pulls of SEEI and TRSP across 85 forecast hours and 4
  runs count as systematic retrieval, so they need an AMQP client
  (sarracenia, or a standard-library AMQP 0-9-1 subscriber). That's a
  dependency decision, as is GRIB2 decoding.
- **Checked:** the Datamart path, grid, variable names and RDPS-within-GDPS
  status now come from official ECCC docs, so the path is no longer ⚠️.
  License version and usage-policy quotes confirmed. Added the 3-hourly
  seeing cadence and that our use counts as systematic retrieval. Evidence:
  [astro page](https://weather.gc.ca/astro/index_e.html),
  [weather.gc.ca robots.txt](https://weather.gc.ca/robots.txt),
  [usage policy](https://eccc-msc.github.io/open-data/usage-policy/readme_en/),
  [licence](https://eccc-msc.github.io/open-data/licence/readme_en/),
  [RDPS](https://eccc-msc.github.io/open-data/msc-data/nwp_rdps/readme_rdps_en/),
  [RDPS on Datamart](https://eccc-msc.github.io/open-data/msc-data/nwp_rdps/readme_rdps-datamart_en/),
  [astronomy variables](https://eccc-msc.github.io/open-data/assets/csv/RDPS-Astronomy_Variables-List_en.csv),
  [GeoMet robots.txt](https://geo.weather.gc.ca/robots.txt),
  [Datamart robots.txt](https://dd.weather.gc.ca/robots.txt).

### 7Timer! ASTRO

[7timer.info/doc.php](https://www.7timer.info/doc.php). 7Timer! (Ye
Quanzhi, community). **avoid**, confirmed.

A 3-day astronomy forecast (cloud, seeing, transparency) from NOAA/NCEP
GFS, as XML or JSON.

- **Coverage:** global, at coarse GFS resolution.
- **Access:**
  `http://www.7timer.info/bin/api.pl?lon=..&lat=..&product=astro&output=json`
  (no key); developers are asked to notify the site. Data are "entirely
  free" to use or redistribute if "not using them for commercial purpose".
  robots.txt returns 404, so no rules (re-checked).
- **Updates:** 4 times a day.
- **Use cases:** not needed: HRRR and ECCC's RDPS are finer and official.
- **Personas:** stargazer. **Effort** S.
- **Risks:** docs last updated Nov 1, 2012; plain `http` in the examples;
  redundant.
- **Checked:** terms, API format, model, update rate, doc date and
  robots.txt confirmed; added the request to notify the site. Evidence:
  [docs](https://www.7timer.info/doc.php),
  [robots.txt](https://www.7timer.info/robots.txt).

### Clear Sky Chart (cleardarksky.com)

[cleardarksky.com](https://www.cleardarksky.com/). CSC Charts (founded by
the late Attilla Danko). **avoid** (link out only), confirmed.

Charts per observing site, built from the Canadian astronomy model.

- **Coverage:** North American observing sites.
- **Terms:** chart images, no key. Its admin page: sites that charge no
  admission and earn no ad revenue may display chart images if each links
  its legend page; mobile-app authors must write to the maintainers for
  permission; charts remain the copyright holder's property. robots.txt
  disallows `/cgi-bin/`, `/so/anal/`, `/txtc/`, `/getcr.php` and `/f.php`,
  allows `/index.html`, with Crawl-delay 50 (re-checked).
- **Use cases:** link out to the charts for Bruneau Dunes and similar
  sites; take the underlying data from ECCC instead.
- **Personas:** stargazer. **Effort** S.
- **Risks:** no scraping; the data source (ECCC) is open anyway.
- **Checked:** the terms are now confirmed from the official admin page
  rather than search snippets; robots.txt confirmed. Evidence:
  [robots.txt](https://www.cleardarksky.com/robots.txt),
  [admin page](https://www.cleardarksky.com/csk/admin.html).

### NWS API (api.weather.gov), sky cover

[api.weather.gov](https://api.weather.gov/). NOAA National Weather Service.
**avoid**, confirmed.

Gridpoint forecasts, including hourly `skyCover`, as keyless JSON (it asks
for a User-Agent). Public domain.

- **Coverage:** the US.
- **robots.txt:** `User-agent: *` / `Disallow: /` (re-checked Oct 7, UTC),
  so no automated use under our rules.
- **Use cases:** none; use HRRR or NBM on AWS instead. Flagged for the
  weather theme.
- **Personas:** weather watcher, stargazer. **Effort** S.
- **Risks:** the API's purpose conflicts with its robots.txt; we respect
  robots.txt.
- **Checked:** robots.txt confirmed verbatim. Evidence:
  [robots.txt](https://api.weather.gov/robots.txt).

## Sun-hours, shade and shadows

### NSRDB (National Solar Radiation Database) on AWS

[registry.opendata.aws/nrel-pds-nsrdb](https://registry.opendata.aws/nrel-pds-nsrdb/).
NREL, now listed as the National Laboratory of the Rockies (NREL). **use**,
corrected.

Satellite-derived GHI, DNI, DHI and cloud type: CONUS at 2 km × 5 min (2018
on), v3 at 4 km × 30 min (1998–2018), Full Disc at 2 km × 10 min (2018 on),
plus Meteosat, Himawari, India and historical model sets.

- **Coverage:** the contiguous US, including the valley.
- **Access:** `s3://nrel-pds-nsrdb/` (us-west-2, HDF5, keyless,
  `--no-sign-request`). HSDS domains sit under `nrel-pds-hsds`; NREL's HSDS
  service has historically needed a `developer.nrel.gov` API key ⚠️.
  Creative Commons Attribution 3.0 United States. robots.txt on the bucket
  returns 404 (NoSuchKey), so no rules (re-checked).
- **Updates and size:** annual additions; very large per year at CONUS 2 km
  × 5 min, but small per-point series through HDF5 range reads.
- **Use cases:** sun-hours after clouds: how much direct sun a garden or
  panel really gets by month (geometry from our surface model times NSRDB's
  clear-sky fraction).
- **Personas:** gardener, farmer, homeowner.
- **Needs from core:** readings contract. **Effort** M.
- **Risks:** HDF5 needs h5py (a dependency). Every `nrel.gov` name failed
  DNS from the research environment on Oct 7 (UTC); the registry's new
  organisation name points to a rename, so contacts and docs may have moved
  ⚠️. The AWS copy doesn't depend on them.
- **Checked:** license, bucket and keyless access confirmed; region and
  dataset list added; the "renaming or outage" now looks like a rename;
  the HSDS key flagged. Evidence:
  [AWS registry](https://registry.opendata.aws/nrel-pds-nsrdb/),
  [robots.txt](https://nrel-pds-nsrdb.s3.amazonaws.com/robots.txt).

### NASA POWER

[power.larc.nasa.gov](https://power.larc.nasa.gov/). NASA Langley.
**avoid**, confirmed.

Daily and climatological solar irradiance and meteorology on a coarse grid
(about 0.5°), through `/api/` endpoints. NASA open data, no key.

- **Coverage:** global.
- **robots.txt:** for `*`, `Allow: /api/pages/` but `Disallow: /api/` (plus
  `/beta/`, `/classic/` and others); GPTBot, ChatGPT-User, anthropic-ai,
  Claude-Web, CCBot and Google-Extended are disallowed entirely
  (re-checked).
- **Use cases:** none; use NSRDB on AWS for sunshine climatology.
- **Personas:** gardener, farmer. **Effort** S.
- **Risks:** robots.txt disallows the API.
- **Checked:** robots.txt confirmed verbatim. Evidence:
  [robots.txt](https://power.larc.nasa.gov/robots.txt).

### High Resolution Canopy Height Maps (WRI and Meta)

[registry.opendata.aws/dataforgood-fb-forests](https://registry.opendata.aws/dataforgood-fb-forests/).
World Resources Institute and Meta. **use**, confirmed.

Global canopy height at about 1 m (the registry says "sub-meter"), from
Maxar imagery (registry credit "Maxar © 2016"; acquisition years vary ⚠️).

- **Coverage:** global, including the valley.
- **Access:** `s3://dataforgood-fb-data/forests/v1/alsgedi_global_v6_float/`
  (us-east-1, keyless), as COG tiles. CC BY 4.0. robots.txt on the bucket
  returns 404 (NoSuchKey), so no rules (re-checked).
- **Updates and size:** static (v1; the registry says "TBD"); tens of MB for
  the box ⚠️.
- **Use cases:** tree heights for shadows and sun-hours where we haven't
  processed LiDAR yet.
- **Personas:** gardener, cyclist, homeowner.
- **Needs from core:** basemap build, 3D engine. **Effort** M.
- **Risks:** older and coarser than the 2023–24 LiDAR; machine-learning
  errors on buildings and shadows.
- **Checked:** license, path, keyless access, version and robots.txt
  confirmed; the exact global prefix added. Evidence:
  [AWS registry](https://registry.opendata.aws/dataforgood-fb-forests/),
  [robots.txt](https://dataforgood-fb-data.s3.amazonaws.com/robots.txt).

### USGS 3DEP LiDAR point clouds (a surface model with trees and buildings)

[usgs.gov/3d-elevation-program](https://www.usgs.gov/3d-elevation-program).
USGS 3D Elevation Program. **use**, corrected.

First returns give tree and building heights (a DSM); subtracting the 1 m
DEM we already have gives canopy height. Per
[ch. 9 §9.2](../09-base-map-data.md#92-elevation-terrain-and-lidar):
`ID_SouthernGaps_2_D23` (QL1, flown 2023-09 to 2024-08, LAZ 1.4, not COPC)
and `ID_SouthernID_21_2018` (QL2, streamable EPT on AWS).

- **Coverage:** Ada and Canyon (ch. 9).
- **Access:** per ch. 9, the 2023–24 LAZ tiles are on
  `rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/...`
  (found through TNM and `tnmaccess`); the 2018–20 data is EPT at
  `s3://usgs-lidar-public/ID_SouthernID_21_2018/ept.json`. No key. Public
  domain.
- **robots.txt:** `usgs-lidar-public` and `prd-tnm` on S3 return 404 (no
  rules). `tnmaccess.nationalmap.gov` returns 403 "Missing Authentication
  Token" (a 4xx, so no rules). **`rockyweb.usgs.gov` timed out from the
  research environment on Oct 7 (UTC), so its robots.txt is unread; treat
  it as disallowed until it's checked from a normal network.**
- **Updates and size:** static per project; about 162 GB of SouthernGaps
  tiles in the box (ch. 9), a few GB for chosen neighbourhoods.
- **Use cases:** exact building and tree shadows for sun-hours at a garden
  bed; horizon profiles at street level.
- **Personas:** gardener, homeowner, photographer.
- **Needs from core:** basemap build, 3D engine. **Effort** L.
- **Risks:** processing needs PDAL or numpy (a dependency); start with a few
  km². The 2023–24 host's robots.txt is unverified.
- **Checked:** the researcher put the 2023–24 LAZ on `prd-tnm`; our own
  ch. 9 places it on `rockyweb.usgs.gov`, which timed out, so its robots.txt
  status is unknown. Confidence lowered to medium; size aligned with ch. 9.
  Evidence: [prd-tnm robots.txt](https://prd-tnm.s3.amazonaws.com/robots.txt),
  [usgs-lidar-public robots.txt](https://usgs-lidar-public.s3.amazonaws.com/robots.txt),
  [tnmaccess robots.txt](https://tnmaccess.nationalmap.gov/robots.txt),
  [rockyweb robots.txt](https://rockyweb.usgs.gov/robots.txt) (timeout),
  [ch. 9 §9.2](../09-base-map-data.md#92-elevation-terrain-and-lidar).

## Drawing the sky

### Precomputed Atmospheric Scattering (Bruneton)

[github.com/ebruneton/precomputed_atmospheric_scattering](https://github.com/ebruneton/precomputed_atmospheric_scattering).
Eric Bruneton. **use**, confirmed.

A 2017 reimplementation of the EGSR 2008 "Precomputed Atmospheric
Scattering" method (a physically based sky and aerial perspective), with an
online WebGL demo.

- **Coverage:** any sun position.
- **Access:** GitHub; port the lookup tables and shaders. No key.
  BSD-3-Clause, "Copyright (c) 2017 Eric Bruneton". Source code, so
  robots.txt doesn't apply.
- **Use cases:** sky and horizon colours, twilight glow and sun colour at
  low elevation, feeding MapLibre's sky and fog colours and lighting our
  clouds.
- **Personas:** everyone, weather watcher, photographer.
- **Needs from core:** 3D engine, proposed core sky ephemeris. **Effort** M.
- **Risks:** GPU cost on a laptop (the lookup tables can be precomputed
  once, offline). A cheap analytic model (Preetham or Hosek-Wilkie style)
  is the fallback. It doesn't model clouds.
- **Checked:** BSD-3-Clause (© 2017), the 2017 reimplementation of the 2008
  paper and the demo confirmed. Evidence:
  [repository](https://github.com/ebruneton/precomputed_atmospheric_scattering),
  [license](https://github.com/ebruneton/precomputed_atmospheric_scattering/blob/master/LICENSE).

### MapLibre style spec: sky, light and hillshade

[maplibre.org/maplibre-style-spec/sky](https://maplibre.org/maplibre-style-spec/sky/).
MapLibre. **use**, confirmed.

- **sky:** `sky-color`, `horizon-color`, `fog-color`, `fog-ground-blend`,
  `horizon-fog-blend`, `sky-horizon-blend`, `atmosphere-blend` (all GL JS
  4.5.0; marked experimental). Colours only, no sun position.
- **light:** `anchor` (`viewport` by default, or `map`), `position`
  `[r, a, p]` (default `[1.15, 210, 30]`; `a` is the azimuth clockwise from
  north when anchored to the map, `p` the polar angle from the zenith),
  `color`, `intensity` (0–1). It lights extruded geometry only.
- **hillshade:** `illumination-direction`, `illumination-altitude`,
  `illumination-anchor`, `exaggeration`, shadow, highlight and accent
  colours, and a method option (standard, basic, combined, igor,
  multidirectional) ⚠️.
- No cast shadows anywhere; hillshade is slope shading without terrain
  occlusion.

Details:
- **Access:** built into MapLibre GL JS 6 (the app uses `^6.12.0`,
  [app/package.json](../../app/package.json)). No key; BSD-3-Clause;
  robots.txt doesn't apply.
- **Use cases:** drive sky colours, extrusion light (anchor `map`, `a` = sun
  azimuth, `p` = 90° − sun elevation) and hillshade direction from the real
  sun on the replay clock ([ch. 13](../13-visual-design.md): lighting that
  follows the real sun).
- **Personas:** everyone.
- **Needs from core:** 3D engine, layer system. **Effort** S.
- **Risks:** real cast shadows, including terrain shadowing at low sun, need
  our own engine or a precomputed horizon map
  ([corrections 3, 9 and 12](#design-corrections-from-verification)). Sky
  is flagged experimental.
- **Checked:** the sky properties and their 4.5.0 version confirmed (the
  researcher's doubt was about hillshade versions). Light semantics added,
  since driving it from the sun needs anchor `map` and polar = 90° −
  elevation. Whether the hillshade method is a paint or layout property is
  unclear ⚠️. Evidence: [sky](https://maplibre.org/maplibre-style-spec/sky/),
  [light](https://maplibre.org/maplibre-style-spec/light/),
  [layers](https://maplibre.org/maplibre-style-spec/layers/).

## Research methods

### Sun-glare and twilight research

[TRID record 1241470](https://trid.trb.org/View/1241470) and others.
Various journals and universities. **use** (methods only), corrected.

- **Hagita and Mori 2013** (TRB 92nd Annual Meeting, "The Effect of Sun
  Glare on Traffic Accidents in Japan", Chiba): daytime clear-weather crash
  rates rise when the viewing angle to the sun drops below 90°, notably
  pedestrian and bicycle crashes and right turns at signalized
  intersections. This is the TRID record the researcher cited; it isn't
  Mitra 2014.
- **Sun 2017** (University of Alberta thesis, Danyang Sun, "Sun Glare:
  Network Characterization and Safety Effects"): collisions projected to
  rise about 30% under glare, mostly at intersections; southbound effects
  in January, November and December.
- **Cunningham et al. 2022** (University of Washington, Current Biology; 23
  states, over 1 million deer collisions, 1994–2021): 14 times more frequent
  2 h after sunset than 2 h before, and 16% higher the week after DST ends.
- **Churchill, Tripodis and Lovell 2012** (J. Transp. Eng. 138(10)) ⚠️ and
  **Mitra 2014** (Safety Science 70) ⚠️ are unverified: ASCE returned 403,
  and no Mitra page was read.

Details:
- **Access and terms:** papers and abstracts, for methods only. Copyrighted
  papers: cite, don't copy. The Alberta thesis is for non-commercial
  purposes only. Pages were read once; nothing is collected.
- **Use cases:** defining glare windows (sun elevation under about 25° and
  azimuth within about ±25° of the heading, plus the terrain horizon) and
  the crash case-crossover design; the wildlife dusk-risk idea.
- **Personas:** traffic researcher, commuter, wildlife.
- **Needs from core:** none. **Effort** S.
- **Risks:** glare thresholds vary by study (visor geometry, eye height), so
  expose them as settings. The "45°" elevation threshold attributed to
  Hagita and Mori isn't in the abstract read.
- **Checked:** the TRID link is Hagita and Mori, not Mitra; their verified
  threshold is a viewing angle under 90°. Sun 2017 and Cunningham 2022
  confirmed from official pages. Evidence:
  [TRID 1241470](https://trid.trb.org/View/1241470),
  [Sun 2017 thesis](https://ualberta.scholaris.ca/items/5e0485da-8a46-4cf7-b2d1-c2fc53ef0f79),
  [UW news on Cunningham 2022](https://www.washington.edu/news/2022/11/02/deer-vehicle-dst/),
  [Churchill 2012](https://ascelibrary.com/doi/10.1061/%28ASCE%29TE.1943-5436.0000418)
  (403).

---

## Ideas by persona

From the research pass, none approved. Each lists the sources it would
use and what it needs from core. Sources marked "in hand" are already
loaded or kept privately ([SOURCES](../SOURCES.md)). These extend the sky
watcher and photographer list in
[ch. 16](../16-ideas-and-personas.md#sky-watcher-and-photographer-sky).

### Commuter and traffic researcher

- **"Glare now" street layer.** Each street segment's direction tints warm
  amber, with a sun icon and arrow (not colour alone), when the sun is
  0–25° up, within ±25° of that direction's heading and above the real
  terrain horizon. It follows the replay clock, so scrubbing a morning shows
  glare sweeping across east–west arterials. For an exact east–west road in
  Boise in 2026 (NOAA/Meeus, flat horizon; reproduced by the verifier),
  eastbound morning glare runs 7:23–8:47 on Mar 1, 7:59–10:03 on Mar 15
  (after DST starts), 7:44–9:38 on Oct 1 and 8:01–9:16 on Oct 15; the
  westbound evening mirrors it (17:31–19:24 on Oct 1). From mid-November to
  late January (Nov 14 to Jan 28) the sun rises too far south to hit
  east–west roads; instead southbound drivers face a sun that never climbs
  above about 23° (December noon).
  *Sources:* NOAA equations, SunCalc, USGS 3DEP DEM (in hand) for the
  horizon, ACHD centerlines and OpenStreetMap (in hand), HRRR cloud cover
  (overcast means no glare). *Needs:* time and replay clock, layer system,
  proposed core sky ephemeris, road segments.
- **Glare and crashes, a case-crossover study.** Tag every COMPASS crash
  with the sun's azimuth and elevation relative to the approach heading, and
  whether the sun was above the terrain horizon and the sky clear (HRRR,
  since 2014). Compare crash counts inside glare windows with the same clock
  time 7 days before and after at the same approach (Mitra 2014 ⚠️; Sun
  2017), and show the result as a glare-risk ranking of signalized
  approaches. *Sources:* COMPASS crash data (in hand; direction of travel
  needed ⚠️), NOAA equations, HRRR, the glare research. *Needs:* full
  replay, evidence and review, road segments.
- **Glare calendar per signal approach and per camera.** A strip with the
  day of year across and time of day down, shading the minutes when the sun
  is in that approach's or camera's view
  ([ch. 11](../11-camera-validation-layer.md) already proposes this for
  cameras). It tests the 2015 account that ACHD scrapped its adaptive
  system partly because sun glare blinded video detection. Archived camera
  frames in those windows are flagged; later, if ATSPM logs ever arrive,
  max-outs during glare minutes are compared with clear minutes.
  *Sources:* Astronomy Engine, camera calibrations and archive (in hand),
  COMPASS signals (in hand). *Needs:* proposed core sky ephemeris, readings
  contract.
- **Route glare forecast in the Valley Feed.** "Tomorrow 7:45 eastbound on
  Ustick: low sun ahead 7:58–8:20, sky clear", from saved trips, HRRR cloud
  cover and the terrain horizon. Plus a seasonal card in the 2–3 weeks
  around each equinox ("glare season on east–west arterials") and on DST
  change days, when the same clock time moves an hour against the sun.
  *Sources:* SunCalc, HRRR, USGS 3DEP DEM (in hand). *Needs:* Valley Feed,
  proposed core sky ephemeris, places and search.
- **Ephemeris test harness (quality).** A stored set of USNO (rise, set,
  twilight, eclipse) and JPL Horizons (planet az/el) answers for Boise
  across seasons, so CI checks our TypeScript and Python sun, moon and
  planet code to within 1 minute and 0.1°. A few dozen API calls, made once
  and committed, since they're facts computed by US government services.
  *Sources:* USNO API, JPL Horizons. *Needs:* nothing from core.

### Cyclist

- **Ride-light helper and a "drivers behind you face the sun" warning.** For
  a planned ride, show sunset and the end of civil twilight (when lights are
  needed) along the route, and flag segments where the sun will be low
  behind the rider, so drivers approaching from behind look into it
  (rear-end risk); for example westbound Hill Road on October evenings.
  *Sources:* SunCalc, ACHD centerlines and OpenStreetMap (in hand), USGS
  3DEP DEM (in hand). *Needs:* proposed core sky ephemeris, road segments.
- **Shade score for hot afternoons** (cyclist and hiker). The share of a
  Greenbelt or foothills route in building, tree or terrain shade at a
  chosen time and date, with the shaded stretches drawn on the map.
  *Sources:* USGS 3DEP LiDAR surface model, WRI/Meta canopy height,
  Overture buildings (in hand), Astronomy Engine. *Needs:* 3D engine,
  basemap build.

### Gardener and homeowner

- **Sun-hours at a garden bed.** Click a spot to get hours of direct sun per
  day from March to October, accounting for the house next door, trees
  (LiDAR or canopy height) and the foothills horizon, scaled by NSRDB's
  monthly clear-sky fraction. In 3D, draw the sun's path arcs over the spot
  for June 21, the equinox and December 21 with hour ticks, and animate the
  shadows on the clock. A rule of thumb shown: a December noon shadow in
  Boise is about 2.4 times the object's height (sun 23° up), a June noon
  shadow about 0.37 times (70°). *Sources:* 3DEP LiDAR surface model,
  canopy height, Overture buildings (in hand), NSRDB, Astronomy Engine.
  *Needs:* 3D engine, basemap build, time and replay clock.
- **"True sunrise" horizon profile for any address.** A 360° skyline from
  the DEM (foothills, Owyhees) with the sun's path on key dates, showing how
  many minutes after astronomical sunrise the sun actually clears the
  ridge. *Sources:* USGS 3DEP DEM (in hand), Astronomy Engine. *Needs:*
  basemap build, proposed core sky ephemeris.

### Farmer

- **Photoperiod card per field.** Day length through the year (Boise about
  15.4 h on June 21, about 8.9 h on December 21) with civil-twilight working
  hours, marking day-length thresholds that matter to valley crops, such as
  long-day onion bulbing ⚠️ (agronomy values to be confirmed with extension
  sources). *Sources:* Astronomy Engine, USDA Cropland Data Layer (farm
  theme). *Needs:* places and search.

### Hiker and camper

- **"When does the sun leave this canyon?"** Click a trailhead or campsite
  for the real terrain sunset, the end of civil twilight, moonrise and the
  moon's phase and brightness for night hiking, plus a daylight-remaining
  countdown on a planned route. *Sources:* USGS 3DEP DEM (in hand),
  Astronomy Engine, USNO (validation). *Needs:* places and search, proposed
  core sky ephemeris.
- **Dark-sky finder** (camper and stargazer). Public land (the lands plugin)
  within a chosen drive time, ranked by artificial sky brightness (Falchi,
  VIIRS), tonight's cloud and transparency (HRRR, ECCC), moon up or down,
  and road access. Bruneau Dunes observatory nights (Friday and Saturday,
  March 13 to October 17) appear as events. *Sources:* Falchi atlas, EOG
  VNL, HRRR, ECCC, Idaho dark-sky places, PAD-US (lands theme). *Needs:*
  areas, places and search, Valley Feed, lifecycles contract.

### Stargazer and photographer

- **Night-sky dome over the 3D valley** (an owner interest). Stars from HYG
  or d3-celestial with true colours, the Milky Way from NASA's Deep Star
  Map, planets and the moon with its phase, and constellation lines on
  demand. The limiting magnitude follows where the camera stands and the
  conditions: about magnitude 4 under downtown Boise's glow against about
  6.5 at Bruneau; a full moon washes the Milky Way out; HRRR cloud hides
  parts of the sky. A "Look up" button drops the camera to eye level and
  tilts it up. The research proposed showing the dome once the sun is below
  about −6°; the verifier suggests always drawing and fading each object by
  sky brightness instead ([correction 7](#design-corrections-from-verification)).
  *Sources:* HYG v4.4, d3-celestial, SVS Deep Star Maps, Astronomy Engine,
  Falchi atlas, HRRR. *Needs:* 3D engine, time and replay clock, proposed
  core sky ephemeris.
- **"Tonight" panel and feed.** Which planets are up and when, moon phase
  and set time, ISS bright passes (start and end direction, peak elevation,
  magnitude), any meteor shower peak with its moon-adjusted rate, aurora
  chance (Kp, OVATION), seeing and transparency, and the hours of true
  darkness. Each item opens the dome at the right time and direction.
  *Sources:* Astronomy Engine, NASA ISS OEM, SatNOGS, IMO calendar, NOAA
  SWPC, ECCC, HRRR. *Needs:* Valley Feed, time and replay clock, lifecycles
  contract.
- **Satellites in 3D.** ISS and bright-satellite pass arcs across the dome
  with time ticks; a zoomed-out globe view shows real orbit ribbons above
  Idaho, with each satellite lit or in Earth's shadow. Starlink trains in
  the days after a launch come later, once Space-Track or CelesTrak is
  cleared. Elements are archived daily so past nights replay correctly.
  *Sources:* NASA ISS OEM, SatNOGS, satellite.js, Space-Track, CelesTrak.
  *Needs:* tracks contract, 3D engine, time and replay clock, full replay.
- **Aurora watch.** A glow on the dome's northern horizon scaled by OVATION
  probability north of the valley, and a Valley Feed alert when Kp reaches
  6–7 and HRRR says the sky is clear. During alerts, north-facing
  road-weather camera frames (already recorded) are flagged for review.
  Replay historic storms such as May 10–11, 2024 ⚠️ from GFZ Kp.
  *Sources:* NOAA SWPC, GFZ Kp, HRRR, road-weather camera archive (in hand).
  *Needs:* readings contract, Valley Feed, full replay, 3D engine.
- **Meteor showers** (stargazers and families). The radiant on the dome with
  the expected rate for your spot (ZHR adjusted for radiant height,
  moonlight and sky brightness), and actual Global Meteor Network
  trajectories over southern Idaho replayed as 3D streaks at true heights.
  Bright CNEOS fireballs appear as events. *Sources:* IMO calendar, IAU MDC
  lists, GMN, CNEOS, Falchi atlas. *Needs:* 3D engine, time and replay
  clock, lifecycles contract.
- **Alignment finder ("Boisehenge")** (photographer). Days when the sun or
  moon rises or sets along a street axis or behind a landmark (Table Rock,
  the Capitol, Bogus Basin), accounting for terrain. Boise's sunset azimuth
  runs from about 237° (Dec 21) through 271° (equinox) to 304° (Jun 21), so
  any street bearing in that fan gets alignment dates. Shows the line of
  sight and the date list. *Sources:* Astronomy Engine, USGS 3DEP DEM (in
  hand), ACHD centerlines and OpenStreetMap (in hand). *Needs:* places and
  search, 3D engine.
- **"Everything overhead"** (sky, with the aircraft plugin). From any spot,
  at eye level looking up: aircraft from the aircraft plugin (with
  altitude), satellites, planets, the moon and stars on one dome. Click
  "what's that light?" for the nearest match by direction and brightness.
  *Sources:* Astronomy Engine, satellite.js, NASA ISS OEM, HYG, the aircraft
  plugin (adsb.lol). *Needs:* tracks contract, 3D engine, time and replay
  clock.

### Everyone

- **Replay the total solar eclipse of August 21, 2017.** The Moon's umbra
  sweeps over the ring, the 3D valley dims under the real eclipse geometry,
  and Boise sits just outside totality (magnitude 0.994, 24 km from the
  southern limit), with a "drive to totality" comparison. The same engine
  previews future solar and lunar eclipses visible from Boise. *Sources:*
  Astronomy Engine, NASA (Espenak) and EclipseWise. *Needs:* full replay, 3D
  engine, proposed core sky ephemeris.
- **Real-sun shadows on the map** ([ch. 13](../13-visual-design.md),
  "later"). Buildings cast shadows from the actual sun as the clock runs,
  and low sun casts terrain shadows into the foothill draws. It needs
  shadow mapping in our WebGL engine, so the engine would draw the
  buildings; until then, precomputed sun-hour rasters cover the analysis
  cases. *Sources:* Overture buildings (in hand), USGS 3DEP DEM (in hand),
  SunCalc. *Needs:* 3D engine, proposed core sky ephemeris.

### Land and development watcher

- **The valley's light footprint on the year slider.** VIIRS annual
  radiance 2012–2024 ⚠️ shows new subdivisions in Meridian, Kuna, Star and
  Nampa lighting up, next to COMPASS permits and plats; optionally Black
  Marble's moon- and snow-corrected yearly values for exact change.
  *Sources:* EOG VNL, NASA Black Marble, NASA GIBS, COMPASS permits (in
  hand). *Needs:* time and replay clock, layer system.

### Wildlife

- **Dusk-risk overlay.** Deer are most active at dusk, and collisions are 14
  times more frequent 2 h after sunset than 2 h before (Cunningham et al.
  2022). Shade the hours after sunset where they overlap the evening
  commute, with the jump in the week after DST ends, on roads that cross
  mule-deer winter range; moon phase is added for night wildlife viewing.
  *Sources:* Astronomy Engine, the twilight research, the wildlife theme
  (winter range, wildlife–vehicle collisions). *Needs:* time and replay
  clock, Valley Feed, layer system.
- **Lights and migration.** The night-lights layer next to the
  bird-migration forecast on peak spring and fall nights, showing where the
  valley's light dome sits on the Snake River corridor. Cross-theme: the
  migration source (BirdCast ⚠️) is for the wildlife theme to vet.
  *Sources:* EOG VNL, Falchi atlas, BirdCast (wildlife theme). *Needs:*
  layer system.

### Fire and hazard watcher

- **Smoke sky.** On smoky days the 3D sun turns orange-red and dims, the sky
  dome greys and the stars fade, all driven by HRRR's column and
  near-surface smoke, so replaying a smoke event looks the way it felt.
  Visibility (HRRR VIS) adds ground haze. *Sources:* HRRR, Bruneton
  scattering. *Needs:* 3D engine, readings contract, time and replay clock.

### Weather watcher (3D weather)

- **Real lighting for real weather.** A sky module turns sun and moon
  position into sky colours, sun colour after atmospheric extinction,
  twilight glow and moonlight, and feeds them to MapLibre's sky, light and
  hillshade and to our engine. HRRR's low, mid and high cloud cover with
  cloud base and top heights places volumetric cloud decks at the right
  altitudes, lit by that sun, with fog from visibility. (The verifier notes
  `wrfsfc` can't place multiple decks; volumetric clouds need the
  per-level files, [correction 10](#design-corrections-from-verification).)
  *Sources:* Bruneton scattering, MapLibre sky, light and hillshade, HRRR,
  SunCalc. *Needs:* 3D engine, proposed core sky ephemeris, time and replay
  clock.

---

## Design notes

The researcher's proposals, with the verifier's corrections folded in and
marked. None is decided.

1. **Core or plugin (a proposal for the owner).** By ch. 15's rule ("core
   when any subject could use it, or two plugins need it"), the sun and
   moon ephemeris and the lighting state it drives belong in core: sun and
   moon direction, twilight phase, sky colour, sun colour and moonlight for
   the current clock time. Core already owns the clock and the 3D engine,
   and the base map wants real-sun lighting ([ch. 13](../13-visual-design.md)).
   Cameras want glare windows ([ch. 11](../11-camera-validation-layer.md)),
   roads want glare, gardening wants shadows, weather wants cloud lighting.
   So: `#lib/sky/` (TypeScript) plus a Python twin in core. A `sky` plugin
   then owns the data-driven layers: satellites, aurora and Kp, light
   pollution, meteor showers, dark-sky places, the astronomy forecast
   (seeing, transparency, cloud), eclipses and the night dome's catalogs.
   The verifier agrees this meets the rule, but
   [§15.7](../15-plugins.md#157-ideas-for-later-plugins) lists "sun and moon
   paths and shadows, glare" under the sky plugin, so moving them changes
   that list and needs the owner's decision (correction 15).
2. **Computing, with no runtime third-party calls for geometry.**
   - Browser: a small NOAA/Meeus port, or SunCalc (BSD-2, about 16 KB),
     always loaded and evaluated once per animation frame or clock tick.
     Astronomy Engine (MIT, 116 KB minified) is lazy-loaded for planets,
     rise and set searches and eclipses. satellite.js (MIT) runs in a Web
     Worker for the few hundred satellites shown, sampled on simulation
     time and interpolated per frame, not at 1 Hz of wall-clock time,
     which breaks during fast replay (correction 13).
   - Server: vendor Astronomy Engine's single `astronomy.py` (MIT, standard
     library only; keep its copyright notice), which keeps the "standard
     library only" rule. SGP4 in Python needs `sgp4` or Skyfield (a
     dependency decision); otherwise pass predictions for the Valley Feed
     come from the browser, or from a small port.
   - Validation: a fixture set from USNO and Horizons (the test-harness
     idea).
   - The prototype used for this research (NOAA equations, about 80 lines
     of standard-library Python) produced the Boise numbers, and the
     verifier reproduced them independently to the minute. Eastbound glare
     (sun 0–25° up, within ±25° of a 090° heading, flat horizon), local
     clock time:

     | Date | Eastbound glare |
     |---|---|
     | Mar 1 | 7:23–8:47 |
     | Mar 15 | 7:59–10:03 |
     | Apr 1 | 7:28–9:50 |
     | Jun 15 | 6:58–8:37 |
     | Oct 1 | 7:44–9:38 |
     | Oct 15 | 8:01–9:16 |
     | Nov 1 | 7:23–7:52 |
     | Nov 14 to Jan 28 | None (corrected from "mid-November to mid-January", correction 1) |

     Westbound evening windows mirror these (17:31–19:24 on Oct 1).
   - Other Boise numbers (checked): sunset azimuth 237.4° (Dec 21), 270.8°
     (Mar 20) and 304.0° (Jun 21); day length about 15.4 h (Jun 21) and
     8.9 h (Dec 21); noon sun 23.0° (Dec) and 69.8° (Jun); noon shadow
     ratios 2.36 and 0.37; precession of about 0.37° by 2026.
   - USNO check: the Oct 6 sample gave sunrise 07:48 and sunset 19:17 MDT
     once a time-zone mistake is corrected (we sent `tz=-6` with
     `dst=true`, so the raw response read an hour late).
3. **Glare model and storage.**
   - Inputs: segment bearings per direction (roads plugin: ACHD segments
     and OSM), sun azimuth and elevation from core, a terrain horizon, and
     optionally buildings downtown.
   - Don't precompute per-minute tables: 38,727 segments × 2 directions ×
     525,600 minutes is far too many.
   - Store a horizon profile per segment: 72 azimuth bins of 5°, 1 byte
     each in 0.25° steps. The horizon doesn't depend on travel direction,
     so that's about **2.8 MB** for all segments, not 5.6 MB (correction 2).
   - Evaluate on the GPU, with the sun vector as one uniform. 72 bytes
     can't be a per-vertex attribute (WebGL allows about 16 vec4
     attributes), so put the profiles in a data texture indexed by segment,
     or store only the horizon height for a few bearings. Use our own line
     layer; a MapLibre feature-state pass over about 38.7k features is
     expensive at 1 Hz, so update it once a minute or per scrub. A MapLibre
     global-state expression could also work ⚠️ (check that it exists in
     v6) (correction 2).
   - For crash analysis, compute once per crash in SQL or Python.
   - Thresholds (elevation 25°, azimuth ±25°) are settings, since studies
     differ: Hagita and Mori's verified threshold is a viewing angle to the
     sun under 90°; the "under 45°" elevation figure is unconfirmed
     (correction 14).
4. **Terrain horizon and sun-hours.**
   - Horizon maps from the 10 m or 1 m DEM, 72 azimuths per cell. March
     rays to **at least 100 km**, not 30 km, and apply Earth curvature
     (d²/2R is about 0.5 km at 80 km) and refraction (k ≈ 0.13): the
     Owyhee crest, about 60–80 km south-west of Boise and roughly 1° high
     after curvature, is exactly where the winter sun sets. The 1 m DEM
     covers only the valley box, so the far field needs 10 m or 30 m 3DEP
     (correction 3).
   - At 100 m cells over the valley box that's about 890 × 944 cells × 72
     bytes, about 61 MB raw (checked), much less compressed: right for the
     glare layer. Build it offline once (numpy or GDAL, a dependency
     decision for `basemap/`), or on the GPU in a one-off browser tool.
   - Sun-hours for gardens need a 1 m surface model with trees: LiDAR first
     returns (QL1, 2023–24) for chosen neighbourhoods, or WRI/Meta canopy
     height as a stopgap; Overture heights for buildings.
   - Output: hours of direct sun per pixel per month at 1 m for a requested
     area, cached.
5. **Real-time shadows.**
   - MapLibre can't cast shadows; fill-extrusion only takes a light
     direction.
   - Our engine would have to draw the buildings itself: Overture
     footprints extruded into meshes per tile, a shadow map from the core
     sun vector, and terrain receiving the shadows through a ground pass.
     One directional shadow map over a city-scale view is blocky, so plan
     cascaded shadow maps. MapLibre's own terrain and fill-extrusions can't
     receive shadows from a custom layer, and a custom layer shares depth
     only in `3d` rendering mode, so shadows need our own buildings plus a
     draped receiver mesh sampled from the DEM, or our own terrain
     (correction 12).
   - Cost and quality must be measured on a laptop.
   - A structural step for the 3D engine; propose it after the UI v2 waves.
6. **Night-sky dome.** A custom layer drawn first, at infinite depth:
   - stars as point sprites (HYG to magnitude 6.5, about 9k, or to
     magnitude 9, about 120k), with size and alpha from magnitude and
     colour from B–V;
   - rotated by local sidereal time and latitude, with J2000-to-date
     precession (about 0.37° by 2026, enough to misalign satellites if
     ignored);
   - the Milky Way as an equirectangular texture (SVS Deep Star Map) in
     celestial coordinates: 8K or less with KTX2/Basis (BC7 or ASTC
     transcoding) or a tiled cubemap, since 16K RGBA is about 512 MB of GPU
     memory uncompressed (8K about 128 MB); exposure and tone mapping for
     the half-float EXR; and stars brighter than the sprite cutoff masked
     out of the texture, which already holds every star to about magnitude
     11 (correction 8);
   - planets and the moon from Astronomy Engine; constellation lines from
     d3-celestial; extinction near the horizon.

   Sky brightness sets the limiting magnitude: twilight from sun elevation;
   moonlight (Krisciunas–Schaefer style); artificial brightness at the
   camera from Falchi or VIIRS, plus natural sky brightness (about 22
   mag/arcsec² at the zenith), since Falchi is artificial only (correction
   8); and cloud from HRRR TCDC. Rather than switching the dome on below one
   sun angle, always render celestial objects and fade each by the computed
   sky brightness against its magnitude: Venus, Jupiter, the Moon and the
   ISS are visible in civil twilight, and Venus and the Moon in daylight
   (correction 7). MapLibre's `sky` paint gets per-frame colours from the
   scattering model (Bruneton, or a cheap analytic model). Budget: 2–3 draw
   calls and well under 1 ms of JavaScript per frame.
7. **Satellites as tracks.**
   - Store element sets, not positions, versioned in `raw.record` as daily
     SatNOGS pulls plus NASA's daily ISS OEM. Positions are computed on
     demand, so replay works for any archived night.
   - Plan on OMM, not TLE: 5-digit catalog numbers ran out on 2026-07-11,
     SatNOGS is TLE-only, and most new Starlinks have no TLE form. OMM comes
     from Space-Track, or from CelesTrak CSV/JSON once permitted;
     satellite.js `json2satrec` reads it. SatNOGS's historical endpoint
     could supply past elements for replay (correction 5).
   - The ISS OEM is inertial EME2000 at 4-minute spacing: rotate J2000 to
     of-date (precession, nutation), then apply Earth rotation (GMST/ERA)
     before computing look angles, and interpolate with Hermite (positions
     plus velocities) or 8–9-point Lagrange. Ignoring precession alone
     shifts the ISS about 44 km, several degrees of az/el on a low pass;
     linear interpolation over 4 minutes (about 1,850 km of travel) is
     unusable (correction 4).
   - The tracks API (`/api/sky/tracks`) can still serve sampled positions,
     so the player and "follow" work as for buses and aircraft.
   - Altitudes of 400–550 km are far beyond the valley camera's far plane:
     show satellites on the dome in the local view, and as real orbits in
     a zoomed-out globe view.
8. **Readings and lifecycles.**
   - Readings (`obs`): Kp (1-minute and 3-hourly); an OVATION slice
     (125–105°W, 35–65°N, 21 × 31 = 651 cells every 30 minutes); HRRR cloud
     layers and smoke at points or on a coarse grid; ECCC seeing and
     transparency.
   - Lifecycles (`evt`): ISS visible passes, meteor shower activity periods
     and peaks, eclipses, aurora alerts, Bruneau Dunes observatory nights,
     comet visibility windows.
   - Storage: the researcher's "under 50 MB a year excluding HRRR" holds
     only if each OVATION snapshot is one array or `bytea` row (about 650
     bytes, mostly zeros, so it compresses well) and Kp is kept 3-hourly or
     with Timescale compression. Stored as one row per value, OVATION
     (about 11.4 M values a year) plus 1-minute Kp (525,600 rows a year)
     comes to hundreds of MB to about 1 GB a year. The readings contract
     should say which (correction 6).
   - Clipped light-pollution rasters are under 1 MB a year; the Milky Way
     texture is the biggest single asset (tens of MB).
9. **Licenses and republishing.**
   - Public domain: NASA (ISS OEM, SVS, Black Marble, GIBS), NOAA (SWPC,
     HRRR), USGS, USNO.
   - CC BY: GFZ Kp, EOG VNL, GMN, Globe at Night, WRI/Meta canopy height.
   - CC BY-SA 4.0 (share-alike): HYG, SatNOGS elements. Published derived
     tables stay BY-SA.
   - CC BY-NC: Falchi, and the Gaia content in the SVS maps. Fine for a
     non-commercial project; manifests should mark republishing as
     non-commercial.
   - ECCC licence: open, with attribution.
   - Space-Track: basic SSA data may be redistributed with citation.
   - IMO: facts only.
10. **robots.txt findings that change plans.**
    - CelesTrak disallows its GP API for all agents (and blocks claudebot),
      so no automated pulls.
    - api.weather.gov disallows everything, which matters for the weather
      theme.
    - NASA POWER disallows `/api/`.
    - The ESA Gaia archive disallows everything but documentation.
    - EOG disallows `/nighttime_light` downloads.
    - astronexus.com disallows `/downloads/catalogs`; Codeberg disallows
      raw, src, media and archive paths for crawlers.
    - LAADS's robots.txt sits behind an Earthdata login.
    - darksky.org answers with a bot challenge.
    - lightpollutionmap.info disallows its geoserver.
    - rockyweb.usgs.gov (the 2023–24 LiDAR) timed out, so it's unverified
      (correction 14).

    Each becomes a by-hand download by the owner, an owner request, or an
    alternative source.
11. **Privacy and ethics.** The sky is nature, but:
    - Globe at Night points and GMN camera stations are mostly at people's
      homes, so show only aggregates (Globe at Night) or meteors (GMN).
      Globe at Night's recent files include coordinates, so aggregate at
      ingest too; GMN publishes station field-of-view KMLs, so the rule
      forbids mirroring them, not just displaying them (correction 16).
    - AMS witness reports name people, so we avoid them.
    - The "everything overhead" view follows the aircraft plugin's privacy
      rules (LADD and PIA aircraft anonymised).
    - dataservices.gfz.de blocks Claude-named agents while allowing `*`.
      The verifier's advice: any by-hand fetch uses the owner's browser,
      and any script uses our project User-Agent (correction 16).
12. **Performance.**
    - Ephemeris per frame: microseconds.
    - Satellites: SGP4 for 300 objects takes about 1 ms, so per-frame
      sampling at moderate replay speeds is affordable (correction 13).
    - Glare tint: one uniform update a minute, or per scrub.
    - The dome: the research said it draws only below about −4° (the ideas
      said −6°) or in "Look up"; see note 6 for fading by sky brightness
      instead (correction 7).

## Design corrections from verification

The verifier re-implemented the NOAA/Meeus equations in standard-library
Python for Boise (43.615, −116.202) and reproduced every glare window,
sunset azimuth, day length, noon elevation and shadow ratio above. The
corrections, numbered as the design notes refer to them:

1. **Glare season dates.** With the stated thresholds, eastbound glare
   stops on Nov 14 and returns on Jan 28. "Mid-November to late January"
   (in the ideas) is right; "none from mid-November to mid-January" (the
   design note as first written) was wrong.
2. **Horizon profile storage and the GPU path.** About 2.8 MB, not 5.6 MB,
   since the horizon doesn't depend on travel direction. 72 bytes can't be
   a per-vertex attribute: use a data texture indexed by segment, or a few
   bearings. A feature-state pass over about 38.7k features at 1 Hz is
   expensive: update once a minute or per scrub, or use our own line layer
   with a sun uniform; a MapLibre global-state expression might work ⚠️.
3. **Terrain horizon range.** 30 km misses the Owyhee crest (60–80 km
   south-west, about 1° high after curvature), where the winter sun sets.
   March to at least 100 km with curvature and refraction (k ≈ 0.13); use 10
   m or 30 m 3DEP for the far field. The 100 m horizon map (about 61 MB)
   checks out for glare; garden sun-hours still need a 1 m surface model.
4. **ISS OEM frame and interpolation.** The states are inertial EME2000 at
   4-minute spacing; satellite.js works in TEME, and Astronomy Engine's
   horizon functions want of-date coordinates. Rotate J2000 to of-date,
   then apply Earth rotation; ignoring precession alone moves the ISS about
   44 km (0.37° at 6,780 km radius). Interpolate with Hermite or 8–9-point
   Lagrange, never linearly.
5. **TLE exhaustion has already happened** (2026-07-11, per CelesTrak). Plan
   on OMM (Space-Track, or CelesTrak CSV/JSON once permitted). SatNOGS's
   schema declares token auth on its TLE endpoints, so a SatNOGS token may
   become an owner action; its historical endpoint could supply past
   elements.
6. **Storage estimates need a format.** The OVATION slice is about 11.4 M
   values a year and 1-minute Kp 525,600 rows a year. One row per value is
   hundreds of MB to about 1 GB a year in Postgres; "under 50 MB" holds
   only with one array or `bytea` row per OVATION snapshot and 3-hourly or
   compressed Kp. Specify it in the readings contract.
7. **Dome threshold.** The ideas said −6°, design note 12 said −4°. Better
   to always render celestial objects and fade each by sky brightness
   against its magnitude.
8. **Milky Way texture.** 16K × 8K RGBA is about 512 MB of GPU memory
   uncompressed (8K × 4K about 128 MB), too much for a laptop. Use 8K or
   less with KTX2/Basis or a tiled cubemap; apply exposure and tone mapping
   to the half-float EXR; mask bright stars from the texture so HYG sprites
   don't double-count them. Add natural sky brightness (about 22
   mag/arcsec² at the zenith) to Falchi's artificial-only values before
   computing a limiting magnitude.
9. **MapLibre lighting specifics.** Light position is `[r, azimuth, polar]`
   with polar measured from the zenith: anchor `map`, `a` = sun azimuth,
   `p` = 90° − sun elevation, clamped to `p` ≤ 90° at night. It lights only
   fill-extrusions. Hillshade is slope and aspect shading with no
   occlusion, so low-sun terrain shadows into foothill draws need the
   horizon map (correction 3) or our engine. The sky spec has no sun and is
   experimental.
10. **HRRR for 3D clouds.** In `wrfsfc`, LCDC, MCDC and HCDC are fractions
    for fixed pressure bands, and cloud base and top are single
    lowest-base and highest-top values, which can't place multiple decks.
    Volumetric clouds need the `wrfprs` or `wrfnat` per-level hydrometeor
    mixing ratios and humidity ⚠️ (bigger downloads, same GRIB2
    dependency). Add AOTK (in `wrfsfc`) for smoke dimming. Field lists
    change across HRRR versions since 2014, and smoke exists only in recent
    ones ⚠️, so a smoke replay or a cloud covariate back to 2014 in the
    case-crossover study must handle the gaps.
11. **ECCC retrieval.** Pulling SEEI and TRSP every run is systematic
    retrieval, which ECCC's policy routes to AMQPS; curl is for ad hoc use,
    and GeoMet `GetMap`/`GetCoverage` are disallowed by robots.txt. An AMQP
    client is a dependency decision alongside the GRIB2 decoder.
12. **Real-time shadows.** Use cascaded shadow maps. MapLibre's terrain and
    fill-extrusions can't receive shadows from a custom layer, which shares
    depth only in `3d` mode, so we'd need our own buildings plus a draped
    receiver mesh from the DEM, or our own terrain. A structural engine
    step.
13. **Satellite worker cadence.** 1 Hz of wall-clock time is wrong in fast
    replay (60×, 600×): sample on simulation time and interpolate per frame.
    SGP4 for 300 objects is about 1 ms, so that's affordable.
14. **Small factual fixes.**
    - USNO has no lunar-eclipse endpoint; check lunar eclipses against
      NASA/Espenak.
    - Astronomy Engine can propagate comets from Horizons state vectors
      with its small-body simulator.
    - NOAA's 0.833° is refraction plus the solar semidiameter.
    - Hagita and Mori's verified threshold is a viewing angle under 90°;
      the "45°" is unconfirmed.
    - The `trid.trb.org/View/1241470` citation is Hagita and Mori 2013, not
      Mitra.
    - EclipseWise's acknowledgment string differs from NASA's.
    - Bruneau Dunes' June 2024 designation is now supported by the Idaho
      Business Review, read directly; the park page never said "not
      formally certified".
    - rockyweb.usgs.gov (the 2023–24 LiDAR) timed out, so its robots.txt is
      unverified.
    - NREL domains don't resolve and the AWS registry now says "National
      Laboratory of the Rockies": a cross-theme flag for the gardening and
      solar sources.
15. **Core or plugin.** The proposal meets ch. 15's rule (cameras, roads,
    gardening, weather and the base map all need it), but §15.7 lists sun
    and moon paths, shadows and glare under the sky plugin, so moving them
    needs the owner's decision. Vendoring `astronomy.py` (MIT) is
    license-compatible if its copyright notice is kept.
16. **Privacy additions.** Forbid mirroring GMN's station field-of-view
    KMLs, not just displaying them; aggregate Globe at Night at ingest.
    dataservices.gfz.de blocks Claude-named agents while allowing `*`: a
    by-hand fetch should use the owner's browser, and a script our project
    User-Agent.

## Open questions

For the owner, one at a time:

1. **Core or plugin:** should the sun and moon ephemeris and lighting state
   (sun and moon direction, twilight, sky colour, moonlight) be core,
   beside the clock and the 3D engine, with a separate `sky` plugin for
   satellites, aurora, light pollution, meteors, dark-sky places and
   astronomy forecasts? That changes the §15.7 list.
2. **Python dependencies:** OK to vendor Astronomy Engine's single-file
   `astronomy.py` (MIT, standard library only) into core? Add `sgp4` or
   Skyfield for server-side satellite passes, numpy or GDAL for horizon and
   sun-hours builds, h5py for Black Marble and NSRDB, and a GRIB2 decoder
   for HRRR and ECCC (shared with the weather theme)? An AMQP client for
   ECCC's push service?
3. **CelesTrak:** its robots.txt disallows `/NORAD/elements/gp*.php` and
   `sup-gp.php` for all agents, though its usage policy describes machine
   clients. Should the owner (a) ask CelesTrak for a written OK for one
   daily download of 2–3 groups (CSV or JSON, since new objects have no
   TLE) with our User-Agent, (b) download by hand when wanted, or (c) skip
   it and rely on SatNOGS plus NASA's ISS ephemeris, adding Space-Track
   later?
4. **Space-Track:** create an individual account (the owner's) for Starlink
   and historical elements? Redistribution of basic SSA data is
   blanket-approved with citation; credentials would live only in the
   server's `.env`. And if SatNOGS starts enforcing its declared token
   auth, a free SatNOGS account too?
5. **Light-pollution data needs owner actions:** EOG registration for VIIRS
   VNL (and a hand download, since robots.txt disallows `/nighttime_light`);
   the Falchi atlas from GFZ (CC BY-NC; the request form, or the new direct
   link if it works); optionally an Earthdata Login for Black Marble. Which,
   if any?
6. **Glare definition:** adopt sun elevation 0–25° and azimuth within ±25°
   of heading, plus the terrain horizon, as the default glare window, with
   a stricter tier (for example elevation ≤ 15°, ±15°)? Do COMPASS's crash
   records carry each vehicle's direction of travel, which the
   case-crossover study needs?
7. **Shadows:** accept that real-time building shadows mean drawing
   Overture buildings in our own WebGL engine rather than MapLibre's
   fill-extrusion, after UI v2? Or start with precomputed sun-hour rasters
   for chosen areas only?
8. **LiDAR surface model:** which areas to process first from the 2023–24
   point clouds (a garden or neighbourhood the owner picks, downtown,
   Greenbelt corridors), given about 162 GB for the whole box? The 2023–24
   host's robots.txt still needs reading from a normal network first.
9. **Night dome scope:** naked-eye magnitude 6.5 (about 9k stars, tiny) or
   binocular magnitude 9 (about 120k, HYG, CC BY-SA)? Should the night look
   with stars become part of the Normal lens after dark, per
   [ch. 13](../13-visual-design.md)?
10. **Satellites in 3D:** dome-only in the valley view, or also a zoomed-out
    globe mode with real orbits?
11. **Bruneau Dunes' certification:** the Idaho Business Review (June 2024)
    and Visit Idaho call it an International Dark Sky Park, and the park
    page doesn't contradict it; darksky.org blocks automated reads. Can the
    owner confirm on darksky.org in a browser before we label it official?
12. **Cross-theme flags:** api.weather.gov and NASA POWER disallow automated
    access in robots.txt, which matters for the weather and gardening
    research; HRRR and NBM on AWS are the open alternatives. NREL's domains
    don't resolve (an apparent rename to the National Laboratory of the
    Rockies), which matters for gardening and solar sources. The
    bird-migration light overlay depends on the wildlife theme's vetting of
    BirdCast.
13. **AI-agent blocks** (added when writing this page): GFZ, GMN, NASA POWER,
    CelesTrak and astronexus.com block Claude-named or other AI agents by
    name, beyond their rules for `*`. The verifier's advice is the owner's browser for by-hand
    fetches and our project User-Agent for scripts. Should research
    sessions also stay off those sites, treating the named blocks as
    meant for them?
