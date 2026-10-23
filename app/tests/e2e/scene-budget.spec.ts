import type { Page } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
import { expect, mapReady, screenPath, test } from './fixtures.js';

/**
 * scene-budget (plan v3 §3.2, S7): the 3D scene takes trees, a registered kind with a low-detail mesh
 * and static fence segments together within budget.
 *
 * - 4,000 tree instances, 1,500 of a registered test kind and 1,500 static segments at z17, pitch 60,
 *   with the view turning: the scene's JS time (update, placement, upload and draw calls) is ≤ 8 ms at
 *   p95. Draw calls and what the caps dropped are logged, not capped.
 * - On a phone-sized screen the trees are capped at 1,000 and the registered kind is off.
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

const stats = (page: Page): Promise<Stats> => page.evaluate(() => (globalThis as any).__tvtSceneTest.stats());

test.describe('scene budget', () => {
	test('4,000 trees, 1,500 registered-kind instances and 1,500 static segments: scene JS p95 ≤ 8 ms at z17, pitch 60, rotating', { tag: '@scene-budget' }, async ({ page, consoleErrors }) => {
		test.setTimeout(900_000);
		await page.setViewportSize({ width: 900, height: 560 });
		await openBudget(page);
		const made = await page.evaluate(() => (globalThis as any).__tvtSceneTest.budget({ trees: 4000, posts: 1500, segments: 1500 }));
		expect(made).toEqual({ trees: 4000, posts: 1500, segments: 1500 });
		await mapReady(page);
		await page.evaluate(() => (globalThis as any).__tvtSceneTest.rotate(true));
		// The scene keeps the JS time of its last 120 frames: wait for that many new ones, so the uploads and the
		// first terrain tiles under the segments are out of the window. A software-GL run draws only a few a second.
		const warm = (await stats(page)).frames;
		await expect.poll(async () => (await stats(page)).frames - warm, { timeout: 420_000, intervals: [1000] }).toBeGreaterThan(130);
		const s = await stats(page);
		await page.screenshot({ path: screenPath('scene-budget-z17.png') });
		await page.evaluate(() => (globalThis as any).__tvtSceneTest.rotate(false));
		record('scene-budget.json', s);
		console.log(`scene budget: JS p95 ${s.p95Ms.toFixed(2)} ms (last ${s.lastFrameMs.toFixed(2)} ms; placement p95 ${s.placeP95Ms.toFixed(2)} ms), ${s.drawCalls} draw calls, ${s.instances} instances, ${s.groundQueries} terrain queries in the last frame, ${s.staticSegments} static segments, dropped ${s.dropped} ${JSON.stringify(s.droppedByGroup)}`);
		test.info().annotations.push({ type: 'scene JS p95', description: `${s.p95Ms.toFixed(2)} ms; ${s.drawCalls} draw calls; dropped ${s.dropped}` });
		// All three loads are there and drawn.
		expect(s.staticSegments).toBe(1500);
		expect(s.instances).toBeGreaterThan(1000);
		// The shrub-like kind keeps to its 300 m radius: the scatter reaches 350 m, so some of it is dropped; the trees' cap of 4,000 drops none.
		expect(s.droppedByGroup['scene-test-posts'] ?? 0).toBeGreaterThan(0);
		expect(s.droppedByGroup['scene-test-trees'] ?? 0).toBe(0);
		expect.soft(s.p95Ms).toBeLessThanOrEqual(SCENE_JS_P95_MS);
		expect(consoleErrors.filter((m) => !/could not be decoded/.test(m))).toEqual([]);
	});

	test('on a phone-sized screen the trees are capped at 1,000 and the registered kind is off', { tag: '@scene-budget' }, async ({ page }) => {
		test.setTimeout(900_000);
		await page.setViewportSize({ width: 390, height: 780 });
		await openBudget(page);
		await page.evaluate(() => (globalThis as any).__tvtSceneTest.budget({ trees: 4000, posts: 1500, segments: 300 }));
		await mapReady(page);
		await expect.poll(async () => (await stats(page)).droppedByGroup['scene-test-trees'] ?? 0, { timeout: 60_000 }).toBe(3000);
		const s = await stats(page);
		console.log(`scene budget on a phone: ${s.instances} instances, dropped ${JSON.stringify(s.droppedByGroup)}, ${s.drawCalls} draw calls`);
		expect(s.droppedByGroup['scene-test-posts']).toBe(1500);
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
