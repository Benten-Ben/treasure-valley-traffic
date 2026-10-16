#!/usr/bin/env node
/**
 * The ground's first load, measured with the map library itself (landscape sprint G1a): which of the ground's
 * PMTiles bytes a first visit in Valley fetches at the default view, before the app wires the ground in (S3a).
 *
 *   node scripts/ground-firstload.mjs --pmtiles <ground-....pmtiles> [--center -116.4,43.6] [--zoom 10]
 *        [--pitch 45] [--viewport 1280x800] [--out result.json]
 *
 * A bare page in headless Chromium (Playwright) with MapLibre (the app's version), the pmtiles protocol (the app's
 * version) and one raster source, the ground file, 512 px tiles, z8-z15, over the flat Valley background: the same
 * request pattern the app will make (the header and root directory, any leaf directories, then each tile as a range
 * request). The file is served from a local server that answers HTTP range requests and logs each one. It prints
 * the requests and bytes, and the tiles (z/x/y) the view drew, so a partial file (G1a paints only some tiles) can be
 * checked for holes: every tile the view asks for must be in it, or the result says which are missing.
 * The budget (basemap/ground/spec.json "budget"): at most 600,000 bytes in at most 14 requests.
 * No terrain, no other layers: the ground's own share of a first load.
 */
import { createServer } from 'node:http';
import { createReadStream, readFileSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const here = dirname(fileURLToPath(import.meta.url));
const app = resolve(here, '..');
const args = process.argv.slice(2);
const opt = (name, def) => {
	const i = args.indexOf(name);
	return i >= 0 ? args[i + 1] : def;
};
const pm = opt('--pmtiles');
if (!pm) {
	console.error('give --pmtiles <file>');
	process.exit(2);
}
const [lon, lat] = opt('--center', '-116.4,43.6').split(',').map(Number);
const zoom = Number(opt('--zoom', '10'));
const pitch = Number(opt('--pitch', '45'));
const [vw, vh] = opt('--viewport', '1280x800').split('x').map(Number);
const spec = JSON.parse(readFileSync(resolve(app, '../basemap/ground/spec.json'), 'utf8'));

const page = `<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/maplibre/maplibre-gl.css">
<style>html,body,#map{margin:0;width:100%;height:100%}</style></head><body><div id="map"></div>
<script src="/pmtiles/pmtiles.js"></script>
<script type="module">
import * as maplibregl from '/maplibre/maplibre-gl.mjs';
const protocol = new pmtiles.Protocol();
maplibregl.addProtocol('pmtiles', protocol.tile);
const map = new maplibregl.Map({ container: 'map', center: [${lon}, ${lat}], zoom: ${zoom}, pitch: ${pitch},
  attributionControl: false, fadeDuration: 0,
  style: { version: 8, sources: { ground: { type: 'raster', url: 'pmtiles://' + location.origin + '/ground.pmtiles',
    tileSize: ${spec.tiles.tileSize} } },
    layers: [{ id: 'flat', type: 'background', paint: { 'background-color': '${spec.flat.valley}' } },
             { id: 'ground', type: 'raster', source: 'ground' }] } });
const drawn = new Set();
map.on('sourcedata', (e) => { if (e.tile && e.sourceId === 'ground') drawn.add(e.tile.tileID.canonical.z + '/' +
  e.tile.tileID.canonical.x + '/' + e.tile.tileID.canonical.y); });
map.on('idle', () => { window.__done = { drawn: [...drawn].sort() }; });
</script></body></html>`;

const log = [];
const size = statSync(pm).size;
const pmtilesDist = join(app, 'node_modules/pmtiles/dist');
const server = createServer((req, res) => {
	const url = new URL(req.url, 'http://x');
	if (url.pathname === '/') {
		res.writeHead(200, { 'content-type': 'text/html' });
		return res.end(page);
	}
	if (url.pathname.startsWith('/maplibre/') || url.pathname.startsWith('/pmtiles/')) {
		const base = url.pathname.startsWith('/maplibre/') ? join(app, 'node_modules/maplibre-gl/dist') : pmtilesDist;
		const file = join(base, url.pathname.split('/').slice(2).join('/'));
		try {
			const body = readFileSync(file);
			const type = file.endsWith('.css') ? 'text/css' : 'text/javascript';
			res.writeHead(200, { 'content-type': type });
			return res.end(body);
		} catch {
			res.writeHead(404);
			return res.end();
		}
	}
	if (url.pathname === '/ground.pmtiles') {
		const m = /bytes=(\d+)-(\d+)/.exec(req.headers.range || '');
		const start = m ? Number(m[1]) : 0;
		const end = Math.min(m ? Number(m[2]) : size - 1, size - 1);
		log.push({ start, end, bytes: end - start + 1 });
		res.writeHead(m ? 206 : 200, { 'content-type': 'application/octet-stream', 'accept-ranges': 'bytes',
			'content-length': end - start + 1, 'content-range': `bytes ${start}-${end}/${size}` });
		return createReadStream(pm, { start, end }).pipe(res);
	}
	res.writeHead(404);
	res.end();
});
await new Promise((ok) => server.listen(0, '127.0.0.1', ok));
const origin = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
try {
	const p = await browser.newPage({ viewport: { width: vw, height: vh } });
	const errors = [];
	p.on('pageerror', (e) => errors.push(String(e)));
	p.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
	await p.goto(origin + '/');
	await p.waitForFunction(() => window.__done, null, { timeout: 60000 }).catch((e) => {
		console.error(errors.join('\n'));
		throw e;
	});
	await p.waitForFunction(() => window.__done, null, { timeout: 60000 });
	const { drawn } = await p.evaluate(() => window.__done);
	const bytes = log.reduce((a, r) => a + r.bytes, 0);
	const budget = spec.budget.valleyDefault;
	const result = {
		view: { center: [lon, lat], zoom, pitch, viewport: [vw, vh] }, file: pm, fileBytes: size,
		requests: log.length, bytes, budget, ok: bytes <= budget.maxBytes && log.length <= budget.maxRequests,
		tiles: drawn, ranges: log
	};
	console.log(JSON.stringify({ ...result, ranges: undefined }, null, 1));
	const out = opt('--out');
	if (out) writeFileSync(out, JSON.stringify(result, null, 1));
} finally {
	await browser.close();
	server.close();
}
