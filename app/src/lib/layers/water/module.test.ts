import type { MapGeoJSONFeature } from 'maplibre-gl';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AppCtx } from '#lib/app/context.js';
import { BODIES_LAYER, REACH_SOLID_LAYER } from '#lib/base/water/water.base.js';
import { WETLAND_THIN_LAYER, WETLAND_TUFT_LAYER } from '#lib/base/water/wetlands.base.js';
import { basemapReady, type BasemapManifest } from '#lib/map/style.js';
import { PRIORITY, type Selection } from '../types.js';
import { NOTICES_URL, POINTS_URL } from './def.js';
import { WaterModule, type WaterSelectionData } from './index.svelte.js';
import { GAUGE_LAYER, LABEL_BODY_LAYER, LABEL_MAIN_LAYER, NOTICE_LAYER, SELECTED_BODY_LAYER, SELECTED_REACH_LAYER, STRUCTURE_FINE_LAYER, STRUCTURE_LAYER } from './layers.js';
import { CREDITS, type Notices, type WaterPoints } from './water.js';

beforeAll(() => basemapReady);

/** The Water module against a fake map, fetch and context: made-up rows, no real records. */

const baked = (credit: string[] = ['© OpenStreetMap contributors', 'HydroShare (CC BY 4.0)']): BasemapManifest =>
	({
		bounds: [-117.05, 43, -115.95, 43.85],
		center: [-116.4, 43.6],
		zoom: 10,
		basemap: { file: 'valley.pmtiles', flavor: 'light', attribution: 'OSM', built: '2026-10-05' },
		glyphs: '',
		sprite: '',
		landscape: {
			status: 'baked',
			file: 'landscape-1.pmtiles',
			digest: '1',
			format: 'pbf',
			minzoom: 8,
			maxzoom: 16,
			promoteId: 'id',
			layers: Object.fromEntries(['water.bodies', 'water.reaches'].map((k) => [k, { plugin: 'water', layer: k.split('.')[1], build: 'b', geometry: 'x', features: 2, fields: {}, minzoom: 8, maxzoom: 16, licence: 'ODbL-1.0', republish: 'yes', credit }])),
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
	}) as BasemapManifest;

const unbaked = (): BasemapManifest => {
	const m = baked();
	return { ...m, landscape: undefined } as BasemapManifest;
};

type Layer = { id: string; layout?: Record<string, unknown>; filter?: unknown; minzoom?: number; maxzoom?: number };

function fakeMap(opts: { landscape: boolean }) {
	const layers = new Map<string, Layer>();
	// The basemap's water labels, which the layer hides only while its own italic names draw.
	for (const id of ['water_waterway_label', 'water_label_lakes', 'water']) layers.set(id, { id, layout: { visibility: 'visible' }, minzoom: 0, maxzoom: 24 });
	const sources = new Map<string, { data?: GeoJSON.FeatureCollection; attribution?: string }>();
	if (opts.landscape) sources.set('landscape', {});
	const images = new Set<string>();
	return {
		layers,
		sources,
		addSource: (id: string, spec: { data?: GeoJSON.FeatureCollection; attribution?: string }) => void sources.set(id, spec),
		getSource: (id: string) => sources.get(id),
		removeSource: (id: string) => sources.delete(id),
		addLayer: (l: Layer) => void layers.set(l.id, { ...l, layout: { ...l.layout } }),
		getLayer: (id: string) => layers.get(id),
		removeLayer: (id: string) => layers.delete(id),
		getLayersOrder: () => [...layers.keys()],
		getLayoutProperty: (id: string, k: string) => layers.get(id)?.layout?.[k],
		setLayoutProperty(id: string, k: string, v: unknown) {
			const l = layers.get(id)!;
			l.layout = { ...l.layout, [k]: v };
		},
		setLayerZoomRange(id: string, min: number, max: number) {
			const l = layers.get(id)!;
			l.minzoom = min;
			l.maxzoom = max;
		},
		setFilter: (id: string, f: unknown) => void (layers.get(id)!.filter = f),
		setPaintProperty() {},
		hasImage: (id: string) => images.has(id),
		addImage: (id: string) => void images.add(id),
		removeImage: (id: string) => void images.delete(id)
	};
}

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as unknown as Response;
const failed = (status: number) => ({ ok: false, status, json: async () => ({ message: `boom ${status}` }) }) as unknown as Response;

const POINTS: WaterPoints = {
	structures: [{ id: 9, kind: 'dam', name: 'Example Dam', minzoom: 11, lng: -116.31, lat: 43.6 }],
	gauges: [
		{ lid: 'XTEST1', name: 'Example Canal Diversion', lng: -116.19, lat: 43.6, flood: null },
		{ lid: 'XTEST2', name: 'Example River at Nowhere', lng: -116.29, lat: 43.6, flood: 'minor' }
	],
	credit: []
};

const NOTICES: Notices = {
	hazards: [{ id: '101', kind: 'temporary', status: 'active', name: 'Fallen tree', description: 'Tree across the right channel', mile_marker: '4.2', since: null, edited: null, lng: -116.21, lat: 43.61 }],
	ecoli: [{ id: 'S1', site: 'Example Pond', sampled: '2030-07-01', result: 456.7, units: 'MPN/100 mL', lng: -116.2, lat: 43.6, history: [] }],
	polled: { boise_river_hazards: null, boise_ecoli: null },
	credit: [],
	license: 'none stated',
	republish: 'internal'
};

/** A baked feature as MapLibre hands it to a pick function. */
const feature = (layer: string, properties: Record<string, unknown>, geometry: unknown = { type: 'LineString', coordinates: [] }) =>
	({ layer: { id: layer }, properties, geometry }) as unknown as MapGeoJSONFeature;

describe('the Water module', () => {
	let fetchMock: ReturnType<typeof vi.fn>;
	let api: Record<string, () => Response>;

	const mount = async (manifest: BasemapManifest, map = fakeMap({ landscape: Boolean(manifest.landscape) }), current: Selection | null = null) => {
		const ctx = { styleReady: Promise.resolve(map), manifest, meta: null, selection: { current } } as unknown as AppCtx;
		const water = new WaterModule();
		await water.mount(ctx);
		return { water, map };
	};

	beforeEach(() => {
		api = { [POINTS_URL]: () => ok(POINTS), [NOTICES_URL]: () => ok(NOTICES) };
		fetchMock = vi.fn((url: string) => Promise.resolve(api[url]?.() ?? failed(404)));
		vi.stubGlobal('fetch', fetchMock);
	});

	afterEach(() => vi.unstubAllGlobals());

	it('adds its badges hidden, its sources full, and shows them only while on', async () => {
		const { water, map } = await mount(baked());
		expect(water.status).toBe('ready');
		expect(water.baked).toBe(true);
		expect((map.sources.get('water-points')!.data as GeoJSON.FeatureCollection).features).toHaveLength(3);
		expect((map.sources.get('water-notices')!.data as GeoJSON.FeatureCollection).features).toHaveLength(2);
		for (const id of [GAUGE_LAYER, STRUCTURE_LAYER, STRUCTURE_FINE_LAYER, NOTICE_LAYER, LABEL_MAIN_LAYER]) expect(map.layers.get(id)?.layout?.visibility, id).toBe('none');
		water.setVisible(true);
		for (const id of [GAUGE_LAYER, STRUCTURE_LAYER, STRUCTURE_FINE_LAYER, NOTICE_LAYER, LABEL_MAIN_LAYER, LABEL_BODY_LAYER]) expect(map.layers.get(id)?.layout?.visibility, id).toBe('visible');
		// The picked shapes stay hidden until something is picked.
		for (const id of [SELECTED_REACH_LAYER, SELECTED_BODY_LAYER]) expect(map.layers.get(id)?.layout?.visibility, id).toBe('none');
		water.setVisible(false);
		for (const id of [GAUGE_LAYER, STRUCTURE_LAYER, NOTICE_LAYER, LABEL_MAIN_LAYER]) expect(map.layers.get(id)?.layout?.visibility, id).toBe('none');
		water.destroy();
		expect(map.layers.has(GAUGE_LAYER)).toBe(false);
		expect(map.sources.has('water-points')).toBe(false);
	});

	it('credits what the badges draw in the map’s attribution card: NWPS, OSM and NHD for the points, the City for its notices', async () => {
		const { map } = await mount(baked());
		const points = map.sources.get('water-points')?.attribution ?? '';
		for (const c of [CREDITS.nwps, CREDITS.osm, CREDITS.nhd]) expect(points, c).toContain(c);
		const notices = map.sources.get('water-notices')?.attribution ?? '';
		for (const c of [CREDITS.boiseHazards, CREDITS.boiseEcoli]) expect(notices, c).toContain(c);
	});

	it('hides the basemap’s water names only while its own italic ones draw', async () => {
		const { water, map } = await mount(baked());
		const names = ['water_waterway_label', 'water_label_lakes'];
		expect(names.map((n) => map.layers.get(n)?.layout?.visibility)).toEqual(['visible', 'visible']);
		water.setVisible(true);
		expect(names.map((n) => map.layers.get(n)?.layout?.visibility)).toEqual(['none', 'none']);
		water.setVisible(false);
		expect(names.map((n) => map.layers.get(n)?.layout?.visibility)).toEqual(['visible', 'visible']);
	});

	it('with no baked water adds no names or picked shapes, and leaves the basemap’s names alone', async () => {
		const { water, map } = await mount(unbaked());
		expect(water.baked).toBe(false);
		for (const id of [LABEL_MAIN_LAYER, LABEL_BODY_LAYER, SELECTED_REACH_LAYER, SELECTED_BODY_LAYER]) expect(map.layers.has(id), id).toBe(false);
		water.setVisible(true);
		expect(map.layers.get('water_waterway_label')?.layout?.visibility).toBe('visible');
		expect(map.layers.get('water_label_lakes')?.layout?.visibility).toBe('visible');
		// The gauges, hazards and structures still draw.
		expect(map.layers.get(GAUGE_LAYER)?.layout?.visibility).toBe('visible');
	});

	it('takes the baked layers’ credits from the manifest, HydroShare when its names are used', async () => {
		const { water } = await mount(baked(['© OpenStreetMap contributors', 'HydroShare (CC BY 4.0)']));
		expect(water.bakedCredit).toEqual(['© OpenStreetMap contributors', 'HydroShare (CC BY 4.0)']);
		const { water: plain } = await mount(baked(['© OpenStreetMap contributors']));
		expect(plain.bakedCredit).toEqual(['© OpenStreetMap contributors']);
	});

	it('opens cards only while on: the baked lines and areas pick at water’s priority, the badges one above', async () => {
		const { water } = await mount(baked());
		const [baseInteractive, pointInteractive] = water.interactive;
		expect(baseInteractive.priority).toBe(PRIORITY.water);
		expect(pointInteractive.priority).toBe(PRIORITY.water + 1);
		expect(baseInteractive.layerIds).toContain(REACH_SOLID_LAYER);
		expect(baseInteractive.layerIds).toContain(BODIES_LAYER);
		// A wetland is the tuft layers' polygon (the bodies' fill leaves it out), so a click on either kind opens its card.
		expect(baseInteractive.layerIds).toContain(WETLAND_TUFT_LAYER);
		expect(baseInteractive.layerIds).toContain(WETLAND_THIN_LAYER);
		const canal = feature(REACH_SOLID_LAYER, { id: 7001, kind: 'canal', name: 'Fixture Main Canal', width_m: 14, intermittent: false, piped: false, nhd_only: false, canal: 1 });
		expect(baseInteractive.pick(canal)).toBeNull();
		water.setVisible(true);
		const sel = baseInteractive.pick(canal)!;
		expect(sel).toMatchObject({ kind: 'water', layer: 'water', id: 'reach:7001', title: 'Fixture Main Canal', fact: 'Canal · about 14 m wide', source: 'OpenStreetMap · USGS NHD' });
		expect(sel.data).toMatchObject({ type: 'reach', id: 7001, canal: 1, nhd_only: false });
		const nhd = baseInteractive.pick(feature(REACH_SOLID_LAYER, { id: 2251799813686239, kind: 'stream', name: '', width_m: 3, intermittent: 1, piped: 0, nhd_only: 1, canal: 0 }))!;
		expect(nhd.title).toBe('Unnamed creek or stream');
		expect(nhd.fact).toContain('federal map only');
		expect(nhd.source).toContain('not in OpenStreetMap');
		expect(nhd.id).toBe('reach:2251799813686239');
		const pond = baseInteractive.pick(feature(BODIES_LAYER, { id: 8001, kind: 'pond', name: 'Fixture Pond', intermittent: false, nhd_only: false }, { type: 'Polygon', coordinates: [] }))!;
		expect(pond).toMatchObject({ id: 'body:8001', title: 'Fixture Pond', fact: 'Pond' });
		expect(baseInteractive.pick(feature(BODIES_LAYER, { id: 8002, kind: 'not-a-kind' }))).toBeNull();
		for (const layer of [WETLAND_TUFT_LAYER, WETLAND_THIN_LAYER]) {
			const marsh = baseInteractive.pick(feature(layer, { id: 8003, kind: 'wetland', name: '', intermittent: false, nhd_only: false, thin: layer === WETLAND_THIN_LAYER }, { type: 'Polygon', coordinates: [] }))!;
			expect(marsh, layer).toMatchObject({ id: 'body:8003', title: 'Unnamed wetland', fact: 'Wetland', data: { type: 'body', id: 8003, kind: 'wetland' } });
		}
		expect(baseInteractive.pick(feature(REACH_SOLID_LAYER, { kind: 'canal' }))).toBeNull();
	});

	it('picks badges: a gauge (its flood in words), a structure, a hazard and an E. coli site, with their points', async () => {
		const { water } = await mount(baked());
		water.setVisible(true);
		const point = (props: Record<string, unknown>, at: [number, number] = [-116.2, 43.6]) => feature(GAUGE_LAYER, props, { type: 'Point', coordinates: at });
		const pick = water.interactive[1].pick;
		const g = pick(point({ kind: 'gauge', lid: 'XTEST2', name: 'Example River at Nowhere', flood: 'minor' }))!;
		expect(g).toMatchObject({ id: 'g:XTEST2', title: 'Example River at Nowhere', fact: 'Gauge · minor flooding', at: [-116.2, 43.6], data: { type: 'gauge', lid: 'XTEST2' } });
		expect(pick(point({ kind: 'gauge', lid: 'XTEST1', name: 'Example Canal Diversion' }))!.fact).toBe('Gauge');
		expect(pick(point({ kind: 'dam', sid: 9, name: 'Example Dam' }))).toMatchObject({ id: 's:9', fact: 'Dam', data: { type: 'structure', id: 9 } });
		expect(pick(point({ kind: 'hazard', hid: '101' }))).toMatchObject({ id: 'h:101', title: 'Fallen tree', fact: 'Temporary hazard · active', source: 'City of Boise (Float the Boise)' });
		expect(pick(point({ kind: 'ecoli', eid: 'S1' }))).toMatchObject({ id: 'e:S1', title: 'Example Pond', fact: 'E. coli 456.7 MPN/100 mL · 2030-07-01' });
		// A notice that is no longer listed picks nothing.
		expect(pick(point({ kind: 'hazard', hid: '999' }))).toBeNull();
		expect(pick(point({ kind: 'weir', sid: 'x', name: 'Bad' }))).toBeNull();
		water.setVisible(false);
		expect(pick(point({ kind: 'gauge', lid: 'XTEST1', name: 'x' }))).toBeNull();
	});

	it('draws the picked reach or area wider, and clears it for anything else', async () => {
		const { water, map } = await mount(baked());
		water.setVisible(true);
		const reach: Selection = { kind: 'water', id: 'reach:7001', layer: 'water', title: 'x', data: { type: 'reach', id: 7001, kind: 'canal', name: null, width_m: 4, intermittent: false, piped: false, nhd_only: false, canal: 0 } satisfies WaterSelectionData };
		water.selected(reach);
		expect(map.layers.get(SELECTED_REACH_LAYER)).toMatchObject({ filter: ['==', ['get', 'id'], 7001], layout: { visibility: 'visible' } });
		expect(map.layers.get(SELECTED_BODY_LAYER)?.layout?.visibility).toBe('none');
		const body: Selection = { kind: 'water', id: 'body:8001', layer: 'water', title: 'x', data: { type: 'body', id: 8001, kind: 'pond', name: null, intermittent: false, nhd_only: false } satisfies WaterSelectionData };
		water.selected(body);
		expect(map.layers.get(SELECTED_BODY_LAYER)).toMatchObject({ filter: ['==', ['get', 'id'], 8001], layout: { visibility: 'visible' } });
		expect(map.layers.get(SELECTED_REACH_LAYER)?.layout?.visibility).toBe('none');
		// A gauge, someone else's selection or none clears both.
		water.selected({ kind: 'water', id: 'g:X', layer: 'water', title: 'x', data: { type: 'gauge', lid: 'X' } });
		expect([SELECTED_REACH_LAYER, SELECTED_BODY_LAYER].map((id) => map.layers.get(id)?.layout?.visibility)).toEqual(['none', 'none']);
		water.selected(reach);
		water.selected({ kind: 'street', id: '1', layer: 'streets', title: 's' });
		expect(map.layers.get(SELECTED_REACH_LAYER)?.layout?.visibility).toBe('none');
		// Turning the layer off puts the picked shape away.
		water.selected(reach);
		water.setVisible(false);
		expect(map.layers.get(SELECTED_REACH_LAYER)?.layout?.visibility).toBe('none');
	});

	it('shows a selection made before it was on, once it is', async () => {
		const sel: Selection = { kind: 'water', id: 'reach:7001', layer: 'water', title: 'x', data: { type: 'reach', id: 7001, kind: 'canal', name: null, width_m: 4, intermittent: false, piped: false, nhd_only: false, canal: 0 } };
		const { water, map } = await mount(baked(), undefined, sel);
		expect(map.layers.get(SELECTED_REACH_LAYER)?.layout?.visibility).toBe('none');
		water.setVisible(true);
		// (the manager tells a module the selection when it turns the layer on)
		water.selected(sel);
		expect(map.layers.get(SELECTED_REACH_LAYER)?.layout?.visibility).toBe('visible');
	});

	it('fails with the reason when the water points cannot be loaded, and goes on without the notices', async () => {
		api[POINTS_URL] = () => failed(503);
		const w1 = new WaterModule();
		await expect(w1.mount({ styleReady: Promise.resolve(fakeMap({ landscape: true })), manifest: baked(), meta: null, selection: { current: null } } as unknown as AppCtx)).rejects.toThrow('Water unavailable: boom 503');
		expect(w1.status).toBe('error');
		expect(w1.error).toContain('boom 503');

		api[POINTS_URL] = () => ok(POINTS);
		api[NOTICES_URL] = () => failed(500);
		const { water } = await mount(baked());
		expect(water.status).toBe('ready');
		expect(water.noticesProblem).toContain("Couldn't load the river notices");
		expect(water.notices).toBeNull();
		expect(water.summary()).toBe('2 gauges');
	});

	it('asks for a thing’s details once and keeps them; a 404 is null and a failure is asked again', async () => {
		const { water } = await mount(baked());
		const calls = () => fetchMock.mock.calls.map((c) => c[0] as string).filter((u) => u.startsWith('/api/water/reach/'));
		api['/api/water/reach/7001'] = () => ok({ id: 7001, kind: 'canal' });
		expect(await water.detail('reach', 7001)).toEqual({ id: 7001, kind: 'canal' });
		expect(await water.detail('reach', 7001)).toEqual({ id: 7001, kind: 'canal' });
		expect(calls()).toEqual(['/api/water/reach/7001']);
		expect(await water.detail('reach', 7002)).toBeNull();
		api['/api/water/gauge/XTEST1'] = () => failed(500);
		await expect(water.detail('gauge', 'XTEST1')).rejects.toThrow('boom 500');
		api['/api/water/gauge/XTEST1'] = () => ok({ lid: 'XTEST1' });
		expect(await water.detail('gauge', 'XTEST1')).toEqual({ lid: 'XTEST1' });
		expect(fetchMock.mock.calls.map((c) => c[0])).toContain('/api/water/gauge/XTEST1');
	});
});
