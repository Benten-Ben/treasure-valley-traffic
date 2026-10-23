import { afterEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { createRequire } from 'node:module';
import type { AppCtx } from '#lib/app/context.js';
import type { DataMeta } from '#lib/contracts/meta.js';
import { slotFlags } from '#lib/map/order.js';
import { CropsModule, FIELD_PARAM } from './index.svelte.js';
import { ALL_IDS, ID, SELECTED_NONE, SOURCE_FIELDS, SOURCE_YEAR } from './layers.js';
import { GRAINS } from './icons.js';
import { PATTERN_KEYS, imageId } from './patterns.js';
import def from './def.js';

const META = { versions: { layers: { 'farm.crop_fields': 'v1' } }, layers: { 'farm.crop_fields': { credit: 'USDA NASS CSB' } } } as unknown as DataMeta;
const YEAR = { built: true, year: 2025, label: "2025 (USDA's newest)", first_year: 2018, edition: 'csb-2018-2025' };
const CARD = {
	id: 77,
	acres: 24,
	county: 'Canyon',
	years: [{ year: 2025, code: 36, name: 'Alfalfa', group: 'hay' }],
	agree: {},
	july: null,
	growth: 'farmed',
	growth_detail: null,
	plat: null,
	valid_to: null,
	centre: [-116.6, 43.6],
	bbox: [-116.61, 43.59, -116.59, 43.61],
	credit: null,
	license: null
};

function fakeMap() {
	const layers = new Map<string, { id: string; layout?: Record<string, unknown>; filter?: unknown; minzoom?: number; maxzoom?: number }>();
	const sources = new Map<string, { spec: { tiles: string[]; attribution?: string }; setTiles(t: string[]): void }>();
	const images = new Map<string, { width: number; data: Uint8ClampedArray }>();
	const calls = { filter: [] as [string, unknown][], paint: [] as [string, string][], layout: [] as [string, string][], zoom: [] as [string, number, number][], flyTo: [] as unknown[] };
	const map = {
		addSource(id: string, spec: { tiles: string[]; attribution?: string }) {
			sources.set(id, { spec, setTiles(t) { this.spec = { ...this.spec, tiles: t }; } });
		},
		getSource: (id: string) => sources.get(id),
		removeSource: (id: string) => sources.delete(id),
		addLayer: (l: { id: string; layout?: Record<string, unknown>; filter?: unknown; minzoom?: number; maxzoom?: number }) => void layers.set(l.id, { ...l }),
		getLayer: (id: string) => layers.get(id),
		removeLayer: (id: string) => layers.delete(id),
		getLayersOrder: () => [...layers.keys()],
		getLayoutProperty: (id: string, k: string) => layers.get(id)?.layout?.[k],
		setLayoutProperty(id: string, k: string, v: unknown) {
			const l = layers.get(id)!;
			l.layout = { ...l.layout, [k]: v };
			if (k === 'text-field') calls.layout.push([id, k]);
		},
		setPaintProperty: (id: string, k: string) => void calls.paint.push([id, k]),
		setFilter(id: string, f: unknown) {
			layers.get(id)!.filter = f;
			calls.filter.push([id, f]);
		},
		getFilter: (id: string) => layers.get(id)?.filter,
		setLayerZoomRange(id: string, min: number, max: number) {
			const l = layers.get(id)!;
			l.minzoom = min;
			l.maxzoom = max;
			calls.zoom.push([id, min, max]);
		},
		hasImage: (id: string) => images.has(id),
		addImage: (id: string, img: { width: number; data: Uint8ClampedArray }) => void images.set(id, img),
		removeImage: (id: string) => images.delete(id),
		getZoom: () => 10,
		flyTo: (o: unknown) => void calls.flyTo.push(o),
		layers,
		sources,
		images,
		calls
	};
	return map;
}

function fakeCtx(map: ReturnType<typeof fakeMap>, hash: Record<string, string | null> = {}) {
	const params = { ...hash };
	const selected: unknown[] = [];
	const ctx = {
		styleReady: Promise.resolve(map),
		meta: META,
		view: {
			getParam: (k: string) => params[k] ?? null,
			setParam: (k: string, v: string | null) => void (params[k] = v)
		},
		selection: { select: (s: unknown) => void selected.push(s), current: null }
	} as unknown as AppCtx;
	return { ctx, params, selected };
}

const json = (body: unknown, status = 200) => ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

describe('the Crop fields module', () => {
	let map: ReturnType<typeof fakeMap>;
	let mod: CropsModule;
	let env: ReturnType<typeof fakeCtx>;
	let fetches: string[];

	const mount = async (opts: { year?: unknown; hash?: Record<string, string | null>; card?: unknown } = {}) => {
		fetches = [];
		vi.stubGlobal('location', { origin: 'http://x' });
		vi.stubGlobal(
			'fetch',
			vi.fn(async (url: string) => {
				fetches.push(url);
				if (url === '/api/farm/year') return json(opts.year ?? YEAR);
				if (url.startsWith('/api/farm/fields/')) return opts.card === null ? json({ message: 'No such field' }, 404) : json(opts.card ?? CARD);
				return json({}, 404);
			})
		);
		map = fakeMap();
		env = fakeCtx(map, opts.hash);
		mod = new CropsModule();
		await mod.mount(env.ctx);
	};

	afterEach(() => {
		mod?.destroy();
		vi.unstubAllGlobals();
	});

	it('is a Landscape tray layer, offered once the farm build has a version, and off under Transit', () => {
		expect(def).toMatchObject({ id: 'crops', title: 'Crop fields', group: 'landscape', offUnder: ['transit'] });
		expect(def.available(META)).toBe(true);
		expect(def.available(null)).toBe('Crop fields are not built yet');
		expect(def.available({ versions: { layers: {} } } as unknown as DataMeta)).toBe('Crop fields are not built yet');
		expect(def.keepsValley).toBeUndefined(); // Auto goes Clay while it is on
	});

	it('uses Phosphor\'s Grains icon, duotone, exactly as phosphor-svelte ships it', () => {
		const dir = join(dirname(createRequire(import.meta.url).resolve('phosphor-svelte/package.json')), 'lib');
		const src = readFileSync(join(dir, `${GRAINS.name}Icon.svelte`), 'utf8');
		const branch = /weight === "duotone"\}\s*([\s\S]*?)\{:else/.exec(src)?.[1] ?? '';
		const [tone, line] = [...branch.matchAll(/<path d="([^"]+)"/g)].map((m) => m[1]);
		expect(GRAINS.tone).toBe(tone);
		expect(GRAINS.line).toBe(line);
	});

	it('mounts: two sources with the build\'s version and credit, a pattern image for every group and state, every layer', async () => {
		await mount();
		expect(mod.status).toBe('ready');
		expect(map.sources.get(SOURCE_FIELDS)!.spec.tiles).toEqual(['http://x/api/farm/tiles/crop_fields/{z}/{x}/{y}?v=v1']);
		expect(map.sources.get(SOURCE_FIELDS)!.spec.attribution).toBe('USDA NASS CSB');
		expect(map.sources.get(SOURCE_YEAR)!.spec.tiles[0]).toBe('http://x/api/farm/tiles/crop_year_2018/{z}/{x}/{y}?v=v1');
		expect([...map.images.keys()].sort()).toEqual(PATTERN_KEYS.map(imageId).sort());
		for (const img of map.images.values()) expect(img.data.some((v, i) => i % 4 === 3 && v > 0)).toBe(true);
		expect([...map.layers.keys()].sort()).toEqual([...ALL_IDS].sort());
		expect(mod.year).toBe(2025);
		expect(mod.years).toEqual([2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]);
		expect(mod.credit).toBe('USDA NASS CSB');
		expect(mod.updatedAt).not.toBeNull();
	});

	it('stays in error, saying so, before the build: no sources or layers', async () => {
		vi.stubGlobal('location', { origin: 'http://x' });
		vi.stubGlobal('fetch', vi.fn(async () => json({ built: false, year: null, label: null, first_year: null, edition: null })));
		map = fakeMap();
		mod = new CropsModule();
		await expect(mod.mount(fakeCtx(map).ctx)).rejects.toThrow('Crop fields are not built yet');
		expect(mod.status).toBe('error');
		expect(mod.error).toBe('Crop fields are not built yet');
		expect(map.layers.size).toBe(0);
		expect(map.sources.size).toBe(0);
	});

	it('shows and hides every layer with setVisible, never touching the year source\'s tiles', async () => {
		await mount();
		for (const id of ALL_IDS) expect(map.layers.get(id)!.layout!.visibility, id).toBe('none');
		mod.setVisible(true);
		for (const id of ALL_IDS) expect(map.layers.get(id)!.layout!.visibility, id).toBe('visible');
		mod.setVisible(false);
		for (const id of ALL_IDS) expect(map.layers.get(id)!.layout!.visibility, id).toBe('none');
	});

	it('switches the year: the year source gets that year\'s tiles, the dissolves swap sources, the fields recolour', async () => {
		await mount();
		mod.setVisible(true);
		// The newest year draws the dissolves from the fields tiles; the year source's layers are out of every zoom.
		expect(map.layers.get(ID.fillLo)!.maxzoom).toBe(11);
		expect(map.layers.get(ID.fillLoYear)!.minzoom).toBe(22);
		mod.setYear(2019);
		expect(mod.year).toBe(2019);
		expect(map.sources.get(SOURCE_YEAR)!.spec.tiles).toEqual(['http://x/api/farm/tiles/crop_year_2019/{z}/{x}/{y}?v=v1']);
		expect(map.layers.get(ID.fillLo)!.minzoom).toBe(22);
		expect(map.layers.get(ID.fillLoYear)!.minzoom).toBe(0);
		expect(map.layers.get(ID.fillLoYear)!.maxzoom).toBe(11);
		expect(map.calls.paint.some(([id, k]) => id === ID.fill && k === 'fill-color')).toBe(true);
		expect(map.calls.paint.some(([id, k]) => id === ID.pattern && k === 'fill-pattern')).toBe(true);
		expect(map.calls.layout).toContainEqual([ID.label, 'text-field']);
		// Visibility is the manager's: switching the year never changes it.
		for (const id of ALL_IDS) expect(map.layers.get(id)!.layout!.visibility, id).toBe('visible');
		// Back to the newest year: the dissolves return to the fields tiles.
		mod.setYear(2025);
		expect(map.layers.get(ID.fillLo)!.minzoom).toBe(0);
		expect(map.layers.get(ID.fillLoYear)!.minzoom).toBe(22);
		// A year that isn't in the window changes nothing.
		const before = map.calls.zoom.length;
		mod.setYear(2010);
		mod.setYear(2025);
		expect(map.calls.zoom.length).toBe(before);
	});

	it('toggles the growth hatches through the layers\' filters', async () => {
		await mount();
		const filterOf = (id: string) => map.layers.get(id)!.filter as unknown[];
		expect(JSON.stringify(filterOf(ID.growth))).toContain('built_over');
		expect(JSON.stringify(filterOf(ID.plat))).toContain('literal'); // off by default: matches nothing
		mod.setGrowth('plat', true);
		expect(JSON.stringify(filterOf(ID.plat))).toContain('"p"');
		mod.setGrowth('built_over', false);
		mod.setGrowth('being_built', false);
		expect(JSON.stringify(filterOf(ID.growth))).not.toContain('built_over');
		expect(mod.growth).toEqual({ built_over: false, being_built: false, plat: true });
		const n = map.calls.filter.length;
		mod.setGrowth('plat', true); // already on
		expect(map.calls.filter.length).toBe(n);
	});

	it('selects a field a click picked: kind crop, owned by the layer, with its acres and crop', async () => {
		await mount();
		const [layer] = mod.interactive;
		expect(layer.layerIds).toEqual([ID.fill, ID.copy, ID.growth, ID.plat]);
		const sel = layer.pick({ id: 77, properties: { a: 24, g: 'hay', n: 'Alfalfa', y: 'hhhhhhhh' } } as never)!;
		expect(sel).toMatchObject({ kind: 'crop', id: '77', layer: 'crops', title: 'Estimated field', fact: '24 acres · Alfalfa' });
		expect(layer.pick({ properties: {} } as never)).toBeNull();
	});

	it('keeps #field= in step with the selection, and outlines the selected field', async () => {
		await mount();
		const sel = mod.interactive[0].pick({ id: 77, properties: { a: 24, g: 'hay' } } as never)!;
		mod.selected(sel);
		expect(env.params[FIELD_PARAM]).toBe('77');
		expect(JSON.stringify(map.layers.get(ID.selected)!.filter)).toContain('77');
		mod.selected(null);
		expect(env.params[FIELD_PARAM]).toBeNull();
		expect(map.layers.get(ID.selected)!.filter).toEqual(SELECTED_NONE);
		// Another layer's selection clears it too.
		mod.selected(sel);
		mod.selected({ kind: 'tree', id: 't', layer: 'trees', title: 'Tree' });
		expect(env.params[FIELD_PARAM]).toBeNull();
	});

	it('opens #field=<id>: fetches the card, selects it, flies there, and keeps the link while it loads', async () => {
		await mount({ hash: { [FIELD_PARAM]: '77' } });
		await vi.waitFor(() => expect(env.selected).toHaveLength(1));
		expect(fetches).toContain('/api/farm/fields/77');
		expect(env.selected[0]).toMatchObject({ kind: 'crop', id: '77', layer: 'crops', at: [-116.6, 43.6] });
		expect(map.calls.flyTo[0]).toMatchObject({ center: [-116.6, 43.6] });
		expect((map.calls.flyTo[0] as { zoom: number }).zoom).toBeGreaterThanOrEqual(14);
		// The manager's first `selected(null)` (nothing selected yet) must not erase the link.
		expect(env.params[FIELD_PARAM]).toBe('77');
	});

	it('drops a link to a field that isn\'t there, and ignores one that isn\'t a number', async () => {
		await mount({ hash: { [FIELD_PARAM]: '99' }, card: null });
		await vi.waitFor(() => expect(env.params[FIELD_PARAM]).toBeNull());
		expect(env.selected).toHaveLength(0);
		mod.destroy();
		await mount({ hash: { [FIELD_PARAM]: 'abc' } });
		expect(fetches.some((u) => u.includes('abc'))).toBe(false);
	});

	it('keeps each card for a while: one request per field', async () => {
		await mount();
		await mod.detail('5');
		await mod.detail('5');
		expect(fetches.filter((u) => u === '/api/farm/fields/5')).toHaveLength(1);
		await expect(mod.detail('404')).resolves.toBeDefined();
	});

	it('declares its slot flags to the manager when its layers are added', async () => {
		await mount();
		// (The fake map has no anchors, so layers go to the end; the flags are what the manager reads.)
		const flags = slotFlags(map);
		expect(flags.size).toBe(ALL_IDS.length);
		expect(flags.get(ID.fill)).toMatchObject({ owner: 'crops', areaFill: true, looks: 'clay' });
		expect(flags.get(ID.copyLoYear)).toMatchObject({ owner: 'crops', areaFill: true, aerial: 'only' });
	});
});

