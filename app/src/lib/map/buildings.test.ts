import { createPropertyExpression, featureFilter, latest, validateStyleMin } from '@maplibre/maplibre-gl-style-spec';
import type { FillExtrusionLayerSpecification, FilterSpecification, LayerSpecification } from 'maplibre-gl';
import { beforeAll, describe, expect, it } from 'vitest';
import { BUILDING_BASE, BUILDING_HEIGHT, DEFAULT_HEIGHT_M, ESTIMATED_FILTER, FLOOR_HEIGHT_M, MEASURED_FILTER, MIN_HEIGHT_M } from './buildings.js';
import { deltaE, oklch } from './color.js';
import { BUILDINGS_PAINT, ESTIMATED_BUILDINGS_PAINT, FLAVOR_NAMES } from './flavors.js';
import { ANCHORS } from './order.js';
import { basemapReady, BUILDINGS_ESTIMATED_LAYER, BUILDINGS_LAYER, BUILDINGS_LAYERS, buildingOpacity, buildStyle, type BasemapManifest } from './style.js';

beforeAll(() => basemapReady);

const manifest: BasemapManifest = {
	bounds: [-117.05, 43, -115.95, 43.85],
	center: [-116.4, 43.6],
	zoom: 10,
	basemap: { file: 'valley.pmtiles', flavor: 'light', attribution: 'OSM', built: '2026-10-05' },
	glyphs: 'fonts/{fontstack}/{range}.pbf',
	sprite: 'sprites/v4/light',
	buildings: { file: 'buildings.pmtiles', sourceLayer: 'buildings', minzoom: 14, attribution: 'Overture', built: '2026-10-05' },
	imagery: { file: 'imagery.pmtiles', tileSize: 512, maxzoom: 14, attribution: 'USDA NAIP', built: '2026-10-05' }
};

/** A building's properties as the tiles carry them (basemap/buildings.py; a missing value is absent). */
type Props = { height?: unknown; num_floors?: unknown; min_height?: unknown };

const PAINT_SPEC = (latest as unknown as Record<string, Record<string, Parameters<typeof createPropertyExpression>[2]>>)['paint_fill-extrusion'];

/** A paint expression evaluated for one building, as MapLibre's style spec evaluates it. */
function evaluate(property: 'fill-extrusion-height' | 'fill-extrusion-base', expression: unknown, props: Props): number {
	const parsed = createPropertyExpression(expression, property, PAINT_SPEC[property]);
	if (parsed.result !== 'success') throw new Error(parsed.value.map((e) => e.message).join('; '));
	return parsed.value.evaluate({ zoom: 15 }, { type: 'Polygon', properties: props }) as number;
}

const matches = (filter: FilterSpecification, props: Props) => featureFilter(filter, 'filter').filter({ zoom: 15 }, { type: 'Polygon', properties: props });

/** How each kind of building is drawn: height, base, and whether it's an estimate (the lighter layer). */
const CASES: { why: string; props: Props; height: number; base: number; estimated: boolean }[] = [
	{ why: 'a measured height, as it is', props: { height: 12.5 }, height: 12.5, base: 0, estimated: false },
	{ why: 'a measured height under 3 m: the minimum', props: { height: 2.1 }, height: 3, base: 0, estimated: false },
	{ why: 'a measured height wins over floors', props: { height: 9, num_floors: 5 }, height: 9, base: 0, estimated: false },
	{ why: 'no height and no floors: 4 m', props: {}, height: 4, base: 0, estimated: true },
	{ why: 'no height, 2 floors: 2 × 3.2 m', props: { num_floors: 2 }, height: 6.4, base: 0, estimated: true },
	{ why: 'no height, 17 floors: 17 × 3.2 m', props: { num_floors: 17 }, height: 54.4, base: 0, estimated: true },
	{ why: 'no height, 1 floor: 3.2 m, above the minimum', props: { num_floors: 1 }, height: 3.2, base: 0, estimated: true },
	{ why: 'no height, 0 floors: as if no floors', props: { num_floors: 0 }, height: 4, base: 0, estimated: true },
	{ why: 'a height of 0 m is no measurement: estimated', props: { height: 0 }, height: 4, base: 0, estimated: true },
	{ why: 'a height of 0 m with floors: from the floors', props: { height: 0, num_floors: 3 }, height: 9.6, base: 0, estimated: true },
	{ why: 'a negative height: estimated', props: { height: -2 }, height: 4, base: 0, estimated: true },
	{ why: 'a height that is not a number: estimated', props: { height: 'tall' }, height: 4, base: 0, estimated: true },
	{ why: 'a number written as text is read as one', props: { height: '12' }, height: 12, base: 0, estimated: false },
	{ why: 'a null height (GeoJSON can carry one): estimated', props: { height: null }, height: 4, base: 0, estimated: true },
	{ why: 'floors that are not a number: the default', props: { num_floors: 'two' }, height: 4, base: 0, estimated: true },
	{ why: 'a min_height that is not a number: from the ground', props: { height: 8, min_height: 'x' }, height: 8, base: 0, estimated: false },
	{ why: 'min_height is the base', props: { height: 5, min_height: 3 }, height: 5, base: 3, estimated: false },
	{ why: 'a raised part under 3 m keeps its base and gets the minimum top', props: { height: 2.5, min_height: 2.2 }, height: 3, base: 2.2, estimated: false },
	{ why: 'the base never goes above the drawn top', props: { height: 4, min_height: 6 }, height: 4, base: 4, estimated: false }
];

describe('the building height floor (owner, Oct 7)', () => {
	it('uses the approved numbers: 4 m when unknown, 3.2 m a floor, 3 m at least', () => {
		expect([DEFAULT_HEIGHT_M, FLOOR_HEIGHT_M, MIN_HEIGHT_M]).toEqual([4, 3.2, 3]);
	});

	for (const c of CASES) {
		it(`${c.why}: ${JSON.stringify(c.props)} → ${c.height} m${c.base ? ` from ${c.base} m` : ''}, ${c.estimated ? 'estimated' : 'measured'}`, () => {
			expect(evaluate('fill-extrusion-height', BUILDING_HEIGHT, c.props)).toBeCloseTo(c.height, 9);
			expect(evaluate('fill-extrusion-base', BUILDING_BASE, c.props)).toBeCloseTo(c.base, 9);
			// Exactly one layer draws it: the measured one, or the lighter estimated one.
			expect(matches(MEASURED_FILTER, c.props)).toBe(!c.estimated);
			expect(matches(ESTIMATED_FILTER, c.props)).toBe(c.estimated);
		});
	}

	it('every building is drawn at least 3 m tall', () => {
		for (const height of [0.5, 2.99, 3, 3.01]) expect(evaluate('fill-extrusion-height', BUILDING_HEIGHT, { height })).toBe(Math.max(MIN_HEIGHT_M, height));
		for (const height of [-1, 0, null, '', 'x']) expect(evaluate('fill-extrusion-height', BUILDING_HEIGHT, { height })).toBe(DEFAULT_HEIGHT_M);
		for (const num_floors of [-1, 0, 0.5, 1, 'x']) expect(evaluate('fill-extrusion-height', BUILDING_HEIGHT, { num_floors })).toBeGreaterThanOrEqual(MIN_HEIGHT_M);
	});
});

const buildingLayers = (aerial: boolean, flavor: (typeof FLAVOR_NAMES)[number]) =>
	buildStyle(manifest, 'http://x', aerial, flavor).layers.filter((l) => BUILDINGS_LAYERS.includes(l.id)) as FillExtrusionLayerSpecification[];

describe('the 3D building layers', () => {
	it('draws measured and estimated buildings as two layers of the same tiles, next to each other in the buildings slot', () => {
		const style = buildStyle(manifest, 'http://x');
		const ids = style.layers.map((l) => l.id);
		expect(BUILDINGS_LAYERS).toEqual([BUILDINGS_LAYER, BUILDINGS_ESTIMATED_LAYER]);
		const [measured, estimated] = buildingLayers(false, 'valley');
		expect([measured.id, estimated.id]).toEqual([BUILDINGS_LAYER, BUILDINGS_ESTIMATED_LAYER]);
		expect(ids.indexOf(BUILDINGS_ESTIMATED_LAYER)).toBe(ids.indexOf(BUILDINGS_LAYER) + 1);
		expect(ids.indexOf(BUILDINGS_LAYER)).toBeGreaterThan(ids.indexOf(ANCHORS.routes));
		expect(ids.indexOf(BUILDINGS_ESTIMATED_LAYER)).toBeLessThan(ids.indexOf(ANCHORS.scene));
		for (const l of [measured, estimated]) {
			expect(l).toMatchObject({ type: 'fill-extrusion', source: 'buildings', 'source-layer': 'buildings', minzoom: 14 });
			expect(l.paint).toMatchObject({ 'fill-extrusion-height': BUILDING_HEIGHT, 'fill-extrusion-base': BUILDING_BASE, 'fill-extrusion-vertical-gradient': true });
		}
		expect([measured.filter, estimated.filter]).toEqual([MEASURED_FILTER, ESTIMATED_FILTER]);
		// Valid by MapLibre's style spec, expressions and filters included.
		const errors = validateStyleMin({ version: 8, sources: { buildings: style.sources.buildings }, layers: [measured, estimated] as LayerSpecification[] });
		expect(errors.map((e) => e.message)).toEqual([]);
	});

	it('paints estimates a slightly lighter tone in both flavors, with the same opacity, Aerial included', () => {
		for (const flavor of FLAVOR_NAMES) {
			for (const aerial of [false, true]) {
				const [measured, estimated] = buildingLayers(aerial, flavor);
				expect(measured.paint?.['fill-extrusion-color']).toBe(BUILDINGS_PAINT[flavor].color);
				expect(estimated.paint?.['fill-extrusion-color']).toBe(ESTIMATED_BUILDINGS_PAINT[flavor].color);
				for (const l of [measured, estimated]) expect(l.paint?.['fill-extrusion-opacity']).toBe(buildingOpacity(aerial, flavor));
			}
			expect(ESTIMATED_BUILDINGS_PAINT[flavor].opacity).toBe(BUILDINGS_PAINT[flavor].opacity);
			// Lighter, and only slightly: ΔE 3.3–3.4 (OKLab ×100), a step the eye catches side by side.
			const m = BUILDINGS_PAINT[flavor].color;
			const e = ESTIMATED_BUILDINGS_PAINT[flavor].color;
			expect(oklch(e).L, flavor).toBeGreaterThan(oklch(m).L);
			expect(deltaE(m, e), flavor).toBeGreaterThan(3);
			expect(deltaE(m, e), flavor).toBeLessThan(3.5);
		}
	});

	it('without buildings in the manifest, there are no building layers', () => {
		const style = buildStyle({ ...manifest, buildings: undefined }, 'http://x');
		expect(style.layers.filter((l) => BUILDINGS_LAYERS.includes(l.id))).toEqual([]);
		expect(style.sources.buildings).toBeUndefined();
	});
});
