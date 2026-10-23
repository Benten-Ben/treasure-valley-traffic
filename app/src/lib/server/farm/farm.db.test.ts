import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import { gunzipSync, gzipSync } from 'node:zlib';
import { VectorTile } from '@mapbox/vector-tile';
import { PbfReader } from 'pbf';
import postgres from 'postgres';
import { fieldCard, yearInfo, type Sql } from './fields.js';

vi.mock('$app/env/private', () => ({ DATABASE_URL: undefined, FRAMES_DIR: '/nonexistent', TVT_FRAME_SOURCE: 'fixture' }));
const { cutLayerTile, layerTileServer, tilePoolOptions } = await import('../mvt.js');
const tiles = (await import('./tiles.js')).default;

/**
 * The crop fields' tiles and card API against a real PostGIS with the farm migration (plugins/farm 0001):
 * one made-up field (edition `csb-2018-2025-dbtest`, CSBID `dbtest-1`, rows marked at tile -998/-998) with its
 * dissolves, cut by the real SQL at every zoom, an earlier year's cut, the card and the crop year. Runs only
 * with TVT_TEST_DATABASE_URL (never `tvt`); skips before the migration. Its rows are removed afterwards.
 */
const URL = process.env.TVT_TEST_DATABASE_URL;
const sql = URL ? postgres(URL, { max: 2, onnotice: () => {} }) : null;
const pool = URL ? postgres(URL, tilePoolOptions()) : null;
const EDITION = 'csb-2018-2025-dbtest';
const MARK = -998;
const VERSION = `dbtest-${Date.now().toString(36)}`;
const WKT = 'SRID=4326;MULTIPOLYGON(((-116.565 43.578, -116.559 43.578, -116.559 43.582, -116.565 43.582, -116.565 43.578)))';
let ready = false;
let fieldId = 0;
const addedClasses: number[] = [];

const tileAt = (lon: number, lat: number, z: number) => {
	const n = 2 ** z;
	const r = (lat * Math.PI) / 180;
	return { z, x: Math.floor(((lon + 180) / 360) * n), y: Math.floor(((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * n) };
};
const decode = (gz: Uint8Array) => new VectorTile(new PbfReader(gunzipSync(gz)));

async function clean() {
	await sql!`delete from core.layer_version where layer = 'farm.crop_fields' and version like 'dbtest-%'`;
	await sql!`delete from farm.field_lo where x = ${MARK} and y = ${MARK}`;
	await sql!`delete from farm.field where edition = ${EDITION}`;
	await sql!`delete from farm.edition where edition = ${EDITION}`;
	if (addedClasses.length) await sql!`delete from farm.crop_class where code = any(${addedClasses})`;
}

beforeAll(async () => {
	if (!sql) return;
	const [has] = await sql`select to_regclass('farm.field') is not null as farm, to_regclass('core.layer_version') is not null as versions`;
	if (!has.farm || !has.versions) return;
	ready = true;
	await clean();
	await sql.begin(async (tx) => {
		for (const [code, name, grp, letter] of [[36, 'Alfalfa', 'hay', 'h'], [1, 'Corn', 'corn', 'c']] as const) {
			const added = await tx`insert into farm.crop_class (code, name, grp, letter) values (${code}, ${name}, ${grp}, ${letter}) on conflict do nothing returning code`;
			if (added.length) addedClasses.push(code);
		}
		await tx`insert into farm.edition (edition, first_year, last_year, file, sha256, license, republish, credit)
		         values (${EDITION}, 2018, 2025, 'dbtest', ${'0'.repeat(64)}, 'synthetic', 'no', 'synthetic')`;
		const [f] = await tx`
			insert into farm.field (field_id, edition, geom, acres, county, first_year, crops, letters, group_now, agree, july, growth, valid_from)
			values ('dbtest-1', ${EDITION}, ST_GeomFromEWKT(${WKT}), 53.4, 'Canyon', 2018, ${[1, 1, 1, 1, 36, 36, 36, 36]}, 'cccchhhh', 'hay',
			        ${tx.json({ '2025': 0.9 })}, ${tx.json({ year: 2025, ndvi: 0.7, state: 'green', px: 100 })}, 'farmed', '2026-03-27')
			returning id`;
		fieldId = Number(f.id);
		for (const z of [8, 9, 10])
			for (const [yr, key] of [[2018, 'corn'], [2025, 'hay']] as const)
				await tx`insert into farm.field_lo (z, x, y, yr, key, now, geom) values (${z}, ${MARK}, ${MARK}, ${yr}, ${key}, ${yr === 2025}, ST_Multi(ST_Transform(ST_GeomFromEWKT(${WKT}), 3857)))`;
		await tx`insert into core.layer_version (layer, version, license, republish, credit) values ('farm.crop_fields', ${VERSION}, 'synthetic', 'no', 'synthetic credit')`;
	});
});

afterAll(async () => {
	if (sql && ready) await clean();
	await sql?.end();
	await pool?.end();
});

describe.skipIf(!URL)('crop fields (database)', () => {
	it('cuts every zoom of the fields layer with the real SQL: dissolves by group, then the field with its columns', async ({ skip }) => {
		if (!ready) skip('the farm migration is not applied');
		const def = tiles[0];
		const stop = new AbortController().signal;
		for (const z of [8, 9, 10]) {
			const t = tileAt(-116.562, 43.58, z);
			const cut = await cutLayerTile(pool!, def, t, stop);
			expect(cut.version, `z${z}`).toBe(VERSION);
			const layer = decode(layerGzip(cut.mvt)).layers.fields;
			expect(layer, `z${z} has the layer`).toBeTruthy();
			const f = layer.feature(0);
			expect(f.properties.g).toBe('hay'); // the current crop year's dissolve
			expect(f.properties).not.toHaveProperty('s');
		}
		for (const z of [11, 12, 14]) {
			const t = tileAt(-116.562, 43.58, z);
			const layer = decode(layerGzip((await cutLayerTile(pool!, def, t, stop)).mvt)).layers.fields;
			const f = layer.feature(0);
			expect(f.id).toBe(fieldId);
			expect(f.properties).toMatchObject({ a: 53, g: 'hay', n: 'Alfalfa', y: 'cccchhhh', s: 'farmed', st: 'green', p: false });
		}
		// Outside the fields: an empty layer; below z8 there is no source.
		const far = await cutLayerTile(pool!, def, tileAt(-110, 40, 11), stop);
		expect(decode(layerGzip(far.mvt)).layers.fields?.length ?? 0).toBe(0);
		expect((await cutLayerTile(pool!, def, { z: 7, x: 22, y: 46 }, stop)).mvt.length).toBe(0);
	});

	it("cuts an earlier year's dissolves over field_lo and gives it the fields layer's version", async ({ skip }) => {
		if (!ready) skip('the farm migration is not applied');
		const year2018 = tiles.find((d) => d.layer === 'crop_year_2018')!;
		const year2019 = tiles.find((d) => d.layer === 'crop_year_2019')!;
		const stop = new AbortController().signal;
		const t = tileAt(-116.562, 43.58, 10);
		const cut = await cutLayerTile(pool!, year2018, t, stop);
		expect(cut.version).toBe(VERSION);
		expect(decode(layerGzip(cut.mvt)).layers.fields.feature(0).properties).toEqual({ g: 'corn' });
		// A year with no rows is an empty tile.
		expect((await cutLayerTile(pool!, year2019, t, stop)).mvt.length).toBe(0);
		// Served through the tile server under its own name, with the shared version.
		const server = layerTileServer({ version: async () => VERSION, cut: (d, tt, signal) => cutLayerTile(pool!, d, tt, signal) });
		const res = await server.respond(year2018, t, VERSION, 'gzip');
		expect(res.headers.get('etag')).toBe(`"farm.crop_year_2018-${VERSION}-gz"`);
		expect(decode(new Uint8Array(await res.arrayBuffer())).layers.fields.length).toBe(1);
	});

	it('reads the card and the crop year from the stored columns', async ({ skip }) => {
		if (!ready) skip('the farm migration is not applied');
		const card = (await fieldCard(sql as unknown as Sql, fieldId))!;
		expect(card).toMatchObject({ id: fieldId, county: 'Canyon', growth: 'farmed', agree: { '2025': 0.9 }, july: { year: 2025, state: 'green', ndvi: 0.7 }, credit: 'synthetic credit' });
		expect(card.years.map((y) => y.name)).toEqual(['Corn', 'Corn', 'Corn', 'Corn', 'Alfalfa', 'Alfalfa', 'Alfalfa', 'Alfalfa']);
		expect(card.centre[0]).toBeCloseTo(-116.562, 3);
		expect(card.bbox[0]).toBeCloseTo(-116.565, 3);
		expect(await fieldCard(sql as unknown as Sql, 2_000_000_000)).toBeNull();
		const year = await yearInfo(sql as unknown as Sql);
		expect(year.built).toBe(true);
		expect(year).toMatchObject({ year: 2025, first_year: 2018 });
	});
});

/** The cut's raw bytes, gzipped as the tile server would send them (the decoder wants bytes it can gunzip). */
function layerGzip(raw: Uint8Array): Uint8Array {
	return new Uint8Array(gzipSync(raw));
}
