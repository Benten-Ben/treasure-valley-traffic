/**
 * Rendering relative to centre (docs/14 §14.8, "Projection and precision").
 *
 * MapLibre's custom-layer `mainMatrix` (float64) takes Web Mercator x and y
 * in [0, 1] and z in Mercator units at the centre's latitude. Plain float32
 * Mercator jitters 22–45 px at z22, where look-through and calibration work,
 * so each frame:
 *
 * - takes an origin at the map's centre, in float64 (and the ground there for z);
 * - expresses every vertex as float32 metres east, north and up from it;
 * - multiplies `u_m = mainMatrix · T(origin) · S(k, −k, k)` in float64 and
 *   casts it to float32, where k = 1 / circumference at the centre latitude.
 *
 * The "metres" are Mercator offsets scaled by the centre's circumference, so
 * east and north are exact true metres at the centre's latitude, and up is
 * the same scale MapLibre uses for elevation (it, too, scales by the centre).
 */
import { circumferenceAt, mercatorX, mercatorY } from '#lib/overlay/project.js';

export { circumferenceAt, mercatorX, mercatorY };

/** A 4×4 column-major matrix. */
export type Mat4 = ArrayLike<number>;

export interface Frame {
	/** Origin, Mercator [0, 1] (float64). */
	ox: number;
	oy: number;
	/** Origin elevation, metres (as MapLibre draws it). */
	oz: number;
	/** 1 / circumference at the centre latitude (Mercator units per metre). */
	k: number;
	/** Centre latitude, degrees. */
	lat: number;
	/** `mainMatrix · T(origin) · S(k, −k, k)` in float64: metres from the origin → clip space. */
	m64: Float64Array;
	/** The same, cast to float32 for the shaders. */
	m32: Float32Array;
	/** Canvas size, CSS px. */
	width: number;
	height: number;
	/** Screen px per metre at clip w = 1 (radius_px = r_m · pxPerMetreW / w). */
	pxPerMetreW: number;
	/** MapLibre world px (the unit of clip w) per metre at the centre. */
	worldPerMetre: number;
}

/** out = a · b (column-major, float64). */
export function multiply(out: Float64Array, a: Mat4, b: Mat4): Float64Array {
	for (let c = 0; c < 4; c++) {
		const b0 = b[c * 4],
			b1 = b[c * 4 + 1],
			b2 = b[c * 4 + 2],
			b3 = b[c * 4 + 3];
		out[c * 4] = a[0] * b0 + a[4] * b1 + a[8] * b2 + a[12] * b3;
		out[c * 4 + 1] = a[1] * b0 + a[5] * b1 + a[9] * b2 + a[13] * b3;
		out[c * 4 + 2] = a[2] * b0 + a[6] * b1 + a[10] * b2 + a[14] * b3;
		out[c * 4 + 3] = a[3] * b0 + a[7] * b1 + a[11] * b2 + a[15] * b3;
	}
	return out;
}

/**
 * The frame's matrices. `main` is the custom layer's
 * `defaultProjectionData.mainMatrix`; (lng, lat) the map's centre; `oz` the
 * elevation the origin sits at (any value near the scene keeps offsets small);
 * `fov` the vertical field of view in radians.
 */
export function makeFrame(main: Mat4, lng: number, lat: number, oz: number, width: number, height: number, fov: number, zoom: number, out?: Frame): Frame {
	const k = 1 / circumferenceAt(lat);
	const ox = mercatorX(lng);
	const oy = mercatorY(lat);
	// T(ox, oy, oz·k) · S(k, −k, k)
	const ts = new Float64Array([k, 0, 0, 0, 0, -k, 0, 0, 0, 0, k, 0, ox, oy, oz * k, 1]);
	const f = out ?? ({ m64: new Float64Array(16), m32: new Float32Array(16) } as Frame);
	multiply(f.m64, main, ts);
	f.m32.set(f.m64);
	f.ox = ox;
	f.oy = oy;
	f.oz = oz;
	f.k = k;
	f.lat = lat;
	f.width = width;
	f.height = height;
	// MapLibre's eye space is in world pixels (512·2^zoom per world), and clip w is eye depth there:
	// a metre is k·worldSize world px, seen at depth w as (H/2)/tan(fov/2) · that / w screen px.
	f.worldPerMetre = k * 512 * 2 ** zoom;
	f.pxPerMetreW = (f.worldPerMetre * (height / 2)) / Math.tan(fov / 2);
	return f;
}

/** Metres east, north and up from the frame's origin (float64; the caller casts). */
export function offset(f: Frame, mx: number, my: number, z: number, out: [number, number, number] | Float32Array | Float64Array, i = 0): void {
	out[i] = (mx - f.ox) / f.k;
	out[i + 1] = -(my - f.oy) / f.k;
	out[i + 2] = z - f.oz;
}

/** Project metres-from-origin to CSS px with the float64 matrix; false when behind the camera (`out.w` is set either way). */
export function projectLocal(f: Frame, e: number, n: number, u: number, out: { x: number; y: number; w: number }): boolean {
	const m = f.m64;
	const w = m[3] * e + m[7] * n + m[11] * u + m[15];
	out.w = w;
	if (!(w > 0)) return false;
	out.x = (((m[0] * e + m[4] * n + m[8] * u + m[12]) / w + 1) / 2) * f.width;
	out.y = ((1 - (m[1] * e + m[5] * n + m[9] * u + m[13]) / w) / 2) * f.height;
	out.w = w;
	return true;
}

/** Project with the float32 matrix and float32 inputs, as the GPU does (for tests). */
export function projectLocal32(f: Frame, e: number, n: number, u: number, out: { x: number; y: number }): boolean {
	const m = f.m32;
	const r = Math.fround;
	const [fe, fn, fu] = [r(e), r(n), r(u)];
	const w = r(r(r(m[3] * fe) + r(m[7] * fn)) + r(r(m[11] * fu) + m[15]));
	if (!(w > 0)) return false;
	const x = r(r(r(m[0] * fe) + r(m[4] * fn)) + r(r(m[8] * fu) + m[12]));
	const y = r(r(r(m[1] * fe) + r(m[5] * fn)) + r(r(m[9] * fu) + m[13]));
	out.x = ((x / w + 1) / 2) * f.width;
	out.y = ((1 - y / w) / 2) * f.height;
	return true;
}

/** What plain float32 Mercator would give (mainMatrix cast to float32, Mercator inputs in float32): the jitter RTC avoids. */
export function projectMercator32(main: Mat4, mx: number, my: number, z: number, lat: number, width: number, height: number, out: { x: number; y: number }): boolean {
	const r = Math.fround;
	const m = Float32Array.from(main as ArrayLike<number>);
	const [x0, y0, z0] = [r(mx), r(my), r(z / circumferenceAt(lat))];
	const w = r(r(r(m[3] * x0) + r(m[7] * y0)) + r(r(m[11] * z0) + m[15]));
	if (!(w > 0)) return false;
	const x = r(r(r(m[0] * x0) + r(m[4] * y0)) + r(r(m[8] * z0) + m[12]));
	const y = r(r(r(m[1] * x0) + r(m[5] * y0)) + r(r(m[9] * z0) + m[13]));
	out.x = ((x / w + 1) / 2) * width;
	out.y = ((1 - y / w) / 2) * height;
	return true;
}
