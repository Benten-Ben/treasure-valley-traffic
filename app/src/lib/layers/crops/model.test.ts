import { describe, expect, it } from 'vitest';
import { fieldSelection, fmtAcres, groupInYear, growthText, howSure, julyText, methodNote, platText, rotationText, subtitle, yearsOf, cropNow, type FieldYear } from './model.js';

const hay = (year: number): FieldYear => ({ year, code: 36, name: 'Alfalfa', group: 'hay' });
const years = (groups: string[], first = 2018): FieldYear[] => groups.map((group, i) => ({ year: first + i, code: 1, name: null, group }));

describe('the field card words', () => {
	it('says "Estimated field · 24 acres · Canyon County"', () => {
		expect(subtitle(24.2, 'Canyon')).toBe('Estimated field · 24 acres · Canyon County');
		expect(subtitle(1, null)).toBe('Estimated field · 1 acre');
		expect(subtitle(null, 'Ada')).toBe('Estimated field · size unknown · Ada County');
		expect(fmtAcres(7.2359)).toBe('7.2 acres');
		expect(fmtAcres(1234.4)).toBe('1,234 acres');
	});

	it("names this year's crop from the CDL, else its group", () => {
		expect(cropNow({ years: [hay(2024), { year: 2025, code: 36, name: 'Alfalfa', group: 'hay' }] })).toEqual({ year: 2025, name: 'Alfalfa', group: 'hay' });
		expect(cropNow({ years: years(['corn', 'grain']) })).toMatchObject({ year: 2019, name: 'Grain' });
		expect(cropNow({ years: [] })).toBeNull();
	});

	it('writes the rotation as runs', () => {
		expect(rotationText(years(['hay', 'hay', 'hay', 'hay', 'hay', 'hay', 'pasture', 'developed']))).toBe('Hay 2018–2023 → Pasture 2024 → Built 2025');
		expect(rotationText(years(Array(8).fill('corn')))).toBe('Corn in all eight years');
		expect(rotationText(years(['corn', 'grain', 'corn']))).toBe('Corn 2018 → Grain 2019 → Corn 2020');
		expect(rotationText([])).toBe('');
	});

	it("says how sure USDA's map is, for the newest year held", () => {
		expect(howSure({})).toBeNull();
		expect(howSure({ '2019': 0.9, '2025': 0.541 })).toMatchObject({ year: 2025, word: 'Somewhat sure', text: "Somewhat sure: USDA's 2025 map agrees with this field's crop on 54% of its pixels." });
		expect(howSure({ '2025': 0.97 })!.word).toBe('Fairly sure');
		expect(howSure({ '2025': 0.2 })!.word).toBe('Not very sure');
	});

	it('reports the July state in its own year', () => {
		expect(julyText({ year: 2025, state: 'bare', ndvi: 0.26 })).toBe('July 2025: bare or harvested (greenness 0.26)');
		expect(julyText({ year: 2025, state: 'green', ndvi: null })).toBe('July 2025: green');
		expect(julyText(null)).toBeNull();
	});

	it('reports growth and plats as stored: a "by" year, permits, an unconfirmed note', () => {
		expect(growthText({ growth: 'built_over', growth_detail: { developed_by: 2024 } })).toBe('Built over: developed by 2024');
		expect(growthText({ growth: 'being_built', growth_detail: { permits: 19, permit_years: [2021, 2022] } })).toBe('Being built: 19 new-construction permits since 2021');
		expect(growthText({ growth: 'being_built', growth_detail: { permits: 1 } })).toBe('Being built: 1 new-construction permit');
		expect(growthText({ growth: 'farmed', growth_detail: { unconfirmed: 'x' } })).toBe('Developed in the newest map, but no permits found');
		expect(growthText({ growth: 'farmed', growth_detail: null })).toBeNull();
		expect(platText(null)).toBeNull();
		expect(platText({ approved: 0.62, pending: 0, built: 0, plats: [{ id: 1, name: 'Sunny Acres No. 2', status: 'Approved', applied_on: null, share: 0.62 }] })).toBe('62% under an approved plat (Sunny Acres No. 2)');
		expect(platText({ approved: 0.005, pending: 0.004, built: 0, plats: [] })).toBeNull();
	});

	it('notes the 2024 method change from 2024 on', () => {
		expect(methodNote(2023)).toBeNull();
		expect(methodNote(2024)).toBe('2024–25 maps use a new USDA method');
		expect(methodNote(2025)).toBe('2024–25 maps use a new USDA method');
	});
});

describe('the switcher and the click', () => {
	it('offers the edition window, oldest first', () => {
		expect(yearsOf({ year: 2025, first_year: 2018 })).toEqual([2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]);
		expect(yearsOf({ year: null, first_year: null })).toEqual([]);
	});

	it("reads a field's group in a year from its letters, the group itself for the newest year", () => {
		const p = { y: 'hhhhhhpd', g: 'developed' };
		expect(groupInYear(p, 2018, 2018, 2025)).toBe('hay');
		expect(groupInYear(p, 2024, 2018, 2025)).toBe('pasture');
		expect(groupInYear(p, 2025, 2018, 2025)).toBe('developed');
		expect(groupInYear({ y: 'c-' }, 2019, 2018, 2019)).toBeUndefined();
		expect(groupInYear({ y: 'c' }, 2030, 2018, 2025)).toBeUndefined();
	});

	it('makes a selection of kind crop, owned by the layer, with the click point', () => {
		const s = fieldSelection({ a: 24, g: 'hay', n: 'Alfalfa' }, 5, 2025, [-116.6, 43.6]);
		expect(s).toMatchObject({ kind: 'crop', id: '5', layer: 'crops', title: 'Estimated field', fact: '24 acres · Alfalfa', at: [-116.6, 43.6] });
		expect(fieldSelection({ a: 3, g: 'developed' }, 6, 2025).fact).toBe('3 acres');
	});
});
