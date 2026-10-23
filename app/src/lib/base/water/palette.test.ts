import { describe, expect, it } from 'vitest';
import { GROUND } from '#lib/map/flavors.js';
import { contrast, DASH, DASHED_MAX_PX, lineWidth, metresPerPixel, MIN_PX, NHD_FINER, TONES, trueWidth } from './palette.js';

describe('the water palette', () => {
	it('uses the basemap’s own water for the fills (docs/13 §13.4)', () => {
		expect(TONES.valley.fill).toBe('#7cc4e4');
		expect(TONES.clay.fill).toBe('#c9dce3');
	});

	it('keeps lines readable on the ground: at least 2:1 in either look; NHD-only lines lighter but not lost', () => {
		for (const flavor of ['valley', 'clay'] as const) {
			const t = TONES[flavor];
			expect(contrast(t.line, GROUND[flavor]), `${flavor} line`).toBeGreaterThanOrEqual(2);
			expect(contrast(t.lineNhd, GROUND[flavor]), `${flavor} NHD-only line`).toBeGreaterThanOrEqual(1.4);
			// Lighter means less contrast with the ground.
			expect(contrast(t.lineNhd, GROUND[flavor])).toBeLessThan(contrast(t.line, GROUND[flavor]));
			expect(contrast(t.fillNhd, GROUND[flavor])).toBeLessThan(contrast(t.fill, GROUND[flavor]));
			// Names are text: 4.5:1 on the ground, and the selection is darker still.
			expect(contrast(t.label, GROUND[flavor]), `${flavor} names`).toBeGreaterThanOrEqual(4.5);
			expect(contrast(t.selected, GROUND[flavor])).toBeGreaterThan(contrast(t.label, GROUND[flavor]));
		}
	});

	it('is never red or green (the colour budget): every tone is in the blue range', () => {
		for (const flavor of ['valley', 'clay'] as const)
			for (const [name, hex] of Object.entries(TONES[flavor])) {
				if (name === 'halo') continue;
				const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
				expect(b, `${flavor} ${name}`).toBeGreaterThan(r);
				expect(b, `${flavor} ${name}`).toBeGreaterThanOrEqual(g);
			}
	});

	it('works out metres per pixel as the ground does (1.73 m a pixel at z15)', () => {
		expect(metresPerPixel(15)).toBeCloseTo(1.73, 1);
		expect(metresPerPixel(16)).toBeCloseTo(metresPerPixel(15) / 2, 6);
	});

	it('gives each form its own dash, and keeps them apart', () => {
		const all = Object.values(DASH).map((d) => d.join());
		expect(new Set(all).size).toBe(all.length); // intermittent, NHD, NHD-intermittent and piped all differ
		expect(DASH.piped[0]).toBeLessThan(DASH.piped[1]);
		expect(DASHED_MAX_PX).toBeGreaterThanOrEqual(2);
		expect(NHD_FINER).toBeLessThan(1);
	});

	it('builds one zoom interpolation over width_m: sqrt-ish below z15, true width from z15', () => {
		const e = lineWidth() as unknown[];
		expect(e.slice(0, 3)).toEqual(['interpolate', ['exponential', 2], ['zoom']]);
		const zooms = e.filter((_, i) => i >= 3 && (i - 3) % 2 === 0);
		expect(zooms).toEqual([8, 12, 14, 15, 22]);
		expect(trueWidth(8, 17)).toBeCloseTo(8 / metresPerPixel(17), 6);
		expect(trueWidth(0.1, 15)).toBe(MIN_PX);
	});
});
