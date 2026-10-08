import { describe, expect, it } from 'vitest';
import { overviewBounds, VALLEY } from './keymap.js';

describe('Overview frames the populated valley, not the tiles', () => {
	it('the valley box, Caldwell to east Boise and Kuna to Eagle', () => {
		expect(overviewBounds()).toEqual([
			[VALLEY[0], VALLEY[1]],
			[VALLEY[2], VALLEY[3]]
		]);
		// The manifest's study box holds it whole: the valley, not the desert south of it.
		expect(overviewBounds([-117.05, 43.0, -115.95, 43.85])).toEqual(overviewBounds());
	});

	it('stays within smaller tiles, and ignores tiles elsewhere', () => {
		expect(overviewBounds([-116.3, 43.5, -116.0, 43.7])).toEqual([
			[-116.3, 43.5],
			[VALLEY[2], 43.7]
		]);
		expect(overviewBounds([-100, 40, -99, 41])).toEqual(overviewBounds());
	});
});
