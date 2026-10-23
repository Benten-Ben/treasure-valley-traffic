import { CREAM, mixOklab } from '#lib/map/color.js';
import { FENCE_POST, MARKINGS, type Palette } from '#lib/map/materials.js';

/**
 * The Fences layer's colors (plan §3.4 K3; docs/13's color budget). One hue: the post tone the shared
 * materials already hold (`FENCE_POST`), the cream the markings use for the line's halo, and the post
 * tone mixed a quarter of the way toward cream for a height we estimated (never told by color alone:
 * the card and legend say it in words).
 */

/** The 2D line and the 3D fence with a height from OpenStreetMap. */
export const POST = FENCE_POST;
/** The halo around the 2D line, 1 px each side: the cream of the road markings. */
export const HALO = MARKINGS.onAsphalt.color;
/** A height estimated by type: the post tone 25% toward cream (plan §3.4 K3). */
export const ESTIMATED = mixOklab(POST, CREAM, 0.25);
/** The share of cream mixed into the post tone for an estimated height. */
export const ESTIMATED_SHARE = 0.25;

export const palette: Palette = {
	id: 'fences',
	colors: [
		{ name: 'fence post', valley: POST, clay: POST, use: 'the 2D line, the post ticks, and a 3D fence or wall whose height is in OpenStreetMap' },
		{ name: 'halo', valley: HALO, clay: HALO, use: 'the 1 px halo around the 2D line' },
		{ name: 'estimated height', valley: ESTIMATED, clay: ESTIMATED, use: 'a 3D fence or wall whose height we estimated from its type' }
	]
};

export default palette;
