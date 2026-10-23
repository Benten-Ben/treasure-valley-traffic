import { describe, expect, it } from 'vitest';
import { fieldCard, yearInfo, type Sql } from './fields.js';

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

const FIELD = {
	id: 16727,
	acres: 7.2359214,
	county: 'Canyon',
	first_year: 2018,
	crops: [36, 36, 36, 36, 36, 36, 176, 122],
	agree: { '2024': 0.435, '2025': 0.541 },
	july: { px: 301, ndvi: 0.26, year: 2025, state: 'bare' },
	growth: 'being_built',
	growth_detail: { rule: 'growth/1', permits: 19, developed_by: 2025, permit_years: [2021, 2022] },
	plat: null,
	valid_to: null,
	lng: -116.6455,
	lat: 43.6122,
	w: -116.647,
	s: 43.611,
	e: -116.644,
	n: 43.613
};

describe('the crop year', () => {
	it('says "not built" before the migration or a load, never failing', async () => {
		const none = { built: false, year: null, label: null, first_year: null, edition: null };
		expect(await yearInfo(fake([], {}).sql)).toEqual(none);
		expect(await yearInfo(fake(['farm.crop_year'], { 'from farm.crop_year': [] }).sql)).toEqual(none);
	});

	it("reads the newest year of the newest edition, with USDA's label", async () => {
		const { sql } = fake(['farm.crop_year'], { 'from farm.crop_year': [{ year: 2025, label: "2025 (USDA's newest)", first_year: 2018, edition: 'csb-2018-2025-rev23' }] });
		expect(await yearInfo(sql)).toEqual({ built: true, year: 2025, label: "2025 (USDA's newest)", first_year: 2018, edition: 'csb-2018-2025-rev23' });
	});
});

describe('a field card', () => {
	it('is null before the farm tables, for a field that is not there, and for an id that cannot be one', async () => {
		const empty = fake([], {});
		expect(await fieldCard(empty.sql, 5)).toBeNull();
		expect(empty.calls).toHaveLength(1); // only the table check
		expect(await fieldCard(fake(['farm.field'], {}).sql, 5)).toBeNull();
		for (const id of [0, -1, 1.5, Number.NaN, 2 ** 60]) expect(await fieldCard(fake(['farm.field'], { 'from farm.field f': [FIELD] }).sql, id)).toBeNull();
	});

	it("gathers the field's years with names and groups, the flags as stored, and the layer's credit", async () => {
		const { sql, calls } = fake(['farm.field', 'core.layer_version'], {
			'from farm.field f where f.id': [FIELD],
			'from farm.crop_class': [
				{ code: 36, name: 'Alfalfa', grp: 'hay' },
				{ code: 176, name: 'Grassland/Pasture', grp: 'pasture' },
				{ code: 122, name: 'Developed/Open Space', grp: 'developed' }
			],
			'from core.layer_version': [{ credit: 'USDA NASS Crop Sequence Boundaries 2018-2025', license: 'public domain' }]
		});
		const card = (await fieldCard(sql, 16727))!;
		expect(card.id).toBe(16727);
		expect(card).toMatchObject({ acres: 7.2359214, county: 'Canyon', growth: 'being_built', plat: null, valid_to: null, centre: [-116.6455, 43.6122], bbox: [-116.647, 43.611, -116.644, 43.613] });
		expect(card.years).toHaveLength(8);
		expect(card.years[0]).toEqual({ year: 2018, code: 36, name: 'Alfalfa', group: 'hay' });
		expect(card.years[6]).toEqual({ year: 2024, code: 176, name: 'Grassland/Pasture', group: 'pasture' });
		expect(card.years[7]).toEqual({ year: 2025, code: 122, name: 'Developed/Open Space', group: 'developed' });
		expect(card.agree).toEqual({ '2024': 0.435, '2025': 0.541 });
		expect(card.july).toEqual({ year: 2025, state: 'bare', ndvi: 0.26 });
		expect(card.growth_detail).toMatchObject({ permits: 19, developed_by: 2025 });
		expect(card.credit).toBe('USDA NASS Crop Sequence Boundaries 2018-2025');
		// It reads the stored columns: it joins nothing to permits, plats or parcels at request time.
		const text = calls.join('\n');
		expect(text).not.toMatch(/core\.plat|building_permit|parcel|assessor/i);
	});

	it('names a code it has no class for "other", and works without the layer-version table or a July state', async () => {
		const { sql } = fake(['farm.field'], { 'from farm.field f where f.id': [{ ...FIELD, july: null, agree: null, crops: [99, 36], first_year: 2024 }], 'from farm.crop_class': [{ code: 36, name: 'Alfalfa', grp: 'hay' }] });
		const card = (await fieldCard(sql, 1))!;
		expect(card.years).toEqual([
			{ year: 2024, code: 99, name: null, group: 'other' },
			{ year: 2025, code: 36, name: 'Alfalfa', group: 'hay' }
		]);
		expect(card.july).toBeNull();
		expect(card.agree).toEqual({});
		expect(card.credit).toBeNull();
	});
});
