import { describe, expect, it } from 'vitest';
import { RAMP_ALONE, RAMP_UNDER, speedColor } from './ramp.js';
import { L, oneWayText, RAMP_LAYERS, selectedFilter, STREET_LAYERS, streetLayers, visibleStreetLayers } from './streets.js';

describe('streets', () => {
	it('colors posted speeds on the stepped ramp, light to dark', () => {
		expect(speedColor(20)).toBe(RAMP_ALONE[0]);
		expect(speedColor(null)).toBe(RAMP_ALONE[0]);
		expect(speedColor(5)).toBe(RAMP_ALONE[0]);
		expect(speedColor(30)).toBe(RAMP_ALONE[2]);
		expect(speedColor(35)).toBe(RAMP_ALONE[3]);
		expect(speedColor(50)).toBe(RAMP_ALONE[6]);
		expect(speedColor(75)).toBe(RAMP_ALONE[10]);
		expect(speedColor(30, 'under')).toBe(RAMP_UNDER[2]);
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
		// The selected outline sits under the road's own lines; both casings under both speed lines.
		const ids = layers.map((l) => l.layer.id);
		expect(ids.indexOf(L.selected)).toBeLessThan(ids.indexOf(L.casing));
		for (const c of [L.casing, L.casingUnder]) for (const s of [L.speed, L.speedUnder]) expect(ids.indexOf(c)).toBeLessThan(ids.indexOf(s));
		expect(selectedFilter(42)).toEqual(['any', ['==', ['id'], 42], ['==', ['get', 'id'], 42]]);
		// Every layer has its own layout object (MapLibre keeps them apart anyway; this keeps tests honest).
		expect(new Set(layers.map((l) => l.layer.layout)).size).toBe(layers.length);
	});

	it('draws the two ramps as two layer pairs on one source, one pair at a time', () => {
		const layers = streetLayers();
		const src = new Set(layers.map((l) => (l.layer as { source?: string }).source));
		expect([...src]).toEqual(['roads']);
		expect(visibleStreetLayers(false, 'alone').size).toBe(0);
		const alone = visibleStreetLayers(true, 'alone');
		const under = visibleStreetLayers(true, 'under');
		for (const id of RAMP_LAYERS.alone) expect([alone.has(id), under.has(id)], id).toEqual([true, false]);
		for (const id of RAMP_LAYERS.under) expect([alone.has(id), under.has(id)], id).toEqual([false, true]);
		// Everything else (selection outline, chevrons, speed numbers) shows with either ramp.
		for (const id of STREET_LAYERS.filter((x) => ![...RAMP_LAYERS.alone, ...RAMP_LAYERS.under].includes(x)))
			expect([alone.has(id), under.has(id)], id).toEqual([true, true]);
	});
});
