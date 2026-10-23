import { error } from '@sveltejs/kit';
import { db } from '#lib/server/db.js';
import { jsonWithEtag } from '#lib/server/json-etag.js';
import { mapUnitCard, type Sql } from '#lib/server/soils/units.js';

/**
 * One map unit's soil card (landscape sprint P1-app): `GET /api/soils/mapunit/<mukey>` → the dominant
 * component and its share, the other components, texture, drainage, the shallowest restriction, farmland
 * class, the hydric rating, the survey area and its version, and the credit. `mukey` is NRCS's map-unit key,
 * the feature property the tiles carry. 404 before the soils migration or a load. `no-cache` with an ETag.
 */
export async function GET({ params, request }) {
	const mukey = params.mukey ?? '';
	if (!/^\d{1,9}$/.test(mukey)) error(400, 'Bad map-unit key');
	const card = await mapUnitCard(db() as unknown as Sql, mukey);
	if (!card) error(404, 'No such map unit');
	return jsonWithEtag(card, request.headers.get('if-none-match'));
}
