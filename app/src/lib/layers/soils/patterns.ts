import type { Rgb } from '#lib/map/color.js';

/**
 * The Soils layer's patterns (never colour alone): the wash is a hue-free ramp, and what the ramp can't say
 * is drawn over it in ink. Three look-alikes of the soil survey's own symbols:
 *
 * - **hatch**, diagonal lines: a hardpan within 50 cm; soils that need draining; a dual hydrologic group;
 * - **stipple**, dots: bedrock within 50 cm;
 * - **cross**, crossed lines: soils reclaimed of salts and sodium.
 *
 * Each is a small tile (`PIXELS` square at `PIXEL_RATIO`) made here as RGBA, so the module adds them as map
 * images with no file to load; the legend and the card draw the same patterns in CSS (`css`).
 */
export type PatternKey = 'hatch' | 'stipple' | 'cross';
export const PATTERN_KEYS: readonly PatternKey[] = ['hatch', 'stipple', 'cross'];
/** The tile's side in pixels, and its pixel ratio (so it is drawn at half that in CSS pixels). */
export const PIXELS = 16;
export const PIXEL_RATIO = 2;
/** CSS pixels one repeat spans in the legend's swatches. */
const CSS_PERIOD = PIXELS / PIXEL_RATIO;

export const imageId = (k: PatternKey): string => `soils-${k}`;

/** What each looks like, in words (the legend names it beside the swatch). */
export const LOOK: Record<PatternKey, string> = { hatch: 'diagonal lines', stipple: 'dots', cross: 'crossed lines' };

/** Whether the pixel (x, y) of the tile is ink. Every pattern tiles seamlessly at `PIXELS`. */
export function inked(k: PatternKey, x: number, y: number): boolean {
	const d1 = (x + y) % 8; // lines running up to the right: 2 px wide every 8
	const d2 = (x - y + 64) % 8; // lines running down to the right
	if (k === 'hatch') return d1 < 2;
	if (k === 'cross') return d1 < 2 || d2 < 2;
	// stipple: 2x2 dots on a staggered 8 px grid
	const row = Math.floor(y / 4);
	const dx = (x + (row % 2 === 0 ? 0 : 4)) % 8;
	return dx < 2 && y % 4 < 2;
}

/** The tile as straight RGBA bytes (ink where inked, transparent elsewhere), for `map.addImage`. */
export function rasterize(k: PatternKey, ink: Rgb): Uint8ClampedArray {
	const out = new Uint8ClampedArray(PIXELS * PIXELS * 4);
	const [r, g, b] = ink.map((c) => Math.round(c * 255));
	for (let y = 0; y < PIXELS; y++)
		for (let x = 0; x < PIXELS; x++)
			if (inked(k, x, y)) out.set([r, g, b, 255], (y * PIXELS + x) * 4);
	return out;
}

/** A CSS `background` for a swatch of the pattern over `fill` (the legend's and the card's). */
export function css(k: PatternKey, ink: string, fill: string): string {
	const p = CSS_PERIOD;
	const line = (deg: number) => `repeating-linear-gradient(${deg}deg, transparent 0 ${p * 0.55}px, ${ink} ${p * 0.55}px ${p * 0.8}px, transparent ${p * 0.8}px ${p}px)`;
	if (k === 'hatch') return `${line(45)}, ${fill}`;
	if (k === 'cross') return `${line(45)}, ${line(135)}, ${fill}`;
	const dot = (at: string) => `radial-gradient(circle at ${at}, ${ink} 0 0.8px, transparent 1px) 0 0 / ${p}px ${p}px`;
	return `${dot('25% 25%')}, ${dot('75% 75%')}, ${fill}`;
}
