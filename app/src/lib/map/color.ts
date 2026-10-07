/**
 * The color module (docs/14 §14.3 "The color budget", §14.4 "Route colors",
 * §14.5 "Streets and the base look").
 *
 * - OKLab helpers: distances (OKLab x100, as the dataviz validator and
 *   ingest/route_colors.py measure them), mixes, WCAG contrast.
 * - `ghostColor()`: the pale color a route draws in when no bus is running
 *   on it. Same formula as ingest/route_colors.py's `ghost`, so it reproduces
 *   §14.4's ghost column.
 * - `interpolateLab()`: CIELAB interpolation exactly as MapLibre's
 *   `interpolate-lab` does it, so a value between two ramp stops gets the
 *   color the map draws.
 *
 * Pure and dependency-free: the client's streets and transit code and the
 * tests share it.
 */

export type Rgb = [number, number, number];
export type Lab = [number, number, number];

/** The Clay flavor's surface, which route colors and ghosts are validated against (§14.4). */
export const CLAY_SURFACE = '#f3ede2';
/** ch. 13 tokens used by the color checks. */
export const INK = '#2b2a33';
export const CREAM = '#fffbf4';

/** A ghost sits about this far (OKLab x100) from the surface (§14.4)… */
export const GHOST_DE = 14;
/** …but keeps at least 30% of its color, found in steps of 0.1%. */
export const GHOST_T_MIN = 0.3;
export const GHOST_STEP = 0.001;

// -- sRGB ----------------------------------------------------------------------------------------

/** `#rrggbb` (or `#rgb`) to sRGB channels in 0–1. */
export function parseHex(hex: string): Rgb {
	let h = hex.trim().replace(/^#/, '');
	if (h.length === 3) h = [...h].map((c) => c + c).join('');
	if (!/^[0-9a-f]{6}$/i.test(h)) throw new Error(`not a #rrggbb color: ${hex}`);
	return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255) as Rgb;
}

/** Python's round(): halves go to the even neighbour, so both sides make the same hex. */
export function roundHalfEven(x: number): number {
	const f = Math.floor(x);
	const d = x - f;
	if (Math.abs(d - 0.5) > 1e-12) return d > 0.5 ? f + 1 : f;
	return f % 2 === 0 ? f : f + 1;
}

const clamp01 = (c: number) => Math.max(0, Math.min(1, c));

/** sRGB channels (0–1) to `#rrggbb`. */
export function toHex(rgb: Rgb): string {
	return '#' + rgb.map((c) => roundHalfEven(clamp01(c) * 255).toString(16).padStart(2, '0')).join('');
}

export const srgbToLinear = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
export const linearToSrgb = (c: number) => {
	c = clamp01(c);
	return c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055;
};

export const linearRgb = (hex: string): Rgb => parseHex(hex).map(srgbToLinear) as Rgb;

// -- OKLab ----------------------------------------------------------------------------------------

/** Linear sRGB to OKLab (Björn Ottosson's matrices, as route_colors.py). */
export function oklabFromLinear([r, g, b]: Rgb): Lab {
	const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
	const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
	const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
	return [
		0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
		1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
		0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s
	];
}

/** OKLab to linear sRGB (unclamped). */
export function linearFromOklab([L, a, b]: Lab): Rgb {
	const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
	const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
	const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
	return [
		4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
		-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
		-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s
	];
}

export const oklab = (hex: string): Lab => oklabFromLinear(linearRgb(hex));

export const oklabToHex = (lab: Lab): string => toHex(linearFromOklab(lab).map(linearToSrgb) as Rgb);

/** OKLCH lightness and chroma. */
export function oklch(hex: string): { L: number; C: number; h: number } {
	const [L, a, b] = oklab(hex);
	return { L, C: Math.hypot(a, b), h: ((Math.atan2(b, a) * 180) / Math.PI + 360) % 360 };
}

/** OKLab distance x100 (normal vision): the unit every check in docs/14 uses. */
export function deltaE(a: string, b: string): number {
	const p = oklab(a);
	const q = oklab(b);
	return 100 * Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]);
}

/** A mix in OKLab: t = 0 is `from`, t = 1 is `to`. */
export function mixOklab(from: string, to: string, t: number): string {
	const s = oklab(from);
	const c = oklab(to);
	return oklabToHex([0, 1, 2].map((i) => s[i] + t * (c[i] - s[i])) as Lab);
}

/**
 * The route's ghost (§14.4): an OKLab mix from the surface toward the color,
 * at the first step (from 30%, by 0.1%) whose hex sits at least ΔE 14 from the
 * surface. A ghost is solid, not transparent, so it fades every route evenly
 * whatever lies underneath.
 */
export function ghostColor(color: string, surface: string = CLAY_SURFACE): string {
	const s = oklab(surface);
	const c = oklab(color);
	for (let step = 0; ; step++) {
		const t = GHOST_T_MIN + step * GHOST_STEP;
		if (t >= 1) return color.toLowerCase();
		const g = oklabToHex([0, 1, 2].map((i) => s[i] + t * (c[i] - s[i])) as Lab);
		if (deltaE(g, surface) >= GHOST_DE) return g;
	}
}

// -- WCAG -----------------------------------------------------------------------------------------

export function luminance(hex: string): number {
	const [r, g, b] = linearRgb(hex);
	return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG contrast ratio. */
export function contrast(a: string, b: string): number {
	const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
	return (x + 0.05) / (y + 0.05);
}

// -- CIELAB, as MapLibre's interpolate-lab ---------------------------------------------------------

// MapLibre's style spec (src/expression/types/color_spaces.ts): D50 white, Bradford-adapted sRGB.
const XN = 0.96422;
const YN = 1;
const ZN = 0.82521;
const T0 = 4 / 29;
const T1 = 6 / 29;
const T2 = 3 * T1 * T1;
const T3 = T1 * T1 * T1;
const xyz2lab = (t: number) => (t > T3 ? Math.cbrt(t) : t / T2 + T0);
const lab2xyz = (t: number) => (t > T1 ? t * t * t : T2 * (t - T0));
const xyz2rgb = (x: number) => clamp01(x <= 0.00304 ? 12.92 * x : 1.055 * x ** (1 / 2.4) - 0.055);

/** sRGB hex to CIELAB, as MapLibre computes it. */
export function cielab(hex: string): Lab {
	const [r, g, b] = linearRgb(hex);
	const y = xyz2lab((0.2225045 * r + 0.7168786 * g + 0.0606169 * b) / YN);
	let x: number;
	let z: number;
	if (r === g && g === b) x = z = y;
	else {
		x = xyz2lab((0.4360747 * r + 0.3850649 * g + 0.1430804 * b) / XN);
		z = xyz2lab((0.0139322 * r + 0.0971045 * g + 0.7141733 * b) / ZN);
	}
	const l = 116 * y - 16;
	return [l < 0 ? 0 : l, 500 * (x - y), 200 * (y - z)];
}

/** CIELAB to sRGB hex, as MapLibre computes it. */
export function cielabToHex([l, a, b]: Lab): string {
	let y = (l + 16) / 116;
	let x = y + a / 500;
	let z = y - b / 200;
	y = YN * lab2xyz(y);
	x = XN * lab2xyz(x);
	z = ZN * lab2xyz(z);
	return toHex([
		xyz2rgb(3.1338561 * x - 1.6168667 * y - 0.4906146 * z),
		xyz2rgb(-0.9787684 * x + 1.9161415 * y + 0.033454 * z),
		xyz2rgb(0.0719453 * x - 0.2289914 * y + 1.4052427 * z)
	]);
}

/** A mix in CIELAB (MapLibre's interpolate-lab between two stops). */
export function mixLab(from: string, to: string, t: number): string {
	const p = cielab(from);
	const q = cielab(to);
	return cielabToHex([0, 1, 2].map((i) => p[i] + t * (q[i] - p[i])) as Lab);
}

/**
 * The color MapLibre's `['interpolate-lab', ['linear'], input, …stops]` gives
 * for `value`: clamped below the first stop and above the last, mixed in
 * CIELAB in between.
 */
export function interpolateLab(stops: readonly (readonly [number, string])[], value: number): string {
	if (!stops.length) throw new Error('no stops');
	if (value <= stops[0][0]) return stops[0][1];
	const last = stops[stops.length - 1];
	if (value >= last[0]) return last[1];
	for (let i = 1; i < stops.length; i++) {
		const [x1, c1] = stops[i];
		if (value === x1) return c1;
		if (value < x1) {
			const [x0, c0] = stops[i - 1];
			return mixLab(c0, c1, (value - x0) / (x1 - x0));
		}
	}
	return last[1];
}
