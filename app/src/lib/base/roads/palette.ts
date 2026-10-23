import { ASPHALT, CLAY_KERB, CONCRETE, CURB, EDGE, INK, MARKINGS, UNPAVED, type Palette } from '#lib/map/materials.js';

/**
 * The colors and zoom ranges of roads at real width (P9; plan v3 §3.4, §3.5). The colors come from the shared
 * material tokens (`#lib/map/materials`), so asphalt is the same asphalt under the surfaces, the piece lines and
 * the markings. Valley asphalt (`#989088`) against the slate of Streets under Transit is a named form
 * exemption (K6's sibling): the surface is a ground, the slate is a drawn line, and Streets keeps its casing.
 */

/** Zoom ranges (plan v3 §3.5). */
export const ZOOM = {
	/** Piece lines start (Protomaps' road lines are hidden from here once the lines are built). */
	linesFrom: 14,
	/** The lines are white at `linesFrom` and asphalt by here. */
	toneBy: 15.5,
	/** The lines fade out over `fadeFrom`..`fadeTo` while the surfaces (opaque) are already there (K11). */
	fadeFrom: 15.5,
	fadeTo: 16,
	/** The generalised surfaces take over at `fadeFrom` (they stop where the full-detail ones start). */
	surfacesZ15From: 15.5,
	surfacesFrom: 16,
	/** Draped decks from here (3D decks stay later). */
	decksFrom: 15,
	/** Markings fade in over `markingsFrom`..`markingsFull`. */
	markingsFrom: 16.5,
	markingsFull: 17
} as const;

/** The latitude the metres-to-pixels conversion is made at (the valley's middle). */
export const LATITUDE = 43.6;

/** Pixels per metre at `zoom` on a 512 px tile world at LATITUDE (what `line-width` takes for a width in metres). */
export function pixelsPerMetre(zoom: number, latitude = LATITUDE): number {
	const metresPerPixel = (40075016.686 * Math.cos((latitude * Math.PI) / 180)) / (512 * 2 ** zoom);
	return 1 / metresPerPixel;
}

/**
 * A style expression for `field` metres wide at any zoom in [from, to]: exponential base 2, which is exact because
 * the scale doubles with every zoom. Outside the range MapLibre holds the end values, so a layer using it must
 * stay within [from, to].
 */
export function metres(field: unknown, from: number, to: number): unknown {
	return ['interpolate', ['exponential', 2], ['zoom'], from, ['*', field, pixelsPerMetre(from)], to, ['*', field, pixelsPerMetre(to)]];
}

/** The tiers whose width is known: a crisp curb. The others (counted, estimated) draw a soft edge. */
export const CRISP_TIERS: readonly string[] = ['inventoried', 'measured'];

/** The materials with a surface of their own; any other value draws as asphalt. */
export const OTHER_MATERIALS: readonly string[] = ['concrete', 'gravel', 'dirt'];

/** Surface edges: the curb is lighter than the surface, the shoulder is the paving's edge. */
export const EDGES = { curb: CURB, shoulder: EDGE, clayKerb: CLAY_KERB } as const;

/** The ink casing of a draped deck. */
export const DECK_CASING = INK;

/** Piece lines start white. */
export const LINE_START = MARKINGS.onAsphalt.color;

export const ROADS_PALETTE: Palette = {
	id: 'roads',
	colors: [
		{ name: 'asphalt', valley: ASPHALT.valley, clay: ASPHALT.clay, use: 'road surfaces and the piece lines by z15.5 (against slate: a form exemption)' },
		{ name: 'concrete', valley: CONCRETE.valley, clay: CONCRETE.clay, use: 'concrete surfaces' },
		{ name: 'line start', valley: LINE_START, clay: LINE_START, use: 'piece lines at z14, before they take the surface tone' },
		{ name: 'curb', valley: CURB, clay: CLAY_KERB, use: 'curb edges and island outlines' },
		{ name: 'shoulder', valley: EDGE, clay: CLAY_KERB, use: 'shoulder edges' },
		{ name: 'dirt', valley: UNPAVED.dirt.color, use: 'unpaved surfaces, as a tint over the ground (18%)' },
		{ name: 'gravel', valley: UNPAVED.gravel.color, use: 'gravel surfaces, as a tint over the ground (35%)' },
		{ name: 'marking on asphalt', valley: MARKINGS.onAsphalt.color, use: 'lane, centre and edge lines, stop bars and crosswalks' },
		{ name: 'marking on concrete', valley: MARKINGS.onConcrete.color, use: 'ink at 70% on concrete' },
		{ name: 'marking in Clay', valley: MARKINGS.clay.color, clay: MARKINGS.clay.color, use: 'ink at 60%, Clay with Lanes on only' },
		{ name: 'deck casing', valley: DECK_CASING, clay: DECK_CASING, use: 'ink outline of a draped deck' }
	]
};

export default ROADS_PALETTE;
