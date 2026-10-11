import { error } from '@sveltejs/kit';
import { cutLayerTile, layerTileServer, parseLayerTile, tileLayer, tilesDb } from '#lib/server/mvt.js';
import { dataMeta } from '#lib/server/versions.js';

/**
 * Toggled layers' vector tiles (#lib/server/mvt; plan C4): one route for every
 * layer a plugin defines in `#lib/server/<plugin>/tiles.ts`. Cut by PostGIS on
 * the tile pool, gzipped once and kept per version in the shared LRU.
 * Immutable for the current `?v=` (/api/meta's `versions.layers`), else
 * `max-age=60`; an empty tile with a short cache on a timeout or before the
 * plugin's migration. Static routes (`/api/tiles/roads`, `/api/trees/...`)
 * take precedence over this one.
 */
const tiles = layerTileServer({
	version: async (id) => (await dataMeta()).versions.layers?.[id] ?? null,
	cut: (def, t, signal) => cutLayerTile(tilesDb(), def, t, signal)
});

export async function GET({ params, url, request }) {
	const def = tileLayer(params.plugin, params.layer);
	if (!def) error(404, 'No such layer');
	const t = parseLayerTile(params, def);
	if (!t) error(404, 'No such tile');
	return tiles.respond(def, t, url.searchParams.get('v'), request.headers.get('accept-encoding'), request.headers.get('if-none-match'));
}
