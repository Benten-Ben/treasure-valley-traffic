import { db } from '#lib/server/db.js';
import { yearInfo, type Sql } from '#lib/server/farm/fields.js';
import { jsonWithEtag } from '#lib/server/json-etag.js';

/**
 * The crop year the Crop fields layer shows (landscape sprint P3-app): `GET /api/farm/year` →
 * `{ built, year, label, first_year, edition }`, "2025 (USDA's newest)". `built: false` before the farm
 * migration or a load. `no-cache` with an ETag.
 */
export async function GET({ request }) {
	return jsonWithEtag(await yearInfo(db() as unknown as Sql), request.headers.get('if-none-match'));
}
