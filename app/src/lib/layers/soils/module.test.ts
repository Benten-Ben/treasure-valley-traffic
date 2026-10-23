import { afterEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { createRequire } from 'node:module';
import type { AppCtx } from '#lib/app/context.js';
import type { DataMeta } from '#lib/contracts/meta.js';
import { slotFlags } from '#lib/map/order.js';
import { PRIORITY } from '../types.js';
import { SoilsModule } from './index.svelte.js';
import { ALL_IDS, ID, PICK_LAYERS, SOURCE } from './layers.js';
import { SHOVEL } from './icons.js';
import { PATTERN_KEYS, imageId } from './patterns.js';
import def from './def.js';

const META = { versions: { layers: { 'soils.units': 'v1' } }, layers: { 'soils.units': { credit: 'Soils: USDA NRCS, SSURGO' } } } as unknown as DataMeta;
const CARD = { mukey: '77', symbol: 'TeA', name: 'Testville silt loam', surveyed: true };

function fakeMap() {
	const layers = new Map<string, { id: string; layout?: Record<string, unknown>; paint?: Record<string, unknown>; filter?: unknown }>();
	const sources = new Map<string, { tiles: string[]; attribution?: string; minzoom?: number; maxzoom?: number }>();
	const images = new Map<string, { width: number; data: Uint8ClampedArray }>();
	const calls = { filter: [] as [string, unknown][], paint: [] as [string, string, unknown][] };
	return {
		addSource: (id: string, spec: { tiles: string[] }) => void sources.set(id, spec),
		getSource: (id: string) => sources.get(id),
		removeSource: (id: string) => sources.delete(id),
		addLayer: (l: { id: string }) => void layers.set(l.id, { ...l }),
		getLayer: (id: string) => layers.get(id),
		removeLayer: (id: string) => layers.delete(id),
		getLayersOrder: () => [...layers.keys()],
		getLayoutProperty: (id: string, k: string) => layers.get(id)?.layout?.[k],
		setLayoutProperty(id: string, k: string, v: unknown) {
			const l = layers.get(id)!;
			l.layout = { ...l.layout, [k]: v };
		},
		setPaintProperty(id: string, k: string, v: unknown) {
			const l = layers.get(id)!;
			l.paint = { ...l.paint, [k]: v };
			calls.paint.push([id, k, v]);
		},
		setFilter(id: string, f: unknown) {
			layers.get(id)!.filter = f;
			calls.filter.push([id, f]);
		},
		getFilter: (id: string) => layers.get(id)?.filter,
		hasImage: (id: string) => images.has(id),
		addImage: (id: string, img: { width: number; data: Uint8ClampedArray }) => void images.set(id, img),
		removeImage: (id: string) => images.delete(id),
		layers,
		sources,
		images,
		calls
	};
}

const json = (body: unknown, status = 200) => ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

describe('the Soils module', () => {
	let map: ReturnType<typeof fakeMap>;
	let mod: SoilsModule;
	let fetches: string[];

	const mount = async (meta: DataMeta = META) => {
		fetches = [];
		vi.stubGlobal('location', { origin: 'http://x' });
		vi.stubGlobal(
			'fetch',
			vi.fn(async (url: string) => {
				fetches.push(url);
				return url.endsWith('/404') ? json({ message: 'No such map unit' }, 404) : json(CARD);
			})
		);
		map = fakeMap();
		mod = new SoilsModule();
		await mod.mount({ styleReady: Promise.resolve(map), meta } as unknown as AppCtx);
	};

	afterEach(() => {
		mod?.destroy();
		vi.unstubAllGlobals();
	});

	it('is a Landscape tray layer, off by default, offered once the soils build has a version, and Auto goes Clay under it', () => {
		expect(def).toMatchObject({ id: 'soils', title: 'Soils', group: 'landscape' });
		expect(def.available(META)).toBe(true);
		expect(def.available(null)).toBe('Soils are not built yet');
		expect(def.available({ versions: { layers: {} } } as unknown as DataMeta)).toBe('Soils are not built yet');
		expect(def.keepsValley).toBeUndefined();
		expect(def.offUnder).toBeUndefined();
	});

	it("uses Phosphor's Shovel icon, duotone, exactly as phosphor-svelte ships it", () => {
		const dir = join(dirname(createRequire(import.meta.url).resolve('phosphor-svelte/package.json')), 'lib');
		const src = readFileSync(join(dir, `${SHOVEL.name}Icon.svelte`), 'utf8');
		const branch = /weight === "duotone"\}\s*([\s\S]*?)\{:else/.exec(src)?.[1] ?? '';
		const paths = [...branch.matchAll(/<path d="([^"]+)"([^>]*)\/>/g)];
		expect(SHOVEL.tone).toBe(paths.find((p) => p[2].includes('opacity="0.2"'))?.[1]);
		expect(SHOVEL.line).toBe(paths.find((p) => !p[2].includes('opacity'))?.[1]);
	});

	it("mounts: one source with the build's version and credit, an image for every pattern, every layer", async () => {
		await mount();
		expect(mod.status).toBe('ready');
		expect(map.sources.get(SOURCE)!.tiles).toEqual(['http://x/api/soils/tiles/units/{z}/{x}/{y}?v=v1']);
		expect(map.sources.get(SOURCE)!.attribution).toBe('Soils: USDA NRCS, SSURGO');
		expect([map.sources.get(SOURCE)!.minzoom, map.sources.get(SOURCE)!.maxzoom]).toEqual([8, 14]);
		expect([...map.images.keys()].sort()).toEqual(PATTERN_KEYS.map(imageId).sort());
		for (const img of map.images.values()) expect(img.data.some((v, i) => i % 4 === 3 && v > 0)).toBe(true);
		expect([...map.layers.keys()].sort()).toEqual([...ALL_IDS].sort());
		expect(mod.credit).toBe('Soils: USDA NRCS, SSURGO');
		expect(mod.updatedAt).not.toBeNull();
		expect(mod.by).toBe('restr');
	});

	it('shows and hides every layer with setVisible, and clears the selected outline when hidden', async () => {
		await mount();
		for (const id of ALL_IDS) expect(map.layers.get(id)!.layout!.visibility, id).toBe('none');
		mod.setVisible(true);
		for (const id of ALL_IDS) expect(map.layers.get(id)!.layout!.visibility, id).toBe('visible');
		mod.setVisible(false);
		for (const id of ALL_IDS) expect(map.layers.get(id)!.layout!.visibility, id).toBe('none');
	});

	it('shows another property in the wash: the fill colours and the patterns change, visibility never does', async () => {
		await mount();
		mod.setVisible(true);
		mod.setBy('drain');
		expect(mod.by).toBe('drain');
		for (const id of [ID.fill, ID.copy]) expect(JSON.stringify(map.layers.get(id)!.paint!['fill-color']), id).toContain('"drain"');
		expect(map.layers.get(ID.pattern)!.filter).toEqual(['==', ['literal', 0], 1]);
		for (const id of ALL_IDS) expect(map.layers.get(id)!.layout!.visibility, id).toBe('visible');
		mod.setBy('farm');
		expect(JSON.stringify(map.layers.get(ID.pattern)!.filter)).toContain('drained');
		// A property that isn't one, or the one shown already, changes nothing.
		const n = map.calls.paint.length;
		mod.setBy('farm');
		mod.setBy('nope' as never);
		expect(map.calls.paint.length).toBe(n);
		expect(mod.by).toBe('farm');
	});

	it('adds its layers with the property it already shows (a module mounted after a change)', async () => {
		fetches = [];
		map = fakeMap();
		mod = new SoilsModule();
		mod.by = 'hsg';
		vi.stubGlobal('location', { origin: 'http://x' });
		await mod.mount({ styleReady: Promise.resolve(map), meta: META } as unknown as AppCtx);
		expect(JSON.stringify(map.layers.get(ID.fill)!.paint!['fill-color'])).toContain('"hsg"');
		expect(map.layers.get(ID.pattern)!.filter).toEqual(['==', ['get', 'dual'], true]);
	});

	it('selects a map unit a click picked, below every other layer, and nothing for a feature without a key', async () => {
		await mount();
		const [layer] = mod.interactive;
		expect(layer.layerIds).toEqual(PICK_LAYERS);
		expect(layer.priority).toBe(PRIORITY.soil);
		const sel = layer.pick({ properties: { mukey: '77', symbol: 'TeA', restr: 2 } } as never)!;
		expect(sel).toMatchObject({ kind: 'soil', id: '77', layer: 'soils', title: 'Soil TeA' });
		expect(layer.pick({ properties: {} } as never)).toBeNull();
	});

	it('outlines the selected map unit while it is selected, and not after another layer\'s selection', async () => {
		await mount();
		const sel = mod.interactive[0].pick({ properties: { mukey: '77', symbol: 'TeA' } } as never)!;
		mod.selected(sel);
		expect(JSON.stringify(map.layers.get(ID.selected)!.filter)).toContain('77');
		mod.selected(null);
		expect(JSON.stringify(map.layers.get(ID.selected)!.filter)).not.toContain('77');
		mod.selected(sel);
		mod.selected({ kind: 'tree', id: 't', layer: 'trees', title: 'Tree' });
		expect(JSON.stringify(map.layers.get(ID.selected)!.filter)).not.toContain('77');
	});

	it('keeps each card for a while: one request per map unit, and a 404 is null', async () => {
		await mount();
		await mod.detail('5');
		await mod.detail('5');
		expect(fetches.filter((u) => u === '/api/soils/mapunit/5')).toHaveLength(1);
		await expect(mod.detail('404')).resolves.toBeNull();
	});

	it('declares its slot flags to the manager when its layers are added', async () => {
		await mount();
		const flags = slotFlags(map);
		expect(flags.get(ID.fill)).toMatchObject({ owner: 'soils', areaFill: true });
		expect(flags.get(ID.copy)).toMatchObject({ owner: 'soils', areaFill: true, aerial: 'only' });
		expect(flags.get(ID.pattern)).toMatchObject({ owner: 'soils', areaFill: true });
		expect(flags.has(ID.pick)).toBe(false); // no flags: it is never gated, so the card opens under any area fill
		expect(flags.has(ID.outline)).toBe(false);
	});
});
