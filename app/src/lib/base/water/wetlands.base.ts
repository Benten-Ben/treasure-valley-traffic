import type { FlavorName } from '#lib/map/flavors.js';
import type { BaseContribution, BaseLayer } from '#lib/base/types.js';
import { TONES } from './palette.js';
import { BODIES } from './water.base.js';

/**
 * The National Wetlands Inventory's vegetated wetlands in Water, as tufts (issue #31; plugins/water/README.md,
 * "Wetlands"). A wetland has no fill colour, no outline and no dashed rim: it is a fill *pattern*, a small tuft glyph
 * (a few short upright strokes) repeated across the polygon, the way the burn scars' stipple is
 * (`#lib/base/hazards/burn-scars.base.ts`): each pattern image is made at run time (self-hosted, no file), one
 * per look, in the palette's wetland tone for that look.
 *
 * - **Zooms.** Recent mapping draws from z14 with the dense pattern. The older mapping (the 1981-83 photos and the
 *   interim product that passed the presence check; the bake's `thin` flag) draws from z15 with the same glyph on a
 *   sparser grid. The form differs by density and zoom, so it never rests on colour alone.
 * - **Not a legal boundary.** Every wetland card and the legend say so; the 1981 ones also say they were mapped
 *   from 1981 photos. Credit: FWS, National Wetlands Inventory (public domain).
 * - **Clicks.** A fill layer is hit by its whole polygon, not by the pattern's strokes, so the Water layer picks a
 *   wetland anywhere inside it (`WETLAND_LAYER_IDS`).
 */

/** The style layer ids (drawn in the Water slot, over the bodies' fill and under the reaches). */
export const WETLAND_TUFT_LAYER = 'water.wetlands.tufts';
export const WETLAND_THIN_LAYER = 'water.wetlands.thin-tufts';
/** Every layer a click on a wetland can hit. */
export const WETLAND_LAYER_IDS = [WETLAND_TUFT_LAYER, WETLAND_THIN_LAYER] as const;

/** The credit the wetlands carry (the bake's `nwi` source, public domain). */
export const WETLAND_CREDIT = 'U.S. Fish and Wildlife Service, National Wetlands Inventory (public domain)';

/** The wording every wetland card and the legend share. */
export const NOT_A_BOUNDARY = 'Not a legal (regulatory) wetland boundary.';
export const MAPPED_FROM_1981 = 'Mapped from 1981 photos.';

export interface TuftLook {
	/** The first zoom it draws from. */
	minzoom: number;
	/** The pattern's tile, px: one tuft per tile, so a bigger tile is a sparser grid. */
	cell: number;
}

/** The tuft's look by mapping age: `thin` is the older mapping. Pure, so the pattern choice is unit-tested. */
export function wetlandTuft(thin: boolean): TuftLook {
	return thin ? { minzoom: 15, cell: 32 } : { minzoom: 14, cell: 16 };
}

/**
 * The glyph: three short upright strokes, each 2 px wide (a 1 px stroke is smeared pale where the map's tiles land
 * between screen pixels; two keeps a solid core), 8 px wide and 8 high, as [x, y] from its top left. The middle
 * stroke is the tallest.
 */
const GLYPH: readonly (readonly [number, number])[] = (() => {
	const out: [number, number][] = [];
	const stroke = (x: number, top: number) => {
		for (let y = top; y < 8; y++) out.push([x, y], [x + 1, y]);
	};
	stroke(0, 3);
	stroke(3, 0);
	stroke(6, 3);
	return out;
})();
const GLYPH_W = 8;
const GLYPH_H = 8;

/** The pixels of one pattern tile that the glyph covers, centred in the tile (the legend draws the same ones). */
export function tuftPixels(thin: boolean): [number, number][] {
	const { cell } = wetlandTuft(thin);
	const ox = Math.floor((cell - GLYPH_W) / 2);
	const oy = Math.floor((cell - GLYPH_H) / 2);
	return GLYPH.map(([x, y]) => [x + ox, y + oy]);
}

/** The pattern image's id on the map: one per mapping age and look. */
export const tuftImageId = (thin: boolean, flavor: FlavorName): string => `water-wetland-tuft${thin ? '-thin' : ''}-${flavor}`;

/** The pattern image, RGBA, transparent but for the glyph in the look's wetland tone. */
export function tuftImage(thin: boolean, flavor: FlavorName): { width: number; height: number; data: Uint8Array } {
	const { cell } = wetlandTuft(thin);
	const data = new Uint8Array(cell * cell * 4);
	const hex = TONES[flavor].wetland;
	const rgb = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
	for (const [x, y] of tuftPixels(thin)) data.set([rgb[0], rgb[1], rgb[2], 255], (y * cell + x) * 4);
	return { width: cell, height: cell, data };
}

/** The lines a wetland's card (or the legend's note) says, in order. */
export function wetlandWords(thin: boolean): string[] {
	return thin ? [NOT_A_BOUNDARY, MAPPED_FROM_1981] : [NOT_A_BOUNDARY];
}

function tuftLayer(id: string, thin: boolean, rank: number): BaseLayer {
	const look = wetlandTuft(thin);
	const paint = (flavor: FlavorName) => ({ 'fill-pattern': tuftImageId(thin, flavor), 'fill-opacity': 1 });
	return {
		id,
		type: 'fill',
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

/** Every pattern image the layers name (both ages, both looks). */
export const TUFT_IMAGES = ([false, true] as const).flatMap((thin) => (['valley', 'clay'] as const).map((flavor) => ({ id: tuftImageId(thin, flavor), thin, flavor })));

/** Add the pattern images to the map; returns the cleanup that takes them away again. */
export function addTuftImages(map: {
	hasImage(id: string): boolean;
	addImage(id: string, image: { width: number; height: number; data: Uint8Array }): unknown;
	removeImage(id: string): unknown;
}): () => void {
	const added: string[] = [];
	for (const { id, thin, flavor } of TUFT_IMAGES) {
		try {
			if (!map.hasImage(id)) {
				map.addImage(id, tuftImage(thin, flavor));
				added.push(id);
			}
		} catch {
			// The map may be torn down already; the tufts then simply aren't drawn.
		}
	}
	return () => {
		for (const id of added) {
			try {
				if (map.hasImage(id)) map.removeImage(id);
			} catch {
				// The map may be torn down already; there is then no image left to remove.
			}
		}
	};
}

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
	credit: WETLAND_CREDIT,
	live: ({ map }) => addTuftImages(map)
};

export default contribution;
