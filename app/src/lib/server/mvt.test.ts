import { describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import type postgres from 'postgres';

vi.mock('$app/env/private', () => ({ DATABASE_URL: undefined, FRAMES_DIR: '/nonexistent', TVT_FRAME_SOURCE: 'fixture' }));
const mvt = await import('./mvt.js');
const {
	buildRegistry,
	cancelOnAbort,
	cutLayerTile,
	EMPTY_CACHE,
	emptyReason,
	layerTileServer,
	LOG_EVERY_MS,
	neverTiled,
	parseLayerTile,
	SHARED_TILE_SCHEMAS,
	TILE_LAYERS,
	TileCache,
	tileKey,
	tileLayerProblems,
	tilePoolOptions,
	tileQuery,
	tileSchemas
} = mvt;
type TileLayerDef = import('./mvt.js').TileLayerDef;
type TileModules = import('./mvt.js').TileModules;
type TileId = import('./road-tiles.js').TileId;
const { IMMUTABLE } = await import('./cache-headers.js');
const { SHORT_CACHE } = await import('./road-tiles.js');

/**
 * The toggled layers' tile server (#lib/server/mvt; plan C4, package S2),
 * with made-up layers and a fake cut: cache keys, versions and caching, the
 * shared LRU's per-layer caps, timeouts, empty tiles before a plugin's
 * migration or a layer's first build (and their log), the definitions'
 * checks (the schemas tiles may read among them) and the SQL they make. The
 * cuts against a real PostGIS are in mvt.db.test.ts.
 */

/** A made-up layer: polygons in 4326 at z8–11 (generalised) and z12–16, labels from z14. */
const SOILS: TileLayerDef = {
	plugin: 'soils',
	layer: 'units',
	minzoom: 8,
	maxzoom: 16,
	parts: [
		{
			name: 'units',
			sources: [
				{ minzoom: 8, maxzoom: 11, table: 'soils.unit_lo', id: 'gid', columns: ['musym', 'ground_type'] },
				{ minzoom: 12, maxzoom: 16, table: 'soils.unit', id: 'gid', columns: ['musym', 'ground_type', 'name'] }
			]
		},
		{ name: 'labels', buffer: 256, sources: [{ minzoom: 14, maxzoom: 16, table: 'soils.unit_label', geom: 'pt', srid: 3857, columns: ['musym'] }] }
	]
};
const TRAILS: TileLayerDef = {
	plugin: 'trails',
	layer: 'paths',
	minzoom: 8,
	maxzoom: 16,
	parts: [{ name: 'paths', sources: [{ minzoom: 10, maxzoom: 16, table: 'trails.path', srid: 3857, id: 'id', columns: ['kind'] }] }]
};
const T: TileId = { z: 12, x: 760, y: 1490 };

/** A fake MVT: deterministic bytes per layer and tile, repetitive enough to compress. */
const fakeMvt = (def: TileLayerDef, t: TileId, n = 200) => new TextEncoder().encode(`${def.plugin}.${def.layer} ${t.z}/${t.x}/${t.y} `.repeat(n));
const pgError = (code: string) => Object.assign(new Error(`postgres ${code}`), { code });

/**
 * A server over a fake cut. `versions` is what /api/meta reports; the cut
 * reads `cutAt` (the database's newest row), which is the same unless a test
 * makes a build land in between.
 */
function server(versions: Record<string, string | null> = { 'soils.units': 's1', 'trails.paths': 't1' }, o: { maxBytes?: number; deadlineMs?: number } = {}) {
	const cutAt: Record<string, string | null> = versions;
	const cut = vi.fn(async (def: TileLayerDef, t: TileId, _signal: AbortSignal): Promise<import('./mvt.js').LayerCut> => ({
		mvt: fakeMvt(def, t),
		version: cutAt[`${def.plugin}.${def.layer}`] ?? null
	}));
	const log = vi.fn();
	const clock = { now: 1_000_000 };
	const s = layerTileServer({ version: async (id) => versions[id] ?? null, cut, log, now: () => clock.now, ...o });
	return { s, cut, versions, log, clock };
}

describe('the shared LRU (plan C4: about 120 MB, per-layer caps)', () => {
	it('keeps one layer within its cap, dropping its own oldest tiles only', () => {
		const c = new TileCache(1000);
		c.set('trails.paths', 't/1', new Uint8Array(1), 100, 300);
		c.set('soils.units', 's/1', new Uint8Array(1), 100, 300);
		c.set('soils.units', 's/2', new Uint8Array(1), 100, 300);
		c.set('soils.units', 's/3', new Uint8Array(1), 100, 300);
		expect(c.get('s/1')).toBeDefined(); // s/1 is now the layer's newest
		c.set('soils.units', 's/4', new Uint8Array(1), 100, 300);
		expect(c.get('s/2')).toBeUndefined();
		expect(c.get('s/1')).toBeDefined();
		expect(c.get('t/1')).toBeDefined(); // older than all of them, but another layer's
		expect(c.layerBytes('soils.units')).toBe(300);
		expect(c.layerBytes('trails.paths')).toBe(100);
		expect(c.bytes).toBe(400);
	});

	it('keeps everyone within the shared budget, dropping the oldest of anyone', () => {
		const c = new TileCache(250);
		c.set('a.x', 'a/1', new Uint8Array(1), 100, 200);
		c.set('b.x', 'b/1', new Uint8Array(1), 100, 200);
		c.get('a/1');
		c.set('b.x', 'b/2', new Uint8Array(1), 100, 200);
		expect(c.get('b/1')).toBeUndefined();
		expect(c.get('a/1')).toBeDefined();
		expect(c.size).toBe(2);
		expect(c.bytes).toBe(200);
	});

	it("doesn't keep a tile bigger than its layer's cap, and replaces a key in place", () => {
		const c = new TileCache(1000);
		c.set('a.x', 'a/1', new Uint8Array(1), 50, 100);
		c.set('a.x', 'a/huge', new Uint8Array(1), 101, 100);
		expect(c.get('a/huge')).toBeUndefined();
		c.set('a.x', 'a/1', new Uint8Array(2), 80, 100);
		expect(c.get('a/1')).toEqual(new Uint8Array(2));
		expect(c.bytes).toBe(80);
		c.set('b.x', 'b/1', new Uint8Array(1), 1001, 2000);
		expect(c.get('b/1')).toBeUndefined();
		expect(c.layerBytes('b.x')).toBe(0);
	});

	it('defaults to about 120 MB shared and 40 MB a layer', () => {
		expect(mvt.CACHE_BYTES).toBe(120e6);
		expect(mvt.LAYER_CACHE_BYTES).toBe(40e6);
		expect(new TileCache().maxBytes).toBe(120e6);
	});
});

describe('the tile server', () => {
	it('keys tiles by layer, version and tile', () => {
		expect(tileKey('soils.units', 's1', T)).toBe('soils.units/s1/12/760/1490');
		expect(tileKey('soils.units', 's2', T)).not.toBe(tileKey('soils.units', 's1', T));
		expect(tileKey('soils.units', 's1', { ...T, x: 761 })).not.toBe(tileKey('soils.units', 's1', T));
	});

	it('answers gzip, immutable for the current version, with an ETag per layer and version', async () => {
		const { s } = server();
		const res = await s.respond(SOILS, T, 's1', 'gzip, deflate, br');
		expect(res.status).toBe(200);
		expect(res.headers.get('content-type')).toBe('application/vnd.mapbox-vector-tile');
		expect(res.headers.get('content-encoding')).toBe('gzip');
		expect(res.headers.get('cache-control')).toBe(IMMUTABLE);
		expect(res.headers.get('vary')).toBe('Accept-Encoding');
		expect(res.headers.get('etag')).toBe('"soils.units-s1-gz"');
		expect(res.headers.get('server-timing')).toMatch(/^cut;dur=\d+$/);
		expect(gunzipSync(new Uint8Array(await res.arrayBuffer()))).toEqual(Buffer.from(fakeMvt(SOILS, T)));
		const plain = await s.respond(SOILS, T, 's1', null);
		expect(plain.headers.get('content-encoding')).toBeNull();
		expect(plain.headers.get('etag')).toBe('"soils.units-s1"');
		expect(new Uint8Array(await plain.arrayBuffer())).toEqual(fakeMvt(SOILS, T));
		expect(plain.headers.get('server-timing')).toBeNull(); // from the cache
	});

	it('answers max-age=60 for an old version or none, and 304 to its ETag', async () => {
		const { s } = server();
		for (const v of ['s0', null, ''])
			expect((await s.respond(SOILS, T, v, 'gzip')).headers.get('cache-control')).toBe(SHORT_CACHE);
		const nm = await s.respond(SOILS, T, null, 'gzip', '"soils.units-s1-gz"');
		expect(nm.status).toBe(304);
		expect(nm.headers.get('cache-control')).toBe(SHORT_CACHE);
		expect((await s.respond(SOILS, T, 's1', 'gzip', 'W/"soils.units-s1-gz"')).headers.get('cache-control')).toBe(IMMUTABLE);
		expect((await s.respond(SOILS, T, 's1', 'gzip', '"soils.units-s0-gz"')).status).toBe(200);
		expect((await s.respond(SOILS, T, 's1', 'gzip', '"trails.paths-s1-gz"')).status).toBe(200);
	});

	it('cuts a tile once per layer and version: the cache and concurrent requests share it', async () => {
		const { s, cut, versions } = server();
		await Promise.all([s.respond(SOILS, T, 's1', 'gzip'), s.respond(SOILS, T, 's1', 'gzip'), s.respond(SOILS, T, null, null)]);
		expect(cut).toHaveBeenCalledTimes(1);
		await s.respond(TRAILS, T, 't1', 'gzip');
		expect(cut).toHaveBeenCalledTimes(2); // another layer, the same tile
		versions['soils.units'] = 's2';
		await s.respond(SOILS, T, 's2', 'gzip');
		expect(cut).toHaveBeenCalledTimes(3);
		await s.respond(SOILS, T, 's2', 'gzip');
		expect(s.cuts).toBe(3);
	});

	it("serves nothing for a layer with no version (no licence on record yet): empty, short cache, never cut", async () => {
		const { s, cut, log } = server({});
		const res = await s.respond(SOILS, T, null, 'gzip');
		expect(res.status).toBe(200);
		expect(res.headers.get('x-tile-status')).toBe('unversioned');
		expect(res.headers.get('cache-control')).toBe(EMPTY_CACHE);
		expect(res.headers.get('etag')).toBeNull();
		expect((await res.arrayBuffer()).byteLength).toBe(0);
		expect((await s.respond(SOILS, T, null, 'gzip', '"soils.units--gz"')).status).toBe(200);
		expect(cut).not.toHaveBeenCalled();
		expect(s.cache.size).toBe(0);
		expect(log).toHaveBeenCalledTimes(1);
		expect(log.mock.calls[0][0]).toMatch(/^tile layer soils\.units: answered empty \(unversioned\) at 12\/760\/1490: no row in core\.layer_version/);
	});

	it('sends a tile cut at a newer version than /api/meta reports with a short cache, and keeps it for neither', async () => {
		const { s, cut, versions } = server();
		// A build committed s2 inside /api/meta's 15 s memo, which still reports s1.
		cut.mockImplementation(async (def, t) => ({ mvt: fakeMvt(def, t), version: 's2' }));
		const res = await s.respond(SOILS, T, 's1', 'gzip');
		expect(res.status).toBe(200);
		expect(res.headers.get('cache-control')).toBe(SHORT_CACHE);
		expect(res.headers.get('etag')).toBeNull();
		expect(gunzipSync(new Uint8Array(await res.arrayBuffer()))).toEqual(Buffer.from(fakeMvt(SOILS, T)));
		expect(s.cache.size).toBe(0);
		await s.respond(SOILS, T, 's1', 'gzip');
		expect(cut).toHaveBeenCalledTimes(2);
		// Once /api/meta sees s2, s2's tiles are kept and immutable again.
		versions['soils.units'] = 's2';
		expect((await s.respond(SOILS, T, 's2', 'gzip')).headers.get('cache-control')).toBe(IMMUTABLE);
		await s.respond(SOILS, T, 's2', 'gzip');
		expect(cut).toHaveBeenCalledTimes(3);
		expect(s.cache.size).toBe(1);
	});

	it('sends a tile with no features empty and keeps it', async () => {
		const { s, cut } = server();
		cut.mockImplementation(async () => ({ mvt: new Uint8Array(), version: 's1' }));
		const res = await s.respond(SOILS, T, 's1', 'gzip');
		expect(res.status).toBe(200);
		expect(res.headers.get('content-encoding')).toBeNull();
		expect(res.headers.get('cache-control')).toBe(IMMUTABLE);
		expect(res.headers.get('x-tile-status')).toBeNull();
		expect((await res.arrayBuffer()).byteLength).toBe(0);
		await s.respond(SOILS, T, 's1', 'gzip');
		expect(cut).toHaveBeenCalledTimes(1);
	});

	it('answers an empty tile with a short cache when the database stops the cut, and keeps nothing', async () => {
		const { s, cut } = server();
		cut.mockRejectedValueOnce(pgError('57014'));
		const res = await s.respond(SOILS, T, 's1', 'gzip');
		expect(res.status).toBe(200);
		expect(res.headers.get('cache-control')).toBe(EMPTY_CACHE);
		expect(res.headers.get('cache-control')).toBe('public, max-age=10');
		expect(res.headers.get('x-tile-status')).toBe('timeout');
		expect(res.headers.get('etag')).toBeNull();
		expect((await res.arrayBuffer()).byteLength).toBe(0);
		expect(s.cache.size).toBe(0);
		const again = await s.respond(SOILS, T, 's1', 'gzip');
		expect(again.headers.get('x-tile-status')).toBeNull();
		expect(again.headers.get('cache-control')).toBe(IMMUTABLE);
		expect(cut).toHaveBeenCalledTimes(2);
	});

	it('gives up on a cut at the deadline, tells it to stop, and answers empty', async () => {
		let seen: AbortSignal | undefined;
		const { s, cut } = server(undefined, { deadlineMs: 20 });
		cut.mockImplementationOnce(
			(_d, _t, signal) =>
				new Promise((_, reject) => {
					seen = signal;
					signal.addEventListener('abort', () => setTimeout(() => reject(pgError('57014')), 5));
				})
		);
		const started = Date.now();
		const res = await s.respond(SOILS, T, 's1', 'gzip');
		expect(Date.now() - started).toBeLessThan(1000);
		expect(seen?.aborted).toBe(true);
		expect(res.headers.get('x-tile-status')).toBe('timeout');
		expect(res.headers.get('cache-control')).toBe(EMPTY_CACHE);
		expect(s.cache.size).toBe(0);
		// A cut that ignores the signal is left behind at the deadline all the same.
		cut.mockImplementationOnce(() => new Promise(() => {}));
		expect((await s.respond(SOILS, { ...T, x: 1 }, 's1', 'gzip')).headers.get('x-tile-status')).toBe('timeout');
	});

	it("answers an empty tile before the plugin's migration (no table, schema or column), and keeps nothing", async () => {
		for (const code of ['42P01', '3F000', '42703']) {
			const { s, cut } = server();
			cut.mockRejectedValueOnce(pgError(code));
			const res = await s.respond(SOILS, T, 's1', 'gzip');
			expect(res.status).toBe(200);
			expect(res.headers.get('x-tile-status')).toBe('missing');
			expect(res.headers.get('cache-control')).toBe(EMPTY_CACHE);
			expect((await res.arrayBuffer()).byteLength).toBe(0);
			expect(s.cache.size).toBe(0);
		}
	});

	it('answers an empty tile when the tile role may not read a table (deploy/tvt_tiles.sql)', async () => {
		const { s, cut } = server();
		cut.mockRejectedValueOnce(pgError('42501'));
		const res = await s.respond(SOILS, T, 's1', 'gzip');
		expect(res.headers.get('x-tile-status')).toBe('denied');
		expect(res.headers.get('cache-control')).toBe(EMPTY_CACHE);
		expect(s.cache.size).toBe(0);
	});

	it('logs empty answers: the first per layer and reason, then at most once a minute, with the code and message', async () => {
		const { s, cut, log, clock } = server();
		cut.mockRejectedValue(Object.assign(new Error('relation "soils.unit" does not exist'), { code: '42P01' }));
		await s.respond(SOILS, T, 's1', 'gzip');
		expect(log).toHaveBeenCalledTimes(1);
		expect(log.mock.calls[0][0]).toBe('tile layer soils.units: answered empty (missing) at 12/760/1490: 42P01 relation "soils.unit" does not exist');
		for (const x of [1, 2, 3]) await s.respond(SOILS, { ...T, x }, 's1', 'gzip');
		expect(log).toHaveBeenCalledTimes(1);
		// Another layer, or another reason, is noted at once.
		await s.respond(TRAILS, T, 't1', 'gzip');
		cut.mockRejectedValueOnce(pgError('57014'));
		await s.respond(SOILS, { ...T, x: 9 }, 's1', 'gzip');
		expect(log).toHaveBeenCalledTimes(3);
		expect(log.mock.calls[1][0]).toMatch(/^tile layer trails\.paths: answered empty \(missing\)/);
		expect(log.mock.calls[2][0]).toMatch(/^tile layer soils\.units: answered empty \(timeout\) .*: 57014 postgres 57014$/);
		clock.now += LOG_EVERY_MS;
		await s.respond(SOILS, { ...T, x: 4 }, 's1', 'gzip');
		expect(log).toHaveBeenCalledTimes(4);
		expect(log.mock.calls[3][0]).toMatch(/at 12\/4\/1490: 42P01 .* \(and 3 more since the last note\)$/);
	});

	it('logs a cut abandoned at the deadline', async () => {
		const { s, cut, log } = server(undefined, { deadlineMs: 20 });
		cut.mockImplementationOnce(() => new Promise(() => {}));
		await s.respond(SOILS, T, 's1', 'gzip');
		expect(log.mock.calls[0][0]).toBe('tile layer soils.units: answered empty (timeout) at 12/760/1490: no answer within 20 ms');
	});

	it("fails on any other error, and doesn't keep it", async () => {
		const { s, cut } = server();
		cut.mockRejectedValueOnce(pgError('XX000'));
		await expect(s.respond(SOILS, T, 's1', 'gzip')).rejects.toThrow('postgres XX000');
		cut.mockRejectedValueOnce(Object.assign(new Error('connect'), { code: 'ECONNREFUSED' }));
		await expect(s.respond(SOILS, T, 's1', 'gzip')).rejects.toThrow('connect');
		expect((await s.respond(SOILS, T, 's1', 'gzip')).status).toBe(200);
		expect(emptyReason(null)).toBeNull();
		expect(emptyReason({ code: 57014 })).toBeNull();
	});

	it("holds each layer to its own cap in the shared cache", async () => {
		const small: TileLayerDef = { ...SOILS, cacheBytes: 600 };
		const { s, cut } = server();
		// Random bytes don't compress: each tile is about 300 bytes gzipped, so the layer keeps one.
		cut.mockImplementation(async (def, t) => ({ mvt: def === small ? crypto.getRandomValues(new Uint8Array(300)) : fakeMvt(def, t) }));
		await s.respond(TRAILS, T, 't1', 'gzip');
		for (const x of [1, 2, 3]) await s.respond(small, { ...T, x }, 's1', 'gzip');
		expect(s.cache.layerBytes('soils.units')).toBeLessThanOrEqual(600);
		expect(s.cache.layerBytes('soils.units')).toBeGreaterThan(0);
		expect(s.cache.get(tileKey('soils.units', 's1', { ...T, x: 1 }))).toBeUndefined();
		expect(s.cache.get(tileKey('soils.units', 's1', { ...T, x: 3 }))).toBeDefined();
		expect(s.cache.get(tileKey('trails.paths', 't1', T))).toBeDefined();
	});
});

describe('definitions', () => {
	it('accepts a good one', () => {
		expect(tileLayerProblems(SOILS)).toEqual([]);
		expect(tileLayerProblems({ plugin: 'hazards', layer: 'burn_scars', minzoom: 8, maxzoom: 14, cut: async () => new Uint8Array() })).toEqual([]);
		const fromCore: TileLayerDef = { ...SOILS, parts: [{ name: 'roads', sources: [{ minzoom: 8, maxzoom: 16, table: 'core.road_segment' }] }] };
		expect(tileLayerProblems(fromCore)).toEqual([]);
	});

	it("reads only the plugin's own schema and core: never restricted or a private plugin's (plan C3)", () => {
		const from = (table: string, plugin = 'soils'): TileLayerDef => ({ ...SOILS, plugin, parts: [{ name: 'u', sources: [{ minzoom: 8, maxzoom: 16, table }] }] });
		expect(tileLayerProblems(from('restricted.crash_unit')).join('; ')).toContain('schema restricted is never tiled');
		expect(tileLayerProblems(from('city_trees.tree')).join('; ')).toContain('schema city_trees is never tiled');
		expect(tileLayerProblems(from('private_parcels.parcel')).join('; ')).toContain('schema private_parcels is never tiled');
		expect(tileLayerProblems(from('trails.path')).join('; ')).toContain("schema trails isn't the plugin's own or core");
		expect(tileLayerProblems(from('raw.record')).join('; ')).toContain("schema raw isn't the plugin's own or core");
		expect(tileLayerProblems(from('obs.reading')).join('; ')).toContain("schema obs isn't the plugin's own or core");
		// A plugin whose own schema is never tiled serves no tiles at all, from parts or a cut.
		expect(tileLayerProblems(from('city_trees.tree', 'city_trees')).join('; ')).toContain('plugin city_trees: its data is never tiled');
		expect(tileLayerProblems(from('city_trees.tree', 'city_trees')).join('; ')).toContain('schema city_trees is never tiled');
		const ownCut = { plugin: 'private_x', layer: 'y', minzoom: 8, maxzoom: 9, cut: async () => new Uint8Array() };
		expect(tileLayerProblems(ownCut).join('; ')).toContain('plugin private_x: its data is never tiled');
		expect(tileLayerProblems({ ...ownCut, plugin: 'restricted' }).join('; ')).toContain('never tiled');
		expect(tileSchemas('soils')).toEqual(['soils', 'core']);
		expect(tileSchemas('private_x')).toEqual(['core']);
		for (const s of ['restricted', 'city_trees', 'private_', 'private_parcels']) expect(neverTiled(s), s).toBe(true);
		for (const s of ['core', 'soils', 'trees', 'privateer']) expect(neverTiled(s), s).toBe(false);
	});

	it('refuses names, zooms and identifiers that would go wrong in a URL or SQL', () => {
		const part = SOILS.parts![0];
		const src = part.sources[1];
		const bad: [string, TileLayerDef][] = [
			['plugin', { ...SOILS, plugin: 'Soils' }],
			['layer', { ...SOILS, layer: 'units/x' }],
			['zooms', { ...SOILS, minzoom: 12, maxzoom: 10 }],
			['zooms', { ...SOILS, maxzoom: 23 }],
			['cacheBytes', { ...SOILS, cacheBytes: 0 }],
			['parts or cut', { ...SOILS, cut: async () => new Uint8Array() }],
			['parts or cut', { plugin: 'a', layer: 'b', minzoom: 8, maxzoom: 9 }],
			['no parts', { ...SOILS, parts: [] }],
			['named twice', { ...SOILS, parts: [part, part] }],
			['its name', { ...SOILS, parts: [{ ...part, name: 'units"' }] }],
			['buffer', { ...SOILS, parts: [{ ...part, buffer: -1 }] }],
			['no sources', { ...SOILS, parts: [{ ...part, sources: [] }] }],
			['overlaps', { ...SOILS, parts: [{ ...part, sources: [part.sources[0], { ...src, minzoom: 11 }] }] }],
			["outside the layer's", { ...SOILS, parts: [{ ...part, sources: [{ ...src, maxzoom: 17 }] }] }],
			['schema.table', { ...SOILS, parts: [{ ...part, sources: [{ ...src, table: 'unit' }] }] }],
			['schema.table', { ...SOILS, parts: [{ ...part, sources: [{ ...src, table: 'soils.unit; drop table x' }] }] }],
			['srid', { ...SOILS, parts: [{ ...part, sources: [{ ...src, srid: 2243 as 3857 }] }] }],
			['column', { ...SOILS, parts: [{ ...part, sources: [{ ...src, columns: ['musym', 'name"'] }] }] }],
			['column', { ...SOILS, parts: [{ ...part, sources: [{ ...src, geom: 'Geom' }] }] }],
			['listed twice', { ...SOILS, parts: [{ ...part, sources: [{ ...src, columns: ['gid'] }] }] }],
			['reserved', { ...SOILS, parts: [{ ...part, sources: [{ ...src, columns: ['mvt_geom'] }] }] }]
		];
		for (const [what, def] of bad) expect(tileLayerProblems(def).join('; '), what).toContain(what);
	});

	it('finds layers by folder, and leaves out (and logs) bad, misplaced and repeated ones', () => {
		const log = vi.fn();
		const r = buildRegistry(
			{
				'./soils/tiles.ts': { default: [SOILS, { ...SOILS, layer: 'wash' }, { ...SOILS }] },
				'./trails/tiles.ts': { default: TRAILS },
				'./farm/tiles.ts': { default: { ...SOILS, plugin: 'farm', layer: 'Fields' } },
				'./water/tiles.ts': { default: { ...SOILS, plugin: 'soils', layer: 'water' } }
			},
			log
		);
		expect([...r.keys()].sort()).toEqual(['soils.units', 'soils.wash', 'trails.paths']);
		expect(r.get('soils.units')).toBe(SOILS);
		const logged = log.mock.calls.flat().join('\n');
		expect(log).toHaveBeenCalledTimes(3);
		expect(logged).toMatch(/soils\.units \(\.\/soils\/tiles\.ts\) left out: defined twice/);
		expect(logged).toMatch(/farm\.Fields .*layer name/);
		expect(logged).toMatch(/soils\.water .*it's in water\/, not soils\//);
	});

	it('registers every layer defined in #lib/server/<plugin>/tiles.ts: none is bad, misplaced or repeated', () => {
		// The same files the registry reads, run through it again: anything it would leave out fails here.
		const found = import.meta.glob('./*/tiles.ts', { eager: true }) as TileModules;
		const log = vi.fn();
		const again = buildRegistry(found, log);
		expect(log.mock.calls.flat()).toEqual([]);
		const defined = Object.values(found).flatMap((m) => ([] as TileLayerDef[]).concat(m.default ?? []));
		expect(again.size).toBe(defined.length);
		expect(TILE_LAYERS.size).toBe(defined.length);
		expect([...TILE_LAYERS.keys()].sort()).toEqual([...again.keys()].sort());
		expect(mvt.tileLayer(undefined, 'x')).toBeUndefined();
		expect(mvt.tileLayer('nope', 'nothing')).toBeUndefined();
	});

	it("serves only schemas deploy/tvt_tiles.sql grants the tile role, and it grants none tiles never read", () => {
		const text = readFileSync(new URL('../../../../deploy/tvt_tiles.sql', import.meta.url), 'utf8');
		const list = text.match(/tile_schemas text\[\] := ARRAY\[([^\]]*)\]/)?.[1];
		expect(list, 'tile_schemas in deploy/tvt_tiles.sql').toBeTruthy();
		const granted = [...list!.matchAll(/'([a-z_][a-z0-9_]*)'/g)].map((m) => m[1]);
		expect(granted.length).toBeGreaterThan(1);
		for (const s of granted) expect(neverTiled(s), s).toBe(false);
		for (const s of SHARED_TILE_SCHEMAS) expect(granted).toContain(s);
		// Every registered layer reads only granted schemas (a `cut` reads its plugin's own).
		for (const def of TILE_LAYERS.values()) {
			const read = def.parts ? def.parts.flatMap((p) => p.sources.map((src) => src.table.split('.')[0])) : [def.plugin];
			for (const s of read) expect(granted, `${def.plugin}.${def.layer} reads ${s}`).toContain(s);
		}
		// And it takes back what tiles never read, with neverTiled's names.
		expect(text).toContain("nspname IN ('restricted', 'city_trees') OR nspname LIKE 'private\\_%'");
	});

	it("parses tiles within the layer's zooms and the grid", () => {
		expect(parseLayerTile({ z: '12', x: '760', y: '1490' }, SOILS)).toEqual(T);
		for (const p of [{ z: '7', x: '0', y: '0' }, { z: '17', x: '0', y: '0' }, { z: '8', x: '256', y: '0' }, { z: '8', x: '-1', y: '0' }, { z: '8', x: '1.5', y: '0' }, { z: '8', x: '', y: '0' }, {}])
			expect(parseLayerTile(p, SOILS)).toBeNull();
		expect(parseLayerTile({ z: '17', x: '0', y: '0' }, { minzoom: 8, maxzoom: 17 })).toEqual({ z: 17, x: 0, y: 0 });
	});
});

describe('the SQL a definition makes', () => {
	const flat = (s: string | null) => s?.replace(/\s+/g, ' ');

	it('reads each part from its zoom band, with quoted identifiers and the tile as parameters', () => {
		const lo = flat(tileQuery(SOILS, 10))!;
		expect(lo).toContain('from "soils"."unit_lo" s');
		expect(lo).toContain('s."gid", s."musym", s."ground_type", ST_AsMVTGeom(ST_Transform(s."geom", 3857), ST_TileEnvelope($1::int, $2::int, $3::int), 4096, 64, true) as mvt_geom');
		expect(lo).toContain(`ST_AsMVT(t, 'units', 4096, 'mvt_geom', 'gid')`);
		// Features within the buffer count too: the envelope is widened by buffer / extent.
		expect(lo).toContain('where s."geom" && ST_Transform(ST_TileEnvelope($1::int, $2::int, $3::int, margin => 0.015625), 4326)');
		expect(lo).not.toContain('labels');
		const hi = flat(tileQuery(SOILS, 15))!;
		expect(hi).toContain('from "soils"."unit" s');
		expect(hi).toContain('s."name"');
		expect(hi).toMatch(/^select \(select coalesce\(ST_AsMVT\(t, 'units'.*\) \|\| \(select coalesce\(ST_AsMVT\(t, 'labels', 4096, 'mvt_geom'\), ''::bytea\).*\) as mvt, /);
		// The layer's version, in the same statement and so the same snapshot as the data.
		expect(hi).toMatch(/ as mvt, \(select version from core\.layer_version where layer = \$4 order by id desc limit 1\) as version$/);
		// Already in web mercator: no transforms, and its own buffer.
		expect(hi).toContain('ST_AsMVTGeom(s."pt", ST_TileEnvelope($1::int, $2::int, $3::int), 4096, 256, true)');
		expect(hi).toContain('where s."pt" && ST_TileEnvelope($1::int, $2::int, $3::int, margin => 0.0625)');
	});

	it('makes no query at a zoom with no source', () => {
		const sparse: TileLayerDef = { ...SOILS, parts: [{ name: 'units', sources: [{ minzoom: 12, maxzoom: 16, table: 'soils.unit' }] }] };
		expect(tileQuery(sparse, 9)).toBeNull();
		expect(tileQuery(sparse, 12)).toContain(`ST_AsMVT(t, 'units', 4096, 'mvt_geom')`);
	});

	it('runs it on the pool with the tile and layer as parameters, and returns its bytes and version', async () => {
		const calls: [string, unknown[]][] = [];
		const begun: string[] = [];
		const unsafe = (text: string, params: unknown[]) => {
			calls.push([text, params]);
			return Promise.resolve([{ mvt: Buffer.from('tile'), version: 's1' }]) as unknown as postgres.PendingQuery<postgres.Row[]>;
		};
		const tx = { unsafe } as unknown as postgres.TransactionSql;
		const sql = {
			unsafe,
			begin: async (options: string, fn: (tx: postgres.TransactionSql) => unknown) => (begun.push(options), fn(tx))
		} as unknown as postgres.Sql;
		const signal = new AbortController().signal;
		expect(await cutLayerTile(sql, SOILS, T, signal)).toEqual({ mvt: new Uint8Array(Buffer.from('tile')), version: 's1' });
		expect(calls).toEqual([[tileQuery(SOILS, 12), [12, 760, 1490, 'soils.units']]]);
		// No source at this zoom: an empty tile, whatever the version, and no query.
		expect(await cutLayerTile(sql, { ...SOILS, parts: [{ name: 'u', sources: [{ minzoom: 14, maxzoom: 16, table: 'soils.b' }] }] }, T, signal)).toEqual({ mvt: new Uint8Array() });
		expect(calls).toHaveLength(1);
		// Its own cut: in a read-only, repeatable-read transaction that reads the version first.
		const own = vi.fn(async () => new Uint8Array([1]));
		expect(await cutLayerTile(sql, { plugin: 'x', layer: 'y', minzoom: 8, maxzoom: 9, cut: own }, T, signal)).toEqual({ mvt: new Uint8Array([1]), version: 's1' });
		expect(begun).toEqual(['isolation level repeatable read read only']);
		expect(calls[1]).toEqual(['select (select version from core.layer_version where layer = $1 order by id desc limit 1) as version', ['x.y']]);
		expect(own).toHaveBeenCalledWith(tx, T, signal);
	});

	it('cancels the query when the deadline aborts, and never starts one after it', async () => {
		const cancel = vi.fn();
		let reject!: (e: Error) => void;
		const pending = Object.assign(new Promise((_, r) => (reject = r)), { cancel: () => (cancel(), reject(pgError('57014'))) });
		const stop = new AbortController();
		const run = cancelOnAbort(stop.signal, () => pending as unknown as postgres.PendingQuery<postgres.Row[]>);
		stop.abort();
		await expect(run).rejects.toMatchObject({ code: '57014' });
		expect(cancel).toHaveBeenCalledTimes(1);
		const query = vi.fn();
		await expect(cancelOnAbort(stop.signal, query)).rejects.toMatchObject({ code: '57014' });
		expect(query).not.toHaveBeenCalled();
	});

	it('uses a pool of its own: 3 connections, statement_timeout 3 s, read-only, as the tile role when given', () => {
		const o = tilePoolOptions();
		expect(o.max).toBe(3);
		expect(o.connection.statement_timeout).toBe(3000);
		expect(o.connection.default_transaction_read_only).toBe(true);
		expect(o.connection).not.toHaveProperty('role');
		expect(mvt.DEADLINE_MS).toBeGreaterThan(o.connection.statement_timeout);
		expect(tilePoolOptions('tvt_tiles').connection).toMatchObject({ role: 'tvt_tiles', default_transaction_read_only: true, statement_timeout: 3000 });
	});
});
