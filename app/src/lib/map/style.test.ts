import { describe, expect, it } from 'vitest';
import type { LayerSpecification } from 'maplibre-gl';
import {
	addAerial,
	aerialAfter,
	BUILDINGS_LAYER,
	buildingOpacity,
	buildStyle,
	firstBasemapLabel,
	IMAGERY_LAYERS,
	setAerial,
	type BasemapManifest,
	type MapLike
} from './style.js';

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
		expect(on.layers.find((l) => l.id === BUILDINGS_LAYER)?.paint).toMatchObject({ 'fill-extrusion-opacity': buildingOpacity(true) });
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
		expect(map.getLayer(BUILDINGS_LAYER)?.paint).toMatchObject({ 'fill-extrusion-opacity': buildingOpacity(true) });
		expect(setAerial(map, manifest, 'http://x', false)).toBe(false);
		for (const id of IMAGERY_LAYERS) expect(map.getLayer(id)?.layout).toMatchObject({ visibility: 'none' });
		expect(map.getLayer(BUILDINGS_LAYER)?.paint).toMatchObject({ 'fill-extrusion-opacity': buildingOpacity(false) });
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
		const firstLabel = style.layers.findIndex((l) => l.type === 'symbol');
		expect(aerialAfter(m)).toBe(style.layers[firstLabel - 1 - (m.buildings ? 1 : 0)].id);
	});

	it('finds the basemap’s first label', () => {
		const style = buildStyle(manifest, 'http://x');
		const map = fakeMap(style.layers, { ...style.sources });
		const id = firstBasemapLabel(map)!;
		expect(map.getLayer(id)?.type).toBe('symbol');
		expect(style.layers.findIndex((l) => l.id === id)).toBe(style.layers.findIndex((l) => l.type === 'symbol'));
	});
});
