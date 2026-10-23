import type postgres from 'postgres';
import type { TileLayerDef } from '../mvt.js';

/**
 * The Soils layer's vector tiles (landscape sprint P1-app; plugins/soils/README.md, "Zoom bands for the Soils
 * layer's tiles"): `GET /api/soils/tiles/units/{z}/{x}/{y}?v=`, read by the generic tile route. The soils
 * build (`soils-load`) writes the layer's one version row (`soils.units`), with the licence, republish and
 * credit.
 *
 * Three MVT layers, by band:
 *
 * | Zooms | `soils` (the wash and outlines: a map unit's shape) | `survey` | `soil_labels` |
 * |---|---|---|---|
 * | z8 | (none: the wash comes in at z9, `WASH_FROM`) | `survey_area.geom_lo` | |
 * | z9 | `soils.map_unit.geom_z8` (100 m), one feature per map unit | `survey_area.geom_lo` | |
 * | z10-11 | `soils.map_unit.geom_z10` (25 m), one per map unit | `survey_area.geom_lo` | |
 * | z12-13 | `soils.polygon.geom_lo` (5 m), one per polygon | | |
 * | z14 on | `soils.polygon.geom` (the overzoomed top zoom) | | `soils.polygon.label_pt`, one per polygon |
 *
 * Only what the map draws travels: `mukey`, `symbol` (the map-unit symbol, "Pm"), the show-by codes
 * (`restr`, `drain`, `aws`, `farm`, `hsg`: 0 is the palest step of the wash, absent means not rated), and the
 * hatches' words (`pat` hardpan or bedrock; `cond` drained or reclaimed; `dual` a dual hydrologic group).
 * The polygon bands join the map unit for them: the codes live on `soils.map_unit`, and the shared tile
 * definition (`parts`) reads one table per band, so this layer cuts its own tiles. The name on a label is the
 * map unit's name up to the first comma ("Purdam silt loam"), on the labels only.
 *
 * mvt.ts finds this file by glob while it loads, so it takes nothing from it at run time (a circular import
 * leaves the registry empty under some loaders): the tile extent and buffer are written out below, and
 * `stopOnAbort` is mvt.ts's `cancelOnAbort`. The test checks both against mvt.ts's.
 */
export const PLUGIN = 'soils';
export const LAYER = 'units';
/** The MVT layers (a style's `source-layer`). */
export const MVT_UNITS = 'soils';
export const MVT_SURVEY = 'survey';
export const MVT_LABELS = 'soil_labels';
/** The layer's zooms: the source stops at z14 and the client overzooms. */
export const MIN_ZOOM = 8;
export const MAX_ZOOM = 14;
/** Where each band starts. */
export const BANDS = { z8: 8, z10: 10, z12: 12, z14: 14 } as const;
/**
 * The wash starts here. The z8 tile over the valley held every map unit (337 KB raw, 251 KB gzip for the
 * busiest one, over the 150 KB budget; plugins/soils/README.md measured 319 KB raw for the geometry alone), so
 * z8 carries the survey bounds only and the wash comes in at z9 (141 KB). A tiling choice inside the app:
 * simplifying the z8 geometry (`SIMPLIFY_Z8_M`) would be a data change for its own issue.
 */
export const WASH_FROM = 9;
/** The survey bounds stop here; labels start at the top zoom. */
export const SURVEY_MAX_ZOOM = 11;
export const LABELS_FROM = 14;

export const EXTENT = 4096;
export const BUFFER = 64;

const ENV = 'ST_TileEnvelope($1::int, $2::int, $3::int)';
const WIDE = `ST_TileEnvelope($1::int, $2::int, $3::int, margin => ${BUFFER / EXTENT})`;
/** The columns a feature carries, from `soils.map_unit` aliased `m`. */
const PROPS = 'm.mukey, m.musym as symbol, m.c_restr as restr, nullif(m.pat, \'none\') as pat, m.c_drain as drain, m.c_aws as aws, m.c_farm as farm, case when m.farm_cond in (\'drained\', \'reclaimed\') then m.farm_cond end as cond, m.c_hsg as hsg, nullif(m.hsg_dual, false) as dual';

const mvt = (name: string, inner: string) => `coalesce((select ST_AsMVT(t, '${name}', ${EXTENT}, 'mvt_geom') from (${inner}) t where t.mvt_geom is not null), ''::bytea)`;
const geom = (g: string) => `ST_AsMVTGeom(ST_Transform(${g}, 3857), ${ENV}, ${EXTENT}, ${BUFFER}, true) as mvt_geom`;
const near = (g: string) => `${g} && ST_Transform(${WIDE}, 4326)`;

/** The SQL for a map unit's own generalised geometry (z8-11). */
const unitsByMapUnit = (col: 'geom_z8' | 'geom_z10') => mvt(MVT_UNITS, `select ${PROPS}, ${geom(`m.${col}`)} from soils.map_unit m where ${near(`m.${col}`)}`);
/** The SQL for polygons joined to their map unit (z12 on). */
const unitsByPolygon = (col: 'geom_lo' | 'geom') =>
	mvt(MVT_UNITS, `select ${PROPS}, ${geom(`p.${col}`)} from soils.polygon p join soils.map_unit m using (mukey) where ${near(`p.${col}`)}`);
const survey = mvt(MVT_SURVEY, `select s.areasymbol as area, ${geom('s.geom_lo')} from soils.survey_area s where ${near('s.geom_lo')}`);
const labels = mvt(
	MVT_LABELS,
	`select m.mukey, m.musym as symbol, split_part(m.muname, ',', 1) as name, ${geom('p.label_pt')} from soils.polygon p join soils.map_unit m using (mukey) where p.label_pt is not null and ${near('p.label_pt')}`
);

/** The tile's SQL at a zoom ($1-$3 are z, x, y), or null outside the layer. */
export function tileSql(z: number): string | null {
	if (!Number.isInteger(z) || z < MIN_ZOOM || z > MAX_ZOOM) return null;
	let parts: string[];
	if (z < WASH_FROM) parts = [survey];
	else if (z < BANDS.z10) parts = [survey, unitsByMapUnit('geom_z8')];
	else if (z < BANDS.z12) parts = [survey, unitsByMapUnit('geom_z10')];
	else if (z < BANDS.z14) parts = [unitsByPolygon('geom_lo')];
	else parts = [unitsByPolygon('geom'), labels];
	return `select ${parts.join(' || ')} as mvt`;
}

function stopOnAbort<T extends readonly postgres.MaybeRow[]>(signal: AbortSignal, query: () => postgres.PendingQuery<T>): Promise<postgres.RowList<T>> {
	if (signal.aborted) return Promise.reject(Object.assign(new Error('canceling statement due to user request'), { code: '57014' }));
	const pending = query();
	const stop = () => void pending.cancel();
	signal.addEventListener('abort', stop, { once: true });
	return Promise.resolve(pending).finally(() => signal.removeEventListener('abort', stop));
}

const units: TileLayerDef = {
	plugin: PLUGIN,
	layer: LAYER,
	minzoom: MIN_ZOOM,
	maxzoom: MAX_ZOOM,
	cut: async (sql: postgres.TransactionSql, t, signal) => {
		const text = tileSql(t.z);
		if (!text) return new Uint8Array();
		const [row] = await stopOnAbort(signal, () => sql.unsafe(text, [t.z, t.x, t.y]));
		return row?.mvt ? new Uint8Array(row.mvt) : new Uint8Array();
	}
};

export default units satisfies TileLayerDef;
