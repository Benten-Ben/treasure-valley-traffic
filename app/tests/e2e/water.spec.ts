import type { Page } from '@playwright/test';
import { expect, mapReady, screenPath, test } from './fixtures.js';
import { cleanWater, GAUGE, NHD_ONLY_ID, SERVICE_AREAS, seedWater, type Seeded } from './water-seed.js';

/**
 * water (landscape sprint plan v3 §4.2 P4-app): the baked water network and the Water layer, on the synthetic
 * landscape fixture (`TILES_DIR=$(node scripts/tiles-fixture.mjs --ground painted)`: a main canal, a lateral, a
 * ditch, a piped lateral, an NHD-only stream, an intermittent gulch and a pond, all made up) and synthetic rows
 * for the APIs (water-seed.ts). It checks the bake's contract in the browser:
 *
 * - dotted source-layer names (`water.reaches`) read, `promoteId` and feature-state work in MapLibre;
 * - the base draws in Valley and in Clay; Protomaps' water is hidden once the network is built and stays when
 *   the manifest lists a water layer under `empty`;
 * - no water layer has a casing, and the only `line-gap-width` is the canal season's, on the solid reach layer;
 * - Auto stays Valley with Water on, and goes Clay with a layer that doesn't keep Valley;
 * - the Water layer's badges, italic names and picked shape come and go with it;
 * - a click on the canal opens its card (its gauge, its irrigation service areas, nothing said about who runs it).
 */

const FIXTURE_TILES = 'landscape fixture';
/** A view over the fixture's pond, lateral and ditch (z14 shows laterals, ditches and the pond). */
const NEAR = '#map=14/43.612/-116.2/0/0';
const FAR = '#map=11/43.605/-116.24/0/0';
/** A view with the gauge, the dam, the hazard and the E. coli site all in it. */
const BADGES = '#map=12/43.606/-116.24/0/0';
/** The canal's vertex east of the lateral. */
const CANAL_POINT: [number, number] = [-116.19, 43.608];

const BASE_LAYERS = ['water.network.bodies', 'water.network.reaches', 'water.network.reaches-intermittent', 'water.network.reaches-nhd', 'water.network.reaches-nhd-intermittent', 'water.network.reaches-piped'];
const PROTOMAPS_WATER = ['water', 'water_stream', 'water_river'];
const PROTOMAPS_WATER_LABELS = ['water_waterway_label', 'water_label_lakes'];

type Info = { enabled: string[]; flavor: 'valley' | 'clay'; clay: boolean; status: Record<string, string>; selection: { kind: string; id: string; layer: string; title: string } | null };
const info = (page: Page): Promise<Info> => page.evaluate(() => (globalThis as any).__tvt.layers);
const vis = (page: Page, id: string) => page.evaluate((id) => (globalThis as any).__tvt.map.getLayoutProperty(id, 'visibility') ?? 'visible', id);
const hasLayer = (page: Page, id: string) => page.evaluate((id) => Boolean((globalThis as any).__tvt.map.getLayer(id)), id);
const paint = (page: Page, id: string, prop: string) => page.evaluate(([l, p]) => (globalThis as any).__tvt.map.getPaintProperty(l, p), [id, prop]);
const water = (page: Page) => page.evaluate(() => (globalThis as any).__tvtWater?.info() ?? null);

/** Look up the saved Base look before the app starts. */
async function look(page: Page, look: 'auto' | 'map' | 'clay') {
	await page.addInitScript((look) => localStorage.setItem('tvt:v2:base', JSON.stringify({ look, buildings: true, terrain: true, labels: 'full' })), look);
}

/** The map is up with the baked water drawn (the fixture's lines are in view). */
async function ready(page: Page, hash: string) {
	await page.goto(`/${hash}`);
	await mapReady(page);
	await expect.poll(() => hasLayer(page, 'water.network.reaches'), { message: `the baked water is in the style (${FIXTURE_TILES})`, timeout: 30_000 }).toBe(true);
}

/** Rendered features of the baked layers in view. */
const rendered = (page: Page, layers: string[]) =>
	page.evaluate((layers) => (globalThis as any).__tvt.map.queryRenderedFeatures({ layers: layers.filter((l) => (globalThis as any).__tvt.map.getLayer(l)) }).map((f: any) => ({ layer: f.layer.id, id: f.properties.id, name: f.properties.name })), layers);

let seeded: Seeded | null = null;

test.beforeAll(async () => {
	seeded = await seedWater();
});

test.afterAll(async () => {
	await cleanWater(seeded);
});

test.describe('water: the baked network', () => {
	test('reads the dotted source-layers, with promoteId and feature-state working', { tag: '@water' }, async ({ page, consoleErrors, offsite }) => {
		test.setTimeout(300_000);
		await ready(page, `${NEAR}&layers=none`);
		await expect.poll(async () => (await rendered(page, BASE_LAYERS)).length, { timeout: 60_000 }).toBeGreaterThan(0);
		const got = await page.evaluate(async () => {
			const map = (globalThis as any).__tvt.map;
			const reaches = map.querySourceFeatures('landscape', { sourceLayer: 'water.reaches' });
			const bodies = map.querySourceFeatures('landscape', { sourceLayer: 'water.bodies' });
			// promoteId: the feature id is the `id` field, so feature-state keys work.
			const withId = reaches.filter((f: any) => f.id === f.properties.id);
			const target = { source: 'landscape', sourceLayer: 'water.reaches', id: 7001 };
			map.setFeatureState(target, { season: 'on' });
			const state = map.getFeatureState(target);
			map.removeFeatureState(target);
			return { reaches: reaches.length, bodies: bodies.length, promoted: withId.length, state, fields: Object.keys(reaches[0]?.properties ?? {}).sort() };
		});
		expect(got.reaches).toBeGreaterThan(0);
		expect(got.bodies).toBeGreaterThan(0);
		expect(got.promoted).toBe(got.reaches);
		expect(got.state).toEqual({ season: 'on' });
		expect(got.fields).toEqual(['canal', 'id', 'intermittent', 'kind', 'name', 'nhd_only', 'piped', 'width_m']);
		expect(consoleErrors).toEqual([]);
		expect(offsite).toEqual([]);
	});

	test('draws in Valley and in Clay, and hides Protomaps’ water once built', { tag: '@water' }, async ({ browser, baseURL }) => {
		test.setTimeout(300_000);
		const seen: Record<string, { flavor: string; color: unknown; drawn: number; hidden: string[]; labelsVisible: string[] }> = {};
		for (const flavor of ['map', 'clay'] as const) {
			const ctx = await browser.newContext({ baseURL: baseURL!, viewport: { width: 1280, height: 800 } });
			const page = await ctx.newPage();
			await look(page, flavor);
			await ready(page, `${NEAR}&layers=none`);
			await expect.poll(async () => (await rendered(page, BASE_LAYERS)).length, { timeout: 60_000 }).toBeGreaterThan(0);
			const f = (await info(page)).flavor;
			expect(f).toBe(flavor === 'map' ? 'valley' : 'clay');
			seen[flavor] = {
				flavor: f,
				color: await paint(page, 'water.network.reaches', 'line-color'),
				drawn: (await rendered(page, BASE_LAYERS)).length,
				hidden: await Promise.all(PROTOMAPS_WATER.map((id) => vis(page, id))),
				labelsVisible: await Promise.all(PROTOMAPS_WATER_LABELS.map((id) => vis(page, id)))
			};
			// All the baked layers are visible in either look, and sit in the water slot, before anchor:water.
			for (const id of BASE_LAYERS) expect(await vis(page, id), `${id} in ${flavor}`).toBe('visible');
			const order: string[] = await page.evaluate(() => (globalThis as any).__tvt.map.getLayersOrder());
			expect(order.indexOf('water.network.bodies')).toBeGreaterThan(order.indexOf('water_river'));
			expect(order.indexOf('water.network.reaches-piped')).toBeLessThan(order.indexOf('anchor:water'));
			expect(order.indexOf('anchor:water')).toBeLessThan(order.indexOf('anchor:surfaces'));
			if (flavor === 'map') await page.screenshot({ path: screenPath('water-base-valley.png') });
			else await page.screenshot({ path: screenPath('water-base-clay.png') });
			await ctx.close();
		}
		expect(seen.map.drawn).toBeGreaterThan(0);
		expect(seen.clay.drawn).toBeGreaterThan(0);
		// The line colour follows the look; the fills are the basemap's own water.
		expect(seen.map.color).toBe('#4a9fcc');
		expect(seen.clay.color).toBe('#7aa3b5');
		for (const s of Object.values(seen)) {
			expect(s.hidden, 'Protomaps’ water fills and lines are hidden').toEqual(['none', 'none', 'none']);
			// With Water off its names stay: the basemap's water labels are only replaced while the layer's draw.
			expect(s.labelsVisible).toEqual(['visible', 'visible']);
		}
	});

	test('leaves Protomaps’ water alone when the manifest lists a water layer under empty', { tag: '@water' }, async ({ page }) => {
		test.setTimeout(300_000);
		// This one test rewrites the manifest (routing turns the HTTP cache off, which only costs time here).
		await page.route('**/tiles/manifest.json', async (route) => {
			const res = await route.fetch();
			const m = await res.json();
			const entry = m.landscape;
			if (entry?.status === 'baked') {
				delete entry.layers['water.reaches'];
				entry.empty = [...entry.empty, 'water.reaches'];
			}
			await route.fulfill({ response: res, json: m });
		});
		await page.goto(`/${NEAR}&layers=water`);
		await mapReady(page);
		await expect.poll(async () => (await water(page))?.visible, { timeout: 60_000 }).toBe(true);
		expect(await water(page)).toMatchObject({ baked: false });
		for (const id of BASE_LAYERS) expect(await hasLayer(page, id), `${id} is not built`).toBe(false);
		for (const id of [...PROTOMAPS_WATER, ...PROTOMAPS_WATER_LABELS]) expect(await vis(page, id), id).toBe('visible');
		// The badges still draw, and the legend says what isn't built.
		expect((await water(page)).gauges).toBeGreaterThan(0);
		await expect(page.locator('[data-not-baked]')).toContainText('isn’t baked into the map yet');
	});

	test('has no casing on any water layer (K5), and no symbol below anchor:routes', { tag: '@water' }, async ({ page }) => {
		test.setTimeout(300_000);
		await ready(page, `${NEAR}&layers=water`);
		await expect.poll(async () => (await water(page))?.visible, { timeout: 60_000 }).toBe(true);
		const layers = await page.evaluate(() => (globalThis as any).__tvt.map.getStyle().layers.map((l: any) => ({ id: l.id, type: l.type, source: l.source, sourceLayer: l['source-layer'], paint: l.paint ?? {}, filter: l.filter ?? null })));
		const mine = layers.filter((l: any) => l.id.startsWith('water.network.') || l.id.startsWith('water-'));
		expect(mine.length).toBeGreaterThan(BASE_LAYERS.length);
		for (const l of mine) {
			expect(l.id, l.id).not.toMatch(/casing|outline|halo/i);
			expect(Object.keys(l.paint), l.id).not.toContain('line-offset');
			// The only gap is the canal season's hollow, on the solid reach layer: 0 unless the feature-state `season` is `off`
			// (P5-app, season.ts); the water tone never changes with it. A dashed layer never has one.
			if (l.id === 'water.network.reaches') expect(JSON.stringify(l.paint['line-gap-width']), l.id).toContain('feature-state');
			else expect(Object.keys(l.paint), l.id).not.toContain('line-gap-width');
		}
		// No two line layers draw the same features one under the other (a casing is exactly that).
		const lines = layers.filter((l: any) => l.id.startsWith('water.network.') && l.type === 'line');
		const keys = lines.map((l: any) => JSON.stringify([l.sourceLayer, l.filter]));
		expect(new Set(keys).size).toBe(keys.length);
		// Symbols only above anchor:routes.
		const ids: string[] = layers.map((l: any) => l.id);
		for (const l of layers) {
			if (l.id.startsWith('water-') && ['symbol', 'circle'].includes(l.type)) expect(ids.indexOf(l.id), l.id).toBeGreaterThan(ids.indexOf('anchor:routes'));
		}
	});

	test('stays Valley in Auto with Water on, and goes Clay with a layer that does not keep Valley', { tag: '@water' }, async ({ page }) => {
		test.setTimeout(300_000);
		await ready(page, `${NEAR}&layers=water`);
		await expect.poll(async () => (await info(page)).enabled).toEqual(['water']);
		expect((await info(page)).flavor).toBe('valley');
		await page.goto(`/${NEAR}&layers=water,cameras`);
		await mapReady(page);
		await expect.poll(async () => (await info(page)).flavor).toBe('clay');
	});
});

test.describe('water: the layer', () => {
	test('draws its badges, italic names and picked shape only while on', { tag: '@water' }, async ({ page, consoleErrors }) => {
		test.setTimeout(300_000);
		await ready(page, `${FAR}&layers=none`);
		await expect.poll(async () => (await info(page)).status.water, { timeout: 60_000 }).toBe('ready');
		// Loaded but off: everything the layer added is hidden, and the basemap's names show.
		const handle = await water(page);
		expect(handle).toMatchObject({ visible: false, baked: true, gauges: 1, structures: 1, hazards: 1, ecoli: 1 });
		expect(handle.images.sort()).toEqual(['water-ecoli', 'water-gauge', 'water-gauge-flood', 'water-hazard', 'water-structure']);
		for (const id of ['water-gauges', 'water-structures', 'water-notices', 'water-labels-main']) expect(await vis(page, id), id).toBe('none');
		for (const id of PROTOMAPS_WATER_LABELS) expect(await vis(page, id), id).toBe('visible');
		// Turn it on: the hash is the layer set.
		await page.goto(`/${BADGES}&layers=water`);
		await mapReady(page);
		await expect.poll(async () => (await water(page))?.visible, { timeout: 60_000 }).toBe(true);
		for (const id of ['water-gauges', 'water-structures', 'water-notices', 'water-labels-main', 'water-labels-bodies']) expect(await vis(page, id), id).toBe('visible');
		// The baked italic names replace the basemap's water names while they draw.
		for (const id of PROTOMAPS_WATER_LABELS) expect(await vis(page, id), id).toBe('none');
		const fonts = await page.evaluate(() => (globalThis as any).__tvt.map.getLayoutProperty('water-labels-main', 'text-font'));
		expect(fonts).toEqual(['Noto Sans Italic']);
		// The hazard and the E. coli site draw in the notice layer, the gauge and the dam in theirs.
		await expect
			.poll(
				async () =>
					page.evaluate(() => {
						const map = (globalThis as any).__tvt.map;
						return ['water-gauges', 'water-structures', 'water-notices'].map((l) => map.queryRenderedFeatures({ layers: [l] }).length > 0);
					}),
				{ timeout: 60_000 }
			)
			.toEqual([true, true, true]);
		await page.screenshot({ path: screenPath('water-layer.png') });
		expect(consoleErrors).toEqual([]);
	});

	test('opens the canal’s card on a click: its gauge, the service areas it runs through, nothing about who runs it', { tag: '@water' }, async ({ page }) => {
		test.setTimeout(300_000);
		await ready(page, `#map=14/${CANAL_POINT[1]}/${CANAL_POINT[0]}/0/0&layers=water`);
		await expect.poll(async () => (await water(page))?.visible, { timeout: 60_000 }).toBe(true);
		await expect.poll(async () => (await rendered(page, ['water.network.reaches'])).some((f: { id: number }) => f.id === 7001), { timeout: 60_000 }).toBe(true);
		const at = await page.evaluate((p) => {
			const pt = (globalThis as any).__tvt.map.project(p);
			return { x: pt.x, y: pt.y };
		}, CANAL_POINT);
		// The canal is under the pointer and nothing else of ours is: the click picks it.
		await page.mouse.click(at.x, at.y);
		await expect.poll(async () => (await info(page)).selection?.id, { timeout: 30_000 }).toBe('reach:7001');
		const sel = (await info(page)).selection!;
		expect(sel).toMatchObject({ kind: 'water', layer: 'water', title: 'Fixture Main Canal' });
		const card = page.locator('section.inspect');
		await expect(card).toContainText('Fixture Main Canal');
		await expect(card).toContainText('Main canal');
		await expect(card).toContainText(GAUGE);
		await expect(card).toContainText('Stage 7.33 ft');
		await expect(card).toContainText('Flow 1,660 cfs');
		await expect(card).toContainText('Irrigation service areas it runs through');
		for (const area of SERVICE_AREAS) await expect(card).toContainText(area);
		await expect(card).toContainText('Treasure Valley Irrigation System');
		const text = (await card.innerText()).toLowerCase();
		expect(text).not.toContain('operated by');
		// Estimates say so.
		expect(text).toContain('estimate');
		// The picked canal is drawn wider and darker, as one line.
		expect(await vis(page, 'water-selected-reach')).toBe('visible');
		await page.screenshot({ path: screenPath('water-canal-card.png') });
		// Esc closes the card and puts the picked shape away.
		await page.keyboard.press('Escape');
		await expect.poll(async () => (await info(page)).selection).toBeNull();
		await expect.poll(() => vis(page, 'water-selected-reach')).toBe('none');
	});

	test('opens the pond’s card, and nothing opens with Water off', { tag: '@water' }, async ({ page }) => {
		test.setTimeout(300_000);
		const POND: [number, number] = [-116.1935, 43.6082];
		await ready(page, `#map=15/${POND[1]}/${POND[0]}/0/0&layers=none`);
		await expect.poll(async () => (await rendered(page, ['water.network.bodies'])).some((f: { id: number }) => f.id === 8001), { timeout: 60_000 }).toBe(true);
		const at = await page.evaluate((p) => {
			const pt = (globalThis as any).__tvt.map.project(p);
			return { x: pt.x, y: pt.y };
		}, POND);
		// Water is loaded but off: the baked area is drawn and a click opens nothing.
		await page.mouse.click(at.x, at.y);
		await page.waitForTimeout(500);
		expect((await info(page)).selection).toBeNull();
		await page.goto(`/#map=15/${POND[1]}/${POND[0]}/0/0&layers=water`);
		await mapReady(page);
		await expect.poll(async () => (await water(page))?.visible, { timeout: 60_000 }).toBe(true);
		await expect.poll(async () => (await rendered(page, ['water.network.bodies'])).some((f: { id: number }) => f.id === 8001), { timeout: 60_000 }).toBe(true);
		await page.mouse.click(at.x, at.y);
		await expect.poll(async () => (await info(page)).selection?.id, { timeout: 30_000 }).toBe('body:8001');
		const card = page.locator('section.inspect');
		await expect(card).toContainText('Fixture Pond');
		await expect(card).toContainText('Pond');
		await expect(card).toContainText('acres');
	});

	test('opens an NHD-only stream’s card and says so', { tag: '@water' }, async ({ page }) => {
		test.setTimeout(300_000);
		const P: [number, number] = [-116.19, 43.614];
		await ready(page, `#map=16/${P[1]}/${P[0]}/0/0&layers=water`);
		await expect.poll(async () => (await water(page))?.visible, { timeout: 60_000 }).toBe(true);
		await expect.poll(async () => (await rendered(page, ['water.network.reaches-nhd'])).some((f: { id: number }) => f.id === NHD_ONLY_ID), { timeout: 60_000 }).toBe(true);
		const at = await page.evaluate((p) => {
			const pt = (globalThis as any).__tvt.map.project(p);
			return { x: pt.x, y: pt.y };
		}, P);
		await page.mouse.click(at.x, at.y);
		await expect.poll(async () => (await info(page)).selection?.id, { timeout: 30_000 }).toBe(`reach:${NHD_ONLY_ID}`);
		const card = page.locator('section.inspect');
		await expect(card).toContainText('Unnamed creek or stream');
		await expect(card).toContainText("OpenStreetMap doesn't have this line");
	});
});

test.describe('water: the APIs', () => {
	test('answer from the synthetic rows: reach and canal, body, structure, gauge, points and notices', { tag: '@water' }, async ({ request }) => {
		const reach = await (await request.get('/api/water/reach/7001')).json();
		expect(reach).toMatchObject({ id: 7001, kind: 'canal', name: 'Fixture Main Canal', geometry_from: 'osm' });
		expect(reach.canal).toMatchObject({ name: 'Fixture Main Canal', kind: 'main_canal' });
		expect(reach.canal.service_areas.map((a: { name: string }) => a.name)).toEqual([...SERVICE_AREAS]);
		expect(reach.canal.gauge).toMatchObject({ lid: GAUGE });
		expect(reach.canal.gauge.reading.facts).toEqual([
			{ label: 'Stage', value: 7.33, unit: 'ft' },
			{ label: 'Flow', value: 1660, unit: 'cfs' }
		]);
		expect(JSON.stringify(reach)).not.toMatch(/operated by/i);
		expect(await (await request.get('/api/water/body/8001')).json()).toMatchObject({ kind: 'pond', name: 'Fixture Pond' });
		expect(await (await request.get('/api/water/structure/9001')).json()).toMatchObject({ kind: 'dam', head_of: [{ id: 1, name: 'Fixture Main Canal' }] });
		const gauge = await (await request.get(`/api/water/gauge/${GAUGE.toLowerCase()}`)).json();
		expect(gauge).toMatchObject({ lid: GAUGE, usgs: false, flood: null });
		// NWPS alone for the reading (its record names no USGS site), then the sources of the canal it measures, HydroShare as its licence asks.
		expect(gauge.credit[0]).toContain('National Weather Service');
		expect(gauge.credit.join(' ')).not.toContain('Geological Survey');
		expect(gauge.credit.some((c: string) => c.includes('HydroShare') && c.includes('modified'))).toBe(true);
		const points = await (await request.get('/api/water/points')).json();
		expect(points.gauges.map((g: { lid: string }) => g.lid)).toContain(GAUGE);
		expect(points.structures.map((s: { id: number }) => s.id)).toContain(9001);
		// IDWR's rows are never in the map's points.
		expect(JSON.stringify(points)).not.toContain(SERVICE_AREAS[0]);
		const notices = await (await request.get('/api/water/notices')).json();
		expect(notices.hazards.map((h: { name: string }) => h.name)).toContain('Fixture Fallen Tree');
		expect(notices.ecoli.map((s: { id: string }) => s.id)).toContain('FXPOND1');
		expect(notices.republish).toBe('internal');
	});

	test('answer 404 for an id the build lacks and 400 for a bad one, and revalidate with an ETag', { tag: '@water' }, async ({ request }) => {
		expect((await request.get('/api/water/reach/123456')).status()).toBe(404);
		expect((await request.get('/api/water/body/123456')).status()).toBe(404);
		expect((await request.get('/api/water/structure/123456')).status()).toBe(404);
		expect((await request.get('/api/water/gauge/NOPE9')).status()).toBe(404);
		expect((await request.get('/api/water/reach/abc')).status()).toBe(400);
		expect((await request.get('/api/water/gauge/bad%20id')).status()).toBe(400);
		const first = await request.get('/api/water/points');
		const etag = first.headers().etag;
		expect(etag).toBeTruthy();
		expect(first.headers()['cache-control']).toBe('no-cache');
		expect((await request.get('/api/water/points', { headers: { 'if-none-match': etag } })).status()).toBe(304);
	});
});
