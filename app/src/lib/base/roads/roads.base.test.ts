import { expression, latest, validateStyleMin } from '@maplibre/maplibre-gl-style-spec';
import { beforeAll, describe, expect, it } from 'vitest';
import type { BaseContribution, BaseLayer, BaseState } from '../types.js';
import { baseContribution } from '../registry.js';
import { contributionLayer, contributionStatus, layerShown } from '#lib/map/flavors.js';
import { ANCHORS, drapedRuns, ordered } from '#lib/map/order.js';
import { basemapReady, buildStyle, type BasemapManifest, type LandscapeEntry } from '#lib/map/style.js';
import { ASPHALT, MARKINGS, UNPAVED } from '#lib/map/materials.js';
import ROADS_PALETTE, { LATITUDE, ZOOM, metres, pixelsPerMetre } from './palette.js';
import lines from './lines.base.js';
import surfaces from './surfaces.base.js';
import decks from './decks.base.js';
import markings, { markingsShown } from './markings.base.js';

beforeAll(() => basemapReady);

const ALL: readonly BaseContribution[] = [lines, surfaces, decks, markings];
const SOURCE_LAYERS = ['roads.lines', 'roads.surfaces_z15', 'roads.surfaces', 'roads.edges', 'roads.markings', 'roads.crosswalks'];

const layerInfo = (layer: string) => ({
	plugin: 'roads',
	layer,
	build: '20261015T000000Z',
	geometry: 'Polygon',
	features: 10,
	fields: { id: 'int' },
	minzoom: 14,
	maxzoom: 16,
	licence: 'ODbL-1.0',
	republish: 'internal',
	credit: ['© OpenStreetMap contributors']
});

const landscape = (without: string[] = []): LandscapeEntry => ({
	status: 'baked',
	file: 'landscape-1.pmtiles',
	digest: '1',
	format: 'pbf',
	minzoom: 8,
	maxzoom: 16,
	promoteId: 'id',
	layers: Object.fromEntries(SOURCE_LAYERS.filter((n) => !without.includes(n)).map((n) => [n, layerInfo(n.split('.')[1])])),
	empty: [],
	attribution: '© OpenStreetMap contributors',
	licences: ['ODbL-1.0'],
	republish: 'internal',
	access: 'tailnet',
	inputs: [],
	built: '2026-10-20',
	spec: 1,
	previous: null
});

const manifest = (without: string[] = []): BasemapManifest => ({
	bounds: [-117.05, 43, -115.95, 43.85],
	center: [-116.4, 43.6],
	zoom: 10,
	basemap: { file: 'valley.pmtiles', flavor: 'light', attribution: 'OSM', built: '2026-10-05' },
	glyphs: 'fonts/{fontstack}/{range}.pbf',
	sprite: 'sprites/v4/light',
	terrain: { file: 'terrain.pmtiles', encoding: 'mapbox', tileSize: 512, exaggeration: 1.3, attribution: 'USGS 3DEP', built: '2026-10-05' },
	landscape: landscape(without)
});

const state = (o: Partial<BaseState> = {}): BaseState => ({ flavor: 'valley', aerial: false, layers: new Set(), ...o });

/** A paint value at a zoom, for a feature (the style spec's own evaluator). */
function evaluate(layer: BaseLayer, prop: string, zoom: number, props: Record<string, unknown> = {}, flavor: 'valley' | 'clay' = 'valley'): unknown {
	const paint = (flavor === 'clay' && layer.clay ? layer.clay : layer.valley)[prop];
	const spec = (latest as unknown as Record<string, Record<string, unknown>>)[`paint_${layer.type}`][prop];
	const e = expression.createPropertyExpression(paint, prop, spec as never);
	if (e.result !== 'success') throw new Error(`${layer.id} ${prop}: ${JSON.stringify(e.value)}`);
	return (e.value as { evaluate(g: unknown, f: unknown): unknown }).evaluate({ zoom }, { type: 1, properties: props });
}

const allLayers = ALL.flatMap((c) => c.layers.map((l) => ({ c, l })));

describe('the roads contributions: registration and order', () => {
	it('are found by the registry, with ids, rows and credits', () => {
		for (const c of ALL) {
			expect(baseContribution(c.id), c.id).toBe(c);
			expect(c.title && c.blurb && c.credit).toBeTruthy();
			expect(c.blurb).toMatch(/ACHD, ITD; internal/);
		}
	});

	it('puts each in its slot and rank: lines in base, surfaces 20 and decks 25 in surfaces, markings in lanes', () => {
		expect(new Set(lines.layers.map((l) => `${l.slot}:${l.rank}`))).toEqual(new Set(['base:10']));
		expect(new Set(surfaces.layers.map((l) => `${l.slot}:${l.rank}`))).toEqual(new Set(['surfaces:20']));
		expect(new Set(decks.layers.map((l) => `${l.slot}:${l.rank}`))).toEqual(new Set(['surfaces:25']));
		expect(new Set(markings.layers.map((l) => l.slot))).toEqual(new Set(['lanes']));
	});

	it('builds into the style in the plan’s order: surfaces, decks, then the piece lines, then the markings', () => {
		const style = buildStyle(manifest(), 'http://x', false, 'valley', { contributions: ALL });
		const ids = style.layers.map((l) => l.id);
		const at = (id: string) => ids.indexOf(id);
		const last = (prefix: string) => Math.max(...ids.map((id, i) => (id.startsWith(prefix) ? i : -1)));
		const first = (prefix: string) => ids.findIndex((id) => id.startsWith(prefix));
		expect(first('roads.surfaces.')).toBeGreaterThan(at(ANCHORS.water));
		expect(last('roads.surfaces.')).toBeLessThan(first('roads.decks.'));
		expect(last('roads.decks.')).toBeLessThan(at(ANCHORS.surfaces));
		// The piece lines are above the surfaces and before anchor:base.
		expect(at('roads.lines.line')).toBeGreaterThan(at(ANCHORS.surfaces));
		expect(at('roads.lines.line')).toBeLessThan(at(ANCHORS.base));
		expect(first('roads.markings.')).toBeGreaterThan(at(ANCHORS.streets));
		expect(last('roads.markings.')).toBeLessThan(at(ANCHORS.lanes));
	});

	it('has valid style layers in both flavors (the style spec accepts them)', () => {
		for (const flavor of ['valley', 'clay'] as const) {
			const style = buildStyle(manifest(), 'http://x', false, flavor, { contributions: ALL });
			const errors = validateStyleMin(style as never).filter((e) => /roads\./.test(e.message));
			expect(errors.map((e) => e.message), flavor).toEqual([]);
		}
	});

	it('keeps the draped run at one stack at z14, z15.5 and z17 with every contribution on', () => {
		const style = buildStyle(manifest(), 'http://x', false, 'valley', { contributions: ALL });
		for (const zoom of [14, 15.5, 17]) {
			expect(drapedRuns(style.layers.map((l) => ordered(l)), zoom).length, `z${zoom}`).toBeLessThanOrEqual(1);
		}
	});

	it('draws only draped layer types and names its source-layers', () => {
		for (const { c, l } of allLayers) {
			expect(['fill', 'line'], l.id).toContain(l.type);
			expect(l.sourceLayer, l.id).toBeTruthy();
			expect(c.source.kind === 'landscape' && c.source.sourceLayers, l.id).toContain(l.sourceLayer);
		}
	});
});

describe('built or not', () => {
	it('is built only when every one of its source-layers is in the bake', () => {
		expect(contributionStatus(lines, manifest())).toEqual({ built: true });
		expect(contributionStatus(lines, manifest(['roads.lines'])).built).toBe(false);
		expect(contributionStatus(surfaces, manifest(['roads.edges'])).built).toBe(false);
		expect(contributionStatus(markings, manifest(['roads.crosswalks'])).built).toBe(false);
		expect(contributionStatus(lines, { ...manifest(), landscape: undefined }).built).toBe(false);
	});

	it('hides Protomaps’ road lines from z14, and only the piece lines do', () => {
		expect(lines.suppresses).toEqual({ groups: ['roads'], fromZoom: 14 });
		for (const c of [surfaces, decks, markings]) expect(c.suppresses).toBeUndefined();
	});
});

describe('K11: the lower layer stays opaque, only the upper one fades', () => {
	const line = lines.layers.find((l) => l.id === 'roads.lines.line')!;
	const fills = surfaces.layers.filter((l) => l.type === 'fill' && /\.(asphalt|concrete)$/.test(l.id));

	it('fades the piece lines from 1 at z15.5 to 0 at z16, and holds 1 below', () => {
		expect(evaluate(line, 'line-opacity', 14, { tunnel: false })).toBe(1);
		expect(evaluate(line, 'line-opacity', 15.5, { tunnel: false })).toBe(1);
		expect(evaluate(line, 'line-opacity', 16, { tunnel: false })).toBe(0);
		const mid = evaluate(line, 'line-opacity', 15.75, { tunnel: false }) as number;
		expect(mid).toBeGreaterThan(0);
		expect(mid).toBeLessThan(1);
		expect(line.maxzoom).toBe(ZOOM.fadeTo);
		expect(line.minzoom).toBe(ZOOM.linesFrom);
	});

	it('keeps the paved surfaces at a plain opacity of 1 with no zoom ramp, whichever flavor', () => {
		expect(fills.length).toBe(4);
		for (const f of fills) {
			for (const p of [f.valley, f.clay!]) expect(p['fill-opacity'], f.id).toBe(1);
		}
	});

	it('leaves no ground showing at any zoom the two share: 1 − surface opacity, times 1 − line opacity, is 0', () => {
		for (let z = 15.5; z < 16; z += 0.05) {
			const surface = fills.some((f) => f.minzoom! <= z && (f.maxzoom ?? 99) > z) ? 1 : 0;
			const upper = evaluate(line, 'line-opacity', z, { tunnel: false }) as number;
			expect((1 - surface) * (1 - upper), `z${z.toFixed(2)}`).toBe(0);
			// And the generalised surfaces hand over to the full ones with no gap at z16.
		}
		const z15 = surfaces.layers.filter((l) => l.id.startsWith('roads.surfaces.z15.'));
		const z16 = surfaces.layers.filter((l) => l.id.startsWith('roads.surfaces.z16.'));
		expect(Math.max(...z15.map((l) => l.maxzoom!))).toBe(Math.min(...z16.map((l) => l.minzoom!)));
		expect(Math.min(...z15.map((l) => l.minzoom!))).toBeLessThanOrEqual(ZOOM.fadeFrom);
	});

	it('is the only layer of the pair that ramps its opacity over z15.5-16', () => {
		for (const l of surfaces.layers) {
			for (const p of [l.valley, l.clay ?? {}]) {
				for (const [k, v] of Object.entries(p)) if (/opacity$/.test(k) && k.startsWith('fill')) expect(JSON.stringify(v), l.id).not.toMatch(/"zoom"/);
			}
		}
	});
});

describe('widths in metres', () => {
	it('converts at the valley latitude: 2^z doubling, about 0.29 px per metre at z14', () => {
		expect(LATITUDE).toBeCloseTo(43.6);
		expect(pixelsPerMetre(15) / pixelsPerMetre(14)).toBeCloseTo(2, 10);
		expect(pixelsPerMetre(14)).toBeGreaterThan(0.28);
		expect(pixelsPerMetre(14)).toBeLessThan(0.3);
	});

	it('draws a piece line w metres wide at any zoom of its range', () => {
		const line = lines.layers.find((l) => l.id === 'roads.lines.line')!;
		for (const z of [14, 14.7, 15.5, 15.99]) {
			expect(evaluate(line, 'line-width', z, { w: 10 }) as number).toBeCloseTo(10 * pixelsPerMetre(z), 6);
		}
		expect(evaluate(line, 'line-offset', 15, { off: -2 }) as number).toBeCloseTo(-2 * pixelsPerMetre(15), 6);
		expect(evaluate(line, 'line-offset', 15, {}) as number).toBe(0);
		expect(metres(['get', 'w'], 14, 16)).toBeTruthy();
	});
});

describe('the tones', () => {
	const line = lines.layers.find((l) => l.id === 'roads.lines.line')!;
	it('runs the piece lines from white at z14 to asphalt by z15.5, per material', () => {
		const rgb = (c: unknown) => c as { r: number; g: number; b: number };
		const at14 = rgb(evaluate(line, 'line-color', 14, { material: 'asphalt' }));
		expect(at14.r).toBeCloseTo(1, 1);
		const hex = (c: { r: number; g: number; b: number }) => '#' + [c.r, c.g, c.b].map((v) => Math.round(v * 255).toString(16).padStart(2, '0')).join('');
		expect(hex(rgb(evaluate(line, 'line-color', 15.5, { material: 'asphalt' })))).toBe(ASPHALT.valley.toLowerCase());
		expect(hex(rgb(evaluate(line, 'line-color', 15.5, { material: 'concrete' })))).toBe('#d2cec6');
		expect(hex(rgb(evaluate(line, 'line-color', 15.5, { material: 'asphalt' }, 'clay')))).toBe(ASPHALT.clay.toLowerCase());
	});

	it('gives gravel and dirt lines the surface tint and no fade, so nothing pops at the K11 handover', () => {
		const un = lines.layers.find((l) => l.id === 'roads.lines.unpaved')!;
		const hex = (c: { r: number; g: number; b: number }) => '#' + [c.r, c.g, c.b].map((v) => Math.round(v * 255).toString(16).padStart(2, '0')).join('');
		expect(un.maxzoom).toBe(ZOOM.fadeFrom);
		for (const [m, t] of [['gravel', UNPAVED.gravel], ['dirt', UNPAVED.dirt]] as const) {
			for (const z of [14, 15.4]) {
				expect(hex(evaluate(un, 'line-color', z, { material: m }) as never), `${m} z${z}`).toBe(t.color.toLowerCase());
				expect(evaluate(un, 'line-opacity', z, { material: m }), `${m} z${z}`).toBe(t.opacity);
			}
		}
		expect(JSON.stringify(lines.layers.find((l) => l.id === 'roads.lines.line')!.filter)).toContain('gravel');
	});

	it('draws a tunnel faint', () => {
		const line = lines.layers.find((l) => l.id === 'roads.lines.line')!;
		expect(evaluate(line, 'line-opacity', 15, { tunnel: true }) as number).toBeLessThan(0.5);
	});

	it('fills a material with its own tone, and an unpaved one as a tint', () => {
		const fill = (name: string) => surfaces.layers.find((l) => l.id === `roads.surfaces.z16.${name}`)!;
		expect(fill('asphalt').valley['fill-color']).toBe(ASPHALT.valley);
		expect(fill('concrete').valley['fill-color']).toBe('#D2CEC6');
		expect(fill('dirt').valley['fill-opacity']).toBe(0.18);
		expect(fill('gravel').valley['fill-opacity']).toBe(0.35);
		expect(fill('asphalt').clay!['fill-color']).toBe(ASPHALT.clay);
	});

	it('hides the surfaces under Aerial and draws a crisp curb for a known width, a soft one for an estimated', () => {
		for (const l of [...surfaces.layers, ...decks.layers]) expect(l.aerial, l.id).toBe('hide');
		const curb = surfaces.layers.find((l) => l.id === 'roads.surfaces.edge.curb')!;
		expect(evaluate(curb, 'line-blur', 16, { tier: 'inventoried' })).toBe(0);
		expect(evaluate(curb, 'line-blur', 16, { tier: 'measured' })).toBe(0);
		expect(evaluate(curb, 'line-blur', 16, { tier: 'estimated' })).toBeGreaterThan(0);
		expect(evaluate(curb, 'line-blur', 16, { tier: 'counted' })).toBeGreaterThan(0);
		expect(evaluate(curb, 'line-width', 16, { tier: 'estimated' }) as number).toBeGreaterThan(evaluate(curb, 'line-width', 16, { tier: 'inventoried' }) as number);
	});

	it('makes the island an outline only, and keeps decks out of the plain surfaces', () => {
		const island = surfaces.layers.find((l) => l.id === 'roads.surfaces.island')!;
		expect(island.type).toBe('line');
		for (const l of surfaces.layers.filter((l) => l.type === 'fill')) {
			expect(JSON.stringify(l.filter), l.id).not.toMatch(/island|deck/);
			expect(JSON.stringify(l.filter), l.id).toMatch(/carriageway/);
		}
		for (const l of decks.layers) expect(JSON.stringify(l.filter), l.id).toContain('deck');
		expect(decks.layers.find((l) => l.id === 'roads.decks.z15.casing')!.valley['line-color']).toBe('#2b2a33');
		expect(Math.min(...decks.layers.map((l) => l.minzoom!))).toBe(15);
	});
});

describe('markings: when they show', () => {
	const cases: [string, Partial<BaseState>, boolean][] = [
		['Valley', {}, true],
		['Valley with Lanes', { layers: new Set(['lanes']) }, true],
		['Valley under Aerial', { aerial: true }, false],
		['Valley under Aerial with Lanes', { aerial: true, layers: new Set(['lanes']) }, true],
		['Clay', { flavor: 'clay' }, false],
		['Clay with Lanes', { flavor: 'clay', layers: new Set(['lanes']) }, true],
		['Clay under Aerial with Lanes', { flavor: 'clay', aerial: true, layers: new Set(['lanes']) }, true],
		['Clay under Aerial', { flavor: 'clay', aerial: true }, false]
	];
	for (const [name, o, shown] of cases) {
		it(`${name}: ${shown ? 'shown' : 'hidden'}`, () => {
			const s = state(o as Partial<BaseState>);
			expect(markingsShown(s)).toBe(shown);
			for (const l of markings.layers) expect(layerShown(markings, l, s), l.id).toBe(shown);
			const spec = contributionLayer(markings, markings.layers[1], s);
			expect((spec.layout as { visibility: string }).visibility).toBe(shown ? 'visible' : 'none');
		});
	}

	it('starts at z16.5, reaches full strength at z17, and is cream (Valley) or ink at 60% (Clay)', () => {
		const solid = markings.layers.find((l) => l.id === 'roads.markings.solid')!;
		expect(solid.minzoom).toBe(16.5);
		expect(evaluate(solid, 'line-opacity', 16.5, { dash: 'solid' })).toBe(0);
		expect(evaluate(solid, 'line-opacity', 17, { dash: 'solid' })).toBe(1);
		expect(evaluate(solid, 'line-opacity', 18, { dash: 'solid' }, 'valley')).toBe(1);
		expect(evaluate(solid, 'line-opacity', 17, {}, 'clay')).toBeCloseTo(0.6);
		expect(solid.valley['line-color']).toBeDefined();
		const hex = (c: { r: number; g: number; b: number }) => '#' + [c.r, c.g, c.b].map((v) => Math.round(v * 255).toString(16).padStart(2, '0')).join('');
		expect(hex(evaluate(solid, 'line-color', 17, { material: 'asphalt' }) as never)).toBe(MARKINGS.onAsphalt.color.toLowerCase());
		// Ink at 70% on concrete, once the export says the material.
		expect(evaluate(solid, 'line-opacity', 17, { material: 'concrete' })).toBeCloseTo(0.7);
	});

	it('draws a double centre line as two cream lines offset either side, with no opaque layer between', () => {
		const left = markings.layers.find((l) => l.id === 'roads.markings.double.left')!;
		const right = markings.layers.find((l) => l.id === 'roads.markings.double.right')!;
		expect(markings.layers.some((l) => l.id.endsWith('.gap'))).toBe(false);
		expect(evaluate(left, 'line-offset', 18, {}) as number).toBeLessThan(0);
		expect(evaluate(right, 'line-offset', 18, {}) as number).toBeGreaterThan(0);
		expect(evaluate(left, 'line-offset', 18, {}) as number).toBeCloseTo(-(evaluate(right, 'line-offset', 18, {}) as number));
		// The offset is one line width, so the gap between the two lines is one line width.
		expect(Math.abs(evaluate(right, 'line-offset', 18, {}) as number)).toBeCloseTo(evaluate(right, 'line-width', 18, {}) as number);
		for (const l of [left, right]) expect(l.valley['line-opacity']).toBeTruthy();
	});
});

describe('the palette', () => {
	it('names its colors and agrees with the tokens', () => {
		expect(ROADS_PALETTE.id).toBe('roads');
		expect(ROADS_PALETTE.colors.find((c) => c.name === 'asphalt')?.valley).toBe(ASPHALT.valley);
		for (const c of ROADS_PALETTE.colors) {
			expect(c.valley, c.name).toMatch(/^#[0-9a-fA-F]{6}$/);
			expect(c.use, c.name).toBeTruthy();
		}
	});

	it('uses no green-led color (never red and green; the roads are warm grays, cream, ink and umber)', () => {
		for (const c of ROADS_PALETTE.colors) {
			const n = parseInt(c.valley.slice(1), 16);
			const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
			expect(g > r || g > b ? g - Math.max(r, b) : 0, c.name).toBeLessThanOrEqual(0);
		}
	});
});
