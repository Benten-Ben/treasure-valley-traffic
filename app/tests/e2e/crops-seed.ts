/**
 * Crop fields for the @crops specs (landscape sprint P3-app), set up by the spec and taken away after it:
 *
 * - **the farm migration** (plugins/farm/migrations/0001_fields.sql), if the database doesn't have it;
 * - **three SYNTHETIC fields** (invented outlines, made-up CSBIDs `e2e-*`, in an edition `csb-2018-2025-e2e`,
 *   no real USDA record) with eight made-up crop years each, the z8-10 dissolves `farm.field_lo` would hold for
 *   them (every year, and the growth state), the crop classes they use, and a layer version
 *   (`core.layer_version` `farm.crop_fields`, version `e2e-...`) so the tiles are served.
 *
 * Nothing here is a real field. The rows are removed after the spec (whatever the database held before stays).
 */
import { readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import postgres from 'postgres';
import { APP_DIR } from '../../scripts/harness-env.mjs';

const REPO = resolve(APP_DIR, '..');
export const EDITION = 'csb-2018-2025-e2e';
export const VERSION = `e2e-${Date.now().toString(36)}`;
export const CREDIT = 'USDA NASS Crop Sequence Boundaries 2018-2025 and USDA NASS Cropland Data Layer (synthetic test fields)';
const db = () => postgres(process.env.DATABASE_URL!, { max: 1, onnotice: () => {} });

/** Crop classes the synthetic fields use: [code, name, group, letter]. */
const CLASSES: [number, string, string, string][] = [
	[1, 'Corn', 'corn', 'c'],
	[36, 'Alfalfa', 'hay', 'h'],
	[24, 'Winter Wheat', 'grain', 'g'],
	[41, 'Sugarbeets', 'roots', 'r'],
	[176, 'Grassland/Pasture', 'pasture', 'p'],
	[122, 'Developed/Open Space', 'developed', 'd']
];
const LETTER = Object.fromEntries(CLASSES.map(([code, , , letter]) => [code, letter]));
const GROUP = Object.fromEntries(CLASSES.map(([code, , group]) => [code, group]));

/** Three adjacent rectangles near Nampa (about 490 m by 440 m each). */
const W = 0.006;
const H = 0.004;
const ORIGIN: [number, number] = [-116.565, 43.578];
export const FIELDS = [
	// A: corn for four years, then hay.
	{ csbid: 'e2e-a', crops: [1, 1, 1, 1, 36, 36, 36, 36], dx: 0, growth: 'farmed' },
	// B: hay, then pasture, then developed, with permits: being built.
	{ csbid: 'e2e-b', crops: [36, 36, 36, 36, 36, 36, 176, 122], dx: W + 0.0004, growth: 'being_built' },
	// C: grain and sugar beets in rotation.
	{ csbid: 'e2e-c', crops: [24, 24, 41, 41, 24, 24, 41, 41], dx: 2 * (W + 0.0004), growth: 'farmed' }
] as const;

/** A field's centre, for the spec to point the map at. */
export const centre = (i: number): [number, number] => [ORIGIN[0] + FIELDS[i].dx + W / 2, ORIGIN[1] + H / 2];
export const CENTRE: [number, number] = [ORIGIN[0] + (2 * (W + 0.0004) + W) / 2, ORIGIN[1] + H / 2];

/** The dissolves' tile coordinates: nothing real is cut to these (the views read by zoom), so they mark ours. */
const MARK = -999;

export interface Seeded {
	madeSchema: boolean;
	ids: number[];
	/** Crop classes this seed added (the database had no row for them). */
	addedClasses: number[];
}

/** The migration, the classes, the edition, the fields, their dissolves and a layer version. */
export async function seedCrops(): Promise<Seeded> {
	const sql = db();
	try {
		const [has] = await sql`select to_regclass('farm.field') is not null as farm, to_regclass('core.layer_version') is not null as versions`;
		if (!has.versions) throw new Error('core.layer_version is missing: run db.mjs migrate');
		let madeSchema = false;
		if (!has.farm) {
			await sql.unsafe(readFileSync(join(REPO, 'plugins', 'farm', 'migrations', '0001_fields.sql'), 'utf8'));
			madeSchema = true;
		}
		await clean(sql);
		const ids: number[] = [];
		const addedClasses: number[] = [];
		await sql.begin(async (tx) => {
			for (const [code, name, grp, letter] of CLASSES) {
				const added = await tx`insert into farm.crop_class (code, name, grp, letter) values (${code}, ${name}, ${grp}, ${letter}) on conflict do nothing returning code`;
				if (added.length) addedClasses.push(code);
			}
			await tx`insert into farm.edition (edition, first_year, last_year, published, file, sha256, license, republish, credit)
			         values (${EDITION}, 2018, 2025, '2026-03-27', 'e2e-synthetic', ${'0'.repeat(64)}, 'synthetic test data', 'no', ${CREDIT})`;
			for (const f of FIELDS) {
				const x0 = ORIGIN[0] + f.dx;
				const wkt = `SRID=4326;MULTIPOLYGON(((${x0} ${ORIGIN[1]}, ${x0 + W} ${ORIGIN[1]}, ${x0 + W} ${ORIGIN[1] + H}, ${x0} ${ORIGIN[1] + H}, ${x0} ${ORIGIN[1]})))`;
				const letters = f.crops.map((c) => LETTER[c]).join('');
				const now = GROUP[f.crops[7]];
				const detail = f.growth === 'being_built' ? { rule: 'growth/1', permits: 7, early_years: [2018, 2021], developed_by: 2025, farmed_early: 4, permit_years: [2022, 2024] } : { rule: 'growth/1' };
				const [row] = await tx`
					insert into farm.field (field_id, edition, geom, label_pt, acres, county, first_year, crops, letters, group_now, agree, july, growth, growth_detail, valid_from)
					values (${f.csbid}, ${EDITION}, ST_GeomFromEWKT(${wkt}), ST_PointOnSurface(ST_GeomFromEWKT(${wkt})),
					        (ST_Area(ST_Transform(ST_GeomFromEWKT(${wkt}), 32611)) / 4046.8564224)::real, 'Canyon', 2018, ${f.crops as unknown as number[]},
					        ${letters}, ${now}, ${tx.json({ '2024': 0.62, '2025': 0.91 })}, ${tx.json({ year: 2025, ndvi: 0.71, state: 'green', px: 400 })},
					        ${f.growth}, ${tx.json(detail)}, '2026-03-27')
					returning id`;
				ids.push(Number(row.id));
			}
			// The dissolves farm.field_lo holds: every year's groups (now = the newest), and the growth state.
			for (const z of [8, 9, 10])
				for (let yr = 2018; yr <= 2025; yr++)
					await tx`
						insert into farm.field_lo (z, x, y, yr, key, now, geom)
						select ${z}, ${MARK}, ${MARK}, ${yr}, group_of, ${yr === 2025}, ST_Multi(ST_Union(g))
						from (select ST_Transform(f.geom, 3857) as g, c.grp as group_of
						      from farm.field f join farm.crop_class c on c.code = f.crops[${yr - 2017}]
						      where f.edition = ${EDITION} and c.grp not in ('developed', 'other')) q
						group by group_of`;
			for (const z of [8, 9, 10])
				await tx`
					insert into farm.field_lo (z, x, y, yr, key, now, geom)
					select ${z}, ${MARK}, ${MARK}, null, growth, true, ST_Multi(ST_Union(ST_Transform(geom, 3857)))
					from farm.field where edition = ${EDITION} and growth in ('built_over', 'being_built') group by growth`;
			await tx`insert into core.layer_version (layer, version, build, features, license, republish, credit, note)
			         values ('farm.crop_fields', ${VERSION}, 'e2e synthetic', 3, 'synthetic test data', 'no', ${CREDIT}, 'e2e: synthetic fields, removed after the spec')`;
		});
		return { madeSchema, ids, addedClasses };
	} finally {
		await sql.end();
	}
}

async function clean(sql: postgres.Sql) {
	await sql`delete from core.layer_version where layer = 'farm.crop_fields' and version like 'e2e-%'`;
	await sql`delete from farm.field_lo where x = ${MARK} and y = ${MARK}`;
	await sql`delete from farm.field where edition = ${EDITION}`;
	await sql`delete from farm.edition where edition = ${EDITION}`;
}

/** Take away what the spec made (the schema too, if the spec made it). */
export async function cleanCrops(seeded: Seeded | null): Promise<void> {
	const sql = db();
	try {
		const [has] = await sql`select to_regclass('farm.field') is not null as farm`;
		if (has.farm) {
			if (seeded?.madeSchema) await sql`drop schema farm cascade`;
			else {
				await clean(sql);
				if (seeded?.addedClasses.length) await sql`delete from farm.crop_class where code = any(${seeded.addedClasses})`;
			}
		}
		await sql`delete from core.layer_version where layer = 'farm.crop_fields' and version like 'e2e-%'`;
	} finally {
		await sql.end();
	}
}
