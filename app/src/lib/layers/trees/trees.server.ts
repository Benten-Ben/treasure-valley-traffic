import type { Box, TreeArea, TreeCatalogue, TreeDetail, TreeLogEntry, TreeRow, TreesInView } from './trees.js';

/**
 * The trees API (docs/19 §19.4, §19.6), from the public plugin's tables
 * (`trees.tree`, `trees.tree_log`, `trees.build`: trees found in the lidar,
 * nothing from an inventory) and, on the owner's own site only, the private
 * catalogue (`city_trees.tree`, the City of Boise's inventory). The public
 * tables hold no catalogue id; the private plugin's `city_trees.tree_match`
 * links a tree's id to the catalogue entry it was matched to (and
 * `city_trees.tree_event` holds the log events that came from the match):
 *
 * - `GET /api/trees?bbox=w,s,e,n&limit=N`: the trees whose point is in the
 *   box, tallest first (limit 4,000 by default, 8,000 at most);
 * - `GET /api/trees/areas`: where trees are built;
 * - `GET /api/trees/<id>`: one tree, its catalogue entry when the private
 *   tables are here and the tree was matched (it then reads as catalogued, with
 *   the match's fit and events), and its log, newest first.
 *
 * Before the plugin's migration (an older database) nothing is built: empty
 * lists, never a 500. Without the private tables, `catalogue` is null.
 */

/** A postgres.js tagged template, or a test's stand-in. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Sql = (strings: TemplateStringsArray, ...values: any[]) => Promise<any[]>;

export const LIMIT_DEFAULT = 4000;
export const LIMIT_MAX = 8000;
/** The largest box asked for, degrees on a side (a whole North End view at z13 is about 0.1°). */
export const BOX_MAX_DEG = 1;

export class BadRequest extends Error {}

/** `w,s,e,n` in degrees: four finite numbers, west of east, south of north, at most BOX_MAX_DEG a side. */
export function parseBbox(raw: string | null): Box {
	if (!raw) throw new BadRequest('bbox=w,s,e,n is required');
	const parts = raw.split(',').map((x) => (x.trim() === '' ? NaN : Number(x)));
	if (parts.length !== 4 || !parts.every(Number.isFinite)) throw new BadRequest('bbox must be four numbers: w,s,e,n');
	const [w, s, e, n] = parts;
	if (w < -180 || e > 180 || s < -90 || n > 90 || w >= e || s >= n) throw new BadRequest('bbox must run west to east and south to north, in degrees');
	if (e - w > BOX_MAX_DEG || n - s > BOX_MAX_DEG) throw new BadRequest(`bbox is at most ${BOX_MAX_DEG}° on a side`);
	return [w, s, e, n];
}

/** `limit`: a whole number from 1 to LIMIT_MAX; LIMIT_DEFAULT when absent. */
export function parseLimit(raw: string | null): number {
	if (raw === null || raw === '') return LIMIT_DEFAULT;
	const n = Number(raw);
	if (!Number.isInteger(n) || n < 1) throw new BadRequest('limit must be a whole number from 1');
	return Math.min(n, LIMIT_MAX);
}

export interface Schema {
	/** The plugin's tables (migration 0001_trees). */
	trees: boolean;
	/** The private catalogue and its links to our trees (the city_trees plugin, the owner's site only). */
	catalogue: boolean;
}

/** Which tables are here. */
export async function schema(sql: Sql): Promise<Schema> {
	const [r] = await sql`
		select to_regclass('trees.tree') is not null and to_regclass('trees.build') is not null
		       and to_regclass('trees.tree_log') is not null as trees,
		       (to_regclass('city_trees.tree') is not null and to_regclass('city_trees.tree_match') is not null
		        and to_regclass('city_trees.tree_event') is not null) as catalogue`;
	return { trees: Boolean(r?.trees), catalogue: Boolean(r?.catalogue) };
}

const num = (v: unknown): number | null => (v === null || v === undefined ? null : Number(v));
const round = (v: number, d: number) => Math.round(v * 10 ** d) / 10 ** d;

/**
 * The trees in a box, tallest first; `truncated` when more were there than `limit`; `catalogue` when the private
 * catalogue's tables answer (the legend lists Catalogued and the credit names the City only then).
 */
export async function treesInBox(sql: Sql, box: Box, limit: number): Promise<TreesInView> {
	const has = await schema(sql);
	if (!has.trees) return { trees: [], truncated: false, catalogue: false };
	const [w, s, e, n] = box;
	const rows = await sql`
		select tree_id as id, kind, type, ST_X(geom) as lng, ST_Y(geom) as lat,
		       height_m as h, crown_radius_m as r, crown_a as a, crown_n as n
		from trees.tree
		where geom && ST_MakeEnvelope(${w}, ${s}, ${e}, ${n}, 4326)
		order by height_m desc, tree_id
		limit ${limit + 1}`;
	const truncated = rows.length > limit;
	const trees: TreeRow[] = rows.slice(0, limit).map((r) => ({
		id: String(r.id),
		kind: r.kind,
		type: r.type,
		lng: round(Number(r.lng), 7),
		lat: round(Number(r.lat), 7),
		h: round(Number(r.h), 2),
		r: round(Number(r.r), 2),
		a: r.a === null ? null : round(Number(r.a), 3),
		n: r.n === null ? null : round(Number(r.n), 3)
	}));
	return { trees, truncated, catalogue: has.catalogue };
}

/** Where trees are built: each area's box, count and when its current build was made. */
export async function treeAreas(sql: Sql): Promise<{ areas: TreeArea[] }> {
	if (!(await schema(sql)).trees) return { areas: [] };
	const rows = await sql`
		with a as (
			select area, count(*)::int as trees, ST_Extent(geom) as box, array_agg(distinct build_id) as builds
			from trees.tree group by area)
		select a.area, a.trees, ST_XMin(a.box) as w, ST_YMin(a.box) as s, ST_XMax(a.box) as e, ST_YMax(a.box) as n,
		       (select coalesce(b.finished_at, b.started_at) from trees.build b
		        where b.build_id = any(a.builds) order by b.loaded_at desc limit 1) as built_at
		from a order by a.area`;
	return {
		areas: rows.map((r) => ({
			area: String(r.area),
			bounds: [round(Number(r.w), 7), round(Number(r.s), 7), round(Number(r.e), 7), round(Number(r.n), 7)] as Box,
			trees: Number(r.trees),
			built_at: r.built_at ? new Date(r.built_at).toISOString() : null
		}))
	};
}

/**
 * One tree with its log (newest first) and, when the private tables are here and the tree was matched to a catalogue
 * entry, that entry (the tree then reads as catalogued, with the match's fit and its private log events); null when
 * there's no such tree. The public tables hold no catalogue id, so the lookup goes through the private plugin's
 * `city_trees.tree_match`, keyed by our tree id and the build that made the tree: ids are rounded positions, so after a
 * rebuild an old match must not attach to whatever crown now has its id.
 */
export async function treeDetail(sql: Sql, id: string): Promise<TreeDetail | null> {
	const has = await schema(sql);
	if (!has.trees) return null;
	const [t] = await sql`
		select tree_id, area, kind, type, height_m, crown_radius_m, ground_m, lidar, fit, build_id
		from trees.tree where tree_id = ${id}`;
	if (!t) return null;
	let log = await sql`
		select at, event, detail from trees.tree_log where tree_id = ${id} order by at desc, event`;
	let catalogue: TreeCatalogue | null = null;
	let kind = t.kind;
	let fit = (t.fit ?? {}) as Record<string, unknown>;
	if (has.catalogue) {
		const [c] = await sql`
			select m.catalogue, m.fit as match_fit, c.catalogue_id, c.common_name, c.genus, c.species, c.dbh_in,
			       c.installed::text as installed, c.last_verified::text as last_verified, c.condition, c.site_type
			from city_trees.tree_match m
			join city_trees.tree c on c.catalogue_id = m.catalogue_id
			where m.tree_id = ${id} and m.catalogue = 'boise' and m.build_id = ${t.build_id}`;
		if (c) {
			catalogue = {
				catalogue: String(c.catalogue),
				catalogue_id: String(c.catalogue_id),
				common_name: c.common_name ?? null,
				genus: c.genus ?? null,
				species: c.species ?? null,
				dbh_in: num(c.dbh_in),
				installed: c.installed ?? null,
				last_verified: c.last_verified ?? null,
				condition: c.condition ?? null,
				site_type: c.site_type ?? null
			};
			kind = 'catalogued';
			fit = { ...fit, ...((c.match_fit ?? {}) as Record<string, unknown>) };
			const own = await sql`
				select at, event, detail from city_trees.tree_event where tree_id = ${id} and build_id = ${t.build_id}`;
			log = [...log, ...own].sort((a, b) => +new Date(b.at) - +new Date(a.at) || String(a.event).localeCompare(String(b.event)));
		}
	}
	return {
		id: String(t.tree_id),
		area: String(t.area),
		kind,
		type: t.type,
		height_m: Number(t.height_m),
		crown_radius_m: Number(t.crown_radius_m),
		ground_m: num(t.ground_m),
		lidar: t.lidar ?? null,
		fit,
		build_id: String(t.build_id),
		catalogue,
		log: log.map(
			(e): TreeLogEntry => ({
				at: e.at instanceof Date ? e.at.toISOString() : String(e.at),
				event: String(e.event),
				detail: (e.detail ?? {}) as Record<string, unknown>
			})
		)
	};
}
