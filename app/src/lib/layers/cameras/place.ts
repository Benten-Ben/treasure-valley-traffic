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
