import type { Page } from '@playwright/test';
import { expect, mapReady, screenPath, test } from './fixtures.js';
import { cleanFences, FENCES, NORTH_END, seedFences, VERSION, type Seeded } from './fences-seed.js';

/**
 * fences (plan P10): with a few SYNTHETIC fences and a `fences.lines` version loaded (fences-seed.ts):
 *
 * - /api/fences/lines answers the one versioned GeoJSON, gzipped with an ETag, immutable for the version;
 * - the 2D line (a cream halo under a post-tone line) shows from z14.5 and at z17;
 * - low 3D walls (one static batch) show from z15.5 and not below it;
 * - turning Fences on leaves Auto on the Valley look (a layer that keeps Valley);
 * - a click on a fence opens its card: type, see-through or solid, height tagged or estimated, "mapped (OpenStreetMap)".
 */

const at = (zoom: number, bearing = 0, pitch = 0) => `/#map=${zoom}/${NORTH_END[1]}/${NORTH_END[0]}/${bearing}/${pitch}&layers=fences`;

type Info = { visible: boolean; fences: number; scene: string; segments: number; walls: boolean; phone: boolean };
const info = (page: Page): Promise<Info> => page.evaluate(() => (globalThis as any).__tvtFences?.info() ?? null);
const points = (page: Page): Promise<{ id: string; x: number; y: number }[]> => page.evaluate(() => (globalThis as any).__tvtFences?.points() ?? []);
const staticSegments = (page: Page): Promise<number> => page.evaluate(() => (globalThis as any).__tvtFences?.sceneStats()?.staticSegments ?? 0);
const selection = (page: Page) => page.evaluate(() => (globalThis as any).__tvt.layers.selection);
const flavor = (page: Page): Promise<string> => page.evaluate(() => (globalThis as any).__tvt.layers.flavor);
/** Fence ids the map draws in its 2D line now. */
const drawn = (page: Page): Promise<string[]> =>
	page.evaluate(() => [...new Set((globalThis as any).__tvt.map.queryRenderedFeatures({ layers: ['fences-line'] }).map((f: any) => f.properties.id))] as string[]);
const attribution = (page: Page): Promise<string> => page.evaluate(() => document.querySelector('.maplibregl-ctrl-attrib-inner')?.textContent ?? '');

/** Console errors with their messages. */
async function keepErrors(page: Page) {
	await page.addInitScript(() => {
		const w = globalThis as any;
		w.__errors = [];
		const orig = console.error.bind(console);
		console.error = (...a: unknown[]) => {
			w.__errors.push(a.map((x) => (x instanceof Error ? `${x.name}: ${x.message}` : String(x))).join(' '));
			orig(...a);
		};
	});
}
const errorsOf = (page: Page): Promise<string[]> => page.evaluate(() => (globalThis as any).__errors ?? []);

let seeded: Seeded | null = null;

test.beforeAll(async () => {
	seeded = await seedFences();
});

test.afterAll(async () => {
	await cleanFences(seeded);
});

/** On screen and clear of the legend column, the inspect column, the top bar and the toolbar. */
const clear = (p: { x: number; y: number }) => p.x > 320 && p.x < 1280 - 400 && p.y > 90 && p.y < 800 - 130;

test.describe('fences', () => {
	test('the route answers the one versioned GeoJSON: gzipped, an ETag, immutable for the version', { tag: '@fences' }, async ({ request }) => {
		const url = `/api/fences/lines?v=${VERSION}`;
		const res = await request.get(url);
		expect(res.status()).toBe(200);
		expect(res.headers()['cache-control']).toContain('immutable');
		expect(res.headers()['content-type']).toContain('application/geo+json');
		const etag = res.headers()['etag'];
		expect(etag).toContain(VERSION);
		const body = await res.json();
		const mine = body.features.filter((f: any) => FENCES.some((s) => s.id === f.properties.id));
		expect(mine).toHaveLength(FENCES.length);
		expect(mine.find((f: any) => f.properties.id === 'osm:w9900002').properties).toMatchObject({ type: 'wall', look: 'solid', h: 2.4, hs: 'tagged', m: 'brick' });
		expect((await request.get(url, { headers: { 'if-none-match': etag } })).status()).toBe(304);
		const old = await request.get('/api/fences/lines?v=old');
		expect(old.headers()['cache-control']).toBe('no-cache');
	});

	test('the 2D line shows from z14.5 and at z17, and the 3D walls from z15.5', { tag: '@fences' }, async ({ page }) => {
		test.setTimeout(300_000);
		await keepErrors(page);
		await page.goto(at(14.4));
		await mapReady(page);
		await expect.poll(async () => (await info(page))?.fences ?? 0, { timeout: 60_000 }).toBeGreaterThanOrEqual(FENCES.length);
		// Below z14.5 nothing of it is drawn.
		expect(await drawn(page)).toEqual([]);
		await page.evaluate(() => (globalThis as any).__tvt.map.jumpTo({ zoom: 14.6 }));
		await mapReady(page);
		await expect.poll(async () => (await drawn(page)).length).toBeGreaterThan(0);
		let i = await info(page);
		expect(i.walls, 'no 3D walls at z14.6').toBe(false);
		await page.screenshot({ path: screenPath('fences-2d-z14.6.png') });
		expect(await attribution(page)).toContain('OpenStreetMap');

		// z15.3: still the line alone.
		await page.evaluate(() => (globalThis as any).__tvt.map.jumpTo({ zoom: 15.3 }));
		await mapReady(page);
		expect((await info(page)).walls).toBe(false);

		// z17: the line, and the walls in one static batch.
		await page.evaluate(() => (globalThis as any).__tvt.map.jumpTo({ zoom: 17, pitch: 50, bearing: -12 }));
		await mapReady(page);
		await expect.poll(async () => (await info(page))?.walls, { timeout: 90_000 }).toBe(true);
		await expect.poll(async () => (await info(page)).segments).toBeGreaterThanOrEqual(FENCES.length * 2);
		await expect.poll(() => staticSegments(page), { timeout: 60_000 }).toBeGreaterThan(0);
		expect((await drawn(page)).length).toBeGreaterThan(0);
		await page.screenshot({ path: screenPath('fences-3d-z17.png') });

		// And back below z15.5 the walls go.
		await page.evaluate(() => (globalThis as any).__tvt.map.jumpTo({ zoom: 15.2, pitch: 0, bearing: 0 }));
		await mapReady(page);
		await expect.poll(async () => (await info(page)).walls).toBe(false);
		expect(await errorsOf(page)).toEqual([]);
	});

	test('Auto stays Valley while Fences is on', { tag: '@fences' }, async ({ page }) => {
		test.setTimeout(240_000);
		await page.goto(at(16));
		await mapReady(page);
		await expect.poll(async () => (await info(page))?.visible).toBe(true);
		expect(await flavor(page)).toBe('valley');
	});

	test('a click on a fence opens its card', { tag: '@fences' }, async ({ page }) => {
		test.setTimeout(300_000);
		await keepErrors(page);
		await page.goto(at(17));
		await mapReady(page);
		await expect.poll(async () => (await drawn(page)).length, { timeout: 60_000 }).toBeGreaterThan(0);
		const wall = (await points(page)).find((p) => p.id === 'osm:w9900002');
		expect(wall && clear(wall), 'the synthetic wall is on screen, clear of the panels').toBeTruthy();
		await page.mouse.click(wall!.x, wall!.y);
		await expect.poll(async () => (await selection(page))?.kind).toBe('fence');
		const sel = await selection(page);
		expect(sel).toMatchObject({ layer: 'fences', id: 'osm:w9900002' });
		const card = page.getByRole('region', { name: 'Selected' });
		await expect(card).toBeVisible();
		await expect(card.getByRole('heading', { name: 'Wall' })).toBeVisible();
		await expect(card.getByText('Solid', { exact: true }).first()).toBeVisible();
		await expect(card.getByText('brick', { exact: true })).toBeVisible();
		await expect(card.getByText('tagged in OpenStreetMap')).toBeVisible();
		await expect(card.getByText('mapped (OpenStreetMap)')).toBeVisible();
		await page.screenshot({ path: screenPath('fences-card-z17.png') });

		// An estimated height says so, on the see-through fence.
		const fence = (await points(page)).find((p) => p.id === 'osm:w9900001');
		expect(fence && clear(fence)).toBeTruthy();
		await page.mouse.click(fence!.x, fence!.y);
		await expect.poll(async () => (await selection(page))?.id).toBe('osm:w9900001');
		await expect(card.getByText('estimated from its type')).toBeVisible();
		await expect(card.getByText('See-through', { exact: true }).first()).toBeVisible();
		const legend = page.getByRole('region', { name: 'Fences legend' });
		await expect(legend.getByText("Mapped in OpenStreetMap; most backyard fences aren't mapped yet.")).toBeVisible();
		expect(await errorsOf(page)).toEqual([]);
	});
});
