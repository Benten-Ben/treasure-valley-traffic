/**
 * Synthetic road-weather stations for the @wp16 specs (docs/14 §14.6 "Road
 * weather"; WP16), set up by the spec itself and removed after it:
 *
 * - **the database:** the real loader (`python3 -m ingest run
 *   idaho511_rwis_sites_oneoff`) reads the plugin's synthetic fixture
 *   (made-up names, ids and positions; nothing from 511's list) as if it were
 *   the private list: 3 stations, 8 views;
 * - **the archive:** ffmpeg test-pattern frames (never a camera image) for
 *   some views, at chosen ages, and a running `regional-cameras` capture
 *   status that records all of them, so the Test Summit station, which has
 *   no picture, shows 511's "no live feed" on every view and is drawn hollow.
 *
 * The road-weather spec and the review's screenshot matrix both use it
 * (`seedRoadWeather`, then `waitForSeeded`; `cleanRoadWeather` afterwards).
 *
 *   node tests/e2e/roadweather-seed.ts [--clean]   (by hand, with the package environment)
 */
import type { APIRequestContext } from '@playwright/test';
import { execFileSync, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { APP_DIR, harnessEnv, localSettings, mainCheckout } from '../../scripts/harness-env.mjs';
import { fetchedAtOf, INDEX, INDEX_HEADER, localDay, stampOf, withComment } from '../../scripts/archive-tick.ts';

const REPO = resolve(APP_DIR, '..');
export const FIXTURE = join(REPO, 'plugins', 'cameras', 'tests', 'fixtures', 'rwis_sites_sample.json');
export const SOURCE = 'idaho511_rwis_sites_oneoff';
const LIST_NAME = '511-camera-sites-statewide-2026-10-05.json';
export const STATUS_TAG = 'regional-cameras';

/** The fixture's stations, as the specs expect them. */
export const STATIONS = {
	grade: { name: 'Example Grade (synthetic)', images: [990011, 990012, 990013, 990014], labels: ['Looking East', 'Looking West', 'Pavement', 'View 4'] },
	summit: { name: 'Test Summit (synthetic)', images: [990021, 990022], labels: ['View 1', 'View 2'] },
	bridge: { name: 'Sample Bridge OR (synthetic)', images: [990031, 990032], labels: ['Northbound', 'Southbound'] }
} as const;
export const IMAGES = Object.values(STATIONS).flatMap((s) => [...s.images]);

/**
 * Seeded pictures: image → minutes old (live within 30, late within 60, stale after; §14.6).
 * 990014 and 990032 are disabled in the list; Test Summit has none.
 */
export const AGES_MIN: Record<number, number> = { 990011: 4, 990012: 40, 990013: 70, 990031: 8 };

const python = () => process.env.TVT_PYTHON || localSettings(mainCheckout()).TVT_PYTHON || 'python3';

/** A labeled 800 × 486 test pattern (fixtures.sh), or the seeded fixture frame with a comment when ffmpeg can't draw text. */
function syntheticFrame(label: string, framesDir: string): Buffer {
	const out = join(mkdtempSync(join(tmpdir(), 'tvt-rw-')), 'frame.jpg');
	try {
		execFileSync(join(APP_DIR, 'scripts', 'fixtures.sh'), ['frame', out, '800', '486', label], { stdio: 'ignore' });
		return readFileSync(out);
	} catch {
		return withComment(readFileSync(join(framesDir, '_fixture', 'default.jpg')), `tvt synthetic road-weather frame: ${label}`);
	} finally {
		rmSync(resolve(out, '..'), { recursive: true, force: true });
	}
}

/** Load the stations (the real loader on the synthetic list) and write their pictures and capture status. */
export function seedRoadWeather(env = harnessEnv(), nowMs = Date.now()): { loaded: string } {
	const priv = mkdtempSync(join(tmpdir(), 'tvt-rw-private-'));
	try {
		cpSync(FIXTURE, join(priv, LIST_NAME));
		const r = spawnSync(python(), ['-m', 'ingest', 'run', SOURCE], {
			cwd: REPO,
			env: { ...process.env, DATABASE_URL: env.DATABASE_URL, TVT_PRIVATE_DATA: priv },
			encoding: 'utf8'
		});
		if (r.status !== 0) throw new Error(`the road-weather loader failed (${python()}):\n${r.stderr || r.stdout || r.error}`);
		const loaded = r.stdout.trim();

		const archive = env.TVT_ARCHIVE;
		for (const image of IMAGES) rmSync(join(archive, 'cameras', 'jpeg', String(image)), { recursive: true, force: true });
		for (const [image, min] of Object.entries(AGES_MIN)) {
			const at = new Date(Math.floor((nowMs - min * 60_000) / 1000) * 1000);
			const station = Object.values(STATIONS).find((s) => (s.images as readonly number[]).includes(Number(image)))!;
			const label = station.labels[(station.images as readonly number[]).indexOf(Number(image))];
			const bytes = syntheticFrame(`${station.name.replace(/ \(synthetic\)$/, '')} - ${label}`, env.FRAMES_DIR);
			const dir = join(archive, 'cameras', 'jpeg', image, localDay(at));
			mkdirSync(dir, { recursive: true });
			const file = `${stampOf(at)}.jpg`;
			writeFileSync(join(dir, file), bytes);
			const sha = createHash('sha256').update(bytes).digest('hex');
			writeFileSync(join(dir, INDEX), `${INDEX_HEADER}\n${fetchedAtOf(at)},${file},${bytes.length},${sha}\n`);
		}
		mkdirSync(join(archive, 'cameras', 'status'), { recursive: true });
		writeFileSync(
			join(archive, 'cameras', 'status', `${STATUS_TAG}.json`),
			JSON.stringify({ version: 1, tag: STATUS_TAG, cadence_s: 600, image_ids: IMAGES, heartbeat: nowMs / 1000, paused_low_disk: false, rolling_up: false })
		);
		return { loaded };
	} finally {
		rmSync(priv, { recursive: true, force: true });
	}
}

export type SeededView = { id: number; imageId: number | null; label: string; disabled: boolean; ageS: number | null; capturing: boolean; feed: string };
export type SeededStation = { id: number; name: string; hollow: boolean; views: SeededView[] };

/**
 * Wait until the app serves the seeded stations as seeded: all three, with the
 * seeded capture status (the archive keeps its list of capture services for
 * 15 s, so right after another spec had Road weather on, the stations can come
 * back before the server reads the new status), and every view's picture
 * through /api/cameras/live (which keeps its view list for a minute).
 */
export async function waitForSeeded(request: APIRequestContext, timeoutMs = 150_000): Promise<SeededStation[]> {
	const names: string[] = Object.values(STATIONS).map((s) => s.name);
	const until = Date.now() + timeoutMs;
	const pause = (ms: number) => new Promise((r) => setTimeout(r, ms));
	let stations: SeededStation[] = [];
	for (;;) {
		const rw = await (await request.get('/api/roadweather')).json();
		stations = (rw.stations as SeededStation[]).filter((s) => names.includes(s.name));
		const seen = stations.flatMap((s) => s.views).filter((v) => v.imageId !== null);
		if (stations.length === 3 && seen.length > 0 && seen.every((v) => v.capturing)) break;
		if (Date.now() > until) throw new Error(`the app serves ${stations.length} of the 3 seeded stations, or not their capture status yet`);
		await pause(1000);
	}
	const ids = stations.flatMap((s) => s.views.map((v) => v.id));
	for (;;) {
		const live = await (await request.get(`/api/cameras/live?views=${ids.join(',')}`)).json();
		const n = Object.values(live.views as Record<string, { cadence: string }>).filter((v) => v.cadence === 'road_weather').length;
		if (n === ids.length) return stations;
		if (Date.now() > until) throw new Error(`/api/cameras/live serves ${n} of the ${ids.length} seeded views`);
		await pause(2000);
	}
}

/** Remove the stations, their pictures and the capture status again. */
export async function cleanRoadWeather(env = harnessEnv()): Promise<void> {
	const archive = env.TVT_ARCHIVE;
	for (const image of IMAGES) rmSync(join(archive, 'cameras', 'jpeg', String(image)), { recursive: true, force: true });
	rmSync(join(archive, 'cameras', 'status', `${STATUS_TAG}.json`), { force: true });
	const postgres = (await import('postgres')).default;
	const sql = postgres(env.DATABASE_URL, { max: 1, onnotice: () => {} });
	try {
		await sql.begin(async (tx) => {
			const cams = await tx`select entity_id from core.source_link where source = ${SOURCE} and entity = 'camera'`;
			const ids = cams.map((c) => Number(c.entity_id));
			await tx`delete from core.camera_view where source = ${SOURCE}`;
			await tx`delete from core.source_link where source = ${SOURCE}`;
			if (ids.length) await tx`delete from core.camera where id in ${tx(ids)}`;
			await tx`delete from raw.record where source = ${SOURCE}`;
		});
	} finally {
		await sql.end();
	}
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
	const env = harnessEnv();
	if (process.argv.includes('--clean')) {
		await cleanRoadWeather(env);
		console.log('road-weather seed removed');
	} else {
		if (!existsSync(join(env.FRAMES_DIR, '_fixture'))) throw new Error('run npm run seed first');
		console.log(seedRoadWeather(env).loaded);
	}
}
