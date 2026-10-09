import { describe, expect, it } from 'vitest';
import { KEEP_SHARE, overlapArea, STACK_SHARE, stackUp, type StackItem } from './stack.js';

/** A plate-sized box (40 × 27 px: body and pointer) centred at (x, y). */
const box = (id: string, x: number, y: number): StackItem => ({ id, x, y, l: 20, t: 13.5, r: 20, b: 13.5, dy: 0 });

describe('fanning out sprites that cover each other (§14.4: the plate is never hidden)', () => {
	it('lifts the earlier of two plates on one spot above the later one, gap px apart', () => {
		const items = [box('a', 100, 100), box('b', 101, 99)];
		const lifted = stackUp(items, 2, 2);
		expect([...lifted]).toEqual(['a']);
		// b stays (drawn last, it's on the buses); a's bottom is 2 px over b's top.
		expect(items[1]).toMatchObject({ x: 101, y: 99, dy: 0 });
		expect(items[0].y + items[0].b).toBeCloseTo(items[1].y - items[1].t - 2, 9);
		expect(items[0].dy).toBeCloseTo(100 - items[0].y, 9);
		expect(overlapArea(items[0], items[1])).toBe(0);
	});

	it('stands three on one spot in a column, the last at the bottom', () => {
		const items = [box('a', 50, 50), box('b', 50, 50), box('c', 50, 50)];
		stackUp(items, 3, 2);
		expect(items[2].y).toBe(50);
		expect(items[1].y).toBeCloseTo(50 - 29, 9);
		expect(items[0].y).toBeCloseTo(50 - 58, 9);
	});

	it('leaves plates that overlap a little where they are, and only looks at the first n', () => {
		// 10 px of a 40 px width: a quarter, under STACK_SHARE.
		const items = [box('a', 100, 100), box('b', 130, 100), box('c', 100, 100)];
		expect(10 / 40).toBeLessThan(STACK_SHARE);
		stackUp(items, 2, 2);
		expect(items[0].y).toBe(100);
		expect(items[1].y).toBe(100);
	});

	it('keeps a lifted plate lifted down to KEEP_SHARE, so a pair near the threshold does not flicker', () => {
		// 8 px of 40 across: 20%, between KEEP_SHARE and STACK_SHARE.
		const at = () => [box('a', 100, 100), box('b', 132, 100)];
		expect(8 / 40).toBeGreaterThan(KEEP_SHARE);
		expect(8 / 40).toBeLessThan(STACK_SHARE);
		const fresh = at();
		expect(stackUp(fresh, 2, 2).size).toBe(0);
		const kept = at();
		expect([...stackUp(kept, 2, 2, new Set(['a']))]).toEqual(['a']);
		expect(kept[0].y).toBeLessThan(100);
		// Farther apart than that, it comes back down.
		const apart = [box('a', 100, 100), box('b', 136, 100)];
		expect(stackUp(apart, 2, 2, new Set(['a'])).size).toBe(0);
	});

	it('writes the ids lifted into the set it is given, cleared first', () => {
		const out = new Set(['stale']);
		const r = stackUp([box('a', 0, 0), box('b', 0, 0)], 2, 2, undefined, out);
		expect(r).toBe(out);
		expect([...out]).toEqual(['a']);
	});
});
