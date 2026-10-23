import type { LayerSpecification } from 'maplibre-gl';
import type { SlottedLayer } from '#lib/map/order.js';
import { SHOW_BY_DEFS, type ShowBy } from './model.js';
import { COPY_OPACITY, FILL_OPACITY, HALO, LABEL, OUTLINE, PATTERN_OPACITY, SELECTED, STEPS, SURVEY_LINE } from './palette.js';
import { imageId } from './patterns.js';
import { MVT_LABELS, MVT_SURVEY, MVT_UNITS, NAMES_FROM, OUTLINE_FROM, SURVEY_TO, SYMBOLS_FROM, WASH_FROM } from './tiles.js';

/**
 * The Soils layer's style layers (landscape sprint plan v3 §3.2, §3.5; P1-app). Pure: the module
 * (index.svelte.ts) adds them and re-styles them when "Show by" changes.
 *
 * - **The wash** in `areas` at rank 20 (an area fill: one at a time), from z9 where the tiles carry it, and its
 *   0.45 copy in `land` at rank 5 over Aerial only. Hue-free: five gray steps for the chosen property; a unit
 *   NRCS doesn't rate for it draws nothing.
 * - **Patterns** over the wash in `land` at rank 10 (hatch, stipple, crossed lines), from z11; they are part of
 *   the fill, so they follow it.
 * - **Linework** in `land` at rank 10: the survey areas' bounds (dashed) at z8-11, the map-unit outlines from
 *   z12, and the selected unit's outline.
 * - **Symbols** from z14 and **names** from z16, in `labels`.
 * - Pick layers (no fill drawn) so a click opens the card whenever the layer is on, whichever area fill draws.
 *
 * One vector source, `soils` (the tiles of `./tiles.ts`).
 */
export const SOURCE = 'soils';

export const ID = {
	fill: 'soils-fill',
	copy: 'soils-fill-aerial',
	pick: 'soils-pick',
	pattern: 'soils-pattern',
	survey: 'soils-survey',
	outline: 'soils-outline',
	selected: 'soils-selected',
	symbol: 'soils-symbol',
	name: 'soils-name'
} as const;

/** The layers a click on a map unit can hit. */
export const PICK_LAYERS: string[] = [ID.pick];

export type Expr = unknown[];
const CLEAR = 'rgba(0,0,0,0)';
const NONE: Expr = ['==', ['literal', 0], 1];
const hidden = { visibility: 'none' } as const;

/** The selected-outline layer's filter for a map unit (none selected: nothing matches). */
export const selectedFilter = (mukey: string | null): Expr => ['==', ['get', 'mukey'], mukey ?? ''];

/** The wash colour for a property: the step of each code, nothing for an unrated unit. */
export function fillColor(by: ShowBy): Expr {
	const d = SHOW_BY_DEFS[by];
	return ['match', ['coalesce', ['get', by], -1], ...d.steps.flatMap((step, code) => [code, STEPS[step]]), CLEAR];
}

/** Which features carry a pattern for this property, and which image. */
export function patternFilter(by: ShowBy): Expr {
	if (by === 'restr') return ['match', ['get', 'pat'], ['hardpan', 'bedrock'], true, false];
	if (by === 'farm') return ['match', ['get', 'cond'], ['drained', 'reclaimed'], true, false];
	if (by === 'hsg') return ['==', ['get', 'dual'], true];
	return NONE;
}
export function patternImage(by: ShowBy): Expr {
	if (by === 'restr') return ['match', ['get', 'pat'], 'bedrock', imageId('stipple'), imageId('hatch')];
	if (by === 'farm') return ['match', ['get', 'cond'], 'reclaimed', imageId('cross'), imageId('hatch')];
	return ['literal', imageId('hatch')];
}

type Slotted = Omit<SlottedLayer, 'layer'> & { layer: LayerSpecification };

export interface SoilLayers {
	/** rank 20 */
	areas: SlottedLayer[];
	/** rank 5 */
	copies: SlottedLayer[];
	/** rank 10 */
	land: SlottedLayer[];
	/** rank 25 */
	labels: SlottedLayer[];
}

const units = { source: SOURCE, 'source-layer': MVT_UNITS } as const;

export function soilLayers(by: ShowBy): SoilLayers {
	const fill = (id: string, opacity: number): LayerSpecification =>
		({ id, type: 'fill', ...units, minzoom: WASH_FROM, layout: hidden, paint: { 'fill-color': fillColor(by), 'fill-opacity': opacity, 'fill-antialias': false } }) as unknown as LayerSpecification;
	const areas: Slotted[] = [
		{ slot: 'areas', layer: fill(ID.fill, FILL_OPACITY), areaFill: true },
		// Not an area fill: it draws nothing, so the card opens even while another layer's fill is the one drawn.
		{ slot: 'areas', layer: { id: ID.pick, type: 'fill', ...units, minzoom: WASH_FROM, layout: hidden, paint: { 'fill-color': CLEAR, 'fill-opacity': 0 } } as unknown as LayerSpecification }
	];
	const copies: Slotted[] = [{ slot: 'land', layer: fill(ID.copy, COPY_OPACITY), areaFill: true, aerial: 'only' }];
	const land: Slotted[] = [
		{
			slot: 'land',
			layer: { id: ID.pattern, type: 'fill', ...units, minzoom: 11, filter: patternFilter(by), layout: hidden, paint: { 'fill-pattern': patternImage(by), 'fill-opacity': PATTERN_OPACITY } } as unknown as LayerSpecification,
			areaFill: true
		},
		{
			slot: 'land',
			layer: {
				id: ID.survey,
				type: 'line',
				source: SOURCE,
				'source-layer': MVT_SURVEY,
				maxzoom: SURVEY_TO,
				layout: { ...hidden, 'line-join': 'round' },
				paint: { 'line-color': SURVEY_LINE, 'line-width': 1.2, 'line-dasharray': [4, 3], 'line-opacity': 0.8 }
			} as unknown as LayerSpecification
		},
		{
			slot: 'land',
			layer: {
				id: ID.outline,
				type: 'line',
				...units,
				minzoom: OUTLINE_FROM,
				layout: { ...hidden, 'line-join': 'round' },
				paint: { 'line-color': OUTLINE, 'line-width': ['interpolate', ['linear'], ['zoom'], OUTLINE_FROM, 0.4, 16, 1, 18, 1.4] as never, 'line-opacity': 0.55 }
			} as unknown as LayerSpecification
		},
		{
			// The selected map unit's outline (the module sets the filter to its key).
			slot: 'land',
			layer: { id: ID.selected, type: 'line', ...units, minzoom: WASH_FROM, filter: selectedFilter(null), layout: { ...hidden, 'line-join': 'round' }, paint: { 'line-color': SELECTED, 'line-width': 2.5 } } as unknown as LayerSpecification
		}
	];
	const text = {
		source: SOURCE,
		'source-layer': MVT_LABELS,
		paint: { 'text-color': LABEL, 'text-halo-color': HALO, 'text-halo-width': 1.4 }
	};
	const labels: Slotted[] = [
		{
			slot: 'labels',
			layer: {
				id: ID.symbol,
				type: 'symbol',
				...text,
				minzoom: SYMBOLS_FROM,
				maxzoom: NAMES_FROM,
				layout: { ...hidden, 'text-field': ['get', 'symbol'], 'text-font': ['Noto Sans Medium'], 'text-size': ['interpolate', ['linear'], ['zoom'], SYMBOLS_FROM, 10, NAMES_FROM, 12], 'text-padding': 4 }
			} as unknown as LayerSpecification
		},
		{
			slot: 'labels',
			layer: {
				id: ID.name,
				type: 'symbol',
				...text,
				minzoom: NAMES_FROM,
				layout: {
					...hidden,
					'text-field': ['concat', ['get', 'symbol'], '\n', ['coalesce', ['get', 'name'], '']],
					'text-font': ['Noto Sans Medium'],
					'text-size': 12,
					'text-max-width': 8,
					'text-padding': 4
				}
			} as unknown as LayerSpecification
		}
	];
	return { areas, copies, land, labels };
}

/** Every layer the module adds. */
export const ALL_IDS: string[] = Object.values(ID);

/** A change to apply to a layer already on the map. */
export type Restyle = { id: string; filter?: Expr; paint?: [string, unknown][] };

/** What changes on the map when "Show by" changes: the wash's colours and the patterns (visibility is the manager's). */
export function restyle(by: ShowBy): Restyle[] {
	return [
		{ id: ID.fill, paint: [['fill-color', fillColor(by)]] },
		{ id: ID.copy, paint: [['fill-color', fillColor(by)]] },
		{ id: ID.pattern, filter: patternFilter(by), paint: [['fill-pattern', patternImage(by)]] }
	];
}
