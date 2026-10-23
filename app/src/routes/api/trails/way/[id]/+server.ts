import { error } from '@sveltejs/kit';
import { db } from '#lib/server/db.js';
import { jsonWithEtag } from '#lib/server/json-etag.js';
import { wayCard } from '#lib/server/trails/card.js';
import type { Sql } from '#lib/server/trails/status.js';

/**
 * One way's trail card (#lib/server/trails/card.ts): `GET /api/trails/way/<osm id>` → its kind, name,
 * surface (with Ridge to Rivers' default), width (tagged or estimated), whether it is informal, and the
 * agencies' lines linked to it with their states. Only for a way the Trails layer draws (404 for a
 * private way, a canal bank, an unknown id, and before the plugin's migration). `no-cache` with an ETag.
 */
export async function GET({ params, request }) {
	const id = /^\d{1,15}$/.test(params.id ?? '') ? Number(params.id) : NaN;
	if (!Number.isSafeInteger(id)) error(400, 'Bad way id');
	const card = await wayCard(db() as unknown as Sql, id);
	if (!card) error(404, 'No such trail');
	return jsonWithEtag(card, request.headers.get('if-none-match'));
}
