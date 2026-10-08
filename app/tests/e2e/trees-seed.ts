/**
 * Trees for the @trees specs (docs/19 §19.6), set up by the spec and taken
 * away after it:
 *
 * - **the build:** the trees plugin's migration and a trees build loaded by
 *   the real loader (`python3 -m ingest trees-load --build DIR`). DIR is
 *   TVT_TREES_BUILD, by default the sample North End build kept with the
 *   private dev data (`$MAIN/data/dev/trees/test-c-window`, never
 *   committed). Already loaded: left as it is;
 * - **a FAKE catalogue:** when the database has no `city_trees.tree` (the
 *   private plugin's table, only on the owner's server), one is made with a
 *   few invented rows (made-up species and sizes, marked `layer =
 *   'synthetic-test'`) for trees the build already has, so the panel's
 *   catalogue fields can be checked. No real city record is used or kept;
 * - **synthetic trees for the measurement:** 15,000 made-up trees in their
 *   own area (`perf`), placed at random around the North End box.
 */
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import postgres from 'postgres';
import { APP_DIR, localSettings, mainCheckout } from '../../scripts/harness-env.mjs';

const REPO = resolve(APP_DIR, '..');
export const AREA = 'c';
export const PERF_AREA = 'perf';
const FAKE_LAYER = 'synthetic-test';
const python = () => process.env.TVT_PYTHON || localSettings(mainCheckout()).TVT_PYTHON || 'python3';
export const buildDir = () => process.env.TVT_TREES_BUILD || join(mainCheckout(), 'data', 'dev', 'trees', 'test-c-window');

const db = () => postgres(process.env.DATABASE_URL!, { max: 1, onnotice: () => {} });

/** The invented catalogue rows: names that say they're made up, sizes from nowhere. */
const FAKE_SPECIES = [
	{ common_name: 'Test linden (synthetic)', genus: 'Exemplia', species: 'fictus', dbh_in: 14, installed: '2009-04-15', last_verified: '2024-06-01', condition: 'Good', site_type: 'Street' },
	{ common_name: 'Sample maple (synthetic)', genus: 'Fabricata', species: 'imaginaria', dbh_in: 21, installed: '1998-10-02', last_verified: '2023-05-12', condition: 'Fair', site_type: 'Park' },
	{ common_name: 'Example oak (synthetic)', genus: 'Exemplia', species: 'inventa', dbh_in: 7, installed: '2019-03-20', last_verified: '2025-08-30', condition: 'Good', site_type: 'Street' }
];

export interface Seeded {
	/** Whether we made the fake catalogue table (and so drop it after). */
	madeCatalogue: boolean;
	/** Tree ids given a fake catalogue row: a catalogued one first. */
	faked: string[];
	trees: number;
}

/** The plugin's tables, the build, and (when there's no private table) the fake catalogue. */
export async function seedTrees(): Promise<Seeded> {
	const sql = db();
	try {
		const [has] = await sql`select to_regclass('trees.tree') is not null as trees, to_regclass('city_trees.tree') is not null as catalogue`;
		if (!has.trees) await sql.unsafe(readFileSync(join(REPO, 'plugins', 'trees', 'migrations', '0001_trees.sql'), 'utf8'));
		// Left over from a run that stopped halfway.
		await dropPerfTrees(sql);
		let [{ n }] = await sql`select count(*)::int as n from trees.tree where area = ${AREA}`;
		if (!n) {
			const dir = buildDir();
			if (!existsSync(join(dir, 'trees.geojson'))) throw new Error(`no trees build loaded and none at ${dir} (set TVT_TREES_BUILD)`);
			execFileSync(python(), ['-m', 'ingest', 'trees-load', '--build', dir], { cwd: REPO, env: { ...process.env }, stdio: 'pipe' });
			[{ n }] = await sql`select count(*)::int as n from trees.tree where area = ${AREA}`;
		}
		let madeCatalogue = false;
		let faked: string[] = [];
		if (!has.catalogue) {
			await sql.begin(async (tx) => {
				await tx`create schema if not exists city_trees`;
				await tx`create table city_trees.tree (
					catalogue_id text primary key, layer text, common_name text, genus text, species text, dbh_in real,
					installed date, last_verified date, condition text, site_type text, geom geometry(Point, 4326),
					attrs jsonb not null default '{}', fetched_at timestamptz not null default now())`;
			});
			madeCatalogue = true;
			// The tallest catalogued trees and one estimated one get invented rows.
			const picks = await sql`
				(select tree_id, catalogue_id from trees.tree where area = ${AREA} and kind = 'catalogued' order by height_m desc limit 2)
				union all
				(select tree_id, catalogue_id from trees.tree where area = ${AREA} and kind = 'estimated' order by height_m desc limit 1)`;
			for (const [i, p] of picks.entries()) {
				const f = FAKE_SPECIES[i % FAKE_SPECIES.length];
				await sql`insert into city_trees.tree (catalogue_id, layer, common_name, genus, species, dbh_in, installed, last_verified, condition, site_type)
					values (${p.catalogue_id}, ${FAKE_LAYER}, ${f.common_name}, ${f.genus}, ${f.species}, ${f.dbh_in}, ${f.installed}, ${f.last_verified}, ${f.condition}, ${f.site_type})`;
			}
			faked = picks.map((p) => String(p.tree_id));
		}
		return { madeCatalogue, faked, trees: n };
	} finally {
		await sql.end();
	}
}

/** Take away what the spec made: the fake catalogue (only if we made it) and the synthetic trees. */
export async function cleanTrees(seeded: Seeded | null): Promise<void> {
	const sql = db();
	try {
		if (seeded?.madeCatalogue) await sql`drop schema if exists city_trees cascade`;
		await dropPerfTrees(sql);
	} finally {
		await sql.end();
	}
}

/** 15,000 synthetic trees (made up: random places, sizes from the crown model's broadleaf curve) around the North End box. */
export async function seedPerfTrees(centre: [number, number], halfM = 900, count = 15_000): Promise<number> {
	const sql = db();
	try {
		await dropPerfTrees(sql);
		const dLng = halfM / (111_320 * Math.cos((centre[1] * Math.PI) / 180));
		const dLat = halfM / 110_574;
		await sql.begin(async (tx) => {
			await tx`insert into trees.build (build_id, area, started_at, finished_at, params, counts)
				values ('perf-synthetic', ${PERF_AREA}, now(), now(), '{"synthetic": true}', ${JSON.stringify({ trees: count })}::jsonb)`;
			await tx`select setseed(0.42)`;
			await tx`
				insert into trees.tree (tree_id, area, kind, type, geom, height_m, crown_radius_m, crown_a, crown_n, lidar, catalogue, catalogue_id, build_id)
				select 'perf-' || g, ${PERF_AREA}, 'placed',
				       (array['broadleaf', 'broadleaf', 'broadleaf', 'narrow', 'conifer'])[1 + floor(random() * 5)::int],
				       ST_SetSRID(ST_MakePoint(${centre[0]} + (random() * 2 - 1) * ${dLng}, ${centre[1]} + (random() * 2 - 1) * ${dLat}), 4326),
				       h, greatest(1, 0.345 * power(h, 1.01) * (0.8 + random() * 0.4)), 0.45, 1.64, 'synthetic', null, null, 'perf-synthetic'
				from (select g, 5 + random() * 23 as h from generate_series(1, ${count}) g) s`;
		});
		const [{ n }] = await sql`select count(*)::int as n from trees.tree where area = ${PERF_AREA}`;
		return n;
	} finally {
		await sql.end();
	}
}

async function dropPerfTrees(sql: postgres.Sql) {
	const [has] = await sql`select to_regclass('trees.tree') is not null as ok`;
	if (!has.ok) return;
	await sql`delete from trees.tree where area = ${PERF_AREA}`;
	await sql`delete from trees.build where build_id = 'perf-synthetic'`;
}
