import { error } from '@sveltejs/kit';
import { db } from '#lib/server/db.js';
import { jsonWithEtag } from '#lib/server/json-etag.js';
import { pavingCard, type Sql } from '#lib/server/roads/paving.js';

/**
 * One paving card (landscape sprint P8-app): `GET /api/roads/paving/lot/<w|r><id>` for a parking lot,
 * `GET /api/roads/paving/way/<id>` for a way. The Lanes layer draws the card; this only answers with its
 * values and the OpenStreetMap credit. `no-cache` with an ETag, as the trees' detail.
 */
export async function GET({ params, request }) {
	const kind = params.kind;
	if (kind !== 'lot' && kind !== 'way') error(404, 'No such paving kind');
	const id = params.id ?? '';
	if (id.length > 40) error(400, 'Bad paving id');
	const card = await pavingCard(db() as unknown as Sql, kind, id);
	if (!card) error(404, 'No such paving');
	return jsonWithEtag(card, request.headers.get('if-none-match'));
}
