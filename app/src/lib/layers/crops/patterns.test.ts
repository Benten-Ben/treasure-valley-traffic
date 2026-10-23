import { describe, expect, it } from 'vitest';
import { GROUPS } from './palette.js';
import { CELL, GROWTH_KEYS, imageId, PATTERN_KEYS, PATTERNS, PIXELS, rasterize, svgMarks } from './patterns.js';

const ink: [number, number, number] = [74, 70, 56];
const alpha = (px: Uint8ClampedArray, x: number, y: number) => px[(((y + PIXELS) % PIXELS) * PIXELS + ((x + PIXELS) % PIXELS)) * 4 + 3];

describe('the patterns', () => {
	it('give every group and every growth state one of its own', () => {
		expect(PATTERN_KEYS).toEqual([...GROUPS, ...GROWTH_KEYS]);
		expect(new Set(PATTERN_KEYS.map(imageId)).size).toBe(PATTERN_KEYS.length);
		expect(new Set(PATTERN_KEYS.map((k) => PATTERNS[k].look)).size).toBe(PATTERN_KEYS.length);
		for (const k of PATTERN_KEYS) expect(PATTERNS[k].key).toBe(k);
	});

	it('draw ink on part of the cell only, clear elsewhere, in the ink colour', () => {
		for (const k of PATTERN_KEYS) {
			const px = rasterize(PATTERNS[k], ink);
			expect(px.length).toBe(PIXELS * PIXELS * 4);
			const inked = [...Array(PIXELS * PIXELS).keys()].filter((i) => px[i * 4 + 3] > 127).length;
			const share = inked / (PIXELS * PIXELS);
			expect(share, k).toBeGreaterThan(0.03);
			expect(share, k).toBeLessThan(0.6);
			expect([px[0], px[1], px[2]]).toEqual(ink);
		}
	});

	it('repeat without a seam: the ink is the same on either side of the cell edge', () => {
		for (const k of PATTERN_KEYS) {
			const px = rasterize(PATTERNS[k], ink);
			// A mark that crosses the edge has ink on both sides of it, or neither does: check both pairs of edges.
			for (let i = 0; i < PIXELS; i++) {
				expect(Math.abs(alpha(px, PIXELS - 1, i) - alpha(px, 0, i)), `${k} column ${i}`).toBeLessThan(200);
				expect(Math.abs(alpha(px, i, PIXELS - 1) - alpha(px, i, 0)), `${k} row ${i}`).toBeLessThan(200);
			}
		}
	});

	it('differ from each other as pictures', () => {
		const alphas = PATTERN_KEYS.map((k) => Array.from(rasterize(PATTERNS[k], ink)).filter((_, i) => i % 4 === 3));
		for (let a = 0; a < alphas.length; a++)
			for (let b = a + 1; b < alphas.length; b++) {
				const diff = alphas[a].reduce((s, v, i) => s + Math.abs(v - alphas[b][i]), 0) / alphas[a].length;
				expect(diff, `${PATTERN_KEYS[a]}/${PATTERN_KEYS[b]}`).toBeGreaterThan(8);
			}
	});

	it('scale the ink by opacity', () => {
		const full = rasterize(PATTERNS.corn, ink, 1);
		const half = rasterize(PATTERNS.corn, ink, 0.5);
		const i = full.findIndex((v, n) => n % 4 === 3 && v === 255);
		expect(half[i]).toBeGreaterThanOrEqual(127);
		expect(half[i]).toBeLessThanOrEqual(128);
	});

	it('make the legend swatch from the same marks, nine cells of them', () => {
		for (const k of PATTERN_KEYS) {
			expect(svgMarks(PATTERNS[k]).length).toBe(PATTERNS[k].marks.length * 9);
			expect(CELL).toBe(16);
		}
		expect(svgMarks(PATTERNS.roots).every((m) => m.tag === 'circle' && m.fill)).toBe(true);
		expect(svgMarks(PATTERNS.fallow).every((m) => m.tag === 'circle' && !m.fill)).toBe(true);
	});
});
