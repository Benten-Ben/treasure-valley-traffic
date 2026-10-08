import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AppCtx } from '#lib/app/context.js';
import { FETCH_DEBOUNCE_MS, TreesModule } from './index.svelte.js';
import { CREDIT_LAYER, DISCS, SOURCE, type TreeRow } from './trees.js';

/**
 * The Trees module against a fake map, fetch and timers: only the newest
 * request for the view's trees may land (an answer for an earlier view must
 * never replace the current one's trees).
 */

type View = { zoom: number; center: [number, number] };
/** A view a little under a kilometre across around `center`. */
const bounds = ({ center: [x, y] }: View) => [x - 0.005, y - 0.003, x + 0.005, y + 0.003];
const V1: View = { zoom: 14, center: [-116.21, 43.62] };
const V2: View = { zoom: 14, center: [-116.17, 43.62] };
/** Nothing built here. */
const FAR_AWAY: View = { zoom: 14, center: [-115.5, 43.62] };

/** A made-up tree at a view's centre (no real records). */
const tree = (id: string, v: View): TreeRow => ({ id, kind: 'placed', type: 'broadleaf', lng: v.center[0], lat: v.center[1], h: 12, r: 4, a: null, n: null });

function fakeMap() {
	const handlers = new Map<string, Set<(e: object) => void>>();
	const layers = new Map<string, { id: string; layout?: Record<string, unknown> }>();
	const sources = new Map<string, { data: GeoJSON.FeatureCollection; setData(d: GeoJSON.FeatureCollection): void }>();
	let view: View = V1;
	const map = {
		addSource(id: string, spec: { data: GeoJSON.FeatureCollection }) {
			sources.set(id, {
				data: spec.data,
				setData(d) {
					this.data = d;
				}
			});
		},
		getSource: (id: string) => sources.get(id),
		removeSource: (id: string) => sources.delete(id),
		addLayer: (l: { id: string; layout?: Record<string, unknown> }) => void layers.set(l.id, { ...l }),
		getLayer: (id: string) => layers.get(id),
		removeLayer: (id: string) => layers.delete(id),
		getLayersOrder: () => [...layers.keys()],
		setLayoutProperty(id: string, k: string, v: unknown) {
			const l = layers.get(id)!;
			l.layout = { ...l.layout, [k]: v };
		},
		setPaintProperty() {},
		setLayerZoomRange() {},
		setFeatureState() {},
		triggerRepaint() {},
		on(type: string, f: (e: object) => void) {
			if (!handlers.has(type)) handlers.set(type, new Set());
			handlers.get(type)!.add(f);
		},
		off: (type: string, f: (e: object) => void) => void handlers.get(type)?.delete(f),
		getZoom: () => view.zoom,
		getCenter: () => ({ lng: view.center[0], lat: view.center[1] }),
		getBounds: () => {
			const [w, s, e, n] = bounds(view);
			return { getWest: () => w, getSouth: () => s, getEast: () => e, getNorth: () => n };
		},
		getCanvas: () => ({ clientWidth: 1280, clientHeight: 800 }),
		/** Jump to a view and say the map stopped there. */
		moveTo(v: View) {
			view = v;
			for (const f of handlers.get('zoom') ?? []) f({});
			for (const f of handlers.get('moveend') ?? []) f({});
		},
		/** The ids of the trees the discs show now. */
		shown: () => (sources.get(SOURCE)?.data.features ?? []).map((f) => String(f.properties?.id)),
		layers
	};
	return map;
}

/** A fake API: areas at once; each /api/trees request waits until the test answers it, and answers even after it was called off. */
function fakeApi() {
	const requests: { url: string; signal: AbortSignal; answer: (trees: TreeRow[]) => void }[] = [];
	const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as unknown as Response;
	const fetch = vi.fn((url: string, init?: RequestInit) => {
		if (url === '/api/trees/areas') return Promise.resolve(ok({ areas: [{ area: 'c', bounds: [-116.3, 43.5, -116.1, 43.7], trees: 2, built_at: null }] }));
		return new Promise<Response>((resolve) => {
			requests.push({ url, signal: init!.signal!, answer: (trees) => resolve(ok({ trees, truncated: false })) });
		});
	});
	return { fetch, requests };
}

const settle = () => vi.advanceTimersByTimeAsync(0);

describe('the Trees module asks for the view’s trees (docs/19 §19.6)', () => {
	let api: ReturnType<typeof fakeApi>;
	let map: ReturnType<typeof fakeMap>;
	let trees: TreesModule;

	beforeEach(async () => {
		vi.useFakeTimers();
		api = fakeApi();
		vi.stubGlobal('fetch', api.fetch);
		map = fakeMap();
		const ctx = {
			styleReady: Promise.resolve(map),
			picker: { onHover: () => () => {} },
			scene: () => Promise.reject(new Error('no scene in this test'))
		} as unknown as AppCtx;
		trees = new TreesModule();
		await trees.mount(ctx);
		trees.setVisible(true);
		await settle();
		// The first view's trees.
		expect(api.requests).toHaveLength(1);
		api.requests[0].answer([tree('v1', V1)]);
		await settle();
		expect(map.shown()).toEqual(['v1']);
	});

	afterEach(() => {
		trees.destroy();
		vi.unstubAllGlobals();
		vi.useRealTimers();
	});

	/** Move, and let the debounce run. */
	const moveTo = async (v: View) => {
		map.moveTo(v);
		await vi.advanceTimersByTimeAsync(FETCH_DEBOUNCE_MS);
	};

	it('a late answer for a view left behind doesn’t replace the trees of the view it came back to', async () => {
		await moveTo(V2);
		expect(api.requests).toHaveLength(2);
		const late = api.requests[1];
		// Back before it answers: what was fetched for V1 still serves, so nothing new is asked for.
		await moveTo(V1);
		expect(api.requests).toHaveLength(2);
		expect(late.signal.aborted).toBe(true);
		late.answer([tree('v2', V2)]);
		await settle();
		expect(map.shown()).toEqual(['v1']);
		expect(trees.view.kinds.placed).toBe(1);
	});

	it('a late answer doesn’t put trees back where nothing is built', async () => {
		await moveTo(V2);
		const late = api.requests[1];
		await moveTo(FAR_AWAY);
		expect(late.signal.aborted).toBe(true);
		expect(trees.view.here).toBe(false);
		expect(map.shown()).toEqual([]);
		late.answer([tree('v2', V2)]);
		await settle();
		expect(map.shown()).toEqual([]);
		expect(trees.view.shown).toBe(0);
		expect(trees.view.kinds).toEqual({ catalogued: 0, placed: 0, estimated: 0 });
	});

	it('a late answer doesn’t land once zoomed out past the discs', async () => {
		await moveTo(V2);
		const late = api.requests[1];
		await moveTo({ ...V2, zoom: 12 });
		expect(late.signal.aborted).toBe(true);
		late.answer([tree('v2', V2)]);
		await settle();
		expect(map.shown()).toEqual(['v1']);
	});

	it('the newest answer lands, and the same box isn’t asked for twice while it’s on its way', async () => {
		await moveTo(V2);
		map.moveTo(V2);
		await vi.advanceTimersByTimeAsync(FETCH_DEBOUNCE_MS);
		expect(api.requests).toHaveLength(2);
		api.requests[1].answer([tree('v2', V2)]);
		await settle();
		expect(map.shown()).toEqual(['v2']);
	});

	it('shows its discs and its credit layer only while on', () => {
		expect(map.layers.get(DISCS)?.layout?.visibility).toBe('visible');
		expect(map.layers.get(CREDIT_LAYER)?.layout?.visibility).toBe('visible');
		trees.setVisible(false);
		expect(map.layers.get(DISCS)?.layout?.visibility).toBe('none');
		expect(map.layers.get(CREDIT_LAYER)?.layout?.visibility).toBe('none');
	});
});
