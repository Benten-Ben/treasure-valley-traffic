import { describe, expect, it } from 'vitest';
import { createPropertyExpression, featureFilter, latest, validateStyleMin, type StyleSpecification } from '@maplibre/maplibre-gl-style-spec';
import { addSlotted, insertSlotted } from '#lib/map/order.js';
import {
	ALL_IDS,
	cropLayers,
	DEFAULT_GROWTH,
	fillColorField,
	fillColorLo,
	growthFilters,
	ID,
	labelText,
	OFF_RANGE,
	patternField,
	PICK_LAYERS,
	restyle,
	SOURCE_FIELDS,
	SOURCE_YEAR,
	type CropState,
	type Expr
} from './layers.js';
import { FILL, GROUPS } from './palette.js';
import { imageId } from './patterns.js';

const STATE: CropState = { year: 2025, current: 2025, first: 2018, growth: { ...DEFAULT_GROWTH } };
const feature = (properties: Record<string, unknown>, id = 1) => ({ type: 3 as const, id, properties, geometry: [] });
const layers = (s = STATE) => {
	const l = cropLayers(s);
	return [...l.areas, ...l.copies, ...l.land, ...l.labels];
};
const spec = (id: string, s = STATE) => layers(s).find((x) => x.layer.id === id)!.layer as unknown as { filter?: Expr; paint?: Record<string, Expr>; layout?: Record<string, unknown>; minzoom?: number; maxzoom?: number };
const passes = (filter: Expr, props: Record<string, unknown>, zoom = 12) => featureFilter(filter as never, 'filter').filter({ zoom }, feature(props) as never);
const evalPaint = (expr: Expr, prop: 'fill-color' | 'fill-pattern', props: Record<string, unknown>, zoom = 12) => {
	const r = createPropertyExpression(expr, 'fill-color', latest.paint_fill[prop] as never);
	if (r.result !== 'success') throw new Error(JSON.stringify(r.value));
	return r.value.evaluate({ zoom }, feature(props) as never);
};

describe('the Crop fields style layers', () => {
	it('are valid MapLibre layers over the two vector sources', () => {
		const style: StyleSpecification = {
			version: 8,
			glyphs: 'http://x/fonts/{fontstack}/{range}.pbf',
			sources: {
				[SOURCE_FIELDS]: { type: 'vector', tiles: ['http://x/api/farm/tiles/crop_fields/{z}/{x}/{y}'], minzoom: 8, maxzoom: 14 },
				[SOURCE_YEAR]: { type: 'vector', tiles: ['http://x/api/farm/tiles/crop_year_2019/{z}/{x}/{y}'], minzoom: 8, maxzoom: 10 }
			},
			layers: layers().map((l) => l.layer)
		};
		const errors = validateStyleMin(style).map((e) => e.message);
		expect(errors).toEqual([]);
		expect(layers().map((l) => l.layer.id).sort()).toEqual([...ALL_IDS].sort());
		expect(new Set(ALL_IDS).size).toBe(ALL_IDS.length);
	});

	it('put fills in areas at rank 10 (Clay only), their copies in land at rank 5 (over Aerial only), the rest in land and labels', () => {
		const l = cropLayers(STATE);
		for (const x of l.areas) expect(x, x.layer.id).toMatchObject({ slot: 'areas', areaFill: true, looks: 'clay' });
		for (const x of l.copies) expect(x, x.layer.id).toMatchObject({ slot: 'land', areaFill: true, aerial: 'only' });
		for (const x of l.copies) expect(x.looks).toBeUndefined(); // the copies are Aerial's, whichever flavor
		for (const x of l.land) expect(x, x.layer.id).toMatchObject({ slot: 'land', areaFill: true, looks: 'clay' });
		expect(l.labels.map((x) => x.layer.id)).toEqual([ID.label]);
		expect(l.labels[0].slot).toBe('labels');
		// All start hidden: the module shows them when the layer is on.
		for (const x of layers()) expect((x.layer.layout as { visibility?: string }).visibility, x.layer.id).toBe('none');
		// Every layer that draws in the draped block is a draped type (fill or line); only the label is a symbol.
		for (const x of layers().filter((x) => x.slot !== 'labels')) expect(['fill', 'line']).toContain(x.layer.type);
	});

	it('records its flags when added, so the manager can gate them', async () => {
		const { slotFlags } = await import('#lib/map/order.js');
		const map: Parameters<typeof addSlotted>[0] = { getLayer: () => ({}), getLayersOrder: () => [] };
		const l = cropLayers(STATE);
		for (const [layers, rank] of [[l.areas, 10], [l.copies, 5], [l.land, 20], [l.labels, 25]] as const) addSlotted(map, layers, rank, () => {}, 'crops');
		const flags = slotFlags(map);
		expect(flags.get(ID.fill)).toMatchObject({ areaFill: true, looks: 'clay', owner: 'crops' });
		expect(flags.get(ID.copy)).toMatchObject({ areaFill: true, aerial: 'only', owner: 'crops' });
		expect(flags.get(ID.copy)?.looks).toBeUndefined();
		expect(flags.size).toBe(ALL_IDS.length);
	});

	it('order the slots: fills, then copies, then patterns and linework, whatever order they are added in', () => {
		const base = [
			{ id: 'anchor:areas', type: 'background' },
			{ id: 'anchor:land', type: 'background' },
			{ id: 'anchor:labels', type: 'background' }
		] as never[];
		const l = cropLayers(STATE);
		let out = base as never[];
		const ranks = {};
		for (const [layers, rank] of [[l.land, 20], [l.areas, 10], [l.labels, 25], [l.copies, 5]] as const) out = insertSlotted(out, layers, rank, ranks) as never[];
		const ids = (out as { id: string }[]).map((x) => x.id);
		expect(ids.indexOf(ID.fill)).toBeLessThan(ids.indexOf('anchor:areas'));
		expect(ids.indexOf('anchor:areas')).toBeLessThan(ids.indexOf(ID.copy));
		expect(ids.indexOf(ID.copy)).toBeLessThan(ids.indexOf(ID.pattern));
		expect(ids.indexOf(ID.pattern)).toBeLessThan(ids.indexOf(ID.edgeEstimated));
		expect(ids.indexOf(ID.edgeEstimated)).toBeLessThan(ids.indexOf('anchor:land'));
		expect(ids.indexOf(ID.label)).toBeLessThan(ids.indexOf('anchor:labels'));
	});

	it('picks on the field fills, their copies and the growth hatches', () => {
		expect(PICK_LAYERS).toEqual([ID.fill, ID.copy, ID.growth, ID.plat]);
	});

	it('colour each group as the palette says, at z8-10 by group and from z11 by the year\'s letter', () => {
		for (const g of GROUPS) expect(evalPaint(fillColorLo(), 'fill-color', { g }, 9).toString(), g).toBe(evalPaint(['literal', FILL[g]], 'fill-color', {}).toString());
		const f = (y: string, year: number) => evalPaint(fillColorField({ year, first: 2018 }), 'fill-color', { y }, 13);
		const want = (g: (typeof GROUPS)[number]) => evalPaint(['literal', FILL[g]], 'fill-color', {});
		// "hhhhhhpd": hay through 2023, pasture 2024, developed (unpainted) 2025.
		expect(f('hhhhhhpd', 2018).toString()).toBe(want('hay').toString());
		expect(f('hhhhhhpd', 2024).toString()).toBe(want('pasture').toString());
		expect(f('hhhhhhpd', 2025).toString()).toBe(evalPaint('rgba(0,0,0,0)' as never, 'fill-color', {}).toString());
		expect(f('crh', 2019).toString()).toBe(want('roots').toString());
		expect(f('crh', 2018).toString()).toBe(want('corn').toString());
		// A year past the string (a short y), or "-" (none): nothing drawn.
		expect(f('c', 2022).toString()).toBe(f('-', 2018).toString());
	});

	it('give every painted group a pattern of its own, by group and by letter', () => {
		for (const g of GROUPS) expect(evalPaint(patternField({ year: 2018, first: 2018 }), 'fill-pattern', { y: `${{ corn: 'c', hay: 'h', grain: 'g', roots: 'r', specialty: 's', pasture: 'p', fallow: 'f' }[g]}` }, 13)?.toString(), g).toContain(`crops-pat-${g}`);
	});

	it('draw only painted groups: developed, other and none are filtered out', () => {
		const filter = spec(ID.fill).filter!;
		for (const y of ['c', 'h', 'g', 'r', 's', 'p', 'f']) expect(passes(filter, { y: y.repeat(8) }), y).toBe(true);
		for (const y of ['d', 'o', '-']) expect(passes(filter, { y: y.repeat(8) }), y).toBe(false);
		const lo = spec(ID.fillLo).filter!;
		expect(passes(lo, { g: 'hay' }, 9)).toBe(true);
		expect(passes(lo, { s: 'built_over' }, 9)).toBe(false); // the growth rows have no group
	});

	it('draw the current year\'s dissolves from the fields tiles, and an earlier year\'s from its own source, moving the other out of every zoom', () => {
		const range = (id: string, st: CropState) => [spec(id, st).minzoom, spec(id, st).maxzoom];
		const earlier = { ...STATE, year: 2019 };
		for (const [now, yearly] of [[ID.fillLo, ID.fillLoYear], [ID.copyLo, ID.copyLoYear], [ID.patternLo, ID.patternLoYear]]) {
			expect(range(now, STATE), now).not.toEqual(OFF_RANGE);
			expect(range(yearly, STATE), yearly).toEqual(OFF_RANGE);
			expect(range(now, earlier), now).toEqual(OFF_RANGE);
			expect(range(yearly, earlier), yearly).not.toEqual(OFF_RANGE);
		}
		expect(range(ID.fillLo, STATE)).toEqual([0, 11]);
		expect(range(ID.patternLo, STATE)).toEqual([10, 11]);
		const ops = restyle(earlier);
		expect(ops.find((o) => o.id === ID.fillLo)!.zoom).toEqual(OFF_RANGE);
		expect(ops.find((o) => o.id === ID.fillLoYear)!.zoom).toEqual([0, 11]);
		expect(ops.find((o) => o.id === ID.patternLoYear)!.zoom).toEqual([10, 11]);
		// The dissolves' filter is the same either way: only painted groups.
		expect(passes(spec(ID.fillLoYear, earlier).filter!, { g: 'corn' }, 9)).toBe(true);
		expect(passes(spec(ID.fillLoYear, earlier).filter!, { g: 'developed' }, 9)).toBe(false);
	});

	it('fade the fills out over z14.5-15.5 while the dashed estimated edge comes in', () => {
		const opacity = (id: string) => {
			const e = (spec(id).paint as Record<string, Expr>)[id.includes('edge-estimated') ? 'line-opacity' : id.includes('edge') ? 'line-opacity' : 'fill-opacity'];
			const r = createPropertyExpression(e, 'opacity', (id.includes('edge') ? latest.paint_line['line-opacity'] : latest.paint_fill['fill-opacity']) as never);
			if (r.result !== 'success') throw new Error('bad expression');
			return (zoom: number) => r.value.evaluate({ zoom }, feature({}) as never) as number;
		};
		const fill = opacity(ID.fill);
		expect(fill(12)).toBeCloseTo(0.85);
		expect(fill(14.5)).toBeCloseTo(0.85);
		expect(fill(15)).toBeCloseTo(0.425);
		expect(fill(15.5)).toBe(0);
		const est = opacity(ID.edgeEstimated);
		expect(est(14)).toBe(0);
		expect(est(15.5)).toBeCloseTo(0.85);
		expect(spec(ID.edgeEstimated).paint!['line-dasharray' as never]).toEqual([3, 2]);
		expect(spec(ID.edge).minzoom).toBe(12);
		expect(spec(ID.label).minzoom).toBe(13.5);
		expect(spec(ID.fill).minzoom).toBe(11);
		expect(spec(ID.fillLo).maxzoom).toBe(11);
	});

	it('hatch the growth states the toggles turn on, and approved plats on their own layer', () => {
		const on = growthFilters({ built_over: true, being_built: false, plat: false });
		expect(passes(on.field, { s: 'built_over' })).toBe(true);
		expect(passes(on.field, { s: 'being_built' })).toBe(false);
		expect(passes(on.plat, { p: true })).toBe(false);
		const plats = growthFilters({ built_over: false, being_built: false, plat: true });
		expect(passes(plats.plat, { p: true })).toBe(true);
		expect(passes(plats.plat, { p: false })).toBe(false);
		expect(passes(plats.field, { s: 'built_over' })).toBe(false);
		expect(passes(plats.lo, { s: 'plat' }, 9)).toBe(true);
		expect(passes(growthFilters({ built_over: false, being_built: false, plat: false }).lo, { s: 'plat' }, 9)).toBe(false);
		expect(evalPaint(spec(ID.growth).paint!['fill-pattern']!, 'fill-pattern', { s: 'being_built' })?.toString()).toContain(imageId('being_built'));
		expect(evalPaint(spec(ID.growthLo).paint!['fill-pattern']!, 'fill-pattern', { s: 'plat' }, 9)?.toString()).toContain(imageId('plat'));
	});

	it('label with the crop name for the newest year and the group for an earlier one', () => {
		const text = (s: CropState, props: Record<string, unknown>) => {
			const r = createPropertyExpression(labelText(s), 'text-field', latest.layout_symbol['text-field'] as never);
			if (r.result !== 'success') throw new Error('bad expression');
			return String(r.value.evaluate({ zoom: 14 }, feature(props) as never));
		};
		expect(text(STATE, { n: 'Alfalfa', y: 'hhhhhhhh' })).toBe('Alfalfa');
		expect(text({ ...STATE, year: 2018 }, { n: 'Alfalfa', y: 'chhhhhhh' })).toBe('Corn');
		expect(text({ ...STATE, year: 2019 }, { n: 'Alfalfa', y: 'chhhhhhh' })).toBe('Hay');
	});

	it('re-style on a year change: filters, colours, patterns and labels follow the year; visibility is never touched', () => {
		const ops = restyle({ ...STATE, year: 2019 });
		const op = (id: string) => ops.find((o) => o.id === id)!;
		expect(op(ID.fillLo).zoom).toEqual(OFF_RANGE);
		expect(JSON.stringify(op(ID.fill).paint)).toContain('"slice"');
		expect(JSON.stringify(op(ID.fill).paint)).toContain('1,2'); // 2019 is the second letter
		expect(op(ID.label).layout![0][0]).toBe('text-field');
		for (const o of ops) expect(Object.keys(o).sort().every((k) => ['id', 'filter', 'paint', 'layout', 'zoom'].includes(k)), o.id).toBe(true);
		expect(JSON.stringify(ops)).not.toContain('visibility');
		expect(ops.map((o) => o.id).every((id) => ALL_IDS.includes(id))).toBe(true);
	});
});
