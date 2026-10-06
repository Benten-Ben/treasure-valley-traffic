#!/usr/bin/env node
/**
 * JavaScript bundle budgets (docs/14 §14.9, "Targets"), from the production
 * build in .svelte-kit/output (run `npm run build` first):
 *
 * - initial JS ≤ 330 KB gzip: SvelteKit's start and app entries plus the
 *   nodes of the `/` route and everything they import statically (the
 *   MapLibre worker is listed separately);
 * - each layer chunk (a dynamic import from src/lib/layers/) ≤ 30 KB brotli;
 * - the scene chunk (src/lib/scene/) ≤ 40 KB gzip.
 *
 * Sizes are gzip (zlib level 6) and brotli (quality 11), computed here, as
 * the harness does everywhere (vite preview doesn't compress like Caddy).
 * Prints a table and writes data/perf/bundle-<time>.json.
 *
 * Exit status: 1 when a budget that applies is exceeded. The initial-JS
 * budget applies from WP2 on (it includes the overlay); until a layer or
 * scene chunk exists, its row reads n/a. `--strict` applies every budget now.
 *
 *   node scripts/bundle-budget.mjs [--strict] [--json]
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { brotliCompressSync, constants, gzipSync } from 'node:zlib';
import { APP_DIR, mainCheckout } from './harness-env.mjs';

const OUT = join(APP_DIR, '.svelte-kit', 'output');
const CLIENT = join(OUT, 'client');
const KB = 1000; // the plan's KB (its 298 KB main chunk is 291.7 KiB)
export const BUDGETS = { initialGzip: 330 * KB, layerBrotli: 30 * KB, sceneGzip: 40 * KB };

const sizes = (file) => {
	const buf = readFileSync(join(CLIENT, file));
	return {
		raw: buf.length,
		gzip: gzipSync(buf, { level: 6 }).length,
		brotli: brotliCompressSync(buf, { params: { [constants.BROTLI_PARAM_QUALITY]: 11 } }).length
	};
};

export async function measure() {
	const viteManifest = join(CLIENT, '.vite', 'manifest.json');
	if (!existsSync(viteManifest)) throw new Error('no build found: run `npm run build` first');
	const vite = JSON.parse(readFileSync(viteManifest, 'utf8'));
	const server = (await import(join(OUT, 'server', 'manifest.js'))).manifest;
	const routes = server.routes ?? server._?.routes;
	const client = server.client ?? server._?.client;
	const root = routes.find((r) => r.page && r.pattern.test('/'));
	if (!root) throw new Error("the build has no page for '/'");
	const nodes = [...root.page.layouts, root.page.leaf].filter((n) => n !== undefined && n !== null);

	// Static-import closure over Vite manifest keys.
	const byFile = new Map(Object.entries(vite).map(([k, v]) => [v.file, k]));
	const seen = new Set();
	const visit = (key) => {
		if (!key || seen.has(key)) return;
		seen.add(key);
		for (const i of vite[key]?.imports ?? []) visit(i);
	};
	for (const f of client.imports ?? [client.start, client.app]) visit(byFile.get(f));
	for (const n of nodes) visit(Object.keys(vite).find((k) => k.endsWith(`/nodes/${n}.js`)));
	const initialFiles = [...seen].map((k) => vite[k].file).filter((f) => f.endsWith('.js'));
	const initial = initialFiles.map((file) => ({ file, ...sizes(file) })).sort((a, b) => b.gzip - a.gzip);
	const total = initial.reduce((s, x) => ({ raw: s.raw + x.raw, gzip: s.gzip + x.gzip, brotli: s.brotli + x.brotli }), { raw: 0, gzip: 0, brotli: 0 });

	const dyn = Object.entries(vite).filter(([, v]) => v.isDynamicEntry && v.src);
	const layers = dyn.filter(([, v]) => /^src\/lib\/layers\//.test(v.src)).map(([, v]) => ({ src: v.src, file: v.file, ...sizes(v.file) }));
	const scene = dyn.filter(([, v]) => /^src\/lib\/scene\//.test(v.src)).map(([, v]) => ({ src: v.src, file: v.file, ...sizes(v.file) }));
	const workers = Object.values(vite).flatMap((v) => v.assets ?? []).filter((f) => /workers\/.*\.js$/.test(f));
	const worker = [...new Set(workers)].map((file) => ({ file, ...sizes(file) }));
	const hasOverlay = Object.values(vite).some((v) => /^src\/lib\/overlay\//.test(v.src ?? '')) ||
		existsSync(join(APP_DIR, 'src', 'lib', 'overlay'));
	return { routeNodes: nodes, initial, total, layers, scene, worker, hasOverlay };
}

const kb = (b) => `${(b / KB).toFixed(1)} KB`;

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
	const strict = process.argv.includes('--strict');
	const m = await measure();
	const rows = [];
	const check = (name, value, limit, applies, note = '') => {
		const ok = value === null ? null : value <= limit;
		rows.push({ name, value: value === null ? 'n/a' : kb(value), limit: kb(limit), status: ok === null ? 'n/a' : ok ? 'ok' : applies ? 'OVER' : 'over (not yet enforced)', note });
		return ok === false && applies;
	};
	let failed = false;
	failed ||= check('initial JS (gzip)', m.total.gzip, BUDGETS.initialGzip, strict || m.hasOverlay,
		m.hasOverlay ? '' : 'enforced once src/lib/overlay exists (WP2)');
	for (const l of m.layers) failed = check(`layer ${l.src} (brotli)`, l.brotli, BUDGETS.layerBrotli, true) || failed;
	if (!m.layers.length) check('layer chunks (brotli)', null, BUDGETS.layerBrotli, false, 'none yet (WP2)');
	for (const s of m.scene) failed = check(`scene ${s.src} (gzip)`, s.gzip, BUDGETS.sceneGzip, true) || failed;
	if (!m.scene.length) check('scene chunk (gzip)', null, BUDGETS.sceneGzip, false, 'none yet (WP9)');

	if (process.argv.includes('--json')) console.log(JSON.stringify({ ...m, rows }, null, 2));
	else {
		console.log(`initial JS for '/' (nodes ${m.routeNodes.join(', ')}): ${m.initial.length} files, ` +
			`${kb(m.total.raw)} raw, ${kb(m.total.gzip)} gzip, ${kb(m.total.brotli)} brotli`);
		for (const f of m.initial.slice(0, 5)) console.log(`  ${f.file.padEnd(48)} ${kb(f.gzip).padStart(10)} gzip`);
		for (const w of m.worker) console.log(`worker ${w.file}: ${kb(w.gzip)} gzip, ${kb(w.brotli)} brotli`);
		console.table(rows);
	}
	try {
		const dir = join(mainCheckout(), 'data', 'perf');
		mkdirSync(dir, { recursive: true });
		writeFileSync(join(dir, `bundle-${new Date().toISOString().replace(/[:.]/g, '-')}.json`), JSON.stringify({ ...m, rows }, null, 2));
	} catch {
		/* the printout is what matters */
	}
	process.exit(failed ? 1 : 0);
}
