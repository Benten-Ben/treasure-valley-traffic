import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import type { Browser } from '@playwright/test';
import { MB, recordNetwork, summarize } from '../../scripts/net.mjs';
import { env, expect, mapReady, test } from './fixtures.js';

/**
 * performance (docs/14 §14.10, WP5 acceptance; §14.9 fixes 1, 5, 6 and 8):
 *
 * - the hillshade is drawn from the 3D terrain's source by default, and
 *   `?hillshade=capped` keeps a second source capped at z12;
 * - both options' cold first loads, recorded side by side (the default's
 *   limits are asserted in the budget spec; the capped option has none);
 * - road tiles go out gzipped, immutable for the current version and
 *   `max-age=60` otherwise, and the versioned APIs answer immutable when
 *   `v` matches;
 * - `?perf` shows the HUD and counts, and `?workers=` sets the worker count.
 */

/** A cold first load at `path` in a fresh context (no cache), measured like perf.mjs --budget. */
async function coldLoad(browser: Browser, baseURL: string, path: string) {
	const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, baseURL });
	const page = await context.newPage();
	const errors: string[] = [];
	page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
	const net = await recordNetwork(page, { throttle: { latencyMs: 40, mbps: 25 } });
	await page.goto(path);
	await mapReady(page);
	await net.settle();
	const s = summarize(net.entries, new URL(baseURL).origin);
	const hillshade = await page.evaluate(() => {
		const map = (globalThis as any).__tvt.map;
		return { source: map.getLayer('hillshade')?.source ?? null, sources: Object.keys(map.style.tileManagers ?? map.style.sourceCaches ?? {}) };
	});
	await net.detach();
	await context.close();
	return {
		path,
		requests: s.requests,
		bytes: s.bytes,
		mb: MB(s.bytes),
		terrain: { requests: s.byKind.terrain?.requests ?? 0, mb: MB(s.byKind.terrain?.bytes ?? 0) },
		duplicates: s.duplicates,
		failed: s.failed,
		foreign: s.foreign,
		byKind: s.byKind,
		hillshade,
		consoleErrors: errors
	};
}

test.describe('performance', () => {
	test('the hillshade reads the terrain source by default; ?hillshade=capped keeps a second source capped at z12', { tag: '@wp5' }, async ({ page, consoleErrors }) => {
		const read = () =>
			page.evaluate(() => {
				const map = (globalThis as any).__tvt.map;
				const second = map.getSource('hillshade');
				return {
					layerSource: map.getLayer('hillshade')?.source,
					terrainSource: map.getTerrain()?.source,
					dem: Object.entries(map.getStyle().sources as Record<string, { type: string }>).filter(([, s]) => s.type === 'raster-dem').map(([id]) => id).sort(),
					secondMaxzoom: second ? second.maxzoom : null,
					drawn: map.getLayoutProperty('hillshade', 'visibility') !== 'none'
				};
			});
		await page.goto('/#map=10/43.6/-116.4/0/45&layers=none');
		await mapReady(page);
		expect(await read()).toEqual({ layerSource: 'terrain', terrainSource: 'terrain', dem: ['terrain'], secondMaxzoom: null, drawn: true });

		// A fresh document: the flag is read once, at boot.
		await page.goto('/?hillshade=capped#map=10/43.6/-116.4/0/45&layers=none');
		await mapReady(page);
		expect(await read()).toEqual({ layerSource: 'hillshade', terrainSource: 'terrain', dem: ['hillshade', 'terrain'], secondMaxzoom: 12, drawn: true });
		expect(consoleErrors).toEqual([]);
	});

	test("records both hillshade options' cold first loads side by side", { tag: '@wp5' }, async ({ browser, baseURL }) => {
		const one = await coldLoad(browser, baseURL!, '/');
		const capped = await coldLoad(browser, baseURL!, '/?hillshade=capped');
		const record = { at: new Date().toISOString(), view: 'default (manifest centre, z10, pitch 45)', terrain: one, capped };
		const dir = join(process.env.TVT_MAIN!, 'data', 'dev', env().wp || 'local');
		mkdirSync(dir, { recursive: true });
		writeFileSync(join(dir, 'budget-hillshade-options.json'), JSON.stringify(record, null, 2));
		const line = (r: typeof one) => `${r.requests} requests, ${r.mb} MB (terrain ${r.terrain.requests} requests, ${r.terrain.mb} MB), ${r.duplicates} duplicate ranges`;
		test.info().annotations.push({ type: 'hillshade=terrain (default)', description: line(one) }, { type: 'hillshade=capped', description: line(capped) });
		for (const r of [one, capped]) {
			expect(r.foreign).toEqual([]);
			expect(r.failed).toBe(0);
			expect(r.consoleErrors).toEqual([]);
		}
		expect(one.hillshade.source).toBe('terrain');
		expect(capped.hillshade.source).toBe('hillshade');
		// One DEM source downloads less terrain than two.
		expect(one.terrain.mb).toBeLessThan(capped.terrain.mb);
	});

	test('road tiles go out gzipped, immutable at the current version; the versioned APIs too', { tag: '@wp5' }, async ({ request }) => {
		const meta = await (await request.get('/api/meta')).json();
		const v = meta.versions;
		expect(v.roads).toBeTruthy();
		// Downtown Boise at z12.
		const tile = (q: string) => request.get(`/api/tiles/roads/12/725/1495${q}`, { headers: { 'accept-encoding': 'gzip' } });
		const current = await tile(`?v=${v.roads}`);
		expect(current.status()).toBe(200);
		expect(current.headers()['content-encoding']).toBe('gzip');
		expect(current.headers()['content-type']).toBe('application/vnd.mapbox-vector-tile');
		expect(current.headers()['cache-control']).toBe('public, max-age=31536000, immutable');
		expect((await current.body()).length).toBeGreaterThan(1000);
		const old = await tile('?v=old');
		expect(old.headers()['cache-control']).toBe('public, max-age=60');
		expect(old.headers()['content-encoding']).toBe('gzip');
		expect((await old.body()).equals(await current.body())).toBe(true);

		for (const [path, key] of [['/api/cameras', 'cameras'], ['/api/calibrations', 'calibrations']] as const) {
			expect(v[key], key).toBeTruthy();
			expect((await request.get(`${path}?v=${v[key]}`)).headers()['cache-control'], path).toBe('public, max-age=31536000, immutable');
			expect((await request.get(`${path}?v=stale`)).headers()['cache-control'], path).toBe('no-cache');
			expect((await request.get(path)).headers()['cache-control'], path).toBe('no-cache');
		}
	});

	test('?perf shows the HUD and its counts; ?workers= sets the worker count', { tag: '@wp5' }, async ({ page, consoleErrors }) => {
		await page.goto('/?perf&workers=2');
		await mapReady(page);
		const hud = page.locator('.tvt-perf-hud');
		await expect(hud).toBeVisible();
		await expect(hud).toContainText('gl tex');
		const p = await page.evaluate(() => {
			const h = (globalThis as any).__tvtPerf;
			const marks = performance.getEntriesByType('mark').map((m) => m.name);
			return { textures: h.textures, setData: h.setDataCalls, snapshot: h.snapshot(), marks };
		});
		expect(p.textures).toBeGreaterThan(0);
		expect(p.setData).toBeGreaterThanOrEqual(0);
		expect(Object.keys(p.snapshot.tiles)).toContain('terrain');
		expect(p.snapshot.requests).toBeGreaterThan(10);
		for (const m of ['tvt:boot', 'tvt:manifest', 'tvt:style-load', 'tvt:load', 'tvt:idle']) expect(p.marks).toContain(m);
		// The default layers (transit, cameras) are marked on, and idle once loaded.
		await expect.poll(() => page.evaluate(() => performance.getEntriesByType('mark').map((m) => m.name).filter((n) => n.startsWith('tvt:layer:')).sort()), { timeout: 60_000 })
			.toEqual(expect.arrayContaining(['tvt:layer:cameras:idle', 'tvt:layer:cameras:on', 'tvt:layer:transit:idle', 'tvt:layer:transit:on']));
		// MapLibre's workers: two, as asked (its default in Chrome is one).
		expect(page.workers().filter((w) => /maplibre-gl-worker/.test(w.url()))).toHaveLength(2);
		expect(consoleErrors).toEqual([]);
	});
});
