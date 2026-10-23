import { beforeAll, describe, expect, it } from 'vitest';
import type { LayerSpecification } from 'maplibre-gl';
import { DRAPED_TYPES } from '#lib/map/order.js';
import { contributionLayer, contributionStatus, syncContributions, type SyncMap } from '#lib/map/flavors.js';
import { basemapReady, buildStyle, PROTOMAPS_GROUPS, type BasemapManifest } from '#lib/map/style.js';
import { BASE_CONTRIBUTIONS, baseContribution } from '#lib/base/registry.js';
import ground from './ground.base.js';

beforeAll(() => basemapReady);

const manifest: BasemapManifest = {
	bounds: [-117.05, 43, -115.95, 43.85],
	center: [-116.4, 43.6],
	zoom: 10,
	basemap: { file: 'valley.pmtiles', flavor: 'light', attribution: 'OSM', built: '2026-10-05' },
	glyphs: 'fonts/{fontstack}/{range}.pbf',
	sprite: 'sprites/v4/light',
	terrain: { file: 'terrain.pmtiles', encoding: 'mapbox', tileSize: 512, exaggeration: 1.3, attribution: 'USGS 3DEP', built: '2026-10-05' },
	buildings: { file: 'buildings.pmtiles', sourceLayer: 'buildings', minzoom: 14, attribution: 'Overture', built: '2026-10-05' }
};
const painted: NonNullable<BasemapManifest['ground']> = {
	status: 'painted',
	file: 'ground-1.pmtiles',
	tileSize: 512,
	format: 'webp',
	minzoom: 8,
	maxzoom: 15,
	detail: { file: 'ground-detail-1.pmtiles', minzoom: 17, maxzoom: 17, boxes: ['a'] },
	attribution: '© OpenStreetMap contributors',
	licence: 'ODbL-1.0',
	republish: 'yes',
	inputs: [],
	fallbacks: [],
	built: '2026-10-20',
	spec: 1
};
const built: BasemapManifest = { ...manifest, ground: painted };
const flat: BasemapManifest = { ...manifest, ground: { status: 'flat', reason: 'Flat ground: no soils export yet.', built: '2026-10-20', spec: 1 } };

/** A map the base pass can drive. */
function fakeMap(style: { layers: LayerSpecification[]; sources: Record<string, unknown> }) {
	const sources: Record<string, unknown> = { ...style.sources };
	const m: any = {
		layers: [...style.layers],
		sources,
		getLayer: (id: string) => m.layers.find((l: LayerSpecification) => l.id === id),
		getSource: (id: string) => (sources[id] ? { id } : undefined),
		addSource: (id: string, s: unknown) => void (sources[id] = s),
		addLayer: (l: LayerSpecification, before?: string) => {
			const i = before ? m.layers.findIndex((x: LayerSpecification) => x.id === before) : -1;
			if (i === -1) m.layers.push(l);
			else m.layers.splice(i, 0, l);
			return m;
		},
		getLayersOrder: () => m.layers.map((l: LayerSpecification) => l.id),
		setLayoutProperty: (id: string, k: string, v: unknown) => {
			const l = m.getLayer(id);
			l.layout = { ...(l.layout ?? {}), [k]: v };
		},
		getLayoutProperty: (id: string, k: string) => (m.getLayer(id)?.layout ?? {})[k],
		setPaintProperty: (id: string, k: string, v: unknown) => {
			const l = m.getLayer(id);
			l.paint = { ...(l.paint ?? {}), [k]: v };
		},
		setLayerZoomRange: (id: string, min: number, max: number) => {
			const l = m.getLayer(id);
			l.minzoom = min;
			l.maxzoom = max;
		}
	};
	return m as SyncMap & { layers: LayerSpecification[]; sources: Record<string, unknown> };
}
const vis = (m: { layers: LayerSpecification[] }, id: string) => (m.layers.find((l) => l.id === id)?.layout as { visibility?: string } | undefined)?.visibility ?? 'visible';
const state = (flavor: 'valley' | 'clay', aerial = false) => ({ flavor, aerial, layers: new Set<never>() });
const sync = (map: SyncMap, m: BasemapManifest, st: ReturnType<typeof state>) => syncContributions(map, m, 'http://x', null, st, [ground]);

describe('the painted ground contribution', () => {
	it('is registered, well formed, and draped in the ground slot', () => {
		expect(baseContribution(ground.id)).toBe(ground);
		expect(BASE_CONTRIBUTIONS).toContain(ground);
		expect(ground.source).toEqual({ kind: 'ground' });
		expect(ground.looks).toBe('valley');
		expect(ground.layers.map((l) => [l.id, l.slot, l.rank, l.type, l.aerial, l.detail ?? false, l.minzoom ?? null])).toEqual([
			['ground-paint', 'ground', 0, 'raster', 'hide', false, null],
			['ground-detail', 'ground', 5, 'raster', 'hide', true, null]
		]);
		for (const l of ground.layers) expect(DRAPED_TYPES.has(l.type)).toBe(true);
	});

	it('suppresses the whole landcover group, aerodromes, industrial, schools and hospitals included', () => {
		expect(ground.suppresses).toEqual({ groups: ['landcover'] });
		for (const id of ['landuse_aerodrome', 'landuse_industrial', 'landuse_school', 'landuse_hospital', 'landcover'])
			expect(PROTOMAPS_GROUPS.landcover as readonly string[], id).toContain(id);
	});

	it('is built only for a painted entry; flat says why; no entry says it is not built', () => {
		expect(contributionStatus(ground, built)).toEqual({ built: true });
		expect(contributionStatus(ground, flat)).toEqual({ built: false, reason: 'Flat ground: no soils export yet.' });
		expect(contributionStatus(ground, manifest)).toEqual({ built: false, reason: 'not built yet' });
	});

	it('makes no ground request in a Clay first visit: no source, no layer, landcover kept', () => {
		const style = buildStyle(built, 'http://x', false, 'clay');
		expect(Object.keys(style.sources)).not.toContain('ground');
		const map = fakeMap(style);
		expect(sync(map, built, state('clay'))).toEqual([]);
		expect(map.sources.ground).toBeUndefined();
		expect(map.sources.groundDetail).toBeUndefined();
		expect(map.getLayer('ground-paint')).toBeUndefined();
		expect(vis(map, 'landcover')).not.toBe('none');
	});

	it('loads on the first use of Valley: both rasters, under the other fills, landcover hidden', () => {
		const map = fakeMap(buildStyle(built, 'http://x', false, 'clay'));
		sync(map, built, state('clay'));
		expect(map.sources.ground).toBeUndefined();
		expect(sync(map, built, state('valley'))).toEqual([ground.id]);
		expect(map.sources.ground).toMatchObject({ type: 'raster', url: 'pmtiles://http://x/tiles/ground-1.pmtiles', tileSize: 512 });
		expect(map.sources.groundDetail).toMatchObject({ type: 'raster', url: 'pmtiles://http://x/tiles/ground-detail-1.pmtiles' });
		const ids = map.getLayersOrder();
		expect(ids.indexOf('ground-paint')).toBeLessThan(ids.indexOf('ground-detail'));
		expect(ids.indexOf('ground-detail')).toBeLessThan(ids.indexOf('landcover'));
		expect(ids.indexOf('ground-paint')).toBeGreaterThan(ids.indexOf('earth'));
		expect(map.getLayer('ground-paint')).toMatchObject({ source: 'ground', type: 'raster' });
		expect(map.getLayer('ground-detail')).toMatchObject({ source: 'groundDetail', minzoom: 17 });
		// The start zoom is the manifest's, not a copy: a rebuild at z16 moves it.
		const z16 = { ...built, ground: { ...painted, detail: { ...painted.detail, minzoom: 16 } } } as BasemapManifest;
		expect(contributionLayer(ground, ground.layers[1], state('valley'), z16)).toMatchObject({ minzoom: 16 });
		expect(vis(map, 'ground-paint')).toBe('visible');
		for (const id of PROTOMAPS_GROUPS.landcover) if (map.getLayer(id)) expect(vis(map, id), id).toBe('none');
		// Once: asking again adds nothing.
		const count = ids.length;
		sync(map, built, state('valley'));
		expect(map.getLayersOrder()).toHaveLength(count);
	});

	it('hides under Aerial (and gives the fills back) and in Clay, and comes back in Valley', () => {
		const map = fakeMap(buildStyle(built, 'http://x', false, 'valley'));
		sync(map, built, state('valley'));
		sync(map, built, state('valley', true));
		for (const id of ['ground-paint', 'ground-detail']) expect(vis(map, id)).toBe('none');
		expect(vis(map, 'landcover')).not.toBe('none');
		sync(map, built, state('valley'));
		expect(vis(map, 'ground-paint')).toBe('visible');
		expect(vis(map, 'landcover')).toBe('none');
		sync(map, built, state('clay'));
		expect(vis(map, 'ground-paint')).toBe('none');
		expect(vis(map, 'landcover')).not.toBe('none');
	});

	it('flat or missing adds nothing and hides nothing, and puts no other source in its place', () => {
		for (const m of [flat, manifest]) {
			const map = fakeMap(buildStyle(m, 'http://x', false, 'valley'));
			const before = map.getLayersOrder();
			expect(sync(map, m, state('valley'))).toEqual([]);
			expect(map.getLayersOrder()).toEqual(before);
			expect(map.sources.ground).toBeUndefined();
			expect(map.sources.groundDetail).toBeUndefined();
			expect(vis(map, 'landcover')).not.toBe('none');
		}
	});
});
