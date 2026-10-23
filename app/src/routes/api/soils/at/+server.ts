import { error } from '@sveltejs/kit';
import { db } from '#lib/server/db.js';
import { jsonWithEtag } from '#lib/server/json-etag.js';
import { unitAt, type Sql } from '#lib/server/soils/units.js';

/**
 * The map unit at a point (landscape sprint P1-app): `GET /api/soils/at?lng=&lat=` →
 * `{ unit: { mukey, symbol, name, surveyed } | null }`. `unit` is null outside the survey, before the soils
 * migration or a load (never a 500), and `surveyed` is false over NRCS's "No Digital Data Available" area.
 * `no-cache` with an ETag. (`/api/soils/tiles/...` is the generic tile route's: this folder has no `tiles/`
 * of its own.)
 */
export async function GET({ url, request }) {
	const lng = Number(url.searchParams.get('lng'));
	const lat = Number(url.searchParams.get('lat'));
	if (!url.searchParams.get('lng') || !url.searchParams.get('lat') || !Number.isFinite(lng) || !Number.isFinite(lat) || Math.abs(lng) > 180 || Math.abs(lat) > 90) {
		error(400, 'Give lng and lat in degrees');
	}
	return jsonWithEtag({ unit: await unitAt(db() as unknown as Sql, lng, lat) }, request.headers.get('if-none-match'));
}
