import { describe, expect, it } from 'vitest';
import { STALL_M2, lotCard, parseLotId, parseWayId, wayCard } from './paving.js';

describe('the paving card', () => {
	it('a lot: its area in m2 and acres, a tagged capacity, and no stall estimate when one is tagged', () => {
		const c = lotCard({
			osm_type: 'w', osm_id: 42, name: 'Lot', operator: null, access: 'customers', fee: 'no',
			area_m2: 3000, capacity: 90, material: 'asphalt', material_source: 'surface'
		});
		expect(c.osm).toBe('w42');
		expect(c.area_m2).toBe(3000);
		expect(c.acres).toBeCloseTo(0.74, 2);
		expect(c.capacity).toBe(90);
		expect(c.stalls_estimated).toBeNull();
		expect(c.material_estimated).toBe(false);
		expect(c.credit).toBe('© OpenStreetMap contributors');
	});

	it('a lot with no capacity tag: an estimate from area, marked as one, with no per-stall figure on the card', () => {
		const c = lotCard({
			osm_type: 'r', osm_id: 7, name: null, operator: null, access: null, fee: null,
			area_m2: 600, capacity: null, material: 'unknown', material_source: null
		});
		expect(c.stalls_estimated).toBe(600 / STALL_M2);
		expect(c.osm).toBe('r7');
		expect(JSON.stringify(c)).not.toMatch(/m²|30 m/);
	});

	it('a way: a surface estimated when the tag is missing, and a width estimated when the tag is missing', () => {
		const c = wayCard({
			osm_id: 9001, kind: 'driveway', surface: null, material_source: 'default',
			width_m: null, width_est_m: 3.4, width_source: 'default', length_m: 41.26
		});
		expect(c.width_m).toBe(3.4);
		expect(c.width_estimated).toBe(true);
		expect(c.surface_estimated).toBe(true);
		expect(c.length_m).toBe(41.3);
		expect(c.osm).toBe('9001');
	});

	it('ids: a lot is w or r then digits; a way is digits; anything else is refused', () => {
		expect(parseLotId('w123')).toEqual({ osm_type: 'w', osm_id: '123' });
		expect(parseLotId('r1')).toEqual({ osm_type: 'r', osm_id: '1' });
		expect(parseLotId('123')).toBeNull();
		expect(parseLotId("w1'; drop")).toBeNull();
		expect(parseWayId('55')).toBe('55');
		expect(parseWayId('w55')).toBeNull();
	});
});
