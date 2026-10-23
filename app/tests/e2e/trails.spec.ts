import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import type { Page } from '@playwright/test';
import { MB, recordNetwork } from '../../scripts/net.mjs';
import { env, expect, mapReady, screenPath, test } from './fixtures.js';
import { BLOCK, cleanTrails, FOOTHILLS, GEO, IDS, seedTrails, type Seeded } from './trails-seed.js';

/**
 * trails (plan §4.2, package P6-app), on made-up trails (trails-seed.ts: invented names and ids, linked the way
 * trails-match links real ones) and, for the paved treads, the synthetic landscape file
 * (`TILES_DIR=$(node scripts/tiles-fixture.mjs --ground painted)`; basemap/landscape/fixtures/README.md):
 *
 * - the lines draw: the ways from the tiles, Protomaps' footpaths hide while Trails is on and come back when it is
 *   off, a private track is not in the tiles, informal ways come in at z16;
 * - the status draws by feature-state: a closed agency line that no way lies along draws itself, closed (its own
 *   layer, its ✕ marks), a muddy way and a caution way take their layers, and the informal way near the closed trail
 *   is hidden;
 * - a click on a way or a line opens the card (surface with Ridge to Rivers' default, width estimated, the status in the
 *   agency's words and who said so), and the legend names every dash;
 * - the paved treads in the base draw from z15.5 and open a card only while Trails is on;
 * - the z13 foothills view's tile bytes and frame times are logged (data/dev/<wp>/trails-perf.json), against the owner's
 *   budget of 150 KB gzip for the busiest tile.
 */

const at = (zoom: number, c: [number, number], layers = 'trails') => `/#map=${zoom}/${c[1]}/${c[0]}/0/0&layers=${layers}`;

type Feature = { id: number; state: Record<string, unknown> | undefined; properties: Record<string, unknown> };
/** The features a style layer draws now (any layer on the map: the Trails ones and the base's), with their feature-state. */
const features = (page: Page, layer: string): Promise<Feature[]> =>
	page.evaluate((l) => {
		const map = (globalThis as any).__tvt.map;
		if (!map.getLayer(l)) return [];
		return map.queryRenderedFeatures({ layers: [l] }).map((f: any) => ({ id: f.id, state: f.state, properties: f.properties }));
	}, layer);
const info = (page: Page): Promise<{ visible: boolean; status: string; error: string | null; applied: number; ways: number; lines: number; statusRequests: number }> =>
	page.evaluate(() => (globalThis as any).__tvtTrails?.info() ?? null);
const selection = (page: Page) => page.evaluate(() => (globalThis as any).__tvt.layers.selection);
const layout = (page: Page, layer: string): Promise<string | null> =>
	page.evaluate((l) => {
		const map = (globalThis as any).__tvt.map;
		return map.getLayer(l) ? (map.getLayoutProperty(l, 'visibility') ?? 'visible') : null;
	}, layer);
/** A map point on the screen (page px), for a click. */
const screenOf = (page: Page, lng: number, lat: number): Promise<{ x: number; y: number }> =>
	page.evaluate(
		([x, y]) => {
			const map = (globalThis as any).__tvt.map;
			const p = map.project([x, y]);
			const r = map.getCanvas().getBoundingClientRect();
			return { x: r.left + p.x, y: r.top + p.y };
		},
		[lng, lat]
	);
/** On screen and clear of the legend column, the top bar and the toolbar (the card is on the right: it opens after the click). */
const clear = (p: { x: number; y: number }) => p.x > 330 && p.x < 1280 - 420 && p.y > 90 && p.y < 800 - 130;
const card = (page: Page) => page.getByRole('region', { name: 'Selected' });

let seeded: Seeded | null = null;
let landscape = false;

test.beforeAll(async () => {
	seeded = await seedTrails();
});

test.afterAll(async () => {
	await cleanTrails();
});

test.beforeEach(async ({ page }) => {
	// Whether the tiles folder holds the synthetic landscape file (the paved treads' test needs it).
	const manifest = await page.request.get('/tiles/manifest.json').then((r) => (r.ok() ? r.json() : null)).catch(() => null);
	landscape = Boolean(manifest?.landscape?.layers?.['trails.paved_paths']);
});

/** Wait until the status is in and applied. */
async function statusIn(page: Page) {
	await expect.poll(async () => (await info(page))?.applied ?? 0, { timeout: 90_000 }).toBeGreaterThan(5);
	const i = await info(page);
	expect(i.status, i.error ?? '').toBe('ready');
}

test.describe('trails', () => {
	test('the lines draw, Protomaps’ footpaths hide while Trails is on, and a private track is not in the tiles', { tag: '@trails' }, async ({ page, consoleErrors }) => {
		test.setTimeout(300_000);
		await page.goto(at(14, FOOTHILLS));
		await mapReady(page);
		await statusIn(page);
		await expect.poll(async () => (await features(page, 'trails-hit-ways')).length, { timeout: 60_000 }).toBeGreaterThanOrEqual(4);
		const ids = (await features(page, 'trails-hit-ways')).map((f) => f.id);
		expect(ids).toEqual(expect.arrayContaining([IDS.ridge, IDS.loop, IDS.climb, IDS.track]));
		// Closed to the public, and informal before z16: left out of the tiles.
		expect(ids).not.toContain(IDS.private);
		expect(ids).not.toContain(IDS.informal);
		expect(await layout(page, 'trails-ways')).toBe('visible');
		// Protomaps' paths are under the Trails layer's lines while it is on.
		expect(await layout(page, 'roads_other')).toBe('none');
		// The legend names every dash.
		const legend = page.getByRole('region', { name: 'Trails legend' });
		await expect(legend).toBeVisible();
		for (const word of ['Open', 'Caution', 'Muddy, stay off', 'Closed', 'Detour', 'Not evaluated', 'Informal']) await expect(legend.getByText(word, { exact: true }).first()).toBeVisible();
		for (const dash of ['Long dashes and ▲', 'Dots and ■', 'Dash and dot, and ✕', 'Short dashes and arrowheads']) await expect(legend.getByText(dash)).toBeVisible();
		await page.screenshot({ path: screenPath('trails-z14.png') });
		expect(consoleErrors.filter((e) => /trails/i.test(e))).toEqual([]);

		// Off, the footpaths are Protomaps' again.
		await page.goto(at(14, FOOTHILLS, 'none'));
		await mapReady(page);
		await expect.poll(() => layout(page, 'roads_other')).toBe('visible');
		// (A hash change keeps the page, so the module stays mounted: its layers are hidden.)
		expect(['none', null]).toContain(await layout(page, 'trails-ways'));
	});

	test('the status draws by feature-state: a closed line that no way lies along draws itself closed, and the others take their dashes', { tag: '@trails' }, async ({ page }) => {
		test.setTimeout(300_000);
		await page.goto(at(14, FOOTHILLS));
		await mapReady(page);
		await statusIn(page);
		const { lines } = seeded!;
		// The closed gulch: an agency line of its own (no way lies along it), in the closed state, with its marks.
		await expect.poll(async () => (await features(page, 'trails-agency-closed')).some((f) => f.id === lines['e2e-gulch']), { timeout: 60_000 }).toBe(true);
		const gulch = (await features(page, 'trails-agency-closed')).find((f) => f.id === lines['e2e-gulch'])!;
		expect(gulch.state).toEqual({ sev: 'closed' });
		expect(gulch.properties).toMatchObject({ name: 'Fixture Closed Gulch', kind: 'trail', part: 'line' });
		// Its whole line carries the ✕ marks (the icon layer reads the same state).
		const marks = await page.evaluate(() => (globalThis as any).__tvt.map.getLayer('trails-mark-closed')?.type);
		expect(marks).toBe('symbol');
		// The unchecked spur is not evaluated; the Greenbelt closure is a stretch of its cycleway; the detour draws itself.
		const sev = async (layer: string, id: number) => (await features(page, layer)).find((f) => f.id === id)?.state?.sev;
		expect(await sev('trails-agency-not_evaluated', lines['e2e-unevaluated'])).toBe('not_evaluated');
		expect(await sev('trails-agency-closed', lines['construction:e2e-1'])).toBe('closed');
		expect(await sev('trails-agency-detour', lines['detour:e2e-1'])).toBe('detour');
		expect((await features(page, 'trails-agency-detour')).find((f) => f.id === lines['detour:e2e-1'])?.properties).toMatchObject({ kind: 'detour', part: 'line' });
		// R2R's three trails paint their OpenStreetMap ways (the ways' tiles are OpenStreetMap's alone: the state is feature-state).
		expect(await sev('trails-ways', IDS.ridge)).toBe('open');
		expect(await sev('trails-ways-do_not_use', IDS.loop)).toBe('do_not_use');
		expect(await sev('trails-ways-caution', IDS.climb)).toBe('caution');
		// Nothing says a way with no line has a state.
		expect(await sev('trails-ways', IDS.track)).toBeUndefined();
		// The agency lines the way layers paint are not drawn again by their own layer's tiles: the ridge's whole line is only at valley zoom.
		const ridgeLine = (await features(page, 'trails-agency-open')).find((f) => f.id === lines['e2e-ridge']);
		expect(ridgeLine, 'a painted trail’s line is not drawn on its own from z13').toBeUndefined();
		await page.screenshot({ path: screenPath('trails-status-z14.png') });
		// The tiles carry no state: the same tile, whatever the status says.
		const tile = await page.evaluate(async () => {
			const meta = await (await fetch('/api/meta')).json();
			const v = meta.versions.layers['trails.agency'];
			const r = await fetch(`/api/trails/tiles/agency/14/2906/5984?v=${encodeURIComponent(v)}`);
			return { status: r.status, type: r.headers.get('content-type'), bytes: (await r.arrayBuffer()).byteLength };
		});
		expect(tile.status).toBe(200);
		expect(tile.type).toContain('vector-tile');
	});

	test('informal ways come in at z16 and the one near the closed trail stays hidden', { tag: '@trails' }, async ({ page }) => {
		test.setTimeout(300_000);
		await page.goto(at(15, FOOTHILLS));
		await mapReady(page);
		await statusIn(page);
		expect(await features(page, 'trails-informal'), 'no informal way before z16').toEqual([]);
		await page.goto(at(16.5, GEO.informal[0] as [number, number]));
		await mapReady(page);
		await statusIn(page);
		await expect.poll(async () => (await features(page, 'trails-informal')).length, { timeout: 60_000 }).toBeGreaterThanOrEqual(1);
		const informal = (await features(page, 'trails-informal')).find((f) => f.id === IDS.informal);
		expect(informal?.state?.hide).toBeUndefined();
		await page.goto(at(16.5, GEO.informalNearGulch[0] as [number, number]));
		await mapReady(page);
		await statusIn(page);
		await expect.poll(async () => (await features(page, 'trails-informal')).some((f) => f.id === IDS.informalNearGulch), { timeout: 60_000 }).toBe(true);
		const near = (await features(page, 'trails-informal')).find((f) => f.id === IDS.informalNearGulch)!;
		expect(near.state).toEqual({ hide: true });
		await page.screenshot({ path: screenPath('trails-informal-z16.5.png') });
	});

	test('a click on a way opens the card: its surface with Ridge to Rivers’ default, an estimated width, and the status in the agency’s words', { tag: '@trails' }, async ({ page }) => {
		test.setTimeout(300_000);
		await page.goto(at(16, GEO.ridge[2] as [number, number]));
		await mapReady(page);
		await statusIn(page);
		await expect.poll(async () => (await features(page, 'trails-hit-ways')).some((f) => f.id === IDS.ridge), { timeout: 60_000 }).toBe(true);
		const p = await screenOf(page, GEO.ridge[2][0], GEO.ridge[2][1]);
		expect(clear(p), `the way’s vertex is on screen and clear of the panels (${p.x.toFixed(0)}, ${p.y.toFixed(0)})`).toBe(true);
		await page.mouse.click(p.x, p.y);
		await expect.poll(async () => (await selection(page))?.id).toBe(`way:${IDS.ridge}`);
		const sel = await selection(page);
		expect(sel).toMatchObject({ kind: 'trail', layer: 'trails', title: 'Fixture Ridge Trail' });
		const c = card(page);
		await expect(c.getByRole('heading', { name: 'Fixture Ridge Trail' })).toBeVisible();
		await expect(c.getByText('Path', { exact: true })).toBeVisible();
		// Nothing tags its surface; a Ridge to Rivers trail runs along it, so the card (only) says dirt, and why.
		await expect(c.locator('dd', { hasText: /^Dirt/ })).toBeVisible({ timeout: 30_000 });
		await expect(c.getByText(/Ridge to Rivers trail runs along it/)).toBeVisible();
		// Its width is an estimate, and says so.
		await expect(c.getByText('0.8 m · 2.6 ft')).toBeVisible();
		await expect(c.getByText('estimated from the kind of way')).toBeVisible();
		// The status, in R2R's words, and whose advice it is.
		await expect(c.getByRole('list', { name: 'Status of this trail' }).getByText('Dry / Tacky - Enjoy')).toBeVisible();
		await expect(c.getByText(/Ridge to Rivers' advice/)).toBeVisible();
		await expect(c.getByText('© OpenStreetMap contributors', { exact: false })).toBeVisible();
		await page.screenshot({ path: screenPath('trails-card-way.png') });
		// The selected way is outlined (a filter on the selected layers), and Esc clears it.
		const filter = await page.evaluate(() => (globalThis as any).__tvt.map.getFilter('trails-selected'));
		expect(filter).toEqual(['==', ['id'], IDS.ridge]);
		await page.keyboard.press('Escape');
		await expect.poll(async () => (await selection(page))?.id ?? null).toBeNull();
		await expect.poll(() => page.evaluate(() => (globalThis as any).__tvt.map.getFilter('trails-selected'))).toEqual(['==', ['id'], -1]);

		// The closed gulch: an agency line of its own, with its card.
		await page.goto(at(16, GEO.gulch[1] as [number, number]));
		await mapReady(page);
		await statusIn(page);
		const gulchId = seeded!.lines['e2e-gulch'];
		await expect.poll(async () => (await features(page, 'trails-hit-agency')).some((f) => f.id === gulchId), { timeout: 60_000 }).toBe(true);
		const q = await screenOf(page, GEO.gulch[1][0], GEO.gulch[1][1]);
		expect(clear(q)).toBe(true);
		await page.mouse.click(q.x, q.y);
		await expect.poll(async () => (await selection(page))?.id).toBe(`line:${gulchId}`);
		await expect(card(page).getByRole('heading', { name: 'Fixture Closed Gulch' })).toBeVisible();
		await expect(card(page).getByText('CLOSED').first()).toBeVisible({ timeout: 30_000 });
		await expect(card(page).getByText(/no OpenStreetMap way lies along it/)).toBeVisible();
		await page.screenshot({ path: screenPath('trails-card-line.png') });
	});

	test('the card API says nothing of what is not drawn, and answers 404 for an unknown way', { tag: '@trails' }, async ({ page }) => {
		const get = (u: string) => page.request.get(u);
		const ok = await get(`/api/trails/way/${IDS.ridge}`);
		expect(ok.status()).toBe(200);
		expect(await ok.json()).toMatchObject({ id: IDS.ridge, name: 'Fixture Ridge Trail', surface: 'dirt', surface_from: 'default', surface_default: 'Ridge to Rivers trail', width_from: 'estimated' });
		expect((await get(`/api/trails/way/${IDS.private}`)).status(), 'a private track has no card').toBe(404);
		expect((await get('/api/trails/way/123456789')).status()).toBe(404);
		expect((await get('/api/trails/way/abc')).status()).toBe(400);
		const status = await (await get('/api/trails/status')).json();
		expect(status.ways[String(IDS.loop)]).toBe('do_not_use');
		expect(status.hidden).toContain(IDS.informalNearGulch);
	});

	test('the paved treads in the base draw from z15.5, and open a card only while Trails is on', { tag: '@trails' }, async ({ page }) => {
		test.setTimeout(300_000);
		test.skip(!landscape, 'the tiles folder has no synthetic landscape file: TILES_DIR=$(node scripts/tiles-fixture.mjs --ground painted)');
		const mid = GEO.riverside[1];
		// Trails on: the treads and the plaza are in the base, and a click on a tread opens the way’s card.
		await page.goto(at(17, [mid[0], mid[1]]));
		await mapReady(page);
		await statusIn(page);
		await expect.poll(async () => (await features(page, 'trails.paved_paths.treads')).length, { timeout: 60_000 }).toBeGreaterThanOrEqual(1);
		expect((await features(page, 'trails.paved_paths.areas')).length).toBeGreaterThanOrEqual(0);
		const tread = (await features(page, 'trails.paved_paths.treads')).find((f) => f.properties.id === 9101 || f.id === 9101);
		expect(tread?.properties).toMatchObject({ kind: 'cycleway', material: 'asphalt', w: 3 });
		await page.screenshot({ path: screenPath('trails-paved-z17.png') });
		const p = await screenOf(page, mid[0], mid[1]);
		expect(clear(p)).toBe(true);
		await page.mouse.click(p.x, p.y);
		await expect.poll(async () => (await selection(page))?.id).toBe(`way:${IDS.riverside}`);
		await expect(card(page).getByRole('heading', { name: 'Fixture Riverside Path' })).toBeVisible({ timeout: 30_000 });
		await expect(card(page).getByText('Bike path', { exact: true })).toBeVisible();
		// Below z15.5 they are not in the base.
		await page.evaluate(([x, y]) => (globalThis as any).__tvt.map.jumpTo({ center: [x, y], zoom: 15.2 }), mid);
		await mapReady(page);
		expect(await features(page, 'trails.paved_paths.treads')).toEqual([]);

		// Trails off: the same treads draw, and a click on one selects nothing.
		await page.goto(at(17, [mid[0], mid[1]], 'none'));
		await mapReady(page);
		await expect.poll(async () => (await features(page, 'trails.paved_paths.treads')).length, { timeout: 60_000 }).toBeGreaterThanOrEqual(1);
		const q = await screenOf(page, mid[0], mid[1]);
		await page.mouse.click(q.x, q.y);
		await page.waitForTimeout(800);
		expect(await selection(page)).toBeNull();
	});

	test('records the z13 foothills view: the trails tiles’ bytes and frame times (150 KB gzip at most for the busiest tile)', { tag: '@trails' }, async ({ page }) => {
		test.setTimeout(300_000);
		const net = await recordNetwork(page);
		await page.goto(at(13, FOOTHILLS));
		await mapReady(page);
		await statusIn(page);
		await net.settle();
		const tiles = net.entries.filter((x) => x.url.includes('/api/trails/tiles/') && !x.failed);
		expect(tiles.length, 'the view asked for trails tiles').toBeGreaterThan(0);
		const byLayer: Record<string, { tiles: number; bytes: number; largest: number }> = {};
		for (const t of tiles) {
			const layer = t.url.match(/\/tiles\/([a-z]+)\//)![1];
			const b = (byLayer[layer] ??= { tiles: 0, bytes: 0, largest: 0 });
			b.tiles++;
			b.bytes += t.bytes;
			b.largest = Math.max(b.largest, t.bytes);
		}
		const status = net.entries.filter((x) => x.url.includes('/api/trails/status'));
		// Frame times while the view pans for 6 s.
		await page.evaluate(() => {
			const map = (globalThis as any).__tvt.map;
			(globalThis as any).__trailsFrames = [];
			(globalThis as any).__trailsOn = () => (globalThis as any).__trailsFrames.push(performance.now());
			map.on('render', (globalThis as any).__trailsOn);
			const c = map.getCenter();
			map.easeTo({ center: [c.lng + 0.012, c.lat + 0.004], duration: 6000 });
		});
		await page.waitForTimeout(6500);
		const t = await page.evaluate(() => {
			(globalThis as any).__tvt.map.off('render', (globalThis as any).__trailsOn);
			return (globalThis as any).__trailsFrames as number[];
		});
		const gaps = t.slice(1).map((x, i) => x - t[i]).sort((a, b) => a - b);
		const q = (p: number) => (gaps.length ? gaps[Math.min(gaps.length - 1, Math.floor(p * gaps.length))] : null);
		const record = {
			at: new Date().toISOString(),
			view: 'z13 over the made-up foothills trails (trails-seed.ts)',
			tiles: byLayer,
			tilesBytes: Object.values(byLayer).reduce((s, b) => s + b.bytes, 0),
			largestTile: Math.max(...Object.values(byLayer).map((b) => b.largest)),
			statusRequests: status.length,
			frames: { count: t.length, p50Ms: q(0.5), p95Ms: q(0.95), maxMs: gaps.at(-1) ?? null },
			note: 'SwiftShader on the laptop, with the seed’s few trails: the frame times say little; the tile bytes are the seed’s. The real foothills’ numbers are measured on the scratch database (PR).'
		};
		const dir = join(process.env.TVT_MAIN!, 'data', 'dev', env().wp || 'local');
		mkdirSync(dir, { recursive: true });
		writeFileSync(join(dir, 'trails-perf.json'), JSON.stringify(record, null, 2));
		await test.info().attach('trails-perf.json', { body: JSON.stringify(record, null, 2), contentType: 'application/json' });
		console.log(`trails z13: ${tiles.length} tiles, ${MB(record.tilesBytes)} MB (largest ${record.largestTile} B); frames ${t.length}, p50 ${q(0.5)?.toFixed(1)} ms, p95 ${q(0.95)?.toFixed(1)} ms`);
		test.info().annotations.push({ type: 'trails z13', description: `${tiles.length} tiles ${record.tilesBytes} B, largest ${record.largestTile} B; frame p95 ${q(0.95)?.toFixed(1)} ms` });
		// The owner's budget (#32 Q1): the busiest tile of any zoom band is at most 150 KB gzip.
		expect(record.largestTile).toBeLessThanOrEqual(150_000);
		await net.detach();
	});
});
