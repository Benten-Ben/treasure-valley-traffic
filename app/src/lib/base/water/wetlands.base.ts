import type { BaseContribution, BaseLayer } from '#lib/base/types.js';
import { TONES } from './palette.js';
import { BODIES } from './water.base.js';

/**
 * The National Wetlands Inventory's vegetated wetlands in Water, as tufts (issue #31; plugins/water/README.md,
 * "Wetlands"). A wetland has no fill colour: it is a sparse rim of short dashes, one tuft per stretch of edge.
 *
 * - **Zooms.** Recent mapping draws from z14. The older mapping (the 1981-83 photos and the interim product that
 *   passed the presence check) is the thinned tuft: sparser and finer, from z15 (the bake's `thin` flag).
 * - **Not a legal boundary.** Every wetland card and the legend say so; the 1981 ones also say they were mapped
 *   from 1981 photos. Credit: FWS, National Wetlands Inventory (public domain).
 */

/** The style layer ids (drawn in the Water slot, under the reaches). */
export const WETLAND_TUFT_LAYER = 'water.network.wetland-tufts';
export const WETLAND_THIN_LAYER = 'water.network.wetland-thin-tufts';

/** The credit the wetlands carry (the bake's `nwi` source, public domain). */
export const WETLAND_CREDIT = 'U.S. Fish and Wildlife Service, National Wetlands Inventory (public domain)';

/** The wording every wetland card and the legend share. */
export const NOT_A_BOUNDARY = 'Not a legal (regulatory) wetland boundary.';
export const MAPPED_FROM_1981 = 'Mapped from 1981 photos.';

export interface TuftLook {
	/** The first zoom it draws from. */
	minzoom: number;
	/** Dash and gap in line widths: a short mark, then a gap; the thinned tuft is sparser. */
	dash: readonly number[];
	/** Line width in px. */
	width: number;
}

/** The tuft's look by mapping age: `thin` is the older mapping. Pure, so the pattern choice is unit-tested. */
export function wetlandTuft(thin: boolean): TuftLook {
	return thin ? { minzoom: 15, dash: [0.5, 9], width: 1 } : { minzoom: 14, dash: [0.8, 4], width: 1.2 };
}

/** The lines a wetland's card (or the legend's note) says, in order. */
export function wetlandWords(thin: boolean): string[] {
	return thin ? [NOT_A_BOUNDARY, MAPPED_FROM_1981] : [NOT_A_BOUNDARY];
}

function tuftLayer(id: string, thin: boolean, rank: number): BaseLayer {
	const look = wetlandTuft(thin);
	const paint = (flavor: 'valley' | 'clay') => ({
		'line-color': TONES[flavor].line,
		'line-width': look.width,
		'line-dasharray': [...look.dash]
	});
	return {
		id,
		type: 'line',
		slot: 'water',
		rank,
		sourceLayer: BODIES,
		filter: ['all', ['==', ['get', 'kind'], 'wetland'], thin ? ['to-boolean', ['get', 'thin']] : ['!', ['to-boolean', ['get', 'thin']]]],
		minzoom: look.minzoom,
		valley: paint('valley'),
		clay: paint('clay')
	};
}

/** The two tuft layers, to be listed in the water contribution's layers. */
export const WETLAND_LAYERS: BaseLayer[] = [tuftLayer(WETLAND_TUFT_LAYER, false, 12), tuftLayer(WETLAND_THIN_LAYER, true, 13)];

/**
 * The wetland tufts as a base contribution: every `*.base.ts` default-exports one (registry.ts). It reads the
 * water bodies source-layer and shows with the Water layer, like the water network it sits under.
 */
export const ID_WETLANDS = 'water.wetlands';

const contribution: BaseContribution = {
	id: ID_WETLANDS,
	title: 'Wetlands',
	blurb: 'National Wetlands Inventory wetlands as tufts: not a legal (regulatory) wetland boundary',
	source: { kind: 'landscape', sourceLayers: [BODIES] },
	looks: 'both',
	layers: WETLAND_LAYERS,
	cardsWhen: 'water',
	credit: WETLAND_CREDIT
};

export default contribution;
