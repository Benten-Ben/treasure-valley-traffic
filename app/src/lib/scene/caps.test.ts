import { describe, expect, it } from 'vitest';
import { CapLimiter, kthSmallest, M_PER_DEG } from './caps.js';

const LNG = -116.2;
const LAT = 43.6;
const cosLat = Math.cos((LAT * Math.PI) / 180);

/** An instance `east` metres east and `north` metres north of the view centre. */
const at = (id: number, east: number, north = 0) => ({ id, lng: LNG + east / (M_PER_DEG * cosLat), lat: LAT + north / M_PER_DEG });

describe('kthSmallest', () => {
	it('finds the k-th smallest, with repeats', () => {
		const xs = [9, 3, 7, 3, 1, 8, 3, 2, 6];
		const sorted = [...xs].sort((a, b) => a - b);
		for (let k = 0; k < xs.length; k++) expect(kthSmallest(Float64Array.from(xs), xs.length, k)).toBe(sorted[k]);
	});
});

describe('instance caps', () => {
	const lim = new CapLimiter<ReturnType<typeof at>>();
	const trees = Array.from({ length: 100 }, (_, i) => at(i, i * 10));

	it('without a cap or radius the group’s own list comes back untouched', () => {
		expect(lim.limit(trees, {}, LNG, LAT, false)).toBe(trees);
		expect(lim.limit(trees, { capPhone: 5 }, LNG, LAT, false)).toBe(trees);
	});

	it('keeps the cap nearest the view centre, in the group’s order', () => {
		const shuffled = [...trees].reverse();
		const kept = lim.limit(shuffled, { cap: 10 }, LNG, LAT, false);
		expect(kept.map((t) => t.id).sort((a, b) => a - b)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);
		expect(kept.map((t) => t.id)).toEqual([9, 8, 7, 6, 5, 4, 3, 2, 1, 0]);
	});

	it('measures from the view centre, not from the origin of the list', () => {
		const kept = lim.limit(trees, { cap: 3 }, LNG + 500 / (M_PER_DEG * cosLat), LAT, false);
		expect(kept.map((t) => t.id)).toEqual([49, 50, 51]);
	});

	it('radiusM drops the far ones before the cap counts', () => {
		expect(lim.limit(trees, { radiusM: 95 }, LNG, LAT, false)).toHaveLength(10);
		expect(lim.limit(trees, { radiusM: 95, cap: 4 }, LNG, LAT, false).map((t) => t.id)).toEqual([0, 1, 2, 3]);
		expect(lim.limit(trees, { radiusM: 95, cap: 40 }, LNG, LAT, false)).toHaveLength(10);
	});

	it('capPhone replaces cap on a phone, and 0 turns the group off there', () => {
		expect(lim.limit(trees, { cap: 50, capPhone: 20 }, LNG, LAT, true)).toHaveLength(20);
		expect(lim.limit(trees, { cap: 50, capPhone: 20 }, LNG, LAT, false)).toHaveLength(50);
		expect(lim.limit(trees, { cap: 50 }, LNG, LAT, true)).toHaveLength(50);
		expect(lim.limit(trees, { cap: 50, capPhone: 0 }, LNG, LAT, true)).toHaveLength(0);
		expect(lim.limit(trees, { cap: 50, capPhone: 0 }, LNG, LAT, false)).toHaveLength(50);
	});

	it('never keeps more than the cap when several are the same distance', () => {
		const ring = Array.from({ length: 12 }, (_, i) => at(i, 30));
		expect(lim.limit(ring, { cap: 5 }, LNG, LAT, false).map((t) => t.id)).toEqual([0, 1, 2, 3, 4]);
		const mixed = [at(0, 30), at(1, 10), at(2, 30), at(3, 30)];
		expect(lim.limit(mixed, { cap: 2 }, LNG, LAT, false).map((t) => t.id)).toEqual([0, 1]);
	});

	it('4,000 trees capped to 1,000 on a phone, 1,500 shrubs off', () => {
		const many = Array.from({ length: 4000 }, (_, i) => at(i, (i % 80) * 12 - 480, Math.floor(i / 80) * 12 - 300));
		expect(lim.limit(many, { cap: 4000, capPhone: 1000 }, LNG, LAT, true)).toHaveLength(1000);
		expect(lim.limit(many, { cap: 4000, capPhone: 1000 }, LNG, LAT, false)).toHaveLength(4000);
		const shrubs = many.slice(0, 1500);
		expect(lim.limit(shrubs, { cap: 1500, radiusM: 300, capPhone: 0 }, LNG, LAT, true)).toHaveLength(0);
		const near = lim.limit(shrubs, { cap: 1500, radiusM: 300, capPhone: 0 }, LNG, LAT, false);
		expect(near.length).toBeLessThan(1500);
		for (const s of near) expect(Math.hypot((s.lng - LNG) * M_PER_DEG * cosLat, (s.lat - LAT) * M_PER_DEG)).toBeLessThanOrEqual(300);
	});
});
