import { afterEach, beforeAll, describe, expect, it } from 'vitest';
import type { HillshadeLayerSpecification, RasterDEMSourceSpecification } from 'maplibre-gl';
import { DEFAULT_FLAGS, DEFAULT_HILLSHADE, parsePerfFlags } from '#lib/perf/flags.js';
import {
	basemapReady,
	buildStyle,
	flavorLayers,
	HILLSHADE_CAP_ZOOM,
	HILLSHADE_LAYER,
	HILLSHADE_SOURCE,
	hillshadeMode,
	setHillshadeMode,
	TERRAIN_SOURCE,
	terrainSources,
	type BasemapManifest
} from './style.js';

beforeAll(() => basemapReady);
afterEach(() => setHillshadeMode(DEFAULT_HILLSHADE));

const manifest: BasemapManifest = {
	bounds: [-117.05, 43, -115.95, 43.85],
	center: [-116.4, 43.6],
	zoom: 10,
	basemap: { file: 'valley.pmtiles', flavor: 'light', attribution: 'OSM', built: '2026-10-05' },
	glyphs: 'fonts/{fontstack}/{range}.pbf',
	sprite: 'sprites/v4/light',
	terrain: { file: 'terrain.pmtiles', encoding: 'mapbox', tileSize: 512, exaggeration: 1.3, attribution: 'USGS 3DEP', built: '2026-10-05' }
};

const dems = (s: ReturnType<typeof buildStyle>) =>
	Object.entries(s.sources).filter(([, v]) => v.type === 'raster-dem') as [string, RasterDEMSourceSpecification][];
const hillshadeOf = (s: ReturnType<typeof buildStyle>) => s.layers.find((l) => l.id === HILLSHADE_LAYER) as HillshadeLayerSpecification;

describe('hillshade sources (docs/14 §14.9 fix 1, Q7)', () => {
	it('by default draws the hillshade from the 3D terrain source: one DEM source', () => {
		expect(hillshadeMode()).toBe('terrain');
		const s = buildStyle(manifest, 'https://example.test');
		expect(dems(s).map(([id]) => id)).toEqual([TERRAIN_SOURCE]);
		expect(s.terrain?.source).toBe(TERRAIN_SOURCE);
		expect(hillshadeOf(s).source).toBe(TERRAIN_SOURCE);
		expect(dems(s)[0][1]).toMatchObject({ url: 'pmtiles://https://example.test/tiles/terrain.pmtiles', encoding: 'mapbox', tileSize: 512 });
		expect(dems(s)[0][1].maxzoom).toBeUndefined();
	});

	it('with ?hillshade=capped keeps a second source for it, capped at z12', () => {
		setHillshadeMode('capped');
		const s = buildStyle(manifest, 'https://example.test');
		expect(dems(s).map(([id]) => id).sort()).toEqual([HILLSHADE_SOURCE, TERRAIN_SOURCE].sort());
		expect(s.terrain?.source).toBe(TERRAIN_SOURCE);
		expect(hillshadeOf(s).source).toBe(HILLSHADE_SOURCE);
		const hs = s.sources[HILLSHADE_SOURCE] as RasterDEMSourceSpecification;
		expect(hs.maxzoom).toBe(HILLSHADE_CAP_ZOOM);
		expect(HILLSHADE_CAP_ZOOM).toBe(12);
		// Same file and encoding as the terrain; the terrain itself is uncapped.
		expect(hs.url).toBe((s.sources[TERRAIN_SOURCE] as RasterDEMSourceSpecification).url);
		expect((s.sources[TERRAIN_SOURCE] as RasterDEMSourceSpecification).maxzoom).toBeUndefined();
	});

	it('keeps the layer order and the flavor paint whichever source it uses', () => {
		const one = buildStyle(manifest, '');
		setHillshadeMode('capped');
		const two = buildStyle(manifest, '');
		expect(two.layers.map((l) => l.id)).toEqual(one.layers.map((l) => l.id));
		expect(hillshadeOf(two).paint).toEqual(hillshadeOf(one).paint);
		// The flavor diff is about paint only, so it's the same in both modes.
		expect(flavorLayers(manifest, 'clay').map((l) => l.id)).toEqual(one.layers.map((l) => l.id));
	});

	it('has no DEM source without terrain', () => {
		const { terrain: _t, ...flat } = manifest;
		expect(terrainSources(flat, '').sources).toEqual({});
		setHillshadeMode('capped');
		expect(dems(buildStyle(flat, ''))).toEqual([]);
		expect(buildStyle(flat, '').layers.some((l) => l.id === HILLSHADE_LAYER)).toBe(false);
	});
});

describe('perf flags', () => {
	it('reads ?hillshade=, ?workers=, ?lod= and ?perf, with safe defaults', () => {
		expect(parsePerfFlags('')).toEqual(DEFAULT_FLAGS);
		expect(DEFAULT_FLAGS.hillshade).toBe('terrain');
		expect(parsePerfFlags('?hillshade=capped').hillshade).toBe('capped');
		expect(parsePerfFlags('?hillshade=terrain').hillshade).toBe('terrain');
		expect(parsePerfFlags('?hillshade=bogus').hillshade).toBe('terrain');
		expect(parsePerfFlags('?workers=2').workers).toBe(2);
		for (const w of ['0', '9', '1.5', 'x', '']) expect(parsePerfFlags(`?workers=${w}`).workers).toBeNull();
		expect(parsePerfFlags('?lod=4,1.5').lod).toEqual([4, 1.5]);
		for (const l of ['4', '4,x', '0,3', '4,3,2']) expect(parsePerfFlags(`?lod=${l}`).lod).toBeNull();
		expect(parsePerfFlags('?perf').hud).toBe(true);
		expect(parsePerfFlags('?perf=1').hud).toBe(true);
		expect(parsePerfFlags('?perf=0').hud).toBe(false);
		expect(parsePerfFlags(new URLSearchParams('hillshade=capped&workers=3&perf'))).toEqual({ hillshade: 'capped', workers: 3, lod: null, hud: true });
	});
});
