import type { ViewManager, ViewSnapshot } from './view.svelte.js';

/**
 * The mode stack (docs/14 §14.3, "Modes and the view stack").
 *
 * The map is in one mode at a time: Explore (the default), Look-through or
 * Calibrate. Entering a mode pushes a snapshot of the view (§14.3 lists what
 * it holds) and suspends the URL hash; leaving pops it and restores it
 * exactly, with `jumpTo`. Every map click handler checks `current`, so a
 * calibration click never selects a bus.
 */
export type ModeId = 'explore' | 'look' | 'calibrate';

export interface ModeEntry {
	mode: Exclude<ModeId, 'explore'>;
	snapshot: ViewSnapshot;
}

export class Modes {
	#stack = $state.raw<ModeEntry[]>([]);
	#view: ViewManager;

	constructor(view: ViewManager) {
		this.#view = view;
	}

	/** The active mode. */
	get current(): ModeId {
		return this.#stack.at(-1)?.mode ?? 'explore';
	}

	get depth(): number {
		return this.#stack.length;
	}

	is(mode: ModeId): boolean {
		return this.current === mode;
	}

	/**
	 * Enter a mode: push the current view's snapshot (or `snapshot`, for a
	 * deep link that has no view of its own to return to) and suspend the hash.
	 */
	enter(mode: ModeEntry['mode'], snapshot: ViewSnapshot = this.#view.snapshot()): ModeEntry {
		const entry = { mode, snapshot };
		this.#stack = [...this.#stack, entry];
		this.#view.suspend();
		return entry;
	}

	/**
	 * Leave `mode` (the topmost entry for it, and anything entered after it):
	 * restore its snapshot exactly and resume the hash. Returns the snapshot,
	 * or null when the mode wasn't active.
	 */
	leave(mode: ModeEntry['mode']): ViewSnapshot | null {
		const i = this.#stack.findLastIndex((e) => e.mode === mode);
		if (i === -1) return null;
		const entry = this.#stack[i];
		const dropped = this.#stack.length - i;
		this.#stack = this.#stack.slice(0, i);
		this.#view.restore(entry.snapshot);
		for (let k = 0; k < dropped; k++) this.#view.resume();
		this.#view.touch();
		return entry.snapshot;
	}

	/** The snapshot a mode will restore, without leaving it. */
	snapshotOf(mode: ModeEntry['mode']): ViewSnapshot | null {
		return this.#stack.findLast((e) => e.mode === mode)?.snapshot ?? null;
	}
}
