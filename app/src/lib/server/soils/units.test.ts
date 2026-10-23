import { describe, expect, it } from 'vitest';
import { componentLabel, CREDIT, mapUnitCard, mixText, REGULATORY, unitAt, type Sql } from './units.js';

/** A stand-in for the tagged template: answers by what the statement reads. */
function fake(tables: string[], rows: Record<string, unknown[]>): { sql: Sql; calls: string[] } {
	const calls: string[] = [];
	const sql: Sql = async (strings, ...values) => {
		const text = strings.join('?').replace(/\s+/g, ' ').trim();
		calls.push(text);
		if (text.startsWith('select to_regclass')) return [{ ok: tables.includes(values[0]) }];
		const key = Object.keys(rows).find((k) => text.includes(k));
		return key ? (rows[key] as never[]) : [];
	};
	return { sql, calls };
}

const UNIT = {
	mukey: '2700001',
	musym: 'TeA',
	muname: 'Testville silt loam, 0 to 1 percent slopes',
	mukind: 'Consociation',
	farmlndcl: 'Prime farmland if irrigated',
	slopegraddcp: 1,
	aws0100wta: 17.44,
	drclassdcd: 'Well drained',
	hydgrpdcd: 'B/D',
	hydclprs: 0,
	restr_kind: 'Duripan',
	restr_top_cm: 60,
	restr_hard: 'Indurated',
	c_aws: 3,
	hsg_dual: true,
	area_in_box_ha: 250.4,
	dom_cokey: 'c1',
	misc: null,
	areasymbol: 'ID001',
	areaname: 'Ada County Area, Idaho',
	saverest: '2025-09-23 00:00:00',
	saversion: 24,
	scale: 24000
};
const COMPONENTS = [
	{ cokey: 'c1', compname: 'Testville', comppct_r: 62, majcomp: true, drainagecl: 'Well drained', slope_r: 1, hydricrating: 'No', texture: 'Silt loam' },
	{ cokey: 'c2', compname: 'Samplon', comppct_r: 38, majcomp: true, drainagecl: 'Well drained', slope_r: 2, hydricrating: 'No', texture: 'Fine sandy loam' }
];
const TABLES = ['soils.map_unit', 'soils.polygon', 'core.layer_version'];
const ROWS = {
	'from soils.map_unit m': [UNIT],
	'from core.layer_version': [{ credit: 'Soils: USDA NRCS, SSURGO (build)', license: 'public domain' }],
	'from soils.polygon p where p.mukey': [{ lng: -116.39, lat: 43.6 }],
	'from soils.component c': COMPONENTS
};

describe('the map unit at a point', () => {
	it('is null before the migration, outside the survey, and for a point that cannot be one', async () => {
		const none = fake([], {});
		expect(await unitAt(none.sql, -116.39, 43.6)).toBeNull();
		expect(none.calls).toHaveLength(1); // only the table check
		expect(await unitAt(fake(['soils.polygon'], {}).sql, -116.39, 43.6)).toBeNull();
		for (const [lng, lat] of [[Number.NaN, 43], [-116, Number.POSITIVE_INFINITY], [-300, 43], [-116, 91]]) {
			expect(await unitAt(fake(['soils.polygon'], { 'from soils.polygon p': [{ mukey: '1' }] }).sql, lng, lat)).toBeNull();
		}
	});

	it('names the unit, and says when it is not surveyed', async () => {
		const surveyed = fake(['soils.polygon'], { 'from soils.polygon p': [{ mukey: '2700001', musym: 'TeA', muname: 'Testville silt loam', misc: null }] });
		expect(await unitAt(surveyed.sql, -116.39, 43.6)).toEqual({ mukey: '2700001', symbol: 'TeA', name: 'Testville silt loam', surveyed: true });
		const notcom = fake(['soils.polygon'], { 'from soils.polygon p': [{ mukey: '2700009', musym: 'NOTCOM', muname: 'No Digital Data Available', misc: 'nodata' }] });
		expect((await unitAt(notcom.sql, -116.39, 43.6))?.surveyed).toBe(false);
	});
});

describe('a soil card', () => {
	it('is null before the soils tables, for a unit that is not there, and for a key that cannot be one', async () => {
		const empty = fake([], {});
		expect(await mapUnitCard(empty.sql, '2700001')).toBeNull();
		expect(empty.calls).toHaveLength(1);
		expect(await mapUnitCard(fake(['soils.map_unit'], {}).sql, '2700001')).toBeNull();
		for (const key of ['', 'x', '1.5', '-3', '1234567890', "1'; drop table x; --"]) expect(await mapUnitCard(fake(TABLES, ROWS).sql, key), key).toBeNull();
	});

	it("gathers the dominant soil, the mix, texture, restriction, farmland, hydric rating, survey and the build's credit", async () => {
		const { sql, calls } = fake(TABLES, ROWS);
		const card = (await mapUnitCard(sql, '2700001'))!;
		expect(card).toMatchObject({
			mukey: '2700001',
			symbol: 'TeA',
			name: 'Testville silt loam, 0 to 1 percent slopes',
			surveyed: true,
			dominant_share: 62,
			mix: '62% Testville silt loam, 38% Samplon fine sandy loam',
			drainage: 'Well drained',
			hydrologic_group: 'B/D',
			hydrologic_dual: true,
			farmland: 'Prime farmland if irrigated',
			water_cm: 17.44,
			water_class: 3,
			restriction: { kind: 'Duripan', top_cm: 60, hard: 'Indurated' },
			hydric: 'No',
			hydric_percent: 0,
			credit: 'Soils: USDA NRCS, SSURGO (build)',
			license: 'public domain',
			note: REGULATORY,
			centre: [-116.39, 43.6]
		});
		expect(card.dominant).toMatchObject({ name: 'Testville', texture: 'Silt loam', percent: 62, label: '62% Testville silt loam' });
		expect(card.survey).toEqual({ symbol: 'ID001', name: 'Ada County Area, Idaho', saverest: '2025-09-23 00:00:00', version: 24, scale: 24000 });
		expect(card.components).toHaveLength(2);
		// It reads the stored tables: nothing joined to parcels, owners or addresses.
		expect(calls.join('\n')).not.toMatch(/parcel|assessor|owner|address/i);
	});

	it('puts the dominant component first even when another has the larger share, and takes the default credit without a build', async () => {
		const swapped = [{ ...COMPONENTS[0], comppct_r: 30 }, { ...COMPONENTS[1], comppct_r: 70 }];
		const { sql } = fake(['soils.map_unit'], { 'from soils.map_unit m': [UNIT], 'from soils.component c': swapped });
		const card = (await mapUnitCard(sql, '2700001'))!;
		expect(card.dominant?.name).toBe('Testville');
		expect(card.mix).toBe('30% Testville silt loam, 70% Samplon fine sandy loam');
		expect(card.credit).toBe(CREDIT);
		expect(card.license).toBeNull();
		expect(card.centre).toBeNull();
	});

	it('says "not surveyed" for NRCS\'s No Digital Data area, and sets nothing else', async () => {
		const { sql } = fake(TABLES, { ...ROWS, 'from soils.map_unit m': [{ ...UNIT, mukey: '2700009', misc: 'nodata', muname: 'No Digital Data Available' }] });
		const card = (await mapUnitCard(sql, '2700009'))!;
		expect(card.surveyed).toBe(false);
		expect(card).toMatchObject({ dominant: null, components: [], mix: null, drainage: null, restriction: null, hydric: null, water_cm: null, note: REGULATORY });
	});

	it('has no mix for a single component, and a card with no restriction says none', async () => {
		const { sql } = fake(TABLES, { ...ROWS, 'from soils.map_unit m': [{ ...UNIT, restr_kind: null, restr_top_cm: null, restr_hard: null }], 'from soils.component c': [COMPONENTS[0]] });
		const card = (await mapUnitCard(sql, '2700001'))!;
		expect(card.mix).toBeNull();
		expect(card.restriction).toBeNull();
	});
});

describe('the wording helpers', () => {
	it('label a component by its share, name and texture', () => {
		expect(componentLabel({ name: 'Purdam', percent: 61.6, texture: 'Silt loam' })).toBe('62% Purdam silt loam');
		expect(componentLabel({ name: 'Rock outcrop', percent: null, texture: null })).toBe('Rock outcrop');
		expect(mixText([{ label: 'a' }])).toBeNull();
		expect(mixText([{ label: '62% A silt loam' }, { label: '38% B silt loam' }])).toBe('62% A silt loam, 38% B silt loam');
	});
});
