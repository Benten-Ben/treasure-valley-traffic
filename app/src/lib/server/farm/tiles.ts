import type postgres from 'postgres';
import type { TileLayerDef } from '../mvt.js';

/**
 * The crop fields' vector tiles (landscape sprint P3-app; plugins/farm/README.md, "Crop fields"):
 * `GET /api/farm/tiles/crop_fields/{z}/{x}/{y}?v=`, read by the generic tile route.
 *
 * - **`crop_fields`**: z8, z9 and z10 are the dissolves of the current crop year (`g`, the crop group) and
 *   of the growth states (`s`: built_over, being_built, plat), one view per zoom; from z11 it is one feature
 *   per current field (`id`, `a` acres, `g` group, `n` crop name, `y` one letter per year from 2018, `s`
 *   growth, `st` July state, `p` approved plat). The build (`farm-derive`) writes the layer's one version
 *   row, with the licence, republish and credit.
 * - **`crop_year_<year>`** (2018 to 2024): the year switcher's z8-10 dissolves of an earlier year, a cut of
 *   its own over `farm.field_lo` (the table holds every year: all eight together are about 630 KB at the
 *   densest z10 tile, too much for one tile). They take `crop_fields`' version and credit (`versionOf`). From
 *   z11 the switcher recolours the field tiles by their `y` letters, so these stop at z10.
 */
export const PLUGIN = 'farm';
export const FIELDS_LAYER = 'crop_fields';
/** The earlier crop years that have a z8-10 cut of their own (the newest year is `crop_fields`' own). */
export const YEARS = [2018, 2019, 2020, 2021, 2022, 2023, 2024] as const;
/** The MVT layer inside every tile of both kinds (a style's `source-layer`). */
export const MVT_LAYER = 'fields';
/** Where the per-field tiles start (the dissolves below), and where the layer stops (the client overzooms past it). */
export const FIELDS_FROM = 11;
export const LAYER_MAXZOOM = 14;
/** The dissolves' zooms, and the year cuts'. */
export const LO_ZOOMS = [8, 9, 10] as const;

export const yearLayer = (year: number): string => `crop_year_${year}`;

const fields: TileLayerDef = {
	plugin: PLUGIN,
	layer: FIELDS_LAYER,
	minzoom: 8,
	maxzoom: LAYER_MAXZOOM,
	parts: [
		{
			name: MVT_LAYER,
			sources: [
				...LO_ZOOMS.map((z) => ({ minzoom: z, maxzoom: z, table: `farm.crop_fields_lo${z}`, srid: 3857 as const, columns: ['g', 's'] as const })),
				{ minzoom: FIELDS_FROM, maxzoom: LAYER_MAXZOOM, table: 'farm.crop_fields', id: 'id', columns: ['a', 'g', 'n', 'y', 's', 'st', 'p'] as const }
			]
		}
	]
};

/**
 * One earlier year's dissolves for a tile: the rows of `farm.field_lo` for the year at this zoom, cut to the
 * tile like the views' (3857 already, so no transform). Only `g`: the year switcher draws crop groups.
 */
/**
 * mvt.ts finds this file by glob while it loads, so this file takes nothing from it at run time (a circular
 * import leaves the registry empty under some loaders): the tile extent and buffer are written out below, and
 * `stopOnAbort` is mvt.ts's `cancelOnAbort`. The test checks both against mvt.ts's.
 */
function stopOnAbort<T extends readonly postgres.MaybeRow[]>(signal: AbortSignal, query: () => postgres.PendingQuery<T>): Promise<postgres.RowList<T>> {
	if (signal.aborted) return Promise.reject(Object.assign(new Error('canceling statement due to user request'), { code: '57014' }));
	const pending = query();
	const stop = () => void pending.cancel();
	signal.addEventListener('abort', stop, { once: true });
	return Promise.resolve(pending).finally(() => signal.removeEventListener('abort', stop));
}

const EXTENT = 4096;
const BUFFER = 64;

export const YEAR_SQL = `select coalesce(ST_AsMVT(t, '${MVT_LAYER}', ${EXTENT}, 'mvt_geom'), ''::bytea) as mvt from (
	select s.key as g, ST_AsMVTGeom(s.geom, ST_TileEnvelope($1::int, $2::int, $3::int), ${EXTENT}, ${BUFFER}, true) as mvt_geom
	from farm.field_lo s
	where s.z = $1::int and s.yr = $4::int and s.geom && ST_TileEnvelope($1::int, $2::int, $3::int, margin => 0.015625)
) t where t.mvt_geom is not null`;

function yearCut(year: number): NonNullable<TileLayerDef['cut']> {
	return async (sql: postgres.TransactionSql, t, signal) => {
		const [row] = await stopOnAbort(signal, () => sql.unsafe(YEAR_SQL, [t.z, t.x, t.y, year]));
		return row?.mvt ? new Uint8Array(row.mvt) : new Uint8Array();
	};
}

const years: TileLayerDef[] = YEARS.map((year) => ({
	plugin: PLUGIN,
	layer: yearLayer(year),
	minzoom: LO_ZOOMS[0],
	maxzoom: LO_ZOOMS[LO_ZOOMS.length - 1],
	versionOf: FIELDS_LAYER,
	cut: yearCut(year)
}));

export default [fields, ...years] satisfies TileLayerDef[];
