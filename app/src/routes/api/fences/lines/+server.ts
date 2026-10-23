import { layerVersion } from '#lib/contracts/layer-tiles.js';
import { db } from '#lib/server/db.js';
import { fenceLinesServer, type Sql } from '#lib/server/fences/lines.js';
import { dataMeta } from '#lib/server/versions.js';

/**
 * GET /api/fences/lines?v=<version> (plan P10): every mapped fence, wall, retaining wall, guard rail and jersey
 * barrier of the valley as one GeoJSON (OpenStreetMap, ODbL), for the Fences layer's 2D line and its 3D batch.
 * Gzipped, with an ETag; immutable when `v` names the current `fences.lines` version (the one /api/meta reports as
 * `versions.layers['fences.lines']`), `no-cache` otherwise. An empty collection before the plugin's migration.
 */
const server = fenceLinesServer({
	sql: () => db() as unknown as Sql,
	version: async () => layerVersion(await dataMeta(), 'fences', 'lines')
});

export async function GET({ url, request }) {
	return server.respond(url.searchParams.get('v'), request.headers.get('accept-encoding'), request.headers.get('if-none-match'));
}
