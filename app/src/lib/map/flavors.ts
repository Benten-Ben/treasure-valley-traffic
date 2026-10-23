import type { Flavor } from '@protomaps/basemaps';
import type { LayerSpecification, Map as GlMap } from 'maplibre-gl';
import type { StyleSpecification } from 'maplibre-gl';
import { BASE_CONTRIBUTIONS } from '#lib/base/registry.js';
import type { BaseContribution, BaseLayer, BaseState, BaseStatus } from '#lib/base/types.js';
import { layerSource, layerVersion } from '#lib/contracts/layer-tiles.js';
import type { DataMeta } from '#lib/contracts/meta.js';
import { beforeSlot, setRank } from './order.js';
import {
	BUILDING_OPACITY,
	BUILDINGS_LAYERS,
	IMAGERY_LAYERS,
	PROTOMAPS_GROUPS,
	pmtilesUrl,
	type BasemapManifest,
	type MapLike,
	type ProtomapsGroup
} from './style.js';

export { BUILDINGS_ESTIMATED_LAYER, BUILDINGS_LAYER, BUILDINGS_LAYERS, buildingOpacity, HILLSHADE_LAYER, IMAGERY_LAYERS } from './style.js';

/**
 * The base flavors (docs/14 §14.5 "Base flavors"; §14.3 "Base").
 *
 * Two variants of Protomaps' `light` flavor, built into the same layer ids:
 *
 * - **Valley**, ch. 13's normal look: warm sand ground, soft greens,
 *   turquoise water, white roads with warm casings.
 * - **Clay**, the backdrop for data (Base on Auto switches to it whenever a
 *   data layer is on): paler ground, very pale greens, blue-gray water,
 *   thinner-looking roads, fewer labels.
 *
 * The map is built in Valley. Switching diffs the two flavors' paint
 * properties once (`clayPaintDiff`) and applies one side with
 * `setPaintProperty` and a 350 ms transition, instant under reduced motion.
 * Address labels, POIs, the basemap's one-way arrows, minor road labels and
 * shields are hidden in Clay (`CLAY_HIDDEN`). On Aerial, Clay lowers the
 * imagery's saturation instead.
 *
 * `style.ts` loads this module with the Protomaps style module, apart from
 * the initial JavaScript, and builds the layers; this module never imports
 * the Protomaps module at run time itself.
 */

export type FlavorName = 'valley' | 'clay';
export const FLAVOR_NAMES: readonly FlavorName[] = ['valley', 'clay'];

/** The crossfade between flavors (ch. 13's lens switch: about 350 ms). */
export const FLAVOR_FADE_MS = 350;

/** Ground colors: ch. 13's sand, and the clay surface every route color is validated against. */
export const GROUND = { valley: '#eee7da', clay: '#f3ede2' } as const;

const INK = '#2b2a33';
const INK_SOFT = '#5d5a66';
const CREAM = '#fffbf4';

/** Roads by weight, as Protomaps' flavor fields name them. */
const MAJOR_ROADS = ['major', 'highway', 'link', 'bridges_major', 'bridges_highway', 'bridges_link'] as const;
const MAJOR_CASINGS = [
	'major_casing_early',
	'major_casing_late',
	'highway_casing_early',
	'highway_casing_late',
	'link_casing',
	'bridges_major_casing',
	'bridges_highway_casing',
	'bridges_link_casing'
] as const;
const MINOR_ROADS = ['minor_a', 'minor_b', 'minor_service', 'other', 'bridges_minor', 'bridges_other'] as const;
const MINOR_CASINGS = ['minor_casing', 'minor_service_casing', 'bridges_minor_casing', 'bridges_other_casing'] as const;
/** Land use other than parks and woods ("as light" in Valley). */
const OTHER_LANDUSE = [
	'hospital',
	'industrial',
	'school',
	'pedestrian',
	'glacier',
	'sand',
	'beach',
	'aerodrome',
	'runway',
	'zoo',
	'military',
	'pier'
] as const;

type ColorKey = { [K in keyof Flavor]: Flavor[K] extends string ? K : never }[keyof Flavor];
const fill = (keys: readonly ColorKey[], color: string): Partial<Flavor> => Object.fromEntries(keys.map((k) => [k, color]));

/** Labels: ink for places, ink-soft for the rest, cream halos (§14.5; ch. 13 tokens). */
const LABELS: Partial<Flavor> = {
	city_label: INK,
	state_label: INK_SOFT,
	country_label: INK_SOFT,
	subplace_label: INK_SOFT,
	roads_label_major: INK_SOFT,
	roads_label_minor: INK_SOFT,
	address_label: INK_SOFT,
	ocean_label: INK_SOFT,
	city_label_halo: CREAM,
	state_label_halo: CREAM,
	subplace_label_halo: CREAM,
	roads_label_major_halo: CREAM,
	roads_label_minor_halo: CREAM,
	address_label_halo: CREAM
};

/** Valley: ch. 13's normal look, over Protomaps' `light`. */
export const VALLEY_OVERRIDES: Partial<Flavor> = {
	background: GROUND.valley,
	earth: GROUND.valley,
	park_a: '#d3e3b4',
	park_b: '#b9d88f',
	wood_a: '#cbddae',
	wood_b: '#a9cf85',
	// Scrub, grassland and grass (most of the Foothills) share Protomaps' park layer with the
	// woods; light's teal (#99d2bb) fights the sand, so they take the pale woods green.
	scrub_a: '#cbddae',
	scrub_b: '#cbddae',
	water: '#7cc4e4',
	buildings: '#e4dacb',
	...fill(MAJOR_ROADS, '#ffffff'),
	...fill(MAJOR_CASINGS, '#e3d7c4'),
	...fill(MINOR_ROADS, '#ffffff'),
	...fill(MINOR_CASINGS, '#e8dfd0'),
	...LABELS
};

/** Clay: the pale backdrop for data. */
export const CLAY_OVERRIDES: Partial<Flavor> = {
	background: GROUND.clay,
	earth: GROUND.clay,
	park_a: '#e4e8d6',
	park_b: '#e4e8d6',
	wood_a: '#e4e8d6',
	wood_b: '#e4e8d6',
	scrub_a: '#e4e8d6',
	scrub_b: '#e4e8d6',
	...fill(OTHER_LANDUSE, '#eee8de'),
	water: '#c9dce3',
	buildings: '#e9e2d6',
	...fill(MAJOR_ROADS, '#fbf8f2'),
	...fill(MAJOR_CASINGS, '#e2d9cb'),
	...fill(MINOR_ROADS, '#f8f4ec'),
	...fill(MINOR_CASINGS, '#e9e1d4'),
	...LABELS,
	// Place labels step back to ink-soft.
	city_label: INK_SOFT
};

export const OVERRIDES: Record<FlavorName, Partial<Flavor>> = { valley: VALLEY_OVERRIDES, clay: CLAY_OVERRIDES };

/** A flavor: Protomaps' base flavor (the manifest's, `light`) with our overrides. */
export function flavorOf(base: Flavor, name: FlavorName): Flavor {
	const o = OVERRIDES[name];
	return {
		...base,
		...o,
		...(base.pois || o.pois ? { pois: { ...base.pois, ...o.pois } as Flavor['pois'] } : {}),
		...(base.landcover || o.landcover ? { landcover: { ...base.landcover, ...o.landcover } as Flavor['landcover'] } : {})
	};
}

/** Basemap layers hidden in Clay (§14.5): address labels, POIs, one-way arrows, minor road labels, shields. */
export const CLAY_HIDDEN: readonly string[] = ['address_label', 'pois', 'roads_oneway', 'roads_labels_minor', 'roads_shields'];

/** The hillshade (§14.5): Valley 0.3 with a warm shadow; Clay softer, with a cream highlight. */
export const HILLSHADE_PAINT: Record<FlavorName, Record<string, unknown>> = {
	valley: { 'hillshade-exaggeration': 0.3, 'hillshade-shadow-color': '#7a6e60', 'hillshade-highlight-color': '#ffffff' },
	clay: { 'hillshade-exaggeration': 0.22, 'hillshade-shadow-color': '#9b9184', 'hillshade-highlight-color': CREAM }
};

/** 3D buildings: cream blocks in Valley, light gray-cream and see-through in Clay. */
export const BUILDINGS_PAINT: Record<FlavorName, { color: string; opacity: number }> = {
	valley: { color: '#f8f4ec', opacity: BUILDING_OPACITY.valley },
	clay: { color: '#efe9df', opacity: BUILDING_OPACITY.clay }
};

/**
 * 3D buildings drawn at an estimated height (no height in the data, or 0 m:
 * `#lib/map/buildings`): a slightly lighter tone than the measured ones,
 * ΔE 3.3–3.4 (OKLab ×100) in both flavors, so the map still tells measured
 * from guessed. In Valley that's as far as white allows. The opacity is the
 * measured blocks', Aerial's included.
 */
export const ESTIMATED_BUILDINGS_PAINT: Record<FlavorName, { color: string; opacity: number }> = {
	valley: { color: '#ffffff', opacity: BUILDING_OPACITY.valley },
	clay: { color: '#f7f4ef', opacity: BUILDING_OPACITY.clay }
};

/** Building opacity while Aerial is on, in either flavor (see style.ts). */
export const AERIAL_BUILDING_OPACITY = BUILDING_OPACITY.aerial;

/** On Aerial, Clay mutes the photo instead of repainting the ground. */
export const AERIAL_SATURATION: Record<FlavorName, number> = { valley: 0, clay: -0.7 };

// -- the diff ----------------------------------------------------------------------------------------

/** One paint property that differs between the flavors. */
export interface PaintChange {
	layer: string;
	property: string;
	valley: unknown;
	clay: unknown;
}

function deepEqual(a: unknown, b: unknown): boolean {
	if (a === b) return true;
	if (typeof a !== 'object' || typeof b !== 'object' || a === null || b === null) return false;
	if (Array.isArray(a) !== Array.isArray(b)) return false;
	const ka = Object.keys(a);
	const kb = Object.keys(b);
	if (ka.length !== kb.length) return false;
	return ka.every((k) => deepEqual((a as Record<string, unknown>)[k], (b as Record<string, unknown>)[k]));
}

/**
 * Every paint property that differs between the Valley and Clay builds of
 * the same layers. The two lists must hold the same layer ids in the same
 * order, with the same layout (flavors change paint only).
 */
export function clayPaintDiff(valley: readonly LayerSpecification[], clay: readonly LayerSpecification[]): PaintChange[] {
	if (valley.length !== clay.length || valley.some((l, i) => l.id !== clay[i].id))
		throw new Error('The Valley and Clay flavors must build the same layers in the same order.');
	const out: PaintChange[] = [];
	valley.forEach((v, i) => {
		const c = clay[i];
		// Paint only, except `visibility`: a Valley-only base layer is hidden in Clay (the manager's base pass
		// shows and hides it; `#lib/map/style` `syncContributions`).
		const { visibility: _v, ...vl } = (v.layout ?? {}) as Record<string, unknown>;
		const { visibility: _c, ...cl } = (c.layout ?? {}) as Record<string, unknown>;
		void _v, void _c;
		if (!deepEqual(vl, cl)) throw new Error(`The flavors differ in ${v.id}'s layout; flavors change paint only.`);
		const vp = (v as { paint?: Record<string, unknown> }).paint ?? {};
		const cp = (c as { paint?: Record<string, unknown> }).paint ?? {};
		for (const property of new Set([...Object.keys(vp), ...Object.keys(cp)])) {
			if (!deepEqual(vp[property], cp[property])) out.push({ layer: v.id, property, valley: vp[property], clay: cp[property] });
		}
	});
	return out;
}

// -- applying a flavor to the map -----------------------------------------------------------------------

/** The parts of a MapLibre map applying a flavor needs (tests pass a fake). */
export type FlavorMap = Pick<GlMap, 'getLayer' | 'setPaintProperty' | 'getLayoutProperty'>;

const applied = new WeakMap<object, FlavorName>();
const trueColor = new WeakMap<object, boolean>();

/** The flavor last applied to this map (Valley, which the style is built in, until then). */
export function appliedFlavor(map: object): FlavorName {
	return applied.get(map) ?? 'valley';
}

/** The aerial photo's saturation on this map now: muted in Clay, unless a mode wants it as it is. */
export function photoSaturation(map: object): number {
	return trueColor.get(map) ? 0 : AERIAL_SATURATION[appliedFlavor(map)];
}

/**
 * Show the aerial photo in full color whatever the flavor (a mode such as
 * calibrating, which matches the photo against a camera's picture), or back
 * as the flavor has it. A constant raster paint change: nothing is laid out
 * again.
 */
export function setTrueColorPhoto(map: FlavorMap, on: boolean): void {
	trueColor.set(map, on);
	const set = map.setPaintProperty.bind(map) as (layer: string, key: string, v: unknown) => void;
	for (const id of IMAGERY_LAYERS) if (map.getLayer(id)) set(id, 'raster-saturation', photoSaturation(map));
}

/** Whether the aerial photo shows on this map. */
export function aerialShown(map: Pick<GlMap, 'getLayer' | 'getLayoutProperty'>): boolean {
	return Boolean(map.getLayer(IMAGERY_LAYERS[0])) && map.getLayoutProperty(IMAGERY_LAYERS[0], 'visibility') !== 'none';
}

/**
 * Switch the map to a flavor: every changed paint property, each with a
 * transition of `duration` ms (0 = instant). Layers not on the map (the
 * imagery before Aerial's first use) are skipped. Building opacity follows
 * Aerial. The data layers' registered paints (`registerFlavorPaint`) go with it. Returns the number of
 * properties set (0 when already applied).
 */
export function applyFlavor(map: FlavorMap, diff: readonly PaintChange[], name: FlavorName, opts: { duration?: number; force?: boolean } = {}): number {
	if (!opts.force && applied.has(map) && applied.get(map) === name) return 0;
	const duration = Math.max(0, opts.duration ?? FLAVOR_FADE_MS);
	const aerial = aerialShown(map);
	// Paint keys and their `-transition` keys, which MapLibre's types don't list.
	const set = map.setPaintProperty.bind(map) as (layer: string, key: string, v: unknown) => void;
	let n = 0;
	for (const ch of diff) {
		if (!map.getLayer(ch.layer)) continue;
		let value = ch[name];
		if (aerial && BUILDINGS_LAYERS.includes(ch.layer) && ch.property === 'fill-extrusion-opacity') value = AERIAL_BUILDING_OPACITY;
		if (trueColor.get(map) && IMAGERY_LAYERS.includes(ch.layer) && ch.property === 'raster-saturation') value = 0;
		set(ch.layer, `${ch.property}-transition`, { duration, delay: 0 });
		set(ch.layer, ch.property, value);
		n++;
	}
	for (const [layer, paint] of dataPaints.get(map) ?? []) n += setDataPaint(map, layer, paint, name, duration);
	applied.set(map, name);
	return n;
}

// -- data layers' flavor paints -----------------------------------------------------------------------------------

/** A data layer's MapLibre layer in each flavor (paint properties). */
export interface DataPaint {
	valley: Record<string, unknown>;
	clay: Record<string, unknown>;
}

const dataPaints = new WeakMap<object, Map<string, DataPaint>>();

type PaintSetter = (layer: string, key: string, v: unknown) => void;

function setDataPaint(map: FlavorMap, layer: string, paint: DataPaint, name: FlavorName, duration: number): number {
	if (!map.getLayer(layer)) return 0;
	const set = map.setPaintProperty.bind(map) as PaintSetter;
	let n = 0;
	for (const [property, value] of Object.entries(paint[name])) {
		set(layer, `${property}-transition`, { duration, delay: 0 });
		set(layer, property, value);
		n++;
	}
	return n;
}

/**
 * A data layer's module registers a MapLibre layer's Valley and Clay paints (a few properties, such as
 * a fence's color), and the manager keeps it in step with the Base look: the current flavor goes on at
 * once (a late layer gets the current look, not Valley's), and every later switch includes it in the
 * 350 ms crossfade (`applyFlavor`). Properties not named are the layer's own, in both flavors. Returns
 * the unregister. Call it after the layer is on the map; a layer not on the map is skipped.
 */
export function registerFlavorPaint(map: FlavorMap & object, layer: string, paint: DataPaint): () => void {
	let layers = dataPaints.get(map);
	if (!layers) dataPaints.set(map, (layers = new Map()));
	layers.set(layer, paint);
	setDataPaint(map, layer, paint, appliedFlavor(map), 0);
	return () => void dataPaints.get(map)?.delete(layer);
}

/** The data layers registered on this map. */
export function registeredFlavorLayers(map: object): string[] {
	return [...(dataPaints.get(map)?.keys() ?? [])];
}

/** The parts of a map the drape keeper needs (tests pass a fake). */
export interface DrapedMap {
	on(type: 'render', fn: () => void): unknown;
	off(type: 'render', fn: () => void): unknown;
	triggerRepaint(): void;
	getTerrain(): unknown;
	readonly terrain?: { tileManager: { releaseAllRTT(): void } } | null;
}

/**
 * Keep the terrain drape in step with a paint transition for `ms`.
 *
 * With terrain on, MapLibre (6.12) draws fill, line, raster and hillshade
 * layers into a cached texture per terrain tile, and redraws a texture only
 * when its tiles, zoom, visible layers or feature state change, or once right
 * after a style change. A paint transition's later frames change none of
 * those, so the drape keeps the transition's first frame (the old flavor)
 * until something else redraws it: for a flavor switch, the basemap's
 * re-layout (its data-driven colors changed) when it lands, a jump rather
 * than a fade; for constant paint only, not until the map moves. While the
 * crossfade runs, this releases the cached textures after every frame, and
 * once more after it ends, so the drape shows each step and then the final
 * colors. Returns a cancel.
 */
export function keepDrapeFresh(map: DrapedMap, ms: number, now: () => number = () => performance.now()): () => void {
	const until = now() + ms;
	let done = false;
	const release = () => {
		if (map.getTerrain()) map.terrain?.tileManager.releaseAllRTT();
	};
	const onRender = () => {
		release();
		if (now() >= until) stop();
		map.triggerRepaint();
	};
	const stop = () => {
		if (done) return;
		done = true;
		map.off('render', onRender);
	};
	map.on('render', onRender);
	release();
	map.triggerRepaint();
	return stop;
}

/**
 * Basemap labels hidden for a flavor and the Base popover's Labels setting:
 * Clay hides its set, and "Fewer" hides the same set in either flavor.
 */
export function hiddenBaseLabels(flavor: FlavorName, labels: 'full' | 'fewer'): Set<string> {
	return new Set(flavor === 'clay' || labels === 'fewer' ? CLAY_HIDDEN : []);
}

/** Whether the viewer asked for reduced motion (then flavors switch instantly). */
export function prefersReducedMotion(): boolean {
	try {
		return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
	} catch {
		return false;
	}
}

// -- base contributions (S3a), applied to the map -----------------------------------------------------------------------------------

/**
 * Whether a contribution is built, or why not (the Base menu says it). **Built** means: every
 * source-layer it names is in the landscape entry's `layers` (never one listed under `empty`); the
 * ground entry's status is `painted`; a toggled layer's tiles have a version in /api/meta. An unbuilt
 * contribution adds nothing to the map and hides nothing.
 */
export function contributionStatus(c: BaseContribution, m: BasemapManifest, meta?: Pick<DataMeta, 'versions'> | null): BaseStatus {
	const notYet: BaseStatus = { built: false, reason: 'not built yet' };
	switch (c.source.kind) {
		case 'landscape': {
			const e = m.landscape;
			if (!e) return notYet;
			if (e.status !== 'baked') return { built: false, reason: e.reason || notYet.reason };
			const missing = c.source.sourceLayers.filter((n) => !(n in e.layers) || e.empty.includes(n));
			return missing.length ? notYet : { built: true };
		}
		case 'ground': {
			const e = m.ground;
			if (!e) return notYet;
			return e.status === 'painted' ? { built: true } : { built: false, reason: e.reason || notYet.reason };
		}
		case 'tiles':
			return layerVersion(meta, c.source.plugin, c.source.layer) ? { built: true } : notYet;
	}
}

/** The style source id a contribution's layer reads. */
function sourceId(c: BaseContribution, l: BaseLayer): string {
	switch (c.source.kind) {
		case 'landscape':
			return 'landscape';
		case 'ground':
			return l.detail ? 'groundDetail' : 'ground';
		case 'tiles':
			return `${c.source.plugin}.${c.source.layer}`;
	}
}

/**
 * The style sources a built contribution needs: the shared landscape vector source (the entry's
 * zooms, `promoteId` and attribution), the ground's two rasters, or a toggled layer's versioned tiles.
 */
export function contributionSources(
	c: BaseContribution,
	m: BasemapManifest,
	origin: string,
	meta?: DataMeta | null
): StyleSpecification['sources'] {
	switch (c.source.kind) {
		case 'landscape': {
			const e = m.landscape;
			if (e?.status !== 'baked') return {};
			return {
				landscape: {
					type: 'vector',
					url: pmtilesUrl(origin, e.file),
					minzoom: e.minzoom,
					maxzoom: e.maxzoom,
					promoteId: e.promoteId,
					attribution: e.attribution
				}
			};
		}
		case 'ground': {
			const e = m.ground;
			if (e?.status !== 'painted') return {};
			return {
				ground: { type: 'raster', url: pmtilesUrl(origin, e.file), tileSize: e.tileSize, attribution: e.attribution },
				groundDetail: { type: 'raster', url: pmtilesUrl(origin, e.detail.file), tileSize: e.tileSize }
			};
		}
		case 'tiles': {
			const { plugin, layer, minzoom, maxzoom, promoteId } = c.source;
			return { [`${plugin}.${layer}`]: layerSource(origin, meta, plugin, layer, { minzoom, maxzoom, promoteId }) };
		}
	}
}

/** Whether a contribution's layer draws in this state (it is built; the manager's pass applies this). */
export function layerShown(c: BaseContribution, l: BaseLayer, state: BaseState): boolean {
	if ((c.looks === 'valley' || c.source.kind === 'ground') && state.flavor !== 'valley') return false;
	if (l.aerial === 'only' && !state.aerial) return false;
	if (l.aerial === 'hide' && state.aerial) return false;
	return l.show ? l.show(state) : true;
}

/** A contribution's layer as a style layer, in the flavor's paint and shown or hidden as `state` says. */
export function contributionLayer(c: BaseContribution, l: BaseLayer, state: BaseState, m?: BasemapManifest): LayerSpecification {
	const paint = state.flavor === 'clay' && l.clay ? l.clay : l.valley;
	// The ground's detail layer starts where the built file does (the manifest's `detail.minzoom`), not at a copy of it here.
	const minzoom = l.detail && c.source.kind === 'ground' && m?.ground?.status === 'painted' ? m.ground.detail.minzoom : l.minzoom;
	return {
		id: l.id,
		type: l.type,
		source: sourceId(c, l),
		...(l.sourceLayer ? { 'source-layer': l.sourceLayer } : {}),
		...(l.filter ? { filter: l.filter } : {}),
		...(minzoom !== undefined ? { minzoom } : {}),
		...(l.maxzoom !== undefined ? { maxzoom: l.maxzoom } : {}),
		layout: { visibility: layerShown(c, l, state) ? 'visible' : 'none' },
		paint
	} as LayerSpecification;
}

/** What suppressing a group needs of a map (so tests pass a fake). */
export type SuppressMap = Pick<GlMap, 'getLayer' | 'setLayoutProperty' | 'getLayoutProperty' | 'setLayerZoomRange'>;

interface Hidden {
	visibility: string;
	minzoom: number;
	maxzoom: number;
	/** owner → hidden from this zoom up, or null for outright. */
	owners: Map<string, number | null>;
}

const hiddenGroups = new WeakMap<object, Map<string, Hidden>>();
const ownerSignature = new WeakMap<object, Map<string, string>>();

function refreshHidden(map: SuppressMap, id: string, h: Hidden): void {
	if (!map.getLayer(id)) return;
	const outright = [...h.owners.values()].some((z) => z === null);
	const from = Math.min(...[...h.owners.values()].filter((z): z is number => z !== null), Infinity);
	map.setLayoutProperty(id, 'visibility', outright ? 'none' : (h.visibility as 'visible' | 'none'));
	if (Number.isFinite(from)) map.setLayerZoomRange(id, h.minzoom, Math.min(h.maxzoom, from));
	else map.setLayerZoomRange(id, h.minzoom, h.maxzoom);
}

/** Stop hiding what `owner` hid. Other owners' hiding of the same layer stays. */
export function releaseGroups(map: SuppressMap & object, owner: string): void {
	ownerSignature.get(map)?.delete(owner);
	const hidden = hiddenGroups.get(map);
	if (!hidden) return;
	for (const [id, h] of hidden) {
		if (!h.owners.delete(owner)) continue;
		refreshHidden(map, id, h);
		if (!h.owners.size) hidden.delete(id);
	}
}

/**
 * Hide basemap groups for `owner` (a layer or a base contribution), from `fromZoom` up when given
 * (the road lines from z14). Owners are counted per layer, so two owners never fight: a layer comes
 * back only when the last owner lets go. Asking again with the same groups and zoom does nothing.
 */
export function suppressGroups(map: SuppressMap & object, owner: string, groups: readonly ProtomapsGroup[], fromZoom?: number): void {
	let sigs = ownerSignature.get(map);
	if (!sigs) ownerSignature.set(map, (sigs = new Map()));
	const sig = `${[...groups].sort().join(',')}@${fromZoom ?? ''}`;
	if (sigs.get(owner) === sig) return;
	releaseGroups(map, owner);
	sigs.set(owner, sig);
	let hidden = hiddenGroups.get(map);
	if (!hidden) hiddenGroups.set(map, (hidden = new Map()));
	for (const g of groups) {
		for (const id of PROTOMAPS_GROUPS[g] as readonly string[]) {
			const layer = map.getLayer(id) as { minzoom?: number; maxzoom?: number } | undefined;
			if (!layer) continue;
			let h = hidden.get(id);
			if (!h) {
				h = {
					visibility: (map.getLayoutProperty(id, 'visibility') as string | undefined) ?? 'visible',
					minzoom: layer.minzoom ?? 0,
					maxzoom: layer.maxzoom ?? 24,
					owners: new Map()
				};
				hidden.set(id, h);
			}
			h.owners.set(owner, fromZoom ?? null);
			refreshHidden(map, id, h);
		}
	}
}

/** What the base pass needs of a map (tests pass a fake). */
export type SyncMap = MapLike & SuppressMap;

const runtimeLayers = new WeakMap<object, Map<string, { c: BaseContribution; l: BaseLayer; flavor: FlavorName }>>();

/**
 * The manager's base pass for contributions: add the ones that join the running map (the painted ground
 * on the first use of Valley, never in a Clay first load; a toggled layer's tiles once /api/meta has
 * its version), then show or hide every contribution layer for this state, and hide the basemap
 * groups of each built, shown contribution. Returns the ids of the contributions built and on the
 * map, for their `live` hooks. An unbuilt contribution adds nothing and hides nothing.
 */
export function syncContributions(
	map: SyncMap & object,
	m: BasemapManifest,
	origin: string,
	meta: DataMeta | null,
	state: BaseState,
	contributions: readonly BaseContribution[] = BASE_CONTRIBUTIONS
): string[] {
	const live: string[] = [];
	let added = runtimeLayers.get(map);
	for (const c of contributions) {
		const owner = `base:${c.id}`;
		const status = contributionStatus(c, m, meta);
		if (!status.built) {
			releaseGroups(map, owner);
			continue;
		}
		if (c.layers.length && !map.getLayer(c.layers[0].id)) {
			// Joins the running map: the ground (first use of Valley) and a toggled layer's tiles.
			if (c.source.kind === 'landscape') continue;
			if ((c.looks === 'valley' || c.source.kind === 'ground') && state.flavor !== 'valley') continue;
			for (const [id, src] of Object.entries(contributionSources(c, m, origin, meta))) if (!map.getSource(id)) map.addSource(id, src);
			if (!added) runtimeLayers.set(map, (added = new Map()));
			for (const l of c.layers) {
				const before = beforeSlot(map as never, l.slot, l.rank);
				map.addLayer(contributionLayer(c, l, state, m), before);
				added.set(l.id, { c, l, flavor: state.flavor });
			}
		}
		for (const l of c.layers) {
			if (!map.getLayer(l.id)) continue;
			setRank(map, l.id, l.rank);
			const want = layerShown(c, l, state) ? 'visible' : 'none';
			if (map.getLayoutProperty(l.id, 'visibility') !== want) map.setLayoutProperty(l.id, 'visibility', want);
			// A layer added at run time isn't in the Valley/Clay diff: repaint it when the flavor changes.
			const r = added?.get(l.id);
			if (r && r.flavor !== state.flavor && l.clay) {
				const paint = state.flavor === 'clay' ? l.clay : l.valley;
				for (const [k, v] of Object.entries(paint)) (map.setPaintProperty as (id: string, k: string, v: unknown) => void)(l.id, k, v);
				r.flavor = state.flavor;
			}
		}
		const shown = c.layers.some((l) => layerShown(c, l, state));
		if (c.suppresses && shown) suppressGroups(map, owner, c.suppresses.groups, c.suppresses.fromZoom);
		else releaseGroups(map, owner);
		live.push(c.id);
	}
	return live;
}
