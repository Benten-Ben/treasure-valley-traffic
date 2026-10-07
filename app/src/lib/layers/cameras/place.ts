import { BESIDE_PX, LEFT_COLUMN, MARGIN, RIGHT_COLUMN, type Layout, type Rect } from '#lib/state/windows.svelte.js';

/**
 * Where a camera click takes the map, and where its window opens (docs/14
 * §14.6 "Camera windows"; the owner's Q2 answer: a single click flies to the
 * camera and opens its window). Pure.
 */
export const FLY_ZOOM = 18;
export const FLY_PITCH = 50;

/** Window keys: one window per camera. */
export const cameraKey = (id: number) => `camera:${id}`;

export function cameraIdOf(key: string): number | null {
	const m = /^camera:(\d+)$/.exec(key);
	return m ? Number(m[1]) : null;
}

/** The fly to a camera: zoom 18, keeping the bearing, pitch 50. */
export function flyTarget(at: [number, number], bearing: number) {
	return { center: at, zoom: FLY_ZOOM, bearing, pitch: FLY_PITCH, essential: true };
}

export interface Padding {
	top?: number;
	right?: number;
	bottom?: number;
	left?: number;
}

/**
 * Where the map's centre is on screen (viewport px): the middle of the area
 * the padding leaves, which is where a fly puts the camera. Its window opens
 * beside this point.
 */
export function paddedCentre(box: { left: number; top: number; width: number; height: number }, p: Padding) {
	const { top = 0, right = 0, bottom = 0, left = 0 } = p;
	return {
		x: Math.round(box.left + left + (box.width - left - right) / 2),
		y: Math.round(box.top + top + (box.height - top - bottom) / 2)
	};
}

/** Room kept between a landed camera and the edges of the free middle, px. */
const LANDING_MARGIN = 48;

/**
 * Where on screen a flown-to camera should land (viewport px), or null for
 * the map's centre:
 *
 * - on a desktop, in the free middle between the legend column and the
 *   inspect column, far enough left that its window (24 px beside it, the
 *   side away from the screen centre) fits between it and the inspect card;
 * - on a phone, in the middle of the map left above the sheet (which a
 *   window lifts to 55%).
 */
export function landing(box: { left: number; top: number; width: number; height: number }, windowWidth: number, layout: Layout): { x: number; y: number } | null {
	const midY = Math.round(box.top + box.height / 2);
	if (layout === 'phone') return { x: Math.round(box.left + box.width / 2), y: Math.round(box.top + 0.27 * box.height) };
	if (layout !== 'desktop') return null;
	const left = box.left + LEFT_COLUMN;
	const right = box.left + box.width - RIGHT_COLUMN;
	const need = windowWidth + BESIDE_PX;
	if (right - left < need + LANDING_MARGIN) return null;
	return { x: Math.round(left + (right - left - need) / 2), y: midY };
}

/**
 * Where a camera should land beside its open window (Fly to, or a click on
 * a camera whose window is open): 24 px left of the window, or right of it
 * when there's no room on the left; level with the window's middle, clear of
 * the bars.
 */
export function landBeside(rect: Rect, box: { left: number; top: number; width: number; height: number }): { x: number; y: number } {
	const minX = box.left + MARGIN + 8;
	const maxX = box.left + box.width - MARGIN - 8;
	const left = rect.x - BESIDE_PX;
	const right = rect.x + rect.w + BESIDE_PX;
	const x = left >= minX ? left : right <= maxX ? right : box.left + box.width / 2;
	const y = Math.min(Math.max(rect.y + rect.h / 2, box.top + 90), box.top + box.height - 120);
	return { x: Math.round(x), y: Math.round(y) };
}
