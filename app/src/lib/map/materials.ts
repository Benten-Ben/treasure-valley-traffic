/**
 * The shared material tokens of the landscape layers (landscape sprint plan §3.4; S3a).
 *
 * One place for the colors the layers share, so asphalt is the same asphalt under the lane markings,
 * the paving fills and the ground's painted lots. Each is a Valley value with its Clay one where the
 * Clay look differs; Clay stays flat in v1 (DECISIONS, Oct 8), so most of them only matter in Valley.
 * Every color is checked against the ground in `docs/13` (never color alone, never red and green).
 */

/** The ink every layer's lines and text come from (`flavors.ts`' INK). */
export const INK = '#2b2a33';

/** A color at a share of full strength: `rgba` is for paint properties that take an opacity of their own. */
export interface Tint {
	color: string;
	/** 0 to 1. */
	opacity: number;
}

export interface Material {
	valley: string;
	clay: string;
}

/** Asphalt and concrete surfaces: Valley's warm gray, Clay's near-white. */
export const ASPHALT: Material = { valley: '#989088', clay: '#F8F4EC' };
export const CONCRETE: Material = { valley: '#D2CEC6', clay: '#F8F4EC' };

/** Edges: the curb line, the paving's edge, and Clay's kerb. */
export const CURB = '#E3D7C4';
export const EDGE = '#BDB6AA';
export const CLAY_KERB = '#E2D9CB';

/** Markings: cream on asphalt, ink at 70% on concrete; in Clay, ink at 60%. */
export const MARKINGS = {
	onAsphalt: { color: '#FFFBF4', opacity: 1 } satisfies Tint,
	onConcrete: { color: INK, opacity: 0.7 } satisfies Tint,
	clay: { color: INK, opacity: 0.6 } satisfies Tint
} as const;

/**
 * Unpaved surfaces are tints over the ground, not colors of their own: dirt is umber at 18%, gravel
 * is cream at 35%. (The umber is raw umber, `#826644`: plan §3.4 gives the share, the hue is ours.)
 */
export const UNPAVED = {
	dirt: { color: '#826644', opacity: 0.18 } satisfies Tint,
	gravel: { color: '#FFFBF4', opacity: 0.35 } satisfies Tint
} as const;

/** The ground band's extremes: the painter's lawn and bare soil, asphalt, and the pale lot. */
export const GROUND_BAND = {
	lawn: '#748357',
	bare: '#b9a07f',
	asphalt: ASPHALT.valley,
	paleLot: '#f7edd6'
} as const;

/** A fence post, and a burn scar's char. */
export const FENCE_POST = '#6F685E';
export const SCAR_CHAR = '#5E5750';

/** Every token by name, for the budget test and the legend swatches. */
export const MATERIALS = {
	asphalt: ASPHALT,
	concrete: CONCRETE,
	curb: { valley: CURB, clay: CLAY_KERB },
	edge: { valley: EDGE, clay: CLAY_KERB },
	fencePost: { valley: FENCE_POST, clay: FENCE_POST },
	scarChar: { valley: SCAR_CHAR, clay: SCAR_CHAR }
} as const satisfies Record<string, Material>;

/**
 * The colors a layer or a base contribution uses, as its `palette.ts` exports them. S3b's budget test
 * finds those files by glob, and counts the distinct hues against the color budget (docs/13).
 */
export interface Palette {
	/** The layer or contribution id. */
	id: string;
	colors: readonly { name: string; valley: string; clay?: string; use: string }[];
}
