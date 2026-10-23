import type { BackgroundLayerSpecification, LayerSpecification } from 'maplibre-gl';
import type { LayerId } from '#lib/layers/types.js';
import type { FlavorName } from './flavors.js';

/**
 * Layer order (docs/14 §14.8, "Layer order").
 *
 * MapLibre renders fill, line, raster and hillshade layers into per-tile
 * textures draped on the terrain, and each *contiguous* run of them costs one
 * terrain draw per frame. The order is fixed by invisible anchor layers that
 * `buildStyle` inserts: every module inserts its layers before its own slot's
 * anchor, so the order never depends on which layer loaded first.
 *
 * Bottom to top:
 *
 * | Slot | Contents |
 * |---|---|
 * | background, earth | the basemap's own |
 * | ground | the painted ground (Valley only, hidden under Aerial; `anchor:ground`) |
 * | landcover, landuse | the basemap's fills |
 * | areas | area fills: soils, crops (`anchor:areas`) |
 * | water | the basemap's water fills and lines |
 * | water | water bodies and reaches (`anchor:water`) |
 * | surfaces | paving under the roads (hidden under Aerial; `anchor:surfaces`) |
 * | road lines | the basemap's road lines, rail and flat buildings |
 * | base | the temporary wash (`anchor:base`) |
 * | hillshade, aerial | the style's own |
 * | land | the area fills' 0.45 copies, shown over Aerial only (`anchor:land`) |
 * | streets | streets casing, speed lines (`anchor:streets`) |
 * | lanes | lane surfaces and markings, later (`anchor:lanes`) |
 * | footprints | camera view footprints and cones (`anchor:footprints`) |
 * | routes | corridor outline, underlay, ribbons, trails (`anchor:routes`) |
 * | — | end of the single draped block |
 * | buildings | `buildings-3d`, `buildings-3d-estimated` (the style's own) |
 * | scene | the 3D scene layer (`anchor:scene`) |
 * | points | stop capsules, camera icons, hub pills (`anchor:points`) |
 * | base labels | the style's own |
 * | labels | route shields, speed numbers, one-way chevrons, badges (`anchor:labels`) |
 * | overlay | the always-loaded 2D overlay (`anchor:overlay`) |
 *
 * The landscape slots (ground, areas, water, surfaces, land) are filled by the base contributions
 * (`#lib/base`, inserted by `buildStyle`) and by the landscape layers; all of them are draped types, so
 * the run from `anchor:ground` to `anchor:routes` stays one block.
 */
export const ANCHORS = {
	ground: 'anchor:ground',
	areas: 'anchor:areas',
	water: 'anchor:water',
	surfaces: 'anchor:surfaces',
	base: 'anchor:base',
	land: 'anchor:land',
	streets: 'anchor:streets',
	lanes: 'anchor:lanes',
	footprints: 'anchor:footprints',
	routes: 'anchor:routes',
	scene: 'anchor:scene',
	points: 'anchor:points',
	labels: 'anchor:labels',
	overlay: 'anchor:overlay'
} as const;

export type Slot = keyof typeof ANCHORS;

export const ANCHOR_IDS: readonly string[] = Object.values(ANCHORS);

/** An anchor: a hidden background layer, which never draws and never breaks a draped run. */
export function anchorLayer(slot: Slot): BackgroundLayerSpecification {
	return { id: ANCHORS[slot], type: 'background', layout: { visibility: 'none' } };
}

/** A layer and the slot it belongs in (each module's static layer list). */
export interface SlottedLayer {
	slot: Slot;
	layer: LayerSpecification;
	/**
	 * `'only'`: shown only while Aerial is on (the area fills' 0.45 copies in `land`);
	 * `'hide'`: hidden under Aerial (the ground, the surfaces). The manager applies it.
	 */
	aerial?: 'only' | 'hide';
	/**
	 * An area fill: one is drawn at a time, and the layer turned on last keeps its fill (plan §3.2).
	 * Its owner's def can name layers it goes off under (`LayerDef.offUnder`).
	 */
	areaFill?: true;
	/**
	 * The base flavor it draws in, as a base contribution's `looks` (plus `'clay'`, for fills that need
	 * Clay's pale ground, like the crop fills): `'both'` (the default), `'clay'` or `'valley'`. The manager
	 * hides it in the other flavor.
	 */
	looks?: 'both' | 'clay' | 'valley';
}

/**
 * Ranks within a slot, per map: slots some modules share (points, labels)
 * keep their modules in rank order, lower first, whatever loaded first. A
 * module's rank is its layer def's `order` (streets 10, transit 20, cameras 30).
 */
const RANKS = new WeakMap<object, Map<string, number>>();

interface Orderable {
	getLayer(id: string): unknown;
	getLayersOrder(): string[];
}

/**
 * Where a layer of `rank` goes in `slot` (MapLibre's `beforeId`): before the
 * first layer of a higher rank already in the slot, else before the slot's
 * anchor. Undefined when the style has no anchors (it then goes on top).
 */
export function beforeSlot(map: Orderable, slot: Slot, rank = 0, ranksOf: object = map): string | undefined {
	const anchor = ANCHORS[slot];
	if (!map.getLayer(anchor)) return undefined;
	const order = map.getLayersOrder();
	const end = order.indexOf(anchor);
	let start = end - 1;
	while (start >= 0 && !ANCHOR_IDS.includes(order[start])) start--;
	const ranks = RANKS.get(ranksOf);
	for (let i = start + 1; i < end; i++) {
		const r = ranks?.get(order[i]);
		if (r !== undefined && r > rank) return order[i];
	}
	return anchor;
}

/** Record a layer's rank (after adding it with `beforeSlot`). */
export function setRank(map: object, layerId: string, rank: number): void {
	let ranks = RANKS.get(map);
	if (!ranks) RANKS.set(map, (ranks = new Map()));
	ranks.set(layerId, rank);
}

/** What the manager gates a layer by (`SlottedLayer`'s flags), and the layer that owns it. */
export interface SlotFlags {
	aerial?: 'only' | 'hide';
	areaFill?: true;
	looks?: 'clay' | 'valley';
	/** The tray layer whose module added it; absent for a layer added without saying (then only `aerial` applies). */
	owner?: LayerId;
}

const FLAGS = new WeakMap<object, Map<string, SlotFlags>>();

/** The flagged layers on this map, by style layer id. */
export function slotFlags(map: object): ReadonlyMap<string, SlotFlags> {
	return FLAGS.get(map) ?? new Map();
}

/**
 * Add a module's slotted layers in their slots at its rank, through `add` (a MapScope's addLayer).
 * `owner` is the layer id whose module this is: with it, the manager can gate its flagged layers
 * (`slotAllowed`).
 */
export function addSlotted(
	map: Orderable & object,
	layers: readonly SlottedLayer[],
	rank: number,
	add: (layer: LayerSpecification, before?: string) => void,
	owner?: LayerId
): void {
	for (const { slot, layer, aerial, areaFill, looks: wanted } of layers) {
		add(layer, beforeSlot(map, slot, rank));
		setRank(map, layer.id, rank);
		const looks = wanted === 'clay' || wanted === 'valley' ? wanted : undefined;
		if (aerial || areaFill || looks) {
			let flags = FLAGS.get(map);
			if (!flags) FLAGS.set(map, (flags = new Map()));
			flags.set(layer.id, { aerial, areaFill, looks, owner });
		}
	}
}

/** What decides whether a flagged layer may draw. */
export interface SlotGate {
	aerial: boolean;
	/** The owner whose area fill is the one drawn (the layer turned on last that has one), or null. */
	fillOwner: LayerId | null;
	/** Owners whose area fills are off now (their `offUnder` layer is on). */
	fillsOff: ReadonlySet<LayerId>;
	/** The flavor the map is drawn in (or going to, in a crossfade); with it, `looks` is applied. */
	flavor?: FlavorName;
}

/** Whether a flagged layer may draw now (its owner's own visibility is separate: both must allow). */
export function slotAllowed(f: SlotFlags, gate: SlotGate): boolean {
	if (f.aerial === 'only' && !gate.aerial) return false;
	if (f.aerial === 'hide' && gate.aerial) return false;
	if (f.looks && gate.flavor && f.looks !== gate.flavor) return false;
	if (f.areaFill && f.owner) return gate.fillOwner === f.owner && !gate.fillsOff.has(f.owner);
	return true;
}

/**
 * The owner whose area fill draws: of the owners that have one and are on, the one turned on last
 * (`enabled` keeps the order layers were turned on).
 */
export function fillOwner(enabled: readonly LayerId[], owners: ReadonlySet<LayerId>): LayerId | null {
	for (let i = enabled.length - 1; i >= 0; i--) if (owners.has(enabled[i])) return enabled[i];
	return null;
}

/** Layer types MapLibre renders to texture and drapes on the terrain. */
export const DRAPED_TYPES: ReadonlySet<string> = new Set(['background', 'fill', 'line', 'raster', 'hillshade', 'color-relief']);

export interface OrderedLayer {
	id: string;
	type: string;
	/** Layout visibility; hidden layers neither draw nor break a run. */
	visible?: boolean;
	minzoom?: number;
	maxzoom?: number;
}

/** Whether MapLibre draws the layer at this zoom (its `isHidden`, inverted). */
export function drawn(l: OrderedLayer, zoom?: number): boolean {
	if (l.visible === false) return false;
	if (zoom === undefined) return true;
	if (l.minzoom && zoom < l.minzoom) return false;
	if (l.maxzoom && zoom >= l.maxzoom) return false;
	return true;
}

/**
 * The draped runs: each contiguous run of draped layers among the drawn ones,
 * as MapLibre's render-to-texture stacks them. With a zoom, layers outside
 * their zoom range don't count (MapLibre skips them too).
 */
export function drapedRuns(layers: readonly OrderedLayer[], zoom?: number): string[][] {
	const runs: string[][] = [];
	let open = false;
	for (const l of layers) {
		if (!drawn(l, zoom)) continue;
		if (DRAPED_TYPES.has(l.type)) {
			if (!open) runs.push([]);
			runs[runs.length - 1].push(l.id);
			open = true;
		} else open = false;
	}
	return runs;
}

/** How many terrain draws a frame costs: the number of draped runs. The target is at most 1. */
export function rttStacks(layers: readonly OrderedLayer[], zoom?: number): number {
	return drapedRuns(layers, zoom).length;
}

/** A style layer as `rttStacks` sees it. */
export function ordered(l: LayerSpecification, visible?: boolean): OrderedLayer {
	return {
		id: l.id,
		type: l.type,
		visible: visible ?? (l.layout as { visibility?: string } | undefined)?.visibility !== 'none',
		minzoom: l.minzoom,
		maxzoom: l.maxzoom
	};
}

/**
 * Insert slotted layers into a style's layer list the way modules do at run
 * time (`addSlotted` at `rank`). Pure: for tests and for checking the order a
 * set of modules would produce. `ranks` carries the ranks across calls.
 */
export function insertSlotted(
	style: readonly LayerSpecification[],
	add: readonly SlottedLayer[],
	rank = 0,
	ranks: object = {}
): LayerSpecification[] {
	const out = [...style];
	const list: Orderable = {
		getLayer: (id: string) => out.find((l) => l.id === id),
		getLayersOrder: () => out.map((l) => l.id)
	};
	for (const { slot, layer } of add) {
		const before = beforeSlot(list, slot, rank, ranks);
		const i = before ? out.findIndex((l) => l.id === before) : -1;
		if (i === -1) out.push(layer);
		else out.splice(i, 0, layer);
		setRank(ranks, layer.id, rank);
	}
	return out;
}
