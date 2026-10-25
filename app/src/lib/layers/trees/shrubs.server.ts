import type { Box } from './trees.js';
import { SHRUB_LIMIT, SHRUB_RADIUS_M, type ShrubArea, type ShrubRow, type ShrubsInView } from './shrubs.js';
import { BadRequest, type Sql } from './trees.server.js';

/**
 * The shrubs API (docs/19 §19.8, plan P11-app), from the public plugin's tables (`trees.shrub` and `trees.shrub_area`:
 * shrubs found in the lidar, nothing from an inventory):
 *
 * - `GET /api/trees/shrubs?bbox=w,s,e,n&center=lng,lat&limit=N`: the shrubs in the box and within SHRUB_RADIUS_M of
 *   the centre, nearest the centre first (limit 1,500, the default and the most);
 * - `GET /api/trees/shrubs/areas`: where shrubs are built.
 *
 * Only an area's current build answers, and only when its republish is "yes". Before the plugin's migration nothing is
 * built: empty lists, never a 500.
 */

/** `lng,lat`: two finite numbers in range. */
export function parseCentre(raw: string | null): [number, number] {
	if (!raw) throw new BadRequest('center=lng,lat is required');
	const parts = raw.split(',').map((x) => (x.trim() === '' ? NaN : Number(x)));
	if (parts.length !== 2 || !parts.every(Number.isFinite)) throw new BadRequest('center must be two numbers: lng,lat');
	const [x, y] = parts;
	if (x < -180 || x > 180 || y < -90 || y > 90) throw new BadRequest('center must be a longitude and a latitude, in degrees');
	return [x, y];
}

/** `limit`: a whole number from 1 to SHRUB_LIMIT; SHRUB_LIMIT when absent. */
export function parseShrubLimit(raw: string | null): number {
	if (raw === null || raw === '') return SHRUB_LIMIT;
	const n = Number(raw);
	if (!Number.isInteger(n) || n < 1) throw new BadRequest('limit must be a whole number from 1');
	return Math.min(n, SHRUB_LIMIT);
}

/** Whether the shrub tables are here (an older database has only the trees). */
export async function shrubSchema(sql: Sql): Promise<boolean> {
	const [r] = await sql`select to_regclass('trees.shrub') is not null and to_regclass('trees.shrub_area') is not null as shrubs`;
	return Boolean(r?.shrubs);
}

const round = (v: number, d: number) => Math.round(v * 10 ** d) / 10 ** d;

/**
 * The shrubs in a box within SHRUB_RADIUS_M of `centre`, nearest first; `truncated` when more were there than
 * `limit`. An area's current build only (`trees.shrub_area`), and only where its republish is "yes".
 */
export async function shrubsInBox(sql: Sql, box: Box, centre: [number, number], limit: number): Promise<ShrubsInView> {
	if (!(await shrubSchema(sql))) return { shrubs: [], truncated: false };
	const [w, s, e, n] = box;
	const [cx, cy] = centre;
	const rows = await sql`
		select s.shrub_id as id, s.look, ST_X(s.geom) as lng, ST_Y(s.geom) as lat, s.height_m as h, s.width_m as w
		from trees.shrub s
		join trees.shrub_area a on a.area = s.area and a.build_id = s.build_id
		where s.geom && ST_MakeEnvelope(${w}, ${s}, ${e}, ${n}, 4326)
		  and a.republish = 'yes'
		  and ST_DWithin(s.geom::geography, ST_SetSRID(ST_MakePoint(${cx}, ${cy}), 4326)::geography, ${SHRUB_RADIUS_M})
		order by ST_Distance(s.geom::geography, ST_SetSRID(ST_MakePoint(${cx}, ${cy}), 4326)::geography), s.shrub_id
		limit ${limit + 1}`;
	const truncated = rows.length > limit;
	const shrubs: ShrubRow[] = rows.slice(0, limit).map((r) => ({
		id: String(r.id),
		look: r.look === 'sage' ? 'sage' : 'bush',
		lng: round(Number(r.lng), 7),
		lat: round(Number(r.lat), 7),
		h: round(Number(r.h), 2),
		w: round(Number(r.w), 2)
	}));
	return { shrubs, truncated };
}

/** Where shrubs are built: each area's outline, count and when its current build was made (republish "yes" only). */
export async function shrubAreas(sql: Sql): Promise<{ areas: ShrubArea[] }> {
	if (!(await shrubSchema(sql))) return { areas: [] };
	const rows = await sql`
		select area, shrubs, built_at, ST_XMin(geom) as w, ST_YMin(geom) as s, ST_XMax(geom) as e, ST_YMax(geom) as n
		from trees.shrub_area where republish = 'yes' order by area`;
	return {
		areas: rows.map((r) => ({
			area: String(r.area),
			bounds: [round(Number(r.w), 7), round(Number(r.s), 7), round(Number(r.e), 7), round(Number(r.n), 7)] as Box,
			shrubs: Number(r.shrubs ?? 0),
			built_at: r.built_at ? new Date(r.built_at).toISOString() : null
		}))
	};
}
