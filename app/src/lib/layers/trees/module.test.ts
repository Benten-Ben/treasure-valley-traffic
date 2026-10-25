import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AppCtx } from '#lib/app/context.js';
import { FETCH_DEBOUNCE_MS, TreesModule } from './index.svelte.js';
import { SHRUB_CREDIT, SHRUBS_3D, SHRUBS_SCENE, type ShrubRow } from './shrubs.js';
import { CREDIT_LAYER, DISC_RING, DISCS, SOURCE, type TreeRow } from './trees.js';

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
	const sources = new Map<string, { data: GeoJSON.FeatureCollection; attribution?: string; setData(d: GeoJSON.FeatureCollection): void }>();
	let view: View = V1;
	const map = {
		addSource(id: string, spec: { data: GeoJSON.FeatureCollection; attribution?: string }) {
			sources.set(id, {
				data: spec.data,
				attribution: spec.attribution,
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
		attribution: () => sources.get(SOURCE)?.attribution,
		shown: () => (sources.get(SOURCE)?.data.features ?? []).map((f) => String(f.properties?.id)),
		layers
	};
	return map;
}

/** A fake API: areas at once; each /api/trees request waits until the test answers it, and answers even after it was called off. */
function fakeApi() {
	const requests: { url: string; signal: AbortSignal; answer: (trees: TreeRow[], catalogue?: boolean) => void }[] = [];
	const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as unknown as Response;
	const fetch = vi.fn((url: string, init?: RequestInit) => {
		if (url === '/api/trees/areas') return Promise.resolve(ok({ areas: [{ area: 'c', bounds: [-116.3, 43.5, -116.1, 43.7], trees: 2, built_at: null }] }));
		if (url === '/api/trees/shrubs/areas') return Promise.resolve(ok({ areas: [] }));
		return new Promise<Response>((resolve) => {
			requests.push({ url, signal: init!.signal!, answer: (trees, catalogue = false) => resolve(ok({ trees, truncated: false, catalogue })) });
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

	it('credits the City and lists the catalogue only once the API says the catalogue answers', async () => {
		// The first answer (a public install: no flag) credits the lidar alone.
		expect(map.attribution()).toBe('Trees: USGS 3DEP lidar; contains modified Copernicus Sentinel data 2025');
		expect(trees.view.catalogue).toBe(false);
		await moveTo(V2);
		api.requests[1].answer([tree('v2', V2)], true);
		await settle();
		expect(trees.view.catalogue).toBe(true);
		expect(map.attribution()).toBe('Trees: USGS 3DEP lidar, City of Boise; contains modified Copernicus Sentinel data 2025');
		expect(map.attribution()).not.toContain('Forest Service');
		// An answer without it takes the City back out.
		await moveTo(V1);
		await moveTo({ ...V1, zoom: 15, center: [V1.center[0] + 0.01, V1.center[1]] });
		api.requests[api.requests.length - 1].answer([tree('v3', V1)], false);
		await settle();
		expect(trees.view.catalogue).toBe(false);
		expect(map.attribution()).not.toContain('City of Boise');
	});

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
		expect(trees.view.kinds).toEqual({ catalogued: 0, placed: 0 });
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

	it('shows the cream ring with the discs, and Valley’s ring paint is registered with the Base look', () => {
		expect(map.layers.get(DISC_RING)?.layout?.visibility).toBe('visible');
		trees.setVisible(false);
		expect(map.layers.get(DISC_RING)?.layout?.visibility).toBe('none');
	});
});

/** A made-up shrub near a view's centre. */
const shrub = (id: string, v: View, i = 0): ShrubRow => ({ id, look: i % 2 ? 'sage' : 'bush', lng: v.center[0] + i * 1e-6, lat: v.center[1], h: 1.2, w: 2 });

/** A scene that records what it is given. */
function fakeScene() {
	const sets: { group: string; list: { id: string }[]; opts: unknown }[] = [];
	const shown = new globalThis.Map<string, boolean>();
	return {
		ok: true,
		sets,
		shown,
		set: (group: string, list: { id: string }[], opts: unknown) => void sets.push({ group, list: [...list], opts }),
		show: (group: string, on: boolean) => void shown.set(group, on),
		remove: (group: string) => void shown.delete(group),
		placed: () => [],
		stats: () => null
	};
}

describe('the Trees module draws shrubs from z17 (docs/19 §19.8)', () => {
	const Z17: View = { zoom: 17, center: [-116.21, 43.62] };
	const Z16: View = { zoom: 16.2, center: [-116.21, 43.62] };
	const Z15: View = { zoom: 15, center: [-116.21, 43.62] };
	let shrubRequests: { url: string; signal: AbortSignal; answer: (rows: ShrubRow[], truncated?: boolean) => void }[];
	let map: ReturnType<typeof fakeMap>;
	let scene: ReturnType<typeof fakeScene>;
	let trees: TreesModule;
	const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as unknown as Response;

	async function start(phone = false) {
		vi.useFakeTimers();
		shrubRequests = [];
		vi.stubGlobal('matchMedia', () => ({ matches: phone }));
		vi.stubGlobal(
			'fetch',
			vi.fn((url: string, init?: RequestInit) => {
				if (url === '/api/trees/areas') return Promise.resolve(ok({ areas: [{ area: 'c', bounds: [-116.3, 43.5, -116.1, 43.7], trees: 2, built_at: null }] }));
				if (url === '/api/trees/shrubs/areas') return Promise.resolve(ok({ areas: [{ area: 'c', bounds: [-116.3, 43.5, -116.1, 43.7], shrubs: 9, built_at: null }] }));
				if (url.startsWith('/api/trees/shrubs?'))
					return new Promise<Response>((resolve) =>
						shrubRequests.push({ url, signal: init!.signal!, answer: (rows, truncated = false) => resolve(ok({ shrubs: rows, truncated })) })
					);
				// Trees: an empty answer at once.
				return Promise.resolve(ok({ trees: [], truncated: false, catalogue: false }));
			})
		);
		map = fakeMap();
		scene = fakeScene();
		const ctx = { styleReady: Promise.resolve(map), picker: { onHover: () => () => {} }, scene: () => Promise.resolve(scene) } as unknown as AppCtx;
		trees = new TreesModule();
		await trees.mount(ctx);
		trees.setVisible(true);
		await settle();
	}

	afterEach(() => {
		trees.destroy();
		vi.unstubAllGlobals();
		vi.useRealTimers();
	});

	const moveTo = async (v: View) => {
		map.moveTo(v);
		await vi.advanceTimersByTimeAsync(FETCH_DEBOUNCE_MS);
	};

	it('asks for none below z16.5, and draws none below z17', async () => {
		await start();
		await moveTo(Z15);
		expect(shrubRequests).toHaveLength(0);
		await moveTo(Z16);
		expect(shrubRequests).toHaveLength(0);
		expect(scene.shown.get(SHRUBS_3D)).toBe(false);
		expect(trees.view.shrubs.drawn).toBe(false);
	});

	it('at z17 asks for the shrubs round the centre, hands the scene the 1,500 limit’s options, and credits them', async () => {
		await start();
		await moveTo(Z17);
		expect(shrubRequests).toHaveLength(1);
		expect(shrubRequests[0].url).toMatch(/^\/api\/trees\/shrubs\?bbox=[-\d.,]+&center=-116\.21,43\.62&limit=1500$/);
		shrubRequests[0].answer([shrub('a', Z17, 0), shrub('b', Z17, 1)]);
		await settle();
		const set = scene.sets.filter((x) => x.group === SHRUBS_3D).at(-1)!;
		expect(set.list.map((i) => i.id)).toEqual(['shrub:a', 'shrub:b']);
		expect(set.opts).toBe(SHRUBS_SCENE);
		expect(scene.shown.get(SHRUBS_3D)).toBe(true);
		expect(trees.view.shrubs).toMatchObject({ bush: 1, sage: 1, drawn: true, here: true });
		expect(map.attribution()).toContain(SHRUB_CREDIT);
		expect(map.attribution()).toContain('contains modified Copernicus Sentinel data 2025');
		// The same box is not asked for twice.
		await moveTo(Z17);
		expect(shrubRequests).toHaveLength(1);
	});

	it('hides them again when zoomed out below z17, and a late answer after leaving doesn’t land', async () => {
		await start();
		await moveTo(Z17);
		shrubRequests[0].answer([shrub('a', Z17)]);
		await settle();
		expect(scene.shown.get(SHRUBS_3D)).toBe(true);
		await moveTo({ ...Z17, zoom: 16.8 });
		expect(scene.shown.get(SHRUBS_3D)).toBe(false);
		await moveTo(Z15);
		expect(trees.view.shrubs.bush + trees.view.shrubs.sage).toBe(0);
		expect(scene.sets.filter((x) => x.group === SHRUBS_3D).at(-1)!.list).toEqual([]);
	});

	it('fetches at z16.7 but the scene group stays hidden, also after Trees is turned off', async () => {
		await start();
		await moveTo({ ...Z17, zoom: 16.7 });
		expect(shrubRequests).toHaveLength(1);
		shrubRequests[0].answer([shrub('a', Z17)]);
		await settle();
		expect(scene.shown.get(SHRUBS_3D)).toBe(false);
		trees.setVisible(false);
		expect(scene.shown.get(SHRUBS_3D)).toBe(false);
	});

	it('asks again for the same cell after an answer was aborted by hiding Trees', async () => {
		await start();
		await moveTo(Z17);
		expect(shrubRequests).toHaveLength(1);
		trees.setVisible(false);
		trees.setVisible(true);
		await settle();
		await moveTo(Z17);
		expect(shrubRequests).toHaveLength(2);
	});

	it('hands the scene all 1,500 the API gave (the scene keeps the nearest within 300 m)', async () => {
		await start();
		await moveTo(Z17);
		shrubRequests[0].answer(Array.from({ length: 1500 }, (_, i) => shrub(`s${i}`, Z17, i)), true);
		await settle();
		expect(scene.sets.filter((x) => x.group === SHRUBS_3D).at(-1)!.list).toHaveLength(1500);
		expect(trees.view.shrubs.truncated).toBe(true);
	});

	it('asks for nothing on a phone', async () => {
		await start(true);
		await moveTo(Z17);
		expect(shrubRequests).toHaveLength(0);
		expect(trees.view.shrubs.phone).toBe(true);
		expect(scene.shown.get(SHRUBS_3D)).toBe(false);
	});

	it('asks for nothing where no shrubs are built', async () => {
		await start();
		await moveTo({ zoom: 17, center: [-115.5, 43.62] });
		expect(shrubRequests).toHaveLength(0);
		expect(trees.view.shrubs.here).toBe(false);
	});
});
