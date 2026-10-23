import { describe, expect, it } from 'vitest';
import { FOCUS_GAP_MS, POLL_MS, levelChanged, refetchOnFocus } from './chip.js';

describe('the status chip timing', () => {
	it('polls every five minutes', () => {
		expect(POLL_MS).toBe(300_000);
	});

	it('refetches on focus when it has never answered, or the answer is old enough', () => {
		const now = 1_000_000;
		expect(refetchOnFocus(null, now)).toBe(true);
		expect(refetchOnFocus(now - FOCUS_GAP_MS, now)).toBe(true);
		expect(refetchOnFocus(now - FOCUS_GAP_MS + 1, now)).toBe(false);
	});
});

describe('the status chip live region', () => {
	it('is silent on the first answer', () => {
		expect(levelChanged(null, 'fresh')).toBe(false);
		expect(levelChanged(null, 'stale')).toBe(false);
	});

	it('speaks only when the level changes', () => {
		expect(levelChanged('fresh', 'fresh')).toBe(false);
		expect(levelChanged('fresh', 'late')).toBe(true);
		expect(levelChanged('late', 'fresh')).toBe(true);
	});
});
