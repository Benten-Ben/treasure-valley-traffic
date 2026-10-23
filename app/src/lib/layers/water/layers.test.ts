import { latest, validateStyleMin } from '@maplibre/maplibre-gl-style-spec';
import type { LayerSpecification } from 'maplibre-gl';
import { beforeAll, describe, expect, it } from 'vitest';
import water from '#lib/base/water/water.base.js';
import { ANCHORS, DRAPED_TYPES, drapedRuns, insertSlotted, ordered, rttStacks } from '#lib/map/order.js';
import { basemapReady, buildStyle, type BasemapManifest } from '#lib/map/style.js';
import {
	BAKED_LAYERS,
	bakedLayers,
	flavorPaints,
	GAUGE_LAYER,
	IMAGE,
	LABEL_BODY_LAYER,
	LABEL_FINE_LAYER,
	LABEL_MAIN_LAYER,
	noticeFeatures,
	NOTICE_LAYER,
	POINT_LAYERS,
	pointFeatures,
	pointId,
	pointLayers,
	SELECTED_BODY_LAYER,
	SELECTED_REACH_LAYER,
	STRUCTURE_FINE_LAYER,
	STRUCTURE_LAYER,
	STRUCTURE_MID_LAYER
} from './layers.js';
import { MARKERS, markerImage } from './markers.js';

beforeAll(() => basemapReady);


const manifest: BasemapManifest = {
	bounds: [-117.05, 43, -115.95, 43.85],
	center: [-116.4, 43.6],
	zoom: 10,
	basemap: { file: 'valley.pmtiles', flavor: 'light', attribution: 'OSM', built: '2026-10-05' },
	glyphs: 'fonts/{fontstack}/{range}.pbf',
	sprite: 'sprites/v4/light',
	landscape: {
		status: 'baked',
		file: 'landscape-1.pmtiles',
		digest: '1',
		format: 'pbf',
		minzoom: 8,
		maxzoom: 16,
		promoteId: 'id',
		layers: Object.fromEntries(['water.bodies', 'water.reaches'].map((k) => [k, { plugin: 'water', layer: k.split('.')[1], build: 'b', geometry: 'x', features: 2, fields: {}, minzoom: 8, maxzoom: 16, licence: 'ODbL-1.0', republish: 'yes', credit: [] }])),
		empty: [],
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

/** The layer’s style layers added the way the module adds them (rank 60, the water layer’s order). */
function withWater() {
	const ranks = {};
	let layers = buildStyle(manifest, 'http://x', false, 'valley', { contributions: [water] }).layers;
	layers = insertSlotted(layers, [...bakedLayers(), ...pointLayers()], 60, ranks);
	return layers;
}

describe('the Water layer’s style layers', () => {
	it('keep every symbol out of the draped block: names in labels, badges in points, lines in water', () => {
		for (const s of pointLayers()) {
			expect(s.slot, s.layer.id).toBe('points');
			expect(s.layer.type, s.layer.id).toBe('symbol');
		}
		for (const s of bakedLayers()) {
			if (s.layer.type === 'symbol') expect(s.slot, s.layer.id).toBe('labels');
			else {
				expect(s.slot, s.layer.id).toBe('water');
				expect(DRAPED_TYPES.has(s.layer.type), s.layer.id).toBe(true);
			}
		}
		const style = withWater();
		const ids = style.map((l) => l.id);
		const at = (id: string) => ids.indexOf(id);
		// "No symbol or circle layer goes below anchor:routes": nothing but draped types between ground and routes.
		for (const l of style.slice(at(ANCHORS.ground), at(ANCHORS.routes))) {
			if (l.id.startsWith('water-')) expect(DRAPED_TYPES.has(l.type), l.id).toBe(true);
		}
		for (const id of POINT_LAYERS) expect(at(id), id).toBeGreaterThan(at(ANCHORS.routes));
		for (const id of [LABEL_MAIN_LAYER, LABEL_FINE_LAYER, LABEL_BODY_LAYER]) {
			expect(at(id), id).toBeGreaterThan(at(ANCHORS.points));
			expect(at(id), id).toBeLessThan(at(ANCHORS.labels));
		}
		// The picked shape sits over the baked network, in its slot.
		expect(at(SELECTED_REACH_LAYER)).toBeGreaterThan(at('water.network.reaches-piped'));
		expect(at(SELECTED_REACH_LAYER)).toBeLessThan(at(ANCHORS.water));
		// The layer adds no draped run of its own: the style has as many as it has without the layer, and the
		// run from the ground to the routes is still one.
		const without = buildStyle(manifest, 'http://x', false, 'valley', { contributions: [water] }).layers;
		// (Anchors stay hidden, as they are; the layer’s own layers are shown, as when it is on.)
		const mine = new Set([...bakedLayers(), ...pointLayers()].map((x) => x.layer.id));
		const shown = (ls: LayerSpecification[]) => ls.map((l) => ordered(l, mine.has(l.id) || l.id.startsWith('water.network.') ? true : undefined));
		expect(rttStacks(shown(style))).toBe(rttStacks(shown(without)));
		const block = style.slice(at(ANCHORS.ground), at(ANCHORS.routes) + 1);
		expect(drapedRuns(shown(block))).toHaveLength(1);
	});

	it('are valid style layers', () => {
		const style = { version: 8 as const, sources: { landscape: { type: 'vector' as const, tiles: ['http://x/{z}/{x}/{y}'] }, 'water-points': { type: 'geojson' as const, data: pointFeatures({ structures: [], gauges: [] }) }, 'water-notices': { type: 'geojson' as const, data: noticeFeatures({ hazards: [], ecoli: [] }) } }, glyphs: 'http://x/{fontstack}/{range}.pbf', sprite: 'http://x/sprite', layers: [...bakedLayers(), ...pointLayers()].map((s) => s.layer) };
		const errors = validateStyleMin(style as never, latest as never);
		expect(errors.map((e) => `${e.identifier ?? ''} ${e.message}`)).toEqual([]);
	});

	it('draw water’s names in italics and nothing here carries a casing (K5)', () => {
		for (const s of bakedLayers()) {
			const l = s.layer as LayerSpecification & { layout?: Record<string, unknown>; paint?: Record<string, unknown> };
			expect(l.id).not.toMatch(/casing/i);
			expect(Object.keys(l.paint ?? {})).not.toContain('line-gap-width');
			if (l.type === 'symbol') expect(l.layout?.['text-font']).toEqual(['Noto Sans Italic']);
		}
		// The picked line is one line, wider than the base's but the same kind, not a pair.
		const picked = bakedLayers().find((s) => s.layer.id === SELECTED_REACH_LAYER)!.layer as LayerSpecification & { paint: Record<string, unknown> };
		expect(Object.keys(picked.paint).sort()).toEqual(['line-color', 'line-width']);
	});

	it('start hidden and draw only from the right sources', () => {
		for (const s of [...bakedLayers(), ...pointLayers()]) expect((s.layer as { layout?: { visibility?: string } }).layout?.visibility, s.layer.id).toBe('none');
		for (const s of bakedLayers()) expect((s.layer as { source: string }).source).toBe('landscape');
		expect(BAKED_LAYERS.slice().sort()).toEqual(bakedLayers().map((s) => s.layer.id).sort());
		expect(pointLayers().map((s) => s.layer.id)).toEqual([STRUCTURE_LAYER, STRUCTURE_MID_LAYER, STRUCTURE_FINE_LAYER, GAUGE_LAYER, NOTICE_LAYER]);
	});

	it('follow the Base look where their colours differ', () => {
		const ids = new Set([...bakedLayers().map((s) => s.layer.id)]);
		for (const [id, p] of Object.entries(flavorPaints())) {
			expect(ids.has(id), id).toBe(true);
			expect(Object.keys(p.clay).sort(), id).toEqual(Object.keys(p.valley).sort());
		}
		expect(flavorPaints()[LABEL_BODY_LAYER].valley['text-color']).not.toBe(flavorPaints()[LABEL_BODY_LAYER].clay['text-color']);
		expect(Object.keys(flavorPaints())).toContain(SELECTED_BODY_LAYER);
	});
});

describe('the structure layers', () => {
	it('split by first zoom so each structure shows from its own, with none shown twice or never', () => {
		const layers = pointLayers().map((s) => s.layer as unknown as { id: string; minzoom?: number; filter: unknown[] });
		const structure = layers.filter((l) => l.id.startsWith('water-structures'));
		expect(structure.map((l) => l.minzoom)).toEqual([9, 12, 14]);
		const bucket = (z: number) =>
			structure.filter((l) => {
				const b = (l.filter[2] as unknown[]);
				const f = (op: unknown[]) => (op[0] === '<=' ? z <= (op[2] as number) : z >= (op[2] as number));
				return b[0] === 'all' ? (b.slice(1) as unknown[][]).every(f) : f(b as unknown[]);
			}).length;
		for (const z of [8, 11, 12, 13, 14, 16]) expect(bucket(z), `minzoom ${z}`).toBe(1);
	});
});

describe('the points', () => {
	it('puts gauges and structures on the map, a flooding gauge’s category in its label', () => {
		const fc = pointFeatures({
			gauges: [
				{ lid: 'XTEST1', name: 'Example Canal Diversion', lng: -116.19, lat: 43.6, flood: null },
				{ lid: 'XTEST2', name: 'Example River at Nowhere', lng: -116.29, lat: 43.6, flood: 'minor' }
			],
			structures: [
				{ id: 9, kind: 'dam', name: 'Example Dam', minzoom: 11, lng: -116.31, lat: 43.6 },
				{ id: 10, kind: 'weir', name: null, minzoom: 13, lng: -116.3, lat: 43.61 }
			]
		});
		const p = fc.features.map((f) => f.properties!);
		expect(p.map((x) => x.id)).toEqual([pointId.gauge('XTEST1'), pointId.gauge('XTEST2'), pointId.structure(9), pointId.structure(10)]);
		expect(p[0].label).toBe('Example Canal Diversion');
		expect('flood' in p[0]).toBe(false);
		expect(p[1]).toMatchObject({ flood: 'minor', label: 'Example River at Nowhere · minor flooding' });
		expect(p[3]).toMatchObject({ name: 'Weir', label: 'Weir', minzoom: 13, kind: 'weir' });
	});

	it('draws a hazard or an E. coli site only where it has a place', () => {
		const fc = noticeFeatures({
			hazards: [
				{ id: '101', kind: 'temporary', status: 'active', name: 'Fallen tree', description: null, mile_marker: null, since: null, edited: null, lng: -116.21, lat: 43.61 },
				{ id: '102', kind: 'extreme', status: 'active', name: null, description: null, mile_marker: null, since: null, edited: null, lng: null, lat: null }
			],
			ecoli: [
				{ id: 'S1', site: 'Pond', sampled: '2030-07-01', result: 3, units: 'MPN/100 mL', lng: -116.2, lat: 43.6, history: [] },
				{ id: 'S2', site: null, sampled: '2030-07-01', result: 3, units: null, lng: null, lat: 43.6, history: [] }
			]
		});
		expect(fc.features.map((f) => f.properties!.id)).toEqual(['h:101', 'e:S1']);
		expect(fc.features[1].properties!.label).toBe('Pond · E. coli');
	});
});

describe('the badges', () => {
	it('have a shape each (never colour alone), and all five are drawn', () => {
		expect(MARKERS.map((m) => m.image).sort()).toEqual(Object.values(IMAGE).sort());
		expect(new Set(MARKERS.map((m) => m.shape)).size).toBe(MARKERS.length);
		for (const m of MARKERS) expect(m.marks.length).toBeGreaterThan(8);
	});

	it('are painted in a browser only', () => {
		expect(markerImage(IMAGE.gauge)).toBeNull();
	});
});
