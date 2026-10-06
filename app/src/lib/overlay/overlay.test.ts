import { describe, expect, it } from 'vitest';
import { ShelfPacker } from '#lib/gl/atlas.js';
import { circumferenceAt, mercatorX, mercatorY, projectTo, pxPerSecond } from './project.js';
import { contrast, haloFor, needsHalo } from './sprites.js';

describe('overlay projection', () => {
	it('matches Web Mercator', () => {
		expect(mercatorX(-180)).toBe(0);
		expect(mercatorX(0)).toBe(0.5);
		expect(mercatorY(0)).toBeCloseTo(0.5, 12);
		expect(mercatorY(85.0511287798066)).toBeCloseTo(0, 9);
		expect(circumferenceAt(0)).toBeCloseTo(2 * Math.PI * 6371008.8, 3);
		expect(circumferenceAt(60)).toBeCloseTo(Math.PI * 6371008.8, 3);
	});

	it('projects through a column-major matrix in float64, with z in Mercator units', () => {
		// An orthographic matrix: x, y in [0, 1] → clip [-1, 1]; z scaled so 1000 m lifts y by a known amount.
		const zLift = 0.001; // clip units per Mercator-z unit … times the circumference below
		const m = new Float64Array([2, 0, 0, 0, 0, -2, 0, 0, 0, zLift, 0, 0, -1, 1, 0, 1]);
		const out = { x: 0, y: 0 };
		expect(projectTo(out, m, 0.25, 0.75, 0, 1, 800, 600)).toBe(true);
		expect(out.x).toBeCloseTo(200, 9);
		expect(out.y).toBeCloseTo(450, 9);
		// Elevation goes through z: 1000 m at a zScale of 1/1000 is z = 1.
		projectTo(out, m, 0.25, 0.75, 1000, 1 / 1000, 800, 600);
		expect(out.y).toBeCloseTo(450 - (zLift / 2) * 600, 9);
		// Behind the camera: w ≤ 0.
		const behind = new Float64Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, -1]);
		expect(projectTo(out, behind, 0.5, 0.5, 0, 1, 10, 10)).toBe(false);
	});

	it('converts ground speed to screen speed', () => {
		// At z10 near Boise a pixel is about 55 m, so 30 m/s is about 0.54 px/s.
		expect(pxPerSecond(30, 10, 43.6)).toBeGreaterThan(0.5);
		expect(pxPerSecond(30, 10, 43.6)).toBeLessThan(0.6);
		expect(pxPerSecond(30, 11, 43.6)).toBeCloseTo(2 * pxPerSecond(30, 10, 43.6), 9);
	});
});

describe('sprite atlas packing', () => {
	it('packs shelves left to right, then down, and says when it is full', () => {
		// Each rect takes 2 px of padding on its right and bottom.
		const p = new ShelfPacker(66, 32);
		expect(p.pack(20, 10)).toEqual({ x: 0, y: 0 });
		expect(p.pack(20, 10)).toEqual({ x: 22, y: 0 });
		expect(p.pack(20, 10)).toEqual({ x: 44, y: 0 });
		expect(p.pack(20, 10)).toEqual({ x: 0, y: 12 });
		expect(p.pack(70, 5)).toBeNull();
		expect(p.pack(10, 30)).toBeNull();
		p.reset(64);
		expect(p.pack(10, 30)).toEqual({ x: 0, y: 0 });
	});
});

describe('the badge rule', () => {
	it('flags blue, orange and red plates and the unknown gray for a halo (docs/14 §14.3)', () => {
		expect(needsHalo('#2a78d6', '#ffffff')).toBe(true); // 4.42
		expect(needsHalo('#eb6834', '#2b2a33')).toBe(true); // 4.43
		expect(needsHalo('#e34948', '#ffffff')).toBe(true); // 3.95
		expect(needsHalo('#8a857c', '#2b2a33')).toBe(true); // 3.86
		expect(needsHalo('#4a3aa7', '#ffffff')).toBe(false); // 8.56
		expect(needsHalo('#eda100', '#2b2a33')).toBe(false); // 6.55
		expect(contrast('#2a78d6', '#ffffff')).toBeCloseTo(4.42, 1);
		expect(haloFor('#ffffff')).toBe('#2b2a33');
		expect(haloFor('#2b2a33')).toBe('#fffbf4');
		// The halo is what the numerals are measured against: about 14:1.
		expect(contrast('#ffffff', haloFor('#ffffff'))).toBeGreaterThan(13);
	});
});
