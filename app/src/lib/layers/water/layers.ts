import type { FeatureCollection } from 'geojson';
import type { LayerSpecification } from 'maplibre-gl';
import { BODIES, REACHES } from '#lib/base/water/water.base.js';
import { lineWidth, TONES } from '#lib/base/water/palette.js';
import type { SlottedLayer } from '#lib/map/order.js';
import { FLOOD_WORD, STRUCTURE_WORD, type Hazard, type EcoliSample, type WaterPoints } from './water.js';

/**
 * The Water layer's map parts (landscape sprint plan v3 §3.2 b5 and 10–13, §4.2 P4-app). Pure, so they're
 * unit-tested. The layer's own style layers, by slot:
 *
 * - `water`: the picked reach or area, drawn over the baked network (never a casing: one line, a little
 *   wider and darker, in place of the line it marks);
 * - `points`: gauges, structures, river hazards and E. coli sites, as badges (symbols never go below
 *   `anchor:routes`, so none is draped);
 * - `labels`: the italic names of reaches and areas, which replace the basemap's water labels while they draw.
 *
 * They read the shared landscape source (`landscape`, the baked file's source id) and two GeoJSON sources of
 * the layer's own. The baked layers themselves (and their picking) belong to the base contribution.
 */
export const LANDSCAPE_SOURCE = 'landscape';
export const POINTS_SOURCE = 'water-points';
export const NOTICES_SOURCE = 'water-notices';

export const SELECTED_REACH_LAYER = 'water-selected-reach';
export const SELECTED_BODY_LAYER = 'water-selected-body';
export const GAUGE_LAYER = 'water-gauges';
export const STRUCTURE_LAYER = 'water-structures';
export const STRUCTURE_MID_LAYER = 'water-structures-mid';
export const STRUCTURE_FINE_LAYER = 'water-structures-fine';
export const NOTICE_LAYER = 'water-notices';
export const LABEL_MAIN_LAYER = 'water-labels-main';
export const LABEL_FINE_LAYER = 'water-labels-fine';
export const LABEL_BODY_LAYER = 'water-labels-bodies';

/** The layers that draw from the baked file: they exist only once the water network is baked. */
export const BAKED_LAYERS = [SELECTED_REACH_LAYER, SELECTED_BODY_LAYER, LABEL_MAIN_LAYER, LABEL_FINE_LAYER, LABEL_BODY_LAYER] as const;
/** The layers of the layer's own points (always there once it is mounted). */
export const POINT_LAYERS = [STRUCTURE_LAYER, STRUCTURE_MID_LAYER, STRUCTURE_FINE_LAYER, GAUGE_LAYER, NOTICE_LAYER] as const;
/** Every pickable point layer. */
export const PICKABLE_POINT_LAYERS = [...POINT_LAYERS] as const;
/** The basemap water-label group's owner string, for `suppressGroups`. */
export const LABELS_OWNER = 'layer:water-labels';

/** Images (see `markers.ts`). */
export const IMAGE = {
	gauge: 'water-gauge',
	gaugeFlood: 'water-gauge-flood',
	structure: 'water-structure',
	hazard: 'water-hazard',
	ecoli: 'water-ecoli'
} as const;

/** Rows whose name sits under the badge, size px. */
const TEXT_SIZE = 11;
const INK = '#2b2a33';
const CREAM = '#fffbf4';

/** The id a point's feature and selection carry: `g:BSEI1`, `s:123`, `h:101`, `e:SITE`. */
export const pointId = {
	gauge: (lid: string) => `g:${lid}`,
	structure: (id: number) => `s:${id}`,
	hazard: (id: string) => `h:${id}`,
	ecoli: (id: string) => `e:${id}`
};

// -- data ------------------------------------------------------------------------------------------------

/** The gauges and structures as GeoJSON points (a flooding gauge says so in its label). */
export function pointFeatures(p: Pick<WaterPoints, 'structures' | 'gauges'>): FeatureCollection {
	return {
		type: 'FeatureCollection',
		features: [
			...p.gauges.map((g) => ({
				type: 'Feature' as const,
				id: g.lid,
				geometry: { type: 'Point' as const, coordinates: [g.lng, g.lat] },
				properties: {
					id: pointId.gauge(g.lid),
					kind: 'gauge',
					lid: g.lid,
					name: g.name,
					...(g.flood ? { flood: g.flood, label: `${g.name} · ${FLOOD_WORD[g.flood]}` } : { label: g.name })
				}
			})),
			...p.structures.map((s) => ({
				type: 'Feature' as const,
				id: s.id,
				geometry: { type: 'Point' as const, coordinates: [s.lng, s.lat] },
				properties: {
					id: pointId.structure(s.id),
					kind: s.kind,
					sid: s.id,
					name: s.name ?? STRUCTURE_WORD[s.kind],
					label: s.name ?? STRUCTURE_WORD[s.kind],
					minzoom: s.minzoom
				}
			}))
		]
	};
}

/** The hazards and E. coli sites that have a place, as GeoJSON points. */
export function noticeFeatures(n: { hazards: readonly Hazard[]; ecoli: readonly EcoliSample[] }): FeatureCollection {
	const at = (lng: number | null, lat: number | null) => (lng === null || lat === null ? null : { type: 'Point' as const, coordinates: [lng, lat] });
	return {
		type: 'FeatureCollection',
		features: [
			...n.hazards.flatMap((h) => {
				const geometry = at(h.lng, h.lat);
				return geometry
					? [{ type: 'Feature' as const, geometry, properties: { id: pointId.hazard(h.id), kind: 'hazard', hid: h.id, name: h.name ?? 'River hazard', label: h.name ?? 'River hazard' } }]
					: [];
			}),
			...n.ecoli.flatMap((s) => {
				const geometry = at(s.lng, s.lat);
				return geometry
					? [{ type: 'Feature' as const, geometry, properties: { id: pointId.ecoli(s.id), kind: 'ecoli', eid: s.id, name: s.site ?? s.id, label: `${s.site ?? s.id} · E. coli` } }]
					: [];
			})
		]
	};
}

// -- the layers ----------------------------------------------------------------------------------------------

const textPaint = (flavor: 'valley' | 'clay') => ({ 'text-color': TONES[flavor].label, 'text-halo-color': TONES[flavor].halo, 'text-halo-width': 1.5 });

/**
 * The layers that draw from the landscape file (labels and the picked shape). Added only when the water
 * network is baked. Names are italic: water is told from the roads and places around it by form (K5).
 */
export function bakedLayers(): SlottedLayer[] {
	const named = ['!=', ['coalesce', ['get', 'name'], ''], ''];
	const wide = ['>=', ['coalesce', ['get', 'width_m'], 0], 4];
	const lineLabel = (id: string, minzoom: number, filter: unknown): SlottedLayer => ({
		slot: 'labels',
		layer: {
			id,
			type: 'symbol',
			source: LANDSCAPE_SOURCE,
			'source-layer': REACHES,
			minzoom,
			filter,
			layout: {
				visibility: 'none',
				'symbol-placement': 'line',
				'text-field': ['get', 'name'],
				'text-font': ['Noto Sans Italic'],
				'text-size': ['interpolate', ['linear'], ['zoom'], 11, 11, 16, 13],
				'text-letter-spacing': 0.06,
				'symbol-spacing': 320
			},
			paint: textPaint('valley')
		} as unknown as LayerSpecification
	});
	return [
		{
			slot: 'water',
			layer: {
				id: SELECTED_REACH_LAYER,
				type: 'line',
				source: LANDSCAPE_SOURCE,
				'source-layer': REACHES,
				filter: ['==', ['get', 'id'], -1],
				layout: { visibility: 'none' },
				paint: { 'line-color': TONES.valley.selected, 'line-width': lineWidth({ extra: 2 }) }
			} as unknown as LayerSpecification
		},
		{
			slot: 'water',
			layer: {
				id: SELECTED_BODY_LAYER,
				type: 'line',
				source: LANDSCAPE_SOURCE,
				'source-layer': BODIES,
				filter: ['==', ['get', 'id'], -1],
				layout: { visibility: 'none' },
				paint: { 'line-color': TONES.valley.selected, 'line-width': 3 }
			} as unknown as LayerSpecification
		},
		lineLabel(LABEL_MAIN_LAYER, 11, ['all', named, wide]),
		lineLabel(LABEL_FINE_LAYER, 14, ['all', named, ['!', wide]]),
		{
			slot: 'labels',
			layer: {
				id: LABEL_BODY_LAYER,
				type: 'symbol',
				source: LANDSCAPE_SOURCE,
				'source-layer': BODIES,
				minzoom: 11,
				filter: ['all', named, ['!=', ['get', 'kind'], 'wetland']],
				layout: {
					visibility: 'none',
					'text-field': ['get', 'name'],
					'text-font': ['Noto Sans Italic'],
					'text-size': 12,
					'text-max-width': 6
				},
				paint: textPaint('valley')
			} as unknown as LayerSpecification
		}
	];
}

/** The layer's own points, in the points slot. They start hidden. */
export function pointLayers(): SlottedLayer[] {
	const label = {
		'text-field': ['get', 'label'],
		'text-font': ['Noto Sans Medium'],
		'text-size': TEXT_SIZE,
		'text-anchor': 'top',
		'text-offset': [0, 1.2],
		'text-max-width': 9,
		'text-optional': true
	};
	const paint = { 'text-color': INK, 'text-halo-color': CREAM, 'text-halo-width': 1.5 };
	return [
		// A structure appears from its own first zoom (dams and big gates early, small gates late): three layers
		// by that zoom, since a per-feature zoom filter isn't evaluated by MapLibre at fractional zooms.
		...(
			[
				[STRUCTURE_LAYER, 9, ['<=', ['get', 'minzoom'], 11], 14],
				[STRUCTURE_MID_LAYER, 12, ['all', ['>=', ['get', 'minzoom'], 12], ['<=', ['get', 'minzoom'], 13]], 14],
				[STRUCTURE_FINE_LAYER, 14, ['>=', ['get', 'minzoom'], 14], 14]
			] as const
		).map(
			([id, minzoom, bucket, labelZoom]): SlottedLayer => ({
				slot: 'points',
				layer: {
					id,
					type: 'symbol',
					source: POINTS_SOURCE,
					minzoom,
					filter: ['all', ['!=', ['get', 'kind'], 'gauge'], bucket],
					layout: {
						visibility: 'none',
						'icon-image': IMAGE.structure,
						'icon-size': ['interpolate', ['linear'], ['zoom'], 9, 0.7, 15, 1],
						'icon-allow-overlap': true,
						...label,
						'text-field': ['step', ['zoom'], '', labelZoom, ['get', 'label']]
					},
					paint
				} as unknown as LayerSpecification
			})
		),
		{
			slot: 'points',
			layer: {
				id: GAUGE_LAYER,
				type: 'symbol',
				source: POINTS_SOURCE,
				filter: ['==', ['get', 'kind'], 'gauge'],
				layout: {
					visibility: 'none',
					'icon-image': ['case', ['has', 'flood'], IMAGE.gaugeFlood, IMAGE.gauge],
					'icon-size': ['interpolate', ['linear'], ['zoom'], 8, 0.8, 14, 1],
					'icon-allow-overlap': true,
					...label,
					'text-field': ['step', ['zoom'], '', 10, ['get', 'label']]
				},
				paint
			} as unknown as LayerSpecification
		},
		{
			slot: 'points',
			layer: {
				id: NOTICE_LAYER,
				type: 'symbol',
				source: NOTICES_SOURCE,
				minzoom: 11,
				layout: {
					visibility: 'none',
					'icon-image': ['match', ['get', 'kind'], 'hazard', IMAGE.hazard, IMAGE.ecoli],
					'icon-size': ['interpolate', ['linear'], ['zoom'], 11, 0.8, 15, 1],
					'icon-allow-overlap': true,
					...label,
					'text-field': ['step', ['zoom'], '', 13, ['get', 'label']]
				},
				paint
			} as unknown as LayerSpecification
		}
	];
}

/** The Valley and Clay paints of the layers that follow the Base look (`registerFlavorPaint`). */
export function flavorPaints(): Record<string, { valley: Record<string, unknown>; clay: Record<string, unknown> }> {
	const text = { valley: textPaint('valley'), clay: textPaint('clay') };
	const out: Record<string, { valley: Record<string, unknown>; clay: Record<string, unknown> }> = {
		[SELECTED_REACH_LAYER]: { valley: { 'line-color': TONES.valley.selected }, clay: { 'line-color': TONES.clay.selected } },
		[SELECTED_BODY_LAYER]: { valley: { 'line-color': TONES.valley.selected }, clay: { 'line-color': TONES.clay.selected } }
	};
	for (const id of [LABEL_MAIN_LAYER, LABEL_FINE_LAYER, LABEL_BODY_LAYER]) out[id] = text;
	return out;
}
