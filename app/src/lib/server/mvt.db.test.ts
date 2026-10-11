import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import { gunzipSync } from 'node:zlib';
import { VectorTile } from '@mapbox/vector-tile';
import { PbfReader } from 'pbf';
import postgres from 'postgres';

vi.mock('$app/env/private', () => ({ DATABASE_URL: undefined, FRAMES_DIR: '/nonexistent', TVT_FRAME_SOURCE: 'fixture' }));
const { cancelOnAbort, cutLayerTile, layerTileServer, STATEMENT_TIMEOUT_MS, tilePoolOptions } = await import('./mvt.js');
const { readDatabase } = await import('./versions.js');
type TileLayerDef = import('./mvt.js').TileLayerDef;

/**
 * The toggled layers' tiles against a real PostGIS (#lib/server/mvt; plan C4):
 * the SQL a definition makes, the tile pool's statement timeout and
 * read-only connections, the deadline's cancel, an empty tile before a
 * migration, and /api/meta's layer versions (migration 0020).
 *
 * Runs only with TVT_TEST_DATABASE_URL, a scratch database migrated through
 * 0020 (never `tvt`). Its made-up rows go in a schema of their own and
 * layer names under `tvt_test.`, both removed afterwards.
 */
const URL = process.env.TVT_TEST_DATABASE_URL;
const SCHEMA = 'tvt_test_mvt';

/** The tile at zoom z holding a point. */
function tileAt(lon: number, lat: number, z: number) {
	const n = 2 ** z;
	const r = (lat * Math.PI) / 180;
	return { z, x: Math.floor(((lon + 180) / 360) * n), y: Math.floor(((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * n) };
}

const UNITS: TileLayerDef = {
	plugin: 'tvt_test',
	layer: 'units',
	minzoom: 8,
	maxzoom: 16,
	parts: [
		{
			name: 'units',
			sources: [
				{ minzoom: 8, maxzoom: 11, table: `${SCHEMA}.unit_lo`, id: 'gid', columns: ['musym'] },
				{ minzoom: 12, maxzoom: 16, table: `${SCHEMA}.unit`, id: 'gid', columns: ['musym', 'name'] }
			]
		},
		{ name: 'labels', sources: [{ minzoom: 14, maxzoom: 16, table: `${SCHEMA}.label`, geom: 'pt', srid: 3857, columns: ['musym'] }] }
	]
};

function decode(raw: Uint8Array) {
	return new VectorTile(new PbfReader(raw));
}

describe.skipIf(!URL)('toggled-layer tiles on PostGIS', () => {
	let admin: postgres.Sql;
	let tiles: postgres.Sql;

	beforeAll(async () => {
		admin = postgres(URL!, { max: 2, onnotice: () => {} });
		tiles = postgres(URL!, tilePoolOptions());
		const [{ ok }] = await admin`select to_regclass('core.layer_version') is not null as ok`;
		if (!ok) throw new Error('core.layer_version is missing: apply migration 0020 to the test database');
		await admin.unsafe(`
			drop schema if exists ${SCHEMA} cascade;
			create schema ${SCHEMA};
			create table ${SCHEMA}.unit (gid int primary key, musym text, name text, geom geometry(Polygon, 4326));
			create table ${SCHEMA}.unit_lo (gid int primary key, musym text, geom geometry(Polygon, 4326));
			create table ${SCHEMA}.label (musym text, pt geometry(Point, 3857));
			-- Two made-up units near Boise (-116.2, 43.6): one around the point, one 20 km away.
			insert into ${SCHEMA}.unit values
			  (1, 'AbC', 'Made-up loam', ST_MakeEnvelope(-116.205, 43.595, -116.195, 43.605, 4326)),
			  (2, 'XyZ', 'Far away', ST_MakeEnvelope(-115.96, 43.595, -115.95, 43.605, 4326));
			insert into ${SCHEMA}.unit_lo values (10, 'LO', ST_MakeEnvelope(-116.3, 43.5, -116.1, 43.7, 4326));
			insert into ${SCHEMA}.label values ('AbC', ST_Transform(ST_SetSRID(ST_MakePoint(-116.2, 43.6), 4326), 3857));
		`);
	});

	afterAll(async () => {
		if (admin) {
			await admin.unsafe(`drop schema if exists ${SCHEMA} cascade`);
			await admin`delete from core.layer_version where layer like 'tvt\\_test.%'`;
			await admin.end();
		}
		await tiles?.end();
	});

	const signal = () => new AbortController().signal;

	it('cuts each part from its zoom band, with ids and properties', async () => {
		const z14 = decode(await cutLayerTile(tiles, UNITS, tileAt(-116.2, 43.6, 14), signal()));
		expect(Object.keys(z14.layers).sort()).toEqual(['labels', 'units']);
		expect(z14.layers.units.length).toBe(1);
		const f = z14.layers.units.feature(0);
		expect(f.id).toBe(1);
		expect(f.properties).toEqual({ musym: 'AbC', name: 'Made-up loam' });
		expect(f.type).toBe(3); // polygon
		expect(z14.layers.labels.feature(0).properties).toEqual({ musym: 'AbC' });
		expect(z14.layers.labels.feature(0).type).toBe(1); // point

		const z10 = decode(await cutLayerTile(tiles, UNITS, tileAt(-116.2, 43.6, 10), signal()));
		expect(Object.keys(z10.layers)).toEqual(['units']);
		expect(z10.layers.units.feature(0).properties).toEqual({ musym: 'LO' });
		expect(z10.layers.units.feature(0).id).toBe(10);
	});

	it('cuts nothing where there is nothing', async () => {
		expect((await cutLayerTile(tiles, UNITS, tileAt(-117.5, 44.5, 14), signal())).length).toBe(0);
	});

	it("answers an empty tile before the plugin's migration", async () => {
		const missing: TileLayerDef = { ...UNITS, parts: [{ name: 'u', sources: [{ minzoom: 8, maxzoom: 16, table: 'tvt_test_none.unit' }] }] };
		const noColumn: TileLayerDef = { ...UNITS, parts: [{ name: 'u', sources: [{ minzoom: 8, maxzoom: 16, table: `${SCHEMA}.unit`, columns: ['nope'] }] }] };
		const s = layerTileServer({ version: async () => null, cut: (def, t, sig) => cutLayerTile(tiles, def, t, sig) });
		for (const def of [missing, noColumn]) {
			const res = await s.respond(def, tileAt(-116.2, 43.6, 14), null, 'gzip');
			expect(res.status).toBe(200);
			expect(res.headers.get('x-tile-status')).toBe('missing');
		}
	});

	it('serves a real cut gzipped, then from the cache', async () => {
		const s = layerTileServer({ version: async () => 'v1', cut: (def, t, sig) => cutLayerTile(tiles, def, t, sig) });
		const t = tileAt(-116.2, 43.6, 15);
		const res = await s.respond(UNITS, t, 'v1', 'gzip');
		expect(res.headers.get('content-encoding')).toBe('gzip');
		expect(decode(gunzipSync(new Uint8Array(await res.arrayBuffer()))).layers.units.length).toBe(1);
		await s.respond(UNITS, t, 'v1', 'gzip');
		expect(s.cuts).toBe(1);
	});

	const sleeper = (seconds: number): TileLayerDef => ({
		plugin: 'tvt_test',
		layer: 'slow',
		minzoom: 8,
		maxzoom: 16,
		cut: async (sql, _t, sig) => {
			await cancelOnAbort(sig, () => sql`select pg_sleep(${seconds})`);
			return new Uint8Array([1]);
		}
	});

	it('stops a slow cut at the statement timeout and answers empty', async () => {
		const s = layerTileServer({ version: async () => 'v1', cut: (def, t, sig) => cutLayerTile(tiles, def, t, sig), deadlineMs: 20_000 });
		const started = Date.now();
		const res = await s.respond(sleeper(10), tileAt(-116.2, 43.6, 14), 'v1', 'gzip');
		const took = Date.now() - started;
		expect(res.headers.get('x-tile-status')).toBe('timeout');
		expect(took).toBeGreaterThanOrEqual(STATEMENT_TIMEOUT_MS - 100);
		expect(took).toBeLessThan(STATEMENT_TIMEOUT_MS + 2_000);
	}, 15_000);

	it('cancels a cut in the database at the deadline', async () => {
		const s = layerTileServer({ version: async () => 'v1', cut: (def, t, sig) => cutLayerTile(tiles, def, t, sig), deadlineMs: 300 });
		const started = Date.now();
		const res = await s.respond(sleeper(2.5), tileAt(-116.2, 43.6, 14), 'v1', 'gzip');
		expect(Date.now() - started).toBeLessThan(1_500);
		expect(res.headers.get('x-tile-status')).toBe('timeout');
		await new Promise((r) => setTimeout(r, 300));
		const [{ n }] = await admin`select count(*)::int as n from pg_stat_activity
			where application_name = 'tvt-app-tiles' and state = 'active' and query like '%pg_sleep%'`;
		expect(n).toBe(0);
	}, 10_000);

	it('connects read-only', async () => {
		await expect(tiles`create table tvt_test_mvt.nope (a int)`).rejects.toMatchObject({ code: '25006' });
	});

	it("reads each layer's newest version for /api/meta", async () => {
		await admin`insert into core.layer_version (layer, version, licence, republish) values
			('tvt_test.units', 'a1', 'public domain', 'yes'), ('tvt_test.units', 'a2', 'public domain', 'yes'),
			('tvt_test.paths', 'p1', 'ODbL', 'yes')`;
		const part = await readDatabase(admin);
		expect(part.layers?.['tvt_test.units']).toBe('a2');
		expect(part.layers?.['tvt_test.paths']).toBe('p1');
		const [current] = await admin`select version from core.layer_version_current where layer = 'tvt_test.units'`;
		expect(current.version).toBe('a2');
	});
});
