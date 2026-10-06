import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
	CLAY_SURFACE,
	cielab,
	cielabToHex,
	contrast,
	deltaE,
	ghostColor,
	INK,
	interpolateLab,
	mixLab,
	mixOklab,
	oklab,
	oklabToHex,
	oklch,
	parseHex,
	roundHalfEven,
	toHex
} from './color.js';

/** docs/14 itself: the acceptance is "reproduces the ghost column in §14.4", so the test reads that table. */
const DOC = readFileSync(new URL('../../../../docs/14-ui-v2.md', import.meta.url), 'utf8');

interface Slot {
	n: number;
	name: string;
	hex: string;
	onClay: number;
	ghost: string;
	text: 'white' | 'ink';
	onPlate: number;
	halo: boolean;
}

/** The rows of §14.4's palette table: `| 1 | blue | `#2a78d6` | 3.79 | `#b1c6e2` | white 4.42, **halo** |`. */
function paletteTable(): Slot[] {
	const re = /^\| (\d+) \| (\w+) \| `(#[0-9a-f]{6})` \| ([\d.]+) \| `(#[0-9a-f]{6})` \| (white|ink) ([\d.]+)(, \*\*halo\*\*)? \|$/;
	return DOC.split('\n')
		.map((l) => re.exec(l.trim()))
		.filter((m): m is RegExpExecArray => m !== null)
		.map((m) => ({
			n: Number(m[1]),
			name: m[2],
			hex: m[3],
			onClay: Number(m[4]),
			ghost: m[5],
			text: m[6] as 'white' | 'ink',
			onPlate: Number(m[7]),
			halo: Boolean(m[8])
		}));
}

const SLOTS = paletteTable();

describe('color', () => {
	it('reads all 13 palette slots from docs/14 §14.4', () => {
		expect(SLOTS.map((s) => s.n)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]);
		expect(SLOTS[0]).toMatchObject({ name: 'blue', hex: '#2a78d6', ghost: '#b1c6e2' });
	});

	it('ghostColor() reproduces the ghost column within ΔE 1 (in fact exactly)', () => {
		for (const s of SLOTS) {
			const g = ghostColor(s.hex);
			expect(deltaE(g, s.ghost), `${s.name}: ${g} vs ${s.ghost}`).toBeLessThanOrEqual(1);
			expect(g, s.name).toBe(s.ghost);
			// Each ghost sits at least ΔE 14 from clay: the first 0.1% step past it, or the 30% floor
			// for colors already that far at 30% (yellow and lime).
			const d = deltaE(g, CLAY_SURFACE);
			expect(d).toBeGreaterThanOrEqual(14);
			expect(d < 14.6 || deltaE(mixOklab(CLAY_SURFACE, s.hex, 0.3), g) < 0.5, `${s.name}: ΔE ${d.toFixed(2)} from clay`).toBe(true);
		}
		// The unknown-route gray and any future color go through the same formula.
		expect(deltaE(ghostColor('#8a857c'), CLAY_SURFACE)).toBeGreaterThanOrEqual(14);
		// A color already that close to the surface stays itself.
		expect(ghostColor('#f0e9de')).toBe('#f0e9de');
	});

	it('measures contrast as the table does (on clay, and badge numerals on the plate)', () => {
		for (const s of SLOTS) {
			expect(contrast(s.hex, CLAY_SURFACE), s.name).toBeCloseTo(s.onClay, 2);
			const text = s.text === 'white' ? '#ffffff' : INK;
			expect(contrast(s.hex, text), s.name).toBeCloseTo(s.onPlate, 2);
			expect(contrast(s.hex, text) < 4.5, `${s.name} halo`).toBe(s.halo);
		}
	});

	it('OKLab: distances, round trips, mixes', () => {
		expect(deltaE('#2a78d6', '#2a78d6')).toBe(0);
		expect(deltaE('#ffffff', '#000000')).toBeCloseTo(100, 0);
		expect(deltaE('#2a78d6', '#eb6834')).toBeCloseTo(deltaE('#eb6834', '#2a78d6'), 10);
		for (const s of SLOTS) expect(oklabToHex(oklab(s.hex))).toBe(s.hex);
		expect(mixOklab('#2a78d6', '#eb6834', 0)).toBe('#2a78d6');
		expect(mixOklab('#2a78d6', '#eb6834', 1)).toBe('#eb6834');
		expect(oklch('#ffffff').L).toBeCloseTo(1, 4);
		expect(oklch('#ffffff').C).toBeCloseTo(0, 4);
	});

	it('hex parsing and Python-style rounding', () => {
		expect(parseHex('#fff')).toEqual([1, 1, 1]);
		expect(toHex([1, 0.5, 0])).toBe('#ff8000');
		expect(roundHalfEven(2.5)).toBe(2);
		expect(roundHalfEven(3.5)).toBe(4);
		expect(roundHalfEven(2.4)).toBe(2);
		expect(() => parseHex('blue')).toThrow();
	});

	it('CIELAB as MapLibre computes it, and interpolate-lab between stops', () => {
		for (const s of SLOTS) expect(cielabToHex(cielab(s.hex))).toBe(s.hex);
		expect(cielab('#ffffff')[0]).toBeCloseTo(100, 3);
		expect(cielab('#000000')).toEqual([0, 0, 0]);
		const stops: [number, string][] = [
			[20, '#9fc2f0'],
			[25, '#7baff0'],
			[75, '#062d59']
		];
		expect(interpolateLab(stops, 5)).toBe('#9fc2f0');
		expect(interpolateLab(stops, 20)).toBe('#9fc2f0');
		expect(interpolateLab(stops, 25)).toBe('#7baff0');
		expect(interpolateLab(stops, 90)).toBe('#062d59');
		expect(interpolateLab(stops, 50)).toBe(mixLab('#7baff0', '#062d59', 0.5));
		const mid = interpolateLab(stops, 22.5);
		expect(deltaE(mid, '#9fc2f0')).toBeGreaterThan(0);
		expect(deltaE(mid, '#7baff0')).toBeGreaterThan(0);
	});
});
