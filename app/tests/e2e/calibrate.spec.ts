import type { Page } from '@playwright/test';
import { createHash } from 'node:crypto';
import postgres from 'postgres';
import { recordNetwork } from '../../scripts/net.mjs';
import { expect, mapReady, screenPath, seeds, test, type Seed } from './fixtures.js';

/**
 * cameras, WP14 (docs/14 §14.10 "WP14", §14.6 "Calibrating on the map"):
 * Calibrate mode on the shared map, on the seeded calibrations (map-rendered
 * frames, never a real camera image), in fixture mode.
 *
 * - entering and leaving restore the view, layers, base and windows, and
 *   the return leg asks for no tile the map had before and no manifest
 *   (Back and Esc);
 * - "Use this frame" keeps exactly the bytes shown in the Live inset, for an
 *   archive frame and an on-demand one;
 * - a reload mid-calibration resumes the draft; Ctrl+Z, Delete and Cancel's
 *   question;
 * - ground heights picked at exaggeration 1.0 and 1.3 agree within 0.25 m;
 * - Check alignment looks through the unsaved pose, and Step out comes back
 *   to Calibrate;
 * - a save works against the seeded database, reopens the window and offers
 *   "Look through to check";
 * - phones get "Calibration needs a larger screen";
 * - /v1/calibrate/[id] still works.
 */
type Pair = { pixel?: [number, number]; ground?: [number, number, number] };
type SeedPairs = Seed & { pairs: { pixel: [number, number]; ground: [number, number, number] }[]; groundZ: number };
type Calib = {
	cameraId: number;
	viewId: number | null;
	entered: boolean;
	mode: string;
	frame: { frame: string; url: string; width: number; height: number } | null;
	pairs: Pair[];
	selected: number | null;
	dirty: boolean;
	resumed: number | null;
	busy: string | null;
	solution: { pose: Seed['pose']; rms: number } | null;
	map: { entered: boolean; hidden: boolean; markers: { n: number }[]; cone: boolean; drape: boolean; scene: unknown; buildingsOpacity: unknown };
};

const seed = (kind: Seed['kind']) => seeds().seeds.find((s) => s.kind === kind)! as SeedPairs;
const mode = (page: Page) => page.evaluate(() => (globalThis as any).__tvt.mode as string);
const calib = (page: Page) => page.evaluate(() => (globalThis as any).__tvtCalib.state() as Calib);
const tileKey = (x: { url: string; range: string | null }) => `${x.url} ${x.range ?? ''}`;
const isTile = (x: { url: string }) => /\/tiles\/.+\.pmtiles/.test(x.url);
const sha = (b: Buffer) => createHash('sha256').update(b).digest('hex');

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

/** Open the calibrator fresh (a deep link) and wait until it's in Calibrate mode. */
async function openCalibrator(page: Page, s: Seed | { cameraId: number; viewId: number }) {
	await page.goto(`/calibrate/${s.cameraId}?view=${s.viewId}`);
	await inCalibrate(page);
}

async function inCalibrate(page: Page) {
	await page.waitForURL(/\/calibrate\//);
	await mapReady(page);
	await page.waitForFunction(() => (globalThis as any).__tvtCalib?.state().entered && (globalThis as any).__tvtCalib.state().frame);
	await mapReady(page);
	expect(await mode(page)).toBe('calibrate');
}

/** Everything entering and leaving must give back (§14.3's snapshot, plus the buildings' opacity). */
const everything = (page: Page) =>
	page.evaluate(() => {
		const t = (globalThis as any).__tvt;
		const m = t.map;
		const c = m.getCenter();
		const info = t.layers;
		return {
			lng: c.lng,
			lat: c.lat,
			zoom: m.getZoom(),
			bearing: m.getBearing(),
			pitch: m.getPitch(),
			roll: m.getRoll(),
			fov: m.getVerticalFieldOfView(),
			padding: m.getPadding(),
			maxZoom: m.getMaxZoom(),
			maxPitch: m.getMaxPitch(),
			clamp: m.getCenterClampedToGround(),
			exaggeration: m.getTerrain()?.exaggeration ?? null,
			enabled: [...info.enabled].sort(),
			shown: [...info.shown].sort(),
			flavor: info.flavor,
			aerial: m.getLayer('aerial') ? m.getLayoutProperty('aerial', 'visibility') !== 'none' : false,
			buildings: m.getLayer('buildings-3d') ? [m.getLayoutProperty('buildings-3d', 'visibility') ?? 'visible', m.getPaintProperty('buildings-3d', 'fill-extrusion-opacity') ?? null] : null,
			windows: (globalThis as any).__tvtCameras.windows().map((w: { key: string }) => w.key).sort(),
			rects: [...document.querySelectorAll('[data-window-key]')].map((el) => {
				const r = el.getBoundingClientRect();
				return `${(el as HTMLElement).dataset.windowKey}:${Math.round(r.x)},${Math.round(r.y)},${Math.round(r.width)}`;
			}).sort()
		};
	});

function expectSame(after: Awaited<ReturnType<typeof everything>>, before: Awaited<ReturnType<typeof everything>>, label: string) {
	expect(Math.abs(after.lng - before.lng), `${label}: centre`).toBeLessThan(1e-7);
	expect(Math.abs(after.lat - before.lat), `${label}: centre`).toBeLessThan(1e-7);
	expect(Math.abs(after.zoom - before.zoom), `${label}: zoom`).toBeLessThan(1e-6);
	for (const k of ['bearing', 'pitch', 'roll', 'fov'] as const) expect(after[k], `${label}: ${k}`).toBeCloseTo(before[k], 6);
	const { lng: _a, lat: _b, zoom: _c, bearing: _d, pitch: _e, roll: _f, fov: _g, ...rest } = after;
	const { lng: _h, lat: _i, zoom: _j, bearing: _k, pitch: _l, roll: _m, fov: _n, ...restBefore } = before;
	expect(rest, `${label}: limits, padding, terrain, layers, base and windows`).toEqual(restBefore);
}

/** Where an image pixel of the reference frame is on screen (zoom 1). */
async function framePoint(page: Page, px: [number, number]) {
	const c = await calib(page);
	const box = (await page.locator('[role="application"][data-frame]').boundingBox())!;
	return { x: box.x + (px[0] / c.frame!.width) * box.width, y: box.y + (px[1] / c.frame!.height) * box.height };
}

/** Screen points over the map, right of the panel and clear of the pair markers. */
const mapPoints = (page: Page, n: number) =>
	page.evaluate((n) => {
		const m = (globalThis as any).__tvt.map;
		const r = m.getContainer().getBoundingClientRect();
		const pad = m.getPadding();
		const marks = [...document.querySelectorAll('.calib-pair, .calib-pole')].map((el) => {
			const b = el.getBoundingClientRect();
			return [b.x + b.width / 2, b.y + b.height / 2];
		});
		const out: { x: number; y: number }[] = [];
		const left = r.left + pad.left + 40;
		for (let fy = 0.25; fy <= 0.75 && out.length < n; fy += 0.125) {
			for (let fx = 0.2; fx <= 0.8 && out.length < n; fx += 0.15) {
				const x = left + (r.right - 40 - left) * fx;
				const y = r.top + r.height * fy;
				if (marks.every(([mx, my]) => Math.hypot(mx - x, my - y) > 40) && out.every((p) => Math.hypot(p.x - x, p.y - y) > 80)) out.push({ x, y });
			}
		}
		return out;
	}, n);

test.describe('calibrate', () => {
	test('entering and leaving restore the view, layers, base and windows; the way back asks for no tile again', { tag: '@wp14' }, async ({ page, offsite, consoleErrors }) => {
		test.setTimeout(600_000);
		const key = seed('key');
		const net = await recordNetwork(page, { bodies: false });
		// Every layer on, tilted and turned, near the key camera; its window open.
		await page.goto(`/#map=16.4/${key.pose.lat.toFixed(5)}/${key.pose.lon.toFixed(5)}/-25/45&layers=streets,transit,cameras`);
		await mapReady(page);
		await page.waitForFunction(() => (globalThis as any).__tvtCameras);
		await page.evaluate((id) => (globalThis as any).__tvtCameras.open(id, false), key.cameraId);
		const win = page.locator(`[data-window-key="camera:${key.cameraId}"]`);
		await expect(win.getByRole('link', { name: 'Recalibrate' })).toBeVisible();
		await mapReady(page);
		const before = await everything(page);
		expect(before.shown).toEqual(['cameras', 'streets', 'transit']);
		expect(before.aerial).toBe(false);
		expect(before.windows).toEqual([`camera:${key.cameraId}`]);
		const loaded = new Set(net.entries.filter((x) => isTile(x) && !x.failed).map(tileKey));

		for (const how of ['Back', 'Esc'] as const) {
			// In through the window's Recalibrate link.
			await win.getByRole('link', { name: 'Recalibrate' }).click();
			await inCalibrate(page);
			const inside = await everything(page);
			// Pitch 0, bearing = the solved heading, zoom 19; terrain at true scale; Aerial on, buildings faint;
			// Transit, Streets and the other cameras hidden; windows stepped aside; the panel's width as padding.
			expect(inside.zoom).toBeCloseTo(19, 6);
			expect(inside.pitch).toBeCloseTo(0, 6);
			expect(((inside.bearing - key.pose.heading + 540) % 360) - 180).toBeCloseTo(0, 3);
			expect(inside.exaggeration).toBe(1);
			expect(inside.aerial).toBe(true);
			expect(inside.buildings?.[1]).toBe(0.25);
			expect(inside.shown).toEqual([]);
			expect(inside.enabled, 'the layer set itself is kept').toEqual(before.enabled);
			expect(inside.windows).toEqual([]);
			expect(inside.flavor, 'the flavor stays (no basemap re-layout)').toBe(before.flavor);
			const panel = (await page.getByRole('region', { name: `Calibrate ${key.name}` }).boundingBox())!;
			expect(inside.padding.left).toBe(Math.round(panel.x + panel.width));
			expect(panel.width / 1280).toBeGreaterThan(0.43);
			expect(panel.width / 1280).toBeLessThan(0.47);
			const c = await calib(page);
			expect(c.map).toMatchObject({ entered: true, cone: true });
			expect(c.map.markers.length).toBe(key.pairs.length);
			expect(await page.evaluate(() => (globalThis as any).__tvt.map.getCanvas().style.cursor)).toBe('crosshair');
			await expect(page.getByRole('group', { name: 'Calibrate mode' })).toBeVisible();
			if (how === 'Back') await page.screenshot({ path: screenPath('wp14-calibrate.png') });

			const mark = net.mark();
			if (how === 'Back') await page.goBack();
			else await page.keyboard.press('Escape');
			await page.waitForURL((u) => !u.pathname.startsWith('/calibrate'));
			await mapReady(page);
			await expect(win).toBeVisible();
			await mapReady(page);
			const ret = net.since(mark);
			expect(ret.filter((x) => isTile(x) && loaded.has(tileKey(x))).map(tileKey), `${how}: tiles asked for again`).toEqual([]);
			expect(ret.filter((x) => x.kind === 'manifest').length, `${how}: manifest requests`).toBe(0);
			expect(await mode(page)).toBe('explore');
			expectSame(await everything(page), before, how);
		}
		expect(await page.evaluate(() => (globalThis as any).__tvt.mapsCreated)).toBe(1);
		await net.detach();
		expect(offsite).toEqual([]);
		expect(consoleErrors.filter((e) => !/could not be decoded|^map error Error$/.test(e))).toEqual([]);
	});

	test('"Use this frame" keeps exactly the bytes on screen, from the archive and from the on-demand fetcher', { tag: '@wp14' }, async ({ page, request, offsite }) => {
		test.setTimeout(400_000);
		const key = seed('key');
		// An uncalibrated camera that isn't recorded: its live picture comes from the (fixture) on-demand fetcher.
		const views: { id: number; cameraId: number; imageId: number | null }[] = (await (await request.get('/api/cameras/views')).json()).views;
		const cams = new Map<number, { status: string }>(
			(await (await request.get('/api/cameras')).json()).features.map((f: { properties: { id: number; status: string } }) => [f.properties.id, f.properties])
		);
		const recorded = new Set(seeds().archive.imageIds);
		const onDemand = views.find((v) => v.imageId !== null && !recorded.has(v.imageId) && cams.get(v.cameraId)?.status === 'uncalibrated')!;
		expect(onDemand, 'an on-demand camera').toBeTruthy();

		for (const [label, target, kind] of [
			['archive', key, 'archive'],
			['on demand', onDemand, 'sha']
		] as const) {
			const cameraId = 'cameraId' in target ? target.cameraId : 0;
			const viewId = 'viewId' in target ? target.viewId : target.id;
			await openCalibrator(page, { cameraId, viewId });
			const inset = page.getByRole('region', { name: 'Live picture' }).getByRole('img');
			await expect(inset).toBeVisible();
			const src = (await inset.getAttribute('src'))!;
			expect(src, `${label}: the inset's picture`).toMatch(kind === 'archive' ? /^\/camera-frames\// : /^\/api\/views\/\d+\/live\/[0-9a-f]{64}$/);
			const shown = sha(await (await request.get(src)).body());
			const posting = page.waitForRequest((r) => r.url().endsWith(`/api/views/${viewId}/frame`) && r.method() === 'POST');
			const kept = page.waitForResponse((r) => r.url().endsWith(`/api/views/${viewId}/frame`) && r.request().method() === 'POST');
			await page.getByRole('button', { name: 'Use this frame' }).click();
			const body = JSON.parse((await posting).postData() ?? 'null');
			if (kind === 'archive') expect(Object.keys(body).sort(), `${label}: posts the frame's identity`).toEqual(['day', 'image', 'stamp']);
			else expect(Object.keys(body), `${label}: posts the frame's identity`).toEqual(['sha']);
			const res = await kept;
			expect(res.status()).toBe(200);
			const saved = await res.json();
			// The reference frame on screen is now the kept one, and its bytes are the inset's.
			await expect(page.locator(`img[src="${saved.url}"]`)).toBeVisible();
			expect((await calib(page)).frame?.frame).toBe(saved.frame);
			expect(sha(await (await request.get(saved.url)).body()), `${label}: byte-identical`).toBe(shown);
			await expect(page.getByRole('status').filter({ hasText: 'as the reference' })).toBeVisible();
			if (kind === 'archive') await page.screenshot({ path: screenPath('wp14-use-this-frame.png') });
		}
		// Bytes no longer held: 410, and the panel asks to pick the current frame again.
		await page.route('**/api/views/*/frame', (r) => r.fulfill({ status: 410, json: { message: "That picture is no longer in the server's memory" } }));
		await page.getByRole('button', { name: 'Use this frame' }).click();
		await expect(page.getByRole('alert').filter({ hasText: 'Pick the current frame again' })).toBeVisible();
		await page.unroute('**/api/views/*/frame');
		expect(offsite).toEqual([]);
	});

	test('a reload mid-calibration resumes the draft; Ctrl+Z, Delete and Cancel', { tag: '@wp14' }, async ({ page, offsite }) => {
		test.setTimeout(400_000);
		const key = seed('key');
		await openCalibrator(page, key);
		let c = await calib(page);
		expect(c.pairs.length).toBe(key.pairs.length);
		expect(c.dirty).toBe(false);
		expect(c.resumed).toBeNull();

		// A new pair: the picture first, then the map.
		const p = await framePoint(page, [0.5 * c.frame!.width, 0.18 * c.frame!.height]);
		await page.mouse.click(p.x, p.y);
		await expect.poll(async () => (await calib(page)).pairs.length).toBe(key.pairs.length + 1);
		await expect(page.getByRole('region', { name: 'Reference frame', exact: true }).getByText('Now click the same spot on the map')).toBeVisible();
		const [m] = await mapPoints(page, 1);
		await page.mouse.click(m.x, m.y);
		await expect.poll(async () => (await calib(page)).pairs.at(-1)?.ground).toBeTruthy();
		c = await calib(page);
		expect(c.dirty).toBe(true);
		const added = c.pairs.at(-1)!;
		expect(c.map.markers.length).toBe(key.pairs.length + 1);

		// Delete removes the selected pair; Ctrl+Z brings it back.
		await page.getByRole('button', { name: 'Select pair 1', exact: true }).click();
		await page.keyboard.press('Delete');
		await expect.poll(async () => (await calib(page)).pairs.length).toBe(key.pairs.length);
		expect((await calib(page)).pairs[0]).toEqual(key.pairs[1]);
		await page.keyboard.press('Control+z');
		await expect.poll(async () => (await calib(page)).pairs.length).toBe(key.pairs.length + 1);
		expect((await calib(page)).pairs[0]).toEqual(key.pairs[0]);

		// The draft is in storage, per view.
		const stored = await page.evaluate((v) => JSON.parse(localStorage.getItem(`tvt:v2:calib-draft:${v}`) ?? 'null'), key.viewId);
		expect(stored?.pairs?.length).toBe(key.pairs.length + 1);

		// A reload resumes it.
		await page.reload();
		await inCalibrate(page);
		c = await calib(page);
		expect(c.pairs.length).toBe(key.pairs.length + 1);
		expect(c.pairs.at(-1)).toEqual(added);
		expect(c.resumed).not.toBeNull();
		await expect(page.getByText('Your unsaved draft from')).toBeVisible();
		await page.screenshot({ path: screenPath('wp14-draft-resumed.png') });

		// Cancel asks first; Discard drops the draft.
		await page.getByRole('button', { name: 'Cancel: leave calibration' }).click();
		const ask = page.getByRole('alertdialog', { name: 'Unsaved changes' });
		await expect(ask).toBeVisible();
		await ask.getByRole('button', { name: 'Discard the changes' }).click();
		await page.waitForURL((u) => !u.pathname.startsWith('/calibrate'));
		await mapReady(page);
		expect(await page.evaluate((v) => localStorage.getItem(`tvt:v2:calib-draft:${v}`), key.viewId)).toBeNull();
		await follow(page, `/calibrate/${key.cameraId}?view=${key.viewId}`);
		await inCalibrate(page);
		c = await calib(page);
		expect(c.pairs.length).toBe(key.pairs.length);
		expect(c.resumed).toBeNull();
		expect(offsite).toEqual([]);
	});

	test('ground heights picked at exaggeration 1.0 and 1.3 agree within 0.25 m', { tag: '@wp14' }, async ({ page }) => {
		test.setTimeout(400_000);
		const key = seed('key');
		await openCalibrator(page, key);
		expect(await page.evaluate(() => (globalThis as any).__tvt.map.getTerrain()?.exaggeration)).toBe(1);
		const points = await mapPoints(page, 3);
		expect(points.length).toBe(3);
		/** Click the map; the pending pair's ground point (each click moves it). */
		const pick = async (x: number, y: number) => {
			const n = (await calib(page)).pairs.length;
			const before = JSON.stringify((await calib(page)).pairs.at(-1)?.ground ?? null);
			await page.mouse.click(x, y);
			await expect.poll(async () => JSON.stringify((await calib(page)).pairs.at(-1)?.ground ?? null)).not.toBe(before);
			const c = await calib(page);
			expect(c.pairs.length).toBeLessThanOrEqual(n + 1);
			return c.pairs.at(-1)!.ground!;
		};
		const at1: [number, number, number][] = [];
		for (const p of points) at1.push(await pick(p.x, p.y));

		await page.evaluate(() => {
			const m = (globalThis as any).__tvt.map;
			m.setTerrain({ ...m.getTerrain(), exaggeration: 1.3 });
		});
		await mapReady(page);
		expect(await page.evaluate(() => (globalThis as any).__tvt.map.getTerrain()?.exaggeration)).toBe(1.3);
		const lines: string[] = [];
		for (const g of at1) {
			const q = await page.evaluate((g) => {
				const m = (globalThis as any).__tvt.map;
				const r = m.getContainer().getBoundingClientRect();
				const p = m.project([g[0], g[1]]);
				return { x: r.left + p.x, y: r.top + p.y, drawn: m.queryTerrainElevation([g[0], g[1]]) };
			}, g);
			const g13 = await pick(q.x, q.y);
			lines.push(`1.0: ${g[2].toFixed(3)} m · 1.3: ${g13[2].toFixed(3)} m · drawn ${q.drawn.toFixed(1)} m`);
			expect(Math.hypot((g13[0] - g[0]) * 80_000, (g13[1] - g[1]) * 111_000), 'the same place').toBeLessThan(0.5);
			expect(Math.abs(g13[2] - g[2]), 'heights agree').toBeLessThanOrEqual(0.25);
			// What dividing by the manifest's exaggeration (or not at all) would have given instead.
			expect(Math.abs(q.drawn - g[2])).toBeGreaterThan(100);
		}
		test.info().annotations.push({ type: 'heights', description: lines.join('; ') });
	});

	test('Check alignment looks through the unsaved pose; Step out comes back to Calibrate', { tag: '@wp14' }, async ({ page, offsite }) => {
		test.setTimeout(400_000);
		const key = seed('key');
		await openCalibrator(page, key);
		await page.waitForFunction(() => (globalThis as any).__tvtLook);
		// Move pair 1's image point: an unsaved pose that differs from the saved one.
		const c0 = await calib(page);
		const from = await framePoint(page, c0.pairs[0].pixel!);
		await page.mouse.move(from.x, from.y);
		await page.mouse.down();
		await page.mouse.move(from.x + 12, from.y + 4, { steps: 3 });
		await page.mouse.move(from.x + 30, from.y + 10, { steps: 3 });
		await page.mouse.up();
		await expect.poll(async () => (await calib(page)).pairs[0].pixel![0]).toBeGreaterThan(c0.pairs[0].pixel![0] + 20);
		const c = await calib(page);
		const draft = c.solution!.pose;
		expect(c.solution!.rms).toBeGreaterThan(0.5);
		const diff = Math.abs(draft.heading - key.pose.heading) + Math.abs(draft.tilt - key.pose.tilt) + Math.abs(draft.vfov - key.pose.vfov);
		expect(diff, 'the draft pose differs from the saved one').toBeGreaterThan(0.05);
		const inside = await everything(page);

		await page.getByRole('button', { name: 'Check alignment' }).click();
		await expect.poll(() => page.evaluate(() => (globalThis as any).__tvtLook.state().phase), { timeout: 60_000 }).toBe('looking');
		await mapReady(page);
		expect(await mode(page)).toBe('look');
		const looked = await page.evaluate(() => (globalThis as any).__tvtLook.inspect());
		for (const k of ['lon', 'lat', 'alt', 'heading', 'tilt', 'roll', 'vfov'] as const) expect(looked.pose[k], k).toBeCloseTo(draft[k], 9);
		expect(looked.errorM).toBeLessThan(0.1);
		await expect(page.getByRole('region', { name: `Calibrate ${key.name}` })).toBeHidden();
		expect((await calib(page)).map.hidden).toBe(true);
		await page.screenshot({ path: screenPath('wp14-check-alignment.png') });

		await page.keyboard.press('Escape');
		await expect.poll(() => mode(page), { timeout: 120_000 }).toBe('calibrate');
		await mapReady(page);
		await expect(page.getByRole('region', { name: `Calibrate ${key.name}` })).toBeVisible();
		expect((await calib(page)).map.hidden).toBe(false);
		// Still the unsaved draft, and the same view.
		expect((await calib(page)).solution!.pose).toEqual(draft);
		expectSame(await everything(page), inside, 'after Step out');
		expect(offsite).toEqual([]);
	});

	test('a save works against the seeded database, reopens the window and offers "Look through to check"', { tag: '@wp14' }, async ({ page, offsite }) => {
		test.setTimeout(500_000);
		const s = seed('roll');
		const sql = postgres(process.env.DATABASE_URL!, { max: 1, onnotice: () => {} });
		const current = async () =>
			(await sql`select id from core.camera_calibration where view_id = ${s.viewId} and upper_inf(valid)`).map((r) => Number(r.id));
		const [seeded] = await current();
		expect(seeded, 'the seeded view has a current calibration').toBeTruthy();
		let saved: number | null = null;
		try {
			await page.goto(`/#map=16.5/${s.pose.lat.toFixed(5)}/${s.pose.lon.toFixed(5)}/10/40&layers=cameras`);
			await mapReady(page);
			await page.waitForFunction(() => (globalThis as any).__tvtCameras);
			await page.evaluate((id) => (globalThis as any).__tvtCameras.open(id, false), s.cameraId);
			const win = page.locator(`[data-window-key="camera:${s.cameraId}"]`);
			await win.getByRole('link', { name: 'Recalibrate' }).click();
			await inCalibrate(page);
			// A change: drop the last pair.
			await page.getByRole('button', { name: `Remove pair ${s.pairs.length}` }).click();
			await expect.poll(async () => (await calib(page)).pairs.length).toBe(s.pairs.length - 1);
			const pose = (await calib(page)).solution!.pose;

			// Ctrl+S saves.
			const saving = page.waitForResponse((r) => r.url().endsWith(`/api/views/${s.viewId}/calibrations`) && r.request().method() === 'POST');
			await page.keyboard.press('Control+s');
			const res = await saving;
			expect(res.status()).toBe(200);
			const body = await res.json();
			saved = body.id;
			expect(body).toMatchObject({ viewId: s.viewId, cameraId: s.cameraId });
			// Back on the map: the snapshot restored, the window open again, and the offer.
			await page.waitForURL((u) => !u.pathname.startsWith('/calibrate'));
			await mapReady(page);
			expect(await mode(page)).toBe('explore');
			await expect(win).toBeVisible();
			const toast = page.getByRole('status').filter({ hasText: 'Saved' });
			await expect(toast).toBeVisible();
			expect(await current(), 'the new row is the only current one').toEqual([saved]);
			const [old] = await sql`select upper_inf(valid) as open from core.camera_calibration where id = ${seeded}`;
			expect(old.open, 'previous row closed').toBe(false);
			const [row] = await sql`select jsonb_array_length(point_pairs) as n, rms_error_px from core.camera_calibration where id = ${saved}`;
			expect(Number(row.n)).toBe(s.pairs.length - 1);
			expect(Number(row.rms_error_px)).toBeCloseTo(body.rms, 4);
			expect(await page.evaluate((v) => localStorage.getItem(`tvt:v2:calib-draft:${v}`), s.viewId), 'no draft left').toBeNull();
			await page.screenshot({ path: screenPath('wp14-saved.png') });

			// "Look through to check" looks through the calibration just saved.
			await toast.getByRole('button', { name: 'Look through to check' }).click();
			await expect.poll(() => page.evaluate(() => (globalThis as any).__tvtLook.state().phase), { timeout: 60_000 }).toBe('looking');
			const looked = await page.evaluate(() => (globalThis as any).__tvtLook.inspect());
			// (The table keeps angles as real: about 6 significant digits.)
			for (const k of ['heading', 'tilt', 'roll', 'vfov'] as const) expect(looked.pose[k], k).toBeCloseTo(pose[k], 3);
			// Step out (resolves once back; SwiftShader can take a while over the 3D cameras).
			await page.evaluate(() => (globalThis as any).__tvtLook.stepOut());
			await expect.poll(() => mode(page), { timeout: 120_000 }).toBe('explore');
		} finally {
			// Put the seeded calibration back as it was, so other specs (and the next run) see the seeds.
			if (saved) await sql`delete from core.camera_calibration where id = ${saved}`;
			await sql`update core.camera_calibration set valid = tstzrange(lower(valid), null) where id = ${seeded}`;
			await sql.end();
		}
		expect(offsite).toEqual([]);
	});

	test('phones get "Calibration needs a larger screen"', { tag: '@wp14' }, async ({ page }) => {
		const key = seed('key');
		await page.setViewportSize({ width: 390, height: 844 });
		await page.goto(`/calibrate/${key.cameraId}?view=${key.viewId}`);
		await mapReady(page);
		const note = page.getByRole('alert').filter({ hasText: 'Calibration needs a larger screen' });
		await expect(note).toBeVisible();
		expect(await mode(page)).toBe('explore');
		await expect(page.getByRole('region', { name: `Calibrate ${key.name}` })).toHaveCount(0);
		expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
		await page.screenshot({ path: screenPath('wp14-phone.png') });
		await note.getByRole('button', { name: 'Back to the map' }).click();
		await page.waitForURL((u) => u.pathname === '/');
		await mapReady(page);
		expect(await mode(page)).toBe('explore');
	});

	test('/v1/calibrate/[id] still works', { tag: '@wp14' }, async ({ page, offsite }) => {
		const key = seed('key');
		await page.goto(`/v1/calibrate/${key.cameraId}`);
		await expect(page.getByText(/px, great/)).toBeVisible({ timeout: 120_000 });
		await expect(page.getByRole('button', { name: 'Save calibration' })).toBeEnabled();
		await expect(page.locator(`img[src="/frames/${key.frame}"]`)).toBeVisible();
		expect(offsite).toEqual([]);
	});
});
