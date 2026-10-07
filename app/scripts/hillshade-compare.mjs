#!/usr/bin/env node
/**
 * Side-by-side hillshade screenshots of the two options (docs/14 §14.9,
 * fix 1; WP5; the owner's Q7 sign-off): `?hillshade=terrain` (the default:
 * the hillshade reads the 3D terrain's own tiles) on the left and
 * `?hillshade=capped` (a second DEM source capped at z12) on the right, at
 * z10 (the default view), z13 and z16 over the Boise foothills, in the Valley
 * look with no data layers and the UI hidden.
 *
 * Writes hillshade-<view>-<option>.png, hillshade-<view>.png (the pair) and
 * hillshade-compare.png (all three rows) to $TVT_SCREENS (git-ignored), from
 * the package's preview server (started when it isn't running).
 *
 *   node scripts/hillshade-compare.mjs [--url http://127.0.0.1:5206] [--size 800x560]
 */
import { spawn } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { chromium } from '@playwright/test';
import { APP_DIR, CHROMIUM_ARGS, harnessEnv, lockedArgs } from './harness-env.mjs';
import { mapReady } from './net.mjs';

const argv = process.argv.slice(2);
const opt = (n, d) => {
	const i = argv.indexOf(n);
	return i === -1 ? d : argv[i + 1];
};
const env = harnessEnv();
Object.assign(process.env, env);
const [W, H] = opt('--size', '800x560').split('x').map(Number);
const OUT = env.TVT_SCREENS;
const OPTIONS = ['terrain', 'capped'];
const VIEWS = [
	{ id: 'z10', title: 'z10, the default view (pitch 45)', hash: 'map=10/43.6/-116.4/0/45' },
	{ id: 'z13', title: 'z13, Boise foothills (pitch 0)', hash: 'map=13/43.622/-116.172/0/0' },
	{ id: 'z16', title: 'z16, Table Rock (pitch 0)', hash: 'map=16/43.6043/-116.1633/0/0' }
];
const LABEL = {
	terrain: 'hillshade=terrain (default): one DEM source',
	capped: 'hillshade=capped: second source, capped at z12'
};

async function healthy(base) {
	try {
		return (await fetch(`${base}/api/health`)).ok;
	} catch {
		return false;
	}
}

async function server() {
	if (opt('--url')) return { base: opt('--url').replace(/\/$/, ''), stop: () => {} };
	const base = `http://127.0.0.1:${env.TVT_PORT}`;
	if (await healthy(base)) return { base, stop: () => {} };
	const child = spawn('node', ['scripts/e2e-server.mjs'], { cwd: APP_DIR, env: { ...process.env, ...env }, stdio: 'ignore' });
	for (let i = 0; i < 600 && !(await healthy(base)); i++) await new Promise((r) => setTimeout(r, 1000));
	if (!(await healthy(base))) throw new Error(`the preview server didn't start on ${base}`);
	return { base, stop: () => child.kill('SIGTERM') };
}

const srv = await server();
const browser = await chromium.launch({ args: [...CHROMIUM_ARGS, ...lockedArgs([new URL(srv.base).hostname])] });
mkdirSync(OUT, { recursive: true });
const shots = {};
try {
	for (const v of VIEWS) {
		for (const o of OPTIONS) {
			const context = await browser.newContext({ viewport: { width: W, height: H }, baseURL: srv.base });
			const page = await context.newPage();
			// The Valley look, saved on a page of the same origin that doesn't start the map.
			await page.goto('/api/health');
			await page.evaluate(() => localStorage.setItem('tvt:v2:base', JSON.stringify({ look: 'map', buildings: true, terrain: true, labels: 'full' })));
			await page.goto(`/?hillshade=${o}#${v.hash}&layers=none`);
			await mapReady(page);
			const source = await page.evaluate(() => globalThis.__tvt.map.getLayer('hillshade')?.source);
			if (source !== (o === 'terrain' ? 'terrain' : 'hillshade')) throw new Error(`${o}: the hillshade reads ${source}`);
			// Only the map: hide the chrome around it.
			await page.addStyleTag({ content: 'body * { visibility: hidden !important } .maplibregl-canvas-container, .maplibregl-canvas-container * { visibility: visible !important }' });
			await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
			const file = join(OUT, `hillshade-${v.id}-${o}.png`);
			await page.screenshot({ path: file });
			shots[`${v.id}-${o}`] = file;
			process.stderr.write(`${v.id} ${o}: ${file}\n`);
			await context.close();
		}
	}

	// The pairs, and all three rows in one image.
	const img = (f) => `data:image/png;base64,${readFileSync(f).toString('base64')}`;
	const row = (v) => `
		<section><h2>${v.title}</h2><div class="pair">
		${OPTIONS.map((o) => `<figure><img src="${img(shots[`${v.id}-${o}`])}"><figcaption>${LABEL[o]}</figcaption></figure>`).join('')}
		</div></section>`;
	const page = await browser.newPage({ viewport: { width: 2 * W + 48, height: 400 } });
	const css = `body { margin: 0; padding: 12px 16px; background: #f4f1ea; font: 14px system-ui, sans-serif; color: #24303c }
		h2 { font-size: 15px; margin: 8px 0 6px } .pair { display: flex; gap: 16px } figure { margin: 0 }
		img { display: block; width: ${W}px; height: ${H}px; border-radius: 6px } figcaption { margin-top: 4px }`;
	for (const v of VIEWS) {
		await page.setContent(`<style>${css}</style>${row(v)}`);
		await page.screenshot({ path: join(OUT, `hillshade-${v.id}.png`), fullPage: true });
	}
	await page.setContent(`<style>${css}</style>${VIEWS.map(row).join('')}`);
	await page.screenshot({ path: join(OUT, 'hillshade-compare.png'), fullPage: true });
	writeFileSync(join(OUT, 'hillshade-compare.txt'), `${VIEWS.map((v) => `hillshade-${v.id}.png: ${v.title}; left ${LABEL.terrain}; right ${LABEL.capped}`).join('\n')}\n`);
	console.log(`hillshade screenshots in ${OUT}`);
} finally {
	await browser.close();
	srv.stop();
}
