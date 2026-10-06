/**
 * The key guard (docs/14 §14.3, "Keymap"): map shortcuts are ignored while
 * focus is in an input, textarea, select or contenteditable element, or
 * while Ctrl, Meta or Alt is held, so typing (or choosing a camera view in a
 * select with the keyboard) never also flips a layer.
 *
 * WP2's keymap registry uses this for every key; it adds the rule that Space
 * and Enter are also ignored on buttons and links.
 */
export const EDITABLE = 'input, textarea, select, [contenteditable]:not([contenteditable="false"])';

type KeyLike = Pick<KeyboardEvent, 'ctrlKey' | 'metaKey' | 'altKey'> & { target: EventTarget | null };

interface ElementLike {
	closest?(selector: string): unknown;
	isContentEditable?: boolean;
}

/** True when a key press must not reach the map's shortcuts. */
export function ignoreKey(e: KeyLike): boolean {
	if (e.ctrlKey || e.metaKey || e.altKey) return true;
	const t = e.target as ElementLike | null;
	if (!t) return false;
	if (t.isContentEditable) return true;
	return typeof t.closest === 'function' && t.closest(EDITABLE) !== null;
}
