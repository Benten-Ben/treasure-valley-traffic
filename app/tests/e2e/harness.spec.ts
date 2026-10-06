import { execFileSync, spawn } from 'node:child_process';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { expect, env, seeds, test } from './fixtures.js';
import { imagesIn, localDay, readIndex, tick } from '../../scripts/archive-tick.ts';

/**
 * WP0's own acceptance (docs/14 §14.10, WP0): /api/meta before and after
 * migrations 0006 and 0007, fixture-mode frame capture, the Caddy-like tiles
 * server, and the seeded data every later package relies on.
 */
const APP = resolve(import.meta.dirname, '..', '..');
const REPO = resolve(APP, '..');

test.describe('harness', () => {
	test('/api/meta answers on the seeded database', { tag: '@wp0' }, async ({ request }) => {
		const res = await request.get('/api/meta');
		expect(res.status()).toBe(200);
		expect(res.headers()['cache-control']).toBe('no-cache');
		const m = await res.json();
		// Since the owner's Q4 answer (Oct 6), 0006 and 0007 live in db/migrations, so the
		// template and every clone have them: progress is available, and no ribbon build exists yet.
		const migrations = readdirSync(join(REPO, 'db', 'migrations'));
		const has0007 = migrations.some((f) => f.startsWith('0007_'));
		expect(m).toMatchObject({ contract: 1, database: 'ok', ribbons: null, progress: { available: has0007 } });
		expect(m.versions.ribbons).toBe('none');
		for (const k of ['gtfs', 'roads', 'cameras', 'calibrations', 'tiles']) expect(m.versions[k], k).toBeTruthy();
		expect(m.cameras.cameras).toBeGreaterThan(0);
		expect(m.calibrations.current).toBeGreaterThanOrEqual(4);
		expect(m.tiles.basemap).toMatch(/^\d{4}-\d{2}-\d{2}$/);
	});

	test('/api/meta answers on a scratch clone with migrations 0006 and 0007', { tag: '@wp0' }, async () => {
		test.setTimeout(300_000);
		const name = `tvt_${env().wp || 'local'}_scratch`;
		const db = (...args: string[]) => execFileSync('node', ['scripts/db.mjs', ...args], { cwd: APP, encoding: 'utf8' });
		db('drop', name);
		db('clone', name);
		const port = Number(process.env.TVT_PORT) + 100;
		let server: ReturnType<typeof spawn> | undefined;
		try {
			const migrations = readdirSync(join(REPO, 'db', 'migrations'));
			const real = ['0006_', '0007_'].every((p) => migrations.some((f) => f.startsWith(p)));
			if (real) db('migrate', name);
			else db('sql', name, 'tests/e2e/sql/0006_0007_schema.sql');
			db('sql', name, 'tests/e2e/sql/ribbon_row.sql');
			test.info().annotations.push({ type: 'schema', description: real ? 'db/migrations 0006 and 0007' : 'the §14.8 schema fixture' });

			const url = db('url', name).trim();
			server = spawn('node', ['scripts/e2e-server.mjs', '--port', String(port)], {
				cwd: APP,
				env: { ...process.env, DATABASE_URL: url, TVT_E2E_BUILD: '0' },
				stdio: 'ignore'
			});
			let meta: any = null;
			for (let i = 0; i < 120 && !meta; i++) {
				meta = await fetch(`http://127.0.0.1:${port}/api/meta`).then((r) => (r.ok ? r.json() : null), () => null);
				if (!meta) await new Promise((r) => setTimeout(r, 500));
			}
			expect(meta, 'the scratch server answered').not.toBeNull();
			expect(meta.database).toBe('ok');
			expect(meta.versions.ribbons).toBe('harness-test-build');
			expect(meta.ribbons).toEqual({ build: 'harness-test-build', segments: 1 });
			expect(meta.progress.available).toBe(true);
		} finally {
			server?.kill('SIGTERM');
			await new Promise((r) => setTimeout(r, 1000));
			db('drop', name);
		}
	});

	test('fixture mode: POST /api/views/[id]/frame saves a seeded frame', { tag: '@wp0' }, async ({ request, baseURL }) => {
		const key = seeds().seeds.find((s) => s.kind === 'key')!;
		// Same-origin, as the browser sends it (SvelteKit's CSRF check).
		const headers = { origin: new URL(baseURL!).origin };
		const res = await request.post(`/api/views/${key.viewId}/frame`, { headers });
		expect(res.status()).toBe(200);
		const body = await res.json();
		expect(body).toMatchObject({ width: key.size.width, height: key.size.height });
		expect(body.frame).toMatch(new RegExp(`^view-${key.viewId}/`));
		const img = await request.get(body.url);
		expect(img.status()).toBe(200);
		expect(img.headers()['content-type']).toBe('image/jpeg');
		// The seeded frame, byte for byte.
		expect(Buffer.compare(await img.body(), readFileSync(join(env().framesDir, '_fixture', `view-${key.viewId}.jpg`)))).toBe(0);
		// A view without its own seed gets the default fixture.
		const other = await request.post('/api/views/1/frame', { headers });
		expect(other.status()).toBe(200);
		expect(await other.json()).toMatchObject({ width: 768, height: 466 });
	});

	test('the tiles server answers like Caddy', { tag: '@wp0' }, async ({ request }) => {
		const manifest = await request.get('/tiles/manifest.json');
		expect(manifest.headers()['cache-control']).toBe('no-cache');
		const part = await request.get('/tiles/valley.pmtiles', { headers: { range: 'bytes=0-126' } });
		expect(part.status()).toBe(206);
		expect(part.headers()['cache-control']).toBe('public, max-age=3600');
		expect((await part.body()).length).toBe(127);
		expect((await part.body()).subarray(0, 7).toString()).toBe('PMTiles');
	});

	test('the seeds are in place: calibrations, frames and archive', { tag: '@wp0' }, async ({ request }) => {
		const s = seeds();
		expect(s.seeds.map((x) => x.kind).sort()).toEqual(['hd', 'key', 'low-tilt', 'roll']);
		const cal = await (await request.get('/api/calibrations')).json();
		for (const seed of s.seeds) {
			const f = cal.features.find((x: any) => x.properties.viewId === seed.viewId);
			expect(f, `calibration for seed ${seed.kind}`).toBeTruthy();
			expect(f.properties.rms).toBe(0);
			expect(f.properties.size).toEqual(seed.size);
			expect(existsSync(join(env().framesDir, seed.frame))).toBe(true);
			if (seed.visual) expect(seed.registration!.maxPx).toBeLessThan(2);
		}
		const hd = s.seeds.find((x) => x.kind === 'hd')!;
		expect(hd.size).toEqual({ width: 1920, height: 1166 });
		expect(Math.abs(s.seeds.find((x) => x.kind === 'roll')!.pose.roll)).toBe(5);
		expect(s.seeds.find((x) => x.kind === 'low-tilt')!.pose.tilt).toBeLessThan(15);

		// The fake archive: the 34 key images, ticked to today by `npm run seed`, and tickable again.
		const archive = env().archive;
		expect(imagesIn(archive)).toHaveLength(34);
		const image = s.archive.imageIds[0];
		const today = localDay(new Date());
		const dir = join(archive, 'cameras', 'jpeg', String(image), today);
		const before = existsSync(join(dir, 'index.csv')) ? readIndex(join(dir, 'index.csv')).length : 0;
		const [done] = tick(archive, [image]);
		const rows = readIndex(join(dir, 'index.csv'));
		expect(rows).toHaveLength(before + 1);
		expect(rows.at(-1)!.sha256).toBe(done.sha256);
		expect(new Set(rows.map((r) => r.sha256)).size).toBe(rows.length);
	});
});
