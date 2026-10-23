/**
 * Trails for the @trails spec (plan §4.2, package P6-app), set up by the spec and taken away after it:
 *
 * - **the plugin's tables**: trails 0001 applied when the database lacks it;
 * - **made-up ways, routes and agency lines**, near the foothills (`FOOTHILLS`) and on the synthetic landscape
 *   block (`BLOCK`, where basemap/landscape/fixtures/trails.paved_paths.geojson puts its treads), with
 *   invented names ("Fixture Ridge Trail") and ids in their own range, linked the way `trails-match` links
 *   real ones: a trail Ridge to Rivers calls open, one it calls muddy, one with caution, a closed one that no
 *   way lies along (it draws itself), one not evaluated, a Greenbelt closure along a part of a cycleway and a
 *   detour that draws itself, a private track (never drawn), and two informal paths, one of them close to
 *   the closed trail (hidden). Nothing here is a real record: no City row or OpenStreetMap way is copied;
 * - **layer versions** for the three tile sets, so the tiles are served (an unversioned layer answers empty).
 *
 * All of it is marked (ids from `B`, source ids `e2e-…`, builds `trails-e2e`) and removed after the spec.
 */
import { readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import postgres from 'postgres';
import { APP_DIR } from '../../scripts/harness-env.mjs';

const REPO = resolve(APP_DIR, '..');
/** Our made-up OpenStreetMap ids start here (real ones are below 1.6 billion). */
export const B = 9_700_000_000;
export const BUILD = 'trails-e2e';

export const FOOTHILLS: [number, number] = [-116.17, 43.662];
/** Where the landscape fixture's paved treads are. */
export const BLOCK: [number, number] = [-116.2, 43.617];

const db = () => postgres(process.env.DATABASE_URL!, { max: 1, onnotice: () => {} });

type Coord = [number, number];
const wkt = (c: Coord[]) => `LINESTRING(${c.map(([x, y]) => `${x} ${y}`).join(', ')})`;
const mwkt = (c: Coord[]) => `MULTILINESTRING((${c.map(([x, y]) => `${x} ${y}`).join(', ')}))`;
const g = (c: Coord[]) => `SRID=4326;${wkt(c)}`;
const mg = (c: Coord[]) => `SRID=4326;${mwkt(c)}`;

/** The made-up geography (lon, lat). */
export const GEO = {
	ridge: [[-116.18, 43.66], [-116.176, 43.6612], [-116.172, 43.6615], [-116.168, 43.6625], [-116.164, 43.663]] as Coord[],
	loop: [[-116.17, 43.664], [-116.168, 43.6655], [-116.165, 43.666], [-116.164, 43.6648], [-116.1665, 43.664], [-116.17, 43.664]] as Coord[],
	climb: [[-116.175, 43.659], [-116.1735, 43.6605], [-116.172, 43.662]] as Coord[],
	track: [[-116.185, 43.668], [-116.18, 43.669], [-116.175, 43.6685]] as Coord[],
	informal: [[-116.169, 43.66], [-116.1685, 43.6612]] as Coord[],
	private: [[-116.178, 43.67], [-116.174, 43.6705]] as Coord[],
	greenbelt: [[-116.195, 43.656], [-116.19, 43.6562], [-116.185, 43.6558], [-116.18, 43.6557]] as Coord[],
	informalNearGulch: [[-116.16, 43.6615], [-116.1597, 43.6622]] as Coord[],
	gulch: [[-116.1605, 43.66], [-116.16, 43.6625], [-116.1595, 43.664]] as Coord[],
	unevaluated: [[-116.156, 43.66], [-116.155, 43.662]] as Coord[],
	closureAlong: [[-116.19, 43.6562], [-116.185, 43.6558]] as Coord[],
	detour: [[-116.185, 43.6558], [-116.185, 43.6545], [-116.18, 43.6545]] as Coord[],
	// On the block of the landscape fixture (trails.paved_paths id 9101).
	riverside: [[-116.2035, 43.6168], [-116.2, 43.6172], [-116.1965, 43.6168]] as Coord[]
};

/** The ids the spec reads. */
export const IDS = {
	ridge: B + 1,
	loop: B + 2,
	climb: B + 3,
	track: B + 4,
	informal: B + 5,
	private: B + 6,
	greenbelt: B + 7,
	informalNearGulch: B + 8,
	/** The paved cycleway on the block; the landscape fixture's tread 9101 is the same way. */
	riverside: 9101
};

export interface Seeded {
	lines: Record<string, number>;
	versions: Record<string, string>;
}

const t0 = new Date('2026-10-11T12:00:00Z');

async function clean(sql: postgres.Sql) {
	await sql`delete from core.layer_version where build = ${BUILD}`;
	await sql`delete from trails.link where source_id like '%e2e-%'`;
	await sql`delete from trails.matched_line where source_id like '%e2e-%'`;
	await sql`delete from evt.event where source_id like '%e2e-%'`;
	await sql`delete from raw.record where source_id like '%e2e-%'`;
	await sql`delete from trails.route_line where osm_id >= ${B}`;
	await sql`delete from trails.osm_route where osm_id >= ${B}`;
	await sql`delete from trails.path_lo where fid >= ${B} or fid = ${IDS.riverside}`;
	await sql`delete from trails.osm_path where osm_id >= ${B} or osm_id = ${IDS.riverside}`;
}

/** Make the tables and the made-up trails (replacing any left by an earlier run). */
export async function seedTrails(): Promise<Seeded> {
	const sql = db();
	try {
		const [has] = await sql`select to_regclass('trails.path') is not null as ok`;
		if (!has.ok) await sql.unsafe(readFileSync(join(REPO, 'plugins', 'trails', 'migrations', '0001_paths.sql'), 'utf8'));
		for (const name of ['r2r_trails', 'boise_greenbelt_closures'])
			await sql`insert into ops.source (name, title, url, access) values (${name}, ${name}, 'https://example.test/', 'open') on conflict (name) do nothing`;
		await clean(sql);
		const lines: Record<string, number> = {};
		await sql.begin(async (tx) => {
			const way = async (id: number, kind: string, name: string | null, surface: string, surfaceFrom: string, widthEst: number, o: { no_access?: boolean; informal?: boolean; coords: Coord[]; width?: number } ) => {
				await tx`insert into trails.osm_path (osm_id, kind, name, surface, surface_from, width_m, width_est_m, no_access, informal, tags, geom)
				         values (${id}, ${kind}, ${name}, ${surface}, ${surfaceFrom}, ${o.width ?? null}, ${widthEst}, ${o.no_access ?? false}, ${o.informal ?? false},
				                 ${tx.json({ highway: kind, ...(o.informal ? { informal: 'yes' } : {}), ...(o.no_access ? { access: 'private' } : {}) })}, ST_GeomFromEWKT(${g(o.coords)}))`;
			};
			await way(IDS.ridge, 'path', 'Fixture Ridge Trail', 'unknown', 'none', 0.8, { coords: GEO.ridge });
			await way(IDS.loop, 'path', 'Fixture Muddy Loop', 'dirt', 'osm', 0.8, { coords: GEO.loop });
			await way(IDS.climb, 'path', 'Fixture Caution Climb', 'dirt', 'osm', 0.8, { coords: GEO.climb });
			await way(IDS.track, 'track', null, 'dirt', 'default', 3.0, { coords: GEO.track });
			await way(IDS.informal, 'path', null, 'unknown', 'none', 0.8, { informal: true, coords: GEO.informal });
			await way(IDS.private, 'track', null, 'dirt', 'default', 3.0, { no_access: true, coords: GEO.private });
			await way(IDS.greenbelt, 'cycleway', 'Fixture Greenbelt', 'paved', 'default', 3.0, { coords: GEO.greenbelt });
			await way(IDS.informalNearGulch, 'path', null, 'unknown', 'none', 0.8, { informal: true, coords: GEO.informalNearGulch });
			await way(IDS.riverside, 'cycleway', 'Fixture Riverside Path', 'paved', 'osm', 3.0, { coords: GEO.riverside, width: 3.0 });
			// The valley-zoom network: the named ways and the Greenbelt's.
			for (const [id, network, kind, name, c] of [
				[IDS.ridge, 'named', 'path', 'Fixture Ridge Trail', GEO.ridge],
				[IDS.loop, 'named', 'path', 'Fixture Muddy Loop', GEO.loop],
				[IDS.climb, 'named', 'path', 'Fixture Caution Climb', GEO.climb],
				[IDS.greenbelt, 'greenbelt', 'cycleway', 'Fixture Greenbelt', GEO.greenbelt],
				[IDS.riverside, 'cycleway', 'cycleway', 'Fixture Riverside Path', GEO.riverside]
			] as [number, string, string, string, Coord[]][])
				await tx`insert into trails.path_lo (fid, network, kind, name, surface, geom, built_at)
				         values (${id}, ${network}, ${kind}, ${name}, 'dirt', ST_GeomFromEWKT(${g(c)}), ${t0})`;
			// A hiking route over the Greenbelt cycleway and the ridge trail.
			await tx`insert into trails.osm_route (osm_id, route, name, network, members, way_ids, tags)
			         values (${B + 50}, 'hiking', 'Fixture Greenbelt Route', 'lwn', ${tx.json([])}::jsonb, ${tx.array([IDS.greenbelt, IDS.ridge], 20)}, ${tx.json({ route: 'hiking' })})`;
			await tx`insert into trails.route_line (osm_id, ways, ways_found, geom, length_m, built_at)
			         values (${B + 50}, 2, 2, ST_GeomFromEWKT(${mg(GEO.greenbelt)}), 3500, ${t0})`;

			// The agencies' lines: raw version, the state, the match.
			const line = async (o: { source: string; id: string; payload: Record<string, unknown>; coords: Coord[]; state?: { kind: string; sourceId: string; state?: string; severity?: string; label: string } }) => {
				await tx`insert into raw.record (source, source_id, version_hash, payload, geom, first_seen, last_seen)
				         values (${o.source}, ${o.id}, '\\x01', ${tx.json({ ...o.payload, _geom: `fp-${o.id}` })}, ST_GeomFromEWKT(${g(o.coords)}), ${t0}, ${t0})`;
				if (o.state)
					await tx`insert into evt.event (source, source_id, kind, geom, declared, observed, active, severity, description, attributes, content_hash, updated_at)
					         values (${o.source}, ${o.state.sourceId}, ${o.state.kind}, null, tstzrange(${t0}, null), tstzrange(${t0}, null), true,
					                 ${o.state.severity ?? null}, ${o.state.label}, ${tx.json(o.state.state ? { trail: o.id, state: o.state.state } : {})}, '\\x01', ${t0})`;
			};
			const r2r = (id: string, name: string, coords: Coord[], state: string, severity: string | null, label: string) =>
				line({
					source: 'r2r_trails',
					id,
					payload: { TrailName: name, SystemName: 'Ridge to Rivers' },
					coords,
					state: { kind: 'trail_condition', sourceId: `${id}/1/${state}`, state, severity: severity ?? undefined, label }
				});
			await r2r('e2e-ridge', 'Fixture Ridge Trail', GEO.ridge, 'dry', 'open', 'Dry / Tacky - Enjoy');
			await r2r('e2e-loop', 'Fixture Muddy Loop', GEO.loop, 'muddy', 'do_not_use', 'Muddy - Stay Off');
			await r2r('e2e-climb', 'Fixture Caution Climb', GEO.climb, 'muddy_further_out', 'caution', 'Dry at start, could be muddy further out');
			await r2r('e2e-gulch', 'Fixture Closed Gulch', GEO.gulch, 'closed', 'closed', 'CLOSED');
			await r2r('e2e-unevaluated', 'Fixture Unchecked Spur', GEO.unevaluated, 'not_evaluated', null, 'Not Evaluated');
			await line({
				source: 'boise_greenbelt_closures',
				id: 'construction:e2e-1',
				payload: { layer: 'construction', PROJECT: 'Fixture Greenbelt closure' },
				coords: GEO.closureAlong,
				state: { kind: 'closure', sourceId: 'construction:e2e-1', label: 'Active' }
			});
			await line({
				source: 'boise_greenbelt_closures',
				id: 'detour:e2e-1',
				payload: { layer: 'detour', PROJECT: 'Fixture Greenbelt detour' },
				coords: GEO.detour,
				state: { kind: 'detour', sourceId: 'detour:e2e-1', label: 'Active' }
			});

			// trails-match's result: R2R's three trails paint their ways; the closed gulch, the unchecked spur and the detour draw
			// themselves (no way lies along them); the closure is a stretch of the Greenbelt cycleway (drawn on its geometry).
			const matched = async (source: string, id: string, kind: string, name: string, c: Coord[], o: { gap?: Coord[]; along?: Coord[]; lineM: number; links: number }) => {
				const [r] = await tx`insert into trails.matched_line (source, source_id, kind, name, line_fp, line_m, covered_m, along, along_m, gap, gap_m, line_lo, links, matched_at, matched_by)
				         values (${source}, ${id}, ${kind}, ${name}, ${`fp-${id}`}, ${o.lineM}, ${o.gap ? null : o.lineM}, ST_GeomFromEWKT(${o.along ? mg(o.along) : null}),
				                 ${o.along ? o.lineM : 0}, ST_GeomFromEWKT(${o.gap ? mg(o.gap) : null}), ${o.gap ? o.lineM : 0},
				                 ST_Multi(ST_GeomFromEWKT(${g(c)})), ${o.links}, ${t0}, 'trails-match')
				         returning line_id`;
				lines[id] = Number(r.line_id);
			};
			await matched('r2r_trails', 'e2e-ridge', 'trail', 'Fixture Ridge Trail', GEO.ridge, { lineM: 1400, links: 1 });
			await matched('r2r_trails', 'e2e-loop', 'trail', 'Fixture Muddy Loop', GEO.loop, { lineM: 1000, links: 1 });
			await matched('r2r_trails', 'e2e-climb', 'trail', 'Fixture Caution Climb', GEO.climb, { lineM: 450, links: 1 });
			await matched('r2r_trails', 'e2e-gulch', 'trail', 'Fixture Closed Gulch', GEO.gulch, { gap: GEO.gulch, lineM: 450, links: 0 });
			await matched('r2r_trails', 'e2e-unevaluated', 'trail', 'Fixture Unchecked Spur', GEO.unevaluated, { gap: GEO.unevaluated, lineM: 230, links: 0 });
			await matched('boise_greenbelt_closures', 'construction:e2e-1', 'closure', 'Fixture Greenbelt closure', GEO.closureAlong, { along: GEO.closureAlong, lineM: 380, links: 1 });
			await matched('boise_greenbelt_closures', 'detour:e2e-1', 'detour', 'Fixture Greenbelt detour', GEO.detour, { gap: GEO.detour, lineM: 650, links: 0 });
			for (const [src, id, way, paints] of [
				['r2r_trails', 'e2e-ridge', IDS.ridge, true],
				['r2r_trails', 'e2e-loop', IDS.loop, true],
				['r2r_trails', 'e2e-climb', IDS.climb, true],
				['boise_greenbelt_closures', 'construction:e2e-1', IDS.greenbelt, false]
			] as [string, string, number, boolean][])
				await tx`insert into trails.link (source, source_id, osm_id, share, off_m, method, paints, matched_at)
				         values (${src}, ${id}, ${way}, 1, 0, ${paints ? 'pieces150_buffer15_bearing20' : 'way_in_pieces150_buffer15_bearing20'}, ${paints}, ${t0})`;

			// Every tile set has a build, with its licence and who must be credited.
			const stamp = Date.now().toString(36);
			for (const [layer, license, republish, credit] of [
				['paths', 'ODbL', 'yes', '© OpenStreetMap contributors'],
				['routes', 'ODbL', 'yes', '© OpenStreetMap contributors'],
				['agency', 'none stated (City of Boise disclaimer only) + ODbL', 'aggregates', 'City of Boise Parks & Recreation (Ridge to Rivers); © OpenStreetMap contributors']
			] as const)
				await tx`insert into core.layer_version (layer, version, build, features, license, republish, credit)
				         values (${`trails.${layer}`}, ${`e2e-${stamp}`}, ${BUILD}, 1, ${license}, ${republish}, ${credit})`;
		});
		const versions = Object.fromEntries((await sql`select layer, version from core.layer_version_current where layer like 'trails.%'`).map((r) => [String(r.layer), String(r.version)]));
		return { lines, versions };
	} finally {
		await sql.end();
	}
}

/** Take away what the spec made. */
export async function cleanTrails(): Promise<void> {
	const sql = db();
	try {
		const [has] = await sql`select to_regclass('trails.path') is not null as ok`;
		if (has.ok) await clean(sql);
	} finally {
		await sql.end();
	}
}
