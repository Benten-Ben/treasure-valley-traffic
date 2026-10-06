import type { LayerId } from '#lib/layers/types.js';
import { readLegacy, readStored, storage, writeStored } from './persisted.svelte.js';

/**
 * Which data layers are on (docs/14 §14.3, "Layers and the toolbar",
 * "Defaults and memory", "Keymap").
 *
 * - Any combination can be on. A first visit opens with Transit and Cameras.
 * - The set is saved in `tvt:v2:layers` and in the URL hash (`layers=`).
 *   Precedence: URL, then saved, then defaults. The old `tvt-lens` value
 *   migrates once into a one-layer set.
 * - 1 turns every data layer off, and again restores them; Shift+digit solos
 *   a layer, and again restores the set from before the solo.
 * - The list keeps the order layers were turned on, so the last one is the
 *   most recently turned on (its legend is the expanded one).
 */
export const LAYERS_KEY = 'layers';
export const LEGACY_LENS_KEY = 'tvt-lens';
export const DEFAULT_LAYERS: readonly LayerId[] = ['transit', 'cameras'];

const unique = <T>(xs: T[]) => [...new Set(xs)];

/** `streets,transit` → the known ids, in order; 'none' or '' → []; null when there's nothing to read. */
export function parseLayerList(raw: string | null | undefined, known: readonly string[]): LayerId[] | null {
	if (raw === null || raw === undefined) return null;
	const s = raw.trim();
	if (s === '' || s === 'none') return [];
	return unique(s.split(',').map((x) => x.trim()).filter((x) => known.includes(x))) as LayerId[];
}

export function formatLayerList(ids: readonly string[]): string {
	return ids.length ? ids.join(',') : 'none';
}

export const sameSet = (a: readonly string[], b: readonly string[]) => a.length === b.length && a.every((x) => b.includes(x));

export type LayersSource = 'url' | 'saved' | 'legacy' | 'default';

export function chooseLayers(o: {
	/** The hash's `layers=` value, or null without one. */
	url: string | null;
	saved: unknown;
	legacyLens: string | null;
	known: readonly string[];
	defaults?: readonly LayerId[];
}): { ids: LayerId[]; source: LayersSource } {
	const fromUrl = parseLayerList(o.url, o.known);
	if (fromUrl) return { ids: fromUrl, source: 'url' };
	if (Array.isArray(o.saved)) {
		const ids = parseLayerList(o.saved.filter((x) => typeof x === 'string').join(',') || 'none', o.known);
		if (ids) return { ids, source: 'saved' };
	}
	if (o.legacyLens && o.known.includes(o.legacyLens)) return { ids: [o.legacyLens as LayerId], source: 'legacy' };
	return { ids: [...(o.defaults ?? DEFAULT_LAYERS)].filter((x) => o.known.includes(x)), source: 'default' };
}

/** Read the saved set (and the old lens) from storage. */
export function storedLayers(): { saved: unknown; legacyLens: string | null } {
	return { saved: readStored<unknown>(LAYERS_KEY), legacyLens: readLegacy(LEGACY_LENS_KEY) };
}

/** Save the set; the old lens key goes once the new one is written. */
export function saveLayers(ids: readonly LayerId[]): void {
	if (!writeStored(LAYERS_KEY, ids)) return;
	try {
		storage()?.removeItem(LEGACY_LENS_KEY);
	} catch {
		/* per-viewer convenience only */
	}
}

export class LayerSet {
	/** The layers that are on, in the order they were turned on. */
	enabled = $state.raw<LayerId[]>([]);
	/** The layer the viewer acted on last (toggled either way), or the last of the first set. */
	last = $state<LayerId | null>(null);
	#beforeAllOff: LayerId[] | null = null;
	#beforeSolo: LayerId[] | null = null;

	constructor(initial: readonly LayerId[] = []) {
		this.enabled = unique([...initial]);
		this.last = this.enabled.at(-1) ?? null;
	}

	has(id: LayerId): boolean {
		return this.enabled.includes(id);
	}

	/** Replace the set (a snapshot restore, a typed hash): forgets the 1 and solo memories. */
	replace(ids: readonly LayerId[]): void {
		this.#beforeAllOff = null;
		this.#beforeSolo = null;
		this.enabled = unique([...ids]);
	}

	setOn(id: LayerId, on: boolean): void {
		this.#beforeAllOff = null;
		this.#beforeSolo = null;
		this.last = id;
		const without = this.enabled.filter((x) => x !== id);
		this.enabled = on ? [...without, id] : without;
	}

	toggle(id: LayerId): boolean {
		const on = !this.has(id);
		this.setOn(id, on);
		return on;
	}

	/** Shift+digit: only this layer; again (while still solo) puts the earlier set back. */
	solo(id: LayerId): void {
		this.last = id;
		const isSolo = this.enabled.length === 1 && this.enabled[0] === id;
		if (isSolo && this.#beforeSolo) {
			this.enabled = this.#beforeSolo;
			this.#beforeSolo = null;
			return;
		}
		// Switching from one solo to another keeps the set from before the first.
		if (!(this.#beforeSolo && this.enabled.length === 1)) this.#beforeSolo = this.enabled;
		this.#beforeAllOff = null;
		this.enabled = [id];
	}

	/** 1: every data layer off; again (while still all off) puts them back. */
	allOff(): void {
		if (this.enabled.length) {
			this.#beforeAllOff = this.enabled;
			this.#beforeSolo = null;
			this.enabled = [];
		} else if (this.#beforeAllOff) {
			this.enabled = this.#beforeAllOff;
			this.#beforeAllOff = null;
		}
	}
}
