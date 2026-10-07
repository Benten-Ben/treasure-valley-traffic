#!/usr/bin/env node
/**
 * Seeded data for the UI v2 packages (docs/14 §14.11, "Seeded data").
 *
 *   npm run seed                                   copy the templates into this package's FRAMES_DIR and
 *     (node scripts/seed-dev.ts [--fresh])         TVT_ARCHIVE (data/dev/<wp>/), then tick the archive once
 *   node scripts/seed-dev.ts templates --db tvt_template
 *                                                  WP0 only: build the templates in data/dev/templates and
 *                                                  write the synthetic calibrations into that database
 *
 * The templates:
 *
 * - **4 synthetic calibrations** near real poles: a key camera, one rolled
 *   5°, one tilted under 15° and one 1920×1166 HD frame. Their point pairs are
 *   made with solver.project, so RMS is 0. Rows have created_by 'seed:wp0'.
 *   A view that already has a real calibration is never touched.
 * - **A reference frame for each, rendered from our own map** at the seeded
 *   pose: the vite dev server serves the app's own createMap; Playwright sets
 *   the field of view, places the camera with
 *   calculateCameraOptionsFromCameraLngLatAltRotation, turns Aerial on with
 *   terrain at exaggeration 1, and screenshots at the frame's size, with a
 *   synthetic 511-style bar. Each seed's pairs are then projected with
 *   map.project and compared with the solver's pixels (the registration
 *   numbers go in seed.json). Without imagery the frame is an ffmpeg test
 *   pattern (fixtures.sh) and the seed is marked `visual: false`.
 * - **_fixture/** frames for TVT_FRAME_SOURCE=fixture (frames.ts).
 * - **A fake archive** with index.csv for the 34 key image IDs: test
 *   patterns, except the seeded key camera, whose archive frames are its
 *   map-rendered frame.
 *
 * No real camera image is used anywhere.
 */
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { cpSync, existsSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { harnessEnv, databaseUrl, mainCheckout, APP_DIR, CHROMIUM_ARGS, lockedArgs } from './harness-env.mjs';
import { INDEX, INDEX_HEADER, fetchedAtOf, jpegDir, localDay, stampOf, tick, withComment } from './archive-tick.ts';
import { pixelToGround, project, type ImageSize, type Pair, type Pixel, type Pose } from '../src/lib/calibration/solver.ts';

const REPO = resolve(APP_DIR, '..');
export const SEED_CREATED_BY = 'seed:wp0';
const SEED_NOTE =
	'Synthetic seed (WP0, docs/14 §14.11): a made-up pose near the real pole, with a reference frame rendered ' +
	'from our own map. Not a real calibration.';

/** The four seeds, by 511 image id (stable across databases). */
export const SEEDS = [
	{ kind: 'key', imageId: 656, offsetM: [8, -6], height: 10, heading: 355, tilt: 20, roll: 0, vfov: 42, size: { width: 768, height: 466 } },
	{ kind: 'roll', imageId: 637, offsetM: [5, 0], height: 8, heading: 150, tilt: 25, roll: -5, vfov: 45, size: { width: 768, height: 466 } },
	{ kind: 'low-tilt', imageId: 634, offsetM: [4, -5], height: 11, heading: 268, tilt: 9, roll: 0, vfov: 30, size: { width: 768, height: 466 } },
	{ kind: 'hd', imageId: 675, offsetM: [0, 8], height: 14, heading: 92, tilt: 16, roll: 0, vfov: 50, size: { width: 1920, height: 1166 } }
] as const;

/** The 511 bar's height for a frame size (docs/14 §14.6, "Fixes carried into the new calibrator"). */
export function barHeight(w: number, h: number): number {
	const b = h - Math.round((w * 9) / 16);
	return b >= 20 && b <= 0.1 * h ? b : Math.round(0.073 * h);
}

const M_PER_DEG_LAT = 111_320;
const offset = (lon: number, lat: number, [e, n]: readonly number[]): [number, number] => [
	lon + e / (M_PER_DEG_LAT * Math.cos((lat * Math.PI) / 180)),
	lat + n / M_PER_DEG_LAT
];

function fixtureFrame(out: string, w: number, h: number, label: string) {
	execFileSync(join(APP_DIR, 'scripts', 'fixtures.sh'), ['frame', out, String(w), String(h), label], { stdio: 'inherit' });
}

function fixtureSeries(outDir: string, w: number, h: number, label: string, count: number) {
	execFileSync(join(APP_DIR, 'scripts', 'fixtures.sh'), ['series', outDir, String(w), String(h), label, String(count)], {
		stdio: 'inherit'
	});
}

/** Key cameras from ingest/key_cameras.csv. */
function keyCameras(): { imageId: number; name: string }[] {
	const lines = readFileSync(join(REPO, 'ingest', 'key_cameras.csv'), 'utf8').trim().split('\n').slice(1);
	return lines.map((l) => {
		const [id, name] = l.split(',');
		return { imageId: Number(id), name };
	});
}

const RENDER_PAGE = `<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/node_modules/maplibre-gl/dist/maplibre-gl.css">
<style>html,body{margin:0;height:100%;overflow:hidden;background:#000}#map{position:absolute;inset:0}
.maplibregl-control-container{display:none!important}
#bar{position:absolute;left:0;right:0;bottom:0;display:none;align-items:center;padding:0 10px;background:#000;color:#fff;
font-family:"DejaVu Sans Mono",monospace;white-space:nowrap;overflow:hidden;z-index:5}</style></head>
<body><div id="map"></div><div id="bar"></div>
<script type="module">
import { createMap } from '/src/lib/map/create.ts';
window.__seed = { createMap };
</script></body></html>`;

interface Rendered {
	frame: string;
	visual: boolean;
	groundZ: number;
	pose: Pose;
	pairs: Pair[];
	registration: { maxPx: number; rmsPx: number; mapRollSign: 1 | -1 } | null;
}

/** Start the app's vite dev server in-process, for its createMap and /tiles/. */
async function startDevServer(tilesDir: string, port: number) {
	process.env.TILES_DIR = tilesDir;
	const { createServer } = await import('vite');
	const server = await createServer({
		configFile: join(APP_DIR, 'vite.config.ts'),
		root: APP_DIR,
		logLevel: 'warn',
		server: { port, strictPort: true, host: '127.0.0.1' },
		optimizeDeps: { include: ['maplibre-gl', 'pmtiles', '@protomaps/basemaps'] }
	});
	await server.listen();
	return { server, base: `http://127.0.0.1:${port}` };
}

type Page = import('@playwright/test').Page;

async function openRenderPage(page: Page, base: string) {
	await page.route('**/__seed/render', (route) => route.fulfill({ contentType: 'text/html', body: RENDER_PAGE }));
	// The first visit may optimize dependencies and reload; wait until the module is in.
	for (let attempt = 0; attempt < 4; attempt++) {
		await page.goto(`${base}/__seed/render`);
		try {
			await page.waitForFunction(() => (window as any).__seed, null, { timeout: 60_000 });
			return;
		} catch {
			/* try again */
		}
	}
	throw new Error('the render page never loaded createMap');
}

/** Create the map with Aerial on and true-scale terrain, labels hidden. Returns the ground height at a point. */
async function setupMap(page: Page, at: [number, number]): Promise<number> {
	return page.evaluate(async (at) => {
		const w = window as any;
		const { map } = await w.__seed.createMap(document.getElementById('map'), { aerial: true, center: at, zoom: 17, pitch: 0, hash: false, pad: 0.3 });
		w.__map = map;
		await new Promise((r) => map.once('load', r));
		for (const l of map.getStyle().layers) if (l.type === 'symbol') map.setLayoutProperty(l.id, 'visibility', 'none');
		map.setTerrain({ source: 'terrain', exaggeration: 1 });
		map.setMaxPitch(89);
		map.setMaxZoom(24);
		map.setCenterClampedToGround(false);
		await new Promise((r) => map.once('idle', r));
		const z = map.queryTerrainElevation(at);
		if (z === null) throw new Error('no terrain at the pole');
		return z;
	}, at);
}

/** Place the map camera at the pose and wait for every tile. */
async function placeCamera(page: Page, pose: Pose, rollSign: 1 | -1) {
	await page.evaluate(
		async ({ pose, rollSign }) => {
			const map = (window as any).__map;
			map.setVerticalFieldOfView(pose.vfov);
			const opts = map.calculateCameraOptionsFromCameraLngLatAltRotation(
				[pose.lon, pose.lat], pose.alt, pose.heading, 90 - pose.tilt, rollSign * pose.roll);
			map.jumpTo(opts);
			await new Promise((r) => map.once('idle', r));
		},
		{ pose, rollSign }
	);
}

const elevations = (page: Page, pts: [number, number][]) =>
	page.evaluate((pts) => pts.map((p) => (window as any).__map.queryTerrainElevation(p) as number), pts);

const screenPoints = (page: Page, pts: [number, number][]) =>
	page.evaluate((pts) => pts.map((p) => { const q = (window as any).__map.project(p); return [q.x, q.y]; }), pts);

/** Ground points spread over the lower image, at most 250 m away, with exact pixels (RMS 0). */
async function makePairs(page: Page, pose: Pose, size: ImageSize, groundZ: number): Promise<Pair[]> {
	const f = size.height / 2 / Math.tan(((pose.vfov / 2) * Math.PI) / 180);
	const horizon = size.height / 2 - f * Math.tan((pose.tilt * Math.PI) / 180);
	const top = Math.max(horizon + 0.12 * size.height, 0.25 * size.height);
	const bottom = size.height - barHeight(size.width, size.height) - 0.06 * size.height;
	const candidates: [number, number][] = [];
	for (const fy of [0.15, 0.5, 0.9]) {
		for (const fx of [0.15, 0.5, 0.85]) {
			const px: Pixel = [fx * size.width, top + fy * (bottom - top)];
			const g = pixelToGround(pose, size, px, groundZ);
			if (!g) continue;
			const dx = (g[0] - pose.lon) * M_PER_DEG_LAT * Math.cos((pose.lat * Math.PI) / 180);
			const dy = (g[1] - pose.lat) * M_PER_DEG_LAT;
			if (Math.hypot(dx, dy) <= 250) candidates.push([g[0], g[1]]);
		}
	}
	const zs = await elevations(page, candidates);
	const pairs: Pair[] = [];
	candidates.forEach(([lon, lat], i) => {
		const ground: [number, number, number] = [+lon.toFixed(8), +lat.toFixed(8), +zs[i].toFixed(2)];
		const pixel = project(pose, size, ground);
		if (pixel && pixel[0] >= 0 && pixel[0] <= size.width && pixel[1] >= 0 && pixel[1] <= size.height)
			pairs.push({ pixel, ground }); // exact: RMS 0
	});
	if (pairs.length < 6) throw new Error(`only ${pairs.length} usable pairs`);
	return pairs;
}

async function registration(page: Page, pairs: Pair[]) {
	const pts = await screenPoints(page, pairs.map((p) => [p.ground[0], p.ground[1]]));
	const errs = pts.map(([x, y], i) => Math.hypot(x - pairs[i].pixel[0], y - pairs[i].pixel[1]));
	return { maxPx: Math.max(...errs), rmsPx: Math.sqrt(errs.reduce((s, e) => s + e * e, 0) / errs.length) };
}

async function screenshotWithBar(page: Page, out: string, size: ImageSize, label: string) {
	const bar = barHeight(size.width, size.height);
	await page.evaluate(
		({ bar, label }) => {
			const el = document.getElementById('bar')!;
			el.style.display = 'flex';
			el.style.height = `${bar}px`;
			el.style.fontSize = `${Math.max(10, Math.round(bar * 0.5))}px`;
			el.textContent = label;
		},
		{ bar, label }
	);
	// SwiftShader takes 10–60 s for one screenshot of a full-size map.
	await page.screenshot({ path: out, type: 'jpeg', quality: 90, timeout: 300_000 });
}

async function buildTemplates(dbName: string) {
	const env = harnessEnv();
	const out = env.TVT_TEMPLATES;
	const tilesDir = env.TILES_DIR;
	const manifestFile = join(tilesDir, 'manifest.json');
	if (!existsSync(manifestFile)) throw new Error(`no basemap at ${tilesDir}: can't render seed frames`);
	const manifest = JSON.parse(readFileSync(manifestFile, 'utf8'));
	const hasImagery = Boolean(manifest.imagery && manifest.terrain);

	const postgres = (await import('postgres')).default;
	const sql = postgres(databaseUrl(dbName, mainCheckout()), { max: 2, onnotice: () => {} });

	const tmp = `${out}.building`;
	rmSync(tmp, { recursive: true, force: true });
	mkdirSync(join(tmp, 'frames', '_fixture'), { recursive: true });

	const rows = await sql`
		select v.id as view_id, v.image_id, c.id as camera_id, c.name, ST_X(c.pole_geom) as lon, ST_Y(c.pole_geom) as lat,
		       exists(select 1 from core.camera_calibration k
		              where k.view_id = v.id and upper_inf(k.valid) and k.created_by <> ${SEED_CREATED_BY}) as real_calibration
		from core.camera_view v join core.camera c on c.id = v.camera_id
		where v.image_id in ${sql(SEEDS.map((s) => s.imageId))}`;
	const byImage = new Map(rows.map((r) => [Number(r.image_id), r]));

	const { chromium } = await import('@playwright/test');
	const port = Number(env.TVT_PORT) + 300;
	const { server, base } = hasImagery ? await startDevServer(tilesDir, port) : { server: null, base: '' };
	const browser = hasImagery ? await chromium.launch({ args: [...CHROMIUM_ARGS, ...lockedArgs()] }) : null;

	const seeds: Record<string, unknown>[] = [];
	try {
		for (const s of SEEDS) {
			const r = byImage.get(s.imageId);
			if (!r) throw new Error(`image ${s.imageId} isn't in ${dbName}`);
			if (r.real_calibration) throw new Error(`view ${r.view_id} (image ${s.imageId}) has a real calibration: pick another seed`);
			const viewId = Number(r.view_id);
			const [lon, lat] = offset(r.lon, r.lat, s.offsetM);
			const rel = `view-${viewId}/seed-wp0.jpg`;
			const file = join(tmp, 'frames', rel);
			mkdirSync(join(tmp, 'frames', `view-${viewId}`), { recursive: true });
			const label = `SYNTHETIC (our map) - ${r.name} - seed ${s.kind}`;
			let rendered: Rendered;
			if (browser) {
				const page = await browser.newPage({ viewport: s.size, deviceScaleFactor: 1 });
				page.on('pageerror', (e) => console.error(`  page error: ${e.message}`));
				await openRenderPage(page, base);
				const groundZ = await setupMap(page, [lon, lat]);
				const pose: Pose = { lon, lat, alt: +(groundZ + s.height).toFixed(2), heading: s.heading, tilt: s.tilt, roll: s.roll, vfov: s.vfov };
				await placeCamera(page, pose, 1);
				const pairs = await makePairs(page, pose, s.size, groundZ);
				let rollSign: 1 | -1 = 1;
				let reg = await registration(page, pairs);
				if (s.roll !== 0 && reg.maxPx > 2) {
					// Settle the roll sign by measurement (docs/14 §14.6, "Look through", step 8).
					await placeCamera(page, pose, -1);
					const other = await registration(page, pairs);
					if (other.maxPx < reg.maxPx) {
						rollSign = -1;
						reg = other;
					} else await placeCamera(page, pose, 1);
				}
				await screenshotWithBar(page, file, s.size, label);
				await page.close();
				rendered = { frame: rel, visual: true, groundZ, pose, pairs, registration: { ...reg, mapRollSign: rollSign } };
				console.log(`seed ${s.kind}: view ${viewId}, ${pairs.length} pairs, registration max ${reg.maxPx.toFixed(2)} px (roll sign ${rollSign})`);
			} else {
				// No imagery or terrain: a test pattern, and the camera is left out of the visual check.
				fixtureFrame(file, s.size.width, s.size.height, `view ${viewId}: ${r.name} (no imagery)`);
				const groundZ = 820;
				const pose: Pose = { lon, lat, alt: groundZ + s.height, heading: s.heading, tilt: s.tilt, roll: s.roll, vfov: s.vfov };
				const pairs: Pair[] = [];
				for (const px of [[0.2, 0.7], [0.5, 0.7], [0.8, 0.7], [0.2, 0.85], [0.5, 0.85], [0.8, 0.85]] as const) {
					const g = pixelToGround(pose, s.size, [px[0] * s.size.width, px[1] * s.size.height], groundZ);
					if (g) pairs.push({ pixel: project(pose, s.size, g)!, ground: g });
				}
				rendered = { frame: rel, visual: false, groundZ, pose, pairs, registration: null };
			}
			cpSync(file, join(tmp, 'frames', '_fixture', `view-${viewId}.jpg`));
			const rms = Math.sqrt(
				rendered.pairs.reduce((acc, p) => {
					const q = project(rendered.pose, s.size, p.ground)!;
					return acc + (q[0] - p.pixel[0]) ** 2 + (q[1] - p.pixel[1]) ** 2;
				}, 0) / rendered.pairs.length
			);
			seeds.push({
				kind: s.kind, viewId, imageId: s.imageId, cameraId: Number(r.camera_id), name: r.name, size: s.size,
				pole: [r.lon, r.lat], pose: rendered.pose, groundZ: rendered.groundZ, pairs: rendered.pairs, rmsPx: rms,
				frame: rendered.frame, visual: rendered.visual, registration: rendered.registration
			});
		}
	} finally {
		await browser?.close();
		await server?.close();
	}

	// The calibrations, in one transaction: earlier seed rows for these views are replaced.
	await sql.begin(async (tx) => {
		for (const s of seeds as any[]) {
			await tx`delete from core.camera_calibration where view_id = ${s.viewId} and created_by = ${SEED_CREATED_BY}`;
			await tx`
				insert into core.camera_calibration (view_id, position, heading_deg, tilt_deg, roll_deg, vfov_deg,
				  image_width, image_height, point_pairs, rms_error_px, reference_frame, notes, created_by)
				values (${s.viewId}, ST_SetSRID(ST_MakePoint(${s.pose.lon}, ${s.pose.lat}, ${s.pose.alt}), 4326),
				  ${s.pose.heading}, ${s.pose.tilt}, ${s.pose.roll}, ${s.pose.vfov}, ${s.size.width}, ${s.size.height},
				  ${tx.json(s.pairs)}, ${s.rmsPx}, ${s.frame}, ${SEED_NOTE}, ${SEED_CREATED_BY})`;
		}
	});
	await sql.end();

	// Fixture-mode frames for views without their own.
	fixtureFrame(join(tmp, 'frames', '_fixture', 'default.jpg'), 768, 466, 'fixture frame (TVT_FRAME_SOURCE=fixture)');

	// The fake archive: 3 frames 50 s apart on the day before the build, for every key camera.
	const day0 = new Date(Date.now() - 86_400_000);
	const dayStart = new Date(`${localDay(day0)}T12:00:00-06:00`);
	const archive = join(tmp, 'archive');
	const seededKey = seeds.find((s: any) => s.kind === 'key') as any;
	const keys = keyCameras();
	for (const k of keys) {
		const hd = /I-84/.test(k.name);
		const [w, h] = hd ? [1920, 1166] : [768, 466];
		const scratch = join(tmp, 'series');
		rmSync(scratch, { recursive: true, force: true });
		const day = localDay(dayStart);
		const dir = jpegDir(archive, k.imageId, day);
		mkdirSync(dir, { recursive: true });
		const lines = [INDEX_HEADER];
		const seeded = seededKey && seededKey.imageId === k.imageId;
		if (!seeded) fixtureSeries(scratch, w, h, `image ${k.imageId}: ${k.name}`, 3);
		for (let i = 0; i < 3; i++) {
			const t = new Date(dayStart.getTime() + i * 50_000);
			const name = `${stampOf(t)}.jpg`;
			const bytes = seeded
				? withComment(readFileSync(join(tmp, 'frames', seededKey.frame)), `tvt seed archive frame ${fetchedAtOf(t)}`)
				: readFileSync(join(scratch, `frame-0${i + 1}.jpg`));
			writeFileSync(join(dir, name), bytes);
			lines.push(`${fetchedAtOf(t)},${name},${bytes.length},${createHash('sha256').update(bytes).digest('hex')}`);
		}
		writeFileSync(join(dir, INDEX), `${lines.join('\n')}\n`);
		rmSync(scratch, { recursive: true, force: true });
	}

	writeFileSync(
		join(tmp, 'seed.json'),
		JSON.stringify(
			{
				about: 'Synthetic seeds for the UI v2 packages (app/scripts/seed-dev.ts). No real camera images.',
				builtAt: new Date().toISOString(),
				database: dbName,
				tiles: { basemap: manifest.basemap?.built ?? null, imagery: manifest.imagery?.built ?? null },
				createdBy: SEED_CREATED_BY,
				seeds,
				archive: { day: localDay(dayStart), imageIds: keys.map((k) => k.imageId), framesPerImage: 3 }
			},
			null,
			2
		)
	);
	rmSync(out, { recursive: true, force: true });
	renameSync(tmp, out);
	console.log(`templates written to ${out}; ${seeds.length} calibrations seeded in ${dbName}`);
}

/** npm run seed: this package's copies of the frames and archive, with a fresh tick. */
function seedPackage(fresh: boolean) {
	const env = harnessEnv();
	const src = env.TVT_TEMPLATES;
	if (!existsSync(join(src, 'seed.json'))) throw new Error(`no templates at ${src}: WP0 builds them (seed-dev.ts templates)`);
	for (const [from, to] of [[join(src, 'frames'), env.FRAMES_DIR], [join(src, 'archive'), env.TVT_ARCHIVE]]) {
		if (fresh) rmSync(to, { recursive: true, force: true });
		mkdirSync(to, { recursive: true });
		cpSync(from, to, { recursive: true, force: true });
	}
	cpSync(join(src, 'seed.json'), join(resolve(env.FRAMES_DIR, '..'), 'seed.json'));
	const ticked = tick(env.TVT_ARCHIVE);
	console.log(`seeded ${env.FRAMES_DIR} and ${env.TVT_ARCHIVE} (${ticked.length} images ticked to now)`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
	const args = process.argv.slice(2);
	if (args[0] === 'templates') {
		const i = args.indexOf('--db');
		const db = i === -1 ? undefined : args[i + 1];
		if (!db) throw new Error('name the database to seed: --db tvt_template');
		await buildTemplates(db);
	} else {
		seedPackage(args.includes('--fresh'));
	}
}
