import type { Palette } from '#lib/base/types.js';
import { CREAM, UMBER, UMBER_TEXT } from './trails.js';

/**
 * The colors the Trails layer uses (S3b's color-budget test finds this file by glob): one trail umber for every
 * line, a cream halo under it (never an ink casing, K7), and a darker umber for the names. The status is a
 * dash and an icon, never a color; the icons' ink and cream are the shared ones.
 */
export const palette: Palette = {
	id: 'trails',
	colors: [
		{ name: 'trail umber', valley: UMBER, use: 'every trail line, in both looks' },
		{ name: 'trail halo', valley: CREAM, use: 'a cream halo under the lines, over the ground band' },
		{ name: 'trail names', valley: UMBER_TEXT, use: 'names along trails and routes, on a cream halo' }
	]
};

export default palette;
