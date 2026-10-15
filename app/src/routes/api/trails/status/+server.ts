import { db } from '#lib/server/db.js';
import { jsonWithEtag } from '#lib/server/json-etag.js';
import { trailStatus, type Sql } from '#lib/server/trails/status.js';

/**
 * Trail status for the Trails layer (#lib/server/trails/status.ts): R2R's
 * condition per trail and the Greenbelt's closures and detours, with the
 * OpenStreetMap ways each lies on, applied as feature-state. Empty before the
 * trails plugin's migration. `no-cache` with an ETag.
 */
export async function GET({ request }) {
	return jsonWithEtag(await trailStatus(db() as unknown as Sql), request.headers.get('if-none-match'));
}
