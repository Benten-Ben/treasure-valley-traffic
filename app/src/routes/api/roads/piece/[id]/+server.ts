import { error } from '@sveltejs/kit';
import { BEHIND_MESSAGE, parseBuild, parsePieceRef } from '#lib/layers/lanes/lanes.js';
import { db } from '#lib/server/db.js';
import { jsonWithEtag } from '#lib/server/json-etag.js';
import { pieceAnswer, type Sql } from '#lib/server/roads/piece.js';

/**
 * One road piece's card (landscape sprint P9): `GET /api/roads/piece/<kind>-<id>?build=<the map's roads build>`, with
 * kind `surface`, `edge`, `marking` or `line` (a picked tile feature, whose id is its build's own) and the build
 * from `tiles/manifest.json`. A map that is a build behind the data gets 409, never another build's road; before
 * the roads tables exist, or for an id the build doesn't have, 404. `no-cache` with an ETag, as the paving card.
 */
export async function GET({ params, url, request }) {
	const ref = parsePieceRef(params.id ?? '');
	if (!ref) error(400, 'Bad road piece id');
	const build = parseBuild(url.searchParams.get('build'));
	if (!build) error(400, "Say which roads build the map is from (?build=)");
	const r = await pieceAnswer(db() as unknown as Sql, ref, build);
	if (r.status === 'behind') error(409, BEHIND_MESSAGE);
	if (r.status === 'none') error(404, 'No such road piece');
	return jsonWithEtag(r.card, request.headers.get('if-none-match'));
}
