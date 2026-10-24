import type { FlavorName } from '#lib/map/flavors.js';
import type { BaseContribution, BaseLayer } from '#lib/base/types.js';
import { DASH, DASHED_MAX_PX, FILL_OPACITY, lineWidth, NHD_FINER, PIPED_FROM_ZOOM, TONES } from './palette.js';
import { seasonLive, seasonPaint } from './season.js';

/**
 * The baked water network as a base contribution (landscape sprint plan v3 §4.2 P4-app, §3.1 C13, §3.2 b5,
 * §3.4 K5, §3.5). It reads two source-layers of the shared landscape file, `water.bodies` and `water.reaches`
 * (plugins/water/README.md, "Exports and the base bake"), and draws them in `anchor:water`, bodies first and
 * the reaches over them, in both looks. Once built it hides Protomaps' water (`suppresses` applies only to a
 * contribution that is built: a bake with no water, or one listing a water layer under `empty`, leaves the
 * basemap's water alone).
 *
 * - **Zooms.** The bake already holds each feature from its own first zoom (main canals z10, named canals z11,
 *   laterals and drains z12, ditches z13, piped water z16), so the style doesn't repeat them; it adds the true-
 *   width ribbons from z15 (`lineWidth`) and the dots of piped water from z16.
 * - **Form, not colour alone** (K5, K8): kinds differ by width; intermittent lines are dashed; lines from the
 *   federal map alone (`nhd_only`) are finer and lighter with their own dash; piped water is dotted. **Never a
 *   casing:** water sits under the streets, so a casing would only dim their shades.
 * - **The canal season** (P5-app, `season.ts`). On the solid reach layer alone, the width and gap read feature-state
 *   `season`: an off canal is hollow inside its own line, at its true footprint (two thin edges in the reach's own
 *   tone, so no casing and no second line); an unknown one is a thin centre line. The `live` hook sets the state
 *   from `/api/water/season`. The dashed layers keep their dashes, so they have no season cue.
 * - **Wetlands** are not drawn here: neither the fill nor the intermittent rim takes them (`notWetland`). They are
 *   tufts, a fill pattern of their own (`wetlands.base.ts`).
 * - **Cards.** `cardsWhen: 'water'`: the Water layer makes these layers clickable while it's on.
 * - **Known limit (box edge).** The bake is clipped to the water plugin's box (plugins/water/ingest/build.py, `BOX`),
 *   but the map can pan 0.15 degrees past the manifest's bounds, and Protomaps' water group is hidden everywhere once
 *   this is built. In that padded ring outside the box the water draws as dry land. Hiding Protomaps' water only
 *   inside the box needs a clipped suppression in the map kit, or a wider box in the bake (a data change): the owner's
 *   call, recorded on the pull request.
 * - Italic names and the flow marks are symbols, so they belong to the Water layer (in `labels`), never here
 *   below `anchor:routes`.
 */

export const ID = 'water.network';
/** The two source-layers of the landscape file. */
export const BODIES = 'water.bodies';
export const REACHES = 'water.reaches';

/** Style layer ids. */
export const BODIES_LAYER = `${ID}.bodies`;
export const BODIES_RIM_LAYER = `${ID}.bodies-intermittent`;
export const REACH_SOLID_LAYER = `${ID}.reaches`;
export const REACH_INTERMITTENT_LAYER = `${ID}.reaches-intermittent`;
export const REACH_NHD_LAYER = `${ID}.reaches-nhd`;
export const REACH_NHD_INTERMITTENT_LAYER = `${ID}.reaches-nhd-intermittent`;
export const REACH_PIPED_LAYER = `${ID}.reaches-piped`;

/** The line layers of the reaches, in drawing order. */
export const REACH_LAYERS = [REACH_SOLID_LAYER, REACH_INTERMITTENT_LAYER, REACH_NHD_LAYER, REACH_NHD_INTERMITTENT_LAYER, REACH_PIPED_LAYER] as const;
/** Every layer a click can pick (the Water layer registers them). */
export const PICKABLE_LAYERS = [BODIES_LAYER, ...REACH_LAYERS] as const;

const flag = (field: string) => ['to-boolean', ['get', field]];
const no = (field: string) => ['!', flag(field)];
/** Wetlands have no fill and no rim here: they are tufts (`wetlands.base.ts`, a fill pattern of their own). */
const notWetland = ['!=', ['get', 'kind'], 'wetland'];

function bodyPaint(flavor: FlavorName) {
	const t = TONES[flavor];
	return {
		'fill-color': ['case', flag('nhd_only'), t.fillNhd, t.fill],
		'fill-opacity': ['case', flag('intermittent'), FILL_OPACITY.intermittent, FILL_OPACITY.solid]
	};
}

interface LineLook {
	/** From the federal map alone: finer and lighter. */
	nhd?: boolean;
	dash?: readonly number[];
	/** Dots need a floor under their width. */
	piped?: boolean;
	/** The solid layer's width and gap read the canal season (feature-state). */
	season?: boolean;
}

function linePaint(flavor: FlavorName, look: LineLook) {
	const t = TONES[flavor];
	return {
		'line-color': look.nhd ? t.lineNhd : t.line,
		...(look.season
			? seasonPaint()
			: {
					'line-width': lineWidth({
						scale: look.nhd ? NHD_FINER : 1,
						...(look.dash ? { cap: DASHED_MAX_PX } : {}),
						...(look.piped ? { floor: 2 } : {})
					})
				}),
		...(look.dash ? { 'line-dasharray': [...look.dash] } : {})
	};
}

function reach(id: string, rank: number, filter: unknown, look: LineLook, minzoom?: number): BaseLayer {
	return {
		id,
		type: 'line',
		slot: 'water',
		rank,
		sourceLayer: REACHES,
		filter,
		...(minzoom !== undefined ? { minzoom } : {}),
		valley: linePaint('valley', look),
		clay: linePaint('clay', look)
	};
}

const layers: BaseLayer[] = [
	{
		id: BODIES_LAYER,
		type: 'fill',
		slot: 'water',
		rank: 10,
		sourceLayer: BODIES,
		filter: notWetland,
		valley: bodyPaint('valley'),
		clay: bodyPaint('clay')
	},
	{
		// An intermittent area keeps a dashed rim, since its form says it dries up. It is the area's only edge,
		// drawn once, never a casing under a line.
		id: BODIES_RIM_LAYER,
		type: 'line',
		slot: 'water',
		rank: 11,
		sourceLayer: BODIES,
		filter: ['all', flag('intermittent'), notWetland],
		minzoom: 11,
		valley: { 'line-color': TONES.valley.edge, 'line-width': 1.2, 'line-dasharray': [...DASH.intermittent] },
		clay: { 'line-color': TONES.clay.edge, 'line-width': 1.2, 'line-dasharray': [...DASH.intermittent] }
	},
	reach(REACH_SOLID_LAYER, 20, ['all', no('piped'), no('nhd_only'), no('intermittent')], { season: true }),
	reach(REACH_INTERMITTENT_LAYER, 21, ['all', no('piped'), no('nhd_only'), flag('intermittent')], { dash: DASH.intermittent }),
	reach(REACH_NHD_LAYER, 22, ['all', no('piped'), flag('nhd_only'), no('intermittent')], { nhd: true, dash: DASH.nhd }),
	reach(REACH_NHD_INTERMITTENT_LAYER, 23, ['all', no('piped'), flag('nhd_only'), flag('intermittent')], { nhd: true, dash: DASH.nhdIntermittent }),
	reach(REACH_PIPED_LAYER, 24, flag('piped'), { dash: DASH.piped, piped: true }, PIPED_FROM_ZOOM)
];

const contribution: BaseContribution = {
	id: ID,
	title: 'Water network',
	blurb: "Rivers, creeks, canals, laterals, ditches and ponds: OpenStreetMap's lines with NHD's facts, replacing the basemap's water",
	source: { kind: 'landscape', sourceLayers: [BODIES, REACHES] },
	looks: 'both',
	layers,
	suppresses: { groups: ['water'] },
	cardsWhen: 'water',
	// The canal season (feature-state, drawn from the API) adds its own credits to the map's attribution while it
	// draws (`seasonLive`): NWPS's gauges, the districts' dates, IDWR's season of use.
	credit: '© OpenStreetMap contributors · USGS National Hydrography Dataset',
	live: seasonLive
};

export default contribution;
