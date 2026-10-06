import { describe, expect, it } from 'vitest';
import { EDITABLE, ignoreKey } from './keyguard.js';

/** An element stand-in: `matches` lists the selectors its closest() finds an ancestor for. */
const el = (matches: boolean, isContentEditable = false) => ({
	closest: (sel: string) => (matches && sel === EDITABLE ? {} : null),
	isContentEditable
});
const key = (target: unknown, mods: Partial<Record<'ctrlKey' | 'metaKey' | 'altKey', boolean>> = {}) => ({
	ctrlKey: false,
	metaKey: false,
	altKey: false,
	...mods,
	target: target as EventTarget | null
});

describe('ignoreKey', () => {
	it('lets keys through on the page and on the map', () => {
		expect(ignoreKey(key(el(false)))).toBe(false);
		expect(ignoreKey(key(null))).toBe(false);
	});

	it('ignores keys typed in inputs, textareas, selects and contenteditable', () => {
		expect(ignoreKey(key(el(true)))).toBe(true);
		expect(ignoreKey(key(el(false, true)))).toBe(true);
	});

	it('ignores keys with Ctrl, Meta or Alt held', () => {
		for (const m of ['ctrlKey', 'metaKey', 'altKey'] as const) expect(ignoreKey(key(el(false), { [m]: true })), m).toBe(true);
	});

	it('covers the four kinds of editable element, but not contenteditable="false"', () => {
		expect(EDITABLE).toContain('input');
		expect(EDITABLE).toContain('textarea');
		expect(EDITABLE).toContain('select');
		expect(EDITABLE).toContain('[contenteditable]:not([contenteditable="false"])');
	});
});
