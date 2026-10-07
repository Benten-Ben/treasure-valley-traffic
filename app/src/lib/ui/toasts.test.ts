import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DEFAULT_TIMEOUT, MAX_TOASTS, ToastStore } from './toasts.svelte.js';

describe('toasts', () => {
	beforeEach(() => vi.useFakeTimers());
	afterEach(() => vi.useRealTimers());

	it('go by themselves after their timeout, or stay when it is null', () => {
		const t = new ToastStore();
		t.show('Hello');
		t.show('Stays', { timeout: null });
		expect(t.list.map((x) => x.text)).toEqual(['Hello', 'Stays']);
		vi.advanceTimersByTime(DEFAULT_TIMEOUT + 1);
		expect(t.list.map((x) => x.text)).toEqual(['Stays']);
	});

	it('a key replaces the earlier toast; at most three show', () => {
		const t = new ToastStore();
		t.show('one', { key: 'k' });
		t.show('two', { key: 'k' });
		expect(t.list.map((x) => x.text)).toEqual(['two']);
		for (let i = 0; i < 5; i++) t.show(`n${i}`);
		expect(t.list).toHaveLength(MAX_TOASTS);
		expect(t.list.map((x) => x.text)).toEqual(['n2', 'n3', 'n4']);
	});

	it('show returns the dismissal', () => {
		const t = new ToastStore();
		const dismiss = t.show('bye', { kind: 'problem' });
		expect(t.list[0].kind).toBe('problem');
		dismiss();
		expect(t.list).toEqual([]);
	});
});
