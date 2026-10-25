import { shrubAreas } from '#lib/layers/trees/shrubs.server.js';
import type { Sql } from '#lib/layers/trees/trees.server.js';
import { db } from '#lib/server/db.js';
import { jsonWithEtag } from '#lib/server/json-etag.js';

/**
 * Where shrubs are built (docs/19 §19.8): `GET /api/trees/shrubs/areas` →
 * `{ areas: [{ area, bounds: [w, s, e, n], shrubs, built_at }] }`. Empty before the shrub tables exist. `no-cache`
 * with an ETag.
 */
export async function GET({ request }) {
	return jsonWithEtag(await shrubAreas(db() as unknown as Sql), request.headers.get('if-none-match'));
}
