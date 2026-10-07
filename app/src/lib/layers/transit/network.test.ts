import { describe, expect, it } from 'vitest';
import { createPropertyExpression, latest, validateStyleMin } from '@maplibre/maplibre-gl-style-spec';
import type { TransitNetwork } from '#lib/contracts/network.js';
import {
	bundlePx,
	capsuleLength,
	idleStops,
	L,
	networkLayers,
	offsetPx,
	parseShield,
	ribbonColor,
	ribbonFeatures,
	ribbonOffset,
	ribbonWidth,
	shieldFeatures,
	shieldName,
	stopFeatures,
	widthPx
} from './network.js';

/**
 * docs/14 §14.4 "Drawing": one feature per route per segment with rid, slot
 * and n; the per-zoom table of width, gap and bundle cap; offsets to the
 * right of the digitized direction; ghost colors and 60% width when a route
 * isn't running, all by feature-state.
 */
const route = (id: string, rid: number, color: string, ghost: string) => ({
	id,
	rid,
	shortName: id,
	longName: `Route ${id}`,
	color,
	ghost,
	textColor: '#ffffff',
	halo: false,
	sortOrder: rid
});

const net: TransitNetwork = {
	contract: 1,
	build: 'test',
	bundled: true,
	feedVersion: null,
	routes: [route('40', 1, '#2a78d6', '#b1c6e2'), route('42', 2, '#eb6834', '#f5b59a'), route('45', 3, '#1baf7a', '#a4d2b2')],
	segments: [
		{ id: 7, coords: [-116.3, 43.6, -116.29, 43.6], routes: ['40', '42', '45'], hub: false, lengthM: 800 },
		{ id: 8, coords: [-116.29, 43.6, -116.28, 43.61], routes: ['42'], hub: false, lengthM: 900 },
		{ id: 9, coords: [-116.28, 43.61], routes: ['40'], hub: false, lengthM: 0 }
	],
	stops: [
		{ id: 's1', name: 'Fairview & Five Mile', lon: -116.295, lat: 43.6, routes: ['40', '42'], segment: 7, n: 3, bearing: 90 },
		{ id: 's2', name: null, lon: -116.285, lat: 43.605, routes: ['42'], segment: null, n: 1, bearing: null }
	],
	hubs: [],
	dormant: []
};

/** Evaluate a paint expression the way MapLibre would. */
function evaluate(prop: 'line-width' | 'line-offset' | 'line-color', expr: unknown, zoom: number, props: Record<string, unknown>, state: Record<string, unknown> = {}) {
	// The reference is a JSON module: its default export under some bundlers.
	const ref = latest as unknown as Record<string, Record<string, unknown>> & { default?: Record<string, Record<string, unknown>> };
	const spec = (ref.paint_line ?? ref.default!.paint_line)[prop];
	const parsed = createPropertyExpression(expr, `layers[0].paint.${prop}`, spec as never);
	if (parsed.result !== 'success') throw new Error(JSON.stringify(parsed.value));
	const v = parsed.value.evaluate({ zoom }, { type: 'LineString', properties: props } as never, state);
	return v;
}

describe('ribbon features', () => {
	const fc = ribbonFeatures(net);

	it('expands each segment into one feature per route, left to right', () => {
		const seg7 = fc.features.filter((f) => f.properties.seg === 7);
		expect(seg7.map((f) => [f.properties.routeId, f.properties.slot, f.properties.n, f.properties.rid])).toEqual([
			['40', 0, 3, 1],
			['42', 1, 3, 2],
			['45', 2, 3, 3]
		]);
		// All of a segment's features share its geometry.
		expect(seg7[0].geometry).toBe(seg7[2].geometry);
		expect(seg7[0].geometry.coordinates).toEqual([
			[-116.3, 43.6],
			[-116.29, 43.6]
		]);
		// A degenerate segment is skipped.
		expect(fc.features.some((f) => f.properties.seg === 9)).toBe(false);
		expect(fc.features).toHaveLength(4);
	});

	it('offsets slots symmetrically, positive to the right, by the per-zoom pitch', () => {
		const props = (slot: number, n: number) => ({ slot, n });
		for (const [z, pitch] of [
			[10, 1.5],
			[14, 4.5],
			[18, 8.5]
		] as const) {
			expect(evaluate('line-offset', ribbonOffset(), z, props(0, 3))).toBeCloseTo(-pitch, 6);
			expect(evaluate('line-offset', ribbonOffset(), z, props(1, 3))).toBeCloseTo(0, 6);
			expect(evaluate('line-offset', ribbonOffset(), z, props(2, 3))).toBeCloseTo(pitch, 6);
			expect(offsetPx(z, 2, 3)).toBeCloseTo(pitch, 6);
		}
		// A big bundle is capped at B: 12 routes at z14 share 18 px.
		expect(evaluate('line-offset', ribbonOffset(), 14, props(11, 12))).toBeCloseTo(5.5 * 1.5, 6);
		expect(bundlePx(14, 12, 0)).toBeCloseTo(18, 6);
	});

	it('draws running routes at full width and the rest at 60%, wider when selected or hovered', () => {
		const p = { slot: 0, n: 3 };
		const w14 = 4.5 * (3.5 / 4.5);
		expect(evaluate('line-width', ribbonWidth(), 14, p, { active: true })).toBeCloseTo(w14, 6);
		expect(evaluate('line-width', ribbonWidth(), 14, p, {})).toBeCloseTo(w14 * 0.6, 6);
		expect(evaluate('line-width', ribbonWidth(), 14, p, { spot: true })).toBeCloseTo(w14 * 1.3, 6);
		expect(evaluate('line-width', ribbonWidth(), 14, p, { active: true, hover: true })).toBeCloseTo(w14 + 2, 6);
		expect(widthPx(14, 3)).toBeCloseTo(w14, 6);
		// Never thinner than 1 px.
		expect(evaluate('line-width', ribbonWidth(), 10, { slot: 0, n: 12 }, {})).toBe(1);
	});

	it('colors by feature-state: running → color, not running → ghost, spotlight and dim', () => {
		const p = { color: '#2a78d6', ghost: '#b1c6e2' };
		const hex = (c: { r: number; g: number; b: number }) =>
			'#' + [c.r, c.g, c.b].map((x) => Math.round(x * 255).toString(16).padStart(2, '0')).join('');
		const color = (state: Record<string, unknown>) => hex(evaluate('line-color', ribbonColor(), 14, p, state) as never);
		expect(color({ active: true })).toBe('#2a78d6');
		expect(color({})).toBe('#b1c6e2');
		expect(color({ active: true, dim: true })).toBe('#b1c6e2');
		expect(color({ spot: true })).toBe('#2a78d6');
	});
});

describe('shields, stops and layers', () => {
	it('names each bundle shield by its routes in slot order and which run', () => {
		const fc = shieldFeatures(net, new Set(['42']));
		expect(fc.features.map((f) => f.properties!.shield)).toEqual([shieldName([1, 2, 3], [false, true, false]), shieldName([2], [true])]);
		expect(parseShield(shieldName([1, 2, 3], [false, true, false]))).toEqual({ rids: [1, 2, 3], running: [false, true, false] });
		expect(parseShield('tvt-capsule:3')).toBeNull();
		expect(parseShield('tvt-shield:1-2:1')).toBeNull();
	});

	it('places stop capsules across the whole bundle, turned to the street, faded where nothing runs', () => {
		const fc = stopFeatures(net);
		expect(fc.features.map((f) => [f.properties.sid, f.properties.n, f.properties.bearing, f.properties.capsule])).toEqual([
			[1, 3, 90, 'tvt-capsule:3'],
			[2, 1, 0, 'tvt-capsule:1']
		]);
		expect(capsuleLength(3)).toBeCloseTo(bundlePx(15, 3), 0);
		expect(idleStops(net, new Set(['45']))).toEqual([true, true]);
		expect(idleStops(net, new Set(['40']))).toEqual([false, true]);
	});

	it('gives valid layers in their slots: the corridor outline and underlay under the ribbons', () => {
		const layers = networkLayers();
		expect(layers.map((l) => [l.layer.id, l.slot])).toEqual([
			[L.outline, 'routes'],
			[L.underlay, 'routes'],
			[L.routes, 'routes'],
			[L.trails, 'routes'],
			[L.stops, 'points'],
			[L.hubs, 'points'],
			[L.shields, 'labels']
		]);
		const sources = Object.fromEntries(
			['transit-ribbons', 'transit-shields', 'transit-stops', 'transit-hubs', 'transit-trails'].map((id) => [id, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } }])
		);
		const errors = validateStyleMin({ version: 8, glyphs: 'https://example.com/{fontstack}/{range}.pbf', sources, layers: layers.map((l) => l.layer) } as never);
		expect(errors.map((e: { message: string }) => e.message)).toEqual([]);
	});
});
