import { describe, expect, it } from 'vitest';
import { BANDS, BUDGET, FIRST_TOGGLE, overBudget, Z8_WITH_WASH } from './budget.js';
import { WASH_FROM } from './tiles.js';

describe("the Soils layer's tile budget", () => {
	it('is the owner\'s: the busiest tile at most 150 KB gzip, the first toggle at most 1 MB', () => {
		expect(BUDGET).toEqual({ busiestTileBytes: 150_000, firstToggleBytes: 1_000_000 });
	});

	it('holds for every band the server serves, and for the first toggle at the default view', () => {
		expect(overBudget()).toEqual([]);
		expect(BANDS.map((b) => b.band.split(' ')[0])).toEqual(['z8', 'z9', 'z10', 'z11', 'z12', 'z13', 'z14']);
		for (const b of BANDS) expect(b.gzip, b.band).toBeLessThan(b.raw);
		expect(FIRST_TOGGLE.gzip).toBeLessThanOrEqual(BUDGET.firstToggleBytes);
		expect(FIRST_TOGGLE.nearest9.gzip).toBeLessThan(FIRST_TOGGLE.gzip);
	});

	it('says why the wash starts at z9: z8 with every map unit in it was over', () => {
		expect(overBudget([Z8_WITH_WASH])).toHaveLength(1);
		expect(WASH_FROM).toBe(9);
	});

	it('reports what is over', () => {
		expect(overBudget([{ band: 'z10', gzip: 151_000 }], 1_100_000)).toEqual(['z10: busiest tile 151000 B gzip is over 150000', 'first toggle 1100000 B gzip is over 1000000']);
	});
});
