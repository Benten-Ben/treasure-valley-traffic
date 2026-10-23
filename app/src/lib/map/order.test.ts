import { beforeAll, describe, expect, it } from 'vitest';
import type { LayerSpecification } from 'maplibre-gl';
import { cameraLayers } from '#lib/layers/cameras/cameras.js';
import { KEEPER, streetLayers } from '#lib/layers/streets/streets.js';
import { roadWeatherLayers } from '#lib/layers/roadweather/layers.js';
import { treeLayers } from '#lib/layers/trees/trees.js';
import { networkLayers, SOURCES as TRANSIT_SOURCES } from '#lib/layers/transit/network.js';
import { stopNameLayer } from '#lib/layers/transit/stops3d.js';
import { fallbackBusLayers } from '#lib/layers/transit/transit.js';
import type { BaseContribution, BaseLayer } from '#lib/base/types.js';
import type { LayerId } from '#lib/layers/types.js';
import { addSlotted, ANCHORS, DRAPED_TYPES, drapedRuns, fillOwner, insertSlotted, ordered, rttStacks, slotAllowed, slotFlags, type Slot, type SlotGate, type SlottedLayer } from './order.js';
import { contributionLayer } from './flavors.js';
import { addAerial, basemapReady, BUILDINGS_LAYERS, buildStyle, type BasemapManifest } from './style.js';

beforeAll(() => basemapReady);

const manifest: BasemapManifest = {
	bounds: [-117.05, 43, -115.95, 43.85],
	center: [-116.4, 43.6],
	zoom: 10,
	basemap: { file: 'valley.pmtiles', flavor: 'light', attribution: 'OSM', built: '2026-10-05' },
	glyphs: 'fonts/{fontstack}/{range}.pbf',
	sprite: 'sprites/v4/light',
	terrain: { file: 'terrain.pmtiles', encoding: 'mapbox', tileSize: 512, exaggeration: 1.3, attribution: 'USGS 3DEP', built: '2026-10-05' },
	buildings: { file: 'buildings.pmtiles', sourceLayer: 'buildings', minzoom: 14, attribution: 'Overture', built: '2026-10-05' },
	imagery: { file: 'imagery.pmtiles', tileSize: 512, maxzoom: 14, attribution: 'USDA NAIP', built: '2026-10-05', detail: { file: 'd.pmtiles', minzoom: 15, maxzoom: 17, points: 1, radius: 1 } }
};

/** The temporary wash the manager adds before anchor:base. */
const wash: SlottedLayer = { slot: 'base', layer: { id: 'base-wash', type: 'fill', source: 'base-wash', paint: {} } };
/** A stand-in for the overlay custom layer (not draped). */
const overlay = { id: 'overlay', type: 'custom' } as unknown as LayerSpecification;

/** Transit's layers as its module adds them (the ribbons, stops, hubs, shields and trails, and stop names). */
const transitLayers = () => [...networkLayers(), stopNameLayer(TRANSIT_SOURCES.stops)];

const ALL_LAYERS: Record<string, string[]> = {
	streets: streetLayers().map((s) => s.layer.id),
	transit: transitLayers().map((s) => s.layer.id),
	cameras: cameraLayers().map((s) => s.layer.id),
	weather: roadWeatherLayers().map((s) => s.layer.id),
	trees: treeLayers().map((s) => s.layer.id)
};

/** The style with every module's layers inserted the way they are at run time, in a given load order. */
function assembled(loadOrder: string[], o: { aerial: boolean }): LayerSpecification[] {
	const style = buildStyle(manifest, 'http://x');
	let layers = style.layers;
	const mods: Record<string, SlottedLayer[]> = {
		streets: streetLayers(),
		transit: [...transitLayers(), ...fallbackBusLayers()],
		cameras: cameraLayers(),
		weather: roadWeatherLayers(),
		trees: treeLayers()
	};
	// Each module's rank is its def's order (streets 10, transit 20, cameras 30, road weather 40, trees 50).
	const rank: Record<string, number> = { streets: 10, transit: 20, cameras: 30, weather: 40, trees: 50 };
	const ranks = {};
	layers = insertSlotted(layers, [wash], 0, ranks);
	for (const id of loadOrder) layers = insertSlotted(layers, mods[id], rank[id], ranks);
	layers = insertSlotted(layers, [{ slot: 'overlay', layer: overlay }], 100, ranks);
	if (o.aerial) {
		const map = {
			layers,
			getLayer: (id: string) => map.layers.find((l) => l.id === id),
			getSource: () => undefined,
			addSource: () => {},
			addLayer: (l: LayerSpecification, before?: string) => {
				const i = before ? map.layers.findIndex((x) => x.id === before) : -1;
				if (i === -1) map.layers.push(l);
				else map.layers.splice(i, 0, l);
			},
			getLayersOrder: () => map.layers.map((l) => l.id),
			setLayoutProperty: () => {},
			setPaintProperty: () => {}
		};
		addAerial(map as never, manifest, 'http://x');
		layers = map.layers;
	}
	return layers;
}

const subsets = <T>(xs: T[]): T[][] => xs.reduce<T[][]>((acc, x) => [...acc, ...acc.map((s) => [...s, x])], [[]]);

describe('rttStacks', () => {
	it('counts contiguous draped runs among the layers that draw', () => {
		const L = (id: string, type: string, visible = true) => ({ id, type, visible });
		expect(rttStacks([])).toBe(0);
		expect(rttStacks([L('a', 'fill'), L('b', 'line'), L('c', 'raster')])).toBe(1);
		expect(rttStacks([L('a', 'fill'), L('s', 'symbol'), L('b', 'line')])).toBe(2);
		// Hidden layers neither draw nor break a run.
		expect(rttStacks([L('a', 'fill'), L('s', 'symbol', false), L('b', 'line')])).toBe(1);
		expect(rttStacks([L('a', 'fill'), L('x', 'fill-extrusion'), L('b', 'line', false)])).toBe(1);
		// Zoom ranges count too (MapLibre's isHidden).
		const z = [{ id: 'a', type: 'fill' }, { id: 'x', type: 'fill-extrusion', minzoom: 14 }, { id: 'b', type: 'line' }];
		expect(rttStacks(z, 12)).toBe(1);
		expect(rttStacks(z, 15)).toBe(2);
		expect(drapedRuns(z, 15)).toEqual([['a'], ['b']]);
	});

	it('is at most 1 for every combination of layers, Aerial and load order, at every zoom', () => {
		const ids = Object.keys(ALL_LAYERS);
		for (const aerial of [false, true]) {
			for (const order of [ids, [...ids].reverse(), ['transit', 'weather', 'trees', 'streets', 'cameras']]) {
				const layers = assembled(order, { aerial });
				for (const on of subsets(ids)) {
					for (const buildings of [true, false]) {
						const shown = new Set(on.flatMap((id) => ALL_LAYERS[id]));
						const list = layers.map((l) => {
							const o = ordered(l);
							if (Object.values(ALL_LAYERS).flat().includes(l.id)) o.visible = shown.has(l.id);
							// Streets' keeper can stay visible after Streets is off (until the map moves): count it as always on.
							if (l.id === KEEPER) o.visible = true;
							if (l.id === 'base-wash') o.visible = on.length > 0;
							if (l.id === 'aerial' || l.id === 'aerial-detail') o.visible = aerial;
							if (BUILDINGS_LAYERS.includes(l.id)) o.visible = buildings;
							return o;
						});
						for (const zoom of [8, 10, 12, 14, 15.5, 17, 19]) {
							const runs = drapedRuns(list, zoom);
							expect(runs.length, `on=[${on}] aerial=${aerial} buildings=${buildings} z${zoom}: ${JSON.stringify(runs)}`).toBeLessThanOrEqual(1);
						}
					}
				}
			}
		}
	});

	it('puts each module’s layers in its slot whatever loads first', () => {
		const a = assembled(['streets', 'transit', 'cameras', 'weather', 'trees'], { aerial: false }).map((l) => l.id);
		const b = assembled(['trees', 'weather', 'cameras', 'transit', 'streets'], { aerial: false }).map((l) => l.id);
		expect(a).toEqual(b);
		const at = (id: string) => a.indexOf(id);
		expect(at('streets-speed')).toBeLessThan(at(ANCHORS.streets));
		expect(at('cones-fill')).toBeGreaterThan(at(ANCHORS.lanes));
		expect(at('transit-routes')).toBeGreaterThan(at(ANCHORS.footprints));
		expect(at('transit-routes')).toBeLessThan(at(ANCHORS.routes));
		expect(at('cameras-calibrated')).toBeGreaterThan(at(ANCHORS.scene));
		expect(at('cameras-calibrated')).toBeLessThan(at(ANCHORS.points));
		// Tree discs: over the buildings with the 3D scene, under the stop capsules and camera icons.
		expect(at('trees-discs')).toBeGreaterThan(at(ANCHORS.routes));
		expect(at('trees-discs')).toBeLessThan(at(ANCHORS.scene));
		// Labels below the buses: every symbol layer sits under the overlay and the fallback bus layers.
		const lastSymbol = a.findLastIndex((id) => id === 'streets-speed-labels' || id === 'transit-shields' || id === 'transit-hubs' || id === 'places_locality');
		expect(lastSymbol).toBeLessThan(at('transit-buses'));
		expect(at('transit-buses')).toBeLessThan(at('overlay'));
	});
});


// -- the landscape slots (S3a) ------------------------------------------------------------------------------------

const info = (plugin: string, layer: string) => ({
	plugin,
	layer,
	build: 'b',
	geometry: 'Polygon',
	features: 1,
	fields: {},
	minzoom: 12,
	maxzoom: 16,
	licence: 'ODbL-1.0',
	republish: 'internal',
	credit: []
});
const landscapeManifest: BasemapManifest = {
	...manifest,
	landscape: {
		status: 'baked',
		file: 'l.pmtiles',
		digest: 'l',
		format: 'pbf',
		minzoom: 8,
		maxzoom: 16,
		promoteId: 'id',
		layers: { 'a.one': info('a', 'one'), 'b.two': info('b', 'two') },
		empty: [],
		attribution: 'OSM',
		licences: [],
		republish: 'internal',
		access: 'tailnet',
		inputs: [],
		built: '2026-10-20',
		spec: 1,
		previous: null
	}
};

const bl = (id: string, type: BaseLayer['type'], slot: Slot, rank: number, o: Partial<BaseLayer> = {}): BaseLayer => ({ id, type, slot, rank, sourceLayer: 'a.one', valley: {}, ...o });
const CONTRIBUTIONS: BaseContribution[] = [
	{ id: 'a.one', title: 'a', blurb: 'a', source: { kind: 'landscape', sourceLayers: ['a.one'] }, looks: 'both', credit: '', layers: [bl('a-fill', 'fill', 'surfaces', 10, { aerial: 'hide' }), bl('a-line', 'line', 'land', 10, { aerial: 'only' })] },
	{ id: 'b.two', title: 'b', blurb: 'b', source: { kind: 'landscape', sourceLayers: ['b.two'] }, looks: 'valley', credit: '', layers: [bl('b-fill', 'fill', 'water', 10, { sourceLayer: 'b.two' })] },
	{ id: 'g.ground', title: 'g', blurb: 'g', source: { kind: 'ground' }, looks: 'valley', credit: '', layers: [bl('g-paint', 'raster', 'ground', 0, { aerial: 'hide' })] },
	{ id: 's.scars', title: 's', blurb: 's', source: { kind: 'tiles', plugin: 's', layer: 'scars', minzoom: 8, maxzoom: 15 }, looks: 'both', credit: '', layers: [bl('s-fill', 'fill', 'areas', 10)] }
];
/** Synthetic tray layers: one draped layer in a landscape slot each (soils, crops in two slots, trails over the streets). */
const TRAY: Record<string, SlottedLayer[]> = {
	soils: [{ slot: 'areas', layer: { id: 'soils-fill', type: 'fill', source: 'x' } as LayerSpecification, areaFill: true }],
	crops: [
		{ slot: 'areas', layer: { id: 'crops-fill', type: 'fill', source: 'x' } as LayerSpecification, areaFill: true },
		{ slot: 'land', layer: { id: 'crops-fill-aerial', type: 'fill', source: 'x' } as LayerSpecification, areaFill: true, aerial: 'only' }
	],
	water: [{ slot: 'water', layer: { id: 'water-line', type: 'line', source: 'x' } as LayerSpecification }],
	trails: [{ slot: 'routes', layer: { id: 'trails-line', type: 'line', source: 'x' } as LayerSpecification }]
};

describe('the landscape slots', () => {
	/** The style with the contributions built in (ground and tiles as the manager adds them) and the tray layers inserted. */
	function landscapeStyle(aerialAdded: boolean) {
		const style = buildStyle(landscapeManifest, 'http://x', aerialAdded, 'valley', { contributions: CONTRIBUTIONS });
		let layers = style.layers;
		const ranks = {};
		for (const c of CONTRIBUTIONS) {
			if (c.source.kind === 'landscape') continue;
			for (const l of c.layers) layers = insertSlotted(layers, [{ slot: l.slot, layer: contributionLayer(c, l, { flavor: 'valley', aerial: false, layers: new Set() }) }], l.rank, ranks);
		}
		let rank = 60;
		for (const [id, add] of Object.entries(TRAY)) layers = insertSlotted(layers, add, rank++ + id.length, ranks);
		layers = insertSlotted(layers, [wash], 0, ranks);
		return layers;
	}

	it('is one draped block from anchor:ground to anchor:routes, in every on/off combination, at z12, z15.5 and z17', () => {
		const ids = Object.keys(TRAY);
		const contributionLayers = CONTRIBUTIONS.flatMap((c) => c.layers.map((l) => l.id));
		const toggles = [...ids, ...contributionLayers];
		for (const aerial of [false, true]) {
			const layers = landscapeStyle(aerial);
			// No layer that isn't draped sits between the ground and the routes anchor, shown or not.
			const from = layers.findIndex((l) => l.id === ANCHORS.ground);
			const to = layers.findIndex((l) => l.id === ANCHORS.routes);
			expect(from).toBeGreaterThan(-1);
			expect(to).toBeGreaterThan(from);
			const bad = layers.slice(from, to).filter((l) => !DRAPED_TYPES.has(l.type));
			expect(bad.map((l) => l.id), 'non-draped layers inside the draped block').toEqual([]);
			const tray = new Set(Object.values(TRAY).flat().map((s) => s.layer.id));
			for (const on of subsets(toggles)) {
				const shown = new Set(on.flatMap((t) => (TRAY[t] ? TRAY[t].map((s) => s.layer.id) : [t])));
				const list = layers.map((l) => {
					const o = ordered(l);
					if (tray.has(l.id) || contributionLayers.includes(l.id)) o.visible = shown.has(l.id);
					if (l.id === 'base-wash') o.visible = on.length > 0;
					if (l.id === 'aerial' || l.id === 'aerial-detail') o.visible = aerial;
					if (overlay.id === l.id) o.visible = true;
					return o;
				});
				for (const zoom of [12, 15.5, 17]) expect(rttStacks(list, zoom), `on=[${on}] aerial=${aerial} z${zoom}`).toBe(1);
			}
		}
	});

	it('orders the slots whatever loads first: tray layers by rank, contributions by theirs', () => {
		const a = landscapeStyle(false).map((l) => l.id);
		const at = (id: string) => a.indexOf(id);
		expect(at('g-paint')).toBeLessThan(at(ANCHORS.ground));
		expect(at(ANCHORS.ground)).toBeLessThan(at('landcover'));
		for (const id of ['soils-fill', 'crops-fill', 's-fill']) {
			expect(at(id), id).toBeGreaterThan(at('landuse_park'));
			expect(at(id), id).toBeLessThan(at(ANCHORS.areas));
		}
		expect(at('water-line')).toBeGreaterThan(at('water'));
		expect(at('water-line')).toBeLessThan(at(ANCHORS.water));
		expect(at('b-fill')).toBeLessThan(at(ANCHORS.water));
		expect(at('a-fill')).toBeGreaterThan(at(ANCHORS.water));
		expect(at('a-fill')).toBeLessThan(at(ANCHORS.surfaces));
		expect(at(ANCHORS.surfaces)).toBeLessThan(at('roads_minor'));
		// The area fills' Aerial copies sit over the photo, under the streets.
		expect(at('crops-fill-aerial')).toBeGreaterThan(at(ANCHORS.base));
		expect(at('a-line')).toBeLessThan(at(ANCHORS.land));
		expect(at(ANCHORS.land)).toBeLessThan(at(ANCHORS.streets));
		expect(at('trails-line')).toBeLessThan(at(ANCHORS.routes));
	});

	it('records the slot flags a module adds, with its owner', () => {
		const map: Parameters<typeof addSlotted>[0] = { getLayer: () => ({}), getLayersOrder: () => [] };
		const added: string[] = [];
		addSlotted(map, TRAY.crops, 80, (l) => void added.push(l.id), 'crops');
		addSlotted(map, TRAY.water, 90, (l) => void added.push(l.id), 'water');
		expect(added).toEqual(['crops-fill', 'crops-fill-aerial', 'water-line']);
		expect([...slotFlags(map)]).toEqual([
			['crops-fill', { aerial: undefined, areaFill: true, owner: 'crops' }],
			['crops-fill-aerial', { aerial: 'only', areaFill: true, owner: 'crops' }]
		]);
		expect([...slotFlags({})]).toEqual([]);
	});

	it('lets one area fill draw at a time, the layer turned on last, and gates by Aerial', () => {
		const owners = new Set<LayerId>(['soils', 'crops']);
		expect(fillOwner(['soils', 'crops'], owners)).toBe('crops');
		expect(fillOwner(['crops', 'soils'], owners)).toBe('soils');
		expect(fillOwner(['crops', 'streets', 'soils'], new Set<LayerId>(['crops']))).toBe('crops');
		expect(fillOwner(['streets'], owners)).toBeNull();
		const gate = (o: Partial<SlotGate> = {}): SlotGate => ({ aerial: false, fillOwner: 'crops', fillsOff: new Set(), ...o });
		const fill = { areaFill: true as const, owner: 'crops' as LayerId };
		expect(slotAllowed(fill, gate())).toBe(true);
		expect(slotAllowed({ ...fill, owner: 'soils' }, gate())).toBe(false);
		// Crops under Transit: its fills off, wherever it sits in the order.
		expect(slotAllowed(fill, gate({ fillsOff: new Set<LayerId>(['crops']) }))).toBe(false);
		// Aerial 'only' (the 0.45 copies) and 'hide' (the ground, the surfaces).
		expect(slotAllowed({ ...fill, aerial: 'only' }, gate())).toBe(false);
		expect(slotAllowed({ ...fill, aerial: 'only' }, gate({ aerial: true }))).toBe(true);
		expect(slotAllowed({ aerial: 'hide' }, gate())).toBe(true);
		expect(slotAllowed({ aerial: 'hide' }, gate({ aerial: true }))).toBe(false);
		// A layer added without an owner is gated by Aerial only.
		expect(slotAllowed({ areaFill: true }, gate({ fillOwner: null }))).toBe(true);
	});
	it('gates a layer by the flavor its `looks` names, as a base contribution\'s looks do', () => {
		const map: Parameters<typeof addSlotted>[0] = { getLayer: () => ({}), getLayersOrder: () => [] };
		const fill = (id: string, looks?: SlottedLayer['looks']): SlottedLayer => ({ slot: 'areas', layer: { id, type: 'fill', source: 's' }, looks });
		addSlotted(map, [fill('clay-only', 'clay'), fill('valley-only', 'valley'), fill('both', 'both'), fill('plain')], 10, () => {}, 'crops');
		const flags = slotFlags(map);
		// 'both' and no looks are no gate at all: not recorded.
		expect([...flags.keys()]).toEqual(['clay-only', 'valley-only']);
		const gate = (flavor?: SlotGate['flavor']): SlotGate => ({ aerial: false, fillOwner: 'crops', fillsOff: new Set(), flavor });
		expect(slotAllowed(flags.get('clay-only')!, gate('clay'))).toBe(true);
		expect(slotAllowed(flags.get('clay-only')!, gate('valley'))).toBe(false);
		expect(slotAllowed(flags.get('valley-only')!, gate('valley'))).toBe(true);
		expect(slotAllowed(flags.get('valley-only')!, gate('clay'))).toBe(false);
		// A gate that doesn't know the flavor leaves `looks` alone; the other flags still apply.
		expect(slotAllowed(flags.get('clay-only')!, gate())).toBe(true);
		expect(slotAllowed({ looks: 'clay', areaFill: true, owner: 'crops' }, { ...gate('clay'), fillsOff: new Set<LayerId>(['crops']) })).toBe(false);
	});
});
