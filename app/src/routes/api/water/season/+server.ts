import { db } from '#lib/server/db.js';
import { jsonWithEtag } from '#lib/server/json-etag.js';
import type { Sql } from '#lib/server/water/common.js';
import { season } from '#lib/server/water/season.js';

/**
 * Each canal's current season, on, off or unknown (#lib/server/water/season.ts): `GET /api/water/season` ->
 * `{ canals, reaches: { on, off, unknown }, credits, updated, republish, license }`. The reach ids are the baked
 * reaches whose canal is in each state; the map sets them as feature-state, and the card reads its canal's words
 * from `canals`. Legal-window states are IDWR's: internal, for this tailnet map. An empty season before the water
 * plugin's migration 0002. `no-cache` with an ETag.
 */
export async function GET({ request }) {
	return jsonWithEtag(await season(db() as unknown as Sql), request.headers.get('if-none-match'));
}
