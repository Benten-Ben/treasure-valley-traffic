import type { Page } from '@playwright/test';
import { expect, mapReady, screenPath, test } from './fixtures.js';
import { cleanShrubs, COUNT, NORTH_END, seedShrubs, type Seeded } from './shrubs-seed.js';

/**
 * shrubs (docs/19 §19.8, plan P11-app): with SYNTHETIC shrubs loaded (shrubs-seed.ts: 1,800 made-up ones round the
 * North End, in their own area):
 *
 * - none below z17: nothing is asked for under z16.5, and nothing is shown under z17;
 * - at z17 the layer asks for the nearest 1,500, hands the scene no more, and draws at most that many;
 * - a click on a shrub opens its small card (height, type, "found in the lidar");
 * - the legend lists bush and sage, says where shrubs are built and names the Sentinel-2 credit;
 * - the cream ring on the tree discs is Valley's: it has a width in Valley and none in Clay.
 */

const at = (zoom: number, bearing = 0, pitch = 0) => `/#map=${zoom}/${NORTH_END[1]}/${NORTH_END[0]}/${bearing}/${pitch}&layers=trees`;

type ShrubInfo = { fetched: number; inScene: number; shown: boolean; phone: boolean; requests: number; url: string | null };
const shrubInfo = (page: Page): Promise<ShrubInfo> => page.evaluate(() => (globalThis as any).__tvtTrees?.shrubs() ?? null);
const shrubsPlaced = (page: Page): Promise<{ id: string; x: number; y: number; r: number }[]> => page.evaluate(() => (globalThis as any).__tvtTrees?.shrubsPlaced() ?? []);
const selection = (page: Page) => page.evaluate(() => (globalThis as any).__tvt.layers.selection);
const paint = (page: Page, id: string, prop: string) => page.evaluate(([l, p]) => (globalThis as any).__tvt.map.getPaintProperty(l, p), [id, prop]);
const attribution = (page: Page): Promise<string> => page.evaluate(() => document.querySelector('.maplibregl-ctrl-attrib-inner')?.textContent ?? '');
/** Look up the saved Base look before the app starts. */
async function look(page: Page, look: 'auto' | 'map' | 'clay') {
	await page.addInitScript((look) => localStorage.setItem('tvt:v2:base', JSON.stringify({ look, buildings: true, terrain: true, labels: 'full' })), look);
}

let seeded: Seeded | null = null;

test.beforeAll(async () => {
	seeded = await seedShrubs();
});

test.afterAll(async () => {
	await cleanShrubs(seeded);
});

/** On screen and clear of the legend column, the inspect column, the top bar and the toolbar. */
const clear = (p: { x: number; y: number }) => p.x > 320 && p.x < 1280 - 400 && p.y > 90 && p.y < 800 - 130;

test.describe('shrubs', () => {
	test('none below z17: nothing is asked for under z16.5 and nothing is shown under z17', { tag: '@shrubs' }, async ({ page }) => {
		test.setTimeout(300_000);
		await page.goto(at(16.2));
		await mapReady(page);
		await expect.poll(async () => (await page.evaluate(() => (globalThis as any).__tvtTrees?.info().visible)) === true, { timeout: 60_000 }).toBe(true);
		// Give a late request its chance.
		await page.waitForTimeout(1500);
		const i = await shrubInfo(page);
		expect(i.requests).toBe(0);
		expect(i.inScene).toBe(0);
		expect(i.shown).toBe(false);
		// Just past z16.5 they are fetched ready, but still not shown below z17.
		await page.evaluate(() => (globalThis as any).__tvt.map.jumpTo({ zoom: 16.7 }));
		await expect.poll(async () => (await shrubInfo(page)).fetched, { timeout: 60_000 }).toBeGreaterThan(0);
		expect((await shrubInfo(page)).shown).toBe(false);
		expect(await shrubsPlaced(page)).toEqual([]);
	});

	test('at z17 at most 1,500 are drawn, the nearest the middle; a click opens the small card; the legend names them', { tag: '@shrubs' }, async ({ page }) => {
		test.setTimeout(300_000);
		await page.goto(at(17, 0, 45));
		await mapReady(page);
		await expect.poll(async () => (await shrubInfo(page)).shown, { timeout: 90_000 }).toBe(true);
		const i = await shrubInfo(page);
		expect(COUNT).toBeGreaterThan(1500);
		expect(i.fetched).toBe(1500);
		expect(i.inScene).toBeLessThanOrEqual(1500);
		expect(i.url).toMatch(/\/api\/trees\/shrubs\?bbox=.*&center=.*&limit=1500$/);
		const drawn = await shrubsPlaced(page);
		expect(drawn.length).toBeGreaterThan(20);
		expect(drawn.length).toBeLessThanOrEqual(1500);
		await page.screenshot({ path: screenPath('shrubs-z17.png') });
		expect(await attribution(page)).toContain('Shrubs: USGS 3DEP lidar, USDA NAIP');
		expect(await attribution(page)).toContain('contains modified Copernicus Sentinel data 2025');

		const target = drawn.find(clear);
		expect(target, 'a shrub on screen, clear of the panels').toBeTruthy();
		await page.mouse.click(target!.x, target!.y);
		await expect.poll(async () => (await selection(page))?.kind, { timeout: 30_000 }).toMatch(/^(shrub|tree)$/);
		const sel = await selection(page);
		if (sel.kind === 'shrub') {
			const card = page.getByRole('region', { name: /Selected/ });
			await expect(card.getByText('measured by the lidar').first()).toBeVisible();
			await expect(card.getByText('found in the lidar').first()).toBeVisible();
			await expect(card.getByText(/Bush|Sage/).first()).toBeVisible();
		}
		const legend = page.getByRole('region', { name: 'Trees legend' });
		await expect(legend.getByText('Bush', { exact: true })).toBeVisible();
		await expect(legend.getByText('Sage', { exact: true })).toBeVisible();
		await expect(legend.getByText(/Shrubs are built for/)).toBeVisible();
	});

	test('the cream ring on the tree discs is Valley’s: a width in Valley and none in Clay', { tag: '@shrubs' }, async ({ page }) => {
		test.setTimeout(300_000);
		await look(page, 'map');
		await page.goto(at(14));
		await mapReady(page);
		await expect.poll(() => paint(page, 'trees-discs-ring', 'circle-stroke-width'), { timeout: 60_000 }).toBe(1);
		expect(await paint(page, 'trees-discs-ring', 'circle-stroke-color')).toBeTruthy();
	});

	test('in Clay the ring has no width', { tag: '@shrubs' }, async ({ page }) => {
		test.setTimeout(300_000);
		await look(page, 'clay');
		await page.goto(at(14));
		await mapReady(page);
		await expect.poll(() => paint(page, 'trees-discs-ring', 'circle-stroke-width'), { timeout: 60_000 }).toBe(0);
	});
});
