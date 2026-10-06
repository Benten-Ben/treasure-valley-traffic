import { readFileSync } from 'node:fs';
import { latest } from '@maplibre/maplibre-gl-style-spec';
import { LIGHT, namedFlavor, type Flavor } from '@protomaps/basemaps';
import type { LayerSpecification } from 'maplibre-gl';
import { beforeAll, describe, expect, it } from 'vitest';
import {
	AERIAL_BUILDING_OPACITY,
	AERIAL_SATURATION,
	aerialShown,
	appliedFlavor,
	applyFlavor,
	BUILDINGS_LAYER,
	BUILDINGS_PAINT,
	CLAY_HIDDEN,
	CLAY_OVERRIDES,
	clayPaintDiff,
	FLAVOR_FADE_MS,
	flavorOf,
	GROUND,
	hiddenBaseLabels,
	HILLSHADE_PAINT,
	keepDrapeFresh,
	IMAGERY_LAYERS,
	VALLEY_OVERRIDES,
	type FlavorMap,
	type FlavorName,
	type PaintChange
} from './flavors.js';
import { basemapReady, buildStyle, flavorDiff, flavorLayers, setAerial, type BasemapManifest } from './style.js';

beforeAll(() => basemapReady);

const manifest: BasemapManifest = {
	bounds: [-117.05, 43, -115.95, 43.85],
	center: [-116.4, 43.6],
	zoom: 10,
	basemap: { file: 'valley.pmtiles', flavor: 'light', attribution: 'OSM', built: '2026-10-05' },
	glyphs: 'fonts/{fontstack}/{range}.pbf',
	sprite: 'sprites/v4/light',
	terrain: { file: 'terrain.pmtiles', encoding: 'mapbox', tileSize: 512, exaggeration: 1.3, attribution: 'USGS 3DEP', built: '2026-10-05' },
	buildings: { file: 'buildings.pmtiles', sourceLayer: 'buildings', minzoom: 14, attribution: 'Overture', built: '2026-10-05' },
	imagery: {
		file: 'imagery.pmtiles',
		tileSize: 512,
		maxzoom: 14,
		attribution: 'USDA NAIP',
		built: '2026-10-05',
		detail: { file: 'imagery-detail.pmtiles', minzoom: 15, maxzoom: 17, points: 228, radius: 250 }
	}
};

type Paint = Record<string, unknown>;
const paintOf = (l: LayerSpecification): Paint => ((l as { paint?: Paint }).paint ?? {}) as Paint;
const byId = (ls: LayerSpecification[]) => new Map(ls.map((l) => [l.id, l]));

/** docs/14 §14.5's flavor table: element → [Valley cell, Clay cell]. */
function flavorTable(): Map<string, [string, string]> {
	const doc = readFileSync(new URL('../../../../docs/14-ui-v2.md', import.meta.url), 'utf8');
	const start = doc.indexOf('| Element | Valley (ch. 13 normal look) | Clay (any data layer on, in Auto) |');
	expect(start, 'the flavor table in §14.5').toBeGreaterThan(0);
	const rows = new Map<string, [string, string]>();
	for (const line of doc.slice(start).split('\n').slice(2)) {
		if (!line.startsWith('|')) break;
		const [, element, valley, clay] = line.split('|').map((c) => c.trim());
		rows.set(element, [valley, clay]);
	}
	return rows;
}
const hexes = (cell: string) => [...cell.matchAll(/#[0-9A-Fa-f]{6}/g)].map((m) => m[0].toLowerCase());

/** A map that holds layers, as MapLibre's paint and layout methods see them. */
function fakeMap(layers: LayerSpecification[]) {
	const calls: [string, string, unknown][] = [];
	const ls = layers.map((l) => structuredClone(l));
	const find = (id: string) => ls.find((l) => l.id === id);
	const map = {
		calls,
		layers: ls,
		getLayer: (id: string) => find(id) as never,
		getLayoutProperty: (id: string, k: string) => ((find(id)?.layout ?? {}) as Paint)[k] as never,
		setLayoutProperty: (id: string, k: string, v: unknown) => {
			const l = find(id)!;
			l.layout = { ...(l.layout ?? {}), [k]: v } as never;
			return map as never;
		},
		setPaintProperty: (id: string, k: string, v: unknown) => {
			calls.push([id, k, v]);
			const l = find(id)! as { paint?: Paint };
			l.paint = { ...(l.paint ?? {}), [k]: v };
			return map as never;
		},
		getSource: () => ({}) as never,
		addSource: () => map as never,
		addLayer: (l: LayerSpecification) => void ls.push(l) as never,
		getLayersOrder: () => ls.map((l) => l.id)
	};
	return map;
}

/** Paint without the transition settings applyFlavor adds. */
const plain = (p: Paint) => Object.fromEntries(Object.entries(p).filter(([k, v]) => !k.endsWith('-transition') && v !== undefined));

describe('flavors', () => {
	it('builds Valley and Clay over Protomaps light, overriding only fields light has', () => {
		const light = namedFlavor('light');
		expect(light).toEqual(LIGHT);
		for (const o of [VALLEY_OVERRIDES, CLAY_OVERRIDES]) for (const k of Object.keys(o)) expect(Object.keys(LIGHT), k).toContain(k);
		const valley = flavorOf(light, 'valley');
		const clay = flavorOf(light, 'clay');
		expect(Object.keys(valley).sort()).toEqual(Object.keys(light).sort());
		expect(Object.keys(clay).sort()).toEqual(Object.keys(light).sort());
		expect(valley.pois).toEqual(light.pois);
		expect(clay.landcover).toEqual(light.landcover);
		expect(valley.earth).toBe(GROUND.valley);
		expect(clay.earth).toBe(GROUND.clay);
	});

	it('follows the §14.5 table, row by row', () => {
		const t = flavorTable();
		const valley = flavorOf(LIGHT, 'valley');
		const clay = flavorOf(LIGHT, 'clay');
		const row = (name: string) => {
			const r = t.get(name);
			expect(r, `row ${name}`).toBeTruthy();
			return r!;
		};
		const ground = row('Ground');
		expect([valley.earth, valley.background]).toEqual([hexes(ground[0])[0], hexes(ground[0])[0]]);
		expect([clay.earth, clay.background]).toEqual([hexes(ground[1])[0], hexes(ground[1])[0]]);
		const parks = row('Parks, woods');
		expect([valley.park_a, valley.park_b, valley.wood_a, valley.wood_b]).toEqual(hexes(parks[0]));
		for (const k of ['park_a', 'park_b', 'wood_a', 'wood_b'] as const) expect(clay[k]).toBe(hexes(parks[1])[0]);
		// Scrub and grassland (the Foothills) go with the woods, in the pale woods green.
		expect([valley.scrub_a, valley.scrub_b, clay.scrub_a, clay.scrub_b]).toEqual([valley.wood_a, valley.wood_a, clay.wood_a, clay.wood_a]);
		const other = row('Other land use');
		expect(other[0]).toBe('as `light`');
		for (const k of ['hospital', 'industrial', 'school', 'pedestrian', 'sand', 'beach', 'aerodrome', 'zoo', 'military'] as const) {
			expect(valley[k], k).toBe(LIGHT[k]);
			expect(clay[k], k).toBe(hexes(other[1])[0]);
		}
		const water = row('Water');
		expect([valley.water, clay.water]).toEqual([hexes(water[0])[0], hexes(water[1])[0]]);
		const flat = row('Flat buildings');
		expect([valley.buildings, clay.buildings]).toEqual([hexes(flat[0])[0], hexes(flat[1])[0]]);
		const b3d = row('3D buildings');
		expect(BUILDINGS_PAINT.valley).toEqual({ color: hexes(b3d[0])[0], opacity: Number(/at ([\d.]+)/.exec(b3d[0])![1]) });
		expect(BUILDINGS_PAINT.clay).toEqual({ color: hexes(b3d[1])[0], opacity: Number(/at ([\d.]+)/.exec(b3d[1])![1]) });
		const roads = (f: Flavor, keys: (keyof Flavor)[]) => [...new Set(keys.map((k) => f[k]))];
		const major: (keyof Flavor)[] = ['major', 'highway', 'link', 'bridges_major', 'bridges_highway', 'bridges_link'];
		const majorCasing: (keyof Flavor)[] = ['major_casing_early', 'major_casing_late', 'highway_casing_early', 'highway_casing_late', 'link_casing'];
		const minor: (keyof Flavor)[] = ['minor_a', 'minor_b', 'minor_service', 'bridges_minor'];
		const minorCasing: (keyof Flavor)[] = ['minor_casing', 'minor_service_casing', 'bridges_minor_casing'];
		const mj = row('Major roads, casing');
		expect([...roads(valley, major), ...roads(valley, majorCasing)]).toEqual(hexes(mj[0]));
		expect([...roads(clay, major), ...roads(clay, majorCasing)]).toEqual(hexes(mj[1]));
		const mn = row('Minor roads, casing');
		expect([...roads(valley, minor), ...roads(valley, minorCasing)]).toEqual(hexes(mn[0]));
		expect([...roads(clay, minor), ...roads(clay, minorCasing)]).toEqual(hexes(mn[1]));
		const labels = row('Labels, halo');
		const [ink, inkSoft, halo] = hexes(labels[0]);
		expect(valley.city_label).toBe(ink);
		for (const k of ['subplace_label', 'roads_label_major', 'roads_label_minor', 'address_label'] as const) expect(valley[k], k).toBe(inkSoft);
		for (const k of ['city_label_halo', 'subplace_label_halo', 'roads_label_major_halo', 'roads_label_minor_halo', 'address_label_halo'] as const)
			expect([valley[k], clay[k]], k).toEqual([halo, halo]);
		expect(labels[1]).toMatch(/^place labels/);
		expect(clay.city_label).toBe(hexes(labels[1])[0]);
		const hs = row('Hillshade');
		expect(HILLSHADE_PAINT.valley).toMatchObject({ 'hillshade-exaggeration': Number(/exaggeration ([\d.]+)/.exec(hs[0])![1]), 'hillshade-shadow-color': hexes(hs[0])[0] });
		expect(HILLSHADE_PAINT.clay).toMatchObject({
			'hillshade-exaggeration': Number(/^([\d.]+)/.exec(hs[1])![1]),
			'hillshade-shadow-color': hexes(hs[1])[0],
			'hillshade-highlight-color': hexes(hs[1])[1]
		});
		const hidden = row('Hidden in Clay');
		expect(hidden[1]).toBe('address labels, POIs, basemap one-way arrows, minor road labels, shields');
	});

	it('clayPaintDiff covers every changed layer: applied to Valley it gives exactly Clay, and back', () => {
		const valley = flavorLayers(manifest, 'valley');
		const clay = flavorLayers(manifest, 'clay');
		expect(valley.map((l) => l.id)).toEqual(clay.map((l) => l.id));
		const diff = clayPaintDiff(valley, clay);
		expect(flavorDiff(manifest)).toEqual(diff);
		const changed = new Set(diff.map((d) => d.layer));
		const c = byId(clay);
		for (const v of valley) {
			const differs = JSON.stringify(paintOf(v)) !== JSON.stringify(paintOf(c.get(v.id)!));
			expect(changed.has(v.id), `${v.id} in the diff`).toBe(differs);
			expect(v.layout ?? {}, `${v.id} layout`).toEqual(c.get(v.id)!.layout ?? {});
		}
		// Applying the diff through the map API turns one into the other.
		for (const [from, to, name] of [
			[valley, clay, 'clay'],
			[clay, valley, 'valley']
		] as [LayerSpecification[], LayerSpecification[], FlavorName][]) {
			const map = fakeMap(from);
			applyFlavor(map as unknown as FlavorMap, diff, name, { force: true });
			const want = byId(to);
			for (const l of map.layers) expect(plain(paintOf(l)), l.id).toEqual(plain(paintOf(want.get(l.id)!)));
		}
		// What it covers: the ground, parks, water, roads, labels, buildings, hillshade and imagery.
		for (const id of ['background', 'earth', 'landuse_park', 'water', 'roads_major', 'roads_minor', 'roads_highway_casing_late', 'buildings', 'places_locality', 'hillshade', BUILDINGS_LAYER, ...IMAGERY_LAYERS])
			expect(changed, id).toContain(id);
		// Never the data slots, the rail or the anchors.
		for (const id of changed) expect(id).not.toMatch(/^(anchor:|rail-)/);
		test_transitionable(diff);
	});

	it('the hidden set is exact: Clay hides those five basemap label layers and nothing else', () => {
		const style = buildStyle(manifest, 'http://x');
		const ids = style.layers.map((l) => l.id);
		expect([...CLAY_HIDDEN].sort()).toEqual(['address_label', 'pois', 'roads_labels_minor', 'roads_oneway', 'roads_shields']);
		for (const id of CLAY_HIDDEN) {
			const l = style.layers[ids.indexOf(id)];
			expect(l, id).toBeTruthy();
			expect(l.type).toBe('symbol');
			expect((l as { source?: string }).source).toBe('protomaps');
		}
		expect([...hiddenBaseLabels('clay', 'full')].sort()).toEqual([...CLAY_HIDDEN].sort());
		expect([...hiddenBaseLabels('clay', 'fewer')].sort()).toEqual([...CLAY_HIDDEN].sort());
		expect([...hiddenBaseLabels('valley', 'full')]).toEqual([]);
		expect([...hiddenBaseLabels('valley', 'fewer')].sort()).toEqual([...CLAY_HIDDEN].sort());
		// The other labels stay (place names, major road names, water).
		for (const id of ['places_locality', 'places_subplace', 'roads_labels_major', 'water_waterway_label']) expect(hiddenBaseLabels('clay', 'full').has(id)).toBe(false);
		// Applying a flavor never touches layout: visibility is the layer manager's, with this set.
		const map = fakeMap(style.layers);
		const layouts = JSON.stringify(map.layers.map((l) => l.layout));
		applyFlavor(map as unknown as FlavorMap, flavorDiff(manifest), 'clay', { force: true });
		expect(JSON.stringify(map.layers.map((l) => l.layout))).toBe(layouts);
	});

	it('crossfades over 350 ms (instant on request), once per change, skipping layers not on the map', () => {
		const style = buildStyle(manifest, 'http://x');
		const map = fakeMap(style.layers);
		const diff = flavorDiff(manifest);
		const m = map as unknown as FlavorMap;
		expect(appliedFlavor(map)).toBe('valley');
		const n = applyFlavor(m, diff, 'clay');
		expect(n).toBeGreaterThan(40);
		expect(appliedFlavor(map)).toBe('clay');
		// Every change gets its transition first, then its value; no imagery yet, so none for it.
		const transitions = map.calls.filter(([, k]) => k.endsWith('-transition'));
		expect(transitions.length).toBe(n);
		expect(new Set(transitions.map(([, , v]) => JSON.stringify(v)))).toEqual(new Set([JSON.stringify({ duration: FLAVOR_FADE_MS, delay: 0 })]));
		expect(map.calls.some(([id]) => IMAGERY_LAYERS.includes(id))).toBe(false);
		// Already Clay: nothing to do.
		map.calls.length = 0;
		expect(applyFlavor(m, diff, 'clay')).toBe(0);
		expect(map.calls).toEqual([]);
		// Reduced motion (or the first apply): instant.
		applyFlavor(m, diff, 'valley', { duration: 0 });
		expect(map.calls.filter(([, k]) => k.endsWith('-transition')).every(([, , v]) => (v as { duration: number }).duration === 0)).toBe(true);
		expect((map.getLayer('earth') as { paint: Paint }).paint['fill-color']).toBe(GROUND.valley);
	});

	it('follows Aerial: muted photo and see-through buildings in Clay, 0.3 buildings on Aerial in either', () => {
		const style = buildStyle(manifest, 'http://x');
		const map = fakeMap(style.layers);
		const m = map as unknown as FlavorMap;
		const diff = flavorDiff(manifest);
		const b3d = () => (map.getLayer(BUILDINGS_LAYER) as { paint: Paint }).paint['fill-extrusion-opacity'];
		const sat = (id: string) => (map.getLayer(id) as { paint: Paint }).paint['raster-saturation'];
		applyFlavor(m, diff, 'clay', { force: true });
		expect(b3d()).toBe(BUILDINGS_PAINT.clay.opacity);
		// Aerial's first use in Clay adds the imagery already muted.
		setAerial(map as never, manifest, 'http://x', true);
		expect(aerialShown(map as never)).toBe(true);
		for (const id of IMAGERY_LAYERS) expect(sat(id)).toBe(AERIAL_SATURATION.clay);
		expect(b3d()).toBe(AERIAL_BUILDING_OPACITY);
		applyFlavor(m, diff, 'valley');
		for (const id of IMAGERY_LAYERS) expect(sat(id)).toBe(AERIAL_SATURATION.valley);
		expect(b3d()).toBe(AERIAL_BUILDING_OPACITY);
		setAerial(map as never, manifest, 'http://x', false);
		expect(b3d()).toBe(BUILDINGS_PAINT.valley.opacity);
		applyFlavor(m, diff, 'clay');
		expect(b3d()).toBe(BUILDINGS_PAINT.clay.opacity);
		setAerial(map as never, manifest, 'http://x', true);
		expect(b3d()).toBe(AERIAL_BUILDING_OPACITY);
		for (const id of IMAGERY_LAYERS) expect(sat(id)).toBe(AERIAL_SATURATION.clay);
	});

	it('builds the style in either flavor, with the same layers', () => {
		const v = buildStyle(manifest, 'http://x');
		const c = buildStyle(manifest, 'http://x', false, 'clay');
		expect(c.layers.map((l) => l.id)).toEqual(v.layers.map((l) => l.id));
		const earth = (s: typeof v) => paintOf(s.layers.find((l) => l.id === 'earth')!)['fill-color'];
		expect([earth(v), earth(c)]).toEqual([GROUND.valley, GROUND.clay]);
		expect(paintOf(c.layers.find((l) => l.id === 'hillshade')!)).toEqual(HILLSHADE_PAINT.clay);
		expect(paintOf(c.layers.find((l) => l.id === BUILDINGS_LAYER)!)).toMatchObject({ 'fill-extrusion-color': BUILDINGS_PAINT.clay.color, 'fill-extrusion-opacity': BUILDINGS_PAINT.clay.opacity });
	});

	it('keeps the terrain drape fresh through the crossfade, then lets go', () => {
		let t = 0;
		const handlers = new Set<() => void>();
		let released = 0;
		let repaints = 0;
		let terrain: object | null = {};
		const map = {
			on: (_: 'render', fn: () => void) => handlers.add(fn),
			off: (_: 'render', fn: () => void) => handlers.delete(fn),
			triggerRepaint: () => void repaints++,
			getTerrain: () => terrain,
			terrain: { tileManager: { releaseAllRTT: () => void released++ } }
		};
		const frame = (dt: number) => {
			t += dt;
			for (const f of [...handlers]) f();
		};
		keepDrapeFresh(map, 450, () => t);
		expect([released, repaints, handlers.size]).toEqual([1, 1, 1]);
		// Every frame of the fade releases the cached drape and asks for the next.
		for (let i = 0; i < 4; i++) frame(100);
		expect([released, repaints, handlers.size]).toEqual([5, 5, 1]);
		// Past the end: one last release and frame (the final colors), then it stops.
		frame(100);
		expect([released, repaints, handlers.size]).toEqual([6, 6, 0]);
		frame(100);
		expect([released, repaints]).toEqual([6, 6]);
		// Without terrain there's no drape to release; cancelling stops it early.
		terrain = null;
		const stop = keepDrapeFresh(map, 450, () => t);
		frame(16);
		expect(released).toBe(6);
		stop();
		expect(handlers.size).toBe(0);
	});

	it('refuses to diff flavors that build different layers', () => {
		const a: LayerSpecification[] = [{ id: 'x', type: 'background', paint: { 'background-color': '#000' } }];
		const b: LayerSpecification[] = [{ id: 'y', type: 'background', paint: { 'background-color': '#000' } }];
		expect(() => clayPaintDiff(a, b)).toThrow();
		const c: LayerSpecification[] = [{ id: 'x', type: 'background', layout: { visibility: 'none' }, paint: { 'background-color': '#000' } }];
		expect(() => clayPaintDiff(a, c)).toThrow(/layout/);
		expect(clayPaintDiff(a, [{ id: 'x', type: 'background', paint: { 'background-color': '#111' } }])).toEqual([
			{ layer: 'x', property: 'background-color', valley: '#000', clay: '#111' }
		] satisfies PaintChange[]);
	});
});

/** Every property in the diff can take a `-transition` (MapLibre's style spec), so the crossfade is valid. */
function test_transitionable(diff: PaintChange[]) {
	const style = buildStyle(manifest, 'http://x', true);
	const types = new Map(style.layers.map((l) => [l.id, l.type]));
	for (const d of diff) {
		const ref = (latest as unknown as Record<string, Record<string, { transition?: boolean }>>)[`paint_${types.get(d.layer)}`];
		expect(ref?.[d.property]?.transition, `${d.layer} ${d.property} is transitionable`).toBe(true);
	}
}
