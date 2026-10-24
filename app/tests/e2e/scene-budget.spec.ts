import type { Page } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { loadavg } from 'node:os';
import { dirname } from 'node:path';
import { chromium } from '@playwright/test';
import { lockedArgs } from '../../scripts/harness-env.mjs';
import { expect, mapReady, screenPath, test } from './fixtures.js';

/**
 * scene-budget (plan v3 §3.2, S7): the 3D scene takes trees, a registered kind with a low-detail mesh
 * and static fence segments together within budget.
 *
 * - 4,000 tree instances, 1,500 of a registered test kind and 1,500 static segments at z17, pitch 60,
 *   with the view turning: the scene's JS time (update, placement, upload and draw calls) is ≤ 8 ms at
 *   p95. Draw calls and what the caps dropped are logged, not capped.
 * - On a phone-sized screen the registered kind is off and the trees are not capped by the scene (production's
 *   trees layer caps its own list; the scene gets no cap for them).
 *
 * The scene's own numbers come through the `?scene-test` hooks (`__tvtSceneTest`, test-scene.ts).
 */

const CENTRE = { lat: 43.632, lng: -116.175 };
const SCENE_JS_P95_MS = 8;

type Stats = { frames: number; drawCalls: number; instances: number; lastFrameMs: number; p95Ms: number; placeMs: number; placeP95Ms: number; groundQueries: number; lodInstances: number; dropped: number; droppedByGroup: Record<string, number>; staticSegments: number };

function record(name: string, data: unknown) {
	const file = screenPath(name);
	mkdirSync(dirname(file), { recursive: true });
	writeFileSync(file, JSON.stringify(data, null, 2));
}

async function openBudget(page: Page) {
	await page.goto(`/?scene-test#map=17/${CENTRE.lat}/${CENTRE.lng}/20/60&layers=none`);
	await page.waitForFunction(() => (globalThis as any).__tvt?.map, null, { timeout: 120_000 });
	await mapReady(page);
	await page.waitForFunction(() => (globalThis as any).__tvtSceneTest, null, { timeout: 90_000 });
	expect(await page.evaluate(() => (globalThis as any).__tvtSceneTest.ok()), 'the scene is running').toBe(true);
	// The 1,000-bus grid isn't part of this case.
	await page.evaluate(() => (globalThis as any).__tvtSceneTest.clear());
}


/** Frames measured per run: the scene's own p95 window is 120, which is too few to trust. */
const FRAMES = 600;

type Q = { p50: number; p95: number; p99: number; max: number; mean: number };
const quant = (xs: number[]): Q => {
	if (!xs.length) return { p50: 0, p95: 0, p99: 0, max: 0, mean: 0 };
	const s = [...xs].sort((a, b) => a - b);
	const at = (q: number) => s[Math.min(s.length - 1, Math.floor(s.length * q))];
	return { p50: at(0.5), p95: at(0.95), p99: at(0.99), max: s[s.length - 1], mean: xs.reduce((a, b) => a + b, 0) / xs.length };
};

/** Per rendered frame, collected in the page: the scene's JS ms, its placement ms, its tracked ground reads, every terrain query made inside the render, and the wall time since the last render. */
async function instrument(page: Page) {
	await page.evaluate(() => {
		const w = globalThis as any;
		const map = w.__tvt.map;
		const impl = map.getLayer('scene-3d').implementation;
		const rows: number[][] = [];
		w.__budgetRows = rows;
		let inRender = false;
		let calls = 0;
		const q = map.queryTerrainElevation.bind(map);
		map.queryTerrainElevation = (...a: unknown[]) => {
			if (inRender) calls++;
			return (q as any)(...a);
		};
		const render = impl.render;
		let last = performance.now();
		impl.render = function (gl: unknown, args: unknown) {
			inRender = true;
			calls = 0;
			try {
				return render.call(this, gl, args);
			} finally {
				inRender = false;
				const s = w.__tvtSceneTest.stats();
				const now = performance.now();
				rows.push([s.lastFrameMs, s.placeMs, s.groundQueries, calls, now - last]);
				last = now;
			}
		};
	});
}

type Node = { id: number; callFrame: { functionName: string; url: string; lineNumber: number }; children?: number[] };

/** Self and inclusive time per function from a CDP CPU profile, in ms. */
function profileTop(profile: { nodes: Node[]; samples: number[]; timeDeltas: number[] }) {
	const byId = new Map(profile.nodes.map((n) => [n.id, n]));
	const parent = new Map<number, number>();
	for (const n of profile.nodes) for (const c of n.children ?? []) parent.set(c, n.id);
	const name = (n: Node) => `${n.callFrame.functionName || '(anonymous)'} ${n.callFrame.url.split('/').pop() ?? ''}:${n.callFrame.lineNumber + 1}`;
	const self = new Map<string, number>();
	const incl = new Map<string, number>();
	let total = 0;
	profile.samples.forEach((id, i) => {
		const dt = (profile.timeDeltas[i] ?? 0) / 1000;
		total += dt;
		const n = byId.get(id)!;
		self.set(name(n), (self.get(name(n)) ?? 0) + dt);
		const seen = new Set<string>();
		for (let cur: number | undefined = id; cur !== undefined; cur = parent.get(cur)) {
			const k = name(byId.get(cur)!);
			if (seen.has(k)) continue;
			seen.add(k);
			incl.set(k, (incl.get(k) ?? 0) + dt);
		}
	});
	const top = (m: Map<string, number>, skip: RegExp) =>
		[...m].filter(([k]) => !skip.test(k)).sort((a, b) => b[1] - a[1]).slice(0, 14).map(([k, v]) => ({ fn: k, ms: Math.round(v) }));
	return { totalMs: Math.round(total), self: top(self, /^\((root|program|idle|garbage collector)\)/), inclusive: top(incl, /^\((root|program|idle|garbage collector)\)/) };
}

/** The budget case on one page: the numbers over `FRAMES` frames, a CPU profile of the window, the renderer and the machine's load. */
async function measureBudget(page: Page) {
	await openBudget(page);
	const renderer = await page.evaluate(() => {
		const gl = document.createElement('canvas').getContext('webgl2');
		const ext = gl?.getExtension('WEBGL_debug_renderer_info');
		return gl ? String(gl.getParameter(ext ? ext.UNMASKED_RENDERER_WEBGL : gl.RENDERER)) : 'none';
	});
	const made = await page.evaluate(() => (globalThis as any).__tvtSceneTest.budget({ trees: 4000, posts: 1500, segments: 1500 }));
	expect(made).toEqual({ trees: 4000, posts: 1500, segments: 1500 });
	await mapReady(page);
	await page.evaluate(() => (globalThis as any).__tvtSceneTest.rotate(true));
	// Warm: the uploads and the first terrain tiles under the segments are out of the window.
	const warm = (await stats(page)).frames;
	await expect.poll(async () => (await stats(page)).frames - warm, { timeout: 420_000, intervals: [1000] }).toBeGreaterThan(130);
	const loadBefore = loadavg()[0];
	await instrument(page);
	const cdp = await page.context().newCDPSession(page);
	await cdp.send('Profiler.enable');
	await cdp.send('Profiler.setSamplingInterval', { interval: 250 });
	await cdp.send('Profiler.start');
	await expect.poll(() => page.evaluate(() => (globalThis as any).__budgetRows.length), { timeout: 800_000, intervals: [1000] }).toBeGreaterThanOrEqual(FRAMES);
	const { profile } = await cdp.send('Profiler.stop');
	const loadAfter = loadavg()[0];
	const rows: number[][] = await page.evaluate(() => (globalThis as any).__budgetRows);
	const s = await stats(page);
	await page.evaluate(() => (globalThis as any).__tvtSceneTest.rotate(false));
	const col = (i: number) => rows.map((r) => r[i]);
	// Terrain queries made in the render beyond the tracker's own are the static batches' (and the centre's).
	const staticReads = rows.map((r) => r[3] - r[2]);
	return {
		renderer,
		load: { before: loadBefore, after: loadAfter },
		frames: rows.length,
		jsMs: quant(col(0)),
		placeMs: quant(col(1)),
		drawMs: quant(rows.map((r) => r[0] - r[1])),
		wallMs: quant(col(4)),
		trackedReads: quant(col(2)),
		staticReads: quant(staticReads),
		framesWithStaticReads: staticReads.filter((n) => n > 2).length,
		profile: profileTop(profile),
		last: s
	};
}

type Budget = Awaited<ReturnType<typeof measureBudget>>;
const f = (q: Q) => `p50 ${q.p50.toFixed(2)} p95 ${q.p95.toFixed(2)} p99 ${q.p99.toFixed(2)} max ${q.max.toFixed(2)}`;

function report(label: string, r: Budget) {
	const s = r.last;
	console.log(
		`scene budget ${label} (${r.renderer}; load ${r.load.before.toFixed(1)} before, ${r.load.after.toFixed(1)} after): ${r.frames} frames; JS ms ${f(r.jsMs)}; placement ms ${f(r.placeMs)}; draw ms ${f(r.drawMs)}; wall ms between renders ${f(r.wallMs)}; ` +
			`terrain reads per frame: tracked mean ${r.trackedReads.mean.toFixed(1)} (max ${r.trackedReads.max}), other mean ${r.staticReads.mean.toFixed(1)} (max ${r.staticReads.max}, ${r.framesWithStaticReads} frames over 2); ` +
			`${s.drawCalls} draw calls, ${s.instances} instances, ${s.staticSegments} static segments, dropped ${s.dropped} ${JSON.stringify(s.droppedByGroup)}`
	);
	console.log(`scene budget ${label} profile: ${JSON.stringify(r.profile)}`);
}

/** All three loads are there and drawn. */
function checkLoads(s: Stats) {
	expect(s.staticSegments).toBe(1500);
	expect(s.instances).toBeGreaterThan(1000);
	// The shrub-like kind keeps to its 300 m radius: the scatter reaches 350 m, so some of it is dropped; the trees group has no cap (production's options), so the scene drops none.
	expect(s.droppedByGroup['scene-test-posts'] ?? 0).toBeGreaterThan(0);
	expect(s.droppedByGroup['scene-test-trees'] ?? 0).toBe(0);
}

const stats = (page: Page): Promise<Stats> => page.evaluate(() => (globalThis as any).__tvtSceneTest.stats());

test.describe('scene budget', () => {
	test('4,000 trees, 1,500 registered-kind instances and 1,500 static segments: scene JS p95 ≤ 8 ms at z17, pitch 60, rotating', { tag: '@scene-budget' }, async ({ page, consoleErrors }) => {
		test.setTimeout(1_200_000);
		await page.setViewportSize({ width: 900, height: 560 });
		const r = await measureBudget(page);
		await page.screenshot({ path: screenPath('scene-budget-z17.png') });
		record('scene-budget.json', r);
		report('SwiftShader', r);
		test.info().annotations.push({ type: 'scene JS p95', description: `${r.jsMs.p95.toFixed(2)} ms over ${r.frames} frames; ${r.last.drawCalls} draw calls; dropped ${r.last.dropped}` });
		checkLoads(r.last);
		expect.soft(r.jsMs.p95).toBeLessThanOrEqual(SCENE_JS_P95_MS);
		expect(consoleErrors.filter((m) => !/could not be decoded/.test(m))).toEqual([]);
	});

	test('the same case on the laptop\'s GPU (headless Chromium with Metal), when it starts', { tag: '@scene-budget' }, async ({}, testInfo) => {
		test.skip(process.platform !== 'darwin', 'the Metal backend exists only on macOS');
		test.setTimeout(1_200_000);
		const browser = await chromium.launch({ args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', ...lockedArgs()] });
		try {
			const ctx = await browser.newContext({ viewport: { width: 900, height: 560 }, baseURL: testInfo.project.use.baseURL });
			const page = await ctx.newPage();
			const errors: string[] = [];
			page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
			const r = await measureBudget(page);
			await page.screenshot({ path: screenPath('scene-budget-z17-gpu.png') });
			// A software fallback must not be recorded or judged as the GPU.
			test.skip(/swiftshader|llvmpipe|software/i.test(r.renderer ?? ''), `no hardware renderer (${r.renderer})`);
			record('scene-budget-gpu.json', r);
			report('GPU', r);
			testInfo.annotations.push({ type: 'scene JS p95 (GPU)', description: `${r.jsMs.p95.toFixed(2)} ms over ${r.frames} frames on ${r.renderer}` });
			checkLoads(r.last);
			expect.soft(r.jsMs.p95).toBeLessThanOrEqual(SCENE_JS_P95_MS);
			expect(errors.filter((m) => !/could not be decoded/.test(m))).toEqual([]);
		} finally {
			await browser.close();
		}
	});

	test('on a phone-sized screen the registered kind is off and the scene drops no trees', { tag: '@scene-budget' }, async ({ page }) => {
		test.setTimeout(900_000);
		await page.setViewportSize({ width: 390, height: 780 });
		await openBudget(page);
		await page.evaluate(() => (globalThis as any).__tvtSceneTest.budget({ trees: 4000, posts: 1500, segments: 300 }));
		await mapReady(page);
		await expect.poll(async () => (await stats(page)).droppedByGroup['scene-test-posts'] ?? 0, { timeout: 60_000 }).toBe(1500);
		const s = await stats(page);
		console.log(`scene budget on a phone: ${s.instances} instances, dropped ${JSON.stringify(s.droppedByGroup)}, ${s.drawCalls} draw calls`);
		expect(s.droppedByGroup['scene-test-posts']).toBe(1500);
		expect(s.droppedByGroup['scene-test-trees'] ?? 0).toBe(0);
		expect(s.staticSegments).toBe(300);
	});

	test('draw calls with every kind in use are counted, not capped: 14 built in, plus one per registered kind, low-detail mesh and static group', { tag: '@scene-budget' }, async ({ page }) => {
		test.setTimeout(900_000);
		await page.setViewportSize({ width: 900, height: 560 });
		await openBudget(page);
		// Count every WebGL draw made inside the scene layer's render, independently of the scene's own counter.
		await page.evaluate(() => {
			const impl = (globalThis as any).__tvt.map.getLayer('scene-3d').implementation;
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
		const count = () =>
			page.evaluate(
				() =>
					new Promise<{ draws: number; stats: Stats }>((resolve) => {
						const map = (globalThis as any).__tvt.map;
						map.once('render', () => resolve({ draws: (globalThis as any).__sceneDraws, stats: (globalThis as any).__tvtSceneTest.stats() }));
						map.triggerRepaint();
					})
			);
		// The showcase (bus, stop, pole, head, pin, shadow, cone, lines, photo) with a bus selected (the ring), and trees of all three kinds.
		await page.evaluate(async () => {
			const t = (globalThis as any).__tvtSceneTest;
			await t.showcase(true);
			t.budget({ trees: 300, posts: 0, segments: 0 });
			t.overPhoto(true);
		});
		await mapReady(page);
		const bus = await page.evaluate(() => (globalThis as any).__tvtSceneTest.placed().find((p: any) => p.id === 'show-bus'));
		expect(bus, 'the showcase bus is on screen').toBeTruthy();
		await page.mouse.click(bus.x, bus.y);
		await expect.poll(() => page.evaluate(() => (globalThis as any).__tvt.layers.selection?.id)).toBe('show-bus');
		const builtIn = await count();
		console.log(`draw calls, built-in kinds in use: ${builtIn.draws} (scene's count ${builtIn.stats.drawCalls}), ${builtIn.stats.instances} instances`);
		expect(builtIn.stats.drawCalls).toBe(builtIn.draws);
		// Nine mesh kinds (bus, stop, pole, head, pin, ring and three trees), shadows, cones, lines and two photo calls.
		expect(builtIn.draws).toBe(14);
		// Then a registered kind (with its low-detail mesh) and a static group: one call each more.
		await page.evaluate(() => (globalThis as any).__tvtSceneTest.budget({ trees: 300, posts: 300, segments: 100 }));
		await mapReady(page);
		const more = await count();
		console.log(`draw calls, plus a registered kind, its low-detail mesh and a static group: ${more.draws} (scene's count ${more.stats.drawCalls}), ${more.stats.lodInstances} low-detail instances`);
		record('draw-calls-budget.json', { builtIn, more });
		expect(more.stats.drawCalls).toBe(more.draws);
		// The static group, and the registered kind's low-detail mesh (every post is under 12 px across at z17).
		expect(more.draws).toBeGreaterThanOrEqual(builtIn.draws + 2);
		expect(more.stats.lodInstances).toBeGreaterThan(0);
		expect(more.stats.staticSegments).toBe(100);
	});
});
