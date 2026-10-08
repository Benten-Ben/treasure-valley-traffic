import type { Component } from 'svelte';
import type { MapGeoJSONFeature } from 'maplibre-gl';
import type { AppCtx } from '#lib/app/context.js';
import type { DataMeta } from '#lib/contracts/meta.js';
import type { IconData } from '#lib/ui/icons.js';

/**
 * The layer registry contract (docs/14 §14.8, "Layer registry").
 *
 * A layer is a folder under `#lib/layers/` with a `def.ts` whose default
 * export is a `LayerDef`. The registry finds every `def.ts` by itself, so a
 * later package adds a layer (road weather, lanes) by adding its folder, not
 * by editing the registry. The def is small and always loaded (the toolbar
 * needs its icon); `load()` imports the module itself, its own chunk (≤ 30 KB
 * brotli), the first time the layer is switched on or prefetched.
 */
export type LayerId = 'streets' | 'transit' | 'cameras' | 'lanes' | 'weather' | 'trees';

/** idle: not loaded yet; loading; ready; stale: shown but its feed is old; error. */
export type LayerStatus = 'idle' | 'loading' | 'ready' | 'stale' | 'error';

/**
 * What can be selected, and its picking priority (§14.3: bus > camera > hub > stop > route > lane > street).
 * Trees (docs/19) rank just under streets: crowns line the streets, so a click on a road under one
 * still opens the road, and a click on the crown away from it opens the tree.
 */
export const PRIORITY = {
	bus: 100,
	camera: 90,
	weather: 85,
	hub: 80,
	stop: 70,
	route: 60,
	lane: 50,
	street: 40,
	tree: 35,
	sprite: 30
} as const;

export type SelectionKind = keyof typeof PRIORITY | 'routes';

/** A numbered plate: route shields, bus plates, legend and card badges (the badge rule, §14.3). */
export interface Badge {
	text: string;
	color: string;
	textColor: string;
	/** The numerals need a 2 px halo in the opposite tone to reach 4.5:1. */
	halo?: boolean;
}

/** The one selected thing (§14.3, "Hover, selection and picking"). */
export interface Selection {
	kind: SelectionKind;
	/** Unique within its kind. */
	id: string;
	/** The layer that owns it (its module's Card shows it), or another owner such as 'overlay-test'. */
	layer: string;
	/** Name, for the card heading and the hover tooltip. */
	title: string;
	/** One fact for the tooltip ("18 mph", "Calibrated"). */
	fact?: string;
	/** Source and age for the tooltip ("ACHD road centerlines"). */
	source?: string;
	badge?: Badge;
	/** A point to ring on the map while selected (cameras, stops); things that move ring themselves. */
	at?: [number, number];
	/** Owner-specific data the card reads. */
	data?: unknown;
	/** For 'routes' (several routes share the street here): each one's own selection. */
	items?: Selection[];
}

/** A stat chip in the top bar (§14.3): "38 buses", "11 calibrated". */
export interface Chip {
	id: string;
	text: string;
	/** Hover: its source and age. */
	title: string;
	/** ▲: its feed is 2 minutes old or more. */
	stale?: boolean;
}

/** MapLibre layers a module makes clickable, and how a feature becomes a selection. */
export interface Interactive {
	layerIds: string[];
	priority: number;
	pick(f: MapGeoJSONFeature): Selection | null;
}

/** A Phosphor icon component (deep import, `phosphor-svelte/lib/<Name>Icon`), drawn duotone. */
export type IconComponent = Component<{ weight?: 'duotone'; size?: number | string; 'aria-hidden'?: 'true' }>;

/** A Phosphor duotone icon: its paths (`#lib/ui/icons.ts`, cheap) or a phosphor-svelte component. */
export type Icon = IconData | IconComponent;

export interface LayerDef {
	id: LayerId;
	title: string;
	/** A Phosphor duotone icon (`#lib/ui/icons.ts`, or a phosphor-svelte deep import). */
	icon: Icon;
	/** Its toggle key, by digit: '2', '4', '7' (ch. 13's numbers). */
	key?: string;
	/** Toolbar order, left to right. */
	order: number;
	/** One line on what it shows (tooltip). */
	blurb: string;
	/** Where its data comes from (tooltip, legend credit). */
	source: string;
	/** What the legend row says while it loads: "Loading routes…". */
	loadingText?: string;
	/** true, or the reason it can't be used yet (the button is disabled with it). */
	available(meta: DataMeta | null): true | string;
	/**
	 * Start the layer's data fetch while its chunk is still loading (through
	 * `#lib/layers/prefetch.ts`, whose `take` the module then uses).
	 */
	prefetch?(ctx: AppCtx): void;
	/** Import the module (its own chunk) and create it. */
	load(): Promise<LayerModule>;
}

export interface LegendProps {
	module: LayerModule;
}

export interface CardProps {
	selection: Selection;
	module: LayerModule;
}

export interface LayerModule {
	/** Start its data fetch at once (before awaiting `ctx.styleReady`), then add its hidden layers. Rejects on failure. */
	mount(ctx: AppCtx): Promise<void>;
	/** Layout visibility only; loaded layers stay mounted while hidden. */
	setVisible(on: boolean): void;
	interactive: Interactive[];
	Legend?: Component<LegendProps>;
	Card?: Component<CardProps>;
	chips?(): Chip[];
	/** Reactive. */
	readonly status: LayerStatus;
	/** Why it's in error, in words. */
	readonly error?: string | null;
	/** When its data last arrived (epoch ms), for "source and age". */
	readonly updatedAt?: number | null;
	/** Counts for the loading card: "42 routes". */
	summary?(): string | null;
	/** The selection changed (to one of its own, or to anything else). */
	selected?(s: Selection | null): void;
	destroy(): void;
}
