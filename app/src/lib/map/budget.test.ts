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
	ownerOf,
	paletteIndicators,
	paletteSubjects,
	referenceSubjects
} from './budget.js';

const keepsValley = (owner: string) => LAYER_DEFS.some((d) => d.id === ownerOf(owner) && d.keepsValley);
const palettes = foundPalettes();
const subjects = [...referenceSubjects(), ...paletteSubjects(palettes)];
const rows = distanceRows(subjects);
const ind = indicatorRows([...REFERENCE_INDICATORS, ...paletteIndicators(palettes, keepsValley)]);

describe('the colour budget (docs/14 §14.4)', () => {
	it('prints the table', () => {
		console.log(formatTable(rows, ind));
		expect(rows.length).toBeGreaterThan(0);
	});

	// Misses from layers merged before this budget (Soils, Trails, Roads, Fences), waiting for the owner's call (#367:
	// a named form exemption, a narrower scope for base surfaces, or a new colour). A ratchet: a miss not listed fails, and a listed one that clears its bar fails too, so the list
	// only shrinks.
	const KNOWN_MISSES = [
		'fences fence post #6F685E (valley) vs streets (slate) slate 8',
		'fences fence post #6F685E (valley) vs streets (slate) slate 9',
		'fences fence post #6F685E (valley) vs streets (slate) slate 10',
		'fences fence post #6F685E (valley) vs streets (slate) slate 11',
		'fences estimated height #918a81 (valley) vs streets (slate) slate 5',
		'fences estimated height #918a81 (valley) vs streets (slate) slate 6',
		'fences estimated height #918a81 (valley) vs streets (slate) slate 7',
		'fences estimated height #918a81 (valley) vs streets (slate) slate 8',
		'fences estimated height #918a81 (valley) vs streets (slate) slate 9',
		'fences estimated height #918a81 (valley) vs streets (slate) slate 10',
		'fences estimated height #918a81 (valley) vs teal camera teal',
		'roads asphalt #989088 (valley) vs streets (slate) slate 5',
		'roads asphalt #989088 (valley) vs streets (slate) slate 6',
		'roads asphalt #989088 (valley) vs streets (slate) slate 7',
		'roads asphalt #989088 (valley) vs streets (slate) slate 8',
		'roads asphalt #989088 (valley) vs streets (slate) slate 9',
		'roads concrete #D2CEC6 (valley) vs streets (alone) blue 1',
		'roads concrete #D2CEC6 (valley) vs streets (slate) slate 1',
		'roads concrete #D2CEC6 (valley) vs streets (slate) slate 2',
		'roads concrete #D2CEC6 (valley) vs streets (slate) slate 3',
		'roads curb #E3D7C4 (valley) vs streets (slate) slate 1',
		'roads curb #E3D7C4 (valley) vs streets (slate) slate 2',
		'roads curb #E2D9CB (clay) vs streets (slate) slate 1',
		'roads curb #E2D9CB (clay) vs streets (slate) slate 2',
		'roads shoulder #BDB6AA (valley) vs streets (alone) blue 1',
		'roads shoulder #BDB6AA (valley) vs streets (slate) slate 1',
		'roads shoulder #BDB6AA (valley) vs streets (slate) slate 2',
		'roads shoulder #BDB6AA (valley) vs streets (slate) slate 3',
		'roads shoulder #BDB6AA (valley) vs streets (slate) slate 4',
		'roads shoulder #E2D9CB (clay) vs streets (slate) slate 1',
		'roads shoulder #E2D9CB (clay) vs streets (slate) slate 2',
		'roads dirt #826644 (valley) vs route route 11 #7f4315',
		'roads dirt #826644 (valley) vs streets (slate) slate 11',
		'roads marking on concrete #2b2a33 (valley) vs streets (alone) blue 11',
		'roads marking in Clay #2b2a33 (valley) vs streets (alone) blue 11',
		'roads deck casing #2b2a33 (valley) vs streets (alone) blue 11',
		'soils wash step 1 #bababa (valley) vs streets (alone) blue 1',
		'soils wash step 3 #757575 (valley) vs teal camera teal',
		'soils survey bounds #5a5a5a (valley) vs streets (slate) slate 11',
		'soils label #2b2a33 (valley) vs streets (alone) blue 11',
		'trails trail umber #6b4a2b (valley) vs route route 11 #7f4315'
	];

	it('every colour clears its bar, except by a named form exemption (or a listed miss the owner is deciding)', () => {
		const failing = rows.filter((r) => r.verdict === 'fail').map((r) => `${r.owner} ${r.subject} ${r.color} (${r.look}) vs ${r.against} ${r.reference}`);
		expect(failing.filter((f) => !KNOWN_MISSES.includes(f))).toEqual([]);
		expect(KNOWN_MISSES.filter((m) => !failing.includes(m))).toEqual([]);
	});

	it('only the named form exemptions are ever used', () => {
		const names = new Set(EXEMPTIONS.map((e) => e.name));
		expect(names.size).toBe(EXEMPTIONS.length);
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

	it('a palette id with a dot belongs to the layer before it, and an unknown use fails loudly', () => {
		expect(ownerOf('water.pond')).toBe('water');
		expect(() => paletteSubjects([{ id: 'x', colors: [{ name: 'a', valley: '#112233', use: 'marker' }] }])).toThrow(/unknown use/);
	});

	it('every palette found by glob is well formed', () => {
		for (const p of palettes) {
			expect(p.id).toMatch(/^[a-z]+(\.[a-z0-9_-]+)?$/);
			for (const c of p.colors) expect(c.valley).toMatch(/^#[0-9a-f]{6}$/i);
		}
	});
});
