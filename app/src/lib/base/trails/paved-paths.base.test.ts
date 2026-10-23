import { readFileSync } from 'node:fs';
import { validateStyleMin } from '@maplibre/maplibre-gl-style-spec';
import { beforeAll, describe, expect, it } from 'vitest';
import { DRAPED_TYPES } from '#lib/map/order.js';
import { contributionLayer, contributionStatus } from '#lib/map/flavors.js';
import { ASPHALT, CONCRETE, CURB } from '#lib/map/materials.js';
import { basemapReady, buildStyle, type BasemapManifest } from '#lib/map/style.js';
import { BASE_CONTRIBUTIONS, baseContribution } from '../registry.js';
import type { BaseState } from '../types.js';
import paved from './paved-paths.base.js';
import { metresPerPx, PAVED_FROM_ZOOM, PAVED_ID, PAVED_LAYER, PAVED_RANK, PAVED_SOURCE_LAYERS } from './paved.js';

/**
 * The paved-path base contribution (paved-paths.base.ts; plan C9): found by the registry, in
 * `anchor:surfaces` at rank 15 from z15.5, both looks, in the materials' tones, hidden under Aerial,
 * built only when the landscape file holds both of its source-layers, and clickable only while Trails is on.
 */

beforeAll(() => basemapReady);

const state = (o: Partial<BaseState> = {}): BaseState => ({ flavor: 'valley', aerial: false, layers: new Set(), ...o });

const manifest = (layers: string[], empty: string[] = []): BasemapManifest =>
	({
		bounds: [-117.05, 43, -115.95, 43.85],
		center: [-116.4, 43.6],
		zoom: 10,
		basemap: { file: 'valley.pmtiles', flavor: 'light', attribution: 'OSM', built: '2026-10-05' },
		glyphs: 'fonts/{fontstack}/{range}.pbf',
		sprite: 'sprites/v4/light',
		landscape: {
			status: 'baked',
			file: 'landscape-1.pmtiles',
			digest: '1',
			format: 'pbf',
			minzoom: 8,
			maxzoom: 16,
			promoteId: 'id',
			layers: Object.fromEntries(layers.map((n) => [n, { plugin: 'trails', layer: n, build: 'b', geometry: 'LineString', features: 1, fields: {}, minzoom: 15, maxzoom: 16, licence: 'ODbL-1.0', republish: 'yes', credit: [] }])),
			empty,
			attribution: '© OpenStreetMap contributors',
			licences: ['ODbL-1.0'],
			republish: 'yes',
			access: 'tailnet',
			inputs: [],
			built: '2026-10-22',
			spec: 1,
			previous: null
		}
	}) as unknown as BasemapManifest;

describe('the paved-path base contribution', () => {
	it('is found by the registry, under its id', () => {
		expect(BASE_CONTRIBUTIONS).toContain(paved);
		expect(baseContribution(PAVED_ID)).toBe(paved);
		expect(paved.id).toMatch(/^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$/);
	});

	it('reads the source-layers trails-export writes, from the landscape file', () => {
		const exporter = readFileSync(new URL('../../../../../plugins/trails/ingest/export.py', import.meta.url), 'utf8');
		expect(exporter).toContain('`paved_paths`');
		expect(exporter).toContain('`paved_areas`');
		expect(paved.source).toEqual({ kind: 'landscape', sourceLayers: ['trails.paved_paths', 'trails.paved_areas'] });
		expect(PAVED_SOURCE_LAYERS).toEqual({ paths: 'trails.paved_paths', areas: 'trails.paved_areas' });
		expect(paved.credit).toBe('© OpenStreetMap contributors');
	});

	it('puts the treads and areas in the surfaces slot at rank 15, drawn from z15.5, as draped types', () => {
		expect(paved.layers.map((l) => l.id)).toEqual([PAVED_LAYER.areas, PAVED_LAYER.treads]);
		for (const l of paved.layers) {
			expect(l.slot).toBe('surfaces');
			expect(l.rank).toBe(PAVED_RANK);
			expect(l.rank).toBe(15);
			expect(l.minzoom).toBe(15.5);
			expect(DRAPED_TYPES.has(l.type), l.id).toBe(true);
			expect(l.aerial, 'hidden under Aerial like the other surfaces').toBe('hide');
		}
		expect(PAVED_FROM_ZOOM).toBe(15.5);
		expect(paved.layers.find((l) => l.id === PAVED_LAYER.areas)!.type).toBe('fill');
		expect(paved.layers.find((l) => l.id === PAVED_LAYER.treads)!.type).toBe('line');
	});

	it('is in both looks, in the materials’ tones: asphalt, concrete, and the curb tone for paving stones in Valley', () => {
		expect(paved.looks).toBe('both');
		for (const l of paved.layers) {
			const color = (p: Record<string, unknown>) => p[l.type === 'fill' ? 'fill-color' : 'line-color'] as unknown[];
			expect(color(l.valley)).toEqual(['match', ['get', 'material'], 'asphalt', ASPHALT.valley, 'concrete', CONCRETE.valley, 'paving_stones', CURB, CONCRETE.valley]);
			expect(color(l.clay!)).toEqual(['match', ['get', 'material'], 'asphalt', ASPHALT.clay, 'concrete', CONCRETE.clay, 'paving_stones', CONCRETE.clay, CONCRETE.clay]);
		}
	});

	it('draws a tread at its width in metres, never under a floor', () => {
		const tread = paved.layers.find((l) => l.id === PAVED_LAYER.treads)!;
		const w = tread.valley['line-width'] as unknown[];
		expect(w.slice(0, 3)).toEqual(['interpolate', ['exponential', 2], ['zoom']]);
		expect(JSON.stringify(w)).toContain('"w"');
		// 3 m at z18 is 3 / 0.216 = 13.9 px.
		const at18 = (w[6] as unknown[])[2] as unknown[];
		expect(at18[0]).toBe('/');
		expect(at18[2]).toBeCloseTo(metresPerPx(18), 9);
		expect(3 / metresPerPx(18)).toBeCloseTo(13.9, 1);
		expect(tread.clay!['line-width']).toEqual(tread.valley['line-width']);
	});

	it('opens a card only while Trails is on, and credits OpenStreetMap', () => {
		expect(paved.cardsWhen).toBe('trails');
	});

	it('is built only when the landscape file holds both source-layers, with features', () => {
		expect(contributionStatus(paved, manifest(['trails.paved_paths', 'trails.paved_areas']))).toEqual({ built: true });
		expect(contributionStatus(paved, manifest(['trails.paved_paths']))).toMatchObject({ built: false });
		expect(contributionStatus(paved, manifest(['trails.paved_paths', 'trails.paved_areas'], ['trails.paved_areas']))).toMatchObject({ built: false });
		expect(contributionStatus(paved, { ...manifest([]), landscape: undefined } as never)).toMatchObject({ built: false });
	});

	it('makes valid style layers in both looks, in Valley’s and Clay’s paint', () => {
		const m = manifest(['trails.paved_paths', 'trails.paved_areas']);
		for (const flavor of ['valley', 'clay'] as const) {
			const layers = paved.layers.map((l) => contributionLayer(paved, l, state({ flavor })));
			const errors = validateStyleMin({
				version: 8,
				sources: { landscape: { type: 'vector', tiles: ['https://example.com/{z}/{x}/{y}'] } },
				layers
			} as never);
			expect(errors.map((e: { message: string }) => e.message), flavor).toEqual([]);
			expect(layers.every((l) => (l.layout as { visibility: string }).visibility === 'visible'), flavor).toBe(true);
			// Hidden under Aerial.
			const aerial = paved.layers.map((l) => contributionLayer(paved, l, state({ flavor, aerial: true })));
			expect(aerial.every((l) => (l.layout as { visibility: string }).visibility === 'none')).toBe(true);
		}
		// ...and the style puts them in the surfaces slot, before the Protomaps road lines.
		const style = buildStyle(m, 'http://x', false, 'valley', { contributions: [paved] }).layers.map((l) => l.id);
		expect(style.indexOf(PAVED_LAYER.areas)).toBeGreaterThan(style.indexOf('anchor:water'));
		expect(style.indexOf(PAVED_LAYER.treads)).toBeLessThan(style.indexOf('anchor:surfaces'));
		expect(style.indexOf(PAVED_LAYER.areas)).toBeLessThan(style.indexOf('anchor:base'));
	});

	it('imports no scene code: the base layers load with the page', () => {
		const src = readFileSync(new URL('./paved-paths.base.ts', import.meta.url), 'utf8');
		expect(src).not.toMatch(/#lib\/scene|\/scene\//);
		expect(src).not.toMatch(/#lib\/layers\//);
	});
});
