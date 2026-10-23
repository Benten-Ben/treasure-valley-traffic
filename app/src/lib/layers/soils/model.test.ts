import { describe, expect, it } from 'vitest';
import type { SoilCard } from '#lib/server/soils/units.js';
import { PRIORITY } from '../types.js';
import * as server from '#lib/server/soils/units.js';
import {
	CREDIT,
	DEFAULT_SHOW_BY,
	groupText,
	hydricText,
	NOT_SURVEYED,
	REGULATORY,
	restrictionText,
	SHOW_BY,
	SHOW_BY_DEFS,
	soilSelection,
	surveyText,
	waterText,
	WATER_CLASS_TEXT,
	WATER_NOTE
} from './model.js';

describe('the Soils words', () => {
	it('say it is mapped soil, not a site test, not for regulatory decisions, and credit NRCS (the server\'s card says the same)', () => {
		expect(REGULATORY).toBe('Mapped soil, not a site test; not for regulatory decisions');
		expect(CREDIT).toBe('Soils: USDA NRCS, Soil Survey Geographic Database (SSURGO)');
		expect(server.REGULATORY).toBe(REGULATORY);
		expect(server.CREDIT).toBe(CREDIT);
		expect([...server.WATER_CLASS_TEXT]).toEqual([...WATER_CLASS_TEXT]);
		expect(NOT_SURVEYED).toMatch(/^Not surveyed/);
	});

	it('word the water-held classes as our scaling to the top metre', () => {
		expect(WATER_NOTE).toMatch(/our scaling to the top metre/i);
		expect(SHOW_BY_DEFS.aws.note).toBe(WATER_NOTE);
		expect(SHOW_BY_DEFS.aws.title).toMatch(/top metre/);
		expect(waterText({ water_cm: 17.44, water_class: 3 })).toBe('17.4 cm in the top metre (15 to 20 cm)');
		expect(waterText({ water_cm: null, water_class: null })).toBeNull();
		expect(waterText({ water_cm: 3, water_class: null })).toBe('3 cm in the top metre');
	});
});

describe('the Show by properties', () => {
	it('are the five of the README, with the same tile property names, each level named', () => {
		expect([...SHOW_BY]).toEqual(['restr', 'drain', 'aws', 'farm', 'hsg']);
		expect(SHOW_BY).toContain(DEFAULT_SHOW_BY);
		const levels = { restr: 5, drain: 5, aws: 5, farm: 3, hsg: 4 };
		for (const k of SHOW_BY) {
			const d = SHOW_BY_DEFS[k];
			expect(d.key).toBe(k);
			expect(d.levels, k).toHaveLength(levels[k]);
			expect(d.steps, k).toHaveLength(levels[k]);
			for (const l of d.levels) expect(l).toBeTruthy();
		}
		// The patterns say what each one means.
		expect(SHOW_BY_DEFS.restr.patterns.map((p) => p.key)).toEqual(['hatch', 'stipple']);
		expect(SHOW_BY_DEFS.hsg.patterns[0].text).toMatch(/Dual group/);
	});
});

describe('a click on a map unit', () => {
	it('selects it as a soil, owned by the layer, with the symbol for the tooltip', () => {
		const s = soilSelection({ mukey: '2700001', symbol: 'TeA', restr: 2 }, [-116.39, 43.6])!;
		expect(s).toMatchObject({ kind: 'soil', id: '2700001', layer: 'soils', title: 'Soil TeA', fact: 'Map unit TeA', source: 'USDA NRCS Soil Survey (SSURGO)', at: [-116.39, 43.6] });
		expect(PRIORITY.soil).toBe(10);
		expect(Math.min(...Object.values(PRIORITY))).toBe(PRIORITY.soil); // everything else is picked first
	});

	it('takes a numeric key, and refuses one that cannot be a key', () => {
		expect(soilSelection({ mukey: 2700001 })?.id).toBe('2700001');
		expect(soilSelection({ mukey: 2700001 })?.title).toBe('Soil map unit');
		for (const m of [undefined, '', 'abc', '1.5', "1'; --", '12345678901']) expect(soilSelection({ mukey: m as never }), String(m)).toBeNull();
	});
});

const CARD = { water_cm: null, water_class: null, hydrologic_group: 'B', hydrologic_dual: false, hydric: null, hydric_percent: null, survey: null } as unknown as SoilCard;

describe('the card\'s lines', () => {
	it('say what the hardpan or bedrock is and from how deep, or that none was found', () => {
		expect(restrictionText({ kind: 'duripan', top_cm: 60, hard: 'Indurated' })).toBe('Duripan from 60 cm (indurated)');
		expect(restrictionText({ kind: 'Lithic bedrock', top_cm: null, hard: null })).toBe('Lithic bedrock');
		expect(restrictionText(null)).toMatch(/^None found/);
	});

	it('say a dual hydrologic group is D where undrained', () => {
		expect(groupText({ ...CARD, hydrologic_group: 'B/D', hydrologic_dual: true })).toBe('B/D, D where undrained');
		expect(groupText(CARD)).toBe('B');
		expect(groupText({ ...CARD, hydrologic_group: null })).toBeNull();
	});

	it('give the hydric rating as a row', () => {
		expect(hydricText({ hydric: 'Partially hydric', hydric_percent: 40 })).toBe('Partially hydric (dominant component); 40% hydric components');
		expect(hydricText({ hydric: 'No', hydric_percent: null })).toBe('No (dominant component)');
		expect(hydricText({ hydric: null, hydric_percent: 0 })).toBe('0% hydric components');
		expect(hydricText({ hydric: null, hydric_percent: null })).toBeNull();
	});

	it('name the survey area, its version and scale', () => {
		expect(surveyText({ symbol: 'ID001', name: 'Ada County Area, Idaho', saverest: '2025-09-23 00:00:00', version: 24, scale: 24000 })).toBe('Ada County Area, Idaho (ID001), version 24 (2025-09-23), 1:24,000');
		expect(surveyText({ symbol: 'OR645', name: 'Malheur', saverest: null, version: null, scale: null })).toBe('Malheur (OR645)');
		expect(surveyText(null)).toBeNull();
	});
});
