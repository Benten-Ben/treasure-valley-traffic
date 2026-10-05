import adapter from '@sveltejs/adapter-node';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig, type Plugin } from 'vite';
import { resolve } from 'node:path';
import sirv from 'sirv';

// Built basemap files (PMTiles, fonts, sprites, manifest.json) live outside
// the app so multi-GB tiles never end up in the build. In production Caddy
// serves them at /tiles/ (see deploy/Caddyfile); in dev and preview this
// plugin does the same job. sirv supports HTTP range requests, which PMTiles
// needs.
const TILES_DIR = resolve(process.env.TILES_DIR ?? '../data/tiles');

function serveTiles(): Plugin {
	const handler = () => sirv(TILES_DIR, { dev: true, etag: true });
	return {
		name: 'tvt-serve-tiles',
		configureServer(server) {
			server.middlewares.use('/tiles', handler());
		},
		configurePreviewServer(server) {
			server.middlewares.use('/tiles', handler());
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
	]
});
