import type { Flavor } from '@protomaps/basemaps';
import type { LayerSpecification, Map } from 'maplibre-gl';
import { BUILDING_OPACITY, BUILDINGS_LAYER, IMAGERY_LAYERS } from './style.js';

export { BUILDINGS_LAYER, buildingOpacity, HILLSHADE_LAYER, IMAGERY_LAYERS } from './style.js';

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
		if (!deepEqual(v.layout ?? {}, c.layout ?? {})) throw new Error(`The flavors differ in ${v.id}'s layout; flavors change paint only.`);
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
export type FlavorMap = Pick<Map, 'getLayer' | 'setPaintProperty' | 'getLayoutProperty'>;

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
export function aerialShown(map: Pick<Map, 'getLayer' | 'getLayoutProperty'>): boolean {
	return Boolean(map.getLayer(IMAGERY_LAYERS[0])) && map.getLayoutProperty(IMAGERY_LAYERS[0], 'visibility') !== 'none';
}

/**
 * Switch the map to a flavor: every changed paint property, each with a
 * transition of `duration` ms (0 = instant). Layers not on the map (the
 * imagery before Aerial's first use) are skipped. Building opacity follows
 * Aerial. Returns the number of properties set (0 when already applied).
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
		if (aerial && ch.layer === BUILDINGS_LAYER && ch.property === 'fill-extrusion-opacity') value = AERIAL_BUILDING_OPACITY;
		if (trueColor.get(map) && IMAGERY_LAYERS.includes(ch.layer) && ch.property === 'raster-saturation') value = 0;
		set(ch.layer, `${ch.property}-transition`, { duration, delay: 0 });
		set(ch.layer, ch.property, value);
		n++;
	}
	applied.set(map, name);
	return n;
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
