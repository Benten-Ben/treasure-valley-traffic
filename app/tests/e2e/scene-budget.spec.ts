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

type Stats = { frames: number; drawCalls: number; instances: number; lastFrameMs: number; p95Ms: number; dropped: number; droppedByGroup: Record<string, number>; staticSegments: number };

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
		test.setTimeout(600_000);
		await openBudget(page);
		const made = await page.evaluate(() => (globalThis as any).__tvtSceneTest.budget({ trees: 4000, posts: 1500, segments: 1500 }));
		expect(made).toEqual({ trees: 4000, posts: 1500, segments: 1500 });
		await mapReady(page);
		await page.evaluate(() => (globalThis as any).__tvtSceneTest.rotate(true));
		// Let the first frames (uploads, terrain tiles under the segments) go by, then take the last 120 frames' p95.
		const warm = (await stats(page)).frames;
		await expect.poll(async () => (await stats(page)).frames - warm, { timeout: 120_000, intervals: [500] }).toBeGreaterThan(150);
		const warm2 = (await stats(page)).frames;
		await expect.poll(async () => (await stats(page)).frames - warm2, { timeout: 120_000, intervals: [500] }).toBeGreaterThan(130);
		const s = await stats(page);
		await page.screenshot({ path: screenPath('scene-budget-z17.png') });
		await page.evaluate(() => (globalThis as any).__tvtSceneTest.rotate(false));
		record('scene-budget.json', s);
		console.log(`scene budget: JS p95 ${s.p95Ms.toFixed(2)} ms (last ${s.lastFrameMs.toFixed(2)} ms), ${s.drawCalls} draw calls, ${s.instances} instances, ${s.staticSegments} static segments, dropped ${s.dropped} ${JSON.stringify(s.droppedByGroup)}`);
		test.info().annotations.push({ type: 'scene JS p95', description: `${s.p95Ms.toFixed(2)} ms; ${s.drawCalls} draw calls; dropped ${s.dropped}` });
		// All three loads are there and drawn.
		expect(s.staticSegments).toBe(1500);
		expect(s.instances).toBeGreaterThan(1000);
		// The shrub-like kind keeps to its 300 m radius: the scatter reaches 350 m, so some of it is dropped; the trees' cap of 4,000 drops none.
		expect(s.droppedByGroup['scene-test-posts'] ?? 0).toBeGreaterThan(0);
		expect(s.droppedByGroup['scene-test-trees'] ?? 0).toBe(0);
		expect(s.p95Ms).toBeLessThanOrEqual(SCENE_JS_P95_MS);
		expect(consoleErrors.filter((m) => !/could not be decoded/.test(m))).toEqual([]);
	});

	test('on a phone-sized screen the trees are capped at 1,000 and the registered kind is off', { tag: '@scene-budget' }, async ({ page }) => {
		test.setTimeout(600_000);
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
});
