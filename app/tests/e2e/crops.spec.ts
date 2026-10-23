import type { Page } from '@playwright/test';
import { expect, mapReady, screenPath, test } from './fixtures.js';
import { centre, CENTRE, cleanCrops, EDITION, seedCrops, type Seeded } from './crops-seed.js';

/**
 * crops (landscape sprint P3-app): with three SYNTHETIC fields loaded (crops-seed.ts: invented outlines, eight
 * made-up crop years each, their z8-10 dissolves and a layer version):
 *
 * - the fills draw in Clay (the pixels under the fields are their groups' colours), go away in the Map look,
 *   and are off under Transit (one area fill at a time, the owner's `offUnder`);
 * - the year switch changes the drawn group at valley zoom, and at z9 the dissolves come from the earlier
 *   year's own tiles (`/api/farm/tiles/crop_year_<year>`, which share the fields layer's version);
 * - a click on a field opens the card: "Estimated field", acres and county, this year's crop with USDA's
 *   label, eight yearly chips, the rotation, growth as stored, the credits; `#field=<id>` opens the same card;
 * - the tile URL answers through the generic route, and the screenshot of hay's cyan is kept for the owner.
 */
const FILL = { corn: '#eac644', hay: '#4bc2d5', grain: '#ad754a', roots: '#b97dc6', specialty: '#ff924b', pasture: '#98c88b', fallow: '#d2ccc2' } as const;
const CLAY = '#f3ede2';
const OPACITY = 0.85;

const hexRgb = (h: string): [number, number, number] => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)) as [number, number, number];
const blend = (fill: string): [number, number, number] => {
	const a = hexRgb(fill);
	const b = hexRgb(CLAY);
	return [0, 1, 2].map((i) => a[i] * OPACITY + b[i] * (1 - OPACITY)) as [number, number, number];
};
const CLASSES = { ...Object.fromEntries(Object.entries(FILL).map(([g, c]) => [g, blend(c)])), clay: hexRgb(CLAY) } as Record<string, [number, number, number]>;
const nearest = (rgb: number[]) => Object.entries(CLASSES).sort((p, q) => dist(rgb, p[1]) - dist(rgb, q[1]))[0][0];
const dist = (a: number[], b: number[]) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);

/** The hash that puts the middle synthetic field at the map's centre. */
const at = (zoom: number, extra = '') => `/#map=${zoom}/${centre(1)[1]}/${centre(1)[0]}/0/0&layers=crops${extra}`;
const info = (page: Page) => page.evaluate(() => (globalThis as any).__tvt.layers);
const crops = (page: Page) => page.evaluate(() => (globalThis as any).__tvtCrops?.info() ?? null);
const layer = (page: Page, id: string) => page.evaluate((id) => (globalThis as any).__tvtCrops?.layer(id) ?? null, id);
const selection = (page: Page) => page.evaluate(() => (globalThis as any).__tvt.layers.selection);

/** A grid of pixels around a lng/lat, read from the canvas inside a render, and the group colour most of them are nearest to. */
const dominant = (page: Page, lngLat: [number, number]) =>
	page.evaluate(
		([lng, lat]) =>
			new Promise<number[][]>((resolve) => {
				const map = (globalThis as any).__tvt.map;
				map.once('render', () => {
					const gl = map.getCanvas().getContext('webgl2') as WebGL2RenderingContext;
					const p = map.project([lng, lat]);
					const k = gl.drawingBufferWidth / map.getCanvas().clientWidth;
					const out: number[][] = [];
					for (let dx = -18; dx <= 18; dx += 6)
						for (let dy = -18; dy <= 18; dy += 6) {
							const px = new Uint8Array(4);
							gl.readPixels(Math.round((p.x + dx) * k), Math.round(gl.drawingBufferHeight - (p.y + dy) * k), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
							out.push([...px.slice(0, 3)]);
						}
					resolve(out);
				});
				map.triggerRepaint();
			}),
		lngLat
	).then((samples) => {
		const votes = new Map<string, number>();
		// Ink from the patterns and hatches is far from every colour: only pixels that are a fill (or the ground) vote.
		for (const s of samples) if (dist(s, CLASSES[nearest(s)]) < 16) votes.set(nearest(s), (votes.get(nearest(s)) ?? 0) + 1);
		if (!votes.size) return 'none';
		return [...votes.entries()].sort((a, b) => b[1] - a[1])[0][0];
	});

let seeded: Seeded | null = null;
let ids: number[] = [];

test.beforeAll(async () => {
	seeded = await seedCrops();
	ids = seeded.ids;
});

test.afterAll(async () => {
	await cleanCrops(seeded);
});

const toolbar = (page: Page) => page.getByRole('toolbar', { name: 'Map layers' });

test.describe('crops', () => {
	test('fills draw in Clay with the groups\' colours, go away in the Map look, and are off under Transit', { tag: '@crops' }, async ({ page, consoleErrors, offsite }) => {
		test.setTimeout(300_000);
		await page.goto(at(13.5));
		await mapReady(page);
		await expect.poll(async () => (await crops(page))?.visible, { timeout: 60_000 }).toBe(true);
		// Auto goes Clay while a layer that doesn't keep Valley is on.
		await expect.poll(async () => (await info(page)).flavor).toBe('clay');
		expect((await layer(page, 'crops-fill')).visibility).toBe('visible');
		// 2025: A is hay (cyan), B is built (unpainted), C is sugar beets (roots).
		await expect.poll(() => dominant(page, centre(0)), { timeout: 60_000 }).toBe('hay');
		await expect.poll(() => dominant(page, centre(2))).toBe('roots');
		expect(await dominant(page, centre(1))).toBe('clay'); // B: developed, nothing painted, only the hatch
		await page.screenshot({ path: screenPath('crops-hay-cyan-z13.5.png') });
		await page.evaluate((c) => (globalThis as any).__tvt.map.jumpTo({ zoom: 14.2, center: c }), centre(0));
		await mapReady(page);
		await page.screenshot({ path: screenPath('crops-hay-cyan-z14.2.png') });

		// The Map look (Valley): the Clay-only fills are hidden, the layer stays on.
		await page.goto(at(13.5));
		await mapReady(page);
		await toolbar(page).getByRole('button', { name: 'Base' }).click();
		const pop = page.getByRole('dialog', { name: 'Base map' });
		await pop.getByRole('radio', { name: 'Map' }).check();
		await expect.poll(async () => (await info(page)).flavor).toBe('valley');
		await expect.poll(async () => (await layer(page, 'crops-fill')).visibility).toBe('none');
		expect((await layer(page, 'crops-pattern')).visibility).toBe('none');
		await pop.getByRole('radio', { name: 'Auto' }).check();
		await expect.poll(async () => (await layer(page, 'crops-fill')).visibility).toBe('visible');

		// Under Transit the crop fills are off (patterns and linework follow), with Crop fields still on.
		await page.goto(at(13.5, ',transit'));
		await mapReady(page);
		await expect.poll(async () => (await info(page)).status.transit, { timeout: 90_000 }).toMatch(/ready|stale/);
		await expect.poll(async () => (await layer(page, 'crops-fill')).visibility).toBe('none');
		expect((await crops(page)).visible).toBe(true);
		expect(await dominant(page, centre(0))).not.toBe('hay');
		expect(consoleErrors.filter((e) => !/Failed to load resource|transit|gtfs/i.test(e))).toEqual([]);
		expect(offsite).toEqual([]);
	});

	test('the year switch changes the drawn group, and the dissolves come from the year\'s own tiles', { tag: '@crops' }, async ({ page }) => {
		test.setTimeout(300_000);
		await page.goto(at(13.5));
		await mapReady(page);
		await expect.poll(async () => (await crops(page))?.visible, { timeout: 60_000 }).toBe(true);
		await expect.poll(() => dominant(page, centre(0)), { timeout: 60_000 }).toBe('hay');
		expect((await crops(page)).years).toEqual([2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]);
		// The legend's chips: 2018, when A was corn, B hay and C grain.
		const chip = page.locator('button[data-year="2018"]');
		await expect(chip).toBeVisible();
		await chip.click();
		await expect(chip).toHaveAttribute('aria-pressed', 'true');
		expect((await crops(page)).year).toBe(2018);
		await expect.poll(() => dominant(page, centre(0)), { timeout: 60_000 }).toBe('corn');
		await expect.poll(() => dominant(page, centre(1))).toBe('hay');
		await expect.poll(() => dominant(page, centre(2))).toBe('grain');
		await page.screenshot({ path: screenPath('crops-year-2018-z13.5.png') });

		// At z9 the dissolves come from crop_year_2018's tiles, sharing the fields layer's version.
		const tile = page.waitForResponse((r) => /\/api\/farm\/tiles\/crop_year_2018\/9\/90\/187\?v=e2e-/.test(r.url()), { timeout: 60_000 });
		await page.evaluate((c) => (globalThis as any).__tvt.map.jumpTo({ zoom: 9.2, center: c }), CENTRE);
		const res = await tile;
		expect(res.status()).toBe(200);
		expect(res.headers()['content-type']).toBe('application/vnd.mapbox-vector-tile');
		expect((await res.body()).length).toBeGreaterThan(0);
		expect((await layer(page, 'crops-fill-lo')).minzoom).toBe(22); // the newest year's dissolves are moved out
		expect((await layer(page, 'crops-fill-lo-year')).maxzoom).toBe(11);
		// Back to the newest year: A is hay again.
		await page.evaluate((c) => (globalThis as any).__tvt.map.jumpTo({ zoom: 13.5, center: c }), centre(1));
		await page.locator('button[data-year="2025"]').click();
		await expect.poll(() => dominant(page, centre(0)), { timeout: 60_000 }).toBe('hay');
	});

	test('a click on a field opens the card; #field=<id> opens the same card', { tag: '@crops' }, async ({ page, consoleErrors }) => {
		test.setTimeout(300_000);
		await page.goto(at(13.5));
		await mapReady(page);
		await expect.poll(() => dominant(page, centre(0)), { timeout: 60_000 }).toBe('hay');
		const pos = (i: number) => page.evaluate(([lng, lat]) => (globalThis as any).__tvt.map.project([lng, lat]), centre(i));
		const a = await pos(0);
		await page.mouse.click(a.x, a.y);
		await expect.poll(async () => (await selection(page))?.layer, { timeout: 30_000 }).toBe('crops');
		const card = page.getByRole('region', { name: /^Selected/ });
		await expect(card.getByRole('heading', { name: 'Estimated field' })).toBeVisible();
		await expect(card).toContainText('Canyon County');
		await expect(card).toContainText('Alfalfa');
		await expect(card).toContainText("2025 (USDA's newest)");
		await expect(card).toContainText('Fairly sure');
		await expect(card).toContainText('Corn 2018–2021 → Hay 2022–2025');
		await expect(card.locator('ol.years li')).toHaveCount(8);
		await expect(card).toContainText('USDA NASS Crop Sequence Boundaries');
		await expect.poll(() => page.evaluate(() => location.hash)).toContain(`field=${ids[0]}`);
		await page.screenshot({ path: screenPath('crops-card-z13.5.png') });

		// The middle field is being built, with permits as stored.
		const b = await pos(1);
		await page.mouse.click(b.x, b.y);
		await expect.poll(async () => (await selection(page))?.id).toBe(String(ids[1]));
		await expect(card).toContainText('Being built: 7 new-construction permits since 2022');
		await expect(card).toContainText('Hay 2018–2023 → Pasture 2024 → Built 2025');

		// The link opens the same card, and flies there (a new document, as opening the link is: a hash change alone keeps the page).
		await page.goto('about:blank');
		await page.goto(`/#map=11/43.5/-116.7/0/0&layers=crops&field=${ids[2]}`);
		await mapReady(page);
		await expect.poll(async () => (await selection(page))?.id, { timeout: 60_000 }).toBe(String(ids[2]));
		await expect(page.getByRole('region', { name: /^Selected/ }).getByRole('heading', { name: 'Estimated field' })).toBeVisible();
		await expect.poll(() => page.evaluate(() => (globalThis as any).__tvt.map.getZoom()), { timeout: 30_000 }).toBeGreaterThan(14);
		expect(consoleErrors.filter((e) => !/Failed to load resource/i.test(e))).toEqual([]);
	});

	test('the card API and the tile URL answer, and say so before a field is there', { tag: '@crops' }, async ({ request }) => {
		const year = await (await request.get('/api/farm/year')).json();
		expect(year).toMatchObject({ built: true, year: 2025, first_year: 2018, edition: EDITION });
		const card = await (await request.get(`/api/farm/fields/${ids[0]}`)).json();
		expect(card).toMatchObject({ id: ids[0], county: 'Canyon', growth: 'farmed' });
		expect(card.years).toHaveLength(8);
		expect((await request.get('/api/farm/fields/999999999')).status()).toBe(404);
		expect((await request.get('/api/farm/fields/abc')).status()).toBe(400);
		const meta = await (await request.get('/api/meta')).json();
		const v = meta.versions.layers['farm.crop_fields'];
		expect(v).toMatch(/^e2e-/);
		const tile = await request.get(`/api/farm/tiles/crop_fields/13/1443/2992?v=${v}`);
		expect(tile.status()).toBe(200);
		expect(tile.headers()['content-type']).toBe('application/vnd.mapbox-vector-tile');
		const year2 = await request.get(`/api/farm/tiles/crop_year_2019/9/90/187?v=${v}`);
		expect(year2.status()).toBe(200);
		expect(year2.headers()['etag']).toBe(`"farm.crop_year_2019-${v}-gz"`);
	});
});
