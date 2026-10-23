import { CLAY_SURFACE, CREAM, deltaE, INK, mixOklab } from '#lib/map/color.js';
import type { Palette } from '#lib/map/materials.js';

/**
 * The Soils layer's colours (landscape sprint plan v3 §3.4 K6; docs/13). The wash is hue-free: five steps of
 * gray, one property at a time, 0 the palest and 4 the darkest (a shallower hardpan or bedrock, wetter, more
 * water held, better farmland, more runoff). Hue stays free for the layers that mean something by colour.
 * Colour is never the only cue: every step is named in the legend, the hardpan and bedrock, drained and
 * dual-group soils carry a pattern, and the card says it all in words.
 *
 * The steps are validated on Clay (`palette.test.ts`): each is at least ΔE 6 from the next and from the
 * surface at the wash's opacity. The wash draws in either look; it is an area fill (one at a time).
 */
export const STEPS = ['#e8e8e8', '#cacaca', '#a8a8a8', '#808080', '#555555'] as const;
export type Step = 0 | 1 | 2 | 3 | 4;
/** The wash's opacity, and the copy over Aerial (the wash sits above the photo at 0.45). */
export const FILL_OPACITY = 0.85;
export const COPY_OPACITY = 0.45;
export const PATTERN_OPACITY = 0.55;

/** The pattern ink over the wash, and the outlines: gray too. */
export const PATTERN_INK = '#3d3d3d';
export const OUTLINE = '#4a4a4a';
export const SURVEY_LINE = '#5a5a5a';
export const LABEL = INK;
export const HALO = CREAM;
export const SELECTED = INK;

/** A step as it looks on the Clay surface at the wash's opacity. */
export const onClay = (step: Step, opacity = FILL_OPACITY): string => mixOklab(CLAY_SURFACE, STEPS[step], opacity);

/** The smallest ΔE between neighbouring steps (on Clay) and from the palest to the surface. */
export function gaps(): { between: number[]; fromSurface: number } {
	const seen = ([0, 1, 2, 3, 4] as Step[]).map((s) => onClay(s));
	return { between: seen.slice(1).map((c, i) => deltaE(seen[i], c)), fromSurface: deltaE(CLAY_SURFACE, seen[0]) };
}

/** The palette the colour budget reads (S3b finds this file by glob). */
export const palette: Palette = {
	id: 'soils',
	colors: [
		...STEPS.map((c, i) => ({ name: `wash step ${i}`, valley: c, use: 'wash' })),
		{ name: 'pattern ink', valley: PATTERN_INK, use: 'line, hardpan and bedrock patterns' },
		{ name: 'outline', valley: OUTLINE, use: 'line, map-unit outlines' },
		{ name: 'survey bounds', valley: SURVEY_LINE, use: 'line, survey-area bounds' },
		{ name: 'label', valley: LABEL, use: 'label, symbols and names' }
	]
};

export default palette;
