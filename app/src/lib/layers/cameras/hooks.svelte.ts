import type { CameraDetail, CameraDetailView } from './detail.js';

/**
 * What later packages plug into the camera window (WP12 builds the window;
 * WP13 adds look-through and the photo in the cone, WP14 calibrating on the
 * map). Until one is set, its button is disabled with the reason, or absent
 * (the 3D photo), so the window never offers what doesn't exist yet.
 */
export interface CameraHooks {
	/** Look through a calibrated view (WP13: the view stack, true-scale terrain, the camera's pose). */
	lookThrough: ((camera: CameraDetail, view: CameraDetailView) => void) | null;
	/** The photo in the cone for an open window, on or off (WP13). */
	photo: { isOn(cameraId: number): boolean; set(cameraId: number, on: boolean): void } | null;
}

export const cameraHooks: CameraHooks = $state({ lookThrough: null, photo: null });

/** Why look-through can't be used for this view, or null when it can. */
export function lookThroughBlocked(o: { calibrated: boolean; sizeChanged: string | null; available: boolean }): string | null {
	if (!o.calibrated) return 'Not calibrated yet: configure it first';
	if (o.sizeChanged) return o.sizeChanged;
	if (!o.available) return 'Look-through arrives with the 3D cameras';
	return null;
}
