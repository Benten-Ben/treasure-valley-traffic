import type { Map, PaddingOptions } from 'maplibre-gl';
import { describe, expect, it, vi } from 'vitest';
import {
	applyPadding,
	cardLanding,
	chromePadding,
	fitPadding,
	isPaddingMove,
	landingFor,
	MIN_VISIBLE,
	paddedCentre,
	REVEAL_CLEAR_PX,
	REVEAL_MS,
	REVEAL_NEAR_PX,
	revealPan,
	revealTarget,
	samePadding,
	WIDGET_COLUMN
} from './padding.js';

describe('the map padding follows the fixed chrome (§14.3 "Regions")', () => {
	it('desktop: the bars, the legend column and the widget, whatever is selected', () => {
		expect(chromePadding({ layout: 'desktop', width: 1280, height: 800 })).toEqual({ top: 76, right: WIDGET_COLUMN, bottom: 104, left: 312 });
		expect(chromePadding({ layout: 'desktop', width: 1280, height: 800, inspect: false })).toEqual(chromePadding({ layout: 'desktop', width: 1280, height: 800 }));
		// The padding a move lands in while the card is open: its column instead of the widget's.
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

	it('its own moves are tagged, so a listener can tell them from real ones (Streets\' keeper)', () => {
		const events: unknown[] = [];
		let padding: PaddingOptions = { top: 0, right: 0, bottom: 0, left: 0 };
		const map = {
			getPadding: () => padding,
			setPadding: (p: PaddingOptions, e?: unknown) => {
				padding = p;
				events.push(e);
			},
			jumpTo: (o: { padding?: PaddingOptions }, e?: unknown) => {
				if (o.padding) padding = o.padding;
				events.push(e);
			},
			getContainer: () => ({ clientWidth: 1280, clientHeight: 800 }),
			unproject: () => ({ lng: -116.2, lat: 43.6 })
		} as unknown as Map;
		// A resize from a desktop to a phone and back.
		const desktop = chromePadding({ layout: 'desktop', width: 1280, height: 800 });
		const phone = chromePadding({ layout: 'phone', width: 1280, height: 800 });
		expect(applyPadding(map, desktop)).toBe(true);
		expect(applyPadding(map, desktop)).toBe(false);
		expect(applyPadding(map, phone)).toBe(true);
		expect(applyPadding(map, desktop)).toBe(true);
		expect(events).toHaveLength(3);
		expect(events.every(isPaddingMove)).toBe(true);
		expect(isPaddingMove({ type: 'movestart' })).toBe(false);
		expect(isPaddingMove(undefined)).toBe(false);
	});
});

describe('the app\'s own moves while the inspect card is open land left of it', () => {
	const stored = chromePadding({ layout: 'desktop', width: 1280, height: 800 });

	it('by an offset from the map\'s padded centre, and extra padding for cameraForBounds', () => {
		const l = cardLanding({ layout: 'desktop', width: 1280, height: 800, stored })!;
		expect(l.padding).toEqual({ top: 76, right: 392, bottom: 104, left: 312 });
		// Half the card's column less the widget's: (392 - 72) / 2 to the left.
		expect(l.offset).toEqual([-160, 0]);
		expect(l.extra).toEqual({ top: 0, right: 320, bottom: 0, left: 0 });
		// The offset takes the map's centre to the middle of the area the card leaves.
		const [x0, y0] = paddedCentre(1280, 800, stored);
		expect([x0 + l.offset[0], y0 + l.offset[1]]).toEqual(paddedCentre(1280, 800, l.padding));
		expect(fitPadding(40, l)).toEqual({ top: 40, right: 360, bottom: 40, left: 40 });
		expect(fitPadding(40, null)).toEqual({ top: 40, right: 40, bottom: 40, left: 40 });
	});

	it('a tablet\'s narrower card; none on a phone, whose card is in the sheet', () => {
		const t = chromePadding({ layout: 'tablet', width: 1000, height: 800 });
		expect(cardLanding({ layout: 'tablet', width: 1000, height: 800, stored: t })!.offset).toEqual([-(352 - 72) / 2, 0]);
		expect(cardLanding({ layout: 'phone', width: 390, height: 844, stored: chromePadding({ layout: 'phone', width: 390, height: 844 }) })).toBeNull();
	});

	it('measured from the padding the map has, so a move lands the same from anywhere', () => {
		// A small tablet shrinks both columns to fit: the offset still lands in the middle of the card-aware area.
		const move = chromePadding({ layout: 'tablet', width: 700, height: 800, inspect: true });
		const l = landingFor({ top: 0, right: 0, bottom: 0, left: 0 }, move);
		expect(l.offset).toEqual([(move.left - move.right) / 2, (move.top - move.bottom) / 2]);
		expect(l.extra).toEqual(move);
		expect(landingFor(move, move).offset).toEqual([0, 0]);
	});
});

describe('a click the inspect card would cover pans clear', () => {
	const card = { left: 904, top: 190, bottom: 696 };

	it('under the card, or within a few px of it: sideways, just clear, at the same height', () => {
		expect(revealTarget({ x: 1000, y: 400 }, card)).toEqual({ x: 904 - REVEAL_CLEAR_PX, y: 400 });
		expect(revealTarget({ x: 904 - REVEAL_NEAR_PX, y: 400 }, card)).toEqual({ x: 904 - REVEAL_CLEAR_PX, y: 400 });
		// Low in the column, where the card grows as it loads.
		expect(revealTarget({ x: 1100, y: 690 }, card)).toEqual({ x: 904 - REVEAL_CLEAR_PX, y: 690 });
		expect(revealTarget({ x: 1100, y: card.top - REVEAL_NEAR_PX }, card)).not.toBeNull();
	});

	it('clear already: nothing moves', () => {
		expect(revealTarget({ x: 880, y: 400 }, card)).toBeNull();
		expect(revealTarget({ x: 904 - REVEAL_NEAR_PX - 1, y: 400 }, card)).toBeNull();
		// Above the card, beside the camera widget; below the column, by the credits.
		expect(revealTarget({ x: 1000, y: 150 }, card)).toBeNull();
		expect(revealTarget({ x: 1000, y: 760 }, card)).toBeNull();
	});

	it('an ease with an offset: same zoom, pitch, bearing and padding; a jump under reduced motion', () => {
		const easeTo = vi.fn();
		const map = {
			getContainer: () => ({ clientWidth: 1280, clientHeight: 800 }),
			getPadding: () => ({ top: 76, right: 72, bottom: 104, left: 312 }),
			easeTo
		} as unknown as Map;
		revealPan(map, { lng: -116.2, lat: 43.6 }, { x: 864, y: 400 }, false);
		// The padded centre is (760, 386).
		expect(easeTo).toHaveBeenLastCalledWith({ center: [-116.2, 43.6], offset: [104, 14], duration: REVEAL_MS });
		revealPan(map, { lng: -116.2, lat: 43.6 }, { x: 864, y: 400 }, true);
		expect(easeTo).toHaveBeenLastCalledWith({ center: [-116.2, 43.6], offset: [104, 14], animate: false });
		for (const [o] of easeTo.mock.calls) expect(Object.keys(o).sort()).not.toContain('padding');
	});
});
