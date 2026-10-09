import { describe, expect, it } from 'vitest';
import { errorDetail } from './errors.js';
import { redrapeTerrain } from './restore.js';

describe('map errors in words', () => {
	it('names the error, its status and URL, and the source and tile', () => {
		expect(errorDetail({ error: { name: 'AJAXError', message: 'Not Found', status: 404, url: '/tiles/x.pmtiles' }, sourceId: 'imagery', tile: { tileID: { canonical: { z: 16, x: 1, y: 2 } } } })).toBe(
			'AJAXError: Not Found · status 404 · url /tiles/x.pmtiles · source imagery · tile 16/1/2'
		);
	});

	it('says so when an error has no message (the console showed just "Error")', () => {
		expect(errorDetail({ error: new Error() })).toBe('Error: (no message)');
		expect(errorDetail({})).toBe('Error: (no message)');
	});
});

describe('the terrain after a context restore', () => {
	it('turns terrain off and on again with the same settings', () => {
		const calls: unknown[] = [];
		let terrain: { source: string; exaggeration?: number } | null = { source: 'terrain', exaggeration: 1.5 };
		const map = {
			getTerrain: () => terrain,
			setTerrain: (t: typeof terrain) => {
				calls.push(t);
				terrain = t;
				return map;
			}
		};
		redrapeTerrain(map as never);
		expect(calls).toEqual([null, { source: 'terrain', exaggeration: 1.5 }]);
	});

	it('leaves a map without terrain alone', () => {
		const calls: unknown[] = [];
		redrapeTerrain({ getTerrain: () => null, setTerrain: (t: unknown) => calls.push(t) } as never);
		expect(calls).toEqual([]);
	});
});
