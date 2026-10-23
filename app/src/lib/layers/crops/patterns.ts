import { GROUPS, type CropGroup } from './palette.js';

/**
 * The crop fields' patterns (plan §3.4 K1: "every group has a pattern, so colour is never alone").
 *
 * A pattern is a few marks in a repeating 16-unit cell. The same marks make the map's pattern image
 * (`rasterize`: transparent, ink-coloured, seamless where it repeats) and the legend's swatch (`svgMarks`),
 * so the two can't differ. Seven for the groups, three for the growth states.
 */
export const CELL = 16;

export type Mark =
	| { t: 'line'; x1: number; y1: number; x2: number; y2: number }
	| { t: 'dot'; x: number; y: number; r: number }
	| { t: 'ring'; x: number; y: number; r: number };

export interface PatternDef {
	/** The map image's name (`crops-pat-<key>`). */
	key: string;
	/** What it looks like, in words (the legend's text for it). */
	look: string;
	/** Stroke width in cell units. */
	width: number;
	marks: Mark[];
}

const line = (x1: number, y1: number, x2: number, y2: number): Mark => ({ t: 'line', x1, y1, x2, y2 });

export const GROWTH_KEYS = ['built_over', 'being_built', 'plat'] as const;
export type GrowthKey = (typeof GROWTH_KEYS)[number];
export type PatternKey = CropGroup | GrowthKey;

export const PATTERNS: Record<PatternKey, PatternDef> = {
	corn: { key: 'corn', look: 'vertical rows', width: 1.5, marks: [line(4, 0, 4, 16), line(12, 0, 12, 16)] },
	hay: { key: 'hay', look: 'horizontal lines', width: 1.5, marks: [line(0, 4, 16, 4), line(0, 12, 16, 12)] },
	grain: { key: 'grain', look: 'diagonal lines', width: 1.5, marks: [line(0, 16, 16, 0), line(-8, 8, 8, -8), line(8, 24, 24, 8)] },
	roots: { key: 'roots', look: 'dots', width: 1, marks: [{ t: 'dot', x: 4, y: 4, r: 1.7 }, { t: 'dot', x: 12, y: 12, r: 1.7 }] },
	specialty: { key: 'specialty', look: 'crosses', width: 1.4, marks: [line(5, 8, 11, 8), line(8, 5, 8, 11)] },
	pasture: { key: 'pasture', look: 'short dashes', width: 1.4, marks: [line(4, 2, 4, 6), line(12, 10, 12, 14)] },
	fallow: { key: 'fallow', look: 'open rings', width: 1.2, marks: [{ t: 'ring', x: 8, y: 8, r: 3.5 }] },
	built_over: { key: 'built_over', look: 'dense crosshatch', width: 1.6, marks: [line(0, 16, 16, 0), line(-8, 8, 8, -8), line(8, 24, 24, 8), line(0, 0, 16, 16), line(-8, 8, 8, 24), line(8, -8, 24, 8)] },
	being_built: { key: 'being_built', look: 'broken diagonals leaning the other way', width: 1.6, marks: [line(0, 0, 6, 6), line(10, 10, 16, 16)] },
	plat: { key: 'plat', look: 'grid', width: 1.2, marks: [line(0, 0, 0, 16), line(16, 0, 16, 16), line(0, 0, 16, 0), line(0, 16, 16, 16)] }
};

export const PATTERN_KEYS: readonly PatternKey[] = [...GROUPS, ...GROWTH_KEYS];

/** The map image's name for a pattern. */
export const imageId = (key: PatternKey): string => `crops-pat-${key}`;

/** The pattern's pixels per cell side: 2 per unit, shown at a pixel ratio of 2 (a 16 px cell on screen). */
export const PIXELS = 32;
export const PIXEL_RATIO = 2;

function distToSegment(px: number, py: number, x1: number, y1: number, x2: number, y2: number): number {
	const dx = x2 - x1;
	const dy = y2 - y1;
	const len2 = dx * dx + dy * dy;
	const t = len2 ? Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / len2)) : 0;
	return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}

/** How far a point is from the edge of the mark's ink (negative inside it), in cell units. */
function reach(m: Mark, px: number, py: number, width: number): number {
	if (m.t === 'line') return distToSegment(px, py, m.x1, m.y1, m.x2, m.y2) - width / 2;
	if (m.t === 'dot') return Math.hypot(px - m.x, py - m.y) - m.r;
	return Math.abs(Math.hypot(px - m.x, py - m.y) - m.r) - width / 2;
}

/**
 * The pattern as RGBA pixels (PIXELS x PIXELS, straight alpha), anti-aliased: ink where a mark is, clear
 * elsewhere. Distances wrap around the cell, so it repeats without a seam. `opacity` scales the ink.
 */
export function rasterize(def: PatternDef, ink: [number, number, number], opacity = 1): Uint8ClampedArray {
	const out = new Uint8ClampedArray(PIXELS * PIXELS * 4);
	const scale = PIXELS / CELL;
	for (let y = 0; y < PIXELS; y++) {
		for (let x = 0; x < PIXELS; x++) {
			const px = (x + 0.5) / scale;
			const py = (y + 0.5) / scale;
			let best = Infinity;
			for (const m of def.marks) for (const ox of [-CELL, 0, CELL]) for (const oy of [-CELL, 0, CELL]) best = Math.min(best, reach(m, px - ox, py - oy, def.width));
			const a = Math.max(0, Math.min(1, 0.5 - best * scale)) * opacity;
			const i = (y * PIXELS + x) * 4;
			out[i] = ink[0];
			out[i + 1] = ink[1];
			out[i + 2] = ink[2];
			out[i + 3] = Math.round(a * 255);
		}
	}
	return out;
}

/** An SVG element of a pattern's marks (the legend's swatches draw these inside an `<svg viewBox="0 0 16 16">`). */
export interface SvgMark {
	tag: 'line' | 'circle';
	attrs: Record<string, number>;
	fill: boolean;
}

/** The marks as SVG elements, repeated at the eight neighbouring cells so the swatch has no gaps at its edge. */
export function svgMarks(def: PatternDef): SvgMark[] {
	const out: SvgMark[] = [];
	for (const ox of [-CELL, 0, CELL]) {
		for (const oy of [-CELL, 0, CELL]) {
			for (const m of def.marks) {
				if (m.t === 'line') out.push({ tag: 'line', attrs: { x1: m.x1 + ox, y1: m.y1 + oy, x2: m.x2 + ox, y2: m.y2 + oy }, fill: false });
				else out.push({ tag: 'circle', attrs: { cx: m.x + ox, cy: m.y + oy, r: m.r }, fill: m.t === 'dot' });
			}
		}
	}
	return out;
}
