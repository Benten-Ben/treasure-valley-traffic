import { createContext } from 'svelte';
import type { Map } from 'maplibre-gl';
import type { DataMeta } from '#lib/contracts/meta.js';
import type { BasemapManifest } from '#lib/map/style.js';
import type { Modes } from '#lib/state/modes.svelte.js';
import type { ViewManager } from '#lib/state/view.svelte.js';

/**
 * The app context (docs/14 §14.8, "App context, boot and the view"): one per
 * visit, created by the `(map)` layout, read by every panel, page and layer
 * module with `getAppCtx()`.
 *
 * This is the part WP1 builds. Later packages add their members (`layers`,
 * `picker`, `loop`, `overlay` from WP2; `clock`, `windows`, `selection`
 * from WP2, WP3 and WP8; `scene()` from WP9) by module augmentation from their
 * own files, without editing this one:
 *
 * ```ts
 * declare module '#lib/app/context.js' {
 *   interface AppCtx { layers: LayerManager }
 * }
 * ```
 */
export type AppStatus = 'loading' | 'ready' | 'unavailable' | 'error';

export interface AppCtx {
	/** The one MapLibre map ($state.raw); null until MapHost has created it. */
	readonly map: Map | null;
	readonly manifest: BasemapManifest | null;
	readonly status: AppStatus;
	/** Why the map is unavailable or failed, in words. */
	readonly problem: string | null;
	/** Resolves on the style's `style.load` (not the full `load`); rejects when the map is unavailable. */
	readonly styleReady: Promise<Map>;
	/** Data versions from /api/meta; null until (or unless) it answers. */
	readonly meta: DataMeta | null;
	readonly view: ViewManager;
	readonly modes: Modes;
	/** The NAIP imagery is shown. */
	readonly aerial: boolean;
	/** Show or hide the imagery, adding its sources the first time. Returns whether it's on. */
	setAerial(on: boolean): boolean;
	/** The live terrain exaggeration (1 without terrain): the one place code reads it. */
	exaggeration(): number;
	setExaggeration(value: number): void;
	/** WebGL context lost: the map is paused. */
	readonly paused: boolean;
	/** How many maps this visit has created (one, always). */
	readonly mapsCreated: number;
	/** Resolves once navigation, mode changes and the map have settled (the map's next `idle`). */
	whenReady(): Promise<void>;
	/** Count a promise (a mode change in progress) as unsettled until it ends. */
	track<T>(p: Promise<T>): Promise<T>;
	/** `path?v=<version>` from /api/meta (see boot.ts). */
	dataUrl(path: string, version?: keyof DataMeta['versions']): Promise<string>;
	/** Say that some data changed here (e.g. 'cameras' after a calibration is saved). */
	notify(topic: DataTopic): void;
	/** Hear about it; returns the unsubscribe. */
	subscribe(topic: DataTopic, fn: () => void): () => void;
}

/** What `notify` can say changed. */
export type DataTopic = 'cameras';

export const [getAppCtx, setAppCtx] = createContext<AppCtx>();
