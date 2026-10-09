import type { Page } from '@playwright/test';
import { createHash } from 'node:crypto';
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { fetchedAtOf, INDEX, INDEX_HEADER, jpegDir, localDay, stampOf, withComment } from '../../scripts/archive-tick.ts';
import { recordNetwork } from '../../scripts/net.mjs';
import { project, type Pose } from '../../src/lib/calibration/solver.ts';
import { env, expect, mapReady, screenPath, seeds, test, type Seed } from './fixtures.js';

/**
 * cameras, WP13 (docs/14 §14.10 "WP13", §14.11): 3D cameras, the photo in the
 * cone and look-through, on the seeded calibrations (map-rendered frames,
 * never a real camera image), in fixture mode.
 *
 * - 3D cameras from z15: pole, head, cone and edges for a calibrated camera,
 *   a pin for one that isn't; the open window's picture hangs in the cone,
 *   and "3D photo" turns it off and on;
 * - registration: on the 4 seeds, at roll 0 and ±5, the mean distance
 *   between `map.project(pair.ground)` and the pair's pixel mapped into the
 *   letterbox is ≤ 1.5 px; the eye reads back within 0.1 m; the low-tilt
 *   camera is at a pitch above 75;
 * - the low-tilt seed's picture isn't clipped: the frame's centre pixel
 *   differs from the map-only render, and the plane is at least twice the
 *   near distance from the eye;
 * - Step out (Esc) restores the view exactly, and its return leg fetches no
 *   tile the map had before and no manifest;
 * - ending in place (fading out by moving) never jumps: pitch, zoom, field of
 *   view and exaggeration are eased, the eye stays above the ground, and
 *   leaving the mode moves nothing;
 * - the Esc order (help, then look-through, before the card and selection);
 *   Enter on a focused window and a double-click go straight in, the latter
 *   from the view before the clicks' fly;
 * - a phone gets the full-screen picture and a bottom strip;
 * - entered from a z13 overview over ground higher than the camera's eye
 *   (through the API, and by a double-click on the camera there), the map's
 *   centre is on the terrain under the view axis and the near plane is under
 *   2 m, on arrival and after the terrain has loaded (the fix round, Oct 8:
 *   it was 10 km out, kilometres underground, with a near plane of 140–200 m);
 * - a frame of another size while looking through says so and never blanks
 *   the picture: the reference frame (labelled) when entered straight in, or
 *   the live picture of the calibrated size it had, with the strip's age the
 *   age of the picture on screen.
 */
type Pair = { pixel: [number, number]; ground: [number, number, number] };
type SeedPairs = Seed & { pairs: Pair[]; groundZ: number };
type Box = { x: number; y: number; width: number; height: number };

const seedsWithPairs = () => seeds().seeds as SeedPairs[];
const at = (s: Seed, zoom = 16, pitch = 45, bearing = 0) =>
	`#map=${zoom}/${s.pose.lat.toFixed(5)}/${s.pose.lon.toFixed(5)}/${bearing}/${pitch}&layers=cameras`;

async function openMap(page: Page, hash: string) {
	await page.goto(`/${hash}`);
	await mapReady(page);
	await page.waitForFunction(() => (globalThis as any).__tvtLook && (globalThis as any).__tvtCameras, null, { timeout: 60_000 });
}

const lookState = (page: Page) => page.evaluate(() => (globalThis as any).__tvtLook.state());
const inspect = (page: Page) => page.evaluate(() => (globalThis as any).__tvtLook.inspect());
const mode = (page: Page) => page.evaluate(() => (globalThis as any).__tvt.mode as string);

/** Everything a mode's snapshot restores (§14.3), read from the map. */
const camera = (page: Page) =>
	page.evaluate(() => {
		const m = (globalThis as any).__tvt.map;
		const c = m.getCenter();
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
			exaggeration: m.getTerrain()?.exaggeration ?? null
		};
	});

/** Look through a seed (optionally at another pose); resolves once looking and settled. */
async function enter(page: Page, s: Seed, pose?: Pose) {
	const ok = await page.evaluate(([id, v, p]) => (globalThis as any).__tvtLook.enter(id, v, p), [s.cameraId, s.viewId, pose ?? null] as const);
	expect(ok, `look through ${s.kind}`).toBe(true);
	await mapReady(page);
	expect((await lookState(page)).phase).toBe('looking');
}

async function stepOut(page: Page) {
	await page.evaluate(() => (globalThis as any).__tvtLook.stepOut());
	await mapReady(page);
	expect(await mode(page)).toBe('explore');
}

/** Mean and largest screen distance between each pair's ground point (map.project) and its pixel in the letterbox. */
async function registration(page: Page, s: SeedPairs, pose: Pose) {
	const pairs = s.pairs.map((p) => ({ ground: p.ground, pixel: project(pose, s.size, p.ground)! }));
	const d: number[] = await page.evaluate(
		({ pairs, size }) => {
			const map = (globalThis as any).__tvt.map;
			const box = (globalThis as any).__tvtLook.state().box;
			return pairs.map((p: { ground: number[]; pixel: number[] }) => {
				const q = map.project([p.ground[0], p.ground[1]]);
				return Math.hypot(q.x - (box.x + (p.pixel[0] * box.width) / size.width), q.y - (box.y + (p.pixel[1] * box.height) / size.height));
			});
		},
		{ pairs, size: s.size }
	);
	return { mean: d.reduce((a, b) => a + b, 0) / d.length, max: Math.max(...d), n: d.length };
}

/** One canvas pixel, read inside the map's render (so the scene's photo plane is in it). */
const pixel = (page: Page, x: number, y: number) =>
	page.evaluate(
		([x, y]) =>
			new Promise<number[]>((resolve) => {
				const map = (globalThis as any).__tvt.map;
				map.once('render', () => {
					const gl = map.getCanvas().getContext('webgl2') as WebGL2RenderingContext;
					const k = gl.drawingBufferWidth / map.getCanvas().clientWidth;
					const out = new Uint8Array(4 * 9);
					gl.readPixels(Math.round(x * k) - 1, Math.round(gl.drawingBufferHeight - y * k) - 1, 3, 3, gl.RGBA, gl.UNSIGNED_BYTE, out);
					const mean = [0, 1, 2].map((c) => out.filter((_, i) => i % 4 === c).reduce((a, b) => a + b, 0) / 9);
					resolve(mean);
				});
				map.triggerRepaint();
			}),
		[x, y]
	);

/** A camera's screen point (viewport px). */
const pointOf = (page: Page, lngLat: [number, number]) =>
	page.evaluate((ll) => {
		const map = (globalThis as any).__tvt.map;
		const r = map.getContainer().getBoundingClientRect();
		const p = map.project(ll);
		return { x: r.left + p.x, y: r.top + p.y };
	}, lngLat);

const tileKey = (x: { url: string; range: string | null }) => `${x.url} ${x.range ?? ''}`;
const isTile = (x: { url: string }) => /\/tiles\/.+\.pmtiles/.test(x.url);
const note = (line: string) => {
	mkdirSync(env().screens, { recursive: true });
	appendFileSync(screenPath('wp13-numbers.txt'), `${new Date().toISOString()} ${line}\n`);
};

/** A frame appended to a recorded camera's fake archive (the capture service's way), as the newest; its stamp and sha. */
function appendFrame(image: number, bytes: Buffer, when: Date) {
	let t = new Date(Math.floor(when.getTime() / 1000) * 1000);
	const dir = jpegDir(env().archive, image, localDay(t));
	mkdirSync(dir, { recursive: true });
	while (existsSync(join(dir, `${stampOf(t)}.jpg`))) t = new Date(t.getTime() + 1000);
	const stamp = stampOf(t);
	const body = withComment(bytes, `tvt lookthrough spec ${fetchedAtOf(t)} (synthetic test frame)`);
	writeFileSync(join(dir, `${stamp}.jpg`), body);
	const index = join(dir, INDEX);
	if (!existsSync(index)) writeFileSync(index, `${INDEX_HEADER}\n`);
	const sha = createHash('sha256').update(body).digest('hex');
	appendFileSync(index, `${fetchedAtOf(t)},${stamp}.jpg,${body.length},${sha}\n`);
	return { stamp, sha };
}

/**
 * z13 overviews over ground higher than the camera's eye (true heights from
 * the map's terrain, Oct 8): the foothills north-east of downtown for Capitol
 * & Myrtle (about 905 m against an eye at 829 m), the bench south-east of
 * Franklin & Milwaukee (about 845 m against 835 m). The camera stays on screen.
 */
const OVERVIEWS: [Seed['kind'], [number, number]][] = [
	['roll', [-116.1742, 43.62266]],
	['low-tilt', [-116.25672, 43.59345]]
];

/** Let CSS animations finish (SwiftShader starves them while the map draws), for screenshots. */
async function settle(page: Page) {
	await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running'), null, { timeout: 15_000 }).catch(() => {});
}

test.describe('cameras: 3D and look-through', () => {
	test('3D cameras from z15, and the open window’s picture in its cone', { tag: '@wp13' }, async ({ page, offsite }) => {
		test.setTimeout(400_000);
		const key = seedsWithPairs().find((x) => x.kind === 'key')!;
		// Tilted, looking back at the camera from behind it, so the picture's front faces us.
		await openMap(page, at(key, 17.2, 62, key.pose.heading));
		expect(await page.evaluate(() => (globalThis as any).__tvtLook.load3d())).toBe(true);
		await expect.poll(() => page.evaluate(() => (globalThis as any).__tvtLook.models()?.shown), { timeout: 60_000 }).toBe(true);
		const models = await page.evaluate(() => (globalThis as any).__tvtLook.models());
		const meshes = models.instances.map((i: { mesh: string }) => i.mesh);
		expect(meshes).toContain('pole');
		expect(meshes).toContain('head');
		expect(models.cones).toBeGreaterThan(0);
		expect(models.lines).toBe(4 * models.cones);
		// Not on 511 or not calibrated: no head; the calibrated key camera's head is there.
		expect(models.instances.some((i: { id: string }) => i.id.startsWith('head-'))).toBe(true);

		// Open its window (no fly): its picture hangs in the cone.
		expect(await page.evaluate((id) => (globalThis as any).__tvtCameras.open(id, false), key.cameraId)).toBe(true);
		await expect
			.poll(async () => (await page.evaluate(() => (globalThis as any).__tvtLook.photos())).photos.map((p: { viewId: number; texture: string | null }) => `${p.viewId}:${Boolean(p.texture)}`), { timeout: 60_000 })
			.toEqual([`${key.viewId}:true`]);
		const win = page.getByRole('dialog', { name: new RegExp(key.name) });
		await expect(win).toBeVisible();
		await mapReady(page);
		await settle(page);
		await page.screenshot({ path: screenPath('wp13-3d-camera-photo.png') });

		// "3D photo" turns it off and on.
		const toggle = win.getByRole('button', { name: '3D photo' });
		await expect(toggle).toHaveAttribute('aria-pressed', 'true');
		await toggle.click();
		await expect(toggle).toHaveAttribute('aria-pressed', 'false');
		await expect.poll(async () => (await page.evaluate(() => (globalThis as any).__tvtLook.photos())).photos.length).toBe(0);
		await toggle.click();
		await expect.poll(async () => (await page.evaluate(() => (globalThis as any).__tvtLook.photos())).photos.length).toBe(1);

		// Below z15 the models and photos go (the icons stay).
		await page.evaluate(() => (globalThis as any).__tvt.map.jumpTo({ zoom: 13.5 }));
		await expect.poll(() => page.evaluate(() => (globalThis as any).__tvtLook.models().shown)).toBe(false);
		await expect.poll(() => page.evaluate(() => (globalThis as any).__tvtLook.photos().visible)).toBe(false);
		expect(offsite).toEqual([]);
	});

	test('registration on the 4 seeds at roll 0 and ±5: ≤ 1.5 px, the eye within 0.1 m; the low-tilt picture isn’t clipped', { tag: '@wp13' }, async ({ page, offsite }) => {
		test.setTimeout(900_000);
		// Jumps instead of flights: this test is about where the camera lands.
		await page.emulateMedia({ reducedMotion: 'reduce' });
		const all = seedsWithPairs();
		for (const s of all) {
			expect(s.visual, `${s.kind} has a map-rendered frame`).toBe(true);
			await openMap(page, at(s, 16.5, 50));
			for (const roll of [0, 5, -5]) {
				const pose: Pose = { ...s.pose, roll };
				await enter(page, s, pose);
				const reg = await registration(page, s, pose);
				const ins = await inspect(page);
				const line = `registration ${s.kind} roll ${roll}: mean ${reg.mean.toFixed(3)} px, max ${reg.max.toFixed(3)} px over ${reg.n} pairs; eye ${ins.errorM.toExponential(2)} m (MapLibre's own ${ins.internalErrorM?.toExponential(2) ?? 'n/a'} m); pitch ${(await camera(page)).pitch.toFixed(2)}`;
				note(line);
				test.info().annotations.push({ type: 'registration', description: line });
				expect(reg.mean, line).toBeLessThanOrEqual(1.5);
				expect(ins.errorM, 'the eye reads back within 0.1 m').toBeLessThanOrEqual(0.1);
				if (ins.internalErrorM !== null) expect(ins.internalErrorM).toBeLessThanOrEqual(0.1);
				if (s.kind === 'low-tilt') expect((await camera(page)).pitch, 'the low-tilt camera looks at a pitch above 75').toBeGreaterThan(75);
				if (roll === 0 && (s.kind === 'key' || s.kind === 'low-tilt')) await page.screenshot({ path: screenPath(`wp13-look-${s.kind}.png`) });

				if (s.kind === 'low-tilt' && roll === 0) {
					// Visibility: the plane is in front of the near plane, and it's drawn.
					expect(ins.plane.depthTest).toBe(false);
					expect(ins.plane.layer, 'the picture is uploaded').toBeGreaterThanOrEqual(0);
					expect(ins.plane.d, `plane at ${ins.plane.d} m, near ${ins.near} m`).toBeGreaterThanOrEqual(2 * ins.near);
					const b: Box = (await lookState(page)).box;
					const cx = b.x + b.width / 2;
					const cy = b.y + (b.height * 0.5 * 432) / 466;
					const withPhoto = await pixel(page, cx, cy);
					await page.evaluate(() => (globalThis as any).__tvtLook.setSlider(0));
					const mapOnly = await pixel(page, cx, cy);
					await page.evaluate(() => (globalThis as any).__tvtLook.setSlider(1));
					const diff = Math.max(...withPhoto.map((v, i) => Math.abs(v - mapOnly[i])));
					note(`low-tilt centre pixel: with the picture ${withPhoto.map((v) => v.toFixed(0))}, map only ${mapOnly.map((v) => v.toFixed(0))} (largest channel difference ${diff.toFixed(1)}); plane ${ins.plane.d.toFixed(2)} m, near ${ins.near.toFixed(2)} m`);
					expect(diff, 'the frame centre differs from the map-only render').toBeGreaterThan(8);
				}
				await stepOut(page);
			}
		}
		expect(offsite).toEqual([]);
	});

	test('the window’s Look through, then Esc: the view restored exactly, and no tile fetched again', { tag: '@wp13' }, async ({ page, offsite, consoleErrors }) => {
		test.setTimeout(600_000);
		const key = seedsWithPairs().find((x) => x.kind === 'key')!;
		const net = await recordNetwork(page, { bodies: false });
		await openMap(page, at(key));
		const pole = await page.evaluate((id) => (globalThis as any).__tvtCameras.cameras().find((c: any) => c.id === id), key.cameraId);
		// A click flies to the camera and opens its window (WP12).
		const p = await pointOf(page, [pole.lng, pole.lat]);
		await page.mouse.click(p.x, p.y);
		const win = page.getByRole('dialog', { name: new RegExp(key.name) });
		await expect(win).toBeVisible();
		await mapReady(page);
		const look = win.getByRole('button', { name: 'Look through' });
		await expect(look).toBeEnabled({ timeout: 60_000 });
		await mapReady(page);
		const loaded = new Set(net.entries.filter((x) => isTile(x) && !x.failed).map(tileKey));
		const before = await camera(page);
		const layersBefore = await page.evaluate(() => (globalThis as any).__tvt.map.getLayersOrder());

		await look.click();
		await expect.poll(async () => (await lookState(page)).phase, { timeout: 120_000 }).toBe('looking');
		await mapReady(page);
		expect(await mode(page)).toBe('look');
		const inside = await camera(page);
		expect(inside).toMatchObject({ maxPitch: 89, maxZoom: 24, clamp: false, exaggeration: 1 });
		await expect(page.getByRole('group', { name: 'Look-through' })).toBeVisible();
		await expect(page.locator('[data-look-frame]')).toBeVisible();
		await settle(page);
		await page.screenshot({ path: screenPath('wp13-look-window-button.png') });

		const mark = net.mark();
		await page.keyboard.press('Escape');
		await expect.poll(() => mode(page), { timeout: 120_000 }).toBe('explore');
		await mapReady(page);
		const ret = net.since(mark);
		const again = ret.filter((x) => isTile(x) && loaded.has(tileKey(x))).map(tileKey);
		note(`round trip (window → look through → Esc): return leg ${ret.length} requests, ${ret.filter(isTile).length} tile requests, ${again.length} of tiles loaded before entering, ${ret.filter((x) => x.kind === 'manifest').length} manifest`);
		expect(again, 'tiles fetched again on the return leg').toEqual([]);
		expect(ret.filter((x) => x.kind === 'manifest').length).toBe(0);
		const after = await camera(page);
		for (const k of ['lng', 'lat', 'zoom', 'bearing', 'pitch', 'roll', 'fov'] as const) expect(Math.abs(after[k] - before[k]), k).toBeLessThan(1e-9);
		expect(after.padding).toEqual(before.padding);
		expect({ maxZoom: after.maxZoom, maxPitch: after.maxPitch, clamp: after.clamp, exaggeration: after.exaggeration }).toEqual({
			maxZoom: before.maxZoom,
			maxPitch: before.maxPitch,
			clamp: before.clamp,
			exaggeration: before.exaggeration
		});
		// The window comes back, and the style is as it was.
		await expect(win).toBeVisible();
		expect(await page.evaluate(() => (globalThis as any).__tvt.map.getLayersOrder())).toEqual(layersBefore);
		expect(await page.evaluate(() => (globalThis as any).__tvt.mapsCreated)).toBe(1);
		await net.detach();
		expect(offsite).toEqual([]);
		expect(consoleErrors.filter((e) => e !== 'map error Error')).toEqual([]);
	});

	test('ending in place never jumps: eased, above the ground, and nothing moves on leaving', { tag: '@wp13' }, async ({ page, offsite }) => {
		test.setTimeout(600_000);
		const low = seedsWithPairs().find((x) => x.kind === 'low-tilt')!;
		await openMap(page, at(low, 16.5, 50));
		await enter(page, low);
		await page.evaluate(() => (globalThis as any).__tvtLook.trace(true));
		// The user drags the map: the picture fades, and 300 ms at 0 ends look-through where they are.
		await page.mouse.move(640, 420);
		await page.mouse.down();
		for (let i = 1; i <= 12; i++) await page.mouse.move(640 + i * 24, 420 + i * 4);
		await page.mouse.up();
		await expect.poll(() => mode(page), { timeout: 180_000 }).toBe('explore');
		await mapReady(page);
		const trace: { phase: string; pitch: number; zoom: number; fov: number; exaggeration: number; eye: number[]; ground: number | null }[] = await page.evaluate(() =>
			(globalThis as any).__tvtLook.trace(false)
		);
		const phase = (p: string) => trace.filter((x) => x.phase === p);
		const cam = phase('end:camera');
		const terrain = phase('end:terrain');
		note(`ending in place: ${cam.length} camera steps (pitch ${cam[0]?.pitch.toFixed(1)} → ${cam.at(-1)?.pitch.toFixed(1)}, fov ${cam[0]?.fov.toFixed(1)} → ${cam.at(-1)?.fov.toFixed(1)}), ${terrain.length} terrain steps (${terrain[0]?.exaggeration} → ${terrain.at(-1)?.exaggeration})`);
		// Eased: at least 8 steps each, every step a small part of the change.
		expect(cam.length).toBeGreaterThanOrEqual(8);
		expect(terrain.length).toBeGreaterThanOrEqual(8);
		const steps = (xs: number[]) => xs.slice(1).map((v, i) => Math.abs(v - xs[i]));
		const pitchTotal = Math.abs(cam.at(-1)!.pitch - cam[0].pitch);
		const fovTotal = Math.abs(cam.at(-1)!.fov - cam[0].fov);
		const exTotal = Math.abs(terrain.at(-1)!.exaggeration - terrain[0].exaggeration);
		expect(Math.max(0, ...steps(cam.map((x) => x.pitch)))).toBeLessThanOrEqual(pitchTotal * 0.4 + 1e-6);
		expect(Math.max(0, ...steps(cam.map((x) => x.fov)))).toBeLessThanOrEqual(fovTotal * 0.4 + 1e-6);
		expect(Math.max(0, ...steps(terrain.map((x) => x.exaggeration)))).toBeLessThanOrEqual(exTotal * 0.4 + 1e-6);
		// Within Explore's limits, and the eye above the drawn ground all the way.
		expect(cam.at(-1)!.pitch).toBeLessThanOrEqual(75 + 1e-9);
		expect(cam.at(-1)!.zoom).toBeLessThanOrEqual(22 + 1e-9);
		for (const x of trace) if (x.ground !== null) expect(x.eye[2] - x.ground, `${x.phase}: eye above the ground`).toBeGreaterThan(0);
		// Leaving moved nothing: the map is where the last step left it.
		const last = trace.filter((x) => x.phase !== 'left').at(-1)!;
		const left = phase('left')[0];
		expect(Math.hypot((left.eye[0] - last.eye[0]) * 80_500, (left.eye[1] - last.eye[1]) * 111_320, left.eye[2] - last.eye[2]), 'eye moved on leaving (m)').toBeLessThan(0.05);
		const after = await camera(page);
		expect(after).toMatchObject({ maxPitch: 75, maxZoom: 22, clamp: true, exaggeration: 1.3 });
		expect(after.pitch).toBeCloseTo(left.pitch, 6);
		await page.screenshot({ path: screenPath('wp13-ended-in-place.png') });
		expect(offsite).toEqual([]);
	});

	test('Esc order, Enter on a focused window, and a double-click straight in from the view before the click', { tag: '@wp13' }, async ({ page, offsite }) => {
		test.setTimeout(900_000);
		const key = seedsWithPairs().find((x) => x.kind === 'key')!;
		await openMap(page, at(key));
		const pole = await page.evaluate((id) => (globalThis as any).__tvtCameras.cameras().find((c: any) => c.id === id), key.cameraId);
		const start = await camera(page);

		// A double-click on the calibrated camera: straight in.
		const p = await pointOf(page, [pole.lng, pole.lat]);
		await page.mouse.dblclick(p.x, p.y);
		await expect.poll(async () => (await lookState(page)).phase, { timeout: 120_000 }).toBe('looking');
		await mapReady(page);
		expect((await lookState(page)).cameraId).toBe(key.cameraId);
		// The first click selected the camera and opened its window; both wait for the mode to end.
		expect(await page.evaluate(() => (globalThis as any).__tvt.layers.selection)).toMatchObject({ kind: 'camera', id: String(key.cameraId) });

		// Help closes first, and look-through stays.
		await page.keyboard.press('Shift+Slash');
		await expect(page.getByRole('button', { name: 'Close help' })).toBeVisible();
		await page.keyboard.press('Escape');
		await expect(page.getByRole('button', { name: 'Close help' })).toHaveCount(0);
		expect(await mode(page)).toBe('look');
		// Then look-through, back to the view before the double-click (not where its first click's fly had got to).
		await page.keyboard.press('Escape');
		await expect.poll(() => mode(page), { timeout: 120_000 }).toBe('explore');
		await mapReady(page);
		const back = await camera(page);
		for (const k of ['lng', 'lat', 'zoom', 'bearing', 'pitch'] as const) expect(Math.abs(back[k] - start[k]), k).toBeLessThan(1e-6);
		// The card and the window are still there: Esc closed only look-through.
		await expect(page.getByRole('region', { name: 'Selected camera' })).toBeVisible();
		const win = page.getByRole('dialog', { name: new RegExp(key.name) });
		await expect(win).toBeVisible();

		// Enter on the focused window goes straight in too.
		await win.focus();
		await page.keyboard.press('Enter');
		await expect.poll(async () => (await lookState(page)).phase, { timeout: 120_000 }).toBe('looking');
		await mapReady(page);
		// ← and → walk the calibrated cameras by distance, still looking through (jumps here: the next
		// camera is 2 km away, and only where the map camera lands matters).
		const count = (await lookState(page)).count;
		expect(count).toBeGreaterThanOrEqual(4);
		await page.emulateMedia({ reducedMotion: 'reduce' });
		await page.keyboard.press('ArrowRight');
		await expect.poll(async () => (await lookState(page)).index, { timeout: 120_000 }).toBe(1);
		await expect.poll(async () => (await lookState(page)).phase, { timeout: 120_000 }).toBe('looking');
		expect((await lookState(page)).cameraId).not.toBe(key.cameraId);
		expect((await inspect(page)).errorM).toBeLessThanOrEqual(0.1);
		await page.keyboard.press('ArrowLeft');
		await expect.poll(async () => (await lookState(page)).cameraId, { timeout: 120_000 }).toBe(key.cameraId);
		await expect.poll(async () => (await lookState(page)).phase, { timeout: 120_000 }).toBe('looking');
		await page.keyboard.press('Escape');
		await expect.poll(() => mode(page), { timeout: 120_000 }).toBe('explore');
		// Then (in Explore) Esc goes on down the chain to the selection.
		for (let i = 0; i < 4 && (await page.evaluate(() => (globalThis as any).__tvt.layers.selection)); i++) await page.keyboard.press('Escape');
		expect(await page.evaluate(() => (globalThis as any).__tvt.layers.selection)).toBeNull();
		expect(offsite).toEqual([]);
	});

	test('on a phone, look-through is full screen with a bottom strip', { tag: '@wp13' }, async ({ page, offsite }) => {
		test.setTimeout(400_000);
		await page.setViewportSize({ width: 390, height: 844 });
		await page.emulateMedia({ reducedMotion: 'reduce' });
		const hd = seedsWithPairs().find((x) => x.kind === 'hd')!;
		await openMap(page, at(hd, 16.5, 50));
		await enter(page, hd);
		const strip = page.getByRole('group', { name: 'Look-through' });
		await expect(strip).toBeVisible();
		await expect(strip.getByRole('slider', { name: 'Picture opacity' })).toBeVisible();
		await expect(strip.getByRole('button', { name: 'Step out' })).toBeVisible();
		const box: Box = (await lookState(page)).box;
		expect(box.width).toBeCloseTo(0.96 * 390, 0);
		expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
		await settle(page);
		await page.screenshot({ path: screenPath('wp13-look-phone.png') });
		await strip.getByRole('button', { name: 'Step out' }).click();
		await expect.poll(() => mode(page), { timeout: 120_000 }).toBe('explore');
		expect(offsite).toEqual([]);
	});

	test('entered from a z13 overview over higher ground, through the API and by a double-click: the centre on the terrain, the near plane under 2 m', { tag: '@wp13' }, async ({ page, offsite }) => {
		test.setTimeout(1_200_000);
		const all = seedsWithPairs();
		for (const [kind, centre] of OVERVIEWS) {
			const s = all.find((x) => x.kind === kind)!;
			for (const how of ['the API', 'a double-click'] as const) {
				// A fresh page each time: no window, no selection, nothing polled yet.
				await page.goto('about:blank');
				await openMap(page, `#map=13/${centre[1].toFixed(5)}/${centre[0].toFixed(5)}/0/0&layers=cameras`);
				// The overview's centre is above the camera's eye: MapLibre alone would put the centre 10 km out from there.
				const high = await page.evaluate(() => {
					const m = (globalThis as any).__tvt.map;
					const g = m.queryTerrainElevation(m.getCenter());
					return g === null ? null : g / (m.getTerrain()?.exaggeration ?? 1);
				});
				expect(high, `${s.kind}: the overview's ground (m) is above the eye at ${s.pose.alt} m`).toBeGreaterThan(s.pose.alt + 2);
				const start = await camera(page);
				// Load look-through (Step out is a no-op outside it), so its trace records the flight in.
				await page.evaluate(() => (globalThis as any).__tvtLook.stepOut());
				await page.evaluate(() => (globalThis as any).__tvtLook.trace(true));
				if (how === 'the API') {
					expect(await page.evaluate(([id, v]) => (globalThis as any).__tvtLook.enter(id, v), [s.cameraId, s.viewId] as const)).toBe(true);
				} else {
					// The first click flies to the camera; the double-click goes in from the overview, before that fly.
					const pole = await page.evaluate((id) => (globalThis as any).__tvtCameras.cameras().find((c: any) => c.id === id), s.cameraId);
					const p = await pointOf(page, [pole.lng, pole.lat]);
					await page.mouse.dblclick(p.x, p.y);
				}
				await expect.poll(async () => (await lookState(page)).phase, { timeout: 180_000 }).toBe('looking');
				expect((await lookState(page)).cameraId).toBe(s.cameraId);
				// The flight in never collapses the zoom (the bug's centre 10 km out read as zoom 12.1–12.7).
				const trace: { phase: string; zoom: number }[] = await page.evaluate(() => (globalThis as any).__tvtLook.trace(false));
				const fly = trace.filter((x) => x.phase === 'fly');
				expect(fly.length).toBeGreaterThan(0);
				const lowest = Math.min(...fly.map((x) => x.zoom));
				expect(lowest, 'the lowest zoom on the way in').toBeGreaterThan(start.zoom - 0.3);
				for (const when of ['on arrival', 'once the terrain has loaded'] as const) {
					if (when !== 'on arrival') {
						await mapReady(page);
						await page.waitForTimeout(3000);
					}
					const ins = await inspect(page);
					const line = `from the overview (${how}) ${s.kind} ${when}: centre ${ins.centre.elevation.toFixed(2)} m over terrain ${ins.centre.ground?.toFixed(2)} m, zoom ${ins.centre.zoom.toFixed(2)}, near ${ins.near.toFixed(2)} m, plane ${ins.plane.d.toFixed(2)} m, eye ${ins.errorM.toExponential(2)} m off; the flight's lowest zoom ${lowest.toFixed(2)} from ${start.zoom.toFixed(2)}`;
					note(line);
					test.info().annotations.push({ type: 'overview', description: line });
					expect(ins.errorM, line).toBeLessThanOrEqual(0.1);
					expect(ins.near, line).toBeLessThanOrEqual(2);
					expect(ins.centre.zoom, line).toBeGreaterThan(18);
					expect(ins.centre.ground, line).not.toBeNull();
					expect(Math.abs(ins.centre.elevation - ins.centre.ground), line).toBeLessThan(3);
					expect(ins.plane.d, line).toBeGreaterThanOrEqual(2 * ins.near);
				}
				const reg = await registration(page, s, s.pose);
				note(`from the overview (${how}) ${s.kind}: registration mean ${reg.mean.toFixed(3)} px, max ${reg.max.toFixed(3)} px`);
				expect(reg.mean).toBeLessThanOrEqual(1.5);
				await settle(page);
				await page.screenshot({ path: screenPath(`fix-look-overview-${s.kind}-${how === 'the API' ? 'api' : 'dblclick'}.png`) });
				// Out: back to the overview exactly.
				await page.keyboard.press('Escape');
				await expect.poll(() => mode(page), { timeout: 120_000 }).toBe('explore');
				await mapReady(page);
				const back = await camera(page);
				for (const k of ['lng', 'lat', 'zoom', 'bearing', 'pitch'] as const) expect(Math.abs(back[k] - start[k]), `${how}: ${k}`).toBeLessThan(1e-6);
			}
		}
		expect(offsite).toEqual([]);
	});

	test('a frame of another size while looking through: the message, never a blank picture, and the strip’s age is the picture’s', { tag: '@wp13' }, async ({ page, offsite }) => {
		test.setTimeout(600_000);
		await page.emulateMedia({ reducedMotion: 'reduce' });
		const all = seedsWithPairs();
		const key = all.find((x) => x.kind === 'key')!;
		const hd = all.find((x) => x.kind === 'hd')!;
		const big = readFileSync(join(env().framesDir, '_fixture', `view-${hd.viewId}.jpg`));
		const original = readFileSync(join(env().framesDir, key.frame));
		const msg = `Image size changed (${key.size.width}×${key.size.height} → ${hd.size.width}×${hd.size.height}); recalibrate`;
		const strip = page.getByRole('group', { name: 'Look-through' });
		const clocks = async () => (await strip.locator('.clocks').textContent())?.trim() ?? '';
		try {
			// 1. Straight in (no window, so nothing has polled the view) while the newest frame is of another size.
			appendFrame(key.imageId, big, new Date());
			await openMap(page, at(key, 16.5, 50));
			await enter(page, key);
			await expect.poll(async () => (await lookState(page)).problem, { timeout: 60_000 }).toBe(msg);
			await expect(strip.getByText(msg)).toBeVisible();
			// The reference frame (the calibrated size) is on the plane, labelled, and drawn: not a blank panel.
			await expect.poll(async () => (await inspect(page)).plane.texture, { timeout: 60_000 }).toBe(`look:${key.viewId}:ref`);
			expect((await inspect(page)).plane.layer).toBeGreaterThanOrEqual(0);
			expect(await lookState(page)).toMatchObject({ phase: 'looking', reference: true, seen: null });
			expect(await clocks()).toBe('reference picture');
			await settle(page);
			await page.screenshot({ path: screenPath('fix-look-size-changed-direct.png') });
			await stepOut(page);

			// 2. Back at the calibrated size, seen 10 minutes ago: looking through shows it, live.
			const old = appendFrame(key.imageId, original, new Date(Date.now() - 10 * 60_000));
			await page.goto('about:blank');
			await openMap(page, at(key, 16.5, 50));
			await enter(page, key);
			await expect.poll(async () => (await lookState(page)).seen, { timeout: 60_000 }).toBe(old.sha);
			expect(await lookState(page)).toMatchObject({ reference: false, problem: null });
			const texture = (await inspect(page)).plane.texture;
			expect(texture).toBe(`look:${key.viewId}:${old.sha}`);

			// 3. A frame of another size arrives: the message; the picture stays, and so does its age (about 10 min, not 0).
			appendFrame(key.imageId, big, new Date());
			await expect.poll(async () => (await lookState(page)).problem, { timeout: 60_000 }).toBe(msg);
			await expect(strip.getByText(msg)).toBeVisible();
			expect((await inspect(page)).plane.texture).toBe(texture);
			expect((await lookState(page)).seen).toBe(old.sha);
			const text = await clocks();
			const age = /^picture seen (\d+):(\d\d) ago$/.exec(text);
			expect(age, text).not.toBeNull();
			expect(Number(age![1]), text).toBeGreaterThanOrEqual(9);
			await settle(page);
			await page.screenshot({ path: screenPath('fix-look-size-changed-while-looking.png') });

			// 4. The calibrated size again: the message goes and the new picture shows.
			const back = appendFrame(key.imageId, original, new Date(Date.now() + 1000));
			await expect.poll(async () => (await lookState(page)).seen, { timeout: 60_000 }).toBe(back.sha);
			expect((await lookState(page)).problem).toBeNull();
			await expect(strip.getByText(msg)).toHaveCount(0);
			await stepOut(page);
		} finally {
			// Leave the newest frame at the calibrated size for the specs after this one.
			appendFrame(key.imageId, original, new Date(Date.now() + 2000));
		}
		expect(offsite).toEqual([]);
	});
});
