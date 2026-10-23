import { describe, expect, it } from 'vitest';
import { CLAY_SURFACE, contrast, deltaE, oklch } from '#lib/map/color.js';
import { ROUTES_FOR_TEST } from './palette.test-util.js';
import palette, { gaps, HALO, LABEL, onClay, OUTLINE, PATTERN_INK, STEPS, SURVEY_LINE } from './palette.js';

describe('the Soils palette', () => {
	it('is a hue-free wash: five steps, every one a true gray, palest first', () => {
		expect(STEPS).toHaveLength(5);
		for (const c of STEPS) {
			expect(oklch(c).C, c).toBeLessThan(0.005); // no hue
		}
		const lightness = STEPS.map((c) => oklch(c).L);
		expect([...lightness].sort((a, b) => b - a)).toEqual(lightness);
		for (const c of [PATTERN_INK, OUTLINE, SURVEY_LINE]) expect(oklch(c).C, c).toBeLessThan(0.005);
	});

	it('keeps neighbouring steps apart on Clay, at the wash\'s opacity (at least ΔE 6), and the palest apart from the surface (ΔE 4: an unrated unit has no fill)', () => {
		const g = gaps();
		for (const d of g.between) expect(d).toBeGreaterThanOrEqual(6);
		expect(g.fromSurface).toBeGreaterThanOrEqual(4);
		expect(onClay(4)).not.toBe(onClay(3));
	});

	it('keeps every colour at least ΔE 10 from the route colours (the colour budget), the wash too', () => {
		for (const c of [...STEPS, PATTERN_INK, OUTLINE, SURVEY_LINE]) for (const r of ROUTES_FOR_TEST) expect(deltaE(c, r), `${c} against ${r}`).toBeGreaterThanOrEqual(10);
	});

	it('reads on the ground: outlines, patterns and text against the palest step and Clay', () => {
		for (const bg of [CLAY_SURFACE, onClay(0)]) {
			expect(contrast(PATTERN_INK, bg)).toBeGreaterThanOrEqual(3);
			expect(contrast(LABEL, bg)).toBeGreaterThanOrEqual(4.5);
		}
		expect(contrast(HALO, LABEL)).toBeGreaterThanOrEqual(4.5);
	});

	it('exports a Palette for S3b\'s colour budget: id soils, every colour with a known use', () => {
		expect(palette.id).toBe('soils');
		expect(palette.colors.length).toBeGreaterThanOrEqual(STEPS.length);
		for (const c of palette.colors) expect(c.use, c.name).toMatch(/^(fill|line|surface|label|wash|indicator)/i);
		expect(palette.colors.filter((c) => c.use === 'wash').map((c) => c.valley)).toEqual([...STEPS]);
	});
});
