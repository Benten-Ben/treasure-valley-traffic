import { describe, expect, it } from 'vitest';
import { BUDGET, FIELDS_BANDS, FIRST_TOGGLE, overBudget, YEAR_CUT_MS, YEAR_CUTS } from './budget.js';

describe('the Crop fields tile budget (owner, Oct 22: #32 Q1)', () => {
	it('is the busiest tile of a band at most 150 KB gzip and the first toggle at most 1 MB', () => {
		expect(BUDGET).toEqual({ busiestTileBytes: 150_000, firstToggleBytes: 1_000_000 });
	});

	it('holds for the measured tiles: every band, every earlier year, and the first toggle', () => {
		expect(overBudget()).toEqual([]);
		expect(FIELDS_BANDS.map((b) => b.band)).toEqual(['z8', 'z9', 'z10', 'z11', 'z12', 'z13', 'z14']);
		const worst = Math.max(...FIELDS_BANDS.map((b) => b.gzip), ...YEAR_CUTS.map((y) => y.gzip));
		expect(worst).toBe(106_699); // z11, the densest tile
		expect(worst).toBeLessThan(BUDGET.busiestTileBytes * 0.75);
		expect(FIRST_TOGGLE.gzip).toBeLessThan(BUDGET.firstToggleBytes / 4);
		// The raw z11 tile is over 150 KB: the budget is gzip.
		expect(FIELDS_BANDS.find((b) => b.band === 'z11')!.raw).toBeGreaterThan(BUDGET.busiestTileBytes);
		for (const b of FIELDS_BANDS) expect(b.gzip).toBeLessThan(b.raw);
	});

	it('reports a tile or a toggle that is over, in words', () => {
		expect(overBudget([{ band: 'z11', gzip: 150_001 }], [], 0)).toEqual(['z11: busiest tile 150001 B gzip is over 150000']);
		expect(overBudget([], [{ year: 2020, gzip: 200_000 }], 0)[0]).toContain('2020');
		expect(overBudget([], [], 1_000_001)[0]).toContain('first toggle');
	});

	it('keeps the year cuts far inside the tile pool\'s 3 s statement timeout', () => {
		for (const [lo, hi] of Object.values(YEAR_CUT_MS)) {
			expect(lo).toBeLessThanOrEqual(hi);
			expect(hi).toBeLessThan(500);
		}
		expect(YEAR_CUTS.map((y) => y.year)).toEqual([2018, 2019, 2020, 2021, 2022, 2023, 2024]);
	});
});
