import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AppCtx } from '#lib/app/context.js';
import type { StaticSegment } from '#lib/scene/batches/static.js';
import { type FenceCollection, GROUP, HALO_LAYER, LINE_LAYER, POSTS_LAYER, SOURCE } from './fences.js';
import { FencesModule, REBUILD_DEBOUNCE_MS } from './index.svelte.js';

/**
 * The Fences module against a fake map, scene and fetch: one GeoJSON feeds the 2D line, the 3D batch is built from
 * z15.5 once the scene runs, built again when the view has moved a good way, and never built on a phone.
 */

const C: [number, number] = [-116.2, 43.6];
const step = 10 / (111_320 * Math.cos((C[1] * Math.PI) / 180));
const line = (id: string, lng: number): GeoJSON.Feature<GeoJSON.LineString> => ({
	type: 'Feature',
	id,
	geometry: { type: 'LineString', coordinates: [[lng, C[1]], [lng + step, C[1]], [lng + 2 * step, C[1]]] },
	properties: { id, type: 'fence', look: 'open', h: 1.8, hs: 'tagged', m: null, ft: null, len: 20, name: null }
});
const DATA = { type: 'FeatureCollection', features: [line('osm:w1', C[0]), line('osm:w2', C[0] + 0.1)] } as FenceCollection;

function fakeMap() {
	const handlers = new Map<string, Set<(e: object) => void>>();
	const layers = new Map<string, { id: string; layout?: Record<string, unknown> }>();
	const sources = new Map<string, { data: unknown }>();
	let view = { zoom: 14, center: C };
	return {
		addSource: (id: string, spec: { data: unknown }) => void sources.set(id, { data: spec.data }),
		getSource: (id: string) => sources.get(id),
		removeSource: (id: string) => sources.delete(id),
		addLayer: (l: { id: string }) => void layers.set(l.id, { ...l }),
		getLayer: (id: string) => layers.get(id),
		removeLayer: (id: string) => layers.delete(id),
		getLayersOrder: () => [...layers.keys()],
		setLayoutProperty(id: string, k: string, v: unknown) {
			layers.get(id)!.layout = { ...layers.get(id)!.layout, [k]: v };
		},
		setFeatureState() {},
		on: (t: string, f: (e: object) => void) => void (handlers.get(t) ?? handlers.set(t, new Set()).get(t)!).add(f),
		off: (t: string, f: (e: object) => void) => void handlers.get(t)?.delete(f),
		getZoom: () => view.zoom,
		getCenter: () => ({ lng: view.center[0], lat: view.center[1] }),
		moveTo(v: { zoom: number; center: [number, number] }) {
			view = v;
			for (const f of handlers.get('zoom') ?? []) f({});
			for (const f of handlers.get('moveend') ?? []) f({});
		},
		layers
	};
}

function fakeScene() {
	const calls: { setStatic: StaticSegment[][]; show: [string, boolean][]; showStatic: [string, boolean][]; removed: string[] } = { setStatic: [], show: [], showStatic: [], removed: [] };
	return {
		ok: true,
		set: vi.fn(),
		setStatic: (_g: string, s: StaticSegment[]) => calls.setStatic.push(s),
		show: (g: string, on: boolean) => calls.show.push([g, on]),
		showStatic: (g: string, on: boolean) => calls.showStatic.push([g, on]),
		remove: (g: string) => calls.removed.push(g),
		calls
	};
}

const settle = () => vi.advanceTimersByTimeAsync(0);

describe('the Fences module (plan P10)', () => {
	let map: ReturnType<typeof fakeMap>;
	let scene: ReturnType<typeof fakeScene>;
	let fences: FencesModule;
	let fetched: string[];

	async function start(phone = false) {
		vi.useFakeTimers();
		fetched = [];
		vi.stubGlobal('fetch', (url: string) => {
			fetched.push(url);
			return Promise.resolve({ ok: true, status: 200, json: async () => DATA } as unknown as Response);
		});
		vi.stubGlobal('matchMedia', () => ({ matches: phone }));
		map = fakeMap();
		scene = fakeScene();
		const ctx = {
			meta: { versions: { layers: { 'fences.lines': 'v1' } }, layers: { 'fences.lines': { credit: '© OpenStreetMap contributors' } } },
			styleReady: Promise.resolve(map),
			picker: { onHover: () => () => {} },
			scene: () => Promise.resolve(scene)
		} as unknown as AppCtx;
		fences = new FencesModule();
		await fences.mount(ctx);
		fences.setVisible(true);
		await settle();
	}

	beforeEach(() => start());
	afterEach(() => {
		fences.destroy();
		vi.unstubAllGlobals();
		vi.useRealTimers();
	});

	it('asks for the one versioned GeoJSON and feeds the 2D line with it', () => {
		expect(fetched).toEqual(['/api/fences/lines?v=v1']);
		expect(fences.status).toBe('ready');
		expect((map.getSource(SOURCE) as { data: FenceCollection }).data.features).toHaveLength(2);
		expect(fences.summary()).toBe('2 mapped fences and walls');
	});

	it('shows its three line layers only while on', () => {
		for (const id of [HALO_LAYER, LINE_LAYER, POSTS_LAYER]) expect(map.layers.get(id)?.layout?.visibility).toBe('visible');
		fences.setVisible(false);
		for (const id of [HALO_LAYER, LINE_LAYER, POSTS_LAYER]) expect(map.layers.get(id)?.layout?.visibility).toBe('none');
	});

	it('opens the card for a click on the line, at the fence priority', () => {
		const [i] = fences.interactive;
		expect(i.layerIds).toEqual([LINE_LAYER]);
		expect(i.priority).toBe(33);
		const sel = i.pick({ properties: DATA.features[0].properties, geometry: DATA.features[0].geometry } as never);
		expect(sel).toMatchObject({ kind: 'fence', layer: 'fences', id: 'osm:w1' });
	});

	it('builds no 3D walls below z15.5, builds them from there (the fences near the view only), and shows them', async () => {
		map.moveTo({ zoom: 15, center: C });
		await settle();
		expect(scene.calls.setStatic).toHaveLength(0);
		map.moveTo({ zoom: 16, center: C });
		await settle();
		expect(scene.calls.setStatic).toHaveLength(1);
		// Fence 1 is 4 segments' worth... two hops; fence 2 is 7 km east, outside the radius.
		expect(scene.calls.setStatic[0].map((s) => s.id)).toEqual(['osm:w1:0', 'osm:w1:1']);
		expect(scene.calls.showStatic.at(-1)).toEqual([GROUP, true]);
		expect(scene.calls.show.at(-1)).toEqual([GROUP, true]);
		expect(fences.view.walls).toBe(true);
		expect(fences.view.segments).toBe(2);
		// Zoomed out again: the batch stays, hidden.
		map.moveTo({ zoom: 15.2, center: C });
		await settle();
		expect(scene.calls.showStatic.at(-1)).toEqual([GROUP, false]);
	});

	it('builds the batch again when the view has moved a good way, not for a small move', async () => {
		map.moveTo({ zoom: 16, center: C });
		await settle();
		expect(scene.calls.setStatic).toHaveLength(1);
		map.moveTo({ zoom: 16, center: [C[0] + 0.001, C[1]] });
		await vi.advanceTimersByTimeAsync(REBUILD_DEBOUNCE_MS);
		expect(scene.calls.setStatic).toHaveLength(1);
		map.moveTo({ zoom: 16, center: [C[0] + 0.1, C[1]] });
		await vi.advanceTimersByTimeAsync(REBUILD_DEBOUNCE_MS);
		expect(scene.calls.setStatic).toHaveLength(2);
		expect(scene.calls.setStatic[1].map((s) => s.id)).toEqual(['osm:w2:0', 'osm:w2:1']);
	});

	it('hides the walls when switched off, and frees the batch when destroyed', async () => {
		map.moveTo({ zoom: 16, center: C });
		await settle();
		fences.setVisible(false);
		expect(scene.calls.showStatic.at(-1)).toEqual([GROUP, false]);
		fences.destroy();
		expect(scene.calls.removed).toEqual([GROUP]);
	});
});

describe('on a phone', () => {
	it('draws the line and builds no 3D walls', async () => {
		vi.useFakeTimers();
		vi.stubGlobal('fetch', () => Promise.resolve({ ok: true, status: 200, json: async () => DATA } as unknown as Response));
		vi.stubGlobal('matchMedia', () => ({ matches: true }));
		const map = fakeMap();
		const scene = fakeScene();
		const ctx = { meta: null, styleReady: Promise.resolve(map), picker: { onHover: () => () => {} }, scene: () => Promise.resolve(scene) } as unknown as AppCtx;
		const fences = new FencesModule();
		await fences.mount(ctx);
		fences.setVisible(true);
		map.moveTo({ zoom: 17, center: C });
		await vi.advanceTimersByTimeAsync(REBUILD_DEBOUNCE_MS);
		expect(map.layers.get(LINE_LAYER)?.layout?.visibility).toBe('visible');
		expect(scene.calls.setStatic).toHaveLength(0);
		expect(fences.view).toMatchObject({ phone: true, walls: false, segments: 0 });
		fences.destroy();
		vi.unstubAllGlobals();
		vi.useRealTimers();
	});
});

describe('when the data cannot be loaded', () => {
	it('says so and rejects', async () => {
		vi.stubGlobal('fetch', () => Promise.resolve({ ok: false, status: 503, json: async () => ({ message: 'no database' }) } as unknown as Response));
		const fences = new FencesModule();
		await expect(fences.mount({ meta: null, styleReady: Promise.resolve(fakeMap()) } as unknown as AppCtx)).rejects.toThrow('Fences unavailable: no database');
		expect(fences.status).toBe('error');
		vi.unstubAllGlobals();
	});
});
