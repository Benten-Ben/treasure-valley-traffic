import type { LayerSpecification } from 'maplibre-gl';
import type { SlottedLayer } from '#lib/map/order.js';
import { INK } from '#lib/map/color.js';
import { EDGE, EDGE_ESTIMATED, FILL, GROUPS, GROUP_NAME, LETTER, PATTERN_INK, type CropGroup } from './palette.js';
import { GROWTH_KEYS, imageId, type GrowthKey } from './patterns.js';
import { FIELDS_FROM, MVT_LAYER } from './tiles.js';

/**
 * The Crop fields layer's style layers (landscape sprint plan §3.4 K1-K2, §3.5; P3-app). Pure: the module
 * (index.svelte.ts) adds them and re-styles them when the year or the growth toggles change.
 *
 * - **Fills** in `areas` at rank 10, Clay only (`looks: 'clay'`: the hay cyan sits near Valley's water), and
 *   their 0.45 copies in `land` at rank 5, shown over Aerial only. All are area fills (one at a time, off under
 *   Transit). z8-10 draw the dissolves (`g`); from z11 each field, coloured by its letter for the year.
 * - **Patterns, the growth hatch and linework** in `land` at rank 20: every group has a pattern; cream edges
 *   from z12; the dashed "estimated edge" comes in as the fills fade out over z14.5-15.5.
 * - **Labels** from z13.5, in the labels slot.
 *
 * Two vector sources feed them: `crops-fields` (the fields tiles, z8-14) and `crops-year` (an earlier year's
 * z8-10 dissolves, its tile URL swapped when the year changes). The current year's dissolves come from
 * `crops-fields`; an earlier year's from `crops-year`; from z11 all years come from `crops-fields`' letters.
 */
export const SOURCE_FIELDS = 'crops-fields';
export const SOURCE_YEAR = 'crops-year';

export const ID = {
	fillLo: 'crops-fill-lo',
	fillLoYear: 'crops-fill-lo-year',
	fill: 'crops-fill',
	copyLo: 'crops-fill-lo-aerial',
	copyLoYear: 'crops-fill-lo-year-aerial',
	copy: 'crops-fill-aerial',
	patternLo: 'crops-pattern-lo',
	patternLoYear: 'crops-pattern-lo-year',
	pattern: 'crops-pattern',
	growthLo: 'crops-growth-lo',
	growth: 'crops-growth',
	plat: 'crops-plat',
	edge: 'crops-edge',
	edgeEstimated: 'crops-edge-estimated',
	label: 'crops-label',
	selected: 'crops-selected'
} as const;

/**
 * The layers a click on a field can hit: the fills, their copies over Aerial, and the growth and plat hatches
 * (a built-over field has no fill, but its hatch is its card's way in while that toggle is on).
 */
export const PICK_LAYERS: string[] = [ID.fill, ID.copy, ID.growth, ID.plat];

/** Where fills fade out and the dashed estimated edge comes in (plan §3.5). */
export const FADE_FROM = 14.5;
export const FADE_TO = 15.5;
export const EDGE_FROM = 12;
export const LABEL_FROM = 13.5;
/** The fills' opacity, and the copies' over Aerial. */
export const FILL_OPACITY = 0.85;
export const COPY_OPACITY = 0.45;
export const PATTERN_OPACITY = 0.6;
export const GROWTH_OPACITY = 0.75;

/** What the style depends on. */
export interface CropState {
	/** The year shown. */
	year: number;
	/** The newest year (the fields layer's own dissolves), and the edition's first. */
	current: number;
	first: number;
	growth: Record<GrowthKey, boolean>;
}

/** The selected-outline layer's filter when nothing is selected, and for a field. */
export const SELECTED_NONE: Expr = ['==', ['id'], -1];
export const selectedFilter = (id: string | number | null): Expr => ['==', ['id'], id === null ? -1 : Number(id)];

export const DEFAULT_GROWTH: Record<GrowthKey, boolean> = { built_over: true, being_built: true, plat: false };

export type Expr = unknown[];

const NONE: Expr = ['==', ['literal', 0], 1];
const CLEAR = 'rgba(0,0,0,0)';
const GROUP_LETTERS = GROUPS.map((g) => LETTER[g]);

/** The field's letter for a year, from the tiles' `y` (one per year from the edition's first). */
export const letterAt = (state: Pick<CropState, 'year' | 'first'>): Expr => {
	const i = state.year - state.first;
	return ['slice', ['get', 'y'], i, i + 1];
};

const fade = (v: number): Expr => ['interpolate', ['linear'], ['zoom'], FADE_FROM, v, FADE_TO, 0];

/** `match input -> value per group`, with `other` for anything else. `keys` are the group names (lo) or letters. */
function byGroup<T>(input: Expr, keys: (g: CropGroup) => string, value: (g: CropGroup) => T, other: T): Expr {
	return ['match', input, ...GROUPS.flatMap((g) => [keys(g), value(g)]), other];
}

/** Fill colour: the dissolves' `g` at z8-10, the field's letter for the year from z11. */
export const fillColorLo = (): Expr => byGroup(['get', 'g'], (g) => g, (g) => FILL[g], CLEAR);
export const fillColorField = (s: Pick<CropState, 'year' | 'first'>): Expr => byGroup(letterAt(s), (g) => LETTER[g], (g) => FILL[g], CLEAR);
export const patternLo = (): Expr => byGroup(['get', 'g'], (g) => g, (g) => imageId(g), imageId('corn'));
export const patternField = (s: Pick<CropState, 'year' | 'first'>): Expr => byGroup(letterAt(s), (g) => LETTER[g], (g) => imageId(g), imageId('corn'));

/** Features that are a painted crop group. */
export const cropFilterLo = (): Expr => ['in', ['get', 'g'], ['literal', [...GROUPS]]];
export const cropFilterField = (s: Pick<CropState, 'year' | 'first'>): Expr => ['in', letterAt(s), ['literal', GROUP_LETTERS]];

/** The label: the CDL's crop name for the newest year, else the group's name for the year's letter. */
export function labelText(s: Pick<CropState, 'year' | 'first' | 'current'>): Expr {
	if (s.year === s.current) return ['coalesce', ['get', 'n'], '']; // the crop name ("Alfalfa")
	return byGroup(letterAt(s), (g) => LETTER[g], (g) => GROUP_NAME[g].split(/,| and /)[0], '');
}

/** The growth layers' filters: which of built over, being built and approved plats are on. */
export function growthFilters(on: Record<GrowthKey, boolean>): { lo: Expr; field: Expr; plat: Expr } {
	const states = GROWTH_KEYS.filter((k) => on[k]);
	const farm = states.filter((k) => k !== 'plat');
	return {
		lo: states.length ? ['in', ['get', 's'], ['literal', states]] : NONE,
		field: farm.length ? ['in', ['get', 's'], ['literal', farm]] : NONE,
		plat: on.plat ? ['==', ['get', 'p'], true] : NONE
	};
}

const growthPattern = (): Expr => ['match', ['get', 's'], ...GROWTH_KEYS.flatMap((k) => [k, imageId(k)]), imageId('plat')];

/**
 * Which dissolves draw at z8-10: the current year's from the fields tiles, an earlier year's from its own
 * source. The one that doesn't is moved out of every zoom the map shows (not filtered or hidden), so its
 * source asks for no tiles it won't draw, and the manager's visibility is never touched.
 */
export const OFF_RANGE: [number, number] = [22, 24];
export function loRange(s: Pick<CropState, 'year' | 'current'>, forYear: boolean, minzoom = 0): [number, number] {
	return forYear === (s.year !== s.current) ? [minzoom, FIELDS_FROM] : OFF_RANGE;
}

const hidden = { visibility: 'none' } as const;
const fadeOut = (v: number) => fade(v) as never;

/** Everything the module adds, by slot and rank. */
export interface CropLayers {
	/** rank 10 */
	areas: SlottedLayer[];
	/** rank 5 */
	copies: SlottedLayer[];
	/** rank 20 */
	land: SlottedLayer[];
	/** rank 25 */
	labels: SlottedLayer[];
}

type Slotted = Omit<SlottedLayer, 'layer'> & { layer: LayerSpecification };

export function cropLayers(s: CropState): CropLayers {
	const range = (forYear: boolean, minzoom = 0) => {
		const [min, max] = loRange(s, forYear, minzoom);
		return { minzoom: min, maxzoom: max };
	};
	const lo = (minzoom = 0) => ({ source: SOURCE_FIELDS, 'source-layer': MVT_LAYER, ...range(false, minzoom) });
	const loYear = (minzoom = 0) => ({ source: SOURCE_YEAR, 'source-layer': MVT_LAYER, ...range(true, minzoom) });
	const field = { source: SOURCE_FIELDS, 'source-layer': MVT_LAYER, minzoom: FIELDS_FROM } as const;
	const g = growthFilters(s.growth);
	const fill = (id: string, base: object, color: Expr, filter: Expr, opacity: number): LayerSpecification =>
		({ id, type: 'fill', ...base, filter, layout: hidden, paint: { 'fill-color': color, 'fill-opacity': fadeOut(opacity), 'fill-antialias': false } }) as unknown as LayerSpecification;
	const patternLayer = (id: string, base: object, image: Expr, filter: Expr, opacity: number): LayerSpecification =>
		({ id, type: 'fill', ...base, filter, layout: hidden, paint: { 'fill-pattern': image, 'fill-opacity': fadeOut(opacity) } }) as unknown as LayerSpecification;

	const clay = { areaFill: true as const, looks: 'clay' as const };
	const areas: Slotted[] = [
		{ slot: 'areas', layer: fill(ID.fillLo, lo(), fillColorLo(), cropFilterLo(), FILL_OPACITY), ...clay },
		{ slot: 'areas', layer: fill(ID.fillLoYear, loYear(), fillColorLo(), cropFilterLo(), FILL_OPACITY), ...clay },
		{ slot: 'areas', layer: fill(ID.fill, field, fillColorField(s), cropFilterField(s), FILL_OPACITY), ...clay }
	];
	const copy = { areaFill: true as const, aerial: 'only' as const };
	const copies: Slotted[] = [
		{ slot: 'land', layer: fill(ID.copyLo, lo(), fillColorLo(), cropFilterLo(), COPY_OPACITY), ...copy },
		{ slot: 'land', layer: fill(ID.copyLoYear, loYear(), fillColorLo(), cropFilterLo(), COPY_OPACITY), ...copy },
		{ slot: 'land', layer: fill(ID.copy, field, fillColorField(s), cropFilterField(s), COPY_OPACITY), ...copy }
	];
	const land: Slotted[] = [
		{ slot: 'land', layer: patternLayer(ID.patternLo, lo(10), patternLo(), cropFilterLo(), PATTERN_OPACITY), ...clay },
		{ slot: 'land', layer: patternLayer(ID.patternLoYear, loYear(10), patternLo(), cropFilterLo(), PATTERN_OPACITY), ...clay },
		{ slot: 'land', layer: patternLayer(ID.pattern, field, patternField(s), cropFilterField(s), PATTERN_OPACITY), ...clay },
		{ slot: 'land', layer: patternLayer(ID.growthLo, { source: SOURCE_FIELDS, 'source-layer': MVT_LAYER, minzoom: 9, maxzoom: FIELDS_FROM }, growthPattern(), g.lo, GROWTH_OPACITY), ...clay },
		{ slot: 'land', layer: patternLayer(ID.growth, field, growthPattern(), g.field, GROWTH_OPACITY), ...clay },
		{ slot: 'land', layer: patternLayer(ID.plat, field, ['literal', imageId('plat')], g.plat, GROWTH_OPACITY), ...clay },
		{
			slot: 'land',
			layer: {
				id: ID.edge,
				type: 'line',
				...field,
				minzoom: EDGE_FROM,
				filter: cropFilterField(s),
				layout: { ...hidden, 'line-join': 'round' },
				paint: { 'line-color': EDGE, 'line-width': ['interpolate', ['linear'], ['zoom'], EDGE_FROM, 0.5, 15, 1.2, 17, 1.8] as never, 'line-opacity': fadeOut(0.9) }
			} as unknown as LayerSpecification,
			...clay
		},
		{
			// The selected field's outline (the module sets the filter to its id).
			slot: 'land',
			layer: {
				id: ID.selected,
				type: 'line',
				...field,
				filter: SELECTED_NONE,
				layout: { ...hidden, 'line-join': 'round' },
				paint: { 'line-color': INK, 'line-width': 2.5 }
			} as unknown as LayerSpecification,
			...clay
		},
		{
			// The edge that stays once the fills are gone: dashed, because USDA's outline is a model, not a survey.
			slot: 'land',
			layer: {
				id: ID.edgeEstimated,
				type: 'line',
				...field,
				filter: cropFilterField(s),
				layout: { ...hidden, 'line-join': 'round' },
				paint: {
					'line-color': EDGE_ESTIMATED,
					'line-width': ['interpolate', ['linear'], ['zoom'], FADE_FROM, 1, 17, 1.6] as never,
					'line-dasharray': [3, 2],
					'line-opacity': ['interpolate', ['linear'], ['zoom'], FADE_FROM, 0, FADE_TO, 0.85] as never
				}
			} as unknown as LayerSpecification,
			...clay
		}
	];
	const labels: Slotted[] = [
		{
			slot: 'labels',
			layer: {
				id: ID.label,
				type: 'symbol',
				...field,
				minzoom: LABEL_FROM,
				filter: cropFilterField(s),
				layout: {
					...hidden,
					'text-field': labelText(s) as never,
					'text-font': ['Noto Sans Medium'],
					'text-size': ['interpolate', ['linear'], ['zoom'], LABEL_FROM, 10, 16, 12] as never,
					'text-max-width': 6,
					'text-padding': 4
				},
				paint: { 'text-color': INK, 'text-halo-color': EDGE, 'text-halo-width': 1.4 }
			} as unknown as LayerSpecification,
			...clay
		}
	];
	return { areas, copies, land, labels };
}

/** Every layer the module adds. */
export const ALL_IDS: string[] = Object.values(ID);

/** A change to apply to a layer already on the map. */
export type Restyle = { id: string; filter?: Expr; paint?: [string, unknown][]; layout?: [string, unknown][]; zoom?: [number, number] };

/**
 * What changes on the map when the year or a growth toggle changes: the filters and colours that depend on
 * them. (Visibility is the manager's and `setVisible`'s; these never touch it.)
 */
export function restyle(s: CropState): Restyle[] {
	const g = growthFilters(s.growth);
	const field = cropFilterField(s);
	return [
		{ id: ID.fillLo, zoom: loRange(s, false) },
		{ id: ID.fillLoYear, zoom: loRange(s, true) },
		{ id: ID.copyLo, zoom: loRange(s, false) },
		{ id: ID.copyLoYear, zoom: loRange(s, true) },
		{ id: ID.patternLo, zoom: loRange(s, false, 10) },
		{ id: ID.patternLoYear, zoom: loRange(s, true, 10) },
		{ id: ID.fill, filter: field, paint: [['fill-color', fillColorField(s)]] },
		{ id: ID.copy, filter: field, paint: [['fill-color', fillColorField(s)]] },
		{ id: ID.pattern, filter: field, paint: [['fill-pattern', patternField(s)]] },
		{ id: ID.edge, filter: field },
		{ id: ID.edgeEstimated, filter: field },
		{ id: ID.label, filter: field, layout: [['text-field', labelText(s)]] },
		{ id: ID.growthLo, filter: g.lo },
		{ id: ID.growth, filter: g.field },
		{ id: ID.plat, filter: g.plat }
	];
}

export { PATTERN_INK };
