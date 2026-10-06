import type { LayerDef } from './types.js';

/**
 * The layer registry (docs/14 §14.8). Every `#lib/layers/<name>/def.ts` is
 * found here at build time, so a package adds a layer by adding its folder
 * (road weather, lanes) and never edits this file. Defs are small and part of
 * the initial bundle; each module itself is a dynamic import.
 */
const found = import.meta.glob<{ default: LayerDef }>('./*/def.ts', { eager: true });

export const LAYER_DEFS: readonly LayerDef[] = Object.values(found)
	.map((m) => m.default)
	.sort((a, b) => a.order - b.order);

export const LAYER_IDS: readonly string[] = LAYER_DEFS.map((d) => d.id);

export function layerDef(id: string): LayerDef | undefined {
	return LAYER_DEFS.find((d) => d.id === id);
}
