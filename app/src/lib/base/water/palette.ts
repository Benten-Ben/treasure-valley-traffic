import type { FlavorName } from '#lib/map/flavors.js';

/**
 * The baked water network's look (landscape sprint plan v3 §3.4 K5, §3.5; P4-app).
 *
 * - **Colours.** One hue family per flavor, the basemap's own water (docs/13 §13.4: Valley turquoise `#7CC4E4`,
 *   Clay blue-gray `#C9DCE3`) for the fills, and a deeper tone of it for lines, so a 1 px canal stays readable
 *   on sand. Lines from the federal map alone (NHD-only, not in OpenStreetMap) are lighter still. Colour is
 *   never the only cue: kinds differ by width, flow by dash, NHD-only by a finer line and its own dash, piped
 *   water by dots (K5, K8).
 * - **Never a casing** (K5): water sits under the streets, so a casing would only dim the street shades above
 *   it. No layer here has a casing, an outline or a halo, and none uses `line-offset`. `line-gap-width` appears
 *   once: on the solid reach layer, as 0 unless the canal's feature-state `season` is `off`, where it makes the
 *   hollow inside the reach's own line (two thin edges in the reach's own tone, the gap between them, so the
 *   footprint equals the true width: `season.ts`). The dashed layers never have one (their dashes are multiples
 *   of the width). `water.base.test.ts` and the `@water` spec check it.
 * - **Widths.** Below z15 a line's width grows with the square root of its (estimated) width in metres; from z15
 *   it is the true width, in pixels, doubling every zoom (`trueWidth`). Dashed and dotted lines keep a thin
 *   width (a dash is a multiple of its line's width, so a ribbon-wide dash would stop reading as a dash).
 */

/** Tones per flavor. `edge` is the intermittent bodies' dashed rim; `label` the italic names; `selected` the picked one. */
export interface WaterTones {
	/** Water areas (lakes, ponds, rivers drawn as areas). */
	fill: string;
	/** Water areas the federal map alone shows. */
	fillNhd: string;
	/** Lines from OpenStreetMap's geometry. */
	line: string;
	/** Lines the federal map alone shows: lighter. */
	lineNhd: string;
	/** The rim of an intermittent area. */
	edge: string;
	/** Italic names. */
	label: string;
	/** The cream halo behind names. */
	halo: string;
	/** The picked line or area. */
	selected: string;
}

export const TONES: Record<FlavorName, WaterTones> = {
	valley: {
		fill: '#7cc4e4',
		fillNhd: '#a0d3ea',
		line: '#4a9fcc',
		lineNhd: '#7fb5d6',
		edge: '#4a9fcc',
		label: '#2f6f8f',
		halo: '#fffbf4',
		selected: '#1d5d85'
	},
	clay: {
		fill: '#c9dce3',
		fillNhd: '#dbe7ec',
		line: '#7aa3b5',
		lineNhd: '#a3bfcc',
		edge: '#7aa3b5',
		label: '#3e6678',
		halo: '#fffbf4',
		selected: '#1d5d85'
	}
};

/** Dash arrays, in multiples of the line's width (MapLibre's rule). Each has its word in the legend (K8). */
export const DASH = {
	/** Intermittent: flows only part of the year. */
	intermittent: [4, 3],
	/** NHD-only, perennial: long dashes with short gaps. */
	nhd: [9, 2.5],
	/** NHD-only and intermittent: the short dashes, in the finer lighter line. */
	nhdIntermittent: [3, 3],
	/** Piped (culverts, siphons): square dots (a dash one width long), from z16. */
	piped: [1, 2]
} as const;

/** Dashed and dotted lines are never wider than this, px. */
export const DASHED_MAX_PX = 4;
/** An NHD-only line is this much finer than an OpenStreetMap line of the same width. */
export const NHD_FINER = 0.6;
/** Piped water draws from this zoom (the export's `minzoom` for it, too). */
export const PIPED_FROM_ZOOM = 16;
/** The true-width ribbons start here. */
export const RIBBON_FROM_ZOOM = 15;
/** A line is never thinner than this, px. */
export const MIN_PX = 0.6;

/** Metres per pixel of a 512 px tile at a zoom and latitude. */
export function metresPerPixel(zoom: number, lat = 43.6): number {
	return (40_075_016.686 * Math.cos((lat * Math.PI) / 180)) / (512 * 2 ** zoom);
}

/** The growth of a line's width with zoom below the ribbons: px per sqrt(metre of width), at these zooms. */
export const SQRT_PX: readonly (readonly [zoom: number, px: number])[] = [
	[8, 0.3],
	[12, 0.55],
	[14, 0.75]
];

type Expr = unknown[];

/** A line's width in px: `width_m` as the tiles carry it, as a style expression. */
export interface WidthOptions {
	/** Multiply the width (the NHD-only lines are finer). */
	scale?: number;
	/** Never wider than this, px. */
	cap?: number;
	/** Never thinner than this, px (dots need room to read as dots). */
	floor?: number;
	/** Add this many px (the picked line is a little wider). */
	extra?: number;
}

/**
 * The width expression: `['interpolate', ['exponential', 2], ['zoom'], ...]` over `width_m`. Base 2 makes the
 * z15 to z22 stretch the exact doubling of a true width.
 */
export function lineWidth(o: WidthOptions = {}): Expr {
	const { scale = 1, cap, floor, extra = 0 } = o;
	const wrap = (e: Expr | number): Expr | number => {
		let out: Expr | number = e;
		if (scale !== 1) out = ['*', scale, out];
		if (cap !== undefined) out = ['min', cap, out];
		if (floor !== undefined) out = ['max', floor, out];
		if (extra) out = ['+', extra, out];
		return out;
	};
	const width = ['coalesce', ['get', 'width_m'], 1];
	const low = (px: number): Expr => ['max', MIN_PX, ['*', px, ['sqrt', width]]];
	const ribbon = (zoom: number): Expr => ['max', MIN_PX, ['/', width, metresPerPixel(zoom)]];
	const stops: unknown[] = [];
	for (const [z, px] of SQRT_PX) stops.push(z, wrap(low(px)));
	stops.push(RIBBON_FROM_ZOOM, wrap(ribbon(RIBBON_FROM_ZOOM)), 22, wrap(ribbon(22)));
	return ['interpolate', ['exponential', 2], ['zoom'], ...stops];
}

/** The true width of a line `width_m` metres wide at a zoom, px (what `lineWidth` gives from z15). */
export function trueWidth(widthM: number, zoom: number): number {
	return Math.max(MIN_PX, widthM / metresPerPixel(zoom));
}

/** Fill opacity by kind: wetlands are a pale wash; an intermittent area is paler. */
export const FILL_OPACITY = { wetland: 0.5, intermittent: 0.65, solid: 1 } as const;

/** WCAG contrast ratio of two #rrggbb colours. */
export function contrast(a: string, b: string): number {
	const lum = (hex: string) => {
		const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
		return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
	};
	const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
	return (hi + 0.05) / (lo + 0.05);
}
