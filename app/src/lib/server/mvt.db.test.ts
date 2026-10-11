import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import { gunzipSync } from 'node:zlib';
import { VectorTile } from '@mapbox/vector-tile';
import { PbfReader } from 'pbf';
import postgres from 'postgres';

vi.mock('$app/env/private', () => ({ DATABASE_URL: undefined, FRAMES_DIR: '/nonexistent', TVT_FRAME_SOURCE: 'fixture' }));
const { cancelOnAbort, cutLayerTile, layerTileServer, STATEMENT_TIMEOUT_MS, TILE_LAYERS, tilePoolOptions } = await import('./mvt.js');
const { readDatabase } = await import('./versions.js');
type TileLayerDef = import('./mvt.js').TileLayerDef;

/**
 * The toggled layers' tiles against a real PostGIS (#lib/server/mvt; plan C4):
 * the SQL a definition makes, the tile pool's statement timeout and
 * read-only connections, the deadline's cancel, an empty tile before a
 * migration, the version read in the cut's own snapshot, /api/meta's layer
 * versions (migration 0020), the tile login (deploy/tvt_tiles.sql), and a cut
 * of every registered layer.
 *
 * Runs only with TVT_TEST_DATABASE_URL, a scratch database migrated with
 * db/migrate.py (never `tvt`). The tile login's tests run once
 * deploy/tvt_tiles.sql has run there (as a superuser) and skip until then;
 * they log in as tvt_tiles with TVT_TEST_TILES_DATABASE_URL, or else with
 * TVT_TEST_DATABASE_URL's address and no password (a laptop's trust login).
 * Its made-up rows go in the made-up plugin `tvt_test`'s schema (and a
 * made-up private one) and layer names under `tvt_test.`, all removed
 * afterwards.
 */
const URL = process.env.TVT_TEST_DATABASE_URL;

/** The tile login's URL for the test database. */
function tilesLoginUrl(): string {
	if (process.env.TVT_TEST_TILES_DATABASE_URL) return process.env.TVT_TEST_TILES_DATABASE_URL;
	const u = new globalThis.URL(URL!);
	u.username = 'tvt_tiles';
	u.password = '';
	return u.toString();
}
/** The made-up plugin's own schema, as a plugin's tables are (plan C3). */
const SCHEMA = 'tvt_test';
const PRIVATE = 'private_tvt_test';

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

const BOISE = [-116.2, 43.6] as const;

describe.skipIf(!URL)('toggled-layer tiles on PostGIS', () => {
	let admin: postgres.Sql;
	let tiles: postgres.Sql;
	/** The tile pool logged in as deploy/tvt_tiles.sql's login, when that has run in this database. */
	let asRole: postgres.Sql | undefined;

	beforeAll(async () => {
		admin = postgres(URL!, { max: 2, onnotice: () => {} });
		tiles = postgres(URL!, tilePoolOptions());
		const [{ ok, role }] = await admin`select to_regclass('core.layer_version') is not null as ok,
			coalesce((select rolcanlogin from pg_roles where rolname = 'tvt_tiles'), false)
			  and has_schema_privilege('tvt_tiles', 'core', 'USAGE') as role`;
		if (!ok) throw new Error('core.layer_version is missing: apply migration 0020 to the test database');
		await admin.unsafe(`
			drop schema if exists ${SCHEMA} cascade;
			drop schema if exists ${PRIVATE} cascade;
			create schema ${SCHEMA};
			create schema ${PRIVATE};
			create table ${PRIVATE}.secret (a int);
			insert into ${PRIVATE}.secret values (1);
			create table ${SCHEMA}.unit (gid int primary key, musym text, name text, geom geometry(Polygon, 4326));
			create table ${SCHEMA}.unit_lo (gid int primary key, musym text, geom geometry(Polygon, 4326));
			create table ${SCHEMA}.label (musym text, pt geometry(Point, 3857));
			-- Two made-up units near Boise (-116.2, 43.6): one around the point, one 20 km away.
			insert into ${SCHEMA}.unit values
			  (1, 'AbC', 'Made-up loam', ST_MakeEnvelope(-116.205, 43.595, -116.195, 43.605, 4326)),
			  (2, 'XyZ', 'Far away', ST_MakeEnvelope(-115.96, 43.595, -115.95, 43.605, 4326));
			insert into ${SCHEMA}.unit_lo values (10, 'LO', ST_MakeEnvelope(-116.3, 43.5, -116.1, 43.7, 4326));
			insert into ${SCHEMA}.label values ('AbC', ST_Transform(ST_SetSRID(ST_MakePoint(-116.2, 43.6), 4326), 3857));
			delete from core.layer_version where layer like 'tvt\\_test.%';
			insert into core.layer_version (layer, version, license, republish, credit) values
			  ('tvt_test.units', 'v1', 'made up', 'yes', 'Made-up credit'), ('tvt_test.slow', 'v1', 'made up', 'yes', 'Made-up credit');
		`);
		if (role) {
			// As a plugin's schema is granted by deploy/tvt_tiles.sql's list (made-up plugins aren't in it).
			await admin.unsafe(`grant usage on schema ${SCHEMA} to tvt_tiles; grant select on all tables in schema ${SCHEMA} to tvt_tiles`);
			asRole = postgres(tilesLoginUrl(), tilePoolOptions());
			await asRole`select 1`.catch((e) => {
				throw new Error(`deploy/tvt_tiles.sql has run here, but tvt_tiles can't log in (set TVT_TEST_TILES_DATABASE_URL): ${e.message}`);
			});
		}
	});

	afterAll(async () => {
		if (admin) {
			await admin.unsafe(`drop schema if exists ${SCHEMA} cascade; drop schema if exists ${PRIVATE} cascade`);
			await admin`delete from core.layer_version where layer like 'tvt\\_test.%'`;
			await admin.end();
		}
		await tiles?.end();
		await asRole?.end();
	});

	const signal = () => new AbortController().signal;

	const mvtOf = async (cut: Promise<{ mvt: Uint8Array }>) => (await cut).mvt;

	it('cuts each part from its zoom band, with ids and properties', async () => {
		const z14 = decode(await mvtOf(cutLayerTile(tiles, UNITS, tileAt(-116.2, 43.6, 14), signal())));
		expect(Object.keys(z14.layers).sort()).toEqual(['labels', 'units']);
		expect(z14.layers.units.length).toBe(1);
		const f = z14.layers.units.feature(0);
		expect(f.id).toBe(1);
		expect(f.properties).toEqual({ musym: 'AbC', name: 'Made-up loam' });
		expect(f.type).toBe(3); // polygon
		expect(z14.layers.labels.feature(0).properties).toEqual({ musym: 'AbC' });
		expect(z14.layers.labels.feature(0).type).toBe(1); // point

		const z10 = decode(await mvtOf(cutLayerTile(tiles, UNITS, tileAt(-116.2, 43.6, 10), signal())));
		expect(Object.keys(z10.layers)).toEqual(['units']);
		expect(z10.layers.units.feature(0).properties).toEqual({ musym: 'LO' });
		expect(z10.layers.units.feature(0).id).toBe(10);
	});

	it('cuts nothing where there is nothing, and reads the version beside the data', async () => {
		expect(await cutLayerTile(tiles, UNITS, tileAt(-117.5, 44.5, 14), signal())).toEqual({ mvt: new Uint8Array(), version: 'v1' });
	});

	it("answers an empty tile before the plugin's migration (or with a misspelled table), and logs it", async () => {
		const noSchema: TileLayerDef = { ...UNITS, plugin: 'tvt_test_none', parts: [{ name: 'u', sources: [{ minzoom: 8, maxzoom: 16, table: 'tvt_test_none.unit' }] }] };
		const noTable: TileLayerDef = { ...UNITS, parts: [{ name: 'u', sources: [{ minzoom: 8, maxzoom: 16, table: `${SCHEMA}.unit_typo` }] }] };
		const noColumn: TileLayerDef = { ...UNITS, parts: [{ name: 'u', sources: [{ minzoom: 8, maxzoom: 16, table: `${SCHEMA}.unit`, columns: ['nope'] }] }] };
		const log = vi.fn();
		const s = layerTileServer({ version: async () => 'v1', cut: (def, t, sig) => cutLayerTile(tiles, def, t, sig), log });
		for (const def of [noSchema, noTable, noColumn]) {
			const res = await s.respond(def, tileAt(-116.2, 43.6, 14), 'v1', 'gzip');
			expect(res.status).toBe(200);
			expect(res.headers.get('x-tile-status')).toBe('missing');
		}
		const logged = log.mock.calls.flat().join('\n');
		expect(logged).toMatch(/tile layer tvt_test_none\.units: answered empty \(missing\) .*: 42P01 relation "tvt_test_none\.unit" does not exist/);
		expect(logged).toMatch(/tile layer tvt_test\.units: answered empty \(missing\) .*: 42P01 relation "tvt_test\.unit_typo" does not exist/);
		expect(log).toHaveBeenCalledTimes(2); // the column typo is the same layer and reason within the minute
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
		await expect(tiles`create table tvt_test.nope (a int)`).rejects.toMatchObject({ code: '25006' });
	});

	it("doesn't keep a tile cut after a build /api/meta hasn't seen yet", async () => {
		const s = layerTileServer({ version: async () => 'v1', cut: (def, t, sig) => cutLayerTile(tiles, def, t, sig) });
		const t = tileAt(-116.2, 43.6, 16);
		await admin`insert into core.layer_version (layer, version, license, republish, credit) values ('tvt_test.units', 'v2', 'made up', 'yes', 'Made-up credit')`;
		try {
			const res = await s.respond(UNITS, t, 'v1', 'gzip');
			expect(res.status).toBe(200);
			expect(res.headers.get('cache-control')).toBe('public, max-age=60');
			expect(res.headers.get('etag')).toBeNull();
			expect(s.cache.size).toBe(0);
			// Its own cut reads the version in its transaction's snapshot too.
			const own: TileLayerDef = { ...UNITS, parts: undefined, cut: async (sql) => new Uint8Array((await sql`select 1`).length) };
			expect((await cutLayerTile(tiles, own, t, signal())).version).toBe('v2');
		} finally {
			await admin`delete from core.layer_version where layer = 'tvt_test.units' and version = 'v2'`;
		}
	});

	it("reads each layer's newest version and credit for /api/meta", async () => {
		await admin`insert into core.layer_version (layer, version, license, republish, credit) values
			('tvt_test.units', 'a1', 'public domain', 'yes', 'USGS'), ('tvt_test.units', 'a2', 'public domain', 'yes', 'USGS; NRCS'),
			('tvt_test.paths', 'p1', 'ODbL', 'yes', '© OpenStreetMap contributors')`;
		const part = await readDatabase(admin);
		expect(part.layers?.['tvt_test.units']).toMatchObject({ version: 'a2', credit: 'USGS; NRCS', license: 'public domain', republish: 'yes' });
		expect(part.layers?.['tvt_test.units']?.builtAt).toBeGreaterThan(1.7e9);
		expect(part.layers?.['tvt_test.paths']).toMatchObject({ version: 'p1', credit: '© OpenStreetMap contributors' });
		const [current] = await admin`select version, credit from core.layer_version_current where layer = 'tvt_test.units'`;
		expect(current).toEqual({ version: 'a2', credit: 'USGS; NRCS' });
	});

	describe('as the tile login (deploy/tvt_tiles.sql)', () => {
		const ownCut = (table: string): TileLayerDef => ({
			plugin: 'tvt_test',
			layer: 'units',
			minzoom: 8,
			maxzoom: 16,
			cut: async (sql, _t, sig) => new Uint8Array((await cancelOnAbort(sig, () => sql.unsafe(`select 1 from ${table} limit 1`))).length)
		});

		it("cuts the plugin's own tables", async (ctx) => {
			if (!asRole) return ctx.skip();
			const [{ who, session }] = await asRole`select current_user as who, session_user as session`;
			expect([who, session]).toEqual(['tvt_tiles', 'tvt_tiles']);
			const z14 = decode(await mvtOf(cutLayerTile(asRole, UNITS, tileAt(-116.2, 43.6, 14), signal())));
			expect(z14.layers.units.length).toBe(1);
		});

		it('is refused restricted and private schemas, even by a cut of its own', async (ctx) => {
			if (!asRole) return ctx.skip();
			const log = vi.fn();
			const s = layerTileServer({ version: async () => 'v1', cut: (def, t, sig) => cutLayerTile(asRole!, def, t, sig), log });
			for (const table of ['restricted.crash_unit', `${PRIVATE}.secret`]) {
				const res = await s.respond(ownCut(table), tileAt(-116.2, 43.6, 14), 'v1', 'gzip');
				expect(res.headers.get('x-tile-status'), table).toBe('denied');
			}
			expect(log.mock.calls[0][0]).toMatch(/answered empty \(denied\) .*: 42501 permission denied for schema restricted/);
			// The superuser-or-owner pool would have read them: the login is what refuses.
			expect((await cutLayerTile(tiles, ownCut(`${PRIVATE}.secret`), tileAt(-116.2, 43.6, 14), signal())).mvt.length).toBe(1);
		});

		it("can't become anyone else: no superuser, a member of nothing", async (ctx) => {
			if (!asRole) return ctx.skip();
			const [me] = await asRole`select rolsuper, rolbypassrls from pg_roles where rolname = session_user`;
			expect(me).toEqual({ rolsuper: false, rolbypassrls: false });
			const [{ n }] = await asRole`select count(*)::int as n from pg_auth_members where member = session_user::regrole`;
			expect(n).toBe(0);
			// What a superuser's session could do (and a cut of its own might try) is refused.
			const [{ owner, root }] = await admin`select pg_get_userbyid(datdba) as owner,
				(select rolname from pg_roles where rolsuper order by oid limit 1) as root from pg_database where datname = current_database()`;
			await asRole.begin(async (tx) => {
				const ident = (name: string) => `"${name.replaceAll('"', '""')}"`;
				for (const attempt of [`set local role ${ident(owner)}`, `set local session authorization ${ident(owner)}`, `set local role ${ident(root)}`])
					await expect(tx.savepoint((sp) => sp.unsafe(attempt)), attempt).rejects.toMatchObject({ code: '42501' });
				await tx`set local role none`;
				const [{ who }] = await tx`select current_user as who`;
				expect(who).toBe('tvt_tiles');
				await expect(tx.savepoint((sp) => sp`select count(*) from restricted.crash_unit`)).rejects.toMatchObject({ code: '42501' });
			});
		});

		it("can't write, even with read-only switched off", async (ctx) => {
			if (!asRole) return ctx.skip();
			await expect(
				asRole.begin('read write', (tx) => tx`insert into core.layer_version (layer, version, license, republish, credit) values ('tvt_test.x', 'w', 'x', 'yes', 'x')`)
			).rejects.toMatchObject({ code: '42501' });
			await expect(asRole.begin('read write', (tx) => tx`create table tvt_test.nope (a int)`)).rejects.toMatchObject({ code: '42501' });
		});
	});

	it('cuts a tile of every registered layer at each of its zoom bands, with nothing missing or refused', async () => {
		// The layers in #lib/server/<plugin>/tiles.ts against this database, migrated with their plugins'
		// migrations: a misspelled table or column, or a schema the tile login isn't granted, fails here.
		const pool = asRole ?? tiles;
		for (const def of TILE_LAYERS.values()) {
			const zooms = def.parts ? [...new Set(def.parts.flatMap((p) => p.sources.map((src) => src.minzoom)))] : [def.minzoom];
			for (const z of zooms) {
				const t = tileAt(BOISE[0], BOISE[1], z);
				await expect(cutLayerTile(pool, def, t, signal()), `${def.plugin}.${def.layer} at ${z}/${t.x}/${t.y}`).resolves.toHaveProperty('mvt');
			}
		}
	});
});
