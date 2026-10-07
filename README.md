# Treasure Valley Traffic: signal timing research

Research on how traffic signals are run in the Treasure Valley of Idaho
(Ada and Canyon counties), what it would take to improve them, and what
emerging AI approaches, especially Google's, have actually shown.

*Research current as of October 2026. Every factual claim is footnoted to a
source. Items marked ⚠️ rest on secondary or search-excerpt sources and
should be verified before you cite them publicly.*

## Contents

| # | Chapter | Question it answers |
|---|---|---|
| 1 | [How traffic signal systems work](docs/01-how-signal-systems-work.md) | What are controllers, phases, cycles, offsets, detection, coordination, adaptive control? What can timing fix and what can't it? |
| 2 | [The Treasure Valley signal system](docs/02-treasure-valley-signal-system.md) | Who owns and runs the lights here, with what technology, how they're timed, what's been tried, what's unfunded |
| 3 | [Regional traffic context and data](docs/03-traffic-context-and-data.md) | How bad is congestion and where; what data a team can get, free or otherwise |
| 4 | [Improvement playbook](docs/04-improvement-playbook.md) | How a team would systematically improve timing: process, evidence, staffing arithmetic, ATSPM, probe data, engaging the agency, funding, a 90-day plan |
| 5 | [AI and emerging technology](docs/05-ai-and-emerging-tech.md) | How Google tested Project Green Light and its other mobility AI; other AI signal systems; what's real vs. hype; what fits here |
| 6 | [Automation and AI agents vs. the staffing gap](docs/06-automation-and-ai-agents.md) | Where retiming labor goes, what automation has already eliminated, what AI agents could add, and their limits |
| 7 | [Do-it-yourself data collection](docs/07-diy-data-collection.md) | What an independent team can legally collect now (and why harvesting Google isn't allowed), partner paths, and a 4-week corridor data sprint |
| 8 | [Data inventory](docs/08-data-inventory.md) | Every source found: what the map servers are, what's open, what's reachable but off-limits, what's blocked from our sandbox, what needs a records request, and 511 API signup |

### Platform (in progress)

We're building our own self-hosted map of the valley with live and
historical data layers.

| # | Chapter | What it covers |
|---|---|---|
| 9 | [Base-map data](docs/09-base-map-data.md) | Open terrain and LiDAR, streets and lanes, buildings with heights, imagery, parcels, and the license for each |
| 10 | [Platform architecture](docs/10-architecture.md) | Proposed stack (SvelteKit, MapLibre + deck.gl, PostGIS/TimescaleDB, Python ingestion) and the home-server plan |
| 11 | [Cameras as a validation layer](docs/11-camera-validation-layer.md) | Camera sources, the 511 image route, API limits, image freshness, the collect-everything processing pipeline, storage and video archiving (measured) |
| 12 | [Database schema v1 (draft)](docs/12-database-schema.md) | PostGIS + TimescaleDB layout: sources and fetches, raw record versions, our own intersection and camera IDs, time series, event lifecycles; decisions for review |
| 13 | [Visual design](docs/13-visual-design.md) | The app as a friendly, game-inspired command center: lenses, the Valley Feed, time replay, camera wall, type and color |
| 14 | [UI v2: one map, every layer](docs/14-ui-v2.md) | The rebuilt map interface: one persistent map, layers, live images, playback, 3D buses and cameras, windows |
| 15 | [Core and plugins](docs/15-plugins.md) | What every subject needs (base map, time and playback, layers, ingest framework) versus plugins per subject (roads, signals, cameras, transit, conditions, safety, demand; later aircraft, lands, trails), private plugins, and the refactor plan |

**Working files:**

- [`docs/DECISIONS.md`](docs/DECISIONS.md): decisions made with the owner,
  plus pending questions.
- [`docs/SOURCES.md`](docs/SOURCES.md): every data source we've considered, what's in use, and what's left.
- [`HANDOFF.md`](HANDOFF.md): how the cloud and local Claude sessions work
  together.
- [`CLAUDE.md`](CLAUDE.md): rules for any Claude session in this repo.

**Platform code (foundation, being built step by step):**

- [`app/`](app/README.md): SvelteKit + MapLibre map of the valley, on
  self-hosted tiles only. Two lenses so far: **Transit** (Valley Regional
  Transit's live buses in route colors) and **Cameras** (with the camera
  calibrator).
- [`basemap/`](basemap/README.md): builds our own map layers: an
  OpenStreetMap extract, fonts and icons, 3DEP terrain, Overture buildings
  and NAIP aerial imagery.
- [`deploy/`](deploy/README.md): Docker Compose for the server VM
  (TimescaleDB/PostGIS, ingest, the app, Caddy).
- [`db/`](db/README.md), [`ingest/`](ingest/README.md): schema migrations
  and collectors: ACHD's camera list, and VRT's schedule and live bus
  positions (recorded every 30 s since Oct 5, 2026).

**Research code:**

- [`tools/`](tools/README.md): small, tested research scripts. GPS
  drive-log analysis (including an experimental cycle-length estimator),
  public data download, and a permission-gated camera sampler.
- [`tvt/`](tvt/README.md): a **throwaway prototype** of the ingestion
  platform. It proved 12 sources; lessons are in docs/10 §10.5.

## Key findings

### How the system is run

- **One agency runs nearly all signals in Ada County.**
  - The Ada County Highway District (ACHD) is Idaho's only countywide highway
    district. It operates roughly 465–600 signals (depending on what's
    counted) for every city in the county.
  - By agreement, it also operates many or all state-highway (ITD) signals
    in the county.
  - In Canyon County, Nampa, Caldwell, ITD and several highway districts
    split responsibility.
- **New equipment.**
  - ACHD began a countywide Econolite rollout in 2024: Centracs central
    software and Cobalt controllers.
  - ACHD opened a $29.4M Traffic Operations Center in April 2025.
- **Timing practice.**
  - Signals run time-of-day plans (AM, midday, PM, off-peak). Downtown Boise
    is pre-timed; most other signals are actuated.
  - Much of the detection is video, which falls back to "max green" in fog.
  - Emergency preemption happens up to about 65,000 times a month
    countywide.
- **Adaptive signals have been tried here, and failed.**
  - Around 2014 ACHD deployed a Rhythm Engineering adaptive system at 22
    locations on Eagle, Chinden, State and Glenwood.
  - It was scrapped after glare and fog detection problems and poor
    side-street service.
  - Since then, ACHD's stated direction has been "proven technology and
    signal performance measurement."

### Why the lights probably feel badly timed (hypotheses to test)

1. **Growth outpacing retiming.**
   - The metro grows about 2% a year, and corridors like SH-44 and Chinden
     have seen traffic grow 7–8% a year.
   - FHWA recommends retiming after 5–10% demand changes, but we found no
     published ACHD retiming cycle.
   - About **$730K of ACHD retiming work** (including all 100 downtown
     signals for $150K) sits on COMPASS's FY2026 **unfunded** needs list.
2. **Detection failures found by complaint, not monitoring.**
   - ACHD and Nampa both describe complaint-driven discovery.
   - Nationally, detector repair was the single largest benefit of
     automated performance monitoring in Utah ($58M of $108M).
   - About **$6M of signal performance measure upgrades** are also on the
     unfunded list.
3. **Jurisdictional seams.**
   - ACHD's and ITD's central systems weren't integrated as of 2020.
   - The worst congested segments (Chinden, Eagle Rd at I-84, Karcher,
     Nampa-Caldwell Blvd) are mostly state highways or cross agency lines.
4. **Peak demand above capacity.**
   - On the worst corridors (Chinden westbound has a travel time index of
     3.26), timing can only shift delay between movements, not remove it.
   - Separating these locations from the timing-fixable ones is the first
     analytical task.

### How a team would start improving things

- **Proven tools, high benefit per dollar.**
  - Retiming has published benefit-cost ratios of about 40:1 or higher.
  - Utah's automated signal performance measures (ATSPM) returned about $9
    per $1.
  - In 2025, a Nampa retiming on Middleton Road measurably improved PM
    travel times (COMPASS evaluated it with INRIX probe data).
- **Resource math.**
  - ITE and FHWA benchmarks imply roughly 5–7 timing engineers and 10–17
    technicians for ACHD's size.
  - A full 3–5 year retiming cycle would cost about $250–750K a year, around
    0.1–0.3% of ACHD's roughly $257M budget.
  - The likely constraint is staff time, not money for hardware.
- **What outsiders can do.**
  - Build a corridor baseline with free and cheap data: ITD counts and
    crashes, COMPASS congestion data, probe APIs, floating-car runs, ACHD
    camera snapshots.
  - File Idaho Public Records Act requests for timing sheets and
    last-retimed dates.
  - Partner with COMPASS and Boise State, whose transportation lab has a
    fiber link to ACHD's operations center.
  - Brief ACHD staff before the elected commission.
  - Make concrete, precedented asks:
    - fund the existing unfunded items;
    - a public read-only ATSPM dashboard like Utah's and Georgia's;
    - a published retiming cycle;
    - a measured pilot.
- See the [90-day starter plan](docs/04-improvement-playbook.md#412-a-phased-starter-plan).

### AI and Google

- **Google Project Green Light is advisory, not autonomous.**
  - It infers existing timing from aggregated Google Maps data and
    recommends small changes. City engineers decide what to implement.
  - It's free, needs no hardware or system connection, and agencies can
    exit with 60 days' notice.
  - Google claims "up to 30%" fewer stops. Boston's third-party (INRIX)
    evaluation found **−13.5% delay and −20% stops** across 114
    intersections.
  - Seattle reverted one change, and Manchester declined some
    recommendations.
  - No Treasure Valley agency appears to be a partner.
- **How Google tests mobility AI.**
  - Its methods range from offline evaluation and calibrated SUMO digital
    twins (including Salt Lake City) to simulate-then-field-verify
    (Seattle stadium traffic).
  - The strongest is a randomized city-wide switchback experiment across 10
    US cities (rerouting; *Nature Cities*, 2026).
  - Green Light's own evidence is mostly before/after. A local pilot could
    hold itself to the stronger designs.
- **The research frontier isn't ready yet.**
  - Reinforcement-learning and LLM signal controllers remain almost entirely
    simulation-only; the sim-to-real gap is unsolved.
  - Commercial AI and adaptive systems mostly report vendor-run results
    without control groups.
- **Recommended order here:**
  1. Measure first (ATSPM plus probe data).
  2. Ask ACHD to join the Green Light waitlist.
  3. Run any pilot as a real experiment with comparison corridors.
  4. Use adaptive or AI control only where demand is truly unpredictable,
     with robust (non-video) detection.

### Automation and doing it ourselves

- **Automation can close much of the engineer gap for retiming.**
  - Counting cars is about 57% of a traditional retime's 43 hours per
    intersection.
  - Utah and Georgia eliminated it with automated performance measures, and
    Georgia cut field visits 70%.
  - Utah runs 1,252 signals with a small team plus consultants.
- **Technicians are the harder gap.** Physical repair doesn't automate away.
- **AI agents' best fit is the gap between dashboard and action.**
  Nationally, staff time is the #1 barrier even to using performance
  dashboards. Agents could rank problems and draft fixes for engineer
  approval. That's promising but unproven, so it's worth piloting with strict
  guardrails.
- **Harvesting Google isn't allowed.**
  - Scraping Google Maps is prohibited.
  - Google's API terms forbid storing or bulk-downloading directions results.
  - TomTom, HERE, Mapbox and Waze self-serve terms likewise bar building a
    stored travel-time dataset.
- **Agencies can get the same kind of data.** Google's Roads Management
  Insights gives public road agencies stored travel times every 10 minutes
  on their own roads.
- **What a team can do now:**
  - GPS floating-car runs;
  - direct signal-timing observation;
  - ACHD camera snapshots (with ACHD's permission);
  - ACHD's published counts table (browse it, or request a CSV export);
  - public ITD/COMPASS data;
  - records requests.

  A university-plus-agency partnership unlocks probe data.

## Open questions worth answering next

These would sharpen everything above. Most can be answered by asking ACHD
directly or by a public records request:

1. ACHD signal-operations staffing (engineers and technicians per signal).
2. When each major corridor was last retimed, and whether ACHD has a
   retiming schedule or Traffic Signal Management Plan.
3. Whether ATSPM / high-resolution logging is live on the new Econolite
   system, and on how many signals.
4. Detector outage rates.
5. The current ACHD–ITD signal operations agreement: who approves timing on
   Eagle, State and Chinden.
6. Results of ITD's 2023 Eagle Road signal timing review.
7. Whether ACHD, ITD or Boise participate in Waze for Cities or have
   considered Google Green Light.

## How this was researched

Desk research in October 2026 drew on primary sources where possible:

- Idaho Code, ACHD/ITD/COMPASS plans and data services, FHWA/NCHRP
  manuals, Google Research publications, city reports;
- local and trade press where primary sources weren't reachable.

Several key figures were checked directly against the source documents and
data services:

- ITD's AADT GIS service;
- TTI's Urban Mobility data file;
- COMPASS's FY2026 Resource Development Plan, 2020 TSMO plan and 2024
  congestion report;
- the City of Boston's Green Light results.

Some agency websites (achdidaho.org, ktvb.com, boisedev.com) blocked
automated access; claims resting only on search excerpts from those sites
are marked ⚠️.

## License

The code is released under the [MIT License](LICENSE). Map data keeps its
own terms:

- OpenStreetMap data: © OpenStreetMap contributors, ODbL. Databases derived
  from it that we publish stay ODbL.
- Overture buildings: ODbL.
- USGS 3DEP elevation and USDA NAIP imagery: public domain.

Data from ACHD, ITD and other agencies is credited where it's used.
