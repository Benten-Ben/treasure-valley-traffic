import { treeAreas, type Sql } from '#lib/layers/trees/trees.server.js';
import { db } from '#lib/server/db.js';
import { jsonWithEtag } from '#lib/server/json-etag.js';

/**
 * Where trees are built (docs/19 §19.6): `GET /api/trees/areas` →
 * `{ areas: [{ area, bounds: [w, s, e, n], trees, built_at }] }`. Empty
 * before the trees plugin's migration. `no-cache` with an ETag.
 */
export async function GET({ request }) {
	return jsonWithEtag(await treeAreas(db() as unknown as Sql), request.headers.get('if-none-match'));
}
