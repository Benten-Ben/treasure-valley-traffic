/**
 * Zoom and pan inside a camera picture (docs/14 §14.6, "Camera windows": the
 * wheel zooms up to 4×, a drag pans, a double-click resets). Pure: the
 * picture is drawn with `transform: translate(x, y) scale(s)` from its top
 * left, inside a box `w` × `h` that it fills at scale 1, and it never shows
 * anything outside itself.
 */
export interface ZoomState {
	/** Scale, 1 to MAX_ZOOM. */
	s: number;
	/** Offset of the picture's top left, px (≤ 0). */
	x: number;
	y: number;
}

export const MAX_ZOOM = 4;
export const IDENTITY: ZoomState = { s: 1, x: 0, y: 0 };
/** Zoom per wheel notch (100 px of deltaY). */
export const WHEEL_STEP = 1.25;

/** Keep the picture covering the box: offsets between w·(1 − s) and 0. */
export function clampZoom(z: ZoomState, w: number, h: number): ZoomState {
	const s = Math.min(MAX_ZOOM, Math.max(1, z.s));
	const x = Math.min(0, Math.max(w * (1 - s), z.x));
	const y = Math.min(0, Math.max(h * (1 - s), z.y));
	return { s, x: x || 0, y: y || 0 };
}

/** Zoom by `factor` about the box point (px, py), which stays put. */
export function zoomAt(z: ZoomState, factor: number, px: number, py: number, w: number, h: number): ZoomState {
	const s = Math.min(MAX_ZOOM, Math.max(1, z.s * factor));
	const k = s / z.s;
	return clampZoom({ s, x: px - (px - z.x) * k, y: py - (py - z.y) * k }, w, h);
}

/** The factor for a wheel event's deltaY (in px; lines are about 40 px). */
export function wheelFactor(deltaY: number): number {
	return WHEEL_STEP ** (-deltaY / 100);
}

/** Pan by (dx, dy) px. */
export function panBy(z: ZoomState, dx: number, dy: number, w: number, h: number): ZoomState {
	return clampZoom({ s: z.s, x: z.x + dx, y: z.y + dy }, w, h);
}

export const isIdentity = (z: ZoomState) => z.s === 1 && z.x === 0 && z.y === 0;
