import type { Page } from '@playwright/test';
import { expect, mapReady, screenPath, test } from './fixtures.js';

/**
 * roads (P9; plan v3 §3.2 b6-b7 and slot 5, §3.4 K11, §3.5): roads at real width from the bake, on the
 * synthetic landscape file (basemap/landscape/fixture.py: two crossing streets, a service way, an alley, a
 * junction, an island, a median, curbs and markings near -116.2025, 43.615). Run it with the fixture:
 *
 *   TILES_DIR=$(node scripts/tiles-fixture.mjs --ground painted) npm run test:e2e -- --grep @roads
 *
 * - the piece lines draw from z14 and hide Protomaps' road lines from there. (That this happens only once
 *   built is the unit test's: the manifest is read on the server, so a spec can't serve the app another one.)
 * - the K11 fade: at z15.5-16 the road's centre is road-toned at every step, never the ground showing through;
 * - markings show in Valley, not in Clay (and not under Aerial) without Lanes on. (There is no Lanes layer to
 *   turn on yet, so the with-Lanes cases are the unit test's: `markingsShown`.)
 * - the draped run stays one stack (rttStacks 1) at z14, z15.5 and z17.
 */

const CENTRE: [number, number] = [-116.2025, 43.615];
const at = (zoom: number) => `/#map=${zoom}/${CENTRE[1]}/${CENTRE[0]}/0/0&layers=none`;
const ROAD_LINES = ['roads_major', 'roads_minor_service', 'roads_other'];

const layerOn = (page: Page, id: string) =>
	page.evaluate((id) => {
		const map = (globalThis as any).__tvt.map;
		const l = map.getLayer(id);
		return !!l && map.getLayoutProperty(id, 'visibility') !== 'none';
	}, id);
const zoomRange = (page: Page, id: string) =>
	page.evaluate((id) => {
		const l = (globalThis as any).__tvt.map.getLayer(id);
		return l ? { min: l.minzoom as number, max: l.maxzoom as number } : null;
	}, id);
const jump = async (page: Page, zoom: number) => {
	await page.evaluate(([z, c]) => (globalThis as any).__tvt.map.jumpTo({ zoom: z, center: c, bearing: 0, pitch: 0 }), [zoom, CENTRE] as const);
	await mapReady(page);
};
const rendered = (page: Page, layers: string[]) =>
	page.evaluate((layers) => (globalThis as any).__tvt.map.queryRenderedFeatures({ layers: layers.filter((l) => (globalThis as any).__tvt.map.getLayer(l)) }).length as number, layers);

/** Draped runs in the live style, as rttStacks counts them. */
const liveRuns = (page: Page) =>
	page.evaluate(() => {
		const map = (globalThis as any).__tvt.map;
		const z = map.getZoom();
		const draped = new Set(['background', 'fill', 'line', 'raster', 'hillshade', 'color-relief']);
		const runs: string[][] = [];
		let open = false;
		for (const id of map.getLayersOrder() as string[]) {
			const l = map.getLayer(id);
			if (map.getLayoutProperty(id, 'visibility') === 'none') continue;
			if ((l.minzoom && z < l.minzoom) || (l.maxzoom && z >= l.maxzoom)) continue;
			if (draped.has(l.type)) {
				if (!open) runs.push([]);
				runs[runs.length - 1].push(id);
				open = true;
			} else open = false;
		}
		return runs;
	});

/**
 * The darkest of a short vertical run of pixels around a lng/lat (read inside a render, while the drawing buffer is
 * valid). The run, not one pixel, because the road's drawn centre can sit a few pixels off the projected point
 * (map padding), and a street is 8-10 px wide at these zooms.
 */
const darkestAround = (page: Page, lngLat: [number, number]) =>
	page.evaluate(
		(ll) =>
			new Promise<number[]>((resolve) => {
				const map = (globalThis as any).__tvt.map;
				map.once('render', () => {
					const p = map.project(ll);
					const gl = map.getCanvas().getContext('webgl2') as WebGL2RenderingContext;
					const k = gl.drawingBufferWidth / map.getCanvas().clientWidth;
					let best: number[] = [255, 255, 255];
					for (let dy = -24; dy <= 24; dy += 2) {
						const out = new Uint8Array(4);
						gl.readPixels(Math.round(p.x * k), Math.round(gl.drawingBufferHeight - (p.y + dy) * k), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, out);
						if (out[0] < best[0]) best = [...out.slice(0, 3)];
					}
					resolve(best);
				});
				map.triggerRepaint();
			}),
		lngLat
	);

test.describe('roads at real width', () => {
	test('the piece lines draw from z14 and hide Protomaps’ road lines from there', { tag: '@roads' }, async ({ page, consoleErrors }) => {
		test.setTimeout(240_000);
		await page.goto(at(14.5));
		await mapReady(page);
		expect(await layerOn(page, 'roads.lines.line')).toBe(true);
		expect(await zoomRange(page, 'roads.lines.line')).toEqual({ min: 14, max: 16 });
		let hidden = 0;
		for (const id of ROAD_LINES) {
			const r = await zoomRange(page, id);
			if (!r) continue;
			hidden++;
			expect(r.max, `${id} stops at z14`).toBeLessThanOrEqual(14);
		}
		expect(hidden, 'Protomaps road layers found').toBeGreaterThan(0);
		await jump(page, 14.5);
		expect(await rendered(page, ['roads.lines.line']), 'the piece lines are drawn at z14.5').toBeGreaterThan(0);
		expect(consoleErrors).toEqual([]);
	});

	test('K11: the road’s centre is road-toned at every step of the z15.5-16 fade', { tag: '@roads' }, async ({ page }) => {
		test.setTimeout(240_000);
		await page.goto(at(15.5));
		await mapReady(page);
		const road: [number, number] = [-116.2025, 43.615];
		// The 3D buildings stand over the road at this tilt-free zoom; take them away, the road is what is measured.
		await page.evaluate(() => {
			const map = (globalThis as any).__tvt.map;
			for (const id of ['buildings-3d', 'buildings-3d-estimated']) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', 'none');
		});
		for (const z of [15.5, 15.6, 15.75, 15.9, 16.05]) {
			await jump(page, z);
			const [r, g, b] = await darkestAround(page, road);
			// Asphalt is about (152,144,136); the fixture ground is about (232,224,208) or its checker tone.
			expect(r, `z${z}: the road's tone shows, not the ground (${r},${g},${b})`).toBeLessThan(200);
		}
		await page.screenshot({ path: screenPath('roads-k11-z1575.png') });
	});

	test('markings show in Valley, not in Clay and not under Aerial without Lanes', { tag: '@roads' }, async ({ page }) => {
		test.setTimeout(240_000);
		await page.goto(at(17.5));
		await mapReady(page);
		const MARK = 'roads.markings.solid';
		expect(await layerOn(page, MARK), 'Valley').toBe(true);
		expect(await rendered(page, [MARK, 'roads.markings.dashed', 'roads.markings.double', 'roads.markings.stop']), 'markings drawn in Valley').toBeGreaterThan(0);
		await page.getByRole('toolbar', { name: 'Map layers' }).getByRole('button', { name: 'Base' }).click();
		const pop = page.getByRole('dialog', { name: 'Base map' });
		await pop.getByRole('radio', { name: 'Clay' }).check();
		await expect.poll(() => layerOn(page, MARK), { message: 'Clay without Lanes' }).toBe(false);
		await pop.getByRole('radio', { name: 'Map' }).check();
		await expect.poll(() => layerOn(page, MARK), { message: 'back in Valley' }).toBe(true);
		await pop.getByRole('switch', { name: /Aerial photos/ }).check();
		await expect.poll(() => layerOn(page, MARK), { message: 'Valley under Aerial without Lanes' }).toBe(false);
		await page.screenshot({ path: screenPath('roads-markings-aerial.png') });
	});

	test('the draped run stays one stack at z14, z15.5 and z17', { tag: '@roads' }, async ({ page }) => {
		test.setTimeout(240_000);
		await page.goto(at(14));
		await mapReady(page);
		for (const z of [14, 15.5, 17]) {
			await jump(page, z);
			const runs = await liveRuns(page);
			expect(runs.length, `rttStacks at z${z}: ${JSON.stringify(runs)}`).toBe(1);
		}
		// With the roads’ layers in the run at z17: surfaces and markings together.
		const ids = (await liveRuns(page))[0];
		expect(ids.some((id) => id.startsWith('roads.surfaces.'))).toBe(true);
		expect(ids.some((id) => id.startsWith('roads.markings.'))).toBe(true);
	});
});
