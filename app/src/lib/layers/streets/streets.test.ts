import { describe, expect, it } from 'vitest';
import { L, oneWayText, selectedFilter, SPEED_BINS, speedColor, streetLayers } from './streets.js';

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

	it('puts its lines in the streets slot and its symbols with the labels, all hidden at first', () => {
		const layers = streetLayers();
		for (const { slot, layer } of layers) {
			expect(layer.layout).toMatchObject({ visibility: 'none' });
			expect(slot).toBe(layer.type === 'line' ? 'streets' : 'labels');
		}
		// The selected outline sits under the road's own lines.
		const ids = layers.map((l) => l.layer.id);
		expect(ids.indexOf(L.selected)).toBeLessThan(ids.indexOf(L.casing));
		expect(selectedFilter(42)).toEqual(['any', ['==', ['id'], 42], ['==', ['get', 'id'], 42]]);
	});
});
