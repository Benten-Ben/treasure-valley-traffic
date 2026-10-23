import { describe, expect, it, vi } from 'vitest';

vi.mock('$app/env/private', () => ({ DATABASE_URL: undefined, FRAMES_DIR: '/nonexistent', TVT_FRAME_SOURCE: 'fixture' }));
const { tileLayerProblems, tileLayer } = await import('#lib/server/mvt.js');
const { default: burnScars } = await import('./tiles.js');

describe('the burn-scar tile layer (hazards.burn_scars)', () => {
	it('is a valid definition: no problems reported by the tile contract', () => {
		expect(tileLayerProblems(burnScars)).toEqual([]);
	});

	it('is registered under its plugin and layer name', () => {
		expect(burnScars.plugin).toBe('hazards');
		expect(burnScars.layer).toBe('burn_scars');
		expect(tileLayer('hazards', 'burn_scars')).toBeDefined();
	});

	it('reads the shown view: simplified outlines z8–12, full ones from z13, z14 overzooms the last band', () => {
		const [part] = burnScars.parts ?? [];
		expect(part.name).toBe('scars');
		const [lo, hi] = part.sources;
		expect(lo).toMatchObject({ minzoom: 8, maxzoom: 12, table: 'hazards.burn_scar_shown', geom: 'geom_lo' });
		expect(hi).toMatchObject({ minzoom: 13, maxzoom: 14, table: 'hazards.burn_scar_shown', geom: 'geom' });
		expect(burnScars.minzoom).toBe(8);
		expect(burnScars.maxzoom).toBe(14);
	});
});
