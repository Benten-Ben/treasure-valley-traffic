import { json } from '@sveltejs/kit';
import { roadWeather, type Sql } from '#lib/layers/roadweather/stations.server.js';
import type { RoadWeather } from '#lib/layers/roadweather/model.js';
import { db } from '#lib/server/db.js';
import { archive, imagesEnabled } from '#lib/server/frames.js';

/**
 * Road-weather stations with their views and each view's newest picture
 * (docs/14 §14.6 "Road weather", WP16; the shape is `RoadWeather` in
 * #lib/layers/roadweather/model.ts). `no-store`: the ages change by the
 * minute. Computed at most every 10 s, however many clients ask.
 */
const TTL_MS = 10_000;
let memo: { at: number; value: Promise<RoadWeather> } | null = null;

export async function GET({ setHeaders }) {
	setHeaders({ 'cache-control': 'no-store' });
	const now = Date.now();
	if (!memo || now - memo.at >= TTL_MS) {
		const value = roadWeather({ sql: db() as unknown as Sql, archive: imagesEnabled() ? archive() : null, nowMs: now });
		memo = { at: now, value };
		// A failure isn't kept: the next request tries again.
		value.catch(() => {
			if (memo?.value === value) memo = null;
		});
	}
	return json(await memo.value);
}
