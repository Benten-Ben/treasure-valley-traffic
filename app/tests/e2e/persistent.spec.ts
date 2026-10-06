import type { Page } from '@playwright/test';
import { recordNetwork } from '../../scripts/net.mjs';
import { expect, mapReady, seeds, test } from './fixtures.js';

/**
 * persistent (docs/14 §14.10, WP1 acceptance): the map is created once per
 * visit; leaving the calibrator returns to the same map, with no tile it
 * already had requested again, no manifest request, and the exact view.
 *
 * Expected to fail until WP1 builds the persistent map shell: today every
 * page change rebuilds the map and the view is lost. WP1 removes the
 * test.fail line (and adds the → Leave cycles once its calibrator has the
 * button).
 */

type View = { lng: number; lat: number; zoom: number; bearing: number; pitch: number };

/** The view from the map when the app exposes it (__tvt, WP1), else from MapLibre's hash. */
async function currentView(page: Page): Promise<View | null> {
	return page.evaluate(() => {
		const map = (globalThis as any).__tvt?.map;
		if (map) {
			const c = map.getCenter();
			return { lng: c.lng, lat: c.lat, zoom: map.getZoom(), bearing: map.getBearing(), pitch: map.getPitch() };
		}
		const m = /^#(?:map=)?([\d.]+)\/(-?[\d.]+)\/(-?[\d.]+)(?:\/(-?[\d.]+))?(?:\/([\d.]+))?/.exec(location.hash);
		return m ? { zoom: +m[1], lat: +m[2], lng: +m[3], bearing: +(m[4] ?? 0), pitch: +(m[5] ?? 0) } : null;
	});
}

/** A client-side navigation, as clicking the app's own link does. */
async function follow(page: Page, href: string) {
	await page.evaluate((href) => {
		const a = document.createElement('a');
		a.href = href;
		document.body.append(a);
		a.click();
		a.remove();
	}, href);
}

const tileKey = (x: { url: string; range: string | null }) => `${x.url} ${x.range ?? ''}`;
const isTile = (x: { url: string }) => /\/tiles\/.+\.pmtiles/.test(x.url);

test.describe('persistent', () => {
	test('camera → Calibrate → Back keeps one map, its tiles and the exact view', { tag: ['@wp0', '@wp1'] }, async ({ page }) => {
		test.fail(true, 'WP1 builds the persistent map (§14.10 WP1); until then the map is rebuilt on every page change.');
		test.setTimeout(600_000);
		const key = seeds().seeds.find((s) => s.kind === 'key')!;
		const net = await recordNetwork(page, { bodies: false });

		// Downtown Boise at z14, pitch 50, in the legacy hash form (WP1 rewrites it).
		await page.goto('/#14/43.6150/-116.2023/20/50');
		await mapReady(page);
		const loaded = new Set(net.entries.filter((x) => isTile(x) && !x.failed).map(tileKey));
		const before = await currentView(page);
		expect(before).not.toBeNull();
		let layersAfterFirst: string[] | null = null;

		for (let cycle = 1; cycle <= 5; cycle++) {
			await follow(page, `/calibrate/${key.cameraId}`);
			await page.waitForURL(/\/calibrate\//);
			await mapReady(page);
			const mark = net.mark();
			await page.goBack();
			await page.waitForURL((u) => !u.pathname.startsWith('/calibrate'));
			await mapReady(page);
			const back = net.since(mark);
			// Any request counts, cache hits included: the map should still hold these tiles.
			expect(back.filter((x) => isTile(x) && loaded.has(tileKey(x))).map(tileKey), `cycle ${cycle}: tiles fetched again`).toEqual([]);
			expect(back.filter((x) => x.kind === 'manifest').length, `cycle ${cycle}: manifest requests`).toBe(0);
			const after = (await currentView(page))!;
			expect(Math.abs(after.lng - before!.lng), `cycle ${cycle}: centre`).toBeLessThan(1e-6);
			expect(Math.abs(after.lat - before!.lat)).toBeLessThan(1e-6);
			expect(Math.abs(after.zoom - before!.zoom)).toBeLessThan(0.01);
			const layers = await page.evaluate(() => (globalThis as any).__tvt?.map?.getLayersOrder() ?? null);
			expect(layers, '__tvt.map (WP1)').not.toBeNull();
			if (cycle === 1) layersAfterFirst = layers;
			else expect(layers).toEqual(layersAfterFirst);
		}
		expect(await page.evaluate(() => (globalThis as any).__tvt?.mapsCreated)).toBe(1);
		await net.detach();
	});
});
