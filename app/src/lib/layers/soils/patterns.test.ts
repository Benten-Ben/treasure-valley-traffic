import { describe, expect, it } from 'vitest';
import { parseHex } from '#lib/map/color.js';
import { css, imageId, inked, LOOK, PATTERN_KEYS, PIXELS, rasterize } from './patterns.js';

describe('the Soils patterns', () => {
	it('are three, each with a name and a look in words', () => {
		expect([...PATTERN_KEYS]).toEqual(['hatch', 'stipple', 'cross']);
		for (const k of PATTERN_KEYS) {
			expect(LOOK[k]).toBeTruthy();
			expect(imageId(k)).toBe(`soils-${k}`);
		}
	});

	it('cover a share of the tile that reads as a texture, not a fill, and differ from each other', () => {
		const share = (k: (typeof PATTERN_KEYS)[number]) => {
			let n = 0;
			for (let y = 0; y < PIXELS; y++) for (let x = 0; x < PIXELS; x++) if (inked(k, x, y)) n++;
			return n / (PIXELS * PIXELS);
		};
		for (const k of PATTERN_KEYS) {
			expect(share(k), k).toBeGreaterThan(0.1);
			expect(share(k), k).toBeLessThan(0.55);
		}
		expect(share('cross')).toBeGreaterThan(share('hatch'));
		const grid = (k: (typeof PATTERN_KEYS)[number]) => Array.from({ length: PIXELS }, (_, y) => Array.from({ length: PIXELS }, (_, x) => (inked(k, x, y) ? 1 : 0)).join('')).join('/');
		expect(new Set(PATTERN_KEYS.map(grid)).size).toBe(3);
	});

	it('tile without a seam: the same at an offset of the tile\'s side', () => {
		for (const k of PATTERN_KEYS) for (const [x, y] of [[0, 0], [3, 5], [7, 11], [15, 15]]) expect(inked(k, x, y), `${k} ${x},${y}`).toBe(inked(k, x + PIXELS, y + PIXELS));
	});

	it('rasterize to straight RGBA in the ink colour, transparent elsewhere', () => {
		const ink = parseHex('#3d3d3d');
		for (const k of PATTERN_KEYS) {
			const data = rasterize(k, ink);
			expect(data).toHaveLength(PIXELS * PIXELS * 4);
			let inkPx = 0;
			for (let i = 0; i < data.length; i += 4) {
				if (data[i + 3] > 0) {
					inkPx++;
					expect([data[i], data[i + 1], data[i + 2], data[i + 3]]).toEqual([61, 61, 61, 255]);
				}
			}
			expect(inkPx).toBeGreaterThan(0);
		}
	});

	it('draw in CSS for the legend and the card, over the fill', () => {
		for (const k of PATTERN_KEYS) {
			const bg = css(k, '#3d3d3d', '#bababa');
			expect(bg).toContain('#3d3d3d');
			expect(bg.endsWith('#bababa')).toBe(true);
		}
		expect(css('hatch', '#000', '#fff')).toContain('repeating-linear-gradient(45deg');
		expect(css('cross', '#000', '#fff')).toContain('repeating-linear-gradient(135deg');
		expect(css('stipple', '#000', '#fff')).toContain('radial-gradient');
	});
});
