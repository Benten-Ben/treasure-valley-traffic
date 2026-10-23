import { beforeAll, describe, expect, it } from 'vitest';
import type { LayerSpecification } from 'maplibre-gl';
import { layers as protomapsLayers, namedFlavor } from '@protomaps/basemaps';
import type { BaseContribution, BaseLayer } from '#lib/base/types.js';
import type { DataMeta } from '#lib/contracts/meta.js';
import { ANCHOR_IDS, ANCHORS } from './order.js';
import { contributionStatus, releaseGroups, suppressGroups, syncContributions, type SyncMap } from './flavors.js';
import {
	addAerial,
	aerialAfter,
	basemapReady,
	BUILDINGS_ESTIMATED_LAYER,
	BUILDINGS_LAYER,
	BUILDINGS_LAYERS,
	buildingOpacity,
	buildStyle,
	firstBasemapLabel,
	IMAGERY_LAYERS,
	PROTOMAPS_GROUPS,
	setAerial,
	type BasemapManifest,
	type LandscapeEntry,
	type MapLike
} from './style.js';

// The Protomaps style module loads apart from the initial bundle (WP2); buildStyle needs it.
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
	imagery: {
		file: 'imagery.pmtiles',
		tileSize: 512,
		maxzoom: 14,
		attribution: 'USDA NAIP',
		built: '2026-10-05',
		detail: { file: 'imagery-detail.pmtiles', minzoom: 15, maxzoom: 17, points: 228, radius: 250 }
	}
};

/** A map that holds a style's layers and sources, as MapLibre's methods see them. */
function fakeMap(layers: LayerSpecification[], sources: Record<string, unknown>): MapLike & { layers: LayerSpecification[] } {
	const m = {
		layers: [...layers],
		getLayer: (id: string) => m.layers.find((l) => l.id === id) as never,
		getSource: (id: string) => (sources[id] ? ({ id } as never) : undefined),
		addSource: (id: string, s: unknown) => void (sources[id] = s),
		addLayer: (l: LayerSpecification, before?: string) => {
			const i = before ? m.layers.findIndex((x) => x.id === before) : -1;
			if (i === -1) m.layers.push(l);
			else m.layers.splice(i, 0, l);
			return m as never;
		},
		getLayersOrder: () => m.layers.map((l) => l.id),
		setLayoutProperty: (id: string, k: string, v: unknown) => {
			const l = m.layers.find((x) => x.id === id)!;
			l.layout = { ...(l.layout ?? {}), [k]: v } as never;
			return m as never;
		},
		setPaintProperty: (id: string, k: string, v: unknown) => {
			const l = m.layers.find((x) => x.id === id)!;
			l.paint = { ...(l.paint ?? {}), [k]: v } as never;
			return m as never;
		}
	};
	return m as never;
}

describe('style', () => {
	it('has no imagery sources or layers unless Aerial is on at creation', () => {
		const off = buildStyle(manifest, 'http://x');
		expect(Object.keys(off.sources)).not.toContain('imagery');
		expect(Object.keys(off.sources)).not.toContain('imageryDetail');
		expect(off.layers.map((l) => l.id)).not.toContain('aerial');
		const on = buildStyle(manifest, 'http://x', true);
		expect(Object.keys(on.sources)).toEqual(expect.arrayContaining(['imagery', 'imageryDetail']));
		const ids = on.layers.map((l) => l.id);
		expect(ids.indexOf('aerial')).toBe(ids.indexOf('hillshade') + 1);
		expect(ids.indexOf('aerial-detail')).toBe(ids.indexOf('aerial') + 1);
		for (const id of BUILDINGS_LAYERS) expect(on.layers.find((l) => l.id === id)?.paint, id).toMatchObject({ 'fill-extrusion-opacity': buildingOpacity(true) });
	});

	it('uses self-hosted URLs only', () => {
		const s = buildStyle(manifest, 'http://127.0.0.1:5202');
		expect(s.glyphs).toBe('http://127.0.0.1:5202/tiles/fonts/{fontstack}/{range}.pbf');
		for (const src of Object.values(s.sources)) {
			const url = (src as { url?: string }).url;
			if (url) expect(url).toMatch(/^pmtiles:\/\/http:\/\/127\.0\.0\.1:5202\/tiles\//);
		}
	});

	it('adds the aerial layers on first use, right after the hillshade, and only once', () => {
		const style = buildStyle(manifest, 'http://x');
		const sources = { ...style.sources } as Record<string, unknown>;
		const map = fakeMap(style.layers, sources);
		// A data layer that went in under the labels before Aerial was ever on.
		map.addLayer({ id: 'streets-speed', type: 'line', source: 'roads' }, firstBasemapLabel(map));
		expect(addAerial(map, manifest, 'http://x')).toBe(true);
		const ids = map.getLayersOrder();
		expect(ids.indexOf('aerial')).toBe(ids.indexOf(aerialAfter(manifest)) + 1);
		expect(ids.indexOf('aerial-detail')).toBe(ids.indexOf('aerial') + 1);
		expect(ids.indexOf('aerial-detail')).toBeLessThan(ids.indexOf(BUILDINGS_LAYER));
		expect(ids.indexOf('aerial-detail')).toBeLessThan(ids.indexOf('streets-speed'));
		expect(map.getLayer('aerial')?.layout).toMatchObject({ visibility: 'none' });
		expect(sources.imagery).toBeTruthy();
		const count = ids.length;
		addAerial(map, manifest, 'http://x');
		expect(map.getLayersOrder()).toHaveLength(count);
	});

	it('setAerial shows and hides the imagery with the buildings to match', () => {
		const style = buildStyle(manifest, 'http://x');
		const map = fakeMap(style.layers, { ...style.sources });
		expect(setAerial(map, manifest, 'http://x', true)).toBe(true);
		for (const id of IMAGERY_LAYERS) expect(map.getLayer(id)?.layout).toMatchObject({ visibility: 'visible' });
		for (const id of BUILDINGS_LAYERS) expect(map.getLayer(id)?.paint, id).toMatchObject({ 'fill-extrusion-opacity': buildingOpacity(true) });
		expect(setAerial(map, manifest, 'http://x', false)).toBe(false);
		for (const id of IMAGERY_LAYERS) expect(map.getLayer(id)?.layout).toMatchObject({ visibility: 'none' });
		for (const id of BUILDINGS_LAYERS) expect(map.getLayer(id)?.paint, id).toMatchObject({ 'fill-extrusion-opacity': buildingOpacity(false) });
	});

	it('without imagery, Aerial stays off', () => {
		const m = { ...manifest, imagery: undefined };
		const style = buildStyle(m, 'http://x', true);
		const map = fakeMap(style.layers, { ...style.sources });
		expect(setAerial(map, m, 'http://x', true)).toBe(false);
		expect(map.getLayer('aerial')).toBeUndefined();
	});

	it('without terrain, the imagery goes after the basemap fills and lines', () => {
		const m = { ...manifest, terrain: undefined };
		const style = buildStyle(m, 'http://x');
		const ids = style.layers.map((l) => l.id);
		// The end of the base slot, which sits right after the basemap's last fill or line.
		expect(aerialAfter(m)).toBe(ANCHORS.base);
		const lastBase = style.layers[ids.indexOf(ANCHORS.base) - 1];
		expect(['fill', 'line']).toContain(lastBase.type);
		expect(ids.indexOf(ANCHORS.base)).toBeLessThan(style.layers.findIndex((l) => l.type === 'symbol'));
		const map = fakeMap(style.layers, { ...style.sources });
		expect(addAerial(map, m, 'http://x')).toBe(true);
		const after = map.getLayersOrder();
		expect(after.indexOf('aerial')).toBe(after.indexOf(ANCHORS.base) + 1);
		expect(after.indexOf('aerial-detail')).toBeLessThan(after.indexOf(ANCHORS.streets));
	});

	it('places the slot anchors in order, hidden, around the style’s own layers', () => {
		for (const m of [manifest, { ...manifest, terrain: undefined, buildings: undefined }]) {
			const style = buildStyle(m, 'http://x', true);
			const ids = style.layers.map((l) => l.id);
			const at = ANCHOR_IDS.map((id) => ids.indexOf(id));
			expect(at.every((i) => i >= 0)).toBe(true);
			expect([...at].sort((a, b) => a - b)).toEqual(at);
			for (const id of ANCHOR_IDS) expect(style.layers[ids.indexOf(id)]).toMatchObject({ type: 'background', layout: { visibility: 'none' } });
			// Hillshade and imagery under the data slots; 3D buildings over them; base labels between points and labels.
			if (m.terrain) expect(ids.indexOf('hillshade')).toBeGreaterThan(ids.indexOf(ANCHORS.base));
			expect(ids.indexOf('aerial')).toBeLessThan(ids.indexOf(ANCHORS.streets));
			if (m.buildings) {
				expect(ids.indexOf(BUILDINGS_LAYER)).toBeGreaterThan(ids.indexOf(ANCHORS.routes));
				expect(ids.indexOf(BUILDINGS_ESTIMATED_LAYER)).toBe(ids.indexOf(BUILDINGS_LAYER) + 1);
				expect(ids.indexOf(BUILDINGS_ESTIMATED_LAYER)).toBeLessThan(ids.indexOf(ANCHORS.scene));
			}
			const firstSymbol = style.layers.findIndex((l) => l.type === 'symbol');
			expect(firstSymbol).toBeGreaterThan(ids.indexOf(ANCHORS.points));
			expect(style.layers.findLastIndex((l) => l.type === 'symbol')).toBeLessThan(ids.indexOf(ANCHORS.labels));
		}
	});

	it('finds the basemap’s first label', () => {
		const style = buildStyle(manifest, 'http://x');
		const map = fakeMap(style.layers, { ...style.sources });
		const id = firstBasemapLabel(map)!;
		expect(map.getLayer(id)?.type).toBe('symbol');
		expect(style.layers.findIndex((l) => l.id === id)).toBe(style.layers.findIndex((l) => l.type === 'symbol'));
	});
});


// -- the landscape slots and base contributions (S3a) -------------------------------------------------------------

const layerInfo = (plugin: string, layer: string) => ({
	plugin,
	layer,
	build: '20261015T000000Z',
	geometry: 'Polygon',
	features: 10,
	fields: { id: 'int' },
	minzoom: 12,
	maxzoom: 16,
	licence: 'ODbL-1.0',
	republish: 'internal',
	credit: ['© OpenStreetMap contributors']
});

const landscape: LandscapeEntry = {
	status: 'baked',
	file: 'landscape-69f5a8c6bc10.pmtiles',
	digest: '69f5a8c6bc10',
	format: 'pbf',
	minzoom: 8,
	maxzoom: 16,
	promoteId: 'id',
	layers: { 'roads.surfaces': layerInfo('roads', 'surfaces'), 'water.reaches': layerInfo('water', 'reaches') },
	empty: ['fences.lines'],
	attribution: '© OpenStreetMap contributors',
	licences: ['ODbL-1.0'],
	republish: 'internal',
	access: 'tailnet',
	inputs: [],
	built: '2026-10-20',
	spec: 1,
	previous: null
};

const painted: NonNullable<BasemapManifest['ground']> = {
	status: 'painted',
	file: 'ground-1.pmtiles',
	tileSize: 512,
	format: 'webp',
	minzoom: 8,
	maxzoom: 15,
	detail: { file: 'ground-detail-1.pmtiles', minzoom: 16, maxzoom: 18, boxes: ['a'] },
	attribution: 'USDA NRCS SSURGO',
	licence: 'public-domain',
	republish: 'yes',
	inputs: [],
	fallbacks: [],
	built: '2026-10-18',
	spec: 1
};

const built: BasemapManifest = { ...manifest, landscape, ground: painted };

const bl = (id: string, type: BaseLayer['type'], slot: BaseLayer['slot'], rank: number, o: Partial<BaseLayer> = {}): BaseLayer => ({
	id,
	type,
	slot,
	rank,
	valley: type === 'raster' ? { 'raster-opacity': 1 } : { [`${type}-color`]: '#989088' },
	...o
});
const contribution = (id: string, source: BaseContribution['source'], looks: BaseContribution['looks'], layers: BaseLayer[], o: Partial<BaseContribution> = {}): BaseContribution => ({
	id,
	title: id,
	blurb: id,
	source,
	looks,
	layers,
	credit: 'test',
	...o
});

const SURFACES = contribution('roads.surfaces', { kind: 'landscape', sourceLayers: ['roads.surfaces'] }, 'both', [
	bl('surfaces-fill', 'fill', 'surfaces', 10, { sourceLayer: 'roads.surfaces', clay: { 'fill-color': '#F8F4EC' }, aerial: 'hide' }),
	// Markings: in Clay only with Lanes on.
	bl('surfaces-marks', 'line', 'surfaces', 20, { sourceLayer: 'roads.surfaces', show: (s) => s.flavor === 'valley' || s.layers.has('lanes') })
]);
const WATER = contribution('water.reaches', { kind: 'landscape', sourceLayers: ['water.reaches'] }, 'valley', [bl('water-fill', 'fill', 'water', 10, { sourceLayer: 'water.reaches' })], {
	suppresses: { groups: ['water', 'water-labels'] }
});
const FENCES = contribution('fences.lines', { kind: 'landscape', sourceLayers: ['fences.lines'] }, 'both', [bl('fence-line', 'line', 'land', 10, { sourceLayer: 'fences.lines' })], {
	suppresses: { groups: ['service'] }
});
const GROUND = contribution('soils.ground', { kind: 'ground' }, 'valley', [
	bl('ground-paint', 'raster', 'ground', 0, { aerial: 'hide' }),
	bl('ground-detail', 'raster', 'ground', 5, { detail: true, minzoom: 16, aerial: 'hide' })
]);
const SCARS = contribution('fire.scars', { kind: 'tiles', plugin: 'fire', layer: 'scars', minzoom: 8, maxzoom: 15 }, 'both', [
	bl('scars-fill', 'fill', 'areas', 10, { sourceLayer: 'scars' })
]);
const ALL = [SURFACES, WATER, FENCES, GROUND, SCARS];

const metaWith = (layers: Record<string, string>) => ({ versions: { layers }, layers: { 'fire.scars': { credit: '© Fire Atlas' } } }) as unknown as DataMeta;

/** A map the base pass can drive: layout reads, zoom ranges and paint writes on top of `fakeMap`. */
function syncMap(style: { layers: LayerSpecification[]; sources: Record<string, unknown> }): SyncMap & { layers: LayerSpecification[]; sources: Record<string, unknown> } {
	const sources = { ...style.sources };
	const m = fakeMap(style.layers, sources) as unknown as SyncMap & { layers: LayerSpecification[]; sources: Record<string, unknown> };
	const any = m as any;
	any.sources = sources;
	any.getLayoutProperty = (id: string, k: string) => (any.layers.find((x: LayerSpecification) => x.id === id)?.layout ?? {})[k];
	any.setLayerZoomRange = (id: string, min: number, max: number) => {
		const l = any.layers.find((x: LayerSpecification) => x.id === id);
		l.minzoom = min;
		l.maxzoom = max;
	};
	return m;
}
const visibility = (map: { layers: LayerSpecification[] }, id: string) => (map.layers.find((l) => l.id === id)?.layout as { visibility?: string } | undefined)?.visibility;
const state = (flavor: 'valley' | 'clay', o: { aerial?: boolean; layers?: string[] } = {}) => ({ flavor, aerial: o.aerial ?? false, layers: new Set((o.layers ?? []) as never[]) });

describe('the landscape slots', () => {
	it('puts the slots in the plan’s order (§3.2) around the basemap’s own fills and lines', () => {
		const ids = buildStyle(manifest, 'http://x', true).layers.map((l) => l.id);
		const at = (id: string) => ids.indexOf(id);
		const order = ['background', 'earth', ANCHORS.ground, 'landcover', ANCHORS.areas, 'water', ANCHORS.water, ANCHORS.surfaces, 'roads_minor', 'rail-track', ANCHORS.base, 'hillshade', 'aerial', 'aerial-detail', ANCHORS.land, ANCHORS.streets, ANCHORS.lanes, ANCHORS.footprints, ANCHORS.routes];
		const positions = order.map(at);
		expect(positions.every((i) => i >= 0), JSON.stringify(order.filter((id) => at(id) < 0))).toBe(true);
		expect([...positions].sort((a, b) => a - b)).toEqual(positions);
		// Every landuse fill is under the areas anchor, every water layer under the water one, every road line over the surfaces.
		for (const id of PROTOMAPS_GROUPS.landcover) expect(at(id), id).toBeLessThan(at(ANCHORS.areas));
		for (const id of PROTOMAPS_GROUPS.water) expect(at(id), id).toBeGreaterThan(at(ANCHORS.areas));
		for (const id of PROTOMAPS_GROUPS.water) expect(at(id), id).toBeLessThan(at(ANCHORS.water));
		for (const id of PROTOMAPS_GROUPS.roads) expect(at(id), id).toBeGreaterThan(at(ANCHORS.surfaces));
	});

	it('names basemap groups that exist in Protomaps’ own layer list', () => {
		const have = new Set(protomapsLayers('protomaps', namedFlavor('light'), { lang: 'en' }).map((l) => l.id));
		for (const [group, ids] of Object.entries(PROTOMAPS_GROUPS)) for (const id of ids) expect(have.has(id), `${group}: ${id}`).toBe(true);
		const roads: readonly string[] = PROTOMAPS_GROUPS.roads;
		for (const id of ['roads_rail', 'roads_runway', 'roads_taxiway', 'roads_pier']) expect(roads).not.toContain(id);
		// Every roads_* line outside those four is in the group.
		const lines = protomapsLayers('protomaps', namedFlavor('light'), { lang: 'en' }).filter((l) => l.id.startsWith('roads_') && l.type === 'line').map((l) => l.id);
		expect(lines.filter((id) => !roads.includes(id)).sort()).toEqual(['roads_pier', 'roads_rail', 'roads_runway', 'roads_taxiway']);
		expect(PROTOMAPS_GROUPS.service).toEqual(['roads_minor_service', 'roads_minor_service_casing']);
		expect(PROTOMAPS_GROUPS.paths).toEqual(['roads_other']);
		expect(PROTOMAPS_GROUPS['water-labels']).toEqual(['water_waterway_label', 'water_label_lakes']);
	});
});

describe('base contributions', () => {
	it('adds nothing for an unbuilt contribution, and says why', () => {
		// No landscape entry at all.
		const style = buildStyle(manifest, 'http://x', false, 'valley', { contributions: ALL });
		expect(Object.keys(style.sources)).not.toContain('landscape');
		const ids = style.layers.map((l) => l.id);
		for (const id of ['surfaces-fill', 'water-fill', 'fence-line', 'ground-paint', 'scars-fill']) expect(ids).not.toContain(id);
		expect(contributionStatus(SURFACES, manifest)).toEqual({ built: false, reason: 'not built yet' });
		expect(contributionStatus(GROUND, manifest)).toEqual({ built: false, reason: 'not built yet' });
		expect(contributionStatus(SCARS, manifest, null)).toEqual({ built: false, reason: 'not built yet' });
		// An empty entry carries its own reason; a flat ground says why it is flat.
		const empty: BasemapManifest = { ...manifest, landscape: { status: 'empty', reason: 'Every base layer is empty.', previous: null, built: '2026-10-20', spec: 1 }, ground: { status: 'flat', reason: 'Flat ground: no soils.', built: '2026-10-20', spec: 1 } };
		expect(contributionStatus(SURFACES, empty)).toEqual({ built: false, reason: 'Every base layer is empty.' });
		expect(contributionStatus(GROUND, empty)).toEqual({ built: false, reason: 'Flat ground: no soils.' });
		expect(Object.keys(buildStyle(empty, 'http://x', false, 'valley', { contributions: ALL }).sources)).not.toContain('landscape');
	});

	it('does not build a layer listed under empty, or one missing from the file', () => {
		expect(contributionStatus(FENCES, built)).toEqual({ built: false, reason: 'not built yet' });
		// Even if the entry (wrongly) lists it in both places, `empty` wins.
		const both: BasemapManifest = { ...built, landscape: { ...landscape, layers: { ...landscape.layers, 'fences.lines': layerInfo('fences', 'lines') }, empty: ['fences.lines'] } };
		expect(contributionStatus(FENCES, both).built).toBe(false);
		const style = buildStyle(built, 'http://x', false, 'valley', { contributions: ALL });
		expect(style.layers.map((l) => l.id)).not.toContain('fence-line');
		// Built contributions are there, and an unbuilt one's groups stay on the map.
		expect(style.layers.map((l) => l.id)).toEqual(expect.arrayContaining(['surfaces-fill', 'water-fill']));
		const map = syncMap(style);
		syncContributions(map, built, 'http://x', null, state('valley'), ALL);
		expect(visibility(map, 'roads_minor_service')).not.toBe('none');
	});

	it('builds the shared landscape source from the entry and slots the layers by rank', () => {
		const style = buildStyle(built, 'http://x', false, 'valley', { contributions: ALL });
		expect(style.sources.landscape).toEqual({
			type: 'vector',
			url: 'pmtiles://http://x/tiles/landscape-69f5a8c6bc10.pmtiles',
			minzoom: 8,
			maxzoom: 16,
			promoteId: 'id',
			attribution: '© OpenStreetMap contributors'
		});
		const ids = style.layers.map((l) => l.id);
		const at = (id: string) => ids.indexOf(id);
		expect(at('surfaces-fill')).toBeGreaterThan(at(ANCHORS.areas));
		expect(at('surfaces-fill')).toBeLessThan(at('surfaces-marks'));
		expect(at('surfaces-marks')).toBeLessThan(at(ANCHORS.surfaces));
		expect(at('surfaces-fill')).toBeGreaterThan(at(ANCHORS.water));
		expect(at('water-fill')).toBeGreaterThan(at(ANCHORS.areas));
		expect(at('water-fill')).toBeLessThan(at(ANCHORS.water));
		// The painted ground and a toggled layer's tiles join the running map, not the style.
		expect(ids).not.toContain('ground-paint');
		expect(ids).not.toContain('scars-fill');
		expect(Object.keys(style.sources)).not.toContain('ground');
		expect(style.layers.find((l) => l.id === 'surfaces-fill')).toMatchObject({ source: 'landscape', 'source-layer': 'roads.surfaces', paint: { 'fill-color': '#989088' } });
	});

	it('paints a Clay style with the Clay paints, and has no ground source', () => {
		const clay = buildStyle(built, 'http://x', false, 'clay', { contributions: ALL });
		expect(clay.layers.find((l) => l.id === 'surfaces-fill')).toMatchObject({ paint: { 'fill-color': '#F8F4EC' } });
		expect(Object.keys(clay.sources)).not.toContain('ground');
		expect(Object.keys(clay.sources)).not.toContain('groundDetail');
		expect(clay.layers.map((l) => l.id)).not.toContain('ground-paint');
		// Valley-only layers are in the style, hidden, so the flavors build the same layers.
		expect(visibility(clay as never, 'water-fill')).toBe('none');
		expect(clay.layers.map((l) => l.id)).toEqual(buildStyle(built, 'http://x', false, 'valley', { contributions: ALL }).layers.map((l) => l.id));
	});

	it('adds the painted ground on the first use of Valley, under the ground anchor, once', () => {
		const style = buildStyle(built, 'http://x', false, 'clay', { contributions: ALL });
		const map = syncMap(style);
		syncContributions(map, built, 'http://x', null, state('clay'), ALL);
		expect(map.getLayer('ground-paint')).toBeUndefined();
		expect(map.sources.ground).toBeUndefined();
		syncContributions(map, built, 'http://x', null, state('valley'), ALL);
		const ids = map.getLayersOrder();
		expect(map.sources.ground).toMatchObject({ type: 'raster', url: 'pmtiles://http://x/tiles/ground-1.pmtiles', tileSize: 512 });
		expect(map.sources.groundDetail).toMatchObject({ type: 'raster', url: 'pmtiles://http://x/tiles/ground-detail-1.pmtiles' });
		expect(ids.indexOf('ground-paint')).toBeLessThan(ids.indexOf('ground-detail'));
		expect(ids.indexOf('ground-detail')).toBe(ids.indexOf(ANCHORS.ground) - 1);
		expect(map.getLayer('ground-detail')).toMatchObject({ source: 'groundDetail', minzoom: 16 });
		const count = ids.length;
		syncContributions(map, built, 'http://x', null, state('valley'), ALL);
		expect(map.getLayersOrder()).toHaveLength(count);
		// Under Aerial the ground hides (the photo replaces it), and it is hidden again in Clay.
		syncContributions(map, built, 'http://x', null, state('valley', { aerial: true }), ALL);
		expect(visibility(map, 'ground-paint')).toBe('none');
		syncContributions(map, built, 'http://x', null, state('valley'), ALL);
		expect(visibility(map, 'ground-paint')).toBe('visible');
		syncContributions(map, built, 'http://x', null, state('clay'), ALL);
		expect(visibility(map, 'ground-paint')).toBe('none');
	});

	it('adds a toggled layer’s tiles once /api/meta has a version, with the build’s credit', () => {
		const map = syncMap(buildStyle(built, 'http://x', false, 'valley', { contributions: ALL }));
		syncContributions(map, built, 'http://x', metaWith({}), state('valley'), ALL);
		expect(map.getLayer('scars-fill')).toBeUndefined();
		syncContributions(map, built, 'http://x', metaWith({ 'fire.scars': 'v7' }), state('valley'), ALL);
		expect(map.sources['fire.scars']).toEqual({
			type: 'vector',
			tiles: ['http://x/api/fire/tiles/scars/{z}/{x}/{y}?v=v7'],
			minzoom: 8,
			maxzoom: 15,
			attribution: '© Fire Atlas'
		});
		const ids = map.getLayersOrder();
		expect(ids.indexOf('scars-fill')).toBeLessThan(ids.indexOf(ANCHORS.areas));
		expect(ids.indexOf('scars-fill')).toBeGreaterThan(ids.indexOf('landcover'));
	});

	it('hides Valley-only layers in Clay, runs `show`, and hides the basemap groups only while shown', () => {
		const map = syncMap(buildStyle(built, 'http://x', false, 'valley', { contributions: ALL }));
		const sync = (st: ReturnType<typeof state>) => syncContributions(map, built, 'http://x', null, st, ALL);
		sync(state('valley'));
		expect(visibility(map, 'water-fill')).toBe('visible');
		expect(visibility(map, 'water')).toBe('none');
		expect(visibility(map, 'water_label_lakes')).toBe('none');
		sync(state('clay'));
		// Clay: the water contribution is hidden and Protomaps' water is back.
		expect(visibility(map, 'water-fill')).toBe('none');
		expect(visibility(map, 'water')).not.toBe('none');
		expect(visibility(map, 'water_label_lakes')).not.toBe('none');
		// Surfaces stay in Clay, with their markings only while Lanes is on.
		expect(visibility(map, 'surfaces-fill')).toBe('visible');
		expect(visibility(map, 'surfaces-marks')).toBe('none');
		sync(state('clay', { layers: ['lanes'] }));
		expect(visibility(map, 'surfaces-marks')).toBe('visible');
		// Aerial hides the surfaces.
		sync(state('valley', { aerial: true }));
		expect(visibility(map, 'surfaces-fill')).toBe('none');
	});

	it('counts the owners that hide a basemap layer, with an optional zoom', () => {
		const map = syncMap(buildStyle(manifest, 'http://x'));
		suppressGroups(map, 'a', ['service']);
		suppressGroups(map, 'b', ['roads'], 14);
		suppressGroups(map, 'c', ['roads']);
		expect(visibility(map, 'roads_minor_service')).toBe('none');
		expect(visibility(map, 'roads_minor')).toBe('none');
		releaseGroups(map, 'c');
		// b alone: the roads draw below z14 only, the service roads are still a's.
		expect(visibility(map, 'roads_minor')).not.toBe('none');
		expect(map.layers.find((l) => l.id === 'roads_minor')).toMatchObject({ maxzoom: 14 });
		expect(visibility(map, 'roads_minor_service')).toBe('none');
		releaseGroups(map, 'a');
		expect(visibility(map, 'roads_minor_service')).not.toBe('none');
		expect(map.layers.find((l) => l.id === 'roads_minor_service')).toMatchObject({ maxzoom: 14 });
		releaseGroups(map, 'b');
		expect(visibility(map, 'roads_minor')).not.toBe('none');
		// The layer’s own zoom range comes back (the basemap's buildings aside, none of these had one).
		expect(map.layers.find((l) => l.id === 'roads_minor')?.maxzoom).toBeGreaterThanOrEqual(24);
		// Asking again with the same groups does nothing; letting go of something never held is fine.
		suppressGroups(map, 'a', ['paths']);
		suppressGroups(map, 'a', ['paths']);
		releaseGroups(map, 'nobody');
		releaseGroups(map, 'a');
		expect(visibility(map, 'roads_other')).not.toBe('none');
	});

	it('hides nothing until a contribution is built, and a layer’s own hidden state is kept', () => {
		const style = buildStyle(manifest, 'http://x', false, 'valley', { contributions: ALL });
		const map = syncMap(style);
		(map.layers.find((l) => l.id === 'roads_minor') as { layout?: unknown }).layout = { visibility: 'none' };
		suppressGroups(map, 'a', ['roads']);
		releaseGroups(map, 'a');
		expect(visibility(map, 'roads_minor')).toBe('none');
		syncContributions(map, manifest, 'http://x', null, state('valley'), ALL);
		expect(visibility(map, 'water')).not.toBe('none');
	});
});
