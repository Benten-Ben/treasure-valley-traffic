import { MARKINGS, type Palette } from '#lib/map/materials.js';

/**
 * The Lanes layer's colors (plan v3 §3.4, §3.6; docs/13's color budget). It draws no color of its own: the ▲ marks
 * and the turn arrows are the road markings' cream inside an ink edge, told by shape and never by color. The ink is
 * the shared `INK` token (the roads palette lists it, for the Clay markings and the deck casings), so it isn't listed
 * again here; `palette.test.ts` checks that it reaches 3:1 against the four extremes of the painted ground the marks
 * sit over (Lanes keeps Valley in Auto). The markings the base contributions draw are `#lib/base/roads/palette.ts`'s.
 */
export const MARK_FILL = MARKINGS.onAsphalt.color;

export const palette: Palette = {
	id: 'lanes',
	colors: [{ name: 'mark fill', valley: MARK_FILL, clay: MARK_FILL, use: 'fill: the inside of the ▲ marks and the turn arrows, in the markings cream' }]
};

export default palette;
