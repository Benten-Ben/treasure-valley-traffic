import type { APIRequestContext, Page } from '@playwright/test';
import { createHash } from 'node:crypto';
import { appendFileSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { expect, env, mapReady, screenPath, seeds, test, type Seed } from './fixtures.js';
import { fetchedAtOf, INDEX, INDEX_HEADER, jpegDir, localDay, stampOf, tick, withComment } from '../../scripts/archive-tick.ts';

/**
 * cameras (docs/14 §14.11): WP12's acceptance, camera windows and live
 * images, in fixture mode (the package's own fake archive, seeded fixtures
 * standing in for 511, CAMERA_IMAGES_ENABLED=true). Nothing here reaches 511.
 *
 * - a click on a camera flies to it and opens its window beside it; each
 *   window's number badge is on its camera; the main-map drape is gone;
 * - after archive-tick, the open window shows the new frame within 20 s; a
 *   frame of another size turns the image-size check on;
 * - a camera fetched on demand gets at most one picture per 55 s however
 *   often the window polls, and all traffic for it stops within 1 s of
 *   closing (network log);
 * - every picture shows its seen time and age, with the live, late, stale
 *   and offline shapes;
 * - at 390×844 a camera opens as a sheet tab;
 * - no request leaves the origin.
 *
 * WP13 and WP14 add their own checks to this spec.
 */
type Win = { key: string; cameraId: number; number: number; status: string | null };
type Badge = { cameraId: number; number: number; x: number | null; y: number | null };
type ViewRow = { id: number; cameraId: number; imageId: number | null };
type CameraRow = { id: number; name: string; status: 'calibrated' | 'uncalibrated' | 'no_image' };

const at = (s: Seed) => `#map=16/${s.pose.lat.toFixed(5)}/${s.pose.lon.toFixed(5)}/0/45&layers=cameras`;

async function openMap(page: Page, hash: string) {
	await page.goto(`/${hash}`);
	await mapReady(page);
	await page.waitForFunction(() => (globalThis as any).__tvtCameras, null, { timeout: 60_000 });
}

const windows = (page: Page): Promise<Win[]> => page.evaluate(() => (globalThis as any).__tvtCameras.windows());
const badges = (page: Page): Promise<Badge[]> => page.evaluate(() => (globalThis as any).__tvtCameras.badges());
const feed = (page: Page) => page.evaluate(() => (globalThis as any).__tvtCameras.feed());
const openCamera = (page: Page, id: number, fly = false) => page.evaluate(([id, fly]) => (globalThis as any).__tvtCameras.open(id, fly), [id, fly] as const);
const dialog = (page: Page, name: string) => page.getByRole('dialog', { name: new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) });
const shownUrl = (page: Page, cameraId: number) =>
	page.evaluate((id) => {
		const imgs = document.querySelectorAll<HTMLImageElement>(`[data-window-key="camera:${id}"] img[data-frame-url]`);
		return imgs.length ? imgs[imgs.length - 1].dataset.frameUrl! : null;
	}, cameraId);
const state = (page: Page, cameraId: number) =>
	page.evaluate((id) => document.querySelector<HTMLElement>(`[data-window-key="camera:${id}"] .cam`)?.dataset.state ?? null, cameraId);

/** A camera's screen point (viewport px). */
const pointOf = (page: Page, lngLat: [number, number]) =>
	page.evaluate((ll) => {
		const map = (globalThis as any).__tvt.map;
		const r = map.getContainer().getBoundingClientRect();
		const p = map.project(ll);
		return { x: r.left + p.x, y: r.top + p.y };
	}, lngLat);

/** Let CSS animations finish (SwiftShader starves them while the map draws), for screenshots. */
async function settle(page: Page) {
	await page
		.waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running'), null, { timeout: 15_000 })
		.catch(() => {});
}

/** Cameras the tests may use besides the seeds: recorded ones and ones fetched on demand, by view. */
async function others(request: APIRequestContext) {
	const views: ViewRow[] = (await (await request.get('/api/cameras/views')).json()).views;
	const cams = new Map<number, CameraRow>(
		(await (await request.get('/api/cameras')).json()).features.map((f: { properties: CameraRow }) => [f.properties.id, f.properties])
	);
	const s = seeds();
	const recorded = new Set(s.archive.imageIds);
	const seeded = new Set(s.seeds.flatMap((x) => [x.imageId]));
	const usable = views
		.filter((v) => v.imageId !== null && !seeded.has(v.imageId) && cams.has(v.cameraId))
		.sort((a, b) => a.id - b.id)
		.map((v) => ({ ...v, imageId: v.imageId!, camera: cams.get(v.cameraId)! }));
	return {
		recorded: usable.filter((v) => recorded.has(v.imageId)),
		onDemand: usable.filter((v) => !recorded.has(v.imageId) && v.camera.status === 'uncalibrated')
	};
}

/** Append a frame with these bytes to the fake archive, as the capture service would, seen at `when`. */
function appendFrame(image: number, bytes: Buffer, when: Date) {
	const root = env().archive;
	let t = new Date(Math.floor(when.getTime() / 1000) * 1000);
	const dir = jpegDir(root, image, localDay(t));
	mkdirSync(dir, { recursive: true });
	while (existsSync(join(dir, `${stampOf(t)}.jpg`))) t = new Date(t.getTime() + 1000);
	const stamp = stampOf(t);
	const body = withComment(bytes, `tvt cameras spec ${fetchedAtOf(t)} (synthetic test frame)`);
	writeFileSync(join(dir, `${stamp}.jpg`), body);
	const index = join(dir, INDEX);
	if (!existsSync(index)) writeFileSync(index, `${INDEX_HEADER}\n`);
	appendFileSync(index, `${fetchedAtOf(t)},${stamp}.jpg,${body.length},${createHash('sha256').update(body).digest('hex')}\n`);
	return { stamp };
}

const fixture = (name: string) => join(env().framesDir, '_fixture', name);

/**
 * Console errors, less MapLibre's own tile-decoding noise while the basemap
 * loads (seen once at z16 before any camera window opened: a raster tile
 * that SwiftShader's Chromium couldn't decode, then MapLibre's bare "Error").
 * Nothing in the Cameras layer decodes images on the map.
 */
const TILE_NOISE = new Set(['map error InvalidStateError: The source image could not be decoded.', 'map error Error']);
const realErrors = (errors: string[]) => errors.filter((e) => !TILE_NOISE.has(e));

test.describe('cameras', () => {
	test('a click flies to the camera and opens its window beside it; badges match the windows', { tag: '@wp12' }, async ({ page, consoleErrors, offsite }) => {
		test.setTimeout(300_000);
		mkdirSync(env().screens, { recursive: true });
		const s = seeds();
		const key = s.seeds.find((x) => x.kind === 'key')!;
		const roll = s.seeds.find((x) => x.kind === 'roll')!;

		// The icons downtown: calibrated ✓, needs calibration ?, not on 511, the recorded notch, footprints from z14.
		await openMap(page, '#map=15.5/43.6160/-116.2010/0/0&layers=cameras');
		await settle(page);
		await page.screenshot({ path: screenPath('wp12-icons.png') });
		// The main-map drape is gone: no "Camera images on the map", no drape layers.
		await expect(page.getByText('Camera images on the map')).toHaveCount(0);
		const drapes = await page.evaluate(() => (globalThis as any).__tvt.map.getLayersOrder().filter((id: string) => id.startsWith('drape-')));
		expect(drapes).toEqual([]);

		await openMap(page, at(key));
		const pole = await page.evaluate((id) => (globalThis as any).__tvtCameras.cameras().find((c: any) => c.id === id), key.cameraId);
		expect(pole).toMatchObject({ id: key.cameraId, status: 'calibrated', recorded: true });
		// The recorded notch is on (feature-state), and the icon is drawn where the camera is.
		await expect
			.poll(() => page.evaluate((id) => (globalThis as any).__tvt.map.getFeatureState({ source: 'cameras', id }).recorded, key.cameraId))
			.toBe(true);
		const before = await page.evaluate(() => (globalThis as any).__tvt.map.getBearing());
		const p = await pointOf(page, [pole.lng, pole.lat]);
		const hit = await page.evaluate(
			({ x, y }) => (globalThis as any).__tvt.map.queryRenderedFeatures([[x - 6, y - 6], [x + 6, y + 6]]).map((f: any) => f.layer.id),
			p
		);
		expect(hit).toContain('cameras-calibrated');

		// One click: fly there (zoom 18, the bearing kept, pitch 50) and open the window beside it.
		await page.mouse.click(p.x, p.y);
		const win = dialog(page, key.name);
		await expect(win).toBeVisible();
		await expect(win).toHaveAttribute('data-window-number', '1');
		await mapReady(page);
		const view = await page.evaluate(() => (globalThis as any).__tvt.view);
		expect(view.zoom).toBeCloseTo(18, 3);
		expect(view.pitch).toBeCloseTo(50, 3);
		expect(view.bearing).toBeCloseTo(before, 3);
		const cam = await pointOf(page, [pole.lng, pole.lat]);
		const box = (await win.boundingBox())!;
		const inside = cam.x >= box.x && cam.x <= box.x + box.width && cam.y >= box.y && cam.y <= box.y + box.height;
		expect(inside, 'the window never covers its camera').toBe(false);
		expect(Math.min(Math.abs(box.x - cam.x), Math.abs(cam.x - (box.x + box.width))), '24 px beside the camera').toBeCloseTo(24, -1);
		// The selection is the camera (its card), and the picture arrives.
		expect(await page.evaluate(() => (globalThis as any).__tvt.layers.selection)).toMatchObject({ kind: 'camera', id: String(key.cameraId) });
		await expect.poll(() => shownUrl(page, key.cameraId), { timeout: 30_000 }).toMatch(new RegExp(`^/camera-frames/${key.imageId}/`));
		await expect(win.getByText(/^(seen \d+:\d\d ago|seen \d+ h \d\d min ago) · updates about every minute$/)).toBeVisible();
		await settle(page);
		await page.screenshot({ path: screenPath('wp12-click-window.png') });

		// A second window: number 2, on its camera too.
		expect(await openCamera(page, roll.cameraId)).toBe(true);
		await expect(dialog(page, roll.name)).toHaveAttribute('data-window-number', '2');
		await expect.poll(async () => (await badges(page)).map((b) => `${b.cameraId}:${b.number}`).sort()).toEqual(
			[`${key.cameraId}:1`, `${roll.cameraId}:2`].sort()
		);
		// Window badges match camera badges, and each badge is drawn on its camera.
		const wins = await windows(page);
		const drawn = await badges(page);
		for (const w of wins) expect(drawn.find((b) => b.cameraId === w.cameraId)?.number, `badge of ${w.key}`).toBe(w.number);
		await expect.poll(async () => (await badges(page)).find((b) => b.cameraId === key.cameraId)?.x ?? null).not.toBeNull();
		const b1 = (await badges(page)).find((b) => b.cameraId === key.cameraId)!;
		const c1 = await pointOf(page, [pole.lng, pole.lat]);
		expect(Math.hypot(b1.x! - c1.x, b1.y! - c1.y), 'badge anchored on the camera').toBeLessThan(3);

		// Closing a window takes its badge off its camera; the other keeps its number.
		await win.getByRole('button', { name: `Close ${key.name}` }).click();
		await expect.poll(async () => (await badges(page)).map((b) => `${b.cameraId}:${b.number}`)).toEqual([`${roll.cameraId}:2`]);
		await dialog(page, roll.name).getByRole('button', { name: `Close ${roll.name}` }).click();
		await expect.poll(() => feed(page)).toMatchObject({ running: false, watching: [] });
		expect(offsite).toEqual([]);
		expect(realErrors(consoleErrors)).toEqual([]);
	});

	test('after archive-tick the open window shows the new frame within 20 s; another size turns the size check on', { tag: '@wp12' }, async ({ page, offsite }) => {
		test.setTimeout(300_000);
		const key = seeds().seeds.find((x) => x.kind === 'key')!;
		await openMap(page, at(key));
		expect(await openCamera(page, key.cameraId)).toBe(true);
		const win = dialog(page, key.name);
		await expect.poll(() => shownUrl(page, key.cameraId), { timeout: 30_000 }).toMatch(new RegExp(`^/camera-frames/${key.imageId}/`));
		// Let the first poll's answer land, so the tick is picked up by a later poll.
		await page.waitForTimeout(1_000);

		const [ticked] = tick(env().archive, [key.imageId]);
		const t0 = Date.now();
		await expect.poll(() => shownUrl(page, key.cameraId), { timeout: 20_000, intervals: [250] }).toContain(ticked.stamp);
		const ms = Date.now() - t0;
		test.info().annotations.push({ type: 'new frame shown after', description: `${ms} ms` });
		appendFileSync(screenPath('wp12-tick.txt'), `${new Date().toISOString()} new archive frame shown in the window after ${ms} ms\n`);
		expect(ms).toBeLessThan(20_000);
		await expect.poll(() => state(page, key.cameraId)).toBe('fresh');
		await expect(win.getByText(/^seen 0:\d\d ago · updates about every minute$/)).toBeVisible();
		expect((await windows(page))[0].status).toBe('● live');

		// The image-size check: a 1920×1166 frame for a camera calibrated at 768×466.
		const hd = seeds().seeds.find((x) => x.kind === 'hd')!;
		const big = readFileSync(fixture(`view-${hd.viewId}.jpg`));
		const { stamp } = appendFrame(key.imageId, big, new Date());
		await expect.poll(() => shownUrl(page, key.cameraId), { timeout: 20_000 }).toContain(stamp);
		await expect(win.getByText(`Image size changed (${key.size.width}×${key.size.height} → ${hd.size.width}×${hd.size.height}); recalibrate`)).toBeVisible();
		await expect(win.getByRole('button', { name: 'Look through' })).toBeDisabled();
		await settle(page);
		await win.screenshot({ path: screenPath('wp12-size-changed.png') });
		// Back to the calibrated size.
		const original = readFileSync(join(env().framesDir, key.frame));
		const back = appendFrame(key.imageId, original, new Date(Date.now() + 1000));
		await expect.poll(() => shownUrl(page, key.cameraId), { timeout: 20_000 }).toContain(back.stamp);
		await expect(win.getByText(/^Image size changed/)).toHaveCount(0);
		expect(offsite).toEqual([]);
	});

	test('a camera fetched on demand: at most one picture per 55 s, and no request within 1 s of closing', { tag: '@wp12' }, async ({ page, request, offsite }) => {
		test.setTimeout(300_000);
		const { onDemand } = await others(request);
		const v = onDemand[0];
		expect(v, 'a camera fetched on demand').toBeTruthy();
		// Its stand-in for 511 changes every second (new bytes, as a real camera's would).
		const file = fixture(`image-${v.imageId}.jpg`);
		const base = readFileSync(fixture('default.jpg'));
		let n = 0;
		const rotate = () => writeFileSync(file, withComment(base, `tvt cameras spec rotation ${n++}`));
		rotate();
		const rotation = setInterval(rotate, 1_000);
		const log: { kind: 'poll' | 'frame'; at: number; url: string }[] = [];
		page.on('request', (r) => {
			const u = new URL(r.url());
			if (u.pathname === '/api/cameras/live' && (u.searchParams.get('views') ?? '').split(',').includes(String(v.id)))
				log.push({ kind: 'poll', at: Date.now(), url: u.pathname + u.search });
			else if (u.pathname.startsWith(`/api/views/${v.id}/live/`)) log.push({ kind: 'frame', at: Date.now(), url: u.pathname });
		});
		try {
			// Fake timers from the start (time flows until moved by hand): the polls can be hurried along.
			await page.clock.install();
			await openMap(page, `#map=16/43.6150/-116.2023/0/0&layers=cameras`);
			expect(await openCamera(page, v.cameraId)).toBe(true);
			await expect.poll(() => shownUrl(page, v.cameraId), { timeout: 30_000 }).toMatch(new RegExp(`^/api/views/${v.id}/live/[0-9a-f]{64}$`));
			const opened = Date.now();
			// 40 s of real time with a poll every 2 s (the client's 15 s steps, hurried): the
			// picture changed 40 times upstream, the window asked 20 times, one picture came.
			while (Date.now() - opened < 40_000) {
				await page.clock.runFor(15_000);
				await page.waitForTimeout(2_000);
			}
			const polls = log.filter((e) => e.kind === 'poll');
			const frames = log.filter((e) => e.kind === 'frame');
			test.info().annotations.push({ type: 'on demand', description: `${polls.length} polls, ${frames.length} picture(s) in ${Math.round((Date.now() - opened) / 1000)} s` });
			expect(polls.length).toBeGreaterThanOrEqual(10);
			expect(frames.length, 'pictures fetched: at most one per 55 s').toBeLessThanOrEqual(Math.ceil((Date.now() - log[0].at) / 55_000));
			for (let i = 1; i < frames.length; i++) expect(frames[i].at - frames[i - 1].at).toBeGreaterThanOrEqual(55_000);

			// Close it: nothing more for this camera, however long we wait.
			const name = v.camera.name;
			await dialog(page, name).getByRole('button', { name: `Close ${name}` }).click();
			const closed = Date.now();
			await expect.poll(() => feed(page), { timeout: 1_000 }).toMatchObject({ running: false });
			await page.clock.runFor(120_000);
			await page.waitForTimeout(1_500);
			const late = log.filter((e) => e.at > closed + 1_000);
			expect(late, 'requests more than 1 s after closing').toEqual([]);
			appendFileSync(
				screenPath('wp12-on-demand.txt'),
				`${new Date().toISOString()} view ${v.id}: ${polls.length} polls, ${frames.length} picture(s) while open; ${log.filter((e) => e.at > closed).length} request(s) after closing\n`
			);
		} finally {
			clearInterval(rotation);
			rmSync(file, { force: true });
		}
		expect(offsite).toEqual([]);
	});

	test('every picture shows its seen time and age: live, late, stale and offline', { tag: '@wp12' }, async ({ page, request, consoleErrors, offsite }) => {
		test.setTimeout(300_000);
		const key = seeds().seeds.find((x) => x.kind === 'key')!;
		const { recorded, onDemand } = await others(request);
		const late = recorded[0];
		const stale = recorded[1];
		const offline = onDemand[1];
		expect([late, stale, offline].every(Boolean), 'two recorded cameras and one fetched on demand').toBe(true);
		// Late: the newest frame seen 5 minutes ago; stale: 15 minutes ago; offline: 511 (the fixture) sends a broken picture.
		tick(env().archive, [key.imageId]);
		tick(env().archive, [late.imageId], new Date(Date.now() - 5 * 60_000));
		tick(env().archive, [stale.imageId], new Date(Date.now() - 15 * 60_000));
		const broken = fixture(`image-${offline.imageId}.jpg`);
		writeFileSync(broken, 'not a picture');
		try {
			// Room for the four windows side by side: two docked on each side (the dock buttons, WCAG 2.5.7).
			await page.setViewportSize({ width: 1600, height: 1400 });
			await openMap(page, at(key));
			const names = new Map<number, string>([
				[key.cameraId, key.name],
				[late.cameraId, late.camera.name],
				[stale.cameraId, stale.camera.name],
				[offline.cameraId, offline.camera.name]
			]);
			let k = 0;
			for (const [id, name] of names) {
				expect(await openCamera(page, id)).toBe(true);
				await dialog(page, name).getByRole('button', { name: k++ < 2 ? 'Dock left' : 'Dock right' }).click();
			}
			const expected: [number, string, string, RegExp][] = [
				[key.cameraId, 'fresh', '● live', /^seen 0:\d\d ago · updates about every minute$/],
				[late.cameraId, 'late', '▲ late', /^seen [45]:\d\d ago · updates about every minute$/],
				[stale.cameraId, 'stale', '■ stale', /^seen 1[56]:\d\d ago · updates about every minute$/],
				[offline.cameraId, 'offline', '■ offline', /^no picture yet · updates about every minute while open$/]
			];
			for (const [id, kind] of expected) await expect.poll(() => state(page, id), { timeout: 30_000 }).toBe(kind);
			const wins = await windows(page);
			for (const [id, , header, foot] of expected) {
				expect(wins.find((w) => w.cameraId === id)?.status, `header of camera ${id}`).toBe(header);
				const el = page.locator(`[data-window-key="camera:${id}"]`);
				await expect(el.locator('.seen')).toHaveText(foot);
				// The chip: shape and word, never color alone.
				await expect(el.locator('[data-freshness]')).toHaveText(header.split(' ')[1]);
			}
			await expect(page.locator(`[data-window-key="camera:${offline.cameraId}"]`).getByText(/not a complete JPEG/)).toBeVisible();
			await settle(page);
			await page.screenshot({ path: screenPath('wp12-states.png') });
			expect(realErrors(consoleErrors)).toEqual([]);
		} finally {
			rmSync(broken, { force: true });
			// Fresh again for whoever comes next.
			tick(env().archive, [late.imageId, stale.imageId]);
		}
		expect(offsite).toEqual([]);
	});

	test('at 390×844 a camera opens as a sheet tab with its picture', { tag: '@wp12' }, async ({ page, offsite }) => {
		test.setTimeout(300_000);
		const key = seeds().seeds.find((x) => x.kind === 'key')!;
		await page.setViewportSize({ width: 390, height: 844 });
		await openMap(page, at(key));
		const cam = await page.evaluate((id) => (globalThis as any).__tvtCameras.cameras().find((c: any) => c.id === id), key.cameraId);
		const p = await pointOf(page, [cam.lng, cam.lat]);
		await page.mouse.click(p.x, p.y);
		const sheet = page.getByRole('region', { name: 'Details' });
		await expect(sheet.getByRole('tab', { name: new RegExp(key.name) })).toHaveAttribute('aria-selected', 'true');
		await expect(page.getByRole('dialog')).toHaveCount(0);
		const panel = sheet.getByRole('tabpanel', { name: new RegExp(key.name) });
		await expect(panel.locator('img[data-frame-url]').last()).toBeVisible({ timeout: 30_000 });
		await mapReady(page);
		// The camera lands above the sheet, with its badge.
		const after = await pointOf(page, [cam.lng, cam.lat]);
		const sheetBox = (await sheet.boundingBox())!;
		expect(after.y).toBeLessThan(sheetBox.y);
		await expect.poll(async () => (await badges(page)).map((b) => `${b.cameraId}:${b.number}`)).toEqual([`${key.cameraId}:1`]);
		expect(await page.evaluate(() => document.documentElement.scrollWidth), 'no horizontal scroll').toBeLessThanOrEqual(390);
		await settle(page);
		await page.screenshot({ path: screenPath('wp12-phone.png') });
		expect(offsite).toEqual([]);
	});
});
