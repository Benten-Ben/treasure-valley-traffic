import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { project, type Pose } from '#lib/calibration/solver.js';

/**
 * POST /api/views/[id]/calibrations (WP14): checks the body, recomputes the
 * error, closes the previous row and inserts the new one in one transaction.
 * The database is a fake that records its statements.
 */
let dir: string;
let statements: { text: string; values: unknown[] }[];
let viewRows: { camera_id: number }[];

const pose: Pose = { lon: -116.3, lat: 43.6, alt: 812, heading: 30, tilt: 20, roll: 0, vfov: 40 };
const size = { width: 768, height: 466 };
/** Four ground points in front of the camera, with their exact pixels. */
const pairs = [
	[-116.29985, 43.60025],
	[-116.29955, 43.60015],
	[-116.29975, 43.60045],
	[-116.2994, 43.6004]
].map(([lon, lat]) => {
	const ground: [number, number, number] = [lon, lat, 800];
	return { pixel: project(pose, size, ground)!, ground };
});

async function load() {
	vi.resetModules();
	vi.doMock('$app/env/private', () => ({
		FRAMES_DIR: dir,
		TVT_FRAME_SOURCE: 'fixture',
		DATABASE_URL: 'postgres://unused',
		CAMERA_IMAGES_ENABLED: false,
		TVT_ARCHIVE: undefined
	}));
	const run = (strings: TemplateStringsArray, ...values: unknown[]) => {
		const text = strings.join('?');
		statements.push({ text, values });
		if (text.includes('from core.camera_view')) return Promise.resolve(viewRows);
		if (text.includes('insert into')) return Promise.resolve([{ id: 77 }]);
		return Promise.resolve([]);
	};
	const tx = Object.assign(run, { json: (v: unknown) => ({ json: v }) });
	const sql = Object.assign(run, { begin: async (fn: (t: typeof tx) => Promise<unknown>) => fn(tx) });
	vi.doMock('#lib/server/db.js', () => ({ db: () => sql }));
	const route = await import('./+server.js');
	return (id: string, body: unknown) =>
		route.POST({
			params: { id },
			request: new Request('http://x/', { method: 'POST', body: typeof body === 'string' ? body : JSON.stringify(body) })
		} as never);
}

/** The status a handler answered or threw with (SvelteKit's error() throws an HttpError). */
async function status(p: Promise<Response>): Promise<number> {
	try {
		return (await p).status;
	} catch (e) {
		return (e as { status?: number }).status ?? 500;
	}
}

beforeEach(async () => {
	dir = await mkdtemp(join(tmpdir(), 'tvt-cal-'));
	await mkdir(join(dir, 'view-5'), { recursive: true });
	await writeFile(join(dir, 'view-5', 'ref.jpg'), 'x');
	statements = [];
	viewRows = [{ camera_id: 9 }];
});

afterEach(async () => {
	vi.doUnmock('$app/env/private');
	vi.doUnmock('#lib/server/db.js');
	await rm(dir, { recursive: true, force: true });
});

const good = { pose, pairs, imageWidth: 768, imageHeight: 466, frame: 'view-5/ref.jpg' };

describe('POST /api/views/[id]/calibrations', () => {
	it('closes the current row and inserts the new one, with the error recomputed', async () => {
		const post = await load();
		const res = await post('5', { ...good, rms: 999 });
		expect(res.status).toBe(200);
		const body = await res.json();
		expect(body).toMatchObject({ id: 77, viewId: 5, cameraId: 9 });
		expect(body.rms).toBeLessThan(1e-6);
		const [check, close, insert] = statements;
		expect(check.text).toContain('from core.camera_view');
		expect(close.text).toMatch(/update core\.camera_calibration set valid/);
		expect(insert.text).toMatch(/insert into core\.camera_calibration/);
		expect(insert.values).toContain('view-5/ref.jpg');
		// Only pixels and ground points go into the row.
		const stored = insert.values.find((v) => (v as { json?: unknown })?.json) as { json: unknown[] };
		expect(stored.json).toEqual(pairs.map((p) => ({ pixel: [...p.pixel], ground: [...p.ground] })));
	});

	it('refuses a bad body before touching the database', async () => {
		const post = await load();
		expect(await status(post('5', '{nope'))).toBe(400);
		expect(await status(post('x', good))).toBe(400);
		expect(await status(post('5', { ...good, pose: { ...pose, vfov: undefined } }))).toBe(400);
		expect(await status(post('5', { ...good, pose: { ...pose, vfov: 200 } }))).toBe(400);
		expect(await status(post('5', { ...good, pairs: pairs.slice(0, 3) }))).toBe(400);
		expect(await status(post('5', { ...good, pairs: [...pairs.slice(0, 3), { pixel: [1], ground: [0, 0, 0] }] }))).toBe(400);
		expect(await status(post('5', { ...good, pairs: Array.from({ length: 201 }, () => pairs[0]) }))).toBe(400);
		expect(await status(post('5', { ...good, imageWidth: 0 }))).toBe(400);
		expect(await status(post('5', { ...good, frame: 'view-5/missing.jpg' }))).toBe(400);
		expect(await status(post('5', { ...good, frame: '../../etc/passwd' }))).toBe(400);
		// A pose that puts the points behind the camera.
		expect(await status(post('5', { ...good, pose: { ...pose, heading: 210 } }))).toBe(400);
		expect(statements).toEqual([]);
	});

	it('answers 404 for an unknown view, writing nothing', async () => {
		viewRows = [];
		const post = await load();
		expect(await status(post('5', good))).toBe(404);
		expect(statements.map((s) => s.text).some((t) => /update|insert/.test(t))).toBe(false);
	});
});
