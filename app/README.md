# app: the valley map

SvelteKit (Svelte 5, TypeScript) with MapLibre GL. Version 1 is 2.5D:
tilt, terrain and extruded buildings, no point clouds. Deployed with
`adapter-node` behind Caddy ([deploy/](../deploy)).

```bash
npm install
npm run dev        # http://localhost:5173
npm run check      # type check
npm run build && npm run preview
```

## Map data

The map uses only our own self-hosted files. These are built by
[basemap/](../basemap) into `data/tiles/` (override with `TILES_DIR`) and
served at `/tiles/`:

- in development and preview, by a small plugin in `vite.config.ts`;
- in production, by Caddy.

There are no third-party tile hosts and no keys. Until the basemap is built,
the page says so instead of showing a map.

| Path | What |
|---|---|
| `src/lib/map/style.ts` | Manifest contract and style builder (Protomaps layers, plus terrain and buildings when built) |
| `src/lib/components/ValleyMap.svelte` | The map component: PMTiles protocol, controls, bundled MapLibre worker |
| `src/routes/+page.svelte` | Full-screen map page (browser-only rendering) |
| `src/routes/api/health/+server.ts` | Health check for the container |

**Imports:** this project uses the new SvelteKit `#lib/...` imports (see
`package.json` `imports`) instead of `$lib`.
