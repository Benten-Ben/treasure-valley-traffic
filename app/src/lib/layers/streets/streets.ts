import type { ExpressionSpecification, FilterSpecification } from 'maplibre-gl';
import type { SlottedLayer } from '#lib/map/order.js';
import { speedExpression, UNDER_WIDTH, type RampName } from './ramp.js';

/**
 * The Streets layer: every Ada County road from ACHD's centerlines, colored by
 * posted speed (one hue, light to dark as speed rises; docs/14 §14.5),
 * widened by road class, with arrows on one-way streets and speed numbers
 * along the bigger roads. Tiles are cut by PostGIS on request
 * (/api/tiles/roads/{z}/{x}/{y}).
 *
 * The speed lines come twice on the same source: the blue ramp "alone", and
 * the pale slate ramp at 70% width "under Transit" (with its own casing).
 * Transit toggles which pair is visible, so no tile is fetched again.
 */

export interface StreetProps {
	id: number;
	name: string | null;
	class: string | null;
	speed: number | null;
	one_way: 'both' | 'forward' | 'backward';
	private: boolean | null;
	elevated: boolean;
	community: string | null;
}

export function oneWayText(s: Pick<StreetProps, 'one_way'>): string {
	return s.one_way === 'both' ? 'Two-way' : 'One-way (arrows show direction)';
}

/** Line width at zoom 14, by road class. */
const CLASS_WIDTH: Record<string, number> = {
	Interstate: 5,
	'Principal Arterial': 4.5,
	'Minor Arterial': 3.5,
	Ramp: 2.5,
	Collector: 2.5,
	Local: 1.4
};

export const L = {
	selectedHalo: 'streets-selected-halo',
	selected: 'streets-selected',
	casing: 'streets-casing',
	casingUnder: 'streets-casing-under',
	speed: 'streets-speed',
	speedUnder: 'streets-speed-under',
	labels: 'streets-speed-labels',
	oneway: 'streets-oneway'
} as const;

/** The two speed lines, each with its casing: "alone" (Transit off) and "under Transit". */
export const RAMP_LAYERS: Record<RampName, readonly string[]> = {
	alone: [L.casing, L.speed],
	under: [L.casingUnder, L.speedUnder]
};

/** Which of the street layers show, for the layer's visibility and the ramp in use. */
export function visibleStreetLayers(on: boolean, ramp: RampName): Set<string> {
	if (!on) return new Set();
	const other = RAMP_LAYERS[ramp === 'alone' ? 'under' : 'alone'];
	return new Set(STREET_LAYERS.filter((id) => !other.includes(id)));
}

/** The filter that picks out the selected road (none: an id no segment has). */
export function selectedFilter(id: number | null): FilterSpecification {
	const n = id ?? -1;
	return ['any', ['==', ['id'], n], ['==', ['get', 'id'], n]];
}

export const STREET_LAYERS: string[] = Object.values(L);
export const ROADS_SOURCE = 'roads';
export const CHEVRON = 'oneway-chevron';

const classWidth: ExpressionSpecification = [
	'match',
	['get', 'class'],
	...Object.entries(CLASS_WIDTH).flat(),
	1
] as unknown as ExpressionSpecification;

/** Line width by road class and zoom, times `scale`, plus `extra` px (a casing's edge). */
const width = (extra = 0, scale = 1): ExpressionSpecification => [
	'interpolate',
	['linear'],
	['zoom'],
	9,
	['+', ['*', classWidth, 0.35 * scale], extra * 0.5],
	14,
	['+', ['*', classWidth, scale], extra],
	17,
	['+', ['*', classWidth, 2 * scale], extra]
];

/**
 * The layers, each with its slot (docs/14 §14.8 "Layer order"): the lines in
 * `streets` (draped with the base), the chevrons and speed numbers in
 * `labels`. All start hidden.
 */
export function streetLayers(): SlottedLayer[] {
	const hidden = { visibility: 'none' as const };
	const line = { ...hidden, 'line-cap': 'round' as const, 'line-join': 'round' as const };
	return [
		// The selected road (§14.3): a 2 px ink edge in a 3 px cream halo, under its speed line.
		{
			slot: 'streets',
			layer: { id: L.selectedHalo, type: 'line', source: ROADS_SOURCE, 'source-layer': 'roads', filter: selectedFilter(null),
				layout: { ...hidden, 'line-cap': 'round', 'line-join': 'round' },
				paint: { 'line-color': '#fffbf4', 'line-width': width(10) } }
		},
		{
			slot: 'streets',
			layer: { id: L.selected, type: 'line', source: ROADS_SOURCE, 'source-layer': 'roads', filter: selectedFilter(null),
				layout: { ...hidden, 'line-cap': 'round', 'line-join': 'round' },
				paint: { 'line-color': '#2b2a33', 'line-width': width(4) } }
		},
		// The cream casings, alone and under Transit (70% width), under both speed lines.
		{
			slot: 'streets',
			layer: { id: L.casing, type: 'line', source: ROADS_SOURCE, 'source-layer': 'roads', layout: { ...line },
				paint: { 'line-color': '#fffbf4', 'line-width': width(2), 'line-opacity': 0.9 } }
		},
		{
			slot: 'streets',
			layer: { id: L.casingUnder, type: 'line', source: ROADS_SOURCE, 'source-layer': 'roads', layout: { ...line },
				paint: { 'line-color': '#fffbf4', 'line-width': width(1.5, UNDER_WIDTH), 'line-opacity': 0.9 } }
		},
		// The speed lines: the blue ramp alone, the slate ramp under Transit (§14.5).
		{
			slot: 'streets',
			layer: { id: L.speed, type: 'line', source: ROADS_SOURCE, 'source-layer': 'roads', layout: { ...line },
				paint: { 'line-color': speedExpression('alone'), 'line-width': width() } }
		},
		{
			slot: 'streets',
			layer: { id: L.speedUnder, type: 'line', source: ROADS_SOURCE, 'source-layer': 'roads', layout: { ...line },
				paint: { 'line-color': speedExpression('under'), 'line-width': width(0, UNDER_WIDTH) } }
		},
		{
			slot: 'labels',
			layer: { id: L.oneway, type: 'symbol', source: ROADS_SOURCE, 'source-layer': 'roads', minzoom: 14,
				filter: ['!=', ['get', 'one_way'], 'both'],
				layout: { ...hidden, 'symbol-placement': 'line', 'symbol-spacing': 90, 'icon-image': CHEVRON,
					'icon-rotate': ['case', ['==', ['get', 'one_way'], 'backward'], 180, 0],
					'icon-rotation-alignment': 'map', 'icon-allow-overlap': true } }
		},
		{
			slot: 'labels',
			layer: { id: L.labels, type: 'symbol', source: ROADS_SOURCE, 'source-layer': 'roads', minzoom: 13,
				filter: ['in', ['get', 'class'], ['literal', ['Interstate', 'Principal Arterial', 'Minor Arterial', 'Collector']]],
				layout: { ...hidden, 'symbol-placement': 'line', 'symbol-spacing': 280, 'text-field': ['to-string', ['get', 'speed']],
					'text-font': ['Noto Sans Medium'], 'text-size': 11, 'text-rotation-alignment': 'viewport' },
				paint: { 'text-color': '#2b2a33', 'text-halo-color': '#fffbf4', 'text-halo-width': 2 } }
		}
	];
}

/** A chevron pointing right (the line's direction), ink with a cream outline. */
export function chevron(): ImageData {
	const w = 24;
	const h = 20;
	const c = document.createElement('canvas');
	c.width = w;
	c.height = h;
	const g = c.getContext('2d')!;
	g.beginPath();
	g.moveTo(5, 3);
	g.lineTo(19, 10);
	g.lineTo(5, 17);
	g.lineJoin = 'round';
	g.lineCap = 'round';
	g.lineWidth = 7;
	g.strokeStyle = '#fffbf4';
	g.stroke();
	g.lineWidth = 3.5;
	g.strokeStyle = '#2b2a33';
	g.stroke();
	return g.getImageData(0, 0, w, h);
}
