import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createServer, request, type Server } from 'node:http';
import { mkdir, mkdtemp, readFile, rm, utimes, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';
import { MANIFEST_CACHE_CONTROL, tilesHandler, TILES_CACHE_CONTROL } from './tiles-static.js';

/**
 * WP5's Caddy edits (docs/14 §14.9, fix 6) and their mirror: the /tiles/
 * block in deploy/Caddyfile and the dev and preview tiles server must agree.
 */
const CADDYFILE = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../deploy/Caddyfile');

/** The body of the `handle_path /tiles/* { … }` block. */
async function tilesBlock(): Promise<string> {
	const text = await readFile(CADDYFILE, 'utf8');
	const start = text.indexOf('handle_path /tiles/* {');
	expect(start).toBeGreaterThan(-1);
	let depth = 0;
	for (let i = text.indexOf('{', start); i < text.length; i++) {
		if (text[i] === '{') depth++;
		if (text[i] === '}' && --depth === 0) return text.slice(start, i + 1);
	}
	throw new Error('unbalanced /tiles/ block');
}

describe('deploy/Caddyfile /tiles/ and its mirror', () => {
	it('sends manifest.json no-cache and everything else max-age=3600, as the mirror does', async () => {
		const block = (await tilesBlock()).replace(/#.*$/gm, '');
		expect(block).toMatch(/@manifest\s+path\s+\/manifest\.json/);
		expect(block).toMatch(/@files\s+not\s+path\s+\/manifest\.json/);
		expect(block).toContain(`header @manifest Cache-Control "${MANIFEST_CACHE_CONTROL}"`);
		expect(block).toContain(`header @files Cache-Control "${TILES_CACHE_CONTROL}"`);
		// Exactly one Cache-Control per file: no unmatched header line left.
		expect(block.match(/header\s+Cache-Control/g)).toBeNull();
	});

	it('serves precompressed gzip glyphs', async () => {
		expect((await tilesBlock()).replace(/#.*$/gm, '')).toMatch(/file_server\s*\{[^}]*precompressed\s+gzip[^}]*\}/);
	});
});

describe('the mirror serves a .gz sidecar as Caddy does', () => {
	let dir: string;
	let server: Server;
	let base: string;
	const glyph = Buffer.from('fake glyph range 0-255 '.repeat(40));
	const plainTime = new Date('2026-10-05T08:36:00Z');
	const gzTime = new Date('2026-10-07T12:00:00Z');

	beforeAll(async () => {
		dir = await mkdtemp(join(tmpdir(), 'tvt-tiles-caddy-'));
		await mkdir(join(dir, 'fonts', 'Noto Sans Regular'), { recursive: true });
		const plain = join(dir, 'fonts', 'Noto Sans Regular', '0-255.pbf');
		await writeFile(plain, glyph);
		await writeFile(`${plain}.gz`, gzipSync(glyph));
		await writeFile(join(dir, 'manifest.json'), '{}');
		await utimes(plain, plainTime, plainTime);
		await utimes(`${plain}.gz`, gzTime, gzTime);
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

	const head = (path: string, headers: Record<string, string>) =>
		new Promise<Record<string, string | string[] | undefined>>((ok, fail) => {
			const req = request(`${base}${path}`, { headers, method: 'HEAD' }, (res) => {
				res.resume();
				ok(res.headers);
			});
			req.on('error', fail);
			req.end();
		});

	it("takes the sidecar's ETag and the original's Last-Modified, without Accept-Ranges", async () => {
		const gz = await head('/fonts/Noto%20Sans%20Regular/0-255.pbf', { 'accept-encoding': 'gzip' });
		const plain = await head('/fonts/Noto%20Sans%20Regular/0-255.pbf', {});
		expect(gz['content-encoding']).toBe('gzip');
		expect(gz['etag']).not.toBe(plain['etag']);
		expect(gz['last-modified']).toBe(plainTime.toUTCString());
		expect(plain['last-modified']).toBe(plainTime.toUTCString());
		expect(gz['accept-ranges']).toBeUndefined();
		expect(plain['accept-ranges']).toBe('bytes');
		expect(gz['vary']).toBe('Accept-Encoding');
		expect(plain['vary']).toBe('Accept-Encoding');
	});

	it('sends the manifest no-cache', async () => {
		expect((await head('/manifest.json', {}))['cache-control']).toBe('no-cache');
	});
});
