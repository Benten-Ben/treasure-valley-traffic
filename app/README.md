# app: the valley map

SvelteKit 3 (Svelte 5 runes, TypeScript) with MapLibre GL 6: one map of
the valley that's created once per visit and never loses its view, with
layers that combine (UI v2, [docs/14](../docs/14-ui-v2.md); the look is
[docs/13](../docs/13-visual-design.md)). 2.5D: tilt, terrain and extruded
buildings, plus our own small WebGL layer for 3D buses, stops and cameras.
Deployed with `adapter-node` behind Caddy ([deploy/](../deploy)).

```bash
npm install
npm run dev            # http://localhost:5173 (needs data/tiles/; camera and transit data need DATABASE_URL)
npm run check          # type check (svelte-check)
npm test               # unit tests (vitest, src/**/*.test.ts)
npm run build && npm run preview
npm run test:e2e       # browser specs (Playwright, Chromium with SwiftShader), tests/e2e/
npm run perf -- --budget     # the performance harness, docs/14 §14.9 (scripts/perf.mjs)
npm run bundle-budget  # initial JS and chunk sizes against their budgets
npm run seed           # seeded camera frames and a fake capture archive for specs (data/dev/<wp>/)
```

Imports use SvelteKit's `#lib/...` (see `package.json` `imports`), not
`$lib`.

## Map data

The map uses only our own self-hosted files. These are built by
[basemap/](../basemap) into `data/tiles/` (override with `TILES_DIR`) and
served at `/tiles/`:

- in development and preview, by a small file server in `vite.config.ts`
  (`src/lib/server/tiles-static.ts`) that mirrors the Caddyfile's headers,
  so local measurements match production;
- in production, by Caddy.

Data layers come from the app's own `/api/` (road tiles cut by PostGIS,
routes, buses, cameras). There are no third-party tile hosts and no keys.
Until the basemap is built, the page says so instead of showing a map; a
layer that isn't available says why on its button.

## Environment

| Variable | What it does |
|---|---|
| `DATABASE_URL` | PostgreSQL + PostGIS. Without it, the data APIs answer 503 and the layers say why. |
| `TILES_DIR` | The basemap folder for dev and preview (default `../data/tiles`). |
| `FRAMES_DIR` | Calibration reference frames (default `../data/frames`). |
| `TVT_FRAME_SOURCE` | `511` (default) or `fixture`: seeded frames under `FRAMES_DIR/_fixture`, nothing fetched. Tests and build agents use `fixture`. |
| `CAMERA_IMAGES_ENABLED` | Live camera images (docs/14 §14.6): the capture archive and the on-demand 511 fetcher. Off unless `true`; `deploy/compose.live-images.yml` turns it on. |
| `TVT_ARCHIVE` | The capture archive; the app reads only `cameras/jpeg` and `cameras/status`, read-only. |
| `TVT_E2E_REQUIRE_DATA` | `1`: a spec fails, rather than skips, when the seeded data is missing (set in the workflow). |
| `TVT_E2E_URL` | Run browser specs against a deployed server instead of a local preview (deploy runbook, step 6). |

The package harness (worktrees, database clones, ports, seeds) is in
[tests/e2e/README.md](tests/e2e/README.md); `scripts/harness-env.mjs` prints
a package's environment.

## Where things are

| Path | What |
|---|---|
| `src/routes/(map)/` | The map layout (MapHost and the chrome) and its pages; `calibrate/[id]` is Calibrate mode on the same map |
| `src/routes/v1/calibrate/[id]/` | The old calibrator, kept until the owner has saved a calibration with the new one |
| `src/routes/api/` | `meta`, `transit/{network,tracks}`, `cameras` (and `views`, `live`, `status`, `[id]`), `calibrations`, `views/[id]/{calibrations,frame,live/[sha]}`, `roadweather`, `tiles/roads`, `health` |
| `src/lib/app/` | Boot (manifest and `/api/meta` before the map exists), the app context, cleanup |
| `src/lib/components/MapHost.svelte` | Creates the one map |
| `src/lib/map/` | Style, the Valley and Clay flavors, colors, layer order, the picker, the render loop, buildings |
| `src/lib/layers/` | The layer registry and manager, and one folder per layer: `streets`, `transit`, `cameras`, `roadweather` |
| `src/lib/overlay/`, `src/lib/gl/` | The always-loaded 2D overlay (bus discs, plates, badges) and its WebGL helpers |
| `src/lib/scene/` | The 3D scene engine (a lazy chunk): buses, stop posts, camera poles, cones and photos |
| `src/lib/calibration/` | The pose solver, the view frustum and the drape |
| `src/lib/state/` | View, modes, windows, history, follow, clock, selection, polling, saved settings |
| `src/lib/ui/` | The chrome: top bar, toolbar, legends, inspect card, windows, phone sheet and tab bar, keys and help |
| `src/lib/contracts/` | The JSON contracts shared by server and client |
| `src/lib/server/` | Database, data versions, tiles, frames, the capture archive, the 511 fetcher and robots.txt, transit queries |
| `src/lib/perf/` | Performance marks and the `?perf` HUD |
| `scripts/` | The harness: seeds, the fake archive, database clones, the e2e server, `perf.mjs`, `bundle-budget.mjs`, `review-page.mjs` |
| `tests/e2e/` | Browser specs, one tag per package (`@wp0` … `@wp17`) |
