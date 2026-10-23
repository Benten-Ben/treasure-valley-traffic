import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { createExpression } from '@maplibre/maplibre-gl-style-spec';
import { describe, expect, it } from 'vitest';
import {
	arrowImageId,
	arrowsOfImage,
	claimText,
	classWord,
	conflictInfo,
	laneSourceLabel,
	lanesPhrase,
	mapIsCurrent,
	metresFeet,
	parseBuild,
	parsePieceRef,
	pavingLotId,
	pavingSelection,
	pieceTitle,
	roadSelection,
	turnArrows
} from './lanes.js';
import { arrowImageExpression, ownLayers, pickablePavingLayers, pickableRoadLayers } from './layers.js';
import { ARROW_IMAGES } from './markers.js';
import { ARROWS_SPLIT } from './icons.js';

describe('lane count labels', () => {
	it('name the source exactly', () => {
		expect(laneSourceLabel('osm', false)).toBe('OpenStreetMap');
		expect(laneSourceLabel('osm', true)).toBe('OpenStreetMap');
		expect(laneSourceLabel('achd_msm', true)).toBe('ACHD rule (Master Street Map)');
		expect(laneSourceLabel('itd_hpms', true)).toBe('ACHD rule (ITD HPMS)');
		expect(laneSourceLabel('itd_hpms', false)).toBe('HPMS');
		expect(laneSourceLabel('compass_centerline', true)).toBe('ACHD rule (COMPASS centerline)');
		expect(laneSourceLabel('default', true)).toBe('assumed');
	});
});

describe('words', () => {
	it('lanes: each way, one count each direction, one-way and the centre turn lane', () => {
		expect(lanesPhrase({ fwd: 2, bwd: 2, centre_turn: false }, 'both')).toBe('2 each way');
		expect(lanesPhrase({ fwd: 3, bwd: 2, centre_turn: true }, 'both')).toBe('3 and 2, one count for each direction, and a centre turn lane');
		expect(lanesPhrase({ fwd: 2, bwd: 0, centre_turn: false }, 'forward')).toBe('2 lanes, one way');
		expect(lanesPhrase({ fwd: 1, bwd: 0, centre_turn: false }, 'forward')).toBe('1 lane, one way');
	});

	it('titles, classes, sizes and claims', () => {
		expect(pieceTitle({ name: 'Chinden Boulevard', ref: 'SH-20', class_word: 'Arterial' })).toBe('Chinden Boulevard');
		expect(pieceTitle({ name: null, ref: 'SH-20', class_word: 'Arterial' })).toBe('SH-20');
		expect(pieceTitle({ name: null, ref: null, class_word: 'Residential street' })).toBe('Unnamed residential street');
		expect(classWord('service', 'alley')).toBe('Alley');
		expect(classWord('motorway_link')).toBe('Ramp or link');
		expect(classWord('weird_road')).toBe('weird road');
		expect(metresFeet(21.34)).toBe('21.3 m (70 ft)');
		expect(claimText({ label: 'OpenStreetMap', fwd: 3, bwd: 2, total: 5 })).toBe('OpenStreetMap: 5 lanes (3 and 2)');
		expect(claimText({ label: 'ACHD rule (Master Street Map)', fwd: 1, bwd: 0, total: 1 })).toBe('ACHD rule (Master Street Map): 1 lane');
	});
});

describe('the review row', () => {
	it('reads both counts, whatever source the rule used', () => {
		const c = conflictInfo([{ osm: [3, 2], itd_hpms: [1, 1], road_segment_id: 4 }]);
		expect(c.osm).toMatchObject({ total: 5 });
		expect(c.other).toEqual({ label: 'ACHD rule (ITD HPMS)', fwd: 1, bwd: 1, total: 2 });
		expect(c.rule_disagrees).toBe(false);
	});
	it('keeps the first of several rows and tolerates garbage', () => {
		expect(conflictInfo([null, 5, 'x', [], { osm: [1, 1] }, { osm: [9, 9] }]).osm?.total).toBe(2);
		expect(conflictInfo([{ osm: [-1, 2], achd_msm: [Infinity, 1] }])).toEqual({ osm: null, other: null, rule_disagrees: false });
		expect(conflictInfo([])).toEqual({ osm: null, other: null, rule_disagrees: false });
	});
});

describe('builds', () => {
	const current = { id: '20261012T031500Z', finished_at: '2026-10-12T03:25:00.123Z' };
	it('an export made after the build finished is current; one made before is a build behind', () => {
		expect(mapIsCurrent('20261012T040000Z', current)).toBe(true);
		expect(mapIsCurrent('20261012T032500Z-x', current)).toBe(true);
		expect(mapIsCurrent('20261012T031000Z', current)).toBe(false);
		expect(mapIsCurrent('20260101T000000Z', current)).toBe(false);
	});
	it("the build's own id is current, and a name that can't be matched is not", () => {
		expect(mapIsCurrent('20261012T031500Z', { id: '20261012T031500Z', finished_at: new Date('2026-12-01') })).toBe(true);
		expect(mapIsCurrent('fixture', current)).toBe(false);
		expect(mapIsCurrent('', current)).toBe(false);
		expect(mapIsCurrent('20261012T040000Z', { id: 'x', finished_at: 'garbage' })).toBe(false);
	});
});

describe('route ids', () => {
	it('parse a kind and an int4 id; anything else is refused', () => {
		expect(parsePieceRef('surface-2001')).toEqual({ kind: 'surface', id: 2001 });
		expect(parsePieceRef('line-1')).toEqual({ kind: 'line', id: 1 });
		expect(parsePieceRef('edge-2147483647')).toEqual({ kind: 'edge', id: 2147483647 });
		for (const bad of ['', 'surface', 'surface-', 'surface-x', 'road-1', 'surface-2147483648', 'surface-1; drop', 'Surface-1', 'marking--1', 'surface-12345678901'])
			expect(parsePieceRef(bad), bad).toBeNull();
	});
	it('the build is letters, digits and . _ - only', () => {
		expect(parseBuild('20261012T031500Z')).toBe('20261012T031500Z');
		expect(parseBuild('fixture')).toBe('fixture');
		for (const bad of [null, '', 'a b', "x'y", 'a/../b', 'x'.repeat(41)]) expect(parseBuild(bad), String(bad)).toBeNull();
	});
	it("paving: a lot's baked id is twice its OpenStreetMap id, plus one for a relation", () => {
		expect(pavingLotId(84)).toBe('w42');
		expect(pavingLotId(85)).toBe('r42');
		expect(pavingLotId(-1)).toBeNull();
		expect(pavingLotId(1.5)).toBeNull();
	});
});

describe('picking', () => {
	it('a road tile feature opens the piece card by kind, id and the build; no build, no pick', () => {
		const s = roadSelection('roads.surfaces', { id: 2003, kind: 'carriageway', tier: 'estimated' }, 'b1')!;
		expect(s).toMatchObject({ kind: 'lane', id: 'surface-2003', layer: 'lanes', title: 'Road surface', fact: 'Width estimated', data: { type: 'piece', ref: 'surface-2003', build: 'b1' } });
		expect(roadSelection('roads.surfaces_z15', { id: 2001, kind: 'deck', tier: 'inventoried' }, 'b1')).toMatchObject({ id: 'surface-2001', title: 'Bridge deck', fact: 'Width measured' });
		expect(roadSelection('roads.edges', { id: 5, kind: 'curb' }, 'b1')).toMatchObject({ id: 'edge-5', title: 'Curb' });
		expect(roadSelection('roads.markings', { id: 9, kind: 'stop_bar' }, 'b1')).toMatchObject({ id: 'marking-9', title: 'Stop bar' });
		expect(roadSelection('roads.crosswalks', { id: 11 }, 'b1')).toMatchObject({ id: 'marking-11', title: 'Crosswalk' });
		expect(roadSelection('roads.lines', { id: 1002, class: 'secondary', lanes: 4, conflict: true }, 'b1')).toMatchObject({ id: 'line-1002', title: 'Arterial', fact: '4 lanes · sources disagree' });
		expect(roadSelection('roads.surfaces', { id: 1 }, null)).toBeNull();
		expect(roadSelection('roads.arrows', { id: 1 }, 'b1')).toBeNull();
		expect(roadSelection('roads.surfaces', { id: 'x' }, 'b1')).toBeNull();
		expect(roadSelection(undefined, { id: 1 }, 'b1')).toBeNull();
	});
	it('paving opens a lot or a way, and not a stall', () => {
		expect(pavingSelection('roads.paving_lots', { id: 84, material: 'asphalt' })).toMatchObject({ kind: 'paving', id: 'lot:w42', title: 'Parking lot', fact: 'asphalt', data: { type: 'paving', kind: 'lot', id: 'w42' } });
		expect(pavingSelection('roads.paving_lots', { id: 85, material: 'unknown' })).toMatchObject({ id: 'lot:r42' });
		expect(pavingSelection('roads.paving_ways', { id: 9001, kind: 'driveway', material: 'concrete' })).toMatchObject({ id: 'way:9001', title: 'Driveway', data: { kind: 'way', id: '9001' } });
		expect(pavingSelection('roads.paving_stalls', { id: 1 })).toBeNull();
		expect(pavingSelection('roads.paving_lots', {})).toBeNull();
	});
	it("makes the contributions' own layers clickable: roads at lane priority, paving without its stalls", () => {
		const road = pickableRoadLayers();
		expect(road).toEqual(expect.arrayContaining(['roads.surfaces.z16.asphalt', 'roads.surfaces.z15.asphalt', 'roads.decks.z16.fill', 'roads.markings.solid', 'roads.markings.crosswalk', 'roads.lines.line', 'lanes-conflict']));
		expect(new Set(road).size).toBe(road.length);
		const paving = pickablePavingLayers();
		expect(paving).toEqual(expect.arrayContaining(['roads.paving_lots', 'roads.paving_ways']));
		expect(paving).not.toContain('roads.paving_stalls');
	});
});

describe('turn arrows', () => {
	const cases: [string, string | null][] = [
		['left', 'L'],
		['through', 'T'],
		['right', 'R'],
		['left;through', 'LT'],
		['through;right', 'TR'],
		['left;through;right', 'LTR'],
		['slight_left;through', 'LT'],
		['sharp_right', 'R'],
		['reverse;left', 'LU'],
		['through;merge_to_left', 'T'],
		['merge_to_right', null],
		['none', null],
		['', null],
		['none;left', 'L']
	];
	it('are the letters of the arrows a lane carries', () => {
		for (const [turns, letters] of cases) expect(arrowImageId(turns), turns).toBe(letters === null ? null : `lanes-arrow:${letters}`);
	});
	it('the style expression picks the same image as the function, for every case', () => {
		const e = createExpression(arrowImageExpression() as never, { type: 'string' } as never);
		expect(e.result).toBe('success');
		const expression = (e as { value: { evaluate(g: object, f: object): string } }).value;
		for (const [turns] of cases) {
			const got = expression.evaluate({ zoom: 18 }, { type: 1, properties: { turns }, id: 1 });
			expect(got, turns).toBe(`lanes-arrow:${arrowImageId(turns)?.slice('lanes-arrow:'.length) ?? ''}`);
		}
		// A feature with no turns at all draws the empty image.
		expect(expression.evaluate({ zoom: 18 }, { type: 1, properties: {}, id: 2 })).toBe('lanes-arrow:');
	});
	it('every combination has an image, and an image names its arrows', () => {
		expect(ARROW_IMAGES).toHaveLength(15);
		expect(new Set(ARROW_IMAGES).size).toBe(15);
		for (const id of ARROW_IMAGES) expect(arrowsOfImage(id).length, id).toBeGreaterThan(0);
		expect(arrowsOfImage('lanes-arrow:LT')).toEqual(['left', 'through']);
		expect(arrowsOfImage('lanes-conflict')).toEqual([]);
		for (const turns of ['left', 'through;right', 'reverse', 'left;through;right;reverse']) expect(ARROW_IMAGES).toContain(arrowImageId(turns));
		expect(turnArrows('through;left')).toEqual(['left', 'through']);
	});
});

describe('its own layers', () => {
	it('add only what the bake holds: ▲ in points from z14, arrows in labels from z17.5, hidden until it is on', () => {
		const all = ownLayers({ lines: true, arrows: true });
		expect(all.map((l) => [l.slot, l.layer.id])).toEqual([
			['points', 'lanes-conflict'],
			['labels', 'lanes-arrows']
		]);
		expect(all[0].layer).toMatchObject({ source: 'landscape', 'source-layer': 'roads.lines', minzoom: 14, filter: ['==', ['get', 'conflict'], true] });
		expect(all[1].layer).toMatchObject({ 'source-layer': 'roads.arrows', minzoom: 17.5 });
		for (const l of all) expect((l.layer as { layout: { visibility: string } }).layout.visibility).toBe('none');
		expect(ownLayers({ lines: false, arrows: true }).map((l) => l.layer.id)).toEqual(['lanes-arrows']);
		expect(ownLayers({ lines: true, arrows: false }).map((l) => l.layer.id)).toEqual(['lanes-conflict']);
		expect(ownLayers({ lines: false, arrows: false })).toEqual([]);
	});
});

describe('the icon', () => {
	it('is Phosphor’s Arrows Split, duotone, exactly as phosphor-svelte ships it', () => {
		const require = createRequire(import.meta.url);
		const dir = dirname(require.resolve('phosphor-svelte/package.json'));
		const src = readFileSync(join(dir, 'lib', `${ARROWS_SPLIT.name}Icon.svelte`), 'utf8');
		const branch = /weight === "duotone"\}\s*([\s\S]*?)\{:else/.exec(src)?.[1] ?? '';
		const paths = [...branch.matchAll(/<path d="([^"]+)"([^>]*)\/>/g)];
		expect(ARROWS_SPLIT.tone).toBe(paths.find((p) => p[2].includes('opacity="0.2"'))?.[1]);
		expect(ARROWS_SPLIT.line).toBe(paths.find((p) => !p[2].includes('opacity'))?.[1]);
	});
});
