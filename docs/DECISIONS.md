# Decision log

Decisions made with the project owner, and open questions. Newest first.
The owner wants to be closely involved: structural choices (stack, schema,
deployment, what counts as "core") are decided together, not by the
assistant alone.

## Decided

| Date | Decision | Notes |
|---|---|---|
| 2026-10-05 | **Transit is the next focus: record VRT's live buses and show them on the map.** A transit worker records all three GTFS-realtime feeds every 30 s: a raw archive of each feed as published, plus bus positions in a time-series table. VRT's static GTFS (routes, stops, shapes) loads daily. The map gets a Transit lens. This lifts "foundation plus cameras only" for transit. Schema decisions 3 (UTM 11N for meters), 6 (high-volume raw feeds archived as files, not in the database) and 7 (keep everything, compress after 7 days) are approved. | Owner: "this all sounds excellent". VRT licenses its GTFS feeds CC BY 3.0 (credit Valley Regional Transit). A temporary raw recorder has run on the server since 2:00 PM MDT Oct 5; the worker takes it over, and positions get backfilled from the archive. Lens design: [ch. 13](13-visual-design.md). |
| 2026-10-05 | **`main` is the default branch.** Pilot sessions work on their own branch and fast-forward `main` once the checks pass. | Owner: "proceed working in relation to it however you see fit" |
| 2026-10-05 | **The repository goes public, under the MIT license.** Kept out of it, in private files on the server: third-party data copies (ACHD's tables, 511's camera list, the camera inventory); the tools that touch robots-disallowed hosts; unsent drafts; and every detail of the owner's network and hardware. The history was squashed to one commit, so none of those remain in it. | Owner. Rules in [CLAUDE.md](../CLAUDE.md#this-repository-is-public). The full earlier history is kept as a bundle in the private files. |
| 2026-10-05 | **Remote access over Tailscale.** Cloud pilot sessions join the owner's tailnet with standard trusted access, like the owner's own machines. The server VM is on the tailnet with Tailscale SSH, and the pilot deploys over it. Each machine is approved by the owner opening a login link; no auth keys, and no router port forwarding. | Owner. The cloud container is destroyed when the chat ends; the owner then removes its machine from the tailnet. Names and addresses are in the private server notes. |
| 2026-10-05 | **The local helper leads the host side**: VM or container, sizing, storage, network and backups are decided by the owner and the helper. The pilot only recommends, then deploys once the VM is on the tailnet. | Owner |
| 2026-10-05 | **First real feature: the camera calibrator.** The map shows cameras as calibrated or uncalibrated nodes. Click one, pair points between its frame and the aerial imagery on terrain, and save the calibration to the database permanently. | Owner. Design in [ch. 13](13-visual-design.md#133-a-walk-through-the-screen) (calibration walk-through) and [ch. 11](11-camera-validation-layer.md). Until the 511 key arrives, camera images come from 511's allowed image route, with view IDs from the Oct 5 one-off list check. Fetched only when someone opens a camera. |
| 2026-10-05 | **Cameras go through the database, and schema decisions 1–2 are approved:** typed tables plus raw record versions, and our own IDs with `source_link` records | Owner ("database sounds good"). Decisions 3–7 in [ch. 12 §12.9](12-database-schema.md#129-decisions-for-the-owner) are still open. |
| 2026-10-05 | **Map scope for now: the foundation plus cameras only.** Terrain, aerial imagery, streets and buildings, and the cameras at their proper locations. No other collected data (counts, crashes, transit, work zones, …) goes on the map yet. | Owner. The data is kept and database work continues; showing it waits for the owner. |
| 2026-10-05 | **One full pull of ACHD's counts and turn-movement tables, now** (about 580 requests, 2 s apart, ~30 min), with our paced one-off tool | Owner: "in line with my comfort". A one-time exception to "no whole-table downloads". Repeats need the owner's explicit OK each time. The copy is kept privately, not published ([data/](data/README.md)). The ACHD note still asks for official exports (and history). |
| 2026-10-05 | **One-off research checks are fine; automated collection from robots-disallowed paths is not.** Lookups made at the owner's request aren't robot access. The tools for them can be kept (with the private files) for reuse if they need an explicit flag, are run by hand and pace themselves. Schedules, ingestors and collectors never touch disallowed paths. | Owner. So the facts from the Oct 4 ACHD header check and the Oct 5 511 list check stay, with their provenance noted ([ch. 11 §11.1](11-camera-validation-layer.md#111-the-source)). |
| 2026-10-05 | **Cameras: collect everything.** Capture every camera at its real refresh rate (about 60 s), measure queues automatically on every frame, and keep the archive and all measurements. Heavy pre-processing is welcome. Scale up in steps (2–5 → 30–40 → all). | Owner direction. Pipeline in [ch. 11 §11.7](11-camera-validation-layer.md#117-processing-pipeline-collect-everything-measure-every-frame). Camera data stays "validation" until checked against manual counts. |
| 2026-10-05 | **Daytime retest** of the compression benchmark before fixing archive settings | Owner agreed |
| 2026-10-05 | **Visual direction: a friendly, game-inspired command center** (Cities: Skylines info views, Civilization lenses, SimCity query tool, with a traffic-center camera wall) | Owner delegated the choice to the pilot. Design in [ch. 13](13-visual-design.md). |
| 2026-10-05 | **Database: PostgreSQL + PostGIS + TimescaleDB**, with DuckDB alongside for analysis | Owner approved |
| 2026-10-05 | **Open-only, no-key stack:** self-hosted basemap and terrain; no Google 3D, Esri or MapTiler | Owner approved |
| 2026-10-05 | **Foundation build order:** skeleton → map on screen → DB schema → first ingestor → server deploy. Owner said to proceed as the pilot sees fit. | |
| 2026-10-05 | **Version 1 is 2.5D, no point clouds.** MapLibre + deck.gl, terrain from the 3DEP 1 m elevation model, extruded buildings. | No LiDAR point clouds or Cesium in v1; revisit later |
| 2026-10-05 | **Two-session workflow:** the cloud session stays primary pilot; a local helper session on the owner's laptop handles anything needing local or home-network access; the owner relays between them | See [HANDOFF.md](../HANDOFF.md) |
| 2026-10-05 | **Deploy on the owner's home server**, not the laptop: one VM running Docker Compose | Created with the owner and the helper, running since Oct 5: 8 vCPU, 16 GB RAM, 100 GB disk. Host specifics are in the private server notes. |
| 2026-10-05 | **Front end: SvelteKit**, not React | Owner preference |
| 2026-10-05 | **Camera images via 511 Idaho's republished copies are a legitimate path** | 511 serves its own copies (ITD-stamped, on its own infrastructure), lists ACHD as a provider, and its robots.txt allows the image path. Use the official 511 API for the camera list. |
| 2026-10-05 | **Still send ACHD a courtesy note** and ask for counts and turn-movement CSVs | The draft is kept privately until it's sent |
| 2026-10-05 | **Cameras are a validation layer, not a core source.** Build health monitoring (C), image samples (D) and queue measurement (E). | Design in [chapter 11](11-camera-validation-layer.md) |
| 2026-10-05 | **Build camera tooling assuming full access**, so we're ready to go | Capture stays off until the 511 key arrives |
| 2026-10-05 | **The `tvt/` package is a throwaway prototype**, not the foundation | Lessons kept in [chapter 10 §10.5](10-architecture.md#105-what-the-prototype-taught-us-kept-as-lessons-not-code) |
| 2026-10-05 | **Go through sources one at a time with the owner** before committing to how each is used | Started with ACHD cameras |
| 2026-10-04 | **Respect robots.txt and terms.** No scraping of disallowed hosts, and no storing Google, TomTom, HERE, Mapbox or Waze data. | [chapter 8](08-data-inventory.md) |
| 2026-10-04 | **Focus on the road network, not people** | No tracking or identification |

## Pending (owner to decide)

| Question | Recommendation | Where discussed |
|---|---|---|
| Backups for the server | Nightly `pg_dump` plus the frames folder and the private files, 14 copies kept on the VM, and a copy **off the server's disk**: (a) pulled to the owner's laptop over Tailscale (refreshes only while it's awake), or (b) a USB disk on the host (a host change). | Pilot's reply to the host inventory |
| Disk for the camera archive | 1–2.5 TB a year needs a disk of its own on the server; options are in the private server notes. Not needed until capture scales past a few cameras. | [ch. 11 §11.7](11-camera-validation-layer.md#117-processing-pipeline-collect-everything-measure-every-frame) |
| Vision model license: permissive or AGPL? | Permissive (Apache/BSD) | [ch. 11](11-camera-validation-layer.md) |
| Which 30–40 key cameras come first | Top-congested corridors plus highest-crash intersections | [ch. 11 §11.6](11-camera-validation-layer.md#116-open-questions-for-the-owner) |
| Camera archive format | AV1 (SVT-AV1, crf30) in MKV, hourly roll-up per camera: 2–7x smaller than JPEG in the night test, about 3x better than H.264/H.265. Confirm with a daytime retest. | [ch. 11 §11.5](11-camera-validation-layer.md#measured-results-night-test-oct-45-2026) |
| Edits to the ACHD note before sending | — | The draft, in the private files |

## Owner actions

- [ ] Register for a 511 Idaho developer key
  (https://511.idaho.gov/my511/register → Developers page) and read the
  developer agreement
- [ ] Edit and send the ACHD note
- [x] Approve the pilot on the tailnet; host inventory; create the server
  VM (Oct 5)
- [x] Make the repository public on GitHub; `main` is the default branch (Oct 5)
- [ ] Choose where backups go
- [ ] When a cloud session ends, remove its machine from the tailnet
  (Tailscale admin console → Machines)
