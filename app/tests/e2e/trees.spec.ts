import { chromium, type Browser, type Page } from '@playwright/test';
import { writeFileSync } from 'node:fs';
import { CHROMIUM_ARGS, lockedArgs } from '../../scripts/harness-env.mjs';
import { expect, mapReady, screenPath, test } from './fixtures.js';
import { cleanTrees, seedPerfTrees, seedTrees, type Seeded } from './trees-seed.js';

/**
 * trees (docs/19 §19.6): with a trees build loaded (trees-seed.ts: the real
 * loader on the North End sample build, and a FAKE catalogue of invented
 * rows when the private table isn't there):
 *
 * - at z17 over the North End the trees stand in 3D (scene instances, by
 *   type), and a click on one opens the tree panel with its kind, sizes, how
 *   we know and its log; the map's attribution credits the trees;
 * - with the map tilted, a tall tree is picked from its trunk to its top, and
 *   stays on the ground at its size when selected;
 * - farther out they're crown discs, which are clickable too, solid until
 *   z14.7 and fading out by zoom alone as the models dither in;
 * - where nothing is built, the legend says where trees are so far, and
 *   takes you there;
 * - the measurement: frame times with a few thousand synthetic trees in view
 *   at several caps (data/dev/screens/<wp>/trees-perf.json).
 */

const NORTH_END: [number, number] = [-116.20892, 43.62755];
const at = (zoom: number, bearing = 0, pitch = 0, c = NORTH_END) => `/#map=${zoom}/${c[1]}/${c[0]}/${bearing}/${pitch}&layers=trees`;

type Info = { visible: boolean; mode: string; scene: string; modelsOn: boolean; fetched: number; truncated: boolean; inScene: number; capped: boolean; requests: number };
/** A drawn tree: screen centre, hit radius (px), distance from the camera, and its hit capsule's axis (trunk end, top end). */
type Placed = { id: string; x: number; y: number; r: number; w: number; seg?: [number, number, number, number] };
const info = (page: Page): Promise<Info> => page.evaluate(() => (globalThis as any).__tvtTrees?.info() ?? null);
const placed = (page: Page): Promise<Placed[]> => page.evaluate(() => (globalThis as any).__tvtTrees?.placed() ?? []);
const attribution = (page: Page): Promise<string> => page.evaluate(() => document.querySelector('.maplibregl-ctrl-attrib-inner')?.textContent ?? '');
/** The crown discs' opacity as MapLibre evaluated it for this zoom (null when it depends on more than the zoom). */
const discOpacityNow = (page: Page): Promise<number | null> =>
	page.evaluate(() => (globalThis as any).__tvt.map.getLayer('trees-discs')?.paint?.get('circle-opacity')?.constantOr(null) ?? null);
const segDist = (x: number, y: number, [x1, y1, x2, y2]: [number, number, number, number]) => {
	const dx = x2 - x1;
	const dy = y2 - y1;
	const t = Math.min(1, Math.max(0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy || 1)));
	return Math.hypot(x - (x1 + t * dx), y - (y1 + t * dy));
};
const discs = (page: Page): Promise<{ id: string; x: number; y: number; r: number }[]> => page.evaluate(() => (globalThis as any).__tvtTrees?.discs() ?? []);
const selection = (page: Page) => page.evaluate(() => (globalThis as any).__tvt.layers.selection);

/** Console errors with their messages (an Error argument prints only as "Error" otherwise). */
async function keepErrors(page: Page) {
	await page.addInitScript(() => {
		const w = globalThis as any;
		w.__errors = [];
		const orig = console.error.bind(console);
		console.error = (...a: unknown[]) => {
			w.__errors.push(a.map((x) => (x instanceof Error ? `${x.name}: ${x.message}` : String(x))).join(' '));
			orig(...a);
		};
	});
}
const errorsOf = (page: Page): Promise<string[]> => page.evaluate(() => (globalThis as any).__errors ?? []);

let seeded: Seeded | null = null;

test.beforeAll(async () => {
	seeded = await seedTrees();
});

test.afterAll(async () => {
	await cleanTrees(seeded);
});

/** On screen and clear of the legend column, the inspect column, the top bar and the toolbar. */
const clear = (p: { x: number; y: number }) => p.x > 320 && p.x < 1280 - 400 && p.y > 90 && p.y < 800 - 130;
/** The tree's centre isn't under a nearer tree's crown (the nearer one is what a click there picks). */
const uncovered = (all: Placed[]) => (p: Placed) => !all.some((q) => q.id !== p.id && q.seg && q.w < p.w && segDist(p.x, p.y, q.seg) <= q.r);

test.describe('trees', () => {
	test('at z17 over the North End the trees stand in 3D, and a click opens the tree panel with its log', { tag: '@trees' }, async ({ page }) => {
		test.setTimeout(300_000);
		await keepErrors(page);
		await page.goto(at(17, -12, 50));
		await mapReady(page);
		await expect.poll(async () => (await info(page))?.modelsOn, { timeout: 90_000 }).toBe(true);
		await expect.poll(async () => (await placed(page)).length, { timeout: 60_000 }).toBeGreaterThan(50);
		const i = await info(page);
		expect(i.mode).toBe('models');
		expect(i.fetched).toBe(seeded!.trees);
		expect(i.inScene).toBe(i.fetched);
		await mapReady(page);
		await page.screenshot({ path: screenPath('trees-3d-z17.png') });
		// The models are drawn without a disc in sight: the attribution still credits the trees.
		await expect.poll(() => attribution(page)).toContain('Trees: USGS 3DEP lidar, City of Boise, US Forest Service');

		// The tallest catalogued tree (given a fake catalogue row when the private table isn't here).
		const all = await placed(page);
		const want = seeded!.faked[0];
		const target = all.find((p) => p.id === want && clear(p) && uncovered(all)(p)) ?? all.find((p) => clear(p) && uncovered(all)(p));
		expect(target, 'a tree on screen, clear of the panels').toBeTruthy();
		await page.mouse.click(target!.x, target!.y);
		await expect.poll(async () => (await selection(page))?.kind).toBe('tree');
		const sel = await selection(page);
		expect(sel.layer).toBe('trees');
		const card = page.getByRole('region', { name: 'Selected tree' });
		await expect(card).toBeVisible();
		await expect(card.getByRole('heading', { name: 'How we know' })).toBeVisible({ timeout: 30_000 });
		await expect(card.getByRole('heading', { name: 'Log' })).toBeVisible();
		const log = card.getByRole('list', { name: 'Log, newest first' });
		await expect(log.getByRole('listitem').first()).toBeVisible();
		await expect(card.getByText('Height', { exact: true })).toBeVisible();
		await expect(card.getByText('Crown width', { exact: true })).toBeVisible();
		await expect(card.getByText(/USGS 3DEP lidar/)).toBeVisible();
		if (sel.id === want && seeded!.madeCatalogue) {
			// The fake catalogue's invented row: the species' name, trunk, planting date, condition.
			await expect(card.getByRole('heading', { name: 'Test linden (synthetic)' })).toBeVisible();
			await expect(card.getByText("In the City of Boise's inventory, measured by the 2023 lidar.")).toBeVisible();
			await expect(card.getByText('Measured by lidar', { exact: true })).toBeVisible();
			await expect(card.getByText('Apr 15, 2009', { exact: true })).toBeVisible();
			await expect(card.getByText('Good', { exact: true })).toBeVisible();
			await expect(card.getByText(/14 in · 36 cm/)).toBeVisible();
		}
		await page.waitForTimeout(1500);
		await page.screenshot({ path: screenPath('trees-panel-z17.png') });

		// A placed tree's panel, too: its kind in words, its crown "estimated by placement".
		const placedTree = await placed(page);
		const pt = placedTree.find((p) => /^c-/.test(p.id) && clear(p) && uncovered(placedTree)(p));
		if (pt) {
			await page.mouse.click(pt.x, pt.y);
			await expect.poll(async () => (await selection(page))?.id).toBe(pt.id);
			await expect(card.getByText('Found in the 2023 lidar; position and crown estimated by placement.')).toBeVisible({ timeout: 30_000 });
			await expect(card.getByText('estimated by placement').first()).toBeVisible();
			await expect(card.getByText('Placed from the lidar', { exact: true })).toBeVisible();
			await page.screenshot({ path: screenPath('trees-panel-placed.png') });
		}
		expect(await errorsOf(page)).toEqual([]);
	});

	test('with the map tilted, a tall tree is picked from its trunk to its top, and stays on the ground when selected', { tag: '@trees' }, async ({ page }) => {
		test.setTimeout(600_000);
		await keepErrors(page);
		await page.goto(at(17, -12, 50));
		await mapReady(page);
		await expect.poll(async () => (await info(page))?.modelsOn, { timeout: 90_000 }).toBe(true);
		// The build's thinnest tall trees: where a hit circle round the middle missed the most.
		const rows = (await page.evaluate(async (u) => (await (await fetch(u)).json()).trees, '/api/trees?bbox=-116.3,43.5,-116.1,43.7&limit=8000')) as { id: string; lng: number; lat: number; h: number; r: number }[];
		const thin = rows.filter((t) => t.h >= 8).sort((a, b) => b.h / b.r - a.h / a.r);
		expect(thin.length).toBeGreaterThan(0);
		let chosen: { tall: Placed; all: Placed[]; beyond: number } | null = null;
		for (const t of thin.slice(0, 4)) {
			// Each in turn at the middle of the screen, the map tilted 65°.
			await page.evaluate(([lng, lat]) => (globalThis as any).__tvt.map.jumpTo({ center: [lng, lat], zoom: 19.5, pitch: 65, bearing: -12 }), [t.lng, t.lat]);
			await mapReady(page);
			await expect.poll(async () => (await placed(page)).some((p) => p.id === t.id), { timeout: 60_000 }).toBe(true);
			const all = await placed(page);
			const tall = all.find((p) => p.id === t.id)!;
			expect(tall.seg, 'a tree has a hit capsule').toBeTruthy();
			// Points only this tree is on (no nearer tree's crown there), clear of the panels.
			const own = (x: number, y: number) => clear({ x, y }) && !all.some((q) => q.id !== tall.id && q.seg && q.w < tall.w && segDist(x, y, q.seg) <= q.r);
			// How far its trunk and top ends lie beyond a circle round its middle (the old hit area).
			const reach = (x: number, y: number) => Math.hypot(x - tall.x, y - tall.y) - Math.max(tall.r, 14);
			const [bx, by, tx, ty] = tall.seg!;
			const beyond = Math.min(reach(bx, by), reach(tx, ty));
			console.log(`candidate ${t.id} (h ${t.h} m, r ${t.r} m): ${beyond.toFixed(1)} px beyond the old circle; trunk end clear ${own(bx, by)}, top end clear ${own(tx, ty)}`);
			if (own(bx, by) && own(tx, ty) && beyond > 4) {
				chosen = { tall, all, beyond };
				break;
			}
		}
		expect(chosen, 'a tall tree whose trunk and top lie beyond its middle circle, with no nearer tree over them').toBeTruthy();
		const { tall, all, beyond } = chosen!;
		const [bx, by, tx, ty] = tall.seg!;
		// Near the trunk.
		await page.mouse.click(bx, by);
		await expect.poll(async () => (await selection(page))?.id).toBe(tall.id);
		// An empty spot clears it.
		const spots = [...Array(48)].map((_, k) => ({ x: 340 + (k % 8) * 70, y: 110 + Math.floor(k / 8) * 100 }));
		const empty = spots.find((q) => clear(q) && all.every((o) => segDist(q.x, q.y, o.seg ?? [o.x, o.y, o.x, o.y]) > Math.max(o.r, 14) + 20));
		expect(empty, 'an empty spot on the map').toBeTruthy();
		await page.mouse.click(empty!.x, empty!.y);
		await expect.poll(async () => (await selection(page))?.id ?? null).toBeNull();
		// Near the top of the crown.
		await page.mouse.click(tx, ty);
		await expect.poll(async () => (await selection(page))?.id).toBe(tall.id);
		await expect(page.getByRole('region', { name: 'Selected tree' })).toBeVisible();
		// Selected, it stays where it stood, at its size (no lift, no growth): the ground ring marks it.
		await page.waitForTimeout(1500);
		await mapReady(page);
		const after = (await placed(page)).find((p) => p.id === tall.id)!;
		expect(Math.abs(after.y - tall.y), 'not lifted').toBeLessThan(1.5);
		expect(Math.abs(after.r - tall.r), 'not grown').toBeLessThan(0.5);
		await page.screenshot({ path: screenPath('trees-tall-selected-z19.5.png') });
		console.log(`tall tree ${tall.id}: centre ${tall.x.toFixed(0)},${tall.y.toFixed(0)}, r ${tall.r.toFixed(1)} px; trunk end ${bx.toFixed(0)},${by.toFixed(0)}; top end ${tx.toFixed(0)},${ty.toFixed(0)}; ${beyond.toFixed(1)} px beyond the old circle`);
		expect(await errorsOf(page)).toEqual([]);
	});

	test('far out the trees are crown discs, clickable too', { tag: '@trees' }, async ({ page }) => {
		test.setTimeout(240_000);
		await page.goto(at(14.6));
		await mapReady(page);
		await expect.poll(async () => (await discs(page)).length, { timeout: 60_000 }).toBeGreaterThan(100);
		const i = await info(page);
		expect(i.mode).toBe('discs');
		expect(i.modelsOn).toBe(false);
		// Solid until z14.7 even once the scene is there to take over (the fade is by zoom alone).
		await expect.poll(async () => (await info(page))?.scene, { timeout: 90_000 }).toBe('ready');
		await mapReady(page);
		await expect.poll(() => discOpacityNow(page)).toBe(1);
		await page.screenshot({ path: screenPath('trees-discs-z14.6.png') });
		expect(await attribution(page)).toContain('Trees: USGS 3DEP lidar');
		// Halfway through the crossfade, half.
		await page.evaluate(() => (globalThis as any).__tvt.map.jumpTo({ zoom: 14.85 }));
		await mapReady(page);
		await expect.poll(async () => Math.round(((await discOpacityNow(page)) ?? -1) * 100) / 100).toBe(0.5);
		await page.screenshot({ path: screenPath('trees-crossfade-z14.85.png') });
		// Closer, still discs below z15: the biggest disc, clicked.
		await page.goto(at(14.65, 0, 0, [-116.2089, 43.62755]));
		await mapReady(page);
		const ds = (await discs(page)).filter(clear).sort((a, b) => b.r - a.r);
		expect(ds.length).toBeGreaterThan(0);
		await page.mouse.click(ds[0].x, ds[0].y);
		await expect.poll(async () => (await selection(page))?.kind).toBe('tree');
		await expect(page.getByRole('region', { name: 'Selected tree' })).toBeVisible();
		await expect(page.getByRole('region', { name: 'Selected tree' }).getByRole('heading', { name: 'Log' })).toBeVisible({ timeout: 30_000 });
		await page.screenshot({ path: screenPath('trees-discs-selected.png') });
	});

	test('where nothing is built, the legend says where trees are so far and takes you there', { tag: '@trees' }, async ({ page }) => {
		test.setTimeout(240_000);
		// Downtown Boise: no trees built there yet.
		await page.goto(at(16, 0, 0, [-116.2035, 43.6152]));
		await mapReady(page);
		const legend = page.getByRole('region', { name: 'Trees legend' });
		await expect(legend.getByText('No trees here yet.')).toBeVisible({ timeout: 30_000 });
		await expect(legend.getByText(/Trees are built for the North End( and area perf)? so far\./)).toBeVisible();
		await page.screenshot({ path: screenPath('trees-legend-elsewhere.png') });
		expect((await info(page)).fetched, 'nothing asked for where nothing is built').toBe(0);
		await legend.getByRole('button', { name: 'Go to the North End' }).click();
		await expect.poll(async () => (await info(page))?.inScene ?? 0, { timeout: 90_000 }).toBeGreaterThan(50);
		await expect(legend.getByText('No trees here yet.')).toHaveCount(0);
	});

	test('frame time with thousands of trees in view, by cap (the measurement)', { tag: '@trees' }, async ({ page, browser }) => {
		test.setTimeout(900_000);
		await keepErrors(page);
		const n = await seedPerfTrees(NORTH_END);
		expect(n).toBe(15_000);
		const out: Record<string, unknown> = { synthetic: n, view: 'z16, pitch 50, 1280 × 800, Trees only, terrain on' };
		const measure = async (p: Page, label: string) => {
			await p.goto(at(16, -12, 50));
			await mapReady(p);
			await expect.poll(async () => (await info(p))?.modelsOn, { timeout: 120_000 }).toBe(true);
			const rows: unknown[] = [];
			// Up to the API's close-up limit (4,000), the most the scene can be handed.
			for (const [cap, limit] of [
				[1000, 4000],
				[2000, 4000],
				[3000, 4000],
				[4000, 4000]
			]) {
				await p.evaluate(([c, l]) => (globalThis as any).__tvtTrees.setCap(c, l), [cap, limit]);
				// (A few of the fetched trees can sit just outside the view's margin.)
				await expect.poll(async () => (await info(p)).inScene, { timeout: 60_000 }).toBeGreaterThanOrEqual(Math.floor(cap * 0.95));
				expect((await info(p)).inScene).toBeLessThanOrEqual(cap);
				await mapReady(p);
				const r = await p.evaluate(
					() =>
						new Promise<Record<string, number>>((resolve) => {
							const map = (globalThis as any).__tvt.map;
							const t = (globalThis as any).__tvtTrees;
							const times: number[] = [];
							const js: number[] = [];
							let seenFrames = t.sceneStats().frames;
							let last = performance.now();
							let on = true;
							const tick = (now: number) => {
								times.push(now - last);
								last = now;
								// The scene's own JS time for each frame it drew while moving.
								const st = t.sceneStats();
								if (st.frames !== seenFrames) {
									seenFrames = st.frames;
									js.push(st.lastFrameMs);
								}
								if (on) requestAnimationFrame(tick);
							};
							requestAnimationFrame((now) => {
								last = now;
								requestAnimationFrame(tick);
							});
							const s0 = t.sceneStats();
							map.once('moveend', () => {
								on = false;
								const s = t.sceneStats();
								const q = (xs: number[], f: number) => {
									const sorted = [...xs].sort((a, b) => a - b);
									return sorted.length ? sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * f))] : NaN;
								};
								resolve({
									inScene: t.info().inScene,
									drawn: s.instances,
									sceneFrames: s.frames - s0.frames,
									jsMedian: q(js, 0.5),
									jsP95: q(js, 0.95),
									groundQueries: s.groundQueries,
									frames: times.length,
									frameMedian: q(times, 0.5),
									frameP95: q(times, 0.95)
								});
							});
							map.easeTo({ bearing: map.getBearing() + 60, duration: 4000, easing: (x: number) => x });
						})
				);
				rows.push({ cap, limit, ...r });
				console.log(`${label} cap ${cap}: ${JSON.stringify(r)}`);
			}
			rows.push({ errors: await errorsOf(p) });
			return rows;
		};
		out.swiftshader = await measure(page, 'SwiftShader');
		await page.screenshot({ path: screenPath('trees-perf-z16.png') });
		// And on the laptop's own GPU (headless Chromium with Metal), when it starts.
		let gpu: Browser | null = null;
		try {
			gpu = await chromium.launch({ args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', ...lockedArgs()] });
			const ctx = await gpu.newContext({ viewport: { width: 1280, height: 800 }, baseURL: test.info().project.use.baseURL });
			const gp = await ctx.newPage();
			await keepErrors(gp);
			const renderer = await gp.evaluate(() => {
				const gl = document.createElement('canvas').getContext('webgl2');
				const ext = gl?.getExtension('WEBGL_debug_renderer_info');
				return gl ? String(gl.getParameter(ext ? ext.UNMASKED_RENDERER_WEBGL : gl.RENDERER)) : 'none';
			});
			out.gpuRenderer = renderer;
			out.gpu = await measure(gp, 'GPU');
			await gp.screenshot({ path: screenPath('trees-perf-z16-gpu.png') });
		} catch (e) {
			out.gpu = `not measured: ${e instanceof Error ? e.message : e}`;
		} finally {
			await gpu?.close();
		}
		out.swiftshaderArgs = CHROMIUM_ARGS;
		writeFileSync(screenPath('trees-perf.json'), JSON.stringify(out, null, 2));
		void browser;
	});
});
