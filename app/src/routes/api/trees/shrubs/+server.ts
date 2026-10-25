import { error, json } from '@sveltejs/kit';
import { parseCentre, parseShrubLimit, shrubsInBox } from '#lib/layers/trees/shrubs.server.js';
import { BadRequest, parseBbox, type Sql } from '#lib/layers/trees/trees.server.js';
import { db } from '#lib/server/db.js';

/**
 * The shrubs near a point (docs/19 §19.8): `GET /api/trees/shrubs?bbox=w,s,e,n&center=lng,lat&limit=N` →
 * `{ shrubs: [{ id, look, lng, lat, h, w }], truncated }`, nearest the centre first, at most 1,500 within about
 * 300 m. Shrubs change only when an area is rebuilt, so a view's answer is cached for five minutes.
 */
export async function GET({ url, setHeaders }) {
	let box, centre, limit;
	try {
		box = parseBbox(url.searchParams.get('bbox'));
		centre = parseCentre(url.searchParams.get('center'));
		limit = parseShrubLimit(url.searchParams.get('limit'));
	} catch (e) {
		if (e instanceof BadRequest) error(400, e.message);
		throw e;
	}
	setHeaders({ 'cache-control': 'public, max-age=300' });
	return json(await shrubsInBox(db() as unknown as Sql, box, centre, limit));
}
