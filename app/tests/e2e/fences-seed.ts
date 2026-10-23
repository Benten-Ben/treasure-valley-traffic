/**
 * Fences for the @fences spec (plan P10), set up by the spec and taken away after it:
 *
 * - **the table:** the fences plugin's migration, when the database doesn't have `fences.fence` (and dropped after
 *   only if we made it);
 * - **a few SYNTHETIC fences** near the North End: made-up lines (ids `osm:w99000NN`, tagged `synthetic-test`), a
 *   see-through fence, a solid wall with a tagged height, a retaining wall and a guard rail. No real record is used;
 * - **a version:** a `fences.lines` row in `core.layer_version`, so /api/meta reports the version the layer asks with.
 */
import { readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import postgres from 'postgres';
import { APP_DIR } from '../../scripts/harness-env.mjs';

const REPO = resolve(APP_DIR, '..');
const db = () => postgres(process.env.DATABASE_URL!, { max: 1, onnotice: () => {} });

export const NORTH_END: [number, number] = [-116.20892, 43.62755];
const BUILD = 'e2e-fences';
export const VERSION = 'e2e-fences-v1';

const M_LNG = 111_320 * Math.cos((NORTH_END[1] * Math.PI) / 180);
const M_LAT = 110_574;
/** A point `east` and `north` metres from the North End centre. */
const at = (east: number, north: number): [number, number] => [NORTH_END[0] + east / M_LNG, NORTH_END[1] + north / M_LAT];

export interface SyntheticFence {
	id: string;
	kind: string;
	type: 'fence' | 'wall' | 'retaining_wall' | 'guard_rail';
	look: 'solid' | 'open';
	height: number;
	source: 'tagged' | 'default';
	material: string | null;
	fenceType: string | null;
	/** East and north metres from the centre. */
	points: [number, number][];
}

export const FENCES: SyntheticFence[] = [
	{ id: 'osm:w9900001', kind: 'fence', type: 'fence', look: 'open', height: 1.8, source: 'default', material: 'wood', fenceType: null, points: [[-30, 12], [0, 12], [30, 12]] },
	{ id: 'osm:w9900002', kind: 'wall', type: 'wall', look: 'solid', height: 2.4, source: 'tagged', material: 'brick', fenceType: null, points: [[40, -30], [40, 0], [40, 30]] },
	{ id: 'osm:w9900003', kind: 'retaining_wall', type: 'retaining_wall', look: 'solid', height: 1.2, source: 'default', material: 'concrete', fenceType: null, points: [[-40, -30], [-40, 0], [-40, 30]] },
	{ id: 'osm:w9900004', kind: 'guard_rail', type: 'guard_rail', look: 'open', height: 0.8, source: 'default', material: 'metal', fenceType: null, points: [[-30, -20], [0, -20], [30, -20]] }
];

export interface Seeded {
	/** Whether we made the plugin's schema (and so drop it after). */
	madeSchema: boolean;
	fences: number;
}

export async function seedFences(): Promise<Seeded> {
	const sql = db();
	try {
		const [has] = await sql`select to_regclass('fences.fence') is not null as fences, to_regclass('core.layer_version') is not null as versions`;
		if (!has.versions) throw new Error('core.layer_version is missing: run db/migrate.py on this database first');
		const madeSchema = !has.fences;
		if (madeSchema) await sql.unsafe(readFileSync(join(REPO, 'plugins', 'fences', 'migrations', '0001_fences.sql'), 'utf8'));
		await clearRows(sql);
		for (const f of FENCES) {
			const wkt = `LINESTRING(${f.points.map(([e, n]) => at(e, n).join(' ')).join(', ')})`;
			await sql`
				insert into fences.fence (fence_id, kind, type, look, height_m, height_source, material, fence_type, name, tags, osm_id, geom)
				values (${f.id}, ${f.kind}, ${f.type}, ${f.look}, ${f.height}, ${f.source}, ${f.material}, ${f.fenceType}, null,
				        ${sql.json({ barrier: f.kind, 'synthetic-test': 'yes' })}, ${Number(f.id.slice(5))}, ST_GeomFromText(${wkt}, 4326))`;
		}
		await sql`
			insert into core.layer_version (layer, version, build, features, license, republish, credit, note)
			values ('fences.lines', ${VERSION}, ${BUILD}, ${FENCES.length}, 'ODbL', 'yes', '© OpenStreetMap contributors', 'synthetic fences for the @fences spec')`;
		return { madeSchema, fences: FENCES.length };
	} finally {
		await sql.end();
	}
}

async function clearRows(sql: postgres.Sql) {
	await sql`delete from core.layer_version where layer = 'fences.lines' and build = ${BUILD}`;
	await sql`delete from fences.fence where tags ? 'synthetic-test'`;
}

/** Take away what the spec made. */
export async function cleanFences(seeded: Seeded | null): Promise<void> {
	const sql = db();
	try {
		await sql`delete from core.layer_version where layer = 'fences.lines' and build = ${BUILD}`;
		if (seeded?.madeSchema) await sql`drop schema if exists fences cascade`;
		else await sql`delete from fences.fence where tags ? 'synthetic-test'`;
	} finally {
		await sql.end();
	}
}
