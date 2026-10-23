import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AppCtx } from '#lib/app/context.js';
import { PAVED_LAYER } from '#lib/base/trails/paved.js';
import type { AgencyState, TrailStatus } from '#lib/server/trails/status.js';

vi.mock('./images.js', () => ({
	statusImages: () => Object.fromEntries(['trails-caution', 'trails-muddy', 'trails-closed', 'trails-detour'].map((id) => [id, { data: { width: 1, height: 1 }, options: { pixelRatio: 2 } }]))
}));
const { POLL_MS, TrailsModule, agoText } = await import('./index.svelte.js');
const { L, SRC, TRAIL_LAYER_IDS, markLayer } = await import('./trails.js');

/**
 * The Trails module against a fake map and fetch: its three tile sources and style layers, the status applied as
 * feature-state (and taken away when the status drops it), a status that doesn't load, the poll while the layer is
 * on, the outline of the selected trail, and the clean-up. Made-up ids and states.
 */

interface FakeLayer {
	id: string;
	layout?: Record<string, unknown>;
	filter?: unknown;
	type?: string;
}

function fakeMap() {
	const handlers = new Map<string, Set<(e: object) => void>>();
	const layers = new Map<string, FakeLayer>();
	const sources = new Map<string, Record<string, unknown>>();
	const images = new Set<string>();
	const states = new Map<string, Record<string, unknown>>();
	const key = (f: { source: string; sourceLayer?: string; id: number }) => `${f.source}/${f.sourceLayer}/${f.id}`;
	const map = {
		addSource: (id: string, spec: Record<string, unknown>) => void sources.set(id, spec),
		getSource: (id: string) => sources.get(id),
		removeSource: (id: string) => sources.delete(id),
		addLayer: (l: FakeLayer) => void layers.set(l.id, { ...l }),
		getLayer: (id: string) => layers.get(id),
		removeLayer: (id: string) => layers.delete(id),
		getLayersOrder: () => [...layers.keys()],
		hasImage: (id: string) => images.has(id),
		addImage: (id: string) => void images.add(id),
		removeImage: (id: string) => images.delete(id),
		setLayoutProperty(id: string, k: string, v: unknown) {
			const l = layers.get(id)!;
			l.layout = { ...l.layout, [k]: v };
		},
		setFilter(id: string, f: unknown) {
			layers.get(id)!.filter = f;
		},
		setFeatureState(f: { source: string; sourceLayer?: string; id: number }, state: Record<string, unknown>) {
			states.set(key(f), { ...states.get(key(f)), ...state });
		},
		removeFeatureState: (f: { source: string; sourceLayer?: string; id: number }) => void states.delete(key(f)),
		on(type: string, f: (e: object) => void) {
			if (!handlers.has(type)) handlers.set(type, new Set());
			handlers.get(type)!.add(f);
		},
		off: (type: string, f: (e: object) => void) => void handlers.get(type)?.delete(f),
		emit: (type: string, e: object) => handlers.get(type)?.forEach((f) => f(e)),
		queryRenderedFeatures: () => [],
		layers,
		sources,
		images,
		states,
		handlers
	};
	return map;
}

const agency = (o: Partial<AgencyState>): AgencyState => ({
	source: 'r2r_trails',
	id: 'x',
	kind: 'trail',
	name: 'Example Ridge',
	system: 'Ridge to Rivers',
	state: 'dry',
	severity: 'open',
	label: 'Dry',
	set_at: null,
	since: null,
	ways: [],
	partial: [],
	line_id: 1,
	drawn: false,
	gap_m: 0,
	along_m: 0,
	covered: null,
	...o
});

const status = (o: Partial<TrailStatus> = {}): TrailStatus => ({
	agencies: [agency({ line_id: 1, ways: [9500000001] }), agency({ line_id: 2, id: 'y', name: 'Closed Gulch', state: 'closed', severity: 'closed', label: 'CLOSED', drawn: true, gap_m: 300 })],
	ways: { '9500000001': 'open' },
	hidden: [9500000009],
	counts: { dry: 1, closed: 1 },
	polled: { r2r_trails: '2026-10-11T18:30:00.000Z', boise_greenbelt_closures: null },
	credit: 'City of Boise Parks & Recreation',
	license: 'none stated',
	republish: 'aggregates',
	...o
});

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as unknown as Response;
const settle = () => vi.advanceTimersByTimeAsync(0);

describe('the Trails module', () => {
	let map: ReturnType<typeof fakeMap>;
	let ctx: AppCtx;
	let answer: () => Promise<Response>;
	let calls: string[];

	const make = () => new TrailsModule();

	beforeEach(() => {
		vi.useFakeTimers();
		vi.stubGlobal('location', { origin: 'http://tv.test' });
		map = fakeMap();
		calls = [];
		answer = () => Promise.resolve(ok(status()));
		vi.stubGlobal('fetch', (url: string) => {
			calls.push(url);
			return answer();
		});
		ctx = {
			styleReady: Promise.resolve(map),
			meta: { versions: { layers: { 'trails.paths': 'p1', 'trails.routes': 'r1', 'trails.agency': 'a1' } }, layers: { 'trails.agency': { credit: 'City of Boise (test credit)' } } }
		} as unknown as AppCtx;
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		vi.useRealTimers();
	});

	it('adds the three tile sources with their versions, and every style layer hidden', async () => {
		const t = make();
		await t.mount(ctx);
		expect([...map.sources.keys()].sort()).toEqual([SRC.agency, SRC.paths, SRC.routes].sort());
		const tiles = (id: string) => (map.sources.get(id) as { tiles: string[]; minzoom: number; maxzoom: number }).tiles[0];
		expect(tiles(SRC.paths)).toBe('http://tv.test/api/trails/tiles/paths/{z}/{x}/{y}?v=p1');
		expect(tiles(SRC.routes)).toBe('http://tv.test/api/trails/tiles/routes/{z}/{x}/{y}?v=r1');
		expect(tiles(SRC.agency)).toBe('http://tv.test/api/trails/tiles/agency/{z}/{x}/{y}?v=a1');
		expect(map.sources.get(SRC.paths)).toMatchObject({ minzoom: 10, maxzoom: 16, attribution: '© OpenStreetMap contributors' });
		// The City's credit comes from its build; the others fall back to the data's own.
		expect(map.sources.get(SRC.agency)).toMatchObject({ attribution: 'City of Boise (test credit)' });
		expect([...map.layers.keys()].sort()).toEqual([...TRAIL_LAYER_IDS].sort());
		for (const l of map.layers.values()) expect(l.layout?.visibility).toBe('none');
		expect(map.images.size).toBe(4);
		expect(t.status).toBe('ready');
		t.destroy();
	});

	it('shows and hides every layer with the layer', async () => {
		const t = make();
		await t.mount(ctx);
		t.setVisible(true);
		for (const l of map.layers.values()) expect(l.layout?.visibility).toBe('visible');
		t.setVisible(false);
		for (const l of map.layers.values()) expect(l.layout?.visibility).toBe('none');
		t.destroy();
	});

	it('applies the status as feature-state: the ways’ states, the lines’ by id on two source-layers, informal ways hidden', async () => {
		const t = make();
		await t.mount(ctx);
		const at = (source: string, layer: string, id: number) => map.states.get(`${source}/${layer}/${id}`);
		expect(at(SRC.paths, 'paths', 9500000001)).toEqual({ sev: 'open' });
		expect(at(SRC.agency, 'agency', 2)).toEqual({ sev: 'closed' });
		expect(at(SRC.agency, 'marks', 2)).toEqual({ sev: 'closed' });
		expect(at(SRC.paths, 'paths', 9500000009)).toEqual({ hide: true });
		expect(t.trail?.counts).toEqual({ dry: 1, closed: 1 });
		expect(t.summary()).toBe('2 Ridge to Rivers trails');
		t.destroy();
	});

	it('takes the status from the prefetched answer the first time (one request), not a second', async () => {
		const { prefetch } = await import('../prefetch.js');
		void prefetch('/api/trails/status');
		const t = make();
		await t.mount(ctx);
		expect(calls).toEqual(['/api/trails/status']);
		t.destroy();
	});

	it('asks again every few minutes while the layer is on, and takes away what the new status drops', async () => {
		const t = make();
		await t.mount(ctx);
		t.setVisible(true);
		calls.length = 0;
		answer = () => Promise.resolve(ok(status({ ways: { '9500000001': 'caution' }, hidden: [], agencies: [agency({ line_id: 1 })] })));
		await vi.advanceTimersByTimeAsync(POLL_MS);
		expect(calls).toEqual(['/api/trails/status']);
		const at = (source: string, layer: string, id: number) => map.states.get(`${source}/${layer}/${id}`);
		expect(at(SRC.paths, 'paths', 9500000001)).toEqual({ sev: 'caution' });
		expect(at(SRC.paths, 'paths', 9500000009)).toBeUndefined();
		expect(at(SRC.agency, 'agency', 2)).toBeUndefined();
		// Off: no more asking.
		t.setVisible(false);
		calls.length = 0;
		await vi.advanceTimersByTimeAsync(POLL_MS * 3);
		expect(calls).toEqual([]);
		t.destroy();
	});

	it('a hidden way that stops being hidden loses the hiding but keeps its state', async () => {
		const t = make();
		await t.mount(ctx);
		t.setVisible(true);
		answer = () => Promise.resolve(ok(status({ ways: { '9500000009': 'caution' }, hidden: [], agencies: [] })));
		await vi.advanceTimersByTimeAsync(POLL_MS);
		expect(map.states.get(`${SRC.paths}/paths/9500000009`)).toEqual({ sev: 'caution' });
		t.destroy();
	});

	it('draws plain lines and shows ▲ when the status doesn’t load; the next poll that does clears it', async () => {
		answer = () => Promise.resolve({ ok: false, status: 503, json: async () => ({ message: 'down' }) } as unknown as Response);
		const t = make();
		await t.mount(ctx);
		expect(t.status).toBe('stale');
		expect(t.error).toMatch(/Trail status unavailable: down/);
		expect(map.layers.size).toBe(TRAIL_LAYER_IDS.length);
		expect(map.states.size).toBe(0);
		t.setVisible(true);
		answer = () => Promise.resolve(ok(status()));
		await vi.advanceTimersByTimeAsync(POLL_MS);
		expect(t.status).toBe('ready');
		expect(t.error).toBeNull();
		expect(map.states.size).toBeGreaterThan(0);
		t.destroy();
	});

	it('goes stale, with the reason, when a trail tile fails to load', async () => {
		const t = make();
		await t.mount(ctx);
		map.emit('error', { sourceId: SRC.paths, error: { message: 'HTTP 500' } });
		expect(t.status).toBe('stale');
		expect(t.error).toContain('HTTP 500');
		// Another source’s tiles are not ours.
		const u = make();
		await u.mount({ ...ctx, styleReady: Promise.resolve(fakeMap()) } as unknown as AppCtx);
		u.destroy();
		t.destroy();
	});

	it('outlines the selected way and the selected line, and clears them', async () => {
		const t = make();
		await t.mount(ctx);
		t.selected({ kind: 'trail', id: 'way:9500000001', layer: 'trails', title: 'x' });
		for (const id of [L.selectedHalo, L.selected]) expect(map.layers.get(id)!.filter).toEqual(['==', ['id'], 9500000001]);
		for (const id of [L.selectedHaloAgency, L.selectedAgency]) expect(map.layers.get(id)!.filter).toEqual(['==', ['id'], -1]);
		t.selected({ kind: 'trail', id: 'line:2', layer: 'trails', title: 'x' });
		expect(map.layers.get(L.selected)!.filter).toEqual(['==', ['id'], -1]);
		expect(map.layers.get(L.selectedAgency)!.filter).toEqual(['==', ['id'], 2]);
		t.selected(null);
		expect(map.layers.get(L.selectedAgency)!.filter).toEqual(['==', ['id'], -1]);
		t.destroy();
	});

	it('makes its hit lines clickable, and the paved base layers too (they open a card only while Trails is on)', async () => {
		const t = make();
		await t.mount(ctx);
		const ids = t.interactive.flatMap((i) => i.layerIds);
		expect(ids).toEqual(expect.arrayContaining([L.hitWays, L.hitAgency, PAVED_LAYER.treads, PAVED_LAYER.areas]));
		// Off, they select nothing (the picker keeps a mounted module's layers; the paved ones are base layers, always drawn).
		const tread = { id: 9101, properties: { kind: 'cycleway', material: 'asphalt', w: 3 } } as never;
		expect(t.interactive[2].pick(tread)).toBeNull();
		expect(t.interactive[3].pick({ id: 9201, properties: { kind: 'pedestrian' } } as never)).toBeNull();
		expect(t.interactive[0].pick({ id: 1, properties: { kind: 'path' } } as never)).toBeNull();
		t.setVisible(true);
		expect(t.interactive[2].pick(tread)).toMatchObject({ kind: 'trail', id: 'way:9101' });
		expect(t.interactive[3].pick({ id: 9201, properties: { kind: 'pedestrian' } } as never)).toMatchObject({ kind: 'paving', id: 'area:9201' });
		const way = t.interactive[0].pick({ id: 9500000001, properties: { kind: 'path', name: 'Example Ridge Trail' } } as never);
		expect(way).toMatchObject({ id: 'way:9500000001', title: 'Example Ridge Trail', fact: expect.any(String) });
		const line = t.interactive[1].pick({ id: 2, properties: { kind: 'trail', name: 'Closed Gulch' } } as never);
		expect(line).toMatchObject({ id: 'line:2', fact: 'CLOSED' });
		t.destroy();
	});

	it('says a closed-trails chip while it is on, and how old the poll is', async () => {
		vi.setSystemTime(new Date('2026-10-11T18:42:00Z'));
		const t = make();
		await t.mount(ctx);
		expect(t.chips()).toEqual([]);
		t.setVisible(true);
		expect(t.chips()).toEqual([expect.objectContaining({ id: 'trails-closed', text: '1 trail closed' })]);
		expect(t.age()).toBe('Ridge to Rivers polled 12 min ago');
		expect(agoText(Date.parse('2026-10-11T15:00:00Z'), Date.parse('2026-10-11T18:42:00Z'))).toBe('4 h ago');
		expect(agoText(1000, 1000)).toBe('just now');
		t.destroy();
	});

	it('caches a card’s details and asks for the right URL', async () => {
		const t = make();
		await t.mount(ctx);
		calls.length = 0;
		answer = () => Promise.resolve(ok({ id: 9500000001 }));
		expect(await t.detail('way', 9500000001)).toEqual({ id: 9500000001 });
		await t.detail('way', 9500000001);
		await t.detail('line', 2);
		expect(calls).toEqual(['/api/trails/way/9500000001', '/api/trails/line/2']);
		answer = () => Promise.resolve({ ok: false, status: 404, json: async () => ({}) } as unknown as Response);
		expect(await t.detail('way', 5)).toBeNull();
		t.destroy();
	});

	it('removes everything it added when it is destroyed', async () => {
		const t = make();
		await t.mount(ctx);
		t.destroy();
		expect(map.layers.size).toBe(0);
		expect(map.sources.size).toBe(0);
		expect(map.images.size).toBe(0);
		expect(markLayer('closed')).toBe('trails-mark-closed');
	});
});
