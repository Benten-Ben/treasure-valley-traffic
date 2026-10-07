import { execFileSync, spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { gzipSync } from 'node:zlib';
import { expect, env, screenPath, test } from './fixtures.js';
import type { Tracks, TrackStep } from '../../src/lib/contracts/tracks.js';

/**
 * WP7's acceptance (docs/14 §14.10, WP7; §14.4 "Playback"): the tracks API on
 * the package's clone, replayed with `at=`.
 *
 * The local clone holds the morning of Oct 6 (fixes 11:23–15:00 UTC), not the
 * Oct 5 20:17–20:34 minutes the plan names, so the replay time is 14:30 UTC
 * (8:30 AM MDT), the busiest stretch. Before the specs, the clone gets
 * migration 0007 and a backfill of those fixes through the matcher
 * (python3 -m ingest.transit_progress), as §14.11 "Seeded data" describes;
 * both are idempotent.
 */
const APP = resolve(import.meta.dirname, '..', '..');
const REPO = resolve(APP, '..');
const AT = '2026-10-06T14:30:00Z';
const AT_S = Date.parse(AT) / 1000;
const MORNING = { from: '2026-10-06T11:00:00Z', to: '2026-10-06T15:05:00Z' };

const dbTool = (...args: string[]) => execFileSync('node', ['scripts/db.mjs', ...args], { cwd: APP, encoding: 'utf8' });

function backfill(databaseUrl: string) {
	return execFileSync('python3', ['-m', 'ingest.transit_progress', '--from', MORNING.from, '--to', MORNING.to], {
		cwd: REPO,
		encoding: 'utf8',
		env: { ...process.env, DATABASE_URL: databaseUrl }
	});
}

/** Great-circle metres between two lon/lat points. */
function metres(lon0: number, lat0: number, lon1: number, lat1: number) {
	const r = Math.PI / 180;
	const a = Math.sin(((lat1 - lat0) * r) / 2) ** 2 + Math.cos(lat0 * r) * Math.cos(lat1 * r) * Math.sin(((lon1 - lon0) * r) / 2) ** 2;
	return 2 * 6_371_008 * Math.asin(Math.sqrt(a));
}

function pathLength(path: number[]) {
	let m = 0;
	for (let i = 2; i < path.length; i += 2) m += metres(path[i - 2], path[i - 1], path[i], path[i + 1]);
	return m;
}

const kindOf = (s: TrackStep) => s[3];

function evidence(name: string, value: unknown) {
	const file = screenPath(name);
	mkdirSync(dirname(file), { recursive: true });
	writeFileSync(file, typeof value === 'string' ? value : JSON.stringify(value, null, 2));
}

test.describe('tracks API', () => {
	test.beforeAll(() => {
		const name = `tvt_${env().wp || 'local'}`;
		dbTool('migrate', name);
		evidence('backfill.txt', backfill(process.env.DATABASE_URL!));
	});

	test('replay at a past time: steps for at least 15 buses, no-store, small', { tag: '@wp7' }, async ({ request }) => {
		const res = await request.get(`/api/transit/tracks?at=${AT}`);
		expect(res.status()).toBe(200);
		expect(res.headers()['cache-control']).toBe('no-store');
		const body = await res.body();
		const t: Tracks = JSON.parse(body.toString());
		expect(t.contract).toBe(1);
		expect(t.now).toBe(AT_S);
		const buses = new Set(t.steps.map((s) => s[0]));
		expect(buses.size).toBeGreaterThanOrEqual(15);
		expect(new Set(Object.keys(t.vehicles))).toEqual(buses);
		// Nothing after the pinned time; one newest fix (t1 null) per bus, at most 15 min old.
		for (const s of t.steps) {
			expect(s[1]).toBeLessThanOrEqual(AT_S);
			if (s[2] !== null) expect(s[2]).toBeLessThanOrEqual(AT_S);
		}
		const newest = t.steps.filter((s) => s[2] === null);
		expect(newest).toHaveLength(buses.size);
		for (const s of newest) expect(s[1]).toBeGreaterThanOrEqual(AT_S - 900);
		// Every step meets the 120 s window, or is a bus's newest fix.
		for (const s of t.steps) if (s[2] !== null) expect(s[2]).toBeGreaterThanOrEqual(AT_S - 120);
		// Along steps carry a path that starts and ends near their fixes.
		const along = t.steps.filter((s) => kindOf(s) === 'along');
		expect(along.length).toBeGreaterThan(20);
		const next = new Map(t.steps.map((s) => [`${s[0]}|${s[1]}`, s]));
		for (const s of along) {
			const path = s[8]!;
			expect(path.length).toBeGreaterThanOrEqual(4);
			expect(metres(s[4], s[5], path[0], path[1])).toBeLessThanOrEqual(40.5);
			const to = next.get(`${s[0]}|${s[2]}`);
			if (to) expect(metres(to[4], to[5], path[path.length - 2], path[path.length - 1])).toBeLessThanOrEqual(40.5);
		}
		for (const v of Object.values(t.vehicles)) {
			expect(v.color).toMatch(/^#[0-9a-f]{6}$/);
			expect(v.textColor).toMatch(/^#(ffffff|2b2a33)$/);
		}
		expect(Object.values(t.vehicles).filter((v) => v.routeId).length).toBeGreaterThanOrEqual(15);
		expect(t.lastFix).toBeGreaterThan(AT_S - 60);
		expect(t.lastFix).toBeLessThanOrEqual(AT_S);
		const gz = gzipSync(body).length;
		expect(gz).toBeLessThanOrEqual(8 * 1024);
		evidence('tracks-at-1430.json', t);
		test.info().annotations.push({ type: 'size', description: `${buses.size} buses, ${t.steps.length} steps, ${gz} B gzip` });
	});

	test('the replayed minutes pass the playback checks', { tag: '@wp7' }, async ({ request, page }) => {
		// 14:13–14:30 UTC: the same 17 minutes the plan checks on Oct 5, on Oct 6's data.
		const res = await request.get(`/api/transit/tracks?at=${AT}&window=900`);
		const late: Tracks = await res.json();
		const early: Tracks = await (await request.get(`/api/transit/tracks?at=2026-10-06T14:15:00Z&window=120`)).json();
		const steps = new Map<string, TrackStep>();
		for (const s of [...early.steps, ...late.steps]) if (s[2] !== null && s[1] >= AT_S - 17 * 60) steps.set(`${s[0]}|${s[1]}`, s);
		const vehicles = { ...early.vehicles, ...late.vehicles };
		const labeled = [...steps.values()].filter((s) => ['feed', 'trip'].includes(vehicles[s[0]]?.routeSource ?? ''));
		const count = (k: string) => labeled.filter((s) => kindOf(s) === k).length;
		const shares = Object.fromEntries(['along', 'still', 'gap', 'straight'].map((k) => [k, count(k) / labeled.length]));
		const prototype = { along: 232 / 323, still: 71 / 323, gap: 14 / 323, straight: 6 / 323 };
		const fastest = Math.max(...[...steps.values()].filter((s) => kindOf(s) === 'along').map((s) => s[7] ?? 0));
		// Distance along each path over its time: never faster than 30 m/s (with 2 m of slack for rounding).
		const pathSpeeds = [...steps.values()]
			.filter((s) => kindOf(s) === 'along')
			.map((s) => (pathLength(s[8]!) - 2) / (s[2]! - s[1]));
		const summary = {
			steps: steps.size,
			labeledSteps: labeled.length,
			shares,
			prototype,
			alongOrStill: shares.along + shares.still,
			fastestAlongMs: fastest,
			fastestPathMs: Math.max(...pathSpeeds)
		};
		evidence('replay-17min.json', summary);
		expect(labeled.length).toBeGreaterThan(500);
		expect(summary.alongOrStill).toBeGreaterThanOrEqual(0.9);
		expect(fastest).toBeLessThanOrEqual(30);
		expect(summary.fastestPathMs).toBeLessThanOrEqual(30);
		for (const k of Object.keys(prototype) as (keyof typeof prototype)[]) {
			expect(Math.abs(shares[k] - prototype[k]), k).toBeLessThanOrEqual(0.1);
		}

		// Evidence for the owner: the replayed paths and fixes, drawn plainly (no map, no camera image).
		const xs = [...steps.values()].flatMap((s) => (s[8] ? s[8].filter((_, i) => i % 2 === 0) : [s[4]]));
		const ys = [...steps.values()].flatMap((s) => (s[8] ? s[8].filter((_, i) => i % 2 === 1) : [s[5]]));
		const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
		const k = 1180 / Math.max((x1 - x0) * Math.cos((43.6 * Math.PI) / 180), y1 - y0);
		const px = (lon: number, lat: number) =>
			`${(10 + (lon - x0) * Math.cos((43.6 * Math.PI) / 180) * k).toFixed(1)},${(10 + (y1 - lat) * k).toFixed(1)}`;
		const lines = [...steps.values()].map((s) => {
			const color = vehicles[s[0]]?.color ?? '#8a857c';
			if (kindOf(s) === 'along') {
				const pts = [];
				for (let i = 0; i < s[8]!.length; i += 2) pts.push(px(s[8]![i], s[8]![i + 1]));
				return `<polyline points="${pts.join(' ')}" stroke="${color}" stroke-width="2.5" fill="none"/>`;
			}
			const to = steps.get(`${s[0]}|${s[2]}`) ?? late.steps.find((n) => n[0] === s[0] && n[1] === s[2]);
			const dash = kindOf(s) === 'gap' ? '2 4' : '6 3';
			return to && kindOf(s) !== 'still'
				? `<line x1="${px(s[4], s[5]).split(',')[0]}" y1="${px(s[4], s[5]).split(',')[1]}" x2="${px(to[4], to[5]).split(',')[0]}" y2="${px(to[4], to[5]).split(',')[1]}" stroke="#2b2a33" stroke-dasharray="${dash}" stroke-width="1.5"/>`
				: '';
		});
		const dots = [...steps.values()].map((s) => `<circle cx="${px(s[4], s[5]).split(',')[0]}" cy="${px(s[4], s[5]).split(',')[1]}" r="1.6" fill="#2b2a33"/>`);
		await page.setViewportSize({ width: 1200, height: 900 });
		await page.setContent(
			`<body style="margin:0;background:#f3ede2;font:14px sans-serif"><div style="position:absolute;left:12px;top:8px">` +
				`Bus playback steps, Oct 6 14:13–14:30 UTC (local replay): solid = along (matched path, route color), ` +
				`dashed = straight, dotted = gap, dots = fixes. ${steps.size} steps.</div>` +
				`<svg width="1200" height="900" viewBox="0 -30 1200 900">${lines.join('')}${dots.join('')}</svg></body>`
		);
		await page.screenshot({ path: screenPath('replay-17min-paths.png') });
	});

	test('each poll stays under 8 KB gzip across the recorded morning', { tag: '@wp7' }, async ({ request }) => {
		const sizes: { at: string; buses: number; gzip: number }[] = [];
		for (let t = Date.parse('2026-10-06T11:30:00Z'); t <= Date.parse('2026-10-06T15:00:00Z'); t += 10 * 60_000) {
			const at = new Date(t).toISOString();
			const res = await request.get(`/api/transit/tracks?window=120&at=${at}`);
			expect(res.status()).toBe(200);
			const body = await res.body();
			sizes.push({ at, buses: Object.keys(JSON.parse(body.toString()).vehicles).length, gzip: gzipSync(body).length });
		}
		evidence('poll-sizes.json', sizes);
		expect(Math.max(...sizes.map((s) => s.buses))).toBeGreaterThanOrEqual(30);
		for (const s of sizes) expect(s.gzip, s.at).toBeLessThanOrEqual(8 * 1024);
	});

	test('routeRuns: spans over the 75 minutes before the playhead', { tag: '@wp7' }, async ({ request }) => {
		const t: Tracks = await (await request.get(`/api/transit/tracks?at=${AT}`)).json();
		const routes = Object.keys(t.routeRuns);
		expect(routes.length).toBeGreaterThanOrEqual(10);
		for (const spans of Object.values(t.routeRuns)) {
			for (const [start, end] of spans) {
				expect(start).toBeLessThanOrEqual(end);
				expect(start).toBeGreaterThan(AT_S - 75 * 60);
				expect(end).toBeLessThanOrEqual(AT_S);
			}
			for (let i = 1; i < spans.length; i++) expect(spans[i][0] - spans[i - 1][1]).toBeGreaterThan(900);
		}
		// Every route with a bus reporting in the last 15 min is running at the playhead.
		const running = routes.filter((r) => t.routeRuns[r].some(([s, e]) => s <= AT_S && e >= AT_S - 900));
		const newest = t.steps.filter((s) => s[2] === null && s[1] >= AT_S - 900);
		for (const s of newest) {
			const route = t.vehicles[s[0]].routeId;
			if (route) expect(running).toContain(route);
		}
	});

	test('a second request within 5 s comes from the micro-cache; bad parameters are refused', { tag: '@wp7' }, async ({ request }) => {
		const url = `/api/transit/tracks?window=300&at=2026-10-06T13:41:17Z`;
		const a = await request.get(url);
		const b = await request.get(url);
		expect([a.headers()['x-cache'], b.headers()['x-cache']]).toEqual(['miss', 'hit']);
		expect(await b.json()).toEqual(await a.json());
		expect((await request.get('/api/transit/tracks?window=abc')).status()).toBe(400);
		expect((await request.get('/api/transit/tracks?at=yesterday')).status()).toBe(400);
		const live = await request.get('/api/transit/tracks');
		expect(live.status()).toBe(200);
		const now: Tracks = await live.json();
		expect(Math.abs(now.now - Date.now() / 1000)).toBeLessThan(30);
	});

	test('with no progress rows (before 0007, and with it empty) buses still play as straight steps', { tag: '@wp7' }, async () => {
		test.setTimeout(300_000);
		const name = `tvt_${env().wp || 'local'}_scratch`;
		dbTool('drop', name);
		dbTool('clone', name);
		const url = dbTool('url', name).trim();
		const port = Number(process.env.TVT_PORT) + 100;
		const results: Record<string, unknown> = {};
		const ask = async (label: string) => {
			const server = spawn('node', ['scripts/e2e-server.mjs', '--port', String(port)], {
				cwd: APP,
				env: { ...process.env, DATABASE_URL: url, TVT_E2E_BUILD: '0' },
				stdio: 'ignore'
			});
			try {
				let t: Tracks | null = null;
				for (let i = 0; i < 120 && !t; i++) {
					t = await fetch(`http://127.0.0.1:${port}/api/transit/tracks?at=${AT}`).then((r) => (r.ok ? r.json() : null), () => null);
					if (!t) await new Promise((r) => setTimeout(r, 500));
				}
				expect(t, `${label}: the scratch server answered`).not.toBeNull();
				const kinds = new Set(t!.steps.map(kindOf));
				results[label] = { buses: Object.keys(t!.vehicles).length, kinds: [...kinds] };
				expect(Object.keys(t!.vehicles).length, label).toBeGreaterThanOrEqual(15);
				expect(kinds.has('straight'), label).toBe(true);
				expect(kinds.has('along'), label).toBe(false);
				expect(t!.steps.every((s) => s[8] === null), label).toBe(true);
			} finally {
				server.kill('SIGTERM');
				await new Promise((r) => setTimeout(r, 1000));
			}
		};
		try {
			const has = () =>
				execFileSync('psql', ['-X', '-At', url, '-c', "select to_regclass('obs.vehicle_progress') is not null"], { encoding: 'utf8' }).trim();
			if (has() === 'f') await ask('before migration 0007');
			dbTool('migrate', name);
			expect(has()).toBe('t');
			// The template is a copy of the server's data, which has progress rows since Oct 7: empty
			// the scratch clone's table, so this case is the one it names.
			execFileSync('psql', ['-X', '-At', url, '-c', 'truncate obs.vehicle_progress'], { encoding: 'utf8' });
			expect(execFileSync('psql', ['-X', '-At', url, '-c', 'select count(*) from obs.vehicle_progress'], { encoding: 'utf8' }).trim()).toBe('0');
			await ask('0007 applied, table empty');
			evidence('no-progress.json', results);
		} finally {
			dbTool('drop', name);
		}
	});
});
