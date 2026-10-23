import type postgres from 'postgres';
import type { TileLayerDef } from '../mvt.js';
import type { TileId } from '../road-tiles.js';

/**
 * The Trails layer's vector tiles (landscape sprint, package P6-app; plan C4 and C18):
 * `GET /api/trails/tiles/<layer>/{z}/{x}/{y}?v=`, three tile sets, as plugins/trails/README.md
 * ("What the map reads") lists them. Each is its own layer, with its own version in
 * `core.layer_version`, because they change on different clocks: a poll that moves a City line gives
 * only `agency` a new version, the build gives all three one.
 *
 * | Layer | MVT layer | z10 to 12 | z13 to 16 | Licence, republish |
 * |---|---|---|---|---|
 * | `paths` | `paths` | `trails.path_lo` (the named network) | `trails.path` | ODbL, yes |
 * | `routes` | `routes` | `trails.route_line` with its route's name | the same | ODbL, yes |
 * | `agency` | `agency`, `marks` | `trails.agency_lo` (whole lines) | `trails.agency_drawn`; `marks`: `agency_lo` at every zoom | the City's, aggregates |
 *
 * Each is a `cut` of its own rather than `parts`, because a `parts` source can't say `where`:
 *
 * - **`paths` leaves out what is never drawn.** Ways closed to the public (`access=private|no`), canal
 *   banks and informal ways before z16 are cut out in SQL (`drawn`, `minzoom`; plan C18), not left to a style
 *   filter, so a private track's line never reaches a viewer and the busiest tile carries only what draws.
 * - **`routes` takes its route's name, kind and network** from `trails.osm_route`, which `route_line` doesn't
 *   carry.
 * - **`agency` is the City's** (Ridge to Rivers and the Greenbelt), republish aggregates: its tiles are for
 *   the owner's tailnet map, and a public build leaves them out. They carry the line's id, kind, name and
 *   the part of it drawn, never its state: the state comes from `/api/trails/status` by feature-state, and
 *   the tile login is refused `agency_state` (deploy/tvt_tiles.sql). The City's source ids and attributes
 *   are not in them.
 *
 * Every cut reads only `trails` and core, as the tile login holds it to. A cut before the plugin's
 * migration fails with a missing table and is answered as an empty tile (mvt.ts).
 */

export const PLUGIN = 'trails';
export const CREDIT_OSM = '© OpenStreetMap contributors';
export const CREDIT_CITY = 'City of Boise Parks & Recreation (Ridge to Rivers); City of Boise Parks and Recreation';
/** The first zoom the full-detail ways and the agencies' drawn parts come in at; below it the valley-zoom network. */
export const DETAIL_ZOOM = 13;
export const MIN_ZOOM = 10;
export const MAX_ZOOM = 16;

/**
 * MVT extent and buffer: mvt.ts's EXTENT and BUFFER (tiles.test.ts checks they agree). This file imports nothing but types
 * from mvt.ts: mvt.ts loads it by glob while it evaluates, so whichever of the two is imported first, a value import here
 * would meet a module not yet evaluated (an empty registry in the one order, a `const` not yet set in the other).
 */
const EXTENT = 4096;
const BUFFER = 64;

/** The tile and its buffered envelope in lon/lat, as the parts' SQL writes them (mvt.ts `partSql`). */
const ENV = 'ST_TileEnvelope($1::int, $2::int, $3::int)';
const WIDE = `ST_Transform(ST_TileEnvelope($1::int, $2::int, $3::int, margin => ${BUFFER / EXTENT}), 4326)`;

/**
 * One MVT layer's bytes from a select of its properties and a `geom` (4326): `from` is the table (or join)
 * with the geometry's alias `s`, `where` its filter; the `id` column is the feature id.
 */
function layerSql(name: string, id: string, cols: string, from: string, where: string): string {
	return (
		`(select coalesce(ST_AsMVT(t, '${name}', ${EXTENT}, 'mvt_geom', '${id}'), ''::bytea) from (` +
		`select ${cols}, ST_AsMVTGeom(ST_Transform(s.geom, 3857), ${ENV}, ${EXTENT}, ${BUFFER}, true) as mvt_geom ` +
		`from ${from} where ${where} and s.geom && ${WIDE}) t where t.mvt_geom is not null)`
	);
}

/** `paths`: the drawn ways from z13 (`trails.path`), the valley-zoom network below (`trails.path_lo`). */
export const PATHS_SQL = {
	lo: layerSql('paths', 'osm_id', 's.fid as osm_id, s.network, s.kind, s.name', 'trails.path_lo s', 'true'),
	// drawn: not private or no-access, not a canal bank (plan C18); minzoom: informal ways come in at z16, tracks at z13.
	hi: layerSql(
		'paths',
		'osm_id',
		's.osm_id, s.kind, s.name, s.surface, round(s.width_m::numeric, 1)::float8 as width_m, s.informal, s.greenbelt, s.bridge',
		'trails.path s',
		's.drawn and s.minzoom <= $1::int'
	)
} as const;

/** `routes`: each route relation's line, with its route's kind, name, ref and network. */
export const ROUTES_SQL = layerSql(
	'routes',
	'osm_id',
	's.osm_id, r.route, r.name, r.ref, r.network',
	'trails.route_line s join trails.osm_route r on r.osm_id = s.osm_id and r.active',
	's.geom is not null'
);

/**
 * `agency`: the City's lines drawn by themselves (from z13) or whole (below), as the MVT layer `agency`, and at
 * every zoom their whole simplified lines as `marks`, which carry no property but the id: the status icons and
 * closure X marks sit on those, so a state's icon doesn't depend on which ways the line paints. The feature id is
 * the line's `line_id` (the same in both layers: one feature-state key; /api/trails/status gives it). Not the views'
 * `fid`, which is `-line_id`: PostGIS leaves a negative id out of a tile, and a feature without an id takes no
 * feature-state.
 */
export const AGENCY_SQL = {
	lo: layerSql('agency', 'fid', 's.line_id as fid, s.kind, s.name', 'trails.agency_lo s', 'true'),
	hi: layerSql('agency', 'fid', 's.line_id as fid, s.kind, s.name, s.part', 'trails.agency_drawn s', 'true'),
	marks: layerSql('marks', 'fid', 's.line_id as fid', 'trails.agency_lo s', 'true')
} as const;

/** The SQL that cuts a tile of `paths` at zoom z ($1 to $3 are z, x, y). */
export const pathsSql = (z: number): string => `select ${z >= DETAIL_ZOOM ? PATHS_SQL.hi : PATHS_SQL.lo} as mvt`;
export const routesSql = (_z: number): string => `select ${ROUTES_SQL} as mvt`;
export const agencySql = (z: number): string => `select ${z >= DETAIL_ZOOM ? AGENCY_SQL.hi : AGENCY_SQL.lo} || ${AGENCY_SQL.marks} as mvt`;

/** mvt.ts's `cancelOnAbort` (it can't be imported, see above): the query is cancelled in the database when `signal` aborts, and fails as a timeout. */
function cancelOnAbort<T extends readonly postgres.MaybeRow[]>(signal: AbortSignal, query: () => postgres.PendingQuery<T>): Promise<postgres.RowList<T>> {
	if (signal.aborted) return Promise.reject(Object.assign(new Error('canceling statement due to user request'), { code: '57014' }));
	const pending = query();
	const stop = () => void pending.cancel();
	signal.addEventListener('abort', stop, { once: true });
	return Promise.resolve(pending).finally(() => signal.removeEventListener('abort', stop));
}

/** A `cut` for a layer whose SQL depends on the zoom. */
function cutOf(sqlFor: (z: number) => string): NonNullable<TileLayerDef['cut']> {
	return async (tx: postgres.TransactionSql, t: TileId, signal: AbortSignal): Promise<Uint8Array> => {
		const [row] = await cancelOnAbort(signal, () => tx.unsafe(sqlFor(t.z), [t.z, t.x, t.y]));
		return row?.mvt ? new Uint8Array(row.mvt) : new Uint8Array();
	};
}

/** Ways and the valley-zoom network: OpenStreetMap's, ODbL, republish yes. */
export const paths: TileLayerDef = { plugin: PLUGIN, layer: 'paths', minzoom: MIN_ZOOM, maxzoom: MAX_ZOOM, cut: cutOf(pathsSql) };
/** The route relations' lines: OpenStreetMap's, ODbL, republish yes. */
export const routes: TileLayerDef = { plugin: PLUGIN, layer: 'routes', minzoom: MIN_ZOOM, maxzoom: MAX_ZOOM, cut: cutOf(routesSql) };
/** What the City's lines draw themselves: the City's with ODbL, republish aggregates. */
export const agency: TileLayerDef = { plugin: PLUGIN, layer: 'agency', minzoom: MIN_ZOOM, maxzoom: MAX_ZOOM, cut: cutOf(agencySql) };

export default [paths, routes, agency] satisfies TileLayerDef[];
