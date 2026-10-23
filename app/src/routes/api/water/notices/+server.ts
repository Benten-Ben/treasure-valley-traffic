import { db } from '#lib/server/db.js';
import { jsonWithEtag } from '#lib/server/json-etag.js';
import type { Sql } from '#lib/server/water/common.js';
import { notices } from '#lib/server/water/notices.js';

/**
 * The river hazards and E. coli results (#lib/server/water/notices.ts): `GET /api/water/notices` ->
 * `{ hazards, ecoli, polled, credit, license, republish }`. The City of Boise's, in its own words and numbers;
 * internal (no licence stated), for this tailnet map. Empty lists before there are rows. `no-cache` with an ETag.
 */
export async function GET({ request }) {
	return jsonWithEtag(await notices(db() as unknown as Sql), request.headers.get('if-none-match'));
}
