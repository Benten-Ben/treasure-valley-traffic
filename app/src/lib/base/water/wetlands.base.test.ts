import { describe, expect, it } from 'vitest';
import { MAPPED_FROM_1981, NOT_A_BOUNDARY, WETLAND_LAYERS, WETLAND_THIN_LAYER, WETLAND_TUFT_LAYER, wetlandTuft, wetlandWords } from './wetlands.base.js';

describe('wetland tufts', () => {
	it('draws recent mapping as tufts from z14 and the 1981-era mapping thinner from z15', () => {
		const recent = wetlandTuft(false);
		const thin = wetlandTuft(true);
		expect(recent.minzoom).toBe(14);
		expect(thin.minzoom).toBe(15);
		// Sparser: the gap after each mark is longer, and the mark is finer.
		expect(thin.dash[1]).toBeGreaterThan(recent.dash[1]);
		expect(thin.width).toBeLessThan(recent.width);
	});

	it('never uses a fill colour: each layer is a line, and the two layers split on the thin flag', () => {
		expect(WETLAND_LAYERS.map((l) => l.id)).toEqual([WETLAND_TUFT_LAYER, WETLAND_THIN_LAYER]);
		for (const layer of WETLAND_LAYERS) {
			expect(layer.type).toBe('line');
			expect(layer.valley).not.toHaveProperty('fill-color');
			expect(layer.clay).not.toHaveProperty('fill-color');
		}
		expect(JSON.stringify(WETLAND_LAYERS[0].filter)).toContain('"!"');
		expect(JSON.stringify(WETLAND_LAYERS[1].filter)).not.toContain('"!"');
	});

	it('says it is not a legal boundary on every wetland, and adds the 1981 note only where mapped then', () => {
		expect(wetlandWords(false)).toEqual([NOT_A_BOUNDARY]);
		expect(wetlandWords(true)).toEqual([NOT_A_BOUNDARY, MAPPED_FROM_1981]);
		expect(NOT_A_BOUNDARY).toBe('Not a legal (regulatory) wetland boundary.');
	});
});
