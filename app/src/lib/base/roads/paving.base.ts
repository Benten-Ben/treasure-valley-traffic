import { ASPHALT, CLAY_KERB, CONCRETE, CURB, EDGE, MARKINGS, UNPAVED } from '#lib/map/materials.js';
import type { BaseContribution } from '#lib/base/types.js';

/**
 * The paving base contribution (landscape sprint plan §4.2 P8-app, §3.3): parking lots, driveways,
 * service ways, sidewalks and stall lines from OpenStreetMap, drawn under the road surfaces in the
 * base. Its feature cards belong to the Lanes layer (`cardsWhen`), which asks `/api/roads/paving`.
 *
 * Source layers come from the landscape bake (`roads.paving_lots`, `roads.paving_ways`,
 * `roads.paving_stalls`). Zooms and paints are as the plan has them: lots as a fill from z14 with no
 * outline until z15; ways fade in at their estimated width over z15.5-16; a hairline curb edge from
 * z16.5 (form, not colour); stall lines from z17.5. Gravel and dirt use their unpaved tones. Under
 * Aerial the photo already shows the paving, so the layers hide.
 *
 * It suppresses the basemap's `service` and `paths` groups from z15.5, where its own ways draw.
 */

/** Fill colour by the bake's `material` property; gravel and dirt are tints over the ground. */
const FILL_MATCH: unknown[] = [
	'match',
	['get', 'material'],
	'concrete', CONCRETE.valley,
	'gravel', '#FFFBF4',
	'dirt', '#826644',
	ASPHALT.valley
];
const FILL_OPACITY: unknown[] = [
	'match',
	['get', 'material'],
	'gravel', UNPAVED.gravel.opacity,
	'dirt', UNPAVED.dirt.opacity,
	1
];
const FILL_MATCH_CLAY: unknown[] = ['match', ['get', 'material'], 'concrete', CONCRETE.clay, ASPHALT.clay];

const paving: BaseContribution = {
	id: 'roads.paving',
	title: 'Paving',
	blurb: 'parking lots, driveways, service roads, sidewalks (OpenStreetMap; widths estimated)',
	source: {
		kind: 'landscape',
		sourceLayers: ['roads.paving_lots', 'roads.paving_ways', 'roads.paving_stalls']
	},
	looks: 'both',
	cardsWhen: 'lanes',
	credit: '© OpenStreetMap contributors',
	suppresses: { groups: ['service', 'paths'], fromZoom: 15.5 },
	layers: [
		{
			id: 'roads.paving_lots',
			type: 'fill',
			slot: 'surfaces',
			rank: 10,
			sourceLayer: 'roads.paving_lots',
			minzoom: 14,
			valley: {
				'fill-color': FILL_MATCH,
				'fill-opacity': FILL_OPACITY,
				'fill-outline-color': ['interpolate', ['linear'], ['zoom'], 14, 'rgba(0,0,0,0)', 15, EDGE]
			},
			clay: { 'fill-color': FILL_MATCH_CLAY, 'fill-opacity': 1, 'fill-outline-color': CLAY_KERB },
			aerial: 'hide'
		},
		{
			id: 'roads.paving_ways',
			type: 'line',
			slot: 'surfaces',
			rank: 10,
			sourceLayer: 'roads.paving_ways',
			minzoom: 15.5,
			valley: {
				// Width in metres (the bake's `w`) at about 2.7 px per metre at z16, doubling each zoom.
				'line-color': FILL_MATCH,
				'line-opacity': ['interpolate', ['linear'], ['zoom'], 15.5, 0, 16, 1],
				'line-width': ['interpolate', ['linear'], ['zoom'], 15.5, 0, 16, ['*', ['get', 'w'], 2.7]]
			},
			clay: { 'line-color': FILL_MATCH_CLAY, 'line-width': ['interpolate', ['linear'], ['zoom'], 15.5, 0, 16, ['*', ['get', 'w'], 2.7]] },
			aerial: 'hide'
		},
		{
			id: 'roads.paving_edges',
			type: 'line',
			slot: 'surfaces',
			rank: 11,
			sourceLayer: 'roads.paving_ways',
			minzoom: 16.5,
			valley: { 'line-color': CURB, 'line-width': 0.6 },
			clay: { 'line-color': CLAY_KERB, 'line-width': 0.6 },
			aerial: 'hide'
		},
		{
			id: 'roads.paving_stalls',
			type: 'line',
			slot: 'surfaces',
			rank: 12,
			sourceLayer: 'roads.paving_stalls',
			minzoom: 17.5,
			valley: { 'line-color': MARKINGS.onConcrete.color, 'line-opacity': MARKINGS.onConcrete.opacity, 'line-width': 0.8 },
			clay: { 'line-color': MARKINGS.clay.color, 'line-opacity': MARKINGS.clay.opacity, 'line-width': 0.8 },
			aerial: 'hide'
		}
	]
};

export default paving;
