import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createServer, type Server } from 'node:http';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { gzipSync } from 'node:zlib';
import { parseRange, tilesHandler, TILES_CACHE_CONTROL } from './tiles-static.js';

// A small fixture folder shaped like data/tiles.
let dir: string;
let server: Server;
let base: string;
const archive = Buffer.from(Array.from({ length: 4096 }, (_, i) => i % 251));
const glyph = Buffer.from('fake glyph range 0-255 '.repeat(40));

beforeAll(async () => {
	dir = await mkdtemp(join(tmpdir(), 'tvt-tiles-'));
	await mkdir(join(dir, 'fonts', 'Noto Sans Regular'), { recursive: true });
	await writeFile(join(dir, 'manifest.json'), JSON.stringify({ basemap: { built: '2026-10-05' } }));
	await writeFile(join(dir, 'valley.pmtiles'), archive);
	await writeFile(join(dir, 'fonts', 'Noto Sans Regular', '0-255.pbf'), glyph);
	await writeFile(join(dir, 'fonts', 'Noto Sans Regular', '0-255.pbf.gz'), gzipSync(glyph));
	await writeFile(join(dir, 'fonts', 'Noto Sans Regular', '256-511.pbf'), glyph);
	const handler = tilesHandler(dir);
	server = createServer((req, res) => handler(req, res));
	await new Promise<void>((ok) => server.listen(0, '127.0.0.1', ok));
	const addr = server.address();
	base = `http://127.0.0.1:${typeof addr === 'object' && addr ? addr.port : 0}`;
});

afterAll(async () => {
	await new Promise((ok) => server.close(ok));
	await rm(dir, { recursive: true, force: true });
});

/** Raw fetch (no automatic decompression), so Content-Encoding can be checked. */
async function get(path: string, headers: Record<string, string> = {}, method = 'GET') {
	const { request } = await import('node:http');
	return new Promise<{ status: number; headers: Record<string, string | string[] | undefined>; body: Buffer }>(
		(ok, fail) => {
			const req = request(`${base}${path}`, { headers, method }, (res) => {
				const chunks: Buffer[] = [];
				res.on('data', (c) => chunks.push(c));
				res.on('end', () => ok({ status: res.statusCode ?? 0, headers: res.headers, body: Buffer.concat(chunks) }));
			});
			req.on('error', fail);
			req.end();
		}
	);
}

describe('the /tiles/ server mirrors Caddy', () => {
	it('serves a glyph range with a .gz sibling precompressed', async () => {
		const r = await get('/fonts/Noto%20Sans%20Regular/0-255.pbf', { 'accept-encoding': 'gzip, br' });
		expect(r.status).toBe(200);
		expect(r.headers['content-encoding']).toBe('gzip');
		expect(r.headers['content-type']).toBe('application/x-protobuf');
		expect(r.headers['vary']).toBe('Accept-Encoding');
		expect(r.headers['cache-control']).toBe(TILES_CACHE_CONTROL);
		expect(r.body.equals(gzipSync(glyph))).toBe(true);
	});

	it('serves the plain glyph to clients without gzip, and when there is no sibling', async () => {
		const plain = await get('/fonts/Noto%20Sans%20Regular/0-255.pbf');
		expect(plain.headers['content-encoding']).toBeUndefined();
		expect(plain.body.equals(glyph)).toBe(true);
		const noSibling = await get('/fonts/Noto%20Sans%20Regular/256-511.pbf', { 'accept-encoding': 'gzip' });
		expect(noSibling.headers['content-encoding']).toBeUndefined();
		expect(noSibling.body.equals(glyph)).toBe(true);
	});

	it('answers manifest.json with no-cache', async () => {
		const r = await get('/manifest.json');
		expect(r.status).toBe(200);
		expect(r.headers['cache-control']).toBe('no-cache');
		expect(JSON.parse(r.body.toString()).basemap.built).toBe('2026-10-05');
	});

	it('answers other files with public, max-age=3600, a strong ETag, and working ranges', async () => {
		const full = await get('/valley.pmtiles');
		expect(full.status).toBe(200);
		expect(full.headers['cache-control']).toBe('public, max-age=3600');
		// Caddy's form: "<mtime ns, base 36><size, base 36>", not a weak W/ tag (pmtiles ignores those).
		expect(full.headers['etag']).toMatch(new RegExp(`^"[0-9a-z]+${archive.length.toString(36)}"$`));
		expect(full.headers['accept-ranges']).toBe('bytes');
		const part = await get('/valley.pmtiles', { range: 'bytes=100-199' });
		expect(part.status).toBe(206);
		expect(part.headers['content-range']).toBe(`bytes 100-199/${archive.length}`);
		expect(part.headers['cache-control']).toBe('public, max-age=3600');
		expect(part.body.equals(archive.subarray(100, 200))).toBe(true);
		const again = await get('/valley.pmtiles', { 'if-none-match': String(full.headers['etag']) });
		expect(again.status).toBe(304);
	});

	it('handles suffix ranges, unsatisfiable ranges, If-Range and HEAD like Go', async () => {
		const tail = await get('/valley.pmtiles', { range: 'bytes=-96' });
		expect(tail.status).toBe(206);
		expect(tail.headers['content-range']).toBe(`bytes ${archive.length - 96}-${archive.length - 1}/${archive.length}`);
		expect(tail.body.equals(archive.subarray(archive.length - 96))).toBe(true);
		const past = await get('/valley.pmtiles', { range: `bytes=${archive.length}-` });
		expect(past.status).toBe(416);
		expect(past.headers['content-range']).toBe(`bytes */${archive.length}`);
		const stale = await get('/valley.pmtiles', { range: 'bytes=0-9', 'if-range': '"not-it"' });
		expect(stale.status).toBe(200);
		expect(stale.body.length).toBe(archive.length);
		const head = await get('/valley.pmtiles', { range: 'bytes=0-9' }, 'HEAD');
		expect(head.status).toBe(206);
		expect(head.headers['content-length']).toBe('10');
		expect(head.body.length).toBe(0);
		expect((await get('/valley.pmtiles', {}, 'POST')).status).toBe(405);
		expect(parseRange('bytes=5-2', 10)).toBeNull();
		expect(parseRange('bytes=0-1,4-5', 10)).toBeNull();
	});

	it('answers 404 for missing files, paths outside the folder, and a missing tiles folder', async () => {
		expect((await get('/../package.json')).status).toBe(404);
		expect((await get('/%2e%2e/%2e%2e/etc/passwd')).status).toBe(404);
		expect((await get('/nope.pmtiles')).status).toBe(404);
		const handler = tilesHandler(join(dir, 'does-not-exist'));
		const res = { statusCode: 0, setHeader() {}, end() {} };
		handler({} as never, res as never);
		expect(res.statusCode).toBe(404);
	});
});
