import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appendFile, mkdir, mkdtemp, readdir, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { GRAY_16x8, TEAL_24x8, sha, variant } from './live-fixtures.test-util.js';
import { variables } from '../../env.js';

/**
 * WP11's acceptance at the level of the server modules and routes (docs/14
 * §14.10, WP11): a temporary archive and FRAMES_DIR, a fake database with
 * three views, and a fake 511 (stubbed fetch) that counts image requests.
 */

// Views: 26 → image 656 (recorded, key), 7 → image 637 (on demand), 30 → image 9001 (road weather), 31 → no image.
const VIEWS = [
	{ id: 26, image_id: 656 },
	{ id: 7, image_id: 637 },
	{ id: 30, image_id: 9001 },
	{ id: 31, image_id: null }
];

let dir: string;
let frames: string;
let archive: string;
let imageRequests: string[];
let robotsText: string;

/** A fake 511: robots.txt, and a new picture for every image request. */
function stub511() {
	let n = 0;
	const f = vi.fn(async (url: string) => {
		if (url.endsWith('/robots.txt')) return new Response(robotsText);
		imageRequests.push(url);
		return new Response(new Uint8Array(variant(TEAL_24x8, n++)));
	});
	vi.stubGlobal('fetch', f);
	return f;
}

/** frames.ts and the routes, with this environment and a fake database. */
async function load(env: { enabled?: boolean; source?: '511' | 'fixture'; archive?: string | null } = {}) {
	vi.resetModules();
	vi.doMock('$app/env/private', () => ({
		FRAMES_DIR: frames,
		TVT_FRAME_SOURCE: env.source ?? '511',
		DATABASE_URL: 'postgres://unused',
		CAMERA_IMAGES_ENABLED: env.enabled ?? true,
		TVT_ARCHIVE: env.archive === null ? undefined : (env.archive ?? archive)
	}));
	vi.doMock('#lib/server/db.js', () => ({
		db: () => async (strings: TemplateStringsArray, ...values: unknown[]) => {
			const q = strings.join('?');
			if (/where id = \?/.test(q)) return VIEWS.filter((v) => v.id === values[0]);
			return VIEWS;
		}
	}));
	const f = await import('./frames.js');
	const routes = {
		live: await import('../../routes/api/cameras/live/+server.js'),
		status: await import('../../routes/api/cameras/status/+server.js'),
		liveFrame: await import('../../routes/api/views/[id]/live/[sha]/+server.js'),
		archiveFrame: await import('../../routes/camera-frames/[...path]/+server.js'),
		save: await import('../../routes/api/views/[id]/frame/+server.js')
	};
	return { f, routes };
}

const get = (path: string, headers: Record<string, string> = {}) => new Request(`http://localhost${path}`, { headers });
const post = (body?: unknown) =>
	new Request('http://localhost/x', { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });

async function liveJson(routes: Awaited<ReturnType<typeof load>>['routes'], views: string) {
	const res = await routes.live.GET({ url: new URL(`http://localhost/api/cameras/live?views=${views}`), setHeaders: () => {} } as never);
	return res.json();
}

async function saveArchiveFrame(image: number, day: string, stamp: string, bytes: Buffer) {
	const d = join(archive, 'cameras', 'jpeg', String(image), day);
	await mkdir(d, { recursive: true });
	await writeFile(join(d, `${stamp}.jpg`), bytes);
	const t = `${stamp.slice(0, 4)}-${stamp.slice(4, 6)}-${stamp.slice(6, 8)}T${stamp.slice(9, 11)}:${stamp.slice(11, 13)}:${stamp.slice(13, 15)}Z`;
	await appendFile(join(d, 'index.csv'), `${t},${stamp}.jpg,${bytes.length},${sha(bytes)}\r\n`);
}

const NOW = Date.parse('2026-10-06T18:00:00Z'); // 12:00 in Boise
const DAY = '2026-10-06';

beforeEach(async () => {
	vi.useFakeTimers({ now: NOW, toFake: ['Date'] });
	dir = await mkdtemp(join(tmpdir(), 'tvt-live-'));
	frames = join(dir, 'frames');
	archive = join(dir, 'archive');
	await mkdir(join(frames, '_fixture'), { recursive: true });
	await writeFile(join(frames, '_fixture', 'default.jpg'), GRAY_16x8);
	await saveArchiveFrame(656, DAY, '20261006T175900Z', GRAY_16x8);
	await saveArchiveFrame(9001, DAY, '20261006T175000Z', TEAL_24x8);
	await mkdir(join(archive, 'cameras', 'status'), { recursive: true });
	const status = (tag: string, cadence: number, ids: number[]) =>
		writeFile(
			join(archive, 'cameras', 'status', `${tag}.json`),
			JSON.stringify({ tag, cadence_s: cadence, image_ids: ids, heartbeat: NOW / 1000 - 20, paused_low_disk: false })
		);
	await status('key_cameras', 50, [656]);
	await status('regional-cameras', 600, [9001]);
	imageRequests = [];
	robotsText = 'User-agent: *\nDisallow: /list/getdata/\nDisallow: /map/map*/\n';
});

afterEach(async () => {
	const f = await import('./frames.js').catch(() => null);
	f?.resetLive();
	vi.useRealTimers();
	vi.unstubAllGlobals();
	vi.doUnmock('$app/env/private');
	vi.doUnmock('#lib/server/db.js');
	await rm(dir, { recursive: true, force: true });
});

describe('GET /api/cameras/live', () => {
	it('serves recorded views from the archive and others from the fetcher; unknown views are left out', async () => {
		stub511();
		const { routes } = await load();
		const body = await liveJson(routes, '26,7,30,31,999999');
		expect(Object.keys(body.views).sort()).toEqual(['26', '30', '31', '7']);
		expect(body.views[26]).toMatchObject({
			source: 'archive',
			state: 'ok',
			cadence: 'key',
			cadenceS: 50,
			frame: {
				url: `/camera-frames/656/${DAY}/20261006T175900Z.jpg`,
				firstSeenAt: Date.parse('2026-10-06T17:59:00Z') / 1000,
				width: 16,
				height: 8,
				sha: sha(GRAY_16x8),
				archive: { image: 656, day: DAY, stamp: '20261006T175900Z' }
			}
		});
		expect(body.views[30]).toMatchObject({ source: 'archive', cadence: 'road_weather', cadenceS: 600, state: 'ok' });
		expect(body.views[31]).toMatchObject({ source: 'none', state: 'no_image', frame: null });
		expect(body.views[7]).toMatchObject({ source: '511', cadence: 'on_demand', state: 'ok', frame: { width: 24, height: 8 } });
		expect(body.views[7].frame.url).toBe(`/api/views/7/live/${body.views[7].frame.sha}`);
		// One upstream request, for the one view that isn't recorded; none for the unknown view.
		expect(imageRequests).toEqual(['https://511.idaho.gov/map/Cctv/637']);
	});

	it('serves a new archive row at the next poll', async () => {
		stub511();
		const { routes } = await load();
		expect((await liveJson(routes, '26')).views[26].frame.archive.stamp).toBe('20261006T175900Z');
		await saveArchiveFrame(656, DAY, '20261006T175950Z', variant(GRAY_16x8, 1));
		expect((await liveJson(routes, '26')).views[26].frame.archive.stamp).toBe('20261006T175950Z');
	});

	it('reads no file for 100 requests while the views are unchanged', async () => {
		stub511();
		const { f, routes } = await load();
		await liveJson(routes, '26,30,7');
		const reads = f.archive().counts.reads;
		const upstream = imageRequests.length;
		for (let i = 0; i < 100; i++) await liveJson(routes, '26,30,7');
		expect(f.archive().counts.reads - reads).toBe(0);
		expect(imageRequests.length).toBe(upstream);
	});

	it('answers "blocked" and makes no request when robots.txt disallows the image', async () => {
		stub511();
		robotsText = '\uFEFFUser-agent: *\r\nDisallow: /map/cctv/\r\n';
		const { routes } = await load();
		const v = (await liveJson(routes, '7')).views[7];
		expect(v).toMatchObject({ source: '511', state: 'blocked', frame: null, reason: "robots.txt doesn't allow it right now" });
		expect(imageRequests).toEqual([]);
	});

	it('refuses more than 12 views and malformed lists', async () => {
		const { routes } = await load();
		const ask = (q: string) => routes.live.GET({ url: new URL(`http://localhost/api/cameras/live?${q}`), setHeaders: () => {} } as never);
		await expect(ask(`views=${Array.from({ length: 13 }, (_, i) => i + 1).join(',')}`)).rejects.toMatchObject({ status: 400 });
		await expect(ask('views=1,x')).rejects.toMatchObject({ status: 400 });
		await expect(ask('')).rejects.toMatchObject({ status: 400 });
	});

	it('writes nothing to FRAMES_DIR from the live path', async () => {
		stub511();
		const { routes } = await load();
		const before = await readdir(frames, { recursive: true });
		for (let i = 0; i < 5; i++) {
			const body = await liveJson(routes, '26,7,30');
			await routes.liveFrame.GET({ params: { id: '7', sha: body.views[7].frame.sha }, request: get('/') } as never);
			const a = body.views[26].frame.archive;
			await routes.archiveFrame.GET({ params: { path: `656/${a.day}/${a.stamp}.jpg` }, request: get('/') } as never);
			vi.setSystemTime(Date.now() + 60_000);
		}
		expect(await readdir(frames, { recursive: true })).toEqual(before);
	});

	it('uses the seeded fixture in fixture mode, without fetching', async () => {
		const f = stub511();
		const { routes } = await load({ source: 'fixture' });
		const v = (await liveJson(routes, '7')).views[7];
		expect(v).toMatchObject({ source: '511', state: 'ok', frame: { sha: sha(GRAY_16x8), width: 16 } });
		expect(f).not.toHaveBeenCalled();
	});
});

describe('frame URLs', () => {
	it('serve archive frames immutable, answer If-None-Match with 304, and 404 unknown images without reading', async () => {
		stub511();
		const { f, routes } = await load();
		const path = `656/${DAY}/20261006T175900Z.jpg`;
		const res = await routes.archiveFrame.GET({ params: { path }, request: get('/') } as never);
		expect(res.status).toBe(200);
		expect(res.headers.get('cache-control')).toBe('private, max-age=31536000, immutable');
		expect(res.headers.get('content-type')).toBe('image/jpeg');
		expect(Buffer.compare(Buffer.from(await res.arrayBuffer()), GRAY_16x8)).toBe(0);
		const etag = res.headers.get('etag')!;
		const reads = f.archive().counts.reads;
		const again = await routes.archiveFrame.GET({ params: { path }, request: get('/', { 'if-none-match': etag }) } as never);
		expect(again.status).toBe(304);
		expect(again.headers.get('etag')).toBe(etag);
		expect(f.archive().counts.reads).toBe(reads);

		const ask = (p: string) => routes.archiveFrame.GET({ params: { path: p }, request: get('/') } as never);
		await expect(ask(`999999/${DAY}/20261006T175900Z.jpg`)).rejects.toMatchObject({ status: 404 });
		await expect(ask(`656/${DAY}/20261006T000000Z.jpg`)).rejects.toMatchObject({ status: 404 });
		await expect(ask(`656/../../status/key_cameras.json`)).rejects.toMatchObject({ status: 404 });
		expect(f.archive().counts.reads).toBe(reads);
		expect(imageRequests).toEqual([]);
	});

	it('serve on-demand frames by sha with 304, only for their own view', async () => {
		stub511();
		const { routes } = await load();
		const frame = (await liveJson(routes, '7')).views[7].frame;
		const ask = (id: string, s: string, h: Record<string, string> = {}) =>
			routes.liveFrame.GET({ params: { id, sha: s }, request: get('/', h) } as never);
		const res = await ask('7', frame.sha);
		expect(res.status).toBe(200);
		expect(res.headers.get('cache-control')).toBe('private, max-age=31536000, immutable');
		expect(sha(Buffer.from(await res.arrayBuffer()))).toBe(frame.sha);
		expect((await ask('7', frame.sha, { 'if-none-match': `"${frame.sha}"` })).status).toBe(304);
		await expect(ask('26', frame.sha)).rejects.toMatchObject({ status: 404 });
		await expect(ask('999999', frame.sha)).rejects.toMatchObject({ status: 404 });
		await expect(ask('7', '0'.repeat(64))).rejects.toMatchObject({ status: 404 });
		expect(imageRequests).toHaveLength(1);
	});
});

describe('POST /api/views/[id]/frame ("Use this frame")', () => {
	const save = (routes: Awaited<ReturnType<typeof load>>['routes'], id: string, body?: unknown) =>
		routes.save.POST({ params: { id }, request: post(body) } as never);

	it('saves exactly the on-demand frame that was served, and answers 410 once it has left memory', async () => {
		stub511();
		const { f, routes } = await load();
		const frame = (await liveJson(routes, '7')).views[7].frame;
		const served = Buffer.from(
			await (await routes.liveFrame.GET({ params: { id: '7', sha: frame.sha }, request: get('/') } as never)).arrayBuffer()
		);
		const saved = await (await save(routes, '7', { sha: frame.sha })).json();
		expect(saved).toMatchObject({ width: 24, height: 8 });
		expect(saved.frame).toMatch(/^view-7\/.+\.jpg$/);
		expect(Buffer.compare(await readFile(join(frames, saved.frame)), served)).toBe(0);

		// Another view can't keep it as its own reference.
		await expect(save(routes, '26', { sha: frame.sha })).rejects.toMatchObject({ status: 400 });
		// Evicted: 64 newer pictures (one a minute) push it out of the LRU of 64.
		for (let i = 0; i < 64; i++) {
			vi.setSystemTime(Date.now() + 56_000);
			await liveJson(routes, '7');
		}
		expect(f.fetcher().frame(frame.sha)).toBeNull();
		await expect(save(routes, '7', { sha: frame.sha })).rejects.toMatchObject({ status: 410 });
		await expect(routes.liveFrame.GET({ params: { id: '7', sha: frame.sha }, request: get('/') } as never)).rejects.toMatchObject({
			status: 404
		});
	});

	it('saves exactly an archive frame, and answers 410 once it has been trimmed', async () => {
		stub511();
		const { routes } = await load();
		const ref = { image: 656, day: DAY, stamp: '20261006T175900Z' };
		const saved = await (await save(routes, '26', ref)).json();
		expect(Buffer.compare(await readFile(join(frames, saved.frame)), GRAY_16x8)).toBe(0);
		await rm(join(archive, 'cameras', 'jpeg', '656', DAY, '20261006T175900Z.jpg'));
		await expect(save(routes, '26', ref)).rejects.toMatchObject({ status: 410 });
		await expect(save(routes, '7', ref)).rejects.toMatchObject({ status: 400 }); // another camera's frame
		await expect(save(routes, '26', { image: 656, day: '../x', stamp: 'y' })).rejects.toMatchObject({ status: 400 });
		await expect(save(routes, '26', { sha: 'nope' })).rejects.toMatchObject({ status: 400 });
		expect(imageRequests).toEqual([]);
	});

	it('with no body, keeps a fresh archive frame, else asks the fetcher', async () => {
		stub511();
		const { routes } = await load();
		const fresh = await (await save(routes, '26')).json();
		expect(Buffer.compare(await readFile(join(frames, fresh.frame)), GRAY_16x8)).toBe(0);
		expect(imageRequests).toEqual([]);
		vi.setSystemTime(NOW + 5 * 60_000); // the archive frame is now 6 minutes old
		const stale = await (await save(routes, '26')).json();
		expect(stale).toMatchObject({ width: 24 });
		expect(imageRequests).toEqual(['https://511.idaho.gov/map/Cctv/656']);
	});
});

describe('GET /api/cameras/status', () => {
	it('reports each capture service and every recorded view', async () => {
		const { routes } = await load();
		const body = await (await routes.status.GET({ setHeaders: () => {} } as never)).json();
		expect(body).toMatchObject({ contract: 1, enabled: true });
		expect(body.services.map((s: { tag: string; alive: boolean }) => [s.tag, s.alive])).toEqual([
			['key_cameras', true],
			['regional-cameras', true]
		]);
		expect(body.recorded).toEqual({
			26: { tag: 'key_cameras', cadence: 'key', lastSeenAt: Date.parse('2026-10-06T17:59:00Z') / 1000 },
			30: { tag: 'regional-cameras', cadence: 'road_weather', lastSeenAt: Date.parse('2026-10-06T17:50:00Z') / 1000 }
		});
	});

	it('falls back to the archive folders when no status file names an image', async () => {
		await rm(join(archive, 'cameras', 'status'), { recursive: true });
		const { routes } = await load();
		const body = await (await routes.status.GET({ setHeaders: () => {} } as never)).json();
		expect(body.services).toEqual([]);
		expect(body.recorded[26]).toMatchObject({ tag: 'archive', cadence: 'key' });
	});
});

describe('CAMERA_IMAGES_ENABLED', () => {
	const parse = (v: string | undefined) => {
		const r = (variables.CAMERA_IMAGES_ENABLED.schema as any)['~standard'].validate(v);
		return r.issues ? 'invalid' : r.value;
	};

	it('is off unless set', () => {
		expect(parse(undefined)).toBe(false);
		expect(parse('')).toBe(false);
		expect(parse('false')).toBe(false);
		expect(parse('0')).toBe(false);
		expect(parse('true')).toBe(true);
		expect(parse('1')).toBe(true);
		expect(parse('maybe')).toBe('invalid');
	});

	it('turns every live-image route off: no file read, no request', async () => {
		const fetch = stub511();
		const { f, routes } = await load({ enabled: false });
		const body = await liveJson(routes, '26,7');
		expect(body.views[26]).toMatchObject({ state: 'disabled', source: 'none', frame: null });
		expect(body.views[7]).toMatchObject({ state: 'disabled', source: 'none', frame: null });
		const status = await (await routes.status.GET({ setHeaders: () => {} } as never)).json();
		expect(status).toMatchObject({ enabled: false, services: [], recorded: {} });
		await expect(
			routes.archiveFrame.GET({ params: { path: `656/${DAY}/20261006T175900Z.jpg` }, request: get('/') } as never)
		).rejects.toMatchObject({ status: 404 });
		await expect(routes.liveFrame.GET({ params: { id: '7', sha: 'a'.repeat(64) }, request: get('/') } as never)).rejects.toMatchObject({
			status: 404
		});
		await expect(save(routes, '26', { sha: 'a'.repeat(64) })).rejects.toMatchObject({ status: 404 });
		await expect(save(routes, '26', { image: 656, day: DAY, stamp: '20261006T175900Z' })).rejects.toMatchObject({ status: 404 });
		expect(f.archive().counts).toEqual({ stats: 0, reads: 0 });
		expect(fetch).not.toHaveBeenCalled();
		expect(await readdir(frames)).toEqual(['_fixture']);
	});

	function save(routes: Awaited<ReturnType<typeof load>>['routes'], id: string, body?: unknown) {
		return routes.save.POST({ params: { id }, request: post(body) } as never);
	}
});
