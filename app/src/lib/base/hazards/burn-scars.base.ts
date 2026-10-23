import type { BaseContribution } from '#lib/base/types.js';

/**
 * Burn scars on the Valley ground (landscape sprint plan C15 and §3.4 K10; package P13): fires after the
 * ground's photo, fading over three growing seasons. A neutral char with a stipple, never red or orange,
 * drawn on the painted ground (anchor:ground) from the toggled layer's tiles (`#lib/server/hazards/tiles.ts`).
 * Not clickable in v1; hidden under Aerial and in Clay.
 */

const CHAR = '#5E5750';
/** The stipple's image, generated at run time (self-hosted, no file): a 8×8 tile with two dots. */
const STIPPLE = 'hazards-burn-stipple';

/** Four-by-four pixel dots on an 8×8 transparent tile, in the char colour. */
function stippleImage(): { width: number; height: number; data: Uint8Array } {
	const width = 8;
	const height = 8;
	const data = new Uint8Array(width * height * 4);
	const [r, g, b] = [0x5e, 0x57, 0x50];
	for (const [x, y] of [
		[1, 1],
		[5, 5]
	]) {
		const i = (y * width + x) * 4;
		data.set([r, g, b, 255], i);
	}
	return { width, height, data };
}

/** The fade is data: `fade` 1 → 2/3 → 1/3 → 0 (the view's column). */
const FADE = ['to-number', ['get', 'fade']] as const;

const contribution: BaseContribution = {
	id: 'hazards.burn_scars',
	title: 'Burn scars',
	blurb: 'Burn scars: fires since July 2025, fading over three growing seasons (NIFC WFIGS)',
	source: { kind: 'tiles', plugin: 'hazards', layer: 'burn_scars', minzoom: 8, maxzoom: 14 },
	looks: 'valley',
	layers: [
		{
			id: 'hazards.burn_scars.char',
			type: 'fill',
			slot: 'ground',
			rank: 20,
			sourceLayer: 'scars',
			aerial: 'hide',
			valley: { 'fill-color': CHAR, 'fill-opacity': ['*', 0.4, FADE] }
		},
		{
			id: 'hazards.burn_scars.stipple',
			type: 'fill',
			slot: 'ground',
			rank: 21,
			sourceLayer: 'scars',
			aerial: 'hide',
			valley: { 'fill-pattern': STIPPLE, 'fill-opacity': ['*', 0.6, FADE] }
		}
	],
	credit: 'National Interagency Fire Center (WFIGS), from IRWIN',
	live({ map }) {
		try {
			if (!map.hasImage(STIPPLE)) map.addImage(STIPPLE, stippleImage());
		} catch {
			// The map may be torn down already; the stipple then simply isn't drawn.
		}
		return () => {};
	}
};

export default contribution;
export { CHAR, STIPPLE, stippleImage };
