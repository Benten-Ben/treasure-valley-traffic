/**
 * A bare terrain page for WP17 (docs/14 §14.10, "Terrain re-encode"): MapLibre
 * with nothing but a terrain-RGB source, its hillshade and, in `terrain` mode,
 * the 3D surface. The e2e spec uses it to check that the browser decodes WebP
 * terrain exactly like PNG, and terrain-compare.mjs uses it for before/after
 * screenshots of the hillshade on its own.
 *
 * It runs on its own small server on 127.0.0.1 (not the app's), so the page,
 * MapLibre's module worker and the terrain files are all same-origin and need
 * no request routing. The server answers byte ranges, which is all pmtiles needs.
 *
 *   const server = await startCheckServer({ roots: { tiles: TILES_DIR } });
 *   const errors = await openCheck(page, server, { dem: 'tiles/terrain.pmtiles', z: 13, lon, lat });
 *   await page.evaluate((pts) => __check.sample(pts), [[lon, lat]]);   // metres (x exaggeration)
 *   await server.close();
 *
 * Page parameters: dem (a path on this server), tileSize (512), mode
 * (`hillshade`, or `terrain` for the 3D surface), terrainEx (1), ex
 * (hillshade-exaggeration, 0.3 like the app), lon, lat, z, pitch, bearing.
 */
import { createReadStream, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { dirname, join, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const APP_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const LIB = {
	'maplibre-gl.mjs': 'node_modules/maplibre-gl/dist/maplibre-gl.mjs',
	'maplibre-gl-shared.mjs': 'node_modules/maplibre-gl/dist/maplibre-gl-shared.mjs',
	'maplibre-gl-worker.mjs': 'node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs',
	'maplibre-gl.css': 'node_modules/maplibre-gl/dist/maplibre-gl.css',
	'pmtiles.js': 'node_modules/pmtiles/dist/pmtiles.js'
};
const TYPES = { '.mjs': 'text/javascript', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json' };

export const CHECK_HTML = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Terrain check</title>
<link rel="stylesheet" href="lib/maplibre-gl.css">
<style>html, body { margin: 0; height: 100%; background: #f4efe6; } #map { position: absolute; inset: 0; }</style>
</head>
<body>
<div id="map"></div>
<script src="lib/pmtiles.js"></script>
<script type="module">
import { Map, addProtocol, setWorkerUrl } from './lib/maplibre-gl.mjs';
const q = new URLSearchParams(location.search);
const num = (k, d) => (q.has(k) ? Number(q.get(k)) : d);
const errors = [];
addEventListener('error', (e) => errors.push(String(e.message)));
addEventListener('unhandledrejection', (e) => errors.push(String(e.reason)));
setWorkerUrl(new URL('lib/maplibre-gl-worker.mjs', location.href).href);
addProtocol('pmtiles', new pmtiles.Protocol({ metadata: true }).tile);
const dem = { type: 'raster-dem', url: 'pmtiles://' + new URL(q.get('dem'), location.href).href,
	tileSize: num('tileSize', 512), encoding: 'mapbox' };
const style = {
	version: 8,
	sources: { dem, hillshade: { ...dem } },
	layers: [
		{ id: 'background', type: 'background', paint: { 'background-color': '#f4efe6' } },
		{ id: 'hillshade', type: 'hillshade', source: 'hillshade', paint: { 'hillshade-exaggeration': num('ex', 0.3) } }
	]
};
if (q.get('mode') === 'terrain') style.terrain = { source: 'dem', exaggeration: num('terrainEx', 1) };
const map = new Map({
	container: 'map', style, center: [num('lon', 0), num('lat', 0)], zoom: num('z', 12),
	pitch: num('pitch', 0), bearing: num('bearing', 0), maxPitch: 85, attributionControl: false, fadeDuration: 0
});
map.on('error', (e) => errors.push(String(e.error?.message ?? e.error ?? e)));
globalThis.__check = {
	map, errors,
	ready: new Promise((ok) => map.once('load', () => map.once('idle', () => ok(true)))),
	sample: (points) => points.map(([lon, lat]) => map.queryTerrainElevation([lon, lat]))
};
</script>
</body>
</html>
`;

/** Serve a file, honouring a single byte range (pmtiles reads archives in ranges). */
function sendFile(req, res, file, type = 'application/octet-stream') {
	let st;
	try {
		st = statSync(file);
	} catch {
		res.writeHead(404).end('Not found');
		return;
	}
	if (!st.isFile()) {
		res.writeHead(404).end('Not found');
		return;
	}
	const headers = {
		'Content-Type': type,
		'Accept-Ranges': 'bytes',
		ETag: `"${st.mtimeMs.toString(36)}-${st.size.toString(36)}"`,
		'Cache-Control': 'no-cache'
	};
	const m = /^bytes=(\d*)-(\d*)$/.exec(String(req.headers.range ?? ''));
	if (m && (m[1] !== '' || m[2] !== '')) {
		const start = m[1] === '' ? Math.max(0, st.size - Number(m[2])) : Number(m[1]);
		const end = m[1] === '' || m[2] === '' ? st.size - 1 : Math.min(Number(m[2]), st.size - 1);
		if (start >= st.size || end < start) {
			res.writeHead(416, { 'Content-Range': `bytes */${st.size}` }).end();
			return;
		}
		res.writeHead(206, { ...headers, 'Content-Range': `bytes ${start}-${end}/${st.size}`, 'Content-Length': end - start + 1 });
		if (req.method === 'HEAD') res.end();
		else createReadStream(file, { start, end }).pipe(res);
		return;
	}
	res.writeHead(200, { ...headers, 'Content-Length': st.size });
	if (req.method === 'HEAD') res.end();
	else createReadStream(file).pipe(res);
}

/**
 * Start the page's server on 127.0.0.1 (an ephemeral port). `roots` maps a
 * first path segment to a folder, e.g. { tiles: TILES_DIR, fixture: dir }.
 * Resolves to { url, requests, close() }; `requests` lists [status, path, range].
 */
export function startCheckServer({ roots = {} } = {}) {
	const folders = Object.fromEntries(Object.entries(roots).map(([k, v]) => [k, resolve(v)]));
	const requests = [];
	const server = createServer((req, res) => {
		const path = decodeURIComponent(new URL(req.url ?? '/', 'http://x').pathname);
		res.on('finish', () => requests.push([res.statusCode, path, req.headers.range ?? null]));
		if (req.method !== 'GET' && req.method !== 'HEAD') return void res.writeHead(405).end();
		if (path === '/' || path === '/index.html') {
			res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-cache' });
			return void res.end(CHECK_HTML);
		}
		const [, first, ...rest] = path.split('/');
		if (first === 'lib' && rest.length === 1 && LIB[rest[0]]) {
			const ext = rest[0].slice(rest[0].lastIndexOf('.'));
			return sendFile(req, res, join(APP_DIR, LIB[rest[0]]), TYPES[ext]);
		}
		const root = folders[first];
		const file = root ? resolve(join(root, ...rest)) : '';
		if (!root || path.includes('\0') || !file.startsWith(root + sep)) return void res.writeHead(404).end('Not found');
		return sendFile(req, res, file);
	});
	return new Promise((ok, fail) => {
		server.once('error', fail);
		server.listen(0, '127.0.0.1', () => {
			const { port } = /** @type {import('node:net').AddressInfo} */ (server.address());
			ok({
				url: `http://127.0.0.1:${port}/`,
				requests,
				close: () => new Promise((done) => server.close(() => done(undefined)))
			});
		});
	});
}

/**
 * Open the page with the given parameters and wait for the map's first `idle`.
 * Returns the errors the page saw (map errors, uncaught errors, console errors).
 */
export async function openCheck(page, server, params, { timeout = 180_000 } = {}) {
	const consoleErrors = [];
	const onConsole = (m) => m.type() === 'error' && consoleErrors.push(m.text());
	page.on('console', onConsole);
	try {
		const qs = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]));
		await page.goto(`${server.url}?${qs}`);
		await page.waitForFunction(() => globalThis.__check, null, { timeout });
		await page.evaluate(
			(ms) => Promise.race([globalThis.__check.ready, new Promise((_, no) => setTimeout(() => no(new Error('no idle')), ms))]),
			timeout
		);
		const errors = await page.evaluate(() => globalThis.__check.errors);
		return [...errors, ...consoleErrors];
	} finally {
		page.off('console', onConsole);
	}
}
