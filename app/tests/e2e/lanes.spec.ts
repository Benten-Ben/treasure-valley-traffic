import type { Page } from '@playwright/test';
import { expect, mapReady, screenPath, test } from './fixtures.js';
import { cleanLanes, NAMES, seedLanes, type Seeded } from './lanes-seed.js';

/**
 * lanes (landscape sprint plan v3 §4.2 P9): the Lanes layer (key 8) on the synthetic landscape fixture
 * (`TILES_DIR=$(node scripts/tiles-fixture.mjs --ground painted)`: two crossing streets, markings, arrows, one street
 * flagged where the sources disagree) and synthetic rows for the card API (lanes-seed.ts):
 *
 *   TILES_DIR=$(node scripts/tiles-fixture.mjs --ground painted) npm run test:e2e -- --grep @lanes
 *
 * - key 8 toggles the layer; Auto stays Valley with it on, and goes Clay with Streets;
 * - the base markings show in Clay only with Lanes on (and stay under Aerial with it);
 * - the ▲ marks and the turn arrows come and go with it, and their images are in the style;
 * - a click on a road surface opens the card with both lane counts, each with its source, and nothing opens with
 *   Lanes off.
 */

const CENTRE: [number, number] = [-116.2, 43.615];
/** On the south arm of the flagged street (fixture surface 2003), clear of the junction. */
const STREET: [number, number] = [-116.2, 43.6136];
const at = (zoom: number, layers = 'none') => `/#map=${zoom}/${CENTRE[1]}/${CENTRE[0]}/0/0&layers=${layers}`;
const MARKINGS = 'roads.markings.solid';

type Info = { enabled: string[]; flavor: 'valley' | 'clay'; clay: boolean; selection: { kind: string; id: string; layer: string; title: string } | null };
const info = (page: Page): Promise<Info> => page.evaluate(() => (globalThis as any).__tvt.layers);
const lanes = (page: Page) => page.evaluate(() => (globalThis as any).__tvtLanes?.info() ?? null);
const layerOn = (page: Page, id: string) =>
	page.evaluate((id) => {
		const map = (globalThis as any).__tvt.map;
		return !!map.getLayer(id) && map.getLayoutProperty(id, 'visibility') !== 'none';
	}, id);
const rendered = (page: Page, layers: string[]) =>
	page.evaluate((layers) => (globalThis as any).__tvt.map.queryRenderedFeatures({ layers: layers.filter((l) => (globalThis as any).__tvt.map.getLayer(l)) }).length as number, layers);
const look = (page: Page, look: 'auto' | 'map' | 'clay') =>
	page.addInitScript((look) => localStorage.setItem('tvt:v2:base', JSON.stringify({ look, buildings: true, terrain: true, labels: 'full' })), look);

async function ready(page: Page, hash: string) {
	await page.goto(hash);
	await mapReady(page);
	await expect.poll(() => lanes(page).then((l) => l?.roads), { message: 'the Lanes module is mounted over the fixture’s roads', timeout: 60_000 }).toBe(true);
}

let seeded: Seeded | null = null;

test.beforeAll(async () => {
	seeded = await seedLanes();
});

test.afterAll(async () => {
	await cleanLanes(seeded);
});

test.describe('lanes', () => {
	test('key 8 toggles Lanes; Auto stays Valley with it and goes Clay with Streets', { tag: '@lanes' }, async ({ page, consoleErrors }) => {
		test.setTimeout(300_000);
		await look(page, 'auto');
		await ready(page, at(16));
		expect((await info(page)).enabled).toEqual([]);
		await page.keyboard.press('Digit8');
		await expect.poll(async () => (await info(page)).enabled).toEqual(['lanes']);
		expect((await lanes(page)).visible).toBe(true);
		expect((await info(page)).flavor).toBe('valley');
		// Nothing of Lanes' own went wrong (the fixture has no basemap or building tiles this far in, which the map reports).
		expect(consoleErrors.filter((e) => /lanes|roads\./i.test(e))).toEqual([]);
		await page.keyboard.press('Digit2');
		await expect.poll(async () => (await info(page)).flavor).toBe('clay');
		await page.keyboard.press('Digit2');
		await expect.poll(async () => (await info(page)).flavor).toBe('valley');
		await page.keyboard.press('Digit8');
		await expect.poll(async () => (await info(page)).enabled).toEqual([]);
		expect((await lanes(page)).visible).toBe(false);
	});

	test('markings show in Clay only with Lanes on, and stay under Aerial with it', { tag: '@lanes' }, async ({ page }) => {
		test.setTimeout(300_000);
		await look(page, 'clay');
		// Lanes is on from the start: a base layer that starts hidden in the style isn't cut into tiles by the browser
		// when it is shown later (a known limit, recorded in the PR), so the drawing is checked with it on at load and the
		// hide and show by the layer's visibility.
		await ready(page, at(17.5, 'lanes'));
		await expect.poll(() => layerOn(page, MARKINGS), { message: 'Clay with Lanes' }).toBe(true);
		await expect.poll(() => rendered(page, [MARKINGS, 'roads.markings.dashed']), { message: 'the markings are drawn in Clay with Lanes', timeout: 60_000 }).toBeGreaterThan(0);
		await page.screenshot({ path: screenPath('lanes-markings-clay.png') });
		// Under Aerial the markings stay with Lanes on.
		await page.getByRole('toolbar', { name: 'Map layers' }).getByRole('button', { name: 'Base' }).click();
		const pop = page.getByRole('dialog', { name: 'Base map' });
		await pop.getByRole('switch', { name: /Aerial photos/ }).check();
		await expect.poll(() => layerOn(page, MARKINGS), { message: 'Aerial with Lanes' }).toBe(true);
		await page.keyboard.press('Escape');
		// Off: they go in Clay, with or without the photo.
		await page.keyboard.press('Digit8');
		await expect.poll(() => layerOn(page, MARKINGS), { message: 'Aerial without Lanes' }).toBe(false);
		await page.getByRole('toolbar', { name: 'Map layers' }).getByRole('button', { name: 'Base' }).click();
		await pop.getByRole('switch', { name: /Aerial photos/ }).uncheck();
		await expect.poll(() => layerOn(page, MARKINGS), { message: 'Clay without Lanes' }).toBe(false);
	});

	test('the ▲ marks and the turn arrows come and go with the layer', { tag: '@lanes' }, async ({ page }) => {
		test.setTimeout(300_000);
		await look(page, 'map');
		await ready(page, at(17.8, 'lanes'));
		const handle = () => page.evaluate(() => ({ layers: (globalThis as any).__tvtLanes.layers(), images: (globalThis as any).__tvtLanes.images() }));
		const got = await handle();
		expect(got.layers).toEqual(['lanes-conflict', 'lanes-arrows']);
		expect(got.images).toEqual(expect.arrayContaining(['lanes-conflict', 'lanes-arrow:L', 'lanes-arrow:T', 'lanes-arrow:R', 'lanes-arrow:LT', 'lanes-arrow:LTRU', 'lanes-arrow:']));
		await expect.poll(() => rendered(page, ['lanes-conflict']), { message: 'a ▲ on the flagged street', timeout: 60_000 }).toBeGreaterThan(0);
		await expect.poll(() => rendered(page, ['lanes-arrows']), { message: 'the fixture’s turn arrows', timeout: 60_000 }).toBeGreaterThan(0);
		await page.screenshot({ path: screenPath('lanes-marks-valley.png') });
		await page.keyboard.press('Digit8');
		await expect.poll(() => layerOn(page, 'lanes-conflict')).toBe(false);
		expect(await layerOn(page, 'lanes-arrows')).toBe(false);
		// The arrows come in from z17.5: not at z17.
		await page.keyboard.press('Digit8');
		await page.evaluate(() => (globalThis as any).__tvt.map.jumpTo({ zoom: 17, center: [-116.2, 43.615], bearing: 0, pitch: 0 }));
		await mapReady(page);
		expect(await rendered(page, ['lanes-arrows'])).toBe(0);
	});

	test('a click on a road opens the card with both lane counts, and nothing opens with Lanes off', { tag: '@lanes' }, async ({ page }) => {
		test.setTimeout(300_000);
		await look(page, 'map');
		// Centred on the street, so the click lands clear of the toolbar and the legend.
		await ready(page, `/#map=17/${STREET[1]}/${STREET[0]}/0/0&layers=none`);
		await expect.poll(() => rendered(page, ['roads.surfaces.z16.asphalt']), { timeout: 60_000 }).toBeGreaterThan(0);
		const point = () =>
			page.evaluate((p) => {
				const pt = (globalThis as any).__tvt.map.project(p);
				return { x: pt.x, y: pt.y };
			}, STREET);
		// Lanes is loaded only once it has been on; turn it on and off again, then click with it off.
		await page.keyboard.press('Digit8');
		await expect.poll(async () => (await info(page)).enabled).toEqual(['lanes']);
		await page.keyboard.press('Digit8');
		await expect.poll(async () => (await lanes(page))?.visible).toBe(false);
		let spot = await point();
		await page.mouse.click(spot.x, spot.y);
		await page.waitForTimeout(500);
		expect((await info(page)).selection).toBeNull();
		await page.keyboard.press('Digit8');
		await expect.poll(async () => (await lanes(page))?.visible).toBe(true);
		spot = await point();
		await page.mouse.click(spot.x, spot.y);
		await expect.poll(async () => (await info(page)).selection?.layer, { timeout: 30_000 }).toBe('lanes');
		const sel = (await info(page)).selection!;
		expect(sel.kind).toBe('lane');
		// The surface and the centre line belong to the same piece: either opens its card.
		expect(['surface-2003', 'marking-4003']).toContain(sel.id);
		const card = page.locator('section.inspect');
		await expect(card).toContainText(NAMES.street, { timeout: 30_000 });
		await expect(card).toContainText('Residential street');
		await expect(card).toContainText('OpenStreetMap: 5 lanes (3 and 2)');
		await expect(card).toContainText('ACHD rule (Master Street Map): 2 lanes (1 and 1)');
		await expect(card).toContainText('The sources disagree on the lanes');
		await expect(card).toContainText('estimated');
		await expect(card).toContainText('internal: shown on this map only');
		await page.screenshot({ path: screenPath('lanes-card.png') });
		await page.keyboard.press('Escape');
		await expect.poll(async () => (await info(page)).selection).toBeNull();
	});
});
