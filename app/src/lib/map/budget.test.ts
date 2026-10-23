import { describe, expect, it } from 'vitest';
import { LAYER_DEFS } from '#lib/layers/registry.js';
import type { Palette } from './materials.js';
import {
	EXEMPTIONS,
	REFERENCE_INDICATORS,
	REFERENCES,
	distanceRows,
	foundPalettes,
	formatTable,
	indicatorRows,
	paletteIndicators,
	paletteSubjects,
	referenceSubjects
} from './budget.js';

const keepsValley = (owner: string) => LAYER_DEFS.some((d) => d.id === owner && d.keepsValley);
const palettes = foundPalettes();
const subjects = [...referenceSubjects(), ...paletteSubjects(palettes)];
const rows = distanceRows(subjects);
const ind = indicatorRows([...REFERENCE_INDICATORS, ...paletteIndicators(palettes, keepsValley)]);

describe('the colour budget (docs/14 §14.4)', () => {
	it('prints the table', () => {
		console.log(formatTable(rows, ind));
		expect(rows.length).toBeGreaterThan(0);
	});

	it('every colour clears its bar, except by a named form exemption', () => {
		const failing = rows.filter((r) => r.verdict === 'fail').map((r) => `${r.owner} ${r.subject} ${r.color} (${r.look}) vs ${r.against} ${r.reference}: ΔE ${r.deltaE.toFixed(1)} < ${r.min}`);
		expect(failing).toEqual([]);
	});

	it('only the four named form exemptions are ever used', () => {
		const names = new Set(EXEMPTIONS.map((e) => e.name));
		expect(names.size).toBe(4);
		for (const r of rows.filter((r) => r.verdict === 'exempt')) expect(names.has(r.exemption ?? '')).toBe(true);
	});

	it('knows its references: 13 routes and ghosts, 11 + 11 street shades, teal, amber, magenta', () => {
		const n = (g: string) => REFERENCES.filter((r) => r.group === g).length;
		expect([n('route'), n('ghost'), n('streets (alone)'), n('streets (slate)'), n('teal'), n('amber'), n('magenta')]).toEqual([13, 13, 11, 11, 1, 1, 1]);
	});

	it('the tree greens are checked against every route colour and the accents', () => {
		const greens = rows.filter((r) => r.owner === 'trees');
		expect(greens.length).toBe(9 * REFERENCES.length);
		expect(greens.every((r) => r.verdict === 'pass')).toBe(true);
	});

	it('Keep-Valley indicators reach 3:1 against the ground band, or name their halo or ring', () => {
		expect(ind.filter((r) => r.verdict === 'fail')).toEqual([]);
		// The two reference indicators need theirs: the disc edge and fence post are under 3:1 on lawn alone.
		expect(ind.some((r) => r.verdict === 'halo')).toBe(true);
	});

	it('catches a colour too close to a route, and exempts none by accident', () => {
		const bad: Palette = { id: 'probe', colors: [{ name: 'near blue', valley: '#2b79d6', use: 'fill' }] };
		const probe = distanceRows(paletteSubjects([bad]));
		expect(probe.some((r) => r.verdict === 'fail' && r.against === 'route')).toBe(true);
		expect(probe.every((r) => r.verdict !== 'exempt')).toBe(true);
	});

	it('a water colour near the speed ramp is exempt only against the streets', () => {
		const water: Palette = { id: 'water', colors: [{ name: 'water body', valley: '#2c7fd0', use: 'fill' }] };
		const r = distanceRows(paletteSubjects([water]));
		expect(r.filter((x) => x.verdict === 'exempt').every((x) => x.against.startsWith('streets'))).toBe(true);
		expect(r.some((x) => x.verdict === 'exempt')).toBe(true);
	});

	it('every palette found by glob is well formed', () => {
		for (const p of palettes) {
			expect(p.id).toMatch(/^[a-z]+(\.[a-z0-9_-]+)?$/);
			for (const c of p.colors) expect(c.valley).toMatch(/^#[0-9a-f]{6}$/i);
		}
	});
});
