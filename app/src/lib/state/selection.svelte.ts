import type { Selection } from '#lib/layers/types.js';

/**
 * The one selected thing (docs/14 §14.3, "Hover, selection and picking"):
 * exactly one thing is selected at a time, and the docked inspect card shows
 * it. The picker selects on click; cards, legends and keys select and clear.
 */
export class SelectionState {
	current = $state.raw<Selection | null>(null);
	#listeners = new Set<(s: Selection | null) => void>();

	select(s: Selection | null): void {
		const prev = this.current;
		if (prev === s || (prev && s && prev.kind === s.kind && prev.id === s.id && prev.layer === s.layer && prev.items === s.items)) return;
		this.current = s;
		for (const fn of this.#listeners) fn(s);
	}

	clear(): void {
		this.select(null);
	}

	is(kind: Selection['kind'], id: string): boolean {
		return this.current?.kind === kind && this.current.id === id;
	}

	/** Hear about every change; returns the unsubscribe. */
	listen(fn: (s: Selection | null) => void): () => void {
		this.#listeners.add(fn);
		return () => this.#listeners.delete(fn);
	}
}
