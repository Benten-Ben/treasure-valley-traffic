/**
 * Synthetic water rows for the @water specs (landscape sprint plan v3 §4.2 P4-app), set up by the spec and taken
 * away after it. Everything is made up and matches the fixture tiles (basemap/landscape/fixtures/water.*.geojson,
 * written by `app/scripts/tiles-fixture.mjs`), so a click on a fixture line finds its row:
 *
 * - **the plugin's tables:** water 0001 (applied here only when the database lacks it, and then dropped again);
 * - **the network:** the fixture's six reaches and its pond as `water.reach` and `water.body` rows, two canals
 *   (a main canal with a gauge, a diversion dam at its head and two invented IDWR-style service areas, and a
 *   lateral), a dam, a gauge `FXTEST1` and a made-up reading from half an hour ago;
 * - **the notices:** one invented river hazard and one invented E. coli site, in the City's field names.
 *
 * Nothing here is a real record, a real agency's area or a real result; the names say "Fixture". Rows are
 * removed by the build they belong to and by their keys, so a database that also holds real water rows keeps
 * them (the specs run on a throwaway clone anyway).
 */
import { readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import postgres from 'postgres';
import { APP_DIR } from '../../scripts/harness-env.mjs';

const REPO = resolve(APP_DIR, '..');
const NOTE = 'water e2e seed (synthetic)';
export const NHD_ONLY_ID = 2251799813686239;
export const GAUGE = 'FXTEST1';
export const SERVICE_AREAS = ['Fixture Irrigation District', 'Fixture Ditch Company'] as const;
const SOURCES = ['nwps_gauges', 'boise_river_hazards', 'boise_ecoli'] as const;

const db = () => postgres(process.env.DATABASE_URL!, { max: 1, onnotice: () => {} });

export interface Seeded {
	/** Whether we applied the plugin's migrations (and so drop the schema after). */
	madeSchema: boolean;
	/** The ops.source rows we made. */
	madeSources: string[];
	build: number;
}

const line = (coords: [number, number][]) => `SRID=4326;LINESTRING(${coords.map((c) => c.join(' ')).join(', ')})`;

export async function seedWater(): Promise<Seeded> {
	const sql = db();
	try {
		const [has] = await sql`select to_regclass('water.reach') is not null as ok`;
		let madeSchema = false;
		if (!has.ok) {
			for (const f of ['0001_hydrography.sql', '0002_canal_season.sql']) await sql.unsafe(readFileSync(join(REPO, 'plugins', 'water', 'migrations', f), 'utf8'));
			madeSchema = true;
		}
		await clean(sql);
		const madeSources: string[] = [];
		for (const name of SOURCES) {
			const [r] = await sql`select 1 as ok from ops.source where name = ${name}`;
			if (!r) {
				await sql`insert into ops.source (name, title, url, access) values (${name}, ${name}, 'https://example.test/', 'open')`;
				madeSources.push(name);
			}
		}
		const now = new Date();
		const halfHourAgo = new Date(now.getTime() - 30 * 60_000);
		const build = await sql.begin(async (tx) => {
			const [{ id: build }] = await tx`insert into water.build (note) values (${NOTE}) returning id`;
			const reach = (id: number, kind: string, name: string | null, o: { width: number; width_from?: string; flow?: string; piped?: boolean; from?: string; canal?: number | null; coords: [number, number][]; minzoom: number; name_from?: string | null }) =>
				tx`insert into water.reach (id, kind, name, name_from, flow, piped, width_m, width_from, minzoom, geometry_from, confirmed, canal_id, length_m, geom, build_id)
				   values (${id}, ${kind}, ${name}, ${o.name_from === undefined ? (name ? 'osm' : null) : o.name_from}, ${o.flow ?? 'perennial'}, ${o.piped ?? false}, ${o.width}, ${o.width_from ?? 'kind'}, ${o.minzoom},
				           ${o.from ?? 'osm'}, ${(o.from ?? 'osm') === 'osm'}, ${o.canal ?? null}, 1200, ST_GeomFromEWKT(${line(o.coords)}), ${build})`;
			await reach(7001, 'canal', 'Fixture Main Canal', { width: 14, canal: 1, minzoom: 10, name_from: 'hydroshare', coords: [[-116.36, 43.592], [-116.3, 43.6], [-116.24, 43.606], [-116.19, 43.608], [-116.13, 43.603]] });
			await reach(7002, 'lateral', 'Fixture Lateral', { width: 4, canal: 2, minzoom: 12, coords: [[-116.21, 43.6075], [-116.2055, 43.613], [-116.204, 43.619]] });
			await reach(7003, 'ditch', 'Fixture Ditch', { width: 1.5, minzoom: 13, coords: [[-116.204, 43.619], [-116.199, 43.6185], [-116.196, 43.6215]] });
			await reach(7004, 'lateral', 'Fixture Piped Lateral', { width: 3, piped: true, canal: 2, minzoom: 16, coords: [[-116.204, 43.619], [-116.2085, 43.6205], [-116.211, 43.6225]] });
			await reach(NHD_ONLY_ID, 'stream', null, { width: 3, from: 'nhd', width_from: 'order', minzoom: 13, coords: [[-116.1925, 43.61], [-116.19, 43.614], [-116.189, 43.618]] });
			await reach(7006, 'stream', 'Fixture Gulch', { width: 2, flow: 'intermittent', width_from: 'order', minzoom: 13, coords: [[-116.215, 43.61], [-116.213, 43.614], [-116.212, 43.617]] });
			await tx`insert into water.reach_evidence (reach_id, source, source_id, role, share, distance_m)
			         values (7001, 'osm_waterways', 'w700100', 'geometry', 1, null), (7001, 'nhd_hr', 'FIXTURE-NHD-1', 'attributes', 0.95, 3.5),
			                (7001, 'hydroshare_canals', 'FX1', 'name', 0.9, 5)`;
			await tx`insert into water.structure (id, kind, name, source, source_id, reach_id, minzoom, geom, build_id)
			         values (9001, 'dam', 'Fixture Diversion Dam', 'osm_waterways', 'w900100', 7001, 11, ST_GeomFromEWKT('SRID=4326;POINT(-116.3 43.6)'), ${build})`;
			await tx`insert into water.canal (id, name, kind, length_m, piped_m, reaches, head_reach_id, head_structure_id, source_kind, gauge_lid, sources, build_id)
			         values (1, 'Fixture Main Canal', 'main_canal', 31000, 0, 5, 7001, 9001, 'reservoir', ${GAUGE}, ${tx.array(['osm_waterways', 'nhd_hr', 'hydroshare_canals'])}, ${build}),
			                (2, 'Fixture Lateral', 'lateral', 900, 150, 2, 7002, null, 'canal', null, ${tx.array(['osm_waterways', 'nhd_hr'])}, ${build})`;
			await tx`update water.canal set source_canal_id = 1 where id = 2`;
			await tx`insert into water.gauge (lid, name, reach_id, canal_id, method, distance_m, geom, build_id)
			         values (${GAUGE}, 'Fixture Canal Diversion', 7001, 1, 'name', 10, ST_GeomFromEWKT('SRID=4326;POINT(-116.24 43.606)'), ${build})`;
			await tx`insert into water.body (id, kind, name, intermittent, area_m2, minzoom, geometry_from, confirmed, osm_type, osm_id, geom, build_id)
			         select 8001, 'pond', 'Fixture Pond', false, 4200, 11, 'osm', true, 'w', 800100, ST_Multi(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(${JSON.stringify(pondShape())}), 4326))), ${build}`;
			await tx`insert into water.canal_org (canal_id, objectid, name, share, at_head, build_id)
			         values (1, 99001, ${SERVICE_AREAS[0]}, 0.7, true, ${build}), (1, 99002, ${SERVICE_AREAS[1]}, 0.3, false, ${build})`;
			return build as number;
		});
		const reading = { lid: GAUGE, pe: 'HGIRZZZ', t: halfHourAgo.toISOString().replace(/\.\d{3}Z$/, 'Z'), primary: 7.33, secondary: 1.66, units: ['ft', 'kcfs'] };
		await sql`insert into raw.record (source, source_id, version_hash, payload, geom, first_seen, last_seen)
		          values ('nwps_gauges', ${`${GAUGE}@${reading.t}`}, ${Buffer.from('fx-r')}, ${sql.json(reading)}, ST_GeomFromEWKT('SRID=4326;POINT(-116.24 43.606)'), ${now}, ${now}),
		                 ('nwps_gauges', ${GAUGE}, ${Buffer.from('fx-m')}, ${sql.json({ lid: GAUGE, usgsId: '', dataAttribution: [] })}, null, ${now}, ${now})`;
		await sql`insert into evt.event (source, source_id, kind, geom, declared, observed, active, severity, description, attributes, content_hash, updated_at)
		          values ('boise_river_hazards', 'fx-1', 'river_hazard', ST_GeomFromEWKT('SRID=4326;POINT(-116.2 43.6125)'), tstzrange(${halfHourAgo}, null), tstzrange(${halfHourAgo}, null), true, 'temporary',
		                  'Fixture Fallen Tree: A made-up tree across a made-up channel', ${sql.json({ type: 'temporary', status: 'active', name: 'Fixture Fallen Tree', mile_marker: '1.0' })}, ${Buffer.from('fx-h')}, ${now})`;
		await sql`insert into raw.record (source, source_id, version_hash, payload, geom, first_seen, last_seen)
		          values ('boise_ecoli', 'FXPOND1|2030-07-01|FX-1', ${Buffer.from('fx-e')},
		                  ${sql.json({ SampleName: 'FXPOND1', SampleDescription: 'Fixture Pond Site', SampleDatetime: '2030-07-01', FinalResultNumeric: 12.5, Units: 'MPN/100 mL', LabNumber: 'FX-1', MostRecent: 'Y' })},
		                  ST_GeomFromEWKT('SRID=4326;POINT(-116.194 43.6082)'), ${now}, ${now})`;
		return { madeSchema, madeSources, build };
	} finally {
		await sql.end();
	}
}

/** A small pond (an irregular polygon near the fixture's, in GeoJSON). */
function pondShape() {
	const c = [-116.1935, 43.6082];
	const ring: [number, number][] = [];
	for (let i = 0; i < 16; i++) {
		const a = (i / 16) * 2 * Math.PI;
		const r = 1 + 0.25 * Math.sin(3 * a);
		ring.push([c[0] + r * 0.0007 * Math.cos(a), c[1] + r * 0.0005 * Math.sin(a)]);
	}
	ring.push(ring[0]);
	return { type: 'Polygon', coordinates: [ring] };
}

async function clean(sql: postgres.Sql) {
	const [has] = await sql`select to_regclass('water.build') is not null as ok`;
	if (has.ok) {
		const builds = (await sql`select id from water.build where note = ${NOTE}`).map((b) => b.id);
		if (builds.length) {
			for (const t of ['canal_org', 'gauge', 'structure', 'canal', 'body', 'reach']) await sql.unsafe(`delete from water.${t} where build_id = any($1::bigint[])`, [builds]);
			await sql`delete from water.reach_evidence where reach_id in (7001, 7002, 7003, 7004, 7006, ${NHD_ONLY_ID})`;
			await sql`delete from water.build where id = any(${builds})`;
		}
	}
	await sql`delete from raw.record where (source = 'nwps_gauges' and source_id like ${GAUGE + '%'}) or (source = 'boise_ecoli' and source_id like 'FXPOND1|%')`;
	await sql`delete from evt.event where source = 'boise_river_hazards' and source_id = 'fx-1'`;
}

/** Take away what the spec made. */
export async function cleanWater(seeded: Seeded | null): Promise<void> {
	if (!seeded) return;
	const sql = db();
	try {
		await clean(sql);
		if (seeded.madeSchema) await sql`drop schema if exists water cascade`;
		for (const name of seeded.madeSources) await sql`delete from ops.source where name = ${name}`;
	} finally {
		await sql.end();
	}
}
