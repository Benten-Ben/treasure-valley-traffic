import { db } from '#lib/server/db.js';
import { jsonWithEtag } from '#lib/server/json-etag.js';
import type { Sql } from '#lib/server/water/common.js';
import { waterPoints } from '#lib/server/water/gauges.js';

/**
 * The water points the map draws (#lib/server/water/gauges.ts): `GET /api/water/points` ->
 * `{ structures, gauges, credit }`. Public-source rows only (OpenStreetMap, NHD, NWPS): never IDWR's.
 * Empty before the water plugin's migration. `no-cache` with an ETag.
 */
export async function GET({ request }) {
	return jsonWithEtag(await waterPoints(db() as unknown as Sql), request.headers.get('if-none-match'));
}
