import { error, json } from '@sveltejs/kit';
import { db } from '#lib/server/db.js';
import { parseAt, parseWindow, readTracks, tracks } from '#lib/server/transit-tracks.js';

/**
 * GET /api/transit/tracks?window=120[&at=<ISO time>]: bus playback steps
 * (docs/14 §14.4 "Playback"; contract in #lib/contracts/tracks).
 *
 * `window` is in seconds (default 120, at most 900). A past `at` pins the
 * window's end for replay and tests; nothing after it is returned, and `now`
 * is `at`. Never cached by the browser; a 5 s server micro-cache means N
 * viewers cost one query (`x-cache: hit` says a response came from it).
 */
export async function GET({ url, setHeaders }) {
	const nowMs = Date.now();
	const windowS = parseWindow(url.searchParams.get('window'));
	if (windowS === null) error(400, '`window` must be a whole number of seconds (at most 900).');
	const at = parseAt(url.searchParams.get('at'), nowMs / 1000);
	if (at === undefined) error(400, '`at` must be an ISO time, e.g. 2026-10-06T14:30:00Z.');
	const sql = db();
	const { body, hit } = await tracks((T, w) => readTracks(sql, T, w), windowS, at, nowMs);
	setHeaders({ 'cache-control': 'no-store', 'x-cache': hit ? 'hit' : 'miss' });
	return json(body);
}
