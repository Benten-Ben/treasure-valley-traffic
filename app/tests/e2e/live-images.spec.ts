import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { expect, env, screenPath, seeds, test } from './fixtures.js';
import { tick } from '../../scripts/archive-tick.ts';

/**
 * WP11, the live images server (docs/14 §14.6 "Live images", §14.10 WP11),
 * against the package's preview server in fixture mode: its own fake archive
 * (ticked by archive-tick), seeded fixture frames standing in for 511, and
 * CAMERA_IMAGES_ENABLED=true. Nothing here reaches 511: the server's on-demand
 * fetcher reads the seeded fixtures, and the browser resolves only localhost.
 */
const APP = resolve(import.meta.dirname, '..', '..');

const files = (dir: string) => (existsSync(dir) ? readdirSync(dir, { recursive: true }).map(String).sort() : []);

/** The seeds that the capture archive records (key cameras) and those fetched on demand. */
function seedViews() {
	const s = seeds();
	const recorded = new Set(s.archive.imageIds);
	const key = s.seeds.find((x) => x.kind === 'key')!;
	const onDemand = s.seeds.filter((x) => !recorded.has(x.imageId));
	expect(recorded.has(key.imageId), 'the key seed is a recorded camera').toBe(true);
	expect(onDemand.length, 'seeds that are fetched on demand').toBeGreaterThanOrEqual(2);
	return { key, onDemand, recorded };
}

test.describe('live images server', () => {
	test('archive frames: newest frame, a new index row served within 1 s, 304 on If-None-Match', { tag: '@wp11' }, async ({ request }) => {
		const { key } = seedViews();
		const live = async () => (await request.get(`/api/cameras/live?views=${key.viewId}`)).json();
		const res = await request.get(`/api/cameras/live?views=${key.viewId}`);
		expect(res.status()).toBe(200);
		expect(res.headers()['cache-control']).toBe('no-store');
		const before = (await res.json()).views[key.viewId];
		expect(before).toMatchObject({ viewId: key.viewId, imageId: key.imageId, source: 'archive', cadence: 'key', state: 'ok' });
		expect(before.frame.url).toMatch(new RegExp(`^/camera-frames/${key.imageId}/\\d{4}-\\d{2}-\\d{2}/\\d{8}T\\d{6}Z\\.jpg$`));
		expect(before.frame).toMatchObject({ width: key.size.width, height: key.size.height, archive: { image: key.imageId } });

		// A new row, as the capture service would append it, is served at the next poll, within 1 s.
		const [ticked] = tick(env().archive, [key.imageId]);
		const t0 = Date.now();
		let after = before;
		while (after.frame.archive.stamp !== ticked.stamp && Date.now() - t0 < 5_000) after = (await live()).views[key.viewId];
		const ms = Date.now() - t0;
		test.info().annotations.push({ type: 'new row served after', description: `${ms} ms` });
		expect(after.frame.archive.stamp).toBe(ticked.stamp);
		expect(after.frame.sha).toBe(ticked.sha256);
		expect(ms).toBeLessThan(1_000);
		expect(Math.abs(after.frame.firstSeenAt * 1000 - Date.now())).toBeLessThan(10_000);

		// The frame URL: the archive's bytes, cached for a year, and 304 for If-None-Match.
		const img = await request.get(after.frame.url);
		expect(img.status()).toBe(200);
		expect(img.headers()['content-type']).toBe('image/jpeg');
		expect(img.headers()['cache-control']).toBe('private, max-age=31536000, immutable');
		expect(Buffer.compare(await img.body(), readFileSync(ticked.file))).toBe(0);
		const etag = img.headers()['etag'];
		expect(etag).toBeTruthy();
		const again = await request.get(after.frame.url, { headers: { 'if-none-match': etag } });
		expect(again.status()).toBe(304);
	});

	test('on-demand frames come from the fixture fetcher, repeat the same picture, and write nothing to FRAMES_DIR', { tag: '@wp11' }, async ({ request, page, offsite }) => {
		const { key, onDemand } = seedViews();
		const framesBefore = files(env().framesDir);
		const ids = onDemand.map((s) => s.viewId);
		const first = (await (await request.get(`/api/cameras/live?views=${[key.viewId, ...ids].join(',')}`)).json()).views;
		for (const s of onDemand) {
			const v = first[s.viewId];
			expect(v, `view ${s.viewId}`).toMatchObject({ imageId: s.imageId, source: '511', cadence: 'on_demand', state: 'ok' });
			expect(v.frame.url).toBe(`/api/views/${s.viewId}/live/${v.frame.sha}`);
			const img = await request.get(v.frame.url);
			expect(img.status()).toBe(200);
			expect(img.headers()['cache-control']).toBe('private, max-age=31536000, immutable');
			// The seeded fixture, byte for byte: in fixture mode nothing is fetched from 511.
			expect(Buffer.compare(await img.body(), readFileSync(join(env().framesDir, '_fixture', `view-${s.viewId}.jpg`)))).toBe(0);
			expect((await request.get(v.frame.url, { headers: { 'if-none-match': img.headers()['etag'] } })).status()).toBe(304);
		}
		// Polling again: the same picture keeps its first seen time (repeats are dropped).
		const second = (await (await request.get(`/api/cameras/live?views=${ids.join(',')}`)).json()).views;
		for (const s of onDemand) {
			expect(second[s.viewId].frame.sha).toBe(first[s.viewId].frame.sha);
			expect(second[s.viewId].frame.firstSeenAt).toBe(first[s.viewId].frame.firstSeenAt);
		}
		expect(files(env().framesDir)).toEqual(framesBefore);

		// Evidence: the JSON and the two kinds of frame URL, in the browser.
		mkdirSync(env().screens, { recursive: true });
		await page.goto(`/api/cameras/live?views=${[key.viewId, ...ids].join(',')}`);
		await page.screenshot({ path: screenPath('live-json.png') });
		const a = first[key.viewId].frame;
		const b = first[onDemand[0].viewId].frame;
		await page.setContent(
			`<body style="margin:0;background:#f4efe6;font:14px sans-serif">` +
				`<figure style="display:inline-block;margin:8px"><img src="${a.url}" width="480"><figcaption>archive: ${a.url}</figcaption></figure>` +
				`<figure style="display:inline-block;margin:8px"><img src="${b.url}" width="480"><figcaption>on demand (fixture): ${b.url.slice(0, 40)}…</figcaption></figure></body>`,
			{ waitUntil: 'load' }
		);
		await page.screenshot({ path: screenPath('frames.png') });
		expect(offsite).toEqual([]);
	});

	test('"Use this frame" keeps exactly the bytes served, and answers 410 when they are gone', { tag: '@wp11' }, async ({ request, baseURL }) => {
		const { key, onDemand } = seedViews();
		const headers = { origin: new URL(baseURL!).origin, 'content-type': 'application/json' };
		const s = onDemand[0];
		const live = (await (await request.get(`/api/cameras/live?views=${key.viewId},${s.viewId}`)).json()).views;

		// An on-demand frame, by sha.
		const served = await (await request.get(live[s.viewId].frame.url)).body();
		const bySha = await request.post(`/api/views/${s.viewId}/frame`, { headers, data: { sha: live[s.viewId].frame.sha } });
		expect(bySha.status()).toBe(200);
		const savedSha = await bySha.json();
		expect(savedSha).toMatchObject({ width: s.size.width, height: s.size.height });
		expect(Buffer.compare(await (await request.get(savedSha.url)).body(), served)).toBe(0);

		// An archive frame, by image, day and stamp.
		const ref = live[key.viewId].frame.archive;
		const archived = await (await request.get(live[key.viewId].frame.url)).body();
		const byRef = await request.post(`/api/views/${key.viewId}/frame`, { headers, data: ref });
		expect(byRef.status()).toBe(200);
		expect(Buffer.compare(await (await request.get((await byRef.json()).url)).body(), archived)).toBe(0);

		// Gone: a sha that isn't in memory, a stamp that isn't in the archive.
		expect((await request.post(`/api/views/${s.viewId}/frame`, { headers, data: { sha: '0'.repeat(64) } })).status()).toBe(410);
		expect(
			(await request.post(`/api/views/${key.viewId}/frame`, { headers, data: { ...ref, stamp: '20000101T000000Z' } })).status()
		).toBe(410);
		// Another camera's frame, and nonsense.
		expect((await request.post(`/api/views/${s.viewId}/frame`, { headers, data: ref })).status()).toBe(400);
		expect((await request.post(`/api/views/${s.viewId}/frame`, { headers, data: { sha: 'x' } })).status()).toBe(400);
	});

	test('status reports the capture services and the recorded views', { tag: '@wp11' }, async ({ request }) => {
		const { key, recorded } = seedViews();
		const dir = join(env().archive, 'cameras', 'status');
		const file = join(dir, 'key_cameras.json');
		mkdirSync(dir, { recursive: true });
		// What ingest/sources/idaho511_frames.py writes each cycle.
		writeFileSync(
			file,
			JSON.stringify({ version: 1, tag: 'key_cameras', cadence_s: 50, image_ids: [...recorded], heartbeat: Date.now() / 1000, paused_low_disk: false, rolling_up: false })
		);
		try {
			let body: any = null;
			// The status is reused for 15 s, so an earlier answer may still be current.
			for (const t0 = Date.now(); Date.now() - t0 < 20_000; await new Promise((r) => setTimeout(r, 500))) {
				body = await (await request.get('/api/cameras/status')).json();
				if (body.services.length) break;
			}
			expect(body).toMatchObject({ contract: 1, enabled: true });
			expect(body.services).toEqual([
				{ tag: 'key_cameras', cadenceS: 50, imageIds: [...recorded], heartbeat: expect.any(Number), pausedLowDisk: false, alive: true }
			]);
			expect(body.recorded[key.viewId]).toMatchObject({ tag: 'key_cameras', cadence: 'key' });
			expect(Math.abs(body.recorded[key.viewId].lastSeenAt * 1000 - Date.now())).toBeLessThan(10 * 60_000);
			// Every key camera with a view is listed; nothing fetched on demand is.
			expect(Object.keys(body.recorded).length).toBeGreaterThanOrEqual(20);
			for (const s of seedViews().onDemand) expect(body.recorded[s.viewId]).toBeUndefined();
		} finally {
			rmSync(file, { force: true });
		}
	});

	test('requests are checked: at most 12 views, and unknown views or images give nothing', { tag: '@wp11' }, async ({ request }) => {
		const { key } = seedViews();
		const many = Array.from({ length: 13 }, (_, i) => i + 1).join(',');
		expect((await request.get(`/api/cameras/live?views=${many}`)).status()).toBe(400);
		expect((await request.get('/api/cameras/live?views=1,abc')).status()).toBe(400);
		expect((await request.get('/api/cameras/live')).status()).toBe(400);
		const body = await (await request.get(`/api/cameras/live?views=${key.viewId},999999`)).json();
		expect(Object.keys(body.views)).toEqual([String(key.viewId)]);
		const day = body.views[key.viewId].frame.archive.day;
		expect((await request.get(`/camera-frames/999999/${day}/20261006T000000Z.jpg`)).status()).toBe(404);
		expect((await request.get(`/camera-frames/${key.imageId}/${day}/index.csv`)).status()).toBe(404);
		expect((await request.get(`/camera-frames/${key.imageId}/..%2F..%2Fstatus/x.jpg`)).status()).toBe(404);
		expect((await request.get(`/api/views/999999/live/${'a'.repeat(64)}`)).status()).toBe(404);
		expect((await request.get(`/api/views/${key.viewId}/live/${'a'.repeat(64)}`)).status()).toBe(404);
	});

	test('CAMERA_IMAGES_ENABLED=false turns every live-image route off', { tag: '@wp11' }, async ({ baseURL }) => {
		test.setTimeout(300_000);
		const { key, onDemand } = seedViews();
		// Not +100: the harness spec's scratch server uses that one.
		const port = Number(process.env.TVT_PORT) + 150;
		const base = `http://127.0.0.1:${port}`;
		const server = spawn('node', ['scripts/e2e-server.mjs', '--port', String(port)], {
			cwd: APP,
			env: { ...process.env, CAMERA_IMAGES_ENABLED: 'false', TVT_E2E_BUILD: '0' },
			stdio: 'ignore'
		});
		try {
			let up = false;
			for (let i = 0; i < 240 && !up; i++) {
				up = await fetch(`${base}/api/health`).then((r) => r.ok, () => false);
				if (!up) await new Promise((r) => setTimeout(r, 500));
			}
			expect(up, 'the second server answered').toBe(true);
			const s = onDemand[0];
			const live = await (await fetch(`${base}/api/cameras/live?views=${key.viewId},${s.viewId}`)).json();
			for (const id of [key.viewId, s.viewId]) expect(live.views[id]).toMatchObject({ state: 'disabled', source: 'none', frame: null });
			expect(await (await fetch(`${base}/api/cameras/status`)).json()).toMatchObject({ enabled: false, services: [], recorded: {} });
			// The frame URLs the enabled server hands out answer 404 here.
			const on = (await (await fetch(`${baseURL}/api/cameras/live?views=${key.viewId},${s.viewId}`)).json()).views;
			expect((await fetch(`${base}${on[key.viewId].frame.url}`)).status).toBe(404);
			expect((await fetch(`${base}${on[s.viewId].frame.url}`)).status).toBe(404);
			const post = (id: number, body?: unknown) =>
				fetch(`${base}/api/views/${id}/frame`, {
					method: 'POST',
					headers: { origin: base, 'content-type': 'application/json' },
					body: body === undefined ? undefined : JSON.stringify(body)
				});
			expect((await post(s.viewId, { sha: on[s.viewId].frame.sha })).status).toBe(404);
			expect((await post(key.viewId, on[key.viewId].frame.archive)).status).toBe(404);
			// No body: today's calibrator capture still works (the seeded fixture in fixture mode).
			const plain = await post(key.viewId);
			expect(plain.status).toBe(200);
			expect(await plain.json()).toMatchObject({ width: key.size.width, height: key.size.height });
		} finally {
			server.kill('SIGTERM');
			await new Promise((r) => setTimeout(r, 1000));
		}
	});
});
