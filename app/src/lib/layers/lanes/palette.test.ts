import { describe, expect, it } from 'vitest';
import { contrast } from '#lib/map/color.js';
import { GROUND_BAND, INK } from '#lib/map/materials.js';
import { MARK_FILL, palette } from './palette.js';

describe('the Lanes colors', () => {
	it('are the markings cream only: the ink edge is the shared ink, told from the ground by 3:1 at every extreme of the band', () => {
		expect(palette.colors.map((c) => c.valley)).toEqual([MARK_FILL]);
		for (const [band, color] of Object.entries(GROUND_BAND)) expect(contrast(INK, color), `ink on ${band}`).toBeGreaterThanOrEqual(3);
	});
});
