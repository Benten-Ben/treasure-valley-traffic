import { error } from '@sveltejs/kit';
import { gaugeDetail } from '#lib/server/water/gauges.js';
import { isBadRequest, type Sql } from '#lib/server/water/common.js';
import { db } from '#lib/server/db.js';
import { jsonWithEtag } from '#lib/server/json-etag.js';

/**
 * One NWPS gauge: what it measures, its latest reading and flood category (#lib/server/water/gauges.ts): `GET /api/water/gauge/<lid>`.
 * `no-cache` with an ETag. Empty (404) before the water plugin's migration, or for an id the build no longer has.
 */
export async function GET({ params, request }) {
	try {
		const found = await gaugeDetail(db() as unknown as Sql, params.lid ?? '');
		if (!found) error(404, 'No such gauge');
		return jsonWithEtag(found, request.headers.get('if-none-match'));
	} catch (e) {
		if (isBadRequest(e)) error(400, e.message);
		throw e;
	}
}
