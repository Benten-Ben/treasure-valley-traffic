import { describe, expect, it } from 'vitest';
import { chooseLayers, formatLayerList, LayerSet, parseLayerList, sameSet } from './layers.svelte.js';

const known = ['streets', 'transit', 'cameras'];

describe('layer set memory', () => {
	it('parses and formats the hash list', () => {
		expect(parseLayerList('streets,transit', known)).toEqual(['streets', 'transit']);
		expect(parseLayerList('transit,bogus,transit', known)).toEqual(['transit']);
		expect(parseLayerList('none', known)).toEqual([]);
		expect(parseLayerList('', known)).toEqual([]);
		expect(parseLayerList(null, known)).toBeNull();
		expect(formatLayerList(['streets', 'cameras'])).toBe('streets,cameras');
		expect(formatLayerList([])).toBe('none');
		expect(sameSet(['a', 'b'], ['b', 'a'])).toBe(true);
		expect(sameSet(['a'], ['a', 'b'])).toBe(false);
	});

	it('takes the URL, then the saved set, then the old lens, then the defaults', () => {
		expect(chooseLayers({ url: 'streets', saved: ['cameras'], legacyLens: 'transit', known })).toEqual({ ids: ['streets'], source: 'url' });
		expect(chooseLayers({ url: null, saved: ['cameras'], legacyLens: 'transit', known })).toEqual({ ids: ['cameras'], source: 'saved' });
		expect(chooseLayers({ url: null, saved: [], legacyLens: 'transit', known })).toEqual({ ids: [], source: 'saved' });
		expect(chooseLayers({ url: null, saved: undefined, legacyLens: 'streets', known })).toEqual({ ids: ['streets'], source: 'legacy' });
		expect(chooseLayers({ url: null, saved: undefined, legacyLens: 'nonsense', known })).toEqual({ ids: ['transit', 'cameras'], source: 'default' });
		expect(chooseLayers({ url: 'none', saved: ['cameras'], legacyLens: null, known })).toEqual({ ids: [], source: 'url' });
	});
});

describe('LayerSet', () => {
	it('toggles any combination, keeping the most recently turned on last', () => {
		const s = new LayerSet(['transit', 'cameras']);
		expect(s.last).toBe('cameras');
		s.toggle('streets');
		expect(s.enabled).toEqual(['transit', 'cameras', 'streets']);
		s.toggle('transit');
		expect(s.enabled).toEqual(['cameras', 'streets']);
		expect(s.last).toBe('transit');
		s.toggle('transit');
		expect(s.enabled).toEqual(['cameras', 'streets', 'transit']);
	});

	it('1 turns everything off, and again restores it', () => {
		const s = new LayerSet(['transit', 'cameras']);
		s.allOff();
		expect(s.enabled).toEqual([]);
		s.allOff();
		expect(s.enabled).toEqual(['transit', 'cameras']);
		// A manual toggle in between forgets what 1 would restore.
		s.allOff();
		s.toggle('streets');
		s.toggle('streets');
		s.allOff();
		expect(s.enabled).toEqual([]);
	});

	it('Shift+digit solos a layer, and again restores the set from before', () => {
		const s = new LayerSet(['transit', 'cameras']);
		s.solo('streets');
		expect(s.enabled).toEqual(['streets']);
		s.solo('streets');
		expect(s.enabled).toEqual(['transit', 'cameras']);
		// Solo to solo keeps the original set.
		s.solo('transit');
		s.solo('cameras');
		expect(s.enabled).toEqual(['cameras']);
		s.solo('cameras');
		expect(s.enabled).toEqual(['transit', 'cameras']);
	});
});
