import { describe, expect, it } from 'vitest';
import { oneWayText, SPEED_BINS, speedColor } from './streets.js';

describe('streets', () => {
	it('bins posted speeds into the ramp, light to dark', () => {
		expect(speedColor(20)).toBe(SPEED_BINS[0].color);
		expect(speedColor(null)).toBe(SPEED_BINS[0].color);
		expect(speedColor(30)).toBe(SPEED_BINS[1].color);
		expect(speedColor(35)).toBe(SPEED_BINS[2].color);
		expect(speedColor(50)).toBe(SPEED_BINS[3].color);
		expect(speedColor(75)).toBe(SPEED_BINS[4].color);
	});

	it('describes direction in words', () => {
		expect(oneWayText({ one_way: 'both' })).toBe('Two-way');
		expect(oneWayText({ one_way: 'backward' })).toMatch(/One-way/);
	});
});
