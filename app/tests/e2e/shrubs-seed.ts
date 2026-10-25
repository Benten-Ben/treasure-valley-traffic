/**
 * Shrubs for the @shrubs spec (docs/19 §19.8, plan P11-app), set up by the spec and taken away after it:
 *
 * - **the tables:** the trees plugin's shrub migration, when the database doesn't have `trees.shrub` (the migration
 *   needs `trees.build`'s schema and `ops.schema_migration` from the plugin's first one: run db/migrate.py first);
 * - **SYNTHETIC shrubs:** 1,800 made-up shrubs (ids `e2e-shrubs-N`, one build `e2e-shrubs`) scattered in a 280 m
 *   disc round the North End, more than the 1,500 the layer draws, in their own area (`e2e`): random places and
 *   sizes, bush and sage, no real record. The build is marked licence Copernicus, republish yes.
 */
import { readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import postgres from 'postgres';
import { APP_DIR } from '../../scripts/harness-env.mjs';

const REPO = resolve(APP_DIR, '..');
const db = () => postgres(process.env.DATABASE_URL!, { max: 1, onnotice: () => {} });

export const NORTH_END: [number, number] = [-116.20892, 43.62755];
export const AREA = 'e2e';
export const BUILD = 'e2e-shrubs';
export const COUNT = 1800;
export const RADIUS_M = 280;

export interface Seeded {
	/** Whether we made the shrub tables (and so drop them after). */
	madeTables: boolean;
	shrubs: number;
}

export async function seedShrubs(): Promise<Seeded> {
	const sql = db();
	try {
		const [has] = await sql`select to_regclass('trees.shrub') is not null as shrubs, to_regclass('trees.build') is not null as trees`;
		if (!has.trees) throw new Error('trees.build is missing: run db/migrate.py on this database first');
		const madeTables = !has.shrubs;
		if (madeTables) await sql.unsafe(readFileSync(join(REPO, 'plugins', 'trees', 'migrations', '0002_shrubs.sql'), 'utf8'));
		await clearRows(sql);
		const [lng, lat] = NORTH_END;
		const dLng = 600 / (111_320 * Math.cos((lat * Math.PI) / 180));
		const dLat = 600 / 110_574;
		await sql`select setseed(0.29)`;
		await sql.begin(async (tx) => {
			await tx`insert into trees.shrub_build (build_id, area, started_at, finished_at, geom, license, republish, credit, counts)
				values (${BUILD}, ${AREA}, now(), now(),
				        ST_Multi(ST_MakeEnvelope(${lng - dLng}::float8, ${lat - dLat}::float8, ${lng + dLng}::float8, ${lat + dLat}::float8, 4326)),
				        'Copernicus', 'yes', 'U.S. Geological Survey, 3D Elevation Program; USDA NAIP', ${JSON.stringify({ shrubs: COUNT })}::jsonb)`;
			// A disc: radius sqrt(random) so the points spread evenly.
			await tx`
				insert into trees.shrub (shrub_id, area, look, geom, height_m, width_m, lidar, build_id)
				select 'e2e-shrubs-' || g, ${AREA}, case when random() < 0.7 then 'bush' else 'sage' end,
				       ST_SetSRID(ST_MakePoint(
				         ${lng}::float8 + sqrt(random()) * ${RADIUS_M}::float8 / ${111_320 * Math.cos((lat * Math.PI) / 180)}::float8 * cos(a),
				         ${lat}::float8 + sqrt(random()) * ${RADIUS_M}::float8 / 110574 * sin(a)), 4326),
				       h, 1.3 * power(h, 0.2), 'synthetic', ${BUILD}
				from (select g, random() * 6.283185 as a, 0.3 + random() * 2.0 as h from generate_series(1, ${COUNT}) g) s`;
		});
		const [{ n }] = await sql`select count(*)::int as n from trees.shrub where build_id = ${BUILD}`;
		return { madeTables, shrubs: n };
	} finally {
		await sql.end();
	}
}

async function clearRows(sql: postgres.Sql) {
	await sql`delete from trees.shrub where build_id = ${BUILD}`;
	await sql`delete from trees.shrub_build where build_id = ${BUILD}`;
}

/** Take away what the spec made: the rows, and the tables only if we made them. */
export async function cleanShrubs(seeded: Seeded | null): Promise<void> {
	const sql = db();
	try {
		const [has] = await sql`select to_regclass('trees.shrub') is not null as ok`;
		if (has.ok) await clearRows(sql);
		if (seeded?.madeTables)
			await sql.unsafe(
				"drop view trees.shrub_area; drop table trees.shrub; drop table trees.shrub_build; delete from ops.schema_migration where name = 'trees/0002_shrubs.sql';"
			);
	} finally {
		await sql.end();
	}
}
