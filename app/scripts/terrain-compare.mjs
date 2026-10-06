#!/usr/bin/env node
/**
 * Before/after screenshots for the terrain re-encode (WP17, docs/14 §14.10):
 * the same views drawn from two terrain files, side by side with an amplified
 * difference, so a reviewer can look for terracing.
 *
 * Views: the Boise foothills and the flat valley floor, each at z10, z13 and
 * z15, drawn three ways:
 *   hillshade  the bare terrain page (terrain-check.mjs), hillshade only, at
 *              hillshade-exaggeration 1 (the app uses 0.3), so any steps
 *              show up as strongly as they can;
 *   app-2d     the app itself, flat;
 *   app-3d     the app itself, tilted to 60 degrees with 3D terrain.
 * The app's views need a running preview or dev server (--app) whose
 * TILES_DIR holds both files; its manifest's terrain entry is pointed at
 * each file in turn.
 *
 * Output (data/dev/screens/<wp>/terrain/ unless --out): raw/<view>-<kind>-<a|b>.png,
 * compare-<view>-<kind>.png (before | after | difference x8) and compare.json
 * (mean and largest pixel difference per view, console errors per page).
 *
 * Usage:
 *   node scripts/terrain-compare.mjs --before terrain.pmtiles --after terrain-webp-20261006.pmtiles \
 *     [--tiles DIR] [--app http://127.0.0.1:5218] [--only foothills-z13] [--kinds hillshade,app-3d]
 */
import { chromium } from '@playwright/test';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { CHROMIUM_ARGS, harnessEnv, lockedArgs } from './harness-env.mjs';
import { mapReady } from './net.mjs';
import { openCheck, startCheckServer } from './terrain-check.mjs';

const { values: args } = parseArgs({
	options: {
		before: { type: 'string', default: 'terrain.pmtiles' },
		after: { type: 'string' },
		tiles: { type: 'string' },
		app: { type: 'string' },
		out: { type: 'string' },
		only: { type: 'string' },
		kinds: { type: 'string', default: 'hillshade,app-2d,app-3d' },
		width: { type: 'string', default: '900' },
		height: { type: 'string', default: '600' }
	}
});
if (!args.after) {
	console.error('usage: node scripts/terrain-compare.mjs --before terrain.pmtiles --after <new file> [--app URL]');
	process.exit(2);
}
const env = harnessEnv();
const tilesDir = resolve(args.tiles ?? env.TILES_DIR);
const out = resolve(args.out ?? join(env.TVT_SCREENS, 'terrain'));
mkdirSync(join(out, 'raw'), { recursive: true });
const manifest = JSON.parse(readFileSync(join(tilesDir, 'manifest.json'), 'utf8'));
const tileSize = manifest.terrain?.tileSize ?? 512;
const viewport = { width: Number(args.width), height: Number(args.height) };

// The foothills above Hulls Gulch and Camel's Back; farmland between Meridian and Kuna.
const PLACES = [
	{ name: 'foothills', lon: -116.175, lat: 43.6478, bearing: 25 },
	{ name: 'valley', lon: -116.42, lat: 43.53, bearing: 20 }
];
const ZOOMS = [10, 13, 15];
const views = PLACES.flatMap((p) => ZOOMS.map((z) => ({ ...p, z, id: `${p.name}-z${z}` }))).filter(
	(v) => !args.only || args.only.split(',').includes(v.id)
);
const kinds = args.kinds.split(',');
if (kinds.some((k) => k.startsWith('app')) && !args.app) {
	console.error('the app views need --app (a running server whose TILES_DIR has both files)');
	process.exit(2);
}

const browser = await chromium.launch({ args: [...CHROMIUM_ARGS, ...lockedArgs()] });
const server = await startCheckServer({ roots: { tiles: tilesDir } });
const results = [];

async function shoot(view, kind, file) {
	const context = await browser.newContext({ viewport });
	const page = await context.newPage();
	const errors = [];
	page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
	page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
	try {
		if (kind === 'hillshade') {
			errors.push(
				...(await openCheck(page, server, {
					dem: `tiles/${file}`,
					tileSize,
					ex: 1,
					lon: view.lon,
					lat: view.lat,
					z: view.z
				}))
			);
		} else {
			await page.route('**/tiles/manifest.json', async (route) => {
				const res = await route.fetch();
				const m = await res.json();
				m.terrain = { ...m.terrain, file };
				await route.fulfill({ response: res, json: m });
			});
			const pitch = kind === 'app-3d' ? 60 : 0;
			const bearing = kind === 'app-3d' ? view.bearing : 0;
			await page.goto(`${args.app}/#${view.z}/${view.lat}/${view.lon}/${bearing}/${pitch}`);
			await mapReady(page, { quietMs: 3000 });
		}
		const path = join(out, 'raw', `${view.id}-${kind}-${file === args.before ? 'a' : 'b'}.png`);
		await page.screenshot({ path, timeout: 180_000 });
		return { path, errors };
	} finally {
		await context.close();
	}
}

/** Before | after | |difference| x8, with captions; returns the difference statistics. */
async function compose(view, kind, a, b) {
	const context = await browser.newContext({ viewport: { width: viewport.width * 3 + 40, height: viewport.height + 70 } });
	const page = await context.newPage();
	try {
		const data = (p) => `data:image/png;base64,${readFileSync(p).toString('base64')}`;
		await page.setContent(`<!doctype html><html><body style="margin:0;background:#2b2a33;font:15px sans-serif;color:#fff">
			<div style="display:flex;gap:10px;padding:10px">
				<figure style="margin:0"><img id="a"><figcaption>before: ${args.before}</figcaption></figure>
				<figure style="margin:0"><img id="b"><figcaption>after: ${args.after}</figcaption></figure>
				<figure style="margin:0"><canvas id="d" width="${viewport.width}" height="${viewport.height}"></canvas>
					<figcaption id="cap">difference x8</figcaption></figure>
			</div><div style="padding:0 10px">${view.id} · ${kind}</div></body></html>`);
		return await page.evaluate(
			async ({ a, b, w, h }) => {
				const load = (id, src) =>
					new Promise((ok) => {
						const img = document.getElementById(id);
						img.onload = () => ok(img);
						img.src = src;
					});
				const [ia, ib] = await Promise.all([load('a', a), load('b', b)]);
				const read = (img) => {
					const c = new OffscreenCanvas(w, h);
					const g = c.getContext('2d');
					g.drawImage(img, 0, 0);
					return g.getImageData(0, 0, w, h).data;
				};
				const pa = read(ia);
				const pb = read(ib);
				const canvas = document.getElementById('d');
				const g = canvas.getContext('2d');
				const diff = g.createImageData(w, h);
				let sum = 0;
				let max = 0;
				let over8 = 0;
				for (let i = 0; i < pa.length; i += 4) {
					const d = Math.max(Math.abs(pa[i] - pb[i]), Math.abs(pa[i + 1] - pb[i + 1]), Math.abs(pa[i + 2] - pb[i + 2]));
					sum += d;
					max = Math.max(max, d);
					if (d > 8) over8++;
					const v = Math.min(255, d * 8);
					diff.data[i] = v;
					diff.data[i + 1] = v;
					diff.data[i + 2] = v;
					diff.data[i + 3] = 255;
				}
				g.putImageData(diff, 0, 0);
				const n = pa.length / 4;
				const stats = { mean: +(sum / n).toFixed(3), max, over8: +((100 * over8) / n).toFixed(3) };
				document.getElementById('cap').textContent =
					`difference x8 · mean ${stats.mean} · max ${stats.max} · ${stats.over8}% of pixels > 8 levels`;
				return stats;
			},
			{ a: data(a), b: data(b), w: viewport.width, h: viewport.height }
		).then(async (stats) => {
			await page.screenshot({ path: join(out, `compare-${view.id}-${kind}.png`), fullPage: true });
			return stats;
		});
	} finally {
		await context.close();
	}
}

try {
	for (const view of views) {
		for (const kind of kinds) {
			const a = await shoot(view, kind, args.before);
			const b = await shoot(view, kind, args.after);
			const diff = await compose(view, kind, a.path, b.path);
			const row = { view: view.id, kind, ...diff, errorsBefore: a.errors, errorsAfter: b.errors };
			results.push(row);
			console.log(
				`${view.id.padEnd(14)} ${kind.padEnd(9)} mean ${String(diff.mean).padStart(6)}  max ${String(diff.max).padStart(3)}  ` +
					`>8: ${String(diff.over8).padStart(6)}%  errors ${a.errors.length}/${b.errors.length}`
			);
			writeFileSync(join(out, 'compare.json'), JSON.stringify({ before: args.before, after: args.after, viewport, results }, null, 1));
		}
	}
} finally {
	await server.close();
	await browser.close();
}
const errors = results.flatMap((r) => [...r.errorsBefore, ...r.errorsAfter]);
console.log(`${results.length} comparisons in ${out}; ${errors.length} console errors`);
process.exit(errors.length ? 1 : 0);
