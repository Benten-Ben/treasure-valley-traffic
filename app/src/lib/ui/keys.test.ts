import { afterEach, describe, expect, it } from 'vitest';
import { escape, handleKey, ignoreKey, match, onEscape, register, type KeyBinding } from './keys.js';

/** An element-like target: `closest` answers for the selectors it matches. */
const el = (matches: (sel: string) => boolean) => ({ closest: (s: string) => (s.split(',').some((x) => matches(x.trim())) ? {} : null) });
const button = el((s) => s === 'button');
const input = el((s) => s === 'input');
const plain = el(() => false);

function key(code: string, o: Partial<KeyboardEvent> & { target?: unknown } = {}): KeyboardEvent {
	let prevented = false;
	return {
		code,
		key: o.key ?? code,
		shiftKey: false,
		ctrlKey: false,
		metaKey: false,
		altKey: false,
		repeat: false,
		target: plain,
		get defaultPrevented() {
			return prevented;
		},
		preventDefault: () => (prevented = true),
		...o
	} as unknown as KeyboardEvent;
}

const cleanup: (() => void)[] = [];
afterEach(() => {
	for (const f of cleanup.splice(0)) f();
});

describe('keymap', () => {
	it('ignores keys in inputs and with modifiers; Space and Enter on controls', () => {
		expect(ignoreKey(key('Digit4', { target: input as never }))).toBe(true);
		expect(ignoreKey(key('Digit4', { ctrlKey: true }))).toBe(true);
		expect(ignoreKey(key('Digit4', { metaKey: true }))).toBe(true);
		expect(ignoreKey(key('Digit4', { target: button as never }))).toBe(false);
		expect(ignoreKey(key('Space', { key: ' ', target: button as never }))).toBe(true);
		expect(ignoreKey(key('Enter', { target: button as never }))).toBe(true);
		expect(ignoreKey(key('Space', { key: ' ', target: plain as never }))).toBe(false);
		// Escape still closes things from inside an input.
		expect(ignoreKey(key('Escape', { target: input as never }))).toBe(false);
	});

	it('matches by code, Shift, and mode', () => {
		const b: KeyBinding[] = [
			{ id: 'four', codes: ['Digit4'], label: '4', description: '', group: 'Layers', run: () => {} },
			{ id: 'solo', codes: ['Digit4'], shift: true, label: 'Shift+4', description: '', group: 'Layers', run: () => {} },
			{ id: 'look', codes: ['ArrowLeft'], label: '←', description: '', group: 'Look-through', modes: ['look'], run: () => {} },
			{ id: 'pan', codes: ['KeyW'], shift: 'any', label: 'W', description: '', group: 'Camera', run: () => {} }
		];
		expect(match({ code: 'Digit4', shiftKey: false }, 'explore', b)?.id).toBe('four');
		expect(match({ code: 'Digit4', shiftKey: true }, 'explore', b)?.id).toBe('solo');
		expect(match({ code: 'Digit4', shiftKey: false }, 'calibrate', b)).toBeUndefined();
		expect(match({ code: 'ArrowLeft', shiftKey: false }, 'explore', b)).toBeUndefined();
		expect(match({ code: 'ArrowLeft', shiftKey: false }, 'look', b)?.id).toBe('look');
		expect(match({ code: 'KeyW', shiftKey: true }, 'explore', b)?.id).toBe('pan');
	});

	it('runs a registered binding once and prevents the default; Space on a button does nothing here', () => {
		let runs = 0;
		cleanup.push(register({ id: 'space', codes: ['Space'], label: 'Space', description: '', group: 'Time', run: () => void runs++ }));
		const onButton = key('Space', { key: ' ', target: button as never });
		expect(handleKey(onButton, 'explore')).toBe(false);
		expect(onButton.defaultPrevented).toBe(false);
		expect(runs).toBe(0);
		const onMap = key('Space', { key: ' ' });
		expect(handleKey(onMap, 'explore')).toBe(true);
		expect(onMap.defaultPrevented).toBe(true);
		expect(runs).toBe(1);
	});

	it('closes in Esc order: the highest rank that has something open', () => {
		const closed: string[] = [];
		let selection = true;
		let popover = true;
		cleanup.push(onEscape(40, () => (selection ? ((selection = false), closed.push('selection'), true) : false)));
		cleanup.push(onEscape(100, () => (popover ? ((popover = false), closed.push('popover'), true) : false)));
		expect(escape()).toBe(true);
		expect(escape()).toBe(true);
		expect(escape()).toBe(false);
		expect(closed).toEqual(['popover', 'selection']);
	});
});
