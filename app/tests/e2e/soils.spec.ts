import type { Page } from '@playwright/test';
import { expect, mapReady, screenPath, test } from './fixtures.js';
import { centre, CENTRE, cleanSoils, seedSoils, UNITS, type Seeded } from './soils-seed.js';

/**
 * soils (landscape sprint P1-app): with four SYNTHETIC map units loaded (soils-seed.ts: invented keys, four
 * adjacent rectangles near Meridian, their made-up components and a layer version):
 *
 * - turning the layer on through the URL hash (`layers=soils`) draws the wash in gray steps, and Auto goes Clay;
 * - "Show by" recolours the wash (the property's codes, not hue), and at z9 the wash comes from the map units'
 *   generalised geometry (`/api/soils/tiles/units/9/...`);
 * - a click opens the soil card with its regulatory wording, the mix of components, the restriction, the
 *   hatched dual group and the credit; over the unsurveyed unit the card says "Not surveyed";
 * - the APIs and the tile URL answer, and say so before a unit is there.
 */
/** The wash's gray steps (palette.ts STEPS) and its opacity over Clay's ground. */
const STEPS = ['#d9d9d9', '#bababa', '#999999', '#757575', '#4d4d4d'];
const CLAY = '#f3ede2';
const OPACITY = 0.85;

const hexRgb = (h: string): [number, number, number] => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)) as [number, number, number];
const blend = (fill: string): [number, number, number] => {
	const a = hexRgb(fill);
	const b = hexRgb(CLAY);
	return [0, 1, 2].map((i) => a[i] * OPACITY + b[i] * (1 - OPACITY)) as [number, number, number];
};
const CLASSES: Record<string, [number, number, number]> = { ...Object.fromEntries(STEPS.map((c, i) => [`step${i}`, blend(c)])), clay: hexRgb(CLAY) };
const dist = (a: number[], b: number[]) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
const nearest = (rgb: number[]) => Object.entries(CLASSES).sort((p, q) => dist(rgb, p[1]) - dist(rgb, q[1]))[0][0];

/** The hash that puts the map at a zoom over the middle of the four units. */
const at = (zoom: number, extra = '') => `/#map=${zoom}/${CENTRE[1]}/${CENTRE[0]}/0/0&layers=soils${extra}`;
const info = (page: Page) => page.evaluate(() => (globalThis as any).__tvt.layers);
const soils = (page: Page) => page.evaluate(() => (globalThis as any).__tvtSoils?.info() ?? null);
const layer = (page: Page, id: string) => page.evaluate((id) => (globalThis as any).__tvtSoils?.layer(id) ?? null, id);
const selection = (page: Page) => page.evaluate(() => (globalThis as any).__tvt.layers.selection);

/** A grid of pixels around a lng/lat, read from the canvas inside a render, and the step colour most of them are nearest to. */
const dominant = (page: Page, lngLat: [number, number]) =>
	page
		.evaluate(
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
		)
		.then((samples) => {
			const votes = new Map<string, number>();
			// Ink from the patterns is far from every step: only pixels that are a step (or the ground) vote.
			for (const s of samples) if (dist(s, CLASSES[nearest(s)]) < 14) votes.set(nearest(s), (votes.get(nearest(s)) ?? 0) + 1);
			if (!votes.size) return 'none';
			return [...votes.entries()].sort((a, b) => b[1] - a[1])[0][0];
		});

let seeded: Seeded | null = null;

test.beforeAll(async () => {
	seeded = await seedSoils();
});

test.afterAll(async () => {
	await cleanSoils(seeded);
});

const tile = (z: number, [lng, lat]: [number, number]) => {
	const n = 2 ** z;
	const r = (lat * Math.PI) / 180;
	return { x: Math.floor(((lng + 180) / 360) * n), y: Math.floor(((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * n) };
};

test.describe('soils', () => {
	test('the wash draws in gray steps, Auto goes Clay, and the legend says it is mapped soil', { tag: '@soils' }, async ({ page, consoleErrors, offsite }) => {
		test.setTimeout(300_000);
		await page.goto(at(13.5));
		await mapReady(page);
		await expect.poll(async () => (await soils(page))?.visible, { timeout: 60_000 }).toBe(true);
		// Auto goes Clay while a layer that doesn't keep Valley is on.
		await expect.poll(async () => (await info(page)).flavor).toBe('clay');
		expect((await layer(page, 'soils-fill')).visibility).toBe('visible');
		expect((await soils(page)).by).toBe('restr');
		// By hardpan or bedrock: unit A has none (the palest step), B a hardpan under 25 cm (the darkest), C bedrock at 50-100 cm; D is not rated.
		await expect.poll(() => dominant(page, centre(0)), { timeout: 60_000 }).toBe('step0');
		await expect.poll(() => dominant(page, centre(1))).toBe('step4');
		await expect.poll(() => dominant(page, centre(2))).toBe('step2');
		expect(await dominant(page, centre(3))).toBe('clay'); // NOTCOM: not rated, no fill
		// The legend: one property at a time, every step named, and the wording NRCS asks for.
		const legend = page.getByText('Show by', { exact: true });
		await expect(legend).toBeVisible();
		await expect(page.getByText('Mapped soil, not a site test; not for regulatory decisions').first()).toBeVisible();
		await expect(page.getByText('Hardpan within 50 cm')).toBeVisible();
		await expect(page.getByText('Not surveyed: NRCS has no digital soil data')).toBeVisible();
		await page.screenshot({ path: screenPath('soils-wash-restr-z13.5.png') });
		expect(consoleErrors.filter((e) => !/Failed to load resource/i.test(e))).toEqual([]);
		expect(offsite).toEqual([]);
	});

	test('"Show by" recolours the wash, and at z9 it comes from the map units\' own tiles', { tag: '@soils' }, async ({ page }) => {
		test.setTimeout(300_000);
		await page.goto(at(13.5));
		await mapReady(page);
		await expect.poll(async () => (await soils(page))?.visible, { timeout: 60_000 }).toBe(true);
		await expect.poll(() => dominant(page, centre(0)), { timeout: 60_000 }).toBe('step0');
		const chip = page.locator('button[data-by="drain"]');
		await expect(chip).toBeVisible();
		await chip.click();
		await expect(chip).toHaveAttribute('aria-pressed', 'true');
		expect((await soils(page)).by).toBe('drain');
		// By drainage: A is well drained (1), B poorly drained (4), C excessively drained (0).
		await expect.poll(() => dominant(page, centre(0)), { timeout: 60_000 }).toBe('step1');
		await expect.poll(() => dominant(page, centre(1))).toBe('step4');
		await expect.poll(() => dominant(page, centre(2))).toBe('step0');
		await page.screenshot({ path: screenPath('soils-wash-drain-z13.5.png') });
		// Farmland: A prime (2: the darkest step), B of importance when drained (1), C not prime (0).
		await page.locator('button[data-by="farm"]').click();
		await expect.poll(() => dominant(page, centre(0))).toBe('step4');
		await expect.poll(() => dominant(page, centre(2))).toBe('step0');

		// At z9 the wash is the map units' z8 geometry, from the tiles of the soils layer.
		const t = tile(9, CENTRE);
		const res = page.waitForResponse((r) => new RegExp(`/api/soils/tiles/units/9/${t.x}/${t.y}\\?v=e2e-`).test(r.url()), { timeout: 60_000 });
		await page.evaluate((c) => (globalThis as any).__tvt.map.jumpTo({ zoom: 9.2, center: c }), CENTRE);
		const tileRes = await res;
		expect(tileRes.status()).toBe(200);
		expect(tileRes.headers()['content-type']).toBe('application/vnd.mapbox-vector-tile');
		expect((await tileRes.body()).length).toBeGreaterThan(0);
		expect((await layer(page, 'soils-fill')).minzoom).toBe(9);
		expect((await layer(page, 'soils-survey')).maxzoom).toBe(12);
		await page.screenshot({ path: screenPath('soils-wash-z9.2.png') });
	});

	test('a click opens the soil card with the regulatory wording; the unsurveyed unit says so', { tag: '@soils' }, async ({ page, consoleErrors }) => {
		test.setTimeout(300_000);
		await page.goto(at(13.5));
		await mapReady(page);
		await expect.poll(() => dominant(page, centre(0)), { timeout: 60_000 }).toBe('step0');
		const pos = (i: number) => page.evaluate(([lng, lat]) => (globalThis as any).__tvt.map.project([lng, lat]), centre(i));
		const a = await pos(0);
		await page.mouse.click(a.x, a.y);
		await expect.poll(async () => (await selection(page))?.layer, { timeout: 30_000 }).toBe('soils');
		const card = page.getByRole('region', { name: /^Selected/ });
		await expect(card.getByRole('heading', { name: 'Testville silt loam, 0 to 1 percent slopes' })).toBeVisible();
		await expect(card).toContainText('Mapped soil, not a site test; not for regulatory decisions');
		await expect(card).toContainText('62% Testville silt loam, 38% Samplon fine sandy loam');
		await expect(card).toContainText('Well drained');
		await expect(card).toContainText('None found within the depth NRCS describes');
		await expect(card).toContainText('17.4 cm in the top metre (15 to 20 cm)');
		await expect(card).toContainText("our scaling of NRCS's 150 cm classes to the top metre");
		await expect(card).toContainText('Prime farmland if irrigated');
		await expect(card).toContainText('No (dominant component)');
		await expect(card).toContainText('Synthetic Test Area, Idaho (E2E01), version 24 (2025-09-23), 1:24,000');
		await expect(card).toContainText('Soils: USDA NRCS, Soil Survey Geographic Database (SSURGO)');
		await page.screenshot({ path: screenPath('soils-card-z13.5.png') });

		// The middle unit: a hardpan from 20 cm, drained, and a dual hydrologic group, hatched.
		const b = await pos(1);
		await page.mouse.click(b.x, b.y);
		await expect.poll(async () => (await selection(page))?.id).toBe(UNITS[1].mukey);
		await expect(card).toContainText('Duripan from 20 cm (indurated)');
		await expect(card).toContainText('B/D, D where undrained');
		await expect(card.getByRole('img', { name: /hatched on the map: a dual hydrologic group/ })).toBeVisible();
		await expect(card).toContainText('Partially hydric (dominant component)');
		await page.screenshot({ path: screenPath('soils-card-hardpan-z13.5.png') });

		// NRCS's "No Digital Data Available": not surveyed, and no soil facts.
		// (The card sits over the right of the map: bring the unit to the middle first.)
		await page.evaluate((c) => (globalThis as any).__tvt.map.jumpTo({ zoom: 13.5, center: c }), centre(3));
		await mapReady(page);
		await expect.poll(() => dominant(page, centre(3)), { timeout: 60_000 }).toBe('clay');
		const d = await pos(3);
		await page.mouse.click(d.x, d.y);
		await expect.poll(async () => (await selection(page))?.id).toBe(UNITS[3].mukey);
		await expect(card.getByRole('heading', { name: 'Not surveyed' })).toBeVisible();
		await expect(card).toContainText('Not surveyed: NRCS has no digital soil data');
		await expect(card).toContainText('Mapped soil, not a site test; not for regulatory decisions');
		await expect(card).not.toContainText('Main soil');
		expect(consoleErrors.filter((e) => !/Failed to load resource/i.test(e))).toEqual([]);
	});

	test('the APIs and the tile URL answer, and say so before a unit is there', { tag: '@soils' }, async ({ request }) => {
		const [lng, lat] = centre(0);
		const hit = await (await request.get(`/api/soils/at?lng=${lng}&lat=${lat}`)).json();
		expect(hit).toEqual({ unit: { mukey: UNITS[0].mukey, symbol: 'TeA', name: UNITS[0].muname, surveyed: true } });
		const notcom = await (await request.get(`/api/soils/at?lng=${centre(3)[0]}&lat=${centre(3)[1]}`)).json();
		expect(notcom.unit).toMatchObject({ mukey: UNITS[3].mukey, surveyed: false });
		expect(await (await request.get('/api/soils/at?lng=-100&lat=40')).json()).toEqual({ unit: null }); // outside the survey
		expect((await request.get('/api/soils/at?lng=x&lat=40')).status()).toBe(400);
		const card = await (await request.get(`/api/soils/mapunit/${UNITS[1].mukey}`)).json();
		expect(card).toMatchObject({ mukey: UNITS[1].mukey, surveyed: true, hydrologic_group: 'B/D', hydrologic_dual: true, restriction: { kind: 'Duripan', top_cm: 20 }, mix: null });
		expect(card.note).toBe('Mapped soil, not a site test; not for regulatory decisions');
		expect((await request.get('/api/soils/mapunit/999999999')).status()).toBe(404);
		expect((await request.get('/api/soils/mapunit/abc')).status()).toBe(400);
		const meta = await (await request.get('/api/meta')).json();
		const v = meta.versions.layers['soils.units'];
		expect(v).toMatch(/^e2e-/);
		const t13 = tile(13, CENTRE);
		const z13 = await request.get(`/api/soils/tiles/units/13/${t13.x}/${t13.y}?v=${v}`);
		expect(z13.status()).toBe(200);
		expect(z13.headers()['content-type']).toBe('application/vnd.mapbox-vector-tile');
		expect(z13.headers()['etag']).toBe(`"soils.units-${v}-gz"`);
		expect((await z13.body()).length).toBeGreaterThan(50);
		// z8 carries the survey bounds only (the wash comes in at z9): non-empty but far smaller than z13's units.
		const t8 = tile(8, CENTRE);
		const z8 = await request.get(`/api/soils/tiles/units/8/${t8.x}/${t8.y}?v=${v}`);
		expect(z8.status()).toBe(200);
		expect((await z8.body()).length).toBeGreaterThan(0);
		expect((await request.get(`/api/soils/tiles/units/15/0/0?v=${v}`)).status()).toBe(404);
	});
});
