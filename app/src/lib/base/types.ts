import type { Map } from 'maplibre-gl';
import type { AppCtx } from '#lib/app/context.js';
import type { LayerId } from '#lib/layers/types.js';
import type { FlavorName } from '#lib/map/flavors.js';
import type { Slot } from '#lib/map/order.js';
import type { ProtomapsGroup } from '#lib/map/style.js';

/**
 * Base contributions (landscape sprint plan §3.1 C4 and C17; S3a).
 *
 * A plugin adds to the base map (soil colours, water bodies, paving, burn scars)
 * with a `<name>.base.ts` file next to its layer folders under `#lib/base/<plugin>/`.
 * The registry finds every one by itself (`registry.ts`), so a package adds a folder and
 * never edits shared code. A contribution is plain data plus two small functions, and it
 * must never import `#lib/scene`: the scene chunk doesn't load for a base layer (docs/14 §14.9).
 *
 * `buildStyle` inserts the built contributions' layers in their slots (`#lib/map/order`),
 * in the flavor's paint, so the Valley/Clay diff covers them; the manager hides the
 * Valley-only ones in Clay and runs each layer's `show`.
 */

/** What a layer's `show` and the manager's base pass know. */
export interface BaseState {
	flavor: FlavorName;
	aerial: boolean;
	/** The data layers that are on. */
	layers: ReadonlySet<LayerId>;
}

/** Where a contribution's tiles come from. */
export type BaseSource =
	/** The shared landscape file (`tiles/manifest.json`'s `landscape` entry): these source-layers of it. */
	| { kind: 'landscape'; sourceLayers: readonly string[] }
	/** The painted ground (the manifest's `ground` entry), a raster. */
	| { kind: 'ground' }
	/** A toggled layer's route (`/api/<plugin>/tiles/<layer>/…`) used as a base: burn scars. */
	| { kind: 'tiles'; plugin: string; layer: string; minzoom: number; maxzoom: number; promoteId?: string };

/** The draped layer types a contribution may use (anything else would split the draped run). */
export type BaseLayerType = 'fill' | 'line' | 'raster';

/** Paint (or layout-free style) properties, as MapLibre takes them. */
export type PaintProps = Record<string, unknown>;

/** One style layer of a contribution. */
export interface BaseLayer {
	/** The style layer's id: `'<contribution id>.<name>'`-like, unique on the map. */
	id: string;
	type: BaseLayerType;
	slot: Slot;
	/** Rank within the slot: lower is drawn first. */
	rank: number;
	/** The source-layer it reads (landscape and tiles sources). */
	sourceLayer?: string;
	/** For a ground contribution: the sharper file around the key spots instead of the valley-wide one. */
	detail?: true;
	filter?: unknown;
	minzoom?: number;
	maxzoom?: number;
	/** Valley's paint. */
	valley: PaintProps;
	/** Clay's paint; without it the layer keeps its Valley paint in Clay (when the contribution shows in Clay). */
	clay?: PaintProps;
	/**
	 * A pure predicate over the flavor, Aerial and the layer set: markings shown in Clay only with Lanes
	 * on, say. Without it the layer shows whenever its contribution does.
	 */
	show?(state: BaseState): boolean;
	/** `'only'`: shown only over Aerial; `'hide'`: hidden under Aerial. */
	aerial?: 'only' | 'hide';
}

/** Basemap groups hidden while a contribution is built and shown. */
export interface BaseSuppress {
	groups: readonly ProtomapsGroup[];
	/** Hidden only from this zoom up (the road lines from z14). */
	fromZoom?: number;
}

/** What `live` gets. */
export interface BaseLive {
	map: Map;
	app: AppCtx;
	/** The style layer ids it added. */
	layerIds: readonly string[];
}

export interface BaseContribution {
	/** `'<plugin>.<name>'`. */
	id: string;
	/** Its row in the Base menu (drawn by S3b). */
	title: string;
	blurb: string;
	source: BaseSource;
	/** `'valley'`: shown in Valley only (hidden in Clay); `'both'`: in either. */
	looks: 'both' | 'valley';
	layers: readonly BaseLayer[];
	suppresses?: BaseSuppress;
	/** Its feature cards belong to this layer (when it's on). */
	cardsWhen?: LayerId;
	/** The credit line it adds. */
	credit: string;
	/** Runtime work such as feature-state; returns its cleanup. Runs once the contribution is built and on the map. */
	live?(ctx: BaseLive): () => void;
}

/** Why a contribution isn't on the map, or that it is built. */
export type BaseStatus = { built: true } | { built: false; reason: string };

export type { Palette } from '#lib/map/materials.js';
