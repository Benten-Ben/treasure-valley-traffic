/**
 * Soils for the @soils specs (landscape sprint P1-app), set up by the spec and taken away after it:
 *
 * - **the soils migration** (plugins/soils/migrations/0001_soils.sql), if the database doesn't have it;
 * - **four SYNTHETIC map units** (invented keys `99000nn`, a survey area `E2E01`, no real NRCS record) as
 *   four adjacent rectangles near Meridian, each one polygon: one with no restriction and good farmland, one
 *   with a hardpan, drained and a dual hydrologic group, one over bedrock, and one that is NRCS's "No Digital
 *   Data Available" (not surveyed); their components and horizons (made-up soils named "Testville"...), the
 *   generalised geometry the low zooms read, and a layer version (`core.layer_version` `soils.units`,
 *   version `e2e-...`) so the tiles are served.
 *
 * Nothing here is a real soil. The rows are removed after the spec (whatever the database held before stays).
 */
import { readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import postgres from 'postgres';
import { APP_DIR } from '../../scripts/harness-env.mjs';

const REPO = resolve(APP_DIR, '..');
export const AREA = 'E2E01';
export const BUILD = 'e2e-synthetic-soils';
export const VERSION = `e2e-${Date.now().toString(36)}`;
export const CREDIT = 'Soils: USDA NRCS, Soil Survey Geographic Database (SSURGO) (synthetic test soils)';
const db = () => postgres(process.env.DATABASE_URL!, { max: 1, onnotice: () => {} });

/** Four adjacent rectangles near Meridian (about 490 m by 440 m each). */
const W = 0.006;
const H = 0.004;
const GAP = 0.0004;
const ORIGIN: [number, number] = [-116.39, 43.6];

export interface Unit {
	mukey: string;
	musym: string;
	muname: string;
	dx: number;
	/** The show-by codes the tiles carry. */
	codes: { c_restr: number | null; pat: string | null; c_drain: number | null; c_aws: number | null; c_farm: number | null; farm_cond: string | null; c_hsg: number | null; hsg_dual: boolean | null };
	ground: string;
	misc: string | null;
	farmlndcl: string | null;
	drclassdcd: string | null;
	hydgrpdcd: string | null;
	aws: number | null;
	restr: { kind: string; top: number; hard: string } | null;
	components: { cokey: string; name: string; pct: number; major: boolean; texture: string; hydric: string }[];
}

export const UNITS: Unit[] = [
	{
		mukey: '9900001',
		musym: 'TeA',
		muname: 'Testville silt loam, 0 to 1 percent slopes',
		dx: 0,
		codes: { c_restr: 0, pat: 'none', c_drain: 1, c_aws: 3, c_farm: 2, farm_cond: 'irrigated', c_hsg: 1, hsg_dual: false },
		ground: 'testville:silt-loam',
		misc: null,
		farmlndcl: 'Prime farmland if irrigated',
		drclassdcd: 'Well drained',
		hydgrpdcd: 'B',
		aws: 17.4,
		restr: null,
		components: [
			{ cokey: '99000011', name: 'Testville', pct: 62, major: true, texture: 'Silt loam', hydric: 'No' },
			{ cokey: '99000012', name: 'Samplon', pct: 38, major: true, texture: 'Fine sandy loam', hydric: 'No' }
		]
	},
	{
		mukey: '9900002',
		musym: 'HdB',
		muname: 'Hardpan loam, 1 to 3 percent slopes',
		dx: W + GAP,
		codes: { c_restr: 4, pat: 'hardpan', c_drain: 4, c_aws: 0, c_farm: 1, farm_cond: 'drained', c_hsg: 3, hsg_dual: true },
		ground: 'hardpan:loam',
		misc: null,
		farmlndcl: 'Farmland of statewide importance, if drained',
		drclassdcd: 'Poorly drained',
		hydgrpdcd: 'B/D',
		aws: 3.2,
		restr: { kind: 'Duripan', top: 20, hard: 'Indurated' },
		components: [{ cokey: '99000021', name: 'Hardpan', pct: 100, major: true, texture: 'Loam', hydric: 'Partially hydric' }]
	},
	{
		mukey: '9900003',
		musym: 'RkC',
		muname: 'Rockton gravelly loam, 3 to 8 percent slopes',
		dx: 2 * (W + GAP),
		codes: { c_restr: 2, pat: 'bedrock', c_drain: 0, c_aws: 1, c_farm: 0, farm_cond: null, c_hsg: 2, hsg_dual: false },
		ground: 'rockton:gravelly-loam',
		misc: null,
		farmlndcl: 'Not prime farmland',
		drclassdcd: 'Excessively drained',
		hydgrpdcd: 'C',
		aws: 7.5,
		restr: { kind: 'Lithic bedrock', top: 40, hard: 'Strongly cemented' },
		components: [{ cokey: '99000031', name: 'Rockton', pct: 85, major: true, texture: 'Gravelly loam', hydric: 'No' }]
	},
	{
		mukey: '9900004',
		musym: 'NOTCOM',
		muname: 'No Digital Data Available',
		dx: 3 * (W + GAP),
		codes: { c_restr: null, pat: null, c_drain: null, c_aws: null, c_farm: null, farm_cond: null, c_hsg: null, hsg_dual: null },
		ground: 'e2e-notcom',
		misc: 'nodata',
		farmlndcl: null,
		drclassdcd: null,
		hydgrpdcd: null,
		aws: null,
		restr: null,
		components: []
	}
];

/** A unit's centre, for the spec to point the map at. */
export const centre = (i: number): [number, number] => [ORIGIN[0] + UNITS[i].dx + W / 2, ORIGIN[1] + H / 2];
export const CENTRE: [number, number] = [ORIGIN[0] + (3 * (W + GAP) + W) / 2, ORIGIN[1] + H / 2];

export interface Seeded {
	madeSchema: boolean;
}

/** The migration, the survey area, the units and a layer version. */
export async function seedSoils(): Promise<Seeded> {
	const sql = db();
	try {
		const [has] = await sql`select to_regclass('soils.map_unit') is not null as soils, to_regclass('core.layer_version') is not null as versions`;
		if (!has.versions) throw new Error('core.layer_version is missing: run db.mjs migrate');
		let madeSchema = false;
		if (!has.soils) {
			await sql.unsafe(readFileSync(join(REPO, 'plugins', 'soils', 'migrations', '0001_soils.sql'), 'utf8'));
			madeSchema = true;
		}
		await clean(sql);
		const box = (dx: number) => {
			const x0 = ORIGIN[0] + dx;
			return `SRID=4326;MULTIPOLYGON(((${x0} ${ORIGIN[1]}, ${x0 + W} ${ORIGIN[1]}, ${x0 + W} ${ORIGIN[1] + H}, ${x0} ${ORIGIN[1] + H}, ${x0} ${ORIGIN[1]})))`;
		};
		const survey = `SRID=4326;MULTIPOLYGON(((${ORIGIN[0] - 0.01} ${ORIGIN[1] - 0.01}, ${ORIGIN[0] + 4 * (W + GAP) + 0.01} ${ORIGIN[1] - 0.01}, ${ORIGIN[0] + 4 * (W + GAP) + 0.01} ${ORIGIN[1] + H + 0.01}, ${ORIGIN[0] - 0.01} ${ORIGIN[1] + H + 0.01}, ${ORIGIN[0] - 0.01} ${ORIGIN[1] - 0.01})))`;
		await sql.begin(async (tx) => {
			await tx`insert into soils.build (build_id, kind, started_at, finished_at, license, republish, credit)
			         values (${BUILD}, 'load', now(), now(), 'synthetic test data', 'no', ${CREDIT})`;
			await tx`insert into soils.survey_area (areasymbol, areaname, saverest, saversion, scale, geom, geom_lo, build_id)
			         values (${AREA}, 'Synthetic Test Area, Idaho', '2025-09-23', 24, 24000, ST_GeomFromEWKT(${survey}), ST_GeomFromEWKT(${survey}), ${BUILD})`;
			for (const u of UNITS) {
				await tx`insert into soils.ground_type (id, series, texture, misc) values (${u.ground}, ${u.ground.split(':')[0]}, ${null}, ${u.misc}) on conflict do nothing`;
				const g = box(u.dx);
				const c = u.codes;
				await tx`
					insert into soils.map_unit (mukey, areasymbol, musym, muname, mukind, farmlndcl, slopegraddcp, aws0100wta, drclassdcd, hydgrpdcd, hydclprs, dom_cokey, ground_type,
					                            restr_kind, restr_top_cm, restr_hard, c_restr, pat, c_drain, c_aws, c_farm, farm_cond, c_hsg, hsg_dual, area_in_box_ha, n_polygons, geom_z8, geom_z10)
					values (${u.mukey}, ${AREA}, ${u.musym}, ${u.muname}, 'Consociation', ${u.farmlndcl}, ${u.misc ? null : 1}, ${u.aws}, ${u.drclassdcd}, ${u.hydgrpdcd}, ${u.misc ? null : 0},
					        ${u.components[0]?.cokey ?? null}, ${u.ground}, ${u.restr?.kind ?? null}, ${u.restr?.top ?? null}, ${u.restr?.hard ?? null},
					        ${c.c_restr}, ${c.pat}, ${c.c_drain}, ${c.c_aws}, ${c.c_farm}, ${c.farm_cond}, ${c.c_hsg}, ${c.hsg_dual},
					        ${(W * H * 111_000 * 81_000) / 10_000}, 1, ST_GeomFromEWKT(${g}), ST_GeomFromEWKT(${g}))`;
				await tx`
					insert into soils.polygon (id, areasymbol, mukey, geom, geom_lo, label_pt, area_m2, area_in_box_m2)
					values (${`${AREA}:${u.mukey}`}, ${AREA}, ${u.mukey}, ST_GeomFromEWKT(${g}), ST_GeomFromEWKT(${g}), ST_PointOnSurface(ST_GeomFromEWKT(${g})), ${W * H * 111_000 * 81_000}, ${W * H * 111_000 * 81_000})`;
				for (const k of u.components) {
					await tx`insert into soils.component (cokey, mukey, compname, compkind, comppct_r, majcomp, drainagecl, slope_r, hydricrating)
					         values (${k.cokey}, ${u.mukey}, ${k.name}, 'Series', ${k.pct}, ${k.major}, ${u.drclassdcd}, 1, ${k.hydric})`;
					await tx`insert into soils.horizon (chkey, cokey, hzname, top_cm, bottom_cm, texture, texcl) values (${`${k.cokey}1`}, ${k.cokey}, 'Ap', 0, 30, ${k.texture}, ${k.texture})`;
				}
			}
			await tx`insert into core.layer_version (layer, version, build, features, license, republish, credit, note)
			         values ('soils.units', ${VERSION}, 'e2e synthetic', ${UNITS.length}, 'synthetic test data', 'no', ${CREDIT}, 'e2e: synthetic soils, removed after the spec')`;
		});
		return { madeSchema };
	} finally {
		await sql.end();
	}
}

async function clean(sql: postgres.Sql) {
	await sql`delete from core.layer_version where layer = 'soils.units' and version like 'e2e-%'`;
	await sql`delete from soils.survey_area where areasymbol = ${AREA}`; // cascades to its units, components, horizons and polygons
	await sql`delete from soils.ground_type where id = any(${UNITS.map((u) => u.ground)})`;
	await sql`delete from soils.build where build_id = ${BUILD}`;
}

/** Take away what the spec made (the schema too, if the spec made it). */
export async function cleanSoils(seeded: Seeded | null): Promise<void> {
	const sql = db();
	try {
		const [has] = await sql`select to_regclass('soils.map_unit') is not null as soils`;
		if (has.soils) {
			if (seeded?.madeSchema) await sql`drop schema soils cascade`;
			else await clean(sql);
		}
		await sql`delete from core.layer_version where layer = 'soils.units' and version like 'e2e-%'`;
	} finally {
		await sql.end();
	}
}
