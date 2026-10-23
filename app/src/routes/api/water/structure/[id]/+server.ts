import { error } from '@sveltejs/kit';
import { structureDetail } from '#lib/server/water/network.js';
import { isBadRequest, type Sql } from '#lib/server/water/common.js';
import { db } from '#lib/server/db.js';
import { jsonWithEtag } from '#lib/server/json-etag.js';

/**
 * One dam, weir, gate, waterfall or spring (#lib/server/water/network.ts): `GET /api/water/structure/<id>`.
 * `no-cache` with an ETag. Empty (404) before the water plugin's migration, or for an id the build no longer has.
 */
export async function GET({ params, request }) {
	try {
		const found = await structureDetail(db() as unknown as Sql, params.id ?? '');
		if (!found) error(404, 'No such structure');
		return jsonWithEtag(found, request.headers.get('if-none-match'));
	} catch (e) {
		if (isBadRequest(e)) error(400, e.message);
		throw e;
	}
}
