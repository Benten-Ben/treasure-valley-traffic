import type { BackgroundLayerSpecification, LayerSpecification } from 'maplibre-gl';

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
 * | base | basemap fills and lines, rail, the temporary wash (`anchor:base`) |
 * | hillshade, aerial | the style's own |
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
 */
export const ANCHORS = {
	base: 'anchor:base',
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

/** Add a module's slotted layers in their slots at its rank, through `add` (a MapScope's addLayer). */
export function addSlotted(
	map: Orderable & object,
	layers: readonly SlottedLayer[],
	rank: number,
	add: (layer: LayerSpecification, before?: string) => void
): void {
	for (const { slot, layer } of layers) {
		add(layer, beforeSlot(map, slot, rank));
		setRank(map, layer.id, rank);
	}
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
