#!/usr/bin/env node
/**
 * Map sheets (basemap/sheets/README.md, "Map sheets"): screenshots of the app at the
 * review places, in the looks and layer sets a review asks for. The worker's sheets
 * show the data over the photo; these show the map as people see it. Playwright
 * drives a browser on the laptop against the preview (`app-next`).
 *
 *   node scripts/map-sheets.mjs --url <preview origin> [options]
 *   node scripts/map-sheets.mjs --list [options]           # the shot list only, no browser
 *
 * Options:
 *   --url ORIGIN        the preview (default $TVT_SHEETS_URL); its address isn't in the repo
 *   --places SEL        basemap/sheets places: sets, ids or at:LON,LAT[,SIZE_M[,RES_M]]
 *                       (default boxes,cameras,spots; comma-separated, an at: keeping the
 *                       numbers after it), read through `python3 -m basemap.sheets.places --json`
 *   --looks LIST        valley, clay, auto, aerial (Valley with the photo) (default valley)
 *   --layers SET        one layer set per --layers, ids joined by +, `none` for none
 *                       (default none), e.g. --layers none --layers trees+lanes
 *   --pitch DEG         default 0 (straight down, like the worker sheets); --bearing DEG
 *   --zoom Z            one zoom for every shot (default: each frame fits the viewport's height)
 *   --size WxH          the viewport (default 1280x800)
 *   --clean             hide the app's chrome (toolbars, cards), keeping the map and its credits
 *   --label NAME        the run's name (its folder's suffix)
 *   --out DIR           default ../data/sheets (git-ignored); the run goes in <out>/<time>[-label]/
 *   --max-shots N       refuse a longer list (default 300)
 *   --channel chrome, --headed, --timeout SEC (per shot, default 120)
 *
 * Each shot is a fresh load: storage cleared, the Base look written to `tvt:v2:base`, then
 * `/#map=z/lat/lng/bearing/pitch&layers=...` (`layers=none` for none); it waits for `__tvt.ready` (the map idle) and
 * for the loading card to go, switches Aerial on through the map's view buttons when asked,
 * and screenshots the page. index.json records each shot's place, look, layers, hash, what
 * `__tvt.layers` reported (the layers actually on and the flavour) and console errors;
 * index.html shows them. The browser resolves only the preview's host (lockedArgs).
 *
 * The sheets are private (they may show internal layers): copy the run to the VM's
 * /srv/tvt/private/sheets/<package>/ and delete it here (data/dev/README-sheets.md).
 */
import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { chromium } from '@playwright/test';
import { APP_DIR, CHROMIUM_ARGS, lockedArgs } from './harness-env.mjs';
import { mapReady } from './net.mjs';

const REPO = resolve(APP_DIR, '..');
const argv = process.argv.slice(2);
const flag = (n) => argv.includes(n);
const opt = (n, d) => {
	const i = argv.indexOf(n);
	return i === -1 ? d : argv[i + 1];
};
const opts = (n) => argv.flatMap((a, i) => (a === n ? [argv[i + 1]] : []));

const LOOKS = {
	valley: { look: 'map', aerial: false },
	clay: { look: 'clay', aerial: false },
	auto: { look: 'auto', aerial: false },
	aerial: { look: 'map', aerial: true }
};

/** The zoom at which size_m fills `px` pixels. */
const fitZoom = (sizeM, px, lat) => Math.log2((40075016.686 * Math.cos((lat * Math.PI) / 180)) / (512 * (sizeM / px)));

/** `#map=z/lat/lng/bearing/pitch&layers=a,b` (or `layers=none`), as the app writes it (view.svelte.ts,
 * layers.svelte.ts): an explicit set, so a first visit's defaults never apply. */
function hashOf({ zoom, lat, lng, bearing = 0, pitch = 0, layers = [] }) {
	const view = [+zoom.toFixed(2), +lat.toFixed(6), +lng.toFixed(6), +bearing.toFixed(1), +pitch.toFixed(1)].join('/');
	return `#map=${view}&layers=${layers.length ? layers.join(',') : 'none'}`;
}

/** The frames (python3 -m basemap.sheets.places --json). */
function frames(sel) {
	// passed whole: places.py splits the commas itself, keeping an at:LON,LAT[,SIZE_M[,RES_M]] together
	const out = execFileSync('python3', ['-m', 'basemap.sheets.places', '--json', sel], {
		cwd: REPO,
		encoding: 'utf8'
	});
	return out.trim().split('\n').filter(Boolean).map((l) => JSON.parse(l));
}

/** Every shot: frames x looks x layer sets. */
function shotList(frameList, { looks, layerSets, size, pitch, bearing, zoom }) {
	const shots = [];
	for (const f of frameList) {
		const [lng, lat] = f.centre_lonlat;
		const sizeM = f.size_px[0] * f.res;
		const z = zoom ?? fitZoom(sizeM, size.height, lat);
		for (const look of looks) {
			for (const layers of layerSets) {
				const tag = [f.id, look, layers.length ? layers.join('+') : 'none'].join('__');
				shots.push({ frame: f.id, name: f.name, set: f.set, look, layers, file: `${tag}.png`,
					hash: hashOf({ zoom: z, lat, lng, bearing, pitch, layers }), zoom: +z.toFixed(2), sizeM });
			}
		}
	}
	return shots;
}

function parseOptions() {
	const looks = (opt('--looks', 'valley') || '').split(',').filter(Boolean);
	for (const l of looks) if (!LOOKS[l]) throw new Error(`--looks: ${l}? (${Object.keys(LOOKS).join(', ')})`);
	const sets = opts('--layers');
	const layerSets = (sets.length ? sets : ['none']).map((s) =>
		s === 'none' || s === '' ? [] : s.split('+').map((x) => x.trim()).filter(Boolean)
	);
	for (const set of layerSets) for (const id of set) if (!/^[a-z][a-z0-9-]*$/.test(id)) throw new Error(`--layers: ${id}?`);
	const m = /^(\d+)x(\d+)$/.exec(opt('--size', '1280x800'));
	if (!m) throw new Error('--size takes WxH, e.g. 1280x800');
	const num = (n, d) => {
		const v = opt(n, null);
		if (v === null) return d;
		if (!Number.isFinite(+v)) throw new Error(`${n} takes a number`);
		return +v;
	};
	return {
		places: opt('--places', 'boxes,cameras,spots'),
		looks,
		layerSets,
		size: { width: +m[1], height: +m[2] },
		pitch: num('--pitch', 0),
		bearing: num('--bearing', 0),
		zoom: num('--zoom', null),
		maxShots: num('--max-shots', 300),
		timeout: num('--timeout', 120) * 1000
	};
}

/** Hide everything that isn't the map or inside it (MapLibre's credits stay). */
async function clean(page) {
	await page.evaluate(() => {
		const map = document.querySelector('.maplibregl-map');
		if (!map) return;
		for (const el of document.body.querySelectorAll('*')) {
			if (el === map || map.contains(el) || el.contains(map)) continue;
			el.style.visibility = 'hidden';
		}
	});
}

async function shoot(context, base, shot, o, folder) {
	const page = await context.newPage();
	const errors = [];
	page.on('console', (m) => m.type() === 'error' && errors.push(m.text().slice(0, 300)));
	page.on('pageerror', (e) => errors.push(`pageerror: ${e.message.slice(0, 300)}`));
	const look = LOOKS[shot.look];
	const record = { ...shot, ok: false };
	try {
		await page.goto(`${base}/api/health`);
		await page.evaluate((b) => {
			localStorage.clear();
			sessionStorage.clear();
			localStorage.setItem('tvt:v2:base', JSON.stringify(b));
		}, { look: look.look, buildings: true, terrain: true, labels: 'full' });
		await page.goto(`${base}/${shot.hash}`);
		record.ready = (await mapReady(page, { timeout: o.timeout })).how;
		if (look.aerial) {
			const button = page.getByRole('group', { name: 'Map view' }).getByRole('button', { name: 'Aerial', exact: true });
			if ((await button.count()) === 0) throw new Error("no Aerial button (the preview's manifest has no imagery?)");
			await button.click();
			await mapReady(page, { timeout: o.timeout });
		}
		await page.getByText('Building the valley…').waitFor({ state: 'detached', timeout: 15_000 }).catch(() => {});
		const info = await page.evaluate(() => {
			const l = globalThis.__tvt?.layers;
			return l ? { enabled: l.enabled, shown: l.shown, flavor: l.flavor, status: l.status } : null;
		});
		record.layersReported = info;
		const missing = shot.layers.filter((id) => !(info?.enabled ?? []).includes(id));
		if (missing.length) record.note = `not on in the app: ${missing.join(', ')} (unknown to this build?)`;
		if (flag('--clean')) await clean(page);
		await page.screenshot({ path: join(folder, shot.file) });
		record.ok = true;
	} catch (err) {
		record.error = String(err?.message ?? err).slice(0, 500);
	} finally {
		record.consoleErrors = errors;
		await page.close();
	}
	return record;
}

function html(index) {
	const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
	const figs = index.shots
		.map((s) => `<figure><a href="${esc(s.file)}">${s.ok ? `<img src="${esc(s.file)}" loading="lazy">` : '<p>failed</p>'}</a>
<figcaption>${esc(s.frame)}: ${esc(s.name)}; ${esc(s.look)}; layers ${esc(s.layers.join(', ') || 'none')}; z${s.zoom}${s.note ? `; ${esc(s.note)}` : ''}${s.error ? `; ${esc(s.error)}` : ''}</figcaption></figure>`)
		.join('\n');
	return `<!doctype html><meta charset=utf-8><title>Map sheets ${esc(index.run)}</title>
<style>body{font:14px/1.4 system-ui,sans-serif;margin:24px;background:#faf8f4;color:#141820}figure{display:inline-block;width:420px;margin:0 12px 18px 0;vertical-align:top}img{width:100%}</style>
<h1>Map sheets ${esc(index.run)}</h1><p>${index.shots.length} shots; a private review sheet, not for publication.</p>${figs}`;
}

async function main() {
	const o = parseOptions();
	const list = shotList(frames(o.places), o);
	if (list.length > o.maxShots) throw new Error(`${list.length} shots, over --max-shots ${o.maxShots}`);
	if (flag('--list')) {
		for (const s of list) console.log(`${s.file.padEnd(48)} ${s.hash}`);
		console.error(`${list.length} shots`);
		return 0;
	}
	const url = opt('--url', process.env.TVT_SHEETS_URL);
	if (!url) throw new Error('--url (or TVT_SHEETS_URL): the preview to screenshot');
	const base = new URL(url).origin;
	const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z');
	const label = (opt('--label', '') || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40);
	const run = label ? `${stamp}-${label}` : stamp;
	const folder = join(resolve(opt('--out', join(REPO, 'data', 'sheets'))), run);
	mkdirSync(folder, { recursive: true });
	const channel = opt('--channel');
	const browser = await chromium.launch({
		headless: !flag('--headed'),
		channel,
		args: [...(channel ? [] : CHROMIUM_ARGS), ...lockedArgs([new URL(base).hostname])]
	});
	const index = { tool: 'app/scripts/map-sheets.mjs', run, created: new Date().toISOString(), options: o, shots: [] };
	let failed = 0;
	try {
		const context = await browser.newContext({ viewport: o.size, deviceScaleFactor: 1 });
		const meta = await (await context.request.get(`${base}/api/meta`)).json().catch(() => null);
		index.meta = meta ? { database: meta.database, versions: meta.versions } : null;
		for (const [i, shot] of list.entries()) {
			const r = await shoot(context, base, shot, o, folder);
			if (!r.ok) failed++;
			index.shots.push(r);
			console.error(`map-sheets: ${i + 1}/${list.length} ${shot.file}: ${r.ok ? 'ok' : `FAILED: ${r.error}`}${r.note ? ` (${r.note})` : ''}`);
		}
		await context.close();
	} finally {
		await browser.close();
		writeFileSync(join(folder, 'index.json'), JSON.stringify(index, null, 1) + '\n');
		writeFileSync(join(folder, 'index.html'), html(index));
	}
	console.error(`map-sheets: ${list.length - failed} of ${list.length} shots in ${folder}`);
	return failed ? 1 : 0;
}

main().then(
	(code) => process.exit(code),
	(err) => {
		console.error(`map-sheets: ${err.message}`);
		process.exit(2);
	}
);
