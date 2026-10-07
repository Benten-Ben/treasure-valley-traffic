import type { Page } from '@playwright/test';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { expect, mapReady, screenPath, test } from './fixtures.js';
import type { TransitNetwork } from '../../src/lib/contracts/network.js';
import type { Tracks } from '../../src/lib/contracts/tracks.js';

/**
 * buses3d (docs/14 §14.10 WP10; §14.4 "Buses and stops"): 3D buses and stops
 * on the `at=` replay.
 *
 * - a bus model is at least 28 px long at z15–16 (measured on the GPU: the
 *   scene's probe projects each model's nose and tail with the mesh shader's
 *   own placement);
 * - its heading is within 10° of the path bearing (the path's tangent over
 *   ±8 m, worked out here from the tracks API's steps at the frame's
 *   playhead);
 * - the route number is readable at z11, z14 and z17 and follows the badge
 *   rule: the disc or plate is drawn unobstructed, and its pixels show the
 *   numerals in the badge text color on the plate (and the halo, where the
 *   rule needs one);
 * - with no input at z15–17 the map renders no faster than the loop's
 *   formula, clamp(2 × the fastest on-screen bus speed in px/s, 2, 60), the
 *   scene's JS stays ≤ 1 ms p95 per frame, and nothing calls setData inside
 *   an animation frame;
 * - stale, unknown-route, selected and spotlit looks; stop posts and names;
 *   buses stay discs when the scene can't load;
 * - the screenshot set for the owner (data/dev/screens/wp10/).
 *
 * The laptop's database holds the 24 hours before 8:40 AM MDT Oct 7 (fixes
 * from 14:40 UTC Oct 6), so the replay is pinned at 23:00 UTC Oct 6 (5 PM
 * MDT, about 40 buses), not WP8's 14:30.
 */
const AT = '2026-10-06T23:00:00Z';
const AT_S = Date.parse(AT) / 1000;
const DOWNTOWN = '43.6152/-116.2035';
const APP = resolve(import.meta.dirname, '..', '..');
/** The overlay's disc (WP2's discSprite default): 26 px across. */
const DISC = 26;

interface BusDebug {
	id: string;
	routeId: string | null;
	lng: number;
	lat: number;
	state: string | null;
	kind: string | null;
	opacity: number;
	x: number | null;
	y: number | null;
	speed: number;
	model: number;
	heading3d: number | null;
	color3d: string | null;
	plate: number;
	plateSprite: string;
	disc: string;
}
interface PlateDebug {
	id: string;
	sprite: string;
	opacity: number;
	altitude: number;
	x: number | null;
	y: number | null;
	box: { x: number; y: number; w: number; h: number } | null;
}
interface Lod {
	zoom: number;
	fade: number;
	disc: number;
	scale: number;
	models: boolean;
	posts: boolean;
	modelZoom: number;
}

const transit = <T>(page: Page, fn: string, ...args: unknown[]): Promise<T> =>
	page.evaluate(([f, a]) => (globalThis as any).__tvtTransit[f as string](...(a as unknown[])), [fn, args] as const);
const buses = (page: Page) => transit<BusDebug[]>(page, 'buses');
const plates = (page: Page) => transit<PlateDebug[]>(page, 'plates');
const lod = (page: Page) => transit<Lod>(page, 'lod');
const pill = (page: Page) => page.locator('.pill-button');

function record(name: string, data: unknown) {
	const file = screenPath(name);
	mkdirSync(dirname(file), { recursive: true });
	writeFileSync(file, JSON.stringify(data, null, 2));
}

/** Open the replay at a view with Transit on, and wait for buses. */
async function open(page: Page, view: string) {
	await page.goto(`/?at=${AT}#map=${view}&layers=transit`);
	await mapReady(page);
	await page.waitForFunction(() => (globalThis as any).__tvtTransit, null, { timeout: 120_000 });
	await expect.poll(async () => (await buses(page)).filter((b) => b.state && b.state !== 'hidden').length, { timeout: 90_000 }).toBeGreaterThan(10);
}

/** Wait until models are drawn (the scene is loaded and the zoom is past the crossfade's start). */
async function modelsDrawn(page: Page) {
	await expect.poll(async () => (await lod(page)).models, { timeout: 120_000 }).toBe(true);
	await expect.poll(async () => (await buses(page)).filter((b) => b.model > 0).length, { timeout: 60_000 }).toBeGreaterThan(0);
}

async function jump(page: Page, cam: { zoom?: number; pitch?: number; bearing?: number; center?: [number, number] }) {
	await page.evaluate((c) => (globalThis as any).__tvt.map.jumpTo(c), cam);
	await mapReady(page);
}

/** Pause or play the replay with Space (focus off any button first). */
async function togglePause(page: Page, want: 'PAUSED' | 'PLAYING') {
	await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
	await page.keyboard.press('Space');
	if (want === 'PAUSED') await expect(pill(page)).toContainText('PAUSED');
	else await expect(pill(page)).not.toContainText('PAUSED');
}

/** The buses as drawn in the next rendered frame, and that frame's playhead. */
function nextFrame(page: Page): Promise<{ T: number; buses: BusDebug[] }> {
	return page.evaluate(
		() =>
			new Promise((resolve) => {
				const g = globalThis as any;
				g.__tvt.map.once('render', () => resolve({ T: g.__tvtTransit.frameT(), buses: g.__tvtTransit.buses() }));
				g.__tvt.map.triggerRepaint();
			})
	);
}

const inside = (x: number | null, y: number | null, m = 0, W = 1280, H = 800) => x !== null && y !== null && x >= m && y >= m && x <= W - m && y <= H - m;

// -- path geometry (the §14.4 definitions, worked out independently of the app) ------------------------

const DEG = Math.PI / 180;
const mPerDegLon = (lat: number) => 111_320 * Math.cos(lat * DEG);
const metres = (a: number, b: number, c: number, d: number) => Math.hypot((c - a) * mPerDegLon((b + d) / 2), (d - b) * 110_574);
const bearing = (a: number, b: number, c: number, d: number) => (Math.atan2((c - a) * mPerDegLon((b + d) / 2), (d - b) * 110_574) / DEG + 360) % 360;
const angle = (a: number, b: number) => Math.abs(((((a - b) % 360) + 540) % 360) - 180);

interface AlongStep {
	t0: number;
	t1: number;
	path: number[];
	cum: number[];
}

function pointAt(s: AlongStep, d: number): [number, number] {
	const { path, cum } = s;
	const n = cum.length;
	if (d <= 0) return [path[0], path[1]];
	if (d >= cum[n - 1]) return [path[2 * n - 2], path[2 * n - 1]];
	let i = 1;
	while (cum[i] < d) i++;
	const f = (d - cum[i - 1]) / (cum[i] - cum[i - 1] || 1);
	return [path[2 * i - 2] + (path[2 * i] - path[2 * i - 2]) * f, path[2 * i - 1] + (path[2 * i + 1] - path[2 * i - 1]) * f];
}

function alongSteps(t: Tracks): Map<string, AlongStep[]> {
	const out = new Map<string, AlongStep[]>();
	for (const s of t.steps) {
		if (s[3] !== 'along' || !s[8] || s[2] === null) continue;
		const path = s[8];
		const cum = [0];
		for (let i = 2; i < path.length; i += 2) cum.push(cum[cum.length - 1] + metres(path[i - 2], path[i - 1], path[i], path[i + 1]));
		if (!out.has(s[0])) out.set(s[0], []);
		out.get(s[0])!.push({ t0: s[1], t1: s[2], path, cum });
	}
	return out;
}

// -- pixels -----------------------------------------------------------------------------------------

const hex = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const near = (p: number[], c: number[], tol: number) => Math.hypot(p[0] - c[0], p[1] - c[1], p[2] - c[2]) <= tol;

/** A screenshot of a box, decoded in the page (no PNG decoder here): RGBA rows. */
async function pixels(page: Page, box: { x: number; y: number; w: number; h: number }, name: string): Promise<{ w: number; h: number; data: number[] }> {
	const clip = { x: Math.round(box.x), y: Math.round(box.y), width: Math.round(box.w), height: Math.round(box.h) };
	const png = await page.screenshot({ clip, path: screenPath(name) });
	return page.evaluate(async (b64) => {
		const img = new Image();
		img.src = `data:image/png;base64,${b64}`;
		await img.decode();
		const c = new OffscreenCanvas(img.width, img.height);
		const g = c.getContext('2d')!;
		g.drawImage(img, 0, 0);
		return { w: img.width, h: img.height, data: Array.from(g.getImageData(0, 0, img.width, img.height).data) };
	}, png.toString('base64'));
}

/** Parse a disc's or plate's sprite key: `bus:` or `plate:` + color:textColor:text:halo:… */
function badgeOf(key: string) {
	const [, color, textColor, text, halo] = key.split(':');
	return { color, textColor, text, halo: halo === '1' };
}

const HALO_OF = (text: string) => (text.toLowerCase() === '#ffffff' ? '#2b2a33' : '#fffbf4');

/** Count the numeral, plate and halo colors inside a sprite's body. */
function readable(px: { w: number; h: number; data: number[] }, badge: { color: string; textColor: string; halo: boolean }, inBody: (x: number, y: number) => boolean) {
	const plate = hex(badge.color);
	const numerals = hex(badge.textColor);
	const halo = hex(HALO_OF(badge.textColor));
	let n = 0;
	let p = 0;
	let h = 0;
	for (let y = 0; y < px.h; y++)
		for (let x = 0; x < px.w; x++) {
			if (!inBody(x, y)) continue;
			const i = (y * px.w + x) * 4;
			const c = [px.data[i], px.data[i + 1], px.data[i + 2]];
			if (near(c, numerals, 40)) n++;
			else if (near(c, plate, 40)) p++;
			else if (badge.halo && near(c, halo, 40)) h++;
		}
	return { numerals: n, plate: p, halo: h };
}

test.describe('buses3d', () => {
	test('a bus model is at least 28 px long at z15–16, and its heading is within 10° of the path bearing', { tag: '@wp10' }, async ({ page, request, consoleErrors }) => {
		test.setTimeout(600_000);
		await open(page, `15.05/${DOWNTOWN}/0/0`);
		await modelsDrawn(page);
		// Nothing moves between the nose and tail probes.
		await togglePause(page, 'PAUSED');
		const rows: { zoom: number; n: number; min: number; max: number; scale: number }[] = [];
		for (const zoom of [15.05, 15.25, 15.5, 15.75, 16]) {
			await jump(page, { zoom });
			await modelsDrawn(page);
			const lengths = (await transit<{ id: string; length: number; x: number; y: number }[]>(page, 'modelLengths')).filter((l) => inside(l.x, l.y));
			const l = await lod(page);
			const row = { zoom, n: lengths.length, min: Math.min(...lengths.map((x) => x.length)), max: Math.max(...lengths.map((x) => x.length)), scale: l.scale };
			rows.push(row);
			console.log(`z${zoom}: ${row.n} models on screen, ${row.min.toFixed(2)}–${row.max.toFixed(2)} px long (scale ${row.scale.toFixed(2)}, fade ${l.fade.toFixed(2)})`);
			expect(row.n, `models on screen at z${zoom}`).toBeGreaterThan(0);
			expect(row.min, `shortest model at z${zoom} (px)`).toBeGreaterThanOrEqual(28);
			expect(l.scale).toBeLessThanOrEqual(4);
		}
		await page.screenshot({ path: screenPath('length-z16-top.png') });
		record('model-lengths.json', rows);

		// Heading: play on, and at each sampled frame compare every model on an along step with the path's
		// tangent at the frame's playhead.
		await togglePause(page, 'PLAYING');
		await jump(page, { zoom: 15.4, center: [-116.2235, 43.6152] });
		await modelsDrawn(page);
		const tracks: Tracks = await (await request.get(`/api/transit/tracks?window=900&at=${new Date((AT_S + 600) * 1000).toISOString()}`)).json();
		const steps = alongSteps(tracks);
		const errs: { id: string; err: number; off: number }[] = [];
		for (let k = 0; k < 40; k++) {
			const s = await nextFrame(page);
			for (const b of s.buses) {
				if (!(b.model > 0) || b.kind !== 'along' || b.heading3d === null) continue;
				const step = steps.get(b.id)?.find((x) => x.t0 <= s.T && x.t1 > s.T);
				if (!step) continue;
				const len = step.cum[step.cum.length - 1];
				const d = ((s.T - step.t0) / (step.t1 - step.t0)) * len;
				const p = pointAt(step, d);
				const a = pointAt(step, Math.max(0, d - 8));
				const c = pointAt(step, Math.min(len, d + 8));
				errs.push({ id: b.id, err: angle(b.heading3d, bearing(a[0], a[1], c[0], c[1])), off: metres(p[0], p[1], b.lng, b.lat) });
			}
			await page.waitForTimeout(300);
		}
		errs.sort((a, b) => a.err - b.err);
		const q = (f: number) => errs[Math.min(errs.length - 1, Math.floor(errs.length * f))].err;
		const summary = { samples: errs.length, buses: new Set(errs.map((e) => e.id)).size, median: q(0.5), p95: q(0.95), max: q(1), maxOffsetM: Math.max(...errs.map((e) => e.off)) };
		record('heading.json', summary);
		console.log(`heading vs path tangent: ${summary.samples} samples of ${summary.buses} buses; median ${summary.median.toFixed(2)}°, p95 ${summary.p95.toFixed(2)}°, max ${summary.max.toFixed(2)}°; position within ${summary.maxOffsetM.toFixed(2)} m`);
		expect(summary.samples).toBeGreaterThanOrEqual(50);
		expect(summary.maxOffsetM, 'the model is where the steps put it (m)').toBeLessThan(1);
		expect(summary.max, 'heading vs path bearing (degrees)').toBeLessThanOrEqual(10);
		expect(consoleErrors).toEqual([]);
	});

	test('the route number is readable at z11, z14 and z17, following the badge rule', { tag: '@wp10' }, async ({ page }) => {
		test.setTimeout(600_000);
		await open(page, '11/43.61/-116.30/0/0');
		await togglePause(page, 'PAUSED');
		const results: Record<string, unknown>[] = [];
		const panels = (x: number, y: number) => x > 320 && x < 1200 && y > 90 && y < 680;

		// Discs at z11 and z14: the clearest one (nothing else drawn within a disc of it).
		for (const [zoom, view] of [
			[11, '11/43.61/-116.30/0/0'],
			[14, `14/${DOWNTOWN}/0/0`]
		] as const) {
			if (zoom === 14) await jump(page, { zoom: 14, center: [-116.2035, 43.6152] });
			const l = await lod(page);
			expect(l.disc, `discs at z${zoom}`).toBe(1);
			const list = (await buses(page)).filter((b) => b.opacity > 0 && inside(b.x, b.y));
			const clear = list.filter((b) => b.opacity >= 0.99 && b.state !== 'stale' && panels(b.x!, b.y!) && list.every((o) => o === b || Math.hypot(o.x! - b.x!, o.y! - b.y!) > DISC + 4));
			expect(clear.length, `an unobstructed disc at z${zoom} (${list.length} drawn)`).toBeGreaterThan(0);
			const b = clear[0];
			const badge = badgeOf(b.disc);
			const px = await pixels(page, { x: b.x! - 16, y: b.y! - 16, w: 32, h: 32 }, `readable-z${zoom}-disc-${b.id}.png`);
			// Inside the disc's rim (radius 13, a 2 px cream stroke): radius 10 around the centre.
			const counts = readable(px, badge, (x, y) => Math.hypot(x - 16, y - 16) <= 10);
			results.push({ zoom, view, bus: b.id, text: badge.text, ...badge, ...counts, drawn: list.length, unobstructed: clear.length });
			console.log(`z${zoom}: disc ${badge.text} (bus ${b.id}): ${counts.numerals} numeral px, ${counts.plate} plate px, ${counts.halo} halo px; ${clear.length} of ${list.length} discs unobstructed`);
			expect(counts.numerals, 'numeral pixels').toBeGreaterThanOrEqual(12);
			expect(counts.plate, 'plate pixels').toBeGreaterThanOrEqual(60);
			if (badge.halo) expect(counts.halo, 'halo pixels').toBeGreaterThanOrEqual(10);
		}

		// Plates at z17, over the models: centre on a running bus that's not stale.
		const target = (await buses(page)).find((b) => b.state !== 'stale' && b.state !== 'hidden' && inside(b.x, b.y, 100))!;
		expect(target, 'a bus to zoom in on').toBeTruthy();
		await jump(page, { zoom: 17, center: [target.lng, target.lat] });
		await modelsDrawn(page);
		const list = (await plates(page)).filter((p) => p.box && p.opacity > 0 && inside(p.box.x, p.box.y, -40));
		const overlaps = (a: NonNullable<PlateDebug['box']>, b: NonNullable<PlateDebug['box']>) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
		const clear = list.filter((p) => p.opacity >= 0.99 && !p.sprite.includes(':hollow') && panels(p.box!.x, p.box!.y) && list.every((o) => o === p || !overlaps(o.box!, p.box!)));
		expect(clear.length, `an unobstructed plate at z17 (${list.length} drawn)`).toBeGreaterThan(0);
		const p = clear.find((x) => x.id === target.id) ?? clear[0];
		const badge = badgeOf(p.sprite);
		const box = p.box!;
		const px = await pixels(page, { x: box.x - 4, y: box.y - 4, w: box.w + 8, h: box.h + 14 }, `readable-z17-plate-${p.id}.png`);
		// The body, 3 px in from its edge (the rim is drawn on the edge).
		const counts = readable(px, badge, (x, y) => x >= 7 && y >= 7 && x < box.w + 1 && y < box.h + 1);
		results.push({ zoom: 17, bus: p.id, ...badge, ...counts, drawn: list.length, unobstructed: clear.length, altitude: p.altitude });
		console.log(`z17: plate ${badge.text} (bus ${p.id}): ${counts.numerals} numeral px, ${counts.plate} plate px, ${counts.halo} halo px; ${clear.length} of ${list.length} plates unobstructed`);
		expect(counts.numerals).toBeGreaterThanOrEqual(12);
		expect(counts.plate).toBeGreaterThanOrEqual(60);
		if (badge.halo) expect(counts.halo).toBeGreaterThanOrEqual(10);
		// The plate is the top of the map: drawn above the model, never under it.
		const layers: string[] = await page.evaluate(() => (globalThis as any).__tvt.map.getLayersOrder());
		expect(layers.indexOf('overlay')).toBeGreaterThan(layers.indexOf('scene-3d'));
		await page.screenshot({ path: screenPath('readable-z17.png') });
		record('readable.json', results);
	});

	test('with no input at z15–17 the map renders within the loop formula, the scene JS stays ≤ 1 ms p95, and no setData runs in an animation frame', { tag: '@wp10' }, async ({ page }) => {
		test.setTimeout(900_000);
		await open(page, `15.3/${DOWNTOWN}/0/0`);
		// Count setData/updateData on every GeoJSON source, and which ran inside a frame (MapLibre's render or any rAF callback).
		await page.evaluate(() => {
			const g = globalThis as any;
			g.__sd = { total: 0, inFrame: 0, ids: {} as Record<string, number> };
			g.__inFrame = 0;
			const map = g.__tvt.map;
			const raf = globalThis.requestAnimationFrame.bind(globalThis);
			globalThis.requestAnimationFrame = (cb: FrameRequestCallback) =>
				raf((t) => {
					g.__inFrame++;
					try {
						cb(t);
					} finally {
						g.__inFrame--;
					}
				});
			const render = map._render;
			map._render = function (...a: unknown[]) {
				g.__inFrame++;
				try {
					return render.apply(this, a);
				} finally {
					g.__inFrame--;
				}
			};
			const proto = Object.getPrototypeOf(map.getSource('transit-ribbons'));
			for (const name of ['setData', 'updateData']) {
				const orig = proto[name];
				proto[name] = function (this: { id: string }, ...args: unknown[]) {
					g.__sd.total++;
					g.__sd.ids[this.id] = (g.__sd.ids[this.id] ?? 0) + 1;
					if (g.__inFrame > 0) g.__sd.inFrame++;
					return orig.apply(this, args);
				};
			}
		});
		const rows: Record<string, unknown>[] = [];
		for (const [zoom, pitch] of [
			[15.3, 0],
			[16, 45],
			[17, 60]
		]) {
			await jump(page, { zoom, pitch, bearing: -15 });
			await modelsDrawn(page);
			await page.waitForTimeout(3000);
			await mapReady(page);
			const m = await page.evaluate(async (ms) => {
				const g = globalThis as any;
				const map = g.__tvt.map;
				const t = g.__tvtTransit;
				const c = map.getCanvas();
				const [W, H] = [c.clientWidth, c.clientHeight];
				const R = 6371008.8;
				const pxps = (mps: number) => mps / ((2 * Math.PI * R * Math.cos((map.getCenter().lat * Math.PI) / 180)) / (512 * 2 ** map.getZoom()));
				g.__sd.total = 0;
				g.__sd.inFrame = 0;
				g.__sd.ids = {};
				let frames = 0;
				let lastScene = t.sceneStats()?.frames ?? 0;
				const sceneMs: number[] = [];
				const onRender = () => {
					frames++;
					const s = t.sceneStats();
					if (s && s.frames !== lastScene) {
						lastScene = s.frames;
						sceneMs.push(s.lastFrameMs);
					}
				};
				map.on('render', onRender);
				let expected = 0;
				let fastestSeen = 0;
				const dt = 100;
				const timer = setInterval(() => {
					let fastest = 0;
					for (const b of t.buses()) if (b.state !== 'hidden' && b.speed > 0 && b.x !== null && b.x >= 0 && b.y >= 0 && b.x <= W && b.y <= H) fastest = Math.max(fastest, b.speed);
					fastestSeen = Math.max(fastestSeen, fastest);
					expected += fastest > 0 ? (Math.min(60, Math.max(2, 2 * pxps(fastest))) * dt) / 1000 : 0;
				}, dt);
				await new Promise((r) => setTimeout(r, ms));
				clearInterval(timer);
				map.off('render', onRender);
				sceneMs.sort((a, b) => a - b);
				const p95 = sceneMs.length ? sceneMs[Math.min(sceneMs.length - 1, Math.floor(sceneMs.length * 0.95))] : null;
				return { frames, expected, fastestSeen, sceneFrames: sceneMs.length, p95, setData: { ...g.__sd }, stats: t.sceneStats(), lod: t.lod() };
			}, 15_000);
			const row = { zoom, pitch, ...m };
			rows.push(row);
			console.log(
				`z${zoom} pitch ${pitch}: ${m.frames} frames in 15 s, formula allows ${m.expected.toFixed(1)} (fastest on screen ${m.fastestSeen.toFixed(1)} m/s); scene JS p95 ${m.p95?.toFixed(2)} ms over ${m.sceneFrames} frames; setData ${m.setData.total} (${m.setData.inFrame} in a frame)`
			);
			expect(m.lod.models, `models at z${zoom}`).toBe(true);
			expect(m.frames, 'buses move, so frames come').toBeGreaterThan(0);
			expect(m.frames, `frames at z${zoom} vs the loop formula`).toBeLessThanOrEqual(m.expected * 1.2 + 3);
			expect(m.p95, `scene JS p95 at z${zoom} (ms)`).not.toBeNull();
			expect(m.p95!, `scene JS p95 at z${zoom} (ms)`).toBeLessThanOrEqual(1);
			expect(m.setData.inFrame, `setData inside an animation frame at z${zoom}`).toBe(0);
		}
		// A camera animation too: still no setData in its frames.
		const anim = await page.evaluate(async () => {
			const g = globalThis as any;
			g.__sd.total = 0;
			g.__sd.inFrame = 0;
			const map = g.__tvt.map;
			map.easeTo({ zoom: 15.6, pitch: 30, bearing: 20, duration: 2500 });
			await new Promise((r) => setTimeout(r, 4000));
			return { ...g.__sd };
		});
		console.log(`during a 2.5 s camera animation: setData ${anim.total} (${anim.inFrame} in a frame)`);
		expect(anim.inFrame).toBe(0);
		record('fps-and-scene-js.json', { rows, anim });
	});

	test('stale, unknown-route, selected and spotlit buses; stop posts and names; discs when the scene can’t load', { tag: '@wp10' }, async ({ page, request, browser }) => {
		test.setTimeout(900_000);
		const net: TransitNetwork = await (await request.get('/api/transit/network')).json();
		const route = new Map(net.routes.map((r) => [r.id, r]));
		// One moving bus is made unknown (as the API sends a bus with no route: gray, ink, halo).
		let unknownId: string | null = null;
		await page.route('**/api/transit/tracks**', async (r) => {
			const res = await r.fetch();
			const t: Tracks = await res.json();
			// The bus moving along its path at the playhead (now − the 90 s delay) for longest after it.
			// (A fixed 30 s margin, t1 > now − 60, found no bus for most of the seconds after `at`.)
			if (!unknownId)
				unknownId =
					t.steps
						.filter((s) => s[3] === 'along' && s[1] <= t.now - 90 && (s[2] ?? 0) > t.now - 90)
						.sort((a, b) => (b[2] ?? 0) - (a[2] ?? 0))[0]?.[0] ?? null;
			if (unknownId && t.vehicles[unknownId])
				t.vehicles[unknownId] = { ...t.vehicles[unknownId], routeId: null, routeSource: null, shortName: null, color: '#8a857c', textColor: '#2b2a33', halo: true };
			await r.fulfill({ json: t, headers: { 'cache-control': 'no-store' } });
		});
		await open(page, `15/${DOWNTOWN}/0/0`);
		await togglePause(page, 'PAUSED');

		// Stale: the ghost body and a hollow plate.
		const stale = (await buses(page)).find((b) => b.state === 'stale');
		expect(stale, 'a stale bus in the replay').toBeTruthy();
		await jump(page, { center: [stale!.lng, stale!.lat], zoom: 16.6, pitch: 50, bearing: 10 });
		await modelsDrawn(page);
		const s = (await buses(page)).find((b) => b.id === stale!.id)!;
		expect(s.plateSprite).toContain(':hollow');
		expect(s.color3d).toBe(route.get(s.routeId!)!.ghost);
		await page.screenshot({ path: screenPath('look-stale.png') });

		// Unknown route: gray with "?".
		const u = (await buses(page)).find((b) => b.id === unknownId)!;
		expect(u, 'the bus made unknown').toBeTruthy();
		await jump(page, { center: [u.lng, u.lat], zoom: 16.6, pitch: 50, bearing: 10 });
		await modelsDrawn(page);
		const uu = (await buses(page)).find((b) => b.id === unknownId)!;
		expect(uu.color3d).toBe('#8a857c');
		expect(uu.plateSprite).toMatch(/^plate:#8a857c:#2b2a33:\?:1:solid/);
		await page.screenshot({ path: screenPath('look-unknown-route.png') });

		// Selected: click the model; the plate gets its ring and lifts with the model; the scene adds the ground ring.
		const before = (await transit<{ drawCalls: number }>(page, 'sceneStats')).drawCalls;
		const placed = await transit<{ id: string; x: number; y: number }[]>(page, 'placed');
		const pick = placed.find((p) => p.id === unknownId) ?? placed.find((p) => (s.id ? p.id === s.id : false));
		expect(pick, 'a model to click').toBeTruthy();
		await page.mouse.click(pick!.x, pick!.y);
		await expect(page.getByRole('region', { name: 'Selected bus' })).toBeVisible();
		await page.waitForTimeout(1500);
		const sel = (await plates(page)).find((p) => p.id === pick!.id)!;
		expect(sel.sprite).toContain(':sel');
		const others = (await plates(page)).filter((p) => p.id !== pick!.id);
		if (others.length) expect(sel.altitude - others[0].altitude).toBeGreaterThanOrEqual(2);
		expect((await transit<{ drawCalls: number }>(page, 'sceneStats')).drawCalls, 'the ground ring adds a draw').toBeGreaterThan(before);
		await page.screenshot({ path: screenPath('look-selected.png') });
		await page.keyboard.press('Escape');

		// Spotlight a running route: every other route's bus takes its ghost body and a dimmed plate.
		await jump(page, { center: [-116.2035, 43.6152], zoom: 16, pitch: 45, bearing: -20 });
		await modelsDrawn(page);
		const drawn = (await buses(page)).filter((b) => b.model > 0 && b.routeId && b.state !== 'stale');
		expect(drawn.length, 'models downtown').toBeGreaterThan(0);
		const spot = drawn[0].routeId!;
		await page.getByRole('region', { name: 'Transit legend' }).getByRole('button', { name: new RegExp(`^${route.get(spot)!.shortName}\\b`) }).first().click();
		await expect(page.getByRole('region', { name: 'Selected route' })).toBeVisible();
		await page.waitForTimeout(1000);
		const lit = await buses(page);
		for (const b of lit.filter((x) => x.model > 0 && x.routeId && x.state !== 'stale')) {
			const r = route.get(b.routeId!)!;
			expect(b.color3d, `bus ${b.id} on route ${b.routeId} while ${spot} is spotlit`).toBe(b.routeId === spot ? r.color : r.ghost);
			if (b.routeId !== spot) expect(b.plate).toBeLessThanOrEqual(0.31);
		}
		await page.screenshot({ path: screenPath('look-spotlight.png') });
		await page.keyboard.press('Escape');

		// Stop posts from z16 with a flag per route, names from z17; a click on a post opens the stop card.
		await jump(page, { center: [-116.2035, 43.6152], zoom: 17.4, pitch: 60, bearing: -25 });
		await expect.poll(async () => (await transit<{ shown: boolean; near: number }>(page, 'posts')).shown, { timeout: 60_000 }).toBe(true);
		const posts = await transit<{ near: number; scale: number }>(page, 'posts');
		expect(posts.near).toBeGreaterThan(0);
		await mapReady(page);
		const names = await page.evaluate(() => (globalThis as any).__tvt.map.queryRenderedFeatures({ layers: ['transit-stop-names'] }).length);
		expect(names, 'stop names at z17.4').toBeGreaterThan(0);
		await page.screenshot({ path: screenPath('look-stop-posts-z17.png') });
		const stopIds = new Set(net.stops.map((x) => x.id));
		const all3d = await transit<{ id: string; x: number; y: number }[]>(page, 'placed');
		const busXY = [...all3d.filter((p) => !stopIds.has(p.id)), ...(await plates(page)).filter((p) => p.x !== null).map((p) => ({ x: p.x!, y: p.y! }))];
		const candidates = all3d.filter((p) => stopIds.has(p.id) && p.x > 340 && p.x < 1180 && p.y > 120 && p.y < 660 && busXY.every((b) => Math.hypot(b.x - p.x, b.y - p.y) > 40));
		// …and away from hub pills, which outrank stops.
		const freeOfHubs: boolean[] = await page.evaluate(
			(pts) => pts.map((p) => !(globalThis as any).__tvt.map.queryRenderedFeatures([[p.x - 30, p.y - 30], [p.x + 30, p.y + 30]], { layers: ['transit-hubs'] }).length),
			candidates
		);
		const post = candidates.find((_, i) => freeOfHubs[i]);
		expect(post, 'a stop post on screen').toBeTruthy();
		await page.mouse.click(post!.x, post!.y);
		await expect(page.getByRole('region', { name: 'Selected stop' })).toBeVisible();
		await page.screenshot({ path: screenPath('look-stop-selected.png') });

		// The scene chunk can't load: buses stay discs at every zoom, and there are no plates.
		const file = resolve(APP, '.svelte-kit', 'output', 'client', '.vite', 'manifest.json');
		const manifest = existsSync(file) ? (JSON.parse(readFileSync(file, 'utf8')) as Record<string, { src?: string; file: string }>) : {};
		const chunk = Object.values(manifest).find((v) => v.src === 'src/lib/scene/index.ts')?.file;
		expect(chunk, 'the scene chunk in the build').toBeTruthy();
		const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
		const p2 = await ctx.newPage();
		await p2.route(`**/${chunk}`, (r) => r.abort());
		await open(p2, `15/${DOWNTOWN}/0/0`);
		await jump(p2, { zoom: 16.5, pitch: 45 });
		await expect.poll(() => transit<string>(p2, 'scene'), { timeout: 60_000 }).toBe('failed');
		await p2.waitForTimeout(1000);
		const discs = (await buses(p2)).filter((b) => b.opacity > 0 && inside(b.x, b.y));
		expect(discs.length, 'discs at z16.5 without the scene').toBeGreaterThan(0);
		expect(await plates(p2)).toEqual([]);
		expect((await lod(p2)).disc).toBe(1);
		await p2.screenshot({ path: screenPath('look-no-scene-discs-z16.png') });
		await ctx.close();
	});

	test('screenshots for the owner: z11 to z18.5, desktop and phone', { tag: '@wp10' }, async ({ page, request }) => {
		test.setTimeout(900_000);
		const net: TransitNetwork = await (await request.get('/api/transit/network')).json();
		// Close-ups centred on a moving bus and on a stop with several routes (posts, flags, names).
		const closeups: [string, 'bus' | 'stop', { zoom: number; pitch: number; bearing: number }][] = [
			['wp10-11-bus-closeup-z17.5-pitch60', 'bus', { zoom: 17.5, pitch: 60, bearing: 30 }],
			['wp10-12-bus-closeup-z18.5-pitch65', 'bus', { zoom: 18.5, pitch: 65, bearing: -40 }],
			['wp10-13-stop-closeup-z18.3-pitch62', 'stop', { zoom: 18.3, pitch: 62, bearing: 20 }]
		];
		await open(page, `16/${DOWNTOWN}/0/0`);
		await modelsDrawn(page);
		await togglePause(page, 'PAUSED');
		for (const [name, what, cam] of closeups) {
			let center: [number, number];
			if (what === 'bus') {
				const list = (await buses(page)).filter((x) => x.model > 0 && x.state !== 'stale' && inside(x.x, x.y, 120));
				const b = list.find((x) => x.state === 'moving') ?? list[0];
				expect(b, 'a bus on screen').toBeTruthy();
				center = [b!.lng, b!.lat];
			} else {
				const c = await page.evaluate(() => (globalThis as any).__tvt.map.getCenter());
				const s = net.stops.filter((x) => x.routes.length >= 3).sort((a, b) => Math.hypot(a.lon - c.lng, a.lat - c.lat) - Math.hypot(b.lon - c.lng, b.lat - c.lat))[0];
				center = [s.lon, s.lat];
			}
			await jump(page, { ...cam, center });
			await page.waitForTimeout(2000);
			await mapReady(page);
			await page.screenshot({ path: screenPath(`${name}.png`) });
			await jump(page, { zoom: 16, pitch: 0, bearing: 0, center: [-116.2035, 43.6152] });
		}
		const shots: [string, string, { width: number; height: number }][] = [
			['wp10-01-valley-z11', '11/43.61/-116.30/0/0', { width: 1280, height: 800 }],
			['wp10-02-downtown-z14', `14/${DOWNTOWN}/0/0`, { width: 1280, height: 800 }],
			['wp10-03-downtown-hub-z15', `15/${DOWNTOWN}/0/0`, { width: 1280, height: 800 }],
			['wp10-04-crossfade-z15.15', `15.15/${DOWNTOWN}/-20/45`, { width: 1280, height: 800 }],
			['wp10-05-downtown-z16-top', `16/${DOWNTOWN}/0/0`, { width: 1280, height: 800 }],
			['wp10-06-downtown-z16-pitch50', `16/${DOWNTOWN}/-20/50`, { width: 1280, height: 800 }],
			['wp10-07-downtown-z17.5-pitch62', `17.5/43.6147/-116.2019/-30/62`, { width: 1280, height: 800 }],
			['wp10-08-fairview-z16-pitch55', '16/43.6177/-116.2650/70/55', { width: 1280, height: 800 }],
			['wp10-09-phone-z16-pitch50', `16/${DOWNTOWN}/-20/50`, { width: 390, height: 844 }],
			['wp10-10-phone-z17-pitch60', `17/43.6147/-116.2019/-30/60`, { width: 390, height: 844 }]
		];
		for (const [name, view, size] of shots) {
			await page.setViewportSize(size);
			await open(page, view);
			if (Number(view.split('/')[0]) >= 15.1) await modelsDrawn(page);
			await page.waitForTimeout(2500);
			await mapReady(page);
			await page.screenshot({ path: screenPath(`${name}.png`) });
		}
	});
});
