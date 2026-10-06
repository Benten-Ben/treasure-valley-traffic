import type { Loop } from '#lib/map/loop.js';
import type { Picker } from '#lib/map/picker.js';
import type { Overlay } from '#lib/overlay/overlay.svelte.js';
import type { SelectionState } from '#lib/state/selection.svelte.js';
import type { LayerManager } from './manager.svelte.js';

/**
 * WP2's members of the app context (docs/14 §14.8, "App context"), added by
 * module augmentation as context.ts describes. The `(map)` layout creates
 * them right after the App and before anything reads them.
 */
export interface LayerSystem {
	/** The layer manager: enabled set, modules, statuses, the Base look. */
	layers: LayerManager;
	/** The one picker (sprites, then MapLibre features, by priority). */
	picker: Picker;
	/** The render loop scheduler. */
	loop: Loop;
	/** The always-loaded 2D overlay. */
	overlay: Overlay;
	/** The one selected thing. */
	selection: SelectionState;
}

declare module '#lib/app/context.js' {
	interface AppCtx extends LayerSystem {}
}

declare module '#lib/app/app.svelte.js' {
	interface App extends LayerSystem {}
}
