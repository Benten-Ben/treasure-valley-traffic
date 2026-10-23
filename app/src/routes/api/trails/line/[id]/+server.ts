import { error } from '@sveltejs/kit';
import { db } from '#lib/server/db.js';
import { jsonWithEtag } from '#lib/server/json-etag.js';
import { lineCard } from '#lib/server/trails/card.js';
import type { Sql } from '#lib/server/trails/status.js';

/**
 * One agency line's trail card (#lib/server/trails/card.ts): `GET /api/trails/line/<line id>` (the id
 * /api/trails/status gives, and the Trails layer's agency tiles carry as the feature id) → the City's
 * line (a Ridge to Rivers trail, a Greenbelt closure or detour) with its state, who set it, and how much
 * of it draws itself. 404 for an unknown id and before the plugin's migration. `no-cache` with an ETag.
 */
export async function GET({ params, request }) {
	const id = /^\d{1,15}$/.test(params.id ?? '') ? Number(params.id) : NaN;
	if (!Number.isSafeInteger(id)) error(400, 'Bad line id');
	const card = await lineCard(db() as unknown as Sql, id);
	if (!card) error(404, 'No such trail');
	return jsonWithEtag(card, request.headers.get('if-none-match'));
}
