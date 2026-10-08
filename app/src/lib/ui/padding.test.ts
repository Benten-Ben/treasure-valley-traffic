import { describe, expect, it } from 'vitest';
import { chromePadding, MIN_VISIBLE, paddedCentre, samePadding, WIDGET_COLUMN } from './padding.js';

describe('the map padding follows the open columns (§14.3 "Regions")', () => {
	it('desktop: the bars, the legend column, and the widget or the open inspect card', () => {
		expect(chromePadding({ layout: 'desktop', width: 1280, height: 800, inspect: false })).toEqual({ top: 76, right: WIDGET_COLUMN, bottom: 104, left: 312 });
		expect(chromePadding({ layout: 'desktop', width: 1280, height: 800, inspect: true })).toEqual({ top: 76, right: 392, bottom: 104, left: 312 });
	});

	it('tablet: the narrower inspect card', () => {
		expect(chromePadding({ layout: 'tablet', width: 1000, height: 800, inspect: true }).right).toBe(352);
	});

	it('phone: under the nameplate and chips, over the smallest sheet and the tab bar', () => {
		expect(chromePadding({ layout: 'phone', width: 390, height: 844, inspect: true })).toEqual({ top: 106, right: 0, bottom: 80 + 211 + 8, left: 0 });
	});

	it('a small screen keeps some map between the paddings', () => {
		const p = chromePadding({ layout: 'tablet', width: 700, height: 800, inspect: true });
		expect(700 - p.left - p.right).toBeGreaterThanOrEqual(MIN_VISIBLE);
		expect(p.left / p.right).toBeCloseTo(312 / 352, 1);
	});

	it('the centre is drawn in the middle of what the padding leaves', () => {
		expect(paddedCentre(1280, 800, { top: 76, right: 72, bottom: 104, left: 312 })).toEqual([760, 386]);
		expect(samePadding({ top: 1, right: 2, bottom: 3, left: 4 }, { top: 1.2, right: 2, bottom: 3, left: 4 })).toBe(true);
		expect(samePadding({ top: 1 }, { top: 2 })).toBe(false);
	});
});
