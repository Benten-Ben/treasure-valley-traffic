import { error } from '@sveltejs/kit';
import { db } from '#lib/server/db.js';
import { fieldCard, type Sql } from '#lib/server/farm/fields.js';
import { jsonWithEtag } from '#lib/server/json-etag.js';

/**
 * One crop field's card (landscape sprint P3-app): `GET /api/farm/fields/<id>` → the field's crop in each
 * year, how sure USDA's map is, its July state, growth and plat flags as stored, and the credits. `id` is
 * `farm.field.id`, the feature id the tiles carry. 404 before the farm migration or a load. `no-cache` with
 * an ETag. (`/api/farm/tiles/...` is the generic tile route's: this folder has no `tiles/` of its own.)
 */
export async function GET({ params, request }) {
	const id = /^\d{1,9}$/.test(params.id ?? '') ? Number(params.id) : NaN;
	if (!Number.isInteger(id) || id < 1) error(400, 'Bad field id');
	const card = await fieldCard(db() as unknown as Sql, id);
	if (!card) error(404, 'No such field');
	return jsonWithEtag(card, request.headers.get('if-none-match'));
}
