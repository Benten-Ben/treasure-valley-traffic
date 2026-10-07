#!/usr/bin/env node
/**
 * Performance harness (docs/14 §14.9, "How we measure"). Playwright drives
 * the app; each scenario runs `--runs` times (default 5) and reports the
 * median. Cold runs use a fresh browser context (empty cache); warm runs
 * reload the same context.
 *
 *   S1  cold load at the default view, and at z14 pitch 60
 *   S2  warm reload
 *   S3  each layer on (cold), then off and on again (warm), by its key (2, 4, 7),
 *       from the default view with no layer on; road tiles (which MapLibre's
 *       worker fetches) are counted from Playwright's request events
 *   S4  an 8 s fly-over of 3 waypoints with every layer on   (needs __tvt.map, WP1)
 *   S5  60 s of playback with no input                       (needs __tvt.map, WP1)
 *   S6  camera → Calibrate → Back: return-leg requests for tiles loaded before, and the view
 *   S7  a 30-minute soak with everything on (only when named) (needs __tvt.map, WP1)
 *   S1flat  fix 8's "flat, then tilt" first visit: a cold load at the default
 *       centre and zoom with pitch 0, then a tilt to 45 once settled; compare
 *       its bytes, requests and time to settle with S1's default view
 *       (only when named)
 *
 * Modes:
 *   --budget  the sandbox: SwiftShader, 25 Mbps / 40 ms throttling. Checks
 *             bytes, requests, duplicate ranges, ordering and return-leg
 *             counts against the §14.9 targets; exits 1 when one is missed.
 *   --real    adds timings, fps and memory, for the owner's laptop over the
 *             tailnet address (--url https://…, --channel chrome, no throttling).
 *
 * Options: --runs N, --scenarios S1,S2, --url <origin> (default: the
 * package's own preview server, started if needed), --channel chrome,
 * --headed, --baseline (write app/scripts/perf-baseline.json, the committed
 * baseline, and don't fail on targets), --no-assert.
 *
 * WP5's A/B options (docs/14 §14.9, fixes 1 and 8; #lib/perf/flags):
 *   --query 'hillshade=capped'   adds a query to every page the scenarios
 *                                open (also workers=N, lod=M,R); the report
 *                                and its file name record it
 *   --label name                 a tag for the results file
 * S5 and S7 open the pages with ?perf, whose HUD counts setData calls and
 * WebGL textures (globalThis.__tvtPerf).
 *
 * Results go to data/perf/<time>-<mode>.json (git-ignored). Bytes count
 * JS and JSON at their gzip size (scripts/net.mjs).
 */
import { spawn, execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import { join } from 'node:path';
import { chromium } from '@playwright/test';
import { APP_DIR, CHROMIUM_ARGS, harnessEnv, lockedArgs } from './harness-env.mjs';
import { firstAt, MB, mapReady, recordNetwork, summarize } from './net.mjs';

const argv = process.argv.slice(2);
const flag = (n) => argv.includes(n);
const opt = (n, d) => {
	const i = argv.indexOf(n);
	return i === -1 ? d : argv[i + 1];
};
const mode = flag('--real') ? 'real' : 'budget';
const runs = Number(opt('--runs', 5));
const baseline = flag('--baseline');
const assert = !baseline && !flag('--no-assert');
const scenarios = opt('--scenarios', mode === 'budget' ? 'S1,S2,S3,S6' : 'S1,S2,S4,S5,S6').split(',');
const query = (opt('--query', '') ?? '').replace(/^\?/, '');
const label = opt('--label', query ? query.replace(/[^\w=,.-]+/g, '_') : '');
const env = harnessEnv();
const THROTTLE = mode === 'budget' ? { latencyMs: 40, mbps: 25 } : undefined;
/** A page path with the --query options (and any of its own) before the hash. */
function withQuery(path, extra = query) {
	const [beforeHash, hash] = path.split('#');
	const [p, q] = beforeHash.split('?');
	const params = new URLSearchParams(q ?? '');
	for (const [k, v] of new URLSearchParams(extra ?? '')) params.set(k, v);
	const qs = params.toString().replace(/=(?=&|$)/g, '');
	return `${p}${qs ? `?${qs}` : ''}${hash !== undefined ? `#${hash}` : ''}`;
}
const VIEWS = {
	default: withQuery('/'),
	z14p60: withQuery('/#14/43.6150/-116.2023/0/60') // downtown Boise
};
const ROUND_TRIP_VIEW = withQuery('/#14/43.6150/-116.2023/20/50');
/** fix 8's flat first visit: the manifest's default centre and zoom (data/tiles/manifest.json), pitch 0. */
const FLAT_VIEW = withQuery('/#10/43.6000/-116.4000/0/0');
const LAYER_KEYS = [['streets', '2'], ['transit', '4'], ['cameras', '7']];

const median = (xs) => {
	const v = xs.filter((x) => typeof x === 'number' && Number.isFinite(x)).sort((a, b) => a - b);
	if (!v.length) return null;
	const m = v.length >> 1;
	return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
};
const medians = (list) => Object.fromEntries(Object.keys(list[0] ?? {}).filter((k) => typeof list[0][k] === 'number' || list[0][k] === null)
	.map((k) => [k, median(list.map((r) => r[k]))]));

async function healthy(base) {
	try {
		return (await fetch(`${base}/api/health`)).ok;
	} catch {
		return false;
	}
}

/** The app to measure: --url, or the package's preview server (started when not running). */
async function server() {
	if (opt('--url')) return { base: opt('--url').replace(/\/$/, ''), stop: () => {} };
	const base = `http://127.0.0.1:${env.TVT_PORT}`;
	if (await healthy(base)) return { base, stop: () => {} };
	const child = spawn('node', ['scripts/e2e-server.mjs'], { cwd: APP_DIR, env: { ...process.env, ...env }, stdio: 'ignore' });
	for (let i = 0; i < 600 && !(await healthy(base)); i++) await new Promise((r) => setTimeout(r, 1000));
	if (!(await healthy(base))) throw new Error(`the preview server didn't start on ${base}`);
	return { base, stop: () => child.kill('SIGTERM') };
}

const offsite = [];

async function newPage(browser, base) {
	const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, baseURL: base });
	// The browser resolves only the measured host (lockedArgs); record any other origin.
	// Not context.route: routing turns the HTTP cache off, and S2 measures it.
	const origin = new URL(base).origin;
	context.on('request', (r) => {
		const u = r.url();
		if (!u.startsWith('data:') && !u.startsWith('blob:') && new URL(u).origin !== origin) offsite.push(u);
	});
	return { context, page: await context.newPage() };
}

const hasTvt = (page) => page.evaluate(() => Boolean(globalThis.__tvt?.map));
const marks = (page) => page.evaluate(() =>
	Object.fromEntries(performance.getEntriesByType('mark').filter((m) => m.name.startsWith('tvt:')).map((m) => [m.name, Math.round(m.startTime)])));

async function heapMB(page) {
	const cdp = await page.context().newCDPSession(page);
	const { metrics } = await cdp.send('Performance.getMetrics').catch(async () => {
		await cdp.send('Performance.enable');
		return cdp.send('Performance.getMetrics');
	});
	await cdp.detach();
	return MB(metrics.find((m) => m.name === 'JSHeapUsedSize')?.value ?? 0);
}

/** The requests of one load, for the results file: path, kind, range, budget bytes, status. */
const requestList = (entries, base) => entries.map((x) => ({
	url: x.url.replace(base, ''), kind: x.kind, range: x.range, bytes: x.fromCache ? 0 : x.gzipBytes ?? x.bytes,
	status: x.status, fromCache: x.fromCache, failed: x.failed ?? undefined
}));

function loadRecord(net, t0, ready) {
	const s = summarize(net.entries);
	return {
		requests: s.requests,
		bytes: s.bytes,
		terrainBytes: s.byKind.terrain?.bytes ?? 0,
		jsGzipBytes: s.byKind.js?.bytes ?? 0,
		apiGzipBytes: s.byKind.api?.bytes ?? 0,
		duplicates: s.duplicates,
		cached: s.cached,
		failed: s.failed,
		firstDataStartS: firstAt(net.entries, (x) => x.kind === 'api' && !x.url.includes('/api/meta'), t0),
		firstDemResponseS: firstAt(net.entries, (x) => x.kind === 'terrain', t0, 'responseAt'),
		settledMs: ready.settledMs,
		byKind: s.byKind
	};
}

async function S1(browser, base) {
	const out = {};
	for (const [name, path] of Object.entries(VIEWS)) {
		const list = [];
		for (let i = 0; i < runs; i++) {
			const { context, page } = await newPage(browser, base);
			const net = await recordNetwork(page, { throttle: THROTTLE });
			await page.goto(path);
			const ready = await mapReady(page);
			await net.settle();
			const t0 = Math.min(...net.entries.map((x) => x.start));
			const r = loadRecord(net, t0, ready);
			r.requestList = requestList(net.entries, base);
			if (mode === 'real') Object.assign(r, { marks: await marks(page), heapMB: await heapMB(page) });
			list.push(r);
			await net.detach();
			await context.close();
			log(`S1 ${name} run ${i + 1}: ${r.requests} requests, ${MB(r.bytes)} MB (terrain ${MB(r.terrainBytes)}), ${r.duplicates} duplicates`);
		}
		out[name] = { median: medians(list), byKind: list.at(-1).byKind, runs: list.map(({ byKind, requestList, ...r }) => r), requests: list.at(-1).requestList };
	}
	return out;
}

async function S1flat(browser, base) {
	const list = [];
	for (let i = 0; i < runs; i++) {
		const { context, page } = await newPage(browser, base);
		const net = await recordNetwork(page, { throttle: THROTTLE });
		await page.goto(FLAT_VIEW);
		const flat = await mapReady(page);
		await net.settle();
		const flatSummary = summarize(net.entries);
		const t0 = Math.min(...net.entries.map((x) => x.start));
		const tiltStart = Date.now();
		await page.evaluate(() => globalThis.__tvt.map.easeTo({ pitch: 45, duration: 600 }));
		const tilt = await mapReady(page);
		await net.settle();
		const r = { ...loadRecord(net, t0, { settledMs: flat.settledMs + (Date.now() - tiltStart) }), flatRequests: flatSummary.requests,
			flatBytes: flatSummary.bytes, flatSettledMs: flat.settledMs, tiltSettledMs: tilt.settledMs };
		if (mode === 'real') Object.assign(r, { marks: await marks(page) });
		delete r.requestList;
		list.push(r);
		await net.detach();
		await context.close();
		log(`S1flat run ${i + 1}: flat ${r.flatRequests} requests / ${MB(r.flatBytes)} MB, after the tilt ${r.requests} / ${MB(r.bytes)} MB (terrain ${MB(r.terrainBytes)}), ${r.duplicates} duplicates`);
	}
	return { median: medians(list), byKind: list.at(-1).byKind, runs: list.map(({ byKind, ...r }) => r) };
}

async function S2(browser, base) {
	// A persistent profile, so the HTTP cache is on disk as in a real Chrome profile.
	// (Incognito contexts keep a small in-memory cache that drops the big terrain range entries.)
	const { mkdtempSync, rmSync } = await import('node:fs');
	const profile = mkdtempSync(join(os.tmpdir(), 'tvt-perf-profile-'));
	const context = await chromium.launchPersistentContext(profile, {
		...launchOptions,
		viewport: { width: 1280, height: 800 },
		baseURL: base
	});
	const origin = new URL(base).origin;
	context.on('request', (r) => {
		const u = r.url();
		if (!u.startsWith('data:') && !u.startsWith('blob:') && new URL(u).origin !== origin) offsite.push(u);
	});
	const page = context.pages()[0] ?? (await context.newPage());
	await page.goto(VIEWS.default);
	await mapReady(page);
	const list = [];
	for (let i = 0; i < runs; i++) {
		const net = await recordNetwork(page, { throttle: THROTTLE, bodies: false });
		await page.reload();
		const ready = await mapReady(page);
		const s = summarize(net.entries);
		list.push({ requests: s.requests + s.cached, networkRequests: s.requests, cacheHits: s.cached, wireBytes: s.wireBytes,
			terrainWireBytes: net.entries.filter((x) => x.kind === 'terrain').reduce((a, x) => a + x.bytes, 0), settledMs: ready.settledMs });
		await net.detach();
		log(`S2 run ${i + 1}: ${s.requests} over the network, ${s.cached} from cache, ${MB(s.wireBytes)} MB`);
	}
	await context.close();
	rmSync(profile, { recursive: true, force: true });
	return { median: medians(list), runs: list, profile: 'persistent (disk cache)' };
}

/**
 * Road tiles: MapLibre's worker fetches them, and the page's CDP session
 * (net.mjs) doesn't see a worker's requests; Playwright's request events do.
 * Bytes are the encoded body (gzip since WP5).
 */
const WORKER_FETCHED = /\/api\/tiles\/roads\//;
function recordWorkerRequests(page) {
	const list = [];
	const on = (r) => WORKER_FETCHED.test(r.url()) && list.push(r);
	page.on('requestfinished', on);
	return {
		mark: () => list.length,
		async summary(from = 0) {
			const rs = list.slice(from);
			let bytes = 0;
			let gzipped = 0;
			for (const r of rs) {
				bytes += (await r.sizes().catch(() => null))?.responseBodySize ?? 0;
				if ((await r.response())?.headers()['content-encoding'] === 'gzip') gzipped++;
			}
			return { requests: rs.length, bytes, gzipped };
		},
		detach: () => page.off('requestfinished', on)
	};
}

/** Periodic polls, which run on their own clock rather than because of a toggle. */
const POLL = /\/api\/(transit\/(vehicles|tracks)|cameras\/(live|status))/;

/**
 * S3 opens the default view with no layer on (`layers=none`: Transit and
 * Cameras are on by default since WP2, so their key would turn them off),
 * waits for the map to settle (the first idle prefetches the off layers'
 * JSON, as designed), then measures each layer's toggles in a fresh context.
 */
const S3_VIEW = withQuery('/#map=10/43.6/-116.4/0/45&layers=none');

async function S3(browser, base) {
	const out = {};
	for (const [layer, key] of LAYER_KEYS) {
		const list = [];
		for (let i = 0; i < runs; i++) {
			const { context, page } = await newPage(browser, base);
			await page.goto(S3_VIEW);
			await mapReady(page);
			const net = await recordNetwork(page, { throttle: THROTTLE });
			const tiles = recordWorkerRequests(page);
			await page.keyboard.press(key); // on (cold)
			await mapReady(page);
			await net.settle();
			const cold = summarize(net.entries);
			const coldTiles = await tiles.summary();
			const mark = net.mark();
			const tileMark = tiles.mark();
			await page.keyboard.press(key); // off
			await page.waitForTimeout(500);
			await page.keyboard.press(key); // on again (warm)
			await mapReady(page, { quietMs: 1500 });
			const since = net.since(mark);
			const warm = summarize(since);
			const warmTiles = await tiles.summary(tileMark);
			const polls = since.filter((x) => POLL.test(x.url)).length;
			const r = {
				coldRequests: cold.requests + coldTiles.requests,
				coldBytes: cold.bytes + coldTiles.bytes,
				coldRoadTiles: coldTiles.requests,
				coldRoadTileBytes: coldTiles.bytes,
				coldRoadTilesGzipped: coldTiles.gzipped,
				warmRequests: warm.requests + warm.cached + warmTiles.requests,
				warmNetworkRequests: warm.requests + warmTiles.requests,
				warmPolls: polls
			};
			list.push(r);
			tiles.detach();
			await net.detach();
			await context.close();
			log(`S3 ${layer} run ${i + 1}: cold ${r.coldRequests} requests / ${MB(r.coldBytes)} MB (road tiles ${coldTiles.requests}, ${coldTiles.gzipped} gzipped); ` +
				`warm toggle ${r.warmRequests} requests (${polls} of them polls)`);
		}
		out[layer] = { median: medians(list), runs: list };
	}
	return out;
}

const view = (page) => page.evaluate(() => {
	const map = globalThis.__tvt?.map;
	if (map) {
		const c = map.getCenter();
		return { lng: c.lng, lat: c.lat, zoom: map.getZoom(), bearing: map.getBearing(), pitch: map.getPitch() };
	}
	const m = /^#(?:map=)?([\d.]+)\/(-?[\d.]+)\/(-?[\d.]+)(?:\/(-?[\d.]+))?(?:\/([\d.]+))?/.exec(location.hash);
	return m ? { zoom: +m[1], lat: +m[2], lng: +m[3], bearing: +(m[4] ?? 0), pitch: +(m[5] ?? 0) } : null;
});

async function S6(browser, base) {
	const seedFile = join(env.FRAMES_DIR, '..', 'seed.json');
	const { readFileSync } = await import('node:fs');
	const key = JSON.parse(readFileSync(seedFile, 'utf8')).seeds.find((s) => s.kind === 'key');
	const list = [];
	for (let i = 0; i < runs; i++) {
		const { context, page } = await newPage(browser, base);
		const net = await recordNetwork(page, { throttle: THROTTLE, bodies: false });
		await page.goto(ROUND_TRIP_VIEW);
		await mapReady(page);
		const isTile = (x) => /\/tiles\/.+\.pmtiles/.test(x.url);
		const keyOf = (x) => `${x.url} ${x.range ?? ''}`;
		const loaded = new Set(net.entries.filter((x) => isTile(x) && !x.failed).map(keyOf));
		const before = await view(page);
		await page.evaluate((href) => {
			const a = document.createElement('a');
			a.href = href;
			document.body.append(a);
			a.click();
			a.remove();
		}, `/calibrate/${key.cameraId}`);
		await page.waitForURL(/\/calibrate\//);
		await mapReady(page);
		const mark = net.mark();
		await page.goBack();
		await page.waitForURL((u) => !u.pathname.startsWith('/calibrate'));
		const ready = await mapReady(page);
		const back = net.since(mark);
		const after = await view(page);
		const r = {
			returnLegRequests: back.length,
			returnLegUrls: back.map((x) => x.url.replace(base, '')),
			returnLegTileRefetches: back.filter((x) => isTile(x) && loaded.has(keyOf(x))).length,
			returnLegManifestRequests: back.filter((x) => x.kind === 'manifest').length,
			returnLegWireBytes: back.reduce((s, x) => s + x.bytes, 0),
			centreErrorDeg: before && after ? Math.max(Math.abs(after.lng - before.lng), Math.abs(after.lat - before.lat)) : null,
			zoomError: before && after ? Math.abs(after.zoom - before.zoom) : null,
			mapsCreated: await page.evaluate(() => globalThis.__tvt?.mapsCreated ?? null),
			settledMs: ready.settledMs
		};
		list.push(r);
		await net.detach();
		await context.close();
		log(`S6 run ${i + 1}: return leg ${r.returnLegRequests} requests, ${r.returnLegTileRefetches} tiles again, ${r.returnLegManifestRequests} manifest`);
	}
	return { median: medians(list), runs: list };
}

/** Frame times while `fn` runs, from the map's render events (needs __tvt.map). */
async function frames(page, fn, ms) {
	await page.evaluate(() => {
		const map = globalThis.__tvt.map;
		globalThis.__perfFrames = [];
		globalThis.__perfOn = () => globalThis.__perfFrames.push(performance.now());
		map.on('render', globalThis.__perfOn);
	});
	await fn();
	await page.waitForTimeout(ms);
	const t = await page.evaluate(() => {
		globalThis.__tvt.map.off('render', globalThis.__perfOn);
		return globalThis.__perfFrames;
	});
	const gaps = t.slice(1).map((x, i) => x - t[i]).sort((a, b) => a - b);
	const p = (q) => (gaps.length ? gaps[Math.min(gaps.length - 1, Math.floor(q * gaps.length))] : null);
	return { frames: t.length, fps: +(t.length / (ms / 1000)).toFixed(1), medianFps: p(0.5) ? +(1000 / p(0.5)).toFixed(1) : 0, p95FrameMs: p(0.95), maxFrameMs: gaps.at(-1) ?? null };
}

async function S4(browser, base) {
	const { context, page } = await newPage(browser, base);
	await page.goto(VIEWS.default);
	await mapReady(page);
	if (!(await hasTvt(page))) return context.close().then(() => ({ skipped: 'needs __tvt.map (WP1)' }));
	for (const key of ['2', '4', '7']) await page.keyboard.press(key);
	await mapReady(page);
	const list = [];
	for (let i = 0; i < runs; i++) {
		list.push(await frames(page, () => page.evaluate(async () => {
			const map = globalThis.__tvt.map;
			const pts = [[-116.2023, 43.615, 14], [-116.3549, 43.6197, 15], [-116.39, 43.597, 13]];
			for (const [lng, lat, zoom] of pts) map.flyTo({ center: [lng, lat], zoom, pitch: 55, duration: 2600 });
		}), 8000));
	}
	await context.close();
	return { median: medians(list), runs: list };
}

async function S5(browser, base) {
	const { context, page } = await newPage(browser, base);
	await page.goto(withQuery(VIEWS.default, 'perf'));
	await mapReady(page);
	if (!(await hasTvt(page))) return context.close().then(() => ({ skipped: 'needs __tvt.map (WP1)' }));
	const net = await recordNetwork(page, { bodies: false });
	const f = await frames(page, async () => {}, 60_000);
	const setData = await page.evaluate(() => globalThis.__tvtPerf?.setDataCalls ?? null);
	await net.detach();
	await context.close();
	return { ...f, requests: net.entries.length, setDataCalls: setData };
}

async function S7(browser, base) {
	const { context, page } = await newPage(browser, base);
	await page.goto(withQuery(VIEWS.default, 'perf'));
	await mapReady(page);
	if (!(await hasTvt(page))) return context.close().then(() => ({ skipped: 'needs __tvt.map (WP1)' }));
	for (const key of ['2', '4', '7']) await page.keyboard.press(key);
	const samples = [];
	for (let m = 0; m <= 30; m++) {
		samples.push({ minute: m, heapMB: await heapMB(page), textures: await page.evaluate(() => globalThis.__tvtPerf?.textures ?? null) });
		if (m < 30) await page.waitForTimeout(60_000);
	}
	await context.close();
	return { samples, heapGrowthMB: +(samples.at(-1).heapMB - samples[0].heapMB).toFixed(1) };
}

const SCENARIOS = { S1, S2, S3, S4, S5, S6, S7, S1flat };

/** §14.9 targets this harness can check today (budget mode). */
function targets(res) {
	const t = [];
	const add = (name, value, ok) => t.push({ name, value, ok });
	const d = res.S1?.default?.median;
	if (d) {
		add('cold first load ≤ 6 MB (default view)', `${MB(d.bytes)} MB`, d.bytes <= 6e6);
		add('cold first load ≤ 50 requests', d.requests, d.requests <= 50);
		add('0 duplicate byte ranges', d.duplicates, d.duplicates === 0);
		add('data fetches start before the first DEM response', `${d.firstDataStartS?.toFixed(2)} s vs ${d.firstDemResponseS?.toFixed(2)} s`,
			d.firstDataStartS !== null && d.firstDemResponseS !== null && d.firstDataStartS < d.firstDemResponseS);
	}
	add('every request same-origin', offsite.length, offsite.length === 0);
	for (const [layer, r] of Object.entries(res.S3 ?? {})) add(`toggling loaded ${layer}: 0 requests`, r.median.warmRequests, r.median.warmRequests === 0);
	const s6 = res.S6?.median;
	if (s6) {
		add('return leg: 0 refetched tiles', s6.returnLegTileRefetches, s6.returnLegTileRefetches === 0);
		add('return leg: 0 manifest requests', s6.returnLegManifestRequests, s6.returnLegManifestRequests === 0);
		add('view restored (centre < 1e-6°, zoom < 0.01)', `${s6.centreErrorDeg} °, ${s6.zoomError}`,
			s6.centreErrorDeg !== null && s6.centreErrorDeg < 1e-6 && s6.zoomError < 0.01);
	}
	return t;
}

function log(msg) {
	process.stderr.write(`${msg}\n`);
}

const srv = await server();
const launchOptions = {
	headless: !flag('--headed'),
	channel: opt('--channel'),
	args: [...(opt('--channel') ? [] : CHROMIUM_ARGS), ...lockedArgs([new URL(srv.base).hostname])]
};
const browser = await chromium.launch(launchOptions);
const results = {};
let gpu = null;
try {
	{
		const { context, page } = await newPage(browser, srv.base);
		await page.goto('/api/health');
		gpu = await page.evaluate(() => {
			const gl = document.createElement('canvas').getContext('webgl2');
			const ext = gl?.getExtension('WEBGL_debug_renderer_info');
			return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl ? 'unknown' : 'no WebGL2';
		});
		await context.close();
	}
	for (const s of scenarios) {
		if (!SCENARIOS[s]) throw new Error(`unknown scenario ${s}`);
		log(`— ${s}`);
		results[s] = await SCENARIOS[s](browser, srv.base);
	}
} finally {
	await browser.close();
	srv.stop();
}

let commit = null;
try {
	commit = execFileSync('git', ['rev-parse', '--short', 'HEAD'], { cwd: APP_DIR, encoding: 'utf8' }).trim();
} catch {
	/* not a checkout */
}
const local = /^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(srv.base);
const report = {
	mode,
	at: new Date().toISOString(),
	commit,
	// A deployed address is the owner's; only localhost goes into a committed file.
	url: local ? srv.base : '<deployed address>',
	browser: `${browser.browserType().name()} ${browser.version()}${opt('--channel') ? ` (${opt('--channel')})` : ''}`,
	os: `${os.type()} ${os.release()} ${os.arch()}`,
	gpu,
	throttle: THROTTLE ?? null,
	runs,
	query: query || null,
	tilesServer: local ? 'vite preview with the Caddy mirror (src/lib/server/tiles-static.ts)' : 'Caddy',
	results,
	offsite: [...new Set(offsite)],
	targets: mode === 'budget' ? targets(results) : []
};

const dir = join(env.TVT_MAIN, 'data', 'perf');
mkdirSync(dir, { recursive: true });
const file = join(dir, `${report.at.replace(/[:.]/g, '-')}-${mode}${label ? `-${label}` : ''}.json`);
writeFileSync(file, JSON.stringify({ ...report, url: srv.base }, null, 2));
if (baseline) writeFileSync(join(APP_DIR, 'scripts', 'perf-baseline.json'), `${JSON.stringify(report, null, 2)}\n`);

console.log(`\nperf ${mode}: ${report.browser}, ${report.gpu}, ${runs} runs each, results in ${file}`);
if (report.targets.length) console.table(report.targets.map((x) => ({ target: x.name, value: x.value, status: x.ok ? 'ok' : 'MISSED' })));
const missed = report.targets.filter((x) => !x.ok).length;
if (assert && missed) {
	console.log(`${missed} target(s) missed`);
	process.exit(1);
}
