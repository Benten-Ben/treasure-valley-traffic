import type { Page } from '@playwright/test';
import postgres from 'postgres';
import { recordNetwork } from '../../scripts/net.mjs';
import { expect, mapReady, screenPath, seeds, test } from './fixtures.js';

/**
 * persistent (docs/14 §14.10, WP1 acceptance): the map is created once per
 * visit; leaving the calibrator returns to the same map, with no tile it
 * already had requested again, no manifest request, and the exact view.
 * Plus the rest of WP1's acceptance: Forward re-enters, a reload restores
 * the view, a legacy hash is rewritten, the calibrator saves from the new
 * route and from /v1, and keys are ignored in a select. (Polling while
 * hidden is in polling.spec.ts; data starting before the first DEM tile in
 * budget.spec.ts.)
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
const mode = (page: Page) => page.evaluate(() => (globalThis as any).__tvt?.mode);
const layersOrder = (page: Page) => page.evaluate(() => (globalThis as any).__tvt?.map?.getLayersOrder() ?? null);

/** Open a camera's card by clicking its dot on the map (it must be in view). */
async function openCameraCard(page: Page, lngLat: [number, number]) {
	const pt = await page.evaluate((ll) => (globalThis as any).__tvt.map.project(ll), lngLat);
	await page.mouse.click(pt.x, pt.y);
	await expect(page.getByRole('region', { name: 'Selected camera' })).toBeVisible();
}

/**
 * Five round trips into the calibrator and back, each checked on its
 * return leg (§14.9 Targets): no tile loaded before entering is requested
 * again, no manifest request, the exact view, and the same style layers as
 * after the first trip (which adds the aerial layers). One map throughout.
 */
async function roundTrips(
	page: Page,
	start: string,
	enter: () => Promise<void>,
	back: () => Promise<void>,
	label: string,
	prepare?: () => Promise<void>
) {
	const net = await recordNetwork(page, { bodies: false });
	await page.goto(start);
	await mapReady(page);
	// Anything that moves the map before the first trip (a camera click flies to it, WP12) happens
	// here, so the tiles and the view the trips must keep are the ones after it.
	if (prepare) {
		await prepare();
		await mapReady(page);
	}
	const loaded = new Set(net.entries.filter((x) => isTile(x) && !x.failed).map(tileKey));
	const before = await currentView(page);
	expect(before).not.toBeNull();
	let layersAfterFirst: string[] | null = null;
	for (let cycle = 1; cycle <= 5; cycle++) {
		await enter();
		await page.waitForURL(/\/calibrate\//);
		await mapReady(page);
		expect(await mode(page), `cycle ${cycle}: calibrate mode`).toBe('calibrate');
		if (cycle === 1) await page.screenshot({ path: screenPath(`persistent-${label}-calibrate.png`) });
		const mark = net.mark();
		await back();
		await page.waitForURL((u) => !u.pathname.startsWith('/calibrate'));
		await mapReady(page);
		const ret = net.since(mark);
		// Any request counts, cache hits included: the map should still hold these tiles.
		expect(ret.filter((x) => isTile(x) && loaded.has(tileKey(x))).map(tileKey), `cycle ${cycle}: tiles fetched again`).toEqual([]);
		expect(ret.filter((x) => x.kind === 'manifest').length, `cycle ${cycle}: manifest requests`).toBe(0);
		expect(await mode(page)).toBe('explore');
		const after = (await currentView(page))!;
		expect(Math.abs(after.lng - before!.lng), `cycle ${cycle}: centre`).toBeLessThan(1e-6);
		expect(Math.abs(after.lat - before!.lat)).toBeLessThan(1e-6);
		expect(Math.abs(after.zoom - before!.zoom)).toBeLessThan(0.01);
		expect(Math.abs(after.bearing - before!.bearing)).toBeLessThan(1e-6);
		expect(Math.abs(after.pitch - before!.pitch)).toBeLessThan(1e-6);
		const layers = await layersOrder(page);
		expect(layers, '__tvt.map (WP1)').not.toBeNull();
		if (cycle === 1) {
			layersAfterFirst = layers;
			expect(layers).toEqual(expect.arrayContaining(['aerial']));
		} else expect(layers, `cycle ${cycle}: style layers`).toEqual(layersAfterFirst);
	}
	expect(await page.evaluate(() => (globalThis as any).__tvt?.mapsCreated)).toBe(1);
	await page.screenshot({ path: screenPath(`persistent-${label}-returned.png`) });
	await net.detach();
}

test.describe('persistent', () => {
	test('camera → Calibrate → Back keeps one map, its tiles and the exact view', { tag: ['@wp0', '@wp1'] }, async ({ page, offsite }) => {
		test.setTimeout(600_000);
		const key = seeds().seeds.find((s) => s.kind === 'key')!;
		// Downtown Boise at z14, pitch 50, in the legacy hash form (rewritten on load).
		await roundTrips(
			page,
			'/#14/43.6150/-116.2023/20/50',
			() => follow(page, `/calibrate/${key.cameraId}`),
			() => page.goBack().then(() => undefined),
			'back'
		);
		expect(offsite).toEqual([]);
	});

	test('camera → Calibrate → Leave keeps one map, its tiles and the exact view', { tag: '@wp1' }, async ({ page, offsite }) => {
		test.setTimeout(600_000);
		const key = seeds().seeds.find((s) => s.kind === 'key')!;
		const pole = await page.request.get(`/api/cameras/${key.cameraId}`).then((r) => r.json()).then((c) => c.pole as [number, number]);
		// Near the key camera, tilted and turned, so its dot can be clicked.
		const start = `/#map=16.3/${pole[1]}/${pole[0]}/-30/40`;
		await roundTrips(
			page,
			start,
			// The selection survives each trip, so every cycle enters from the card's link.
			() => page.getByRole('region', { name: 'Selected camera' }).getByRole('link').click(),
			() => page.getByRole('button', { name: 'Leave calibration' }).click(),
			'leave',
			// A click on the camera flies to it and opens its window (Q2, WP12): select it first.
			() => openCameraCard(page, pole)
		);
		expect(offsite).toEqual([]);
	});

	test('Forward re-enters the calibrator, and Back returns again', { tag: '@wp1' }, async ({ page }) => {
		test.setTimeout(300_000);
		const key = seeds().seeds.find((s) => s.kind === 'key')!;
		await page.goto('/#map=13/43.6/-116.3/0/30');
		await mapReady(page);
		const before = (await currentView(page))!;
		await follow(page, `/calibrate/${key.cameraId}`);
		await page.waitForURL(/\/calibrate\//);
		await mapReady(page);
		const inside = (await currentView(page))!;
		await page.goBack();
		await mapReady(page);
		expect(await mode(page)).toBe('explore');
		await page.goForward();
		await page.waitForURL(/\/calibrate\//);
		await mapReady(page);
		expect(await mode(page)).toBe('calibrate');
		const again = (await currentView(page))!;
		expect(again.zoom).toBeCloseTo(19, 5);
		expect(again.pitch).toBeCloseTo(0, 5);
		expect(Math.abs(again.lng - inside.lng)).toBeLessThan(1e-9);
		expect(Math.abs(again.lat - inside.lat)).toBeLessThan(1e-9);
		await expect(page.getByRole('heading', { name: key.name })).toBeVisible();
		await page.goBack();
		await mapReady(page);
		const after = (await currentView(page))!;
		expect(Math.abs(after.lng - before.lng)).toBeLessThan(1e-6);
		expect(Math.abs(after.lat - before.lat)).toBeLessThan(1e-6);
		expect(Math.abs(after.zoom - before.zoom)).toBeLessThan(0.01);
		expect(await page.evaluate(() => (globalThis as any).__tvt.mapsCreated)).toBe(1);
	});

	test('a reload restores the view exactly, and the hash alone restores it rounded', { tag: '@wp1' }, async ({ page, browser }) => {
		await page.goto('/');
		await mapReady(page);
		// An awkward view: nothing about it is round.
		const want = { lng: -116.2468213579, lat: 43.6012345678, zoom: 13.37, bearing: 17.3, pitch: 41.2 };
		await page.evaluate((w) => {
			(globalThis as any).__tvt.map.jumpTo({ center: [w.lng, w.lat], zoom: w.zoom, bearing: w.bearing, pitch: w.pitch });
		}, want);
		await expect.poll(() => page.evaluate(() => location.hash)).toMatch(/^#map=13\.37\/43\.6012\d*\/-116\.2468\d*\/17\.3\/41\.2$/);
		const hash = await page.evaluate(() => location.hash);
		await page.reload();
		await mapReady(page);
		const after = (await currentView(page))!;
		expect(Math.abs(after.lng - want.lng)).toBeLessThan(1e-6);
		expect(Math.abs(after.lat - want.lat)).toBeLessThan(1e-6);
		expect(Math.abs(after.zoom - want.zoom)).toBeLessThan(0.01);
		expect(after.bearing).toBeCloseTo(want.bearing, 5);
		expect(after.pitch).toBeCloseTo(want.pitch, 5);

		// A fresh browser with only the link: the hash's (rounded) view.
		const other = await browser.newContext({ baseURL: test.info().project.use.baseURL });
		const p2 = await other.newPage();
		await p2.goto(`/${hash}`);
		await mapReady(p2);
		const shared = (await currentView(p2))!;
		expect(Math.abs(shared.lng - want.lng)).toBeLessThan(1e-4);
		expect(Math.abs(shared.lat - want.lat)).toBeLessThan(1e-4);
		expect(Math.abs(shared.zoom - want.zoom)).toBeLessThan(0.01);
		await other.close();
	});

	test('a legacy #z/lat/lng/bearing/pitch hash is rewritten once, in place', { tag: '@wp1' }, async ({ page }) => {
		// History's length before the map has loaded (the rewrite waits for the style).
		await page.goto('/#14/43.6150/-116.2023/20/50', { waitUntil: 'commit' });
		const length = await page.evaluate(() => history.length);
		await mapReady(page);
		await expect.poll(() => page.evaluate(() => location.hash)).toBe('#map=14/43.615/-116.2023/20/50');
		expect(await page.evaluate(() => history.length), 'replaced, not pushed').toBe(length);
		const v = (await currentView(page))!;
		expect(v).toMatchObject({ zoom: 14, bearing: 20, pitch: 50 });
		expect(Math.abs(v.lat - 43.615)).toBeLessThan(1e-9);
		expect(Math.abs(v.lng + 116.2023)).toBeLessThan(1e-9);
	});

	test('a calibration link opened fresh leaves to the camera at z16, pitch 50', { tag: '@wp1' }, async ({ page }) => {
		const key = seeds().seeds.find((s) => s.kind === 'key')!;
		const pole = await page.request.get(`/api/cameras/${key.cameraId}`).then((r) => r.json()).then((c) => c.pole as [number, number]);
		await page.goto(`/calibrate/${key.cameraId}`);
		await mapReady(page);
		expect(await mode(page)).toBe('calibrate');
		await page.getByRole('button', { name: 'Leave calibration' }).click();
		await page.waitForURL((u) => u.pathname === '/');
		await mapReady(page);
		const v = (await currentView(page))!;
		expect(Math.abs(v.lng - pole[0])).toBeLessThan(1e-6);
		expect(Math.abs(v.lat - pole[1])).toBeLessThan(1e-6);
		expect(v.zoom).toBeCloseTo(16, 5);
		expect(v.pitch).toBeCloseTo(50, 5);
		expect(await page.evaluate(() => (globalThis as any).__tvt.mapsCreated)).toBe(1);
		await expect.poll(() => page.evaluate(() => location.hash)).toMatch(/^#map=16\//);
	});

	test('an unknown camera shows its error inside the map', { tag: '@wp1' }, async ({ page }) => {
		await page.goto('/');
		await mapReady(page);
		await follow(page, '/calibrate/999999');
		await expect(page.getByRole('alert').filter({ hasText: 'Not found' })).toBeVisible();
		expect(await page.evaluate(() => Boolean((globalThis as any).__tvt.map))).toBe(true);
		expect(await mode(page)).toBe('explore');
		await page.getByRole('link', { name: 'Back to the map' }).click();
		await mapReady(page);
		expect(await page.evaluate(() => (globalThis as any).__tvt.mapsCreated)).toBe(1);
	});

	test('keys are ignored in a select, and work again outside it', { tag: '@wp1' }, async ({ page }) => {
		await page.goto('/');
		await mapReady(page);
		const lens = () => page.evaluate(() => (globalThis as any).__tvt.layers?.lens);
		await expect.poll(() => page.evaluate(() => (globalThis as any).__tvt.layers?.transit)).toBe(true);
		expect(await lens()).toBe('cameras');
		await page.evaluate(() => {
			const s = document.createElement('select');
			s.id = 'probe-select';
			s.innerHTML = '<option>1</option><option>4</option>';
			document.body.append(s);
		});
		await page.focus('#probe-select');
		await page.keyboard.press('4');
		await page.keyboard.press('2');
		expect(await lens(), 'keys in a select').toBe('cameras');
		await page.evaluate(() => (document.activeElement as HTMLElement).blur());
		await page.keyboard.press('Control+4');
		expect(await lens(), 'keys with a modifier').toBe('cameras');
		await page.keyboard.press('4');
		expect(await lens(), 'keys elsewhere').toBe('transit');
	});

	test('the calibrator saves from the new route and from /v1, closing the previous row', { tag: '@wp1' }, async ({ page, offsite }) => {
		test.setTimeout(400_000);
		const key = seeds().seeds.find((s) => s.kind === 'key')!;
		const sql = postgres(process.env.DATABASE_URL!, { max: 1, onnotice: () => {} });
		const current = async () =>
			(await sql`select id from core.camera_calibration where view_id = ${key.viewId} and upper_inf(valid)`).map((r) => Number(r.id));
		const [seeded] = await current();
		const saved: number[] = [];
		try {
			for (const path of [`/calibrate/${key.cameraId}`, `/v1/calibrate/${key.cameraId}`]) {
				const [previous] = await current();
				expect(previous, 'the seeded view has a current calibration').toBeTruthy();
				await page.goto(path);
				await mapReady(page);
				// The current calibration loads with its pairs and solves.
				await expect(page.getByText(/px, great/)).toBeVisible();
				const saving = page.waitForResponse((r) => r.url().endsWith(`/api/views/${key.viewId}/calibrations`) && r.request().method() === 'POST');
				await page.getByRole('button', { name: 'Save calibration' }).click();
				const res = await saving;
				expect(res.status(), `${path}: POST`).toBe(200);
				const { id } = await res.json();
				saved.push(id);
				await expect(page.getByRole('status').filter({ hasText: 'Saved' })).toBeVisible();
				expect(await current(), `${path}: the new row is the only current one`).toEqual([id]);
				const [old] = await sql`select upper_inf(valid) as open from core.camera_calibration where id = ${previous}`;
				expect(old.open, `${path}: previous row closed`).toBe(false);
			}
		} finally {
			// Put the seeded calibration back as it was, so other specs (and the next run) see the seeds.
			if (saved.length) await sql`delete from core.camera_calibration where id in ${sql(saved)}`;
			if (seeded) await sql`update core.camera_calibration set valid = tstzrange(lower(valid), null) where id = ${seeded}`;
			await sql.end();
		}
		expect(offsite).toEqual([]);
	});

	test('"New frame" goes through the fixture switch', { tag: '@wp1' }, async ({ page, offsite }) => {
		const key = seeds().seeds.find((s) => s.kind === 'key')!;
		await page.goto(`/calibrate/${key.cameraId}`);
		await mapReady(page);
		const capture = page.waitForResponse((r) => r.url().endsWith(`/api/views/${key.viewId}/frame`));
		await page.getByRole('button', { name: 'New frame' }).click();
		const res = await capture;
		expect(res.status()).toBe(200);
		const frame = await res.json();
		expect(frame.url).toMatch(/^\/frames\//);
		await expect(page.locator(`img[src="${frame.url}"]`)).toBeVisible();
		expect(offsite).toEqual([]);
	});

	test('imagery loads only once Aerial is turned on, and its layers then stay', { tag: '@wp1' }, async ({ page }) => {
		const imagery: string[] = [];
		page.on('request', (r) => {
			if (/\/tiles\/imagery[^/]*\.pmtiles/.test(r.url())) imagery.push(r.url());
		});
		await page.goto('/#map=15/43.6197/-116.3549/0/0');
		await mapReady(page);
		expect(imagery, 'imagery requests before Aerial').toEqual([]);
		expect(await layersOrder(page)).not.toContain('aerial');
		await page.getByRole('button', { name: 'Aerial' }).click();
		await mapReady(page);
		expect(imagery.length).toBeGreaterThan(0);
		await page.getByRole('button', { name: 'Map', exact: true }).click();
		await mapReady(page);
		const layers = await layersOrder(page);
		expect(layers).toEqual(expect.arrayContaining(['aerial', 'aerial-detail']));
		expect(layers!.indexOf('aerial')).toBe(layers!.indexOf('hillshade') + 1);
		expect(await page.evaluate(() => (globalThis as any).__tvt.map.getLayoutProperty('aerial', 'visibility'))).toBe('none');
	});

	test('a new deploy shows "New version: reload when convenient"', { tag: '@wp1' }, async ({ page }) => {
		await page.goto('/');
		await mapReady(page);
		// Only SvelteKit's version file is answered by the test (no cache measurement here).
		await page.route('**/_app/version.json', (r) => r.fulfill({ json: { version: 'a-newer-build' } }));
		await page.evaluate(() => window.dispatchEvent(new Event('focus')));
		const toast = page.getByRole('status').filter({ hasText: 'New version: reload when convenient' });
		await expect(toast).toBeVisible();
		await page.screenshot({ path: screenPath('persistent-new-version.png') });
		await toast.getByRole('button', { name: 'Dismiss' }).click();
		await expect(toast).toHaveCount(0);
	});

	test('a lost WebGL context shows "Map paused" until it comes back', { tag: '@wp1' }, async ({ page }) => {
		await page.goto('/');
		await mapReady(page);
		await page.evaluate(() => {
			const gl = (globalThis as any).__tvt.map.getCanvas().getContext('webgl2');
			(globalThis as any).__lose = gl.getExtension('WEBGL_lose_context');
			(globalThis as any).__lose.loseContext();
		});
		await expect(page.getByRole('alert').filter({ hasText: 'Map paused' })).toBeVisible();
		await page.screenshot({ path: screenPath('persistent-context-lost.png') });
		await page.evaluate(() => (globalThis as any).__lose.restoreContext());
		await expect(page.getByRole('alert').filter({ hasText: 'Map paused' })).toHaveCount(0);
	});
});
