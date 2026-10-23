import { describe, expect, it } from 'vitest';
import { contrast } from '#lib/map/color.js';
import { GROUND } from '#lib/map/flavors.js';
import { FENCE_POST, GROUND_BAND } from '#lib/map/materials.js';
import { ESTIMATED, HALO, palette, POST } from './palette.js';

/**
 * The line's halo against the ground band (plan §3.4 K3): the line is the post tone, with a 1 px cream halo each
 * side so it reads over lawn, soil and asphalt alike. Nothing is told by color alone (the legend and card say it in words).
 */
describe('the Fences palette', () => {
	it('uses the shared post tone, not a copy', () => {
		expect(POST).toBe(FENCE_POST);
		expect(palette.id).toBe('fences');
		expect(palette.colors.map((c) => c.name)).toEqual(['fence post', 'halo', 'estimated height']);
	});

	it('keeps the line readable on its halo (4.5:1)', () => {
		expect(contrast(POST, HALO)).toBeGreaterThanOrEqual(4.5);
	});

	// Over a dark ground the halo stands out; over a pale one the line itself does.
	const BAND = [
		['lawn', GROUND_BAND.lawn],
		['asphalt', GROUND_BAND.asphalt],
		['pale lot', GROUND_BAND.paleLot],
		['the Valley ground', GROUND.valley]
	] as const;
	for (const [name, ground] of BAND) {
		it(`stands out from ${name}: the halo or the line reaches 3:1`, () => {
			expect(Math.max(contrast(HALO, ground), contrast(POST, ground))).toBeGreaterThanOrEqual(3);
		});
	}

	it('on bare soil, the weakest ground, the pair still reaches 2.4:1 (the line is 4.5:1 on its halo)', () => {
		expect(Math.max(contrast(HALO, GROUND_BAND.bare), contrast(POST, GROUND_BAND.bare))).toBeGreaterThanOrEqual(2.4);
	});

	it('draws an estimated height paler than a tagged one, still a post-tone mix', () => {
		expect(ESTIMATED).not.toBe(POST);
		expect(contrast(ESTIMATED, HALO)).toBeLessThan(contrast(POST, HALO));
		expect(contrast(ESTIMATED, HALO)).toBeGreaterThan(2);
	});
});
