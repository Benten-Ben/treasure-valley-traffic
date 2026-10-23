import { latest, validateStyleMin } from '@maplibre/maplibre-gl-style-spec';
import { createPropertyExpression, featureFilter } from '@maplibre/maplibre-gl-style-spec';
import type { LayerSpecification } from 'maplibre-gl';
import { beforeAll, describe, expect, it } from 'vitest';
import { BASE_CONTRIBUTIONS, baseContribution } from '#lib/base/registry.js';
import type { BaseState } from '#lib/base/types.js';
import { contributionLayer, contributionStatus, syncContributions, type SyncMap } from '#lib/map/flavors.js';
import { ANCHORS, DRAPED_TYPES, drapedRuns, ordered } from '#lib/map/order.js';
import { basemapReady, buildStyle, PROTOMAPS_GROUPS, type BasemapManifest } from '#lib/map/style.js';
import water, {
	BODIES_LAYER,
	BODIES_RIM_LAYER,
	ID,
	PICKABLE_LAYERS,
	REACH_INTERMITTENT_LAYER,
	REACH_LAYERS,
	REACH_NHD_INTERMITTENT_LAYER,
	REACH_NHD_LAYER,
	REACH_PIPED_LAYER,
	REACH_SOLID_LAYER
} from './water.base.js';
import { DASH, DASHED_MAX_PX, trueWidth } from './palette.js';

beforeAll(() => basemapReady);

const manifest: BasemapManifest = {
	bounds: [-117.05, 43, -115.95, 43.85],
	center: [-116.4, 43.6],
	zoom: 10,
	basemap: { file: 'valley.pmtiles', flavor: 'light', attribution: 'OSM', built: '2026-10-05' },
	glyphs: 'fonts/{fontstack}/{range}.pbf',
	sprite: 'sprites/v4/light'
};

const info = (layer: string) => ({ plugin: 'water', layer, build: 'b1', geometry: 'x', features: 3, fields: {}, minzoom: 8, maxzoom: 16, licence: 'ODbL-1.0', republish: 'yes', credit: [] });

/** A landscape entry that holds the water layers (and lists `empty` ones as the bake does). */
function withLandscape(layers: string[], empty: string[] = []): BasemapManifest {
	return {
		...manifest,
		landscape: {
			status: 'baked',
			file: 'landscape-1.pmtiles',
			digest: '1',
			format: 'pbf',
			minzoom: 8,
			maxzoom: 16,
			promoteId: 'id',
			layers: Object.fromEntries(layers.map((l) => [l, info(l.split('.')[1])])),
			empty,
			attribution: 'OSM',
			licences: ['ODbL-1.0'],
			republish: 'yes',
			access: 'tailnet',
			inputs: [],
			built: '2026-10-20',
			spec: 1,
			previous: null
		}
	};
}

const BOTH = ['water.bodies', 'water.reaches'];

/** The paint a layer has, per flavor. */
const paint = (id: string, flavor: 'valley' | 'clay') => water.layers.find((l) => l.id === id)![flavor === 'clay' ? 'clay' : 'valley'] as Record<string, unknown>;
const layer = (id: string) => water.layers.find((l) => l.id === id)!;
const state: BaseState = { flavor: 'valley', aerial: false, layers: new Set() };

describe('the water contribution', () => {
	it('is found by the registry, reads the two water source-layers, shows in both looks and opens cards for Water', () => {
		expect(baseContribution(ID)).toBe(water);
		expect(BASE_CONTRIBUTIONS.map((c) => c.id)).toContain('water.network');
		expect(water.source).toEqual({ kind: 'landscape', sourceLayers: ['water.bodies', 'water.reaches'] });
		expect(water.looks).toBe('both');
		expect(water.cardsWhen).toBe('water');
		expect(water.credit).toContain('OpenStreetMap');
		expect(water.credit).toContain('National Hydrography Dataset');
	});

	it('draws bodies, then reaches, all in anchor:water, all draped types', () => {
		expect(water.layers[0].id).toBe(BODIES_LAYER);
		for (const l of water.layers) {
			expect(l.slot, l.id).toBe('water');
			expect(DRAPED_TYPES.has(l.type), l.id).toBe(true);
			expect(l.sourceLayer, l.id).toMatch(/^water\.(bodies|reaches)$/);
		}
		const rank = (id: string) => layer(id).rank;
		expect(rank(BODIES_LAYER)).toBeLessThan(rank(BODIES_RIM_LAYER));
		for (const r of REACH_LAYERS) expect(rank(r), r).toBeGreaterThan(rank(BODIES_RIM_LAYER));
		const ranks = water.layers.map((l) => l.rank);
		expect(new Set(ranks).size).toBe(ranks.length);
		expect(Object.keys(ANCHORS)).toContain('water');
	});

	it('never has a casing (K5): no casing layer, no offset, a gap only on the solid layer and only for an off canal, and no line layer repeats another one’s features', () => {
		for (const l of water.layers) {
			expect(l.id, l.id).not.toMatch(/casing|outline|halo/i);
			for (const flavor of ['valley', 'clay'] as const) {
				const p = paint(l.id, flavor);
				expect(Object.keys(p), l.id).not.toContain('line-offset');
				// The gap is the season's hollow: the solid reach layer alone has one.
				if (l.id === REACH_SOLID_LAYER) expect(Object.keys(p), l.id).toContain('line-gap-width');
				else expect(Object.keys(p), l.id).not.toContain('line-gap-width');
			}
		}
		// The solid layer's gap is 0 unless the canal's season is off; the colour never changes with it.
		expect(paint(REACH_SOLID_LAYER, 'valley')['line-color']).toBe('#4a9fcc');
		// At whole zooms: MapLibre reads a zoom-and-feature expression at the tile's whole zoom and the next (season.test.ts blends them).
		for (const z of [8, 9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 22]) {
			for (const width_m of [0.5, 1.5, 4, 8, 14]) {
				const where = `z${z}, ${width_m} m`;
				const on = widthAt(REACH_SOLID_LAYER, { width_m }, z);
				for (const state of [undefined, 'on', 'unknown'] as const) expect(gapAt(REACH_SOLID_LAYER, { width_m }, z, state), `${state} ${where}`).toBe(0);
				// Off: a plain line (as today) or a hollow whose footprint, gap plus two edges, is the on width.
				const off = widthAt(REACH_SOLID_LAYER, { width_m }, z, 'off');
				const gap = gapAt(REACH_SOLID_LAYER, { width_m }, z, 'off');
				if (gap === 0) expect(off, `plain ${where}`).toBeCloseTo(on, 6);
				else {
					expect(gap + 2 * off, `the hollow's footprint is the true width, ${where}`).toBeCloseTo(on, 1);
					expect(off, `edges, ${where}`).toBeGreaterThanOrEqual(0.6 - 1e-9);
					expect(off, `edges, ${where}`).toBeLessThanOrEqual(1.2 + 1e-9);
				}
			}
		}
		// At whole zooms the hollow reads exactly where the on width is 3 px or more, and never under it.
		for (const z of [8, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22]) {
			for (const width_m of [0.5, 1.5, 4, 8, 14]) {
				const on = widthAt(REACH_SOLID_LAYER, { width_m }, z);
				const gap = gapAt(REACH_SOLID_LAYER, { width_m }, z, 'off');
				expect(gap > 0, `z${z}, ${width_m} m (${on.toFixed(2)} px)`).toBe(on >= 3);
			}
		}
		// Each reach is in exactly one line layer: the filters partition piped / NHD-only / intermittent.
		const feats = [] as { piped: boolean; nhd_only: boolean; intermittent: boolean }[];
		for (const piped of [false, true]) for (const nhd_only of [false, true]) for (const intermittent of [false, true]) feats.push({ piped, nhd_only, intermittent });
		for (const f of feats) {
			const hits = REACH_LAYERS.filter((id) => matches(layer(id).filter, f));
			expect(hits, JSON.stringify(f)).toHaveLength(1);
		}
		// Reaches are only drawn as lines, and no reach layer is a fill.
		for (const id of REACH_LAYERS) expect(layer(id).type).toBe('line');
	});

	it('tells kinds apart by form: widths, dashes, NHD-only finer with its own dash, piped dotted', () => {
		const dash = (id: string) => paint(id, 'valley')['line-dasharray'];
		expect(dash(REACH_SOLID_LAYER)).toBeUndefined();
		expect(dash(REACH_INTERMITTENT_LAYER)).toEqual([...DASH.intermittent]);
		expect(dash(REACH_NHD_LAYER)).toEqual([...DASH.nhd]);
		expect(dash(REACH_NHD_INTERMITTENT_LAYER)).toEqual([...DASH.nhdIntermittent]);
		expect(dash(REACH_PIPED_LAYER)).toEqual([...DASH.piped]);
		// The dashes are all different from each other (K8: each has its word in the legend).
		const dashes = [DASH.intermittent, DASH.nhd, DASH.piped].map((d) => d.join());
		expect(new Set(dashes).size).toBe(3);
		// Piped water draws from z16 only.
		expect(layer(REACH_PIPED_LAYER).minzoom).toBe(16);
		for (const id of REACH_LAYERS.filter((i) => i !== REACH_PIPED_LAYER)) expect(layer(id).minzoom, id).toBeUndefined();
		// An NHD-only line is finer than an OpenStreetMap line of the same width, at every zoom, and lighter.
		for (const zoom of [9, 12, 14, 15, 16, 18]) {
			const osm = widthAt(REACH_SOLID_LAYER, { width_m: 6 }, zoom);
			const nhd = widthAt(REACH_NHD_LAYER, { width_m: 6 }, zoom);
			expect(nhd, `z${zoom}`).toBeLessThan(osm);
		}
		expect(paint(REACH_NHD_LAYER, 'valley')['line-color']).not.toBe(paint(REACH_SOLID_LAYER, 'valley')['line-color']);
		expect(paint(REACH_NHD_INTERMITTENT_LAYER, 'clay')['line-color']).toBe(paint(REACH_NHD_LAYER, 'clay')['line-color']);
	});

	it('draws true-width ribbons from z15 and keeps dashed and dotted lines thin', () => {
		for (const [w, z] of [[14, 15], [14, 17], [4, 16], [2.5, 18]] as const) {
			expect(widthAt(REACH_SOLID_LAYER, { width_m: w }, z), `${w} m at z${z}`).toBeCloseTo(trueWidth(w, z), 1);
		}
		// Doubles every zoom from z15, as a true width does.
		expect(widthAt(REACH_SOLID_LAYER, { width_m: 8 }, 17) / widthAt(REACH_SOLID_LAYER, { width_m: 8 }, 16)).toBeCloseTo(2, 1);
		// Below z15 the width grows with zoom and with the (estimated) width.
		expect(widthAt(REACH_SOLID_LAYER, { width_m: 8 }, 12)).toBeGreaterThan(widthAt(REACH_SOLID_LAYER, { width_m: 8 }, 9));
		expect(widthAt(REACH_SOLID_LAYER, { width_m: 14 }, 11)).toBeGreaterThan(widthAt(REACH_SOLID_LAYER, { width_m: 1.5 }, 11));
		// No line is thinner than 0.6 px.
		expect(widthAt(REACH_SOLID_LAYER, { width_m: 0.5 }, 8)).toBeGreaterThanOrEqual(0.6);
		// Dashed lines stay at DASHED_MAX_PX and under at any zoom, dots at least 2 px.
		for (const id of [REACH_INTERMITTENT_LAYER, REACH_NHD_LAYER, REACH_NHD_INTERMITTENT_LAYER, REACH_PIPED_LAYER])
			for (const z of [12, 16, 19, 21]) expect(widthAt(id, { width_m: 14 }, z), `${id} z${z}`).toBeLessThanOrEqual(DASHED_MAX_PX + 1e-9);
		expect(widthAt(REACH_PIPED_LAYER, { width_m: 1 }, 16)).toBeGreaterThanOrEqual(2);
	});

	it('lets a missing width read as 1 m (a tile without width_m still draws)', () => {
		expect(widthAt(REACH_SOLID_LAYER, {}, 16)).toBeCloseTo(trueWidth(1, 16), 1);
	});

	it('has the same paint properties in Valley and Clay (so the flavor diff covers every change), and only the colours differ', () => {
		for (const l of water.layers) {
			const v = paint(l.id, 'valley');
			const c = paint(l.id, 'clay');
			expect(Object.keys(c).sort(), l.id).toEqual(Object.keys(v).sort());
			for (const k of Object.keys(v)) if (!/color$/.test(k)) expect(c[k], `${l.id} ${k}`).toEqual(v[k]);
		}
		expect(paint(BODIES_LAYER, 'valley')['fill-color']).toEqual(['case', ['to-boolean', ['get', 'nhd_only']], '#a0d3ea', '#7cc4e4']);
		expect(paint(BODIES_LAYER, 'clay')['fill-color']).toEqual(['case', ['to-boolean', ['get', 'nhd_only']], '#dbe7ec', '#c9dce3']);
	});

	it('picks the layers a click can hit: the areas and every reach line, no helper layers', () => {
		expect([...PICKABLE_LAYERS]).toEqual([BODIES_LAYER, ...REACH_LAYERS]);
		for (const id of PICKABLE_LAYERS) expect(water.layers.map((l) => l.id)).toContain(id);
	});

	it('hides Protomaps’ water group, which names real Protomaps layers', () => {
		expect(water.suppresses).toEqual({ groups: ['water'] });
		expect(PROTOMAPS_GROUPS.water).toEqual(['water', 'water_stream', 'water_river']);
	});

	it('makes style layers MapLibre accepts, in both flavors', () => {
		for (const flavor of ['valley', 'clay'] as const) {
			const layers = water.layers.map((l) => contributionLayer(water, l, { ...state, flavor }));
			const style = { version: 8 as const, sources: { landscape: { type: 'vector' as const, tiles: ['http://x/{z}/{x}/{y}'] } }, layers: layers.map((l) => ({ ...l, source: 'landscape' })) };
			const errors = validateStyleMin(style as never, latest as never);
			expect(errors.map((e) => `${e.identifier ?? ''} ${e.message}`), flavor).toEqual([]);
		}
	});
});

describe('the water contribution in the style', () => {
	it('is built only when both source-layers are in the bake, never one listed under empty', () => {
		expect(contributionStatus(water, manifest)).toEqual({ built: false, reason: 'not built yet' });
		expect(contributionStatus(water, withLandscape(BOTH))).toEqual({ built: true });
		expect(contributionStatus(water, withLandscape(['water.reaches']))).toEqual({ built: false, reason: 'not built yet' });
		expect(contributionStatus(water, withLandscape(['water.reaches'], ['water.bodies']))).toEqual({ built: false, reason: 'not built yet' });
		expect(contributionStatus(water, withLandscape(BOTH, ['water.bodies']))).toEqual({ built: false, reason: 'not built yet' });
	});

	it('puts the layers between the basemap’s water and the surfaces: one draped run, in Valley and in Clay', () => {
		const m = withLandscape(BOTH);
		for (const flavor of ['valley', 'clay'] as const) {
			const style = buildStyle(m, 'http://x', false, flavor, { contributions: [water] });
			const ids = style.layers.map((l) => l.id);
			const at = (id: string) => ids.indexOf(id);
			expect(at('water'), 'the basemap’s water is still in the style').toBeGreaterThan(-1);
			expect(at(BODIES_LAYER)).toBeGreaterThan(at('water_river'));
			expect(at(BODIES_LAYER)).toBeLessThan(at(REACH_SOLID_LAYER));
			expect(at(REACH_PIPED_LAYER)).toBeLessThan(at(ANCHORS.water));
			expect(at(ANCHORS.water)).toBeLessThan(at(ANCHORS.surfaces));
			expect(at(ANCHORS.water)).toBeLessThan(at('roads_major'));
			// Only the water slot grew: a single draped block still runs to anchor:routes.
			const runs = drapedRuns(style.layers.map((l) => ordered(l)));
			expect(runs.length, flavor).toBe(1);
			// Both looks show it (a Valley-only contribution is hidden in Clay).
			for (const l of water.layers) {
				const built = style.layers.find((x) => x.id === l.id)! as LayerSpecification;
				expect((built.layout as { visibility?: string }).visibility, `${l.id} in ${flavor}`).toBe('visible');
			}
		}
	});

	it('adds nothing, and hides nothing, when the bake holds no water', () => {
		const style = buildStyle(withLandscape(['roads.surfaces'], BOTH), 'http://x', false, 'valley', { contributions: [water] });
		expect(style.layers.map((l) => l.id).filter((id) => id.startsWith(`${ID}.`))).toEqual([]);
		const sync = syncMap(style.layers);
		syncContributions(sync as unknown as SyncMap, withLandscape(['roads.surfaces'], BOTH), 'http://x', null, state, [water]);
		for (const id of PROTOMAPS_GROUPS.water) expect(sync.layers.find((l) => l.id === id)?.layout?.visibility ?? 'visible', id).toBe('visible');
	});

	it('hides Protomaps’ water once built, in both looks, and gives it back when the bake loses its water', () => {
		const m = withLandscape(BOTH);
		for (const flavor of ['valley', 'clay'] as const) {
			const style = buildStyle(m, 'http://x', false, flavor, { contributions: [water] });
			const sync = syncMap(style.layers);
			const live = syncContributions(sync as unknown as SyncMap, m, 'http://x', null, { ...state, flavor }, [water]);
			expect(live).toEqual([ID]);
			for (const id of PROTOMAPS_GROUPS.water) expect(sync.layers.find((l) => l.id === id)?.layout?.visibility, `${id} in ${flavor}`).toBe('none');
			// The water labels stay: the Water layer hides them only while its own italic names draw.
			for (const id of PROTOMAPS_GROUPS['water-labels']) expect(sync.layers.find((l) => l.id === id)?.layout?.visibility ?? 'visible', id).not.toBe('none');
			// A later bake without the reaches leaves the basemap's water as it was.
			const lost = withLandscape(['water.bodies'], ['water.reaches']);
			expect(syncContributions(sync as unknown as SyncMap, lost, 'http://x', null, { ...state, flavor }, [water])).toEqual([]);
			for (const id of PROTOMAPS_GROUPS.water) expect(sync.layers.find((l) => l.id === id)?.layout?.visibility, id).toBe('visible');
		}
	});
});

// -- helpers -------------------------------------------------------------------------------------------------

type Feature = Record<string, unknown>;

/** Whether a layer’s filter keeps a feature (MapLibre’s own filter evaluator). */
function matches(filter: unknown, properties: Feature): boolean {
	const f = featureFilter(filter as never, 'layers[0].filter');
	return Boolean(f.filter({ zoom: 14 } as never, { type: 2, properties } as never));
}

type Evaluator = { evaluate(g: unknown, f: unknown, s: unknown): number };
const parsed = new Map<string, Evaluator>();

/** A paint property's value MapLibre would give a feature at a zoom, from the layer’s own style expression (and its feature-state). */
function paintAt(layerId: string, prop: 'line-width' | 'line-gap-width', properties: Feature, zoom: number, season?: string): number {
	const key = `${layerId} ${prop}`;
	let e = parsed.get(key);
	if (!e) {
		const spec = (latest as { paint_line: Record<string, unknown> }).paint_line[prop];
		const p = createPropertyExpression(paint(layerId, 'valley')[prop] as never, `layers[${layerId}].paint.${prop}`, spec as never);
		if (p.result !== 'success') throw new Error(`${prop} does not parse: ${JSON.stringify(p.value)}`);
		parsed.set(key, (e = p.value as Evaluator));
	}
	return e.evaluate({ zoom }, { type: 2, properties }, season ? { season } : {});
}

/** The line width MapLibre would give a feature at a zoom. */
const widthAt = (layerId: string, properties: Feature, zoom: number, season?: string) => paintAt(layerId, 'line-width', properties, zoom, season);
/** The gap MapLibre would give it. */
const gapAt = (layerId: string, properties: Feature, zoom: number, season?: string) => paintAt(layerId, 'line-gap-width', properties, zoom, season);

/** A map that holds style layers, as the base pass sees them. */
function syncMap(layers: LayerSpecification[]) {
	const ls = layers.map((l) => structuredClone(l)) as (LayerSpecification & { layout?: Record<string, unknown> })[];
	const find = (id: string) => ls.find((l) => l.id === id);
	const map = {
		layers: ls,
		getLayer: (id: string) => find(id) as never,
		getLayoutProperty: (id: string, k: string) => (find(id)?.layout ?? {})[k] as never,
		setLayoutProperty: (id: string, k: string, v: unknown) => {
			const l = find(id)!;
			l.layout = { ...(l.layout ?? {}), [k]: v };
			return map as never;
		},
		setLayerZoomRange: () => map as never,
		setPaintProperty: () => map as never,
		getSource: () => ({}) as never,
		addSource: () => map as never,
		addLayer: (l: LayerSpecification) => void ls.push(l) as never,
		getLayersOrder: () => ls.map((l) => l.id)
	};
	return map;
}
