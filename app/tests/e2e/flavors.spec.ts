import type { Page } from '@playwright/test';
import { appendFileSync, writeFileSync } from 'node:fs';
import { expect, mapReady, screenPath, seeds, test } from './fixtures.js';

/**
 * flavors (docs/14 §14.10, WP4 acceptance; §14.3 "Base", §14.5): the Valley
 * and Clay base flavors, Auto clay, the 350 ms crossfade (and a drape that
 * follows it with terrain on), Clay's hidden labels, a mode drawing the Map
 * look, the stepped speed ramp switching to slate with Transit and back with
 * no road tile fetched again, and the screenshot matrix's views 1–5 (§14.11)
 * at 1280×800 and 390×844 for review.
 *
 * The unit tests (color, flavors, ramp) check the numbers against the doc's
 * tables: the ghost column within ΔE 1, clayPaintDiff covering every changed
 * layer with the exact hidden set, and the ramp stops.
 */

type Info = { enabled: string[]; status: Record<string, string>; clay: boolean; flavor: 'valley' | 'clay' };

const info = (page: Page): Promise<Info> => page.evaluate(() => (globalThis as any).__tvt.layers);
const toolbar = (page: Page) => page.getByRole('toolbar', { name: 'Map layers' });
const paint = (page: Page, layer: string, prop: string) => page.evaluate(([l, p]) => (globalThis as any).__tvt.map.getPaintProperty(l, p), [layer, prop]);
const vis = (page: Page, id: string) => page.evaluate((id) => (globalThis as any).__tvt.map.getLayoutProperty(id, 'visibility') ?? 'visible', id);
/** The 3D buildings' opacity, measured and estimated (always the same). */
const buildingOpacities = (page: Page) => Promise.all(['buildings-3d', 'buildings-3d-estimated'].map((l) => paint(page, l, 'fill-extrusion-opacity')));
/** Whether each 3D building layer draws something in view, and only its own kind (with a height, or without). */
const drawnBuildings = (page: Page) =>
	page.evaluate(() => {
		const map = (globalThis as any).__tvt.map;
		const kinds = (id: string) => map.queryRenderedFeatures({ layers: [id] }).map((f: any) => f.properties.height !== undefined);
		const measured: boolean[] = kinds('buildings-3d');
		const estimated: boolean[] = kinds('buildings-3d-estimated');
		return { measured: measured.length > 0 && measured.every(Boolean), estimated: estimated.length > 0 && !estimated.some(Boolean) };
	});
const view = (page: Page) =>
	page.evaluate(() => {
		const m = (globalThis as any).__tvt.map;
		const c = m.getCenter();
		return { lng: c.lng, lat: c.lat, zoom: m.getZoom(), bearing: m.getBearing(), pitch: m.getPitch() };
	});

/** Clay's hidden basemap labels (docs/14 §14.5). */
const CLAY_HIDDEN = ['address_label', 'pois', 'roads_oneway', 'roads_labels_minor', 'roads_shields'];
const GROUND = { valley: '#eee7da', clay: '#f3ede2' };

/** Every layer loaded (the first idle prefetches the ones that are off). */
async function allLoaded(page: Page) {
	await expect.poll(async () => Object.values((await info(page)).status).every((s) => s === 'ready' || s === 'stale'), { timeout: 90_000 }).toBe(true);
}

/** One pixel of the drawn map (read inside a render, while the drawing buffer is valid). */
const pixel = (page: Page, x: number, y: number) =>
	page.evaluate(
		([x, y]) =>
			new Promise<number[]>((resolve) => {
				const map = (globalThis as any).__tvt.map;
				map.once('render', () => {
					const gl = map.getCanvas().getContext('webgl2') as WebGL2RenderingContext;
					const k = gl.drawingBufferWidth / map.getCanvas().clientWidth;
					const out = new Uint8Array(4);
					gl.readPixels(Math.round(x * k), Math.round(gl.drawingBufferHeight - y * k), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, out);
					resolve([...out.slice(0, 3)]);
				});
				map.triggerRepaint();
			}),
		[x, y]
	);

/** Spots where only the ground is drawn (no road, park, water or label within 6 px). DOM panels don't matter: pixels are read from the canvas. */
const groundSpots = (page: Page) =>
	page.evaluate(() => {
		const map = (globalThis as any).__tvt.map;
		const c = map.getCanvas();
		const out: { x: number; y: number }[] = [];
		for (let y = 40; y < c.clientHeight - 40 && out.length < 12; y += 7)
			for (let x = 40; x < c.clientWidth - 40 && out.length < 12; x += 7) {
				const f = map.queryRenderedFeatures([[x - 6, y - 6], [x + 6, y + 6]]);
				if (f.length && f.every((g: any) => g.layer.id === 'earth')) out.push({ x, y });
			}
		return out;
	});

/** Render timestamps from now on (ms since the mark), for the frame-time check. */
const startFrameLog = (page: Page) =>
	page.evaluate(() => {
		const map = (globalThis as any).__tvt.map;
		const g = globalThis as any;
		g.__wp4frames = [];
		g.__wp4t0 = performance.now();
		g.__wp4log = () => g.__wp4frames.push(performance.now() - g.__wp4t0);
		map.on('render', g.__wp4log);
	});
const stopFrameLog = (page: Page): Promise<number[]> =>
	page.evaluate(() => {
		const g = globalThis as any;
		g.__tvt.map.off('render', g.__wp4log);
		return g.__wp4frames as number[];
	});

function frameReport(label: string, frames: number[]) {
	// The crossfade's window: 350 ms plus the drape keeper's 100 ms, from the input.
	const fade = frames.filter((t) => t <= 450);
	const gaps = fade.map((t, i) => t - (i ? fade[i - 1] : 0));
	const line = `${label}: ${fade.length} frames in the first 450 ms after the input (${frames.length} in all), at ${fade.map((t) => t.toFixed(0)).join(', ')} ms; largest gap there ${Math.max(0, ...gaps).toFixed(0)} ms (SwiftShader defers GPU work, so these say little about a real GPU)`;
	test.info().annotations.push({ type: 'crossfade frames', description: line });
	appendFileSync(screenPath('wp4-crossfade.txt'), `${new Date().toISOString()} ${line}\n`);
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

test.describe('flavors', () => {
	test('Auto: Clay while a data layer is on, Map with none; Clay hides its five label layers; a 350 ms crossfade', { tag: '@wp4' }, async ({ page, consoleErrors, offsite }) => {
		test.setTimeout(300_000);
		await page.goto('/#map=13/43.615/-116.2023/0/30&layers=none');
		await mapReady(page);
		expect((await info(page)).flavor).toBe('valley');
		expect(await paint(page, 'earth', 'fill-color')).toBe(GROUND.valley);
		expect(await paint(page, 'water', 'fill-color')).toBe('#7cc4e4');
		expect(await paint(page, 'hillshade', 'hillshade-exaggeration')).toBe(0.3);
		expect(await paint(page, 'hillshade', 'hillshade-shadow-color')).toBe('#7a6e60');
		for (const id of CLAY_HIDDEN) expect(await vis(page, id), id).toBe('visible');
		expect(await page.evaluate(() => (globalThis as any).__tvt.map.getLayersOrder().filter((id: string) => id.includes('wash')))).toEqual([]);

		await startFrameLog(page);
		await page.keyboard.press('7');
		await expect.poll(async () => (await info(page)).flavor).toBe('clay');
		expect((await info(page)).clay).toBe(true);
		expect(await paint(page, 'earth', 'fill-color')).toBe(GROUND.clay);
		expect(await paint(page, 'earth', 'fill-color-transition')).toEqual({ duration: 350, delay: 0 });
		expect(await paint(page, 'water', 'fill-color')).toBe('#c9dce3');
		expect(await paint(page, 'hillshade', 'hillshade-exaggeration')).toBe(0.22);
		expect(await paint(page, 'hillshade', 'hillshade-highlight-color')).toBe('#fffbf4');
		for (const id of CLAY_HIDDEN) expect(await vis(page, id), `${id} in Clay`).toBe('none');
		// The other labels stay.
		for (const id of ['places_locality', 'roads_labels_major']) expect(await vis(page, id), id).toBe('visible');
		await mapReady(page);
		frameReport('Map → Clay (Cameras on)', await stopFrameLog(page));
		await page.screenshot({ path: screenPath('wp4-auto-clay.png') });

		// None on again: back to the Map look, labels back.
		await page.keyboard.press('7');
		await expect.poll(async () => (await info(page)).flavor).toBe('valley');
		expect(await paint(page, 'earth', 'fill-color')).toBe(GROUND.valley);
		for (const id of CLAY_HIDDEN) expect(await vis(page, id), `${id} in Valley`).toBe('visible');
		await mapReady(page);

		// Reduced motion: the switch is instant.
		await page.emulateMedia({ reducedMotion: 'reduce' });
		await page.keyboard.press('7');
		await expect.poll(async () => (await info(page)).flavor).toBe('clay');
		expect(await paint(page, 'earth', 'fill-color-transition')).toEqual({ duration: 0, delay: 0 });
		await mapReady(page);
		expect(consoleErrors).toEqual([]);
		expect(offsite).toEqual([]);
	});

	test('with terrain on, the drape is redrawn through the crossfade and ends at the new flavor without the map moving', { tag: '@wp4' }, async ({ page }) => {
		test.setTimeout(300_000);
		// Labels "fewer", so switching hides or shows no label layer.
		await page.addInitScript(() => {
			if (sessionStorage.getItem('wp4-seeded')) return;
			localStorage.setItem('tvt:v2:base', JSON.stringify({ look: 'map', buildings: true, terrain: true, labels: 'fewer' }));
			sessionStorage.setItem('wp4-seeded', '1');
		});
		await page.goto('/#map=13/43.615/-116.2023/0/0&layers=none');
		await mapReady(page);
		// The prefetched layers mount (hidden) first, so their style changes don't land in the counts below.
		await allLoaded(page);
		await mapReady(page);
		expect(await page.evaluate(() => Boolean((globalThis as any).__tvt.map.getTerrain()))).toBe(true);
		expect((await info(page)).flavor).toBe('valley');
		const spots = await groundSpots(page);
		expect(spots.length, 'ground-only spots in view').toBeGreaterThan(2);
		const at = spots[Math.floor(spots.length / 2)];
		const v0 = await view(page);
		const p0 = await pixel(page, at.x, at.y);

		await toolbar(page).getByRole('button', { name: 'Base' }).click();
		const pop = page.getByRole('dialog', { name: 'Base map' });
		// Count releases of the terrain's cached drape textures (MapLibre's own, once per style
		// change, and the drape keeper's, once per frame of the crossfade).
		await page.evaluate(() => {
			const g = globalThis as any;
			const tm = g.__tvt.map.terrain.tileManager;
			const orig = tm.releaseAllRTT.bind(tm);
			g.__wp4releases = [];
			tm.releaseAllRTT = () => {
				g.__wp4releases.push(performance.now() - g.__wp4t0);
				return orig();
			};
		});
		await startFrameLog(page);
		await pop.getByRole('radio', { name: 'Clay' }).check();
		// The map can't go idle while the keeper asks for frames, so after this it has let go.
		await mapReady(page);
		const releases: number[] = await page.evaluate(() => [...(globalThis as any).__wp4releases]);
		await page.waitForTimeout(2500);
		const later: number[] = await page.evaluate(() => (globalThis as any).__wp4releases.slice());
		frameReport('Map → Clay (Base popover)', await stopFrameLog(page));
		appendFileSync(screenPath('wp4-crossfade.txt'), `${new Date().toISOString()} drape releases (ms after the input): ${releases.map((t) => t.toFixed(0)).join(', ')}\n`);
		// Through the fade: the keeper's first release, one per frame, and MapLibre's own (without the keeper, only MapLibre's).
		expect(releases.length, `drape releases during the fade: ${releases.map((t) => t.toFixed(0))}`).toBeGreaterThanOrEqual(3);
		// Then it lets go: no more once the map is idle.
		expect(later.length - releases.length, 'drape releases after the fade').toBe(0);
		const p1 = await pixel(page, at.x, at.y);
		expect(Math.max(...p1.map((c, i) => Math.abs(c - p0[i]))), `the ground went clay: ${p0} → ${p1}`).toBeGreaterThan(3);
		// Clay's ground is paler than Valley's.
		expect(p1.reduce((a, b) => a + b)).toBeGreaterThan(p0.reduce((a, b) => a + b));

		await pop.getByRole('radio', { name: 'Map' }).check();
		await mapReady(page);
		await page.waitForTimeout(500);
		const p2 = await pixel(page, at.x, at.y);
		for (let k = 0; k < 3; k++) expect(Math.abs(p2[k] - p0[k]), `back to the Map look without moving: ${p0} → ${p2}`).toBeLessThanOrEqual(2);
		const v1 = await view(page);
		expect(v1.zoom).toBeCloseTo(v0.zoom, 6);
		expect(v1.lng).toBeCloseTo(v0.lng, 9);
	});

	test('with Streets on, toggling Transit switches the ramp with 0 road tile requests', { tag: '@wp4' }, async ({ page, consoleErrors }) => {
		test.setTimeout(400_000);
		// Road tiles are fetched by MapLibre's worker: Playwright's request events hear those (the
		// page's own DevTools session doesn't), so they do the counting here.
		const roads: string[] = [];
		page.context().on('request', (r) => {
			if (r.url().includes('/api/tiles/roads/')) roads.push(r.url());
		});
		// Fairview Ave at Five Mile Rd: arterials of 35–45 mph among 20–25 mph local streets.
		await page.goto('/#map=14/43.6195/-116.3143/0/0&layers=streets');
		await mapReady(page);
		await allLoaded(page);
		await mapReady(page);
		const atLoad = roads.length;
		expect(atLoad, 'road tile requests heard at load (so a zero below means something)').toBeGreaterThan(0);
		expect((await info(page)).flavor).toBe('clay');
		const legend = page.getByRole('region', { name: 'Streets legend' });
		const ramp = legend.getByRole('img', { name: /Posted speed/ });
		// Turning Transit on expands its legend and folds the others to a row: open the Streets one.
		const openLegend = async () => {
			const row = legend.locator('button.row');
			if ((await row.getAttribute('aria-expanded')) !== 'true') await row.click();
			await expect(row).toHaveAttribute('aria-expanded', 'true');
		};
		const drawn = (layer: string) =>
			page.evaluate((layer) => {
				const map = (globalThis as any).__tvt.map;
				const c = map.getCanvas();
				return map.queryRenderedFeatures([[0, 0], [c.clientWidth, c.clientHeight]], { layers: [layer] }).length;
			}, layer);

		// Transit off: the blue ramp.
		expect([await vis(page, 'streets-speed'), await vis(page, 'streets-speed-under')]).toEqual(['visible', 'none']);
		expect([await vis(page, 'streets-casing'), await vis(page, 'streets-casing-under')]).toEqual(['visible', 'none']);
		expect(await drawn('streets-speed')).toBeGreaterThan(50);
		await expect(ramp).toHaveAttribute('data-ramp', 'alone');
		await expect(legend.getByText('Dimmed while Transit is on')).toHaveCount(0);
		await legend.screenshot({ path: screenPath('wp4-legend-alone.png') });
		const colorAlone = JSON.stringify(await paint(page, 'streets-speed', 'line-color'));
		expect(colorAlone).toContain('"interpolate-lab"');
		expect(colorAlone).toContain('"#9fc2f0"');
		expect(colorAlone).toContain('"#062d59"');
		await page.screenshot({ path: screenPath('wp4-streets-alone.png') });

		const mark = roads.length;
		await page.keyboard.press('4');
		await mapReady(page);
		// Transit on: the slate ramp, 70% width, legend says so.
		expect([await vis(page, 'streets-speed'), await vis(page, 'streets-speed-under')]).toEqual(['none', 'visible']);
		expect([await vis(page, 'streets-casing'), await vis(page, 'streets-casing-under')]).toEqual(['none', 'visible']);
		expect(await drawn('streets-speed-under')).toBeGreaterThan(50);
		expect(await drawn('streets-speed')).toBe(0);
		const colorUnder = JSON.stringify(await paint(page, 'streets-speed-under', 'line-color'));
		expect(colorUnder).toContain('"#c3cfdf"');
		expect(colorUnder).toContain('"#657284"');
		expect(colorUnder).not.toContain('"#2a78d6"');
		await openLegend();
		await expect(ramp).toHaveAttribute('data-ramp', 'under');
		await expect(legend.getByText('Dimmed while Transit is on; speeds approximate')).toBeVisible();
		await legend.screenshot({ path: screenPath('wp4-legend-under.png') });
		await page.screenshot({ path: screenPath('wp4-streets-under-transit.png') });

		await page.keyboard.press('4');
		await mapReady(page);
		expect([await vis(page, 'streets-speed'), await vis(page, 'streets-speed-under')]).toEqual(['visible', 'none']);
		await openLegend();
		await expect(ramp).toHaveAttribute('data-ramp', 'alone');
		await page.keyboard.press('4');
		await mapReady(page);
		expect(await vis(page, 'streets-speed-under')).toBe('visible');
		const during = roads.slice(mark);
		writeFileSync(screenPath('wp4-ramp-switch.txt'), `road tile requests at load: ${atLoad}; over 3 Transit toggles with Streets on: ${during.length}\n`);
		expect(during, 'road tile requests while toggling Transit').toEqual([]);
		expect(consoleErrors).toEqual([]);
	});

	test('the road card shows the exact speed with the shade drawn now', { tag: '@wp4' }, async ({ page }) => {
		test.setTimeout(300_000);
		await page.goto('/#map=16/43.6195/-116.3143/0/0&layers=streets,transit');
		await mapReady(page);
		await allLoaded(page);
		await mapReady(page);
		// A road drawn on the slate ramp, away from routes and stops.
		const spot = await page.evaluate(() => {
			const map = (globalThis as any).__tvt.map;
			const c = map.getCanvas();
			for (let y = 200; y < c.clientHeight - 200; y += 8)
				for (let x = 360; x < c.clientWidth - 440; x += 8) {
					const r = map.queryRenderedFeatures([[x - 2, y - 2], [x + 2, y + 2]], { layers: ['streets-speed-under'] });
					if (!r.length || !r[0].properties.speed) continue;
					const busy = map.queryRenderedFeatures([[x - 18, y - 18], [x + 18, y + 18]]).some((f: any) => /^(transit|cameras|cones)/.test(f.layer.id));
					if (!busy) return { x, y, speed: r[0].properties.speed as number };
				}
			return null;
		});
		expect(spot, 'a slate road in view').not.toBeNull();
		await page.mouse.click(spot!.x, spot!.y);
		const card = page.getByRole('region', { name: 'Selected road' });
		await expect(card).toBeVisible();
		await expect(card.locator('.speed-sign .num')).toHaveText(String(spot!.speed));
		// "Collector · Boise", never "Collector·Boise".
		await expect(card.locator('.meta')).not.toContainText(/\S·|·\S/);
		const swatch = await card.locator('.swatch').evaluate((el) => getComputedStyle(el).backgroundColor);
		// The slate ramp (§14.5), as the swatch's computed color; 20 mph and under share the first shade.
		const slate = ['#c3cfdf', '#b2c4db', '#a2b8d5', '#94adcd', '#87a1c3', '#7d96b6', '#748aa7', '#6d7f97', '#6a7b91', '#68788c', '#657284'];
		const stops = [20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 75];
		const hex = slate[stops.indexOf(Math.max(20, spot!.speed))];
		const rgb = `rgb(${[1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)).join(', ')})`;
		expect(swatch, `${spot!.speed} mph on the slate ramp`).toBe(rgb);
		await card.screenshot({ path: screenPath('wp4-road-card.png') });
	});

	test('the Base popover: Map, Clay and Auto; the photo muted in Clay; buildings follow', { tag: '@wp4' }, async ({ page }) => {
		test.setTimeout(300_000);
		await page.goto('/#map=15/43.6152/-116.2035/-12/50&layers=none');
		await mapReady(page);
		await toolbar(page).getByRole('button', { name: 'Base' }).click();
		const pop = page.getByRole('dialog', { name: 'Base map' });
		await expect(pop.getByText('Now Map: no data layer is on')).toBeVisible();
		expect(await paint(page, 'buildings-3d', 'fill-extrusion-color')).toBe('#f8f4ec');
		expect(await paint(page, 'buildings-3d', 'fill-extrusion-opacity')).toBe(0.9);
		// Buildings without a height stand at an estimate, a lighter tone (the height floor, Oct 7).
		expect(await paint(page, 'buildings-3d-estimated', 'fill-extrusion-color')).toBe('#ffffff');
		expect(await buildingOpacities(page)).toEqual([0.9, 0.9]);
		expect(await drawnBuildings(page), 'downtown has both measured and estimated buildings in view').toEqual({ measured: true, estimated: true });
		await pop.getByRole('radio', { name: 'Clay' }).check();
		expect((await info(page)).flavor).toBe('clay');
		await expect(pop.getByText('Clay, whatever is on')).toBeVisible();
		await expect(pop.getByText('Clay leaves out addresses, places of interest and minor street names')).toBeVisible();
		expect(await paint(page, 'buildings-3d', 'fill-extrusion-color')).toBe('#efe9df');
		expect(await paint(page, 'buildings-3d-estimated', 'fill-extrusion-color')).toBe('#f7f4ef');
		expect(await buildingOpacities(page)).toEqual([0.55, 0.55]);
		await mapReady(page);
		await page.screenshot({ path: screenPath('wp4-base-popover-clay.png') });
		// Aerial in Clay: the photo muted, buildings see-through.
		await pop.getByRole('switch', { name: /Aerial photos/ }).check();
		await expect(pop.getByText('NAIP, muted in Clay')).toBeVisible();
		expect(await paint(page, 'aerial', 'raster-saturation')).toBe(-0.7);
		expect(await buildingOpacities(page)).toEqual([0.3, 0.3]);
		await mapReady(page);
		await page.screenshot({ path: screenPath('wp4-aerial-clay.png') });
		await pop.getByRole('radio', { name: 'Map' }).check();
		expect(await paint(page, 'aerial', 'raster-saturation')).toBe(0);
		expect(await buildingOpacities(page)).toEqual([0.3, 0.3]);
		await pop.getByRole('switch', { name: /Aerial photos/ }).uncheck();
		expect(await buildingOpacities(page)).toEqual([0.9, 0.9]);
		await pop.getByRole('radio', { name: 'Auto' }).check();
		await expect(pop.getByText('Now Map: no data layer is on')).toBeVisible();
		await page.keyboard.press('Escape');
		await page.keyboard.press('4');
		await expect.poll(async () => (await info(page)).flavor).toBe('clay');
		// Let Transit's first draw settle: under a loaded SwiftShader the page can starve the
		// animation frames Playwright's click waits on.
		await mapReady(page);
		await toolbar(page).getByRole('button', { name: 'Base' }).click();
		await expect(pop.getByText('Now Clay: a data layer is on')).toBeVisible();
	});

	test('a mode keeps the flavor it found and shows the photo in full color; leaving mutes it again', { tag: '@wp4' }, async ({ page }) => {
		test.setTimeout(300_000);
		const key = seeds().seeds.find((s) => s.kind === 'key')!;
		await page.goto('/#map=14/43.6/-116.3/0/30&layers=transit,cameras');
		await mapReady(page);
		expect((await info(page)).flavor).toBe('clay');
		const ids = await page.evaluate(() => (globalThis as any).__tvt.map.getLayersOrder());
		await follow(page, `/calibrate/${key.cameraId}`);
		await page.waitForURL(/\/calibrate\//);
		await mapReady(page);
		expect(await page.evaluate(() => (globalThis as any).__tvt.mode)).toBe('calibrate');
		// No basemap re-layout in a mode (it would drop the tiles the way back needs): Clay stays,
		// labels as they were, but the calibrator's photo isn't muted.
		expect((await info(page)).flavor).toBe('clay');
		expect(await paint(page, 'earth', 'fill-color')).toBe(GROUND.clay);
		for (const id of CLAY_HIDDEN) expect(await vis(page, id)).toBe('none');
		expect(await vis(page, 'aerial')).toBe('visible');
		expect(await paint(page, 'aerial', 'raster-saturation')).toBe(0);
		await page.screenshot({ path: screenPath('wp4-calibrate-photo.png') });
		await page.goBack();
		await page.waitForURL((u) => !u.pathname.startsWith('/calibrate'));
		await mapReady(page);
		expect(await page.evaluate(() => (globalThis as any).__tvt.mode)).toBe('explore');
		expect((await info(page)).flavor).toBe('clay');
		expect(await paint(page, 'earth', 'fill-color')).toBe(GROUND.clay);
		for (const id of CLAY_HIDDEN) expect(await vis(page, id)).toBe('none');
		// Aerial off again, and muted again for when it's next on in Clay.
		expect(await vis(page, 'aerial')).toBe('none');
		expect(await paint(page, 'aerial', 'raster-saturation')).toBe(-0.7);
		// Flavors add no layers: the style holds the same ones, plus the aerial layers calibrating added
		// and the 3D scene's one layer, which Transit asks for from z14.5 (WP10; the calibrator is at z19).
		const after = await page.evaluate(() => (globalThis as any).__tvt.map.getLayersOrder());
		expect(after.filter((id: string) => !ids.includes(id) && !id.startsWith('aerial') && id !== 'scene-3d')).toEqual([]);
		expect(ids.filter((id: string) => !after.includes(id))).toEqual([]);
	});

	test('screenshots of views 1–5 (§14.11) at 1280×800 and 390×844', { tag: '@wp4' }, async ({ page, consoleErrors }) => {
		test.setTimeout(1_200_000);
		const views = [
			{ n: 1, name: 'downtown hub, z15, Transit only', hash: '#map=15/43.6155/-116.2037/-12/45&layers=transit', flavor: 'clay', ramp: null },
			{ n: 2, name: 'Fairview and Five Mile, z14, Transit and Streets', hash: '#map=14/43.6195/-116.3143/-12/45&layers=transit,streets', flavor: 'clay', ramp: 'under' },
			{ n: 3, name: 'Eagle Rd, z16, every layer', hash: '#map=16/43.6195/-116.3545/-12/50&layers=transit,streets,cameras', flavor: 'clay', ramp: 'under' },
			{ n: 4, name: 'valley overview, z11, every layer', hash: '#map=11/43.6/-116.45/0/0&layers=transit,streets,cameras', flavor: 'clay', ramp: 'under' },
			{ n: 5, name: 'view 4 with Clay off', hash: '#map=11/43.6/-116.45/0/0&layers=transit,streets,cameras', flavor: 'valley', ramp: 'under', look: 'map' }
		] as const;
		const lines: string[] = [];
		for (const size of [
			{ width: 1280, height: 800 },
			{ width: 390, height: 844 }
		]) {
			await page.setViewportSize(size);
			for (const v of views) {
				const look = 'look' in v ? v.look : 'auto';
				// The saved Base look, set on a page of the same origin that doesn't start the map.
				await page.goto('/api/health');
				await page.evaluate((look) => localStorage.setItem('tvt:v2:base', JSON.stringify({ look, buildings: true, terrain: true, labels: 'full' })), look);
				await page.goto(`/${v.hash}`);
				await mapReady(page);
				await allLoaded(page);
				await mapReady(page);
				const i = await info(page);
				expect(i.flavor, `view ${v.n} flavor`).toBe(v.flavor);
				if (v.ramp) expect(await vis(page, v.ramp === 'under' ? 'streets-speed-under' : 'streets-speed'), `view ${v.n} ramp`).toBe('visible');
				// The "Building the valley…" card fades out over 500 ms after the first idle.
				await expect(page.getByText('Building the valley…')).toHaveCount(0);
				const file = `wp4-view${v.n}-${size.width}x${size.height}.png`;
				await page.screenshot({ path: screenPath(file) });
				lines.push(`${file}: view ${v.n}, ${v.name}; flavor ${i.flavor}; layers ${i.enabled.join(',')}`);
			}
		}
		// MapLibre's tile errors (create.ts logs them as "map error") are recorded, not failed on: under
		// the shared sandbox's load a basemap or terrain range fetch now and then fails in transport
		// ("Failed to fetch", "could not be decoded"), which no WP4 code touches. Anything else fails.
		const mapErrors = consoleErrors.filter((e) => e.startsWith('map error'));
		lines.push(`MapLibre tile errors during the run: ${mapErrors.length}`, ...mapErrors.map((e) => `  ${e.slice(0, 300)}`));
		writeFileSync(screenPath('wp4-views.txt'), lines.join('\n') + '\n');
		if (mapErrors.length) test.info().annotations.push({ type: 'map errors', description: mapErrors.join(' | ') });
		expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
		expect(consoleErrors.filter((e) => !e.startsWith('map error'))).toEqual([]);
	});
});
