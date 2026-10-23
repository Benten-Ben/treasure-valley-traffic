import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AppCtx } from '#lib/app/context.js';
import { LanesModule } from './index.svelte.js';
import { CardError } from './lanes.js';
import { ARROW_LAYER, CONFLICT_LAYER } from './layers.js';
import def from './def.js';

/**
 * The Lanes module against a fake map, manifest and fetch: its own layers only when the landscape file holds the road
 * lines and arrows, shown only while on; clicks open cards only while on, keyed by the build the manifest gives; the
 * card API is asked with that build, and a map behind the data is told so.
 */

function fakeMap(sources: string[] = ['landscape']) {
	const layers = new Map<string, { id: string; layout?: Record<string, unknown> }>();
	const have = new Set(sources);
	const order: string[] = ['anchor:points', 'anchor:labels'];
	return {
		getSource: (id: string) => (have.has(id) ? {} : undefined),
		addSource: (id: string) => void have.add(id),
		removeSource: (id: string) => void have.delete(id),
		addLayer: (l: { id: string }, before?: string) => {
			layers.set(l.id, { ...l });
			const i = before ? order.indexOf(before) : -1;
			order.splice(i < 0 ? order.length : i, 0, l.id);
		},
		getLayer: (id: string) => layers.get(id) ?? (id.startsWith('anchor:') ? {} : undefined),
		removeLayer: (id: string) => layers.delete(id),
		getLayersOrder: () => order,
		hasImage: () => false,
		addImage: () => {},
		removeImage: () => {},
		getLayoutProperty: (id: string, k: string) => layers.get(id)?.layout?.[k],
		setLayoutProperty(id: string, k: string, v: unknown) {
			layers.get(id)!.layout = { ...layers.get(id)!.layout, [k]: v };
		},
		layers,
		order
	};
}

const info = (build: string) => ({ plugin: 'roads', layer: 'x', build, geometry: 'x', features: 1, fields: {}, minzoom: 14, maxzoom: 16, licence: 'x', republish: 'internal', credit: [] });

function manifest(layers: string[], build = '20261012T040000Z') {
	return { landscape: { status: 'baked', layers: Object.fromEntries(layers.map((l) => [l, info(build)])), empty: [] } };
}

async function start(o: { layers?: string[]; sources?: string[]; build?: string } = {}) {
	const map = fakeMap(o.sources);
	const ctx = { styleReady: Promise.resolve(map), manifest: manifest(o.layers ?? ['roads.lines', 'roads.arrows', 'roads.surfaces'], o.build) } as unknown as AppCtx;
	const lanes = new LanesModule();
	await lanes.mount(ctx);
	return { lanes, map };
}

const f = (sourceLayer: string, properties: Record<string, unknown>) => ({ sourceLayer, properties }) as never;

afterEach(() => vi.unstubAllGlobals());

describe('the Lanes module (plan P9)', () => {
	it('is the main-bar layer on key 8 that keeps Valley, with no tray group', () => {
		expect(def).toMatchObject({ id: 'lanes', key: '8', keepsValley: true });
		expect(def.group).toBeUndefined();
		expect(def.available({ database: 'ok', tiles: { landscape: null } } as never)).toMatch(/not built/);
		expect(def.available({ database: 'ok', tiles: { landscape: '2026-10-12' } } as never)).toBe(true);
		expect(def.available(null)).toBe(true);
	});

	it('adds its ▲ and arrow layers when the landscape file holds the road lines and arrows, hidden until it is on', async () => {
		const { lanes, map } = await start();
		expect(lanes.status).toBe('ready');
		expect([...map.layers.keys()]).toEqual([CONFLICT_LAYER, ARROW_LAYER]);
		// The ▲ is in the points slot, the arrows in labels.
		expect(map.order.indexOf(CONFLICT_LAYER)).toBeLessThan(map.order.indexOf('anchor:points'));
		expect(map.order.indexOf(ARROW_LAYER)).toBeGreaterThan(map.order.indexOf('anchor:points'));
		expect(map.order.indexOf(ARROW_LAYER)).toBeLessThan(map.order.indexOf('anchor:labels'));
		for (const id of [CONFLICT_LAYER, ARROW_LAYER]) expect(map.layers.get(id)?.layout?.visibility).toBe('none');
		lanes.setVisible(true);
		for (const id of [CONFLICT_LAYER, ARROW_LAYER]) expect(map.layers.get(id)?.layout?.visibility).toBe('visible');
		lanes.setVisible(false);
		for (const id of [CONFLICT_LAYER, ARROW_LAYER]) expect(map.layers.get(id)?.layout?.visibility).toBe('none');
		lanes.destroy();
		expect(map.layers.size).toBe(0);
	});

	it('adds nothing when the roads are not baked, and says so', async () => {
		const { lanes, map } = await start({ layers: ['water.reaches'], sources: [] });
		expect(map.layers.size).toBe(0);
		expect(lanes.roads).toBe(false);
		expect(lanes.summary()).toBe('roads not built yet');
		lanes.setVisible(true);
		const noLines = await start({ layers: ['roads.surfaces'] });
		expect(noLines.map.layers.size).toBe(0);
		expect(noLines.lanes.roads).toBe(true);
		const lines = await start({ layers: ['roads.lines'] });
		expect([...lines.map.layers.keys()]).toEqual([CONFLICT_LAYER]);
	});

	it('picks roads at lane priority and paving at paving priority, only while on, with the manifest’s build', async () => {
		const { lanes } = await start({ build: '20261012T040000Z' });
		const [road, paving] = lanes.interactive;
		expect(road.priority).toBe(50);
		expect(paving.priority).toBe(22);
		const surface = f('roads.surfaces', { id: 2003, kind: 'carriageway', tier: 'estimated' });
		expect(road.pick(surface)).toBeNull();
		expect(paving.pick(f('roads.paving_lots', { id: 84 }))).toBeNull();
		lanes.setVisible(true);
		expect(road.pick(surface)).toMatchObject({ id: 'surface-2003', data: { type: 'piece', ref: 'surface-2003', build: '20261012T040000Z' } });
		expect(paving.pick(f('roads.paving_lots', { id: 84 }))).toMatchObject({ id: 'lot:w42' });
		lanes.setVisible(false);
		expect(road.pick(surface)).toBeNull();
	});

	it('picks nothing for a source-layer the manifest does not list: it cannot say which build the tile is from', async () => {
		const { lanes } = await start({ layers: ['roads.lines'] });
		lanes.setVisible(true);
		expect(lanes.interactive[0].pick(f('roads.surfaces', { id: 1, kind: 'carriageway' }))).toBeNull();
		expect(lanes.interactive[0].pick(f('roads.lines', { id: 1, class: 'secondary' }))).not.toBeNull();
	});

	it('asks the card API with the build, keeps the answer, and a map behind the data gets the server’s words (409)', async () => {
		const { lanes } = await start();
		const urls: string[] = [];
		vi.stubGlobal('fetch', (url: string) => {
			urls.push(url);
			if (url.includes('line-9')) return Promise.resolve({ ok: false, status: 409, json: async () => ({ message: 'The map is a build behind the road data.' }) });
			if (url.includes('line-8')) return Promise.resolve({ ok: false, status: 404, json: async () => ({ message: 'No such road piece' }) });
			return Promise.resolve({ ok: true, status: 200, json: async () => ({ kind: 'piece', name: 'X' }) });
		});
		const d = (ref: string) => ({ type: 'piece' as const, ref, build: '20261012T040000Z' });
		expect(await lanes.piece(d('surface-2003'))).toMatchObject({ name: 'X' });
		await lanes.piece(d('surface-2003'));
		expect(urls).toEqual(['/api/roads/piece/surface-2003?build=20261012T040000Z']);
		await expect(lanes.piece(d('line-9'))).rejects.toMatchObject({ status: 409, message: 'The map is a build behind the road data.' });
		await expect(lanes.piece(d('line-8'))).rejects.toBeInstanceOf(CardError);
		// A failed one isn't kept: asking again asks again.
		await lanes.piece(d('line-9')).catch(() => {});
		expect(urls.filter((u) => u.includes('line-9'))).toHaveLength(2);
		await lanes.paving({ type: 'paving', kind: 'lot', id: 'w42' });
		expect(urls.at(-1)).toBe('/api/roads/paving/lot/w42');
	});
});
