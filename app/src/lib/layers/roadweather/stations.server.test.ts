import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Archive, localDay } from '#lib/server/archive.js';
import { resetCameraProvider } from '#lib/server/camera-provider.js';
import { GRAY_16x8, sha, variant } from '#lib/server/live-fixtures.test-util.js';
import { NO_FEED_AFTER_S } from './model.js';
import { NO_MIGRATION, roadWeather, type Sql } from './stations.server.js';

/**
 * GET /api/roadweather's answer (WP16), from a fake database and a temporary
 * capture archive: three synthetic stations, the views' newest pictures and
 * their ages, "no live feed" from capture and from 511's list, hollow
 * stations, and the answer with live images off or before the migration.
 */

const NOW = Date.parse('2026-10-07T18:00:00Z');
// Station 1: 3 views (live, 30 min old, disabled); station 2: 2 views with no pictures (hollow);
// station 3 (ODOT): 1 view not in any capture list.
const ROWS = [
	{ id: 1, name: 'Example Grade (synthetic)', provider: 'ITD RWIS', lon: -116.24, lat: 43.56, view_id: 11, image_id: 990011, status: 'Enabled', direction: 'Looking East', sort_order: 0 },
	{ id: 1, name: 'Example Grade (synthetic)', provider: 'ITD RWIS', lon: -116.24, lat: 43.56, view_id: 12, image_id: 990012, status: 'Enabled', direction: null, sort_order: 1 },
	{ id: 1, name: 'Example Grade (synthetic)', provider: 'ITD RWIS', lon: -116.24, lat: 43.56, view_id: 14, image_id: 990014, status: 'Disabled', direction: null, sort_order: 3 },
	{ id: 2, name: 'Test Summit (synthetic)', provider: 'ITD RWIS', lon: -116.43, lat: 43.69, view_id: 21, image_id: 990021, status: 'Enabled', direction: null, sort_order: 0 },
	{ id: 2, name: 'Test Summit (synthetic)', provider: 'ITD RWIS', lon: -116.43, lat: 43.69, view_id: 22, image_id: 990022, status: 'Enabled', direction: null, sort_order: 1 },
	{ id: 3, name: 'Sample Bridge OR (synthetic)', provider: 'ODOT', lon: -117.01, lat: 43.72, view_id: 31, image_id: 990031, status: 'Enabled', direction: 'Northbound', sort_order: 0 },
	{ id: 4, name: 'No Views (synthetic)', provider: 'ITD RWIS', lon: -116.9, lat: 43.2, view_id: null, image_id: null, status: null, direction: null, sort_order: null }
];

let dir: string;
let queries: string[];

/** A fake postgres.js: the column check, then the stations query; `sql(list)` is a list fragment. */
function fakeSql(o: { provider?: boolean } = {}): Sql {
	return ((first: TemplateStringsArray | readonly unknown[], ...values: unknown[]) => {
		if (!('raw' in first)) return { list: first };
		const q = first.join('?');
		queries.push(q);
		if (q.includes('information_schema.columns')) return Promise.resolve([{ ok: o.provider ?? true }]);
		expect(values[0]).toEqual({ list: ['ITD RWIS', 'ODOT'] });
		return Promise.resolve(ROWS);
	}) as unknown as Sql;
}

async function frame(image: number, at: number, n: number) {
	const day = localDay(at);
	const folder = join(dir, 'cameras', 'jpeg', String(image), day);
	await mkdir(folder, { recursive: true });
	const stamp = new Date(at).toISOString().replace(/\.\d+Z$/, 'Z').replace(/[-:]/g, '');
	const bytes = variant(GRAY_16x8, n);
	await writeFile(join(folder, `${stamp}.jpg`), bytes);
	const fetched = new Date(at).toISOString().replace(/\.\d+Z$/, 'Z');
	await writeFile(join(folder, 'index.csv'), `fetched_at,file,bytes,sha256\n${fetched},${stamp}.jpg,${bytes.length},${sha(bytes)}\n`);
}

async function status(images: number[], heartbeatAgoS = 30) {
	await mkdir(join(dir, 'cameras', 'status'), { recursive: true });
	await writeFile(
		join(dir, 'cameras', 'status', 'regional-cameras.json'),
		JSON.stringify({ tag: 'regional-cameras', cadence_s: 600, image_ids: images, heartbeat: NOW / 1000 - heartbeatAgoS, paused_low_disk: false })
	);
}

beforeEach(async () => {
	dir = await mkdtemp(join(tmpdir(), 'tvt-roadweather-'));
	queries = [];
	resetCameraProvider();
	await frame(990011, NOW - 4 * 60_000, 1);
	await frame(990012, NOW - 30 * 60_000, 2);
	await status([990011, 990012, 990014, 990021, 990022]);
});

afterEach(async () => {
	await rm(dir, { recursive: true, force: true });
	resetCameraProvider();
});

describe('GET /api/roadweather', () => {
	it('gives each view its newest picture’s age, and says which show no live feed', async () => {
		const rw = await roadWeather({ sql: fakeSql(), archive: new Archive({ root: dir }), nowMs: NOW });
		expect(rw).toMatchObject({ contract: 1, now: NOW / 1000, images: true });
		expect(rw.stations.map((s) => [s.id, s.provider, s.views.length, s.hollow])).toEqual([
			[1, 'ITD RWIS', 3, false],
			[2, 'ITD RWIS', 2, true],
			[3, 'ODOT', 1, false],
			[4, 'ITD RWIS', 0, false]
		]);
		const [a, b, c] = rw.stations;
		expect(a.views.map((v) => [v.id, v.label, v.ageS, v.feed, v.disabled])).toEqual([
			[11, 'Looking East', 240, 'live', false],
			[12, 'View 2', 1800, 'live', false],
			[14, 'View 3', null, 'no_feed', true]
		]);
		expect(a.views[0].seenAt).toBe((NOW - 240_000) / 1000);
		// Recorded but nothing saved: 511 has been serving its "no live feed" picture.
		expect(b.views.map((v) => [v.ageS, v.capturing, v.feed])).toEqual([
			[null, true, 'no_feed'],
			[null, true, 'no_feed']
		]);
		// Not recorded by any running capture: can't tell.
		expect(c.views[0]).toMatchObject({ label: 'Northbound', capturing: false, feed: 'unknown' });
	});

	it('a picture older than 45 minutes while capture runs is no live feed', async () => {
		await frame(990021, NOW - (NO_FEED_AFTER_S + 60) * 1000, 3);
		await frame(990022, NOW - 10 * 60_000, 4);
		const rw = await roadWeather({ sql: fakeSql(), archive: new Archive({ root: dir }), nowMs: NOW });
		const b = rw.stations[1];
		expect(b.views.map((v) => v.feed)).toEqual(['no_feed', 'live']);
		expect(b.hollow).toBe(false);
	});

	it('when capture has stopped, a station without pictures is not called hollow', async () => {
		await status([990011, 990012, 990021, 990022], 4 * 3600);
		const rw = await roadWeather({ sql: fakeSql(), archive: new Archive({ root: dir }), nowMs: NOW });
		expect(rw.stations[1].views.map((v) => v.feed)).toEqual(['unknown', 'unknown']);
		expect(rw.stations[1].hollow).toBe(false);
	});

	it('with live images off, reads no archive and gives no ages', async () => {
		const rw = await roadWeather({ sql: fakeSql(), archive: null, nowMs: NOW });
		expect(rw.images).toBe(false);
		expect(rw.stations.flatMap((s) => s.views.map((v) => v.ageS))).toEqual([null, null, null, null, null, null]);
		expect(rw.stations[0].views.map((v) => v.feed)).toEqual(['unknown', 'unknown', 'no_feed']);
		expect(rw.stations.some((s) => s.hollow)).toBe(false);
	});

	it('before the cameras plugin’s migration, answers no stations and says why', async () => {
		const rw = await roadWeather({ sql: fakeSql({ provider: false }), archive: null, nowMs: NOW });
		expect(rw).toMatchObject({ stations: [], note: NO_MIGRATION });
		expect(queries.some((q) => q.includes('core.camera c'))).toBe(false);
	});
});
