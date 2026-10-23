import type { Page } from '@playwright/test';
import { expect, mapReady, test } from './fixtures.js';

/**
 * The painted ground (landscape plan v3 §4.2 G1a; basemap/ground/README.md, "Switching in"), on the
 * synthetic ground fixture:
 *
 *   TILES_DIR=$(node scripts/tiles-fixture.mjs --ground painted) npm run test:e2e -- --grep @ground
 *   TILES_DIR=$(node scripts/tiles-fixture.mjs --ground flat)    npm run test:e2e -- --grep @ground
 *
 * With a painted ground: Valley draws it and hides the landcover fills; a Clay first visit makes no
 * ground request and keeps its fills; the ground loads when Valley is first used; Aerial hides it.
 * With a flat one: no ground source exists and the fills stay. The tests that don't fit the manifest in
 * TILES_DIR skip, so each run covers one of the two cases.
 *
 * The Base popover has no row for a contribution yet (S3b draws them). The row's text is
 * `contributionStatus(...).reason`, which the unit test (src/lib/base/ground/ground.test.ts) checks; here
 * the flat case checks the manifest carries a reason and that nothing stands in for the ground.
 */

const VIEW = '#map=10/43.6/-116.4/0/45&layers=none';
const LANDCOVER = 'landcover';
const GROUND_FILE = /\/tiles\/ground-[^/]*\.pmtiles(?:\?|$)/;

type GroundEntry = { status: 'painted' | 'flat'; reason?: string } | undefined;

const groundEntry = async (page: Page): Promise<GroundEntry> => {
	const m = await page.request.get('/tiles/manifest.json').then((r) => r.json());
	return m.ground;
};
/** Record the page's requests to the ground's files. */
const watchGround = (page: Page) => {
	const urls: string[] = [];
	page.on('request', (r) => GROUND_FILE.test(r.url()) && urls.push(r.url()));
	return urls;
};
/** The saved Base look (`map` is Valley), set from a page of the same origin that doesn't start the map. */
async function setLook(page: Page, look: 'map' | 'clay' | 'auto') {
	await page.goto('/api/health');
	await page.evaluate((look) => localStorage.setItem('tvt:v2:base', JSON.stringify({ look, buildings: true, terrain: true, labels: 'full' })), look);
}
const vis = (page: Page, id: string) => page.evaluate((id) => (globalThis as any).__tvt.map.getLayoutProperty(id, 'visibility') ?? 'visible', id);
const has = (page: Page, what: { source?: string; layer?: string }) =>
	page.evaluate((w) => {
		const map = (globalThis as any).__tvt.map;
		return { source: w.source ? Boolean(map.getSource(w.source)) : null, layer: w.layer ? Boolean(map.getLayer(w.layer)) : null };
	}, what);
const flavor = (page: Page) => page.evaluate(() => (globalThis as any).__tvt.layers.flavor as string);

test.describe('the painted ground', () => {
	test('Valley draws the ground and hides the landcover fills', { tag: '@ground' }, async ({ page }) => {
		test.setTimeout(300_000);
		await page.goto('/api/health');
		test.skip((await groundEntry(page))?.status !== 'painted', 'the ground in TILES_DIR is not painted');
		const requests = watchGround(page);
		await setLook(page, 'map');
		await page.goto(`/${VIEW}`);
		await mapReady(page);
		expect(await flavor(page)).toBe('valley');
		expect(await has(page, { source: 'ground', layer: 'ground-paint' })).toEqual({ source: true, layer: true });
		expect((await has(page, { source: 'groundDetail', layer: 'ground-detail' }))).toEqual({ source: true, layer: true });
		expect(await vis(page, 'ground-paint')).toBe('visible');
		expect(await vis(page, LANDCOVER)).toBe('none');
		// It drew: tiles were asked for and the source finished loading them.
		await expect.poll(() => requests.length, { timeout: 60_000 }).toBeGreaterThan(0);
		await expect
			.poll(() => page.evaluate(() => (globalThis as any).__tvt.map.isSourceLoaded('ground')), { timeout: 60_000 })
			.toBe(true);
		// The ground sits under the basemap's own fills.
		const order: string[] = await page.evaluate(() => (globalThis as any).__tvt.map.getLayersOrder());
		expect(order.indexOf('ground-paint')).toBeGreaterThan(order.indexOf('earth'));
		expect(order.indexOf('ground-paint')).toBeLessThan(order.indexOf(LANDCOVER));
	});

	test('a Clay first visit makes no ground request and keeps its fills; the first use of Valley loads it', { tag: '@ground' }, async ({ page }) => {
		test.setTimeout(300_000);
		await page.goto('/api/health');
		const entry = await groundEntry(page);
		test.skip(entry?.status !== 'painted', 'the ground in TILES_DIR is not painted');
		const requests = watchGround(page);
		// A first visit: nothing saved, so Auto with the default layers on (Transit, Cameras), which is Clay.
		await page.evaluate(() => localStorage.removeItem('tvt:v2:base'));
		await page.goto('/');
		await mapReady(page);
		expect(await flavor(page)).toBe('clay');
		expect(await has(page, { source: 'ground', layer: 'ground-paint' })).toEqual({ source: false, layer: false });
		expect(await vis(page, LANDCOVER)).not.toBe('none');
		expect(requests, 'no ground request in a Clay first visit').toEqual([]);
		// The first use of Valley: the ground loads now.
		await page.getByRole('toolbar', { name: 'Map layers' }).getByRole('button', { name: 'Base' }).click();
		const pop = page.getByRole('dialog', { name: 'Base map' });
		await pop.getByRole('radio', { name: 'Map' }).check();
		await expect.poll(() => flavor(page)).toBe('valley');
		await expect.poll(async () => (await has(page, { source: 'ground' })).source).toBe(true);
		await expect.poll(() => requests.length, { timeout: 60_000 }).toBeGreaterThan(0);
		expect(await vis(page, 'ground-paint')).toBe('visible');
		expect(await vis(page, LANDCOVER)).toBe('none');
		// Back to Clay: hidden, the fills are back.
		await pop.getByRole('radio', { name: 'Clay' }).check();
		await expect.poll(() => flavor(page)).toBe('clay');
		expect(await vis(page, 'ground-paint')).toBe('none');
		expect(await vis(page, LANDCOVER)).not.toBe('none');
	});

	test('Aerial hides the ground', { tag: '@ground' }, async ({ page }) => {
		test.setTimeout(300_000);
		await page.goto('/api/health');
		test.skip((await groundEntry(page))?.status !== 'painted', 'the ground in TILES_DIR is not painted');
		await setLook(page, 'map');
		await page.goto(`/${VIEW}`);
		await mapReady(page);
		expect(await vis(page, 'ground-paint')).toBe('visible');
		await page.getByRole('toolbar', { name: 'Map layers' }).getByRole('button', { name: 'Base' }).click();
		const pop = page.getByRole('dialog', { name: 'Base map' });
		await pop.getByRole('switch', { name: /Aerial photos/ }).check();
		await expect.poll(() => vis(page, 'ground-paint')).toBe('none');
		expect(await vis(page, 'ground-detail')).toBe('none');
		await pop.getByRole('switch', { name: /Aerial photos/ }).uncheck();
		await expect.poll(() => vis(page, 'ground-paint')).toBe('visible');
	});

	test('a flat ground adds nothing, says why, and no other source stands in for it', { tag: '@ground' }, async ({ page }) => {
		test.setTimeout(300_000);
		await page.goto('/api/health');
		const entry = await groundEntry(page);
		test.skip(entry?.status !== 'flat', 'the ground in TILES_DIR is not flat: run with --ground flat');
		// The reason the Base row shows is the manifest's.
		expect(entry?.reason, 'a flat entry carries its reason').toBeTruthy();
		const requests = watchGround(page);
		await setLook(page, 'map');
		await page.goto(`/${VIEW}`);
		await mapReady(page);
		expect(await flavor(page)).toBe('valley');
		expect(await has(page, { source: 'ground', layer: 'ground-paint' })).toEqual({ source: false, layer: false });
		expect(await has(page, { source: 'groundDetail', layer: 'ground-detail' })).toEqual({ source: false, layer: false });
		expect(await vis(page, LANDCOVER)).not.toBe('none');
		expect(requests).toEqual([]);
	});
});
