import { describe, expect, it } from 'vitest';
import { ANCHORS, insertSlotted } from '#lib/map/order.js';
import { SHOW_BY, SHOW_BY_DEFS } from './model.js';
import { ALL_IDS, fillColor, ID, patternFilter, patternImage, PICK_LAYERS, restyle, selectedFilter, soilLayers, SOURCE } from './layers.js';
import { STEPS } from './palette.js';
import { imageId } from './patterns.js';
import { MVT_LABELS, MVT_SURVEY, MVT_UNITS } from './tiles.js';

const all = () => {
	const l = soilLayers('restr');
	return [...l.areas, ...l.copies, ...l.land, ...l.labels];
};
const byId = (id: string) => all().find((s) => s.layer.id === id)!;
const spec = (id: string) => byId(id).layer as unknown as Record<string, unknown> & { paint: Record<string, unknown>; layout: Record<string, unknown> };

describe('the Soils style layers', () => {
	it('are every id once, all hidden until the manager shows them, on the one source', () => {
		expect(all().map((s) => s.layer.id).sort()).toEqual([...ALL_IDS].sort());
		expect(new Set(ALL_IDS).size).toBe(ALL_IDS.length);
		for (const s of all()) {
			expect((s.layer as { source?: string }).source, s.layer.id).toBe(SOURCE);
			expect(spec(s.layer.id).layout.visibility, s.layer.id).toBe('none');
		}
	});

	it('read the MVT layers the tiles make: units for the wash and outlines, survey for the bounds, soil_labels for the text', () => {
		for (const id of [ID.fill, ID.copy, ID.pick, ID.pattern, ID.outline, ID.selected]) expect(spec(id)['source-layer'], id).toBe(MVT_UNITS);
		expect(spec(ID.survey)['source-layer']).toBe(MVT_SURVEY);
		for (const id of [ID.symbol, ID.name]) expect(spec(id)['source-layer'], id).toBe(MVT_LABELS);
	});

	it('put the wash in areas (rank 20, an area fill), its 0.45 copy in land over Aerial only, and the rest where the plan says', () => {
		const l = soilLayers('restr');
		expect(l.areas.map((s) => [s.layer.id, s.slot, !!s.areaFill])).toEqual([
			[ID.fill, 'areas', true],
			[ID.pick, 'areas', false]
		]);
		expect(l.copies).toHaveLength(1);
		expect(l.copies[0]).toMatchObject({ slot: 'land', areaFill: true, aerial: 'only' });
		expect(spec(ID.copy).paint['fill-opacity']).toBe(0.45);
		expect(spec(ID.fill).paint['fill-opacity']).toBeGreaterThan(0.45);
		expect(l.land.every((s) => s.slot === 'land')).toBe(true);
		expect(l.labels.every((s) => s.slot === 'labels')).toBe(true);
		// The patterns are part of the fill (they follow it); the linework and the pick layer are not.
		expect(byId(ID.pattern).areaFill).toBe(true);
		for (const id of [ID.survey, ID.outline, ID.selected]) expect(byId(id).areaFill, id).toBeUndefined();
	});

	it('draw by zoom: wash from z9, survey bounds z8-11, outlines from z12, symbols from z14, names from z16', () => {
		expect(spec(ID.fill).minzoom).toBe(9);
		expect(spec(ID.survey).maxzoom).toBe(12);
		expect(spec(ID.survey).minzoom).toBeUndefined(); // the tiles start at z8
		expect(spec(ID.outline).minzoom).toBe(12);
		expect([spec(ID.symbol).minzoom, spec(ID.symbol).maxzoom]).toEqual([14, 16]);
		expect(spec(ID.name).minzoom).toBe(16);
		expect(spec(ID.name).layout['text-field']).toEqual(['concat', ['get', 'symbol'], '\n', ['coalesce', ['get', 'name'], '']]);
	});

	it('draw the pick layer with no opacity, so a click opens the card even when another fill is the one drawn', () => {
		expect(spec(ID.pick).paint['fill-opacity']).toBe(0);
		expect(PICK_LAYERS).toEqual([ID.pick]);
	});

	it('land in the slots around real anchors: areas under water, land over the base, labels over the points', () => {
		const anchors = Object.values(ANCHORS).map((id) => ({ id, type: 'background', layout: { visibility: 'none' } }) as never);
		const l = soilLayers('restr');
		let style = insertSlotted(anchors, l.areas, 20);
		style = insertSlotted(style, l.copies, 5);
		style = insertSlotted(style, l.land, 10);
		style = insertSlotted(style, l.labels, 25);
		const order = style.map((x) => x.id);
		const idx = (id: string) => order.indexOf(id);
		expect(idx(ID.fill)).toBeGreaterThan(idx(ANCHORS.ground));
		expect(idx(ID.fill)).toBeLessThan(idx(ANCHORS.areas));
		expect(idx(ID.copy)).toBeGreaterThan(idx(ANCHORS.base));
		expect(idx(ID.copy)).toBeLessThan(idx(ID.outline)); // rank 5 under rank 10
		expect(idx(ID.outline)).toBeLessThan(idx(ANCHORS.land));
		expect(idx(ID.symbol)).toBeLessThan(idx(ANCHORS.labels));
	});
});

describe('the wash', () => {
	it('colours each code by its gray step and leaves an unrated unit clear, for every property', () => {
		for (const by of SHOW_BY) {
			const d = SHOW_BY_DEFS[by];
			const e = fillColor(by) as unknown[];
			expect(e[0]).toBe('match');
			expect(e[1]).toEqual(['coalesce', ['get', by], -1]);
			const pairs = e.slice(2, -1);
			expect(pairs).toHaveLength(d.levels.length * 2);
			d.levels.forEach((_, code) => {
				expect(pairs[code * 2], `${by} code`).toBe(code);
				expect(pairs[code * 2 + 1], `${by} colour`).toBe(STEPS[d.steps[code]]);
			});
			expect(e.at(-1)).toBe('rgba(0,0,0,0)');
		}
	});

	it('spreads a shorter scale over the five steps, palest to darkest', () => {
		for (const by of SHOW_BY) {
			const s = SHOW_BY_DEFS[by].steps;
			expect([...s].sort((a, b) => a - b), by).toEqual([...s]);
			expect(s[0]).toBe(0);
			expect(s.at(-1)).toBe(4);
			expect(new Set(s).size).toBe(s.length);
		}
	});

	it('draws the patterns the property carries and nothing for the others', () => {
		expect(JSON.stringify(patternFilter('restr'))).toContain('hardpan');
		expect(patternImage('restr')).toEqual(['match', ['get', 'pat'], 'bedrock', imageId('stipple'), imageId('hatch')]);
		expect(JSON.stringify(patternFilter('farm'))).toContain('drained');
		expect(patternImage('farm')).toEqual(['match', ['get', 'cond'], 'reclaimed', imageId('cross'), imageId('hatch')]);
		expect(patternFilter('hsg')).toEqual(['==', ['get', 'dual'], true]);
		for (const by of ['drain', 'aws'] as const) expect(patternFilter(by)).toEqual(['==', ['literal', 0], 1]); // matches nothing
		// Every property that has patterns in the legend has them on the map.
		for (const by of SHOW_BY) expect(SHOW_BY_DEFS[by].patterns.length > 0, by).toBe(JSON.stringify(patternFilter(by)).includes('"literal",0') === false);
	});

	it('re-styles the wash and the pattern in place when "Show by" changes, never touching visibility', () => {
		const ops = restyle('drain');
		expect(ops.map((o) => o.id)).toEqual([ID.fill, ID.copy, ID.pattern]);
		expect(ops[0].paint).toEqual([['fill-color', fillColor('drain')]]);
		expect(ops[2].filter).toEqual(patternFilter('drain'));
		for (const o of ops) expect(JSON.stringify(o)).not.toContain('visibility');
	});

	it('outlines the selected map unit by its key, and no unit when nothing is selected', () => {
		expect(selectedFilter('2700001')).toEqual(['==', ['get', 'mukey'], '2700001']);
		expect(selectedFilter(null)).toEqual(['==', ['get', 'mukey'], '']);
	});
});
