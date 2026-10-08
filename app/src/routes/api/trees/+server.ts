import { error, json } from '@sveltejs/kit';
import { BadRequest, parseBbox, parseLimit, treesInBox, type Sql } from '#lib/layers/trees/trees.server.js';
import { db } from '#lib/server/db.js';

/**
 * The trees in a box (docs/19 §19.6): `GET /api/trees?bbox=w,s,e,n&limit=N`
 * → `{ trees: [{ id, kind, type, lng, lat, h, r, a, n }], truncated }`,
 * tallest first, `limit` 4,000 by default and 8,000 at most. Trees change
 * only when an area is rebuilt (monthly), so a view's answer is cached for
 * five minutes.
 */
export async function GET({ url, setHeaders }) {
	let box, limit;
	try {
		box = parseBbox(url.searchParams.get('bbox'));
		limit = parseLimit(url.searchParams.get('limit'));
	} catch (e) {
		if (e instanceof BadRequest) error(400, e.message);
		throw e;
	}
	setHeaders({ 'cache-control': 'public, max-age=300' });
	return json(await treesInBox(db() as unknown as Sql, box, limit));
}
