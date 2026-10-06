/**
 * The overlay's projection, on the CPU in float64 (docs/14 §14.8, "The
 * overlay"). Each anchor (lon, lat, and its ground elevation as MapLibre
 * reports it, exaggeration included) goes through the frame's `mainMatrix`,
 * the custom-layer matrix that takes Web Mercator x and y in [0, 1] and z in
 * Mercator units at the centre's latitude. That is exactly what
 * `map.project` does with its own 3D pixel matrix, so sprites sit where
 * `map.project` says, terrain included.
 */

/** MapLibre's earth radius (metres). */
export const EARTH_RADIUS = 6371008.8;

export function mercatorX(lng: number): number {
	return (180 + lng) / 360;
}

export function mercatorY(lat: number): number {
	return (180 - (180 / Math.PI) * Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360))) / 360;
}

/** Metres per Mercator unit at a latitude (MapLibre's circumferenceAtLatitude). */
export function circumferenceAt(lat: number): number {
	return 2 * Math.PI * EARTH_RADIUS * Math.cos((lat * Math.PI) / 180);
}

/** A 4×4 column-major matrix (gl-matrix layout), ideally Float64Array. */
export type Mat4 = ArrayLike<number>;

/**
 * Project one anchor to CSS pixels. `zScale` is 1 / circumferenceAt(centre
 * latitude). Returns false (and leaves `out` alone) when the point is behind
 * the camera.
 */
export function projectTo(
	out: { x: number; y: number },
	m: Mat4,
	mx: number,
	my: number,
	elevation: number,
	zScale: number,
	width: number,
	height: number
): boolean {
	const mz = elevation * zScale;
	const w = m[3] * mx + m[7] * my + m[11] * mz + m[15];
	if (!(w > 0)) return false;
	const x = (m[0] * mx + m[4] * my + m[8] * mz + m[12]) / w;
	const y = (m[1] * mx + m[5] * my + m[9] * mz + m[13]) / w;
	out.x = ((x + 1) / 2) * width;
	out.y = ((1 - y) / 2) * height;
	return true;
}

/** Screen pixels per second for something moving `metresPerSecond` at a zoom and latitude (512 px tiles). */
export function pxPerSecond(metresPerSecond: number, zoom: number, lat: number): number {
	const metresPerPx = circumferenceAt(lat) / (512 * 2 ** zoom);
	return metresPerSecond / metresPerPx;
}
