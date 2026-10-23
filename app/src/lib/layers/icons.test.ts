import { describe, expect, it } from 'vitest';
import { layerIcon } from './icons.js';
import { LAYER_DEFS } from './registry.js';

describe('the layers’ icons (kept out of the always-loaded defs)', () => {
	it('gives every layer its own icon, not the fallback', () => {
		const streets = layerIcon({ id: 'streets' });
		for (const d of LAYER_DEFS) {
			expect(layerIcon(d), d.id).toBeTruthy();
			if (d.id !== 'streets') expect(layerIcon(d), d.id).not.toBe(streets);
		}
	});

	it('keeps path data out of the defs', () => {
		for (const d of LAYER_DEFS) expect(d.icon, d.id).toBeUndefined();
	});
});
