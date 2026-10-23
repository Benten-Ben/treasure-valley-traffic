/**
 * Synthetic roads rows for the @lanes spec (landscape sprint plan v3 §4.2 P9), set up by the spec and taken away after
 * it. Everything is made up and matches the fixture tiles (basemap/landscape/fixtures/roads.*.geojson, written by
 * `app/scripts/tiles-fixture.mjs`), so a click on a fixture surface finds its row:
 *
 * - **a roads build named `fixture`**: the fixture manifest's landscape layers say `build: "fixture"`, and the card
 *   API accepts a map whose build is the current build's own id, so the card is asked and answered as in production;
 * - **two pieces** (the fixture's two streets): `Fixture Avenue` (id 1001: 3 lanes from OpenStreetMap, measured) and
 *   `Fixture Street` (id 1002, flagged: OpenStreetMap has 5 lanes where ACHD's rule has 2), with the `lanes_conflict`
 *   review row that carries both counts;
 * - **their surfaces, an edge and markings** (ids as in the fixture tiles), a junction and an island with no piece.
 *
 * Nothing here is a real record or a real agency's value; the names say "Fixture". The seed's ids are bare numbers, so
 * it **refuses to run** (the spec fails with the reason) on a database that holds a real roads build or real pieces:
 * run it on a throwaway clone or a database with no roads build (the browser specs' own). It deletes only its own ids.
 */
import { readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import postgres from 'postgres';
import { APP_DIR } from '../../scripts/harness-env.mjs';

const REPO = resolve(APP_DIR, '..');
export const BUILD = 'fixture';
export const PIECES = { avenue: 1001, street: 1002 } as const;
export const NAMES = { avenue: 'Fixture Avenue', street: 'Fixture Street' } as const;
const NOTE = 'lanes e2e seed (synthetic)';

const db = () => postgres(process.env.DATABASE_URL!, { max: 1, onnotice: () => {} });

export interface Seeded {
	/** Whether we applied the plugin's migrations (and so drop the schema after). */
	madeSchema: boolean;
	/** The build that was current before ours, to make current again. */
	previousCurrent: string | null;
}

const line = (coords: [number, number][]) => `SRID=32611;LINESTRING(${coords.map((c) => c.join(' ')).join(', ')})`;
const square = (x: number, y: number) => `SRID=32611;MULTIPOLYGON(((${x} ${y}, ${x + 8} ${y}, ${x + 8} ${y + 8}, ${x} ${y + 8}, ${x} ${y})))`;

export async function seedLanes(): Promise<Seeded> {
	const sql = db();
	let madeSchema = false;
	let previousCurrent: string | null = null;
	try {
		const [has] = await sql`select to_regclass('roads.build') is not null as ok`;
		if (has.ok) await refuseRealRoads(sql);
		if (!has.ok) {
			// One transaction, so a failure leaves no half-made schema behind.
			await sql.begin(async (tx) => {
				for (const f of ['0001_osm_street.sql', '0003_real_width.sql']) await tx.unsafe(readFileSync(join(REPO, 'plugins', 'roads', 'migrations', f), 'utf8'));
			});
			madeSchema = true;
		}
		await clean(sql);
		const [prev] = await sql`select id from roads.build where current`;
		previousCurrent = prev?.id ?? null;
		await sql.begin(async (tx) => {
			await tx`update roads.build set current = false where current`;
			await tx`insert into roads.build (id, started_at, finished_at, current, extract_md5, inputs, params, counts, seconds, license, republish, credit)
			         values (${BUILD}, now() - interval '1 hour', now() - interval '59 minutes', true, 'fixture', ${tx.json([])}, ${tx.json({})}, ${tx.json({ note: NOTE })}, 1, 'ODbL', 'internal', 'fixture')`;
			const piece = (id: number, osm: number, highway: string, name: string, coords: [number, number][]) =>
				tx`insert into roads.piece (id, osm_id, seq, source, highway, name, oneway, from_node, to_node, county, road_segment_id, length_m, geom)
				   values (${id}, ${osm}, 1, 'osm_valley', ${highway}, ${name}, 0, ${id * 10}, ${id * 10 + 1}, 'Ada', 77, 600, ST_GeomFromEWKT(${line(coords)}))`;
			await piece(PIECES.avenue, 910001, 'secondary', NAMES.avenue, [[560000, 4829000], [560800, 4829000]]);
			await piece(PIECES.street, 910002, 'residential', NAMES.street, [[560400, 4828400], [560400, 4829600]]);
			const xsection = (id: number, o: { fwd: number; bwd: number; centre: boolean; source: string; tier: string; wsource: string; total: number; flags: string[]; markings: boolean }) =>
				tx`insert into roads.xsection (piece_id, lanes_fwd, lanes_bwd, centre_turn, lanes_source, lanes_conf, lane_w_m, edge_l, edge_r, width_left_m, width_right_m, total_w_m,
				                               width_tier, width_source, material, material_source, markings, sources, republish, flags)
				   values (${id}, ${o.fwd}, ${o.bwd}, ${o.centre}, ${o.source}, 1, 3.4, 'curb', 'curb', ${o.total / 2}, ${o.total / 2}, ${o.total},
				           ${o.tier}, ${o.wsource}, 'asphalt', 'surface', ${o.markings}, ${tx.json({ lanes: o.source })}, 'internal', ${tx.array(o.flags)})`;
			await xsection(PIECES.avenue, { fwd: 1, bwd: 1, centre: true, source: 'osm', tier: 'inventoried', wsource: 'achd_bike_network', total: 11, flags: [], markings: true });
			await xsection(PIECES.street, { fwd: 3, bwd: 2, centre: false, source: 'osm', tier: 'estimated', wsource: 'class_default', total: 7.3, flags: ['conflict', 'split_estimated'], markings: false });
			await tx`insert into roads.junction (id, kind, nodes, pieces, radius_m, intersection_id, geom)
			         values (1, 'signal', 1, ${tx.array([PIECES.avenue, PIECES.street], 1007)}, 6, null, ST_GeomFromEWKT('SRID=32611;POINT(560400 4829000)'))`;
			const surface = (id: number, kind: string, p: number | null, j: number | null, x: number, y: number) =>
				tx`insert into roads.surface (id, kind, piece_id, junction_id, material, tier, geom) values (${id}, ${kind}, ${p}, ${j}, 'asphalt', 'estimated', ST_GeomFromEWKT(${square(x, y)}))`;
			await surface(2001, 'carriageway', PIECES.avenue, null, 560000, 4829000);
			await surface(2002, 'junction', null, 1, 560400, 4829000);
			await surface(2003, 'carriageway', PIECES.street, null, 560400, 4828400);
			await surface(2004, 'island', null, null, 560420, 4829020);
			await tx`insert into roads.edge (id, kind, tier, piece_id, geom) values (3001, 'curb', 'inventoried', ${PIECES.avenue}, ST_GeomFromEWKT('SRID=32611;MULTILINESTRING((560000 4829005, 560300 4829005))'))`;
			await tx`insert into roads.marking (id, kind, dash, piece_id, geom) values
			         (4002, 'lane', 'dashed', ${PIECES.avenue}, ST_GeomFromEWKT('SRID=32611;MULTILINESTRING((560000 4829001, 560300 4829001))')),
			         (4003, 'centre_double', 'double', ${PIECES.street}, ST_GeomFromEWKT('SRID=32611;MULTILINESTRING((560400 4828400, 560400 4828900))'))`;
			await tx`insert into roads.review (id, kind, piece_id, osm_id, road_segment_id, detail)
			         values (1, 'lanes_conflict', ${PIECES.street}, 910002, 77, ${tx.json({ osm: [3, 2], achd_msm: [1, 1], road_segment_id: 77 })})`;
		});
		return { madeSchema, previousCurrent };
	} catch (e) {
		// A failure partway leaves no rows or schema of ours for a later run to keep for good (but a refusal touched nothing).
		if (!(e instanceof RealRoadsError)) await cleanLanes({ madeSchema, previousCurrent }).catch(() => {});
		throw e;
	} finally {
		await sql.end();
	}
}

class RealRoadsError extends Error {}

/** The seed's ids are bare numbers, so it never runs where a real roads build (or a real piece) could share them. */
async function refuseRealRoads(sql: postgres.Sql) {
	const builds = await sql`select id from roads.build where id <> ${BUILD}`;
	const [pieces] = await sql`select count(*)::int as n from roads.piece where osm_id <> all(${[910001, 910002]})`;
	if (builds.length || pieces.n) {
		throw new RealRoadsError(
			`lanes e2e seed: this database holds a real roads build (${builds.length} build(s), ${pieces.n} piece(s) that are not the seed's). ` +
				'Run the @lanes spec on a throwaway clone or a database with no roads build; nothing was changed.'
		);
	}
}

async function clean(sql: postgres.Sql) {
	const [has] = await sql`select to_regclass('roads.build') is not null as ok`;
	if (!has.ok) return;
	const ids = { piece: [PIECES.avenue, PIECES.street], surface: [2001, 2002, 2003, 2004], edge: [3001], marking: [4002, 4003] };
	await sql`delete from roads.review where id = 1 and piece_id = ${PIECES.street}`;
	await sql`delete from roads.marking where id = any(${ids.marking})`;
	await sql`delete from roads.edge where id = any(${ids.edge})`;
	await sql`delete from roads.surface where id = any(${ids.surface})`;
	await sql`delete from roads.junction where id = 1 and ${PIECES.avenue}::int = any(pieces)`;
	await sql`delete from roads.xsection where piece_id = any(${ids.piece})`;
	await sql`delete from roads.piece where id = any(${ids.piece}) and osm_id in (910001, 910002)`;
	await sql`delete from roads.build where id = ${BUILD}`;
}

/** Take away what the spec made. */
export async function cleanLanes(seeded: Seeded | null) {
	if (!seeded) return;
	const sql = db();
	try {
		if (seeded.madeSchema) {
			await sql.unsafe('drop schema roads cascade');
			return;
		}
		await clean(sql);
		if (seeded.previousCurrent) await sql`update roads.build set current = true where id = ${seeded.previousCurrent}`;
	} finally {
		await sql.end();
	}
}
