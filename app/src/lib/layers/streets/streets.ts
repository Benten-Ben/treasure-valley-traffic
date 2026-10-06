import type { ExpressionSpecification } from 'maplibre-gl';
import type { SlottedLayer } from '#lib/map/order.js';

/**
 * The Streets layer: every Ada County road from ACHD's centerlines, colored by
 * posted speed (one hue, light to dark as speed rises), widened by road class,
 * with arrows on one-way streets and speed numbers along the bigger roads.
 * Tiles are cut by PostGIS on request (/api/tiles/roads/{z}/{x}/{y}).
 *
 * Ported from the Streets lens (lib/map/streets.ts) to the layer registry
 * (WP2); WP4 replaces the ramp with the stepped one of §14.5.
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

/** Posted-speed bins and colors: a validated single-hue ramp on the cream map. */
export const SPEED_BINS: { label: string; from: number; color: string }[] = [
	{ label: '20 mph or less', from: 0, color: '#6da7ec' },
	{ label: '25–30 mph', from: 25, color: '#3987e5' },
	{ label: '35–40 mph', from: 35, color: '#256abf' },
	{ label: '45–50 mph', from: 45, color: '#184f95' },
	{ label: '55 mph and up', from: 55, color: '#0d366b' }
];

export function speedColor(mph: number | null): string {
	let color = SPEED_BINS[0].color;
	for (const b of SPEED_BINS) if ((mph ?? 0) >= b.from) color = b.color;
	return color;
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
	casing: 'streets-casing',
	speed: 'streets-speed',
	labels: 'streets-speed-labels',
	oneway: 'streets-oneway'
} as const;

export const STREET_LAYERS: string[] = Object.values(L);
export const ROADS_SOURCE = 'roads';
export const CHEVRON = 'oneway-chevron';

const classWidth: ExpressionSpecification = [
	'match',
	['get', 'class'],
	...Object.entries(CLASS_WIDTH).flat(),
	1
] as unknown as ExpressionSpecification;

const width = (extra = 0): ExpressionSpecification => [
	'interpolate',
	['linear'],
	['zoom'],
	9,
	['+', ['*', classWidth, 0.35], extra * 0.5],
	14,
	['+', classWidth, extra],
	17,
	['+', ['*', classWidth, 2], extra]
];

/**
 * The layers, each with its slot (docs/14 §14.8 "Layer order"): the lines in
 * `streets` (draped with the base), the chevrons and speed numbers in
 * `labels`. All start hidden.
 */
export function streetLayers(): SlottedLayer[] {
	const hidden = { visibility: 'none' as const };
	const speedStep = [
		'step',
		['coalesce', ['get', 'speed'], 0],
		SPEED_BINS[0].color,
		...SPEED_BINS.slice(1).flatMap((b) => [b.from, b.color])
	] as unknown as ExpressionSpecification;
	return [
		{
			slot: 'streets',
			layer: { id: L.casing, type: 'line', source: ROADS_SOURCE, 'source-layer': 'roads',
				layout: { ...hidden, 'line-cap': 'round', 'line-join': 'round' },
				paint: { 'line-color': '#fffbf4', 'line-width': width(2), 'line-opacity': 0.9 } }
		},
		{
			slot: 'streets',
			layer: { id: L.speed, type: 'line', source: ROADS_SOURCE, 'source-layer': 'roads',
				layout: { ...hidden, 'line-cap': 'round', 'line-join': 'round' },
				paint: { 'line-color': speedStep, 'line-width': width() } }
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
