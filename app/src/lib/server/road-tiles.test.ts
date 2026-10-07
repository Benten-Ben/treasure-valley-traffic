import { beforeEach, describe, expect, it, vi } from 'vitest';
import { gunzipSync } from 'node:zlib';
import { IMMUTABLE, versionedCacheControl } from './cache-headers.js';
import { ByteLru, classesAt, parseTile, roadTileServer, SHORT_CACHE, type TileId } from './road-tiles.js';

/** A fake MVT: deterministic bytes, repetitive enough to compress. */
const mvt = (t: TileId) => new TextEncoder().encode(`roads ${t.z}/${t.x}/${t.y} `.repeat(200));

function server(version: string | null = 'r1', cut = vi.fn(async (t: TileId) => mvt(t))) {
	let v = version;
	const s = roadTileServer({ version: async () => v, cut });
	return { s, cut, setVersion: (x: string | null) => (v = x) };
}

const T = { z: 12, x: 760, y: 1490 };

describe('road tiles (docs/14 §14.9 fix 5)', () => {
	it('answers gzip with immutable caching for the current version', async () => {
		const { s } = server('r1');
		const res = await s.respond(T, 'r1', 'gzip, deflate, br');
		expect(res.status).toBe(200);
		expect(res.headers.get('content-encoding')).toBe('gzip');
		expect(res.headers.get('content-type')).toBe('application/vnd.mapbox-vector-tile');
		expect(res.headers.get('cache-control')).toBe(IMMUTABLE);
		expect(res.headers.get('cache-control')).toContain('immutable');
		expect(res.headers.get('vary')).toBe('Accept-Encoding');
		const body = new Uint8Array(await res.arrayBuffer());
		expect(gunzipSync(body)).toEqual(Buffer.from(mvt(T)));
		expect(body.length).toBeLessThan(mvt(T).length / 4);
	});

	it('answers max-age=60 for an old version, no version, or when there is no current one', async () => {
		const { s, setVersion } = server('r2');
		for (const v of ['r1', null, '']) {
			const res = await s.respond(T, v, 'gzip');
			expect(res.headers.get('cache-control')).toBe(SHORT_CACHE);
			expect(res.headers.get('cache-control')).toBe('public, max-age=60');
			expect(res.headers.get('content-encoding')).toBe('gzip');
		}
		setVersion(null);
		expect((await s.respond(T, 'r2', 'gzip')).headers.get('cache-control')).toBe('public, max-age=60');
	});

	it('cuts each tile once per version: the cache and concurrent requests share it', async () => {
		const { s, cut, setVersion } = server('r1');
		await Promise.all([s.respond(T, 'r1', 'gzip'), s.respond(T, 'r1', 'gzip'), s.respond(T, null, 'gzip')]);
		expect(cut).toHaveBeenCalledTimes(1);
		await s.respond(T, 'r1', 'gzip');
		expect(cut).toHaveBeenCalledTimes(1);
		setVersion('r2');
		await s.respond(T, 'r2', 'gzip');
		expect(cut).toHaveBeenCalledTimes(2);
		expect(s.cuts).toBe(2);
	});

	it('sends plain MVT to a client that does not accept gzip', async () => {
		const { s } = server('r1');
		for (const ae of [null, 'identity', 'br', 'gzip;q=0']) {
			const res = await s.respond(T, 'r1', ae);
			expect(res.headers.get('content-encoding')).toBeNull();
			expect(new Uint8Array(await res.arrayBuffer())).toEqual(mvt(T));
		}
	});

	it('sends an empty tile empty, without an encoding', async () => {
		const { s } = server('r1', vi.fn(async () => new Uint8Array()));
		const res = await s.respond(T, 'r1', 'gzip');
		expect(res.status).toBe(200);
		expect(res.headers.get('content-encoding')).toBeNull();
		expect((await res.arrayBuffer()).byteLength).toBe(0);
		expect(res.headers.get('cache-control')).toBe(IMMUTABLE);
	});

	it('has a strong ETag per version and encoding, and answers 304 to it', async () => {
		const { s } = server('r1');
		const a = await s.respond(T, 'r1', 'gzip');
		const b = await s.respond(T, 'r1', null);
		expect(a.headers.get('etag')).toBe('"roads-r1-gz"');
		expect(b.headers.get('etag')).toBe('"roads-r1"');
		const c = await s.respond(T, null, 'gzip', '"roads-r1-gz"');
		expect(c.status).toBe(304);
		expect(c.headers.get('cache-control')).toBe('public, max-age=60');
		expect((await s.respond(T, null, 'gzip', '"roads-r0-gz"')).status).toBe(200);
	});

	it("doesn't cache a failed cut", async () => {
		let fail = true;
		const cut = vi.fn(async (t: TileId) => {
			if (fail) throw new Error('database down');
			return mvt(t);
		});
		const { s } = server('r1', cut);
		await expect(s.respond(T, 'r1', 'gzip')).rejects.toThrow('database down');
		fail = false;
		expect((await s.respond(T, 'r1', 'gzip')).status).toBe(200);
		expect(cut).toHaveBeenCalledTimes(2);
	});

	it('keeps the LRU within its byte budget, dropping the least recently used', () => {
		const lru = new ByteLru<string>(100);
		lru.set('a', 'A', 40);
		lru.set('b', 'B', 40);
		expect(lru.get('a')).toBe('A'); // a is now the most recent
		lru.set('c', 'C', 40);
		expect(lru.get('b')).toBeUndefined();
		expect(lru.get('a')).toBe('A');
		expect(lru.get('c')).toBe('C');
		expect(lru.bytes).toBe(80);
		lru.set('huge', 'H', 101);
		expect(lru.get('huge')).toBeUndefined();
		expect(lru.size).toBe(2);
	});

	it('parses tile params like the old route: z8–z16, inside the grid', () => {
		expect(parseTile({ z: '12', x: '760', y: '1490' })).toEqual(T);
		for (const p of [{ z: '7', x: '0', y: '0' }, { z: '17', x: '0', y: '0' }, { z: '8', x: '256', y: '0' }, { z: '8', x: '-1', y: '0' }, { z: '8', x: '1.5', y: '0' }, { z: '8', x: '', y: '0' }])
			expect(parseTile(p)).toBeNull();
		expect(classesAt(8)).toEqual(['Interstate', 'Principal Arterial']);
		expect(classesAt(16)).toContain('Local');
	});
});

describe('versioned API caching', () => {
	it('is immutable only when the requested version is the current one', () => {
		expect(versionedCacheControl('abc', 'abc')).toBe(IMMUTABLE);
		expect(versionedCacheControl('abc', 'abd')).toBe('no-cache');
		expect(versionedCacheControl(null, 'abc')).toBe('no-cache');
		expect(versionedCacheControl('abc', null)).toBe('no-cache');
		expect(versionedCacheControl(null, null)).toBe('no-cache');
		expect(versionedCacheControl('x', 'y', 'public, max-age=60')).toBe('public, max-age=60');
	});
});

// The routes themselves, with the database and /api/meta replaced.
const versions = { cameras: 'cam1', calibrations: 'cal1', roads: 'road1' };
vi.mock('#lib/server/versions.js', () => ({ dataMeta: async () => ({ versions }) }));
const rows = vi.fn(async (): Promise<unknown[]> => []);
vi.mock('#lib/server/db.js', () => ({ db: () => (..._args: unknown[]) => rows() }));

async function call(route: { GET: (e: never) => Promise<Response> }, search: string) {
	const headers: Record<string, string> = {};
	const url = new URL(`http://x/api${search}`);
	const res = await route.GET({
		url,
		params: { z: '12', x: '760', y: '1490' },
		request: new Request(url, { headers: { 'accept-encoding': 'gzip' } }),
		setHeaders: (h: Record<string, string>) => Object.assign(headers, h)
	} as never);
	return { res, cacheControl: headers['cache-control'] ?? res.headers.get('cache-control') };
}

describe('the routes', () => {
	beforeEach(() => rows.mockClear());

	it('GET /api/cameras is immutable when v matches, no-cache otherwise', async () => {
		const route = await import('../../routes/api/cameras/+server.js');
		expect((await call(route, '?v=cam1')).cacheControl).toBe(IMMUTABLE);
		expect((await call(route, '?v=cam0')).cacheControl).toBe('no-cache');
		expect((await call(route, '')).cacheControl).toBe('no-cache');
		const { res } = await call(route, '?v=cam1');
		expect((await res.json()).type).toBe('FeatureCollection');
	});

	it('GET /api/calibrations is immutable when v matches, no-cache otherwise', async () => {
		const route = await import('../../routes/api/calibrations/+server.js');
		expect((await call(route, '?v=cal1')).cacheControl).toBe(IMMUTABLE);
		expect((await call(route, '?v=cam1')).cacheControl).toBe('no-cache');
		expect((await call(route, '')).cacheControl).toBe('no-cache');
	});

	it('GET /api/tiles/roads answers gzip, immutable for the current version and max-age=60 otherwise', async () => {
		rows.mockImplementation(async () => [{ mvt: Buffer.from(mvt(T)) }]);
		const route = await import('../../routes/api/tiles/roads/[z]/[x]/[y]/+server.js');
		const current = await call(route, '?v=road1');
		expect(current.res.headers.get('content-encoding')).toBe('gzip');
		expect(current.cacheControl).toBe(IMMUTABLE);
		const old = await call(route, '?v=road0');
		expect(old.res.headers.get('content-encoding')).toBe('gzip');
		expect(old.cacheControl).toBe('public, max-age=60');
		expect(gunzipSync(new Uint8Array(await old.res.arrayBuffer()))).toEqual(Buffer.from(mvt(T)));
		// One cut served both.
		expect(rows).toHaveBeenCalledTimes(1);
	});
});
