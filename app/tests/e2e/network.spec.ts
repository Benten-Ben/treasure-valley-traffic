import { execFileSync, spawn } from 'node:child_process';
import { mkdirSync, openSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { gzipSync } from 'node:zlib';
import { expect, screenPath, test } from './fixtures.js';
import type { TransitNetwork } from '#lib/contracts/network.js';

/**
 * WP6's acceptance for GET /api/transit/network (docs/14 §14.10 WP6, §14.4,
 * §14.8 "APIs"): the plain-shapes answer before any ribbon build, then the
 * build's answer, its size and its caching. Runs on its own scratch clone
 * (tvt_<wp>_net) with its own server, so the package clone stays as seeded.
 */
const APP = resolve(import.meta.dirname, '..', '..');
const REPO = resolve(APP, '..');
const LIMIT_GZIP = 60 * 1024;
// docs/14 §14.4: the 13 slots, and the ones whose badge numerals need a halo.
const PALETTE = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948', '#99095c',
	'#a791fa', '#7f4315', '#9059af', '#8cc63f'];
const HALO = new Set(['#2a78d6', '#eb6834', '#e34948', '#8a857c']);

/** Everything in the answer that breaks the contract (an empty list when it's sound). */
function contractProblems(net: TransitNetwork): string[] {
	const bad: string[] = [];
	const check = (ok: boolean, what: string) => {
		if (!ok && bad.length < 20) bad.push(what);
	};
	check(net.contract === 1, 'contract 1');
	const ids = new Set(net.routes.map((r) => r.id));
	check(ids.size === net.routes.length, 'route ids unique');
	net.routes.forEach((r, i) => {
		check(r.rid === i + 1, `route ${r.id} rid ${r.rid}`);
		check(/^#[0-9a-f]{6}$/.test(r.color) && /^#[0-9a-f]{6}$/.test(r.ghost), `route ${r.id} colors`);
		check(r.textColor === '#ffffff' || r.textColor === '#2b2a33', `route ${r.id} text color`);
		check(r.halo === HALO.has(r.color), `route ${r.shortName} (${r.color}) halo ${r.halo}`);
	});
	const segs = new Map(net.segments.map((s) => [s.id, s]));
	check(segs.size === net.segments.length, 'segment ids unique');
	for (const s of net.segments) {
		check(s.routes.length > 0 && new Set(s.routes).size === s.routes.length, `segment ${s.id} routes`);
		check(s.routes.every((r) => ids.has(r)), `segment ${s.id} names an unknown route`);
		check(s.coords.length % 2 === 0 && s.coords.length >= 4, `segment ${s.id} coords`);
		check(s.coords.every((v) => Math.abs(v * 1e6 - Math.round(v * 1e6)) < 1e-3), `segment ${s.id} decimals`);
	}
	for (const st of net.stops) {
		if (st.segment === null) continue;
		const seg = segs.get(st.segment);
		check(seg !== undefined && st.n === seg.routes.length, `stop ${st.id} on segment ${st.segment} with n ${st.n}`);
		check(st.bearing !== null && st.bearing >= -180 && st.bearing <= 360, `stop ${st.id} bearing`);
	}
	for (const d of net.dormant) check(ids.has(d.routeId), `dormant ${d.routeId}`);
	return bad;
}

const checkContract = (net: TransitNetwork) => expect(contractProblems(net)).toEqual([]);

test.describe('transit network', () => {
	test('plain shapes until the first ribbon build, then the build: contract, size and caching', { tag: '@wp6' }, async () => {
		test.setTimeout(600_000);
		const name = `tvt_${process.env.TVT_WP || 'local'}_net`;
		const db = (...args: string[]) => execFileSync('node', ['scripts/db.mjs', ...args], { cwd: APP, encoding: 'utf8' });
		db('drop', name);
		db('clone', name);
		const port = Number(process.env.TVT_PORT) + 110;
		const base = `http://127.0.0.1:${port}`;
		let server: ReturnType<typeof spawn> | undefined;
		const evidence: Record<string, unknown> = {};
		try {
			db('migrate', name);
			const url = db('url', name).trim();
			// Its output goes to data/dev/<wp>/network-server.log, for when something fails.
			const logDir = resolve(process.env.TVT_MAIN ?? REPO, 'data', 'dev', process.env.TVT_WP || 'local');
			mkdirSync(logDir, { recursive: true });
			const log = openSync(resolve(logDir, 'network-server.log'), 'w');
			server = spawn('node', ['scripts/e2e-server.mjs', '--port', String(port)], {
				cwd: APP,
				env: { ...process.env, DATABASE_URL: url, TVT_E2E_BUILD: '0' },
				stdio: ['ignore', log, log]
			});
			let meta: any = null;
			for (let i = 0; i < 120 && !meta; i++) {
				meta = await fetch(`${base}/api/meta`).then((r) => (r.ok ? r.json() : null), () => null);
				if (!meta) await new Promise((r) => setTimeout(r, 500));
			}
			expect(meta?.database, 'the scratch server answered').toBe('ok');
			expect(meta.versions.ribbons).toBe('none');

			// 1. No build yet: each route's plain shapes, one route per segment, never immutable.
			let res = await fetch(`${base}/api/transit/network?v=none`);
			expect(res.status).toBe(200);
			expect(res.headers.get('cache-control')).toBe('no-cache');
			let body = await res.text();
			const plain: TransitNetwork = JSON.parse(body);
			checkContract(plain);
			expect(plain).toMatchObject({ build: 'none', bundled: false, feedVersion: meta.gtfs.feedVersion, dormant: [] });
			expect(plain.routes.length).toBe(meta.gtfs.routes);
			expect(plain.segments.every((s) => s.routes.length === 1)).toBe(true);
			expect(new Set(plain.segments.flatMap((s) => s.routes))).toEqual(new Set(plain.routes.map((r) => r.id)));
			expect(plain.stops.every((s) => s.n === 1)).toBe(true);
			evidence.plain = { bytes: body.length, gzip: gzipSync(body).length, segments: plain.segments.length };
			expect(gzipSync(body).length).toBeLessThanOrEqual(LIMIT_GZIP);

			// 2. Build the ribbons the way vrt_gtfs's daily run does.
			const out = execFileSync('python3', ['-m', 'ingest.transit_ribbons'], {
				cwd: REPO,
				env: { ...process.env, DATABASE_URL: url },
				encoding: 'utf8',
				timeout: 120_000
			});
			expect(out).toMatch(/ribbons built/);
			const seconds = Number(/seconds ([\d.]+)/.exec(out)?.[1]);
			expect(seconds).toBeLessThanOrEqual(30);
			evidence.build = out.trim().split('\n').at(-1);

			// /api/meta is memoized for 15 s: wait for it to report the build.
			for (let i = 0; i < 40 && meta.versions.ribbons === 'none'; i++) {
				await new Promise((r) => setTimeout(r, 1000));
				meta = await (await fetch(`${base}/api/meta`)).json();
			}
			const build = meta.versions.ribbons;
			expect(build).not.toBe('none');

			res = await fetch(`${base}/api/transit/network?v=${encodeURIComponent(build)}`);
			expect(res.status).toBe(200);
			expect(res.headers.get('cache-control')).toBe('public, max-age=31536000, immutable');
			body = await res.text();
			const net: TransitNetwork = JSON.parse(body);
			checkContract(net);
			expect(net).toMatchObject({ build, bundled: true, feedVersion: meta.gtfs.feedVersion });
			expect(net.segments.length).toBe(meta.ribbons.segments);
			for (const r of net.routes) expect(PALETTE).toContain(r.color);
			const gzip = gzipSync(body).length;
			evidence.bundled = { bytes: body.length, gzip, segments: net.segments.length, stops: net.stops.length,
				onSegment: net.stops.filter((s) => s.segment !== null).length,
				maxRoutes: Math.max(...net.segments.map((s) => s.routes.length)), hubs: net.hubs.map((h) => h.name) };
			expect(gzip, 'payload gzip').toBeLessThanOrEqual(LIMIT_GZIP);
			// Routes really are bundled: up to 11 on one street downtown; 40 and 45 share I-84.
			expect(Math.max(...net.segments.map((s) => s.routes.length))).toBeGreaterThanOrEqual(3);
			const shared = (a: string, b: string) =>
				net.segments.filter((s) => s.routes.includes(a) && s.routes.includes(b)).reduce((t, s) => t + s.lengthM, 0);
			expect(shared('40', '45')).toBeGreaterThanOrEqual(5000);
			expect(net.segments.some((s) => ['40', '42', '45'].every((r) => s.routes.includes(r)))).toBe(true);
			expect(net.hubs.map((h) => h.name).sort()).toEqual(['Main Street Station', 'Towne Square Mall P&R']);
			expect(net.segments.some((s) => s.hub)).toBe(true);
			expect(net.stops.filter((s) => s.segment !== null).length).toBeGreaterThan(net.stops.length * 0.95);

			// Not immutable for another version; revalidates with its ETag.
			const stale = await fetch(`${base}/api/transit/network?v=older`);
			expect(stale.headers.get('cache-control')).toBe('no-cache');
			expect(await stale.text()).toBe(body);
			const again = await fetch(`${base}/api/transit/network?v=older`, { headers: { 'if-none-match': res.headers.get('etag')! } });
			expect(again.status).toBe(304);

			// A forced rebuild of unchanged input changes nothing: same build, same bytes.
			const forced = execFileSync('python3', ['-m', 'ingest.transit_ribbons', '--force'], {
				cwd: REPO, env: { ...process.env, DATABASE_URL: url }, encoding: 'utf8', timeout: 120_000
			});
			expect(forced).toMatch(/colors changed 0/);
			expect(forced).toContain(`build ${build}`);
			expect(await (await fetch(`${base}/api/transit/network?v=${encodeURIComponent(build)}`)).text()).toBe(body);
		} finally {
			mkdirSync(dirname(screenPath('network.json')), { recursive: true });
			writeFileSync(screenPath('network.json'), JSON.stringify(evidence, null, 1));
			server?.kill('SIGTERM');
			await new Promise((r) => setTimeout(r, 1000));
			db('drop', name);
		}
	});

	test('the package database answers the network contract', { tag: '@wp6' }, async ({ request }) => {
		const meta = await (await request.get('/api/meta')).json();
		const res = await request.get(`/api/transit/network?v=${encodeURIComponent(meta.versions.ribbons)}`);
		expect(res.status()).toBe(200);
		const net: TransitNetwork = await res.json();
		checkContract(net);
		expect(net.build).toBe(meta.versions.ribbons);
		expect(net.bundled).toBe(meta.versions.ribbons !== 'none');
		expect(res.headers()['cache-control']).toBe(net.bundled ? 'public, max-age=31536000, immutable' : 'no-cache');
		expect(gzipSync(await res.body()).length).toBeLessThanOrEqual(LIMIT_GZIP);
	});
});
