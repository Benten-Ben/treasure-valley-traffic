import { db } from '#lib/server/db.js';
import { cacheControl, transitNetwork } from '#lib/server/transit-network.js';

/**
 * GET /api/transit/network?v=<build> (docs/14 §14.4, §14.8 "APIs"; contract in
 * #lib/contracts/network). Routes and their colors, side-by-side corridor
 * segments, stops, hubs and dormant routes; each route's plain shapes
 * (`bundled: false`) until the first ribbon build exists.
 *
 * Immutable when `v` names the current build (the client takes it from
 * /api/meta), `no-cache` otherwise, with an ETag either way.
 */
export async function GET({ url, request }) {
	const answer = await transitNetwork(db());
	const headers = {
		'content-type': 'application/json',
		'cache-control': cacheControl(answer, url.searchParams.get('v')),
		etag: answer.etag
	};
	if (request.headers.get('if-none-match') === answer.etag) return new Response(null, { status: 304, headers });
	return new Response(answer.body, { headers });
}
