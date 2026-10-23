import { describe, expect, it } from 'vitest';
import { oklch } from '#lib/map/color.js';
import { CLAY_SURFACE, distance, EDGE, FILL, GROUP_NAME, GROUPS, LETTER, simulate, VISION, type Vision } from './palette.js';

const VISIONS: (Vision | undefined)[] = [undefined, 'protan', 'deutan', 'tritan'];
const pairs = GROUPS.flatMap((a, i) => GROUPS.slice(i + 1).map((b) => [a, b] as const));

/** A pair this close would be hard to tell apart by colour alone; the patterns keep it readable, but report it. */
const MIN_NORMAL = 10;
const MIN_DEFICIENT = 6;

describe('the crop colours (K1)', () => {
	it('stand out from Clay, the surface they are drawn on', () => {
		for (const g of GROUPS) for (const v of VISIONS) expect(distance(FILL[g], CLAY_SURFACE, v), `${g} ${v ?? 'normal'}`).toBeGreaterThanOrEqual(9);
	});

	it('are told apart from each other, with normal vision', () => {
		for (const [a, b] of pairs) expect(distance(FILL[a], FILL[b]), `${a}/${b}`).toBeGreaterThanOrEqual(MIN_NORMAL);
	});

	it('are told apart with protan, deutan and tritan vision', () => {
		for (const v of VISIONS.filter((x): x is Vision => !!x)) for (const [a, b] of pairs) expect(distance(FILL[a], FILL[b], v), `${a}/${b} ${v}`).toBeGreaterThanOrEqual(MIN_DEFICIENT);
	});

	it('use no red or green pair: no group is hued like the other', () => {
		// "Never red/green": nothing in the palette sits in OKLCH red (hue ~ 15-40 degrees, chroma > .12) next to a green one.
		const hues = GROUPS.map((g) => ({ g, ...oklch(FILL[g]) }));
		const reds = hues.filter((x) => x.C > 0.12 && (x.h < 40 || x.h > 345));
		const greens = hues.filter((x) => x.C > 0.12 && x.h > 115 && x.h < 165);
		expect(reds.length === 0 || greens.length === 0, `reds ${reds.map((x) => x.g)} greens ${greens.map((x) => x.g)}`).toBe(true);
	});

	it('keep hay a cyan and corn a yellow, and every group named with a letter of its own', () => {
		expect(oklch(FILL.hay).h).toBeGreaterThan(190);
		expect(oklch(FILL.hay).h).toBeLessThan(230);
		expect(oklch(FILL.corn).h).toBeGreaterThan(85);
		expect(oklch(FILL.corn).h).toBeLessThan(110);
		expect(new Set(GROUPS.map((g) => LETTER[g])).size).toBe(GROUPS.length);
		for (const g of GROUPS) expect(GROUP_NAME[g].length).toBeGreaterThan(3);
		expect(EDGE).toBe('#fffbf4');
	});

	it('simulate deficiencies as the matrices say (greys stay grey, and the three differ)', () => {
		for (const v of Object.keys(VISION) as Vision[]) {
			const grey = simulate('#808080', v);
			const [r, g, b] = [1, 3, 5].map((i) => parseInt(grey.slice(i, i + 2), 16));
			expect(Math.max(r, g, b) - Math.min(r, g, b)).toBeLessThanOrEqual(3);
		}
		expect(new Set(['protan', 'deutan', 'tritan'].map((v) => simulate(FILL.hay, v as Vision))).size).toBe(3);
	});
});
