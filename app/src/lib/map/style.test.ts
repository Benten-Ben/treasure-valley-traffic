import { beforeAll, describe, expect, it } from 'vitest';
import type { LayerSpecification } from 'maplibre-gl';
import { ANCHOR_IDS, ANCHORS } from './order.js';
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
	setAerial,
	type BasemapManifest,
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
