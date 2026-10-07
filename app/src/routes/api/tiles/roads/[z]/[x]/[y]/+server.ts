import { error } from '@sveltejs/kit';
import { db } from '#lib/server/db.js';
import { cutRoadTile, parseTile, roadTileServer } from '#lib/server/road-tiles.js';
import { dataMeta } from '#lib/server/versions.js';

/**
 * Road segments as Mapbox vector tiles (layer "roads"), cut by PostGIS once
 * per roads version, gzipped once and kept in an LRU (#lib/server/road-tiles).
 * Immutable for the current `?v=` (from /api/meta), else `max-age=60`.
 */
const tiles = roadTileServer({
	version: async () => (await dataMeta()).versions.roads,
	cut: (t) => cutRoadTile(db(), t)
});

export async function GET({ params, url, request }) {
	const t = parseTile(params);
	if (!t) error(404, 'No such tile');
	return tiles.respond(t, url.searchParams.get('v'), request.headers.get('accept-encoding'), request.headers.get('if-none-match'));
}
