import { ASPHALT, CONCRETE, CURB } from '#lib/map/materials.js';
import type { BaseContribution, BaseLayer } from '../types.js';
import { metresPerPx, PAVED_FROM_ZOOM, PAVED_ID, PAVED_LAYER, PAVED_RANK, PAVED_SOURCE_LAYERS } from './paved.js';

/**
 * Paved paths in the base (landscape sprint, package P6-app; plan C9, §3.3, §3.5): OpenStreetMap's paved
 * footways, cycleways and paths (`trails.paved_paths`, as lines at their width) and paved pedestrian areas
 * (`trails.paved_areas`), baked into the landscape file by `ingest trails-export` from z15 and shown from
 * z15.5, in `anchor:surfaces` at rank 15 (over the baked paving, under the road surfaces). Both looks
 * (Valley and Clay), in the materials' tones: asphalt, concrete, and concrete for paving stones and for a
 * paving the tag doesn't name. Hidden under Aerial, like the other surfaces.
 *
 * Only paved ones are here (plan C9: unpaved paths are never in the base; the Trails layer draws them). The
 * City's trail attributes stay out of the base (C17). They open a card only while the Trails layer is on
 * (`cardsWhen`; the layer's module makes these style layers clickable).
 */

/** The material's tone: asphalt for asphalt, concrete for concrete, the curb tone for paving stones (Valley), concrete for the rest. */
const tone = (key: 'valley' | 'clay') => [
	'match',
	['get', 'material'],
	'asphalt',
	ASPHALT[key],
	'concrete',
	CONCRETE[key],
	'paving_stones',
	key === 'valley' ? CURB : CONCRETE.clay,
	CONCRETE[key]
];

/** A tread's width in px: its width in metres (`w`, tagged or estimated by the export) at the zoom, never under a floor. */
const treadWidth = [
	'interpolate',
	['exponential', 2],
	['zoom'],
	PAVED_FROM_ZOOM,
	['max', 1.6, ['/', ['coalesce', ['get', 'w'], 1.8], metresPerPx(PAVED_FROM_ZOOM)]],
	18,
	['max', 3, ['/', ['coalesce', ['get', 'w'], 1.8], metresPerPx(18)]]
];

const layers: BaseLayer[] = [
	{
		id: PAVED_LAYER.areas,
		type: 'fill',
		slot: 'surfaces',
		rank: PAVED_RANK,
		sourceLayer: PAVED_SOURCE_LAYERS.areas,
		minzoom: PAVED_FROM_ZOOM,
		valley: { 'fill-color': tone('valley'), 'fill-opacity': 1 },
		clay: { 'fill-color': tone('clay'), 'fill-opacity': 1 },
		aerial: 'hide'
	},
	{
		id: PAVED_LAYER.treads,
		type: 'line',
		slot: 'surfaces',
		rank: PAVED_RANK,
		sourceLayer: PAVED_SOURCE_LAYERS.paths,
		minzoom: PAVED_FROM_ZOOM,
		valley: { 'line-color': tone('valley'), 'line-width': treadWidth, 'line-opacity': 1 },
		clay: { 'line-color': tone('clay'), 'line-width': treadWidth, 'line-opacity': 1 },
		aerial: 'hide'
	}
];

const contribution: BaseContribution = {
	id: PAVED_ID,
	title: 'Paved paths',
	blurb: 'Paved footways, bike paths and plazas, drawn at their width from z15.5',
	source: { kind: 'landscape', sourceLayers: [PAVED_SOURCE_LAYERS.paths, PAVED_SOURCE_LAYERS.areas] },
	looks: 'both',
	layers,
	cardsWhen: 'trails',
	credit: '© OpenStreetMap contributors'
};

export default contribution;
