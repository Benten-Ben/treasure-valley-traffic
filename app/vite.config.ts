import adapter from '@sveltejs/adapter-node';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';
import type { Plugin } from 'vite';
import { resolve } from 'node:path';
import { tilesHandler } from './src/lib/server/tiles-static.js';

// Built basemap files (PMTiles, fonts, sprites, manifest.json) live outside
// the app so multi-GB tiles never end up in the build. In production Caddy
// serves them at /tiles/ (see deploy/Caddyfile); in dev and preview this
// plugin does the same job with the same headers (src/lib/server/tiles-static.ts).
const TILES_DIR = resolve(process.env.TILES_DIR ?? '../data/tiles');

function serveTiles(): Plugin {
	return {
		name: 'tvt-serve-tiles',
		configureServer(server) {
			server.middlewares.use('/tiles', tilesHandler(TILES_DIR));
		},
		configurePreviewServer(server) {
			server.middlewares.use('/tiles', tilesHandler(TILES_DIR));
		}
	};
}

export default defineConfig({
	plugins: [
		serveTiles(),
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
			},
			adapter: adapter()
		})
	],
	test: {
		// Unit tests only; the Playwright specs in tests/e2e run with `npm run test:e2e`.
		include: ['src/**/*.test.ts']
	}
});
