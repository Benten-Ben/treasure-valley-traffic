import { ignoreKey as editableOrModified } from '#lib/app/keyguard.js';
import type { ModeId } from '#lib/state/modes.svelte.js';
import { logKey, ranLog } from './keylog.js';

/**
 * The keymap registry (docs/14 §14.3, "Keymap"). One registry drives both the
 * key handler and the help overlay. Packages register their own keys from
 * their own modules (Backspace from WP3, Space and L from WP8, ← and → from
 * WP13), so only WP2 edits this file.
 *
 * - Keys are matched by `event.code` (Shift+digit works on any layout).
 * - Ignored while focus is in an input, textarea, select or contenteditable
 *   element, or while Ctrl, Meta or Alt is held (Escape still closes things
 *   from inside an input).
 * - Space and Enter are also ignored when focus is on a button, link,
 *   summary, slider or anything with role=button, so one press never both
 *   activates a control and runs a shortcut.
 * - A binding runs only in its modes (Explore unless it says otherwise).
 * - Esc closes, in order: help or a popover; the focused window;
 *   look-through; calibrate; follow; the inspect card; the selection. Each
 *   closer registers with its rank (`ESC`), and the first that closes
 *   something wins.
 */

export interface KeyBinding {
	/** Unique id ('layer-transit', 'pan-north'). */
	id: string;
	/** `event.code` values: 'Digit4', 'KeyW', 'Slash', 'Backspace', 'Space', 'ArrowLeft'. */
	codes: string[];
	/** Shift must be held (true), must not be (false, the default), or either ('any'). */
	shift?: boolean | 'any';
	/** How the help overlay writes it: '4', 'Shift+4', 'W A S D'. */
	label: string;
	/** What it does, for the help overlay. */
	description: string;
	/** Help overlay section. */
	group: 'Layers' | 'Camera' | 'Time' | 'Windows' | 'Look-through' | 'Help' | string;
	/** Modes it works in (default: Explore only). */
	modes?: readonly ModeId[];
	/** Do it; returning false means "not handled" (the key passes on). */
	run(e: KeyboardEvent): void | boolean;
	/** Shown in the help overlay (default true); a key reserved for later can be listed but disabled. */
	help?: boolean;
}

/** Esc ranks (higher closes first). */
export const ESC = {
	popover: 100,
	window: 90,
	look: 80,
	calibrate: 70,
	follow: 60,
	inspect: 50,
	selection: 40
} as const;

const bindings: KeyBinding[] = [];
const escapes: { rank: number; close: () => boolean }[] = [];
const changeFns = new Set<() => void>();
export { ranLog };

/** Add bindings; returns their removal. */
export function register(b: KeyBinding | KeyBinding[]): () => void {
	const list = Array.isArray(b) ? b : [b];
	bindings.push(...list);
	for (const f of changeFns) f();
	return () => {
		for (const x of list) {
			const i = bindings.indexOf(x);
			if (i !== -1) bindings.splice(i, 1);
		}
		for (const f of changeFns) f();
	};
}

/** Add an Esc closer at a rank (ESC.*); `close` returns true when it closed something. */
export function onEscape(rank: number, close: () => boolean): () => void {
	const e = { rank, close };
	escapes.push(e);
	escapes.sort((a, b) => b.rank - a.rank);
	return () => {
		const i = escapes.indexOf(e);
		if (i !== -1) escapes.splice(i, 1);
	};
}

export function allBindings(): readonly KeyBinding[] {
	return bindings;
}

/** Hear when bindings change (the help overlay). */
export function onBindingsChange(fn: () => void): () => void {
	changeFns.add(fn);
	return () => changeFns.delete(fn);
}

/** Controls where Space and Enter belong to the control itself. */
export const CONTROLS = 'button, a[href], summary, [role="button"], [role="slider"], [role="switch"], [role="tab"], [role="menuitem"], [role="radio"], [role="checkbox"], input[type="range"]';

type KeyLike = Pick<KeyboardEvent, 'code' | 'key' | 'ctrlKey' | 'metaKey' | 'altKey' | 'shiftKey'> & { target: EventTarget | null };

interface ElementLike {
	closest?(selector: string): unknown;
}

/** True when a key press must not reach the map's shortcuts. */
export function ignoreKey(e: KeyLike): boolean {
	if (e.code === 'Escape' || e.key === 'Escape') return e.ctrlKey || e.metaKey || e.altKey;
	if (editableOrModified(e)) return true;
	if (e.code === 'Space' || e.code === 'Enter' || e.code === 'NumpadEnter' || e.key === ' ' || e.key === 'Enter') {
		const t = e.target as ElementLike | null;
		if (t && typeof t.closest === 'function' && t.closest(CONTROLS)) return true;
	}
	return false;
}

/** The binding a key press matches in a mode, if any. */
export function match(e: Pick<KeyboardEvent, 'code' | 'shiftKey'>, mode: ModeId, list: readonly KeyBinding[] = bindings): KeyBinding | undefined {
	return list.find((b) => {
		if (!b.codes.includes(e.code)) return false;
		const shift = b.shift ?? false;
		if (shift !== 'any' && shift !== e.shiftKey) return false;
		return (b.modes ?? ['explore']).includes(mode);
	});
}

/** Run the Esc chain; true when something closed. */
export function escape(): boolean {
	for (const e of [...escapes]) if (e.close()) return true;
	return false;
}

/**
 * The one key handler (the layout puts it on window). Returns true when a
 * shortcut handled the key (and prevented its default).
 */
export function handleKey(e: KeyboardEvent, mode: ModeId): boolean {
	if (e.defaultPrevented) return false;
	if (ignoreKey(e)) return false;
	if (e.code === 'Escape') {
		if (escape()) {
			e.preventDefault();
			logKey('escape');
			return true;
		}
		return false;
	}
	const b = match(e, mode);
	if (!b) return false;
	if (b.run(e) === false) return false;
	e.preventDefault();
	logKey(b.id);
	return true;
}
