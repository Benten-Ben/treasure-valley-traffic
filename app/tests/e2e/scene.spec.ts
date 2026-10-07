import type { Page } from '@playwright/test';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { gzipSync } from 'node:zlib';
import { expect, mapReady, screenPath, test } from './fixtures.js';

/**
 * scene (docs/14 §14.10, WP9; §14.8 "The 3D engine"): the 3D mesh engine.
 *
 * - Spike gate: one instanced batch on the terrain lands within 0.1 px of
 *   map.project at pitch 0–85, field of view 20–60° and roll ±5. "Lands" is
 *   measured on the GPU: the probe runs the mesh shader's own placement and
 *   reads it back by transform feedback, in the same frame as map.project.
 * - A model's base is within 0.2 m of queryTerrainElevation at z ≥ 15.
 * - At z22.5, panning in 1 px steps keeps every instance within 0.5 px of
 *   the float64 reference.
 * - ≤ 12 draw calls with every batch in use; the chunk is ≤ 40 KB gzip, isn't
 *   requested before the first idle, and never with Transit and Cameras off.
 * - After WEBGL_lose_context lose and restore, the scene comes back.
 * - The hit radius is ≥ 14 px, and a 3D click never also selects the route.
 */

type Summary = { n: number; max: number; mean: number; mercMax: number; baseMax: number };

const FOOTHILLS = { center: [-116.175, 43.632] as [number, number], zoom: 13.2, bearing: 25 };

function record(name: string, data: unknown) {
	const file = screenPath(name);
	mkdirSync(dirname(file), { recursive: true });
	writeFileSync(file, JSON.stringify(data, null, 2));
}

async function openTest(page: Page, hash: string) {
	await page.goto(`/?scene-test${hash}`);
	// Record map errors with their source from the moment the map exists.
	await page.waitForFunction(() => (globalThis as any).__tvt?.map, null, { timeout: 120_000 });
	await watchMapErrors(page);
	await mapReady(page);
	await page.waitForFunction(() => (globalThis as any).__tvtSceneTest, null, { timeout: 90_000 });
	expect(await page.evaluate(() => (globalThis as any).__tvtSceneTest.ok()), 'the scene is running').toBe(true);
}

/** Set the camera (pitch beyond Explore's 75 needs a higher limit), wait for the map, lay the grid out again and probe it. */
async function probeAt(page: Page, cam: { center: [number, number]; zoom: number; bearing: number; pitch: number; roll: number; fov: number }, fraction = 1): Promise<Summary> {
	await page.evaluate((c) => {
		const map = (globalThis as any).__tvt.map;
		map.setMaxPitch(89);
		map.setMaxZoom(24);
		map.setVerticalFieldOfView(c.fov);
		map.jumpTo({ center: c.center, zoom: c.zoom, bearing: c.bearing, pitch: c.pitch, roll: c.roll });
	}, cam);
	await mapReady(page);
	return page.evaluate(async (fraction) => {
		const t = (globalThis as any).__tvtSceneTest;
		t.reset(fraction);
		const s = await t.probe();
		return { n: s.n, max: s.max, mean: s.mean, mercMax: s.mercMax, baseMax: s.baseMax };
	}, fraction);
}

type MapError = { source: string | null; tile: string | null; message: string };

/** Record the map's error events with their source (an `error` event's console line doesn't say which source). */
async function watchMapErrors(page: Page) {
	await page.evaluate(() => {
		const w = globalThis as any;
		if (w.__mapErrors) return;
		w.__mapErrors = [];
		w.__tvt.map.on('error', (ev: any) => {
			const c = ev.tile?.tileID?.canonical;
			w.__mapErrors.push({ source: ev.sourceId ?? null, tile: c ? `${c.z}/${c.x}/${c.y}` : null, message: String(ev.error?.message ?? ev.error) });
		});
	});
}

/**
 * Console errors, less basemap tiles that failed to decode (seen at high pitch
 * and zoom: a basemap source's tile, never the scene's, which has no source).
 * Each tolerated one must come from a basemap source and is noted on the test.
 */
async function sceneErrors(page: Page, consoleErrors: string[]): Promise<string[]> {
	const mapErrors: MapError[] = await page.evaluate(() => (globalThis as any).__mapErrors ?? []);
	for (const e of mapErrors) expect(e.source, `map error from ${e.source}: ${e.message}`).toMatch(/^(terrain|hillshade|imagery|naip|protomaps|buildings)/);
	if (mapErrors.length) test.info().annotations.push({ type: 'basemap tile errors', description: mapErrors.map((e) => `${e.source} ${e.tile}: ${e.message}`).join('; ') });
	return consoleErrors.filter((m) => !(mapErrors.length && /^map error .*could not be decoded/.test(m)));
}

/** The scene chunk's file and gzip size, from the build's Vite manifest. */
function sceneChunk(): { file: string; gzip: number } {
	const manifest = join(process.cwd(), '.svelte-kit', 'output', 'client', '.vite', 'manifest.json');
	if (!existsSync(manifest)) throw new Error('no build manifest');
	const vite = JSON.parse(readFileSync(manifest, 'utf8'));
	const entry = Object.values(vite).find((v: any) => v.src === 'src/lib/scene/index.ts') as { file: string } | undefined;
	if (!entry) throw new Error('no scene chunk in the build');
	const bytes = readFileSync(join(process.cwd(), '.svelte-kit', 'output', 'client', entry.file));
	return { file: entry.file, gzip: gzipSync(bytes, { level: 6 }).length };
}

test.describe('scene', () => {
	test('spike gate: one instanced batch on the terrain lands within 0.1 px of map.project (pitch 0–85, fov 20–60, roll ±5)', { tag: '@wp9' }, async ({ page, consoleErrors }) => {
		test.setTimeout(1_500_000);
		await openTest(page, `#map=${FOOTHILLS.zoom}/${FOOTHILLS.center[1]}/${FOOTHILLS.center[0]}/${FOOTHILLS.bearing}/0&layers=none`);
		const rows: (Summary & { pitch: number; fov: number; roll: number; zoom: number })[] = [];
		const cams: { pitch: number; fov: number; roll: number; zoom: number }[] = [];
		for (const pitch of [0, 30, 60, 75, 85]) for (const fov of [20, 60]) for (const roll of [-5, 5]) cams.push({ pitch, fov, roll, zoom: FOOTHILLS.zoom });
		cams.push({ pitch: 45, fov: 36.87, roll: 0, zoom: FOOTHILLS.zoom }, { pitch: 70, fov: 36.87, roll: 0, zoom: 16.5 }, { pitch: 80, fov: 50, roll: -5, zoom: 18 });
		for (const c of cams) {
			const s = await probeAt(page, { ...FOOTHILLS, zoom: c.zoom, pitch: c.pitch, roll: c.roll, fov: c.fov });
			rows.push({ ...c, ...s });
			console.log(`pitch ${c.pitch} fov ${c.fov} roll ${c.roll} z${c.zoom}: ${s.n} on screen, max ${s.max.toFixed(4)} px, mean ${s.mean.toFixed(4)} px (float32 Mercator ${s.mercMax.toFixed(2)} px), base ±${s.baseMax.toFixed(3)} m`);
		}
		await page.screenshot({ path: screenPath('spike-last-view.png') });
		const worst = Math.max(...rows.map((r) => r.max));
		const mapErrors: MapError[] = await page.evaluate(() => (globalThis as any).__mapErrors);
		record('spike.json', { at: new Date().toISOString(), worstPx: worst, rows, mapErrors });
		test.info().annotations.push({ type: 'spike', description: `worst ${worst.toFixed(4)} px over ${rows.length} camera settings` });
		for (const r of rows) {
			expect(r.n, `instances on screen at pitch ${r.pitch}, fov ${r.fov}, roll ${r.roll}`).toBeGreaterThan(50);
			expect(r.max, `GPU vs map.project at pitch ${r.pitch}, fov ${r.fov}, roll ${r.roll}, z${r.zoom} (px)`).toBeLessThanOrEqual(0.1);
		}
		expect(await sceneErrors(page, consoleErrors)).toEqual([]);
	});

	test("a model's base is within 0.2 m of queryTerrainElevation at z ≥ 15", { tag: '@wp9' }, async ({ page }) => {
		test.setTimeout(900_000);
		await openTest(page, `#map=15/${FOOTHILLS.center[1]}/${FOOTHILLS.center[0]}/${FOOTHILLS.bearing}/50&layers=none`);
		const rows: (Summary & { zoom: number })[] = [];
		for (const zoom of [15, 16.5, 18, 20]) {
			const s = await probeAt(page, { ...FOOTHILLS, zoom, pitch: 50, roll: 0, fov: 36.87 });
			rows.push({ zoom, ...s });
			console.log(`z${zoom}: ${s.n} models, base within ${s.baseMax.toFixed(4)} m of queryTerrainElevation, GPU ${s.max.toFixed(4)} px from map.project`);
		}
		record('base.json', rows);
		for (const r of rows) {
			expect(r.n, `models on screen at z${r.zoom}`).toBeGreaterThan(50);
			expect(r.baseMax, `base vs queryTerrainElevation at z${r.zoom} (m)`).toBeLessThanOrEqual(0.2);
			expect(r.max, `GPU vs map.project at z${r.zoom} (px)`).toBeLessThanOrEqual(0.1);
		}
	});

	test('at z22.5, panning in 1 px steps keeps every instance within 0.5 px of the float64 reference', { tag: '@wp9' }, async ({ page }) => {
		test.setTimeout(900_000);
		// Downtown Boise, at the zoom look-through and calibration work at.
		await openTest(page, '#map=17/43.6150/-116.2023/17/60&layers=none');
		await page.evaluate(() => {
			const map = (globalThis as any).__tvt.map;
			map.setMaxZoom(24);
			map.jumpTo({ zoom: 22.5 });
		});
		await mapReady(page);
		// Models at 1/200 scale (about 6 cm, some 20 px here): full-size buses would be thousands of px long,
		// which only costs SwiftShader overdraw; the anchor's placement is what's measured.
		await page.evaluate(() => (globalThis as any).__tvtSceneTest.reset(0.6, 0.005));
		const steps: { step: number; max: number; mercMax: number; n: number }[] = [];
		for (let step = 0; step < 40; step++) {
			const s: Summary = await page.evaluate(async (step) => {
				const map = (globalThis as any).__tvt.map;
				// Right, then down, then diagonally back: 1 px at a time.
				const d = step < 15 ? [1, 0] : step < 30 ? [0, 1] : [-1, -1];
				if (step > 0) map.panBy(d, { animate: false });
				const r = await (globalThis as any).__tvtSceneTest.probe();
				return { n: r.n, max: r.max, mean: r.mean, mercMax: r.mercMax, baseMax: r.baseMax };
			}, step);
			steps.push({ step, max: s.max, mercMax: s.mercMax, n: s.n });
		}
		const worst = Math.max(...steps.map((x) => x.max));
		const mercWorst = Math.max(...steps.map((x) => x.mercMax));
		record('jitter-z22.5.json', { worstPx: worst, float32MercatorWorstPx: mercWorst, steps });
		test.info().annotations.push({ type: 'z22.5', description: `RTC worst ${worst.toFixed(4)} px; plain float32 Mercator worst ${mercWorst.toFixed(1)} px` });
		console.log(`z22.5 pan: RTC worst ${worst.toFixed(4)} px over ${steps.length} steps; plain float32 Mercator ${mercWorst.toFixed(1)} px`);
		for (const x of steps) expect(x.n, `instances on screen at step ${x.step}`).toBeGreaterThan(20);
		expect(worst).toBeLessThanOrEqual(0.5);
	});

	test('every batch in use makes at most 12 draw calls', { tag: '@wp9' }, async ({ page, consoleErrors }) => {
		test.setTimeout(600_000);
		await openTest(page, `#map=18.3/${FOOTHILLS.center[1]}/${FOOTHILLS.center[0]}/200/62&layers=none`);
		// Count every WebGL draw made inside the scene layer's render, independently of the scene's own counter.
		await page.evaluate(() => {
			const map = (globalThis as any).__tvt.map;
			const impl = map.getLayer('scene-3d').implementation;
			const proto = WebGL2RenderingContext.prototype as any;
			const w = globalThis as any;
			w.__sceneDraws = 0;
			let counting = false;
			let n = 0;
			for (const fn of ['drawArrays', 'drawElements', 'drawArraysInstanced', 'drawElementsInstanced', 'drawRangeElements']) {
				const orig = proto[fn];
				proto[fn] = function (...a: unknown[]) {
					if (counting) n++;
					return orig.apply(this, a);
				};
			}
			const render = impl.render;
			impl.render = function (gl: unknown, args: unknown) {
				counting = true;
				n = 0;
				try {
					return render.call(this, gl, args);
				} finally {
					counting = false;
					w.__sceneDraws = n;
				}
			};
		});
		// The showcase alone first, so a click picks its bus: the selection adds the ground ring.
		await page.evaluate(async () => {
			const t = (globalThis as any).__tvtSceneTest;
			t.clear();
			await t.showcase(true);
		});
		await mapReady(page);
		const bus = await page.evaluate(() => (globalThis as any).__tvtSceneTest.placed().find((p: any) => p.id === 'show-bus'));
		expect(bus, 'the showcase bus is on screen').toBeTruthy();
		await page.mouse.click(bus.x, bus.y);
		await expect.poll(() => page.evaluate(() => (globalThis as any).__tvt.layers.selection?.id)).toBe('show-bus');
		await page.waitForTimeout(1500);
		await page.screenshot({ path: screenPath('showcase-selected-z18.png') });
		// Then the 1,000-model grid around it too (more instances, the same batches).
		await page.evaluate(() => (globalThis as any).__tvtSceneTest.reset(0.9, 0.5));
		await mapReady(page);
		const r = await page.evaluate(
			() =>
				new Promise<{ draws: number; stats: any }>((resolve) => {
					const map = (globalThis as any).__tvt.map;
					map.once('render', () => resolve({ draws: (globalThis as any).__sceneDraws, stats: (globalThis as any).__tvtSceneTest.stats() }));
					map.triggerRepaint();
				})
		);
		await page.screenshot({ path: screenPath('showcase-grid-z18.png') });
		record('draw-calls.json', r);
		console.log(`scene draws: ${r.draws} (scene's count ${r.stats.drawCalls}), ${r.stats.instances} instances, JS ${r.stats.lastFrameMs.toFixed(2)} ms`);
		// bus, stop, pole, head, pin, ring, shadows, cones, lines, photos: 10 kinds in use.
		expect(r.stats.drawCalls).toBe(r.draws);
		expect(r.draws).toBeGreaterThanOrEqual(10);
		expect(r.draws).toBeLessThanOrEqual(12);
		expect(await sceneErrors(page, consoleErrors)).toEqual([]);
	});

	test('the scene chunk is ≤ 40 KB gzip, requested only after the first idle, and never with Transit and Cameras off', { tag: '@wp9' }, async ({ page, browser }) => {
		test.setTimeout(600_000);
		const chunk = sceneChunk();
		console.log(`scene chunk ${chunk.file}: ${(chunk.gzip / 1000).toFixed(1)} KB gzip`);
		expect(chunk.gzip).toBeLessThanOrEqual(40_000);
		const requested = (p: Page) =>
			p.evaluate((file) => {
				const r = performance.getEntriesByType('resource').find((e) => e.name.endsWith(file));
				return r ? r.startTime : null;
			}, chunk.file);

		// A first visit (Transit and Cameras on): prefetched after the first idle, not before.
		await page.goto('/');
		await mapReady(page);
		await expect.poll(() => requested(page), { timeout: 60_000 }).not.toBeNull();
		const t = await page.evaluate((file) => {
			const r = performance.getEntriesByType('resource').find((e) => e.name.endsWith(file))!;
			const idle = performance.getEntriesByName('tvt:idle')[0];
			return { chunk: r.startTime, idle: idle?.startTime ?? null };
		}, chunk.file);
		expect(t.idle, 'the first idle was marked').not.toBeNull();
		expect(t.chunk, 'scene chunk requested after the first idle').toBeGreaterThanOrEqual(t.idle!);

		// Transit and Cameras off: never requested, even well after idle; turning Transit on loads it.
		const ctx = await browser.newContext();
		const p2 = await ctx.newPage();
		await p2.goto('/#map=12/43.61/-116.25/0/30&layers=streets');
		await mapReady(p2);
		await p2.waitForTimeout(5000);
		await p2.evaluate(() => (globalThis as any).__tvt.map.jumpTo({ zoom: 13 }));
		await mapReady(p2);
		await p2.waitForTimeout(3000);
		expect(await requested(p2), 'scene chunk with Transit and Cameras off').toBeNull();
		await p2.getByRole('toolbar', { name: 'Map layers' }).getByRole('button', { name: 'Transit', exact: true }).click();
		await expect.poll(() => requested(p2), { timeout: 60_000 }).not.toBeNull();
		await ctx.close();
	});

	test('after WEBGL_lose_context lose and restore, the scene comes back', { tag: '@wp9' }, async ({ page }) => {
		test.setTimeout(600_000);
		await openTest(page, `#map=16/${FOOTHILLS.center[1]}/${FOOTHILLS.center[0]}/20/50&layers=none`);
		const before = await page.evaluate(async () => {
			const s = await (globalThis as any).__tvtSceneTest.probe();
			return { n: s.n, max: s.max };
		});
		expect(before.n).toBeGreaterThan(50);
		await page.screenshot({ path: screenPath('context-before.png') });
		await page.evaluate(async () => {
			const gl = (globalThis as any).__tvt.map.getCanvas().getContext('webgl2');
			const ext = gl.getExtension('WEBGL_lose_context');
			ext.loseContext();
			await new Promise((r) => setTimeout(r, 1000));
			ext.restoreContext();
		});
		await page.waitForFunction(() => Boolean((globalThis as any).__tvt.map.getLayer('scene-3d')), null, { timeout: 120_000 });
		await mapReady(page);
		const after = await page.evaluate(async () => {
			const t = (globalThis as any).__tvtSceneTest;
			const s = await t.probe();
			return { n: s.n, max: s.max, ok: t.ok(), stats: t.stats() };
		});
		await page.screenshot({ path: screenPath('context-restored.png') });
		// For the record (not WP9's): whether the 2D overlay's custom layer came back too.
		const overlayLayer = await page.evaluate(() => Boolean((globalThis as any).__tvt.map.getLayer('overlay')));
		record('context-restore.json', { before, after, overlayLayerAfterRestore: overlayLayer });
		expect(after.ok).toBe(true);
		expect(after.n).toBe(before.n);
		expect(after.max).toBeLessThanOrEqual(0.1);
		expect(after.stats.drawCalls).toBeGreaterThanOrEqual(1);
	});

	test('the hit radius is at least 14 px, and a 3D click selects the model, never also the route under it', { tag: '@wp9' }, async ({ page }) => {
		test.setTimeout(600_000);
		await openTest(page, '#map=15.5/43.6150/-116.2023/0/30&layers=transit');
		await expect.poll(() => page.evaluate(() => (globalThis as any).__tvt.layers.status.transit), { timeout: 60_000 }).toBe('ready');
		await mapReady(page);
		await page.evaluate(() => (globalThis as any).__tvtSceneTest.clear());
		// A frame without the grid, so the picker has no stale placements.
		await mapReady(page);
		expect(await page.evaluate(() => (globalThis as any).__tvtSceneTest.placed().length)).toBe(0);
		// A point on a route line, away from any bus.
		const pt = await page.evaluate(() => {
			const map = (globalThis as any).__tvt.map;
			const c = map.getCanvas();
			const [W, H] = [c.clientWidth, c.clientHeight];
			const buses = ['transit-buses'].filter((l) => map.getLayer(l));
			for (let y = H * 0.35; y < H * 0.65; y += 5)
				for (let x = W * 0.3; x < W * 0.7; x += 5) {
					if (!map.queryRenderedFeatures([x, y], { layers: ['transit-routes'] }).length) continue;
					const near = buses.length ? map.queryRenderedFeatures([[x - 30, y - 30], [x + 30, y + 30]], { layers: buses }) : [];
					if (!near.length) return { x: Math.round(x), y: Math.round(y) };
				}
			return null;
		});
		expect(pt, 'a route line on screen').not.toBeNull();
		const selection = () => page.evaluate(() => (globalThis as any).__tvt.layers.selection);
		await page.mouse.click(pt!.x, pt!.y);
		await expect.poll(async () => (await selection())?.kind).toMatch(/^routes?$/);
		await page.keyboard.press('Escape');
		// A model on the same spot: the click selects it, not the route.
		const id = await page.evaluate(({ x, y }) => (globalThis as any).__tvtSceneTest.placeAt(x, y), pt!);
		await mapReady(page);
		const placed = await page.evaluate((id) => (globalThis as any).__tvtSceneTest.placed().find((p: any) => p.id === id), id);
		expect(placed).toBeTruthy();
		expect(placed.r, 'the model alone is smaller than the picker minimum').toBeLessThan(13);
		await page.mouse.click(placed.x, placed.y);
		await expect.poll(async () => (await selection())?.id).toBe(id);
		expect((await selection()).kind).toBe('bus');
		expect((await selection()).layer).toBe('scene-test');
		await page.keyboard.press('Escape');
		await expect.poll(async () => (await selection())?.id ?? null).toBeNull();
		// 13 px from its centre still hits it (the 14 px minimum)…
		await page.mouse.click(placed.x + 13, placed.y);
		await expect.poll(async () => (await selection())?.id).toBe(id);
		await page.keyboard.press('Escape');
		await expect.poll(async () => (await selection())?.id ?? null).toBeNull();
		// …and 20 px away does not.
		await page.mouse.click(placed.x, placed.y + 20);
		await page.waitForTimeout(500);
		expect((await selection())?.id ?? null).not.toBe(id);
	});

	test('1,000 moving models: frames come from the loop, and nothing calls setData', { tag: '@wp9' }, async ({ page }) => {
		test.setTimeout(600_000);
		await openTest(page, `#map=${FOOTHILLS.zoom}/${FOOTHILLS.center[1]}/${FOOTHILLS.center[0]}/${FOOTHILLS.bearing}/55&layers=none`);
		await page.evaluate(() => {
			const map = (globalThis as any).__tvt.map;
			const w = globalThis as any;
			w.__setData = 0;
			for (const id of Object.keys(map.getStyle().sources)) {
				const src = map.getSource(id);
				if (src && typeof src.setData === 'function') {
					const orig = src.setData.bind(src);
					src.setData = (...a: unknown[]) => {
						w.__setData++;
						return orig(...a);
					};
				}
			}
		});
		const stats = () => page.evaluate(() => (globalThis as any).__tvtSceneTest.stats());
		// A still frame with a still camera queries no terrain.
		await page.evaluate(() => new Promise<void>((r) => ((globalThis as any).__tvt.map.once('render', () => r()), (globalThis as any).__tvt.map.triggerRepaint())));
		const still = await stats();
		const pos = () => page.evaluate(() => (globalThis as any).__tvtSceneTest.placed().slice(0, 50).map((p: any) => [p.x, p.y]));
		const before = { frames: still.frames, pos: await pos(), t: Date.now() };
		await page.evaluate(() => (globalThis as any).__tvtSceneTest.setMoving(true));
		// The loop asks for frames by itself (SwiftShader frames take a while here: count, don't time).
		await expect.poll(async () => (await stats()).frames - before.frames, { timeout: 180_000 }).toBeGreaterThanOrEqual(6);
		const moving = await page.evaluate(() => ({ stats: (globalThis as any).__tvtSceneTest.stats(), setData: (globalThis as any).__setData }));
		const after = await pos();
		const seconds = (Date.now() - before.t) / 1000;
		await page.screenshot({ path: screenPath('grid-1000-z13.png') });
		await page.evaluate(() => (globalThis as any).__tvtSceneTest.setMoving(false));
		await page.waitForTimeout(3000);
		const f1 = (await stats()).frames;
		await page.waitForTimeout(4000);
		const f2 = (await stats()).frames;
		const moved = after.filter((p: number[], i: number) => before.pos[i] && Math.hypot(p[0] - before.pos[i][0], p[1] - before.pos[i][1]) > 0.01).length;
		record('moving.json', { framesWhileMoving: moving.stats.frames - before.frames, seconds, stillFrameGroundQueries: still.groundQueries, stats: moving.stats, setData: moving.setData, moved, framesAfterStop: f2 - f1 });
		console.log(
			`moving: ${moving.stats.frames - before.frames} frames in ${seconds.toFixed(1)} s, ${moving.stats.instances} instances, ${moved}/50 moved on screen, JS p95 ${moving.stats.p95Ms.toFixed(2)} ms and last ${moving.stats.lastFrameMs.toFixed(2)} ms (sandbox), ${moving.stats.groundQueries} terrain queries a frame; still frame ${still.groundQueries} queries; setData ${moving.setData}; after stop ${f2 - f1} frames in 4 s`
		);
		expect(still.groundQueries, 'terrain queries in a still frame').toBe(0);
		expect(moving.stats.instances).toBe(1000);
		expect(moved).toBeGreaterThan(40);
		expect(moving.setData).toBe(0);
		expect(f2 - f1, 'no frames once nothing moves').toBeLessThanOrEqual(1);
	});
});
