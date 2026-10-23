import { error } from '@sveltejs/kit';
import { reachDetail } from '#lib/server/water/network.js';
import { isBadRequest, type Sql } from '#lib/server/water/common.js';
import { db } from '#lib/server/db.js';
import { jsonWithEtag } from '#lib/server/json-etag.js';

/**
 * One reach, and its canal when it belongs to a named one (#lib/server/water/network.ts): `GET /api/water/reach/<id>`.
 * The canal's irrigation service areas are IDWR's (internal: this tailnet map only).
 * `no-cache` with an ETag. Empty (404) before the water plugin's migration, or for an id the build no longer has.
 */
export async function GET({ params, request }) {
	try {
		const found = await reachDetail(db() as unknown as Sql, params.id ?? '');
		if (!found) error(404, 'No such reach');
		return jsonWithEtag(found, request.headers.get('if-none-match'));
	} catch (e) {
		if (isBadRequest(e)) error(400, e.message);
		throw e;
	}
}
