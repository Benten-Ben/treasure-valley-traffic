import { gunzipSync } from 'node:zlib';
import { describe, expect, it, vi } from 'vitest';
import { IMMUTABLE } from '../cache-headers.js';
import { fenceFeature, fenceLinesServer, readFenceLines, type Sql, UNVERSIONED_KEEP_MS } from './lines.js';

/** Made-up rows (no real records): a fence, a wall with a tagged height, and a hedge the query leaves out. */
const ROWS = [
	{ fence_id: 'osm:w1', type: 'fence', look: 'open', height_m: 1.8, height_source: 'default', material: 'wood', fence_type: null, name: null, length_m: 41.26, geometry: '{"type":"LineString","coordinates":[[-116.2,43.6],[-116.1999,43.6]]}' },
	{ fence_id: 'osm:w2', type: 'wall', look: 'solid', height_m: 2.4, height_source: 'tagged', material: 'brick', fence_type: null, name: 'Garden wall', length_m: 12, geometry: '{"type":"LineString","coordinates":[[-116.21,43.61],[-116.209,43.61]]}' }
];

function fakeSql(o: { table?: boolean; rows?: Record<string, unknown>[] } = {}) {
	const seen: string[] = [];
	const sql = (async (strings: TemplateStringsArray) => {
		const text = strings.join('$').replace(/\s+/g, ' ').trim();
		seen.push(text);
		if (text.includes('to_regclass')) return [{ fences: o.table ?? true }];
		return o.rows ?? ROWS;
	}) as Sql;
	return { sql, seen };
}

function server(o: { table?: boolean; rows?: Record<string, unknown>[]; version?: string | null } = {}) {
	const db = fakeSql(o);
	let version = o.version === undefined ? 'v1' : o.version;
	let clock = 1_000_000;
	const s = fenceLinesServer({ sql: () => db.sql, version: async () => version, now: () => clock });
	return { s, db, setVersion: (v: string | null) => (version = v), advance: (ms: number) => (clock += ms) };
}

const json = async (res: Response) => JSON.parse(gunzipSync(Buffer.from(await res.arrayBuffer())).toString());

describe('the fences lines route (plan P10)', () => {
	it('answers every active line but hedges, as gzipped GeoJSON with short properties', async () => {
		const { s, db } = server();
		const res = await s.respond('v1', 'gzip');
		expect(res.status).toBe(200);
		expect(res.headers.get('content-type')).toBe('application/geo+json');
		expect(res.headers.get('content-encoding')).toBe('gzip');
		expect(res.headers.get('vary')).toBe('Accept-Encoding');
		const body = await json(res);
		expect(body.type).toBe('FeatureCollection');
		expect(body.features).toHaveLength(2);
		expect(body.features[0]).toMatchObject({ id: 'osm:w1', geometry: { type: 'LineString' }, properties: { id: 'osm:w1', type: 'fence', look: 'open', h: 1.8, hs: 'default', m: 'wood', len: 41.3 } });
		expect(body.features[1].properties).toMatchObject({ hs: 'tagged', name: 'Garden wall' });
		const query = db.seen.find((t) => t.includes('from fences.fence'))!;
		expect(query).toContain('active');
		expect(query).toContain("type <> 'hedge'");
	});

	it('is immutable when asked with the current version, no-cache otherwise', async () => {
		const { s } = server({ version: 'v1' });
		expect((await s.respond('v1', 'gzip')).headers.get('cache-control')).toBe(IMMUTABLE);
		for (const v of [null, '', 'v0']) expect((await s.respond(v, 'gzip')).headers.get('cache-control')).toBe('no-cache');
	});

	it('has an ETag named for the version, and answers 304 to it', async () => {
		const { s } = server({ version: 'v1' });
		const first = await s.respond('v1', 'gzip');
		const etag = first.headers.get('etag')!;
		expect(etag).toBe('"fences-v1-gz"');
		const again = await s.respond('v1', 'gzip', etag);
		expect(again.status).toBe(304);
		expect(again.headers.get('etag')).toBe(etag);
		expect(again.headers.get('cache-control')).toBe(IMMUTABLE);
		expect((await s.respond('v1', 'gzip', `W/${etag}, "other"`)).status).toBe(304);
		// A plain answer has its own tag, so a cache never mixes the two.
		const plain = await s.respond('v1', null);
		expect(plain.headers.get('etag')).toBe('"fences-v1"');
		expect((await s.respond('v1', null, etag)).status).toBe(200);
		// A new version is not matched by the old tag.
		const { s: s2, setVersion } = server({ version: 'v1' });
		setVersion('v2');
		expect((await s2.respond('v2', 'gzip', etag)).status).toBe(200);
	});

	it('sends plain JSON to a client that does not take gzip', async () => {
		const { s } = server();
		for (const ae of [null, 'identity', 'br', 'gzip;q=0']) {
			const res = await s.respond('v1', ae);
			expect(res.headers.get('content-encoding')).toBeNull();
			expect((await res.json()).features).toHaveLength(2);
		}
	});

	it('reads the table once per version, whatever the number of requests', async () => {
		const { s, setVersion } = server({ version: 'v1' });
		await Promise.all([s.respond('v1', 'gzip'), s.respond('v1', 'gzip'), s.respond(null, null)]);
		await s.respond('v1', 'gzip');
		expect(s.reads).toBe(1);
		setVersion('v2');
		await s.respond('v2', 'gzip');
		expect(s.reads).toBe(2);
	});

	it('is an empty collection before the migration (no table), never an error', async () => {
		const { s, db } = server({ table: false, version: null });
		const res = await s.respond(null, 'gzip');
		expect(res.status).toBe(200);
		expect(await json(res)).toEqual({ type: 'FeatureCollection', features: [] });
		expect(res.headers.get('cache-control')).toBe('no-cache');
		expect(res.headers.get('etag')).toMatch(/^"fences-none-.+-gz"$/);
		expect(db.seen.some((t) => t.includes('from fences.fence'))).toBe(false);
		// Asking with a version that does not exist is no-cache too.
		expect((await s.respond('v9', 'gzip')).headers.get('cache-control')).toBe('no-cache');
	});

	it('is empty when the table has no rows yet, and keeps an answer it has no version for only briefly', async () => {
		const { s, advance } = server({ rows: [], version: null });
		expect((await json(await s.respond(null, 'gzip'))).features).toEqual([]);
		await s.respond(null, 'gzip');
		expect(s.reads).toBe(1);
		advance(UNVERSIONED_KEEP_MS + 1);
		await s.respond(null, 'gzip');
		expect(s.reads).toBe(2);
	});
});

describe('the rows', () => {
	it('skips a row that cannot be drawn', () => {
		const ok = ROWS[0];
		expect(fenceFeature(ok)).not.toBeNull();
		expect(fenceFeature({ ...ok, type: 'hedge' })).toBeNull();
		expect(fenceFeature({ ...ok, height_m: 0 })).toBeNull();
		expect(fenceFeature({ ...ok, geometry: '{"type":"Point","coordinates":[0,0]}' })).toBeNull();
		expect(fenceFeature({ ...ok, geometry: '{"type":"LineString","coordinates":[[0,0]]}' })).toBeNull();
	});

	it('reads through readFenceLines with the same filter', async () => {
		const { sql } = fakeSql({ rows: [...ROWS, { ...ROWS[0], fence_id: 'osm:w3', type: 'hedge' }] });
		expect((await readFenceLines(sql)).features.map((f) => f.id)).toEqual(['osm:w1', 'osm:w2']);
	});
});

describe('the route file', () => {
	it('answers GET with the version from /api/meta', async () => {
		vi.resetModules();
		const sql = fakeSql().sql;
		vi.doMock('$app/env/private', () => ({ DATABASE_URL: 'postgres://test' }));
		vi.doMock('#lib/server/db.js', () => ({ db: () => sql }));
		vi.doMock('#lib/server/versions.js', () => ({ dataMeta: async () => ({ versions: { layers: { 'fences.lines': 'v7' } } }) }));
		const { GET } = await import('../../../routes/api/fences/lines/+server.js');
		const req = (url: string, h: Record<string, string> = {}) => ({ url: new URL(url, 'http://x'), request: new Request(new URL(url, 'http://x'), { headers: h }) });
		const res = await GET(req('/api/fences/lines?v=v7', { 'accept-encoding': 'gzip' }) as never);
		expect(res.headers.get('cache-control')).toBe(IMMUTABLE);
		expect(res.headers.get('etag')).toBe('"fences-v7-gz"');
		expect((await json(res)).features).toHaveLength(2);
		expect((await GET(req('/api/fences/lines?v=v7', { 'accept-encoding': 'gzip', 'if-none-match': '"fences-v7-gz"' }) as never)).status).toBe(304);
		expect((await GET(req('/api/fences/lines?v=old', { 'accept-encoding': 'gzip' }) as never)).headers.get('cache-control')).toBe('no-cache');
		vi.doUnmock('#lib/server/versions.js');
	});
});
