import { EDITABLE } from '#lib/app/keyguard.js';

/**
 * The calibrator's keys (docs/14 §14.6, "Calibrating on the map"): Ctrl+Z
 * undoes, Delete removes the selected pair, Ctrl+S saves. Cmd works as Ctrl
 * (the owner's Mac), and on a Mac keyboard "delete" is Backspace, so both
 * remove the pair.
 *
 * The keymap registry ignores keys with Ctrl or Cmd held (§14.3), so the
 * page listens for these itself, only while it's in Calibrate mode. Ctrl+S
 * is caught even in a text field (the browser would offer to save the page);
 * the others leave text fields alone.
 */
export type CalibrateKey = 'undo' | 'save' | 'remove';

type KeyLike = Pick<KeyboardEvent, 'code' | 'key' | 'ctrlKey' | 'metaKey' | 'altKey' | 'shiftKey'> & { target: EventTarget | null };

interface ElementLike {
	closest?(selector: string): unknown;
	isContentEditable?: boolean;
}

function editable(t: EventTarget | null): boolean {
	const el = t as ElementLike | null;
	if (!el) return false;
	if (el.isContentEditable) return true;
	return typeof el.closest === 'function' && el.closest(EDITABLE) !== null;
}

export function calibrateKey(e: KeyLike): CalibrateKey | null {
	const mod = e.ctrlKey || e.metaKey;
	if (mod && !e.altKey && !e.shiftKey && e.code === 'KeyS') return 'save';
	if (editable(e.target)) return null;
	if (mod && !e.altKey && !e.shiftKey && e.code === 'KeyZ') return 'undo';
	if (!mod && !e.altKey && !e.shiftKey && (e.code === 'Delete' || e.code === 'Backspace')) return 'remove';
	return null;
}
