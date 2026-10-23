import { CLAY_SURFACE, deltaE, linearRgb, linearToSrgb, toHex, type Rgb } from '#lib/map/color.js';

/**
 * The crop fields' groups and colours (landscape sprint plan §3.4 K1; plugins/farm/README.md, "Crop groups").
 *
 * Seven groups are painted; developed and "other" fields are not crops (a built-over field shows through the
 * growth hatch, not a fill). Each group has a colour, a pattern (patterns.ts) and a name, so colour is never
 * alone, and none relies on red against green. The fills draw on Clay only: the hay cyan sits near Valley's
 * turquoise water (K1), and Clay is the surface every colour here is validated against (`palette.test.ts`:
 * distance from the surface, distance between groups for normal vision and for the three kinds of
 * colour-vision deficiency).
 */
export const GROUPS = ['corn', 'hay', 'grain', 'roots', 'specialty', 'pasture', 'fallow'] as const;
export type CropGroup = (typeof GROUPS)[number];

/** The group names the tiles carry besides the painted ones (`farm.crop_class.grp`). */
export type TileGroup = CropGroup | 'developed' | 'other';

export const GROUP_NAME: Record<CropGroup, string> = {
	corn: 'Corn and sorghum',
	hay: 'Hay and alfalfa',
	grain: 'Small grains',
	roots: 'Roots, vegetables and beans',
	specialty: 'Mint, hops, orchards and vineyards',
	pasture: 'Pasture',
	fallow: 'Fallow'
};

/** A short word for chips and labels. */
export const GROUP_SHORT: Record<TileGroup, string> = {
	corn: 'Corn',
	hay: 'Hay',
	grain: 'Grain',
	roots: 'Roots & beans',
	specialty: 'Specialty',
	pasture: 'Pasture',
	fallow: 'Fallow',
	developed: 'Built',
	other: 'Other'
};

/** The fills, on Clay. Hay is the cyan K1 names; corn a warm yellow; none is red against green. Picked by a search for the widest
 * gaps under all four visions (at least 11 between any two for normal vision, 6.8 under the deficiencies, 10
 * from Clay). */
export const FILL: Record<CropGroup, string> = {
	corn: '#eac644',
	hay: '#4bc2d5',
	grain: '#ad754a',
	roots: '#b97dc6',
	specialty: '#ff924b',
	pasture: '#98c88b',
	fallow: '#d2ccc2'
};

/** The pattern ink over the fills (`patterns.ts`), and the cream edge of a field from z12 (docs/13). */
export const PATTERN_INK = '#4a4638';
export const EDGE = '#fffbf4';
export const EDGE_ESTIMATED = '#6a6455';

/** The tiles' per-year letter (`farm.crop_class.letter`) for each group; developed, other and none draw nothing. */
export const LETTER: Record<TileGroup, string> = {
	corn: 'c',
	hay: 'h',
	grain: 'g',
	roots: 'r',
	specialty: 's',
	pasture: 'p',
	fallow: 'f',
	developed: 'd',
	other: 'o'
};
export const GROUP_OF_LETTER: Record<string, TileGroup | undefined> = Object.fromEntries((Object.keys(LETTER) as TileGroup[]).map((g) => [LETTER[g], g]));

/** The group a letter stands for (undefined for "-", an unknown letter or none). */
export function groupOfLetter(letter: string | undefined): TileGroup | undefined {
	return letter ? GROUP_OF_LETTER[letter] : undefined;
}

export const isCrop = (g: string | undefined | null): g is CropGroup => !!g && (GROUPS as readonly string[]).includes(g);

// --- colour-vision simulation --------------------------------------------------------------------

/**
 * Machado, Oliveira & Fernandes (2009), severity 1.0, applied in linear sRGB: the matrices for protanopia,
 * deuteranopia and tritanopia. Used only by the tests and the palette's checks.
 */
export const VISION = {
	protan: [
		[0.152286, 1.052583, -0.204868],
		[0.114503, 0.786281, 0.099216],
		[-0.003882, -0.048116, 1.051998]
	],
	deutan: [
		[0.367322, 0.860646, -0.227968],
		[0.280085, 0.672501, 0.047413],
		[-0.01182, 0.04294, 0.968881]
	],
	tritan: [
		[1.255528, -0.076749, -0.178779],
		[-0.078411, 0.930809, 0.147602],
		[0.004733, 0.691367, 0.3039]
	]
} as const;
export type Vision = keyof typeof VISION;

/** A colour as someone with that deficiency sees it. */
export function simulate(hex: string, vision: Vision): string {
	const m = VISION[vision];
	const lin = linearRgb(hex);
	const out = m.map((row) => Math.min(1, Math.max(0, row[0] * lin[0] + row[1] * lin[1] + row[2] * lin[2]))) as Rgb;
	return toHex(out.map(linearToSrgb) as Rgb);
}

/** The distance (OKLab x 100, `deltaE`) between two colours as seen with `vision`, or normally with none. */
export function distance(a: string, b: string, vision?: Vision): number {
	return vision ? deltaE(simulate(a, vision), simulate(b, vision)) : deltaE(a, b);
}

export { CLAY_SURFACE };
